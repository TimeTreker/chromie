from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.mining.catalog import build_candidate_catalog
from benchmarks.mining.models import (
    MiningError,
    candidate_fingerprint,
    create_review_record,
    load_json,
    validate_candidate,
    validate_mining_manifest,
    validate_review_record,
)
from benchmarks.mining.promote import promote_candidate
from benchmarks.mining.variations import build_variation_briefs


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "benchmarks/manifests/scenario_mining_v1.json"


def _manifest() -> dict:
    return load_json(MANIFEST_PATH)


def _candidate(text: str = "Walk forward, not a social gesture.") -> dict:
    return {
        "schema_version": 1,
        "candidate_contract": {
            "schema_version": 1,
            "authoritative": False,
            "runtime_policy_authority": False,
            "auto_promotion_allowed": False,
        },
        "id": "candidate_walk_not_social",
        "suite": "goal_interpretation",
        "level": "module",
        "description": "Mined regression candidate.",
        "tags": ["candidate", "experience-mined", "wrong_action_class"],
        "review": {
            "status": "pending_human_review",
            "source_episode_id": "episode-1",
            "source_evaluation_id": "evaluation-1",
            "source_conversation_id": "conversation-1",
            "score": 30,
            "requires_human_review": True,
            "reviewed_by": None,
            "reviewed_at": None,
        },
        "promotion": {
            "regression_allowed": False,
            "training_allowed": False,
            "auto_promotion_allowed": False,
            "required_review_status": "approved",
        },
        "input": {"text": text},
        "stub": {
            "llm_decision": {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "walk forward instead of making a social gesture",
                        "bindings": {"direction": "forward"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        },
        "expect": {
            "confidence": 0.95,
            "llm_calls": 1,
            "llm_stages": ["goal_interpretation"],
            "unresolved": [],
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "walk forward instead of making a social gesture",
                    "bindings": {"direction": "forward"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                }
            ],
        },
    }


def test_mining_manifest_forbids_automatic_authority() -> None:
    manifest = _manifest()
    validate_mining_manifest(manifest)
    assert manifest["runtime_policy_authority"] is False
    assert manifest["auto_promotion_allowed"] is False
    assert manifest["promotion"]["auto_prompt_edit"] is False


def test_review_is_separate_and_bound_to_immutable_candidate() -> None:
    candidate = _candidate()
    manifest = _manifest()
    validate_candidate(candidate, manifest)
    review = create_review_record(
        candidate,
        decision="approved",
        reviewer="owner",
        rationale="Reproduces the earliest planning boundary.",
        reviewed_at="2026-07-26T12:00:00+00:00",
    )
    validate_review_record(review, candidate)
    assert review["candidate_fingerprint"] == candidate_fingerprint(candidate)
    assert review["regression_promotion_allowed"] is True
    changed = json.loads(json.dumps(candidate))
    changed["description"] = "mutated"
    with pytest.raises(MiningError, match="fingerprint"):
        validate_review_record(review, changed)


def test_candidate_catalog_reports_related_and_historical_recurrence() -> None:
    candidate = _candidate("Please stop looking at me and walk forward.")
    normalized = [
        {
            "id": "historical.walk_not_gaze",
            "datasets": ["historical_regression"],
            "inputs": {"text": "Please stop looking at me and walk forward."},
            "source": {"path": "tests/scenarios/history.json"},
            "legacy_expectations": {},
        }
    ]
    report = build_candidate_catalog([(Path("candidate.json"), candidate)], normalized, _manifest())
    assert report["candidate_count"] == 1
    assert report["candidates"][0]["historical_regression_recurrence"] is True
    assert report["exact_committed_duplicates"]
    assert "wrong_action_class" in report["coverage_gaps"]
    assert report["automatic_promotion_performed"] is False



def test_candidate_catalog_clusters_similar_candidate_inputs() -> None:
    first = _candidate("Walk forward instead of looking at me.")
    second = _candidate("Walk forward instead of looking at me please.")
    second["id"] = "candidate_walk_not_social_2"
    second["review"]["source_episode_id"] = "episode-2"
    report = build_candidate_catalog(
        [(Path("first.json"), first), (Path("second.json"), second)],
        [],
        _manifest(),
    )
    assert report["similarity_clusters"] == [[
        "candidate_walk_not_social",
        "candidate_walk_not_social_2",
    ]]
    assert report["candidate_similarity_edges"]

def test_variation_briefs_do_not_generate_or_promote_scenarios() -> None:
    briefs = build_variation_briefs(
        _candidate(),
        [("language", "zh-CN"), ("politeness", "low")],
        _manifest(),
    )
    assert len(briefs) == 2
    assert all(item["generated_scenario"] is None for item in briefs)
    assert all(item["requires_human_review"] is True for item in briefs)
    assert all(item["runtime_policy_authority"] is False for item in briefs)


def test_approved_candidate_promotes_with_auditable_provenance(tmp_path: Path) -> None:
    candidate = _candidate("A uniquely worded regression request 7139.")
    review = create_review_record(
        candidate,
        decision="approved",
        reviewer="owner",
        rationale="Reviewed deterministic regression boundary.",
        reviewed_at="2026-07-26T12:00:00+00:00",
    )
    candidate_path = tmp_path / "candidate.json"
    review_path = tmp_path / "candidate.review.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    review_path.write_text(json.dumps(review), encoding="utf-8")
    scenario_root = tmp_path / "scenarios"
    target, payload = promote_candidate(
        candidate_path,
        review_path,
        _manifest(),
        scenario_root=scenario_root,
        target_id="reviewed_walk_regression",
    )
    assert target.exists()
    assert payload["provenance"]["source_candidate_id"] == candidate["id"]
    assert payload["provenance"]["review_id"] == review["review_id"]
    assert payload["provenance"]["promotion_auto_applied"] is False
    assert "candidate" not in payload["tags"]
