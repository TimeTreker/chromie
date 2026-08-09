from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from urllib import request

import pytest

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import apply_semantic_reviews
from benchmarks.review.consensus import aggregate_semantic_reviews
from benchmarks.review.judge import judge_review_bundle
from benchmarks.review.prompting import render_review_prompt
from benchmarks.review.providers import (
    ReviewerConfiguration,
    ReviewerProfile,
    invoke_reviewer,
)


def _scenario_case(tmp_path: Path) -> tuple[Path, dict, dict]:
    bundle_dir = tmp_path / "bundle"
    artifact_dir = bundle_dir / "artifacts" / "case.001"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "000-events.jsonl"
    artifact.write_text(
        '{"event":"speech","text":"I remembered blue."}\n',
        encoding="utf-8",
    )
    scenario = {
        "scenario_id": "case.001",
        "review_reason": "semantic_adjudication",
        "oracle_policy": {
            "mode": "hybrid",
            "deterministic_sources": ["invariants"],
            "semantic_dimensions": ["intent_understanding"],
            "semantic_blocking": True,
        },
        "scenario": {
            "id": "case.001",
            "inputs": {"turns": ["Remember blue", "What did I say?"]},
            "expectations": {
                "primary_outcomes": ["Recall blue"],
                "acceptable_auxiliary": [],
                "forbidden_behaviors": ["invent another color"],
            },
        },
        "execution_result": {
            "scenario_id": "case.001",
            "status": "review",
            "observations": {"primary_outcome": "I remembered blue."},
            "evaluation": {
                "semantic_review_required": True,
                "deterministic_status": "pass",
            },
        },
        "review_request": {
            "semantic_dimensions": ["intent_understanding"],
            "primary_outcomes": ["Recall blue"],
            "acceptable_auxiliary": [],
            "forbidden_behaviors": ["invent another color"],
            "review_rubric": {},
            "deterministic_boundaries_are_non_overridable": True,
            "judge_meaning_not_exact_wording": True,
        },
        "artifact_inventory": [
            {
                "label": "000-events.jsonl",
                "status": "included",
                "included_path": "case.001/000-events.jsonl",
            }
        ],
    }
    bundle = {
        "schema_version": 1,
        "kind": "chromie_semantic_review_bundle",
        "run": {"revision": "abc123"},
        "scenarios": [scenario],
    }
    (bundle_dir / "review-bundle.json").write_text(
        json.dumps(bundle), encoding="utf-8"
    )
    return bundle_dir, bundle, scenario


def _review(
    reviewer_id: str, verdict: str, *, model_family: str | None = None
) -> dict:
    return {
        "schema_version": 1,
        "reviewer": {
            "kind": "llm",
            "reviewer_id": reviewer_id,
            "model": f"{reviewer_id}-model",
            "model_family": model_family or reviewer_id,
        },
        "reviews": [
            {
                "scenario_id": "case.001",
                "verdict": verdict,
                "rationale": f"{reviewer_id} judged {verdict}",
                "evidence_refs": ["000-events.jsonl"],
                "dimensions": {
                    "intent_understanding": {
                        "verdict": verdict,
                        "rationale": "The response recalls the requested fact.",
                    }
                },
                "findings": [],
                "failure_attribution": {
                    "primary_category": "none" if verdict == "pass" else "unresolved",
                    "model_inference_fault": (
                        "not_supported" if verdict == "pass" else "unresolved"
                    ),
                    "confidence": "high" if verdict == "pass" else "low",
                    "rationale": "The retained output directly satisfies the scenario.",
                    "evidence_refs": ["000-events.jsonl"],
                },
                "likely_root_causes": [],
            }
        ],
    }


def test_reviewer_configuration_rejects_inline_api_secrets() -> None:
    with pytest.raises(ContractError, match="unknown keys: api_key"):
        ReviewerConfiguration.from_mapping(
            {
                "schema_version": 1,
                "reviewers": [
                    {
                        "id": "unsafe",
                        "protocol": "openai_responses",
                        "base_url": "https://api.example/v1",
                        "model": "review-model",
                        "model_family": "openai",
                        "api_key_env": "OPENAI_API_KEY",
                        "api_key": "must-not-be-stored",
                    }
                ],
                "consensus": {
                    "policy": "majority",
                    "minimum_reviewers": 1,
                    "minimum_model_families": 1,
                },
            }
        )


def test_reviewer_configuration_selects_enabled_profiles() -> None:
    config = ReviewerConfiguration.from_mapping(
        {
            "schema_version": 1,
            "reviewers": [
                {
                    "id": "openai",
                    "protocol": "openai_responses",
                    "base_url": "https://api.example/v1",
                    "model": "review-model",
                    "model_family": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                },
                {
                    "id": "disabled",
                    "enabled": False,
                    "protocol": "anthropic_messages",
                    "base_url": "https://api.example/v1",
                    "model": "other-model",
                    "model_family": "anthropic-claude",
                    "api_key_env": "OTHER_API_KEY",
                },
            ],
            "consensus": {
                "policy": "majority",
                "minimum_reviewers": 1,
                "minimum_model_families": 1,
            },
        }
    )
    assert [profile.reviewer_id for profile in config.selected()] == ["openai"]


def test_openai_compatible_provider_uses_key_without_retaining_it() -> None:
    profile = ReviewerProfile(
        reviewer_id="deepseek",
        protocol="openai_chat_completions",
        base_url="https://api.example/v1",
        model="review-model",
        model_family="deepseek",
        api_key_env="REVIEW_KEY",
    )
    captured: dict[str, object] = {}

    def transport(
        outbound: request.Request, timeout_s: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        captured["url"] = outbound.full_url
        captured["authorization"] = outbound.headers.get("Authorization")
        captured["body"] = json.loads((outbound.data or b"{}").decode("utf-8"))
        captured["timeout"] = timeout_s
        response = {
            "model": "returned-model",
            "choices": [{"message": {"content": '{"scenario_id":"case.001"}'}}],
        }
        return 200, {"x-request-id": "req-1"}, json.dumps(response).encode()

    response = invoke_reviewer(
        profile,
        system_prompt="system",
        user_prompt="user",
        environment={"REVIEW_KEY": "secret-value"},
        transport=transport,
    )
    assert captured["url"] == "https://api.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret-value"
    assert response.request_id == "req-1"
    assert response.returned_model == "returned-model"
    assert "secret-value" not in json.dumps(profile.public_metadata())


def test_prompt_capsule_is_provider_neutral_and_contains_retained_evidence(
    tmp_path: Path,
) -> None:
    bundle_dir, bundle, scenario = _scenario_case(tmp_path)
    system, user, metadata = render_review_prompt(
        bundle,
        scenario,
        bundle_dir=bundle_dir,
    )
    assert "independent evaluator" in system
    assert "failed scenario alone is not evidence" in system
    assert "failure_attribution" in user
    assert "I remembered blue" in user
    assert metadata["scenario_id"] == "case.001"
    assert len(metadata["prompt_sha256"]) == 64


def test_majority_consensus_preserves_votes_and_provenance() -> None:
    consensus = aggregate_semantic_reviews(
        [
            _review("openai", "pass"),
            _review("claude", "pass"),
            _review("deepseek", "fail"),
        ],
        policy="majority",
        minimum_reviewers=3,
    )
    result = consensus["reviews"][0]
    assert consensus["reviewer"]["kind"] == "llm_ensemble"
    assert result["verdict"] == "pass"
    assert result["agreement"]["agreement_ratio"] == 2 / 3
    assert len(result["judge_votes"]) == 3


def test_same_model_family_aliases_do_not_satisfy_diversity() -> None:
    consensus = aggregate_semantic_reviews(
        [
            _review("openai-a", "pass", model_family="openai"),
            _review("openai-b", "pass", model_family="openai"),
            _review("claude", "pass", model_family="anthropic-claude"),
        ],
        policy="majority",
        minimum_reviewers=3,
        minimum_model_families=3,
    )
    result = consensus["reviews"][0]
    assert result["verdict"] == "insufficient_evidence"
    assert result["agreement"]["model_family_count"] == 2


def test_unanimous_policy_fails_closed_on_disagreement() -> None:
    consensus = aggregate_semantic_reviews(
        [_review("openai", "pass"), _review("claude", "fail")],
        policy="unanimous",
        minimum_reviewers=2,
    )
    assert consensus["reviews"][0]["verdict"] == "insufficient_evidence"


def test_attribution_consensus_requires_reviewers_to_agree_on_model_fault() -> None:
    agreed = aggregate_semantic_reviews(
        [_review("openai", "pass"), _review("claude", "pass")],
        minimum_reviewers=2,
    )["reviews"][0]["failure_attribution"]
    disputed = aggregate_semantic_reviews(
        [_review("openai", "pass"), _review("claude", "fail")],
        minimum_reviewers=2,
    )["reviews"][0]["failure_attribution"]

    assert agreed["model_inference_fault"] == "not_supported"
    assert agreed["primary_category"] == "none"
    assert disputed["model_inference_fault"] == "unresolved"
    assert disputed["primary_category"] == "mixed"


def test_ensemble_cannot_override_deterministic_failure() -> None:
    report = {
        "schema_version": 1,
        "run": {},
        "summary": {"total": 1, "pass": 0, "fail": 1, "review": 0, "error": 0},
        "results": [
            {
                "scenario_id": "case.001",
                "status": "fail",
                "evaluation": {
                    "semantic_review_required": True,
                    "deterministic_status": "fail",
                },
            }
        ],
        "errors": [],
    }
    ensemble = aggregate_semantic_reviews(
        [_review("openai", "pass"), _review("claude", "pass")],
        minimum_reviewers=2,
    )
    reviewed = apply_semantic_reviews(report, ensemble)
    assert reviewed["results"][0]["status"] == "fail"
    assert reviewed["results"][0]["evaluation"]["semantic_review_effect"] == (
        "diagnostic_only"
    )


def test_judge_dry_run_renders_all_prompts_without_api_keys(tmp_path: Path) -> None:
    bundle_dir, _, _ = _scenario_case(tmp_path)
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "reviewers": [
                    {
                        "id": "openai",
                        "protocol": "openai_responses",
                        "base_url": "https://api.example/v1",
                        "model": "review-model",
                        "model_family": "openai",
                        "api_key_env": "MISSING_KEY",
                    }
                ],
                "consensus": {
                    "policy": "majority",
                    "minimum_reviewers": 1,
                    "minimum_model_families": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "judgments"
    report = judge_review_bundle(
        bundle_path=bundle_dir,
        reviewer_config_path=config_path,
        output_dir=output_dir,
        dry_run=True,
    )
    assert report["dry_run"] is True
    assert report["prompts"][0]["scenario_id"] == "case.001"
    assert (output_dir / "judge-report.json").exists()
