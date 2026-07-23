from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from orchestrator.runtime.outcome_reconciliation import (
    ExecutionOutcomeReconciler,
    build_execution_outcome_bundle,
)
from orchestrator.runtime.outcome_response import compose_outcome_response
from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ProviderPostconditionEvidence,
    aggregate_execution_status,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.interaction import (
    SkillRequest,
    SkillResult,
    SkillTrace,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)


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
                "skill_id": "chromie.weather.lookup",
                "args": {"city": "Beijing"},
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
                "skill_id": "chromie.weather.lookup",
                "args": {"city": "Beijing"},
                "source_goal_ids": ["goal-weather"],
            },
            {
                "step_id": "lookup-calendar",
                "skill_id": "chromie.calendar.lookup",
                "args": {},
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
                "skill_id": "chromie.scene.observe",
                "args": {},
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
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
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
) -> SkillRequest:
    step = next(item for item in plan.steps if item.step_id == step_id)
    return SkillRequest(
        request_id=request_id or f"request-{step_id}",
        skill_id=step.skill_id,
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
        result = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            status="completed",
            provider_id="weather.provider",
            output={"summary": "Light rain."},
            trace_id="trace-weather",
        )
        trace = SkillTrace(
            trace_id="trace-weather",
            interaction_id="interaction-weather",
            request_id=request.request_id,
            skill_id=request.skill_id,
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

    def test_one_success_and_one_failure_remain_mixed_per_goal(self) -> None:
        plan = two_goal_plan()
        requests = [
            request_for_step(plan, "lookup-weather"),
            request_for_step(plan, "lookup-calendar"),
        ]
        results = [
            SkillResult(
                request_id=requests[0].request_id,
                skill_id=requests[0].skill_id,
                status="completed",
                output={"summary": "Sunny."},
            ),
            SkillResult(
                request_id=requests[1].request_id,
                skill_id=requests[1].skill_id,
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
            SkillResult(
                request_id=requests[0].request_id,
                skill_id=requests[0].skill_id,
                status="failed",
                reason_code="provider_error",
            ),
            SkillResult(
                request_id=requests[1].request_id,
                skill_id=requests[1].skill_id,
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
        request = request_for_step(plan, "lookup")

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
            "missing_skill_result",
        )

    def test_shared_step_evidence_can_support_multiple_owned_goals(self) -> None:
        plan = shared_step_plan()
        request = request_for_step(plan, "shared-observation")
        result = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
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
        result = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
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
        social = SkillRequest(
            request_id="social-look",
            skill_id="soridormi.look_at_person",
            metadata={
                "source": "social_attention_plan",
                "auxiliary_social_attention": True,
                "canonical_plan_id": plan.plan_id,
            },
        )
        results = [
            SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                status="completed",
            ),
            SkillResult(
                request_id=social.request_id,
                skill_id=social.skill_id,
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
        completed = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            status="completed",
        )
        unknown = SkillResult(
            request_id="uncommitted-result",
            skill_id="soridormi.unplanned_motion",
            status="completed",
        )
        committed_non_auxiliary = SkillRequest(
            request_id="committed-non-auxiliary",
            skill_id="soridormi.unplanned_motion",
        )
        non_auxiliary_result = SkillResult(
            request_id=committed_non_auxiliary.request_id,
            skill_id=committed_non_auxiliary.skill_id,
            status="completed",
        )

        with self.assertRaisesRegex(
            ValueError,
            "no committed canonical or auxiliary SkillRequest",
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
            "no committed canonical or auxiliary SkillRequest",
        ):
            build_execution_outcome_bundle(
                turn_id="turn-non-auxiliary-result",
                plan=plan,
                interaction_id="interaction-non-auxiliary-result",
                requests=[request, committed_non_auxiliary],
                results=[completed, non_auxiliary_result],
            )

    def test_nonterminal_skill_result_fails_closed(self) -> None:
        plan = single_plan()
        request = request_for_step(plan, "lookup")
        result = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
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
            "non_terminal_skill_result",
        )
        self.assertEqual(bundle.evidence[0].reported_status, "running")

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
        result = SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
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
                request.skill_id: schema,
            },
        )
        speech = compose_outcome_response(bundle, plan, "en-US")

        self.assertEqual(bundle.evidence[0].observation.status, "sensitive")
        self.assertEqual(bundle.evidence[0].observation.data, {})
        self.assertNotIn(
            secret,
            bundle.evidence[0].observation.model_dump_json(),
        )
        self.assertNotIn(
            secret,
            " ".join(item.text for item in speech.speech),
        )

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
        wrong_result = SkillResult(
            request_id=request.request_id,
            skill_id="chromie.weather.other",
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
        with self.assertRaisesRegex(ValueError, "SkillResult skill_id"):
            build_execution_outcome_bundle(
                turn_id="turn-wrong-result",
                plan=plan,
                interaction_id="interaction-wrong-result",
                requests=[request],
                results=[wrong_result],
            )
        with self.assertRaisesRegex(ValueError, "no committed SkillRequest"):
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
