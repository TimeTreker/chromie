from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.adapters.legacy_json import normalize_payload
from benchmarks.adapters.normalize import normalize_inventory
from benchmarks.contracts import (
    ContractError,
    NormalizedScenario,
    OraclePolicy,
    SourceReference,
)


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
        review_rubric={"dimensions": ["primary_outcome"]},
    ).to_dict()
    assert scenario["expectations"]["acceptable_auxiliary"][0] == "none"
    assert scenario["expectations"]["invariants"] == ["primary response is not delayed"]
    assert scenario["oracle_policy"]["mode"] == "hybrid"
    assert scenario["oracle_policy"]["semantic_dimensions"] == ["primary_outcome"]


def test_explicit_deterministic_oracle_keeps_fixture_truth_authoritative() -> None:
    scenario = NormalizedScenario.create(
        id="module.fixture.001",
        layer="module",
        datasets=["goal_interpretation"],
        source=SourceReference(path="fixture.json", adapter="test"),
        inputs={"user_text": "weather"},
        primary_outcomes=["preserved human-readable description"],
        legacy_expectations={"expected_status": "ok"},
        oracle_policy=OraclePolicy.create(
            mode="deterministic",
            deterministic_sources=["legacy_expectations"],
        ),
    ).to_dict()
    assert scenario["oracle_policy"] == {
        "mode": "deterministic",
        "deterministic_sources": ["legacy_expectations"],
        "semantic_dimensions": [],
        "semantic_blocking": True,
    }


def test_oracle_contract_rejects_missing_semantic_dimensions() -> None:
    with pytest.raises(ContractError, match="requires semantic_dimensions"):
        OraclePolicy.create(mode="hybrid", deterministic_sources=["fixture"])


def test_legacy_adapter_rejects_retired_route_expectations() -> None:
    with pytest.raises(ContractError, match="retired route/intent expectations"):
        normalize_payload(
            [{"scenario_id": "goal_interpretation.weather.zh", "user_text": "重庆天气如何？", "expected_route": "tool"}],
            source_path="scenarios/goal_interpretation/weather.json",
            layer="module",
            datasets=["goal_interpretation", "tool_use"],
            evidence_requirements=["replay"],
        )
    with pytest.raises(ContractError, match="retired route/intent expectations"):
        normalize_payload(
            {"cases": [{"name": "greeting", "input": "hello", "expected": {"route": "chat"}}]},
            source_path="scenarios/interaction/greeting.json",
            layer="integration",
            datasets=["interaction"],
        )


def test_legacy_container_and_single_case_are_supported() -> None:
    container = normalize_payload(
        {"cases": [{"name": "greeting", "input": "hello", "expected": {"status": "ok"}}]},
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
        datasets=["goal_interpretation"],
    )[0]["id"]
    second = normalize_payload(
        {"expected": "chat", "input": "hello"},
        source_path="scenarios/goal_interpretation/anonymous.json",
        layer="module",
        datasets=["goal_interpretation"],
    )[0]["id"]
    assert first == second


def test_unrecognized_input_fails_closed() -> None:
    with pytest.raises(ContractError, match="no recognizable input"):
        normalize_payload(
            {"id": "broken", "expected": "anything"},
            source_path="broken.json",
            layer="module",
            datasets=["goal_interpretation"],
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
                "datasets": ["goal_interpretation"],
                "evidence_levels": ["static"],
            }
            for name in ("a", "b")
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate normalized scenario id"):
        normalize_inventory(tmp_path, inventory_path)
