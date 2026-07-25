from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.inventory.core import InventoryError, build_inventory, coverage, validate_inventory


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    _write(tmp_path / "scenarios/goal_interpretation/cases.json", [{"id": "route.greeting", "input": "Hello"}, {"id": "route.zh", "input": "你好"}])
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/general_ability_acceptance.py").write_text("# entrypoint\n", encoding="utf-8")
    config = {
        "schema_version": 1, "benchmark_version": "1.0", "allowed_datasets": ["router", "general_ability"],
        "sources": [
            {"name": "router", "path": "scenarios/goal_interpretation", "glob": "**/*.json", "layer": "module", "datasets": ["router"], "evidence_levels": ["static"]},
            {"name": "general", "path": "scripts/general_ability_acceptance.py", "kind": "acceptance_entrypoint", "layer": "e2e", "datasets": ["general_ability"], "evidence_levels": ["live_service"]}
        ]
    }
    config_path = tmp_path / "benchmarks/manifests/suites.json"
    _write(config_path, config)
    return tmp_path, config_path


def test_inventory_is_deterministic_and_classified(tmp_path: Path) -> None:
    root, config = _repo(tmp_path)
    first = build_inventory(root, config)
    second = build_inventory(root, config)
    assert first == second
    assert [item["id"] for item in first["scenarios"]] == ["entrypoint.general", "route.greeting", "route.zh"]
    assert coverage(first)["by_layer"] == {"e2e": 1, "module": 2}


def test_duplicate_ids_fail_closed(tmp_path: Path) -> None:
    root, config = _repo(tmp_path)
    _write(root / "scenarios/goal_interpretation/duplicate.json", {"id": "route.greeting"})
    with pytest.raises(InventoryError, match="duplicate scenario ID"):
        build_inventory(root, config)


def test_unknown_dataset_is_rejected(tmp_path: Path) -> None:
    root, config = _repo(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["sources"][0]["datasets"] = ["not_declared"]
    _write(config, payload)
    with pytest.raises(InventoryError, match="unknown datasets"):
        build_inventory(root, config)


def test_missing_required_source_is_rejected(tmp_path: Path) -> None:
    root, config = _repo(tmp_path)
    (root / "scripts/general_ability_acceptance.py").unlink()
    with pytest.raises(InventoryError, match="missing source path"):
        build_inventory(root, config)


def test_broken_inventory_reference_is_rejected(tmp_path: Path) -> None:
    root, config = _repo(tmp_path)
    inventory = build_inventory(root, config)
    inventory["scenarios"][0]["source_path"] = "missing.json"
    with pytest.raises(InventoryError, match="broken source reference"):
        validate_inventory(root, inventory, {"router", "general_ability"})
