#!/usr/bin/env python3
"""Generate and validate Chromie's hardware-aware runtime environment.

This is the only supported hardware-profile resolver. It always detects the
current machine from a fresh system-information snapshot, selects the matching
committed profile, merges configuration deterministically, and writes a flat
.env.runtime with one value per key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Mapping

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MODEL_PLAN_KEYS = (
    "AGENT_MODEL",
    "OLLAMA_MODEL",
    "ROUTER_MODEL",
    "ROUTER_REVIEW_MODEL",
    "AGENT_GOAL_ASSOCIATION_MODEL",
    "AGENT_FAST_PLANNER_MODEL",
    "AGENT_DEEP_PLANNER_MODEL",
    "AGENT_RESPONSE_COMPOSER_MODEL",
    "AGENT_TASK_CONTINUITY_MODEL",
    "AGENT_SOCIAL_ATTENTION_MODEL",
    "AGENT_RESPONSE_REVIEW_MODEL",
)

COGNITIVE_BUDGET_KEYS = (
    "CHROMIE_COGNITIVE_BUDGET_PROFILE",
    "ROUTER_TIMEOUT_MS",
    "AGENT_GOAL_ASSOCIATION_TIMEOUT_MS",
    "AGENT_FAST_PLANNER_TIMEOUT_MS",
    "AGENT_DEEP_PLANNER_TIMEOUT_MS",
    "AGENT_RESPONSE_COMPOSER_TIMEOUT_MS",
    "ORCH_ROUTER_TIMEOUT_MS",
    "ORCH_GOAL_ASSOCIATION_TIMEOUT_MS",
    "ORCH_FAST_PLANNER_TIMEOUT_MS",
    "ORCH_DEEP_PLANNER_TIMEOUT_MS",
    "ORCH_RESPONSE_COMPOSER_TIMEOUT_MS",
    "ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS",
)

REQUIRED_PROFILE_KEYS = (
    "CHROMIE_HARDWARE_PROFILE",
    "CHROMIE_ARCH",
    "CHROMIE_GPU_VENDOR",
    "CHROMIE_GPU_CLASS",
    "TTS_CUDA_ARCH",
    *MODEL_PLAN_KEYS,
)

IDENTITY_KEYS = {
    "CHROMIE_HARDWARE_PROFILE",
    "CHROMIE_ACTIVE_PROFILE",
    "CHROMIE_ACTIVE_VALIDATION_PROFILE",
    "CHROMIE_SYSTEM_INFO_FILE",
    "CHROMIE_RUNTIME_ENV_FINGERPRINT",
    "CHROMIE_CPU_ARCH",
    "CHROMIE_CPU_MODEL",
    "CHROMIE_CPU_CORES",
    "CHROMIE_MEM_TOTAL_MIB",
    "CHROMIE_IS_JETSON",
    "CHROMIE_JETSON_MODEL",
    "CHROMIE_NVIDIA_GPU_NAME",
    "CHROMIE_NVIDIA_COMPUTE_CAP",
    "CHROMIE_NVIDIA_MEMORY_TOTAL_MIB",
    "CHROMIE_DETECTED_CUDA_ARCH",
}


class ConfigurationError(RuntimeError):
    """Raised when profile configuration cannot be trusted."""


def _parse_value(raw: str, *, path: Path, line_number: int) -> str:
    value = raw.strip()
    if value == "":
        return ""
    try:
        tokens = shlex.split(value, comments=False, posix=True)
    except ValueError as exc:
        raise ConfigurationError(
            f"{path}:{line_number}: invalid shell/env value: {exc}"
        ) from exc
    if len(tokens) == 0:
        return ""
    if len(tokens) != 1:
        raise ConfigurationError(
            f"{path}:{line_number}: values containing spaces must be quoted or escaped"
        )
    return tokens[0]


def parse_env_file(path: Path, *, required: bool = True) -> OrderedDict[str, str]:
    if not path.exists():
        if required:
            raise ConfigurationError(f"missing required environment file: {path}")
        return OrderedDict()

    values: OrderedDict[str, str] = OrderedDict()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            raise ConfigurationError(
                f"{path}:{line_number}: expected KEY=VALUE, got {raw_line!r}"
            )
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not KEY_RE.fullmatch(key):
            raise ConfigurationError(f"{path}:{line_number}: invalid variable name {key!r}")
        if key in values:
            raise ConfigurationError(f"{path}:{line_number}: duplicate variable {key}")
        values[key] = _parse_value(raw_value, path=path, line_number=line_number)
    return values


def shell_quote(value: str) -> str:
    # POSIX shell quoting is accepted by Docker Compose env files and by
    # `source .env.runtime`. Empty strings remain explicit rather than missing.
    return shlex.quote(value)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def run_checked(command: Iterable[str], *, cwd: Path, env: Mapping[str, str] | None = None) -> str:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise ConfigurationError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout


def collect_system_info(root: Path, destination: Path, supplied: Path | None) -> OrderedDict[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if supplied is not None:
        supplied = supplied.resolve()
        if not supplied.is_file():
            raise ConfigurationError(f"system-info file does not exist: {supplied}")
        content = supplied.read_text(encoding="utf-8")
    else:
        content = run_checked([str(root / "scripts" / "collect_system_info.sh")], cwd=root)
    values_path = supplied if supplied is not None else destination
    if supplied is not None:
        # Keep a reproducible copy in the normal generated location.
        atomic_write(destination, content if content.endswith("\n") else content + "\n")
        values_path = destination
    else:
        atomic_write(destination, content if content.endswith("\n") else content + "\n")
    return parse_env_file(values_path)


def detect_profile(root: Path, system_info_path: Path) -> str:
    env = dict(os.environ)
    env["CHROMIE_SYSTEM_INFO_FILE"] = str(system_info_path)
    detected = run_checked(
        [str(root / "scripts" / "detect_hardware_profile.sh")],
        cwd=root,
        env=env,
    ).strip()
    if not detected or not re.fullmatch(r"[a-z0-9_]+", detected):
        raise ConfigurationError(f"hardware detector returned invalid profile name: {detected!r}")
    return detected


def _require_nonempty(values: Mapping[str, str], keys: Iterable[str], *, source: Path) -> None:
    missing = [key for key in keys if not values.get(key)]
    if missing:
        raise ConfigurationError(
            f"hardware profile {source} is incomplete; missing non-empty values: {', '.join(missing)}"
        )


def validate_profile(
    profile_name: str,
    profile_path: Path,
    profile: Mapping[str, str],
    system_info: Mapping[str, str],
) -> None:
    _require_nonempty(profile, REQUIRED_PROFILE_KEYS, source=profile_path)
    declared = profile["CHROMIE_HARDWARE_PROFILE"]
    if declared != profile_name:
        raise ConfigurationError(
            f"{profile_path} declares CHROMIE_HARDWARE_PROFILE={declared!r}; expected {profile_name!r}"
        )

    detected_arch = system_info.get("CHROMIE_CPU_ARCH", "")
    profile_arch = profile.get("CHROMIE_ARCH", "")
    if profile_name != "default" and detected_arch and detected_arch != "unknown" and profile_arch != detected_arch:
        raise ConfigurationError(
            f"profile {profile_name} expects CPU architecture {profile_arch}, detected {detected_arch}"
        )

    detected_gpu = system_info.get("CHROMIE_NVIDIA_GPU_NAME", "")
    if detected_gpu and profile.get("CHROMIE_GPU_VENDOR") != "nvidia":
        raise ConfigurationError(
            f"profile {profile_name} is inconsistent with detected NVIDIA GPU {detected_gpu!r}"
        )

    detected_cuda_arch = system_info.get("CHROMIE_DETECTED_CUDA_ARCH", "")
    configured_cuda_arch = profile.get("TTS_CUDA_ARCH", "")
    if detected_cuda_arch and configured_cuda_arch != detected_cuda_arch:
        raise ConfigurationError(
            f"profile {profile_name} sets TTS_CUDA_ARCH={configured_cuda_arch}, "
            f"but hardware detection reported {detected_cuda_arch}"
        )


def resolve_validation_profile(local: Mapping[str, str]) -> str:
    process_value = os.environ.get("CHROMIE_VALIDATION_PROFILE", "").strip()
    local_value = local.get("CHROMIE_VALIDATION_PROFILE", "").strip()
    if process_value and local_value and process_value != local_value:
        raise ConfigurationError(
            "CHROMIE_VALIDATION_PROFILE differs between the process environment and .env.local"
        )
    value = process_value or local_value
    if value and not re.fullmatch(r"[a-z0-9_]+", value):
        raise ConfigurationError(f"invalid validation profile name: {value!r}")
    return value


def merge_runtime_environment(
    *,
    system_info: Mapping[str, str],
    common: Mapping[str, str],
    profile: Mapping[str, str],
    validation: Mapping[str, str],
    local: Mapping[str, str],
    profile_name: str,
    validation_profile: str,
    system_info_path: Path,
    strict_local_conflicts: bool,
) -> tuple[OrderedDict[str, str], dict[str, str], list[str]]:
    profile_owned_local = (set(profile) | set(validation) | IDENTITY_KEYS) & set(local)
    profile_owned_local.discard("CHROMIE_VALIDATION_PROFILE")
    ignored_local_overrides = sorted(profile_owned_local)
    if ignored_local_overrides and strict_local_conflicts:
        keys = ", ".join(ignored_local_overrides)
        raise ConfigurationError(
            ".env.local overrides hardware/validation-owned settings: "
            f"{keys}. Remove those values or unset CHROMIE_ENV_STRICT so the detected "
            "profile can ignore them and remain authoritative."
        )

    allowed_local = OrderedDict(
        (key, value)
        for key, value in local.items()
        if key not in profile_owned_local
    )

    resolved: OrderedDict[str, str] = OrderedDict()
    provenance: dict[str, str] = {}

    def apply(source_name: str, values: Mapping[str, str]) -> None:
        for key, value in values.items():
            resolved[key] = value
            provenance[key] = source_name

    apply("system_info", system_info)
    apply("common", common)
    apply(f"profile:{profile_name}", profile)
    if validation:
        apply(f"validation:{validation_profile}", validation)
    apply("local", allowed_local)

    resolved["CHROMIE_ACTIVE_PROFILE"] = profile_name
    provenance["CHROMIE_ACTIVE_PROFILE"] = "generator"
    resolved["CHROMIE_ACTIVE_VALIDATION_PROFILE"] = validation_profile or "none"
    provenance["CHROMIE_ACTIVE_VALIDATION_PROFILE"] = "generator"
    resolved["CHROMIE_SYSTEM_INFO_FILE"] = str(system_info_path)
    provenance["CHROMIE_SYSTEM_INFO_FILE"] = "generator"

    _require_nonempty(resolved, MODEL_PLAN_KEYS, source=Path(f"env/profiles/{profile_name}.env"))
    return resolved, provenance, ignored_local_overrides


def runtime_fingerprint(
    resolved: Mapping[str, str],
    *,
    profile_name: str,
    validation_profile: str,
) -> str:
    payload = {
        "profile": profile_name,
        "validation_profile": validation_profile or "none",
        "values": dict(sorted(resolved.items())),
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def active_models(values: Mapping[str, str]) -> list[str]:
    models: list[str] = []

    def append(value: str | None) -> None:
        if value and value not in models:
            models.append(value)

    if enabled(values.get("ROUTER_USE_LLM")):
        append(values.get("ROUTER_MODEL"))
        if values.get("ROUTER_REVIEW_MODEL") and (
            enabled(values.get("ROUTER_POST_INTERRUPT_REVIEW_ENABLED"))
            or enabled(values.get("ROUTER_SLOW_REVIEW_RECOVERY_ENABLED"), default=True)
            or enabled(values.get("ROUTER_GENERIC_CHAT_REVIEW_ENABLED"), default=True)
        ):
            append(values.get("ROUTER_REVIEW_MODEL"))

    if enabled(values.get("AGENT_USE_LLM"), default=True):
        append(values.get("AGENT_MODEL") or values.get("OLLAMA_MODEL"))
    if enabled(values.get("AGENT_GOAL_ASSOCIATION_ENABLED"), default=True):
        append(values.get("AGENT_GOAL_ASSOCIATION_MODEL"))
    if enabled(values.get("AGENT_FAST_PLANNER_ENABLED"), default=True):
        append(values.get("AGENT_FAST_PLANNER_MODEL"))
    if enabled(values.get("AGENT_DEEP_PLANNER_ENABLED"), default=True):
        append(values.get("AGENT_DEEP_PLANNER_MODEL"))
    if enabled(values.get("AGENT_RESPONSE_COMPOSER_ENABLED"), default=True):
        append(values.get("AGENT_RESPONSE_COMPOSER_MODEL"))
    if enabled(values.get("AGENT_TASK_CONTINUITY_ENABLED"), default=True):
        append(values.get("AGENT_TASK_CONTINUITY_MODEL"))
    if values.get("AGENT_SOCIAL_ATTENTION_MODE", "off") != "off":
        append(values.get("AGENT_SOCIAL_ATTENTION_MODEL"))
    if enabled(values.get("AGENT_RESPONSE_REVIEW_ENABLED")):
        append(values.get("AGENT_RESPONSE_REVIEW_MODEL"))
    return models


def render_env(values: Mapping[str, str], provenance: Mapping[str, str]) -> str:
    lines = [
        "# Generated by scripts/generate_runtime_env.py",
        "# Do not edit. Hardware is detected automatically on every supported build/start.",
        "# Edit .env.common, env/profiles/*.env, env/validation/*.env, or allowed .env.local keys.",
        "",
    ]
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    for key in values:
        grouped.setdefault(provenance.get(key, "generator"), []).append(key)
    for index, (source, keys) in enumerate(grouped.items()):
        if index:
            lines.append("")
        lines.append(f"# ---- {source} ----")
        for key in keys:
            lines.append(f"{key}={shell_quote(values[key])}")
    return "\n".join(lines) + "\n"


def generate(root: Path, *, supplied_system_info: Path | None = None) -> dict[str, object]:
    root = root.resolve()
    common_path = root / ".env.common"
    local_path = root / ".env.local"
    runtime_path = root / ".env.runtime"
    compose_env_path = root / ".env"
    system_info_path = root / ".chromie" / "system_info.env"
    manifest_path = root / ".chromie" / "runtime_profile.json"

    system_info = collect_system_info(root, system_info_path, supplied_system_info)
    profile_name = detect_profile(root, system_info_path)
    profile_path = root / "env" / "profiles" / f"{profile_name}.env"

    common = parse_env_file(common_path)
    profile = parse_env_file(profile_path)
    local = parse_env_file(local_path, required=False)
    validation_profile = resolve_validation_profile(local)
    validation_path = root / "env" / "validation" / f"{validation_profile}.env"
    validation = parse_env_file(validation_path) if validation_profile else OrderedDict()

    validate_profile(profile_name, profile_path, profile, system_info)
    strict_local_conflicts = enabled(os.environ.get("CHROMIE_ENV_STRICT"))
    resolved, provenance, ignored_local_overrides = merge_runtime_environment(
        system_info=system_info,
        common=common,
        profile=profile,
        validation=validation,
        local=local,
        profile_name=profile_name,
        validation_profile=validation_profile,
        system_info_path=Path(".chromie/system_info.env"),
        strict_local_conflicts=strict_local_conflicts,
    )
    fingerprint = runtime_fingerprint(
        resolved,
        profile_name=profile_name,
        validation_profile=validation_profile,
    )
    resolved["CHROMIE_RUNTIME_ENV_FINGERPRINT"] = fingerprint
    provenance["CHROMIE_RUNTIME_ENV_FINGERPRINT"] = "generator"

    content = render_env(resolved, provenance)
    if compose_env_path.exists():
        first_lines = compose_env_path.read_text(encoding="utf-8", errors="replace").splitlines()[:3]
        generated_markers = (
            "Generated by scripts/generate_runtime_env.py",
            "Generated by scripts/build_runtime_env.sh",
        )
        if not any(marker in line for line in first_lines for marker in generated_markers):
            raise ConfigurationError(
                f"{compose_env_path} is user-managed. Remove or rename it so Chromie can maintain the Compose compatibility env file."
            )

    # All validation completes before any runtime/Compose file is replaced.
    atomic_write(runtime_path, content)
    atomic_write(compose_env_path, content)

    models = active_models(resolved)
    manifest = {
        "schema_version": 2,
        "active_profile": profile_name,
        "active_validation_profile": validation_profile or "none",
        "fingerprint": fingerprint,
        "profile_file": str(profile_path.relative_to(root)),
        "system_info_file": ".chromie/system_info.env",
        "hardware": {key: system_info.get(key, "") for key in system_info},
        "models": {key: resolved[key] for key in MODEL_PLAN_KEYS},
        "cognitive_budgets": {
            key: resolved.get(key, "") for key in COGNITIVE_BUDGET_KEYS
        },
        "active_ollama_models": models,
        "ignored_local_overrides": ignored_local_overrides,
        "strict_local_conflicts": strict_local_conflicts,
    }
    atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--system-info-file",
        type=Path,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    try:
        manifest = generate(args.root, supplied_system_info=args.system_info_file)
    except ConfigurationError as exc:
        print(f"[env][error] {exc}", file=sys.stderr)
        return 1

    ignored = manifest.get("ignored_local_overrides", [])
    assert isinstance(ignored, list)
    if ignored:
        print(
            "[env][warning] Ignoring .env.local values for profile/validation-owned "
            f"settings: {', '.join(str(key) for key in ignored)}",
            file=sys.stderr,
        )
        print(
            f"[env][warning] Detected profile {manifest['active_profile']} remains authoritative. "
            "Set CHROMIE_ENV_STRICT=1 to reject these conflicts instead.",
            file=sys.stderr,
        )

    models = manifest["models"]
    assert isinstance(models, dict)
    print(f"[env] Auto-detected hardware profile: {manifest['active_profile']}")
    print(
        "[env] Model plan: "
        f"router={models['ROUTER_MODEL']} "
        f"association={models['AGENT_GOAL_ASSOCIATION_MODEL']} "
        f"fast={models['AGENT_FAST_PLANNER_MODEL']} "
        f"deep={models['AGENT_DEEP_PLANNER_MODEL']} "
        f"composer={models['AGENT_RESPONSE_COMPOSER_MODEL']}"
    )
    budgets = manifest["cognitive_budgets"]
    assert isinstance(budgets, dict)
    print(
        "[env] Cognitive budgets: "
        f"profile={budgets.get('CHROMIE_COGNITIVE_BUDGET_PROFILE') or 'default'} "
        f"fast={budgets.get('AGENT_FAST_PLANNER_TIMEOUT_MS')}ms "
        f"deep={budgets.get('AGENT_DEEP_PLANNER_TIMEOUT_MS')}ms "
        f"host_deep={budgets.get('ORCH_DEEP_PLANNER_TIMEOUT_MS')}ms "
        f"total={budgets.get('ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS')}ms"
    )
    print("[env] Wrote .env.runtime, .env, and .chromie/runtime_profile.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
