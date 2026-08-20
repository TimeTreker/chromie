from __future__ import annotations

from scripts.daily_conversation_live_adapter import (
    _safe_id,
    _semantic_turn_record,
    _structural_invariants,
    _turns,
)


def test_daily_conversation_live_adapter_accepts_single_and_multi_turn_inputs() -> None:
    assert _turns({"text": " Hello "}) == ["Hello"]
    assert _turns({"turns": [" First ", "Second"]}) == ["First", "Second"]


def test_daily_conversation_live_adapter_keeps_artifact_ids_bounded() -> None:
    assert _safe_id("daily.v1/friends:reply") == "daily.v1-friends-reply"


def test_daily_conversation_live_adapter_reports_structural_not_semantic_proof() -> None:
    summary = {
        "ok": True,
        "preview_only": True,
        "interaction_response": {
            "speech": [
                {
                    "text": "A response",
                    "metadata": {"delivery_role": "response"},
                }
            ]
        },
        "provenance": {"runtime_identity": {"complete": True}},
    }
    results = _structural_invariants(
        [
            "typed_output_and_schema_boundaries_remain_valid",
            "speech_claims_match_available_commitment_and_evidence",
            "chromie_identity_and_robotic_body_truth_remain_consistent",
        ],
        [summary],
    )

    assert results["typed_output_and_schema_boundaries_remain_valid"]["passed"] is True
    assert results["speech_claims_match_available_commitment_and_evidence"]["passed"] is None
    assert results["chromie_identity_and_robotic_body_truth_remain_consistent"]["passed"] is None
    assert "semantic" in results["speech_claims_match_available_commitment_and_evidence"]["detail"]
    assert (
        "LLM review"
        in results["chromie_identity_and_robotic_body_truth_remain_consistent"]["detail"]
    )


def test_daily_conversation_live_adapter_retains_goal_and_plan_semantics() -> None:
    record = _semantic_turn_record(
        {
            "text": "Walk and tell a story",
            "ok": True,
            "interaction_response": {
                "speech": [{"text": "Once upon a time"}],
                "capabilities": [
                    {
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 5},
                        "timing": "parallel",
                        "metadata": {"execution_lane": "activity"},
                    }
                ],
            },
            "cognitive_runtime": {
                "goal_association": {"new_goals": [{"description": "walk"}]},
                "metadata": {"deep_planner_invoked": True},
            },
            "errors": [],
        }
    )

    assert record["goal_association"]["new_goals"][0]["description"] == "walk"
    assert record["planner_metadata"]["deep_planner_invoked"] is True
    assert record["proposed_skills"][0]["timing"] == "parallel"
