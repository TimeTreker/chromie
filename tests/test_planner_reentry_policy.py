from __future__ import annotations

import hashlib

from orchestrator.runtime.planner_reentry import (
    execution_outcome_user_text,
    planner_reentry_repeats_completed_activity,
    planner_reentry_responsibilities,
    suppress_already_delivered_speech,
    suppress_redundant_completed_body_followup,
    terminal_evidence_relevance,
    terminal_result_waits_for_batch_closure,
)
from agent.app.planner_context import (
    goal_association_prompt_projection,
    planner_goal_context,
)
from agent.app.planner_fallback import materialize_fast_escalation
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
            "normalized_input": {"text": "Check both things."}
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
        metadata["goal_interpretation"] = {
            "responsibilities": [
                {
                    "local_ref": "responsibility-a",
                    "outcome": "Obtain the first requested result.",
                    "output_mode": "information",
                    "relationship": "new",
                    "confidence": 1.0,
                },
                {
                    "local_ref": "responsibility-b",
                    "outcome": "Obtain the second requested result.",
                    "output_mode": "information",
                    "relationship": "new",
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


def test_successful_multi_capability_result_waits_for_aggregate_closure() -> None:
    assert terminal_result_waits_for_batch_closure(
        source_capability_count=2,
        status="completed",
    )
    assert not terminal_result_waits_for_batch_closure(
        source_capability_count=1,
        status="completed",
    )
    assert not terminal_result_waits_for_batch_closure(
        source_capability_count=2,
        status="failed",
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
    assert [
        item["goal_id"] for item in association_projection["new_goals"]
    ] == ["goal-walk", "goal-blink"]


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

    fallback = materialize_fast_escalation(
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


def test_planner_reentry_selects_only_goal_bound_responsibility() -> None:
    responsibilities = planner_reentry_responsibilities(
        source_response=_response(),
        goal_ids=["goal-a"],
    )

    assert [item.local_ref for item in responsibilities] == ["responsibility-a"]


def test_planner_reentry_does_not_invent_missing_responsibility() -> None:
    assert planner_reentry_responsibilities(
        source_response=_response(include_interpretation=False),
        goal_ids=["goal-a"],
    ) == []


def test_one_unbound_responsibility_does_not_cover_multiple_goals() -> None:
    response = _response()
    response.metadata["goal_interpretation"] = {
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

    assert planner_reentry_responsibilities(
        source_response=response,
        goal_ids=["goal-a", "goal-b"],
    ) == []


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


def test_duplicate_speech_suppression_preserves_only_new_delta() -> None:
    response = InteractionResponse(
        interaction_id="interaction-speech-delta",
        speech=[
            {"id": "speech-old", "text": "Already said."},
            {"id": "speech-new", "text": "New result."},
        ],
    )

    filtered, count = suppress_already_delivered_speech(
        response,
        ["  Already   said.  "],
    )

    assert count == 1
    assert [item.text for item in filtered.speech] == ["New result."]


def test_completed_body_followup_is_suppressed_after_delivered_sibling_response() -> None:
    source = _response()
    source.metadata["goal_association"]["new_goals"] = [
        {
            "goal_id": "goal-a",
            "source_responsibility_refs": ["responsibility-a"],
            "metadata": {"output_mode": "body_action"},
        },
        {
            "goal_id": "goal-b",
            "source_responsibility_refs": ["responsibility-b"],
            "metadata": {"output_mode": "speech"},
        },
    ]
    plan = CanonicalPlan(
        plan_id="mixed-body-and-speech",
        planner_tier="fast",
        disposition="mixed",
        coverage="complete",
        confidence=1.0,
        goal_ids=["goal-a", "goal-b"],
        steps=[
            {
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-a"],
            }
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-a",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["blink"],
            },
            {
                "goal_id": "goal-b",
                "disposition": "respond",
                "coverage": "complete",
                "response_text": "A joke.",
            },
        ],
    )
    followup = InteractionResponse(
        interaction_id="body-followup",
        speech=[{"id": "body-done", "text": "I blinked twice."}],
    )
    evidence = ToolResultEvidence(
        evidence_id="blink-result",
        tool_id="soridormi.blink_eyes",
        status="completed",
        data={},
        output_sha256=canonical_value_sha256({}),
    )

    filtered, count = suppress_redundant_completed_body_followup(
        followup,
        source_response=source,
        source_plan=plan,
        reentry_goal_ids=["goal-a"],
        evidence=[evidence],
        delivered_events=[{"source_goal_ids": ["goal-b"], "text": "A joke."}],
    )

    assert count == 1
    assert filtered.speech == []


def test_completed_information_result_is_not_suppressed_by_sibling_response() -> None:
    source = _response()
    source.metadata["goal_association"]["new_goals"][0]["metadata"] = {
        "output_mode": "information"
    }
    plan = CanonicalPlan(
        plan_id="mixed-information-and-speech",
        planner_tier="fast",
        disposition="mixed",
        coverage="complete",
        confidence=1.0,
        goal_ids=["goal-a", "goal-b"],
        steps=[
            {
                "step_id": "lookup",
                "capability_id": "chromie.test.lookup",
                "args": {},
                "source_goal_ids": ["goal-a"],
            }
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-a",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["lookup"],
            },
            {
                "goal_id": "goal-b",
                "disposition": "respond",
                "coverage": "complete",
                "response_text": "Meanwhile.",
            },
        ],
    )
    followup = InteractionResponse(
        interaction_id="information-followup",
        speech=[{"id": "result", "text": "The result is ready."}],
    )
    evidence = ToolResultEvidence(
        evidence_id="lookup-result",
        tool_id="chromie.test.lookup",
        status="completed",
        data={"value": 1},
        output_sha256=canonical_value_sha256({"value": 1}),
    )

    filtered, count = suppress_redundant_completed_body_followup(
        followup,
        source_response=source,
        source_plan=plan,
        reentry_goal_ids=["goal-a"],
        evidence=[evidence],
        delivered_events=[{"source_goal_ids": ["goal-b"]}],
    )

    assert count == 0
    assert [item.text for item in filtered.speech] == ["The result is ready."]


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
        "original_text_sha256": hashlib.sha256(
            b"scoped responsibility"
        ).hexdigest(),
        "language": "auto",
        "authority": "normalized_transport_fallback",
    }
