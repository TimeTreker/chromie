#!/usr/bin/env python3
"""Summarize repeated inference-provider contention evidence into latency distributions."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.chromie_runtime.latency_evidence import distribution  # noqa: E402


REPORT_TYPE = "chromie.inference_provider_contention_summary"
REPORT_SCHEMA_VERSION = 2


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _discover_sources(values: Iterable[str | Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for value in values:
        source = Path(value).expanduser().resolve()
        if source.is_file():
            found[str(source)] = source
            continue
        if not source.is_dir():
            raise FileNotFoundError(source)
        for path in source.glob("*.json"):
            found[str(path.resolve())] = path.resolve()
    return [found[key] for key in sorted(found)]


def _is_provider_evidence(payload: dict[str, Any]) -> bool:
    return (
        payload.get("schema_version") == 3
        and isinstance(payload.get("provider"), str)
        and isinstance(payload.get("phases"), dict)
        and "foreground_under_deliberative_load" in payload["phases"]
    )


def _identity(payload: dict[str, Any]) -> dict[str, Any]:
    scheduler = payload.get("scheduler_config")
    operator_record = scheduler.get("operator_record") if isinstance(scheduler, dict) else None
    return {
        "provider": payload.get("provider"),
        "provider_version": payload.get("provider_version"),
        "runtime_image": payload.get("runtime_image"),
        "cuda_runtime": payload.get("cuda_runtime"),
        "accelerator_identity": payload.get("accelerator_identity"),
        "model": payload.get("model"),
        "model_revision": payload.get("model_revision"),
        "model_artifact": payload.get("model_artifact"),
        "base_url": payload.get("base_url"),
        "git_revision": payload.get("git_revision"),
        "git_dirty": payload.get("git_dirty"),
        "git_worktree_state_sha256": payload.get("git_worktree_state_sha256"),
        "scheduler_operator_record": operator_record,
        "workload_config": payload.get("workload_config"),
    }


def _require_stable_identity(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    first = _identity(payloads[0])
    for index, payload in enumerate(payloads[1:], start=2):
        current = _identity(payload)
        if current != first:
            differing = [key for key in first if first.get(key) != current.get(key)]
            raise ValueError(
                "provider contention sources mix qualification identities at sample "
                f"{index}: {', '.join(differing)}"
            )
    return first


def _number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric_values(samples: list[dict[str, Any]], *path: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        current: Any = sample
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            continue
        values.append(float(current))
    return values


def _foreground_window_ms(phase: dict[str, Any]) -> float | None:
    requests = phase.get("requests")
    if not isinstance(requests, dict):
        return None
    fast_gi = requests.get("fast_gi_canary")
    fast_planner = requests.get("fast_planner_canary")
    if not isinstance(fast_gi, dict) or not isinstance(fast_planner, dict):
        return None
    started = _number(fast_gi, "started_s")
    finished = _number(fast_planner, "finished_s")
    if started is None or finished is None or finished < started:
        return None
    return (finished - started) * 1000.0


def build_summary(sources: Iterable[str | Path], *, label: str = "") -> dict[str, Any]:
    paths = _discover_sources(sources)
    provider_samples: list[tuple[Path, dict[str, Any]]] = []
    ignored: list[str] = []
    for path in paths:
        payload = _read_json(path)
        if _is_provider_evidence(payload):
            provider_samples.append((path, payload))
        else:
            ignored.append(str(path))
    if not provider_samples:
        raise ValueError("no inference-provider contention evidence found")

    payloads = [payload for _, payload in provider_samples]
    identity = _require_stable_identity(payloads)
    phases = [payload["phases"]["foreground_under_deliberative_load"] for payload in payloads]
    if not all(isinstance(phase, dict) for phase in phases):
        raise ValueError("contention phase must be a JSON object in every source")
    typed_phases: list[dict[str, Any]] = [phase for phase in phases if isinstance(phase, dict)]

    phase_statuses = Counter(str(phase.get("status") or "unknown") for phase in typed_phases)
    run_statuses = Counter(str(payload.get("status") or "unknown") for payload in payloads)
    foreground_windows = [
        value for phase in typed_phases if (value := _foreground_window_ms(phase)) is not None
    ]

    metrics = {
        "foreground_window_ms": distribution(foreground_windows),
        "fast_gi_ttft_ms": distribution(
            _metric_values(typed_phases, "requests", "fast_gi_canary", "ttft_ms")
        ),
        "fast_gi_elapsed_ms": distribution(
            _metric_values(typed_phases, "requests", "fast_gi_canary", "elapsed_ms")
        ),
        "fast_planner_ttft_ms": distribution(
            _metric_values(typed_phases, "requests", "fast_planner_canary", "ttft_ms")
        ),
        "fast_planner_elapsed_ms": distribution(
            _metric_values(typed_phases, "requests", "fast_planner_canary", "elapsed_ms")
        ),
        "deliberative_ttft_ms": distribution(
            _metric_values(typed_phases, "requests", "deliberative", "ttft_ms")
        ),
        "deliberative_elapsed_ms": distribution(
            _metric_values(typed_phases, "requests", "deliberative", "elapsed_ms")
        ),
        "tts_first_audio_ms": distribution(
            _metric_values(
                typed_phases,
                "tts",
                "under_foreground_and_deliberative_load",
                "first_audio_ms",
            )
        ),
        "tts_elapsed_ms": distribution(
            _metric_values(
                typed_phases,
                "tts",
                "under_foreground_and_deliberative_load",
                "elapsed_ms",
            )
        ),
        "peak_gpu_memory_used_mib": distribution(
            _metric_values(payloads, "resources", "peak_gpu_memory_used_mib")
        ),
        "peak_gpu_utilization_percent": distribution(
            _metric_values(payloads, "resources", "peak_gpu_utilization_percent")
        ),
    }

    sample_count = len(payloads)
    clean_count = sum(payload.get("git_dirty") is False for payload in payloads)
    foreground_before_deep_count = sum(
        phase.get("foreground_completed_before_deep") is True for phase in typed_phases
    )
    deep_active_planner_count = sum(
        phase.get("deep_active_at_fast_planner_start") is True for phase in typed_phases
    )
    tts_sample_count = metrics["tts_first_audio_ms"].get("count", 0)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "claim_boundary": (
            "Repeated provider-level foreground-under-deliberative-load timing distributions "
            "only; not an Agent workflow, PresentationCommit, audible playback, simulator, "
            "target, physical robot, or provider-promotion decision."
        ),
        "label": label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
        "source": {
            "discovered_json_count": len(paths),
            "included_sample_count": sample_count,
            "ignored_json_count": len(ignored),
            "ignored_paths": ignored,
            "paths": [str(path) for path, _ in provider_samples],
            "clean_git_sample_count": clean_count,
        },
        "outcomes": {
            "run_status_counts": dict(sorted(run_statuses.items())),
            "phase_status_counts": dict(sorted(phase_statuses.items())),
            "foreground_completed_before_deep_count": foreground_before_deep_count,
            "foreground_completed_before_deep_rate": round(
                foreground_before_deep_count / sample_count, 6
            ),
            "deep_active_at_fast_planner_start_count": deep_active_planner_count,
            "deep_active_at_fast_planner_start_rate": round(
                deep_active_planner_count / sample_count, 6
            ),
            "tts_sample_count": tts_sample_count,
        },
        "metrics": metrics,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_summary(args.source, label=args.label)
        _write_json(args.output.expanduser(), report)
        print(
            "Inference provider contention summary: "
            f"samples={report['source']['included_sample_count']} "
            f"output={args.output.expanduser()}"
        )
        return 0
    except Exception as exc:
        print(
            f"inference-provider-summary error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
