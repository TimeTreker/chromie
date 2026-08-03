from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.contracts import ContractError
from benchmarks.regression.archive import (
    find_single,
    load_json,
    materialize_source,
    qualification_root,
    verify_artifact_index,
)

_STATUS_RANK = {"PASS": 4, "SKIP": 2, "TIMEOUT": 1, "FAIL": 0, "MISSING": -1}
_SEMANTIC_RANK = {"pass": 4, "partial": 3, "review": 2, "insufficient_evidence": 1, "fail": 0}


@dataclass(frozen=True)
class RunSnapshot:
    source: str
    root: Path
    report: dict[str, Any]
    artifact_integrity: dict[str, Any]
    checks: dict[str, dict[str, Any]]
    scenarios: dict[str, dict[str, Any]]
    metrics: dict[str, float]

    @property
    def revision(self) -> str | None:
        value = self.report.get("revision")
        return value if isinstance(value, str) else None


def _check_key(row: Mapping[str, Any]) -> str:
    return f"{row.get('phase', '')}::{row.get('check', '')}"


def _scenario_rows(root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for summary_path in sorted(root.glob("e2e/**/summary.json")):
        try:
            payload = load_json(summary_path)
        except ContractError:
            continue
        for section in ("transport", "workflow"):
            values = payload.get(section)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, Mapping):
                    continue
                scenario_id = item.get("id") or item.get("scenario_id")
                if not isinstance(scenario_id, str) or not scenario_id:
                    continue
                rows[scenario_id] = {
                    "scenario_id": scenario_id,
                    "source": str(summary_path.relative_to(root)),
                    "status": str(item.get("status") or ("pass" if item.get("passed") else "fail")),
                    "mechanical_passed": item.get("mechanical_passed", item.get("passed")),
                    "semantic_review_required": bool(item.get("semantic_review_required")),
                    "semantic_verdict": None,
                    "evidence_present": bool(item.get("artifacts") or item.get("captured_wav")),
                }
    for path in sorted(root.rglob("*.json")):
        if path.name in {"summary.json", "collection-report.json", "artifact-index.json"}:
            continue
        try:
            payload = load_json(path)
        except ContractError:
            continue
        reviews = payload.get("reviews")
        if not isinstance(reviews, list):
            continue
        for review in reviews:
            if not isinstance(review, Mapping):
                continue
            scenario_id = review.get("scenario_id")
            verdict = review.get("verdict")
            if not isinstance(scenario_id, str) or not isinstance(verdict, str):
                continue
            row = rows.setdefault(
                scenario_id,
                {
                    "scenario_id": scenario_id,
                    "source": str(path.relative_to(root)),
                    "status": "review",
                    "mechanical_passed": None,
                    "semantic_review_required": True,
                    "semantic_verdict": None,
                    "evidence_present": False,
                },
            )
            row["semantic_verdict"] = verdict
            row["review_source"] = str(path.relative_to(root))
    return rows


def _walk_numbers(value: Any, *, prefix: str = "") -> Iterable[tuple[str, float]]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        lowered = prefix.casefold()
        allowed = (
            "latency",
            "duration",
            "rtf",
            "error_rate",
            "wer",
            "cer",
            "memory.used",
            "memory_used",
            "gpu_memory",
            "first_audio",
            "first_pcm",
            "playback",
        )
        if any(token in lowered for token in allowed):
            yield prefix, float(value)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk_numbers(item, prefix=child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_numbers(item, prefix=f"{prefix}[{index}]")


def _metrics(root: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for path in sorted(root.rglob("*.json")):
        if path.name == "artifact-index.json":
            continue
        try:
            payload = load_json(path)
        except ContractError:
            continue
        relative = str(path.relative_to(root))
        for key, value in _walk_numbers(payload):
            metrics[f"{relative}:{key}"] = value
    return metrics


def _snapshot(source: Path) -> RunSnapshot:
    with materialize_source(source) as materialized:
        root = qualification_root(materialized)
        report = load_json(root / "collection-report.json")
        checks_value = report.get("checks")
        if not isinstance(checks_value, list):
            raise ContractError(f"{root}: collection report has no check ledger")
        checks = {
            _check_key(row): dict(row)
            for row in checks_value
            if isinstance(row, Mapping)
        }
        # Copy values out of the temporary extraction before the context closes.
        return RunSnapshot(
            source=str(source),
            root=Path(str(root)),
            report=dict(report),
            artifact_integrity=verify_artifact_index(root),
            checks=checks,
            scenarios=_scenario_rows(root),
            metrics=_metrics(root),
        )


def _identity(snapshot: RunSnapshot) -> dict[str, Any]:
    return {
        "source": snapshot.source,
        "revision": snapshot.revision,
        "overall_status": snapshot.report.get("overall_status"),
        "capture_mode": snapshot.report.get("capture_mode"),
        "languages": snapshot.report.get("languages"),
        "runner_version": snapshot.report.get("runner_version"),
        "artifact_integrity": snapshot.artifact_integrity,
    }


def compare_qualification_runs(
    baseline_source: Path,
    candidate_source: Path,
    *,
    max_relative_regression: float = 0.20,
    absolute_latency_ms: float = 100.0,
) -> dict[str, Any]:
    if max_relative_regression < 0:
        raise ContractError("max_relative_regression must be non-negative")
    if absolute_latency_ms < 0:
        raise ContractError("absolute_latency_ms must be non-negative")
    baseline = _snapshot(baseline_source)
    candidate = _snapshot(candidate_source)

    deterministic_regressions: list[dict[str, Any]] = []
    deterministic_improvements: list[dict[str, Any]] = []
    added_checks: list[str] = []
    removed_checks: list[str] = []
    for key in sorted(set(baseline.checks) | set(candidate.checks)):
        before = baseline.checks.get(key)
        after = candidate.checks.get(key)
        if before is None:
            added_checks.append(key)
            continue
        if after is None:
            removed_checks.append(key)
            deterministic_regressions.append(
                {"check": key, "baseline": before.get("status"), "candidate": "MISSING", "reason": "check_missing"}
            )
            continue
        before_status = str(before.get("status") or "MISSING")
        after_status = str(after.get("status") or "MISSING")
        before_rank = _STATUS_RANK.get(before_status, -1)
        after_rank = _STATUS_RANK.get(after_status, -1)
        record = {"check": key, "baseline": before_status, "candidate": after_status}
        if after_rank < before_rank:
            deterministic_regressions.append(record)
        elif after_rank > before_rank:
            deterministic_improvements.append(record)

    scenario_regressions: list[dict[str, Any]] = []
    scenario_improvements: list[dict[str, Any]] = []
    scenario_additions: list[str] = []
    scenario_removals: list[str] = []
    for scenario_id in sorted(set(baseline.scenarios) | set(candidate.scenarios)):
        before = baseline.scenarios.get(scenario_id)
        after = candidate.scenarios.get(scenario_id)
        if before is None:
            scenario_additions.append(scenario_id)
            continue
        if after is None:
            scenario_removals.append(scenario_id)
            scenario_regressions.append(
                {"scenario_id": scenario_id, "reason": "scenario_or_evidence_missing", "baseline": before, "candidate": None}
            )
            continue
        reasons: list[str] = []
        if before.get("mechanical_passed") is True and after.get("mechanical_passed") is not True:
            reasons.append("mechanical_pass_to_non_pass")
        before_semantic = before.get("semantic_verdict")
        after_semantic = after.get("semantic_verdict")
        if isinstance(before_semantic, str):
            if not isinstance(after_semantic, str):
                reasons.append("semantic_review_missing")
            elif _SEMANTIC_RANK.get(after_semantic, -1) < _SEMANTIC_RANK.get(before_semantic, -1):
                reasons.append("semantic_verdict_regressed")
        if before.get("evidence_present") and not after.get("evidence_present"):
            reasons.append("evidence_lost")
        if reasons:
            scenario_regressions.append(
                {"scenario_id": scenario_id, "reasons": reasons, "baseline": before, "candidate": after}
            )
        elif (
            before.get("mechanical_passed") is not True
            and after.get("mechanical_passed") is True
        ) or (
            isinstance(before_semantic, str)
            and isinstance(after_semantic, str)
            and _SEMANTIC_RANK.get(after_semantic, -1) > _SEMANTIC_RANK.get(before_semantic, -1)
        ):
            scenario_improvements.append(
                {"scenario_id": scenario_id, "baseline": before, "candidate": after}
            )

    performance_regressions: list[dict[str, Any]] = []
    performance_changes: list[dict[str, Any]] = []
    for key in sorted(set(baseline.metrics) & set(candidate.metrics)):
        before = baseline.metrics[key]
        after = candidate.metrics[key]
        delta = after - before
        relative = delta / abs(before) if before else None
        record = {
            "metric": key,
            "baseline": before,
            "candidate": after,
            "delta": delta,
            "relative_change": relative,
        }
        performance_changes.append(record)
        lowered = key.casefold()
        is_latency = any(token in lowered for token in ("latency", "duration", "first_audio", "first_pcm", "playback"))
        is_error = any(token in lowered for token in ("error_rate", "wer", "cer", "rtf"))
        threshold_hit = relative is not None and relative > max_relative_regression
        absolute_hit = not is_latency or delta > absolute_latency_ms
        if delta > 0 and (is_latency or is_error) and threshold_hit and absolute_hit:
            performance_regressions.append(record)

    cohort_compatible = (
        baseline.report.get("capture_mode") == candidate.report.get("capture_mode")
        and baseline.report.get("languages") == candidate.report.get("languages")
    )
    integrity_failed = any(
        snapshot.artifact_integrity.get("status") == "failed"
        for snapshot in (baseline, candidate)
    )
    regression = bool(
        deterministic_regressions
        or scenario_regressions
        or performance_regressions
        or integrity_failed
    )
    verdict = "regression" if regression else "inconclusive" if not cohort_compatible else "no_regression_detected"
    return {
        "schema_version": 1,
        "kind": "chromie_qualification_regression_comparison",
        "verdict": verdict,
        "cohort_compatible": cohort_compatible,
        "thresholds": {
            "max_relative_regression": max_relative_regression,
            "absolute_latency_ms": absolute_latency_ms,
        },
        "baseline": _identity(baseline),
        "candidate": _identity(candidate),
        "deterministic": {
            "regressions": deterministic_regressions,
            "improvements": deterministic_improvements,
            "added_checks": added_checks,
            "removed_checks": removed_checks,
        },
        "scenarios": {
            "regressions": scenario_regressions,
            "improvements": scenario_improvements,
            "added": scenario_additions,
            "removed": scenario_removals,
        },
        "performance": {
            "regressions": performance_regressions,
            "compared_metric_count": len(performance_changes),
            "changes": performance_changes,
        },
        "notes": [
            "Deterministic regressions are non-overridable.",
            "Semantic comparison uses retained verdicts and never invents a missing review.",
            "Incompatible cohorts are reported as inconclusive even when no regression is detected.",
        ],
    }
