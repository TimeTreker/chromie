from __future__ import annotations

import unittest

from agent.app.goal_association import (
    GoalAssociationModelOutput,
    GoalAssociationResolver,
)
from agent.app.planner_contract import coordinated_action_goal_ids
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution


class PlannerCommunicationBoundaryTests(unittest.TestCase):
    def test_failed_planner_activity_validation_dispatches_no_provider(self) -> None:
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="robot_action",
            fallback_reason="planner communicative activity invalid",
            metadata={
                "failure_stage": "planner_communicative_activity_validation"
            },
        )

        summary = VoiceAssistant._cognitive_resolution_summary(resolution)

        self.assertFalse(summary["interaction_response_constructed"])
        self.assertEqual(summary["provider_request_count"], 0)
        self.assertFalse(summary["provider_dispatch_possible"])


class GoalAndCoverageRegressionTests(unittest.TestCase):
    def test_single_new_goal_with_retained_context_requires_coverage_proof(self) -> None:
        output = GoalAssociationModelOutput.model_validate(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "source_responsibility_refs": ["r1"],
                        "description": "Perform several independently observable outcomes together.",
                        "output_mode": "capability_work",
                    }
                ],
                "confidence": 1.0,
            }
        )

        required = GoalAssociationResolver._responsibility_coverage_required(
            output,
            request=object(),
        )

        self.assertTrue(required)

    def test_typed_resource_goal_always_requires_coverage_audit(self) -> None:
        goal_ids = coordinated_action_goal_ids(
            [
                {
                    "goal_id": "goal-resource",
                    "metadata": {"responsibility_kind": "capability_dependent"},
                    "resource_responsibility": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource": {
                            "kind": "information",
                            "description": "requested performance content",
                        },
                    },
                    "object": {"bindings": {}},
                }
            ]
        )

        self.assertEqual(goal_ids, {"goal-resource"})


if __name__ == "__main__":
    unittest.main()
