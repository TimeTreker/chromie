from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.contracts import ContractError
from benchmarks.inventory.core import build_inventory


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load inventory {path}: {exc}") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("scenarios"), list):
        raise ContractError("inventory must use schema_version 1 and contain scenarios")
    return payload


def _normalize_inventory_payload(
    repo_root: Path, inventory: dict[str, Any], *, generated_from: str
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: dict[str, str] = {}
    grouped: dict[str, dict[str, Any]] = {}
    for entry in inventory["scenarios"]:
        if entry.get("source_kind") != "scenario_file":
            continue
        source_path = entry.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            errors.append(f"invalid inventory source path: {source_path!r}")
            continue
        prior = grouped.get(source_path)
        if prior is None:
            grouped[source_path] = entry
            continue
        classification = (entry.get("layer"), entry.get("datasets"), entry.get("evidence_levels"))
        prior_classification = (
            prior.get("layer"), prior.get("datasets"), prior.get("evidence_levels")
        )
        if classification != prior_classification:
            errors.append(
                f"{source_path}: inconsistent inventory classification within one source file"
            )

    for source_path, entry in sorted(grouped.items()):
        try:
            normalized = normalize_json_file(
                repo_root / source_path,
                repo_root=repo_root,
                layer=entry["layer"],
                datasets=entry["datasets"],
                evidence_requirements=entry["evidence_levels"],
            )
            for case in normalized:
                prior = seen.get(case["id"])
                if prior is not None:
                    raise ContractError(
                        f"duplicate normalized scenario id {case['id']!r}: {prior}, {source_path}"
                    )
                seen[case["id"]] = source_path
                cases.append(case)
        except (ContractError, KeyError, TypeError) as exc:
            errors.append(f"{source_path}: {exc}")
    if errors:
        raise ContractError("normalization failed:\n" + "\n".join(sorted(errors)))
    cases.sort(
        key=lambda item: (
            item["id"],
            item["source"]["path"],
            item["source"]["source_index"]
            if item["source"]["source_index"] is not None
            else -1,
        )
    )
    return {
        "schema_version": 1,
        "generated_from": generated_from,
        "cases": cases,
    }


def normalize_inventory(repo_root: Path, inventory_path: Path) -> dict[str, Any]:
    inventory = _load_inventory(inventory_path)
    try:
        generated_from = inventory_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        generated_from = str(inventory_path.resolve())
    return _normalize_inventory_payload(
        repo_root, inventory, generated_from=generated_from
    )


def normalize_config(repo_root: Path, config_path: Path) -> dict[str, Any]:
    inventory = build_inventory(repo_root, config_path)
    try:
        generated_from = config_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        generated_from = str(config_path.resolve())
    return _normalize_inventory_payload(
        repo_root, inventory, generated_from=f"{generated_from}#generated-inventory"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize inventoried scenarios into the common contract")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--inventory", type=Path, default=Path("benchmarks/manifests/existing_scenarios.json")
    )
    parser.add_argument(
        "--config", type=Path, default=Path("benchmarks/manifests/suites.json")
    )
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/normalized_scenarios.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    inventory_path = args.inventory if args.inventory.is_absolute() else repo_root / args.inventory
    config_path = args.config if args.config.is_absolute() else repo_root / args.config
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    try:
        if inventory_path.exists():
            result = normalize_inventory(repo_root, inventory_path)
        else:
            result = normalize_config(repo_root, config_path)
    except ContractError as exc:
        print(f"benchmark normalization error: {exc}", file=sys.stderr)
        return 2
    print(f"normalized {len(result['cases'])} scenarios")
    if not args.check:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output_path.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
