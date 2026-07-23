#!/usr/bin/env python3
"""Collect deterministic source inputs and resolved runtime release provenance."""

from __future__ import annotations

import hashlib
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

REQUIREMENT_FILES = (
    "agent/requirements.txt",
    "asr/requirements.txt",
    "hardware/requirements.txt",
    "orchestrator/requirements.txt",
    "requirements-test.txt",
    "router/requirements.txt",
    "tts/requirements.txt",
)
PROJECT_IMAGE_NAMES = (
    "chromie-asr",
    "chromie-tts",
    "chromie-router",
    "chromie-agent",
)
MUTABLE_TAGS = {"latest", "main", "master", "stable", "edge"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def declared_images(root: Path, env: dict[str, str]) -> list[str]:
    tag = required_env(env, "CHROMIE_IMAGE_TAG")
    images = [f"{name}:{tag}" for name in PROJECT_IMAGE_NAMES]
    images.append(required_env(env, "OLLAMA_IMAGE"))
    images.append(env.get("PYTHON_IMAGE", "python:3.12.10-slim-bookworm"))
    for dockerfile, key in (
        ("asr/Dockerfile", "ASR_CUDA_IMAGE"),
        ("tts_candidates/cosyvoice/Dockerfile", "TTS_CANDIDATE_CUDA_IMAGE"),
    ):
        text = (root / dockerfile).read_text(encoding="utf-8") if (root / dockerfile).is_file() else ""
        match = re.search(rf"^ARG {key}=([^\s]+)", text, re.MULTILINE)
        default = match.group(1) if match else ""
        images.append(env.get(key, default))
    return [item for item in images if item]


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


def pip_freeze(image: str) -> list[str]:
    output = subprocess.check_output(
        ["docker", "run", "--rm", "--entrypoint", "python", image, "-m", "pip", "freeze", "--all"],
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
            agent_models.add(values["AGENT_MODEL"])

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
    router_model = common.get("ROUTER_MODEL")
    if router_model and router_model not in set(ollama.get("router_models", [])):
        errors.append("ROUTER_MODEL is absent from release/model-lock.json")
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
        "router/Dockerfile",
        "tts/Dockerfile",
        "tts/candidate_server.py",
        "tts/candidate_provider.py",
        "tts/streaming_worker.py",
        "tts_candidates/cosyvoice/Dockerfile",
        "tts_candidates/cosyvoice/provider_impl.py",
        "tts_candidates/qwen3/Dockerfile",
        "tts_candidates/qwen3/provider_impl.py",
        "tts_candidates/model-lock.json",
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
                for name in PROJECT_IMAGE_NAMES:
                    image = f"{name}:{tag}"
                    try:
                        resolved_dependencies[image] = pip_freeze(image)
                    except subprocess.CalledProcessError as exc:
                        runtime_errors.append(f"could not capture pip freeze for {image}: {exc}")
        else:
            runtime_errors.append("docker executable is unavailable; image digests and resolved dependencies were not captured")

        try:
            resolved_ollama = ollama_models(
                env.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                [env.get("AGENT_MODEL", "gemma4:e2b"), env.get("ROUTER_MODEL", "qwen3:4b")],
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
