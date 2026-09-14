from __future__ import annotations

import unittest

from agent.app.inference_compute import (
    CognitionComputeClass,
    compute_class_for_purpose,
    compute_rank,
    goal_interpreter_compute_class,
)


class InferenceComputePolicyTests(unittest.TestCase):
    def test_social_response_precedes_work_in_each_independent_engine(self) -> None:
        self.assertGreater(
            compute_rank(compute_class_for_purpose("social_cognition")),
            compute_rank(compute_class_for_purpose("fast_planner")),
        )
        self.assertGreater(
            compute_rank(compute_class_for_purpose("social_cognition_deep")),
            compute_rank(compute_class_for_purpose("deep_planner")),
        )

    def test_relative_rank_protects_foreground_from_deliberation(self) -> None:
        ordered = [
            CognitionComputeClass.REALTIME,
            CognitionComputeClass.INTERPRETATION,
            CognitionComputeClass.CONTINUITY,
            CognitionComputeClass.INTERACTIVE,
            CognitionComputeClass.DELIBERATIVE,
            CognitionComputeClass.BACKGROUND,
        ]

        self.assertEqual([compute_rank(item) for item in ordered], [5, 4, 3, 2, 1, 0])
        roles = ["social_cognition", "goal_interpreter_fast", "goal_association", "fast_planner"]
        ranks = [compute_rank(compute_class_for_purpose(role)) for role in roles]
        self.assertTrue(all(left > right for left, right in zip(ranks, ranks[1:])))

    def test_known_purposes_map_without_semantic_content_inspection(self) -> None:
        self.assertEqual(
            compute_class_for_purpose("fast_planner"),
            CognitionComputeClass.INTERACTIVE,
        )
        self.assertEqual(
            compute_class_for_purpose("goal_association"),
            CognitionComputeClass.CONTINUITY,
        )
        self.assertEqual(
            compute_class_for_purpose("deep_planner"),
            CognitionComputeClass.DELIBERATIVE,
        )
        self.assertEqual(
            compute_class_for_purpose("reflection"),
            CognitionComputeClass.BACKGROUND,
        )

    def test_unknown_purpose_defaults_to_interactive(self) -> None:
        self.assertEqual(
            compute_class_for_purpose("future_role"),
            CognitionComputeClass.INTERACTIVE,
        )

    def test_goal_interpreter_priority_is_independent_of_model_depth(self) -> None:
        self.assertEqual(
            goal_interpreter_compute_class("goal_interpretation_fast"),
            CognitionComputeClass.INTERPRETATION,
        )
        self.assertEqual(
            goal_interpreter_compute_class("goal_interpretation_deep"),
            CognitionComputeClass.INTERPRETATION,
        )
        self.assertEqual(
            goal_interpreter_compute_class("startup_warm"),
            CognitionComputeClass.BACKGROUND,
        )


if __name__ == "__main__":
    unittest.main()
