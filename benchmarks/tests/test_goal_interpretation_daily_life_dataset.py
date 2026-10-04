from __future__ import annotations

import copy
import json

import pytest

from benchmarks.datasets.goal_interpretation_daily_life.validate import (
    DATASET_ROOT,
    _validate_case_shape,
    scenario_paths,
    scenario_tree_digest,
    validate_dataset,
)


def test_goal_interpretation_daily_life_dataset_passes_current_contract() -> None:
    summary = validate_dataset()

    assert summary["dataset_id"] == "chromie.goal_interpretation_daily_life.v1"
    assert summary["scenario_count"] == 1496
    assert summary["contrast_set_count"] == 374
    assert summary["dynamic_schema_passed"] == 1496
    assert summary["host_validation_passed"] == 1496
    assert summary["known_host_validation_gaps"] == 0
    assert summary["languages"] == {"en-US": 748, "zh-CN": 748}
    assert summary["splits"] == {
        "frozen_test": 380,
        "train_candidate": 896,
        "validation": 220,
    }
    assert summary["independent_semantic_review"] is False
    assert summary["training_eligible"] is False
    assert set(summary["binding_dimensions"]) == {
        "actor",
        "addressee",
        "attribute",
        "comparison",
        "count",
        "direction",
        "distance",
        "duration",
        "entity",
        "experiencer",
        "intensity",
        "item",
        "location",
        "magnitude",
        "polarity",
        "preference",
        "prior_assistant_utterance",
        "proposition",
        "quantity",
        "recipient",
        "severity",
        "speed",
        "subtype",
        "threshold",
        "time",
        "time_scope",
    }
    assert set(summary["output_modes"]) == {
        "body_action",
        "humming",
        "information",
        "media_playback",
        "nonverbal_vocalization",
        "recitation",
        "singing",
        "speech",
        "stateful_effect",
        "styled_speech",
    }
    assert summary["context_scenarios"] == 306
    assert summary["unresolved_scenarios"] == 68
    assert summary["digit_measurement_surface_bindings"] == 406


def test_goal_interpretation_daily_life_stores_one_scenario_per_file() -> None:
    paths = scenario_paths()

    assert len(paths) == 1496
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert path.stem == payload["id"]
        assert path.parent.name == payload["category"]
        assert path.parent.parent.name == payload["split"]
        assert "scenarios" not in payload
        assert payload["review"]["training_eligible"] is False
        assert payload["review"]["independent_semantic_review"] is False


def test_goal_interpretation_daily_life_manifest_matches_file_tree() -> None:
    manifest = json.loads((DATASET_ROOT / "dataset.json").read_text(encoding="utf-8"))

    assert manifest["coverage_contract"]["scenario_count"] == len(scenario_paths())
    assert manifest["coverage_contract"]["scenarios_per_contrast_set"] == 4
    assert manifest["split_policy"]["cross_split_contrast_sets_allowed"] is False
    assert manifest["authoring"]["training_eligible"] is False
    assert manifest["asset_contract"]["scenario_tree_sha256"] == scenario_tree_digest()


def test_body_effect_reference_cannot_disagree_with_its_semantic_expectation() -> None:
    path = next(path for path in scenario_paths() if "compound" in path.name)
    original = json.loads(path.read_text(encoding="utf-8"))
    case = copy.deepcopy(original)
    body_index = next(
        index
        for index, item in enumerate(case["target"]["reference_wire_output"]["responsibilities"])
        if item["output_mode"] == "body_action"
    )
    case["target"]["semantic_expectations"]["responsibilities"][body_index]["body_effect_family"] = "gaze_or_orientation"

    with pytest.raises(ValueError, match="body_effect_family expectation drift"):
        _validate_case_shape(path, case)

    _validate_case_shape(path, original)
