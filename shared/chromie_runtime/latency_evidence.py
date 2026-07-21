"""Retained Runtime Trace latency reports and evidence-based regression gates."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

LATENCY_REPORT_SCHEMA_VERSION = 1
LATENCY_GATE_POLICY_SCHEMA_VERSION = 1
LATENCY_GATE_RESULT_SCHEMA_VERSION = 1
REPORT_TYPE = "chromie.runtime_trace_latency_report"
GATE_RESULT_TYPE = "chromie.runtime_trace_latency_gate_result"
_SAFE_METRIC = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def discover_trace_files(sources: Sequence[str | Path]) -> list[Path]:
    """Discover immutable trace payloads from files or Runtime Event roots."""

    found: dict[str, Path] = {}
    for value in sources:
        source = Path(value).expanduser().resolve()
        if source.is_file():
            if source.name != "trace.json":
                raise ValueError(f"trace source file must be named trace.json: {source}")
            found[str(source)] = source
            continue
        if not source.is_dir():
            raise FileNotFoundError(source)
        direct = source / "trace.json"
        if direct.is_file():
            found[str(direct)] = direct
            continue
        ready = source / "ready"
        search_root = ready if ready.is_dir() else source
        for path in search_root.glob("**/trace.json"):
            if ".staging" in path.parts or "active" in path.parts:
                continue
            found[str(path.resolve())] = path.resolve()
    return [found[key] for key in sorted(found)]


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def distribution(values: Iterable[int | float]) -> dict[str, Any]:
    numeric = [float(value) for value in values if math.isfinite(float(value))]
    if not numeric:
        return {"count": 0}
    return {
        "count": len(numeric),
        "mean": round(sum(numeric) / len(numeric), 3),
        "min": round(min(numeric), 3),
        "p50": round(_quantile(numeric, 0.50), 3),
        "p90": round(_quantile(numeric, 0.90), 3),
        "p95": round(_quantile(numeric, 0.95), 3),
        "p99": round(_quantile(numeric, 0.99), 3),
        "max": round(max(numeric), 3),
    }


def _trace_summary(trace_path: Path, trace: Mapping[str, Any]) -> dict[str, Any]:
    summary_path = trace_path.with_name("trace-summary.json")
    if summary_path.is_file():
        return _read_json(summary_path)
    from .runtime_trace import _summarize_trace  # local import avoids public API expansion

    return _summarize_trace(trace)


def _event_manifest(trace_path: Path) -> dict[str, Any]:
    path = trace_path.with_name("event.json")
    return _read_json(path) if path.is_file() else {}


def _numeric_resource_metrics(trace: Mapping[str, Any]) -> dict[str, float]:
    per_metric: dict[str, list[float]] = defaultdict(list)
    for item in trace.get("items") or []:
        if not isinstance(item, Mapping) or item.get("kind") != "resource_sample":
            continue
        module = item.get("module") if isinstance(item.get("module"), Mapping) else {}
        module_name = str(module.get("name") or "unknown")
        attributes = item.get("attributes")
        if not isinstance(attributes, Mapping):
            continue
        for key, value in attributes.items():
            metric_name = f"{module_name}.{key}"
            if (
                _SAFE_METRIC.fullmatch(metric_name)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            ):
                per_metric[metric_name].append(float(value))
    return {name: max(values) for name, values in per_metric.items() if values}


def build_latency_report(
    *,
    sources: Sequence[str | Path],
    evidence_class: str,
    environment: str,
    label: str = "",
    chromie_revision: str | None = None,
    chromie_dirty: bool | None = None,
    include_abandoned: bool = False,
) -> dict[str, Any]:
    trace_paths = discover_trace_files(sources)
    samples: list[dict[str, Any]] = []
    total_values: list[float] = []
    observable_values: list[float] = []
    item_values: list[float] = []
    module_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    resource_values: dict[str, list[float]] = defaultdict(list)
    states: Counter[str] = Counter()
    coverage: Counter[str] = Counter()

    for trace_path in trace_paths:
        trace = _read_json(trace_path)
        if int(trace.get("schema_version") or 0) != 1:
            raise ValueError(f"{trace_path}: unsupported Runtime Trace schema")
        state = str(trace.get("state") or "unknown")
        if state == "abandoned" and not include_abandoned:
            continue
        summary = _trace_summary(trace_path, trace)
        manifest = _event_manifest(trace_path)
        total = float(summary.get("total_duration_ms") or 0.0)
        observable_raw = summary.get("first_user_observable_latency_ms")
        observable = float(observable_raw) if observable_raw is not None else None
        item_count = float(summary.get("item_count") or 0)
        states[state] += 1
        coverage[str(trace.get("coverage") or "unknown")] += 1
        total_values.append(total)
        item_values.append(item_count)
        if observable is not None:
            observable_values.append(observable)
        for aggregate in summary.get("module_aggregates") or []:
            if not isinstance(aggregate, Mapping):
                continue
            module = aggregate.get("module") if isinstance(aggregate.get("module"), Mapping) else {}
            name = str(module.get("name") or "unknown")
            for metric in (
                "inclusive_duration_ms",
                "exclusive_duration_ms",
                "max_duration_ms",
                "item_count",
                "error_count",
            ):
                value = aggregate.get(metric)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    module_values[name][metric].append(float(value))
        resource_metrics = _numeric_resource_metrics(trace)
        for name, value in resource_metrics.items():
            resource_values[name].append(value)
        samples.append(
            {
                "trace_id": str(trace.get("trace_id") or ""),
                "state": state,
                "coverage": str(trace.get("coverage") or "unknown"),
                "total_duration_ms": round(total, 3),
                "first_user_observable_latency_ms": (
                    round(observable, 3) if observable is not None else None
                ),
                "item_count": int(item_count),
                "correlations": dict(trace.get("correlations") or {}),
                "event": {
                    "event_id": manifest.get("event_id"),
                    "event_type": manifest.get("event_type"),
                    "event_subtype": manifest.get("event_subtype"),
                    "occurred_at": manifest.get("occurred_at"),
                },
                "source": str(trace_path),
            }
        )

    digest_payload = [
        {
            "trace_id": sample["trace_id"],
            "total_duration_ms": sample["total_duration_ms"],
            "first_user_observable_latency_ms": sample[
                "first_user_observable_latency_ms"
            ],
            "state": sample["state"],
        }
        for sample in samples
    ]
    source_digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": LATENCY_REPORT_SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "generated_at": _utc_now(),
        "label": str(label or ""),
        "evidence_class": str(evidence_class or "unspecified"),
        "environment": str(environment or "unspecified"),
        "provenance": {
            "chromie_revision": chromie_revision,
            "chromie_dirty": chromie_dirty,
        },
        "source": {
            "input_paths": [str(Path(value).expanduser()) for value in sources],
            "discovered_trace_count": len(trace_paths),
            "included_trace_count": len(samples),
            "include_abandoned": bool(include_abandoned),
            "digest_sha256": source_digest,
        },
        "state_counts": dict(sorted(states.items())),
        "coverage_counts": dict(sorted(coverage.items())),
        "metrics": {
            "total_duration_ms": distribution(total_values),
            "first_user_observable_latency_ms": distribution(observable_values),
            "item_count": distribution(item_values),
        },
        "module_metrics": {
            module: {
                metric: distribution(values)
                for metric, values in sorted(metrics.items())
            }
            for module, metrics in sorted(module_values.items())
        },
        "resource_metrics": {
            name: distribution(values) for name, values in sorted(resource_values.items())
        },
        "samples": samples,
    }


def _metric_distribution(
    report: Mapping[str, Any], *, scope: str, metric: str
) -> Mapping[str, Any] | None:
    if scope == "metrics":
        value = (report.get("metrics") or {}).get(metric)
    elif scope == "resource_metrics":
        value = (report.get("resource_metrics") or {}).get(metric)
    elif scope == "module_metrics":
        if "." not in metric:
            return None
        module, metric_name = metric.rsplit(".", 1)
        value = ((report.get("module_metrics") or {}).get(module) or {}).get(metric_name)
    else:
        return None
    return value if isinstance(value, Mapping) else None


def evaluate_latency_gate(
    *,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if int(policy.get("schema_version") or 0) != LATENCY_GATE_POLICY_SCHEMA_VERSION:
        errors.append("unsupported latency gate policy schema")
    if baseline.get("report_type") != REPORT_TYPE:
        errors.append("baseline is not a Runtime Trace latency report")
    if candidate.get("report_type") != REPORT_TYPE:
        errors.append("candidate is not a Runtime Trace latency report")
    enabled = bool(policy.get("enabled"))
    if not enabled:
        errors.append("latency gate policy is disabled")
    if enabled and not list(policy.get("gates") or []):
        errors.append("latency gate policy contains no metric gates")

    baseline_count = int(
        ((baseline.get("source") or {}).get("included_trace_count")) or 0
    )
    candidate_count = int(
        ((candidate.get("source") or {}).get("included_trace_count")) or 0
    )
    minimum_baseline = int(policy.get("minimum_baseline_samples") or 1)
    minimum_candidate = int(policy.get("minimum_candidate_samples") or 1)
    if baseline_count < minimum_baseline:
        errors.append(
            f"baseline sample count {baseline_count} is below {minimum_baseline}"
        )
    if candidate_count < minimum_candidate:
        errors.append(
            f"candidate sample count {candidate_count} is below {minimum_candidate}"
        )

    required_class = str(policy.get("required_evidence_class") or "").strip()
    if required_class:
        if baseline.get("evidence_class") != required_class:
            errors.append("baseline evidence class does not match policy")
        if candidate.get("evidence_class") != required_class:
            errors.append("candidate evidence class does not match policy")
    elif baseline.get("evidence_class") != candidate.get("evidence_class"):
        errors.append("baseline and candidate evidence classes differ")

    if bool(policy.get("require_same_environment", True)) and (
        baseline.get("environment") != candidate.get("environment")
    ):
        errors.append("baseline and candidate environments differ")
    if bool(policy.get("require_clean_revision", True)):
        for name, report in (("baseline", baseline), ("candidate", candidate)):
            if (report.get("provenance") or {}).get("chromie_dirty") is not False:
                errors.append(f"{name} does not record a clean Chromie revision")

    gate_results: list[dict[str, Any]] = []
    if not errors:
        for index, gate in enumerate(policy.get("gates") or []):
            if not isinstance(gate, Mapping):
                errors.append(f"gate {index} is not an object")
                continue
            scope = str(gate.get("scope") or "metrics")
            metric = str(gate.get("metric") or "")
            statistic = str(gate.get("statistic") or "p95")
            baseline_distribution = _metric_distribution(
                baseline, scope=scope, metric=metric
            )
            candidate_distribution = _metric_distribution(
                candidate, scope=scope, metric=metric
            )
            if baseline_distribution is None or candidate_distribution is None:
                errors.append(f"gate metric is unavailable: {scope}.{metric}")
                continue
            minimum_metric_samples = int(gate.get("minimum_metric_samples") or 1)
            if int(baseline_distribution.get("count") or 0) < minimum_metric_samples:
                errors.append(f"baseline metric has insufficient samples: {scope}.{metric}")
                continue
            if int(candidate_distribution.get("count") or 0) < minimum_metric_samples:
                errors.append(f"candidate metric has insufficient samples: {scope}.{metric}")
                continue
            baseline_value = baseline_distribution.get(statistic)
            candidate_value = candidate_distribution.get(statistic)
            if not isinstance(baseline_value, (int, float)) or not isinstance(
                candidate_value, (int, float)
            ):
                errors.append(
                    f"statistic is unavailable: {scope}.{metric}.{statistic}"
                )
                continue
            baseline_float = float(baseline_value)
            candidate_float = float(candidate_value)
            delta_ms = candidate_float - baseline_float
            delta_percent = (
                delta_ms / baseline_float * 100.0 if baseline_float > 0 else None
            )
            violations: list[str] = []
            max_candidate = gate.get("max_candidate_ms")
            if max_candidate is not None and candidate_float > float(max_candidate):
                violations.append("max_candidate_ms")
            max_delta = gate.get("max_regression_ms")
            if max_delta is not None and delta_ms > float(max_delta):
                violations.append("max_regression_ms")
            max_percent = gate.get("max_regression_percent")
            if max_percent is not None:
                if delta_percent is None:
                    violations.append("relative_baseline_zero")
                elif delta_percent > float(max_percent):
                    violations.append("max_regression_percent")
            gate_results.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "statistic": statistic,
                    "baseline": round(baseline_float, 3),
                    "candidate": round(candidate_float, 3),
                    "delta": round(delta_ms, 3),
                    "delta_percent": (
                        round(delta_percent, 3) if delta_percent is not None else None
                    ),
                    "passed": not violations,
                    "violations": violations,
                }
            )

    status = "invalid" if errors else (
        "pass" if all(result["passed"] for result in gate_results) else "fail"
    )
    return {
        "schema_version": LATENCY_GATE_RESULT_SCHEMA_VERSION,
        "result_type": GATE_RESULT_TYPE,
        "generated_at": _utc_now(),
        "status": status,
        "ok": status == "pass",
        "errors": errors,
        "policy_label": str(policy.get("label") or ""),
        "baseline": {
            "label": baseline.get("label"),
            "revision": (baseline.get("provenance") or {}).get("chromie_revision"),
            "digest_sha256": (baseline.get("source") or {}).get("digest_sha256"),
            "sample_count": baseline_count,
        },
        "candidate": {
            "label": candidate.get("label"),
            "revision": (candidate.get("provenance") or {}).get("chromie_revision"),
            "digest_sha256": (candidate.get("source") or {}).get("digest_sha256"),
            "sample_count": candidate_count,
        },
        "gates": gate_results,
    }
