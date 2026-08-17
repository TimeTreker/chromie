#!/usr/bin/env python3
"""Capture source-, model-, manifest-, and image-bound runtime identity.

The resulting JSON is an evidence input, not a release claim. It is intentionally
strict: a dirty Chromie checkout or missing required service image fails unless
an operator explicitly requests an incomplete diagnostic capture.
"""

from __future__ import annotations

import argparse
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

from orchestrator.runtime.evidence_identity import canonical_json_sha256  # noqa: E402
from scripts.generate_runtime_env import COGNITIVE_BUDGET_KEYS  # noqa: E402

DEFAULT_OUTPUT = ROOT / ".chromie" / "evidence" / "runtime-identity.json"
DEFAULT_SERVICES = ("chromie-agent", "chromie-llm", "chromie-asr", "chromie-tts")
RUNTIME_KEYS = (
    "CHROMIE_RUNTIME_ENV_FINGERPRINT",
    "CHROMIE_ACTIVE_PROFILE",
    "CHROMIE_ACTIVE_VALIDATION_PROFILE",
    "ORCH_COGNITIVE_RUNTIME_MODE",
    "ORCH_COGNITIVE_APPLY_LANES",
)

MODEL_KEYS = (
    "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
    "AGENT_GOAL_INTERPRETER_MODEL",
    "AGENT_GOAL_ASSOCIATION_MODEL",
    "AGENT_FAST_PLANNER_MODEL",
    "AGENT_DEEP_PLANNER_MODEL",
    "AGENT_RESPONSE_COMPOSER_MODEL",
    "AGENT_TOOL_RESULT_INTERPRETER_MODEL",
    "AGENT_SOCIAL_ATTENTION_MODEL",
    "AGENT_RESPONSE_REVIEW_MODEL",
    "AGENT_MODEL",
    "OLLAMA_MODEL",
)


class CaptureError(RuntimeError):
    pass


def _run(command: Iterable[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise CaptureError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip()


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"failed to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CaptureError(f"{path}: expected a JSON object")
    return payload


def _read_env(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            raise CaptureError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _git_identity(root: Path) -> dict[str, Any]:
    revision = _run(["git", "rev-parse", "HEAD"], cwd=root)
    branch = _run(["git", "branch", "--show-current"], cwd=root)
    status = _run(["git", "status", "--porcelain"], cwd=root)
    version_path = root / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None
    return {
        "revision": revision,
        "branch": branch,
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
        "version": version,
    }


def _compose_args(root: Path, overrides: list[Path]) -> list[str]:
    args = [
        "docker",
        "compose",
        "--env-file",
        str(root / ".env.runtime"),
        "-f",
        str(root / "docker-compose.yml"),
    ]
    for override in overrides:
        args.extend(["-f", str(override)])
    return args


def _container_environment(container_id: str) -> dict[str, str]:
    raw = _run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
            container_id,
        ]
    )
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _deployment_identity(
    *,
    root: Path,
    services: list[str],
    overrides: list[Path],
    allow_missing_images: bool,
) -> dict[str, Any]:
    compose = _compose_args(root, overrides)
    service_images: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for service in services:
        try:
            container_id = _run([*compose, "ps", "-q", service], cwd=root)
            if not container_id:
                raise CaptureError(f"service {service} has no running container")
            image_id = _run(
                ["docker", "inspect", "--format", "{{.Image}}", container_id],
                cwd=root,
            )
            config_image = _run(
                ["docker", "inspect", "--format", "{{.Config.Image}}", container_id],
                cwd=root,
            )
            env = _container_environment(container_id)
            service_images[service] = {
                "container_id": container_id,
                "image_id": image_id,
                "configured_image": config_image,
                "effective_models": {
                    key: env[key]
                    for key in MODEL_KEYS
                    if str(env.get(key) or "").strip()
                },
                "effective_runtime": {
                    key: env[key]
                    for key in RUNTIME_KEYS
                    if str(env.get(key) or "").strip()
                },
            }
        except CaptureError as exc:
            errors.append(str(exc))
    if errors and not allow_missing_images:
        raise CaptureError("; ".join(errors))
    return {
        "compose_files": [str(root / "docker-compose.yml"), *map(str, overrides)],
        "service_images": service_images,
        "capture_errors": errors,
        "complete": not errors and set(service_images) == set(services),
    }


def _manifest_identity(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "source": payload.get("source"),
        "schema_version": payload.get("schema_version"),
        "upstream_revision": metadata.get("upstream_commit"),
    }


def _validated_orchestrator_cognitive_budgets(
    runtime_profile: dict[str, Any],
    orchestrator_env: dict[str, str],
) -> dict[str, str]:
    profile_budgets = runtime_profile.get("cognitive_budgets")
    if not isinstance(profile_budgets, dict):
        raise CaptureError("runtime profile has no cognitive_budgets object")
    missing_profile = [key for key in COGNITIVE_BUDGET_KEYS if key not in profile_budgets]
    if missing_profile:
        raise CaptureError(
            "runtime profile is missing cognitive budget keys: "
            + ", ".join(missing_profile)
        )
    missing_effective = [
        key for key in COGNITIVE_BUDGET_KEYS if key not in orchestrator_env
    ]
    if missing_effective:
        raise CaptureError(
            "generated Orchestrator environment is missing profile-owned cognitive "
            "budgets: " + ", ".join(missing_effective)
        )
    mismatches = [
        key
        for key in COGNITIVE_BUDGET_KEYS
        if str(orchestrator_env[key]) != str(profile_budgets[key])
    ]
    if mismatches:
        raise CaptureError(
            "generated Orchestrator environment cognitive budgets differ from the "
            "runtime profile: " + ", ".join(mismatches)
        )
    return {key: str(orchestrator_env[key]) for key in COGNITIVE_BUDGET_KEYS}


def capture_identity(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    runtime_profile_path = Path(args.runtime_profile).expanduser().resolve()
    runtime_profile = _read_json(runtime_profile_path)
    chromie = _git_identity(root)
    if chromie["dirty"] and not args.allow_dirty:
        raise CaptureError(
            "Chromie worktree is dirty; commit the evaluated source or pass "
            "--allow-dirty for diagnostic-only identity"
        )

    overrides = [Path(item).expanduser().resolve() for item in args.compose_override]
    env_override_value = os.getenv("CHROMIE_COMPOSE_OVERRIDE_FILES", "")
    for item in env_override_value.split(","):
        value = item.strip()
        if value:
            path = Path(value).expanduser().resolve()
            if path not in overrides:
                overrides.append(path)
    for path in overrides:
        if not path.exists():
            raise CaptureError(f"Compose override does not exist: {path}")

    orchestrator_env_path = (
        Path(args.orchestrator_env).expanduser().resolve()
        if args.orchestrator_env
        else None
    )
    orchestrator_env = _read_env(orchestrator_env_path)
    effective_cognitive_budgets = _validated_orchestrator_cognitive_budgets(
        runtime_profile,
        orchestrator_env,
    )
    deployment = _deployment_identity(
        root=root,
        services=list(args.service or DEFAULT_SERVICES),
        overrides=overrides,
        allow_missing_images=args.allow_missing_images,
    )
    manifests = [
        _manifest_identity(Path(item).expanduser().resolve())
        for item in (
            args.capability_manifest
            or [str(root / "capabilities" / "soridormi.json")]
        )
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "evidence_claim": "runtime_identity_only",
        "chromie": chromie,
        "runtime_profile": {
            "path": str(runtime_profile_path),
            "sha256": _sha256_file(runtime_profile_path),
            "fingerprint": runtime_profile.get("fingerprint"),
            "active_profile": runtime_profile.get("active_profile"),
            "active_validation_profile": runtime_profile.get(
                "active_validation_profile"
            ),
            "models": runtime_profile.get("models"),
            "cognitive_budgets": runtime_profile.get("cognitive_budgets"),
            "active_ollama_models": runtime_profile.get("active_ollama_models"),
        },
        "orchestrator_runtime": {
            "env_path": str(orchestrator_env_path) if orchestrator_env_path else None,
            "env_sha256": (
                _sha256_file(orchestrator_env_path)
                if orchestrator_env_path and orchestrator_env_path.exists()
                else None
            ),
            "effective_models": {
                key: orchestrator_env[key]
                for key in MODEL_KEYS
                if str(orchestrator_env.get(key) or "").strip()
            },
            "effective_cognitive_budgets": effective_cognitive_budgets,
            "cognitive_runtime_mode": orchestrator_env.get(
                "ORCH_COGNITIVE_RUNTIME_MODE"
            ),
            "cognitive_apply_lanes": orchestrator_env.get(
                "ORCH_COGNITIVE_APPLY_LANES"
            ),
        },
        "capability_manifests": manifests,
        "deployment": deployment,
        "qualification": {
            "source_clean": chromie["dirty"] is False,
            "deployment_complete": deployment["complete"],
            "release_qualified": False,
            "human_review_required": True,
        },
    }
    payload["identity_sha256"] = canonical_json_sha256(payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--runtime-profile",
        type=Path,
        default=ROOT / ".chromie" / "runtime_profile.json",
    )
    parser.add_argument(
        "--orchestrator-env",
        default=str(ROOT / ".chromie" / "voice-runtime" / "orchestrator.env"),
    )
    parser.add_argument(
        "--capability-manifest",
        action="append",
        default=None,
    )
    parser.add_argument("--compose-override", action="append", default=[])
    parser.add_argument("--service", action="append", default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--allow-missing-images",
        action="store_true",
        help="Create diagnostic-only identity when required services are not running.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = capture_identity(args)
    except Exception as exc:
        print(f"[runtime-identity][error] {exc}", file=sys.stderr)
        return 1
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
