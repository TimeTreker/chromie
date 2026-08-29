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
    FastPlannerCapabilityActivity,
    FastPlannerCommunicativeAct,
    fast_planner_activity_request_id,
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
    WorkDAGCancelHandler,
    WorkDAGHandler,
    WorkDAGCapabilityProvider,
    work_dag_capability_definition,
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

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
SpeechCancelScheduler = Callable[
    [CapabilityRequest, dict[str, Any]],
    None | Awaitable[None],
]
CommunicativeDeliveryRecorder = Callable[[str | None, str, dict[str, Any]], None]
CommunicativeGoalCompletionRecorder = Callable[
    [str | None, list[str], dict[str, Any]], None
]
_WORK_DAG_CAPABILITY_ID = "chromie.work_dag.execute"


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
class ReadyPlannerCommunicativeExecution:
    """One Planner-owned Communicative Activity entering the Vocal lane."""

    activity: FastPlannerCommunicativeAct
    interaction_id: str
    interaction_response: InteractionResponse
    speech: InteractionSpeech
    task: asyncio.Task[CapabilityRuntimeResult]


@dataclass
class ReadyFastPlannerCapabilityExecution:
    """Safe Fast Activities accepted while GA establishes canonical Goal IDs."""

    interaction_id: str
    turn_id: str
    activities: list[FastPlannerCapabilityActivity]
    dispatch: CapabilityInteractionDispatch
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
        work_dag_handler: WorkDAGHandler | None = None,
        work_dag_cancel_handler: WorkDAGCancelHandler | None = None,
        agent_tool_handler: AgentToolHandler | None = None,
        conversation_memory_handler: ConversationMemoryHandler | None = None,
        vocal_provider: VocalPerformanceCapabilityProvider | None = None,
        media_provider: MediaPlaybackCapabilityProvider | None = None,
        capability_manifest_paths: str | None = None,
        max_concurrency: int | None = None,
        catalog_refresh_ttl_s: float | None = None,
        interaction_ledger: Any | None = None,
        communicative_delivery_recorder: CommunicativeDeliveryRecorder | None = None,
        communicative_goal_completion_recorder: (
            CommunicativeGoalCompletionRecorder | None
        ) = None,
        speech_timeout_ms: int | None = None,
    ) -> None:
        self.registry = CapabilityRegistry()
        self.registry.register(local_speech_definition(timeout_ms=speech_timeout_ms))
        self.registry.register(session_interrupt_definition())
        self.registry.register(work_dag_capability_definition())
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
        self._work_dag_enabled = work_dag_handler is not None
        if work_dag_handler is not None:
            self.runtime.register_provider(
                WorkDAGCapabilityProvider(
                    work_dag_handler,
                    work_dag_cancel_handler,
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
        self.communicative_delivery_recorder = communicative_delivery_recorder
        self.communicative_goal_completion_recorder = (
            communicative_goal_completion_recorder
        )
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

    async def start_fast_planner_communicative_act(
        self,
        activity: FastPlannerCommunicativeAct,
        *,
        session_id: str,
        turn_id: str,
        language: str,
    ) -> ReadyPlannerCommunicativeExecution:
        """Start one Planner-worded Communicative Activity.

        This path carries no canonical Goal or completion authority.  It exists so
        a safe progress/clarification act may begin while Goal Association or
        deeper planning continues in parallel.
        """

        speech = InteractionSpeech(
            id=f"fast_activity_speech_{activity.activity_id}",
            text=activity.text,
            timing="immediate",
            style="brief",
            priority="normal",
            interruptible=True,
            metadata={
                "source": "fast_planner_advance",
                "wording_owner": "planner",
                "truth_stage": activity.truth_stage,
                "evidence_refs": list(activity.evidence_refs),
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
                "wait_for_voice_release": activity.role == "complete_response",
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
                return
            execution = completed.result()
            delivered = any(
                result.capability_id == "chromie.speak"
                and result.status == "completed"
                for result in execution.results
            )
            if not delivered or self.communicative_delivery_recorder is None:
                return
            try:
                self.communicative_delivery_recorder(
                    session_id,
                    activity.text,
                    {
                        "source": "fast_planner_communicative_delivery",
                        "turn_id": turn_id,
                        "fast_activity_id": activity.activity_id,
                        "delivery_role": activity.role,
                        "speech_act": activity.speech_act,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "truth_stage": activity.truth_stage,
                    },
                )
            except Exception as recorder_exc:  # delivery evidence must not crash Runtime
                logger.warning(
                    "fast_planner_vocal_delivery_record_failed turn_id=%s "
                    "activity_id=%s error_type=%s error=%s",
                    turn_id,
                    activity.activity_id,
                    type(recorder_exc).__name__,
                    recorder_exc,
                )

        task.add_done_callback(observe_completion)
        return ReadyPlannerCommunicativeExecution(
            activity,
            interaction_id,
            response,
            speech,
            task,
        )

    def bind_fast_planner_communicative_execution(
        self,
        execution: ReadyPlannerCommunicativeExecution,
        *,
        session_id: str | None,
        goal_ids_by_responsibility: dict[str, list[str]],
    ) -> list[str]:
        """Bind delivered Fast complete-response evidence to canonical Goal IDs.

        Fast Planner may start a safe Communicative Activity before Goal Association
        has produced canonical Goal identity.  Once GA is committed, this bridge
        attaches the already-running (or already-completed) ``chromie.speak``
        execution to the exact Goals owned by the Activity's Responsibility refs.
        Only a delivered ``complete_response`` can close a conversational Goal;
        progress/acknowledgement speech never receives completion authority.
        """

        activity = execution.activity
        if activity.role != "complete_response":
            return []
        goal_ids: list[str] = []
        for responsibility_ref in activity.source_responsibility_refs:
            raw_goal_ids = goal_ids_by_responsibility.get(responsibility_ref)
            if not isinstance(raw_goal_ids, list):
                continue
            for goal_id in raw_goal_ids:
                normalized = " ".join(str(goal_id or "").strip().split())
                if normalized and normalized not in goal_ids:
                    goal_ids.append(normalized)
        if not goal_ids or self.communicative_goal_completion_recorder is None:
            return goal_ids

        def reconcile_completion(
            completed: asyncio.Task[CapabilityRuntimeResult],
        ) -> None:
            if completed.cancelled():
                return
            exc = completed.exception()
            if exc is not None:
                return
            result = completed.result()
            delivered = any(
                item.capability_id == "chromie.speak" and item.status == "completed"
                for item in result.results
            )
            if not delivered:
                return
            try:
                self.communicative_goal_completion_recorder(
                    session_id,
                    goal_ids,
                    {
                        "source": "fast_planner_communicative_completion",
                        "turn_id": execution.speech.metadata.get("turn_id"),
                        "interaction_id": execution.interaction_id,
                        "fast_activity_id": activity.activity_id,
                        "delivery_role": activity.role,
                        "speech_act": activity.speech_act,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "source_goal_ids": list(goal_ids),
                    },
                )
            except Exception as recorder_exc:
                logger.warning(
                    "fast_planner_vocal_goal_completion_record_failed "
                    "activity_id=%s goal_ids=%s error_type=%s error=%s",
                    activity.activity_id,
                    goal_ids,
                    type(recorder_exc).__name__,
                    recorder_exc,
                )

        if execution.task.done():
            reconcile_completion(execution.task)
        else:
            execution.task.add_done_callback(reconcile_completion)
        return goal_ids


    async def start_fast_planner_capability_activities(
        self,
        activities: list[FastPlannerCapabilityActivity],
        *,
        session_id: str,
        turn_id: str,
    ) -> ReadyFastPlannerCapabilityExecution | None:
        """Accept safe, side-effect-free Fast Activities without waiting for GA.

        These requests initially retain GI Responsibility references.  Once GA
        returns, :meth:`bind_fast_planner_capability_execution` reindexes every
        still-open task into the canonical per-Goal task lists and seeds terminal
        Evidence into the final canonical response so Work is never executed twice.
        """

        if not activities:
            return None
        await self.ensure_capability_definitions(
            activity.capability_id for activity in activities
        )
        requests: list[CapabilityRequest] = []
        for activity in activities:
            definition = self.capability_definition(activity.capability_id)
            metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
            if (
                not definition.available
                or definition.requires_confirmation
                or str(metadata.get("safety_class") or "") != "safe_read"
                or metadata.get("side_effect_free") is not True
            ):
                raise ValueError(
                    "Fast execution before GA completes is limited to available, "
                    "side-effect-free safe-read Capabilities"
                )
            if activity.timing == "parallel":
                if not definition.can_run_parallel:
                    raise ValueError(
                        f"Capability {activity.capability_id!r} is not parallel-safe"
                    )
                if metadata.get("parallel_metadata_declared") is not True:
                    raise ValueError(
                        f"Capability {activity.capability_id!r} lacks parallel metadata"
                    )
            schema_errors = validate_args_for_schema(
                activity.args,
                definition.input_schema,
            )
            if schema_errors:
                raise ValueError(
                    f"Fast Activity {activity.activity_id!r} has invalid args: "
                    + "; ".join(schema_errors[:4])
                )
            request_id = fast_planner_activity_request_id(
                turn_id,
                activity.activity_id,
            )
            requests.append(
                CapabilityRequest(
                    request_id=request_id,
                    capability_id=activity.capability_id,
                    capability_version=definition.version,
                    args=dict(activity.args),
                    timing=activity.timing,
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=False,
                    idempotency_key=f"{turn_id}:fast_activity:{activity.activity_id}",
                    committed_output_schema_sha256=output_schema_sha256(
                        definition.output_schema
                    ),
                    metadata={
                        "source": "fast_planner_advance",
                        "turn_id": turn_id,
                        "fast_activity_id": activity.activity_id,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "source_goal_ids": [],
                        "canonical_goal_binding_pending": True,
                        "task_list_revision": 1,
                        "safety_class": "safe_read",
                        "effectful": False,
                        "execution_lane": str(
                            metadata.get("execution_lane") or "activity"
                        ),
                    },
                )
            )
        interaction_id = f"fast_activity_work_{turn_id}"
        response = InteractionResponse(
            interaction_id=interaction_id,
            status="ok",
            capabilities=requests,
            metadata={
                "source": "fast_planner_advance",
                "session_id": session_id,
                "turn_id": turn_id,
                "planning_result": "execute",
                "capability_decision": "execute",
                "canonical_goal_binding_pending": True,
            },
        )
        dispatch = await self.submit_response(response, session_id=session_id)
        task = asyncio.create_task(self.wait_dispatch(dispatch))
        return ReadyFastPlannerCapabilityExecution(
            interaction_id=interaction_id,
            turn_id=turn_id,
            activities=list(activities),
            dispatch=dispatch,
            task=task,
        )

    async def bind_fast_planner_capability_execution(
        self,
        execution: ReadyFastPlannerCapabilityExecution,
        *,
        target_interaction_id: str,
        canonical_plan_id: str,
        canonical_plan_fingerprint: str,
        goal_ids_by_responsibility: dict[str, list[str]],
        task_list_revision: int = 1,
    ) -> CapabilityRuntimeResult:
        """Bind provisional Fast Work to Goal lists and preserve its Evidence."""

        await self.runtime.bind_scheduled_tasks_to_goals(
            execution.interaction_id,
            goal_ids_by_responsibility=goal_ids_by_responsibility,
            canonical_plan_id=canonical_plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint,
            task_list_revision=task_list_revision,
        )
        result = await execution.task
        traces_by_request = {
            trace.request_id: trace for trace in result.traces
        }
        for capability_result in result.results:
            matching_activity = next(
                (
                    activity
                    for activity in execution.activities
                    if fast_planner_activity_request_id(
                        execution.turn_id,
                        activity.activity_id,
                    )
                    == capability_result.request_id
                ),
                None,
            )
            source_goal_ids: list[str] = []
            if matching_activity is not None:
                for responsibility_ref in matching_activity.source_responsibility_refs:
                    for goal_id in goal_ids_by_responsibility.get(
                        responsibility_ref, []
                    ):
                        if goal_id not in source_goal_ids:
                            source_goal_ids.append(goal_id)
                capability_result = capability_result.model_copy(
                    deep=True,
                    update={
                        "metadata": {
                            **capability_result.metadata,
                            "source_goal_ids": source_goal_ids,
                            "source_responsibility_refs": list(
                                matching_activity.source_responsibility_refs
                            ),
                            "canonical_plan_id": canonical_plan_id,
                            "canonical_plan_fingerprint": canonical_plan_fingerprint,
                            "task_list_revision": task_list_revision,
                            "fast_activity_id": matching_activity.activity_id,
                        }
                    },
                )
            trace = traces_by_request.get(capability_result.request_id)
            if trace is not None:
                trace = trace.model_copy(
                    deep=True,
                    update={"interaction_id": target_interaction_id},
                )
            self._preexecuted[
                (target_interaction_id, capability_result.request_id)
            ] = (capability_result, trace)
        return result

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
        work_dag_requests = [
            request
            for request in prepared.capabilities
            if request.capability_id == _WORK_DAG_CAPABILITY_ID
        ]
        if work_dag_requests and not self._work_dag_enabled:
            failed = await self._body_setup_failure(
                prepared,
                work_dag_requests,
                session_id=session_id,
                reason_code="work_dag_execution_disabled",
                message=(
                    "InteractionResponse requested a WorkDAG, but host "
                    "WorkDAG execution is disabled"
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
        # Evidence. Drop that pre-authored wording so Cognitive result re-entry
        # can compose a grounded follow-up. A distinct context-grounded speech
        # Goal explicitly ordered after Work (for example, perform A then greet)
        # is not a completion claim about A; the Planner/Runtime projection marks
        # that exact case and the scheduler preserves it after the capabilities.
        deferred_speech_ids = [
            speech.id
            for speech in prepared.speech
            if speech.timing == "after_capabilities"
            and not (
                speech.metadata.get("ordered_context_grounded_after_work") is True
                and speech.metadata.get("source")
                == "planner_communicative_activity"
                and str(speech.metadata.get("canonical_plan_id") or "").strip()
                == str(prepared.metadata.get("canonical_plan_id") or "").strip()
                and bool(str(prepared.metadata.get("canonical_plan_id") or "").strip())
                and set(speech.metadata.get("truth_stages") or [])
                == {"context_grounded"}
            )
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
        return annotate_preflight_validation(
            self._enforce_structured_planning_state(
                self._with_session_metadata(response, session_id)
            ),
            registry=self.registry,
            provider_ids=self.runtime.provider_ids(),
            confirmed_request_ids=confirmed_request_ids,
            soridormi_catalog_loaded=self._catalog_loaded,
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

    async def cancel_scope(
        self,
        directive: CancellationDirective,
    ) -> CancellationDispatchReceipt:
        return await self.runtime.cancel_scope(directive)

    async def reusable_request_snapshot(
        self,
        *,
        interaction_id: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        """Read the live Runtime identity used to validate Planner reuse."""

        return await self.runtime.reusable_request_snapshot(
            interaction_id=interaction_id,
            request_id=request_id,
        )

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






def build_soridormi_invoker(
    *,
    manifest_path: str | Path,
) -> McpStreamableHttpInvoker:
    configured = build_configured_registry([str(manifest_path)])
    return McpStreamableHttpInvoker(configured.registry)
