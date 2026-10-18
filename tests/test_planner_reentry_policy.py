from __future__ import annotations

import hashlib
import copy

import pytest

from orchestrator.runtime.planner_reentry import (
    execution_outcome_user_text,
    planner_reentry_repeats_completed_activity,
    planner_reentry_responsibilities,
    terminal_evidence_relevance,
    terminal_result_waits_for_batch_closure,
)
from agent.app.planner_context import (
    PlannerGoalContext,
    goal_association_prompt_projection,
    planner_goal_context,
)
from agent.app.planner_prompt import (
    fast_evidence_reentry_prompt,
    fast_plan_prompt,
    planner_reentry_execution_truth_projection,
    planner_reentry_source_work_projection,
)
from agent.app.planner_fallback import materialize_planner_failure
from agent.app.planner_model_contract import (
    PlannerEvidenceReentryModelOutput,
    PlannerModelOutput,
    materialize_evidence_reentry_model_output,
)
from agent.app.planner_schema import fast_evidence_reentry_response_schema
from shared.chromie_contracts.core_interpretation import (
    CognitiveWorkRequest,
    PlannerReentryScope,
)
from shared.chromie_contracts.execution_outcome import ExecutionEvidence
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.tool_result import (
    ToolResultEvidence,
    canonical_value_sha256,
)


def _response(*, include_interpretation: bool = True) -> InteractionResponse:
    metadata = {
        "canonical_plan_id": "plan-current",
        "canonical_plan_fingerprint": "f" * 64,
        "user_turn_envelope": {
            "turn_id": "turn-reentry-source",
            "original_input": {"text": "  Check both things.  "},
            "normalized_input": {"text": "Check both things."},
        },
        "goal_association": {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-a",
                    "source_responsibility_refs": ["responsibility-a"],
                },
                {
                    "goal_id": "goal-b",
                    "source_responsibility_refs": ["responsibility-b"],
                },
            ],
        },
    }
    if include_interpretation:
        metadata["user_meaning_interpretation"] = {
            "responsibilities": [
                {
                    "local_ref": "responsibility-a",
                    "outcome": "Obtain the first requested result.",
                    "output_mode": "information",
                    "confidence": 1.0,
                },
                {
                    "local_ref": "responsibility-b",
                    "outcome": "Obtain the second requested result.",
                    "output_mode": "information",
                    "confidence": 1.0,
                },
            ]
        }
    return InteractionResponse(
        interaction_id="interaction-reentry-policy",
        capabilities=[
            {
                "request_id": "request-a",
                "capability_id": "chromie.test.lookup",
                "args": {"target": "a"},
                "metadata": {"source_goal_ids": ["goal-a"]},
            }
        ],
        metadata=metadata,
    )


def _evidence() -> ExecutionEvidence:
    return ExecutionEvidence(
        evidence_id="evidence-a",
        request_id="request-a",
        step_id="step-a",
        capability_id="chromie.test.lookup",
        source_goal_ids=["goal-a"],
        status="completed",
    )


def _current_binding() -> list[dict[str, object]]:
    return [
        {
            "goal_id": "goal-a",
            "found": True,
            "responsibility_status": "open",
            "canonical_plan_id": "plan-current",
            "canonical_plan_fingerprint": "f" * 64,
            "request_ids": ["request-a"],
        }
    ]


def test_successful_result_waits_for_aggregate_closure_and_postconditions() -> None:
    assert terminal_result_waits_for_batch_closure(
        source_capability_count=2,
        status="completed",
    )
    assert terminal_result_waits_for_batch_closure(
        source_capability_count=1,
        status="completed",
    )
    assert not terminal_result_waits_for_batch_closure(
        source_capability_count=2,
        status="failed",
    )
    for status in ("running", "failed", "cancelled", "blocked", "timed_out"):
        assert not terminal_result_waits_for_batch_closure(
            source_capability_count=1, status=status,
        )


def test_typed_reentry_scope_bounds_full_association_to_affected_goals() -> None:
    context = {
        "goal_association_resolution": {
            "new_goals": [
                {"goal_id": "goal-walk", "metadata": {"output_mode": "body_action"}},
                {"goal_id": "goal-sing", "metadata": {"output_mode": "singing"}},
                {"goal_id": "goal-blink", "metadata": {"output_mode": "body_action"}},
            ]
        },
        "result_evidence_reentry": {
            "source_goal_ids": ["goal-walk", "goal-blink"],
            "evidence_refs": ["evidence-walk", "evidence-blink"],
        },
        "trusted_terminal_evidence": [
            {
                "evidence_id": "evidence-walk",
                "tool_id": "soridormi.walk_forward",
                "status": "completed",
                "data": {},
                "output_sha256": canonical_value_sha256({}),
            },
            {
                "evidence_id": "evidence-blink",
                "tool_id": "soridormi.blink_eyes",
                "status": "completed",
                "data": {},
                "output_sha256": canonical_value_sha256({}),
            },
        ],
    }
    scope = PlannerReentryScope(
        trigger="capability_result_reentry",
        goal_ids=["goal-walk", "goal-blink"],
        evidence_refs=["evidence-walk", "evidence-blink"],
        source_plan_id="plan-original",
        source_plan_fingerprint="f" * 64,
    )

    projected = planner_goal_context(context, reentry_scope=scope)

    assert projected.expected_goal_ids == ("goal-walk", "goal-blink")
    assert [item["goal_id"] for item in projected.authoritative_goals] == [
        "goal-walk",
        "goal-blink",
    ]
    association_projection = goal_association_prompt_projection(
        context,
        goal_ids=scope.goal_ids,
    )
    assert [item["goal_id"] for item in association_projection["new_goals"]] == [
        "goal-walk",
        "goal-blink",
    ]


def test_failed_safe_read_reentry_opens_execution_only_with_two_sided_recovery_truth() -> None:
    context = {
        "goal_association_resolution": {
            "new_goals": [{"goal_id": "goal-weather", "metadata": {"output_mode": "information"}}]
        },
        "result_evidence_reentry": {
            "source_goal_ids": ["goal-weather"],
            "evidence_refs": ["evidence-weather"],
        },
        "trusted_terminal_evidence": [
            {
                "evidence_id": "evidence-weather",
                "tool_id": "chromie.weather.lookup",
                "status": "failed",
                "data": {},
                "output_sha256": canonical_value_sha256({}),
            }
        ],
        "trusted_execution_outcome": {
            "evidence": [
                {
                    "capability_id": "chromie.weather.lookup",
                    "status": "failed",
                    "source_goal_ids": ["goal-weather"],
                    "provider_retryability": {"recoverable": True, "retryable": True},
                }
            ]
        },
        "active_task_snapshots": [
            {
                "status": "recoverable",
                "metadata": {
                    "execution_binding": {
                        "retryable_safe_read": True,
                        "recoverable_request_ids": ["request-weather"],
                        "planned_capabilities": [
                            {
                                "request_id": "request-weather",
                                "capability_id": "chromie.weather.lookup",
                                "source_goal_ids": ["goal-weather"],
                                "safety_class": "safe_read",
                                "retryable_safe_read": True,
                            }
                        ],
                    }
                },
            }
        ],
    }
    scope = PlannerReentryScope(
        trigger="capability_result_reentry",
        goal_ids=["goal-weather"],
        evidence_refs=["evidence-weather"],
        source_plan_id="plan-weather",
        source_plan_fingerprint="f" * 64,
    )

    projected = planner_goal_context(context, reentry_scope=scope)

    assert projected.requires_execution is True
    assert projected.response_goal_ids == ()

    context["trusted_execution_outcome"]["evidence"][0]["provider_retryability"]["retryable"] = (
        False
    )
    fail_closed = planner_goal_context(context, reentry_scope=scope)
    assert fail_closed.requires_execution is False
    assert fail_closed.response_goal_ids == ("goal-weather",)


def test_fast_fail_safe_cannot_widen_typed_reentry_scope() -> None:
    context = {
        "goal_association_resolution": {
            "new_goals": [
                {"goal_id": "goal-walk", "metadata": {"output_mode": "body_action"}},
                {"goal_id": "goal-blink", "metadata": {"output_mode": "body_action"}},
            ]
        },
        "result_evidence_reentry": {
            "source_goal_ids": ["goal-blink"],
            "evidence_refs": ["evidence-blink"],
        },
        "trusted_terminal_evidence": [
            {
                "evidence_id": "evidence-blink",
                "tool_id": "soridormi.blink_eyes",
                "status": "completed",
                "data": {},
                "output_sha256": canonical_value_sha256({}),
            }
        ],
    }
    scope = PlannerReentryScope(
        trigger="capability_result_reentry",
        goal_ids=["goal-blink"],
        evidence_refs=["evidence-blink"],
        source_plan_id="plan-original",
        source_plan_fingerprint="f" * 64,
    )
    request = CognitiveWorkRequest(
        sid="scope-fail-safe",
        text="Walk and blink.",
        responsibilities=[
            {
                "local_ref": "blink",
                "outcome": "blink once",
                "output_mode": "body_action",
                "confidence": 1.0,
            }
        ],
        interpretation_confidence=1.0,
        planner_reentry_scope=scope,
        context=context,
    )

    fallback = materialize_planner_failure(
        "plan-fallback",
        request,
        "primary_semantic_validation_failed",
    )

    assert fallback.goal_ids == ["goal-blink"]


def test_terminal_evidence_relevance_accepts_exact_current_binding() -> None:
    assert terminal_evidence_relevance(
        source_response=_response(),
        evidence=_evidence(),
        goal_bindings=_current_binding(),
    ) == (True, "current")


def test_terminal_evidence_relevance_rejects_superseded_plan() -> None:
    bindings = _current_binding()
    bindings[0]["canonical_plan_id"] = "plan-new"

    assert terminal_evidence_relevance(
        source_response=_response(),
        evidence=_evidence(),
        goal_bindings=bindings,
    ) == (False, "canonical_plan_superseded")


def test_value_declined_evidence_never_authorizes_a_replan() -> None:
    # Live 2026-10-11 (h_no_shower_zh): after a value decline the Planner re-planned and
    # asked for "another way", routing around Value Judgment (VALUE-JUDGMENT-001).
    evidence = _evidence().model_copy(update={"status": "refused", "reason_code": "value_judgment_declined"})
    assert terminal_evidence_relevance(
        source_response=_response(),
        evidence=evidence,
        goal_bindings=_current_binding(),
    ) == (False, "value_judgment_declined")


def test_planner_reentry_selects_only_goal_bound_responsibility() -> None:
    responsibilities = planner_reentry_responsibilities(
        source_response=_response(),
        goal_ids=["goal-a"],
    )

    assert [item.local_ref for item in responsibilities] == ["responsibility-a"]


def test_planner_reentry_does_not_invent_missing_responsibility() -> None:
    assert (
        planner_reentry_responsibilities(
            source_response=_response(include_interpretation=False),
            goal_ids=["goal-a"],
        )
        == []
    )


def test_one_unbound_responsibility_does_not_cover_multiple_goals() -> None:
    response = _response()
    response.metadata["user_meaning_interpretation"] = {
        "responsibilities": [
            {
                "local_ref": "responsibility-a",
                "outcome": "Obtain one requested result.",
                "output_mode": "information",
                "relationship": "new",
                "confidence": 1.0,
            }
        ]
    }
    response.metadata["goal_association"] = {
        "associations": [],
        "new_goals": [
            {"goal_id": "goal-a"},
            {"goal_id": "goal-b"},
        ],
    }

    assert (
        planner_reentry_responsibilities(
            source_response=response,
            goal_ids=["goal-a", "goal-b"],
        )
        == []
    )


def test_planner_reentry_rejects_exact_repeat_of_completed_activity() -> None:
    data = {"answer": "done"}
    evidence = ToolResultEvidence(
        evidence_id="evidence-a",
        tool_id="chromie.test.lookup",
        status="completed",
        data=data,
        output_sha256=canonical_value_sha256(data),
    )
    plan = CanonicalPlan(
        plan_id="plan-repeat",
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=1.0,
        goal_ids=["goal-a"],
        steps=[
            {
                "step_id": "step-repeat",
                "capability_id": "chromie.test.lookup",
                "args": {"target": "a"},
                "timing": "sequential",
                "source_goal_ids": ["goal-a"],
            }
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-a",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["step-repeat"],
            }
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-a"],
        },
    )

    assert planner_reentry_repeats_completed_activity(
        source_response=_response(),
        plan=plan,
        extra_context={"terminal_request_id": "request-a"},
        evidence=[evidence],
    )


def test_execution_outcome_user_text_prefers_admitted_turn() -> None:
    response = _response()
    plan = CanonicalPlan(
        plan_id="plan-summary",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=1.0,
        goal_ids=["goal-a"],
        goal_summary="Fallback summary.",
        response_text="Done.",
        goal_outcomes=[
            {
                "goal_id": "goal-a",
                "disposition": "respond",
                "coverage": "complete",
                "response_text": "Done.",
            }
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-a"],
        },
    )

    assert execution_outcome_user_text(response, plan) == "  Check both things.  "


def test_work_request_rejects_unverified_source_projection() -> None:
    request = CognitiveWorkRequest(
        sid="runtime-only-id",
        text="scoped responsibility",
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": "scoped responsibility",
                "output_mode": "information",
                "confidence": 1.0,
            }
        ],
        context={
            "source_turn_provenance": {
                "original_text": "spoofed whole turn",
                "original_text_sha256": "0" * 64,
                "authority": "read_only_source_provenance",
            }
        },
    )

    assert request.source_turn_provenance == {
        "schema_version": 1,
        "turn_id": "",
        "original_text": "scoped responsibility",
        "original_text_sha256": hashlib.sha256(b"scoped responsibility").hexdigest(),
        "language": "auto",
        "authority": "normalized_transport_fallback",
    }


def test_planner_reentry_source_work_projection_is_provenance_not_output_template() -> None:
    source_plan = {
        "schema_version": 1,
        "plan_id": "plan-weather",
        "planner_tier": "fast",
        "disposition": "execute",
        "coverage": "complete",
        "goal_ids": ["goal-weather", "goal-other"],
        "goal_outcomes": [{"goal_id": "goal-weather", "disposition": "execute"}],
        "goal_satisfaction": {"status": "exact", "score": 1.0},
        "metadata": {"path_classification": "terminal"},
        "steps": [
            {
                "step_id": "weather-read",
                "capability_id": "chromie.weather.lookup",
                "args": {"location": "chongqing"},
                "timing": "sequential",
                "source_goal_ids": ["goal-weather"],
                "step_purpose": "acquire_information",
                "expected_outcome": "Weather evidence for Chongqing.",
            },
            {
                "step_id": "other-read",
                "capability_id": "chromie.test.lookup",
                "args": {},
                "timing": "sequential",
                "source_goal_ids": ["goal-other"],
            },
        ],
    }

    projection = planner_reentry_source_work_projection(
        source_plan, goal_ids={"goal-weather"}
    )

    assert projection["plan_id"] == "plan-weather"
    assert projection["goal_ids"] == ["goal-weather"]
    assert [step["step_id"] for step in projection["steps"]] == ["weather-read"]
    for obsolete_envelope_field in (
        "schema_version", "planner_tier", "disposition", "coverage",
        "goal_outcomes", "goal_satisfaction", "metadata",
    ):
        assert obsolete_envelope_field not in projection


def test_planner_reentry_execution_truth_projection_is_fact_shaped_not_output_shaped() -> None:
    truth = {
        "outcome_id": "outcome-weather",
        "aggregate_status": "completed",
        "goal_outcomes": [{
            "goal_id": "goal-weather",
            "status": "completed",
            "planned_satisfaction": {
                "status": "exact",
                "score": 1.0,
                "satisfied_goal_ids": ["goal-weather"],
            },
            "requires_planner_continuation": False,
            "reason_codes": [],
            "evidence_ids": ["evidence-weather"],
            "completion_qualification": {
                "required": True,
                "established": True,
                "qualifications": [{
                    "claim": "capability request completed",
                    "evidence_id": "evidence-weather",
                    "status": "established",
                    "reason_codes": [],
                }],
            },
        }],
        "evidence": [{
            "evidence_id": "evidence-weather",
            "capability_id": "chromie.weather.lookup",
            "source_goal_ids": ["goal-weather"],
            "status": "completed",
            "reason_code": "",
            "observation_status": "available",
            "provider_retryability": {},
        }],
    }

    projection = planner_reentry_execution_truth_projection(
        truth, goal_ids={"goal-weather"}
    )

    assert projection == {
        "execution_outcome_ref": "outcome-weather",
        "aggregate_execution_state": "completed",
        "goal_execution_facts": [{
            "goal_ref": "goal-weather",
            "execution_state": "completed",
            "evidence_refs": ["evidence-weather"],
            "runtime_continuation_required": False,
            "completion_gate": {
                "required": True,
                "established": True,
                "evidence_refs": ["evidence-weather"],
            },
        }],
        "evidence_facts": [{
            "evidence_ref": "evidence-weather",
            "capability_ref": "chromie.weather.lookup",
            "goal_refs": ["goal-weather"],
            "execution_state": "completed",
            "observation_state": "available",
        }],
    }
    serialized = str(projection)
    for output_shaped_key in (
        "goal_outcomes", "planned_satisfaction", "respond", "satisfaction",
        "steps", "disposition", "coverage",
    ):
        assert output_shaped_key not in serialized

def test_planner_reentry_prompt_does_not_expose_old_plan_envelope_as_template() -> None:
    scope = PlannerReentryScope(
        trigger="capability_result_reentry",
        goal_ids=["goal-weather"],
        evidence_refs=["evidence-weather"],
        source_plan_id="plan-weather",
        source_plan_fingerprint="f" * 64,
    )
    request = CognitiveWorkRequest(
        sid="reentry-prompt-projection",
        text="what's the weather today in chongqing?",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "the weather today in chongqing",
            "output_mode": "information",
            "continuity_scope": "goal",
            "confidence": 1.0,
        }],
        interpretation_confidence=1.0,
        planner_reentry_scope=scope,
        context={
            "trusted_execution_outcome": {
                "outcome_id": "outcome-weather",
                "aggregate_status": "completed",
                "goal_outcomes": [{
                    "goal_id": "goal-weather",
                    "status": "completed",
                    "planned_satisfaction": {"status": "exact", "score": 1.0},
                    "requires_planner_continuation": False,
                    "evidence_ids": ["evidence-weather"],
                    "completion_qualification": {
                        "required": True,
                        "established": True,
                        "qualifications": [{
                            "evidence_id": "evidence-weather",
                            "status": "established",
                        }],
                    },
                }],
                "evidence": [{
                    "evidence_id": "evidence-weather",
                    "capability_id": "chromie.weather.lookup",
                    "source_goal_ids": ["goal-weather"],
                    "status": "completed",
                    "observation_status": "available",
                    "provider_retryability": {},
                }],
            },
            "canonical_plan_resolution": {
                "schema_version": 1,
                "plan_id": "plan-weather",
                "planner_tier": "fast",
                "disposition": "execute",
                "coverage": "complete",
                "goal_ids": ["goal-weather"],
                "goal_outcomes": [{"goal_id": "goal-weather", "disposition": "execute"}],
                "goal_satisfaction": {"status": "exact", "score": 1.0},
                "metadata": {"path_classification": "terminal"},
                "steps": [{
                    "step_id": "weather-read",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "chongqing"},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-weather"],
                    "step_purpose": "acquire_information",
                }],
            },
        },
    )
    goal_context = PlannerGoalContext(
        expected_goal_ids=("goal-weather",),
        authoritative_goals=({
            "goal_id": "goal-weather",
            "description": "the weather today in chongqing",
            "metadata": {"output_mode": "information"},
        },),
        cancellation_reentry_goal_ids=frozenset(),
        result_reentry_goal_ids=frozenset({"goal-weather"}),
        response_goal_ids=(),
        response_only=False,
        requires_execution=False,
    )

    prompt = fast_plan_prompt(
        request, [], response_schema={}, goal_context=goal_context
    )

    assert "PLANNER RE-ENTRY CONTRACT" in prompt
    assert "Historical source Work correlation JSON" in prompt
    assert "Trusted execution fact rows JSON" in prompt
    assert "Trusted execution outcome truth JSON" not in prompt
    assert "Authoritative source Plan JSON for exact re-entry correlation" not in prompt
    source_section = prompt.split(
        "Historical source Work correlation JSON", 1
    )[1].split("Trusted Work planning facts JSON", 1)[0]
    for old_envelope_field in (
        '"disposition"', '"coverage"', '"goal_outcomes"',
        '"goal_satisfaction"', '"planner_tier"',
        '"planned_satisfaction"', '"respond"', '"satisfaction"',
    ):
        assert old_envelope_field not in source_section
    assert '"goal_execution_facts"' in source_section
    assert '"evidence_facts"' in source_section
    assert "respond outcome with zero steps" in prompt


def test_fast_evidence_reentry_contract_is_disjoint_from_plan_envelopes() -> None:
    from jsonschema import Draft202012Validator

    schema = fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-weather"],
        evidence_refs=["evidence-weather"],
        allowed_capability_ids=[],
        capability_input_schemas={},
        allow_new_work=False,
    )
    assert schema["title"] == "FastPlannerEvidenceReentryOutput"
    assert set(schema["properties"]) == {
        "goal_decisions",
        "new_work",
        "confidence",
        "plan_relation",
        "user_confirmation_required",
    }
    for forbidden in (
        "goal_outcomes", "steps", "disposition", "coverage",
        "unmet_goal_ids", "unmet_requirements", "response_text",
    ):
        assert forbidden not in schema["properties"]

    valid = {
        "goal_decisions": [{
            "goal_id": "goal-weather",
            "next_action": "respond",
            "satisfaction_status": "exact",
            "satisfaction_score": 1.0,
            "evidence_refs": ["evidence-weather"],
            "unresolved_needs": [],
            "unmet_requirements": [],
            "rationale": "Fresh trusted weather evidence fully answers the Goal.",
        }],
        "new_work": [],
        "confidence": 1.0,
        "plan_relation": "exact",
        "user_confirmation_required": False,
    }
    Draft202012Validator(schema).validate(valid)
    assert not Draft202012Validator(schema).is_valid({
        "goal_outcomes": [{"goal_id": "goal-weather", "disposition": "respond"}],
        "steps": [],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
    })


def test_fast_evidence_reentry_lifts_to_current_planner_contract() -> None:
    compact = PlannerEvidenceReentryModelOutput.model_validate({
        "goal_decisions": [{
            "goal_id": "goal-weather",
            "next_action": "respond",
            "satisfaction_status": "exact",
            "satisfaction_score": 1.0,
            "evidence_refs": ["evidence-weather"],
            "unresolved_needs": [],
            "unmet_requirements": [],
            "rationale": "Fresh trusted weather evidence fully answers the Goal.",
        }],
        "new_work": [],
        "confidence": 1.0,
        "plan_relation": "exact",
        "user_confirmation_required": False,
    })
    lifted = materialize_evidence_reentry_model_output(
        compact,
        expected_goal_ids_for_turn=["goal-weather"],
        allowed_evidence_refs={"evidence-weather"},
        completed_step_evidence={
            "weather-read": {
                "step_id": "weather-read",
                "evidence_id": "evidence-weather",
                "source_goal_ids": ["goal-weather"],
            }
        },
    )
    current = PlannerModelOutput.model_validate(lifted)
    assert current.disposition == "respond"
    assert current.steps == []
    assert current.goal_outcomes["goal-weather"].follows_step_ids == ["weather-read"]
    # The lifted DTO carries no Plan-level aggregate; Host folds it from the per-Goal judgment.
    assert "goal_satisfaction" not in lifted
    assert current.derived_goal_satisfaction is not None
    assert current.derived_goal_satisfaction.status == "exact"


def _reentry_decision_output(status="exact", score=1.0):
    return {
        "goal_decisions": [{
            "goal_id": "goal-weather", "next_action": "respond",
            "satisfaction_status": status, "satisfaction_score": score,
            "evidence_refs": ["evidence-weather"],
            "rationale": "Fresh weather Evidence answers the current request.",
        }],
        "new_work": [], "confidence": 1.0, "plan_relation": "exact",
        "user_confirmation_required": False,
    }


@pytest.mark.parametrize("status", ["exact", "substantial", "partial", "unsatisfied"])
@pytest.mark.parametrize("score", [0.0, 0.01, 0.5, 0.749999, 0.75, 0.949999, 0.95, 1.0])
def test_reentry_decoder_satisfaction_bands_match_dto(status, score):
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError

    schema = fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-weather"], evidence_refs=["evidence-weather"],
        allowed_capability_ids=[], allow_new_work=False,
    )
    raw = _reentry_decision_output(status, score)
    try:
        PlannerEvidenceReentryModelOutput.model_validate(raw)
        accepted = True
    except ValidationError:
        accepted = False
    assert Draft202012Validator(schema).is_valid(raw) == accepted


@pytest.mark.parametrize("allow_new_work", [True, False])
def test_reentry_never_refuses_a_failed_read(allow_new_work):
    """Live 2026-10-15: a weather timeout re-entered as `refused`; Host rejects it for every tier."""
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError

    schema = fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-weather"], evidence_refs=["evidence-weather"],
        allowed_capability_ids=[], allow_new_work=allow_new_work,
    )
    validator = Draft202012Validator(schema)
    for action, accepted in (("refused", False), ("unavailable", True)):
        raw = _reentry_decision_output("unsatisfied", 0.0)
        raw["goal_decisions"][0].update(
            next_action=action, evidence_refs=[], unresolved_needs=[],
            rationale="The weather provider did not answer.",
        )
        try:
            PlannerEvidenceReentryModelOutput.model_validate(raw)
            dto_accepts = True
        except ValidationError:
            dto_accepts = False
        assert dto_accepts is accepted
        assert validator.is_valid(raw) is accepted


@pytest.mark.parametrize("goal_count", [1, 2])
def test_reentry_decoder_offers_no_delegation(goal_count):
    # One Planner (PLANNER-AUTHORITY-001): re-entry decides, never delegates.
    from jsonschema import Draft202012Validator

    raw = _reentry_decision_output()
    goals = ["goal-weather"]
    if goal_count == 2:
        goals.append("goal-other")
        other = copy.deepcopy(raw["goal_decisions"][0])
        other["goal_id"] = "goal-other"
        raw["goal_decisions"].append(other)
    schema = fast_evidence_reentry_response_schema(
        expected_goal_ids=goals, evidence_refs=["evidence-weather"],
        allowed_capability_ids=[], allow_new_work=False,
    )
    validator = Draft202012Validator(schema)
    assert validator.is_valid(raw)
    assert not validator.is_valid({**raw, "escalation_reason": "Needs deeper reasoning."})
    raw["goal_decisions"][-1].update(
        next_action="escalate", satisfaction_status="partial", satisfaction_score=0.5,
    )
    assert not validator.is_valid(raw)


def test_fast_evidence_reentry_prompt_is_bounded_and_has_no_old_output_template() -> None:
    scope = PlannerReentryScope(
        trigger="capability_result_reentry",
        goal_ids=["goal-weather"],
        evidence_refs=["evidence-weather"],
        source_plan_id="plan-weather",
        source_plan_fingerprint="f" * 64,
    )
    request = CognitiveWorkRequest(
        sid="compact-reentry",
        text="What's the weather today in Chongqing?",
        responsibilities=[{
            "local_ref": "r1",
            "outcome": "the weather today in Chongqing",
            "output_mode": "information",
            "continuity_scope": "goal",
            "confidence": 1.0,
        }],
        interpretation_confidence=1.0,
        planner_reentry_scope=scope,
        context={
            "trusted_terminal_evidence": [{
                "evidence_id": "evidence-weather",
                "tool_id": "chromie.weather.lookup",
                "status": "completed",
                "source_goal_ids": ["goal-weather"],
                "data": {"location": "Chongqing", "temperature_c": 25.8},
            }],
            "trusted_execution_outcome": {
                "outcome_id": "outcome-weather",
                "aggregate_status": "completed",
                "goal_outcomes": [{
                    "goal_id": "goal-weather",
                    "status": "completed",
                    "requires_planner_continuation": False,
                    "evidence_ids": ["evidence-weather"],
                    "completion_qualification": {
                        "required": True,
                        "established": True,
                    },
                }],
                "evidence": [{
                    "evidence_id": "evidence-weather",
                    "capability_id": "chromie.weather.lookup",
                    "source_goal_ids": ["goal-weather"],
                    "status": "completed",
                    "observation_status": "available",
                }],
            },
            "canonical_plan_resolution": {
                "plan_id": "plan-weather",
                "goal_ids": ["goal-weather"],
                "steps": [{
                    "step_id": "weather-read",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "Chongqing"},
                    "source_goal_ids": ["goal-weather"],
                    "step_purpose": "acquire_information",
                }],
            },
        },
    )
    goal_context = PlannerGoalContext(
        expected_goal_ids=("goal-weather",),
        authoritative_goals=({
            "goal_id": "goal-weather",
            "description": "the weather today in Chongqing",
            "metadata": {"output_mode": "information"},
        },),
        cancellation_reentry_goal_ids=frozenset(),
        result_reentry_goal_ids=frozenset({"goal-weather"}),
        response_goal_ids=(),
        response_only=False,
        requires_execution=False,
    )
    prompt = str(fast_evidence_reentry_prompt(
        request, [], goal_context=goal_context, allow_new_work=False
    ))
    assert len(prompt) < 8000
    assert "FastPlannerEvidenceReentryOutput" in prompt
    assert "Owner-approved Chromie identity" not in prompt
    assert "Personality Expression" not in prompt
    assert "Stable Mind" not in prompt
    facts = prompt.split("Trusted post-execution facts JSON:", 1)[1]
    assert '"fresh_evidence"' in facts
    assert '"goal_execution_facts"' in facts
    # Historical objects may be discussed in the contract text, but no old Planner
    # result object is embedded as a candidate output example.
    assert '"planned_satisfaction"' not in facts
    assert '"goal_satisfaction"' not in facts
    assert '"respond"' not in facts


def test_reentry_new_work_purpose_is_its_providers() -> None:
    """Live 2026-10-12 (cond_sunny_wave_en): re-entry decided a wave as an information
    read, which the step contract then rejected; the decoder now offers each provider's purpose."""
    from jsonschema import Draft202012Validator

    from agent.app.planner_validation import capability_ids_acquiring_information

    catalog = [
        {"capability_id": "soridormi.wave_hand", "effects": ["physical_motion"],
         "safety_class": "physical_motion", "input_schema": {"type": "object", "properties": {}}},
        {"capability_id": "chromie.weather.lookup", "effects": ["read_only"], "safety_class": "safe_read",
         "hints": {"resource_contract": {"provider_role": "acquire_information"}},
         "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}}},
    ]
    schema = fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-wave"], evidence_refs=["evidence-weather"],
        allowed_capability_ids=[item["capability_id"] for item in catalog],
        capability_input_schemas={item["capability_id"]: item["input_schema"] for item in catalog},
        information_capability_ids=capability_ids_acquiring_information(catalog),
    )
    validator = Draft202012Validator(schema)

    def output(step):
        return {
            "goal_decisions": [{
                "goal_id": "goal-wave", "next_action": "execute",
                "satisfaction_status": "unsatisfied", "satisfaction_score": 0.0,
                "evidence_refs": ["evidence-weather"], "rationale": "Tomorrow is sunny, so wave.",
            }],
            "new_work": [{"step_id": "act_wave_final", "args": {}, "depends_on": [],
                          "source_goal_ids": ["goal-wave"], **step}],
            "confidence": 1.0, "plan_relation": "exact", "user_confirmation_required": False,
        }

    live = output({"capability_id": "soridormi.wave_hand", "step_purpose": "acquire_information"})
    assert not validator.is_valid(live)
    assert validator.is_valid(output({"capability_id": "soridormi.wave_hand", "step_purpose": "achieve_effect"}))
    read = {"capability_id": "chromie.weather.lookup", "args": {"location": "Shanghai"},
            "step_purpose": "acquire_information"}
    assert not validator.is_valid(output(read))
    assert validator.is_valid(output({**read, "expected_outcome": "Tomorrow's Shanghai forecast."}))


def test_reentry_decoder_offers_only_actions_the_host_accepts() -> None:
    """Live 2026-10-12: a timed-out read was "responded" (Host requires completed
    Evidence), and a clarify came as a safe_adjustment without Work (DTO requires Work);
    both were rejected and the person heard nothing."""
    from jsonschema import Draft202012Validator

    wave = {"type": "object", "properties": {}, "additionalProperties": False}

    def schema(completed):
        return Draft202012Validator(fast_evidence_reentry_response_schema(
            expected_goal_ids=["goal-rain"], evidence_refs=["evidence-weather"],
            allowed_capability_ids=["test.nod"], capability_input_schemas={"test.nod": wave},
            completed_evidence_refs=completed))

    def output(action, *, work=(), relation="exact", confirm=False, status="unsatisfied", score=0.0):
        return {"goal_decisions": [{"goal_id": "goal-rain", "next_action": action,
                                    "satisfaction_status": status, "satisfaction_score": score,
                                    "evidence_refs": ["evidence-weather"], "rationale": "From the read."}],
                "new_work": list(work), "confidence": 1.0, "plan_relation": relation,
                "user_confirmation_required": confirm}

    timed_out, completed = schema([]), schema(["evidence-weather"])
    assert not timed_out.is_valid(output("respond"))
    assert timed_out.is_valid(output("unavailable"))
    assert completed.is_valid(output("respond", status="exact", score=1.0))
    assert not completed.is_valid(output("clarify", relation="safe_adjustment", confirm=True))
    assert not completed.is_valid(output("clarify", confirm=True))
    nod = {"step_id": "nod", "capability_id": "test.nod", "args": {}, "depends_on": ["evidence-weather"],
           "source_goal_ids": ["goal-rain"]}
    assert completed.is_valid(output("execute", work=[nod]))
    assert completed.is_valid(output("execute", work=[nod], relation="alternative", confirm=True))
    assert not completed.is_valid(output("execute", work=[nod], relation="alternative"))


def test_a_reentry_clarify_names_the_need_its_goal_outcome_requires() -> None:
    """Live 2026-10-13 (errand_milk_en, errand_remote_en): after a failed fetch the
    Planner chose clarify with only a rationale. The decoder and the compact DTO
    accepted it, its lifted Goal outcome did not, and the person heard a generic
    failure. Each of the three now asks for the input need the person can resolve."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-milk"], evidence_refs=["evidence-fetch"],
        allowed_capability_ids=[], allow_new_work=False))

    def output(needs):
        return {"goal_decisions": [{"goal_id": "goal-milk", "next_action": "clarify",
                                    "satisfaction_status": "unsatisfied", "satisfaction_score": 0.0,
                                    "evidence_refs": ["evidence-fetch"], "unresolved_needs": needs,
                                    "unmet_requirements": ["the milk was not found"],
                                    "rationale": "The fetch failed."}],
                "new_work": [], "confidence": 1.0, "plan_relation": "exact",
                "user_confirmation_required": False}

    assert not validator.is_valid(output([]))
    assert validator.is_valid(output(["where the milk is"]))
    with pytest.raises(ValueError, match="clarify re-entry requires the unresolved input need"):
        PlannerEvidenceReentryModelOutput.model_validate(output([]))
    compact = PlannerEvidenceReentryModelOutput.model_validate(output(["where the milk is"]))
    lifted = PlannerModelOutput.model_validate(materialize_evidence_reentry_model_output(
        compact, expected_goal_ids_for_turn=["goal-milk"], allowed_evidence_refs={"evidence-fetch"}))
    assert lifted.goal_outcomes["goal-milk"].unresolved == ["where the milk is"]


def test_completed_work_may_be_cited_by_its_evidence_ref() -> None:
    """Live 2026-10-12 (cond_sunny_wave_en): the re-entry wave depended on the read's
    evidence_ref, the identifier its prompt shows for completed Work."""
    from agent.app.planner_model_contract import materialize_planner_output

    completed = {"weather-read": {"step_id": "weather-read", "evidence_id": "evidence-weather",
                                  "source_goal_ids": ["goal-wave"]}}
    compact = PlannerEvidenceReentryModelOutput.model_validate({
        "goal_decisions": [{
            "goal_id": "goal-wave", "next_action": "execute", "satisfaction_status": "unsatisfied",
            "satisfaction_score": 0.0, "evidence_refs": ["evidence-weather"],
            "rationale": "Tomorrow is sunny, so wave."}],
        "new_work": [{"step_id": "wave", "capability_id": "test.wave", "args": {},
                      "depends_on": ["evidence-weather"], "source_goal_ids": ["goal-wave"]}],
        "confidence": 1.0, "plan_relation": "exact", "user_confirmation_required": False,
    })
    lifted = PlannerModelOutput.model_validate(materialize_evidence_reentry_model_output(
        compact, expected_goal_ids_for_turn=["goal-wave"], allowed_evidence_refs={"evidence-weather"},
        completed_step_evidence=completed))

    def plan(evidence):
        return materialize_planner_output(lifted, planner_tier="fast", plan_id="plan-wave",
                                          expected_goal_ids_for_turn=["goal-wave"],
                                          completed_step_evidence=evidence)

    assert [step["step_id"] for step in plan(completed)["steps"]] == ["wave"]
    with pytest.raises(ValueError, match="must cite earlier steps or completed Work"):
        plan({})


def test_reentry_sees_the_action_the_source_plan_held_for_it() -> None:
    """Owner choice B (2026-10-12): the source Plan's deferred step reaches the re-entry,
    which decides it from the trusted result; executable steps stay as before."""
    from shared.chromie_contracts.plan import CanonicalPlanStep, validate_deferred_steps

    read = CanonicalPlanStep(step_id="read", capability_id="chromie.weather.lookup", args={"location": "Shanghai"},
                             source_goal_ids=["goal-nod"], step_purpose="acquire_information",
                             expected_outcome="Shanghai rain forecast")
    nod = CanonicalPlanStep(step_id="nod", capability_id="test.nod", args={"count": 2},
                            source_goal_ids=["goal-nod"], metadata={"depends_on": ["read"], "deferred": True})
    plan = {"plan_id": "plan-nod", "goal_ids": ["goal-nod"], "steps": [read.model_dump()],
            "deferred_steps": [nod.model_dump()]}
    projected = planner_reentry_source_work_projection(plan, goal_ids={"goal-nod"})
    assert [step["step_id"] for step in projected["steps"]] == ["read"]
    assert projected["deferred_steps"] == [{"step_id": "nod", "capability_id": "test.nod", "args": {"count": 2},
                                            "source_goal_ids": ["goal-nod"], "depends_on": ["read"]}]
    assert "deferred_steps" not in planner_reentry_source_work_projection(
        {**plan, "deferred_steps": []}, goal_ids={"goal-nod"})

    validate_deferred_steps([read], [nod])
    wave = read.model_copy(update={"step_id": "wave", "capability_id": "test.wave", "step_purpose": "achieve_effect"})
    for steps, held, reason in (
        ([read, wave], nod.model_copy(update={"metadata": {"depends_on": ["wave"]}}), "acquisition"),
        ([read], nod.model_copy(update={"metadata": {}}), "waits on acquisition"),
        ([read], nod.model_copy(update={"source_goal_ids": ["goal-other"]}), "own Goal"),
    ):
        with pytest.raises(ValueError, match=reason):
            validate_deferred_steps(steps, [held])


def test_a_held_effect_is_performed_only_as_a_committed_execute() -> None:
    """Live 2026-10-13 (cond_sunny_wave_en/zh): the re-entry performed the held wave but
    scored it partial 0.5; Host made that a limitation and the person heard "I can't
    wave". For a Goal whose source Plan holds an effect, execute is offered only at
    substantial or exact; other Goals keep their bands."""
    from jsonschema import Draft202012Validator

    wave = {"type": "object", "properties": {}, "additionalProperties": False}

    def output(goal, status, score):
        return {"goal_decisions": [{"goal_id": goal, "next_action": "execute",
                                    "satisfaction_status": status, "satisfaction_score": score,
                                    "evidence_refs": ["evidence-weather"], "rationale": "From the read."}],
                "new_work": [{"capability_id": "test.wave", "step_id": "wave", "args": {},
                              "depends_on": ["evidence-weather"], "source_goal_ids": [goal]}],
                "confidence": 1.0, "plan_relation": "exact", "user_confirmation_required": False}

    for held in ([], ["goal-wave"]):
        schema = Draft202012Validator(fast_evidence_reentry_response_schema(
            expected_goal_ids=["goal-wave"], evidence_refs=["evidence-weather"],
            allowed_capability_ids=["test.wave"], capability_input_schemas={"test.wave": wave},
            completed_evidence_refs=["evidence-weather"], held_effect_goal_ids=held))
        assert schema.is_valid(output("goal-wave", "partial", 0.5)) is (not held)
        assert schema.is_valid(output("goal-wave", "exact", 1.0))

    mixed = Draft202012Validator(fast_evidence_reentry_response_schema(
        expected_goal_ids=["goal-wave", "goal-read"], evidence_refs=["evidence-weather"],
        allowed_capability_ids=["test.wave"], capability_input_schemas={"test.wave": wave},
        completed_evidence_refs=["evidence-weather"], held_effect_goal_ids=["goal-wave"]))
    decision = output("goal-read", "partial", 0.5)["goal_decisions"][0]
    both = output("goal-wave", "exact", 1.0)
    both["goal_decisions"].append(decision)
    assert mixed.is_valid(both)
    both["goal_decisions"][0].update(satisfaction_status="partial", satisfaction_score=0.5)
    assert not mixed.is_valid(both)


def test_a_reentry_answer_outside_reporting_is_a_committed_answer() -> None:
    """Live 2026-10-12: the re-entry answered "no rain, so no nod" scored unsatisfied 0.0;
    Host turned it into a limitation by the commitment rule. Outside reporting, respond is
    offered only at substantial or exact; a lower score is unavailable's decision."""
    from jsonschema import Draft202012Validator

    def schema(commitment):
        return Draft202012Validator(fast_evidence_reentry_response_schema(
            expected_goal_ids=["goal-weather"], evidence_refs=["evidence-weather"],
            allowed_capability_ids=[], allow_new_work=False,
            completed_evidence_refs=["evidence-weather"], respond_requires_commitment=commitment))

    low, exact = _reentry_decision_output("unsatisfied", 0.0), _reentry_decision_output("exact", 1.0)
    assert schema(False).is_valid(low)
    assert not schema(True).is_valid(low)
    assert schema(True).is_valid(exact)
