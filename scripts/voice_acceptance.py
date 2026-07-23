#!/usr/bin/env python3
"""Voice-to-MuJoCo acceptance and evidence capture.

Four modes are available:

* ``synthetic`` generates prompt audio with Chromie TTS and injects framed PCM16
  into the Orchestrator stdin path. It is fully automatic and reproducible.
* ``virtual-mic`` generates the same fixtures and plays them into a temporary
  PulseAudio/PipeWire monitor source, exercising host audio-device capture.
* ``acoustic`` generates fixtures and plays them through the configured host
  output so Chromie hears them through the configured host input device.
* ``supervised`` uses the real microphone and asks an operator to confirm
  audible and visual behavior. Supervised evidence is required for a human
  physical voice-device claim; automated modes may support a narrower
  generated-speech claim when the release compatibility policy accepts them.
"""

from __future__ import annotations

import argparse
import ast
import getpass
import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.audio_injection import encode_audio_packet
from scripts.acceptance_audio import (
    AudioFixture,
    HostSpeakerPlayer,
    PulseVirtualMicrophone,
    generate_tts_fixtures,
)

DEFAULT_EVIDENCE_ROOT = ROOT / ".chromie" / "acceptance" / "voice"
AUTOMATIC_MODES = {"synthetic", "virtual-mic", "acoustic"}
ACCEPTANCE_MODES = ("synthetic", "virtual-mic", "acoustic", "supervised")
FULL_CASE_ORDER = (
    "speech-only",
    "speech-skill",
    "refusal",
    "barge-in",
    "body-cancel",
    "stop",
    "follow-up",
)
BODY_CASES = {"speech-skill", "refusal", "body-cancel", "stop"}
AGENT_COMPOSE_SERVICE = "chromie-agent"
HOST_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
RUNTIME_REEXEC_ENV = "CHROMIE_VOICE_ACCEPTANCE_RUNTIME_REEXEC"


def _missing_automatic_runtime_packages(mode: str) -> list[str]:
    packages = ["websockets"]
    if mode == "acoustic" and HostSpeakerPlayer.available_backend() is None:
        packages.extend(["numpy", "sounddevice"])
    return [
        package
        for package in packages
        if importlib.util.find_spec(package) is None
    ]


def ensure_acceptance_runtime(argv: Sequence[str]) -> None:
    """Re-exec automatic modes in the managed host environment when needed."""

    if "--dry-run" in argv or "--preflight-only" in argv:
        return
    mode = "synthetic"
    if "--mode" in argv:
        mode_index = argv.index("--mode") + 1
        if mode_index < len(argv):
            mode = argv[mode_index]
    if mode not in AUTOMATIC_MODES:
        return
    missing_packages = _missing_automatic_runtime_packages(mode)
    if not missing_packages:
        return
    if os.getenv(RUNTIME_REEXEC_ENV) == "1":
        raise RuntimeError(
            "The managed acceptance runtime does not provide required package(s): "
            + ", ".join(missing_packages)
        )
    conda = shutil.which("conda")
    if conda is None:
        raise RuntimeError(
            "Automatic voice acceptance requires package(s) "
            + ", ".join(missing_packages)
            + " or a managed conda runtime"
        )
    environment = os.environ.copy()
    environment[RUNTIME_REEXEC_ENV] = "1"
    env_name = os.getenv("CONDA_ENV_NAME", os.getenv("CHROMIE_CONDA_ENV", "Chromie"))
    os.execvpe(
        conda,
        [
            conda,
            "run",
            "--no-capture-output",
            "-n",
            env_name,
            "python",
            str(Path(__file__).resolve()),
            *argv,
        ],
        environment,
    )


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
                "--exclude-effect",
                "test_control",
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
                "--exclude-effect",
                "test_control",
            ],
            environment,
            endpoint,
        )

    raise ValueError(f"Unsupported probe runtime: {runtime}")


@dataclass(frozen=True)
class SpokenStep:
    prompt: str
    required_term_groups: tuple[tuple[str, ...], ...] = ()
    wait_before_events: tuple[str, ...] = ()
    wait_for_confirmation_prompt_completion: bool = False
    wait_before_label: str | None = None
    countdown_s: int | None = None


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    title: str
    instructions: tuple[str, ...]
    expected: tuple[str, ...]
    spoken_steps: tuple[SpokenStep, ...]


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
            "Router and goal-driven cognitive runtime complete.",
            "Interaction reports zero skills and TTS playback completes.",
        ),
        (SpokenStep("Tell me one short fact about the Moon.", (("moon",),)),),
    ),
    "speech-skill": AcceptanceCase(
        "speech-skill",
        "Confirmed speech plus named Soridormi skill",
        (
            "Ensure the MuJoCo-backed Soridormi endpoint is ready and safely idle.",
            "Say: Please perform a nodding gesture two times.",
            "After Chromie asks for confirmation, say: Yes.",
            "Observe audible speech and the named nod skill in simulation.",
        ),
        (
            "Native interaction contains at least one skill.",
            "Host confirmation is bound to the exact named-skill request.",
            "The confirmation prompt finishes playback before approval is injected.",
            "Soridormi catalog/plan/execute path completes.",
            "Simulator returns to safe idle.",
        ),
        (
            SpokenStep(
                "Please perform a nodding gesture two times.",
                (("nod", "nodding"), ("twice", "two")),
            ),
            SpokenStep(
                "Yes.",
                (("yes",),),
                wait_for_confirmation_prompt_completion=True,
                wait_before_label="the request-bound confirmation prompt to finish playing",
            ),
        ),
    ),
    "refusal": AcceptanceCase(
        "refusal",
        "Spoken confirmation denial",
        (
            "Say: Please perform a nodding gesture two times.",
            "After Chromie asks for confirmation, say: No thanks.",
            "Confirm that no Soridormi execution occurs.",
        ),
        (
            "The exact pending request is denied and consumed.",
            "A user-facing denial is spoken.",
            "No named body skill executes.",
        ),
        (
            SpokenStep(
                "Please perform a nodding gesture two times.",
                (("nod", "nodding"), ("twice", "two")),
            ),
            SpokenStep(
                "No thanks.",
                (("no",),),
                wait_for_confirmation_prompt_completion=True,
                wait_before_label="the request-bound confirmation prompt to finish playing",
            ),
        ),
    ),
    "barge-in": AcceptanceCase(
        "barge-in",
        "Barge-in during speech",
        (
            "Ask for a response long enough to begin playback.",
            "While Chromie is speaking, say: Stop talking.",
        ),
        (
            "The previous session is marked interrupted.",
            "Playback generation is cancelled and stale speech does not resume.",
        ),
        (
            SpokenStep(
                "Tell me a detailed story about the Moon that takes at least thirty seconds."
            ),
            SpokenStep(
                "Stop talking.",
                (("stop",),),
                wait_before_events=("playback_start",),
                wait_before_label="audible playback to begin",
                countdown_s=0,
            ),
        ),
    ),
    "body-cancel": AcceptanceCase(
        "body-cancel",
        "Cancellation during a simulated body skill",
        (
            "Start a long named nod skill, which is long enough to interrupt.",
            "Approve the exact request when Chromie asks for confirmation.",
            "During the skill, say: Stop talking.",
            "Observe the simulator and verify safe idle afterward.",
        ),
        (
            "Host-observed Skill Runtime cancellation is recorded.",
            "Post-cancellation Soridormi status reports safe idle.",
            "No active simulated task is reported afterward.",
        ),
        (
            SpokenStep(
                "Please perform a nodding gesture eight times.",
                (("nod", "nodding"), ("eight", "8")),
            ),
            SpokenStep(
                "Yes.",
                (("yes",),),
                wait_for_confirmation_prompt_completion=True,
                wait_before_label="the request-bound confirmation prompt to finish playing",
            ),
            SpokenStep(
                "Stop talking.",
                (("stop",),),
                wait_before_events=("confirmation_authorized",),
                wait_before_label="the long nod skill to be authorized",
                countdown_s=0,
            ),
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
        (
            SpokenStep(
                "Tell me a detailed story about space that takes at least thirty seconds."
            ),
            SpokenStep(
                "Stop talking.",
                (("stop",),),
                wait_before_events=("playback_start",),
                wait_before_label="audible playback to begin",
                countdown_s=0,
            ),
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
        (
            SpokenStep("Remember that my test color is blue.", (("blue",),)),
            SpokenStep(
                "What test color did I say?",
                (("color", "colour"),),
                wait_before_events=("session_done",),
                wait_before_label="the first response to finish",
            ),
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


def tcp_endpoint_check(name: str, endpoint: str) -> CheckResult:
    parsed = urlsplit(endpoint)
    host = parsed.hostname
    if not host:
        return CheckResult(name, False, f"invalid endpoint: {endpoint}")
    try:
        if parsed.port is not None:
            port = parsed.port
        elif parsed.scheme in {"https", "wss"}:
            port = 443
        else:
            port = 80
    except ValueError as exc:
        return CheckResult(name, False, f"invalid endpoint: {exc}")
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        return CheckResult(name, False, f"{host}:{port} is unreachable: {exc}")
    return CheckResult(name, True, f"{host}:{port} is reachable")


def acceptance_readiness(
    args: argparse.Namespace,
    selected: Sequence[str],
) -> list[CheckResult]:
    """Check prerequisites without creating or modifying acceptance evidence."""

    checks: list[CheckResult] = []
    build_script = ROOT / "scripts" / "build_runtime_env.sh"
    checks.append(
        CheckResult(
            "runtime configuration",
            build_script.is_file() and os.access(build_script, os.X_OK),
            (
                f"{build_script.relative_to(ROOT)} is executable"
                if build_script.is_file() and os.access(build_script, os.X_OK)
                else f"{build_script.relative_to(ROOT)} is missing or not executable"
            ),
        )
    )

    docker = shutil.which("docker")
    checks.append(
        CheckResult(
            "Docker CLI",
            docker is not None,
            docker or "docker was not found on PATH",
        )
    )
    if docker is not None:
        try:
            daemon = subprocess.run(
                [docker, "info"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            daemon_detail = (
                "Docker daemon is reachable"
                if daemon.returncode == 0
                else (
                    daemon.stderr.strip()
                    or daemon.stdout.strip()
                    or f"docker info exited {daemon.returncode}"
                )
            )
            checks.append(
                CheckResult("Docker daemon", daemon.returncode == 0, daemon_detail)
            )
        except subprocess.TimeoutExpired:
            checks.append(
                CheckResult(
                    "Docker daemon",
                    False,
                    "docker info timed out after 15 seconds",
                )
            )

    if args.mode in AUTOMATIC_MODES:
        missing_runtime_packages = _missing_automatic_runtime_packages(args.mode)
        managed_conda = shutil.which("conda")
        checks.append(
            CheckResult(
                "automatic acceptance runtime",
                not missing_runtime_packages or managed_conda is not None,
                (
                    "required Python packages are importable"
                    if not missing_runtime_packages
                    else (
                        f"managed runtime is available through {managed_conda}"
                        if managed_conda
                        else "missing Python package(s): "
                        + ", ".join(missing_runtime_packages)
                    )
                ),
            )
        )
        if args.start_services:
            checks.append(
                CheckResult(
                    "TTS endpoint",
                    True,
                    "Chromie services will be started by --start-services",
                )
            )
        else:
            checks.append(tcp_endpoint_check("TTS endpoint", args.tts_url))

    if args.mode == "virtual-mic":
        backend = PulseVirtualMicrophone.available_backend()
        checks.append(
            CheckResult(
                "virtual microphone backend",
                backend is not None,
                backend or "neither PulseAudio nor PipeWire tools are available",
            )
        )
    if args.mode == "acoustic":
        host_player = HostSpeakerPlayer.available_backend()
        missing_playback_packages = [
            package
            for package in ("numpy", "sounddevice")
            if importlib.util.find_spec(package) is None
        ]
        managed_conda = shutil.which("conda")
        checks.append(
            CheckResult(
                "acoustic playback runtime",
                host_player is not None
                or not missing_playback_packages
                or managed_conda is not None,
                (
                    f"{host_player} is available"
                    if host_player is not None
                    else "sounddevice and numpy are importable"
                    if not missing_playback_packages
                    else (
                        f"managed runtime is available through {managed_conda}"
                        if managed_conda
                        else "missing Python package(s): "
                        + ", ".join(missing_playback_packages)
                    )
                ),
            )
        )

    needs_soridormi = bool(BODY_CASES.intersection(selected))
    if needs_soridormi:
        if args.soridormi_mcp_url:
            checks.append(
                tcp_endpoint_check("Soridormi MCP endpoint", args.soridormi_mcp_url)
            )
        else:
            checks.append(
                CheckResult(
                    "Soridormi MCP endpoint",
                    False,
                    "--soridormi-mcp-url or SORIDORMI_MCP_URL is required",
                )
            )
        if args.soridormi_repo:
            repo = Path(args.soridormi_repo).expanduser()
            checks.append(
                CheckResult(
                    "Soridormi repository",
                    repo.is_dir() and (repo / ".git").exists(),
                    (
                        f"{repo} is available"
                        if repo.is_dir() and (repo / ".git").exists()
                        else f"{repo} is not a Git repository"
                    ),
                )
            )

    return checks


def print_readiness(checks: Sequence[CheckResult]) -> bool:
    print("Voice-to-MuJoCo voice acceptance readiness")
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    passed = all(check.passed for check in checks)
    print(f"Overall: {'ready' if passed else 'not ready'}")
    return passed


@dataclass(frozen=True)
class SpokenCapture:
    check: CheckResult
    sid: str | None
    transcript: str
    attempts: int


@dataclass
class AcceptanceAudioDriver:
    mode: str
    fixtures: dict[str, AudioFixture]
    orchestrator_process: subprocess.Popen[Any] | None = None
    virtual_microphone: PulseVirtualMicrophone | None = None
    speaker_player: HostSpeakerPlayer | None = None

    def deliver(self, prompt: str) -> AudioFixture:
        fixture = self.fixtures[prompt]
        if self.mode == "synthetic":
            process = self.orchestrator_process
            if process is None or process.stdin is None:
                raise RuntimeError("synthetic mode requires an Orchestrator stdin pipe")
            process.stdin.write(
                encode_audio_packet(
                    pcm16=fixture.pcm16,
                    sample_rate=fixture.sample_rate,
                    channels=fixture.channels,
                )
            )
            process.stdin.flush()
        elif self.mode == "virtual-mic":
            if self.virtual_microphone is None:
                raise RuntimeError("virtual-mic mode is not initialized")
            self.virtual_microphone.play(fixture)
        elif self.mode == "acoustic":
            if self.speaker_player is None:
                raise RuntimeError("acoustic mode requires a speaker player")
            self.speaker_player.play(fixture)
        else:
            raise RuntimeError(f"Audio delivery is not used in mode {self.mode!r}")
        return fixture


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
        return self.operator_verdict in {"pass", "automated"} and all(
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


def extract_asr_text(event: dict[str, Any]) -> str:
    """Return the transcript rendered in an ``asr_final`` event message."""

    message = str(event.get("message", ""))
    match = re.search(r"\btext=(.+)$", message)
    if not match:
        return ""
    rendered = match.group(1).strip()
    try:
        value = ast.literal_eval(rendered)
    except (SyntaxError, ValueError):
        return rendered
    return value if isinstance(value, str) else str(value)


def normalize_spoken_text(value: str) -> str:
    """Normalize recognized text for lightweight intent-keyword checks."""

    lowered = value.casefold()
    lowered = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return " ".join(lowered.split())


def missing_required_terms(
    transcript: str,
    required_term_groups: Sequence[Sequence[str]],
) -> list[str]:
    """Return human-readable alternatives that were not recognized.

    Each group represents alternatives, for example ``("twice", "two")``.
    Empty groups are ignored. This is intentionally a small acceptance-time
    check rather than a pronunciation score.
    """

    normalized = normalize_spoken_text(transcript)
    padded = f" {normalized} "
    missing: list[str] = []
    for raw_group in required_term_groups:
        group = [normalize_spoken_text(item) for item in raw_group if item.strip()]
        if not group:
            continue
        if not any(f" {item} " in padded for item in group):
            missing.append("/".join(raw_group))
    return missing


def events_for_sessions(
    events: Iterable[dict[str, Any]],
    session_ids: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Keep only events belonging to the current acceptance case sessions."""

    allowed = {value for value in (session_ids or ()) if value}
    if not allowed:
        return list(events)
    return [item for item in events if str(item.get("sid", "")) in allowed]


def message_field(message: str, name: str) -> str | None:
    """Extract a whitespace-delimited ``name=value`` field from an event."""

    match = re.search(rf"(?:^|\s){re.escape(name)}=([^\s]+)", message)
    return match.group(1) if match else None


def scheduled_tts_text(message: str) -> str:
    match = re.search(r"(?:^|\s)text=(.+)$", message)
    if match is None:
        return ""
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return ""
    return value if isinstance(value, str) else ""


def is_confirmation_prompt_text(text: str) -> bool:
    normalized = normalize_spoken_text(text)
    return bool(
        normalized
        and (
            "confirm" in normalized
            or "yes or no" in normalized
            or "确认" in normalized
            or "是否" in normalized
        )
    )


def friendly_event_line(event: dict[str, Any]) -> str | None:
    """Render a concise operator-facing line for important pipeline events."""

    name = str(event.get("event", ""))
    message = str(event.get("message", ""))
    sid = str(event.get("sid", "unknown"))
    prefix = f"[{sid}]"
    if name == "asr_final":
        return f"{prefix} ASR heard: {extract_asr_text(event)!r}"
    if name == "router_done":
        return (
            f"{prefix} Router: route={message_field(message, 'route') or '?'} "
            f"intent={message_field(message, 'intent') or '?'}"
        )
    if name in {"interaction_done", "cognitive_interaction_ready"}:
        return (
            f"{prefix} Goal-driven interaction: speech={message_field(message, 'speech') or '?'} "
            f"skills={message_field(message, 'skills') or '?'} "
            "confirmation="
            f"{message_field(message, 'requires_confirmation') or '?'}"
        )
    if name == "skill_proposed":
        return (
            f"{prefix} Skill proposed: {message_field(message, 'skill_id') or '?'} "
            f"request={message_field(message, 'request_id') or '?'} "
            f"confirmation={message_field(message, 'requires_confirmation') or '?'}"
        )
    if name == "skill_result":
        return (
            f"{prefix} Skill result: {message_field(message, 'skill_id') or '?'} "
            f"status={message_field(message, 'status') or '?'}"
        )
    if name == "skill_runtime_cancelled":
        return f"{prefix} Skill runtime: cancelled"
    if name == "playback_start":
        return f"{prefix} TTS playback: started"
    if name == "interrupt_previous_audio_done":
        return f"{prefix} Interruption: previous audio/work stopped"
    if name == "session_done":
        return f"{prefix} Session: completed"
    return None


def wait_for_any_event(
    path: Path,
    *,
    marker: int,
    event_names: Iterable[str],
    timeout_s: float,
    session_ids: Iterable[str] | None = None,
    poll_s: float = 0.2,
) -> dict[str, Any] | None:
    """Wait for one of ``event_names`` appended after ``marker``."""

    expected = set(event_names)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for item in events_for_sessions(read_events(path)[marker:], session_ids):
            if item.get("event") in expected:
                return item
        time.sleep(poll_s)
    return None


def wait_for_confirmation_prompt_completion(
    path: Path,
    *,
    marker: int,
    timeout_s: float,
    session_ids: Iterable[str] | None = None,
    poll_s: float = 0.2,
) -> dict[str, Any] | None:
    """Wait for a request-bound confirmation prompt to finish playback."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        scoped = events_for_sessions(read_events(path)[marker:], session_ids)
        for request_index, requested in enumerate(scoped):
            if requested.get("event") != "confirmation_requested":
                continue
            request_sid = str(requested.get("sid") or "")
            if not request_sid:
                continue
            for schedule_index in range(request_index + 1, len(scoped)):
                schedule = scoped[schedule_index]
                if (
                    schedule.get("event") != "tts_schedule"
                    or str(schedule.get("sid") or "") != request_sid
                ):
                    continue
                schedule_message = str(schedule.get("message") or "")
                order = message_field(schedule_message, "order")
                if order is None or not is_confirmation_prompt_text(
                    scheduled_tts_text(schedule_message)
                ):
                    continue
                playback_started = False
                for playback in scoped[schedule_index + 1 :]:
                    if str(playback.get("sid") or "") != request_sid:
                        continue
                    playback_message = str(playback.get("message") or "")
                    if message_field(playback_message, "order") != order:
                        continue
                    if playback.get("event") == "playback_start":
                        playback_started = True
                    elif playback.get("event") == "playback_end" and playback_started:
                        return playback
        time.sleep(poll_s)
    return None


def wait_for_case_checks(
    case_id: str,
    path: Path,
    *,
    marker: int,
    timeout_s: float,
    session_ids: Iterable[str] | None = None,
    show_progress: bool = False,
    poll_s: float = 0.25,
) -> tuple[list[dict[str, Any]], list[CheckResult]]:
    """Wait until all event-based checks pass or the case timeout expires."""

    deadline = time.monotonic() + timeout_s
    events: list[dict[str, Any]] = []
    checks: list[CheckResult] = []
    shown: set[tuple[str, str, str]] = set()
    while time.monotonic() < deadline:
        events = events_for_sessions(read_events(path)[marker:], session_ids)
        if show_progress:
            for item in events:
                key = (
                    str(item.get("sid", "")),
                    str(item.get("event", "")),
                    str(item.get("message", "")),
                )
                if key in shown:
                    continue
                shown.add(key)
                rendered = friendly_event_line(item)
                if rendered and item.get("event") != "asr_final":
                    print(f"  {rendered}", flush=True)
        checks = analyze_case(case_id, events)
        if checks and all(item.passed for item in checks):
            return events, checks
        time.sleep(poll_s)
    events = events_for_sessions(read_events(path)[marker:], session_ids)
    return events, analyze_case(case_id, events)


def print_countdown(seconds: int) -> None:
    print("\nGet ready to speak.")
    for remaining in range(max(0, seconds), 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1.0)


def guide_spoken_step(
    *,
    case: AcceptanceCase,
    step: SpokenStep,
    step_index: int,
    events_path: Path,
    case_marker: int,
    countdown_s: int,
    asr_timeout_s: float,
    trigger_timeout_s: float,
    asr_retries: int,
    case_session_ids: set[str],
    mode: str = "supervised",
    audio_driver: AcceptanceAudioDriver | None = None,
) -> SpokenCapture:
    """Guide one spoken utterance and confirm that ASR captured it."""

    if step.wait_for_confirmation_prompt_completion or step.wait_before_events:
        label = step.wait_before_label or "/".join(step.wait_before_events)
        print(f"\nWaiting for {label} before the next utterance...")
        if step.wait_for_confirmation_prompt_completion:
            trigger = wait_for_confirmation_prompt_completion(
                events_path,
                marker=case_marker,
                timeout_s=trigger_timeout_s,
                session_ids=case_session_ids,
            )
        else:
            trigger = wait_for_any_event(
                events_path,
                marker=case_marker,
                event_names=step.wait_before_events,
                timeout_s=trigger_timeout_s,
                session_ids=case_session_ids,
            )
        if trigger is None:
            return SpokenCapture(
                check=CheckResult(
                    name=f"guided utterance {step_index}",
                    passed=False,
                    detail=(
                        f"timed out after {trigger_timeout_s:.0f}s waiting for {label}; "
                        "the utterance was not requested"
                    ),
                ),
                sid=None,
                transcript="",
                attempts=0,
            )
        print(f"Ready condition detected: {trigger.get('event')}")

    attempts = max(1, asr_retries + 1)
    latest_transcript = ""
    latest_sid: str | None = None
    for attempt in range(1, attempts + 1):
        marker = len(read_events(events_path))
        if mode == "supervised":
            print_countdown(countdown_s if step.countdown_s is None else step.countdown_s)
            print("\n" + "!" * 72)
            print(
                f">>> SPEAK NOW ({case.case_id}, step {step_index}/{len(case.spoken_steps)}, "
                f"attempt {attempt}/{attempts})"
            )
            print(f">>> {step.prompt}")
            print("!" * 72)
        else:
            if audio_driver is None:
                raise RuntimeError(f"{mode} mode requires generated test audio")
            fixture = audio_driver.deliver(step.prompt)
            print("\n" + "!" * 72)
            print(
                f">>> TEST AUDIO INJECTED ({case.case_id}, "
                f"step {step_index}/{len(case.spoken_steps)}, attempt {attempt}/{attempts})"
            )
            print(f">>> Text : {step.prompt}")
            print(f">>> WAV  : {fixture.path}")
            print(
                f">>> Audio: {fixture.sample_rate} Hz, {fixture.channels} channel(s), "
                f"{len(fixture.pcm16)} PCM bytes"
            )
            print("!" * 72)
        print(
            f"Listening for ASR for up to {asr_timeout_s:.0f} seconds...",
            flush=True,
        )

        event = wait_for_any_event(
            events_path,
            marker=marker,
            event_names=("asr_final",),
            timeout_s=asr_timeout_s,
        )
        if event is None:
            print("[ASR] No final transcript was detected.")
            if attempt < attempts:
                print("[ASR] Retrying the same utterance automatically.")
                continue
            return SpokenCapture(
                check=CheckResult(
                    name=f"guided utterance {step_index}",
                    passed=False,
                    detail=f"no asr_final event within {asr_timeout_s:.0f}s",
                ),
                sid=None,
                transcript="",
                attempts=attempt,
            )

        latest_sid = str(event.get("sid") or "") or None
        if latest_sid:
            case_session_ids.add(latest_sid)
        latest_transcript = extract_asr_text(event)
        missing = missing_required_terms(
            latest_transcript,
            step.required_term_groups,
        )
        print("\nASR RESULT")
        print(f"  Expected : {step.prompt}")
        print(f"  Heard    : {latest_transcript or '<transcript unavailable>'}")
        print(f"  Session  : {latest_sid or '<unknown>'}")
        if not missing:
            print("  Intent   : recognized")
            return SpokenCapture(
                check=CheckResult(
                    name=f"guided utterance {step_index}",
                    passed=True,
                    detail=f"ASR transcript: {latest_transcript or '<unavailable>'}",
                ),
                sid=latest_sid,
                transcript=latest_transcript,
                attempts=attempt,
            )

        print(f"  Intent   : missing expected word(s): {', '.join(missing)}")
        if attempt < attempts:
            print("[ASR] The command intent was not recognized; retrying automatically.")
            continue

        return SpokenCapture(
            check=CheckResult(
                name=f"guided utterance {step_index}",
                passed=False,
                detail=(
                    f"ASR transcript {latest_transcript!r} did not contain required "
                    f"terms: {', '.join(missing)}"
                ),
            ),
            sid=latest_sid,
            transcript=latest_transcript,
            attempts=attempt,
        )

    raise AssertionError("unreachable spoken-step loop")


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

    def rows(event_name: str) -> list[tuple[int, dict[str, Any], str]]:
        return [
            (index, item, str(item.get("message", "")))
            for index, item in enumerate(events)
            if item.get("event") == event_name
        ]

    def field(item: dict[str, Any], name: str) -> str | None:
        value = message_field(str(item.get("message", "")), name)
        if value is None or value in {"", "None", "null"}:
            return None
        return value

    def integer_field(message: str, name: str) -> int | None:
        raw = message_field(message, name)
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def scheduled_text(message: str) -> str:
        return scheduled_tts_text(message)

    def require(event: str, label: str | None = None) -> None:
        checks.append(
            CheckResult(
                name=label or event,
                passed=has_event(events, event),
                detail=f"required event: {event}",
            )
        )

    def require_interaction() -> list[tuple[int, dict[str, Any], str]]:
        interaction_rows = [
            *rows("cognitive_interaction_ready"),
            *rows("interaction_done"),
        ]
        interaction_rows.sort(key=lambda value: value[0])
        checks.append(
            CheckResult(
                name="goal-driven interaction ready",
                passed=bool(interaction_rows),
                detail=(
                    "required event: cognitive_interaction_ready "
                    "(interaction_done is accepted only for compatibility evidence)"
                ),
            )
        )
        return interaction_rows

    def proposed_requests(
        skill_id: str,
        *,
        count: int | None = None,
    ) -> list[tuple[int, str]]:
        proposal_rows = [
            *rows("cognitive_skill_proposed"),
            *rows("skill_proposed"),
        ]
        proposal_rows.sort(key=lambda value: value[0])
        matches: list[tuple[int, str]] = []
        for index, item, message in proposal_rows:
            if f"skill_id={skill_id}" not in message:
                continue
            if count is not None:
                match = re.search(r"\bargs=(\{.*\})\s*$", message)
                if match is None:
                    continue
                try:
                    args = json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
                if not isinstance(args, dict) or args.get("count") != count:
                    continue
            request_id = field(item, "request_id")
            if request_id is not None:
                matches.append((index, request_id))
        return matches

    def safe_idle_status(
        *,
        after_index: int = -1,
        sid: str | None = None,
    ) -> bool:
        return any(
            index > after_index
            and (sid is None or str(item.get("sid") or "") == sid)
            and all(
                token in message
                for token in (
                    "mode=sim",
                    "backend=runtime",
                    "safe_idle=True",
                    "active_task_present=False",
                    "emergency_stop=False",
                    "fallen=False",
                )
            )
            for index, item, message in rows("soridormi_post_status")
        )

    def confirmation_chain(
        *,
        decision: str,
        terminal_event: str,
        request_ids: set[str],
    ) -> dict[str, Any] | None:
        """Return one ordered, request-bound confirmation chain.

        The host emits both the single-use confirmation ID and the exact request
        fingerprint at every stage. Acceptance must correlate both values; mere
        presence of unrelated confirmation events is not sufficient.
        """

        for request_index, requested, _message in rows("confirmation_requested"):
            confirmation_id = field(requested, "confirmation_id")
            fingerprint = field(requested, "fingerprint")
            bound_request_ids = set(
                (field(requested, "request_ids") or "").split(",")
            ) - {""}
            if (
                confirmation_id is None
                or fingerprint is None
                or not request_ids
                or not request_ids.issubset(bound_request_ids)
            ):
                continue
            for reply_index, reply, _reply_message in rows("confirmation_reply"):
                if reply_index <= request_index:
                    continue
                if (
                    field(reply, "confirmation_id") != confirmation_id
                    or field(reply, "fingerprint") != fingerprint
                    or field(reply, "decision") != decision
                ):
                    continue
                for terminal_index, terminal, _terminal_message in rows(
                    terminal_event
                ):
                    if terminal_index <= reply_index:
                        continue
                    if (
                        field(terminal, "confirmation_id") != confirmation_id
                        or field(terminal, "fingerprint") != fingerprint
                    ):
                        continue
                    if (
                        terminal_event == "confirmation_rejected"
                        and field(terminal, "reason") != decision
                    ):
                        continue
                    if terminal_event == "confirmation_authorized":
                        authorized_ids = set(
                            (field(terminal, "request_ids") or "").split(",")
                        ) - {""}
                        if not request_ids.issubset(authorized_ids):
                            continue
                        requested_interaction = field(requested, "interaction_id")
                        authorized_interaction = field(terminal, "interaction_id")
                        if (
                            requested_interaction is None
                            or authorized_interaction != requested_interaction
                        ):
                            continue
                    return {
                        "confirmation_id": confirmation_id,
                        "fingerprint": fingerprint,
                        "request_index": request_index,
                        "request_sid": str(requested.get("sid") or ""),
                        "reply_index": reply_index,
                        "terminal_index": terminal_index,
                        "terminal_sid": str(terminal.get("sid") or ""),
                    }
        return None

    def confirmation_prompt_playback_completed(chain: dict[str, Any]) -> bool:
        request_index = int(chain["request_index"])
        reply_index = int(chain["reply_index"])
        request_sid = str(chain["request_sid"])
        for schedule_index, schedule, message in rows("tts_schedule"):
            if not (
                request_index < schedule_index < reply_index
                and str(schedule.get("sid") or "") == request_sid
            ):
                continue
            order = field(schedule, "order")
            prompt_text = scheduled_text(message)
            if order is None or not is_confirmation_prompt_text(prompt_text):
                continue
            playback_start_index = next(
                (
                    playback_index
                    for playback_index, playback, _message in rows("playback_start")
                    if schedule_index < playback_index < reply_index
                    and str(playback.get("sid") or "") == request_sid
                    and field(playback, "order") == order
                ),
                None,
            )
            if playback_start_index is None:
                continue
            if any(
                playback_start_index < playback_index < reply_index
                and str(playback.get("sid") or "") == request_sid
                and field(playback, "order") == order
                for playback_index, playback, _message in rows("playback_end")
            ):
                return True
        return False

    def completed_tts(
        *,
        after_index: int = -1,
        sid: str | None = None,
        required_word: str | None = None,
        denial: bool = False,
    ) -> tuple[bool, str]:
        for schedule_index, schedule, message in rows("tts_schedule"):
            schedule_sid = str(schedule.get("sid") or "")
            if schedule_index <= after_index or (sid and schedule_sid != sid):
                continue
            order = field(schedule, "order")
            text = scheduled_text(message)
            normalized = normalize_spoken_text(text)
            if order is None or not text:
                continue
            if required_word:
                padded = f" {normalized} "
                if f" {normalize_spoken_text(required_word)} " not in padded:
                    continue
            padded_normalized = f" {normalized} "
            if denial and not (
                any(
                    marker in padded_normalized
                    for marker in (
                        " will not ",
                        " won t ",
                        " cancelled ",
                        " canceled ",
                    )
                )
                or any(marker in normalized for marker in ("不会", "不执行", "已取消"))
            ):
                continue
            start_index = next(
                (
                    index
                    for index, item, _ in rows("playback_start")
                    if index > schedule_index
                    and str(item.get("sid") or "") == schedule_sid
                    and field(item, "order") == order
                ),
                None,
            )
            if start_index is None:
                continue
            end_index = next(
                (
                    index
                    for index, item, _ in rows("playback_end")
                    if index > start_index
                    and str(item.get("sid") or "") == schedule_sid
                    and field(item, "order") == order
                ),
                None,
            )
            if end_index is None:
                continue
            session_complete = any(
                index > end_index
                and str(item.get("sid") or "") == schedule_sid
                and (scheduled := integer_field(done_message, "scheduled_tts"))
                is not None
                and (played := integer_field(done_message, "played_tts")) is not None
                and integer_field(done_message, "failed_tts") == 0
                and integer_field(done_message, "skipped_tts") == 0
                and scheduled >= 1
                and scheduled == played
                for index, item, done_message in rows("session_done")
            )
            if session_complete:
                return True, text
        return False, ""

    def interrupt_chain(*, forbid_later_work: bool) -> dict[str, Any] | None:
        for interrupted_index, interrupted, _message in rows(
            "session_interrupted_by_new_session"
        ):
            old_sid = str(interrupted.get("sid") or "")
            new_sid = field(interrupted, "new_sid")
            if not old_sid or new_sid is None or new_sid == old_sid:
                continue
            interrupt_asr = next(
                (
                    index
                    for index, item, _ in rows("asr_final")
                    if index > interrupted_index
                    and str(item.get("sid") or "") == new_sid
                    and any(
                        f" {term} "
                        in f" {normalize_spoken_text(extract_asr_text(item))} "
                        for term in ("stop", "cancel", "停止", "取消")
                    )
                ),
                None,
            )
            if interrupt_asr is None:
                continue
            interrupt_route = next(
                (
                    index
                    for index, item, _ in rows("router_done")
                    if index > interrupt_asr
                    and str(item.get("sid") or "") == new_sid
                    and field(item, "route") == "interrupt"
                ),
                None,
            )
            if interrupt_route is None:
                continue
            active_playback = False
            for start_index, start, _ in rows("playback_start"):
                if start_index >= interrupted_index:
                    continue
                if str(start.get("sid") or "") != old_sid:
                    continue
                order = field(start, "order")
                if order is None:
                    continue
                ended_before_interrupt = any(
                    start_index < end_index < interrupted_index
                    and str(end.get("sid") or "") == old_sid
                    and field(end, "order") == order
                    for end_index, end, _ in rows("playback_end")
                )
                if not ended_before_interrupt:
                    active_playback = True
                    break
            if not active_playback:
                continue
            done_index = next(
                (
                    index
                    for index, item, _ in rows("interrupt_previous_audio_done")
                    if index > interrupt_route
                    and str(item.get("sid") or "") == new_sid
                ),
                None,
            )
            if done_index is None:
                continue
            forbidden_events = {"playback_start", "playback_end"}
            if forbid_later_work:
                forbidden_events.add("tts_schedule")
            forbidden_sids = (
                {old_sid, new_sid} if forbid_later_work else {old_sid}
            )
            stale_output = any(
                index > done_index
                and str(item.get("sid") or "") in forbidden_sids
                and item.get("event") in forbidden_events
                for index, item in enumerate(events)
            )
            later_completed_work = forbid_later_work and any(
                index > done_index
                and str(item.get("sid") or "") in forbidden_sids
                and (
                    (
                        item.get("event") == "skill_result"
                        and field(item, "status") == "completed"
                    )
                    or (
                        item.get("event") == "skill_runtime_done"
                        and field(item, "status") == "completed"
                    )
                )
                for index, item in enumerate(events)
            )
            return {
                "old_sid": old_sid,
                "new_sid": new_sid,
                "done_index": done_index,
                "no_later_output_or_work": not stale_output
                and not later_completed_work,
            }
        return None

    if case_id in {
        "speech-only",
        "speech-skill",
        "refusal",
        "body-cancel",
        "follow-up",
    }:
        require("asr_final")
        require("router_done")
        interaction_messages = require_interaction()
    else:
        interaction_messages = []

    if case_id == "speech-only":
        prepared = next(
            (
                (index, item)
                for index, item, message in interaction_messages
                if (speech := re.search(r"\bspeech=(\d+)\b", message))
                and int(speech.group(1)) > 0
                and re.search(r"\bskills=0\b", message)
            ),
            None,
        )
        checks.append(
            CheckResult(
                "speech prepared without body skill",
                prepared is not None,
                "the prepared interaction must report speech>0 and skills=0",
            )
        )
        output_complete = False
        if prepared is not None:
            prepared_index, prepared_event = prepared
            output_complete, _ = completed_tts(
                after_index=prepared_index,
                sid=str(prepared_event.get("sid") or "") or None,
            )
        checks.append(
            CheckResult(
                "speech output completed",
                output_complete,
                "a correlated TTS schedule, playback start/end, and clean session_done are required",
            )
        )
    elif case_id == "speech-skill":
        proposals = proposed_requests("soridormi.nod_yes", count=2)
        proposal_ids = {request_id for _index, request_id in proposals}
        checks.append(
            CheckResult(
                "exact nod skill proposed",
                bool(proposals),
                "the prepared interaction must propose soridormi.nod_yes count=2",
            )
        )
        approval = confirmation_chain(
            decision="approved",
            terminal_event="confirmation_authorized",
            request_ids=proposal_ids,
        )
        checks.append(
            CheckResult(
                "exact request confirmation approved",
                approval is not None,
                "requested, approved, and authorized events must share confirmation_id and fingerprint",
            )
        )
        checks.append(
            CheckResult(
                "confirmation prompt playback completed",
                bool(approval and confirmation_prompt_playback_completed(approval)),
                "the bound confirmation prompt must be scheduled and finish playback before approval",
            )
        )
        completed_result = next(
            (
                (index, item)
                for index, item, _message in rows("skill_result")
                if index
                > int(approval["terminal_index"] if approval else len(events))
                and field(item, "request_id") in proposal_ids
                and field(item, "skill_id") == "soridormi.nod_yes"
                and field(item, "status") == "completed"
            ),
            None,
        )
        checks.append(
            CheckResult(
                "exact nod skill completed",
                completed_result is not None,
                "soridormi.nod_yes must report status=completed",
            )
        )
        completed_index = (
            completed_result[0] if completed_result is not None else len(events)
        )
        completed_sid = (
            str(completed_result[1].get("sid") or "")
            if completed_result is not None
            else None
        )
        checks.append(
            CheckResult(
                "simulator returned safe idle",
                safe_idle_status(
                    after_index=completed_index,
                    sid=completed_sid,
                ),
                "post-execution Soridormi status must be sim/runtime and safe idle",
            )
        )
    elif case_id == "refusal":
        proposals = proposed_requests("soridormi.nod_yes", count=2)
        proposal_ids = {request_id for _index, request_id in proposals}
        checks.append(
            CheckResult(
                "exact nod skill proposed",
                bool(proposals),
                "the denied request must be soridormi.nod_yes count=2",
            )
        )
        denial_chain = confirmation_chain(
            decision="denied",
            terminal_event="confirmation_rejected",
            request_ids=proposal_ids,
        )
        body_invoked = any(
            "skill_id=soridormi." in item
            for item in event_messages(events, "skill_result")
        )
        checks.append(
            CheckResult(
                "exact request confirmation denied",
                denial_chain is not None,
                "requested, denied, and rejected events must share confirmation_id and fingerprint",
            )
        )
        denial_spoken = False
        denial_text = ""
        if denial_chain is not None:
            denial_spoken, denial_text = completed_tts(
                after_index=int(denial_chain["terminal_index"]),
                sid=str(denial_chain["terminal_sid"]),
                denial=True,
            )
        checks.append(
            CheckResult(
                "denial speech output completed",
                denial_spoken,
                (
                    f"completed denial output: {denial_text!r}"
                    if denial_spoken
                    else "a denial TTS schedule and correlated playback completion are required"
                ),
            )
        )
        checks.append(
            CheckResult(
                "body skill not executed",
                not body_invoked,
                "no Soridormi skill_result of any status may follow denial",
            )
        )
    elif case_id == "barge-in":
        interruption = interrupt_chain(forbid_later_work=False)
        checks.append(
            CheckResult(
                "active playback session interrupted",
                interruption is not None,
                "an active old-session playback must link to the new interrupt session",
            )
        )
        checks.append(
            CheckResult(
                "stale playback did not resume",
                bool(
                    interruption
                    and interruption["no_later_output_or_work"]
                ),
                "no old-session playback_start/playback_end may follow interrupt completion",
            )
        )
    elif case_id == "body-cancel":
        proposals = proposed_requests("soridormi.nod_yes", count=8)
        proposal_ids = {request_id for _index, request_id in proposals}
        checks.append(
            CheckResult(
                "exact long nod skill proposed",
                bool(proposals),
                "the cancellable request must be soridormi.nod_yes count=8",
            )
        )
        approval = confirmation_chain(
            decision="approved",
            terminal_event="confirmation_authorized",
            request_ids=proposal_ids,
        )
        checks.append(
            CheckResult(
                "exact body request confirmed",
                approval is not None,
                "requested, approved, and authorized events must share confirmation_id and fingerprint",
            )
        )
        execution_sid = str(approval["terminal_sid"]) if approval else ""
        cancellation_indices = [
            index
            for index, item, _message in rows("skill_runtime_cancelled")
            if approval is not None
            and index > int(approval["terminal_index"])
            and str(item.get("sid") or "") == execution_sid
        ] + [
            index
            for event_name in ("skill_runtime_done", "skill_result")
            for index, item, _message in rows(event_name)
            if approval is not None
            and index > int(approval["terminal_index"])
            and str(item.get("sid") or "") == execution_sid
            and field(item, "status") == "cancelled"
        ]
        cancelled = bool(cancellation_indices)
        cancellation_index = min(cancellation_indices, default=len(events))
        stop_session: tuple[int, str] | None = None
        if approval is not None:
            for asr_index, asr, _message in rows("asr_final"):
                asr_sid = str(asr.get("sid") or "")
                transcript = f" {normalize_spoken_text(extract_asr_text(asr))} "
                if asr_index <= int(approval["terminal_index"]) or not any(
                    f" {term} " in transcript for term in ("stop", "cancel", "停止", "取消")
                ):
                    continue
                route_index = next(
                    (
                        index
                        for index, item, _ in rows("router_done")
                        if index > asr_index
                        and str(item.get("sid") or "") == asr_sid
                        and field(item, "route") == "interrupt"
                    ),
                    None,
                )
                if route_index is not None:
                    stop_session = (route_index, asr_sid)
                    break
        interrupted = bool(
            stop_session
            and any(
                index > max(cancellation_index, stop_session[0])
                and str(item.get("sid") or "") == stop_session[1]
                for index, item, _message in rows("interrupt_previous_audio_done")
            )
        )
        checks.append(
            CheckResult(
                "host-observed skill cancellation",
                cancelled,
                "host evidence must record a cancelled Skill Runtime task or result",
            )
        )
        checks.append(
            CheckResult(
                "host interruption completed",
                interrupted,
                "interrupt_previous_audio_done must follow observed cancellation",
            )
        )
        checks.append(
            CheckResult(
                "simulator returned safe idle",
                safe_idle_status(
                    after_index=cancellation_index,
                    sid=execution_sid or None,
                ),
                "post-cancellation status must report sim/runtime safe idle with no active task",
            )
        )
    elif case_id == "stop":
        interruption = interrupt_chain(forbid_later_work=True)
        stop_sid = str(interruption["new_sid"]) if interruption else ""
        deterministic = any(
            str(item.get("sid") or "") == stop_sid
            and field(item, "route") == "interrupt"
            for _index, item, _message in rows("router_done")
        )
        checks.append(
            CheckResult(
                "deterministic stop route",
                deterministic,
                "router_done must report route=interrupt",
            )
        )
        checks.append(
            CheckResult(
                "active work interruption completed",
                bool(interruption),
                "an active old session must link to the completed stop session",
            )
        )
        checks.append(
            CheckResult(
                "no stale output or completed work after stop",
                bool(
                    interruption
                    and interruption["no_later_output_or_work"]
                ),
                "old-session TTS/playback or completed skill work may not follow stop completion",
            )
        )
    elif case_id == "follow-up":
        asr_rows = rows("asr_final")
        utterance_pair: tuple[
            tuple[int, dict[str, Any], str],
            tuple[int, dict[str, Any], str],
        ] | None = None
        for first in asr_rows:
            first_text = normalize_spoken_text(extract_asr_text(first[1]))
            if " blue " not in f" {first_text} ":
                continue
            for second in asr_rows:
                second_text = normalize_spoken_text(extract_asr_text(second[1]))
                if second[0] > first[0] and any(
                    f" {word} " in f" {second_text} "
                    for word in ("color", "colour")
                ):
                    utterance_pair = (first, second)
                    break
            if utterance_pair is not None:
                break

        conversation_ids: list[str] = []
        if utterance_pair is not None:
            first, second = utterance_pair
            for utterance, upper_bound in ((first, second[0]), (second, len(events))):
                utterance_sid = str(utterance[1].get("sid") or "")
                snapshot = next(
                    (
                        item
                        for index, item, _message in rows("context_snapshot")
                        if utterance[0] < index < upper_bound
                        and str(item.get("sid") or "") == utterance_sid
                    ),
                    None,
                )
                conversation_id = (
                    field(snapshot, "conversation_id") if snapshot else None
                )
                if conversation_id is not None:
                    conversation_ids.append(conversation_id)
        same_conversation = len(conversation_ids) == 2 and len(
            set(conversation_ids)
        ) == 1
        checks.append(
            CheckResult(
                "conversation retained",
                same_conversation,
                f"observed conversation IDs: {conversation_ids}",
            )
        )
        checks.append(
            CheckResult(
                "two intended utterances captured",
                utterance_pair is not None,
                "ASR must capture the blue-memory statement and later color question",
            )
        )
        recalled_blue = False
        recalled_text = ""
        if utterance_pair is not None:
            second = utterance_pair[1]
            recalled_blue, recalled_text = completed_tts(
                after_index=second[0],
                sid=str(second[1].get("sid") or "") or None,
                required_word="blue",
            )
        checks.append(
            CheckResult(
                "follow-up response recalled blue",
                recalled_blue,
                (
                    f"completed response: {recalled_text!r}"
                    if recalled_blue
                    else "the second session must complete TTS output containing 'blue'"
                ),
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
        value = input(
            "Automated checks passed. Did you hear/observe the expected result? "
            "[Enter/p=pass, f=fail, s=skip]: "
        ).strip().lower()
        mapping = {
            "": "pass",
            "p": "pass",
            "pass": "pass",
            "f": "fail",
            "fail": "fail",
            "s": "skip",
            "skip": "skip",
        }
        if value in mapping:
            return mapping[value]
        print("Press Enter for pass, or enter p, f, or s.")


def render_summary(
    *,
    evidence_dir: Path,
    metadata: dict[str, Any],
    results: list[CaseResult],
    status: str,
) -> str:
    lines = [
        "# Voice Acceptance Summary",
        "",
        f"- **Status:** `{status}`",
        f"- **Acceptance ID:** `{metadata['acceptance_id']}`",
        f"- **Started:** {metadata['started_utc']}",
        f"- **Finished:** {metadata.get('finished_utc', 'in progress')}",
        f"- **Mode:** `{metadata.get('runner', {}).get('mode', 'supervised')}`",
        f"- **Human-supervised input mode:** `{metadata.get('runner', {}).get('human_supervised_mode', False)}`",
        "- **Release eligibility:** determined only by `verify_voice_evidence.py` after provenance and runtime checks",
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
            "- `cognitive-runtime.jsonl` — applied goal-driven runtime evidence",
            "- `orchestrator.log` — complete host Orchestrator output",
            "- `cases.json` — per-case checks and operator notes",
            "- `recordings/` — raw input/output captures when enabled",
            "- `generated-input/` — TTS-generated test WAV files in automated modes",
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
    soridormi_local_dirty: bool | None = None
    if args.soridormi_repo:
        repo = Path(args.soridormi_repo).expanduser()
        try:
            soridormi_local_revision = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            soridormi_status = subprocess.check_output(
                ["git", "-C", str(repo), "status", "--porcelain"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            soridormi_local_dirty = bool(soridormi_status)
        except Exception:
            soridormi_local_revision = "unknown"
            soridormi_local_dirty = None
    return {
        "schema_version": 2,
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
        "soridormi_local_dirty": soridormi_local_dirty,
        "soridormi_source_binding": {
            "kind": "declared_paired_checkout",
            "endpoint_revision": None,
        },
        "soridormi_mcp_url": args.soridormi_mcp_url or "not-configured",
        "selected_cases": selected,
        "runner": {
            "mode": args.mode,
            "semantic_runtime": {
                "mode": "apply",
                "apply_lanes": ["chat", "robot_action"],
                "fallback_policy": "fail_closed",
                "legacy_semantic_fallback": False,
            },
            "human_supervised_mode": args.mode == "supervised",
            "start_services": args.start_services,
            "dry_run": args.dry_run,
            "allow_dirty": args.allow_dirty,
            "orchestrator_timeout_s": args.orchestrator_timeout_s,
            "countdown_s": args.countdown_s,
            "asr_timeout_s": args.asr_timeout_s,
            "asr_retries": args.asr_retries,
            "case_timeout_s": args.case_timeout_s,
            "continue_after_failure": args.continue_after_failure,
            "probe_runtime": args.probe_runtime,
            "probe_service": (
                AGENT_COMPOSE_SERVICE if args.probe_runtime == "container" else None
            ),
            "probe_endpoint": (
                endpoint_for_container(args.soridormi_mcp_url)
                if args.probe_runtime == "container" and args.soridormi_mcp_url
                else args.soridormi_mcp_url
            ),
            "tts_url": args.tts_url,
            "tts_speaker_id": args.tts_speaker_id,
            "tts_timeout_s": args.tts_timeout_s,
            "virtual_mic_sink": (
                args.virtual_mic_sink if args.mode == "virtual-mic" else None
            ),
            "acoustic_playback_gain": (
                args.acoustic_playback_gain if args.mode == "acoustic" else None
            ),
            "acoustic_player": args.acoustic_player if args.mode == "acoustic" else None,
            "acoustic_output_target": (
                args.acoustic_output_target if args.mode == "acoustic" else None
            ),
            "acoustic_response_output_mode": (
                args.acoustic_response_output_mode if args.mode == "acoustic" else None
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
    mode: str = "supervised",
    virtual_mic_source: str | None = None,
    acoustic_response_output_mode: str = "discard",
) -> None:
    values = {
        "ORCH_ENABLE_ROUTER": "1",
        "ORCH_ENABLE_AGENT": "1",
        "ORCH_ENABLE_INTERACTION_RESPONSE": "1",
        "ORCH_ENABLE_SORIDORMI_SKILLS": "1" if enable_soridormi else "0",
        "ORCH_AUTO_CONFIRM_SIM_SKILLS": "0",
        "ORCH_COGNITIVE_RUNTIME_MODE": "apply",
        "ORCH_COGNITIVE_APPLY_LANES": "chat,robot_action",
        "ORCH_COGNITIVE_FALLBACK_POLICY": "fail_closed",
        "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED": "0",
        "ORCH_COGNITIVE_EVIDENCE_ENABLED": "1",
        "ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT": "0",
        "ORCH_COGNITIVE_EVIDENCE_PATH": str(
            event_path.parent / "cognitive-runtime.jsonl"
        ),
        "ORCH_SESSION_TIMING_LOGS": "1",
        "ORCH_EVENT_LOG_PATH": str(event_path),
        "ORCH_SAVE_AUDIO": "true",
        "RECORDINGS_DIR": str(recordings_dir),
        "AGENT_INTERACTION_OUTPUT_MODE": "native",
        "AGENT_NATIVE_INTERACTION_FALLBACK": "0",
    }
    if mode == "synthetic":
        values.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "stdin",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
                "ORCH_DISCARD_PLAYBACK_REALTIME": "1",
                "ORCH_INPUT_RATE": "16000",
                "ORCH_INPUT_CHANNELS": "1",
                "ORCH_MIN_AUDIO_MS": "250",
                "ORCH_MIN_RMS": "40",
                "ORCH_BARGE_IN_MIN_RMS": "40",
            }
        )
    elif mode == "virtual-mic":
        if not virtual_mic_source:
            raise ValueError("virtual-mic mode requires a monitor source")
        values.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
                "ORCH_DISCARD_PLAYBACK_REALTIME": "1",
                "ORCH_INPUT_DEVICE": virtual_mic_source,
                "PULSE_SOURCE": virtual_mic_source,
                "ORCH_INPUT_CHANNELS": "1",
                "ORCH_MIN_AUDIO_MS": "250",
                "ORCH_MIN_RMS": "40",
                "ORCH_BARGE_IN_MIN_RMS": "40",
            }
        )
    elif mode == "acoustic":
        output_mode = (
            acoustic_response_output_mode
            if acoustic_response_output_mode in {"discard", "device"}
            else "discard"
        )
        values.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": output_mode,
                "ORCH_DISCARD_PLAYBACK_REALTIME": "1",
            }
        )
        for key in (
            "ORCH_INPUT_DEVICE",
            "ORCH_OUTPUT_DEVICE",
            "ORCH_INPUT_RATE",
            "ORCH_OUTPUT_RATE",
            "ORCH_INPUT_CHANNELS",
            "ORCH_OUTPUT_CHANNELS",
            "ORCH_INPUT_GAIN",
            "ORCH_MIN_AUDIO_MS",
            "ORCH_MIN_RMS",
            "ORCH_BARGE_IN_MIN_RMS",
            "ORCH_VAD_MODE",
            "ORCH_VAD_SILENCE_MS",
        ):
            value = os.getenv(key)
            if value not in {None, ""}:
                values[key] = value
    elif mode == "supervised":
        values.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "device",
            }
        )
        for key in (
            "ORCH_INPUT_DEVICE",
            "ORCH_OUTPUT_DEVICE",
            "ORCH_INPUT_RATE",
            "ORCH_OUTPUT_RATE",
            "ORCH_INPUT_CHANNELS",
            "ORCH_OUTPUT_CHANNELS",
            "ORCH_INPUT_GAIN",
            "ORCH_MIN_AUDIO_MS",
            "ORCH_MIN_RMS",
            "ORCH_BARGE_IN_MIN_RMS",
            "ORCH_VAD_MODE",
            "ORCH_VAD_SILENCE_MS",
        ):
            value = os.getenv(key)
            if value not in {None, ""}:
                values[key] = value
    else:
        raise ValueError(f"Unsupported acceptance mode: {mode}")
    if soridormi_mcp_url:
        values["SORIDORMI_MCP_URL"] = soridormi_mcp_url
    path.write_text(
        "# Generated by scripts/voice_acceptance.py\n"
        + "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items())
        + "\n",
        encoding="utf-8",
    )


def service_runtime_overrides(
    *,
    soridormi_mcp_url: str | None,
    enable_soridormi: bool,
) -> dict[str, str]:
    """Return Docker-service overrides needed by selected acceptance cases."""

    if not enable_soridormi:
        return {}
    values = {
        "AGENT_CAPABILITY_MANIFESTS": "/app/capabilities/soridormi.json",
    }
    if soridormi_mcp_url:
        values["SORIDORMI_MCP_URL"] = endpoint_for_container(soridormi_mcp_url)
    return values


def write_service_override_file(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "# Generated by scripts/voice_acceptance.py for Docker services\n"
        + "\n".join(
            f"{key}={shlex.quote(value)}" for key, value in sorted(values.items())
        )
        + "\n",
        encoding="utf-8",
    )


def run_acceptance(args: argparse.Namespace) -> int:
    selected = parse_case_list(args.cases)
    if args.mode not in ACCEPTANCE_MODES:
        raise ValueError(f"Unsupported acceptance mode: {args.mode}")
    if args.countdown_s < 0:
        raise ValueError("--countdown-s must be zero or greater")
    if args.asr_timeout_s <= 0:
        raise ValueError("--asr-timeout-s must be greater than zero")
    if args.asr_retries < 0:
        raise ValueError("--asr-retries must be zero or greater")
    if args.tts_timeout_s <= 0:
        raise ValueError("--tts-timeout-s must be greater than zero")
    if args.case_timeout_s <= 0:
        raise ValueError("--case-timeout-s must be greater than zero")
    needs_soridormi = bool(BODY_CASES.intersection(selected))
    if (
        needs_soridormi
        and not args.soridormi_mcp_url
        and not args.dry_run
        and not args.preflight_only
    ):
        raise ValueError(
            "Body-skill cases require --soridormi-mcp-url or SORIDORMI_MCP_URL"
        )
    if args.preflight_only:
        return 0 if print_readiness(acceptance_readiness(args, selected)) else 1
    if not args.dry_run:
        readiness = acceptance_readiness(args, selected)
        if not print_readiness(readiness):
            raise RuntimeError(
                "Acceptance prerequisites are not ready; no evidence bundle was created"
            )

    metadata = build_metadata(args, selected)
    if metadata["chromie"]["dirty"] and not args.allow_dirty and not args.dry_run:
        raise ValueError(
            "Chromie worktree is dirty. Commit the evaluated revision before a "
            "release-evidence run, or use --allow-dirty only for exploratory evidence."
        )

    virtual_microphone = (
        PulseVirtualMicrophone(args.virtual_mic_sink)
        if args.mode == "virtual-mic"
        else None
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
    service_override_path = evidence_dir / "service-overrides.env"
    write_json(evidence_dir / "metadata.json", metadata)
    write_override_file(
        override_path,
        event_path=events_path,
        recordings_dir=recordings_dir,
        soridormi_mcp_url=args.soridormi_mcp_url,
        enable_soridormi=needs_soridormi,
        mode=args.mode,
        virtual_mic_source=(
            virtual_microphone.source_name if virtual_microphone else None
        ),
        acoustic_response_output_mode=args.acoustic_response_output_mode,
    )
    service_overrides = service_runtime_overrides(
        soridormi_mcp_url=args.soridormi_mcp_url,
        enable_soridormi=needs_soridormi,
    )
    if service_overrides:
        write_service_override_file(service_override_path, service_overrides)

    results: list[CaseResult] = []
    process: subprocess.Popen[Any] | None = None
    audio_driver: AcceptanceAudioDriver | None = None
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
        if args.mode == "synthetic":
            (evidence_dir / "audio-devices.log").write_text(
                "synthetic mode: physical input/output devices are not required\n",
                encoding="utf-8",
            )
        else:
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
            service_env = os.environ.copy()
            if service_overrides:
                service_env["CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE"] = str(
                    service_override_path
                )
            run_command(
                ["./scripts/start_services.sh"],
                evidence_dir / "start-services.log",
                env=service_env,
                check=True,
                timeout=args.service_timeout_s,
            )
        if virtual_microphone is not None:
            virtual_microphone.start()
            with (evidence_dir / "audio-devices.log").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(
                    "\n# Temporary virtual microphone\n"
                    f"sink={virtual_microphone.sink_name}\n"
                    f"source={virtual_microphone.source_name}\n"
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
        if args.mode in AUTOMATIC_MODES:
            prompts = [
                step.prompt
                for case_id in selected
                for step in CASES[case_id].spoken_steps
            ]
            print(
                f"Generating {len(dict.fromkeys(prompts))} reusable test utterance(s) "
                f"with Chromie TTS at {args.tts_url}...",
                flush=True,
            )
            fixtures = generate_tts_fixtures(
                texts=prompts,
                output_dir=evidence_dir / "generated-input",
                tts_url=args.tts_url,
                speaker_id=args.tts_speaker_id,
                default_sample_rate=args.tts_sample_rate,
                timeout_s=args.tts_timeout_s,
            )
            write_json(
                evidence_dir / "generated-input" / "manifest.json",
                {
                    text: {
                        "path": str(fixture.path.relative_to(evidence_dir)),
                        "sample_rate": fixture.sample_rate,
                        "channels": fixture.channels,
                        "pcm_bytes": len(fixture.pcm16),
                    }
                    for text, fixture in fixtures.items()
                },
            )
            audio_driver = AcceptanceAudioDriver(
                mode=args.mode,
                fixtures=fixtures,
                virtual_microphone=virtual_microphone,
                speaker_player=(
                    HostSpeakerPlayer(
                        device=os.getenv("ORCH_OUTPUT_DEVICE"),
                        channels=int(os.getenv("ORCH_OUTPUT_CHANNELS", "2")),
                        playback_gain=args.acoustic_playback_gain,
                        player=args.acoustic_player,
                        target=args.acoustic_output_target,
                    )
                    if args.mode == "acoustic"
                    else None
                ),
            )

        environment = os.environ.copy()
        environment["ORCH_RUNTIME_OVERRIDE_FILE"] = str(override_path)
        with orchestrator_log.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                ["./scripts/start_orchestrator.sh"],
                cwd=ROOT,
                env=environment,
                stdin=(subprocess.PIPE if args.mode == "synthetic" else None),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=False,
                start_new_session=True,
            )
        if audio_driver is not None:
            audio_driver.orchestrator_process = process
        readiness_marker = (
            "Audio input started: mode=stdin"
            if args.mode == "synthetic"
            else (
                "Audio input started: mode=device"
                if args.mode == "virtual-mic"
                else "Microphone started"
            )
        )
        wait_for_log(
            process,
            orchestrator_log,
            readiness_marker,
            args.orchestrator_timeout_s,
        )

        print(f"\nVoice acceptance evidence: {evidence_dir}")
        print(f"Acceptance mode: {args.mode}")
        print("The runner is recording structured session events and audio captures.")
        if args.mode == "supervised":
            print("Use only a supervised MuJoCo endpoint for body-skill cases.\n")
        elif args.mode == "acoustic":
            print(
                "Generated test speech will be played through the configured host "
                "output and captured through the configured host input device; no "
                "human speech or operator verdict is required.\n"
            )
        else:
            print(
                "Generated test speech will be supplied automatically; no operator "
                "speech or verdict is required.\n"
            )

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
            if args.mode == "supervised":
                input(
                    "\nPress Enter when you are ready. The runner will count down and "
                    "show SPEAK NOW..."
                )
            else:
                print("\nStarting this case automatically...")
            started = utc_now()
            marker = len(read_events(events_path))
            guidance_checks: list[CheckResult] = []
            case_session_ids: set[str] = set()
            for step_index, step in enumerate(case.spoken_steps, start=1):
                capture = guide_spoken_step(
                    case=case,
                    step=step,
                    step_index=step_index,
                    events_path=events_path,
                    case_marker=marker,
                    countdown_s=args.countdown_s,
                    asr_timeout_s=args.asr_timeout_s,
                    trigger_timeout_s=args.case_timeout_s,
                    asr_retries=args.asr_retries,
                    case_session_ids=case_session_ids,
                    mode=args.mode,
                    audio_driver=audio_driver,
                )
                guidance_checks.append(capture.check)
                if not capture.check.passed:
                    break

            if all(item.passed for item in guidance_checks):
                print(
                    f"\nAll utterances were captured. Waiting up to "
                    f"{args.case_timeout_s:.0f}s for the case evidence to complete..."
                )
                case_events, event_checks = wait_for_case_checks(
                    case_id,
                    events_path,
                    marker=marker,
                    timeout_s=args.case_timeout_s,
                    session_ids=case_session_ids,
                    show_progress=True,
                )
            else:
                case_events = events_for_sessions(
                    read_events(events_path)[marker:],
                    case_session_ids,
                )
                event_checks = analyze_case(case_id, case_events)

            time.sleep(args.settle_s)
            checks = guidance_checks + event_checks
            print("\nAutomated evidence checks:")
            for item in checks:
                symbol = "PASS" if item.passed else "FAIL"
                print(f"  [{symbol}] {item.name}: {item.detail}")
            automated_passed = bool(checks) and all(item.passed for item in checks)
            if automated_passed:
                if args.mode == "supervised":
                    verdict = prompt_verdict()
                    notes = input(
                        "Operator notes (required for fail/skip; optional for pass): "
                    ).strip()
                    if verdict != "pass" and not notes:
                        notes = "No operator notes supplied."
                else:
                    verdict = "automated"
                    notes = f"Automatically passed in {args.mode} mode."
                    print(f"[AUTO-PASS] {case_id} completed in {args.mode} mode.")
            else:
                verdict = "fail"
                failed_names = ", ".join(
                    item.name for item in checks if not item.passed
                )
                notes = f"Automatically failed: {failed_names or 'missing evidence'}"
                print(
                    "\n[AUTO-FAIL] Required machine evidence is missing. "
                    "An operator pass cannot override this result."
                )

            result = CaseResult(
                case_id=case_id,
                title=case.title,
                started_utc=started,
                finished_utc=utc_now(),
                event_count=len(case_events),
                session_ids=sorted(case_session_ids),
                checks=[asdict(item) for item in checks],
                operator_verdict=verdict,
                operator_notes=notes,
            )
            results.append(result)
            write_json(evidence_dir / "cases.json", [asdict(item) for item in results])

            if not result.passed and not args.continue_after_failure:
                print(
                    "\nStopping after the failed case. Fix the issue and rerun, or use "
                    "--continue-after-failure for exploratory collection."
                )
                break

        final_status = "passed" if all(item.passed for item in results) else "failed"
        return 0 if final_status == "passed" else 1
    except KeyboardInterrupt:
        final_status = "aborted"
        return 130
    finally:
        if process is not None and process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass
        stop_process(process)
        if virtual_microphone is not None:
            virtual_microphone.stop()
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
        metadata["event_count"] = (
            0 if final_status == "dry-run" else len(read_events(events_path))
        )
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
        print(f"\nVoice acceptance status: {final_status}")
        print(f"Evidence bundle: {evidence_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=ACCEPTANCE_MODES,
        default="synthetic",
        help=(
            "synthetic: TTS -> framed Orchestrator input (default); virtual-mic: "
            "TTS -> Pulse/PipeWire monitor source; acoustic: TTS -> host output "
            "-> host input device; supervised: real microphone with operator "
            "confirmation."
        ),
    )
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
        "--tts-url",
        default=os.getenv("TTS_URL", "ws://127.0.0.1:5000"),
        help="Chromie TTS websocket used to generate automated input fixtures.",
    )
    parser.add_argument(
        "--tts-speaker-id",
        default=os.getenv("TTS_SPEAKER_ID", "default"),
    )
    parser.add_argument(
        "--tts-sample-rate",
        type=int,
        default=int(os.getenv("TTS_SAMPLE_RATE", "44100")),
        help="Fallback rate when the TTS start frame omits sample_rate.",
    )
    parser.add_argument(
        "--tts-timeout-s",
        type=float,
        default=180.0,
        help="Per-utterance timeout while generating automatic TTS fixtures.",
    )
    parser.add_argument(
        "--virtual-mic-sink",
        default="chromie_voice_test",
        help="Temporary PulseAudio/PipeWire null-sink name for virtual-mic mode.",
    )
    parser.add_argument(
        "--acoustic-playback-gain",
        type=float,
        default=float(os.getenv("ACCEPTANCE_ACOUSTIC_PLAYBACK_GAIN", "1.0")),
        help="Software gain for generated prompt playback in acoustic mode.",
    )
    parser.add_argument(
        "--acoustic-player",
        choices=("auto", "pw-play", "paplay", "aplay", "sounddevice"),
        default=os.getenv("ACCEPTANCE_ACOUSTIC_PLAYER", "auto"),
        help="Host playback backend for acoustic mode.",
    )
    parser.add_argument(
        "--acoustic-output-target",
        default=os.getenv("ACCEPTANCE_ACOUSTIC_OUTPUT_TARGET"),
        help="Optional host audio target name or node for acoustic playback.",
    )
    parser.add_argument(
        "--acoustic-response-output-mode",
        choices=("discard", "device"),
        default=os.getenv("ACCEPTANCE_ACOUSTIC_RESPONSE_OUTPUT_MODE", "discard"),
        help=(
            "Orchestrator response playback mode during acoustic acceptance. "
            "Generated test prompts still play through the host audio player."
        ),
    )
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
        "--preflight-only",
        action="store_true",
        help=(
            "Check acceptance prerequisites and exit without starting services "
            "or creating an evidence bundle."
        ),
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit exploratory evidence from an uncommitted tree; release verification will still warn/fail.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--settle-s", type=float, default=1.0)
    parser.add_argument(
        "--countdown-s",
        type=int,
        default=3,
        help="Countdown shown before each spoken utterance.",
    )
    parser.add_argument(
        "--asr-timeout-s",
        type=float,
        default=20.0,
        help="Maximum time to wait for an asr_final event after each input utterance.",
    )
    parser.add_argument(
        "--asr-retries",
        type=int,
        default=1,
        help=(
            "Automatic retries when ASR produces no transcript or misses the "
            "case's intent keywords."
        ),
    )
    parser.add_argument(
        "--case-timeout-s",
        type=float,
        default=60.0,
        help="Maximum time to wait for case triggers and automated evidence.",
    )
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help=(
            "Continue collecting later cases after an automatic or operator failure. "
            "The default stops at the first failed case."
        ),
    )
    parser.add_argument("--orchestrator-timeout-s", type=float, default=240.0)
    parser.add_argument("--service-timeout-s", type=float, default=900.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_acceptance(args)
    except (ValueError, FileExistsError, RuntimeError, TimeoutError) as exc:
        print(f"[voice-acceptance][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    ensure_acceptance_runtime(sys.argv[1:])
    raise SystemExit(main())
