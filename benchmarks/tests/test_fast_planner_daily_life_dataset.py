from __future__ import annotations

import json

from benchmarks.datasets.fast_planner_daily_life.qualification import (
    DATASET_ROOT,
    PRODUCTION_TRANSACTION_FILES,
    production_source_identity,
    scenario_paths,
    validate_dataset,
)


def test_fast_planner_daily_life_corpus_is_complete_and_mechanically_valid() -> None:
    assert len(scenario_paths()) == 1_500
    summary = validate_dataset()

    assert summary["scenario_count"] == 1_500
    assert summary["contrast_set_count"] == 150
    assert summary["validated"] == 1_500
    assert summary["languages"] == {"en-US": 750, "zh-CN": 750}
    assert summary["splits"] == {
        "frozen_test": 250,
        "train_candidate": 1_000,
        "validation": 250,
    }
    assert summary["runtime_variants"] == {
        "canonical_primary": 500,
        "canonical_reentry": 500,
        "streaming_advance": 500,
    }
    assert len(summary["categories"]) == 15
    assert set(summary["categories"].values()) == {100}


def test_fast_planner_daily_life_stores_one_scenario_per_file() -> None:
    paths = scenario_paths()

    assert len(paths) == 1_500
    assert len({path.resolve() for path in paths}) == 1_500
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == payload["id"]
        assert path.parent.name == payload["category"]
        assert path.parent.parent.name == payload["split"]
        assert "target" not in payload["input"]
        assert payload["review"]["review_status"] == (
            "mechanically_validated_dataset_candidate"
        )
        assert payload["review"]["author_model"] == "gpt-5.6-sol"
        assert payload["review"]["training_eligible"] is False
        assert payload["review"]["independent_semantic_review"] is False


def test_fast_planner_daily_life_manifest_matches_file_tree() -> None:
    manifest = json.loads((DATASET_ROOT / "dataset.json").read_text(encoding="utf-8"))

    assert manifest["coverage_contract"]["scenario_count"] == len(scenario_paths())
    assert manifest["coverage_contract"]["contrast_set_count"] == 150
    assert manifest["coverage_contract"]["scenarios_per_contrast_set"] == 10
    assert manifest["asset_contract"]["path_pattern"] == (
        "scenarios/<split>/<category>/<scenario-id>.json"
    )
    assert manifest["coverage_contract"]["training_eligible"] is False
    assert manifest["coverage_contract"]["independent_semantic_review"] is False


def test_fast_planner_source_identity_covers_the_production_transaction() -> None:
    identity = production_source_identity()

    assert len(identity["production_files"]) == len(PRODUCTION_TRANSACTION_FILES)
    assert len(identity["production_files_sha256"]) == 64
    assert len(identity["production_tracked_diff_sha256"]) == 64
    assert identity["git_revision"]
