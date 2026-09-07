from __future__ import annotations

import unittest

from agent.app.inference_compute import (
    CognitionComputeClass,
    compute_class_for_purpose,
    compute_rank,
    goal_interpreter_compute_class,
)


class InferenceComputePolicyTests(unittest.TestCase):
    def test_relative_rank_protects_foreground_from_deliberation(self) -> None:
        ordered = [
            CognitionComputeClass.REALTIME,
            CognitionComputeClass.INTERACTIVE,
            CognitionComputeClass.CONTINUITY,
            CognitionComputeClass.DELIBERATIVE,
            CognitionComputeClass.BACKGROUND,
        ]

        self.assertEqual([compute_rank(item) for item in ordered], [4, 3, 2, 1, 0])

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

    def test_goal_interpreter_depths_share_authority_but_not_compute_class(self) -> None:
        self.assertEqual(
            goal_interpreter_compute_class("goal_interpretation_fast"),
            CognitionComputeClass.INTERACTIVE,
        )
        self.assertEqual(
            goal_interpreter_compute_class("goal_interpretation_deep"),
            CognitionComputeClass.DELIBERATIVE,
        )
        self.assertEqual(
            goal_interpreter_compute_class("startup_warm"),
            CognitionComputeClass.BACKGROUND,
        )


if __name__ == "__main__":
    unittest.main()
