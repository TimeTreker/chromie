#!/usr/bin/env python3
"""Prepare, execute, and adjudicate target-blind GA qualification batches.

Each candidate receives only the exact rendered production system/user prompt
and dynamic JSON Schema. Hidden corpus targets are introduced only during
deterministic adjudication. Codex remains the same-model offline surrogate;
Ollama mode exercises the declared model through Chromie's production client
and exact frozen generation options without claiming service or robot evidence.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import httpx
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.goal_association import GoalAssociationResolver  # noqa: E402
from agent.app.clients.ollama_client import (  # noqa: E402
    OllamaClient,
    OllamaGenerationError,
)
from shared.chromie_contracts.core_interpretation import (  # noqa: E402
    CognitiveWorkRequest,
)
from shared.chromie_contracts.goal import GoalAssociationResolution  # noqa: E402

from benchmarks.datasets.goal_association_daily_life.validate import (  # noqa: E402
    DATASET_ID,
    DATASET_ROOT,
    MANIFEST_PATH,
    load_cases,
    scenario_paths,
    scenario_tree_digest,
    validate_dataset,
)


PRODUCTION_TRANSACTION_FILES = (
    ROOT / "agent" / "app" / "goal_association.py",
    ROOT / "agent" / "app" / "goal_association_contract.py",
    ROOT / "agent" / "app" / "goal_association_prompt.py",
    ROOT / "agent" / "app" / "goal_association_schema.py",
    ROOT / "agent" / "app" / "goal_association_validation.py",
    ROOT / "agent" / "app" / "clients" / "ollama_client.py",
    ROOT / "shared" / "chromie_contracts" / "core_interpretation.py",
    ROOT / "shared" / "chromie_contracts" / "goal.py",
)
HARNESS_FILES = (
    Path(__file__).resolve(),
    DATASET_ROOT / "validate.py",
)
RECOVERY_METADATA_KEYS = (
    "optional_contract_recovery",
    "mechanical_contract_recovery",
    "optional_quantity_contract_recovery",
    "source_grounding_recovery",
    "generic_location_type_recovery",
    "missing_description_recovery",
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _write_ordered_json(path: Path, value: Any) -> None:
    """Freeze JSON without changing production-observable object key order."""

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _case_ref(case_id: str) -> str:
    return f"case_{_sha256(case_id)[:24]}"


def production_source_identity() -> dict[str, Any]:
    files = {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in PRODUCTION_TRANSACTION_FILES
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", "--", *files],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "git_revision": revision,
        "production_files": files,
        "production_files_sha256": _sha256(_json_bytes(files)),
        "production_tracked_diff_sha256": _sha256(diff),
    }


def harness_file_identity() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in HARNESS_FILES
    }


class CaptureModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": str(prompt), **kwargs})
        return self.payload


class ReplayModel:
    def __init__(self, raw_outputs: list[str]) -> None:
        self.raw_outputs = raw_outputs
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: Any, **kwargs: Any) -> dict[str, Any]:
        index = len(self.calls)
        self.calls.append({"prompt": str(prompt), **kwargs})
        if index >= len(self.raw_outputs):
            raise RuntimeError("candidate replay has no output for requested repair")
        value = json.loads(self.raw_outputs[index])
        if not isinstance(value, dict):
            raise ValueError("candidate Goal Association output is not an object")
        return value


async def build_transaction(
    case: dict[str, Any],
    *,
    num_ctx: int = 4096,
    num_predict: int = 512,
) -> dict[str, Any]:
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    capture = CaptureModel(case["target"]["reference_model_output"])
    resolution = await GoalAssociationResolver(
        capture,
        num_ctx=num_ctx,
        num_predict=num_predict,
    ).resolve(request)
    if resolution.resolution_status != "resolved" or len(capture.calls) != 1:
        raise ValueError(
            f"{case['id']}: production prompt capture failed: "
            f"status={resolution.resolution_status} calls={len(capture.calls)}"
        )
    call = capture.calls[0]
    response_schema = call.get("response_format")
    if not isinstance(response_schema, dict):
        raise ValueError(f"{case['id']}: missing dynamic response Schema")
    Draft202012Validator.check_schema(response_schema)
    system = str(call.get("system") or "")
    prompt = str(call["prompt"])
    return {
        "system_prompt": system,
        "user_prompt": prompt,
        "response_schema": response_schema,
        "options": call.get("options") or {},
        "production_prompt_family": call.get("prompt_family") or "",
        "prompt_identity": {
            "system_sha256": _sha256(system),
            "user_sha256": _sha256(prompt),
            "schema_sha256": _sha256(_json_bytes(response_schema)),
        },
    }


async def _ollama_model_identity(base_url: str, model: str) -> dict[str, Any]:
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(30.0),
        trust_env=False,
    ) as client:
        version_response = await client.get("/api/version")
        version_response.raise_for_status()
        tags_response = await client.get("/api/tags")
        tags_response.raise_for_status()
    version_payload = version_response.json()
    tags_payload = tags_response.json()
    for item in tags_payload.get("models") or []:
        if isinstance(item, dict) and item.get("name") == model:
            return {
                "provider": "ollama",
                "provider_version": version_payload.get("version"),
                "name": model,
                "digest": item.get("digest"),
                "size_bytes": item.get("size"),
                "modified_at": item.get("modified_at"),
                "details": item.get("details"),
            }
    raise ValueError(f"model {model!r} is not installed at {base_url}")


async def prepare_batch(
    output_dir: Path,
    *,
    label: str,
    model: str,
    reasoning_effort: str,
    provider: str = "codex",
    ollama_url: str = "http://127.0.0.1:11434",
    num_ctx: int = 4096,
    num_predict: int = 512,
    timeout_ms: int = 120000,
    only_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    if provider not in {"codex", "ollama"}:
        raise ValueError(f"unsupported qualification provider: {provider!r}")
    await asyncio.to_thread(validate_dataset)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    packets_dir = output_dir / "packets"
    schemas_dir = output_dir / "schemas"
    packets_dir.mkdir()
    schemas_dir.mkdir()
    envelope_schema = {
        "type": "object",
        "properties": {"model_output_text": {"type": "string"}},
        "required": ["model_output_text"],
        "additionalProperties": False,
    }
    if provider == "codex":
        (output_dir / "codex-envelope-schema.json").write_text(
            json.dumps(envelope_schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    all_cases = load_cases()
    requested_ids = set(only_case_ids or [])
    known_ids = {case["id"] for case in all_cases}
    unknown_ids = requested_ids - known_ids
    if unknown_ids:
        raise ValueError(f"unknown focused scenario IDs: {sorted(unknown_ids)}")
    cases = (
        [case for case in all_cases if case["id"] in requested_ids]
        if requested_ids
        else all_cases
    )
    scenario_path_by_id = {path.stem: path for path in scenario_paths()}
    index: list[dict[str, Any]] = []
    prompt_identities: dict[str, dict[str, str]] = {}
    for position, case in enumerate(cases, start=1):
        transaction = await build_transaction(
            case,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
        case_ref = _case_ref(case["id"])
        schema_sha = transaction["prompt_identity"]["schema_sha256"]
        schema_path = schemas_dir / f"{schema_sha}.json"
        if not schema_path.exists():
            # JSON object order is semantically irrelevant to a validator but
            # observable to a constrained decoder. Preserve the exact order
            # produced by the production Schema builder while the canonical
            # order-insensitive digest still binds its value.
            _write_ordered_json(schema_path, transaction["response_schema"])
        packet = {
            "schema_version": 1,
            "case_ref": case_ref,
            "system_prompt": transaction["system_prompt"],
            "user_prompt": transaction["user_prompt"],
            "response_schema_path": schema_path.relative_to(output_dir).as_posix(),
            "response_schema_sha256": schema_sha,
            "production_prompt_family": transaction["production_prompt_family"],
            "production_options": transaction["options"],
            "prompt_identity": transaction["prompt_identity"],
            "target_blind": True,
        }
        packet_path = packets_dir / f"{case_ref}.json"
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index.append(
            {
                "position": position,
                "case_ref": case_ref,
                "scenario_id": case["id"],
                "scenario_path": scenario_path_by_id[case["id"]]
                .relative_to(ROOT)
                .as_posix(),
                "packet_path": packet_path.relative_to(output_dir).as_posix(),
            }
        )
        prompt_identities[case_ref] = transaction["prompt_identity"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if provider == "codex":
        harness_runtime = {
            "codex_cli": subprocess.run(
                ["codex", "--version"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        }
        inference = {
            "provider": "codex",
            "authority": "Codex CLI same-model offline GA surrogate",
            "model": model,
            "reasoning_effort": reasoning_effort,
            "primary_calls_per_scenario": 1,
            "mechanical_repair_calls": (
                "zero or one, only when production resolver requests it"
            ),
            "retry_policy": "none",
            "same_model_non_independent": True,
            "independent_semantic_review": False,
            "transport_limit": (
                "Exact production prompt/Schema is projected through a strict Codex "
                "string envelope; Codex CLI is not deployed Ollama constrained decoding."
            ),
        }
    else:
        model_identity = await _ollama_model_identity(ollama_url, model)
        harness_runtime = {
            "ollama_url": ollama_url.rstrip("/"),
            "ollama_model_identity": model_identity,
        }
        inference = {
            "provider": "ollama",
            "authority": "Chromie production OllamaClient Goal Association transaction",
            "model": model,
            "model_digest": model_identity.get("digest"),
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
            "timeout_ms": timeout_ms,
            "primary_calls_per_scenario": 1,
            "mechanical_repair_calls": (
                "zero or one, only when production resolver requests it"
            ),
            "retry_policy": "none",
            "same_model_non_independent": False,
            "independent_semantic_review": False,
            "transport_limit": (
                "Exact production prompt, dynamic Schema, options, and non-thinking "
                "OllamaClient transport; this bypasses the deployed Agent HTTP service."
            ),
        }
    identity = {
        "schema_version": 1,
        "label": label,
        "issue": "https://github.com/TimeTreker/chromie/issues/34",
        "dataset_id": DATASET_ID,
        "scenario_count": len(cases),
        "corpus_scenario_count": len(all_cases),
        "scenario_selection": (
            sorted(requested_ids) if requested_ids else "complete_corpus"
        ),
        "scenario_tree_sha256": scenario_tree_digest(),
        "manifest_scenario_tree_sha256": manifest["asset_contract"]
        ["scenario_tree_sha256"],
        "source": production_source_identity(),
        "harness": {
            "files": harness_file_identity(),
            "python": sys.version,
            **harness_runtime,
        },
        "inference": inference,
        "codex_envelope_schema_sha256": (
            _sha256(_json_bytes(envelope_schema)) if provider == "codex" else None
        ),
        "prompt_identity_index_sha256": _sha256(_json_bytes(prompt_identities)),
        "candidate_packet_policy": (
            "system/user/schema only; scenario id, target, oracle, category, split, "
            "rubric, and expected result excluded"
        ),
    }
    (output_dir / "packet-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "batch-identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return identity


def _candidate_prompt(
    *,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
) -> str:
    return (
        "Execute this one Goal Association semantic transaction. Do not inspect "
        "files, run tools, discuss the benchmark, or add commentary. Treat the "
        "following SYSTEM PROMPT as the complete role instruction and USER PROMPT "
        "as the authoritative transaction.\n\nSYSTEM PROMPT\n"
        f"{system_prompt}\n\nUSER PROMPT\n{user_prompt}\n\n"
        "DYNAMIC PRODUCTION RESPONSE SCHEMA\n"
        f"{json.dumps(response_schema, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n\n"
        "Return one Codex transport envelope with exactly one field named "
        "model_output_text. The string must contain only the raw JSON object required "
        "by the dynamic production response Schema. The envelope is transport only "
        "and is removed before production validation."
    )


async def _codex_call(
    *,
    output_dir: Path,
    case_ref: str,
    phase: str,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
    model: str,
    reasoning_effort: str,
    timeout_s: float,
) -> dict[str, Any]:
    phase_root = output_dir / phase
    raw_dir = phase_root / "raw-outputs"
    envelope_dir = phase_root / "codex-envelopes"
    logs_dir = phase_root / "call-logs"
    executions_dir = phase_root / "call-executions"
    for directory in (raw_dir, envelope_dir, logs_dir, executions_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{case_ref}.txt"
    envelope_path = envelope_dir / f"{case_ref}.json"
    log_path = logs_dir / f"{case_ref}.log"
    execution_path = executions_dir / f"{case_ref}.json"
    if raw_path.exists() or envelope_path.exists() or execution_path.exists():
        raise FileExistsError(f"immutable {phase} output exists for {case_ref}")
    workdir = output_dir / "codex-empty-workdir"
    workdir.mkdir(exist_ok=True)
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        str(workdir),
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-o",
        str(envelope_path),
        "--output-schema",
        str(output_dir / "codex-envelope-schema.json"),
        "-",
    ]
    started = time.time()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(
                _candidate_prompt(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                ).encode("utf-8")
            ),
            timeout=timeout_s,
        )
        timed_out = False
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        timed_out = True
    ended = time.time()
    log_path.write_bytes(b"STDOUT\n" + stdout + b"\nSTDERR\n" + stderr)
    envelope_error = ""
    if envelope_path.exists():
        try:
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            raw_output = envelope["model_output_text"]
            if not isinstance(raw_output, str):
                raise TypeError("model_output_text is not a string")
            raw_path.write_text(raw_output, encoding="utf-8")
        except Exception as exc:
            envelope_error = f"{type(exc).__name__}: {exc}"
    execution = {
        "schema_version": 1,
        "case_ref": case_ref,
        "phase": phase,
        "started_epoch_s": started,
        "ended_epoch_s": ended,
        "latency_s": ended - started,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "output_present": raw_path.exists(),
        "output_sha256": _sha256(raw_path.read_bytes()) if raw_path.exists() else "",
        "codex_envelope_present": envelope_path.exists(),
        "codex_envelope_sha256": (
            _sha256(envelope_path.read_bytes()) if envelope_path.exists() else ""
        ),
        "codex_envelope_error": envelope_error,
        "log_sha256": _sha256(log_path.read_bytes()),
    }
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return execution


async def _ollama_call(
    *,
    output_dir: Path,
    case_ref: str,
    phase: str,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
    production_options: dict[str, Any],
    client: OllamaClient,
    timeout_s: float,
) -> dict[str, Any]:
    phase_root = output_dir / phase
    raw_dir = phase_root / "raw-outputs"
    logs_dir = phase_root / "call-logs"
    executions_dir = phase_root / "call-executions"
    for directory in (raw_dir, logs_dir, executions_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{case_ref}.txt"
    log_path = logs_dir / f"{case_ref}.log"
    execution_path = executions_dir / f"{case_ref}.json"
    if raw_path.exists() or execution_path.exists():
        raise FileExistsError(f"immutable {phase} output exists for {case_ref}")
    started = time.time()
    timed_out = False
    error: dict[str, Any] | None = None
    try:
        value = await asyncio.wait_for(
            client.generate(
                user_prompt,
                system=system_prompt,
                options=production_options,
                response_format=response_schema,
                prompt_family=(
                    "goal_association.primary"
                    if phase == "primary"
                    else "goal_association.contract_repair"
                ),
                turn_id=case_ref,
                attempt=1 if phase == "primary" else 2,
            ),
            timeout=timeout_s,
        )
        if not isinstance(value, dict):
            raise TypeError("Ollama Goal Association output is not an object")
        raw_path.write_text(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            encoding="utf-8",
        )
    except TimeoutError as exc:
        timed_out = True
        error = {"error_type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        error = {
            "error_type": type(exc).__name__,
            "message": str(exc),
            **(
                exc.metadata()
                if isinstance(exc, OllamaGenerationError)
                else {}
            ),
        }
    ended = time.time()
    log_path.write_text(
        json.dumps(
            {
                "provider": "ollama",
                "model": client.model,
                "production_options": production_options,
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    execution = {
        "schema_version": 1,
        "case_ref": case_ref,
        "phase": phase,
        "provider": "ollama",
        "model": client.model,
        "started_epoch_s": started,
        "ended_epoch_s": ended,
        "latency_s": ended - started,
        "exit_code": 0 if error is None else 1,
        "timed_out": timed_out,
        "output_present": raw_path.exists(),
        "output_sha256": _sha256(raw_path.read_bytes()) if raw_path.exists() else "",
        "error": error,
        "log_sha256": _sha256(log_path.read_bytes()),
    }
    execution_path.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return execution


async def _capture_repair_call(
    request: CognitiveWorkRequest,
    primary_raw: str,
) -> dict[str, Any] | None:
    try:
        json.loads(primary_raw)
    except Exception:
        return None
    replay = ReplayModel([primary_raw, primary_raw])
    previous_level = logging.getLogger("chromie.agent.goal_association").level
    logging.getLogger("chromie.agent.goal_association").setLevel(logging.CRITICAL)
    try:
        await GoalAssociationResolver(replay).resolve(request)
    finally:
        logging.getLogger("chromie.agent.goal_association").setLevel(previous_level)
    if len(replay.calls) != 2:
        return None
    repair = replay.calls[1]
    if repair.get("prompt_family") != "goal_association.contract_repair":
        raise ValueError("second GA call was not the permitted mechanical repair")
    schema = repair.get("response_format")
    if not isinstance(schema, dict):
        raise ValueError("mechanical repair call omitted its response Schema")
    return {
        "system_prompt": str(repair.get("system") or ""),
        "user_prompt": str(repair["prompt"]),
        "response_schema": schema,
    }


async def _run_one(
    *,
    output_dir: Path,
    item: dict[str, Any],
    semaphore: asyncio.Semaphore,
    timeout_s: float,
    model: str,
    reasoning_effort: str,
    provider: str,
    ollama_client: OllamaClient | None,
) -> dict[str, Any]:
    async with semaphore:
        case_ref = item["case_ref"]
        packet = json.loads(
            (output_dir / item["packet_path"]).read_text(encoding="utf-8")
        )
        schema = json.loads(
            (output_dir / packet["response_schema_path"]).read_text(encoding="utf-8")
        )
        if provider == "ollama":
            if ollama_client is None:
                raise ValueError("Ollama provider has no production client")
            primary = await _ollama_call(
                output_dir=output_dir,
                case_ref=case_ref,
                phase="primary",
                system_prompt=packet["system_prompt"],
                user_prompt=packet["user_prompt"],
                response_schema=schema,
                production_options=packet["production_options"],
                client=ollama_client,
                timeout_s=timeout_s,
            )
        else:
            primary = await _codex_call(
                output_dir=output_dir,
                case_ref=case_ref,
                phase="primary",
                system_prompt=packet["system_prompt"],
                user_prompt=packet["user_prompt"],
                response_schema=schema,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout_s=timeout_s,
            )
        repair: dict[str, Any] | None = None
        primary_path = output_dir / "primary" / "raw-outputs" / f"{case_ref}.txt"
        if primary_path.exists():
            request = CognitiveWorkRequest.model_validate(
                json.loads(
                    (ROOT / item["scenario_path"]).read_text(encoding="utf-8")
                )["input"]["request"]
            )
            repair_call = await _capture_repair_call(
                request,
                primary_path.read_text(encoding="utf-8"),
            )
            if repair_call is not None:
                if provider == "ollama":
                    if ollama_client is None:
                        raise ValueError("Ollama provider has no production client")
                    repair = await _ollama_call(
                        output_dir=output_dir,
                        case_ref=case_ref,
                        phase="repair",
                        system_prompt=repair_call["system_prompt"],
                        user_prompt=repair_call["user_prompt"],
                        response_schema=repair_call["response_schema"],
                        production_options=packet["production_options"],
                        client=ollama_client,
                        timeout_s=timeout_s,
                    )
                else:
                    repair = await _codex_call(
                        output_dir=output_dir,
                        case_ref=case_ref,
                        phase="repair",
                        system_prompt=repair_call["system_prompt"],
                        user_prompt=repair_call["user_prompt"],
                        response_schema=repair_call["response_schema"],
                        model=model,
                        reasoning_effort=reasoning_effort,
                        timeout_s=timeout_s,
                    )
        return {"primary": primary, "repair": repair}


async def run_batch(
    output_dir: Path,
    *,
    concurrency: int,
    timeout_s: float,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text(encoding="utf-8"))
    index = json.loads((output_dir / "packet-index.json").read_text(encoding="utf-8"))
    if len(index) != identity["scenario_count"]:
        raise ValueError("packet index count drift")
    if (output_dir / "primary").exists() or (output_dir / "source-stability.json").exists():
        raise FileExistsError("batch has execution artifacts; interrupted batches are not resumed")
    provider = identity["inference"].get("provider", "codex")
    source_before = production_source_identity()
    harness_before = harness_file_identity()
    if source_before != identity["source"] or harness_before != identity["harness"]["files"]:
        raise ValueError("source or harness changed after packet freeze")
    provider_model_before: dict[str, Any] | None = None
    if provider == "ollama":
        provider_model_before = await _ollama_model_identity(
            identity["harness"]["ollama_url"],
            identity["inference"]["model"],
        )
        if provider_model_before != identity["harness"]["ollama_model_identity"]:
            raise ValueError("Ollama model identity changed after packet freeze")
    model = identity["inference"]["model"]
    reasoning_effort = identity["inference"].get("reasoning_effort", "")
    ollama_client = None
    if provider == "ollama":
        ollama_client = OllamaClient(
            identity["harness"]["ollama_url"],
            model,
            timeout_ms=int(identity["inference"]["timeout_ms"]),
            purpose="goal_association",
        )
    semaphore = asyncio.Semaphore(max(1, concurrency))
    completed = 0
    results: list[dict[str, Any]] = []

    async def tracked(item: dict[str, Any]) -> None:
        nonlocal completed
        result = await _run_one(
            output_dir=output_dir,
            item=item,
            semaphore=semaphore,
            timeout_s=timeout_s,
            model=model,
            reasoning_effort=reasoning_effort,
            provider=provider,
            ollama_client=ollama_client,
        )
        results.append(result)
        completed += 1
        if completed % 25 == 0 or completed == len(index):
            repairs = sum(1 for value in results if value["repair"] is not None)
            print(
                f"goal-association qualification progress {completed}/{len(index)} "
                f"repairs={repairs}",
                flush=True,
            )

    await asyncio.gather(*(tracked(item) for item in index))
    source_after = production_source_identity()
    harness_after = harness_file_identity()
    provider_model_after: dict[str, Any] | None = None
    if provider == "ollama":
        provider_model_after = await _ollama_model_identity(
            identity["harness"]["ollama_url"],
            identity["inference"]["model"],
        )
    primary_results = [value["primary"] for value in results]
    repair_results = [value["repair"] for value in results if value["repair"] is not None]
    stability = {
        "schema_version": 1,
        "source_before": source_before,
        "source_after": source_after,
        "harness_before": harness_before,
        "harness_after": harness_after,
        "provider_model_before": provider_model_before,
        "provider_model_after": provider_model_after,
        "stable": (
            source_before == source_after == identity["source"]
            and harness_before == harness_after == identity["harness"]["files"]
            and (
                provider != "ollama"
                or provider_model_before
                == provider_model_after
                == identity["harness"]["ollama_model_identity"]
            )
        ),
        "completed_primary_calls": len(primary_results),
        "successful_primary_processes": sum(
            1
            for value in primary_results
            if value["exit_code"] == 0 and not value["timed_out"]
        ),
        "primary_timeouts": sum(1 for value in primary_results if value["timed_out"]),
        "repair_calls": len(repair_results),
        "successful_repair_processes": sum(
            1
            for value in repair_results
            if value["exit_code"] == 0 and not value["timed_out"]
        ),
        "repair_timeouts": sum(1 for value in repair_results if value["timed_out"]),
    }
    (output_dir / "source-stability.json").write_text(
        json.dumps(stability, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not stability["stable"]:
        raise ValueError("production source or harness changed during immutable batch")
    return stability


def _resolution_map(resolution: GoalAssociationResolution) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for association in resolution.associations:
        for source_ref in association.source_responsibility_refs:
            mapped.append(
                {
                    "source_ref": source_ref,
                    "operation": "association",
                    "relationship": association.relationship,
                    "target_goal_ids": association.target_goal_ids,
                }
            )
    for goal in resolution.new_goals:
        for source_ref in goal.source_responsibility_refs:
            mapped.append(
                {
                    "source_ref": source_ref,
                    "operation": "new_goal",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "output_mode": goal.metadata.get("output_mode", "unspecified"),
                    "supersedes_goal_ids": goal.supersedes_goal_ids,
                }
            )
    return sorted(mapped, key=lambda item: item["source_ref"])


async def _adjudicate_one(
    case: dict[str, Any],
    primary_raw: str,
    repair_raw: str | None,
    schema: dict[str, Any],
) -> dict[str, Any]:
    raw_outputs = [primary_raw] + ([repair_raw] if repair_raw is not None else [])
    replay = ReplayModel(raw_outputs)
    schema_results: list[dict[str, Any]] = []
    for phase, raw in (("primary", primary_raw), ("repair", repair_raw)):
        if raw is None:
            continue
        try:
            value = json.loads(raw)
            errors = [
                error.message
                for error in Draft202012Validator(schema).iter_errors(value)
            ][:20]
        except Exception as exc:
            errors = [f"{type(exc).__name__}: {exc}"]
        schema_results.append(
            {"phase": phase, "accepted": not errors, "errors": errors}
        )
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    previous_level = logging.getLogger("chromie.agent.goal_association").level
    logging.getLogger("chromie.agent.goal_association").setLevel(logging.CRITICAL)
    try:
        resolution = await GoalAssociationResolver(replay).resolve(request)
    finally:
        logging.getLogger("chromie.agent.goal_association").setLevel(previous_level)
    observed_map = _resolution_map(resolution) if resolution.resolution_status == "resolved" else []
    expected_map = case["target"]["semantic_expectations"]["responsibility_map"]
    target_errors: list[str] = []
    if observed_map != expected_map:
        target_errors.append(
            "responsibility map drift: "
            f"actual={json.dumps(observed_map, ensure_ascii=False, sort_keys=True)} "
            f"expected={json.dumps(expected_map, ensure_ascii=False, sort_keys=True)}"
        )
    expected_calls = 2 if repair_raw is not None else 1
    if len(replay.calls) != expected_calls:
        target_errors.append(
            f"model call count drift: actual={len(replay.calls)} expected={expected_calls}"
        )
    recovery_keys = [key for key in RECOVERY_METADATA_KEYS if resolution.metadata.get(key)]
    final_schema = schema_results[-1] if schema_results else {"accepted": False}
    hard_pass = (
        bool(final_schema["accepted"])
        and resolution.resolution_status == "resolved"
        and not target_errors
    )
    strict_pass = hard_pass and repair_raw is None and not recovery_keys
    return {
        "schema_version": 1,
        "scenario_id": case["id"],
        "case_ref": _case_ref(case["id"]),
        "language": case["input"]["language"],
        "category": case["category"],
        "split": case["split"],
        "variant": (
            "candidate_aware" if case["target"]["semantic_expectations"]["candidate_goal_ids"] else "segmentation"
        ),
        "transport": {
            "primary_complete": bool(primary_raw),
            "repair_present": repair_raw is not None,
        },
        "schema": schema_results,
        "host": {
            "resolution_status": resolution.resolution_status,
            "model_call_count": len(replay.calls),
            "recovery_keys": recovery_keys,
            "terminal_state": resolution.metadata.get("goal_semantic_transaction", {}).get(
                "terminal_state"
            ),
        },
        "observed_responsibility_map": observed_map,
        "target_region": {"hard_errors": target_errors},
        "hard_pass": hard_pass,
        "strict_pass": strict_pass,
    }


async def adjudicate_batch(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text(encoding="utf-8"))
    stability = json.loads((output_dir / "source-stability.json").read_text(encoding="utf-8"))
    if not stability.get("stable") or stability.get("completed_primary_calls") != identity["scenario_count"]:
        raise ValueError("batch is incomplete or source-unstable")
    cases_by_id = {case["id"]: case for case in load_cases()}
    index = json.loads((output_dir / "packet-index.json").read_text(encoding="utf-8"))
    adjudications_dir = output_dir / "adjudication"
    if adjudications_dir.exists():
        raise FileExistsError("adjudication already exists for immutable batch")
    adjudications_dir.mkdir()
    counts: Counter[str] = Counter()
    slices: dict[str, dict[str, Counter[str]]] = {
        "category": defaultdict(Counter),
        "language": defaultdict(Counter),
        "split": defaultdict(Counter),
        "variant": defaultdict(Counter),
    }
    failures: list[dict[str, Any]] = []
    for item in index:
        case = cases_by_id[item["scenario_id"]]
        packet = json.loads(
            (output_dir / item["packet_path"]).read_text(encoding="utf-8")
        )
        schema = json.loads(
            (output_dir / packet["response_schema_path"]).read_text(encoding="utf-8")
        )
        primary_path = output_dir / "primary" / "raw-outputs" / f"{item['case_ref']}.txt"
        repair_path = output_dir / "repair" / "raw-outputs" / f"{item['case_ref']}.txt"
        primary_raw = primary_path.read_text(encoding="utf-8") if primary_path.exists() else ""
        repair_raw = repair_path.read_text(encoding="utf-8") if repair_path.exists() else None
        result = await _adjudicate_one(case, primary_raw, repair_raw, schema)
        (adjudications_dir / f"{item['case_ref']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verdict = "pass" if result["hard_pass"] else "fail"
        strict = "strict_pass" if result["strict_pass"] else "not_strict"
        counts[verdict] += 1
        counts[strict] += 1
        if result["transport"]["repair_present"]:
            counts["repair_used"] += 1
        if result["host"]["recovery_keys"]:
            counts["host_recovery_used"] += 1
        for slice_name in slices:
            slices[slice_name][result[slice_name]][verdict] += 1
        if verdict == "fail" and len(failures) < 150:
            failures.append(
                {
                    "scenario_id": result["scenario_id"],
                    "category": result["category"],
                    "schema": result["schema"],
                    "resolution_status": result["host"]["resolution_status"],
                    "target_errors": result["target_region"]["hard_errors"],
                }
            )
    provider = identity["inference"].get("provider", "codex")
    if provider == "ollama":
        semantic_review_status = (
            "deterministic hidden-oracle region; exact declared Ollama model and "
            "production transport; no independent semantic review"
        )
        evidence_ceiling = (
            "Declared Ollama model/digest through Chromie's production OllamaClient "
            "over exact rendered GA prompts, dynamic Schemas, and frozen generation "
            "options; bypasses the deployed Agent HTTP service and establishes no "
            "voice, simulator, hardware, independent-review, or release evidence."
        )
    else:
        semantic_review_status = (
            "deterministic hidden-oracle region; same-model and non-independent"
        )
        evidence_ceiling = (
            "Same-model offline Codex surrogate over exact rendered GA prompts and "
            "dynamic Schemas; not deployed provider/model, service, voice, simulator, "
            "hardware, independent review, or release evidence."
        )
    summary = {
        "schema_version": 1,
        "batch_label": identity["label"],
        "scenario_count": identity["scenario_count"],
        "source_stable": stability["stable"],
        "verdicts": dict(counts),
        "by_category": {
            key: dict(value) for key, value in sorted(slices["category"].items())
        },
        "by_language": {
            key: dict(value) for key, value in sorted(slices["language"].items())
        },
        "by_split": {
            key: dict(value) for key, value in sorted(slices["split"].items())
        },
        "by_variant": {
            key: dict(value) for key, value in sorted(slices["variant"].items())
        },
        "failure_examples": failures,
        "provider": provider,
        "model": identity["inference"]["model"],
        "model_digest": identity["inference"].get("model_digest"),
        "semantic_review_status": semantic_review_status,
        "evidence_ceiling": evidence_ceiling,
    }
    (output_dir / "adjudication-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--label", required=True)
    prepare.add_argument("--provider", choices=("codex", "ollama"), default="codex")
    prepare.add_argument("--model", default="gpt-5.6-sol")
    prepare.add_argument("--reasoning-effort", default="high")
    prepare.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    prepare.add_argument("--num-ctx", type=int, default=4096)
    prepare.add_argument("--num-predict", type=int, default=512)
    prepare.add_argument("--timeout-ms", type=int, default=120000)
    prepare.add_argument("--only-case", action="append", default=[])
    run = subparsers.add_parser("run")
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument("--timeout-s", type=float, default=600.0)
    adjudicate = subparsers.add_parser("adjudicate")
    adjudicate.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        result = validate_dataset()
    elif args.command == "prepare":
        result = asyncio.run(
            prepare_batch(
                args.output_dir,
                label=args.label,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                provider=args.provider,
                ollama_url=args.ollama_url,
                num_ctx=args.num_ctx,
                num_predict=args.num_predict,
                timeout_ms=args.timeout_ms,
                only_case_ids=args.only_case,
            )
        )
    elif args.command == "run":
        result = asyncio.run(
            run_batch(
                args.output_dir,
                concurrency=args.concurrency,
                timeout_s=args.timeout_s,
            )
        )
    else:
        result = asyncio.run(adjudicate_batch(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
