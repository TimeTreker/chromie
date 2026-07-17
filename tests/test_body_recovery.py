from __future__ import annotations

import unittest

from orchestrator.runtime.body_recovery import (
    build_body_recovery_confirmation,
    is_recoverable_body_result,
)
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult


class BodyRecoveryTests(unittest.TestCase):
    def test_recoverable_result_builds_request_bound_retry(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-grasp",
            speech=[
                {"text": "Trying now.", "timing": "immediate"},
                {"text": "Done.", "timing": "after_skills"},
            ],
            skills=[
                {
                    "request_id": "grasp-1",
                    "skill_id": "soridormi.grasp_object",
                    "args": {"object": "cup"},
                    "metadata": {"route_stage": "quick_intent"},
                }
            ],
            metadata={"language": "en-US"},
        )
        result = SkillResult(
            request_id="grasp-1",
            skill_id="soridormi.grasp_object",
            status="failed",
            reason_code="execution_incomplete",
            output={
                "completed": False,
                "recoverable": True,
                "user_message": "The object slipped.",
            },
        )

        recovery = build_body_recovery_confirmation(
            response,
            [result],
            max_attempts=2,
            timeout_s=10.0,
            language="en-US",
        )

        assert recovery is not None
        self.assertEqual(recovery.failed_request_ids, ("grasp-1",))
        self.assertEqual(recovery.retry_request_ids, ("grasp-1_recovery1",))
        self.assertEqual(
            recovery.confirmed_request_ids,
            frozenset({"grasp-1_recovery1"}),
        )
        self.assertIn("recoverable movement issue", recovery.prompt)
        self.assertIn("The object slipped", recovery.prompt)
        self.assertEqual(len(recovery.response.skills), 1)
        retry = recovery.response.skills[0]
        self.assertEqual(retry.request_id, "grasp-1_recovery1")
        self.assertTrue(retry.requires_confirmation)
        self.assertEqual(retry.skill_id, "soridormi.grasp_object")
        self.assertEqual(retry.args, {"object": "cup"})
        self.assertEqual(retry.metadata["body_recovery_attempt"], 1)
        self.assertEqual(retry.metadata["body_recovery_parent_request_id"], "grasp-1")
        self.assertEqual(retry.metadata["execution_mode"], "proposed")
        self.assertEqual(
            [speech.text for speech in recovery.response.speech],
            ["Done."],
        )

    def test_terminal_body_results_do_not_trigger_recovery(self) -> None:
        cases = (
            SkillResult(
                request_id="move-1",
                skill_id="soridormi.move_base",
                status="refused",
                reason_code="safety_monitor_refused",
                output={"recoverable": True},
            ),
            SkillResult(
                request_id="move-1",
                skill_id="soridormi.move_base",
                status="failed",
                reason_code="execute_failed_retryable",
                output={},
            ),
        )

        for result in cases:
            with self.subTest(status=result.status, reason_code=result.reason_code):
                self.assertFalse(is_recoverable_body_result(result))

    def test_retry_budget_exhaustion_returns_no_recovery(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-grasp",
            skills=[
                {
                    "request_id": "grasp-1_recovery1",
                    "skill_id": "soridormi.grasp_object",
                    "metadata": {"body_recovery_attempt": 1},
                }
            ],
        )
        result = SkillResult(
            request_id="grasp-1_recovery1",
            skill_id="soridormi.grasp_object",
            status="failed",
            reason_code="execute_failed_retryable",
            output={"recoverable": True},
        )

        recovery = build_body_recovery_confirmation(
            response,
            [result],
            max_attempts=1,
            timeout_s=10.0,
            language="en-US",
        )

        self.assertIsNone(recovery)


if __name__ == "__main__":
    unittest.main()
