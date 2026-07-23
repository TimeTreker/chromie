from __future__ import annotations

import hashlib
import unittest
from typing import Any

from orchestrator.runtime.outcome_response import compose_outcome_response
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
    aggregate_execution_status,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)


def _plan(
    statuses: list[tuple[str, list[str]]],
    *,
    plan_id: str = "plan-post-execution",
) -> CanonicalPlan:
    goal_ids = [goal_id for goal_id, _ in statuses]
    steps: list[dict[str, Any]] = []
    goal_outcomes: list[dict[str, Any]] = []
    for goal_index, (goal_id, evidence_statuses) in enumerate(statuses, start=1):
        step_ids: list[str] = []
        for step_index, _status in enumerate(evidence_statuses, start=1):
            step_id = f"step-{goal_index}-{step_index}"
            step_ids.append(step_id)
            steps.append(
                {
                    "step_id": step_id,
                    "skill_id": f"test.skill.{goal_index}.{step_index}",
                    "source_goal_ids": [goal_id],
                    "reason_summary": "Execute one bounded test step.",
                }
            )
        goal_outcomes.append(
            {
                "goal_id": goal_id,
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": step_ids,
            }
        )
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="execute",
        coverage="complete",
        confidence=0.95,
        goal_ids=goal_ids,
        goal_summary="Execute the requested tasks.",
        steps=steps,
        goal_outcomes=goal_outcomes,
    )


def _observation(data: dict[str, Any]) -> ModelObservation:
    payload = repr(data).encode("utf-8")
    return ModelObservation(
        status="available",
        data=data,
        schema_validated=True,
        output_sha256=hashlib.sha256(payload).hexdigest(),
        output_size_bytes=len(payload),
    )


def _bundle(
    plan: CanonicalPlan,
    statuses: list[tuple[str, list[str]]],
    *,
    observations: dict[str, ModelObservation] | None = None,
    provider_messages: dict[str, str] | None = None,
) -> ExecutionOutcomeBundle:
    observations = observations or {}
    provider_messages = provider_messages or {}
    evidence: list[ExecutionEvidence] = []
    goal_outcomes: list[GoalExecutionOutcome] = []
    steps_by_id = {step.step_id: step for step in plan.steps}

    for goal_index, (goal_id, evidence_statuses) in enumerate(statuses, start=1):
        plan_outcome = plan.outcome_for_goal(goal_id)
        assert plan_outcome is not None
        evidence_ids: list[str] = []
        completed_step_ids: list[str] = []
        unresolved_step_ids: list[str] = []
        for step_index, status in enumerate(evidence_statuses, start=1):
            step_id = plan_outcome.step_ids[step_index - 1]
            step = steps_by_id[step_id]
            evidence_id = f"evidence-{goal_index}-{step_index}"
            evidence_ids.append(evidence_id)
            if status == "completed":
                completed_step_ids.append(step_id)
            else:
                unresolved_step_ids.append(step_id)
            evidence.append(
                ExecutionEvidence(
                    evidence_id=evidence_id,
                    request_id=f"request-{goal_index}-{step_index}",
                    step_id=step_id,
                    skill_id=step.skill_id,
                    source_goal_ids=[goal_id],
                    status=status,
                    reported_status=status,
                    provider_id="test-provider",
                    observation=observations.get(evidence_id),
                    message=provider_messages.get(evidence_id, ""),
                    missing_result=status == "not_run",
                )
            )
        goal_outcomes.append(
            GoalExecutionOutcome(
                goal_id=goal_id,
                status=aggregate_execution_status(evidence_statuses),
                step_ids=list(plan_outcome.step_ids),
                evidence_ids=evidence_ids,
                completed_step_ids=completed_step_ids,
                unresolved_step_ids=unresolved_step_ids,
            )
        )

    return ExecutionOutcomeBundle(
        outcome_id="outcome-post-execution",
        turn_id="turn-post-execution",
        interaction_id="interaction-post-execution",
        canonical_plan_id=plan.plan_id,
        canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
        canonical_goal_ids=list(plan.goal_ids),
        aggregate_status=aggregate_execution_status(
            [item.status for item in goal_outcomes]
        ),
        evidence=evidence,
        goal_outcomes=goal_outcomes,
    )


class OutcomeResponseTests(unittest.TestCase):
    def test_covers_every_executable_goal_once_in_canonical_order(self) -> None:
        statuses = [
            ("goal-weather", ["completed"]),
            ("goal-motion", ["failed"]),
            ("goal-memory", ["cancelled"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)
        reversed_payload = bundle.model_dump(mode="python")
        reversed_payload["goal_outcomes"] = list(
            reversed(reversed_payload["goal_outcomes"])
        )
        bundle = ExecutionOutcomeBundle.model_validate(reversed_payload)

        response = compose_outcome_response(bundle, plan, "en-US")

        self.assertEqual(response.interaction_id, bundle.interaction_id)
        self.assertEqual(response.skills, [])
        self.assertFalse(response.requires_confirmation)
        self.assertEqual(
            [
                item.metadata["covers_goal_ids"]
                for item in response.speech
            ],
            [["goal-weather"], ["goal-motion"], ["goal-memory"]],
        )
        self.assertEqual(
            [item.text for item in response.speech],
            [
                "The first requested task completed.",
                "The second requested task failed.",
                "The third requested task was cancelled.",
            ],
        )

    def test_preserves_all_terminal_status_distinctions_in_chinese(self) -> None:
        statuses = [
            ("goal-completed", ["completed"]),
            ("goal-partial", ["completed", "failed"]),
            ("goal-failed", ["failed"]),
            ("goal-refused", ["refused"]),
            ("goal-timeout", ["timed_out"]),
            ("goal-cancelled", ["cancelled"]),
            ("goal-not-run", ["not_run"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        response = compose_outcome_response(bundle, plan, "zh-CN")

        self.assertEqual(
            [item.text for item in response.speech],
            [
                "第1个请求的任务已完成。",
                "第2个请求的任务仅部分完成。",
                "第3个请求的任务执行失败。",
                "第4个请求的任务被拒绝执行。",
                "第5个请求的任务执行超时。",
                "第6个请求的任务已取消。",
                "第7个请求的任务未执行。",
            ],
        )
        self.assertEqual(
            [
                item["status"]
                for item in response.metadata["per_goal_evidence_refs"]
            ],
            [
                "completed",
                "partial",
                "failed",
                "refused",
                "timed_out",
                "cancelled",
                "not_run",
            ],
        )

    def test_all_uncompleted_mixture_never_claims_partial_completion(self) -> None:
        statuses = [
            ("goal-failed", ["failed"]),
            ("goal-timeout", ["timed_out"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        response = compose_outcome_response(bundle, plan, "en-US")

        self.assertEqual(bundle.aggregate_status, "failed")
        self.assertEqual(response.reason, "post_execution_failed")
        self.assertEqual(
            [item.metadata["goal_status"] for item in response.speech],
            ["failed", "timed_out"],
        )
        self.assertEqual(
            [item.text for item in response.speech],
            [
                "The first requested task failed.",
                "The second requested task timed out.",
            ],
        )
        self.assertNotIn(
            "partial",
            " ".join(item.text for item in response.speech).casefold(),
        )

    def test_single_goal_all_uncompleted_steps_uses_conservative_failure(
        self,
    ) -> None:
        statuses = [("goal-mixed-failure", ["failed", "timed_out"])]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        response = compose_outcome_response(bundle, plan, "en-US")

        self.assertEqual(bundle.goal_outcomes[0].status, "failed")
        self.assertEqual(bundle.aggregate_status, "failed")
        self.assertEqual(
            response.speech[0].text,
            "The requested task failed.",
        )

    def test_partial_wording_requires_real_completed_work(self) -> None:
        statuses = [("goal-partial", ["completed", "failed"])]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        response = compose_outcome_response(bundle, plan, "en-US")

        self.assertEqual(bundle.goal_outcomes[0].status, "partial")
        self.assertEqual(
            response.speech[0].text,
            "The requested task was partially completed.",
        )

    def test_uses_only_available_model_observation_for_provider_output(self) -> None:
        statuses = [("goal-weather", ["completed"])]
        plan = _plan(statuses)
        without_observation = _bundle(
            plan,
            statuses,
            provider_messages={
                "evidence-1-1": "Internal provider message: 28 degrees."
            },
        )

        conservative = compose_outcome_response(
            without_observation,
            plan,
            "en",
        )

        self.assertEqual(
            conservative.speech[0].text,
            "The requested task completed.",
        )
        self.assertNotIn("28", conservative.speech[0].text)

        with_observation = _bundle(
            plan,
            statuses,
            observations={
                "evidence-1-1": _observation(
                    {"summary": "It is raining in Beijing"}
                )
            },
        )
        observed = compose_outcome_response(with_observation, plan, "en")

        self.assertEqual(
            observed.speech[0].text,
            (
                "The requested task completed. "
                "Observed output: It is raining in Beijing."
            ),
        )
        self.assertEqual(
            observed.speech[0].metadata["observed_evidence_ids"],
            ["evidence-1-1"],
        )

    def test_does_not_speak_internal_identifiers_from_observation(self) -> None:
        statuses = [("goal-weather", ["completed"])]
        plan = _plan(statuses)
        bundle = _bundle(
            plan,
            statuses,
            observations={
                "evidence-1-1": _observation(
                    {
                        "summary": (
                            "goal-weather completed under "
                            "plan-post-execution"
                        )
                    }
                )
            },
        )

        response = compose_outcome_response(bundle, plan, "en")

        self.assertEqual(
            response.speech[0].text,
            "The requested task completed.",
        )
        self.assertNotIn("goal-weather", response.speech[0].text)
        self.assertNotIn("plan-post-execution", response.speech[0].text)

    def test_metadata_retains_exact_bundle_fingerprint_and_evidence_refs(self) -> None:
        statuses = [
            ("goal-a", ["completed"]),
            ("goal-b", ["timed_out"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        response = compose_outcome_response(bundle, plan, "en")

        self.assertEqual(
            response.metadata["execution_outcome_bundle"],
            bundle.model_dump(mode="json"),
        )
        self.assertEqual(
            response.metadata["execution_outcome_fingerprint"],
            execution_outcome_fingerprint(bundle),
        )
        self.assertEqual(
            response.metadata["canonical_plan_fingerprint"],
            canonical_plan_fingerprint(plan),
        )
        self.assertEqual(
            [
                item["evidence_ids"]
                for item in response.metadata["per_goal_evidence_refs"]
            ],
            [["evidence-1-1"], ["evidence-2-1"]],
        )

    def test_fails_closed_on_plan_id_or_fingerprint_mismatch(self) -> None:
        statuses = [("goal-a", ["completed"])]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        wrong_id = bundle.model_dump(mode="python")
        wrong_id["canonical_plan_id"] = "another-plan"
        with self.assertRaisesRegex(ValueError, "plan ID mismatch"):
            compose_outcome_response(
                ExecutionOutcomeBundle.model_validate(wrong_id),
                plan,
                "en",
            )

        wrong_fingerprint = bundle.model_dump(mode="python")
        wrong_fingerprint["canonical_plan_fingerprint"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            compose_outcome_response(
                ExecutionOutcomeBundle.model_validate(wrong_fingerprint),
                plan,
                "en",
            )

    def test_fails_closed_on_goal_order_or_step_skill_mismatch(self) -> None:
        statuses = [
            ("goal-a", ["completed"]),
            ("goal-b", ["completed"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        wrong_order = bundle.model_dump(mode="python")
        wrong_order["canonical_goal_ids"] = list(
            reversed(wrong_order["canonical_goal_ids"])
        )
        with self.assertRaisesRegex(ValueError, "goal correlation or order"):
            compose_outcome_response(
                ExecutionOutcomeBundle.model_validate(wrong_order),
                plan,
                "en",
            )

        wrong_skill = bundle.model_dump(mode="python")
        wrong_skill["evidence"][0]["skill_id"] = "test.skill.unrelated"
        with self.assertRaisesRegex(ValueError, "skill does not match"):
            compose_outcome_response(
                ExecutionOutcomeBundle.model_validate(wrong_skill),
                plan,
                "en",
            )

    def test_rejects_non_execution_plan(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-response-only",
            planner_tier="fast",
            disposition="respond",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-chat"],
            goal_summary="Answer directly.",
            response_text="Hello.",
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-response-only",
            turn_id="turn-response-only",
            interaction_id="interaction-response-only",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_goal_ids=list(plan.goal_ids),
            non_execution_goal_ids=list(plan.goal_ids),
            aggregate_status="not_run",
        )

        with self.assertRaisesRegex(ValueError, "executable canonical goal"):
            compose_outcome_response(bundle, plan, "en")


if __name__ == "__main__":
    unittest.main()
