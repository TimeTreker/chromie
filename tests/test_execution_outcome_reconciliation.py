from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from orchestrator.runtime.outcome_reconciliation import (
    planner_execution_outcome_truth,
    ExecutionOutcomeReconciler,
    build_execution_outcome_bundle,
)
from shared.chromie_contracts.execution_outcome import (
    ClaimQualificationPolicy,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ProviderPostconditionEvidence,
    aggregate_execution_status,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.plan import canonical_plan_fingerprint


def output_schema(*properties: str) -> dict:
    return {
        "type": "object",
        "properties": {
            name: {"type": "string"} for name in properties
        },
        "additionalProperties": False,
    }


def single_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-weather",
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=0.96,
        goal_ids=["goal-weather"],
        goal_summary="Look up the weather.",
        steps=[
            {
                "step_id": "lookup",
                "capability_id": "chromie.weather.lookup",
                "args": {"city": "Beijing"},
                "timing": "sequential",
                "source_goal_ids": ["goal-weather"],
            }
        ],
    )


def two_goal_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-two-goals",
        planner_tier="deep",
        disposition="execute",
        coverage="complete",
        confidence=0.93,
        goal_ids=["goal-weather", "goal-calendar"],
        goal_summary="Check weather and calendar.",
        steps=[
            {
                "step_id": "lookup-weather",
                "capability_id": "chromie.weather.lookup",
                "args": {"city": "Beijing"},
                "timing": "sequential",
                "source_goal_ids": ["goal-weather"],
            },
            {
                "step_id": "lookup-calendar",
                "capability_id": "chromie.calendar.lookup",
                "args": {},
                "timing": "sequential",
                "source_goal_ids": ["goal-calendar"],
            },
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-weather",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["lookup-weather"],
            },
            {
                "goal_id": "goal-calendar",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["lookup-calendar"],
            },
        ],
    )


def shared_step_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-shared-step",
        planner_tier="deep",
        disposition="execute",
        coverage="complete",
        confidence=0.91,
        goal_ids=["goal-a", "goal-b"],
        goal_summary="Use one observation for two goals.",
        steps=[
            {
                "step_id": "shared-observation",
                "capability_id": "chromie.scene.observe",
                "args": {},
                "timing": "sequential",
                "source_goal_ids": ["goal-a", "goal-b"],
            }
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-a",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["shared-observation"],
            },
            {
                "goal_id": "goal-b",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["shared-observation"],
            },
        ],
    )


def mixed_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-mixed",
        planner_tier="deep",
        disposition="mixed",
        coverage="complete",
        confidence=0.92,
        goal_ids=["goal-action", "goal-answer"],
        goal_summary="Blink and answer.",
        steps=[
            {
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "timing": "sequential",
                "source_goal_ids": ["goal-action"],
            }
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-action",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["blink"],
            },
            {
                "goal_id": "goal-answer",
                "disposition": "respond",
                "coverage": "complete",
                "response_text": "Here is the answer.",
            },
        ],
    )


def request_for_step(
    plan: CanonicalPlan,
    step_id: str,
    *,
    request_id: str | None = None,
) -> CapabilityRequest:
    step = next(item for item in plan.steps if item.step_id == step_id)
    return CapabilityRequest(
        request_id=request_id or f"request-{step_id}",
        capability_id=step.capability_id,
        args=step.args,
        timing=step.timing,
        metadata={
            "source": "goal_driven_canonical_plan",
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": canonical_plan_fingerprint(plan),
            "step_id": step.step_id,
            "source_goal_ids": step.source_goal_ids,
        },
    )


class ExecutionOutcomeReconciliationTests(unittest.TestCase):
    def test_partial_requires_completed_and_unresolved_work(self) -> None:
        self.assertEqual(
            aggregate_execution_status(["completed", "timed_out"]),
            "partial",
        )
        self.assertEqual(
            aggregate_execution_status(["failed", "timed_out"]),
            "failed",
        )
        self.assertEqual(
            aggregate_execution_status(["cancelled", "not_run"]),
            "failed",
        )

        with self.assertRaisesRegex(
            ValidationError,
            "requires completed and unresolved steps",
        ):
            GoalExecutionOutcome(
                goal_id="goal-no-completion",
                status="partial",
                step_ids=["step-failed", "step-timeout"],
                evidence_ids=["evidence-failed", "evidence-timeout"],
                completed_step_ids=[],
                unresolved_step_ids=["step-failed", "step-timeout"],
            )

    def test_incremental_terminal_evidence_reconciles_only_exact_request(self) -> None:
        plan = two_goal_plan()
        weather_request = request_for_step(plan, "lookup-weather")
        calendar_request = request_for_step(plan, "lookup-calendar")
        weather_result = CapabilityResult(
            request_id=weather_request.request_id,
            capability_id=weather_request.capability_id,
            status="completed",
            provider_id="mock.weather",
            output={"summary": "sunny"},
        )
        calendar_result = CapabilityResult(
            request_id=calendar_request.request_id,
            capability_id=calendar_request.capability_id,
            status="completed",
            provider_id="mock.calendar",
            output={"summary": "free"},
        )
        reconciler = ExecutionOutcomeReconciler()

        evidence = reconciler.reconcile_terminal_result(
            turn_id="turn-two",
            plan=plan,
            interaction_id="interaction-two",
            requests=[weather_request, calendar_request],
            result=weather_result,
        )

        self.assertEqual(evidence.request_id, weather_request.request_id)
        self.assertEqual(evidence.step_id, "lookup-weather")
        self.assertEqual(evidence.status, "completed")
        self.assertFalse(evidence.missing_result)
        self.assertNotEqual(evidence.status, "not_run")

        final_bundle = reconciler.build(
            turn_id="turn-two",
            plan=plan,
            interaction_id="interaction-two",
            requests=[weather_request, calendar_request],
            results=[weather_result, calendar_result],
        )
        final_weather = next(
            item
            for item in final_bundle.evidence
            if item.request_id == weather_request.request_id
        )
        self.assertEqual(evidence.evidence_id, final_weather.evidence_id)
        self.assertEqual(evidence.model_dump(mode="json"), final_weather.model_dump(mode="json"))

    def test_incremental_terminal_evidence_does_not_mark_running_sibling_not_run(self) -> None:
        plan = two_goal_plan()
        weather_request = request_for_step(plan, "lookup-weather")
        calendar_request = request_for_step(plan, "lookup-calendar")
        weather_result = CapabilityResult(
            request_id=weather_request.request_id,
            capability_id=weather_request.capability_id,
            status="completed",
            provider_id="mock.weather",
        )
        reconciler = ExecutionOutcomeReconciler()

        evidence = reconciler.reconcile_terminal_result(
            turn_id="turn-partial-runtime",
            plan=plan,
            interaction_id="interaction-partial-runtime",
            requests=[weather_request, calendar_request],
            result=weather_result,
        )
        legacy_partial_bundle = reconciler.build(
            turn_id="turn-partial-runtime",
            plan=plan,
            interaction_id="interaction-partial-runtime",
            requests=[weather_request, calendar_request],
            results=[weather_result],
        )

        self.assertEqual(evidence.request_id, weather_request.request_id)
        self.assertFalse(evidence.missing_result)
        calendar_evidence = next(
            item
            for item in legacy_partial_bundle.evidence
            if item.request_id == calendar_request.request_id
        )
        self.assertEqual(calendar_evidence.status, "not_run")
        self.assertTrue(calendar_evidence.missing_result)
        # Incremental reconciliation deliberately returns no sibling evidence at all.
        self.assertNotEqual(evidence.request_id, calendar_evidence.request_id)

    def test_incremental_evidence_rejects_non_terminal_or_uncommitted_result(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        reconciler = ExecutionOutcomeReconciler()

        with self.assertRaisesRegex(ValueError, "requires a terminal CapabilityResult"):
            reconciler.reconcile_terminal_result(
                turn_id="turn-weather",
                plan=plan,
                interaction_id="interaction-weather",
                requests=[request],
                result=CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    status="running",
                ),
            )

        with self.assertRaisesRegex(ValueError, "committed canonical plan request"):
            reconciler.reconcile_terminal_result(
                turn_id="turn-weather",
                plan=plan,
                interaction_id="interaction-weather",
                requests=[request],
                result=CapabilityResult(
                    request_id="unknown-request",
                    capability_id=request.capability_id,
                    status="completed",
                ),
            )

    def test_committed_request_must_match_plan_args_and_timing(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        reconciler = ExecutionOutcomeReconciler()

        with self.assertRaisesRegex(ValueError, "args do not match"):
            reconciler.build(
                turn_id="turn-weather",
                plan=plan,
                interaction_id="interaction-weather",
                requests=[
                    request.model_copy(
                        deep=True,
                        update={"args": {"city": "Shanghai"}},
                    )
                ],
                results=[],
            )
        with self.assertRaisesRegex(ValueError, "timing does not match"):
            reconciler.build(
                turn_id="turn-weather",
                plan=plan,
                interaction_id="interaction-weather",
                requests=[
                    request.model_copy(
                        deep=True,
                        update={"timing": "parallel"},
                    )
                ],
                results=[],
            )

    def test_completed_result_is_correlated_and_exposes_validated_output(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        started = datetime.now(timezone.utc)
        finished = started + timedelta(milliseconds=20)
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            provider_id="weather.provider",
            output={"summary": "Light rain."},
            trace_id="trace-weather",
        )
        trace = CapabilityTrace(
            trace_id="trace-weather",
            interaction_id="interaction-weather",
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id="weather.provider",
            status="completed",
            started_at=started,
            finished_at=finished,
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-weather",
            plan=plan,
            interaction_id="interaction-weather",
            requests=[request],
            results=[result],
            traces=[trace],
            output_schemas={
                "chromie.weather.lookup": output_schema("summary")
            },
        )

        self.assertEqual(bundle.aggregate_status, "completed")
        self.assertEqual(bundle.goal_outcomes[0].status, "completed")
        evidence = bundle.evidence[0]
        self.assertEqual(evidence.status, "completed")
        self.assertEqual(evidence.source_goal_ids, ["goal-weather"])
        self.assertEqual(evidence.started_at, started)
        self.assertEqual(evidence.finished_at, finished)
        self.assertEqual(evidence.observation.status, "available")
        self.assertEqual(
            evidence.observation.data,
            {"summary": "Light rain."},
        )
        self.assertEqual(len(execution_outcome_fingerprint(bundle)), 64)

    def test_provider_completed_with_schema_invalid_observation_fails_closed(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            provider_id="weather.provider",
            output={"summary": "Rain.", "unexpected": True},
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-schema-invalid",
            plan=plan,
            interaction_id="interaction-schema-invalid",
            requests=[request],
            results=[result],
            output_schemas={
                "chromie.weather.lookup": output_schema("summary")
            },
        )

        self.assertEqual(bundle.aggregate_status, "failed")
        self.assertEqual(bundle.goal_outcomes[0].status, "failed")
        evidence = bundle.evidence[0]
        self.assertEqual(evidence.status, "failed")
        self.assertEqual(evidence.reason_code, "completion_observation_not_trusted")
        self.assertIsNotNone(evidence.observation)
        assert evidence.observation is not None
        self.assertEqual(evidence.observation.status, "schema_invalid")
        self.assertFalse(evidence.observation.schema_validated)
        self.assertTrue(evidence.metadata["reported_provider_completion"])
        self.assertEqual(
            evidence.metadata["completion_observation_status"],
            "schema_invalid",
        )

    def test_completed_evidence_contract_rejects_explicit_schema_invalid_observation(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        valid = build_execution_outcome_bundle(
            turn_id="turn-contract-schema-invalid",
            plan=plan,
            interaction_id="interaction-contract-schema-invalid",
            requests=[request],
            results=[
                CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    status="completed",
                    output={"summary": "Clear."},
                )
            ],
            output_schemas={
                "chromie.weather.lookup": output_schema("summary")
            },
        ).model_dump(mode="json")
        evidence = valid["evidence"][0]
        output_sha256 = evidence["observation"]["output_sha256"]
        evidence["observation"] = {
            "status": "schema_invalid",
            "schema_validated": False,
            "data": {},
            "output_sha256": output_sha256,
            "output_size_bytes": 0,
            "validation_errors": ["provider output failed schema validation"],
        }

        with self.assertRaisesRegex(
            ValidationError,
            "completed execution evidence cannot rely",
        ):
            ExecutionOutcomeBundle.model_validate(valid)

    def test_one_success_and_one_failure_remain_mixed_per_goal(self) -> None:
        plan = two_goal_plan()
        requests = [
            request_for_step(plan, "lookup-weather"),
            request_for_step(plan, "lookup-calendar"),
        ]
        results = [
            CapabilityResult(
                request_id=requests[0].request_id,
                capability_id=requests[0].capability_id,
                status="completed",
                output={"summary": "Sunny."},
            ),
            CapabilityResult(
                request_id=requests[1].request_id,
                capability_id=requests[1].capability_id,
                status="failed",
                reason_code="provider_unavailable",
                message="Calendar provider unavailable.",
            ),
        ]

        bundle = build_execution_outcome_bundle(
            turn_id="turn-two",
            plan=plan,
            interaction_id="interaction-two",
            requests=requests,
            results=results,
            output_schemas={
                "chromie.weather.lookup": output_schema("summary"),
                "chromie.calendar.lookup": output_schema("summary"),
            },
        )

        self.assertEqual(bundle.aggregate_status, "partial")
        self.assertEqual(
            {item.goal_id: item.status for item in bundle.goal_outcomes},
            {
                "goal-weather": "completed",
                "goal-calendar": "failed",
            },
        )

    def test_all_uncompleted_mixture_is_failed_with_exact_goal_statuses(
        self,
    ) -> None:
        plan = two_goal_plan()
        requests = [
            request_for_step(plan, "lookup-weather"),
            request_for_step(plan, "lookup-calendar"),
        ]
        results = [
            CapabilityResult(
                request_id=requests[0].request_id,
                capability_id=requests[0].capability_id,
                status="failed",
                reason_code="provider_error",
            ),
            CapabilityResult(
                request_id=requests[1].request_id,
                capability_id=requests[1].capability_id,
                status="timed_out",
                reason_code="provider_timeout",
            ),
        ]

        bundle = build_execution_outcome_bundle(
            turn_id="turn-all-uncompleted",
            plan=plan,
            interaction_id="interaction-all-uncompleted",
            requests=requests,
            results=results,
        )

        self.assertEqual(bundle.aggregate_status, "failed")
        self.assertEqual(
            {item.goal_id: item.status for item in bundle.goal_outcomes},
            {
                "goal-weather": "failed",
                "goal-calendar": "timed_out",
            },
        )

    def test_missing_result_is_explicit_not_run(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup").model_copy(
            deep=True,
            update={
                "metadata": {
                    **request_for_step(plan, "lookup").metadata,
                    "safety_class": "safe_read",
                    "effects": [],
                    "retryable_safe_read": True,
                }
            },
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-missing",
            plan=plan,
            interaction_id="interaction-missing",
            requests=[request],
            results=[],
        )

        self.assertEqual(bundle.aggregate_status, "not_run")
        self.assertEqual(bundle.goal_outcomes[0].status, "not_run")
        self.assertTrue(bundle.evidence[0].missing_result)
        self.assertEqual(bundle.evidence[0].status, "not_run")
        self.assertEqual(
            bundle.evidence[0].reason_code,
            "missing_capability_result",
        )
        self.assertEqual(
            bundle.evidence[0].metadata["request_args"],
            {"city": "Beijing"},
        )
        self.assertTrue(bundle.evidence[0].metadata["retryable_safe_read"])

    def test_shared_step_evidence_can_support_multiple_owned_goals(self) -> None:
        plan = shared_step_plan()
        request = request_for_step(plan, "shared-observation")
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            output={"summary": "One person is present."},
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-shared",
            plan=plan,
            interaction_id="interaction-shared",
            requests=[request],
            results=[result],
            output_schemas={
                "chromie.scene.observe": output_schema("summary")
            },
        )

        self.assertEqual(len(bundle.evidence), 1)
        self.assertEqual(
            bundle.evidence[0].source_goal_ids,
            ["goal-a", "goal-b"],
        )
        self.assertEqual(
            [item.status for item in bundle.goal_outcomes],
            ["completed", "completed"],
        )
        self.assertEqual(
            {
                item.evidence_ids[0]
                for item in bundle.goal_outcomes
            },
            {bundle.evidence[0].evidence_id},
        )

    def test_non_execution_goals_are_retained_but_not_inferred_complete(self) -> None:
        plan = mixed_plan()
        request = request_for_step(plan, "blink")
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-mixed",
            plan=plan,
            interaction_id="interaction-mixed",
            requests=[request],
            results=[result],
        )

        self.assertEqual(
            bundle.canonical_goal_ids,
            ["goal-action", "goal-answer"],
        )
        self.assertEqual(
            bundle.non_execution_goal_ids,
            ["goal-answer"],
        )
        self.assertEqual(
            [item.goal_id for item in bundle.goal_outcomes],
            ["goal-action"],
        )

    def test_auxiliary_social_attention_and_its_result_are_ignored(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        social = CapabilityRequest(
            request_id="social-look",
            capability_id="soridormi.look_at_person",
            metadata={
                "source": "social_attention_plan",
                "auxiliary_social_attention": True,
                "canonical_plan_id": plan.plan_id,
            },
        )
        results = [
            CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                status="completed",
            ),
            CapabilityResult(
                request_id=social.request_id,
                capability_id=social.capability_id,
                status="completed",
            ),
        ]

        bundle = build_execution_outcome_bundle(
            turn_id="turn-social",
            plan=plan,
            interaction_id="interaction-social",
            requests=[request, social],
            results=results,
        )

        self.assertEqual(len(bundle.evidence), 1)
        self.assertEqual(
            bundle.metadata["ignored_non_plan_request_count"],
            1,
        )
        self.assertEqual(
            bundle.metadata["ignored_non_plan_result_count"],
            1,
        )

    def test_unknown_or_non_auxiliary_result_fails_exact_reconciliation(
        self,
    ) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        completed = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
        )
        unknown = CapabilityResult(
            request_id="uncommitted-result",
            capability_id="soridormi.unplanned_motion",
            status="completed",
        )
        committed_non_auxiliary = CapabilityRequest(
            request_id="committed-non-auxiliary",
            capability_id="soridormi.unplanned_motion",
        )
        non_auxiliary_result = CapabilityResult(
            request_id=committed_non_auxiliary.request_id,
            capability_id=committed_non_auxiliary.capability_id,
            status="completed",
        )

        with self.assertRaisesRegex(
            ValueError,
            "no committed canonical or auxiliary CapabilityRequest",
        ):
            build_execution_outcome_bundle(
                turn_id="turn-unknown-result",
                plan=plan,
                interaction_id="interaction-unknown-result",
                requests=[request],
                results=[completed, unknown],
            )
        with self.assertRaisesRegex(
            ValueError,
            "no committed canonical or auxiliary CapabilityRequest",
        ):
            build_execution_outcome_bundle(
                turn_id="turn-non-auxiliary-result",
                plan=plan,
                interaction_id="interaction-non-auxiliary-result",
                requests=[request, committed_non_auxiliary],
                results=[completed, non_auxiliary_result],
            )

    def test_nonterminal_capability_result_fails_closed(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="running",
        )

        bundle = build_execution_outcome_bundle(
            turn_id="turn-running",
            plan=plan,
            interaction_id="interaction-running",
            requests=[request],
            results=[result],
        )

        self.assertEqual(bundle.aggregate_status, "failed")
        self.assertEqual(
            bundle.evidence[0].reason_code,
            "non_terminal_capability_result",
        )
        self.assertEqual(bundle.evidence[0].reported_status, "running")

    def test_schema_valid_execution_observation_establishes_owner_policy(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        policy = ClaimQualificationPolicy(
            claim="weather lookup request completed",
            requirement_groups=[
                {
                    "requirements": [
                        {
                            "source": "execution_observation",
                            "field_assertions": {"summary": "sunny"},
                        }
                    ]
                }
            ],
        )
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            provider_id="weather.provider",
            output={"summary": "sunny"},
        )

        bundle = ExecutionOutcomeReconciler().build(
            turn_id="turn-qualified",
            plan=plan,
            interaction_id="interaction-qualified",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: output_schema("summary")},
            completion_evidence_policies={request.request_id: policy},
        )

        qualification = bundle.evidence[0].completion_qualification
        self.assertIsNotNone(qualification)
        assert qualification is not None
        self.assertEqual(qualification.status, "established")
        self.assertEqual(qualification.evidence_ids, [bundle.evidence[0].evidence_id])
        self.assertEqual(qualification.trust_domains, ["weather.provider"])

    def test_embodied_policy_requires_postcondition_and_preserves_contradiction(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result_schema = {
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "required": ["completed"],
            "additionalProperties": False,
        }
        status_schema = {
            "type": "object",
            "properties": {
                "safe_idle": {"type": "boolean"},
                "active_task_present": {"type": "boolean"},
            },
            "required": ["safe_idle", "active_task_present"],
            "additionalProperties": False,
        }
        policy = ClaimQualificationPolicy(
            claim="embodied request completed with safe closure",
            requirement_groups=[
                {
                    "requirements": [
                        {
                            "source": "execution_observation",
                            "field_assertions": {"completed": True},
                        },
                        {
                            "source": "provider_postcondition",
                            "condition": "post_execution_robot_status",
                            "field_assertions": {
                                "safe_idle": True,
                                "active_task_present": False,
                            },
                        },
                    ]
                }
            ],
        )
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            provider_id="soridormi.mcp",
            output={"completed": True},
        )
        reconciler = ExecutionOutcomeReconciler()

        missing = reconciler.build(
            turn_id="turn-postcondition-missing",
            plan=plan,
            interaction_id="interaction-postcondition-missing",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: result_schema},
            completion_evidence_policies={request.request_id: policy},
        )
        missing_qualification = missing.evidence[0].completion_qualification
        self.assertIsNotNone(missing_qualification)
        assert missing_qualification is not None
        self.assertEqual(missing_qualification.status, "insufficient")

        contradicted_postcondition = ProviderPostconditionEvidence(
            evidence_id="postcondition-contradicted",
            provider_id="soridormi.mcp",
            condition="post_execution_robot_status",
            observation=reconciler.build_model_observation(
                {"safe_idle": False, "active_task_present": False},
                output_schema=status_schema,
            ),
            source_goal_ids=["goal-weather"],
            observed_at=datetime.now(timezone.utc),
        )
        contradicted = reconciler.build(
            turn_id="turn-postcondition-contradicted",
            plan=plan,
            interaction_id="interaction-postcondition-contradicted",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: result_schema},
            completion_evidence_policies={request.request_id: policy},
            provider_postconditions=[contradicted_postcondition],
        )
        contradicted_qualification = contradicted.evidence[0].completion_qualification
        self.assertIsNotNone(contradicted_qualification)
        assert contradicted_qualification is not None
        self.assertEqual(contradicted_qualification.status, "contradicted")

        good_postcondition = contradicted_postcondition.model_copy(
            update={
                "evidence_id": "postcondition-good",
                "observation": reconciler.build_model_observation(
                    {"safe_idle": True, "active_task_present": False},
                    output_schema=status_schema,
                ),
            }
        )
        established = reconciler.build(
            turn_id="turn-postcondition-good",
            plan=plan,
            interaction_id="interaction-postcondition-good",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: result_schema},
            completion_evidence_policies={request.request_id: policy},
            provider_postconditions=[good_postcondition],
        )
        established_qualification = established.evidence[0].completion_qualification
        self.assertIsNotNone(established_qualification)
        assert established_qualification is not None
        self.assertEqual(established_qualification.status, "established")
        self.assertEqual(
            established_qualification.evidence_ids,
            [established.evidence[0].evidence_id, "postcondition-good"],
        )

    def test_independent_trust_domain_requirement_is_mechanical(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result_schema = {
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "required": ["completed"],
            "additionalProperties": False,
        }
        status_schema = {
            "type": "object",
            "properties": {"safe_idle": {"type": "boolean"}},
            "required": ["safe_idle"],
            "additionalProperties": False,
        }
        policy = ClaimQualificationPolicy(
            claim="two-domain completion",
            requirement_groups=[
                {
                    "requirements": [
                        {"source": "execution_observation"},
                        {
                            "source": "provider_postcondition",
                            "condition": "robot_status",
                            "field_assertions": {"safe_idle": True},
                        },
                    ],
                    "minimum_independent_trust_domains": 2,
                }
            ],
        )
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            provider_id="same.provider",
            output={"completed": True},
        )
        reconciler = ExecutionOutcomeReconciler()
        postcondition = ProviderPostconditionEvidence(
            evidence_id="same-domain-status",
            provider_id="same.provider",
            condition="robot_status",
            observation=reconciler.build_model_observation(
                {"safe_idle": True}, output_schema=status_schema
            ),
            source_goal_ids=["goal-weather"],
            observed_at=datetime.now(timezone.utc),
        )

        bundle = reconciler.build(
            turn_id="turn-domain",
            plan=plan,
            interaction_id="interaction-domain",
            requests=[request],
            results=[result],
            output_schemas={request.request_id: result_schema},
            completion_evidence_policies={request.request_id: policy},
            provider_postconditions=[postcondition],
        )

        qualification = bundle.evidence[0].completion_qualification
        self.assertIsNotNone(qualification)
        assert qualification is not None
        self.assertEqual(qualification.status, "insufficient")
        self.assertIn(
            "independent_trust_domains_insufficient",
            qualification.reason_codes,
        )

    def test_provider_postcondition_does_not_turn_missing_work_into_success(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        reconciler = ExecutionOutcomeReconciler()
        postcondition = ProviderPostconditionEvidence(
            evidence_id="postcondition-safe-idle",
            provider_id="soridormi.mcp",
            condition="safe_idle",
            observation=reconciler.build_model_observation(
                {"safe_idle": "true"},
                output_schema=output_schema("safe_idle"),
            ),
            source_goal_ids=["goal-weather"],
        )

        bundle = reconciler.build(
            turn_id="turn-postcondition",
            plan=plan,
            interaction_id="interaction-postcondition",
            requests=[request],
            results=[],
            provider_postconditions=[postcondition],
        )

        self.assertEqual(bundle.aggregate_status, "not_run")
        self.assertEqual(bundle.goal_outcomes[0].status, "not_run")
        self.assertEqual(len(bundle.provider_postconditions), 1)

    def test_model_observation_requires_closed_nonempty_schema(self) -> None:
        reconciler = ExecutionOutcomeReconciler()
        weak_schemas = [
            {},
            {"type": "object"},
            {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
            {
                "type": "object",
                "properties": {"details": {"type": "object"}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "details": {
                        "type": ["object", "null"],
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"details": {"type": "provider-specific"}},
                "additionalProperties": False,
            },
        ]

        for schema in weak_schemas:
            with self.subTest(schema=schema):
                observation = reconciler.build_model_observation(
                    {"summary": "Sunny."},
                    output_schema=schema,
                )
                self.assertNotEqual(observation.status, "available")
                self.assertEqual(observation.data, {})

    def test_model_observation_rejects_invalid_large_and_sensitive_output(self) -> None:
        reconciler = ExecutionOutcomeReconciler(
            max_observation_bytes=32,
            max_total_observation_bytes=64,
        )
        schema = output_schema("summary")
        invalid = reconciler.build_model_observation(
            {"unexpected": "value"},
            output_schema=schema,
        )
        large = reconciler.build_model_observation(
            {"summary": "x" * 100},
            output_schema=schema,
        )
        sensitive = reconciler.build_model_observation(
            {"token": "secret"},
            output_schema=output_schema("token"),
        )

        self.assertEqual(invalid.status, "schema_invalid")
        self.assertEqual(large.status, "too_large")
        self.assertEqual(sensitive.status, "sensitive")
        self.assertEqual(invalid.data, {})
        self.assertEqual(large.data, {})
        self.assertEqual(sensitive.data, {})

    def test_sensitive_key_variants_never_reach_observation_or_speech(
        self,
    ) -> None:
        reconciler = ExecutionOutcomeReconciler()
        secret = "NEVER-SPEAK-THIS-SECRET"
        variants = (
            "accessToken",
            "access token",
            "access.token",
            "CLIENT_SECRET",
            "api-key",
            "authorization header",
            "sessionCookie",
            "privateKeyMaterial",
        )

        for key in variants:
            with self.subTest(key=key):
                observation = reconciler.build_model_observation(
                    {key: secret},
                    output_schema=output_schema(key),
                )
                self.assertEqual(observation.status, "sensitive")
                self.assertEqual(observation.data, {})
                self.assertNotIn(
                    secret,
                    observation.model_dump_json(),
                )

        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            status="completed",
            output={"accessToken": secret},
        )
        schema = output_schema("accessToken")
        bundle = reconciler.build(
            turn_id="turn-sensitive-output",
            plan=plan,
            interaction_id="interaction-sensitive-output",
            requests=[request],
            results=[result],
            output_schemas={
                request.request_id: schema,
                request.capability_id: schema,
            },
        )
        projection = planner_execution_outcome_truth(bundle)

        self.assertEqual(bundle.evidence[0].observation.status, "sensitive")
        self.assertEqual(bundle.evidence[0].observation.data, {})
        self.assertNotIn(
            secret,
            bundle.evidence[0].observation.model_dump_json(),
        )
        self.assertNotIn(secret, repr(projection))

    def test_request_and_result_correlation_fail_closed(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        stale_request = request.model_copy(
            deep=True,
            update={
                "metadata": {
                    **request.metadata,
                    "canonical_plan_fingerprint": "stale",
                }
            },
        )
        wrong_result = CapabilityResult(
            request_id=request.request_id,
            capability_id="chromie.weather.other",
            status="completed",
        )

        with self.assertRaisesRegex(ValueError, "fingerprint"):
            build_execution_outcome_bundle(
                turn_id="turn-stale",
                plan=plan,
                interaction_id="interaction-stale",
                requests=[stale_request],
                results=[],
            )
        with self.assertRaisesRegex(ValueError, "CapabilityResult capability_id"):
            build_execution_outcome_bundle(
                turn_id="turn-wrong-result",
                plan=plan,
                interaction_id="interaction-wrong-result",
                requests=[request],
                results=[wrong_result],
            )
        with self.assertRaisesRegex(ValueError, "no committed CapabilityRequest"):
            build_execution_outcome_bundle(
                turn_id="turn-no-request",
                plan=plan,
                interaction_id="interaction-no-request",
                requests=[],
                results=[],
            )

    def test_bundle_contract_rejects_missing_executable_goal_outcome(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        bundle = build_execution_outcome_bundle(
            turn_id="turn-contract",
            plan=plan,
            interaction_id="interaction-contract",
            requests=[request],
            results=[],
        )
        raw = bundle.model_dump(mode="json")
        raw["goal_outcomes"] = []

        with self.assertRaisesRegex(
            ValidationError,
            "cover exactly executable canonical goals",
        ):
            ExecutionOutcomeBundle.model_validate(raw)

    def test_bundle_contract_rejects_orphan_or_duplicate_step_evidence(
        self,
    ) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        bundle = build_execution_outcome_bundle(
            turn_id="turn-evidence-contract",
            plan=plan,
            interaction_id="interaction-evidence-contract",
            requests=[request],
            results=[],
        )

        orphan = bundle.model_dump(mode="json")
        extra = dict(orphan["evidence"][0])
        extra["evidence_id"] = "evidence-orphan"
        extra["request_id"] = "request-orphan"
        extra["step_id"] = "orphan-step"
        orphan["evidence"].append(extra)
        with self.assertRaisesRegex(
            ValidationError,
            "referenced by a goal outcome",
        ):
            ExecutionOutcomeBundle.model_validate(orphan)

        duplicate_step = bundle.model_dump(mode="json")
        extra = dict(duplicate_step["evidence"][0])
        extra["evidence_id"] = "evidence-duplicate-step"
        extra["request_id"] = "request-duplicate-step"
        duplicate_step["evidence"].append(extra)
        with self.assertRaisesRegex(
            ValidationError,
            "step IDs must be unique",
        ):
            ExecutionOutcomeBundle.model_validate(duplicate_step)


if __name__ == "__main__":
    unittest.main()
