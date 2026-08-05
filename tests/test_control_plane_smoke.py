from __future__ import annotations

import unittest

from scripts.control_plane_smoke import (
    DEFAULT_GOAL_ID,
    DEFAULT_TEXT,
    build_core_request,
    build_fast_plan_request,
)
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.route import RouteDecision


class ControlPlaneSmokeContractTests(unittest.TestCase):
    def test_builds_current_gateway_core_contract(self) -> None:
        request = build_core_request()

        self.assertEqual(request.turn_envelope.admission, "admit")
        self.assertEqual(request.turn_envelope.normalized_input.text, DEFAULT_TEXT)
        self.assertEqual(
            request.turn_envelope.turn_id,
            request.context_snapshot.turn_id,
        )
        self.assertEqual(
            request.turn_envelope.context_refs,
            request.context_snapshot.references,
        )

    def test_projects_core_result_into_fast_planner_contract(self) -> None:
        core_request = build_core_request()
        decision = RouteDecision(
            route="chat",
            agents=["conversation_agent", "speaker_agent"],
            intent="greeting",
            confidence=0.99,
            language="en-US",
            needs_agent=True,
            should_speak=True,
            source="llm",
        )
        interpretation = CoreInterpretationResult.from_route_decision(
            envelope=core_request.turn_envelope,
            decision=decision,
        )

        request = build_fast_plan_request(interpretation)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(
            request.context["goal_association_resolution"]["new_goals"][0]["goal_id"],
            DEFAULT_GOAL_ID,
        )
        self.assertEqual(request.context["active_goal_snapshots"], [])
        self.assertEqual(request.history, [])


if __name__ == "__main__":
    unittest.main()
