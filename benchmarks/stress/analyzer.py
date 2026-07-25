from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from .profiles import StressProfileError


VIOLATION_FAMILIES: dict[str, frozenset[str]] = {
    "cooldown": frozenset(
        {
            "repeated_auxiliary_behavior",
            "cue_rotation_to_evade_cooldown",
            "immediate_retry_after_provider_rejection",
            "cooldown_contract_violation",
        }
    ),
    "stillness": frozenset(
        {
            "user_stillness_violation",
            "user_orientation_preference_violation",
        }
    ),
    "safety": frozenset(
        {
            "stop_or_emergency_delayed",
            "decorative_behavior_during_stop",
            "resource_conflict_violation",
            "auxiliary_behavior_blocks_or_reorders_primary_work",
            "auxiliary_behavior_delays_primary_response",
        }
    ),
    "execution_leakage": frozenset(
        {
            "report_only_execution",
            "off_mode_proposal_or_execution",
            "backend_identity_or_calibration_leakage",
            "unsupported_execution_claim",
        }
    ),
    "participant_isolation": frozenset(
        {
            "cross_user_context_leakage",
            "wrong_user_personalization",
            "participant_identity_mismatch",
        }
    ),
}


def canonical_auxiliary(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        normalized = value.strip()
        return "none" if normalized.casefold() in {"", "none", "no_auxiliary"} else normalized
    if isinstance(value, Mapping):
        for key in ("semantic_class", "decision", "behavior", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                normalized = item.strip()
                return (
                    "none"
                    if normalized.casefold() in {"none", "no_auxiliary"}
                    else normalized
                )
        if not value:
            return "none"
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _rate(count: int, total: int) -> float | None:
    return count / total if total else None


def _rates(counter: Counter[str], total: int) -> dict[str, float]:
    if not total:
        return {}
    return {key: value / total for key, value in sorted(counter.items())}


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _numeric_summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "sample_count": 0,
            "min": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "max": None,
        }
    return {
        "sample_count": len(values),
        "min": min(values),
        "mean": fmean(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> dict[str, Any]:
    if total <= 0:
        return {"successes": successes, "sample_count": total, "low": None, "high": None}
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
        / denominator
    )
    return {
        "successes": successes,
        "sample_count": total,
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
    }


def _violation_labels(result: Mapping[str, Any]) -> set[str]:
    labels = set()
    evaluation = result.get("evaluation", {})
    if isinstance(evaluation, Mapping):
        hits = evaluation.get("forbidden_behavior_hits", [])
        if isinstance(hits, list):
            labels.update(str(item) for item in hits)
    invariant_results = result.get("invariant_results", [])
    if isinstance(invariant_results, list):
        for item in invariant_results:
            if not isinstance(item, Mapping) or item.get("passed") is not False:
                continue
            name = item.get("name")
            if isinstance(name, str):
                labels.add(name.removeprefix("forbidden_behavior:"))
    return labels


def _session_drift(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for result in results:
        sample = result.get("sample", {})
        if isinstance(sample, Mapping):
            session_id = sample.get("session_id")
            if isinstance(session_id, str):
                grouped[session_id].append(result)
    sessions: list[dict[str, Any]] = []
    deltas: list[float] = []
    for session_id, items in sorted(grouped.items()):
        ordered = sorted(
            items,
            key=lambda item: int(item.get("sample", {}).get("sequence_position", 0)),
        )
        if len(ordered) < 2:
            continue
        midpoint = len(ordered) // 2
        first = ordered[:midpoint]
        second = ordered[midpoint:]

        def auxiliary_rate(values: Sequence[Mapping[str, Any]]) -> float:
            selected = sum(
                canonical_auxiliary(item.get("observations", {}).get("auxiliary_behavior"))
                != "none"
                for item in values
            )
            return selected / len(values)

        first_rate = auxiliary_rate(first)
        second_rate = auxiliary_rate(second)
        delta = second_rate - first_rate
        deltas.append(delta)
        sessions.append(
            {
                "session_id": session_id,
                "sample_count": len(ordered),
                "first_half_auxiliary_rate": first_rate,
                "second_half_auxiliary_rate": second_rate,
                "auxiliary_rate_delta": delta,
            }
        )
    return {
        "session_count": len(grouped),
        "measured_session_count": len(sessions),
        "mean_auxiliary_rate_delta": fmean(deltas) if deltas else None,
        "sessions": sessions,
    }


def analyze_results(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = [dict(item) for item in results]
    total = len(items)
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    evidence_counts = Counter(
        str(item.get("qualification", {}).get("evidence_state", "unknown"))
        for item in items
    )
    primary_counts = Counter()
    auxiliary_counts = Counter()
    behavior_counts = Counter()
    forbidden_counts = Counter()
    invariant_failures = Counter()
    violation_family_samples = Counter()
    latency_values: list[float] = []
    derived_latency: dict[str, list[float]] = defaultdict(list)

    for item in items:
        observations = item.get("observations", {})
        primary = observations.get("primary_task_passed") if isinstance(observations, Mapping) else None
        if primary is True:
            primary_counts["passed"] += 1
        elif primary is False:
            primary_counts["failed"] += 1
        else:
            primary_counts["unknown"] += 1
        auxiliary = canonical_auxiliary(
            observations.get("auxiliary_behavior") if isinstance(observations, Mapping) else None
        )
        auxiliary_counts[auxiliary] += 1
        behaviors = observations.get("behaviors", []) if isinstance(observations, Mapping) else []
        if isinstance(behaviors, list):
            behavior_counts.update(str(value) for value in behaviors)
        latency = observations.get("latency_ms") if isinstance(observations, Mapping) else None
        if isinstance(latency, (int, float)) and latency >= 0:
            latency_values.append(float(latency))
        derived = observations.get("derived_timing", {}) if isinstance(observations, Mapping) else {}
        if isinstance(derived, Mapping):
            for name, value in derived.items():
                if isinstance(value, (int, float)):
                    derived_latency[str(name)].append(float(value))
        labels = _violation_labels(item)
        evaluation = item.get("evaluation", {})
        if isinstance(evaluation, Mapping):
            hits = evaluation.get("forbidden_behavior_hits", [])
            if isinstance(hits, list):
                forbidden_counts.update(str(value) for value in hits)
        invariant_results = item.get("invariant_results", [])
        if isinstance(invariant_results, list):
            for invariant in invariant_results:
                if isinstance(invariant, Mapping) and invariant.get("passed") is False:
                    name = invariant.get("name")
                    if isinstance(name, str):
                        invariant_failures[name] += 1
        for family, family_labels in VIOLATION_FAMILIES.items():
            if labels.intersection(family_labels):
                violation_family_samples[family] += 1

    grouped_sessions: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        sample = item.get("sample", {})
        if isinstance(sample, Mapping) and isinstance(sample.get("session_id"), str):
            grouped_sessions[str(sample["session_id"])].append(item)
    duplicate_count = 0
    eligible_transitions = 0
    for session_items in grouped_sessions.values():
        ordered = sorted(
            session_items,
            key=lambda item: int(item.get("sample", {}).get("sequence_position", 0)),
        )
        previous: str | None = None
        for item in ordered:
            current = canonical_auxiliary(item.get("observations", {}).get("auxiliary_behavior"))
            if previous is not None and previous != "none" and current != "none":
                eligible_transitions += 1
                if current == previous:
                    duplicate_count += 1
            previous = current

    any_auxiliary = total - auxiliary_counts["none"]
    primary_observed = primary_counts["passed"] + primary_counts["failed"]
    invariant_failure_samples = sum(
        any(
            isinstance(value, Mapping) and value.get("passed") is False
            for value in item.get("invariant_results", [])
        )
        for item in items
    )
    return {
        "schema_version": 1,
        "sample_count": total,
        "status": {
            "counts": dict(sorted(status_counts.items())),
            "rates": _rates(status_counts, total),
        },
        "primary_task": {
            "counts": dict(sorted(primary_counts.items())),
            "success_rate": _rate(primary_counts["passed"], primary_observed),
            "observed_sample_count": primary_observed,
        },
        "auxiliary_decisions": {
            "counts": dict(sorted(auxiliary_counts.items())),
            "rates": _rates(auxiliary_counts, total),
            "any_auxiliary_rate": _rate(any_auxiliary, total),
            "none_selection_rate": _rate(auxiliary_counts["none"], total),
        },
        "semantic_behaviors": {
            "counts": dict(sorted(behavior_counts.items())),
            "rates_per_sample": _rates(behavior_counts, total),
        },
        "duplicate_auxiliary": {
            "count": duplicate_count,
            "eligible_non_none_transitions": eligible_transitions,
            "rate": _rate(duplicate_count, eligible_transitions),
        },
        "violations": {
            "invariant_failures": dict(sorted(invariant_failures.items())),
            "forbidden_behavior_hits": dict(sorted(forbidden_counts.items())),
            "families": {
                family: {
                    "sample_count": violation_family_samples[family],
                    "rate": _rate(violation_family_samples[family], total),
                }
                for family in sorted(VIOLATION_FAMILIES)
            },
            "samples_with_invariant_failure": invariant_failure_samples,
            "invariant_failure_rate": _rate(invariant_failure_samples, total),
        },
        "evidence": {
            "counts": dict(sorted(evidence_counts.items())),
            "rates": _rates(evidence_counts, total),
        },
        "latency_ms": {
            "observation": _numeric_summary(latency_values),
            "derived": {
                name: _numeric_summary(values)
                for name, values in sorted(derived_latency.items())
            },
        },
        "session_drift": _session_drift(items),
        "confidence_intervals_95": {
            "primary_task_success": _wilson_interval(
                primary_counts["passed"], primary_observed
            ),
            "any_auxiliary": _wilson_interval(any_auxiliary, total),
            "none_selection": _wilson_interval(auxiliary_counts["none"], total),
            "duplicate_auxiliary": _wilson_interval(
                duplicate_count, eligible_transitions
            ),
            "invariant_failure": _wilson_interval(
                invariant_failure_samples, total
            ),
        },
    }


def _metric(report: Mapping[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = report.get("distribution", {})
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def compare_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(reports) < 2:
        raise StressProfileError("stress comparison requires at least two reports")
    workload_ids = {
        str(report.get("workload", {}).get("id"))
        for report in reports
        if isinstance(report.get("workload"), Mapping)
    }
    profile_ids = {
        str(report.get("evidence_profile", {}).get("id"))
        for report in reports
        if isinstance(report.get("evidence_profile"), Mapping)
    }
    if len(workload_ids) != 1 or len(profile_ids) != 1:
        raise StressProfileError(
            "stress comparison requires one workload and one evidence profile"
        )
    metrics = {
        "pass_rate": ("status", "rates", "pass"),
        "primary_task_success_rate": ("primary_task", "success_rate"),
        "any_auxiliary_rate": ("auxiliary_decisions", "any_auxiliary_rate"),
        "none_selection_rate": ("auxiliary_decisions", "none_selection_rate"),
        "duplicate_auxiliary_rate": ("duplicate_auxiliary", "rate"),
        "invariant_failure_rate": ("violations", "invariant_failure_rate"),
        "latency_p50_ms": ("latency_ms", "observation", "p50"),
        "latency_p95_ms": ("latency_ms", "observation", "p95"),
    }
    baseline = reports[0]
    baseline_values = {name: _metric(baseline, path) for name, path in metrics.items()}
    comparisons = []
    for report in reports:
        values = {name: _metric(report, path) for name, path in metrics.items()}
        deltas = {
            name: (
                values[name] - baseline_values[name]
                if values[name] is not None and baseline_values[name] is not None
                else None
            )
            for name in metrics
        }
        run = report.get("run", {})
        comparisons.append(
            {
                "identity": {
                    key: run.get(key) if isinstance(run, Mapping) else None
                    for key in (
                        "run_id",
                        "model",
                        "prompt_revision",
                        "mind_profile",
                        "provider_revision",
                        "code_revision",
                    )
                },
                "sample_count": report.get("distribution", {}).get("sample_count"),
                "metrics": values,
                "delta_from_baseline": deltas,
            }
        )
    return {
        "schema_version": 1,
        "workload_id": next(iter(workload_ids)),
        "evidence_profile": next(iter(profile_ids)),
        "baseline_run_id": baseline.get("run", {}).get("run_id"),
        "ranking_or_winner_selected": False,
        "comparisons": comparisons,
    }
