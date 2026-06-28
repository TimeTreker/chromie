"""Environment loading and validation for the Chromie developer CLI."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

BOOL_VARS = (
    "ROUTER_USE_LLM",
    "AGENT_NATIVE_INTERACTION_FALLBACK",
    "AGENT_ENABLE_TASK_GRAPH_PLANNING",
    "AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION",
    "ORCH_ENABLE_ROUTER",
    "ORCH_ENABLE_AGENT",
    "ORCH_ENABLE_INTERACTION_RESPONSE",
    "ORCH_ENABLE_SORIDORMI_SKILLS",
    "ORCH_AUTO_CONFIRM_SIM_SKILLS",
    "ORCH_ENABLE_CONVERSATION_STATE",
    "ORCH_ACTION_DRY_RUN",
    "ORCH_SAVE_AUDIO",
)

POSITIVE_INT_VARS = (
    "ROUTER_TIMEOUT_MS",
    "ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS",
    "ROUTER_CAPABILITY_MATCH_LIMIT",
    "AGENT_MAX_SPEAK_CHARS",
    "AGENT_TASK_GRAPH_MAX_CONCURRENCY",
    "AGENT_TASK_GRAPH_TRACE_MAX_ENTRIES",
    "AGENT_TASK_GRAPH_TRACE_TTL_SEC",
    "AGENT_TASK_GRAPH_GRANT_MAX_ENTRIES",
    "AGENT_CAPABILITY_CATALOG_REFRESH_SEC",
    "AGENT_CAPABILITY_MATCH_LIMIT",
    "AGENT_CAPABILITY_NUM_CTX",
    "AGENT_CAPABILITY_NUM_PREDICT",
    "ORCH_CONVERSATION_MAX_TURNS",
    "ORCH_CONVERSATION_IDLE_TIMEOUT_SEC",
    "ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC",
    "ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS",
    "ORCH_CONVERSATION_MAX_CONTEXT_CHARS",
    "ORCH_CONVERSATION_MAX_PENDING_TASKS",
    "TTS_MAX_CONCURRENT_SYNTHESIS",
    "TTS_GENERATION_RETRIES",
    "TTS_WORKER_STARTUP_TIMEOUT_SEC",
    "TTS_MIN_TEXT_CHARS",
    "TTS_MAX_TEXT_CHARS",
    "TTS_SAMPLE_RATE",
    "TTS_CHUNK_MS",
    "TTS_WORKER_COUNT",
    "ORCH_CONFIRMATION_TTL_SEC",
    "ORCH_SKILL_MAX_CONCURRENCY",
    "ORCH_ROUTER_TIMEOUT_MS",
    "ORCH_ASR_TIMEOUT_MS",
    "ORCH_ACTION_TIMEOUT_MS",
    "TTS_FLUSH_CHARS",
    "ORCH_TTS_CHUNK_CHARS",
    "ORCH_TTS_MIN_CHUNK_CHARS",
    "ORCH_TTS_PLAYBACK_START_TIMEOUT_MS",
    "ASR_BEAM_SIZE",
    "ASR_MAX_CONCURRENT_TRANSCRIPTIONS",
    "AGENT_TIMEOUT_MS",
    "ORCH_AGENT_TIMEOUT_MS",
    "TTS_THREADS",
)

URL_VARS = (
    "ROUTER_URL",
    "AGENT_URL",
    "ACTION_EXECUTOR_URL",
    "ROUTER_CAPABILITY_CATALOG_URL",
    "ASR_URL",
    "TTS_URL",
    "LLM_URL",
    "SORIDORMI_MCP_URL",
)

STATUS_KEYS = (
    "CHROMIE_ACTIVE_PROFILE",
    "CHROMIE_HARDWARE_PROFILE",
    "ORCH_ENABLE_ROUTER",
    "ORCH_ENABLE_AGENT",
    "ORCH_ENABLE_INTERACTION_RESPONSE",
    "ORCH_ENABLE_SORIDORMI_SKILLS",
    "ORCH_AUTO_CONFIRM_SIM_SKILLS",
    "ORCH_ACTION_DRY_RUN",
    "AGENT_INTERACTION_OUTPUT_MODE",
    "AGENT_NATIVE_INTERACTION_FALLBACK",
    "AGENT_ENABLE_TASK_GRAPH_PLANNING",
    "AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION",
    "AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION",
    "ROUTER_URL",
    "AGENT_URL",
    "ASR_URL",
    "TTS_URL",
    "LLM_URL",
    "SORIDORMI_MCP_URL",
    "ORCH_SORIDORMI_MANIFEST",
)


@dataclass(frozen=True)
class Diagnostic:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class EnvSnapshot:
    root: Path
    values: dict[str, str]
    sources: list[str]
    runtime_file_used: bool
    active_profile: str
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def get(self, name: str, default: str = "") -> str:
        return self.values.get(name, default)

    def bool_value(self, name: str, default: bool = False) -> bool:
        parsed = parse_bool(self.values.get(name, ""))
        if parsed is None:
            return default
        return parsed


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        if (
            len(value) >= 2
            and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]
        values[name] = value
    return values


def parse_bool(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    return None


def parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def load_env(root: Path) -> EnvSnapshot:
    root = root.resolve()
    diagnostics: list[Diagnostic] = []
    runtime = root / ".env.runtime"
    if runtime.exists():
        values = parse_env_file(runtime)
        profile = values.get(
            "CHROMIE_ACTIVE_PROFILE",
            values.get("CHROMIE_HARDWARE_PROFILE", "unknown"),
        )
        return EnvSnapshot(
            root=root,
            values=values,
            sources=[".env.runtime"],
            runtime_file_used=True,
            active_profile=profile,
            diagnostics=diagnostics,
        )

    values: dict[str, str] = {}
    sources: list[str] = []
    common = root / ".env.common"
    if common.exists():
        values.update(parse_env_file(common))
        sources.append(".env.common")
    else:
        diagnostics.append(
            Diagnostic("failure", "missing_common_env", "Missing .env.common")
        )

    local_values = parse_env_file(root / ".env.local")
    profile = (
        local_values.get("CHROMIE_HARDWARE_PROFILE")
        or values.get("CHROMIE_HARDWARE_PROFILE")
        or "default"
    )
    profile_path = root / "env" / "profiles" / f"{profile}.env"
    if not profile_path.exists() and profile != "default":
        diagnostics.append(
            Diagnostic(
                "warning",
                "missing_selected_profile",
                f"Missing env/profiles/{profile}.env; using default profile values",
            )
        )
        profile = "default"
        profile_path = root / "env" / "profiles" / "default.env"
    if profile_path.exists():
        values.update(parse_env_file(profile_path))
        sources.append(str(profile_path.relative_to(root)))
    else:
        diagnostics.append(
            Diagnostic(
                "failure",
                "missing_profile_env",
                f"Missing env/profiles/{profile}.env",
            )
        )
    if local_values:
        values.update(local_values)
        sources.append(".env.local")
    values.setdefault("CHROMIE_ACTIVE_PROFILE", profile)
    return EnvSnapshot(
        root=root,
        values=values,
        sources=sources,
        runtime_file_used=False,
        active_profile=profile,
        diagnostics=diagnostics,
    )


def deployment_mode(snapshot: EnvSnapshot) -> str:
    interaction = snapshot.bool_value("ORCH_ENABLE_INTERACTION_RESPONSE")
    soridormi = snapshot.bool_value("ORCH_ENABLE_SORIDORMI_SKILLS")
    physical = snapshot.bool_value("AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION")
    if physical:
        return "physical_robot_unsupported"
    if interaction and soridormi:
        return "structured_mujoco"
    if interaction:
        return "structured_speech"
    return "compatibility_voice"


def selected_status_values(snapshot: EnvSnapshot) -> dict[str, str]:
    return {
        name: snapshot.values[name]
        for name in STATUS_KEYS
        if name in snapshot.values and snapshot.values[name] != ""
    }


def validate_config(snapshot: EnvSnapshot) -> list[Diagnostic]:
    diagnostics = list(snapshot.diagnostics)
    values = snapshot.values

    for name in BOOL_VARS:
        if name in values and parse_bool(values[name]) is None:
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "invalid_bool",
                    f"{name} must be one of 1/0, true/false, yes/no, or on/off",
                )
            )

    for name in POSITIVE_INT_VARS:
        if name in values and parse_positive_int(values[name]) is None:
            diagnostics.append(
                Diagnostic("failure", "invalid_positive_int", f"{name} must be > 0")
            )

    for name in URL_VARS:
        value = values.get(name, "")
        if value and not _url_has_scheme_and_host(value):
            diagnostics.append(
                Diagnostic("failure", "invalid_url", f"{name} is not a valid URL")
            )

    _compare_timeout(
        diagnostics,
        values,
        host_name="ORCH_ROUTER_TIMEOUT_MS",
        service_name="ROUTER_TIMEOUT_MS",
    )
    _compare_timeout(
        diagnostics,
        values,
        host_name="ORCH_AGENT_TIMEOUT_MS",
        service_name="AGENT_TIMEOUT_MS",
    )

    interaction = snapshot.bool_value("ORCH_ENABLE_INTERACTION_RESPONSE")
    soridormi = snapshot.bool_value("ORCH_ENABLE_SORIDORMI_SKILLS")
    physical = snapshot.bool_value("AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION")
    guarded = snapshot.bool_value("AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION")

    if soridormi and not interaction:
        diagnostics.append(
            Diagnostic(
                "failure",
                "soridormi_requires_interaction",
                "ORCH_ENABLE_SORIDORMI_SKILLS=1 requires ORCH_ENABLE_INTERACTION_RESPONSE=1",
            )
        )
    if soridormi and not values.get("SORIDORMI_MCP_URL", "").strip():
        diagnostics.append(
            Diagnostic(
                "failure",
                "missing_soridormi_url",
                "Structured Soridormi mode requires SORIDORMI_MCP_URL",
            )
        )
    manifest = values.get("ORCH_SORIDORMI_MANIFEST", "")
    if soridormi and manifest and not (snapshot.root / manifest).exists():
        diagnostics.append(
            Diagnostic(
                "failure",
                "missing_soridormi_manifest",
                f"ORCH_SORIDORMI_MANIFEST does not exist: {manifest}",
            )
        )
    if physical:
        diagnostics.append(
            Diagnostic(
                "failure",
                "physical_execution_unsupported",
                "AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION must remain off until commissioning evidence exists",
            )
        )
    if physical and not guarded:
        diagnostics.append(
            Diagnostic(
                "failure",
                "physical_requires_guarded",
                "Physical TaskGraph execution requires guarded execution",
            )
        )
    if guarded and not values.get("AGENT_TASK_GRAPH_EXECUTION_TOKEN", "").strip():
        diagnostics.append(
            Diagnostic(
                "failure",
                "missing_execution_token",
                "Guarded TaskGraph execution requires AGENT_TASK_GRAPH_EXECUTION_TOKEN",
            )
        )
    if not snapshot.bool_value("ORCH_ACTION_DRY_RUN", default=True):
        diagnostics.append(
            Diagnostic(
                "warning",
                "legacy_action_dry_run_disabled",
                "ORCH_ACTION_DRY_RUN=false can call the legacy mock hardware daemon",
            )
        )
    return diagnostics


def summarize_diagnostics(diagnostics: list[Diagnostic]) -> tuple[str, int]:
    from .output import ExitCode

    if any(item.level == "failure" for item in diagnostics):
        return "failure", int(ExitCode.FAILURE)
    if any(item.level == "warning" for item in diagnostics):
        return "warning", int(ExitCode.WARNING)
    return "ok", int(ExitCode.OK)


def diagnostics_by_level(diagnostics: list[Diagnostic]) -> dict[str, list[str]]:
    return {
        level: [item.message for item in diagnostics if item.level == level]
        for level in ("failure", "warning", "skip", "ok")
        if any(item.level == level for item in diagnostics)
    }


def service_endpoint(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.hostname:
        return None
    if parsed.port:
        return parsed.hostname, parsed.port
    if parsed.scheme in {"https", "wss"}:
        return parsed.hostname, 443
    return parsed.hostname, 80


def _url_has_scheme_and_host(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "ws", "wss"} and bool(parsed.hostname)


def _compare_timeout(
    diagnostics: list[Diagnostic],
    values: dict[str, str],
    *,
    host_name: str,
    service_name: str,
) -> None:
    if host_name not in values or service_name not in values:
        return
    host_value = parse_positive_int(values[host_name])
    service_value = parse_positive_int(values[service_name])
    if host_value is None or service_value is None:
        return
    if host_value <= service_value:
        diagnostics.append(
            Diagnostic(
                "failure",
                "host_timeout_too_short",
                f"{host_name} must exceed {service_name}",
            )
        )


def can_open_tcp(host: str, port: int, timeout_s: float = 0.25) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, "reachable"
    except OSError as exc:
        return False, str(exc)


def diagnostic_counts(diagnostics: list[Diagnostic]) -> dict[str, int]:
    return {
        level: sum(1 for item in diagnostics if item.level == level)
        for level in ("ok", "warning", "failure", "skip")
    }


def diagnostics_payload(diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    return [
        {"level": item.level, "code": item.code, "message": item.message}
        for item in diagnostics
    ]
