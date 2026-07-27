#!/usr/bin/env python3
"""Run the source-bound Cognitive Gateway/Core qualification workflow.

This command coordinates existing evidence collectors and verifiers. It does not
supply semantic expectations to Chromie's models, approve human review, alter
runtime policy, or grant release qualification.
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
    ROOT / "benchmarks" / "manifests" / "cognitive_gateway_core_qualification_v1.json"
)
DEFAULT_ACCEPTANCE_ROOT = ROOT / ".chromie" / "acceptance" / "cognitive-gateway-core"
DEFAULT_COMPOSE_OVERRIDE = ROOT / ".chromie" / "voice-runtime" / "compose.voice-mujoco.yaml"
DEFAULT_ORCHESTRATOR_ENV = ROOT / ".chromie" / "voice-runtime" / "orchestrator.env"
DEFAULT_CAPABILITY_MANIFEST = ROOT / "capabilities" / "soridormi.json"


@dataclass(frozen=True)
class WorkflowPaths:
    root: Path
    state: Path
    logs: Path
    runtime_identity: Path
    live_dir: Path
    live_summary: Path
    mujoco_dir: Path
    mujoco_summary: Path
    cancellation_dir: Path
    cancellation_summary: Path
    human_review: Path
    qualification: Path


@dataclass(frozen=True)
class StageSpec:
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


def _artifact_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"expected artifact was not created: {resolved}")
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _paths(root: Path) -> WorkflowPaths:
    resolved = root.expanduser().resolve()
    return WorkflowPaths(
        root=resolved,
        state=resolved / "workflow-state.json",
        logs=resolved / "logs",
        runtime_identity=resolved / "runtime-identity.json",
        live_dir=resolved / "live-text",
        live_summary=resolved / "live-text" / "summary.json",
        mujoco_dir=resolved / "mujoco",
        mujoco_summary=resolved / "mujoco" / "summary.json",
        cancellation_dir=resolved / "active-cancel",
        cancellation_summary=resolved / "active-cancel" / "summary.json",
        human_review=resolved / "human-review.json",
        qualification=resolved / "qualification.json",
    )


def _initial_state(paths: WorkflowPaths, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "run_id": paths.root.name,
        "evidence_root": str(paths.root),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "stages": {},
        "qualification": {
            "issue_closure_eligible": False,
            "release_qualified": False,
            "human_review_required": True,
        },
    }


def _load_or_create_state(
    paths: WorkflowPaths,
    manifest: dict[str, Any],
    *,
    resume: bool,
) -> dict[str, Any]:
    if paths.state.is_file():
        state = _read_json(paths.state)
        if state.get("qualification_id") != manifest.get("qualification_id"):
            raise ValueError("workflow state belongs to a different qualification")
        if not resume:
            raise FileExistsError(
                f"workflow state already exists at {paths.state}; use --resume or a new evidence root"
            )
        return state
    if resume:
        raise FileNotFoundError(f"cannot resume; workflow state does not exist: {paths.state}")
    return _initial_state(paths, manifest)


def _write_state(paths: WorkflowPaths, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _stage_is_resumable(state: dict[str, Any], stage: StageSpec) -> bool:
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


def _run_stage(
    paths: WorkflowPaths,
    state: dict[str, Any],
    stage: StageSpec,
    *,
    resume: bool,
) -> None:
    if resume and _stage_is_resumable(state, stage):
        print(f"[gateway-core-workflow] resume: {stage.name} already complete")
        return

    paths.logs.mkdir(parents=True, exist_ok=True)
    log_path = paths.logs / f"{stage.name}.log"
    stages = state.setdefault("stages", {})
    stages[stage.name] = {
        "status": "running",
        "started_at": _utc_now(),
        "command": list(stage.command),
        "log": str(log_path),
        "artifacts": [],
    }
    _write_state(paths, state)
    print(f"[gateway-core-workflow] running: {stage.name}")
    print("[gateway-core-workflow] command: " + " ".join(stage.command))

    completed = subprocess.run(
        list(stage.command),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    log_path.write_text(output, encoding="utf-8")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")

    item = stages[stage.name]
    item["completed_at"] = _utc_now()
    item["exit_code"] = completed.returncode
    if completed.returncode != 0:
        item["status"] = "failed"
        _write_state(paths, state)
        raise RuntimeError(
            f"stage {stage.name} failed with exit code {completed.returncode}; see {log_path}"
        )
    item["artifacts"] = [_artifact_record(path) for path in stage.artifacts]
    item["status"] = "completed"
    _write_state(paths, state)


def _flag(value: bool, name: str) -> str:
    return f"--{name}" if value else f"--no-{name}"


def _collect_stages(
    args: argparse.Namespace,
    paths: WorkflowPaths,
    manifest: dict[str, Any],
) -> list[StageSpec]:
    python = str(Path(args.python).expanduser())
    common_agent = ("--agent-url", args.agent_url)
    common_provider = ("--soridormi-mcp-url", args.soridormi_mcp_url)
    speaker_flag = _flag(args.speaker, "speaker")

    simulator = manifest.get("simulator_expectations")
    required_skills = (
        simulator.get("required_terminal_skills")
        if isinstance(simulator, dict)
        and isinstance(simulator.get("required_terminal_skills"), list)
        else []
    )
    cancellation = manifest.get("cancellation_expectations")
    if not isinstance(cancellation, dict):
        raise ValueError("qualification manifest has no cancellation expectations")
    command_text = str(cancellation.get("command_text") or "").strip()
    interrupt_text = str(cancellation.get("interrupt_text") or "").strip()
    required_skill = str(cancellation.get("required_skill") or "").strip()
    if not command_text or not interrupt_text or not required_skill:
        raise ValueError("qualification cancellation expectations are incomplete")

    identity_command: list[str] = [
        python,
        "scripts/capture_runtime_identity.py",
        "--compose-override",
        str(args.compose_override),
        "--orchestrator-env",
        str(args.orchestrator_env),
        "--capability-manifest",
        str(args.capability_manifest),
        "--output",
        str(paths.runtime_identity),
    ]
    if args.runtime_profile:
        identity_command.extend(("--runtime-profile", str(args.runtime_profile)))

    live_command = [
        python,
        "scripts/cognitive_gateway_core_live_text.py",
        "--manifest",
        str(args.manifest),
        "--runtime-identity",
        str(paths.runtime_identity),
        "--output-dir",
        str(paths.live_dir),
        *common_agent,
        "--timeout-s",
        str(args.timeout_s),
        speaker_flag,
    ]

    mujoco_command = [
        python,
        "scripts/interaction_text_mujoco_check.py",
        "--runtime-identity",
        str(paths.runtime_identity),
        "--soridormi-repo",
        str(args.soridormi_repo),
        "--manifest",
        str(args.capability_manifest),
        "--evidence-dir",
        str(paths.mujoco_dir),
        *common_agent,
        *common_provider,
        "--timeout-s",
        str(args.timeout_s),
        speaker_flag,
        "--expect-route",
        "robot_action",
        "--reject-internal-speech",
    ]
    for skill_id in required_skills:
        mujoco_command.extend(("--expect-skill", str(skill_id)))

    cancellation_command = [
        python,
        "scripts/interaction_text_mujoco_check.py",
        command_text,
        "--runtime-identity",
        str(paths.runtime_identity),
        "--soridormi-repo",
        str(args.soridormi_repo),
        "--manifest",
        str(args.capability_manifest),
        "--evidence-dir",
        str(paths.cancellation_dir),
        *common_agent,
        *common_provider,
        "--timeout-s",
        str(args.timeout_s),
        "--interrupt-start-timeout-s",
        str(args.interrupt_start_timeout_s),
        speaker_flag,
        "--expect-route",
        "robot_action",
        "--interrupt-text",
        interrupt_text,
        "--interrupt-skill-prefix",
        required_skill,
        "--expect-cancelled",
        "--reject-internal-speech",
    ]

    review_command = [
        python,
        "scripts/create_cognitive_gateway_core_review.py",
        "--manifest",
        str(args.manifest),
        "--runtime-identity",
        str(paths.runtime_identity),
        "--live-summary",
        str(paths.live_summary),
        "--mujoco-summary",
        str(paths.mujoco_summary),
        "--cancellation-summary",
        str(paths.cancellation_summary),
        "--reviewer",
        args.reviewer,
        "--output",
        str(paths.human_review),
    ]

    return [
        StageSpec("runtime-identity", tuple(identity_command), (paths.runtime_identity,)),
        StageSpec("live-text", tuple(live_command), (paths.live_summary,)),
        StageSpec("mujoco", tuple(mujoco_command), (paths.mujoco_summary,)),
        StageSpec(
            "active-cancellation",
            tuple(cancellation_command),
            (paths.cancellation_summary,),
        ),
        StageSpec("human-review-template", tuple(review_command), (paths.human_review,)),
    ]


def _finalize_stage(args: argparse.Namespace, paths: WorkflowPaths) -> StageSpec:
    return StageSpec(
        "final-verification",
        (
            str(Path(args.python).expanduser()),
            "scripts/verify_cognitive_gateway_core_qualification.py",
            "--manifest",
            str(args.manifest),
            "--runtime-identity",
            str(paths.runtime_identity),
            "--live-summary",
            str(paths.live_summary),
            "--mujoco-summary",
            str(paths.mujoco_summary),
            "--cancellation-summary",
            str(paths.cancellation_summary),
            "--human-review",
            str(paths.human_review),
            "--output",
            str(paths.qualification),
        ),
        (paths.qualification,),
    )


def _resolve_evidence_root(value: Path | None, *, require_existing: bool) -> Path:
    if value is None:
        if require_existing:
            raise ValueError("--evidence-root is required for this command")
        return DEFAULT_ACCEPTANCE_ROOT / _run_id()
    return value.expanduser().resolve()


def collect(args: argparse.Namespace) -> int:
    manifest = _read_json(args.manifest.expanduser().resolve())
    paths = _paths(_resolve_evidence_root(args.evidence_root, require_existing=False))
    paths.root.mkdir(parents=True, exist_ok=True)
    state = _load_or_create_state(paths, manifest, resume=args.resume)
    _write_state(paths, state)
    for stage in _collect_stages(args, paths, manifest):
        _run_stage(paths, state, stage, resume=args.resume)
    print(f"[gateway-core-workflow] collection complete: {paths.root}")
    print(
        "[gateway-core-workflow] review the retained artifacts, update "
        f"{paths.human_review} from pending to an explicit reviewed decision, "
        "then run the finalize command."
    )
    print(
        "[gateway-core-workflow] finalize: "
        f"{Path(args.python).name} scripts/run_cognitive_gateway_core_qualification.py "
        f"finalize --evidence-root {paths.root}"
    )
    return 0


def finalize(args: argparse.Namespace) -> int:
    paths = _paths(_resolve_evidence_root(args.evidence_root, require_existing=True))
    manifest = _read_json(args.manifest.expanduser().resolve())
    state = _load_or_create_state(paths, manifest, resume=True)
    _run_stage(paths, state, _finalize_stage(args, paths), resume=False)
    report = _read_json(paths.qualification)
    eligible = bool(
        isinstance(report.get("qualification"), dict)
        and report["qualification"].get("issue_closure_eligible") is True
    )
    state["qualification"] = {
        "issue_closure_eligible": eligible,
        "release_qualified": False,
        "human_review_required": True,
        "report_sha256": _sha256(paths.qualification),
    }
    _write_state(paths, state)
    if not eligible:
        print("[gateway-core-workflow][error] bundle is not eligible for Issue closure")
        return 1
    print(f"[gateway-core-workflow] Issue closure eligible: {paths.qualification}")
    return 0


def status(args: argparse.Namespace) -> int:
    paths = _paths(_resolve_evidence_root(args.evidence_root, require_existing=True))
    state = _read_json(paths.state)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--evidence-root", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Capture one source-bound live-text, MuJoCo, cancellation, and pending-review bundle.",
    )
    _add_common(collect_parser)
    collect_parser.add_argument("--resume", action="store_true")
    collect_parser.add_argument(
        "--reviewer",
        default=os.getenv("USER", "").strip(),
        help="Identity written into the pending human-review template.",
    )
    collect_parser.add_argument("--soridormi-repo", type=Path, default=ROOT.parent / "soridormi")
    collect_parser.add_argument("--compose-override", type=Path, default=DEFAULT_COMPOSE_OVERRIDE)
    collect_parser.add_argument("--orchestrator-env", type=Path, default=DEFAULT_ORCHESTRATOR_ENV)
    collect_parser.add_argument("--runtime-profile", type=Path)
    collect_parser.add_argument("--capability-manifest", type=Path, default=DEFAULT_CAPABILITY_MANIFEST)
    collect_parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    collect_parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    collect_parser.add_argument("--timeout-s", type=float, default=180.0)
    collect_parser.add_argument("--interrupt-start-timeout-s", type=float, default=30.0)
    collect_parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Play retained responses. Headless no-speaker collection is the default.",
    )

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Verify an explicitly reviewed retained bundle and update workflow state.",
    )
    _add_common(finalize_parser)

    status_parser = subparsers.add_parser(
        "status",
        help="Show the retained workflow state and artifact fingerprints.",
    )
    _add_common(status_parser)
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
        print(f"[gateway-core-workflow][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
