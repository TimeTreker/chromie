from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from agent.app.capabilities.loader import build_configured_registry
from agent.app.tool_invocation import (
    AsyncToolInvoker,
    McpStreamableHttpInvoker,
    ToolInvocationContext,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillResult,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
)

from .skill_runtime import (
    LocalSpeechSkillProvider,
    RuntimeAuthorization,
    SessionControlSkillProvider,
    SkillRegistry,
    SkillRuntime,
    SkillRuntimeResult,
    VocalPerformanceSkillProvider,
    local_speech_definition,
    session_interrupt_definition,
    vocal_performance_definition,
)
from .skill_adapters import (
    TaskGraphCancelHandler,
    TaskGraphHandler,
    TaskGraphSkillProvider,
    task_graph_skill_definition,
)
from .soridormi_skill_provider import SoridormiNamedSkillAdapter
from .agent_tool_provider import (
    AgentToolHandler,
    AgentToolSkillProvider,
    local_agent_tool_definitions,
)
from .conversation_memory_provider import (
    ConversationMemoryHandler,
    ConversationMemorySkillProvider,
    host_runtime_memory_definitions,
)
from .body_recovery import (
    build_body_recovery_confirmation,
    conservative_body_failure_message,
)
from .interaction_preflight import annotate_preflight_validation
from .task_proposals import annotate_task_proposal_ledger

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
SpeechCancelScheduler = Callable[
    [SkillRequest, dict[str, Any]],
    None | Awaitable[None],
]
_TASK_GRAPH_SKILL_ID = "chromie.task_graph.execute"


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
        vocal_provider: VocalPerformanceSkillProvider | None = None,
        capability_manifest_paths: str | None = None,
        max_concurrency: int | None = None,
        catalog_refresh_ttl_s: float | None = None,
        body_recovery_max_attempts: int | None = None,
        body_recovery_confirmation_ttl_s: float | None = None,
    ) -> None:
        self.registry = SkillRegistry()
        self.registry.register(local_speech_definition())
        self.registry.register(session_interrupt_definition())
        self.registry.register(task_graph_skill_definition())
        self.runtime = SkillRuntime(
            self.registry,
            max_concurrency=max(
                1,
                int(
                    max_concurrency
                    if max_concurrency is not None
                    else os.getenv("ORCH_SKILL_MAX_CONCURRENCY", "8")
                ),
            ),
        )
        self.runtime.register_provider(
            LocalSpeechSkillProvider(
                speech_scheduler,
                speech_cancel_scheduler,
            )
        )
        if vocal_provider is not None:
            self.registry.register(vocal_performance_definition(vocal_provider.declaration))
            self.runtime.register_provider(vocal_provider)
        self.runtime.register_provider(SessionControlSkillProvider())
        if agent_tool_handler is not None:
            definitions = local_agent_tool_definitions(capability_manifest_paths)
            for definition in definitions:
                self.registry.register(definition)
            if definitions:
                self.runtime.register_provider(AgentToolSkillProvider(agent_tool_handler))
        if conversation_memory_handler is not None:
            memory_definitions = host_runtime_memory_definitions(capability_manifest_paths)
            for definition in memory_definitions:
                self.registry.register(definition)
            if memory_definitions:
                self.runtime.register_provider(
                    ConversationMemorySkillProvider(conversation_memory_handler)
                )
        self._task_graph_enabled = task_graph_handler is not None
        if task_graph_handler is not None:
            self.runtime.register_provider(
                TaskGraphSkillProvider(
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
        self.body_recovery_max_attempts = (
            max(0, int(body_recovery_max_attempts))
            if body_recovery_max_attempts is not None
            else _int_env("ORCH_BODY_RECOVERY_MAX_ATTEMPTS", 1)
        )
        self.body_recovery_confirmation_ttl_s = (
            max(1.0, float(body_recovery_confirmation_ttl_s))
            if body_recovery_confirmation_ttl_s is not None
            else _float_env(
                "ORCH_BODY_RECOVERY_CONFIRMATION_TTL_S",
                10.0,
                minimum=1.0,
            )
        )
        self._catalog_lock = asyncio.Lock()

    async def ensure_skill_definitions(self, skill_ids: Iterable[str]) -> None:
        """Refresh provider-backed definitions needed for a canonical plan.

        This is a deterministic catalog operation. It does not authorize or
        execute any requested skill.
        """

        normalized = [str(item).strip() for item in skill_ids if str(item).strip()]
        body_ids = [item for item in normalized if item.startswith("soridormi.")]
        if body_ids:
            await self._ensure_soridormi_catalog(required_skill_ids=body_ids)
        for skill_id in normalized:
            self.registry.get(skill_id)

    def skill_definition(self, skill_id: str):
        return self.registry.get(skill_id)

    async def execute(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        opened = self.runtime.begin_interaction(response.interaction_id)
        try:
            return await self._execute_open_interaction(
                response,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
        finally:
            if opened:
                self.runtime.end_interaction(response.interaction_id)

    def reserve_interaction(self, interaction_id: str) -> None:
        """Synchronously expose a launch before any awaitable preflight."""

        if not self.runtime.begin_interaction(interaction_id):
            raise ValueError(f"cannot reserve an already-open interaction_id={interaction_id!r}")

    def release_interaction(self, interaction_id: str) -> None:
        self.runtime.end_interaction(interaction_id)

    async def _execute_open_interaction(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        raw_body_requests = [
            request for request in response.skills if request.skill_id.startswith("soridormi.")
        ]
        suppress_body_failure_speech = self._suppress_body_failure_speech(response)
        if raw_body_requests:
            if self.soridormi_invoker is None:
                try:
                    await self._ensure_soridormi_catalog(
                        required_skill_ids=(request.skill_id for request in raw_body_requests),
                    )
                except RuntimeError as exc:
                    if suppress_body_failure_speech:
                        return await self._body_setup_failure(
                            response,
                            raw_body_requests,
                            session_id=session_id,
                            reason_code="provider_disabled",
                            message=str(exc),
                            suppress_speech=True,
                        )
                    raise
            try:
                await self._ensure_soridormi_catalog(
                    required_skill_ids=(request.skill_id for request in raw_body_requests),
                )
            except RuntimeError as exc:
                return await self._body_setup_failure(
                    response,
                    raw_body_requests,
                    session_id=session_id,
                    reason_code="catalog_unavailable",
                    message=str(exc),
                    suppress_speech=suppress_body_failure_speech,
                )

        prepared = self.prepare_response(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        if prepared.status == "error" and not prepared.skills and not prepared.speech:
            return SkillRuntimeResult(
                interaction_id=prepared.interaction_id,
                status="failed",
            )
        suppress_body_failure_speech = self._suppress_body_failure_speech(prepared)
        body_requests = [
            request for request in prepared.skills if request.skill_id.startswith("soridormi.")
        ]
        task_graph_requests = [
            request for request in prepared.skills if request.skill_id == _TASK_GRAPH_SKILL_ID
        ]
        gated_requests = [*body_requests, *task_graph_requests]
        if task_graph_requests and not self._task_graph_enabled:
            return await self._body_setup_failure(
                prepared,
                task_graph_requests,
                session_id=session_id,
                reason_code="task_graph_execution_disabled",
                message=(
                    "InteractionResponse requested a TaskGraph, but host "
                    "TaskGraph execution is disabled"
                ),
                suppress_speech=suppress_body_failure_speech,
            )
        if body_requests:
            unavailable = [
                request
                for request in body_requests
                if not self.registry.get(request.skill_id).available
            ]
            if unavailable:
                definition = self.registry.get(unavailable[0].skill_id)
                return await self._body_setup_failure(
                    prepared,
                    body_requests,
                    session_id=session_id,
                    reason_code="skill_unavailable",
                    message=definition.unavailable_reason or "unavailable",
                    suppress_speech=suppress_body_failure_speech,
                )

        authorized_request_ids = set(confirmed_request_ids or ())
        after_skills_speech = [
            speech for speech in prepared.speech if speech.timing == "after_skills"
        ]
        primary = (
            prepared.model_copy(
                deep=True,
                update={
                    "speech": [
                        speech for speech in prepared.speech if speech.timing != "after_skills"
                    ]
                },
            )
            if gated_requests and after_skills_speech
            else prepared
        )
        execution = await self.runtime.execute(
            primary,
            authorization=RuntimeAuthorization(
                confirmed_request_ids=authorized_request_ids,
            ),
        )
        if not gated_requests:
            return execution

        gated_request_ids = {request.request_id for request in gated_requests}
        body_results = [
            result for result in execution.results if result.request_id in gated_request_ids
        ]
        failed_body_results = [
            result
            for result in body_results
            if result.status in {"failed", "refused", "timed_out", "cancelled"}
        ]
        if execution.status == "cancelled":
            return execution
        if failed_body_results:
            if suppress_body_failure_speech:
                return execution
            recovery_confirmation = build_body_recovery_confirmation(
                prepared,
                body_results,
                max_attempts=self.body_recovery_max_attempts,
                timeout_s=self.body_recovery_confirmation_ttl_s,
                language=str(prepared.metadata.get("language") or ""),
            )
            if recovery_confirmation is not None:
                return execution
            fallback = InteractionResponse(
                interaction_id=prepared.interaction_id,
                speech=[
                    {
                        "text": self._body_failure_message(
                            failed_body_results,
                            language=str(prepared.metadata.get("language") or ""),
                        ),
                        "timing": "sequential",
                        "style": "warning",
                        "priority": "high",
                        "interruptible": True,
                        "metadata": {
                            "source": "host_body_failure_fallback",
                            "failed_request_ids": [
                                result.request_id for result in failed_body_results
                            ],
                            "session_id": session_id,
                        },
                    }
                ],
                metadata={"source": "host_body_failure_fallback"},
            )
            fallback_execution = await self.runtime.execute(fallback)
            return self._merge_executions(
                execution,
                fallback_execution,
                status="failed",
            )

        if after_skills_speech:
            followup = InteractionResponse(
                interaction_id=prepared.interaction_id,
                speech=after_skills_speech,
                metadata=prepared.metadata,
            )
            followup_execution = await self.runtime.execute(followup)
            return self._merge_executions(
                execution,
                followup_execution,
                status=("completed" if followup_execution.status == "completed" else "failed"),
            )
        return execution

    @classmethod
    def _suppress_body_failure_speech(
        cls,
        response: InteractionResponse,
    ) -> bool:
        return bool(
            cls._is_cognitive_effectful(response)
            or response.metadata.get("suppress_body_failure_speech") is True
        )

    @staticmethod
    def _is_cognitive_effectful(response: InteractionResponse) -> bool:
        metadata = response.metadata
        return bool(
            metadata.get("cognitive_runtime_apply") is True
            and isinstance(metadata.get("canonical_plan"), dict)
            and response.skills
        )

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
        effectful = [request for request in response.skills if request.skill_id != "chromie.speak"]
        if not effectful:
            return response
        return response.model_copy(
            deep=True,
            update={
                "skills": [
                    request for request in response.skills if request.skill_id == "chromie.speak"
                ],
                "requires_confirmation": False,
                "metadata": {
                    **metadata,
                    "structured_planning_execution_suppressed": True,
                    "suppressed_capability_ids": [request.skill_id for request in effectful],
                },
            },
        )

    async def _body_setup_failure(
        self,
        response: InteractionResponse,
        body_requests: list[SkillRequest],
        *,
        session_id: str | None,
        reason_code: str,
        message: str,
        suppress_speech: bool = False,
    ) -> SkillRuntimeResult:
        body_results = [
            SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=request.skill_version,
                status="failed",
                provider_id="soridormi.mcp",
                reason_code=reason_code,
                message=message,
            )
            for request in body_requests
        ]
        failed = SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=body_results,
        )
        if suppress_speech:
            return failed
        fallback = InteractionResponse(
            interaction_id=response.interaction_id,
            speech=[
                {
                    "text": self._body_failure_message(
                        body_results,
                        language=str(response.metadata.get("language") or ""),
                    ),
                    "timing": "sequential",
                    "style": "warning",
                    "priority": "high",
                    "interruptible": True,
                    "metadata": {
                        "source": "host_body_setup_failure_fallback",
                        "failed_request_ids": [result.request_id for result in body_results],
                        "session_id": session_id,
                    },
                }
            ],
            metadata={"source": "host_body_setup_failure_fallback"},
        )
        fallback_execution = await self.runtime.execute(fallback)
        return self._merge_executions(
            failed,
            fallback_execution,
            status="failed",
        )

    def _body_failure_message(
        self,
        results: list[SkillResult],
        *,
        language: str,
    ) -> str:
        zh = language.lower().startswith("zh")
        if any(result.skill_id == _TASK_GRAPH_SKILL_ID for result in results):
            if any(result.status == "cancelled" for result in results):
                return (
                    "任务已取消，我没有继续执行。"
                    if zh
                    else "The task was cancelled, so I did not continue."
                )
            if any(result.status == "timed_out" for result in results):
                return (
                    "任务执行超时，我无法确认它已安全完成。"
                    if zh
                    else "The task timed out, and I could not confirm it completed safely."
                )
            return "我无法安全完成这个任务。" if zh else "I could not complete that task safely."
        if any(result.status == "refused" for result in results):
            return (
                "安全检查未通过，我没有执行这个动作。"
                if zh
                else "The safety check did not pass, so I did not perform that movement."
            )
        if any(result.status == "timed_out" for result in results):
            return (
                "动作执行超时，我无法确认它已安全完成。"
                if zh
                else "The movement timed out, and I could not confirm it completed safely."
            )
        conservative = conservative_body_failure_message(results, language=language)
        if conservative:
            return conservative
        return "我无法安全完成这个动作。" if zh else "I could not complete that movement safely."

    def _merge_executions(
        self,
        first: SkillRuntimeResult,
        second: SkillRuntimeResult,
        *,
        status: str,
    ) -> SkillRuntimeResult:
        return SkillRuntimeResult(
            interaction_id=first.interaction_id,
            status=status,
            results=[*first.results, *second.results],
            traces=[*first.traces, *second.traces],
        )

    async def confirmation_request_ids(
        self,
        response: InteractionResponse,
    ) -> set[str]:
        body_requests = [
            request for request in response.skills if request.skill_id.startswith("soridormi.")
        ]
        if body_requests:
            await self._ensure_soridormi_catalog(
                required_skill_ids=(request.skill_id for request in body_requests),
            )

        required = {
            request.request_id
            for request in response.skills
            if request.requires_confirmation
            or self.registry.get(request.skill_id).requires_confirmation
        }
        if response.requires_confirmation and not required:
            required.update(request.request_id for request in response.skills)
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
        required_skill_ids: Iterable[str] | None = None,
    ) -> None:
        required = set(required_skill_ids or ())
        if self.soridormi_invoker is None:
            raise RuntimeError(
                "InteractionResponse requested a Soridormi skill, but "
                "ORCH_ENABLE_SORIDORMI_SKILLS is disabled"
            )
        if not self._should_refresh_soridormi_catalog(
            force=force,
            required_skill_ids=required,
        ):
            return
        async with self._catalog_lock:
            if not self._should_refresh_soridormi_catalog(
                force=force,
                required_skill_ids=required,
            ):
                return
            outcome = await self.soridormi_invoker.invoke(
                "soridormi.skill.list",
                {},
            )
            if outcome.status != "success":
                raise RuntimeError(outcome.error or "Soridormi named-skill catalog lookup failed")
            skills = outcome.output.get("skills")
            if not isinstance(skills, list):
                raise RuntimeError("Soridormi named-skill catalog response has no skills list")
            self.registry.import_soridormi_catalog(skills)
            if "soridormi.mcp" not in self.runtime.provider_ids():
                self.runtime.register_provider(SoridormiNamedSkillAdapter(self.soridormi_invoker))
            self._catalog_loaded = True
            self._catalog_last_loaded_at = time.monotonic()

            missing = self._missing_soridormi_skill_ids(required)
            if missing:
                raise RuntimeError(
                    "Soridormi named-skill catalog did not include requested "
                    f"skills: {', '.join(sorted(missing))}"
                )

    def _should_refresh_soridormi_catalog(
        self,
        *,
        force: bool,
        required_skill_ids: set[str],
    ) -> bool:
        if force or not self._catalog_loaded:
            return True
        if self._required_soridormi_skills_need_refresh(required_skill_ids):
            return True
        if self._catalog_refresh_ttl_s <= 0:
            return True
        if self._catalog_last_loaded_at is None:
            return True
        return (time.monotonic() - self._catalog_last_loaded_at) >= self._catalog_refresh_ttl_s

    def _required_soridormi_skills_need_refresh(
        self,
        skill_ids: Iterable[str],
    ) -> bool:
        for skill_id in skill_ids:
            if not skill_id.startswith("soridormi."):
                continue
            try:
                definition = self.registry.get(skill_id)
            except ValueError:
                return True
            if definition.metadata.get("catalog_absent") is True:
                return True
        return False

    def _missing_soridormi_skill_ids(self, skill_ids: Iterable[str]) -> set[str]:
        missing: set[str] = set()
        for skill_id in skill_ids:
            if not skill_id.startswith("soridormi."):
                continue
            try:
                self.registry.get(skill_id)
            except ValueError:
                missing.add(skill_id)
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
                "skills": [],
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
        for request in response.skills:
            if request.skill_id == "chromie.speak":
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
                request.skill_id.startswith("soridormi.")
                or request.skill_id == _TASK_GRAPH_SKILL_ID
                or request.skill_id == "session.interrupt"
            ):
                return True
        return False


def build_soridormi_invoker(
    *,
    manifest_path: str | Path,
) -> McpStreamableHttpInvoker:
    configured = build_configured_registry([str(manifest_path)])
    return McpStreamableHttpInvoker(configured.registry)
