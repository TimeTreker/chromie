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


def _simulator_report(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    cognitive = summary.get("cognitive_runtime")
    execution = summary.get("execution")
    status_after = summary.get("status_after")
    return {
        "evidence_class": "simulator_execution",
        "ok": bool(summary.get("ok")),
        "cognitive_status": (
            cognitive.get("status") if isinstance(cognitive, dict) else None
        ),
        "execution_status": (
            execution.get("status") if isinstance(execution, dict) else None
        ),
        "safe_idle": bool(
            isinstance(status_after, dict)
            and status_after.get("active_task") is None
            and status_after.get("emergency_stop") is False
            and status_after.get("fallen") is not True
        ),
        "summary_path": summary.get("evidence_dir"),
    }


def build_bundle(
    *,
    events_path: Path | None,
    text_mujoco_summary: Path | None,
) -> dict[str, Any]:
    level_a = _level_a_report()
    events = _read_events(events_path) if events_path is not None else []
    live_text = _events_report(events) if events_path is not None else None
    simulator_summary = _read_json(text_mujoco_summary) if text_mujoco_summary else None
    simulator = _simulator_report(simulator_summary)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chromie_revision": _git_revision(),
        "status_vocabulary": {
            "implemented": True,
            "automatically_verified": bool(level_a["ok"]),
            "target_validated": bool(simulator and simulator["ok"] and simulator["safe_idle"]),
            "release_ready": False,
        },
        "level_a": level_a,
        "live_text": live_text,
        "simulator": simulator,
        "limitations": [
            "Operational JSONL alone is not simulator or physical-robot evidence.",
            "A passing simulator summary is not physical-audio or hardware evidence.",
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
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--text-mujoco-summary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-applied-lane", action="append", default=[])
    args = parser.parse_args(argv)

    try:
        if args.mode in {"check", "level-a"}:
            payload = _level_a_report()
        elif args.mode == "evidence":
            payload = _events_report(_read_events(args.events))
            applied_events = [
                item
                for item in _read_events(args.events)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
