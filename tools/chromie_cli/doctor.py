"""Doctor command for local Chromie diagnostics."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .env import (
    Diagnostic,
    can_open_tcp,
    deployment_mode,
    diagnostic_counts,
    diagnostics_payload,
    load_env,
    service_endpoint,
    validate_config,
)
from .output import CommandResult, ExitCode


def doctor(root: Path) -> CommandResult:
    snapshot = load_env(root)
    diagnostics = validate_config(snapshot)
    diagnostics.extend(_environment_checks())
    diagnostics.extend(_file_checks(snapshot.root))
    diagnostics.extend(_service_checks(snapshot))
    diagnostics.extend(_audio_checks(snapshot))

    if any(item.level == "failure" for item in diagnostics):
        status = "failure"
        exit_code = ExitCode.FAILURE
    elif any(item.level == "warning" for item in diagnostics):
        status = "warning"
        exit_code = ExitCode.WARNING
    else:
        status = "ok"
        exit_code = ExitCode.OK

    return CommandResult(
        status=status,
        message="Chromie doctor checks complete.",
        details={
            "mode": deployment_mode(snapshot),
            "active_profile": snapshot.active_profile,
            "counts": diagnostic_counts(diagnostics),
            "diagnostics": diagnostics_payload(diagnostics),
        },
        exit_code=exit_code,
    )


def _environment_checks() -> list[Diagnostic]:
    diagnostics = [
        Diagnostic(
            "ok",
            "python_version",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    ]
    docker = shutil.which("docker")
    if docker:
        diagnostics.append(Diagnostic("ok", "docker_binary", f"docker found at {docker}"))
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            diagnostics.append(
                Diagnostic("warning", "docker_compose_unavailable", str(exc))
            )
        else:
            diagnostics.append(
                Diagnostic("ok", "docker_compose_available", "docker compose is available")
            )
    else:
        diagnostics.append(
            Diagnostic("warning", "docker_missing", "docker is not on PATH")
        )
        diagnostics.append(
            Diagnostic(
                "skip",
                "docker_compose_skipped",
                "docker compose check skipped because docker is missing",
            )
        )
    return diagnostics


def _file_checks(root: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for relative in (".env.common", ".env.runtime", ".env", "capabilities/soridormi.json"):
        path = root / relative
        if path.exists():
            diagnostics.append(Diagnostic("ok", "file_present", f"{relative} exists"))
        elif relative in {".env.runtime", ".env"}:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "generated_file_missing",
                    f"{relative} is missing; run scripts/build_runtime_env.sh",
                )
            )
        else:
            diagnostics.append(Diagnostic("failure", "file_missing", f"{relative} is missing"))

    manifest = root / "capabilities" / "soridormi.json"
    if manifest.exists():
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "manifest_json_invalid",
                    f"capabilities/soridormi.json is invalid JSON: {exc}",
                )
            )
        else:
            diagnostics.append(
                Diagnostic("ok", "manifest_json_valid", "capabilities/soridormi.json parses")
            )
    return diagnostics


def _service_checks(snapshot) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    checks = {
        "router": snapshot.get("ROUTER_URL"),
        "agent": snapshot.get("AGENT_URL"),
        "action_executor": snapshot.get("ACTION_EXECUTOR_URL"),
        "asr": snapshot.get("ASR_URL", "ws://127.0.0.1:9001"),
        "tts": snapshot.get("TTS_URL", "ws://127.0.0.1:5000"),
        "ollama": snapshot.get("LLM_URL", "http://127.0.0.1:11434/api/generate"),
        "soridormi": snapshot.get("SORIDORMI_MCP_URL"),
    }
    for name, url in checks.items():
        if not url:
            diagnostics.append(
                Diagnostic("skip", f"{name}_url_missing", f"{name} URL is not configured")
            )
            continue
        endpoint = service_endpoint(url)
        if endpoint is None:
            diagnostics.append(
                Diagnostic("failure", f"{name}_url_invalid", f"{name} URL is invalid: {url}")
            )
            continue
        host, port = endpoint
        ok, cause = can_open_tcp(host, port)
        if ok:
            diagnostics.append(
                Diagnostic("ok", f"{name}_reachable", f"{name} reachable at {host}:{port}")
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    f"{name}_unreachable",
                    f"{name} not reachable at {host}:{port}: {cause}",
                )
            )
    return diagnostics


def _audio_checks(snapshot) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    input_device = snapshot.get("ORCH_INPUT_DEVICE")
    output_device = snapshot.get("ORCH_OUTPUT_DEVICE")
    if input_device:
        diagnostics.append(
            Diagnostic("ok", "audio_input_configured", f"ORCH_INPUT_DEVICE={input_device}")
        )
    else:
        diagnostics.append(
            Diagnostic("skip", "audio_input_unconfigured", "ORCH_INPUT_DEVICE is not configured")
        )
    if output_device:
        diagnostics.append(
            Diagnostic("ok", "audio_output_configured", f"ORCH_OUTPUT_DEVICE={output_device}")
        )
    else:
        diagnostics.append(
            Diagnostic(
                "skip",
                "audio_output_unconfigured",
                "ORCH_OUTPUT_DEVICE is not configured",
            )
        )
    return diagnostics
