#!/usr/bin/env python3
"""Validate PR7 goal-driven runtime scenarios and retained operational evidence.

This tool deliberately separates deterministic Level A scenarios, live-text
operational evidence, and simulator execution evidence. It never upgrades one
evidence class into release readiness.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.behavior_scenarios import (  # noqa: E402
    DEFAULT_SCENARIO_ROOT,
    load_scenarios,
    run_scenarios_sync,
)

DEFAULT_EVENTS = ROOT / ".chromie" / "evidence" / "cognitive-runtime" / "events.jsonl"
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "acceptance" / "cognitive-runtime"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        events.append(value)
    return events


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _soridormi_revision() -> str | None:
    try:
        payload = _read_json(ROOT / "capabilities" / "soridormi.json")
    except Exception:
        return None
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("upstream_commit"):
        return None
    return str(metadata["upstream_commit"])


def _level_a_report() -> dict[str, Any]:
    scenarios = load_scenarios(DEFAULT_SCENARIO_ROOT, suites={"cognitive_runtime"})
    report = run_scenarios_sync(scenarios)
    return {
        "evidence_class": "automated_level_a",
        "ok": bool(report.get("ok")),
        "case_count": int(report.get("case_count", 0)),
        "passed": int(report.get("passed", 0)),
        "failed": int(report.get("failed", 0)),
        "cases": report.get("cases", []),
    }


def _events_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(str(item.get("status") or "unknown") for item in events)
    lanes = Counter(str(item.get("lane") or "unknown") for item in events)
    modes = Counter(str(item.get("mode") or "unknown") for item in events)
    latencies = [
        float((item.get("timings_ms") or {}).get("total", 0.0))
        for item in events
        if isinstance(item.get("timings_ms"), dict)
    ]
    applied_skills: list[str] = []
    for item in events:
        interaction = item.get("interaction")
        if isinstance(interaction, dict):
            applied_skills.extend(str(value) for value in interaction.get("skill_ids") or [])
    return {
        "evidence_class": "live_text_operational",
        "event_count": len(events),
        "status_counts": dict(sorted(status.items())),
        "lane_counts": dict(sorted(lanes.items())),
        "mode_counts": dict(sorted(modes.items())),
        "mean_total_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "applied_skill_ids": applied_skills,
    }


def _run_provenance(summary: dict[str, Any]) -> dict[str, Any]:
    provenance = summary.get("run_provenance") or summary.get("provenance") or {}
    if not isinstance(provenance, dict):
        provenance = {}
    chromie = provenance.get("chromie") or {}
    soridormi = provenance.get("soridormi") or {}
    chromie_revision = (
        provenance.get("chromie_revision")
        or (chromie.get("revision") if isinstance(chromie, dict) else None)
        or summary.get("chromie_revision")
    )
    soridormi_revision = (
        provenance.get("soridormi_revision")
        or (
            soridormi.get("upstream_revision") or soridormi.get("revision")
            if isinstance(soridormi, dict)
            else None
        )
        or summary.get("soridormi_revision")
    )
    semantic_runtime = provenance.get("semantic_runtime") or {}
    return {
        "chromie_revision": str(chromie_revision) if chromie_revision else None,
        "chromie_dirty": (
            chromie.get("dirty") if isinstance(chromie, dict) else None
        ),
        "soridormi_revision": (
            str(soridormi_revision) if soridormi_revision else None
        ),
        "soridormi_checkout_revision": (
            str(soridormi.get("checkout_revision"))
            if isinstance(soridormi, dict) and soridormi.get("checkout_revision")
            else None
        ),
        "soridormi_checkout_dirty": (
            soridormi.get("checkout_dirty")
            if isinstance(soridormi, dict)
            else None
        ),
        "soridormi_source_binding": (
            soridormi.get("source_binding")
            if isinstance(soridormi, dict)
            else None
        ),
        "soridormi_endpoint_revision": (
            str(soridormi.get("endpoint_revision"))
            if isinstance(soridormi, dict) and soridormi.get("endpoint_revision")
            else None
        ),
        "semantic_runtime_path": (
            semantic_runtime.get("path")
            if isinstance(semantic_runtime, dict)
            else None
        ),
        "cognitive_runtime_mode": (
            (
                semantic_runtime.get("configured_cognitive_runtime_mode")
                or semantic_runtime.get("cognitive_runtime_mode")
            )
            if isinstance(semantic_runtime, dict)
            else None
        ),
        "cognitive_runtime_selected_for_route": (
            semantic_runtime.get("cognitive_runtime_selected_for_route")
            if isinstance(semantic_runtime, dict)
            else None
        ),
    }


def _simulator_report(
    summary: dict[str, Any] | None,
    *,
    expected_chromie_revision: str | None,
    expected_soridormi_revision: str | None,
) -> dict[str, Any] | None:
    if summary is None:
        return None
    cognitive = summary.get("cognitive_runtime")
    execution = summary.get("execution")
    status_before = summary.get("status_before")
    status_after = summary.get("status_after")
    cognitive_status = cognitive.get("status") if isinstance(cognitive, dict) else None
    execution_status = execution.get("status") if isinstance(execution, dict) else None
    run_provenance = _run_provenance(summary)
    chromie_revision = run_provenance["chromie_revision"]
    soridormi_revision = run_provenance["soridormi_revision"]
    provenance_errors: list[str] = []
    if not chromie_revision:
        provenance_errors.append("simulator run has no recorded Chromie revision")
    elif not expected_chromie_revision:
        provenance_errors.append("current Chromie revision could not be determined")
    elif chromie_revision != expected_chromie_revision:
        provenance_errors.append(
            f"simulator Chromie revision {chromie_revision!r} does not match "
            f"expected revision {expected_chromie_revision!r}"
        )
    if run_provenance["chromie_dirty"] is not False:
        provenance_errors.append(
            "simulator run did not record a clean Chromie worktree"
        )
    if not soridormi_revision:
        provenance_errors.append("simulator run has no recorded Soridormi revision")
    elif not expected_soridormi_revision:
        provenance_errors.append("current Soridormi revision could not be determined")
    elif soridormi_revision != expected_soridormi_revision:
        provenance_errors.append(
            f"simulator Soridormi revision {soridormi_revision!r} does not match "
            f"expected revision {expected_soridormi_revision!r}"
        )
    if run_provenance["soridormi_checkout_revision"] != expected_soridormi_revision:
        provenance_errors.append(
            "simulator run does not bind the declared paired Soridormi checkout to "
            f"expected revision {expected_soridormi_revision!r}"
        )
    if run_provenance["soridormi_checkout_dirty"] is not False:
        provenance_errors.append(
            "simulator run did not record a clean declared paired Soridormi checkout"
        )
    if run_provenance["soridormi_source_binding"] != "endpoint_reported_revision":
        provenance_errors.append(
            "simulator run does not bind the Soridormi endpoint to its reported source revision"
        )
    if run_provenance["soridormi_endpoint_revision"] != expected_soridormi_revision:
        provenance_errors.append(
            "simulator endpoint source revision does not match the expected Soridormi revision"
        )
    if run_provenance["semantic_runtime_path"] != "goal_driven_cognitive_runtime":
        provenance_errors.append(
            "simulator run was not recorded on the goal-driven cognitive runtime path"
        )
    if run_provenance["cognitive_runtime_mode"] != "apply":
        provenance_errors.append(
            "simulator run was not recorded with cognitive runtime mode 'apply'"
        )
    if run_provenance["cognitive_runtime_selected_for_route"] is not True:
        provenance_errors.append(
            "simulator run did not select the cognitive runtime for its route"
        )
    sim_status = bool(
        isinstance(status_before, dict)
        and isinstance(status_after, dict)
        and status_before.get("mode") == "sim"
        and status_after.get("mode") == "sim"
        and status_before.get("backend") == "runtime"
        and status_after.get("backend") == "runtime"
    )
    if not sim_status:
        provenance_errors.append(
            "simulator run does not record pre/post mode='sim' with backend='runtime'"
        )
    def records_safe_idle(status: Any) -> bool:
        return bool(
            isinstance(status, dict)
            and status.get("safe_idle") is True
            and "active_task" in status
            and status.get("active_task") is None
            and status.get("emergency_stop") is False
            and status.get("fallen") is False
        )

    safe_idle_before = records_safe_idle(status_before)
    safe_idle_after = records_safe_idle(status_after)
    if not safe_idle_before:
        provenance_errors.append(
            "simulator run does not record an explicitly safe-idle pre-run state"
        )
    if not safe_idle_after:
        provenance_errors.append(
            "simulator run does not record an explicitly safe-idle post-run state"
        )
    execution_results = (
        execution.get("results")
        if isinstance(execution, dict) and isinstance(execution.get("results"), list)
        else []
    )
    completed_soridormi_results = [
        item
        for item in execution_results
        if isinstance(item, dict)
        and str(item.get("skill_id") or "").startswith("soridormi.")
        and item.get("status") == "completed"
        and isinstance(item.get("output"), dict)
        and item["output"].get("mode") == "sim"
    ]
    if not completed_soridormi_results:
        provenance_errors.append(
            "simulator run has no completed soridormi.* result with output mode='sim'"
        )
    target_validated = bool(
        summary.get("ok") is True
        and cognitive_status == "applied"
        and execution_status == "completed"
        and sim_status
        and completed_soridormi_results
        and safe_idle_before
        and safe_idle_after
        and not provenance_errors
    )
    return {
        "evidence_class": (
            "simulator_execution" if sim_status else "unverified_target_execution"
        ),
        "ok": bool(summary.get("ok")),
        "cognitive_status": cognitive_status,
        "execution_status": execution_status,
        "simulator_status_verified": sim_status,
        "completed_soridormi_results": len(completed_soridormi_results),
        "safe_idle_before": safe_idle_before,
        "safe_idle_after": safe_idle_after,
        "safe_idle": safe_idle_before and safe_idle_after,
        "run_provenance": run_provenance,
        "expected_provenance": {
            "chromie_revision": expected_chromie_revision,
            "soridormi_revision": expected_soridormi_revision,
        },
        "provenance_matches": not provenance_errors,
        "provenance_errors": provenance_errors,
        "target_validated": target_validated,
        "summary_path": summary.get("evidence_dir"),
    }


def build_bundle(
    *,
    events_path: Path | None,
    text_mujoco_summary: Path | None,
    expected_chromie_revision: str | None = None,
    expected_soridormi_revision: str | None = None,
) -> dict[str, Any]:
    generator_chromie_revision = _git_revision()
    if expected_chromie_revision is None:
        expected_chromie_revision = generator_chromie_revision
    if expected_soridormi_revision is None:
        expected_soridormi_revision = _soridormi_revision()
    level_a = _level_a_report()
    events = _read_events(events_path) if events_path is not None else []
    live_text = _events_report(events) if events_path is not None else None
    simulator_summary = _read_json(text_mujoco_summary) if text_mujoco_summary else None
    simulator = _simulator_report(
        simulator_summary,
        expected_chromie_revision=expected_chromie_revision,
        expected_soridormi_revision=expected_soridormi_revision,
    )
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_generator": {
            "chromie_revision": generator_chromie_revision,
            "soridormi_revision": _soridormi_revision(),
        },
        "status_vocabulary": {
            "implemented": True,
            "automatically_verified": bool(level_a["ok"]),
            "target_validated": bool(simulator and simulator["target_validated"]),
            "release_ready": False,
        },
        "level_a": level_a,
        "live_text": live_text,
        "simulator": simulator,
        "limitations": [
            "Operational JSONL alone is not simulator or physical-robot evidence.",
            "A passing simulator summary is not physical-audio or hardware evidence.",
            "Retained simulator evidence validates the current target only when its "
            "recorded Chromie and Soridormi revisions match the expected source.",
            "This tool never declares release readiness.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["check", "level-a", "evidence", "bundle"],
        default="check",
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=None,
        help=(
            "Operational JSONL to inspect. Evidence mode defaults to the global "
            "cognitive-runtime log; bundle mode includes events only when supplied."
        ),
    )
    parser.add_argument("--text-mujoco-summary", type=Path)
    parser.add_argument("--expected-chromie-revision")
    parser.add_argument("--expected-soridormi-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-applied-lane", action="append", default=[])
    args = parser.parse_args(argv)

    try:
        if args.mode in {"check", "level-a"}:
            payload = _level_a_report()
        elif args.mode == "evidence":
            events_path = args.events or DEFAULT_EVENTS
            events = _read_events(events_path)
            payload = _events_report(events)
            applied_events = [
                item
                for item in events
                if item.get("status") == "applied"
            ]
            applied_lanes = {str(item.get("lane")) for item in applied_events}
            missing = sorted(set(args.require_applied_lane) - applied_lanes)
            payload["required_applied_lanes"] = list(args.require_applied_lane)
            payload["missing_applied_lanes"] = missing
            payload["ok"] = not missing and not payload["status_counts"].get("error", 0)
        else:
            payload = build_bundle(
                events_path=args.events if args.events else None,
                text_mujoco_summary=args.text_mujoco_summary,
                expected_chromie_revision=args.expected_chromie_revision,
                expected_soridormi_revision=args.expected_soridormi_revision,
            )
    except Exception as exc:
        print(f"cognitive runtime acceptance failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    if args.mode in {"check", "level-a", "evidence"}:
        return 0 if payload.get("ok", True) else 1
    if args.text_mujoco_summary is not None:
        return 0 if payload["status_vocabulary"]["target_validated"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
