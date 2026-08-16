from __future__ import annotations

import unittest

from scripts.control_plane_smoke import (
    DEFAULT_GOAL_ID,
    DEFAULT_TEXT,
    build_core_request,
    build_fast_plan_request,
)
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult


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
        interpretation = CoreInterpretationResult(
            turn_id=core_request.turn_envelope.turn_id,
            session_id=core_request.turn_envelope.session_id,
            confidence=0.99,
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "socially reciprocate the user's greeting",
                    "bindings": {},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.99,
                }
            ],
        )

        request = build_fast_plan_request(interpretation)

        self.assertEqual(len(request.responsibilities), 1)
        self.assertEqual(request.responsibilities[0].local_ref, "r1")
        self.assertEqual(
            request.context["goal_association_resolution"]["new_goals"][0]["goal_id"],
            DEFAULT_GOAL_ID,
        )
        self.assertEqual(request.context["active_goal_snapshots"], [])
        self.assertEqual(request.history, [])


if __name__ == "__main__":
    unittest.main()
