from __future__ import annotations

import unittest
from typing import Any

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.models import CapabilityRegistry as AgentCapabilityRegistry
from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.capability_runtime import (
    CapabilityRegistry,
    CapabilityRuntime,
    RuntimeAuthorization,
)
from orchestrator.runtime.soridormi_capability_provider import (
    SoridormiCapabilityProvider,
    import_soridormi_capability_catalog,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.semantic_capability import (
    normalize_semantic_capability_facade,
    realize_semantic_capability_args,
)
from tests.capability_runtime_test_support import submit_and_wait_terminal


PROVIDER_SCHEMA = {
    "type": "object",
    "properties": {
        "yaw_radps": {"type": "number", "minimum": -0.4, "maximum": 0.4, "default": 0.12},
        "duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0, "default": 2.0},
        "count": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1},
    },
    "required": ["yaw_radps"],
    "additionalProperties": False,
}
SEMANTIC_FACADE = {
    "input_schema": {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["left", "right"]},
            "turn_rate_radps": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 0.4, "default": 0.12},
            "duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0, "default": 2.0},
            "count": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1},
        },
        "required": ["direction"],
        "additionalProperties": False,
    },
    "provider_realizations": {
        "yaw_radps": {
            "kind": "signed_magnitude",
            "direction_argument": "direction",
            "magnitude_argument": "turn_rate_radps",
            "positive_direction": "left",
            "negative_direction": "right",
            "default_magnitude": 0.12,
        }
    },
}


def turn_skill() -> dict[str, Any]:
    return {
        "skill_id": "turn_in_place",
        "version": "1.0.0",
        "description": "Turn the body left or right in place.",
        "parameters_schema": PROVIDER_SCHEMA,
        "available": True,
        "effects": ["physical_motion"],
        "safety_class": "low_risk_action",
        "requires_confirmation": False,
        "metadata": {"semantic_facade": SEMANTIC_FACADE},
    }


class _CatalogOutcome:
    status = "success"
    error = None

    def __init__(self) -> None:
        self.output = {"skills": [turn_skill()]}


class _CatalogInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None):
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _CatalogOutcome()


class _ExecutionInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success({
                "plan_id": "turn-plan",
                "skill_id": args["skill_id"],
                "requires_confirmation": False,
            })
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success({
                "completed": True,
                "skill_id": "turn_in_place",
                "summary": "turned",
            })
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class SemanticCapabilityFacadeTests(unittest.IsolatedAsyncioTestCase):
    def test_signed_direction_is_realized_below_the_semantic_contract(self) -> None:
        normalized = normalize_semantic_capability_facade(
            SEMANTIC_FACADE,
            capability_id="soridormi.turn_in_place",
            provider_input_schema=PROVIDER_SCHEMA,
        )
        left = realize_semantic_capability_args(
            {"direction": "left", "duration_s": 3.0},
            facade=normalized,
            provider_input_schema=PROVIDER_SCHEMA,
            capability_id="soridormi.turn_in_place",
        )
        right = realize_semantic_capability_args(
            {"direction": "right", "turn_rate_radps": 0.2},
            facade=normalized,
            provider_input_schema=PROVIDER_SCHEMA,
            capability_id="soridormi.turn_in_place",
        )
        self.assertEqual(left, {"duration_s": 3.0, "yaw_radps": 0.12})
        self.assertEqual(right, {"yaw_radps": -0.2})

    async def test_planner_catalog_sees_semantic_schema_not_provider_yaw_sign(self) -> None:
        catalog = CapabilityCatalog(AgentCapabilityRegistry(), live_invoker=_CatalogInvoker())
        entries = await catalog.prompt_entries(scope="all", refresh=True)
        turn = next(item for item in entries if item.capability_id == "soridormi.turn_in_place")
        properties = turn.input_schema["properties"]
        self.assertIn("direction", properties)
        self.assertIn("turn_rate_radps", properties)
        self.assertNotIn("yaw_radps", properties)
        self.assertEqual(turn.input_schema["required"], ["direction"])

    async def test_runtime_validates_semantic_args_then_realizes_provider_args(self) -> None:
        invoker = _ExecutionInvoker()
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry, [turn_skill()])
        definition = registry.get("soridormi.turn_in_place")
        self.assertIn("direction", definition.input_schema["properties"])
        self.assertNotIn("yaw_radps", definition.input_schema["properties"])
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(SoridormiCapabilityProvider(invoker))

        execution = await submit_and_wait_terminal(
            runtime,
            InteractionResponse(
                interaction_id="semantic-turn",
                capabilities=[{
                    "request_id": "turn-right",
                    "capability_id": "soridormi.turn_in_place",
                    "args": {"direction": "right", "duration_s": 1.5},
                    "requires_confirmation": False,
                }],
            ),
            authorization=RuntimeAuthorization(safety_monitor_active=True),
        )
        self.assertEqual(execution.status, "completed")
        create = next(args for tool, args, _ in invoker.calls if tool == "soridormi.skill.create_plan")
        self.assertEqual(create["parameters"], {"duration_s": 1.5, "yaw_radps": -0.12})
        self.assertNotIn("direction", create["parameters"])

    async def test_provider_sign_change_does_not_change_planner_semantics(self) -> None:
        reversed_facade = {
            **SEMANTIC_FACADE,
            "provider_realizations": {
                "yaw_radps": {
                    **SEMANTIC_FACADE["provider_realizations"]["yaw_radps"],
                    "positive_direction": "right",
                    "negative_direction": "left",
                }
            },
        }
        left_default = realize_semantic_capability_args(
            {"direction": "left"},
            facade=SEMANTIC_FACADE,
            provider_input_schema=PROVIDER_SCHEMA,
            capability_id="default-frame",
        )
        left_reversed = realize_semantic_capability_args(
            {"direction": "left"},
            facade=reversed_facade,
            provider_input_schema=PROVIDER_SCHEMA,
            capability_id="reversed-frame",
        )
        self.assertEqual(left_default["yaw_radps"], 0.12)
        self.assertEqual(left_reversed["yaw_radps"], -0.12)
        self.assertEqual({"direction": "left"}, {"direction": "left"})
