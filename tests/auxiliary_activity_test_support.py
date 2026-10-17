"""Capability runtime doubles shared by auxiliary-activity and Social Cognition tests."""

from __future__ import annotations

from types import SimpleNamespace

from orchestrator.runtime.capability_runtime import CapabilityDefinition
from shared.chromie_contracts.interaction import InteractionResponse


class RecordingCapabilityRuntime:
    """Capability runtime double that records submitted responses."""

    def __init__(self, definitions: list[CapabilityDefinition]) -> None:
        self.definitions = {item.capability_id: item for item in definitions}
        self.executed: list[tuple[InteractionResponse, str]] = []

    async def ensure_capability_definitions(self, capability_ids):
        for capability_id in capability_ids:
            if capability_id not in self.definitions:
                raise ValueError(capability_id)

    def capability_definition(self, capability_id):
        return self.definitions[capability_id]

    async def submit_response(self, response, *, session_id):
        self.executed.append((response, session_id))
        return SimpleNamespace(response=response, session_id=session_id)

    async def wait_dispatch(self, _dispatch):
        return SimpleNamespace(status="completed")


def social_capability_definition(
    capability_id: str = "soridormi.blink_eyes",
    *,
    domains: list[str] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        provider_id="soridormi.mcp",
        input_schema={
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 3}},
            "required": ["count"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "required": ["completed"],
            "additionalProperties": False,
        },
        available=True,
        requires_confirmation=False,
        can_run_parallel=True,
        exclusive_group="face_expression",
        metadata={
            "behavior_domains": domains or ["social_attention"],
            "effects": ["social_expression"],
            "parallel_metadata_declared": True,
            "resource_claims": ["face"],
        },
    )
