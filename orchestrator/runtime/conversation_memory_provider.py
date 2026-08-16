from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent.app.capabilities.loader import build_configured_registry, parse_manifest_paths
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    reject_forbidden_low_level_fields,
)

from .capability_runtime import CapabilityDefinition, CapabilityExecutionContext

ConversationMemoryHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class ConversationMemoryCapabilityProvider:
    """Host-owned exact retrieval of verified short-term tool evidence."""

    provider_id = "chromie.conversation_memory"

    def __init__(self, handler: ConversationMemoryHandler) -> None:
        self._handler = handler

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        retrieved = self._handler(dict(request.args))
        reject_forbidden_low_level_fields(retrieved)
        found = bool(retrieved.get("found"))
        output = {
            "found": found,
            "reason": str(retrieved.get("reason") or ""),
            "evidence_id": str(retrieved.get("evidence_id") or ""),
            "tool_id": str(retrieved.get("tool_id") or ""),
            "request_args_json": _canonical_json_text(
                retrieved.get("request_args")
                if isinstance(retrieved.get("request_args"), dict)
                else {}
            ),
            "recorded_ms": (
                float(retrieved["recorded_ms"])
                if isinstance(retrieved.get("recorded_ms"), (int, float))
                and not isinstance(retrieved.get("recorded_ms"), bool)
                else None
            ),
            "age_ms": (
                float(retrieved["age_ms"])
                if isinstance(retrieved.get("age_ms"), (int, float))
                and not isinstance(retrieved.get("age_ms"), bool)
                else None
            ),
            "max_age_s": (
                float(retrieved["max_age_s"])
                if isinstance(retrieved.get("max_age_s"), (int, float))
                and not isinstance(retrieved.get("max_age_s"), bool)
                else None
            ),
            # The original provider output is intentionally carried as canonical
            # JSON text. A generic memory capability cannot truthfully declare a
            # closed object schema for every possible source tool, while the
            # runtime must never expose an open-ended object to later models.
            "result_json": _canonical_json_text(
                retrieved.get("data")
                if isinstance(retrieved.get("data"), dict)
                else {}
            ),
            "source": str(retrieved.get("source") or ""),
        }
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed" if found else "failed",
            provider_id=self.provider_id,
            output=output,
            reason_code=None if found else str(output.get("reason") or "memory_miss"),
            message="" if found else "No exact fresh verified tool result matched the resolved bindings",
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        return None


def host_runtime_memory_definitions(
    manifest_paths: str | None = None,
) -> list[CapabilityDefinition]:
    configured = build_configured_registry(parse_manifest_paths(manifest_paths or ""))
    definitions: list[CapabilityDefinition] = []
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
            CapabilityDefinition(
                capability_id=tool.name,
                version=tool.version,
                provider_id=ConversationMemoryCapabilityProvider.provider_id,
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
    "ConversationMemoryCapabilityProvider",
    "host_runtime_memory_definitions",
]
