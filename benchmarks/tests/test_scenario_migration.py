from __future__ import annotations

import json
from pathlib import Path

from benchmarks.inventory.core import build_inventory
from benchmarks.scenarios.catalog import build_migration_report, load_migration_manifest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "benchmarks/manifests/scenario_migration_v1.json"
SUITES = ROOT / "benchmarks/manifests/suites.json"


def test_suites_manifest_is_a_single_authority_redirect() -> None:
    payload = json.loads(SUITES.read_text(encoding="utf-8"))
    assert payload["source_manifest"] == "benchmarks/manifests/scenario_migration_v1.json"
    assert payload["deprecated_inline_sources"] is True
    assert "sources" not in payload


def test_migration_manifest_reconciles_inventory_and_normalized_counts() -> None:
    report = build_migration_report(ROOT, MIGRATION)
    assert report["status"] == "pass"
    manifest = load_migration_manifest(MIGRATION)
    assert report["inventory_total"] == manifest["expected_inventory_total"]
    assert report["normalized_total"] == manifest["expected_normalized_total"]
    assert report["runtime_policy_authority"] is False
    assert report["release_claims_changed"] is False
    assert report["source_counts"]["social_attention_v1"] == 128
    assert report["source_counts"]["daily_conversation_v1"] == 150


def test_every_compatibility_entrypoint_has_a_removal_schedule() -> None:
    manifest = load_migration_manifest(MIGRATION)
    for entrypoint in manifest["compatibility_entrypoints"]:
        schedule = entrypoint["removal_schedule"]
        assert schedule["earliest_after"]
        assert schedule["required_gates"]
        assert entrypoint["replacement"]


def test_inventory_still_uses_stable_source_ids_through_redirect() -> None:
    inventory = build_inventory(ROOT, SUITES)
    ids = {item["id"] for item in inventory["scenarios"]}
    assert "sa.v1.greetings_farewells.direct_hello" in ids
    assert len(ids) == len(inventory["scenarios"])
