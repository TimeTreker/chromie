from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.app.capabilities.loader import build_configured_registry
from agent.app.capabilities.validator import validate_args_for_schema
from agent.app.tool_invocation import (
    AsyncToolInvoker,
    McpStreamableHttpInvoker,
    ToolInvocationContext,
)
from shared.chromie_contracts.plan import (
    FastPlannerVocalActivity,
    render_fast_planner_vocal_activity,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
    output_schema_sha256,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
)

from .capability_runtime import (
    CapabilityDispatchReceipt,
    LocalSpeechCapabilityProvider,
    MediaPlaybackCapabilityProvider,
    RuntimeAuthorization,
    SessionControlCapabilityProvider,
    CapabilityRegistry,
    CapabilityRuntime,
    CapabilityRuntimeResult,
    VocalPerformanceCapabilityProvider,
    local_speech_definition,
    media_playback_definitions,
    session_interrupt_definition,
    vocal_performance_definition,
)
from .capability_adapters import (
    TaskGraphCancelHandler,
    TaskGraphHandler,
    TaskGraphCapabilityProvider,
    task_graph_capability_definition,
)
from .soridormi_capability_provider import (
    SoridormiCapabilityProvider,
    import_soridormi_capability_catalog,
)
from .agent_tool_provider import (
    AgentToolHandler,
    AgentToolCapabilityProvider,
    local_agent_tool_definitions,
)
from .conversation_memory_provider import (
    ConversationMemoryHandler,
    ConversationMemoryCapabilityProvider,
    host_runtime_memory_definitions,
)
from .interaction_preflight import annotate_preflight_validation
from .task_proposals import annotate_task_proposal_ledger

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
SpeechCancelScheduler = Callable[
    [CapabilityRequest, dict[str, Any]],
    None | Awaitable[None],
]
_TASK_GRAPH_CAPABILITY_ID = "chromie.task_graph.execute"


def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


@dataclass
class ReadyPlannerVocalExecution:
    """One Fast-Planner-authored conversational Activity entering the Vocal lane."""

    activity: FastPlannerVocalActivity
    interaction_id: str
    speech: InteractionSpeech
    task: asyncio.Task[CapabilityRuntimeResult]


@dataclass
class CapabilityInteractionDispatch:
    """Detached cognitive Capability dispatch owned by the trusted Runtime.

    This is a bounded Host integration handle, not a second execution owner.
    ``receipt`` remains the CapabilityRuntime authority for live provider work;
    ``source_response`` retains the immutable cognitive Plan/request commitments
    needed for later Evidence reconciliation and cognitive re-entry.
    """

    source_response: InteractionResponse
    runtime_response: InteractionResponse
    receipt: CapabilityDispatchReceipt | None
    immediate_execution: CapabilityRuntimeResult | None
    preexecuted_results: list[CapabilityResult]
    preexecuted_traces: list[CapabilityTrace]


@dataclass
class InteractionRuntimeCoordinator:
    """Host integration boundary for InteractionResponse execution."""

    def __init__(
        self,
        speech_scheduler: SpeechScheduler,
        *,
        speech_cancel_scheduler: SpeechCancelScheduler | None = None,
        soridormi_invoker: AsyncToolInvoker | None = None,
        task_graph_handler: TaskGraphHandler | None = None,
        task_graph_cancel_handler: TaskGraphCancelHandler | None = None,
        agent_tool_handler: AgentToolHandler | None = None,
        conversation_memory_handler: ConversationMemoryHandler | None = None,
        vocal_provider: VocalPerformanceCapabilityProvider | None = None,
        media_provider: MediaPlaybackCapabilityProvider | None = None,
        capability_manifest_paths: str | None = None,
        max_concurrency: int | None = None,
        catalog_refresh_ttl_s: float | None = None,
        interaction_ledger: Any | None = None,
    ) -> None:
        self.registry = CapabilityRegistry()
        self.registry.register(local_speech_definition())
        self.registry.register(session_interrupt_definition())
        self.registry.register(task_graph_capability_definition())
        self.runtime = CapabilityRuntime(
            self.registry,
            max_concurrency=max(
                1,
                int(
                    max_concurrency
                    if max_concurrency is not None
                    else os.getenv("ORCH_CAPABILITY_MAX_CONCURRENCY", "8")
                ),
            ),
        )
        self.runtime.register_provider(
            LocalSpeechCapabilityProvider(
                speech_scheduler,
                speech_cancel_scheduler,
            )
        )
        if vocal_provider is not None:
            self.registry.register(vocal_performance_definition(vocal_provider.declaration))
            self.runtime.register_provider(vocal_provider)
        if media_provider is not None:
            for definition in media_playback_definitions(media_provider.declaration):
                self.registry.register(definition)
            self.runtime.register_provider(media_provider)
        self.runtime.register_provider(SessionControlCapabilityProvider())
        if agent_tool_handler is not None:
            definitions = local_agent_tool_definitions(capability_manifest_paths)
            for definition in definitions:
                self.registry.register(definition)
            if definitions:
                self.runtime.register_provider(AgentToolCapabilityProvider(agent_tool_handler))
        if conversation_memory_handler is not None:
            memory_definitions = host_runtime_memory_definitions(capability_manifest_paths)
            for definition in memory_definitions:
                self.registry.register(definition)
            if memory_definitions:
                self.runtime.register_provider(
                    ConversationMemoryCapabilityProvider(conversation_memory_handler)
                )
        self._task_graph_enabled = task_graph_handler is not None
        if task_graph_handler is not None:
            self.runtime.register_provider(
                TaskGraphCapabilityProvider(
                    task_graph_handler,
                    task_graph_cancel_handler,
                )
            )
        self.soridormi_invoker = soridormi_invoker
        self._catalog_loaded = False
        self._catalog_last_loaded_at: float | None = None
        self._catalog_refresh_ttl_s = (
            max(0.0, float(catalog_refresh_ttl_s))
            if catalog_refresh_ttl_s is not None
            else _float_env(
                "ORCH_SORIDORMI_CATALOG_REFRESH_TTL_S",
                30.0,
            )
        )
        self._catalog_lock = asyncio.Lock()
        self.interaction_ledger = interaction_ledger
        self._preexecuted: dict[tuple[str, str], tuple[CapabilityResult, CapabilityTrace | None]] = {}

    async def ensure_capability_definitions(self, capability_ids: Iterable[str]) -> None:
        """Refresh provider-backed definitions needed for a canonical plan.

        This is a deterministic catalog operation. It does not authorize or
        execute any requested skill.
        """

        normalized = [str(item).strip() for item in capability_ids if str(item).strip()]
        body_ids = [item for item in normalized if item.startswith("soridormi.")]
        if body_ids:
            await self._ensure_soridormi_catalog(required_capability_ids=body_ids)
        for capability_id in normalized:
            self.registry.get(capability_id)

    def capability_definition(self, capability_id: str):
        return self.registry.get(capability_id)

    async def start_fast_planner_vocal_activity(
        self,
        activity: FastPlannerVocalActivity,
        *,
        session_id: str,
        turn_id: str,
        language: str,
    ) -> ReadyPlannerVocalExecution:
        """Start one planner-authored immediate conversational Activity.

        This path carries no canonical Goal or completion authority.  It exists so
        a safe progress/clarification act may begin while Goal Association or
        deeper planning continues in parallel.
        """

        text = render_fast_planner_vocal_activity(activity, language=language)
        speech = InteractionSpeech(
            id=f"fast_activity_speech_{activity.activity_id}",
            text=text,
            timing="immediate",
            style="brief",
            priority="normal",
            interruptible=True,
            metadata={
                "source": "fast_planner_advance",
                "phase": "fast_planner_immediate",
                "speech_act": activity.speech_act,
                "turn_id": turn_id,
                "session_id": session_id,
                "language": language,
                "fast_activity_id": activity.activity_id,
                "source_responsibility_refs": list(activity.source_responsibility_refs),
                "canonical_goal_binding_pending": True,
                "goal_completion_authority": False,
                "execution_lane": "vocal",
                "delivery_role": activity.role,
                "wait_for_playback_start": True,
                "playback_start_required_for_delivery": True,
            },
        )
        interaction_id = f"fast_advance_{turn_id}_{activity.activity_id}"
        response = InteractionResponse(
            interaction_id=interaction_id,
            status="ok",
            speech=[speech],
            metadata={
                "source": "fast_planner_advance",
                "turn_id": turn_id,
                "session_id": session_id,
                "language": language,
                "fast_activity_id": activity.activity_id,
                "source_responsibility_refs": list(activity.source_responsibility_refs),
                "canonical_goal_binding_pending": True,
                "goal_completion_authority": False,
            },
        )
        task = asyncio.create_task(self._dispatch_to_terminal(response))

        def observe_completion(completed: asyncio.Task[CapabilityRuntimeResult]) -> None:
            if completed.cancelled():
                return
            exc = completed.exception()
            if exc is not None:  # delivery failure is evidence, not semantic replanning
                logger.warning(
                    "fast_planner_vocal_activity_failed turn_id=%s activity_id=%s "
                    "error_type=%s error=%s",
                    turn_id,
                    activity.activity_id,
                    type(exc).__name__,
                    exc,
                )

        task.add_done_callback(observe_completion)
        return ReadyPlannerVocalExecution(activity, interaction_id, speech, task)

    def _consume_preexecuted(
        self, response: InteractionResponse
    ) -> tuple[InteractionResponse, list[CapabilityResult], list[CapabilityTrace]]:
        consumed_results: list[CapabilityResult] = []
        consumed_traces: list[CapabilityTrace] = []
        remaining_skills: list[CapabilityRequest] = []
        remaining_speech: list[InteractionSpeech] = []

        def consume(request_id: str) -> bool:
            seeded = self._preexecuted.pop(
                (response.interaction_id, request_id),
                None,
            )
            if seeded is None:
                return False
            result, trace = seeded
            consumed_results.append(result)
            if trace is not None:
                consumed_traces.append(trace)
            return True

        for request in response.capabilities:
            if not consume(request.request_id):
                remaining_skills.append(request)
        for speech in response.speech:
            if not consume(speech.id):
                remaining_speech.append(speech)
        if (
            len(remaining_skills) == len(response.capabilities)
            and len(remaining_speech) == len(response.speech)
        ):
            return response, consumed_results, consumed_traces
        return (
            response.model_copy(
                deep=True,
                update={
                    "capabilities": remaining_skills,
                    "speech": remaining_speech,
                },
            ),
            consumed_results,
            consumed_traces,
        )

    async def submit_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> CapabilityInteractionDispatch:
        """Prepare and submit one InteractionResponse without joining providers.

        This is the only maintained coordinator dispatch boundary.  It returns
        after Runtime acceptance; callers that genuinely need terminal delivery
        must join explicitly with :meth:`wait_dispatch`.  Cognitive effectful
        responses additionally defer planner-authored terminal wording until
        terminal Evidence exists.
        """

        raw_body_requests = [
            request
            for request in response.capabilities
            if request.capability_id.startswith("soridormi.")
        ]
        if raw_body_requests:
            try:
                await self._ensure_soridormi_catalog(
                    required_capability_ids=(
                        request.capability_id for request in raw_body_requests
                    ),
                )
            except RuntimeError as exc:
                failed = await self._body_setup_failure(
                    response,
                    raw_body_requests,
                    session_id=session_id,
                    reason_code=(
                        "provider_disabled"
                        if self.soridormi_invoker is None
                        else "catalog_unavailable"
                    ),
                    message=str(exc),
                )
                return CapabilityInteractionDispatch(
                    source_response=response,
                    runtime_response=response.model_copy(
                        deep=True,
                        update={"speech": []},
                    ),
                    receipt=None,
                    immediate_execution=failed,
                    preexecuted_results=[],
                    preexecuted_traces=[],
                )

        prepared = self.prepare_response(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        if self.interaction_ledger is not None:
            envelope = prepared.metadata.get("user_turn_envelope")
            turn_id = (
                str(envelope.get("turn_id") or "").strip()
                if isinstance(envelope, dict)
                else ""
            ) or prepared.interaction_id
            self.interaction_ledger.record_committed_requests(
                session_id=str(session_id or turn_id),
                turn_id=turn_id,
                interaction_id=prepared.interaction_id,
                requests=prepared.capabilities,
            )

        if prepared.status == "error" and not prepared.capabilities and not prepared.speech:
            return CapabilityInteractionDispatch(
                source_response=prepared,
                runtime_response=prepared,
                receipt=None,
                immediate_execution=CapabilityRuntimeResult(
                    interaction_id=prepared.interaction_id,
                    status="failed",
                ),
                preexecuted_results=[],
                preexecuted_traces=[],
            )

        body_requests = [
            request
            for request in prepared.capabilities
            if request.capability_id.startswith("soridormi.")
        ]
        task_graph_requests = [
            request
            for request in prepared.capabilities
            if request.capability_id == _TASK_GRAPH_CAPABILITY_ID
        ]
        if task_graph_requests and not self._task_graph_enabled:
            failed = await self._body_setup_failure(
                prepared,
                task_graph_requests,
                session_id=session_id,
                reason_code="task_graph_execution_disabled",
                message=(
                    "InteractionResponse requested a TaskGraph, but host "
                    "TaskGraph execution is disabled"
                ),
            )
            return CapabilityInteractionDispatch(
                source_response=prepared,
                runtime_response=prepared.model_copy(deep=True, update={"speech": []}),
                receipt=None,
                immediate_execution=failed,
                preexecuted_results=[],
                preexecuted_traces=[],
            )
        if body_requests:
            unavailable = [
                request
                for request in body_requests
                if not self.registry.get(request.capability_id).available
            ]
            if unavailable:
                definition = self.registry.get(unavailable[0].capability_id)
                failed = await self._body_setup_failure(
                    prepared,
                    body_requests,
                    session_id=session_id,
                    reason_code="capability_unavailable",
                    message=definition.unavailable_reason or "unavailable",
                )
                return CapabilityInteractionDispatch(
                    source_response=prepared,
                    runtime_response=prepared.model_copy(
                        deep=True,
                        update={"speech": []},
                    ),
                    receipt=None,
                    immediate_execution=failed,
                    preexecuted_results=[],
                    preexecuted_traces=[],
                )

        # Result-dependent completion speech cannot be truthful before terminal
        # Evidence.  Any response that also dispatches capabilities therefore
        # drops pre-authored ``after_capabilities`` wording from the executable
        # response. Cognitive result re-entry may compose grounded follow-up;
        # non-cognitive/internal dispatch stays silent rather than inventing a
        # completion claim.
        deferred_speech_ids = [
            speech.id
            for speech in prepared.speech
            if speech.timing == "after_capabilities"
        ] if prepared.capabilities else []
        runtime_response = prepared.model_copy(
            deep=True,
            update={
                "speech": [
                    speech
                    for speech in prepared.speech
                    if speech.id not in set(deferred_speech_ids)
                ],
                "metadata": {
                    **prepared.metadata,
                    **(
                        {
                            "result_deferred_speech_ids": deferred_speech_ids,
                            "result_deferred_speech_reason": (
                                "terminal_evidence_owns_result_wording"
                            ),
                        }
                        if deferred_speech_ids
                        else {}
                    ),
                },
            },
        )
        runtime_response, preexecuted_results, preexecuted_traces = (
            self._consume_preexecuted(runtime_response)
        )
        if not runtime_response.capabilities and not runtime_response.speech:
            merged = CapabilityRuntimeResult(
                interaction_id=prepared.interaction_id,
                status=(
                    "completed"
                    if (
                        not preexecuted_results
                        or all(
                            item.status == "completed"
                            for item in preexecuted_results
                        )
                    )
                    else "failed"
                ),
                results=list(preexecuted_results),
                traces=list(preexecuted_traces),
            )
            return CapabilityInteractionDispatch(
                source_response=prepared,
                runtime_response=runtime_response,
                receipt=None,
                immediate_execution=merged,
                preexecuted_results=[],
                preexecuted_traces=[],
            )

        receipt = await self.runtime.submit(
            runtime_response,
            authorization=RuntimeAuthorization(
                confirmed_request_ids=set(confirmed_request_ids or ()),
            ),
        )
        return CapabilityInteractionDispatch(
            source_response=prepared,
            runtime_response=runtime_response,
            receipt=receipt,
            immediate_execution=None,
            preexecuted_results=preexecuted_results,
            preexecuted_traces=preexecuted_traces,
        )

    async def wait_dispatch(
        self,
        dispatch: CapabilityInteractionDispatch,
    ) -> CapabilityRuntimeResult:
        """Explicitly join one accepted coordinator dispatch when terminal truth is required."""

        if dispatch.immediate_execution is not None:
            return dispatch.immediate_execution
        if dispatch.receipt is None:
            raise RuntimeError("capability interaction dispatch has no Runtime receipt")
        execution = await self.runtime.wait_terminal(dispatch.receipt)
        if not dispatch.preexecuted_results:
            return execution
        merged_results = [*dispatch.preexecuted_results, *execution.results]
        merged_traces = [*dispatch.preexecuted_traces, *execution.traces]
        return execution.model_copy(
            update={
                "results": merged_results,
                "traces": merged_traces,
                "status": (
                    "completed"
                    if merged_results
                    and all(item.status == "completed" for item in merged_results)
                    else execution.status
                ),
            }
        )

    async def _dispatch_to_terminal(
        self,
        response: InteractionResponse,
        *,
        authorization: RuntimeAuthorization | None = None,
    ) -> CapabilityRuntimeResult:
        """Private explicit join for bounded internal delivery/acceptance paths."""

        receipt = await self.runtime.submit(response, authorization=authorization)
        return await self.runtime.wait_terminal(receipt)

    def prepare_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> InteractionResponse:
        return annotate_task_proposal_ledger(
            annotate_preflight_validation(
                self._reconcile_truth(
                    self._enforce_structured_planning_state(
                        self._with_session_metadata(response, session_id)
                    ),
                    session_id=session_id,
                ),
                registry=self.registry,
                provider_ids=self.runtime.provider_ids(),
                confirmed_request_ids=confirmed_request_ids,
                soridormi_catalog_loaded=self._catalog_loaded,
            )
        )

    def _enforce_structured_planning_state(
        self,
        response: InteractionResponse,
    ) -> InteractionResponse:
        """Prevent effectful execution when the structured planner blocked it.

        This does not interpret user language or choose an alternative. It only
        enforces the planner's structured decision so a partially accumulated
        skill cannot survive a clarification/unavailable result.
        """

        metadata = response.metadata if isinstance(response.metadata, dict) else {}
        planning_result = str(metadata.get("planning_result") or "").strip()
        capability_decision = str(metadata.get("capability_decision") or "").strip()
        blocked = planning_result in {
            "needs_clarification",
            "unavailable",
            "blocked",
        } or capability_decision in {"clarify", "unsupported", "blocked"}
        if not blocked:
            return response
        effectful = [request for request in response.capabilities if request.capability_id != "chromie.speak"]
        if not effectful:
            return response
        return response.model_copy(
            deep=True,
            update={
                "capabilities": [
                    request for request in response.capabilities if request.capability_id == "chromie.speak"
                ],
                "requires_confirmation": False,
                "metadata": {
                    **metadata,
                    "structured_planning_execution_suppressed": True,
                    "suppressed_capability_ids": [request.capability_id for request in effectful],
                },
            },
        )

    async def _body_setup_failure(
        self,
        response: InteractionResponse,
        body_requests: list[CapabilityRequest],
        *,
        session_id: str | None,
        reason_code: str,
        message: str,
    ) -> CapabilityRuntimeResult:
        """Return terminal provider-setup Evidence without inventing speech.

        The trusted coordinator owns lifecycle truth, not semantic recovery
        wording.  Cognitive result interpretation may decide what to say after
        this failure becomes canonical Evidence.
        """

        del session_id
        return CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=request.capability_version,
                    status="failed",
                    provider_id="soridormi.mcp",
                    reason_code=reason_code,
                    message=message,
                )
                for request in body_requests
            ],
        )

    async def confirmation_request_ids(
        self,
        response: InteractionResponse,
    ) -> set[str]:
        body_requests = [
            request for request in response.capabilities if request.capability_id.startswith("soridormi.")
        ]
        if body_requests:
            await self._ensure_soridormi_catalog(
                required_capability_ids=(request.capability_id for request in body_requests),
            )

        required = {
            request.request_id
            for request in response.capabilities
            if request.requires_confirmation
            or self.registry.get(request.capability_id).requires_confirmation
        }
        if response.requires_confirmation and not required:
            required.update(request.request_id for request in response.capabilities)
        return required

    async def cancel_all(self) -> None:
        await self.runtime.cancel_all()

    async def cancel_scope(
        self,
        directive: CancellationDirective,
    ) -> CancellationDispatchReceipt:
        return await self.runtime.cancel_scope(directive)

    async def emergency_stop(self, *, reason: str) -> dict[str, Any]:
        """Dispatch Soridormi's dedicated E-stop without model mediation."""

        if self.soridormi_invoker is None:
            return {
                "status": "unavailable",
                "tool": "soridormi.safety.emergency_stop",
                "reason": "soridormi_invoker_disabled",
            }
        try:
            outcome = await self.soridormi_invoker.invoke(
                "soridormi.safety.emergency_stop",
                {"reason": str(reason or "cognitive_gateway_emergency_stop")},
                context=ToolInvocationContext(allow_safety_controls=True),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "tool": "soridormi.safety.emergency_stop",
                "error": f"{type(exc).__name__}:{exc}",
            }
        output = dict(outcome.output or {})
        required_postconditions = ("stopped", "emergency", "safe_idle")
        postcondition_confirmed = outcome.status == "success" and all(
            output.get(key) is True for key in required_postconditions
        )
        if outcome.status == "success" and not postcondition_confirmed:
            return {
                "status": "unconfirmed",
                "provider_status": outcome.status,
                "tool": "soridormi.safety.emergency_stop",
                "output": output,
                "reason": "emergency_stop_postcondition_unconfirmed",
                "required_postconditions": list(required_postconditions),
                "error": outcome.error,
            }
        return {
            "status": outcome.status,
            "tool": "soridormi.safety.emergency_stop",
            "output": output,
            "postcondition_confirmed": postcondition_confirmed,
            "error": outcome.error,
        }

    async def refresh_soridormi_catalog(self, *, force: bool = True) -> None:
        await self._ensure_soridormi_catalog(force=force)

    async def _ensure_soridormi_catalog(
        self,
        *,
        force: bool = False,
        required_capability_ids: Iterable[str] | None = None,
    ) -> None:
        required = set(required_capability_ids or ())
        if self.soridormi_invoker is None:
            raise RuntimeError(
                "InteractionResponse requested a Soridormi capability, but "
                "ORCH_ENABLE_SORIDORMI_CAPABILITIES is disabled"
            )
        if not self._should_refresh_soridormi_catalog(
            force=force,
            required_capability_ids=required,
        ):
            return
        async with self._catalog_lock:
            if not self._should_refresh_soridormi_catalog(
                force=force,
                required_capability_ids=required,
            ):
                return
            outcome = await self.soridormi_invoker.invoke(
                "soridormi.skill.list",
                {},
            )
            if outcome.status != "success":
                raise RuntimeError(outcome.error or "Soridormi named-capability catalog lookup failed")
            provider_skills = outcome.output.get("skills")
            if not isinstance(provider_skills, list):
                raise RuntimeError("Soridormi named-capability catalog response has no skills list")
            import_soridormi_capability_catalog(self.registry, provider_skills)
            if "soridormi.mcp" not in self.runtime.provider_ids():
                self.runtime.register_provider(SoridormiCapabilityProvider(self.soridormi_invoker))
            self._catalog_loaded = True
            self._catalog_last_loaded_at = time.monotonic()

            missing = self._missing_soridormi_capability_ids(required)
            if missing:
                raise RuntimeError(
                    "Soridormi named-capability catalog did not include requested "
                    f"capabilities: {', '.join(sorted(missing))}"
                )

    def _should_refresh_soridormi_catalog(
        self,
        *,
        force: bool,
        required_capability_ids: set[str],
    ) -> bool:
        if force or not self._catalog_loaded:
            return True
        if self._required_soridormi_capabilities_need_refresh(required_capability_ids):
            return True
        if self._catalog_refresh_ttl_s <= 0:
            return True
        if self._catalog_last_loaded_at is None:
            return True
        return (time.monotonic() - self._catalog_last_loaded_at) >= self._catalog_refresh_ttl_s

    def _required_soridormi_capabilities_need_refresh(
        self,
        capability_ids: Iterable[str],
    ) -> bool:
        for capability_id in capability_ids:
            if not capability_id.startswith("soridormi."):
                continue
            try:
                definition = self.registry.get(capability_id)
            except ValueError:
                return True
            if definition.metadata.get("catalog_absent") is True:
                return True
        return False

    def _missing_soridormi_capability_ids(self, capability_ids: Iterable[str]) -> set[str]:
        missing: set[str] = set()
        for capability_id in capability_ids:
            if not capability_id.startswith("soridormi."):
                continue
            try:
                self.registry.get(capability_id)
            except ValueError:
                missing.add(capability_id)
        return missing

    def _with_session_metadata(
        self,
        response: InteractionResponse,
        session_id: str | None,
    ) -> InteractionResponse:
        return response.model_copy(
            deep=True,
            update={
                "speech": [
                    speech.model_copy(
                        update={
                            "metadata": {
                                **speech.metadata,
                                "session_id": session_id,
                            }
                        }
                    )
                    for speech in response.speech
                ]
            },
        )

    def _reconcile_truth(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
    ) -> InteractionResponse:
        proposed = self._int_metadata(
            response,
            "deepthinking_proposed_effect_task_count",
            fallback_key="deepthinking_proposed_action_count",
        )
        valid = self._int_metadata(
            response,
            "deepthinking_valid_effect_task_count",
            fallback_key="deepthinking_valid_action_count",
        )
        if proposed <= 0 or valid > 0:
            return response
        if self._has_effectful_runtime_skill(response):
            return response
        reason = str(response.metadata.get("truth_reconciliation_reason") or "").strip()
        if not reason:
            reason = "deepthinking_effect_task_without_valid_skill"
        metadata = {
            **response.metadata,
            "truth_reconciled": True,
            "truth_reconciliation_reason": reason,
        }
        if self._has_typed_supersession_evidence(response):
            metadata["truth_reconciliation_speech_source"] = "typed_superseded_proposal"
            return response.model_copy(deep=True, update={"metadata": metadata})

        metadata.update(
            {
                "truth_reconciliation_speech_source": "none_model_repair_required",
                "truth_reconciliation_requires_model_repair": True,
                "truth_reconciliation_session_id": session_id,
            }
        )
        return response.model_copy(
            deep=True,
            update={
                "speech": [],
                "capabilities": [],
                "status": "error",
                "reason": "truth_reconciliation_requires_model_repair",
                "metadata": metadata,
            },
        )

    @staticmethod
    def _has_typed_supersession_evidence(
        response: InteractionResponse,
    ) -> bool:
        if not response.speech:
            return False
        reason = str(response.metadata.get("truth_reconciliation_reason") or "").strip()
        superseded = response.metadata.get("superseded_task_proposals")
        if not reason or not isinstance(superseded, list) or not superseded:
            return False
        return all(
            isinstance(item, dict) and bool(str(item.get("superseded_by") or "").strip())
            for item in superseded
        )

    @staticmethod
    def _int_metadata(
        response: InteractionResponse,
        key: str,
        *,
        fallback_key: str | None = None,
    ) -> int:
        value = response.metadata.get(key)
        if value is None and fallback_key:
            value = response.metadata.get(fallback_key)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _has_effectful_runtime_skill(response: InteractionResponse) -> bool:
        for request in response.capabilities:
            if request.capability_id == "chromie.speak":
                continue
            metadata = request.metadata if isinstance(request.metadata, dict) else {}
            if "effectful" in metadata:
                if metadata.get("effectful") is True:
                    return True
                continue
            safety_class = str(metadata.get("safety_class") or "")
            effects = {str(item) for item in metadata.get("effects") or []}
            if safety_class in {
                "physical_motion",
                "safety_critical",
                "high_risk_action",
                "guarded_operation",
            }:
                return True
            if effects.intersection({"physical_motion", "safety_control", "emergency_stop"}):
                return True
            # Historical compatibility may lack capability metadata. Keep the
            # old body/task safety surface, but never classify arbitrary
            # chromie.* read-only tools as physical effects by name alone.
            if not metadata and (
                request.capability_id.startswith("soridormi.")
                or request.capability_id == _TASK_GRAPH_CAPABILITY_ID
                or request.capability_id == "session.interrupt"
            ):
                return True
        return False


def build_soridormi_invoker(
    *,
    manifest_path: str | Path,
) -> McpStreamableHttpInvoker:
    configured = build_configured_registry([str(manifest_path)])
    return McpStreamableHttpInvoker(configured.registry)
