from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.runners.core import select_cases


class QualificationError(ValueError):
    pass


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot load {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise QualificationError(f"{label} must be a JSON object")
    return payload


def load_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path, label="Social Attention qualification manifest")
    if payload.get("schema_version") != 1:
        raise QualificationError("qualification manifest must use schema_version 1")
    if payload.get("runtime_policy_authority") is not False:
        raise QualificationError("qualification manifest must deny Runtime policy authority")
    if payload.get("release_qualification_automatic") is not False:
        raise QualificationError("qualification manifest must deny automatic release qualification")
    required = payload.get("required_run_identity")
    gates = payload.get("hard_gates")
    if not isinstance(required, list) or not all(
        isinstance(item, str) and item for item in required
    ):
        raise QualificationError("required_run_identity must contain non-empty strings")
    if not isinstance(gates, list) or not gates:
        raise QualificationError("qualification manifest must contain hard_gates")
    ids: set[str] = set()
    for gate in gates:
        if not isinstance(gate, Mapping):
            raise QualificationError("each hard gate must be an object")
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            raise QualificationError("each hard gate requires a non-empty id")
        if gate_id in ids:
            raise QualificationError(f"duplicate hard gate id {gate_id!r}")
        ids.add(gate_id)
        minimum = gate.get("minimum_cases", 1)
        if not isinstance(minimum, int) or minimum < 1:
            raise QualificationError(
                f"hard gate {gate_id!r} minimum_cases must be positive"
            )
    return payload


def _identity_missing(run: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    required = list(manifest.get("required_run_identity", []))
    profile = run.get("evidence_profile")
    profile_required = manifest.get("profile_required_run_identity", {})
    if isinstance(profile_required, Mapping) and isinstance(profile, str):
        values = profile_required.get(profile, [])
        if isinstance(values, list):
            required.extend(item for item in values if isinstance(item, str))
    missing: list[str] = []
    for name in dict.fromkeys(required):
        value = run.get(name)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(name)
        elif name == "sample_count" and (
            not isinstance(value, int) or value < 1
        ):
            missing.append(name)
    return missing


def _select_gate_cases(
    cases: list[Mapping[str, Any]], selectors: Mapping[str, Any]
) -> list[dict[str, Any]]:
    def values(name: str) -> set[str] | None:
        value = selectors.get(name)
        if value is None:
            return None
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise QualificationError(
                f"gate selector {name!r} must be an array of strings"
            )
        return set(value) or None

    return select_cases(
        cases,
        layers=values("layers"),
        datasets=values("datasets"),
        ids=values("ids"),
        cohorts=values("cohorts"),
        styles=values("styles"),
        modes=values("modes"),
        languages=values("languages"),
        invariants=values("invariants"),
        forbidden_behaviors=values("forbidden_behaviors"),
    )


def _gate_case_result(
    gate: Mapping[str, Any],
    case: Mapping[str, Any],
    result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    scenario_id = str(case["id"])
    failures: list[str] = []
    if result is None:
        return {
            "scenario_id": scenario_id,
            "passed": False,
            "failures": ["result_missing"],
        }
    if result.get("status") in {"fail", "error"}:
        failures.append(f"result_status:{result.get('status')}")
    reported = {
        item.get("name"): item
        for item in result.get("invariant_results", [])
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    for name in gate.get("required_invariants", []):
        item = reported.get(name)
        if item is None:
            failures.append(f"invariant_missing:{name}")
        elif item.get("passed") is not True:
            failures.append(f"invariant_failed:{name}")
    forbidden_hits = set(
        result.get("evaluation", {}).get("forbidden_behavior_hits", [])
    )
    for name in gate.get("forbidden_behaviors", []):
        if name in forbidden_hits:
            failures.append(f"forbidden_behavior:{name}")
    lifecycle = result.get("observations", {}).get(
        "social_attention_lifecycle", {}
    )
    if not isinstance(lifecycle, Mapping):
        lifecycle = {}
    allowed = gate.get("lifecycle_allowed", {})
    if not isinstance(allowed, Mapping):
        raise QualificationError(
            f"gate {gate.get('id')!r} lifecycle_allowed must be an object"
        )
    for name, states in allowed.items():
        if not isinstance(states, list) or not all(
            isinstance(item, str) for item in states
        ):
            raise QualificationError(
                f"gate {gate.get('id')!r} lifecycle states for {name!r} "
                "must be strings"
            )
        observed = lifecycle.get(name)
        if observed is None:
            failures.append(f"lifecycle_missing:{name}")
        elif observed not in states:
            failures.append(f"lifecycle_disallowed:{name}={observed}")
    return {
        "scenario_id": scenario_id,
        "passed": not failures,
        "failures": failures,
    }


def _case_scope(case: Mapping[str, Any]) -> tuple[str | None, str | None]:
    context = case.get("context")
    metadata = context.get("metadata") if isinstance(context, Mapping) else None
    if not isinstance(metadata, Mapping):
        return None, None
    mode = metadata.get("mode")
    style = metadata.get("style")
    return (
        str(mode).strip() if isinstance(mode, str) and mode.strip() else None,
        str(style).strip() if isinstance(style, str) and style.strip() else None,
    )


def _collect_bundle(
    *,
    reports: Sequence[Mapping[str, Any]],
    social_cases: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if not reports:
        raise QualificationError("qualification requires at least one E2E report")

    cases_by_id = {str(item["id"]): item for item in social_cases}
    runs: list[dict[str, Any]] = []
    result_map: dict[str, Mapping[str, Any]] = {}
    result_provenance: dict[str, str] = {}
    duplicate_results: list[str] = []
    unexpected_results: list[str] = []
    scope_errors: list[str] = []
    run_ids: set[str] = set()
    identity_runs: list[dict[str, Any]] = []

    for index, report in enumerate(reports):
        if report.get("schema_version") != 1:
            raise QualificationError(
                f"E2E report {index + 1} must use schema_version 1"
            )
        run = report.get("run")
        results = report.get("results")
        if not isinstance(run, Mapping) or not isinstance(results, list):
            raise QualificationError(
                f"E2E report {index + 1} must contain run and results"
            )
        run_payload = dict(run)
        run_id = str(run_payload.get("run_id") or f"report-{index + 1}")
        missing = _identity_missing(run_payload, manifest)
        if run_id in run_ids:
            scope_errors.append(f"duplicate_run_id:{run_id}")
        run_ids.add(run_id)
        runs.append(run_payload)
        identity_runs.append(
            {"run_id": run_id, "complete": not missing, "missing": missing}
        )

        run_mode = run_payload.get("social_attention_mode")
        run_style = run_payload.get("social_interaction_style")
        for item in results:
            if not isinstance(item, Mapping):
                scope_errors.append(f"invalid_result_object:{run_id}")
                continue
            scenario_id = item.get("scenario_id")
            if not isinstance(scenario_id, str) or not scenario_id:
                scope_errors.append(f"missing_scenario_id:{run_id}")
                continue
            case = cases_by_id.get(scenario_id)
            if case is None:
                unexpected_results.append(scenario_id)
                continue
            if scenario_id in result_map:
                duplicate_results.append(scenario_id)
                continue
            expected_mode, expected_style = _case_scope(case)
            if expected_mode and run_mode != expected_mode:
                scope_errors.append(
                    f"mode_mismatch:{scenario_id}:expected={expected_mode}:run={run_mode}"
                )
            if expected_style and run_style != expected_style:
                scope_errors.append(
                    f"style_mismatch:{scenario_id}:expected={expected_style}:run={run_style}"
                )
            result_map[scenario_id] = item
            result_provenance[scenario_id] = run_id

    missing_results = sorted(set(cases_by_id) - set(result_map))
    return {
        "runs": runs,
        "result_map": result_map,
        "result_provenance": result_provenance,
        "identity_runs": identity_runs,
        "duplicate_results": sorted(set(duplicate_results)),
        "unexpected_results": sorted(set(unexpected_results)),
        "missing_results": missing_results,
        "scope_errors": sorted(set(scope_errors)),
    }


def build_qualification_report(
    *,
    manifest: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    e2e_reports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    social_cases = [
        item for item in cases if "social_attention" in item.get("datasets", [])
    ]
    bundle = _collect_bundle(
        reports=e2e_reports,
        social_cases=social_cases,
        manifest=manifest,
    )
    result_map = bundle["result_map"]

    gate_reports: list[dict[str, Any]] = []
    for gate in manifest["hard_gates"]:
        selected = _select_gate_cases(social_cases, gate.get("selectors", {}))
        case_results = [
            _gate_case_result(gate, case, result_map.get(case["id"]))
            for case in selected
        ]
        minimum = int(gate.get("minimum_cases", 1))
        failures = [item for item in case_results if not item["passed"]]
        gate_reports.append(
            {
                "id": gate["id"],
                "description": gate.get("description", ""),
                "selected_cases": len(selected),
                "minimum_cases": minimum,
                "passed_cases": len(case_results) - len(failures),
                "failed_cases": len(failures),
                "passed": len(selected) >= minimum and not failures,
                "results": case_results,
            }
        )

    identity_complete = all(item["complete"] for item in bundle["identity_runs"])
    scope_complete = not bundle["scope_errors"]
    coverage_complete = not any(
        (
            bundle["missing_results"],
            bundle["duplicate_results"],
            bundle["unexpected_results"],
        )
    )
    hard_gates_passed = bool(gate_reports) and all(
        item["passed"] for item in gate_reports
    )
    eligible = (
        hard_gates_passed
        and identity_complete
        and scope_complete
        and coverage_complete
    )

    return {
        "schema_version": 1,
        "qualification_id": manifest["qualification_id"],
        "dataset_id": manifest["dataset_id"],
        "runs": bundle["runs"],
        "identity_validation": {
            "complete": identity_complete,
            "runs": bundle["identity_runs"],
        },
        "scope_validation": {
            "complete": scope_complete,
            "errors": bundle["scope_errors"],
            "policy": (
                "Each E2E report is one launcher-effective Social Attention mode "
                "and one owner-approved interaction style."
            ),
        },
        "coverage_validation": {
            "complete": coverage_complete,
            "missing_scenario_results": bundle["missing_results"],
            "duplicate_scenario_results": bundle["duplicate_results"],
            "unexpected_scenario_results": bundle["unexpected_results"],
            "result_provenance": bundle["result_provenance"],
        },
        "summary": {
            "social_case_count": len(social_cases),
            "reported_result_count": len(result_map),
            "run_count": len(bundle["runs"]),
            "hard_gate_count": len(gate_reports),
            "hard_gates_passed": sum(1 for item in gate_reports if item["passed"]),
            "hard_gates_failed": sum(1 for item in gate_reports if not item["passed"]),
        },
        "qualification": {
            "deterministic_hard_gates_passed": hard_gates_passed,
            "identity_complete": identity_complete,
            "scope_complete": scope_complete,
            "coverage_complete": coverage_complete,
            "release_qualified": False,
            "human_approval_required": True,
            "state": "human_review_required" if eligible else "not_eligible",
        },
        "hard_gates": gate_reports,
        "policy": {
            "runtime_policy_authority": False,
            "benchmark_specific_prompt_or_runtime_changes_allowed": False,
            "automatic_model_selection_allowed": False,
            "mixed_runtime_policy_in_one_run_allowed": False,
        },
    }


def load_report(path: Path) -> dict[str, Any]:
    return _load_json(path, label="E2E report")
