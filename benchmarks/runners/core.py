from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.adapters.normalize import normalize_inventory
from benchmarks.contracts import ContractError
from benchmarks.runners.evaluation import evaluate_boundaries
from benchmarks.runners.executors import ScenarioExecutor
from benchmarks.runners.models import RunProfile


def load_normalized_cases(
    repo_root: Path,
    *,
    normalized_path: Path | None = None,
    inventory_path: Path | None = None,
) -> list[dict[str, Any]]:
    if normalized_path is not None:
        try:
            payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot load normalized scenarios {normalized_path}: {exc}") from exc
        cases = payload.get("cases") if isinstance(payload, Mapping) else None
        if payload.get("schema_version") != 1 or not isinstance(cases, list):
            raise ContractError("normalized scenario file must use schema_version 1 and contain cases")
        return [dict(item) for item in cases]
    if inventory_path is None:
        raise ContractError("normalized_path or inventory_path is required")
    return normalize_inventory(repo_root, inventory_path)["cases"]


def _scenario_axis(source: Mapping[str, Any], name: str) -> str | None:
    context = source.get("context", {})
    if not isinstance(context, Mapping):
        return None
    metadata = context.get("metadata", {})
    if isinstance(metadata, Mapping):
        value = metadata.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if name == "language":
        inputs = source.get("inputs", {})
        if isinstance(inputs, Mapping):
            value = inputs.get("language")
            if isinstance(value, str) and value.strip():
                return value.strip()
    value = context.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def select_cases(
    cases: Iterable[Mapping[str, Any]],
    *,
    layers: set[str] | None = None,
    datasets: set[str] | None = None,
    ids: set[str] | None = None,
    cohorts: set[str] | None = None,
    styles: set[str] | None = None,
    modes: set[str] | None = None,
    languages: set[str] | None = None,
    invariants: set[str] | None = None,
    forbidden_behaviors: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for source in cases:
        if layers and source.get("layer") not in layers:
            continue
        if datasets and not datasets.intersection(source.get("datasets", [])):
            continue
        if ids and source.get("id") not in ids:
            continue
        if cohorts and _scenario_axis(source, "cohort") not in cohorts:
            continue
        if styles and _scenario_axis(source, "style") not in styles:
            continue
        if modes and _scenario_axis(source, "mode") not in modes:
            continue
        if languages and _scenario_axis(source, "language") not in languages:
            continue
        expectations = source.get("expectations", {})
        if not isinstance(expectations, Mapping):
            expectations = {}
        declared_invariants = set(expectations.get("invariants", []))
        declared_forbidden = set(expectations.get("forbidden_behaviors", []))
        if invariants and not invariants.intersection(declared_invariants):
            continue
        if forbidden_behaviors and not forbidden_behaviors.intersection(declared_forbidden):
            continue
        selected.append(dict(source))
    selected.sort(key=lambda item: item["id"])
    return selected


class BenchmarkRunner:
    def __init__(self, executor: ScenarioExecutor, profile: RunProfile) -> None:
        self._executor = executor
        self._profile = profile

    def run(self, cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for scenario in cases:
            try:
                observation = self._executor.execute(scenario, self._profile)
                results.append(evaluate_boundaries(scenario, observation, self._profile))
            except (ContractError, KeyError, TypeError) as exc:
                errors.append({"scenario_id": str(scenario.get("id", "unknown")), "error": str(exc)})
        counts = Counter(item["status"] for item in results)
        counts["error"] = len(errors)
        return {
            "schema_version": 1,
            "run": self._profile.to_dict(),
            "summary": {
                "total": len(results) + len(errors),
                "pass": counts["pass"],
                "fail": counts["fail"],
                "review": counts["review"],
                "error": counts["error"],
            },
            "results": results,
            "errors": errors,
        }
