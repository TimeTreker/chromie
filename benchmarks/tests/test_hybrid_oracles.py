from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import apply_semantic_reviews
from benchmarks.review.bundle import build_review_bundle, write_review_bundle


def _scenario(mode: str = "hybrid") -> dict:
    deterministic = ["invariants"] if mode in {"deterministic", "hybrid"} else []
    semantic = ["intent_understanding"] if mode in {"semantic_review", "hybrid"} else []
    return {
        "schema_version": 1,
        "id": "case.001",
        "layer": "e2e",
        "datasets": ["daily_conversation"],
        "source": {
            "path": "case.json",
            "adapter": "test",
            "source_index": None,
            "source_id": "case.001",
        },
        "inputs": {"user_text": "Tell me what you understood."},
        "context": {},
        "capabilities": [],
        "expectations": {
            "primary_outcomes": ["Respond to the latest intent"],
            "acceptable_auxiliary": ["none"],
            "forbidden_behaviors": [],
            "invariants": ["no stale speech"] if deterministic else [],
            "distribution_observations": [],
        },
        "evidence_requirements": ["live_service"],
        "review_rubric": {
            "dimensions": semantic,
            "guidance": ["Judge meaning, not exact wording."],
        },
        "legacy_expectations": {},
        "oracle_policy": {
            "mode": mode,
            "deterministic_sources": deterministic,
            "semantic_dimensions": semantic,
            "semantic_blocking": True,
        },
    }


def _result(*, status: str = "review", deterministic_status: str = "pass") -> dict:
    return {
        "schema_version": 1,
        "scenario_id": "case.001",
        "status": status,
        "run": {"mode": "live_model", "evidence_level": "live_service"},
        "observations": {
            "primary_task_passed": None,
            "primary_outcome": "I understood the latest request.",
            "behaviors": [],
            "evidence": [{"turn_id": "turn-1"}],
        },
        "evaluation": {
            "semantic_review_required": True,
            "forbidden_behavior_hits": [],
            "oracle_policy": _scenario()["oracle_policy"],
            "deterministic_status": deterministic_status,
            "semantic_review_status": "pending",
        },
        "invariant_results": [
            {
                "name": "no stale speech",
                "passed": deterministic_status == "pass",
                "detail": None,
            }
        ],
        "artifacts": ["events.jsonl"],
    }


def _suite(result: dict) -> dict:
    return {
        "schema_version": 1,
        "run": {"mode": "live_model", "evidence_level": "live_service"},
        "summary": {
            "total": 1,
            "pass": int(result["status"] == "pass"),
            "fail": int(result["status"] == "fail"),
            "review": int(result["status"] == "review"),
            "error": 0,
        },
        "results": [result],
        "errors": [],
    }


def _review(verdict: str) -> dict:
    return {
        "schema_version": 1,
        "reviewer": {"kind": "llm", "model": "review-model"},
        "reviews": [
            {
                "scenario_id": "case.001",
                "verdict": verdict,
                "rationale": "The answer addresses the newest user intent.",
                "evidence_refs": ["turn-1"],
                "dimensions": {
                    "intent_understanding": {
                        "verdict": "pass",
                        "rationale": "Directly responsive.",
                    }
                },
            }
        ],
    }


def test_review_bundle_preserves_scenario_result_and_non_override_rule() -> None:
    bundle = build_review_bundle(
        {"schema_version": 1, "cases": [_scenario()]},
        _suite(_result()),
    )
    assert bundle["kind"] == "chromie_semantic_review_bundle"
    assert bundle["scenarios"][0]["review_request"][
        "deterministic_boundaries_are_non_overridable"
    ] is True
    assert bundle["scenarios"][0]["review_request"]["semantic_dimensions"] == [
        "intent_understanding"
    ]


def test_review_bundle_copies_declared_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    (artifact_root / "events.jsonl").write_text("{}\n", encoding="utf-8")
    normalized = tmp_path / "normalized.json"
    report = tmp_path / "report.json"
    normalized.write_text(
        json.dumps({"schema_version": 1, "cases": [_scenario()]}),
        encoding="utf-8",
    )
    report.write_text(json.dumps(_suite(_result())), encoding="utf-8")
    output = tmp_path / "bundle"
    bundle = write_review_bundle(
        normalized_path=normalized,
        report_path=report,
        output_dir=output,
        artifact_root=artifact_root,
    )
    inventory = bundle["scenarios"][0]["artifact_inventory"]
    assert inventory[0]["status"] == "included"
    assert (output / "review-bundle.json").exists()


def test_semantic_pass_adjudicates_pending_result() -> None:
    reviewed = apply_semantic_reviews(_suite(_result()), _review("pass"))
    assert reviewed["results"][0]["status"] == "pass"
    assert reviewed["summary"] == {
        "total": 1,
        "pass": 1,
        "fail": 0,
        "review": 0,
        "error": 0,
    }


def test_partial_semantic_review_remains_review() -> None:
    reviewed = apply_semantic_reviews(_suite(_result()), _review("partial"))
    assert reviewed["results"][0]["status"] == "review"
    assert reviewed["results"][0]["evaluation"]["semantic_review_effect"] == (
        "requires_follow_up"
    )


def test_semantic_review_cannot_override_deterministic_failure() -> None:
    reviewed = apply_semantic_reviews(
        _suite(_result(status="fail", deterministic_status="fail")),
        _review("pass"),
    )
    assert reviewed["results"][0]["status"] == "fail"
    assert reviewed["results"][0]["evaluation"]["semantic_review_effect"] == (
        "diagnostic_only"
    )


def test_review_for_deterministic_only_scenario_fails_closed() -> None:
    result = _result(status="pass")
    result["evaluation"]["semantic_review_required"] = False
    with pytest.raises(ContractError, match="deterministic-only"):
        apply_semantic_reviews(_suite(result), _review("pass"))
