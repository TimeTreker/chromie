from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from shared.chromie_contracts.agent import AgentResult
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
    SkillResult,
)

from .skill_runtime import SkillDefinition, SkillExecutionContext


class AgentResultInteractionAdapter:
    """Translate the current AgentResult shape into the I0 interaction contract."""

    def convert(self, result: AgentResult) -> InteractionResponse:
        speech = [
            InteractionSpeech(
                text=item.text,
                timing="immediate",
                style=item.style,
                priority=item.priority,
                interruptible=item.interruptible,
                metadata=item.metadata,
            )
            for item in result.speak_immediate
        ]
        speech.extend(
            InteractionSpeech(
                text=item.text,
                timing="after_skills",
                style=item.style,
                priority=item.priority,
                interruptible=item.interruptible,
                metadata=item.metadata,
            )
            for item in result.speak_after
        )
        skills = [self._action_request(action) for action in result.actions]
        skills.extend(
            SkillRequest(
                skill_id="chromie.task_graph.execute",
                args={"graph": graph},
                timing="sequential",
                requires_confirmation=result.requires_confirmation,
            )
            for graph in result.task_graphs
        )
        return InteractionResponse(
            status=self._status(result.status),
            speech=speech,
            skills=skills,
            requires_confirmation=result.requires_confirmation,
            reason=result.reason,
            metadata={
                "handled_by": result.handled_by,
                "legacy_trace": result.trace,
                "memory_updates": [
                    update.model_dump(mode="json") for update in result.memory_updates
                ],
            },
        )

    def _status(self, status: str) -> str:
        return {
            "blocked": "refused",
        }.get(status, status)

    def _action_request(self, action: Any) -> SkillRequest:
        skill_id, args = self._named_skill(action)
        translated_named_skill = skill_id != action.type
        return SkillRequest(
            request_id=action.id,
            skill_id=skill_id,
            skill_version=action.metadata.get("skill_version"),
            args=args,
            timing="sequential" if action.blocking else "parallel",
            timeout_ms=None if translated_named_skill else action.timeout_ms,
            requires_confirmation=action.requires_confirmation,
            metadata={
                **action.metadata,
                "legacy_target": action.target,
                "legacy_action_type": action.type,
                "legacy_timeout_ms": action.timeout_ms,
            },
        )

    def _named_skill(self, action: Any) -> tuple[str, dict[str, Any]]:
        if action.type == "head.nod":
            return "soridormi.nod_yes", {
                "count": max(2, int(action.params.get("times", 1))),
            }
        if action.type == "head.shake":
            return "soridormi.shake_no", {
                "count": max(2, int(action.params.get("times", 1))),
            }
        if action.type == "head.look_at_user":
            duration_ms = action.params.get("duration_ms")
            args: dict[str, Any] = {}
            if isinstance(duration_ms, (int, float)) and duration_ms > 0:
                args["duration_s"] = duration_ms / 1000.0
            return "soridormi.look_at_person", args
        return str(action.metadata.get("skill_id") or action.type), dict(action.params)


TaskGraphHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class TaskGraphSkillProvider:
    """Compatibility provider around the existing guarded TaskGraph executor."""

    provider_id = "chromie.task_graph"

    def __init__(self, handler: TaskGraphHandler) -> None:
        self._handler = handler
        self.cancelled_request_ids: set[str] = set()

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        raw = self._handler(request.args["graph"])
        output = await raw if inspect.isawaitable(raw) else raw
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output=output,
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        self.cancelled_request_ids.add(request.request_id)


def task_graph_skill_definition() -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.task_graph.execute",
        version="1.0.0",
        provider_id=TaskGraphSkillProvider.provider_id,
        description="Execute a validated legacy Chromie TaskGraph.",
        input_schema={
            "type": "object",
            "properties": {
                "graph": {"type": "object"},
            },
            "required": ["graph"],
            "additionalProperties": False,
        },
        timeout_ms=120000,
        interruptible=True,
        can_run_parallel=False,
    )
