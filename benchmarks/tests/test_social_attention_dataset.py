from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.inventory.core import load_config
from benchmarks.datasets.social_attention.validate import (
    DatasetValidationError,
    validate_dataset,
)


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "benchmarks/datasets/social_attention/cases.json"
MANIFEST_PATH = ROOT / "benchmarks/manifests/social_attention_v1.json"
SUITES_PATH = ROOT / "benchmarks/manifests/suites.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reviewed_dataset_meets_declared_coverage() -> None:
    report = validate_dataset(
        _load(DATASET_PATH),
        _load(MANIFEST_PATH),
        repo_root=ROOT,
        dataset_path=DATASET_PATH,
    )
    assert report["total"] == 128
    assert set(report["by_cohort"].values()) == {8}
    assert report["by_mode"]["off"] == 8
    assert report["by_mode"]["report_only"] == 8
    assert report["with_explicit_stillness"] >= 8
    assert report["with_recent_auxiliary_evidence"] >= 8


def test_every_case_keeps_none_as_a_valid_decision() -> None:
    dataset = _load(DATASET_PATH)
    assert all(
        "none" in case["acceptable_auxiliary_behavior"]
        for case in dataset["scenarios"]
    )


def test_dataset_normalizes_through_common_contract() -> None:
    normalized = normalize_json_file(
        DATASET_PATH,
        repo_root=ROOT,
        layer="integration",
        datasets=("social_attention",),
        evidence_requirements=("static", "live_model"),
    )
    assert len(normalized) == 128
    assert all(item["datasets"] == ["social_attention"] for item in normalized)
    assert all("none" in item["expectations"]["acceptable_auxiliary"] for item in normalized)


def test_fixed_named_gesture_expectation_is_rejected() -> None:
    dataset = deepcopy(_load(DATASET_PATH))
    dataset["scenarios"][0]["acceptable_auxiliary_behavior"] = [
        "none",
        "soridormi.nod_yes",
    ]
    with pytest.raises(DatasetValidationError, match="fixed action/skill"):
        validate_dataset(dataset, _load(MANIFEST_PATH))


def test_duplicate_input_contract_is_rejected() -> None:
    dataset = deepcopy(_load(DATASET_PATH))
    dataset["scenarios"][1]["inputs"] = deepcopy(dataset["scenarios"][0]["inputs"])
    with pytest.raises(DatasetValidationError, match="duplicate input contract"):
        validate_dataset(dataset, _load(MANIFEST_PATH))


def test_social_attention_source_is_registered_once() -> None:
    _, rules = load_config(SUITES_PATH)
    sources = [item for item in rules if item.name == "social_attention_v1"]
    assert len(sources) == 1
    source = sources[0]
    assert source.path == "benchmarks/datasets/social_attention"
    assert source.glob == "cases.json"
    assert source.layer == "integration"
    assert source.datasets == ("social_attention",)
    assert source.evidence_levels == ("static", "live_model")
