#!/usr/bin/env python3
"""Run the source-bound live Agent Skill and weather qualification workflow.

The workflow reuses the deployed text entrypoint, retains exact runtime events,
and creates a pending fingerprint-bound human review. It does not select Skills,
change prompts, approve review, or grant release qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "agent_skill_weather_qualification_v1.json"
)
DEFAULT_ROOT = ROOT / ".chromie" / "acceptance" / "agent-skill-weather"


@dataclass(frozen=True)
class Paths:
    root: Path
    state: Path
    logs: Path
    live_dir: Path
    live_summary: Path
    cognitive_events: Path
    runtime_identity: Path
    automatic_report: Path
    human_review: Path
    qualification: Path


@dataclass(frozen=True)
class Stage:
    name: str
    command: tuple[str, ...]
    artifacts: tuple[Path, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"expected artifact was not created: {resolved}")
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _paths(root: Path, runtime_identity: Path | None = None) -> Paths:
    resolved = root.expanduser().resolve()
    identity = (
        runtime_identity.expanduser().resolve()
        if runtime_identity is not None
        else resolved / "runtime-identity.json"
    )
    return Paths(
        root=resolved,
        state=resolved / "workflow-state.json",
        logs=resolved / "logs",
        live_dir=resolved / "live-text",
        live_summary=resolved / "live-text" / "summary.json",
        cognitive_events=resolved / "live-text" / "cognitive_events.jsonl",
        runtime_identity=identity,
        automatic_report=resolved / "automatic-verification.json",
        human_review=resolved / "human-review.json",
        qualification=resolved / "qualification.json",
    )


def _write_state(paths: Paths, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _initial_state(paths: Paths, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "run_id": paths.root.name,
        "evidence_root": str(paths.root),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "stages": {},
        "qualification": {
            "track_closure_eligible": False,
            "release_qualified": False,
            "human_review_required": True,
        },
    }


def _load_state(paths: Paths, manifest: dict[str, Any], *, resume: bool) -> dict[str, Any]:
    if paths.state.is_file():
        state = _read_json(paths.state)
        if state.get("qualification_id") != manifest.get("qualification_id"):
            raise ValueError("workflow state belongs to a different qualification")
        if not resume:
            raise FileExistsError(
                f"workflow state already exists at {paths.state}; use --resume or a new root"
            )
        return state
    if resume:
        raise FileNotFoundError(f"cannot resume; missing workflow state {paths.state}")
    return _initial_state(paths, manifest)


def _resumable(state: dict[str, Any], stage: Stage) -> bool:
    stages = state.get("stages")
    item = stages.get(stage.name) if isinstance(stages, dict) else None
    if not isinstance(item, dict) or item.get("status") != "completed":
        return False
    retained = item.get("artifacts")
    if not isinstance(retained, list) or len(retained) != len(stage.artifacts):
        return False
    by_path = {
        str(value.get("path") or ""): value
        for value in retained
        if isinstance(value, dict)
    }
    for artifact in stage.artifacts:
        resolved = artifact.expanduser().resolve()
        record = by_path.get(str(resolved))
        if not resolved.is_file() or not isinstance(record, dict):
            return False
        if record.get("sha256") != _sha256(resolved):
            return False
    return True


def _run(paths: Paths, state: dict[str, Any], stage: Stage, *, resume: bool) -> None:
    if resume and _resumable(state, stage):
        print(f"[agent-skill-weather-workflow] resume: {stage.name} already complete")
        return
    paths.logs.mkdir(parents=True, exist_ok=True)
    log = paths.logs / f"{stage.name}.log"
    stages = state.setdefault("stages", {})
    stages[stage.name] = {
        "status": "running",
        "started_at": _utc_now(),
        "command": list(stage.command),
        "log": str(log),
        "artifacts": [],
    }
    _write_state(paths, state)
    print(f"[agent-skill-weather-workflow] running: {stage.name}")
    completed = subprocess.run(
        list(stage.command),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    log.write_text(output, encoding="utf-8")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    item = stages[stage.name]
    item["completed_at"] = _utc_now()
    item["exit_code"] = completed.returncode
    if completed.returncode != 0:
        item["status"] = "failed"
        _write_state(paths, state)
        raise RuntimeError(
            f"stage {stage.name} failed with exit code {completed.returncode}; see {log}"
        )
    item["artifacts"] = [_record(path) for path in stage.artifacts]
    item["status"] = "completed"
    _write_state(paths, state)


def _root(value: Path | None, *, existing: bool) -> Path:
    if value is None:
        if existing:
            raise ValueError("--evidence-root is required")
        return DEFAULT_ROOT / _run_id()
    return value.expanduser().resolve()


def _collect_stages(args: argparse.Namespace, paths: Paths) -> list[Stage]:
    python = str(Path(args.python).expanduser())
    live = Stage(
        "live-text",
        (
            python,
            "scripts/cognitive_gateway_core_live_text.py",
            "--manifest",
            str(args.manifest),
            "--runtime-identity",
            str(paths.runtime_identity),
            "--output-dir",
            str(paths.live_dir),
            "--agent-url",
            args.agent_url,
            "--timeout-s",
            str(args.timeout_s),
            "--speaker" if args.speaker else "--no-speaker",
        ),
        (paths.live_summary, paths.cognitive_events),
    )
    automatic = Stage(
        "automatic-verification",
        (
            python,
            "scripts/verify_agent_skill_weather_qualification.py",
            "--manifest",
            str(args.manifest),
            "--runtime-identity",
            str(paths.runtime_identity),
            "--live-summary",
            str(paths.live_summary),
            "--cognitive-events",
            str(paths.cognitive_events),
            "--allow-pending-review",
            "--output",
            str(paths.automatic_report),
        ),
        (paths.automatic_report,),
    )
    review = Stage(
        "human-review-template",
        (
            python,
            "scripts/create_agent_skill_weather_review.py",
            "--manifest",
            str(args.manifest),
            "--runtime-identity",
            str(paths.runtime_identity),
            "--live-summary",
            str(paths.live_summary),
            "--cognitive-events",
            str(paths.cognitive_events),
            "--reviewer",
            args.reviewer,
            "--output",
            str(paths.human_review),
        ),
        (paths.human_review,),
    )
    return [live, automatic, review]


def collect(args: argparse.Namespace) -> int:
    manifest = _read_json(args.manifest.expanduser().resolve())
    root = _root(args.evidence_root, existing=False)
    paths = _paths(root, args.runtime_identity)
    if not paths.runtime_identity.is_file():
        raise FileNotFoundError(
            "source-bound runtime identity is required; collect Gateway/Core identity first"
        )
    paths.root.mkdir(parents=True, exist_ok=True)
    state = _load_state(paths, manifest, resume=args.resume)
    state["runtime_identity"] = _record(paths.runtime_identity)
    _write_state(paths, state)
    for stage in _collect_stages(args, paths):
        _run(paths, state, stage, resume=args.resume)
    print(f"[agent-skill-weather-workflow] collection complete: {paths.root}")
    print(f"[agent-skill-weather-workflow] review and approve: {paths.human_review}")
    return 0


def finalize(args: argparse.Namespace) -> int:
    manifest = _read_json(args.manifest.expanduser().resolve())
    paths = _paths(_root(args.evidence_root, existing=True), args.runtime_identity)
    state = _load_state(paths, manifest, resume=True)
    stage = Stage(
        "final-verification",
        (
            str(Path(args.python).expanduser()),
            "scripts/verify_agent_skill_weather_qualification.py",
            "--manifest",
            str(args.manifest),
            "--runtime-identity",
            str(paths.runtime_identity),
            "--live-summary",
            str(paths.live_summary),
            "--cognitive-events",
            str(paths.cognitive_events),
            "--human-review",
            str(paths.human_review),
            "--output",
            str(paths.qualification),
        ),
        (paths.qualification,),
    )
    _run(paths, state, stage, resume=False)
    report = _read_json(paths.qualification)
    eligible = bool(
        isinstance(report.get("qualification"), dict)
        and report["qualification"].get("track_closure_eligible") is True
    )
    state["qualification"] = {
        "track_closure_eligible": eligible,
        "release_qualified": False,
        "human_review_required": True,
        "report_sha256": _sha256(paths.qualification),
    }
    _write_state(paths, state)
    return 0 if eligible else 1


def status(args: argparse.Namespace) -> int:
    paths = _paths(_root(args.evidence_root, existing=True), args.runtime_identity)
    print(json.dumps(_read_json(paths.state), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--runtime-identity", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    _common(collect_parser)
    collect_parser.add_argument("--resume", action="store_true")
    collect_parser.add_argument("--reviewer", default=os.getenv("USER", "").strip())
    collect_parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    collect_parser.add_argument("--timeout-s", type=float, default=180.0)
    collect_parser.add_argument(
        "--speaker", action=argparse.BooleanOptionalAction, default=False
    )
    finalize_parser = sub.add_parser("finalize")
    _common(finalize_parser)
    status_parser = sub.add_parser("status")
    _common(status_parser)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "collect":
            if not args.reviewer:
                raise ValueError("--reviewer is required when USER is unavailable")
            return collect(args)
        if args.command == "finalize":
            return finalize(args)
        if args.command == "status":
            return status(args)
        raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        print(f"[agent-skill-weather-workflow][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
