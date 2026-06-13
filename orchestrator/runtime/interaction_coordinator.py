from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent.app.capabilities.loader import build_configured_registry
from agent.app.tool_invocation import AsyncToolInvoker, McpStreamableHttpInvoker
from shared.chromie_contracts.interaction import InteractionResponse

from .skill_runtime import (
    LocalSpeechSkillProvider,
    RuntimeAuthorization,
    SkillRegistry,
    SkillRuntime,
    SkillRuntimeResult,
    local_speech_definition,
)
from .soridormi_skill_provider import SoridormiMcpSkillProvider

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class InteractionRuntimeCoordinator:
    """Host integration boundary for InteractionResponse execution."""

    def __init__(
        self,
        speech_scheduler: SpeechScheduler,
        *,
        soridormi_invoker: AsyncToolInvoker | None = None,
        auto_confirm_sim: bool = True,
    ) -> None:
        self.registry = SkillRegistry()
        self.registry.register(local_speech_definition())
        self.runtime = SkillRuntime(
            self.registry,
            max_concurrency=max(
                1,
                int(os.getenv("ORCH_SKILL_MAX_CONCURRENCY", "8")),
            ),
        )
        self.runtime.register_provider(LocalSpeechSkillProvider(speech_scheduler))
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
        if body_requests:
            await self._ensure_soridormi_catalog()

        authorized_request_ids = set(confirmed_request_ids or ())
        if (
            body_requests
            and self.soridormi_mode == "sim"
            and self.auto_confirm_sim
        ):
            authorized_request_ids.update(
                request.request_id for request in body_requests
            )
        return await self.runtime.execute(
            prepared,
            authorization=RuntimeAuthorization(
                confirmed_request_ids=authorized_request_ids,
            ),
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
