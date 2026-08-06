#!/usr/bin/env python3
"""Close Chromie vocal Goal/Planner Issue #1 with retained Level A/C evidence.

The runner executes the canonical source gate, captures the running deployment
identity, runs the exact retained Chinese walk/sing/blink turn through the
maintained Goal-driven runtime and Soridormi/MuJoCo, and then validates the
resulting Goal, Plan, dispatch, execution, and safe-idle evidence mechanically.

A passing report proves only the Issue #1 contract on the recorded source and
simulator deployment. It does not prove physical microphone, speaker, singing,
or robot hardware behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.evidence_identity import (  # noqa: E402
    RuntimeEvidenceIdentityError,
    load_runtime_evidence_identity,
)

DEFAULT_TEXT = "你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。"
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "acceptance" / "vocal-issue-1"
DEFAULT_RUNTIME_IDENTITY = ROOT / ".chromie" / "evidence" / "runtime-identity.json"
DEFAULT_MANIFEST = ROOT / "capabilities" / "soridormi.json"


class ClosureError(RuntimeError):
    """Raised when closure evidence cannot be collected or read safely."""


def _acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClosureError(f"{path}: expected a JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(
    command: Iterable[str],
    *,
    log_path: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_list = list(command)
    completed = subprocess.run(
        command_list,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + " ".join(command_list) + "\n\n"
        + completed.stdout
        + ("\n[stderr]\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )
    return completed


def _git_text(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ClosureError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _goal_metadata(goal: dict[str, Any]) -> dict[str, Any]:
    metadata = goal.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _goal_signature(goal: dict[str, Any]) -> tuple[str, str, str, bool]:
    metadata = _goal_metadata(goal)
    return (
        str(metadata.get("responsibility_kind") or ""),
        str(metadata.get("execution_lane") or ""),
        str(metadata.get("output_mode") or ""),
        metadata.get("provider_required") is True,
    )


def _outcomes_by_goal(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outcomes = plan.get("goal_outcomes")
    if not isinstance(outcomes, list):
        return {}
    return {
        str(item.get("goal_id") or ""): item
        for item in outcomes
        if isinstance(item, dict) and str(item.get("goal_id") or "")
    }


def _steps_by_id(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return {}
    return {
        str(item.get("step_id") or ""): item
        for item in steps
        if isinstance(item, dict) and str(item.get("step_id") or "")
    }


def _capability_id(item: dict[str, Any]) -> str:
    return str(item.get("capability_id") or item.get("skill_id") or "").strip()


def _source_goal_ids(item: dict[str, Any]) -> set[str]:
    direct = item.get("source_goal_ids")
    metadata = item.get("metadata")
    if not isinstance(direct, list) and isinstance(metadata, dict):
        direct = metadata.get("source_goal_ids")
    if not isinstance(direct, list):
        return set()
    return {str(value).strip() for value in direct if str(value).strip()}


def _safe_idle_errors(status: Any, *, label: str) -> list[str]:
    if not isinstance(status, dict):
        return [f"{label} Soridormi status is missing"]
    errors: list[str] = []
    if status.get("mode") != "sim":
        errors.append(f"{label} Soridormi mode is not sim: {status.get('mode')!r}")
    if status.get("safe_idle") is not True:
        errors.append(f"{label} safe_idle is not true")
    if status.get("active_task") is not None:
        errors.append(f"{label} active_task is not idle")
    if status.get("emergency_stop") is not False:
        errors.append(f"{label} emergency_stop is not false")
    if status.get("fallen") is not False:
        errors.append(f"{label} fallen is not false")
    return errors


def validate_runtime_identity(
    path: Path,
    *,
    expected_chromie_revision: str,
) -> tuple[list[str], dict[str, Any]]:
    """Validate that retained deployment identity binds to this clean source."""

    errors: list[str] = []
    try:
        payload = load_runtime_evidence_identity(path)
    except RuntimeEvidenceIdentityError as exc:
        return [str(exc)], {}
    if payload is None:
        return ["runtime identity file is missing"], {}

    chromie = payload.get("chromie")
    chromie = chromie if isinstance(chromie, dict) else {}
    if chromie.get("revision") != expected_chromie_revision:
        errors.append(
            "runtime identity Chromie revision mismatch: "
            f"{chromie.get('revision')!r} != {expected_chromie_revision!r}"
        )
    if chromie.get("dirty") is not False:
        errors.append("runtime identity does not record a clean Chromie checkout")

    deployment = payload.get("deployment")
    deployment = deployment if isinstance(deployment, dict) else {}
    if deployment.get("complete") is not True:
        errors.append("runtime identity deployment is incomplete")

    qualification = payload.get("qualification")
    qualification = qualification if isinstance(qualification, dict) else {}
    if qualification.get("source_clean") is not True:
        errors.append("runtime identity source_clean qualification is not true")
    if qualification.get("deployment_complete") is not True:
        errors.append("runtime identity deployment_complete qualification is not true")

    return errors, payload


def validate_closure_summary(
    summary: dict[str, Any],
    *,
    expected_chromie_revision: str,
    expected_walk_capability: str,
    expected_blink_capability: str,
    expected_runtime_identity_sha256: str | None = None,
    duration_s: float = 15.0,
    tolerance: float = 0.25,
) -> tuple[list[str], dict[str, Any]]:
    """Validate the exact Issue #1 semantic and live execution contract."""

    errors: list[str] = []
    if summary.get("ok") is not True:
        errors.append("underlying text-to-MuJoCo run did not pass")
        for item in summary.get("errors") or []:
            errors.append(f"underlying:{item}")

    provenance = summary.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    chromie = provenance.get("chromie")
    chromie = chromie if isinstance(chromie, dict) else {}
    if chromie.get("revision") != expected_chromie_revision:
        errors.append(
            "Chromie evidence revision mismatch: "
            f"{chromie.get('revision')!r} != {expected_chromie_revision!r}"
        )
    if chromie.get("dirty") is not False:
        errors.append("Chromie evidence was not collected from a clean checkout")
    runtime_identity = provenance.get("runtime_identity")
    runtime_identity = runtime_identity if isinstance(runtime_identity, dict) else {}
    if runtime_identity.get("complete") is not True:
        errors.append("runtime identity is missing or incomplete")
    identity_sha256 = str(runtime_identity.get("identity_sha256") or "").strip()
    if expected_runtime_identity_sha256 and identity_sha256 != expected_runtime_identity_sha256:
        errors.append(
            "live summary runtime identity mismatch: "
            f"{identity_sha256!r} != {expected_runtime_identity_sha256!r}"
        )
    soridormi = provenance.get("soridormi")
    soridormi = soridormi if isinstance(soridormi, dict) else {}
    endpoint_revision = str(soridormi.get("endpoint_revision") or "").strip()
    checkout_revision = str(soridormi.get("checkout_revision") or "").strip()
    if not endpoint_revision:
        errors.append("Soridormi endpoint did not report its source revision")
    if not checkout_revision:
        errors.append("paired Soridormi checkout revision is missing")
    if endpoint_revision and checkout_revision and endpoint_revision != checkout_revision:
        errors.append(
            "Soridormi endpoint/checkout revision mismatch: "
            f"{endpoint_revision!r} != {checkout_revision!r}"
        )
    if soridormi.get("checkout_dirty") is not False:
        errors.append("paired Soridormi checkout is dirty or unverified")

    errors.extend(_safe_idle_errors(summary.get("status_before"), label="before"))
    errors.extend(_safe_idle_errors(summary.get("status_after"), label="after"))

    route = summary.get("route")
    route = route if isinstance(route, dict) else {}
    if route.get("route") != "robot_action":
        errors.append(f"route is not robot_action: {route.get('route')!r}")

    cognitive = summary.get("cognitive_runtime")
    cognitive = cognitive if isinstance(cognitive, dict) else {}
    if cognitive.get("status") != "applied":
        errors.append(f"Goal-driven runtime status is not applied: {cognitive.get('status')!r}")
    association = cognitive.get("goal_association")
    association = association if isinstance(association, dict) else {}
    goals = association.get("new_goals")
    goals = goals if isinstance(goals, list) else []
    typed_goals = [item for item in goals if isinstance(item, dict)]
    singing_goals = [
        item
        for item in typed_goals
        if _goal_signature(item)
        == ("spoken_response", "speaking", "singing", True)
    ]
    body_goals = [
        item
        for item in typed_goals
        if _goal_signature(item)
        == ("executable_action", "activity", "body_action", True)
    ]
    if len(singing_goals) != 1:
        errors.append(f"expected exactly one typed singing Goal, got {len(singing_goals)}")
    if len(body_goals) < 2:
        errors.append(f"expected at least two typed body Goals, got {len(body_goals)}")
    if singing_goals and singing_goals[0].get("resource_responsibility") is not None:
        errors.append("singing Goal incorrectly carries resource_responsibility")

    singing_goal_id = (
        str(singing_goals[0].get("goal_id") or "") if singing_goals else ""
    )
    body_goal_ids = {
        str(item.get("goal_id") or "")
        for item in body_goals
        if str(item.get("goal_id") or "")
    }

    plan = cognitive.get("terminal_plan")
    if not isinstance(plan, dict):
        plan = cognitive.get("fast_plan")
    plan = plan if isinstance(plan, dict) else {}
    outcomes = _outcomes_by_goal(plan)
    steps = _steps_by_id(plan)
    if singing_goal_id:
        singing_outcome = outcomes.get(singing_goal_id)
        if not isinstance(singing_outcome, dict):
            errors.append("terminal Plan has no outcome for the singing Goal")
        else:
            disposition = singing_outcome.get("disposition")
            if disposition not in {"unavailable", "refused"}:
                errors.append(
                    "singing Goal was not honestly unavailable/refused: "
                    f"{disposition!r}"
                )
            if singing_outcome.get("step_ids"):
                errors.append("singing unavailable/refused outcome references executable steps")

    for step_id, step in steps.items():
        owners = _source_goal_ids(step)
        if singing_goal_id and singing_goal_id in owners:
            errors.append(
                f"singing Goal incorrectly owns executable Activity step {step_id!r}"
            )

    expected_capabilities = {
        expected_walk_capability,
        expected_blink_capability,
    }
    planned_by_capability = {
        _capability_id(step): step for step in steps.values() if _capability_id(step)
    }
    missing_plan = expected_capabilities - set(planned_by_capability)
    if missing_plan:
        errors.append("Plan is missing body capabilities: " + ", ".join(sorted(missing_plan)))
    for capability_id in expected_capabilities.intersection(planned_by_capability):
        step = planned_by_capability[capability_id]
        owners = _source_goal_ids(step)
        if not owners or not owners.issubset(body_goal_ids):
            errors.append(
                f"{capability_id} step ownership is not limited to typed body Goals"
            )
        if step.get("timing") != "parallel":
            errors.append(f"{capability_id} is not planned with timing=parallel")
    walk_step = planned_by_capability.get(expected_walk_capability)
    if isinstance(walk_step, dict):
        args = walk_step.get("args")
        args = args if isinstance(args, dict) else {}
        actual_duration = args.get("duration_s")
        if not isinstance(actual_duration, (int, float)) or abs(
            float(actual_duration) - duration_s
        ) > tolerance:
            errors.append(
                f"walk duration is not {duration_s}s within tolerance: {actual_duration!r}"
            )

    response = summary.get("interaction_response")
    response = response if isinstance(response, dict) else {}
    requests = response.get("skills")
    requests = requests if isinstance(requests, list) else []
    request_items = [item for item in requests if isinstance(item, dict)]
    requested_by_capability = {
        _capability_id(item): item for item in request_items if _capability_id(item)
    }
    missing_requests = expected_capabilities - set(requested_by_capability)
    if missing_requests:
        errors.append(
            "InteractionResponse is missing body requests: "
            + ", ".join(sorted(missing_requests))
        )
    for capability_id in expected_capabilities.intersection(requested_by_capability):
        request = requested_by_capability[capability_id]
        if request.get("timing") != "parallel":
            errors.append(f"{capability_id} request is not timing=parallel")
        owners = _source_goal_ids(request)
        if not owners or not owners.issubset(body_goal_ids):
            errors.append(
                f"{capability_id} request ownership is not limited to typed body Goals"
            )
    for request in request_items:
        if singing_goal_id and singing_goal_id in _source_goal_ids(request):
            errors.append(
                "singing Goal incorrectly reached Trusted Capability Runtime as "
                f"{_capability_id(request)!r}"
            )

    execution = summary.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    if execution.get("status") != "completed":
        errors.append(
            "Trusted Capability Runtime status is not completed: "
            f"{execution.get('status')!r}"
        )
    results = execution.get("results")
    results = results if isinstance(results, list) else []
    result_items = [item for item in results if isinstance(item, dict)]
    results_by_capability = {
        _capability_id(item): item for item in result_items if _capability_id(item)
    }
    missing_results = expected_capabilities - set(results_by_capability)
    if missing_results:
        errors.append(
            "execution evidence is missing body results: "
            + ", ".join(sorted(missing_results))
        )
    for capability_id in expected_capabilities.intersection(results_by_capability):
        result = results_by_capability[capability_id]
        if result.get("status") != "completed":
            errors.append(
                f"{capability_id} execution status is not completed: {result.get('status')!r}"
            )
        owners = _source_goal_ids(result)
        if not owners or not owners.issubset(body_goal_ids):
            errors.append(
                f"{capability_id} result ownership is not limited to typed body Goals"
            )
    for result in result_items:
        if singing_goal_id and singing_goal_id in _source_goal_ids(result):
            errors.append("ordinary capability execution was recorded as singing evidence")

    report = {
        "expected_chromie_revision": expected_chromie_revision,
        "soridormi_endpoint_revision": endpoint_revision or None,
        "soridormi_checkout_revision": checkout_revision or None,
        "runtime_identity_sha256": identity_sha256 or None,
        "singing_goal_id": singing_goal_id or None,
        "body_goal_ids": sorted(body_goal_ids),
        "planned_capabilities": sorted(planned_by_capability),
        "requested_capabilities": sorted(requested_by_capability),
        "executed_capabilities": sorted(results_by_capability),
        "singing_outcome": (
            outcomes.get(singing_goal_id) if singing_goal_id else None
        ),
        "safe_idle_before": not _safe_idle_errors(
            summary.get("status_before"), label="before"
        ),
        "safe_idle_after": not _safe_idle_errors(
            summary.get("status_after"), label="after"
        ),
    }
    return errors, report


def _issue_comment(report: dict[str, Any], *, closure_report_sha256: str) -> str:
    evidence = report.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    validation = report.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    return "\n".join(
        [
            "Issue #1 closure evidence passed.",
            "",
            f"- Chromie revision: `{report.get('chromie_revision')}`",
            f"- Canonical gate: `{report.get('canonical_gate', {}).get('status')}`",
            f"- Live simulator validation: `{validation.get('status')}`",
            f"- Soridormi revision: `{validation.get('soridormi_endpoint_revision')}`",
            f"- Evidence directory: `{evidence.get('directory')}`",
            f"- Closure report SHA-256: `{closure_report_sha256}`",
            "",
            "Scope: current-revision text-to-MuJoCo Goal/Planner and body execution "
            "evidence with exact singing unavailability. This is not physical audio, "
            "singing-provider, or hardware evidence.",
        ]
    ) + "\n"


def _failure_summary(report: dict[str, Any]) -> str:
    validation = report.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    errors = validation.get("errors")
    errors = errors if isinstance(errors, list) else []
    lines = [
        "Issue #1 closure evidence did not pass. Do not close the Issue.",
        "",
        f"- Chromie revision: `{report.get('chromie_revision')}`",
        f"- Canonical gate: `{report.get('canonical_gate', {}).get('status')}`",
        f"- Runtime identity: `{report.get('runtime_identity', {}).get('status')}`",
        f"- Live run: `{report.get('live_run', {}).get('status')}`",
        f"- Evidence validation: `{validation.get('status')}`",
    ]
    if errors:
        lines.extend(["", "Validation errors:"])
        lines.extend(f"- {item}" for item in errors)
    return "\n".join(lines) + "\n"


def _close_issue(
    *,
    repository: str,
    comment: str,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "gh",
            "issue",
            "close",
            "1",
            "--repo",
            repository,
            "--reason",
            "completed",
            "--comment",
            comment,
        ],
        log_path=log_path,
    )


def _build_live_command(
    *,
    agent_url: str,
    soridormi_mcp_url: str,
    manifest: Path,
    soridormi_repo: Path,
    live_dir: Path,
    runtime_identity_path: Path,
    conversation_id: str,
    timeout_s: float,
    skill_timeout_s: float,
    speaker: bool,
) -> list[str]:
    command = [
        sys.executable,
        "scripts/interaction_text_mujoco_check.py",
        DEFAULT_TEXT,
        "--agent-url",
        agent_url,
        "--soridormi-mcp-url",
        soridormi_mcp_url,
        "--manifest",
        str(manifest),
        "--soridormi-repo",
        str(soridormi_repo),
        "--language",
        "zh-CN",
        "--evidence-dir",
        str(live_dir),
        "--runtime-identity",
        str(runtime_identity_path),
        "--conversation-id",
        conversation_id,
        "--cognitive-runtime",
        "--cognitive-apply-lanes",
        "chat,memory,robot_action,tool",
        "--grant-confirmation",
        "--require-speech",
        "--reject-internal-speech",
        "--expect-route",
        "robot_action",
        "--timeout-s",
        str(timeout_s),
        "--skill-timeout-s",
        str(skill_timeout_s),
        "--speaker" if speaker else "--no-speaker",
    ]
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument(
        "--soridormi-repo",
        type=Path,
        required=True,
        help="Clean paired Soridormi checkout whose revision must match the live endpoint.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--runtime-identity", type=Path, default=DEFAULT_RUNTIME_IDENTITY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--walk-capability", default="soridormi.walk_velocity")
    parser.add_argument("--blink-capability", default="soridormi.blink_eyes")
    parser.add_argument("--timeout-s", type=float, default=1200.0)
    parser.add_argument("--skill-timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--speaker",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use real speaker output. The default discard path still requires TTS completion.",
    )
    parser.add_argument(
        "--skip-canonical-gate",
        action="store_true",
        help="Diagnostic only; a skipped gate can never produce closure-eligible evidence.",
    )
    parser.add_argument(
        "--reuse-runtime-identity",
        action="store_true",
        help="Use the supplied identity file instead of recapturing the running deployment.",
    )
    parser.add_argument(
        "--close-issue",
        action="store_true",
        help="Close TimeTreker/chromie#1 through authenticated gh only after evidence passes.",
    )
    parser.add_argument(
        "--issue-repo",
        default="TimeTreker/chromie",
        help="GitHub repository used with --close-issue.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    revision = _git_text("rev-parse", "HEAD")
    dirty = bool(_git_text("status", "--porcelain"))
    if dirty:
        print(
            "[vocal-issue-closure][error] commit the evaluated patch first; "
            "closure evidence requires a clean checkout",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output_dir or DEFAULT_OUTPUT_ROOT / _acceptance_id())
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    gate_log = output_dir / "canonical_gate.log"
    if args.skip_canonical_gate:
        gate_status = "skipped"
        gate_returncode = None
        gate_log.write_text("canonical gate skipped by operator\n", encoding="utf-8")
    else:
        gate = _run(["./scripts/run_tests.sh"], log_path=gate_log)
        gate_returncode = gate.returncode
        gate_status = "passed" if gate.returncode == 0 else "failed"

    runtime_identity_path = Path(args.runtime_identity).expanduser().resolve()
    identity_log = output_dir / "runtime_identity.log"
    build_env_returncode = 0
    if not args.reuse_runtime_identity:
        build_env = _run(
            ["./scripts/build_runtime_env.sh"],
            log_path=output_dir / "build_runtime_env.log",
        )
        build_env_returncode = build_env.returncode
        if build_env.returncode != 0:
            print(build_env.stderr or build_env.stdout, file=sys.stderr)
        identity = _run(
            [
                sys.executable,
                "scripts/capture_runtime_identity.py",
                "--output",
                str(runtime_identity_path),
            ],
            log_path=identity_log,
        )
        identity_returncode = identity.returncode
    else:
        identity_returncode = 0 if runtime_identity_path.is_file() else 1
        identity_log.write_text(
            f"reused runtime identity: {runtime_identity_path}\n",
            encoding="utf-8",
        )

    identity_errors: list[str] = []
    runtime_identity_payload: dict[str, Any] = {}
    if identity_returncode == 0:
        identity_errors, runtime_identity_payload = validate_runtime_identity(
            runtime_identity_path,
            expected_chromie_revision=revision,
        )
    else:
        identity_errors.append("runtime identity capture failed")
    expected_identity_sha256 = str(
        runtime_identity_payload.get("identity_sha256") or ""
    ).strip()

    live_dir = output_dir / "live"
    command = _build_live_command(
        agent_url=args.agent_url,
        soridormi_mcp_url=args.soridormi_mcp_url,
        manifest=Path(args.manifest).expanduser().resolve(),
        soridormi_repo=Path(args.soridormi_repo).expanduser().resolve(),
        live_dir=live_dir,
        runtime_identity_path=runtime_identity_path,
        conversation_id=f"vocal-issue-1-{_acceptance_id()}",
        timeout_s=args.timeout_s,
        skill_timeout_s=args.skill_timeout_s,
        speaker=args.speaker,
    )
    live = _run(command, log_path=output_dir / "live_run.log")

    live_summary_path = live_dir / "summary.json"
    validation_errors: list[str] = []
    validation_details: dict[str, Any] = {}
    if live_summary_path.is_file():
        live_summary = _read_json(live_summary_path)
        validation_errors, validation_details = validate_closure_summary(
            live_summary,
            expected_chromie_revision=revision,
            expected_walk_capability=args.walk_capability,
            expected_blink_capability=args.blink_capability,
            expected_runtime_identity_sha256=expected_identity_sha256 or None,
        )
    else:
        validation_errors.append("live runner did not retain summary.json")

    validation_errors = [*identity_errors, *validation_errors]
    closure_eligible = bool(
        gate_status == "passed"
        and build_env_returncode == 0
        and identity_returncode == 0
        and live.returncode == 0
        and not validation_errors
    )
    report = {
        "schema_version": 1,
        "issue": "TimeTreker/chromie#1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "chromie_revision": revision,
        "evidence_level": "C_live_text_to_mujoco",
        "closure_eligible": closure_eligible,
        "canonical_gate": {
            "status": gate_status,
            "returncode": gate_returncode,
            "log": str(gate_log),
        },
        "runtime_identity": {
            "status": (
                "passed"
                if identity_returncode == 0 and not identity_errors
                else "failed"
            ),
            "build_env_returncode": build_env_returncode,
            "capture_returncode": identity_returncode,
            "identity_sha256": expected_identity_sha256 or None,
            "errors": identity_errors,
            "path": str(runtime_identity_path),
            "log": str(identity_log),
        },
        "live_run": {
            "status": "passed" if live.returncode == 0 else "failed",
            "returncode": live.returncode,
            "summary": str(live_summary_path),
            "log": str(output_dir / "live_run.log"),
        },
        "validation": {
            "status": "passed" if not validation_errors else "failed",
            "errors": validation_errors,
            **validation_details,
        },
        "claim": (
            "Current-revision Goal/Planner semantics and live Soridormi/MuJoCo "
            "body execution pass for the retained walk/sing/blink case; singing "
            "remains an exact unavailable/refused Goal because no singing-capable "
            "provider is qualified."
        ),
        "exclusions": [
            "physical microphone evidence",
            "physical speaker quality",
            "singing-provider performance",
            "physical robot behavior",
            "release readiness",
        ],
        "evidence": {
            "directory": str(output_dir),
        },
    }
    report_path = output_dir / "closure_summary.json"
    _write_json(report_path, report)
    closure_report_sha256 = _sha256_file(report_path)
    (output_dir / "closure_summary.sha256").write_text(
        f"{closure_report_sha256}  {report_path.name}\n",
        encoding="utf-8",
    )
    issue_close_returncode: int | None = None
    if closure_eligible:
        comment = _issue_comment(
            report,
            closure_report_sha256=closure_report_sha256,
        )
        comment_path = output_dir / "issue_comment.md"
        comment_path.write_text(comment, encoding="utf-8")
        if args.close_issue:
            issue_close = _close_issue(
                repository=args.issue_repo,
                comment=comment,
                log_path=output_dir / "issue_close.log",
            )
            issue_close_returncode = issue_close.returncode
    else:
        (output_dir / "closure_failure.md").write_text(
            _failure_summary(report),
            encoding="utf-8",
        )
        if args.close_issue:
            print(
                "[vocal-issue-closure][error] refusing to close Issue #1 because "
                "closure_eligible is false",
                file=sys.stderr,
            )

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not closure_eligible:
        return 1
    if args.close_issue and issue_close_returncode != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
