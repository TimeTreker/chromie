from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from agent.app.capabilities.loader import build_configured_registry, parse_manifest_paths
from shared.chromie_runtime.env_values import parse_bool
from shared.chromie_contracts.social_cognition import MEMORY_KEY_PATTERN
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    reject_forbidden_low_level_fields,
)

from .capability_runtime import CapabilityDefinition, CapabilityExecutionContext
from .memory import person_fact_entry

ConversationMemoryHandler = Callable[[dict[str, Any]], dict[str, Any]]
KEEP_CAPABILITY_ID = "chromie.memory.keep"


def _canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class ConversationMemoryCapabilityProvider:
    """Host-owned Memory: exact retrieval of verified tool evidence, and keeping what a person asks."""

    provider_id = "chromie.conversation_memory"

    def __init__(self, handler: ConversationMemoryHandler,
                 keep_handler: ConversationMemoryHandler | None = None) -> None:
        self._handler = handler
        self._keep_handler = keep_handler

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        if request.capability_id == KEEP_CAPABILITY_ID:
            return self._keep(request, definition)
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

    def _keep(self, request: CapabilityRequest, definition: CapabilityDefinition) -> CapabilityResult:
        kept = self._keep_handler(dict(request.args)) if self._keep_handler is not None else {}
        output = {"kept": bool(kept.get("kept")), "key": str(kept.get("key") or ""),
                  "text": str(kept.get("text") or ""), "kept_for": str(kept.get("kept_for") or "for_now")}
        return CapabilityResult(
            request_id=request.request_id, capability_id=request.capability_id,
            capability_version=definition.version, provider_id=self.provider_id,
            status="completed" if output["kept"] else "failed", output=output,
            reason_code=None if output["kept"] else str(kept.get("reason") or "memory_unavailable"),
            message="" if output["kept"] else "Memory did not keep it",
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
        if not parse_bool(
            tool.llm_hints.get("interaction_executable"),
            name=f"{tool.name} llm_hints.interaction_executable",
            default=False,
        ):
            continue
        # Retrieval reads only; keeping writes nothing but the person's own Memory.
        keeps = tool.name == KEEP_CAPABILITY_ID and set(tool.effects) == {"memory_write"}
        if not keeps and (tool.safety_class != "safe_read" or not tool.execution.side_effect_free):
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


def keep_person_fact(state: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Keep what the person asked Chromie to remember as the speaker's Memory (owner decision 2026-10-27)."""
    key, text = str(args.get("key") or "note"), " ".join(str(args.get("text") or "").split())
    lasting = args.get("holds") == "lasting"
    if not state.enabled or not re.fullmatch(MEMORY_KEY_PATTERN, key) or len(text) < 3:
        return {"kept": False, "key": key, "text": text, "reason": "memory_unavailable"}
    durable = bool(state._durable_memory.enabled)
    # Kept in the person's own words, said by them, like the person facts Social Cognition writes
    # (live 2026-10-27: a kept "I'm allergic to peanuts." was later read as Chromie's own allergy).
    state._store_explicit_memory_entries([person_fact_entry(
        person_ref=state.speaker_person_refs[0], key=key, text=f'The person said: "{text}"', sid=None,
        durable=durable, lasting=lasting)])
    kept_for = "for_now" if not lasting else "long_term" if durable else "this_conversation"
    return {"kept": True, "key": key, "text": text, "kept_for": kept_for}


__all__ = [
    "KEEP_CAPABILITY_ID",
    "keep_person_fact",
    "ConversationMemoryHandler",
    "ConversationMemoryCapabilityProvider",
    "host_runtime_memory_definitions",
]
