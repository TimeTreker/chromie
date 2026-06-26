from __future__ import annotations

import unittest

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.main import _catalog_decision, _validate_llm_capability_decision
from router.app.schema import RouteDecision, RouteRequest


PLANNING = {
    "capability_id": "soridormi.motion.create_plan",
    "score": 0.91,
    "available": True,
    "interaction_executable": False,
    "invocation_kind": "mcp_tool",
}

WALK = {
    "capability_id": "soridormi.walk_velocity",
    "score": 0.62,
    "available": True,
    "interaction_executable": True,
    "invocation_kind": "named_skill",
}


def catalog_result() -> CapabilityCatalogResult:
    return CapabilityCatalogResult(
        query="walk forward",
        matched=True,
        suggested_route="robot_action",
        suggested_agents=["capability_agent", "speaker_agent"],
        matches=[PLANNING, WALK],
        catalog_version=7,
    )


class ConstrainedLlmCapabilityRoutingTests(unittest.TestCase):
    def test_valid_executable_selection_is_preserved(self) -> None:
        request = RouteRequest(text="Walk forward at 0.15 speed for 5 seconds.")
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent"],
            intent="capability:soridormi.walk_velocity",
            confidence=0.95,
            source="llm",
        )

        result = _validate_llm_capability_decision(request, decision, catalog_result())

        self.assertEqual(result.route, "robot_action")
        self.assertEqual(result.intent, "capability:soridormi.walk_velocity")
        self.assertIn("safety_agent", result.agents)

    def test_non_executable_robot_selection_is_left_for_agent_planning(self) -> None:
        request = RouteRequest(text="Walk forward at 0.15 speed for 5 seconds.")
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent"],
            intent="capability:soridormi.motion.create_plan",
            confidence=0.92,
            source="llm",
        )

        result = _validate_llm_capability_decision(request, decision, catalog_result())

        self.assertEqual(result.route, "robot_action")
        self.assertEqual(result.intent, "robot_action")
        self.assertIn("capability_agent", result.agents)
        self.assertIn("safety_agent", result.agents)
        self.assertIn("cleared invalid capability selection", result.reason or "")

    def test_explicit_planning_request_does_not_execute_fallback_skill(self) -> None:
        request = RouteRequest(text="Create a motion plan to walk forward without executing it.")
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent"],
            intent="capability:soridormi.motion.create_plan",
            confidence=0.92,
            source="llm",
        )

        result = _validate_llm_capability_decision(request, decision, catalog_result())

        self.assertEqual(result.route, "clarify")
        self.assertEqual(result.intent, "clarify_capability_selection")

    def test_catalog_fallback_never_routes_planning_tool_as_robot_action(self) -> None:
        request = RouteRequest(text="Walk forward.")

        result = _catalog_decision(request, catalog_result())

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.intent, "capability:soridormi.walk_velocity")


if __name__ == "__main__":
    unittest.main()
