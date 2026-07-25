from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.adapters.legacy_json import normalize_payload
from benchmarks.adapters.normalize import normalize_inventory
from benchmarks.contracts import ContractError, NormalizedScenario, SourceReference


def test_common_contract_keeps_behavior_regions_separate() -> None:
    scenario = NormalizedScenario.create(
        id="social.greeting.001",
        layer="integration",
        datasets=["social_attention"],
        source=SourceReference(path="scenario.json", adapter="test"),
        inputs={"user_text": "Hello"},
        primary_outcomes=["Acknowledge the greeting naturally"],
        acceptable_auxiliary=["none", "one subtle greeting-compatible cue"],
        forbidden_behaviors=["locomotion", "repeated auxiliary behavior"],
        invariants=["primary response is not delayed"],
        distribution_observations=["record auxiliary selection"],
    ).to_dict()
    assert scenario["expectations"]["acceptable_auxiliary"][0] == "none"
    assert scenario["expectations"]["invariants"] == ["primary response is not delayed"]


def test_legacy_list_preserves_declared_id_and_expectation() -> None:
    cases = normalize_payload(
        [{"scenario_id": "router.weather.zh", "user_text": "重庆天气如何？", "expected_route": "tool"}],
        source_path="scenarios/goal_interpretation/weather.json",
        layer="module",
        datasets=["router", "tool_use"],
        evidence_requirements=["replay"],
    )
    assert cases[0]["id"] == "router.weather.zh"
    assert cases[0]["inputs"] == {"user_text": "重庆天气如何？"}
    assert cases[0]["legacy_expectations"]["expected_route"] == "tool"
    assert cases[0]["source"]["source_id"] == "router.weather.zh"


def test_legacy_container_and_single_case_are_supported() -> None:
    container = normalize_payload(
        {"cases": [{"name": "greeting", "input": "hello", "expected": {"route": "chat"}}]},
        source_path="scenarios/interaction/greeting.json",
        layer="integration",
        datasets=["interaction"],
    )
    single = normalize_payload(
        {"case_id": "stop", "request": "stop now", "invariants": ["stop has priority"]},
        source_path="tests/scenarios/stop.json",
        layer="regression",
        datasets=["safety"],
    )
    assert container[0]["id"] == "greeting"
    assert single[0]["expectations"]["invariants"] == ["stop has priority"]


def test_stable_derived_id_does_not_depend_on_key_order() -> None:
    first = normalize_payload(
        {"input": "hello", "expected": "chat"},
        source_path="scenarios/goal_interpretation/anonymous.json",
        layer="module",
        datasets=["router"],
    )[0]["id"]
    second = normalize_payload(
        {"expected": "chat", "input": "hello"},
        source_path="scenarios/goal_interpretation/anonymous.json",
        layer="module",
        datasets=["router"],
    )[0]["id"]
    assert first == second


def test_unrecognized_input_fails_closed() -> None:
    with pytest.raises(ContractError, match="no recognizable input"):
        normalize_payload(
            {"id": "broken", "expected": "anything"},
            source_path="broken.json",
            layer="module",
            datasets=["router"],
        )


def test_inventory_normalization_detects_duplicate_normalized_ids(tmp_path: Path) -> None:
    (tmp_path / "scenarios").mkdir()
    for name in ("a", "b"):
        (tmp_path / "scenarios" / f"{name}.json").write_text(
            json.dumps({"id": "duplicate", "input": name, "expected": "chat"}), encoding="utf-8"
        )
    inventory = {
        "schema_version": 1,
        "scenarios": [
            {
                "source_path": f"scenarios/{name}.json",
                "source_kind": "scenario_file",
                "layer": "module",
                "datasets": ["router"],
                "evidence_levels": ["static"],
            }
            for name in ("a", "b")
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate normalized scenario id"):
        normalize_inventory(tmp_path, inventory_path)
