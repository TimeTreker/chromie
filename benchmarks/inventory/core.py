from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

LAYERS = {"module", "integration", "e2e", "stress", "regression"}
LANGUAGES = {"en", "zh", "mixed", "unknown"}
EVIDENCE_LEVELS = {"static", "replay", "live_model", "live_service", "simulated", "physical", "unknown"}
ID_KEYS = ("id", "scenario_id", "case_id", "name")


class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRule:
    name: str
    path: str
    layer: str
    datasets: tuple[str, ...]
    evidence_levels: tuple[str, ...]
    glob: str = "**/*.json"
    kind: str = "scenario_file"
    optional: bool = False


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read JSON {path}: {exc}") from exc


def load_config(path: Path) -> tuple[dict[str, Any], list[SourceRule]]:
    raw = _load_json(path)
    if raw.get("schema_version") != 1:
        raise InventoryError("suites manifest schema_version must be 1")
    allowed = set(raw.get("allowed_datasets", []))
    if not allowed:
        raise InventoryError("allowed_datasets must not be empty")
    rules: list[SourceRule] = []
    for item in raw.get("sources", []):
        rule = SourceRule(
            name=item["name"], path=item["path"], layer=item["layer"],
            datasets=tuple(item["datasets"]), evidence_levels=tuple(item["evidence_levels"]),
            glob=item.get("glob", "**/*.json"), kind=item.get("kind", "scenario_file"),
            optional=bool(item.get("optional", False)),
        )
        if rule.layer not in LAYERS:
            raise InventoryError(f"unknown layer {rule.layer!r} in rule {rule.name}")
        unknown = set(rule.datasets) - allowed
        if unknown:
            raise InventoryError(f"unknown datasets in rule {rule.name}: {sorted(unknown)}")
        if not set(rule.evidence_levels) <= EVIDENCE_LEVELS:
            raise InventoryError(f"unknown evidence level in rule {rule.name}")
        rules.append(rule)
    return raw, rules


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not value:
        raise InventoryError("scenario ID cannot be normalized")
    return value


def _declared_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ID_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _language(payload: Any) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False)
    has_zh = bool(re.search(r"[\u3400-\u9fff]", text))
    has_en = bool(re.search(r"[A-Za-z]", text))
    if has_zh and has_en:
        return ["mixed"]
    if has_zh:
        return ["zh"]
    if has_en:
        return ["en"]
    return ["unknown"]


def _scenario_payloads(payload: Any) -> Iterable[tuple[int | None, Any]]:
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            yield index, item
        return
    if isinstance(payload, dict):
        for key in ("scenarios", "cases", "tests"):
            value = payload.get(key)
            if isinstance(value, list):
                for index, item in enumerate(value):
                    yield index, item
                return
    yield None, payload


def build_inventory(repo_root: Path, config_path: Path) -> dict[str, Any]:
    config, rules = load_config(config_path)
    scenarios: list[dict[str, Any]] = []
    for rule in rules:
        target = repo_root / rule.path
        if rule.kind == "acceptance_entrypoint":
            if not target.is_file():
                if rule.optional:
                    continue
                raise InventoryError(f"missing source path: {rule.path}")
            scenarios.append({
                "id": _slug(f"entrypoint.{rule.name}"), "source_path": rule.path,
                "source_kind": rule.kind, "layer": rule.layer, "datasets": list(rule.datasets),
                "languages": ["unknown"], "evidence_levels": list(rule.evidence_levels),
                "provenance": {"inventory_rule": rule.name, "declared_id": None},
            })
            continue
        if not target.is_dir():
            if rule.optional:
                continue
            raise InventoryError(f"missing source path: {rule.path}")
        files = sorted(path for path in target.glob(rule.glob) if path.is_file())
        for path in files:
            payload = _load_json(path)
            relative = path.relative_to(repo_root).as_posix()
            payloads = list(_scenario_payloads(payload))
            for index, item in payloads:
                declared = _declared_id(item)
                fallback = path.relative_to(target).with_suffix("").as_posix().replace("/", ".")
                suffix = f".{index + 1}" if index is not None else ""
                scenario_id = _slug(declared or f"{rule.name}.{fallback}{suffix}")
                scenarios.append({
                    "id": scenario_id, "source_path": relative, "source_kind": rule.kind,
                    "layer": rule.layer, "datasets": list(rule.datasets),
                    "languages": _language(item), "evidence_levels": list(rule.evidence_levels),
                    "provenance": {"inventory_rule": rule.name, "declared_id": declared},
                })
    scenarios.sort(key=lambda item: (item["id"], item["source_path"]))
    inventory = {
        "schema_version": 1, "benchmark_version": config["benchmark_version"],
        "generated_from": config_path.relative_to(repo_root).as_posix(), "scenarios": scenarios,
    }
    validate_inventory(repo_root, inventory, set(config["allowed_datasets"]))
    return inventory


def validate_inventory(repo_root: Path, inventory: dict[str, Any], allowed_datasets: set[str]) -> None:
    if inventory.get("schema_version") != 1:
        raise InventoryError("inventory schema_version must be 1")
    seen: dict[str, str] = {}
    for scenario in inventory.get("scenarios", []):
        scenario_id = scenario.get("id")
        source_path = scenario.get("source_path")
        if not isinstance(scenario_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", scenario_id):
            raise InventoryError(f"invalid scenario ID: {scenario_id!r}")
        if scenario_id in seen:
            raise InventoryError(f"duplicate scenario ID {scenario_id!r}: {seen[scenario_id]} and {source_path}")
        seen[scenario_id] = source_path
        if scenario.get("layer") not in LAYERS:
            raise InventoryError(f"invalid layer for {scenario_id}")
        if not set(scenario.get("datasets", [])) or not set(scenario["datasets"]) <= allowed_datasets:
            raise InventoryError(f"invalid datasets for {scenario_id}")
        if not set(scenario.get("languages", [])) <= LANGUAGES:
            raise InventoryError(f"invalid languages for {scenario_id}")
        if not set(scenario.get("evidence_levels", [])) <= EVIDENCE_LEVELS:
            raise InventoryError(f"invalid evidence levels for {scenario_id}")
        if not isinstance(source_path, str) or not (repo_root / source_path).exists():
            raise InventoryError(f"broken source reference for {scenario_id}: {source_path}")
        provenance = scenario.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("inventory_rule"):
            raise InventoryError(f"missing provenance for {scenario_id}")


def coverage(inventory: dict[str, Any]) -> dict[str, dict[str, int] | int]:
    scenarios = inventory["scenarios"]
    def count_values(key: str) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for item in scenarios:
            values = item[key] if isinstance(item[key], list) else [item[key]]
            counter.update(values)
        return dict(sorted(counter.items()))
    return {
        "total": len(scenarios), "by_layer": count_values("layer"),
        "by_dataset": count_values("datasets"), "by_language": count_values("languages"),
        "by_evidence_level": count_values("evidence_levels"),
        "by_source": dict(sorted(Counter(item["provenance"]["inventory_rule"] for item in scenarios).items())),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate the Chromie benchmark inventory")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("benchmarks/manifests/suites.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/manifests/existing_scenarios.json"))
    parser.add_argument("--coverage-output", type=Path, default=Path("benchmarks/reports/inventory_coverage.json"))
    parser.add_argument("--check", action="store_true", help="validate only; do not write generated files")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    try:
        inventory = build_inventory(root, config)
        report = coverage(inventory)
        if not args.check:
            output = args.output if args.output.is_absolute() else root / args.output
            coverage_output = args.coverage_output if args.coverage_output.is_absolute() else root / args.coverage_output
            _write_json(output, inventory)
            _write_json(coverage_output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except InventoryError as exc:
        print(f"benchmark inventory error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
