from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.contracts import ContractError


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load inventory {path}: {exc}") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("scenarios"), list):
        raise ContractError("inventory must use schema_version 1 and contain scenarios")
    return payload


def normalize_inventory(repo_root: Path, inventory_path: Path) -> dict[str, Any]:
    inventory = _load_inventory(inventory_path)
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: dict[str, str] = {}
    for entry in inventory["scenarios"]:
        if entry.get("source_kind") != "scenario_file":
            continue
        source_path = entry.get("source_path")
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
    cases.sort(key=lambda item: (item["id"], item["source"]["path"], item["source"]["source_index"] or -1))
    return {
        "schema_version": 1,
        "generated_from": inventory_path.resolve().relative_to(repo_root.resolve()).as_posix(),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize inventoried scenarios into the common contract")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--inventory", type=Path, default=Path("benchmarks/manifests/existing_scenarios.json")
    )
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/normalized_scenarios.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    inventory_path = args.inventory if args.inventory.is_absolute() else repo_root / args.inventory
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    try:
        result = normalize_inventory(repo_root, inventory_path)
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
