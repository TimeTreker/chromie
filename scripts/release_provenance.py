#!/usr/bin/env python3
"""Collect deterministic source inputs and resolved runtime release provenance."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 host tooling fallback.
    tomllib = None
import urllib.request
from pathlib import Path
from typing import Any

try:
    from evidence_io import sha256_file as sha256
    from generate_runtime_env import MODEL_PLAN_KEYS
except ImportError:  # imported as scripts.release_provenance
    from scripts.evidence_io import sha256_file as sha256
    from scripts.generate_runtime_env import MODEL_PLAN_KEYS

REQUIREMENT_FILES = (
    "agent/requirements.txt",
    "asr/requirements.txt",
    "hardware/requirements.txt",
    "orchestrator/requirements.txt",
    "requirements-test.txt",
    "tts/requirements.txt",
)
PROJECT_IMAGE_NAMES = (
    "chromie-asr",
    "chromie-tts",
    "chromie-agent",
)
# Built from llm/sglang/Dockerfile by the SGLang hardware-profile overlays.
SGLANG_IMAGE_NAME = "chromie-sglang"
# Base images of repository-built images: (Dockerfile, its ARG, the env key
# docker-compose.yml passes to that ARG).
BASE_IMAGE_ARGS = (
    ("asr/Dockerfile", "ASR_CUDA_IMAGE", "ASR_CUDA_IMAGE"),
    ("tts_candidates/cosyvoice/Dockerfile", "CUDA_IMAGE", "TTS_CANDIDATE_CUDA_IMAGE"),
)
# Every Ollama model key a hardware profile may assign. The lock must name each
# model these keys select on any Ollama profile.
OLLAMA_ROLE_MODEL_KEYS = (
    *MODEL_PLAN_KEYS,
    "AGENT_SKILL_SELECTION_MODEL",
    "TTS_COSYVOICE_OLLAMA_MODEL",
)
MUTABLE_TAGS = {"latest", "main", "master", "stable", "edge"}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def source_environment(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (".env.common", ".env.runtime", ".env.local"):
        values.update(parse_env(root / name))
    return values


def load_pyproject_toml(text: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(text)

    payload: dict[str, Any] = {}
    section: str | None = None
    active_array_key: str | None = None
    active_array_values: list[str] = []

    def finish_array() -> None:
        nonlocal active_array_key, active_array_values
        if section and active_array_key:
            payload.setdefault(section, {})[active_array_key] = list(active_array_values)
        active_array_key = None
        active_array_values = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            finish_array()
            section = line[1:-1].strip()
            payload.setdefault(section, {})
            continue
        if section is None:
            continue
        if active_array_key is not None:
            if line == "]":
                finish_array()
                continue
            value = line.rstrip(",").strip().strip('"').strip("'")
            if value:
                active_array_values.append(value)
            continue
        if "=" not in line:
            continue

        key, value = (part.strip() for part in line.split("=", 1))
        if value == "[":
            active_array_key = key
            active_array_values = []
        elif value.startswith("[") and value.endswith("]"):
            items = []
            for item in value[1:-1].split(","):
                item = item.strip().strip('"').strip("'")
                if item:
                    items.append(item)
            payload.setdefault(section, {})[key] = items
        else:
            payload.setdefault(section, {})[key] = value.strip('"').strip("'")
    finish_array()
    return payload


def exact_requirement_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIREMENT_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing requirement lock: {relative}")
            continue
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(("--", "-r ")):
                continue
            if "==" not in line or any(token in line for token in (".*", ">=", "<=", "~=", "!=")):
                errors.append(f"{relative}:{number} is not an exact == pin: {line}")
    pyproject = root / "shared" / "pyproject.toml"
    if not pyproject.is_file():
        errors.append("missing dependency lock: shared/pyproject.toml")
    else:
        payload = load_pyproject_toml(pyproject.read_text(encoding="utf-8"))
        locked = list(payload.get("project", {}).get("dependencies", []))
        locked.extend(payload.get("build-system", {}).get("requires", []))
        for value in locked:
            if "==" not in value or any(op in value for op in (">=", "<=", "~=", "!=", ".*")):
                errors.append(
                    "shared/pyproject.toml has a non-exact build/runtime pin: "
                    + value
                )
    return errors


def required_env(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"required environment variable is missing: {name}")
    return value


def _inference_provider(env: dict[str, str]) -> str:
    return str(env.get("AGENT_LLM_PROVIDER") or "ollama").strip().casefold()


def project_image_names(env: dict[str, str]) -> tuple[str, ...]:
    if _inference_provider(env) == "sglang":
        return (*PROJECT_IMAGE_NAMES, SGLANG_IMAGE_NAME)
    return PROJECT_IMAGE_NAMES


def declared_images(root: Path, env: dict[str, str]) -> list[str]:
    tag = required_env(env, "CHROMIE_IMAGE_TAG")
    images = [f"{name}:{tag}" for name in project_image_names(env)]
    if _inference_provider(env) != "sglang":
        images.append(required_env(env, "OLLAMA_IMAGE"))
    images.append(env.get("PYTHON_IMAGE", "python:3.12.10-slim-bookworm"))
    for dockerfile, arg, key in BASE_IMAGE_ARGS:
        text = (root / dockerfile).read_text(encoding="utf-8") if (root / dockerfile).is_file() else ""
        match = re.search(rf"^ARG {arg}=([^\s]+)", text, re.MULTILINE)
        default = match.group(1) if match else ""
        images.append(env.get(key) or default)
    return [item for item in images if item]


def effective_ollama_models(env: dict[str, str]) -> list[str]:
    """Return the Ollama models the launchers actually run for ``env``.

    Mirrors scripts/compact_cognition.sh: with the CosyVoice3 backend and
    TTS_COSYVOICE_COMPACT_COGNITION=1 every cognitive role runs
    TTS_COSYVOICE_OLLAMA_MODEL; Agent Skill selection keeps its own model.
    """

    backend = str(env.get("CHROMIE_TTS_BACKEND") or "cosyvoice3").strip().casefold()
    compact = backend in {"cosyvoice", "cosyvoice3"} and (
        str(env.get("TTS_COSYVOICE_COMPACT_COGNITION") or "1").strip() == "1"
    )
    if compact:
        candidates = [env.get("TTS_COSYVOICE_OLLAMA_MODEL") or "qwen3:4b"]
    else:
        candidates = [env.get(key) for key in MODEL_PLAN_KEYS]
    if str(env.get("AGENT_SKILL_SELECTION_ENABLED") or "1").strip().casefold() in {"1", "true", "yes", "on"}:
        candidates.append(env.get("AGENT_SKILL_SELECTION_MODEL"))
    models: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in models:
            models.append(value)
    return models


def mutable_image_errors(images: list[str]) -> list[str]:
    errors: list[str] = []
    for image in images:
        if "@sha256:" in image:
            continue
        tail = image.rsplit("/", 1)[-1]
        if ":" not in tail:
            errors.append(f"container image lacks an explicit tag or digest: {image}")
            continue
        tag = tail.rsplit(":", 1)[-1]
        if tag in MUTABLE_TAGS:
            errors.append(f"container image uses mutable tag {tag!r}: {image}")
    return errors


def inspect_image(image: str) -> dict[str, Any]:
    raw = subprocess.check_output(
        ["docker", "image", "inspect", image],
        text=True,
        stderr=subprocess.STDOUT,
    )
    item = json.loads(raw)[0]
    return {
        "reference": image,
        "id": item.get("Id"),
        "repo_digests": sorted(item.get("RepoDigests") or []),
        "created": item.get("Created"),
    }


def pip_freeze(image: str, python: str = "python") -> list[str]:
    output = subprocess.check_output(
        ["docker", "run", "--rm", "--entrypoint", python, image, "-m", "pip", "freeze", "--all"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def ollama_models(url: str, expected: list[str]) -> list[dict[str, Any]]:
    with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=10) as response:
        payload = json.load(response)
    by_name: dict[str, dict[str, Any]] = {}
    for model in payload.get("models", []):
        for key in {model.get("name"), model.get("model")}:
            if key:
                by_name[str(key)] = model
    result = []
    for name in expected:
        model = by_name.get(name)
        if model is None:
            raise RuntimeError(f"configured Ollama model is not installed: {name}")
        digest = model.get("digest")
        if not digest:
            raise RuntimeError(f"Ollama did not report a digest for model: {name}")
        result.append(
            {
                "name": name,
                "digest": digest,
                "size": model.get("size"),
                "modified_at": model.get("modified_at"),
            }
        )
    return result


def model_lock_errors(root: Path, env: dict[str, str] | None = None) -> list[str]:
    errors: list[str] = []
    path = root / "release" / "model-lock.json"
    if not path.is_file():
        return ["missing immutable model lock: release/model-lock.json"]
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid release/model-lock.json: {exc}"]

    asr_lock = lock.get("asr", {})
    agent_models: set[str] = set()
    role_models: set[str] = set()
    common_values = parse_env(root / ".env.common")
    for profile in sorted((root / "env" / "profiles").glob("*.env")):
        values = parse_env(profile)
        model = values.get("ASR_MODEL")
        revision = values.get("ASR_MODEL_REVISION")
        if model:
            expected = asr_lock.get(model, {}).get("revision")
            if not revision or revision != expected:
                errors.append(
                    f"{profile.relative_to(root)} ASR model/revision does not match release/model-lock.json"
                )
        if values.get("AGENT_MODEL"):
            provider = values.get("AGENT_LLM_PROVIDER", "ollama").strip().casefold()
            if provider == "ollama":
                agent_models.add(values["AGENT_MODEL"])
                merged = {**common_values, **values}
                role_models.update(
                    merged[key] for key in OLLAMA_ROLE_MODEL_KEYS if merged.get(key)
                )
            elif provider == "sglang":
                served = lock.get("sglang", {}).get("candidate_served_models", {})
                configured = {
                    value for key, value in values.items()
                    if key.startswith("AGENT_") and key.endswith("_MODEL") and value
                }
                missing = sorted(configured - set(served))
                if missing:
                    errors.append(
                        f"{profile.relative_to(root)} SGLang models absent from "
                        f"release/model-lock.json: {missing}"
                    )

    common = env or source_environment(root)
    tts = lock.get("tts", {})
    default_tts = tts.get("default", {})
    alternatives = tts.get("alternatives", {})
    oute = alternatives.get("oute", {})
    qwen = alternatives.get("qwen3_tts", {})
    pairs = (
        ("TTS_PROVIDER", default_tts.get("provider_id")),
        ("COSYVOICE3_SOURCE_REVISION", default_tts.get("runtime", {}).get("revision")),
        ("COSYVOICE3_MODEL_ID", default_tts.get("model", {}).get("repository")),
        ("COSYVOICE3_MODEL_REVISION", default_tts.get("model", {}).get("revision")),
        ("TTS_TOKENIZER_REPO", oute.get("tokenizer", {}).get("repository")),
        ("TTS_TOKENIZER_REVISION", oute.get("tokenizer", {}).get("revision")),
        ("TTS_GGUF_REPO", oute.get("gguf", {}).get("repository")),
        ("TTS_GGUF_REVISION", oute.get("gguf", {}).get("revision")),
        ("QWEN3_TTS_SOURCE_REVISION", qwen.get("runtime", {}).get("revision")),
        ("QWEN3_TTS_MODEL_ID", qwen.get("model", {}).get("repository")),
        ("QWEN3_TTS_MODEL_REVISION", qwen.get("model", {}).get("revision")),
    )
    for name, expected in pairs:
        if not expected or common.get(name) != expected:
            errors.append(f"{name} does not match release/model-lock.json")

    ollama = lock.get("ollama", {})
    locked_agents = set(ollama.get("agent_models", []))
    if agent_models != locked_agents:
        errors.append(
            "release/model-lock.json agent_models do not match maintained hardware profiles"
        )
    locked_roles = set(ollama.get("role_models", []))
    if role_models != locked_roles:
        errors.append(
            "release/model-lock.json role_models do not match the Ollama role models "
            f"of the maintained hardware profiles: {sorted(role_models)}"
        )
    inference_provider = _inference_provider(common)
    if inference_provider == "ollama":
        user_meaning_interpreter_model = common.get("AGENT_USER_MEANING_INTERPRETER_MODEL")
        if user_meaning_interpreter_model and user_meaning_interpreter_model not in set(
            ollama.get("user_meaning_interpreter_models", [])
        ):
            errors.append("AGENT_USER_MEANING_INTERPRETER_MODEL is absent from release/model-lock.json")
        unlocked = sorted(set(effective_ollama_models(common)) - locked_roles)
        if unlocked:
            errors.append(
                "running Ollama model(s) are absent from release/model-lock.json role_models: "
                + ", ".join(unlocked)
            )
    elif inference_provider == "sglang":
        served = lock.get("sglang", {}).get("candidate_served_models", {})
        if not isinstance(served, dict) or not served:
            errors.append("release/model-lock.json has no SGLang candidate served models")
        else:
            sglang_model_keys = (
                "AGENT_MODEL",
                "AGENT_USER_MEANING_INTERPRETER_MODEL",
                "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
                "AGENT_GOAL_ASSOCIATION_MODEL",
                "AGENT_PLANNER_MODEL",
                "AGENT_DELIBERATIVE_MODEL",
                "AGENT_SKILL_SELECTION_MODEL",
            )
            configured_sglang_models = {
                str(common.get(key) or "").strip()
                for key in sglang_model_keys
                if str(common.get(key) or "").strip()
            }
            missing = sorted(configured_sglang_models - set(served))
            if missing:
                errors.append(
                    "configured SGLang model(s) are absent from release/model-lock.json: "
                    + ", ".join(missing)
                )
    else:
        errors.append(f"unsupported AGENT_LLM_PROVIDER in model lock check: {inference_provider}")
    return errors

def collect_provenance(
    root: Path, *, require_runtime: bool, attempt_runtime: bool = True
) -> dict[str, Any]:
    root = root.resolve()
    env = source_environment(root)
    image_config_errors: list[str] = []
    try:
        images = declared_images(root, env)
    except ValueError as exc:
        images = []
        if require_runtime:
            image_config_errors.append(str(exc))
    # Local development may use mutable aliases, but publishable provenance
    # rejects them before resolved image IDs/digests are collected below.
    source_errors = (
        exact_requirement_errors(root)
        + image_config_errors
        + mutable_image_errors(images)
        + model_lock_errors(root, env)
    )
    model_lock = root / "release" / "model-lock.json"

    tracked_inputs = []
    for relative in (
        *REQUIREMENT_FILES,
        "shared/pyproject.toml",
        "docker-compose.yml",
        "agent/Dockerfile",
        "asr/Dockerfile",
        "tts/Dockerfile",
        "tts/candidate_server.py",
        "tts/candidate_provider.py",
        "tts/streaming_worker.py",
        "tts_candidates/cosyvoice/Dockerfile",
        "tts_candidates/cosyvoice/provider_impl.py",
        "tts_candidates/qwen3/Dockerfile",
        "tts_candidates/qwen3/provider_impl.py",
        "release/model-lock.json",
    ):
        path = root / relative
        if path.is_file():
            tracked_inputs.append({"path": relative, "sha256": sha256(path)})

    runtime_errors: list[str] = []
    inspected_images: list[dict[str, Any]] = []
    resolved_dependencies: dict[str, list[str]] = {}
    resolved_ollama: list[dict[str, Any]] = []
    if not attempt_runtime:
        runtime_errors.append("runtime provenance collection was skipped for this preview")
    else:
        docker_available = shutil.which("docker") is not None
        if docker_available:
            for image in images:
                try:
                    inspected_images.append(inspect_image(image))
                except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as exc:
                    runtime_errors.append(f"could not inspect image {image}: {exc}")
            try:
                tag = required_env(env, "CHROMIE_IMAGE_TAG")
            except ValueError as exc:
                runtime_errors.append(str(exc))
            else:
                for name in project_image_names(env):
                    image = f"{name}:{tag}"
                    try:
                        # Use the interpreter the SGLang Compose entrypoint runs.
                        python = "python3" if name == SGLANG_IMAGE_NAME else "python"
                        resolved_dependencies[image] = pip_freeze(image, python)
                    except subprocess.CalledProcessError as exc:
                        runtime_errors.append(f"could not capture pip freeze for {image}: {exc}")
        else:
            runtime_errors.append("docker executable is unavailable; image digests and resolved dependencies were not captured")

        if _inference_provider(env) == "ollama":
            try:
                resolved_ollama = ollama_models(
                    env.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                    effective_ollama_models(env),
                )
            except Exception as exc:  # release diagnostics should preserve all failures
                runtime_errors.append(f"could not capture Ollama model digests: {exc}")

    complete = not source_errors and not runtime_errors
    return {
        "schema_version": 1,
        "complete": complete,
        "runtime_required": require_runtime,
        "source_errors": source_errors,
        "runtime_errors": runtime_errors,
        "declared_images": images,
        "resolved_images": inspected_images,
        "resolved_python_dependencies": resolved_dependencies,
        "resolved_ollama_models": resolved_ollama,
        "model_lock": json.loads(model_lock.read_text(encoding="utf-8")) if model_lock.is_file() else None,
        "tracked_input_sha256": tracked_inputs,
    }
