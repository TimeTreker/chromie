from __future__ import annotations

from orchestrator.runtime.planner_reentry import (
    execution_outcome_user_text,
    planner_reentry_repeats_completed_activity,
    planner_reentry_responsibilities,
    suppress_already_delivered_speech,
    terminal_evidence_relevance,
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
                    "output_mode": "capability_work",
                    "relationship": "new",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 1.0,
                },
                {
                    "local_ref": "responsibility-b",
                    "outcome": "Obtain the second requested result.",
                    "output_mode": "capability_work",
                    "relationship": "new",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
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
                "output_mode": "capability_work",
                "relationship": "new",
                "completion_requires_work": True,
                "completion_requires_fresh_evidence": True,
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

    assert execution_outcome_user_text(response, plan) == "Check both things."
