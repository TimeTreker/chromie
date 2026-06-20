from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent.app.capabilities.loader import build_configured_registry
from agent.app.tool_invocation import AsyncToolInvoker, McpStreamableHttpInvoker
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillResult,
)

from .skill_runtime import (
    LocalSpeechSkillProvider,
    RuntimeAuthorization,
    SkillRegistry,
    SkillRuntime,
    SkillRuntimeResult,
    local_speech_definition,
)
from .skill_adapters import TaskGraphHandler, TaskGraphSkillProvider, task_graph_skill_definition
from .soridormi_skill_provider import SoridormiMcpSkillProvider

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
_TASK_GRAPH_SKILL_ID = "chromie.task_graph.execute"


class InteractionRuntimeCoordinator:
    """Host integration boundary for InteractionResponse execution."""

    def __init__(
        self,
        speech_scheduler: SpeechScheduler,
        *,
        soridormi_invoker: AsyncToolInvoker | None = None,
        task_graph_handler: TaskGraphHandler | None = None,
        auto_confirm_sim: bool = True,
    ) -> None:
        self.registry = SkillRegistry()
        self.registry.register(local_speech_definition())
        self.registry.register(task_graph_skill_definition())
        self.runtime = SkillRuntime(
            self.registry,
            max_concurrency=max(
                1,
                int(os.getenv("ORCH_SKILL_MAX_CONCURRENCY", "8")),
            ),
        )
        self.runtime.register_provider(LocalSpeechSkillProvider(speech_scheduler))
        self._task_graph_enabled = task_graph_handler is not None
        if task_graph_handler is not None:
            self.runtime.register_provider(TaskGraphSkillProvider(task_graph_handler))
        self.soridormi_invoker = soridormi_invoker
        self.auto_confirm_sim = auto_confirm_sim
        self.soridormi_mode: str | None = None
        self._catalog_loaded = False
        self._catalog_lock = asyncio.Lock()

    async def execute(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        prepared = self._with_session_metadata(response, session_id)
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
            )
        if body_requests:
            if self.soridormi_invoker is None:
                await self._ensure_soridormi_catalog()
            try:
                await self._ensure_soridormi_catalog()
            except RuntimeError as exc:
                return await self._body_setup_failure(
                    prepared,
                    body_requests,
                    session_id=session_id,
                    reason_code="catalog_unavailable",
                    message=str(exc),
                )
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
                )

        authorized_request_ids = set(confirmed_request_ids or ())
        if (
            body_requests
            and self.soridormi_mode == "sim"
            and self.auto_confirm_sim
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

    async def _body_setup_failure(
        self,
        response: InteractionResponse,
        body_requests: list[SkillRequest],
        *,
        session_id: str | None,
        reason_code: str,
        message: str,
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
            await self._ensure_soridormi_catalog()

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
        ):
            required.difference_update(
                request.request_id for request in body_requests
            )
        return required

    async def cancel_all(self) -> None:
        await self.runtime.cancel_all()

    async def _ensure_soridormi_catalog(self) -> None:
        if self._catalog_loaded:
            return
        if self.soridormi_invoker is None:
            raise RuntimeError(
                "InteractionResponse requested a Soridormi skill, but "
                "ORCH_ENABLE_SORIDORMI_SKILLS is disabled"
            )
        async with self._catalog_lock:
            if self._catalog_loaded:
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
            self.runtime.register_provider(
                SoridormiMcpSkillProvider(self.soridormi_invoker)
            )
            self._catalog_loaded = True

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
