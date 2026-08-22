from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone
from typing import Any

from orchestrator.runtime.outcome_reconciliation import (
    ExecutionOutcomeReconciler,
    planner_execution_outcome_truth,
)
from shared.chromie_contracts.execution_outcome import (
    ClaimQualification,
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
    aggregate_execution_status,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.interaction import CapabilityRequest, CapabilityResult
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.plan import canonical_plan_fingerprint


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
                    "capability_id": f"test.skill.{goal_index}.{step_index}",
                    "timing": "sequential",
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
                    capability_id=step.capability_id,
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


def _require_unestablished_completion(
    bundle: ExecutionOutcomeBundle,
    *,
    status: str = "insufficient",
) -> ExecutionOutcomeBundle:
    raw = bundle.model_dump(mode="python")
    raw_evidence = raw["evidence"][0]
    raw_evidence["metadata"] = {
        **raw_evidence.get("metadata", {}),
        "completion_qualification_required": True,
    }
    raw_evidence["completion_qualification"] = ClaimQualification(
        claim="requested capability completion is established",
        status=status,
        policy_sha256="a" * 64,
        evidence_ids=[raw_evidence["evidence_id"]],
        reason_codes=["completion_evidence_insufficient"],
        evaluated_at=datetime.now(timezone.utc),
    ).model_dump(mode="python")
    return ExecutionOutcomeBundle.model_validate(raw)


class OutcomeTruthProjectionTests(unittest.TestCase):
    def test_projection_preserves_terminal_goal_truth_without_wording(self) -> None:
        statuses = [
            ("goal-weather", ["completed"]),
            ("goal-motion", ["failed"]),
            ("goal-memory", ["cancelled"]),
        ]
        plan = _plan(statuses)
        bundle = _bundle(plan, statuses)

        projection = planner_execution_outcome_truth(bundle)

        self.assertEqual(projection["aggregate_status"], bundle.aggregate_status)
        self.assertEqual(
            [item["status"] for item in projection["goal_outcomes"]],
            ["completed", "failed", "cancelled"],
        )
        self.assertEqual(
            [item["status"] for item in projection["evidence"]],
            ["completed", "failed", "cancelled"],
        )
        rendered = repr(projection)
        self.assertNotIn("Done.", rendered)
        self.assertNotIn("I cannot do that.", rendered)
        self.assertNotIn("好啦。", rendered)

    def test_projection_preserves_unestablished_completion_qualification(self) -> None:
        statuses = [("goal-motion", ["completed"])]
        plan = _plan(statuses)
        bundle = _require_unestablished_completion(_bundle(plan, statuses))

        projection = planner_execution_outcome_truth(bundle)
        qualification = projection["goal_outcomes"][0]["completion_qualification"]

        self.assertTrue(qualification["required"])
        self.assertFalse(qualification["established"])
        self.assertEqual(
            qualification["qualifications"][0]["status"],
            "insufficient",
        )


    def test_projection_preserves_provider_retryability_as_fact_only(self) -> None:
        statuses = [("goal-motion", ["failed"])]
        plan = _plan(statuses, plan_id="plan-recoverable-motion")
        step = plan.steps[0]
        request = CapabilityRequest(
            request_id="request-motion",
            capability_id=step.capability_id,
            args={},
            timing="sequential",
            metadata={
                "source": "goal_driven_canonical_plan",
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": canonical_plan_fingerprint(plan),
                "step_id": step.step_id,
                "source_goal_ids": list(step.source_goal_ids),
            },
        )
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="failed",
            reason_code="path_temporarily_blocked",
            output={
                "recovery": {
                    "recoverable": True,
                    "retryable": True,
                    "failure_class": "b_level_recovery",
                    "user_message": "do not project this provider wording",
                }
            },
        )
        bundle = ExecutionOutcomeReconciler().build(
            turn_id="turn-recoverable-motion",
            plan=plan,
            interaction_id="interaction-recoverable-motion",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: {}},
        )

        projection = planner_execution_outcome_truth(bundle)
        recovery = projection["evidence"][0]["provider_retryability"]

        self.assertEqual(
            recovery,
            {
                "recoverable": True,
                "retryable": True,
                "failure_class": "b_level_recovery",
            },
        )
        rendered = repr(projection)
        self.assertNotIn("do not project this provider wording", rendered)
        self.assertNotIn("try again", rendered.casefold())
        self.assertNotIn("confirm", rendered.casefold())

    def test_projection_excludes_provider_message_and_observation_payload(self) -> None:
        secret = "NEVER-SPEAK-THIS-SECRET"
        statuses = [("goal-weather", ["failed"])]
        plan = _plan(statuses)
        bundle = _bundle(
            plan,
            statuses,
            provider_messages={"evidence-1-1": secret},
        )

        projection = planner_execution_outcome_truth(bundle)
        rendered = repr(projection)

        self.assertNotIn(secret, rendered)
        self.assertEqual(projection["evidence"][0]["status"], "failed")
        self.assertEqual(projection["evidence"][0]["observation_status"], "none")


if __name__ == "__main__":
    unittest.main()
