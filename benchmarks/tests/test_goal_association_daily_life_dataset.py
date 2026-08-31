from __future__ import annotations

import json

from benchmarks.datasets.goal_association_daily_life.validate import (
    DATASET_ROOT,
    FAMILIES,
    scenario_paths,
    validate_dataset,
)


def test_goal_association_daily_life_corpus_is_complete_and_mechanically_valid() -> None:
    assert len(scenario_paths()) == 1_500
    summary = validate_dataset()

    assert summary["scenario_count"] == 1_500
    assert summary["languages"] == {"en-US": 750, "zh-CN": 750}
    assert summary["splits"] == {
        "frozen_test": 450,
        "train_candidate": 600,
        "validation": 450,
    }
    assert summary["runtime"] == {
        "host_accepted": 1_400,
        "known_contract_gaps": 100,
        "validated": 1_500,
    }
    assert set(summary["categories"]) == set(FAMILIES)
    assert set(summary["categories"].values()) == {100}


def test_goal_association_daily_life_stores_one_scenario_per_file() -> None:
    paths = scenario_paths()

    assert len(paths) == 1_500
    assert len({path.resolve() for path in paths}) == 1_500
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert path.stem == payload["id"]
        assert path.parent.name == payload["category"]
        assert path.parent.parent.name == payload["split"]
        assert "scenarios" not in payload
        assert payload["review"]["training_eligible"] is False
        assert payload["review"]["independent_semantic_review"] is False


def test_goal_association_daily_life_manifest_matches_file_tree() -> None:
    manifest = json.loads((DATASET_ROOT / "dataset.json").read_text(encoding="utf-8"))

    assert manifest["coverage_contract"]["scenario_count"] == len(scenario_paths())
    assert manifest["asset_contract"]["path_pattern"] == (
        "scenarios/<split>/<category>/<scenario-id>.json"
    )
    assert manifest["asset_contract"]["contrast_set_size"] == len(FAMILIES)
    assert manifest["coverage_contract"]["training_eligible"] is False
