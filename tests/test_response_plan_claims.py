from __future__ import annotations

import unittest

from orchestrator.runtime.response_plan import (
    validate_immediate_response_plan,
    validate_response_stage,
)
from shared.chromie_contracts.semantic_task import (
    ResponsePlan,
    ResponseStage,
    pending_action_stage_direction_claims,
)


class ResponsePlanClaimValidationTests(unittest.TestCase):
    @staticmethod
    def _snapshot(status: str, **evidence: bool) -> dict:
        return {
            "task_id": "task-1",
            "status": status,
            "semantic_goal": {
                "description": "Do the requested task.",
                "source_text": "Please do it.",
            },
            "goal_version": 1,
            "plan_version": 0,
            "open_information_gaps": [],
            "commitment_state": "evaluating",
            "evidence_summary": evidence,
        }

    def test_evaluating_immediate_stage_is_valid_for_planning_task(self) -> None:
        stage = ResponseStage(
            text="I will check how I can do that.",
            commitment_state="evaluating",
            covers_task_ids=["task-1"],
        )

        result = validate_response_stage(stage, [self._snapshot("planning")])

        self.assertTrue(result.accepted)
        self.assertEqual(result.errors, ())

    def test_accepted_claim_is_rejected_before_commit(self) -> None:
        stage = ResponseStage(
            text="I have accepted the task.",
            commitment_state="accepted",
            covers_task_ids=["task-1"],
        )

        result = validate_response_stage(stage, [self._snapshot("planning")])

        self.assertFalse(result.accepted)
        self.assertIn(
            "commitment_not_supported_by_task_state:task-1:planning:accepted",
            result.errors,
        )

    def test_completed_stage_requires_done_state_and_explicit_terminal_contract(self) -> None:
        stage = ResponseStage(
            text="The task is complete.",
            commitment_state="completed",
            must_not_claim_completion=False,
            covers_task_ids=["task-1"],
            claims=["completed"],
        )

        planning = validate_response_stage(stage, [self._snapshot("planning")])
        done = validate_response_stage(stage, [self._snapshot("done")])

        self.assertFalse(planning.accepted)
        self.assertTrue(done.accepted)

    def test_clarification_can_wait_for_user_before_task_status_changes(self) -> None:
        stage = ResponseStage(
            text="Which drink should I make iced?",
            speech_act="clarify",
            commitment_state="waiting_for_user",
            covers_task_ids=["task-1"],
        )

        result = validate_response_stage(stage, [self._snapshot("planning")])

        self.assertTrue(result.accepted)

    def test_unknown_task_id_is_rejected(self) -> None:
        stage = ResponseStage(
            text="I will check that.",
            commitment_state="evaluating",
            covers_task_ids=["missing-task"],
        )

        result = validate_response_stage(stage, [self._snapshot("planning")])

        self.assertFalse(result.accepted)
        self.assertIn("unknown_task_ids:missing-task", result.errors)

    def test_evidence_claim_requires_trusted_evidence_summary(self) -> None:
        stage = ResponseStage(
            text="I have the tool result.",
            commitment_state="accepted",
            covers_task_ids=["task-1"],
            claims=["tool_result_available"],
        )

        missing = validate_response_stage(stage, [self._snapshot("committed")])
        present = validate_response_stage(
            stage,
            [self._snapshot("committed", tool_result_available=True)],
        )

        self.assertFalse(missing.accepted)
        self.assertTrue(present.accepted)

    def test_unscoped_stage_cannot_claim_execution(self) -> None:
        stage = ResponseStage(
            text="I am executing it.",
            commitment_state="executing",
        )

        result = validate_response_stage(stage, [])

        self.assertFalse(result.accepted)
        self.assertIn(
            "unscoped_stage_may_only_use_process_commitment",
            result.errors,
        )

    def test_response_stage_contract_rejects_terminal_default(self) -> None:
        with self.assertRaises(ValueError):
            ResponseStage(
                text="Done.",
                commitment_state="completed",
            )

    def test_immediate_response_plan_parsing_and_validation(self) -> None:
        plan = ResponsePlan(
            immediate=ResponseStage(
                text="I am checking that.",
                commitment_state="evaluating",
                covers_task_ids=["task-1"],
            )
        )

        result = validate_immediate_response_plan(
            plan.model_dump(mode="json"),
            [self._snapshot("planning")],
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.stage.text, "I am checking that.")  # type: ignore[union-attr]

    def test_pending_action_stage_direction_is_derived_from_skill_id(self) -> None:
        claims = pending_action_stage_direction_claims(
            "*Blinks twice* Here is a joke.",
            ["soridormi.blink_eyes"],
        )
        prospective = pending_action_stage_direction_claims(
            "I will blink twice. Here is a joke.",
            ["soridormi.blink_eyes"],
        )

        self.assertEqual(claims, ["blink"])
        self.assertEqual(prospective, [])


if __name__ == "__main__":
    unittest.main()
