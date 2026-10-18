from __future__ import annotations

from pathlib import Path

from scripts.daily_conversation_live_adapter import (
    _configured_fast_model,
    _observation,
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


def _health_observation(tmp_path: Path, *, fast_model: str, expected_fast_model: str | None):
    evidence_dir = tmp_path / "turn"
    evidence_dir.mkdir()
    (evidence_dir / "agent_health.json").write_text(
        '{"model": "chromie-gemma4-12b", "goal_association_model": "chromie-gemma4-12b", '
        f'"planner_model": "{fast_model}"}}',
        encoding="utf-8",
    )
    request = {
        "scenario": {"id": "daily.v1.case", "inputs": {"text": "Hi"}, "expectations": {}},
        "run": {"model": "chromie-gemma4-12b"},
    }
    summary = {"ok": True, "evidence_dir": str(evidence_dir), "interaction_response": {}}
    return _observation(request, [summary], tmp_path, expected_fast_model=expected_fast_model)


def test_daily_conversation_live_adapter_uses_the_configured_fast_model(tmp_path: Path) -> None:
    # A maintained SGLang profile serves its own Planner model, not qwen3:4b.
    observation = _health_observation(
        tmp_path, fast_model="chromie-gemma4-12b", expected_fast_model="chromie-gemma4-12b"
    )
    topology = next(item for item in observation["evidence"] if item["kind"] == "model_topology")
    assert topology["configured_fast_model_match"] is True
    assert observation["primary_task_passed"] is None


def test_daily_conversation_live_adapter_fails_a_fast_model_mismatch(tmp_path: Path) -> None:
    observation = _health_observation(
        tmp_path, fast_model="qwen3:4b", expected_fast_model="chromie-qwen35-4b"
    )
    assert observation["primary_task_passed"] is False


def test_daily_conversation_live_adapter_reads_the_profile_fast_model() -> None:
    assert _configured_fast_model({"AGENT_PLANNER_MODEL": " chromie-qwen35-4b "}) == "chromie-qwen35-4b"
    assert _configured_fast_model({}) is None
