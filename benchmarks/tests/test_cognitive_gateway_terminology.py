from __future__ import annotations

import json
from pathlib import Path

from benchmarks.runtime_adapters.profiles import COMPONENT_PROFILES


ROOT = Path(__file__).resolve().parents[2]


def test_cognitive_gateway_is_the_ingress_component_profile() -> None:
    assert "cognitive_gateway" in COMPONENT_PROFILES
    assert "router" not in COMPONENT_PROFILES
    profile = COMPONENT_PROFILES["cognitive_gateway"]
    assert profile.url_env == "CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_URL"
    assert profile.callable_env == "CHROMIE_BENCHMARK_COGNITIVE_GATEWAY_CALLABLE"


def test_runtime_adapter_manifest_uses_gateway_terminology() -> None:
    payload = json.loads(
        (ROOT / "benchmarks/manifests/runtime_adapters.json").read_text(encoding="utf-8")
    )
    names = {item["name"] for item in payload["components"]}
    assert "cognitive_gateway" in names
    assert "router" not in names


def test_legacy_router_paths_are_explicit_regressions() -> None:
    payload = json.loads(
        (ROOT / "benchmarks/manifests/suites.json").read_text(encoding="utf-8")
    )
    by_path = {item["path"]: item for item in payload["sources"]}
    for path in ("scenarios/goal_interpretation", "scenarios/cognitive_core_dialogue"):
        source = by_path[path]
        assert source["layer"] == "regression"
        assert "historical_regression" in source["datasets"]
        assert any(tag.startswith("compatibility_router") for tag in source["datasets"])
