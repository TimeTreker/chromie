from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from benchmarks.adapters.normalize import normalize_config
from benchmarks.inventory.core import build_inventory


class MigrationError(ValueError):
    """Raised when maintained scenario migration metadata loses parity."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MigrationError(f"{path} must contain a JSON object")
    return payload


def load_migration_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != 1:
        raise MigrationError("scenario migration manifest schema_version must be 1")
    if payload.get("manifest_id") != "chromie.scenario_migration.v1":
        raise MigrationError("unexpected scenario migration manifest id")
    if payload.get("authority") != "benchmark_suite":
        raise MigrationError("Benchmark Suite must own scenario source classification")
    if payload.get("source_strategy") != "referenced_in_place":
        raise MigrationError("maintained scenario sources must use referenced_in_place migration")
    if payload.get("runtime_policy_authority") is not False:
        raise MigrationError("scenario migration metadata cannot own Runtime policy")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise MigrationError("scenario migration manifest must declare sources")
    compatibility = payload.get("compatibility_entrypoints")
    if not isinstance(compatibility, list) or not compatibility:
        raise MigrationError("compatibility entrypoints must have explicit removal schedules")
    for item in compatibility:
        if not isinstance(item, Mapping):
            raise MigrationError("compatibility entrypoint must be an object")
        schedule = item.get("removal_schedule")
        if not isinstance(schedule, Mapping) or not schedule.get("earliest_after"):
            raise MigrationError(f"{item.get('path')}: missing removal schedule")
        gates = schedule.get("required_gates")
        if not isinstance(gates, list) or not gates:
            raise MigrationError(f"{item.get('path')}: missing compatibility removal gates")
    return payload


def build_migration_report(
    repo_root: Path,
    manifest_path: Path,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    manifest = load_migration_manifest(manifest_path)
    config_path = config_path or repo_root / "benchmarks/manifests/suites.json"
    inventory = build_inventory(repo_root, config_path)
    normalized = normalize_config(repo_root, config_path)
    counts = Counter(
        str(item.get("provenance", {}).get("inventory_rule") or "")
        for item in inventory["scenarios"]
    )
    source_reports: list[dict[str, Any]] = []
    errors: list[str] = []
    declared_names: set[str] = set()
    for source in manifest["sources"]:
        if not isinstance(source, Mapping):
            errors.append("scenario source entry must be an object")
            continue
        name = str(source.get("name") or "")
        declared_names.add(name)
        path = str(source.get("path") or "")
        optional = bool(source.get("optional", False))
        exists = (repo_root / path).exists()
        expected = source.get("expected_inventory_count")
        actual = counts.get(name, 0)
        if not exists and not optional:
            errors.append(f"{name}: missing maintained source {path}")
        if expected is not None and actual != expected:
            errors.append(f"{name}: inventory count {actual} != expected {expected}")
        if source.get("migration_state") != "referenced_in_place":
            errors.append(f"{name}: source is not referenced_in_place")
        if not str(source.get("target_reference") or "").strip():
            errors.append(f"{name}: missing target Benchmark reference")
        source_reports.append(
            {
                "name": name,
                "source_path": path,
                "target_reference": source.get("target_reference"),
                "inventory_count": actual,
                "expected_inventory_count": expected,
                "optional": optional,
                "exists": exists,
            }
        )
    unexpected = sorted(set(counts) - declared_names)
    if unexpected:
        errors.append(f"inventory contains undeclared migration sources: {unexpected}")
    inventory_total = len(inventory["scenarios"])
    normalized_total = len(normalized["cases"])
    if inventory_total != int(manifest.get("expected_inventory_total", -1)):
        errors.append(
            f"inventory total {inventory_total} != expected {manifest.get('expected_inventory_total')}"
        )
    if normalized_total != int(manifest.get("expected_normalized_total", -1)):
        errors.append(
            f"normalized total {normalized_total} != expected {manifest.get('expected_normalized_total')}"
        )
    if errors:
        raise MigrationError("scenario migration parity failed:\n" + "\n".join(sorted(errors)))
    return {
        "schema_version": 1,
        "manifest_id": manifest["manifest_id"],
        "status": "pass",
        "source_strategy": manifest["source_strategy"],
        "inventory_total": inventory_total,
        "normalized_total": normalized_total,
        "source_counts": dict(sorted(counts.items())),
        "sources": source_reports,
        "compatibility_entrypoints": manifest["compatibility_entrypoints"],
        "release_claims_changed": False,
        "runtime_policy_authority": False,
    }
