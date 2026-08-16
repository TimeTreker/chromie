from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.app.capabilities.loader import build_configured_registry, parse_manifest_paths
from shared.chromie_contracts.interaction import CapabilityRequest, CapabilityResult
from shared.chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse

from .capability_runtime import CapabilityDefinition, CapabilityExecutionContext

AgentToolHandler = Callable[
    [ToolExecutionRequest, int],
    Awaitable[ToolExecutionResponse],
]


class AgentToolCapabilityProvider:
    """Host provider for exact, already-planned Chromie local tool calls."""

    provider_id = "chromie.agent_tool"

    def __init__(self, handler: AgentToolHandler) -> None:
        self._handler = handler

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        response = await self._handler(
            ToolExecutionRequest(
                request_id=request.request_id,
                tool_id=request.capability_id,
                args=request.args,
                correlation_id=context.interaction_id,
                language=str(request.metadata.get("language") or "en-US"),
            ),
            request.timeout_ms or definition.timeout_ms,
        )
        status = "failed" if response.status == "unavailable" else response.status
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status=status,
            provider_id=self.provider_id,
            output=response.output,
            metadata=response.metadata,
            reason_code=response.reason_code or None,
            message=response.message,
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        # Read-only HTTP provider calls are cancelled by the runtime task itself.
        return None


def local_agent_tool_definitions(
    manifest_paths: str | None = None,
) -> list[CapabilityDefinition]:
    configured = build_configured_registry(parse_manifest_paths(manifest_paths or ""))
    definitions: list[CapabilityDefinition] = []
    for tool in configured.registry.list_tools():
        manifest = configured.registry.get_agent(tool.agent_id)
        if manifest.transport.kind != "local_python":
            continue
        if not _truthy(tool.llm_hints.get("interaction_executable")):
            continue
        if tool.safety_class != "safe_read" or not tool.execution.side_effect_free:
            continue
        if tool.confirmation.required:
            continue
        definitions.append(
            CapabilityDefinition(
                capability_id=tool.name,
                version=tool.version,
                provider_id=AgentToolCapabilityProvider.provider_id,
                description=tool.description,
                input_schema=dict(tool.input_schema),
                output_schema=dict(tool.output_schema),
                available=bool(manifest.status.available and tool.availability.available),
                unavailable_reason=(tool.availability.reason or manifest.status.reason),
                requires_confirmation=False,
                interruptible=True,
                can_run_parallel=tool.execution.can_run_parallel,
                exclusive_group=tool.execution.exclusive_group,
                timeout_ms=max(1, int(float(tool.execution.timeout_s or 30.0) * 1000)),
                idempotent=tool.execution.idempotent,
                durable_runtime_eligible=tool.execution.durable_runtime_eligible,
                requires_safety_monitor=False,
                metadata={
                    "agent_id": tool.agent_id,
                    "effects": list(tool.effects),
                    "safety_class": tool.safety_class,
                    "semantic_authority": "goal_driven_cognitive_core",
                    "execution_boundary": "trusted_local_tool",
                    "side_effect_free": bool(tool.execution.side_effect_free),
                    "semantic_scope": dict(tool.llm_hints.get("semantic_scope") or {}),
                    "resource_contract": dict(tool.llm_hints.get("resource_contract") or {}),
                },
            )
        )
    return definitions


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["AgentToolHandler", "AgentToolCapabilityProvider", "local_agent_tool_definitions"]
