from __future__ import annotations

from agent.app import goal_association_validation as ga_validation

import unittest

from agent.app import planner_validation
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution


class PlannerCommunicationBoundaryTests(unittest.TestCase):
    def test_failed_planner_activity_validation_dispatches_no_provider(self) -> None:
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            fallback_reason="planner communicative activity invalid",
            metadata={
                "failure_stage": "planner_communicative_activity_validation"
            },
        )

        summary = VoiceAssistant._cognitive_resolution_summary(resolution)

        self.assertFalse(summary["interaction_response_constructed"])
        self.assertEqual(summary["provider_request_count"], 0)
        self.assertFalse(summary["provider_dispatch_possible"])


class GoalAndConservationRegressionTests(unittest.TestCase):
    def test_goal_association_has_no_independent_coverage_authority(self) -> None:
        self.assertFalse(
            hasattr(ga_validation, "responsibility_coverage_required")
        )
        self.assertFalse(hasattr(ga_validation, "coverage_verdict"))

    def test_planner_has_no_independent_coordinated_coverage_auditor(self) -> None:
        self.assertFalse(hasattr(planner_validation, "coordinated_action_goal_ids"))


if __name__ == "__main__":
    unittest.main()
