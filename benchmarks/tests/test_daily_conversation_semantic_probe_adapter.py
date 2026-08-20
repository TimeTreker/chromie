from __future__ import annotations

import json

from scripts import daily_conversation_semantic_probe_adapter as adapter


def _scenario() -> dict:
    return {
        "id": "daily.v1.test.no_oracle_leak",
        "inputs": {
            "language": "en-US",
            "turns": ["What's the weather in Seattle?", "No, Portland."],
        },
        "context": {
            "interaction": {
                "scenario_state": "two-turn location correction",
                "turn_count": 2,
            },
            "capabilities": ["chromie.weather.lookup"],
        },
        "capabilities": ["chromie.weather.lookup"],
        "expectations": {
            "primary_outcomes": ["SECRET EXPECTED OUTCOME"],
            "forbidden_behaviors": ["SECRET FORBIDDEN BEHAVIOR"],
            "invariants": ["typed_output_and_schema_boundaries_remain_valid"],
        },
        "review_rubric": {"dimensions": ["SECRET REVIEW DIMENSION"]},
    }


def _valid_candidate() -> dict:
    return {
        "interpretation": "Correct the current weather request to Portland.",
        "primary_act": "action_pending",
        "response": "Okay, Portland—I'll check the current weather there.",
        "goals": [
            {
                "kind": "fresh_information",
                "operation": "correct",
                "description": "Get current Portland weather.",
            }
        ],
        "evidence_needed": "current_external",
        "ambiguity": "",
        "coordination": "correction",
        "completion_claimed": False,
    }


def test_semantic_probe_supplies_state_but_never_oracle_fields() -> None:
    prompt = adapter._prompt(_scenario())

    assert "two-turn location correction" in prompt
    assert "chromie.weather.lookup" in prompt
    assert "Seattle" in prompt
    assert "Portland" in prompt
    assert "SECRET EXPECTED OUTCOME" not in prompt
    assert "SECRET FORBIDDEN BEHAVIOR" not in prompt
    assert "SECRET REVIEW DIMENSION" not in prompt


def test_semantic_probe_small_contract_rejects_cross_contract_output() -> None:
    candidate = _valid_candidate()

    assert adapter._validate_candidate(candidate) == []
    candidate["unsupported_field"] = "not allowed"
    assert adapter._validate_candidate(candidate) == [
        "unknown fields: unsupported_field"
    ]


def test_schema_validity_does_not_promote_semantic_invariants() -> None:
    results = adapter._structural_invariants(
        [
            "typed_output_and_schema_boundaries_remain_valid",
            "one_primary_user_facing_act_per_turn",
            "speech_claims_match_available_commitment_and_evidence",
            "chromie_identity_and_robotic_body_truth_remain_consistent",
        ],
        structured_output_valid=True,
    )

    assert results["typed_output_and_schema_boundaries_remain_valid"]["passed"] is True
    assert results["one_primary_user_facing_act_per_turn"]["passed"] is None
    assert (
        results["speech_claims_match_available_commitment_and_evidence"]["passed"]
        is None
    )
    assert (
        results["chromie_identity_and_robotic_body_truth_remain_consistent"]["passed"]
        is None
    )


def test_semantic_probe_retains_candidate_output_for_review(
    tmp_path, monkeypatch
) -> None:
    candidate = _valid_candidate()

    def fake_call(**_kwargs):
        return (
            {
                "model": "candidate:model",
                "response": json.dumps(candidate),
                "done": True,
                "eval_count": 40,
            },
            123.0,
        )

    monkeypatch.setattr(adapter, "_call_ollama", fake_call)
    request = {
        "schema_version": 1,
        "scenario": _scenario(),
        "run": {"model": "candidate:model", "prompt_revision": "probe-v1"},
    }

    observation = adapter._execute(request, tmp_path)

    assert observation["primary_task_passed"] is None
    assert observation["primary_outcome"]["candidate_semantic_plan"] == candidate
    assert observation["auxiliary_behavior"]["oracle_fields_supplied_to_candidate"] == []
    artifact_path = tmp_path / "daily.v1.test.no_oracle_leak/semantic_probe.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["candidate_output"] == candidate
    assert json.loads(artifact["raw_model_text"]) == candidate
    assert artifact["oracle_fields_supplied_to_candidate"] == []
