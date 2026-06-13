#!/usr/bin/env python3
"""Guided M13 microphone-to-MuJoCo acceptance and evidence capture.

This runner does not declare a result by itself. It combines structured runtime
checks with an operator verdict because audible output, microphone quality, and
simulator state still require observation on the reference host.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "m13"
FULL_CASE_ORDER = (
    "speech-only",
    "speech-skill",
    "refusal",
    "barge-in",
    "body-cancel",
    "stop",
    "follow-up",
)
BODY_CASES = {"speech-skill", "body-cancel", "stop"}
AGENT_COMPOSE_SERVICE = "chromie-agent"
HOST_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def endpoint_for_container(endpoint: str) -> str:
    """Translate a host-loopback URL for access from a Docker container."""

    parsed = urlsplit(endpoint)
    if parsed.hostname not in HOST_LOOPBACK_NAMES:
        return endpoint

    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{userinfo}host.docker.internal{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def capability_probe_invocation(
    *,
    runtime: str,
    endpoint: str,
) -> tuple[list[str], dict[str, str] | None, str]:
    """Build the capability-probe command for the selected runtime."""

    if runtime == "container":
        effective_endpoint = endpoint_for_container(endpoint)
        return (
            [
                "docker",
                "compose",
                "--env-file",
                ".env.runtime",
                "exec",
                "-T",
                "-e",
                f"SORIDORMI_MCP_URL={effective_endpoint}",
                AGENT_COMPOSE_SERVICE,
                "python",
                "-m",
                "app.probe_capabilities",
                "--manifest",
                "/app/capabilities/soridormi.json",
            ],
            None,
            effective_endpoint,
        )

    if runtime == "host":
        environment = os.environ.copy()
        environment["PYTHONPATH"] = "agent"
        environment["SORIDORMI_MCP_URL"] = endpoint
        return (
            [
                sys.executable,
                "-m",
                "app.probe_capabilities",
                "--manifest",
                "capabilities/soridormi.json",
            ],
            environment,
            endpoint,
        )

    raise ValueError(f"Unsupported probe runtime: {runtime}")


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    title: str
    instructions: tuple[str, ...]
    expected: tuple[str, ...]


CASES: dict[str, AcceptanceCase] = {
    "speech-only": AcceptanceCase(
        "speech-only",
        "Speech-only response",
        (
            "Say: Tell me one short fact about the Moon.",
            "Listen for one audible response and do not request a body skill.",
        ),
        (
            "ASR emits final text.",
            "Router and native /interaction path complete.",
            "Interaction reports zero skills and TTS playback completes.",
        ),
    ),
    "speech-skill": AcceptanceCase(
        "speech-skill",
        "Speech plus named Soridormi skill",
        (
            "Ensure the MuJoCo-backed Soridormi endpoint is ready and safely idle.",
            "Say: Please nod twice.",
            "Observe audible speech and the named nod skill in simulation.",
        ),
        (
            "Native interaction contains at least one skill.",
            "Soridormi catalog/plan/execute path completes.",
            "Simulator returns to safe idle.",
        ),
    ),
    "refusal": AcceptanceCase(
        "refusal",
        "Invalid or unavailable skill refusal",
        (
            "Say: Set your left knee motor to ninety degrees.",
            "Confirm that no low-level or unknown physical command is executed.",
        ),
        (
            "A user-facing refusal or safe alternative is spoken.",
            "No untrusted low-level physical provider call occurs.",
        ),
    ),
    "barge-in": AcceptanceCase(
        "barge-in",
        "Barge-in during speech",
        (
            "Ask for a response long enough to begin playback.",
            "While Chromie is speaking, say: Stop.",
        ),
        (
            "The previous session is marked interrupted.",
            "Playback generation is cancelled and stale speech does not resume.",
        ),
    ),
    "body-cancel": AcceptanceCase(
        "body-cancel",
        "Cancellation during a simulated body skill",
        (
            "Start a cancellable named skill that runs long enough to interrupt.",
            "During the skill, say: Stop.",
            "Observe the simulator and verify safe idle afterward.",
        ),
        (
            "The active Skill Runtime execution is cancelled.",
            "The provider cancellation/stop path is visible in evidence.",
            "No orphaned simulated motion remains.",
        ),
    ),
    "stop": AcceptanceCase(
        "stop",
        "Explicit operational stop",
        (
            "Start active speech or simulated work.",
            "Say a direct stop command.",
            "If emergency stop is exercised, follow Soridormi recovery before more motion.",
        ),
        (
            "Router takes the deterministic interrupt route.",
            "Active speech and work stop without waiting for model discretion.",
            "Safety/recovery state is recorded by the operator.",
        ),
    ),
    "follow-up": AcceptanceCase(
        "follow-up",
        "Conversation follow-up",
        (
            "Say: Remember that my test color is blue.",
            "After the first response, ask: What test color did I say?",
        ),
        (
            "Two utterances share the intended conversation ID.",
            "The second response uses bounded conversation history correctly.",
        ),
    ),
}

SENSITIVE_ENV_PARTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "PRIVATE_KEY",
    "COOKIE",
    "CREDENTIAL",
    "AUTHORIZATION",
)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class CaseResult:
    case_id: str
    title: str
    started_utc: str
    finished_utc: str
    event_count: int
    session_ids: list[str]
    checks: list[dict[str, Any]]
    operator_verdict: str
    operator_notes: str

    @property
    def passed(self) -> bool:
        return self.operator_verdict == "pass" and all(
            bool(item.get("passed")) for item in self.checks
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def acceptance_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_command(
    command: Sequence[str],
    output_path: Path,
    *,
    env: dict[str, str] | None = None,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("$ " + shlex.join(command) + "\n\n")
        handle.flush()
        try:
            completed = subprocess.run(
                list(command),
                cwd=ROOT,
                env=env,
                text=True,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except Exception as exc:
            handle.write(f"\nrunner_exception={type(exc).__name__}: {exc}\n")
            if check:
                raise
            return subprocess.CompletedProcess(command, 125, "", str(exc))
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {shlex.join(command)}; "
            f"see {output_path}"
        )
    return completed


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_manifest_metadata() -> dict[str, Any]:
    path = ROOT / "capabilities" / "soridormi.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    return {
        "schema_version": payload.get("schema_version"),
        "source": payload.get("source"),
        "upstream_repository": (metadata or {}).get("upstream_repository"),
        "upstream_commit": (metadata or {}).get("upstream_commit"),
    }


def read_version() -> str:
    path = ROOT / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "unversioned"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def redact_env_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        destination.write_text("# source file was not present\n", encoding="utf-8")
        return
    output: list[str] = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            output.append(raw)
            continue
        key, value = raw.split("=", 1)
        normalized = key.strip().upper()
        if any(part in normalized for part in SENSITIVE_ENV_PARTS):
            value = "<redacted>"
        output.append(f"{key}={value}")
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            records.append(
                {
                    "event": "invalid_jsonl",
                    "message": f"line {line_number} is invalid JSON",
                    "sid": "unknown",
                }
            )
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def event_messages(events: Iterable[dict[str, Any]], event: str) -> list[str]:
    return [
        str(item.get("message", ""))
        for item in events
        if item.get("event") == event
    ]


def has_event(events: Iterable[dict[str, Any]], event: str) -> bool:
    return any(item.get("event") == event for item in events)


def parse_conversation_ids(events: Iterable[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    pattern = re.compile(r"conversation_id=([^\s]+)")
    for message in event_messages(events, "context_snapshot"):
        match = pattern.search(message)
        if match:
            values.append(match.group(1))
    return values


def analyze_case(case_id: str, events: list[dict[str, Any]]) -> list[CheckResult]:
    checks: list[CheckResult] = []

    def require(event: str, label: str | None = None) -> None:
        checks.append(
            CheckResult(
                name=label or event,
                passed=has_event(events, event),
                detail=f"required event: {event}",
            )
        )

    if case_id in {"speech-only", "speech-skill", "refusal", "follow-up"}:
        require("asr_final")
        require("router_done")
        require("interaction_done")

    if case_id == "speech-only":
        messages = event_messages(events, "interaction_done")
        no_skills = any(re.search(r"\bskills=0\b", item) for item in messages)
        checks.append(
            CheckResult(
                "no body skill",
                no_skills,
                "interaction_done must report skills=0",
            )
        )
        require("session_done", "speech playback completed")
    elif case_id == "speech-skill":
        messages = event_messages(events, "interaction_done")
        has_skill = any(
            (match := re.search(r"\bskills=(\d+)\b", item))
            and int(match.group(1)) > 0
            for item in messages
        )
        checks.append(
            CheckResult(
                "named skill proposed",
                has_skill,
                "interaction_done must report one or more skills",
            )
        )
        completed = any(
            "status=completed" in item for item in event_messages(events, "skill_result")
        )
        checks.append(
            CheckResult(
                "named skill completed",
                completed,
                "skill_result must report status=completed",
            )
        )
    elif case_id == "refusal":
        runtime_failure = has_event(events, "skill_runtime_exception")
        rejected = any(
            any(
                token in item
                for token in ("status=rejected", "status=failed", "status=unavailable")
            )
            for item in event_messages(events, "skill_result")
        )
        no_skill = any(
            re.search(r"\bskills=0\b", item)
            for item in event_messages(events, "interaction_done")
        )
        checks.append(
            CheckResult(
                "fails closed",
                not runtime_failure and (rejected or no_skill),
                "no runtime exception; request is rejected or produces no provider skill",
            )
        )
    elif case_id == "barge-in":
        require("session_interrupted_by_new_session", "previous session interrupted")
        require("interrupt_previous_audio_done", "playback interruption completed")
    elif case_id == "body-cancel":
        cancelled = has_event(events, "skill_runtime_cancelled") or any(
            "status=cancelled" in item
            for item in event_messages(events, "skill_result")
        )
        checks.append(
            CheckResult(
                "active skill cancelled",
                cancelled,
                "skill_runtime_cancelled or cancelled skill_result is required",
            )
        )
        require("interrupt_previous_audio_done", "interruption completed")
    elif case_id == "stop":
        deterministic = any(
            "route=interrupt" in item
            for item in event_messages(events, "router_done")
        )
        checks.append(
            CheckResult(
                "deterministic stop route",
                deterministic,
                "router_done must report route=interrupt",
            )
        )
        require("interrupt_previous_audio_done", "active work interrupted")
    elif case_id == "follow-up":
        conversation_ids = parse_conversation_ids(events)
        same_conversation = (
            len(conversation_ids) >= 2 and len(set(conversation_ids[-2:])) == 1
        )
        checks.append(
            CheckResult(
                "conversation retained",
                same_conversation,
                f"observed conversation IDs: {conversation_ids}",
            )
        )
        asr_count = sum(1 for item in events if item.get("event") == "asr_final")
        checks.append(
            CheckResult(
                "two utterances captured",
                asr_count >= 2,
                f"observed {asr_count} asr_final events",
            )
        )
    else:
        raise ValueError(f"Unknown acceptance case: {case_id}")

    return checks


def parse_case_list(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(FULL_CASE_ORDER)
    selected = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in selected if item not in CASES]
    if unknown:
        raise ValueError(f"Unknown cases: {', '.join(unknown)}")
    if not selected:
        raise ValueError("At least one acceptance case is required")
    return selected


def wait_for_log(
    process: subprocess.Popen[Any],
    log_path: Path,
    marker: str,
    timeout_s: float,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(
                f"Orchestrator exited before readiness (code {process.returncode}).\n{tail}"
            )
        if log_path.exists() and marker in log_path.read_text(
            encoding="utf-8", errors="replace"
        ):
            return
        time.sleep(1.0)
    raise TimeoutError(
        f"Timed out after {timeout_s:.0f}s waiting for {marker!r}; see {log_path}"
    )


def stop_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def prompt_verdict() -> str:
    while True:
        value = input("Operator verdict [p=pass, f=fail, s=skip]: ").strip().lower()
        mapping = {
            "p": "pass",
            "pass": "pass",
            "f": "fail",
            "fail": "fail",
            "s": "skip",
            "skip": "skip",
        }
        if value in mapping:
            return mapping[value]
        print("Please enter p, f, or s.")


def render_summary(
    *,
    evidence_dir: Path,
    metadata: dict[str, Any],
    results: list[CaseResult],
    status: str,
) -> str:
    lines = [
        "# M13 Voice Acceptance Summary",
        "",
        f"- **Status:** `{status}`",
        f"- **Acceptance ID:** `{metadata['acceptance_id']}`",
        f"- **Started:** {metadata['started_utc']}",
        f"- **Finished:** {metadata.get('finished_utc', 'in progress')}",
        f"- **Operator:** {metadata['operator']}",
        f"- **Chromie revision:** `{metadata['chromie']['revision']}`",
        f"- **Chromie version candidate:** `{metadata['chromie']['version']}`",
        f"- **Soridormi manifest revision:** `{metadata['soridormi_manifest'].get('upstream_commit')}`",
        "",
        "## Cases",
        "",
        "| Case | Automated checks | Operator | Result |",
        "|---|---:|---|---|",
    ]
    for result in results:
        passed_checks = sum(1 for item in result.checks if item.get("passed"))
        total_checks = len(result.checks)
        final = "PASS" if result.passed else "FAIL"
        if result.operator_verdict == "skip":
            final = "SKIP"
        lines.append(
            f"| `{result.case_id}` | {passed_checks}/{total_checks} | "
            f"{result.operator_verdict} | **{final}** |"
        )
    lines.extend(
        [
            "",
            "## Evidence files",
            "",
            "- `metadata.json` — revisions, host and run configuration",
            "- `runtime.env.redacted` — generated runtime configuration with secret-like values redacted",
            "- `audio-devices.log` — host audio-device discovery",
            "- `events.jsonl` — correlated Orchestrator session events",
            "- `orchestrator.log` — complete host Orchestrator output",
            "- `cases.json` — per-case checks and operator notes",
            "- `recordings/` — raw input/output captures when enabled",
            "",
            f"Evidence directory: `{evidence_dir}`",
            "",
            "A passed bundle still requires review before changing tracked milestone or release status.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_metadata(args: argparse.Namespace, selected: list[str]) -> dict[str, Any]:
    status = git_output("status", "--porcelain")
    soridormi_local_revision = "not-provided"
    if args.soridormi_repo:
        repo = Path(args.soridormi_repo).expanduser()
        try:
            soridormi_local_revision = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            soridormi_local_revision = "unknown"
    return {
        "schema_version": 1,
        "acceptance_id": args.acceptance_id,
        "started_utc": utc_now(),
        "operator": args.operator,
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version,
        },
        "chromie": {
            "version": read_version(),
            "revision": git_output("rev-parse", "HEAD"),
            "branch": git_output("branch", "--show-current"),
            "dirty": bool(status),
            "status_porcelain": status.splitlines(),
        },
        "soridormi_manifest": load_manifest_metadata(),
        "soridormi_local_revision": soridormi_local_revision,
        "soridormi_mcp_url": args.soridormi_mcp_url or "not-configured",
        "selected_cases": selected,
        "runner": {
            "start_services": args.start_services,
            "dry_run": args.dry_run,
            "allow_dirty": args.allow_dirty,
            "orchestrator_timeout_s": args.orchestrator_timeout_s,
            "probe_runtime": args.probe_runtime,
            "probe_service": (
                AGENT_COMPOSE_SERVICE if args.probe_runtime == "container" else None
            ),
            "probe_endpoint": (
                endpoint_for_container(args.soridormi_mcp_url)
                if args.probe_runtime == "container" and args.soridormi_mcp_url
                else args.soridormi_mcp_url
            ),
        },
    }


def write_override_file(
    path: Path,
    *,
    event_path: Path,
    recordings_dir: Path,
    soridormi_mcp_url: str | None,
    enable_soridormi: bool,
) -> None:
    values = {
        "ORCH_ENABLE_ROUTER": "1",
        "ORCH_ENABLE_AGENT": "1",
        "ORCH_ENABLE_INTERACTION_RESPONSE": "1",
        "ORCH_ENABLE_SORIDORMI_SKILLS": "1" if enable_soridormi else "0",
        "ORCH_AUTO_CONFIRM_SIM_SKILLS": "1",
        "ORCH_SESSION_TIMING_LOGS": "1",
        "ORCH_EVENT_LOG_PATH": str(event_path),
        "ORCH_SAVE_AUDIO": "true",
        "RECORDINGS_DIR": str(recordings_dir),
        "AGENT_INTERACTION_OUTPUT_MODE": "native",
        "AGENT_NATIVE_INTERACTION_FALLBACK": "0",
    }
    if soridormi_mcp_url:
        values["SORIDORMI_MCP_URL"] = soridormi_mcp_url
    path.write_text(
        "# Generated by scripts/m13_voice_acceptance.py\n"
        + "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items())
        + "\n",
        encoding="utf-8",
    )


def run_acceptance(args: argparse.Namespace) -> int:
    selected = parse_case_list(args.cases)
    needs_soridormi = bool(BODY_CASES.intersection(selected))
    if needs_soridormi and not args.soridormi_mcp_url and not args.dry_run:
        raise ValueError(
            "Body-skill cases require --soridormi-mcp-url or SORIDORMI_MCP_URL"
        )

    metadata = build_metadata(args, selected)
    if metadata["chromie"]["dirty"] and not args.allow_dirty and not args.dry_run:
        raise ValueError(
            "Chromie worktree is dirty. Commit the candidate revision before a "
            "release-evidence run, or use --allow-dirty only for exploratory evidence."
        )

    evidence_dir = Path(args.evidence_root).expanduser() / args.acceptance_id
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise FileExistsError(
            f"Evidence directory already exists and is not empty: {evidence_dir}"
        )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    recordings_dir = evidence_dir / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    events_path = evidence_dir / "events.jsonl"
    override_path = evidence_dir / "acceptance-overrides.env"
    write_json(evidence_dir / "metadata.json", metadata)
    write_override_file(
        override_path,
        event_path=events_path,
        recordings_dir=recordings_dir,
        soridormi_mcp_url=args.soridormi_mcp_url,
        enable_soridormi=needs_soridormi,
    )

    results: list[CaseResult] = []
    process: subprocess.Popen[Any] | None = None
    orchestrator_log = evidence_dir / "orchestrator.log"
    final_status = "failed"

    try:
        if args.dry_run:
            for placeholder in (
                evidence_dir / "runtime.env.redacted",
                evidence_dir / "audio-devices.log",
                events_path,
                orchestrator_log,
            ):
                placeholder.write_text(
                    "DRY RUN: no target evidence was collected.\n",
                    encoding="utf-8",
                )
            for case_id in selected:
                case = CASES[case_id]
                results.append(
                    CaseResult(
                        case_id=case_id,
                        title=case.title,
                        started_utc=utc_now(),
                        finished_utc=utc_now(),
                        event_count=0,
                        session_ids=[],
                        checks=[
                            asdict(CheckResult("dry-run", False, "case was not executed"))
                        ],
                        operator_verdict="skip",
                        operator_notes="Dry-run plan only.",
                    )
                )
            final_status = "dry-run"
            return 0

        run_command(
            ["./scripts/build_runtime_env.sh"],
            evidence_dir / "runtime-env.log",
            check=True,
            timeout=120,
        )
        redact_env_file(ROOT / ".env.runtime", evidence_dir / "runtime.env.redacted")
        run_command(
            [sys.executable, "orchestrator/list_devices.py"],
            evidence_dir / "audio-devices.log",
            timeout=60,
        )
        run_command(
            ["docker", "compose", "--env-file", ".env.runtime", "ps"],
            evidence_dir / "compose-ps.log",
            timeout=60,
        )
        run_command(
            ["git", "status", "--short"],
            evidence_dir / "git-status.log",
            timeout=30,
        )
        if args.start_services:
            run_command(
                ["./scripts/start_services.sh"],
                evidence_dir / "start-services.log",
                check=True,
                timeout=args.service_timeout_s,
            )
        if needs_soridormi:
            probe_command, probe_env, _ = capability_probe_invocation(
                runtime=args.probe_runtime,
                endpoint=args.soridormi_mcp_url,
            )
            run_command(
                probe_command,
                evidence_dir / "soridormi-probe.log",
                env=probe_env,
                check=True,
                timeout=60,
            )

        environment = os.environ.copy()
        environment["ORCH_RUNTIME_OVERRIDE_FILE"] = str(override_path)
        with orchestrator_log.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                ["./scripts/start_orchestrator.sh"],
                cwd=ROOT,
                env=environment,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        wait_for_log(
            process,
            orchestrator_log,
            "Microphone started",
            args.orchestrator_timeout_s,
        )

        print(f"\nM13 acceptance evidence: {evidence_dir}")
        print("The runner is recording structured session events and audio captures.")
        print("Use only a supervised MuJoCo endpoint for body-skill cases.\n")

        for case_id in selected:
            case = CASES[case_id]
            print("=" * 72)
            print(f"{case.case_id}: {case.title}")
            print("Instructions:")
            for item in case.instructions:
                print(f"  - {item}")
            print("Expected:")
            for item in case.expected:
                print(f"  - {item}")
            input("\nPress Enter immediately before performing this case...")
            started = utc_now()
            marker = len(read_events(events_path))
            input("Perform the case now, then press Enter after the response/state settles...")
            time.sleep(args.settle_s)
            case_events = read_events(events_path)[marker:]
            checks = analyze_case(case_id, case_events)
            print("\nAutomated evidence checks:")
            for item in checks:
                symbol = "PASS" if item.passed else "FAIL"
                print(f"  [{symbol}] {item.name}: {item.detail}")
            verdict = prompt_verdict()
            notes = input(
                "Operator notes (required for fail/skip; optional for pass): "
            ).strip()
            if verdict != "pass" and not notes:
                notes = "No operator notes supplied."
            results.append(
                CaseResult(
                    case_id=case_id,
                    title=case.title,
                    started_utc=started,
                    finished_utc=utc_now(),
                    event_count=len(case_events),
                    session_ids=sorted(
                        {
                            str(item.get("sid"))
                            for item in case_events
                            if item.get("sid") not in {None, "", "unknown"}
                        }
                    ),
                    checks=[asdict(item) for item in checks],
                    operator_verdict=verdict,
                    operator_notes=notes,
                )
            )
            write_json(evidence_dir / "cases.json", [asdict(item) for item in results])

        final_status = "passed" if all(item.passed for item in results) else "failed"
        return 0 if final_status == "passed" else 1
    except KeyboardInterrupt:
        final_status = "aborted"
        return 130
    finally:
        stop_process(process)
        if orchestrator_log.exists():
            device_lines = [
                line
                for line in orchestrator_log.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if "Input device name=" in line or "Output device name=" in line
            ]
            if device_lines:
                with (evidence_dir / "audio-devices.log").open(
                    "a", encoding="utf-8"
                ) as handle:
                    handle.write("\n# Device selection reported by the running Orchestrator\n")
                    handle.write("\n".join(device_lines) + "\n")
        metadata["finished_utc"] = utc_now()
        metadata["status"] = final_status
        metadata["event_count"] = len(read_events(events_path))
        write_json(evidence_dir / "metadata.json", metadata)
        write_json(evidence_dir / "cases.json", [asdict(item) for item in results])
        (evidence_dir / "summary.md").write_text(
            render_summary(
                evidence_dir=evidence_dir,
                metadata=metadata,
                results=results,
                status=final_status,
            ),
            encoding="utf-8",
        )
        print(f"\nM13 acceptance status: {final_status}")
        print(f"Evidence bundle: {evidence_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        default="all",
        help="Comma-separated case IDs or 'all'.",
    )
    parser.add_argument(
        "--evidence-root",
        default=str(DEFAULT_EVIDENCE_ROOT),
        help="Parent directory for timestamped evidence bundles.",
    )
    parser.add_argument("--acceptance-id", default=acceptance_id())
    parser.add_argument("--operator", default=getpass.getuser())
    parser.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL"),
    )
    parser.add_argument("--soridormi-repo")
    parser.add_argument(
        "--probe-runtime",
        choices=("container", "host"),
        default="container",
        help=(
            "Run the Soridormi capability probe in the Agent container "
            "(recommended) or in the host Python environment."
        ),
    )
    parser.add_argument("--start-services", action="store_true")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit exploratory evidence from an uncommitted tree; release verification will still warn/fail.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--settle-s", type=float, default=1.0)
    parser.add_argument("--orchestrator-timeout-s", type=float, default=240.0)
    parser.add_argument("--service-timeout-s", type=float, default=900.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_acceptance(args)
    except (ValueError, FileExistsError, RuntimeError, TimeoutError) as exc:
        print(f"[m13-acceptance][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
