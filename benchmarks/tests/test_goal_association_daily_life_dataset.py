from __future__ import annotations

import asyncio
import json

from benchmarks.datasets.goal_association_daily_life.qualification import (
    _adjudicate_one,
    _capture_repair_call,
    build_transaction,
)
from benchmarks.datasets.goal_association_daily_life.validate import (
    DATASET_ROOT,
    FAMILIES,
    load_cases,
    scenario_paths,
    validate_dataset,
)
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest


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
        "host_accepted": 1_500,
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


def test_clarify_oracles_do_not_claim_an_unproven_gap_resolution() -> None:
    clarify_cases = [
        case for case in load_cases() if case["category"] == "clarify_open_gap"
    ]

    assert len(clarify_cases) == 100
    for case in clarify_cases:
        associations = case["target"]["reference_model_output"]["associations"]
        assert len(associations) == 1
        assert associations[0]["relationship"] == "clarify"
        assert associations[0]["resolved_gap_ids"] == []


def test_goal_association_qualification_replays_hidden_mixed_oracle() -> None:
    case = next(
        item
        for item in load_cases()
        if item["category"] == "mixed_continue_and_new_contract_gap"
    )
    transaction = asyncio.run(build_transaction(case))
    result = asyncio.run(
        _adjudicate_one(
            case,
            json.dumps(case["target"]["reference_model_output"]),
            None,
            transaction["response_schema"],
        )
    )

    assert transaction["production_prompt_family"] == "goal_association.primary"
    assert result["hard_pass"] is True
    assert result["strict_pass"] is True
    assert [item["operation"] for item in result["observed_responsibility_map"]] == [
        "association",
        "new_goal",
    ]


def test_goal_association_qualification_captures_only_permitted_repair() -> None:
    case = next(
        item
        for item in load_cases()
        if item["category"] == "mixed_continue_and_new_contract_gap"
    )
    raw = dict(case["target"]["reference_model_output"])
    raw["decision"] = "associate"

    repair = asyncio.run(
        _capture_repair_call(
            request=CognitiveWorkRequest.model_validate(case["input"]["request"]),
            primary_raw=json.dumps(raw),
        )
    )

    assert repair is not None
    assert "mechanically malformed" in repair["user_prompt"]
    assert "reinterpret" in repair["system_prompt"]
