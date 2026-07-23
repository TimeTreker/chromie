from __future__ import annotations

import asyncio
import os
import re
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
    InteractionSpeech,
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
    local_speech_definition,
    session_interrupt_definition,
)
from .skill_adapters import (
    TaskGraphCancelHandler,
    TaskGraphHandler,
    TaskGraphSkillProvider,
    task_graph_skill_definition,
)
from .soridormi_skill_provider import SoridormiNamedSkillAdapter
from .body_recovery import (
    build_body_recovery_confirmation,
    conservative_body_failure_message,
)
from .interaction_preflight import annotate_preflight_validation
from .task_proposals import annotate_task_proposal_ledger

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
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
        soridormi_invoker: AsyncToolInvoker | None = None,
        task_graph_handler: TaskGraphHandler | None = None,
        task_graph_cancel_handler: TaskGraphCancelHandler | None = None,
        auto_confirm_sim: bool = True,
    ) -> None:
        self.registry = SkillRegistry()
        self.registry.register(local_speech_definition())
        self.registry.register(session_interrupt_definition())
        self.registry.register(task_graph_skill_definition())
        self.runtime = SkillRuntime(
            self.registry,
            max_concurrency=max(
                1,
                int(os.getenv("ORCH_SKILL_MAX_CONCURRENCY", "8")),
            ),
        )
        self.runtime.register_provider(LocalSpeechSkillProvider(speech_scheduler))
        self.runtime.register_provider(SessionControlSkillProvider())
        self._task_graph_enabled = task_graph_handler is not None
        if task_graph_handler is not None:
            self.runtime.register_provider(
                TaskGraphSkillProvider(
                    task_graph_handler,
                    task_graph_cancel_handler,
                )
            )
        self.soridormi_invoker = soridormi_invoker
        self.auto_confirm_sim = auto_confirm_sim
        self.soridormi_mode: str | None = None
        self._catalog_loaded = False
        self._catalog_last_loaded_at: float | None = None
        self._catalog_refresh_ttl_s = _float_env(
            "ORCH_SORIDORMI_CATALOG_REFRESH_TTL_S",
            30.0,
        )
        self.body_recovery_max_attempts = _int_env(
            "ORCH_BODY_RECOVERY_MAX_ATTEMPTS",
            1,
        )
        self.body_recovery_confirmation_ttl_s = _float_env(
            "ORCH_BODY_RECOVERY_CONFIRMATION_TTL_S",
            10.0,
            minimum=1.0,
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
            raise ValueError(
                "cannot reserve an already-open interaction_id="
                f"{interaction_id!r}"
            )

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
            request
            for request in response.skills
            if request.skill_id.startswith("soridormi.")
        ]
        optional_body_cue = bool(response.metadata.get("optional_body_cue"))
        cognitive_effectful = self._is_cognitive_effectful(response)
        if raw_body_requests:
            if self.soridormi_invoker is None:
                try:
                    await self._ensure_soridormi_catalog(
                        required_skill_ids=(
                            request.skill_id for request in raw_body_requests
                        ),
                    )
                except RuntimeError as exc:
                    if optional_body_cue or cognitive_effectful:
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
                    required_skill_ids=(
                        request.skill_id for request in raw_body_requests
                    ),
                )
            except RuntimeError as exc:
                return await self._body_setup_failure(
                    response,
                    raw_body_requests,
                    session_id=session_id,
                    reason_code="catalog_unavailable",
                    message=str(exc),
                    suppress_speech=optional_body_cue or cognitive_effectful,
                )

        prepared = self.prepare_response(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        optional_body_cue = bool(prepared.metadata.get("optional_body_cue"))
        cognitive_effectful = self._is_cognitive_effectful(prepared)
        body_requests = [
            request
            for request in prepared.skills
            if request.skill_id.startswith("soridormi.")
        ]
        task_graph_requests = [
            request
            for request in prepared.skills
            if request.skill_id == _TASK_GRAPH_SKILL_ID
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
                suppress_speech=cognitive_effectful,
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
                    suppress_speech=optional_body_cue or cognitive_effectful,
                )

        authorized_request_ids = set(confirmed_request_ids or ())
        if (
            body_requests
            and self.soridormi_mode == "sim"
            and self.auto_confirm_sim
            and self._body_auto_confirm_allowed(prepared)
        ):
            authorized_request_ids.update(
                request.request_id for request in body_requests
            )
        after_skills_speech = [
            speech for speech in prepared.speech if speech.timing == "after_skills"
        ]
        primary = (
            prepared.model_copy(
                deep=True,
                update={
                    "speech": [
                        speech
                        for speech in prepared.speech
                        if speech.timing != "after_skills"
                    ]
                },
            )
            if gated_requests and after_skills_speech
            else prepared
        )
        try:
            execution = await self.runtime.execute(
                primary,
                authorization=RuntimeAuthorization(
                    confirmed_request_ids=authorized_request_ids,
                ),
            )
        except ValueError as exc:
            if optional_body_cue and gated_requests:
                return SkillRuntimeResult(
                    interaction_id=prepared.interaction_id,
                    status="failed",
                    results=[
                        SkillResult(
                            request_id=request.request_id,
                            skill_id=request.skill_id,
                            skill_version=request.skill_version,
                            status="failed",
                            provider_id="soridormi.mcp",
                            reason_code="optional_body_cue_unavailable",
                            message=str(exc),
                        )
                        for request in gated_requests
                    ],
                )
            raise
        if not gated_requests:
            return execution

        gated_request_ids = {request.request_id for request in gated_requests}
        body_results = [
            result
            for result in execution.results
            if result.request_id in gated_request_ids
        ]
        failed_body_results = [
            result
            for result in body_results
            if result.status in {"failed", "refused", "timed_out", "cancelled"}
        ]
        if execution.status == "cancelled":
            return execution
        if failed_body_results:
            if optional_body_cue or cognitive_effectful:
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
                status=(
                    "completed"
                    if followup_execution.status == "completed"
                    else "failed"
                ),
            )
        return execution

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
        effectful = [
            request
            for request in response.skills
            if request.skill_id != "chromie.speak"
        ]
        if not effectful:
            return response
        return response.model_copy(
            deep=True,
            update={
                "skills": [
                    request
                    for request in response.skills
                    if request.skill_id == "chromie.speak"
                ],
                "requires_confirmation": False,
                "metadata": {
                    **metadata,
                    "structured_planning_execution_suppressed": True,
                    "suppressed_skill_ids": [
                        request.skill_id for request in effectful
                    ],
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
                        "failed_request_ids": [
                            result.request_id for result in body_results
                        ],
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
            return (
                "我无法安全完成这个任务。"
                if zh
                else "I could not complete that task safely."
            )
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
        return (
            "我无法安全完成这个动作。"
            if zh
            else "I could not complete that movement safely."
        )

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

    @staticmethod
    def _body_auto_confirm_allowed(response: InteractionResponse) -> bool:
        metadata = response.metadata if isinstance(response.metadata, dict) else {}
        if metadata.get("disable_body_auto_confirm") is True:
            return False
        if metadata.get("post_interrupt_physical_resume_lock") is True:
            return False
        for request in response.skills:
            request_metadata = request.metadata if isinstance(request.metadata, dict) else {}
            if request_metadata.get("post_interrupt_physical_resume_lock") is True:
                return False
        return True

    async def confirmation_request_ids(
        self,
        response: InteractionResponse,
    ) -> set[str]:
        body_requests = [
            request
            for request in response.skills
            if request.skill_id.startswith("soridormi.")
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
        if (
            self.soridormi_mode == "sim"
            and self.auto_confirm_sim
            and self._body_auto_confirm_allowed(response)
        ):
            required.difference_update(
                request.request_id for request in body_requests
            )
        return required

    async def confirmation_exemption_request_ids(
        self,
        response: InteractionResponse,
    ) -> set[str]:
        body_requests = [
            request
            for request in response.skills
            if request.skill_id.startswith("soridormi.")
        ]
        if not body_requests:
            return set()
        await self._ensure_soridormi_catalog(
            required_skill_ids=(request.skill_id for request in body_requests),
        )
        if not (
            self.soridormi_mode == "sim"
            and self.auto_confirm_sim
            and self._body_auto_confirm_allowed(response)
        ):
            return set()
        return {
            request.request_id
            for request in body_requests
            if request.requires_confirmation
            or self.registry.get(request.skill_id).requires_confirmation
        }

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
        postcondition_confirmed = (
            outcome.status == "success"
            and all(output.get(key) is True for key in required_postconditions)
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
                raise RuntimeError(
                    outcome.error or "Soridormi named-skill catalog lookup failed"
                )
            skills = outcome.output.get("skills")
            if not isinstance(skills, list):
                raise RuntimeError(
                    "Soridormi named-skill catalog response has no skills list"
                )
            self.soridormi_mode = str(outcome.output.get("mode") or "unknown")
            self.registry.import_soridormi_catalog(
                skills,
                requires_confirmation=not (
                    self.soridormi_mode == "sim" and self.auto_confirm_sim
                ),
            )
            if "soridormi.mcp" not in self.runtime.provider_ids():
                self.runtime.register_provider(
                    SoridormiNamedSkillAdapter(self.soridormi_invoker)
                )
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
        return (
            time.monotonic() - self._catalog_last_loaded_at
        ) >= self._catalog_refresh_ttl_s

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
        unsafe_speech_without_effect = (
            bool(response.speech)
            and not self._has_effectful_runtime_skill(response)
            and any(
                self._speech_claims_unverified_effect(
                    " ".join(str(speech.text or "").strip().split())
                )
                for speech in response.speech
            )
        )
        if (proposed <= 0 or valid > 0) and not unsafe_speech_without_effect:
            return response
        if self._has_effectful_runtime_skill(response):
            return response
        reason = str(response.metadata.get("truth_reconciliation_reason") or "").strip()
        if not reason:
            reason = (
                "speech_claimed_effect_without_runtime_skill"
                if unsafe_speech_without_effect
                else "deepthinking_effect_task_without_valid_skill"
            )
        metadata = {
            **response.metadata,
            "truth_reconciled": True,
            "truth_reconciliation_reason": reason,
        }
        if self._safe_existing_truth_reconciliation_speech(response):
            metadata["truth_reconciliation_speech_source"] = "llm_safe_existing_speech"
            return response.model_copy(deep=True, update={"metadata": metadata})

        language = str(response.metadata.get("language") or "")
        text = self._truth_reconciliation_message(response, language=language)
        return response.model_copy(
            deep=True,
            update={
                "speech": [
                    InteractionSpeech(
                        text=text,
                        timing="sequential",
                        style="warning",
                        priority="high",
                        interruptible=True,
                        metadata={
                            "source": "host_truth_reconciliation",
                            "session_id": session_id,
                        },
                    )
                ],
                "metadata": metadata,
            },
        )

    def _safe_existing_truth_reconciliation_speech(
        self,
        response: InteractionResponse,
    ) -> bool:
        if not response.speech:
            return False
        for speech in response.speech:
            text = " ".join(str(speech.text or "").strip().split())
            if not text:
                return False
            if self._speech_claims_unverified_effect(text):
                return False
        return True

    @staticmethod
    def _speech_claims_unverified_effect(text: str) -> bool:
        return bool(
            re.search(
                r"(?:执行(?:指令|命令)?|已经执行|正在执行|我(?:会|将|要|这就|马上|现在)(?:[^。！？,.，]*)(?:向前|往前|移动|走|转|执行)|"
                r"I(?:'ll| will) (?:walk|move|turn|execute|perform)|\b(?:moving|walking|turning|executing|performing)\b|soridormi\.|chromie\.)",
                text,
                flags=re.IGNORECASE,
            )
        )

    def _truth_reconciliation_message(
        self,
        response: InteractionResponse,
        *,
        language: str,
    ) -> str:
        zh = language.lower().startswith("zh")
        if self._looks_like_warning_correction(response):
            return (
                "抱歉，我刚才把提醒误解成了方向指令。谢谢提醒，我会保持不动。"
                if zh
                else "Sorry, I misunderstood that as a direction. Thanks for warning me. I will hold still."
            )
        return (
            "我理解你是想让我做一个动作。为了安全，我需要先确认一下。"
            if zh
            else "I understand you want me to do a movement. For safety, I need to confirm first."
        )

    @staticmethod
    def _looks_like_warning_correction(response: InteractionResponse) -> bool:
        metadata = response.metadata
        route_intent = str(metadata.get("route_intent") or "").casefold()
        reason = str(metadata.get("truth_reconciliation_reason") or "").casefold()
        if "warning" in route_intent or "warning" in reason:
            return True
        superseded = metadata.get("superseded_task_proposals")
        if isinstance(superseded, list):
            for item in superseded:
                if not isinstance(item, dict):
                    continue
                text = " ".join(
                    str(item.get(key) or "")
                    for key in ("reason", "intent", "task_type", "skill_id")
                ).casefold()
                if "warning" in text:
                    return True
        return False

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
        return any(
            request.skill_id.startswith("soridormi.")
            or request.skill_id == _TASK_GRAPH_SKILL_ID
            or (
                request.skill_id not in {"chromie.speak"}
                and request.skill_id.startswith("chromie.")
            )
            for request in response.skills
        )


def build_soridormi_invoker(
    *,
    manifest_path: str | Path,
) -> McpStreamableHttpInvoker:
    configured = build_configured_registry([str(manifest_path)])
    return McpStreamableHttpInvoker(configured.registry)
