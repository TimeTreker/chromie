from __future__ import annotations

"""Relation-aware generalization checks for retained semantic observations.

This module does not run cognition and contains no phrase-to-answer oracle.  It compares
already-produced structured observations according to owner-declared metamorphic relations:
which owned semantic fields must remain invariant, which controlled fields must change, and
which exact assertions must hold on either side of the relation.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


_MISSING = object()


def _lookup(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for raw_part in path.split("."):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"invalid empty path segment in {path!r}")
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _path_value(value: Any, path: str) -> tuple[bool, Any]:
    found = _lookup(value, path)
    return (found is not _MISSING, None if found is _MISSING else found)


def compare_relation(
    *,
    relation: Mapping[str, Any],
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    relation_id = str(relation.get("id") or "").strip()
    left_id = str(relation.get("left") or "").strip()
    right_id = str(relation.get("right") or "").strip()
    if not relation_id or not left_id or not right_id:
        raise ValueError("generalization relation requires id, left and right")
    if left_id not in observations or right_id not in observations:
        raise ValueError(
            f"relation {relation_id!r} references missing observations {left_id!r}/{right_id!r}"
        )
    left = observations[left_id]
    right = observations[right_id]
    failures: list[str] = []

    for path in relation.get("invariants") or []:
        path = str(path)
        left_found, left_value = _path_value(left, path)
        right_found, right_value = _path_value(right, path)
        if not left_found or not right_found:
            failures.append(f"invariant {path}: missing on {'left' if not left_found else 'right'}")
        elif left_value != right_value:
            failures.append(
                f"invariant {path}: {left_value!r} != {right_value!r}"
            )

    for path in relation.get("deltas") or []:
        path = str(path)
        left_found, left_value = _path_value(left, path)
        right_found, right_value = _path_value(right, path)
        if not left_found or not right_found:
            failures.append(f"delta {path}: missing on {'left' if not left_found else 'right'}")
        elif left_value == right_value:
            failures.append(f"delta {path}: values did not change ({left_value!r})")

    for side_name, observation in (("left", left), ("right", right)):
        assertions = relation.get(f"{side_name}_assertions") or {}
        if not isinstance(assertions, Mapping):
            raise ValueError(
                f"relation {relation_id!r} {side_name}_assertions must be an object"
            )
        for path, expected in assertions.items():
            found, actual = _path_value(observation, str(path))
            if not found:
                failures.append(f"{side_name} assertion {path}: missing")
            elif actual != expected:
                failures.append(
                    f"{side_name} assertion {path}: {actual!r} != expected {expected!r}"
                )

    return {
        "id": relation_id,
        "left": left_id,
        "right": right_id,
        "transformation": str(relation.get("transformation") or ""),
        "passed": not failures,
        "failures": failures,
    }


def evaluate_generalization_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    observations = spec.get("observations")
    relations = spec.get("relations")
    if not isinstance(observations, Mapping) or not observations:
        raise ValueError("generalization spec requires observations")
    if not isinstance(relations, list) or not relations:
        raise ValueError("generalization spec requires relations")
    results = [
        compare_relation(relation=relation, observations=observations)
        for relation in relations
        if isinstance(relation, Mapping)
    ]
    if len(results) != len(relations):
        raise ValueError("every generalization relation must be an object")
    return {
        "schema_version": "0.1",
        "relation_count": len(results),
        "passed": all(item["passed"] for item in results),
        "failed_relation_ids": [item["id"] for item in results if not item["passed"]],
        "relations": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    report = evaluate_generalization_spec(spec)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
