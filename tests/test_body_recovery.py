from __future__ import annotations

import unittest

from orchestrator.runtime.body_recovery import (
    build_body_recovery_confirmation,
    is_recoverable_body_result,
)
from orchestrator.runtime.outcome_reconciliation import (
    ExecutionOutcomeReconciler,
)
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)


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

    def test_cognitive_retry_derives_an_exact_failed_step_plan(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-two-step",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-walk", "goal-look"],
            steps=[
                {
                    "step_id": "step-walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"distance_m": 1.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "step-look",
                    "skill_id": "soridormi.look_left",
                    "args": {},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-look"],
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-walk"],
                },
                {
                    "goal_id": "goal-look",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-look"],
                },
            ],
        )
        parent_fingerprint = canonical_plan_fingerprint(plan)
        response = InteractionResponse(
            interaction_id="interaction-two-step",
            skills=[
                {
                    "request_id": "request-walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"distance_m": 1.0},
                    "timing": "sequential",
                    "metadata": {
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": parent_fingerprint,
                        "step_id": "step-walk",
                        "source_goal_ids": ["goal-walk"],
                    },
                },
                {
                    "request_id": "request-look",
                    "skill_id": "soridormi.look_left",
                    "timing": "sequential",
                    "metadata": {
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": parent_fingerprint,
                        "step_id": "step-look",
                        "source_goal_ids": ["goal-look"],
                    },
                },
            ],
            metadata={
                "cognitive_runtime_apply": True,
                "canonical_plan": plan.model_dump(mode="json"),
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": parent_fingerprint,
                "turn_id": "turn-two-step",
            },
        )
        results = [
            SkillResult(
                request_id="request-walk",
                skill_id="soridormi.walk_forward",
                status="failed",
                reason_code="path_temporarily_blocked",
                output={"recoverable": True},
            ),
            SkillResult(
                request_id="request-look",
                skill_id="soridormi.look_left",
                status="completed",
            ),
        ]

        recovery = build_body_recovery_confirmation(
            response,
            results,
            max_attempts=1,
            timeout_s=10.0,
            language="en-US",
        )

        assert recovery is not None
        retry_plan = CanonicalPlan.model_validate(
            recovery.response.metadata["canonical_plan"]
        )
        self.assertEqual(retry_plan.goal_ids, ["goal-walk"])
        self.assertEqual(
            [step.step_id for step in retry_plan.steps],
            ["step-walk"],
        )
        retry_request = recovery.response.skills[0]
        self.assertEqual(
            retry_request.metadata["canonical_plan_id"],
            retry_plan.plan_id,
        )
        self.assertEqual(
            retry_request.metadata["canonical_plan_fingerprint"],
            canonical_plan_fingerprint(retry_plan),
        )
        bundle = ExecutionOutcomeReconciler().build(
            turn_id="turn-two-step",
            plan=retry_plan,
            interaction_id=recovery.response.interaction_id,
            requests=recovery.response.skills,
            results=[
                SkillResult(
                    request_id=retry_request.request_id,
                    skill_id=retry_request.skill_id,
                    status="completed",
                )
            ],
            output_schemas={retry_request.request_id: {}},
        )
        self.assertEqual(bundle.aggregate_status, "completed")
        self.assertEqual(
            [outcome.goal_id for outcome in bundle.goal_outcomes],
            ["goal-walk"],
        )

    def test_recovery_is_blocked_when_a_committed_sibling_has_no_result(
        self,
    ) -> None:
        response = InteractionResponse(
            interaction_id="interaction-missing-sibling",
            skills=[
                {
                    "request_id": "request-a",
                    "skill_id": "soridormi.walk_forward",
                },
                {
                    "request_id": "request-b",
                    "skill_id": "soridormi.look_left",
                },
            ],
        )
        returned_failure = SkillResult(
            request_id="request-a",
            skill_id="soridormi.walk_forward",
            status="failed",
            reason_code="path_temporarily_blocked",
            output={"recoverable": True},
        )

        recovery = build_body_recovery_confirmation(
            response,
            [returned_failure],
            max_attempts=1,
            timeout_s=10.0,
            language="en-US",
        )

        self.assertIsNone(recovery)

    def test_cognitive_recovery_is_blocked_when_non_body_sibling_is_missing(
        self,
    ) -> None:
        plan = CanonicalPlan(
            plan_id="plan-mixed-shared-goal",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-combined"],
            steps=[
                {
                    "step_id": "step-move",
                    "skill_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-combined"],
                },
                {
                    "step_id": "step-weather",
                    "skill_id": "chromie.weather.lookup",
                    "source_goal_ids": ["goal-combined"],
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-combined",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-move", "step-weather"],
                }
            ],
        )
        fingerprint = canonical_plan_fingerprint(plan)
        response = InteractionResponse(
            interaction_id="interaction-mixed-shared-goal",
            skills=[
                {
                    "request_id": "request-move",
                    "skill_id": "soridormi.walk_forward",
                    "metadata": {
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                        "step_id": "step-move",
                        "source_goal_ids": ["goal-combined"],
                    },
                },
                {
                    "request_id": "request-weather",
                    "skill_id": "chromie.weather.lookup",
                    "metadata": {
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                        "step_id": "step-weather",
                        "source_goal_ids": ["goal-combined"],
                    },
                },
            ],
            metadata={
                "cognitive_runtime_apply": True,
                "canonical_plan": plan.model_dump(mode="json"),
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
            },
        )
        returned_failure = SkillResult(
            request_id="request-move",
            skill_id="soridormi.walk_forward",
            status="failed",
            reason_code="path_temporarily_blocked",
            output={"recoverable": True},
        )

        recovery = build_body_recovery_confirmation(
            response,
            [returned_failure],
            max_attempts=1,
            timeout_s=10.0,
            language="en-US",
        )

        self.assertIsNone(recovery)


if __name__ == "__main__":
    unittest.main()
