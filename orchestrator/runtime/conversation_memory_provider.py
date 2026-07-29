from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.app.capabilities.loader import build_configured_registry, parse_manifest_paths
from shared.chromie_contracts.interaction import SkillRequest, SkillResult

from .skill_runtime import SkillDefinition, SkillExecutionContext

ConversationMemoryHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ConversationMemorySkillProvider:
    """Host-owned exact retrieval of verified short-term tool evidence."""

    provider_id = "chromie.conversation_memory"

    def __init__(self, handler: ConversationMemoryHandler) -> None:
        self._handler = handler

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        output = self._handler(dict(request.args))
        found = bool(output.get("found"))
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed" if found else "failed",
            provider_id=self.provider_id,
            output=output,
            reason_code=None if found else str(output.get("reason") or "memory_miss"),
            message="" if found else "No exact fresh verified tool result matched the resolved bindings",
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        return None


def host_runtime_memory_definitions(
    manifest_paths: str | None = None,
) -> list[SkillDefinition]:
    configured = build_configured_registry(parse_manifest_paths(manifest_paths or ""))
    definitions: list[SkillDefinition] = []
    for tool in configured.registry.list_tools():
        manifest = configured.registry.get_agent(tool.agent_id)
        if manifest.transport.kind != "host_runtime":
            continue
        if tool.agent_id != "chromie.memory":
            continue
        if not _truthy(tool.llm_hints.get("interaction_executable")):
            continue
        if tool.safety_class != "safe_read" or not tool.execution.side_effect_free:
            continue
        if tool.confirmation.required:
            continue
        definitions.append(
            SkillDefinition(
                skill_id=tool.name,
                version=tool.version,
                provider_id=ConversationMemorySkillProvider.provider_id,
                description=tool.description,
                input_schema=dict(tool.input_schema),
                output_schema=dict(tool.output_schema),
                available=bool(
                    manifest.status.available and tool.availability.available
                ),
                unavailable_reason=(
                    tool.availability.reason or manifest.status.reason
                ),
                requires_confirmation=False,
                interruptible=True,
                can_run_parallel=tool.execution.can_run_parallel,
                exclusive_group=tool.execution.exclusive_group,
                timeout_ms=max(
                    1,
                    int(float(tool.execution.timeout_s or 2.0) * 1000),
                ),
                idempotent=tool.execution.idempotent,
                requires_safety_monitor=False,
                metadata={
                    "agent_id": tool.agent_id,
                    "effects": list(tool.effects),
                    "safety_class": tool.safety_class,
                    "semantic_authority": "goal_driven_cognitive_core",
                    "execution_boundary": "host_verified_conversation_memory",
                    "reference_resolution_authority": False,
                },
            )
        )
    return definitions


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "ConversationMemoryHandler",
    "ConversationMemorySkillProvider",
    "host_runtime_memory_definitions",
]
