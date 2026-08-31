#!/usr/bin/env python3
"""Prepare, execute, and adjudicate Fast Planner qualification batches.

This is incomplete harness scaffolding until the model-authored corpus is reviewed,
materialized, and bound by ``dataset.json``. Its presence is not qualification
evidence and the current tracked checkpoint is not executable as a frozen batch.

Candidate calls are target-blind and one Codex invocation is used per scenario.
Codex receives the exact rendered production system/user prompt and the exact
dynamic canonical JSON Schema.  Streaming cases retain the production tagged
text transport.  This is same-model offline surrogate evidence: Codex is not
the deployed Ollama transport and no release/deployment claim follows from it.
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
from typing import Any, AsyncIterator

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.capabilities.catalog import CatalogCapability  # noqa: E402
from agent.app.fast_planner import (  # noqa: E402
    FastPlannerResolver,
    parse_fast_stream_document,
)
from agent.app.planner_context import (  # noqa: E402
    auxiliary_social_capability_payloads,
    fast_capability_payload,
)
from agent.app.planner_model_contract import is_planner_step_capability  # noqa: E402
from agent.app.planner_schema import fast_streaming_advance_response_schema  # noqa: E402
from shared.chromie_contracts.core_interpretation import (  # noqa: E402
    CognitiveWorkRequest,
)
from shared.chromie_contracts.plan import (  # noqa: E402
    FastPlannerStreamFailure,
    FastPlannerStreamTerminal,
)


DATASET_ROOT = ROOT / "benchmarks" / "datasets" / "fast_planner_daily_life"
SCENARIO_ROOT = DATASET_ROOT / "scenarios"
CATALOG_ROOT = DATASET_ROOT / "catalogs"
MANIFEST_PATH = DATASET_ROOT / "dataset.json"
PRODUCTION_TRANSACTION_FILES = (
    ROOT / "agent" / "app" / "fast_planner.py",
    ROOT / "agent" / "app" / "planner_prompt.py",
    ROOT / "agent" / "app" / "planner_schema.py",
    ROOT / "agent" / "app" / "planner_model_contract.py",
    ROOT / "agent" / "app" / "planner_validation.py",
    ROOT / "agent" / "app" / "planner_fast_validation.py",
    ROOT / "agent" / "app" / "planner_context.py",
    ROOT / "shared" / "chromie_contracts" / "core_interpretation.py",
    ROOT / "shared" / "chromie_contracts" / "plan.py",
)
HARNESS_FILES = (
    Path(__file__).resolve(),
    DATASET_ROOT / "validate.py",
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


def scenario_paths(dataset_root: Path = DATASET_ROOT) -> list[Path]:
    return sorted((dataset_root / "scenarios").glob("*/*/*.json"))


def load_cases(dataset_root: Path = DATASET_ROOT) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in scenario_paths(dataset_root):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path}: scenario must be an object")
        if path.stem != value.get("id"):
            raise ValueError(f"{path}: file stem does not match scenario id")
        if path.parent.name != value.get("category"):
            raise ValueError(f"{path}: category directory drift")
        if path.parent.parent.name != value.get("split"):
            raise ValueError(f"{path}: split directory drift")
        cases.append(value)
    return cases


def scenario_tree_digest(dataset_root: Path = DATASET_ROOT) -> str:
    digest = hashlib.sha256()
    for path in scenario_paths(dataset_root):
        digest.update(path.relative_to(dataset_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def production_source_identity() -> dict[str, Any]:
    files = {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in PRODUCTION_TRANSACTION_FILES
    }


def harness_file_identity() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in HARNESS_FILES
    }
    aggregate = _sha256(_json_bytes(files))
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
        "production_files_sha256": aggregate,
        "production_tracked_diff_sha256": _sha256(diff),
    }


class StaticCatalog:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.items = [CatalogCapability.model_validate(item) for item in entries]

    async def prompt_entries(self, **_: Any) -> list[CatalogCapability]:
        return list(self.items)


def materialize_catalog(case_input: dict[str, Any]) -> list[dict[str, Any]]:
    direct = case_input.get("catalog_capabilities")
    if isinstance(direct, list):
        entries = [dict(item) for item in direct if isinstance(item, dict)]
    else:
        fixture_id = str(case_input.get("catalog_fixture_id") or "").strip()
        if not fixture_id or not fixture_id.replace("_", "").isalnum():
            raise ValueError("scenario requires a safe catalog_fixture_id")
        fixture_path = CATALOG_ROOT / f"{fixture_id}.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        entries = [dict(item) for item in fixture["capabilities"]]
    overrides = case_input.get("catalog_overrides") or []
    if not isinstance(overrides, list):
        raise ValueError("catalog_overrides must be an array")
    by_id = {str(item.get("capability_id") or ""): item for item in entries}
    for override in overrides:
        if not isinstance(override, dict):
            raise ValueError("catalog override must be an object")
        capability_id = str(override.get("capability_id") or "").strip()
        if capability_id not in by_id:
            raise ValueError(f"catalog override references unknown Capability {capability_id}")
        allowed = {"capability_id", "available"}
        if set(override) - allowed:
            raise ValueError("catalog override may change only availability")
        by_id[capability_id]["available"] = bool(override.get("available"))
    return [by_id[key] for key in sorted(by_id)]


class CaptureModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": str(prompt), **kwargs})
        return {}

    async def generate_stream(
        self, prompt: Any, **kwargs: Any
    ) -> AsyncIterator[str]:
        self.calls.append({"prompt": str(prompt), **kwargs})
        if False:  # pragma: no cover - marks this function as an async generator
            yield ""


class ReplayModel:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    async def generate(self, prompt: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        value = json.loads(self.raw)
        if not isinstance(value, dict):
            raise ValueError("candidate canonical output is not an object")
        return value

    async def generate_stream(
        self, prompt: Any, **kwargs: Any
    ) -> AsyncIterator[str]:
        self.calls += 1
        yield self.raw


def _stream_schema(
    request: CognitiveWorkRequest,
    catalog: StaticCatalog,
) -> dict[str, Any]:
    responsibilities = list(request.responsibilities)
    responsibility_refs = [item.local_ref for item in responsibilities]
    available = [
        item
        for item in catalog.items
        if item.available
        and item.interaction_executable
        and is_planner_step_capability(item.capability_id)
    ]
    capability_payload = [
        fast_capability_payload(item, include_side_effect_free=True)
        for item in available[:24]
    ]
    auxiliary = auxiliary_social_capability_payloads(catalog.items)
    schema = fast_streaming_advance_response_schema(
        responsibility_refs,
        responsibilities=responsibilities,
        capabilities=capability_payload,
        auxiliary_social_capabilities=auxiliary,
        interpretation_unresolved=list(request.interpretation_unresolved),
        language=str(request.language or ""),
    )
    if request.interpretation_unresolved:
        presentation = schema["properties"]["presentation_commit"]
        presentation["properties"]["activity"] = {"type": "null"}
        presentation["properties"]["auxiliary_activities"] = {
            "type": "array",
            "maxItems": 0,
        }
    return schema


async def build_transaction(case: dict[str, Any]) -> dict[str, Any]:
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    catalog = StaticCatalog(materialize_catalog(case["input"]))
    capture = CaptureModel()
    resolver = FastPlannerResolver(
        capture,
        catalog,
        max_contract_repairs=0,
    )
    runtime_variant = case["input"]["runtime_variant"]
    previous_level = logging.getLogger("chromie.agent.fast_planner").level
    logging.getLogger("chromie.agent.fast_planner").setLevel(logging.CRITICAL)
    try:
        if runtime_variant == "streaming_advance":
            _ = [frame async for frame in resolver.stream_advance(request)]
        else:
            await resolver.resolve(request)
    finally:
        logging.getLogger("chromie.agent.fast_planner").setLevel(previous_level)
    if len(capture.calls) != 1:
        raise ValueError(
            f"{case['id']}: prompt capture expected one primary call, got {len(capture.calls)}"
        )
    call = capture.calls[0]
    response_schema = (
        _stream_schema(
            CognitiveWorkRequest.model_validate(case["input"]["request"]),
            catalog,
        )
        if runtime_variant == "streaming_advance"
        else call["response_format"]
    )
    if not isinstance(response_schema, dict):
        raise ValueError(f"{case['id']}: missing dynamic response Schema")
    Draft202012Validator.check_schema(response_schema)
    system_prompt = str(call.get("system") or "")
    user_prompt = str(call["prompt"])
    prompt_identity = {
        "system_sha256": _sha256(system_prompt),
        "user_sha256": _sha256(user_prompt),
        "schema_sha256": _sha256(_json_bytes(response_schema)),
    }
    return {
        "runtime_variant": runtime_variant,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response_schema": response_schema,
        "options": call.get("options") or {},
        "production_prompt_family": call.get("prompt_family") or "",
        "production_response_transport": (
            "tagged_two_frame_text"
            if runtime_variant == "streaming_advance"
            else "structured_json"
        ),
        "prompt_identity": prompt_identity,
    }


def _case_ref(case_id: str) -> str:
    return f"case_{_sha256(case_id)[:24]}"


async def validate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_requests: set[str] = set()
    contrast_members: dict[str, set[str]] = defaultdict(set)
    contrast_splits: dict[str, set[str]] = defaultdict(set)

    for case in cases:
        case_id = str(case.get("id") or "")
        try:
            if case.get("schema_version") != 1:
                raise ValueError("unknown scenario schema version")
            if case_id in seen_ids or not case_id:
                raise ValueError("missing or duplicate scenario id")
            seen_ids.add(case_id)
            request = CognitiveWorkRequest.model_validate(case["input"]["request"])
            catalog = StaticCatalog(materialize_catalog(case["input"]))
            if not catalog.items:
                raise ValueError("empty Capability catalog")
            request_key = _sha256(_json_bytes(request.model_dump(mode="json")))
            if request_key in seen_requests:
                raise ValueError("duplicate complete Planner request")
            seen_requests.add(request_key)
            if request.language != case["input"]["language"]:
                raise ValueError("language/request drift")
            if case["review"]["training_eligible"] is not False:
                raise ValueError("generated scenario became training eligible")
            if case["review"]["independent_semantic_review"] is not False:
                raise ValueError("unreviewed scenario claims independent review")
            contrast_id = str(case["contrast_set"]["id"])
            contrast_members[contrast_id].add(str(case["contrast_set"]["member"]))
            contrast_splits[contrast_id].add(str(case["split"]))
            expectation = case["target"]["reference_region"]
            expected_refs = [item.local_ref for item in request.responsibilities]
            if expectation["expected_responsibility_refs"] != expected_refs:
                raise ValueError("Responsibility reference oracle drift")
            expected_goals = [
                str(item.get("goal_id") or "")
                for item in request.context.get("goal_association_resolution", {}).get("new_goals", [])
            ]
            if expectation["expected_goal_ids"] != expected_goals:
                raise ValueError("Goal reference oracle drift")
            transaction = await build_transaction(case)
            if "target" in transaction or "reference_region" in transaction:
                raise ValueError("target leaked into candidate transaction")
            counts[f"language:{case['input']['language']}"] += 1
            counts[f"split:{case['split']}"] += 1
            counts[f"category:{case['category']}"] += 1
            counts[f"runtime:{case['input']['runtime_variant']}"] += 1
            counts["validated"] += 1
        except Exception as exc:
            errors.append(f"{case_id}: {type(exc).__name__}: {exc}")

    for contrast_id, members in contrast_members.items():
        if len(members) != 10:
            errors.append(f"{contrast_id}: expected 10 contrast members, got {len(members)}")
        if len(contrast_splits[contrast_id]) != 1:
            errors.append(f"{contrast_id}: contrast set crosses splits")
    if errors:
        raise ValueError("Fast Planner corpus validation failed:\n" + "\n".join(errors[:100]))
    return {
        "scenario_count": len(cases),
        "languages": {key.split(":", 1)[1]: value for key, value in counts.items() if key.startswith("language:")},
        "splits": {key.split(":", 1)[1]: value for key, value in counts.items() if key.startswith("split:")},
        "categories": {key.split(":", 1)[1]: value for key, value in counts.items() if key.startswith("category:")},
        "runtime_variants": {key.split(":", 1)[1]: value for key, value in counts.items() if key.startswith("runtime:")},
        "contrast_set_count": len(contrast_members),
        "validated": counts["validated"],
        "scenario_tree_sha256": scenario_tree_digest(),
    }


def validate_dataset(dataset_root: Path = DATASET_ROOT) -> dict[str, Any]:
    manifest = json.loads((dataset_root / "dataset.json").read_text(encoding="utf-8"))
    cases = load_cases(dataset_root)
    summary = asyncio.run(validate_cases(cases))
    expected = manifest["coverage_contract"]
    if summary["scenario_count"] != expected["scenario_count"]:
        raise ValueError("manifest scenario count drift")
    if summary["languages"] != expected["languages"]:
        raise ValueError("manifest language count drift")
    if summary["splits"] != expected["splits"]:
        raise ValueError("manifest split count drift")
    if summary["categories"] != expected["categories"]:
        raise ValueError("manifest category count drift")
    if summary["runtime_variants"] != expected["runtime_variants"]:
        raise ValueError("manifest runtime count drift")
    if summary["scenario_tree_sha256"] != manifest["asset_contract"]["scenario_tree_sha256"]:
        raise ValueError("manifest scenario-tree digest drift")
    return summary


async def prepare_batch(output_dir: Path, *, label: str) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    packets_dir = output_dir / "packets"
    schemas_dir = output_dir / "schemas"
    packets_dir.mkdir()
    schemas_dir.mkdir()
    codex_envelope_schema = {
        "type": "object",
        "properties": {"model_output_text": {"type": "string"}},
        "required": ["model_output_text"],
        "additionalProperties": False,
    }
    (output_dir / "codex-envelope-schema.json").write_text(
        json.dumps(codex_envelope_schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cases = load_cases()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source = production_source_identity()
    index: list[dict[str, Any]] = []
    prompt_identities: dict[str, dict[str, str]] = {}
    scenario_path_by_id = {path.stem: path for path in scenario_paths()}
    for position, case in enumerate(cases, start=1):
        transaction = await build_transaction(case)
        case_ref = _case_ref(case["id"])
        schema_sha = transaction["prompt_identity"]["schema_sha256"]
        schema_path = schemas_dir / f"{schema_sha}.json"
        if not schema_path.exists():
            schema_path.write_text(
                json.dumps(transaction["response_schema"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        packet = {
            "schema_version": 1,
            "case_ref": case_ref,
            "system_prompt": transaction["system_prompt"],
            "user_prompt": transaction["user_prompt"],
            "response_schema_sha256": schema_sha,
            "response_schema_path": schema_path.relative_to(output_dir).as_posix(),
            "production_prompt_family": transaction["production_prompt_family"],
            "production_response_transport": transaction["production_response_transport"],
            "production_options": transaction["options"],
            "prompt_identity": transaction["prompt_identity"],
            "target_blind": True,
        }
        packet_path = packets_dir / f"{case_ref}.json"
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index.append({
            "position": position,
            "case_ref": case_ref,
            "scenario_id": case["id"],
            "scenario_path": scenario_path_by_id[case["id"]].relative_to(ROOT).as_posix(),
            "packet_path": packet_path.relative_to(output_dir).as_posix(),
        })
        prompt_identities[case_ref] = transaction["prompt_identity"]
    batch_identity = {
        "schema_version": 1,
        "label": label,
        "issue": "https://github.com/TimeTreker/chromie/issues/35",
        "dataset_id": manifest["dataset_id"],
        "scenario_count": len(cases),
        "scenario_tree_sha256": scenario_tree_digest(),
        "source": source,
        "harness": {
            "files": harness_file_identity(),
            "python": sys.version,
            "codex_cli": subprocess.run(
                ["codex", "--version"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        },
        "inference": {
            "authority": "Codex CLI same-model offline surrogate",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "candidate_calls_per_scenario": 1,
            "retry_policy": "none",
            "same_model_non_independent": True,
            "transport_limit": "Exact production prompt/schema content is projected through a strict Codex string envelope; Codex CLI is not the deployed Ollama structured decoder or text stream.",
        },
        "codex_envelope_schema_sha256": _sha256(
            _json_bytes(codex_envelope_schema)
        ),
        "prompt_identity_index_sha256": _sha256(_json_bytes(prompt_identities)),
        "candidate_packet_policy": "system/user/schema only; target, rubric, category, split, and expected result excluded",
    }
    (output_dir / "packet-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "batch-identity.json").write_text(
        json.dumps(batch_identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return batch_identity


def _candidate_prompt(
    packet: dict[str, Any],
    response_schema: dict[str, Any],
) -> str:
    transport = packet["production_response_transport"]
    raw_instruction = (
        "The model_output_text string must contain only the raw JSON object required "
        "by the dynamic production response Schema."
        if transport == "structured_json"
        else "The model_output_text string must contain only the exact two tagged frames "
        "required by the Fast Planner system prompt."
    )
    return (
        "Execute this one Fast Planner semantic transaction. Do not inspect files, "
        "run tools, discuss the task, or add benchmark commentary. Treat the following "
        "SYSTEM PROMPT as your role instruction and the USER PROMPT as the complete "
        "authoritative transaction.\n\n"
        "SYSTEM PROMPT\n"
        f"{packet['system_prompt']}\n\n"
        "USER PROMPT\n"
        f"{packet['user_prompt']}\n\n"
        "DYNAMIC PRODUCTION RESPONSE SCHEMA\n"
        f"{json.dumps(response_schema, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n\n"
        "Return one Codex transport envelope with exactly one field named "
        "model_output_text. This envelope is transport only and is removed before "
        "production validation. "
        f"{raw_instruction}"
    )


async def _run_one(
    *,
    output_dir: Path,
    item: dict[str, Any],
    semaphore: asyncio.Semaphore,
    timeout_s: float,
) -> dict[str, Any]:
    async with semaphore:
        case_ref = item["case_ref"]
        packet = json.loads((output_dir / item["packet_path"]).read_text(encoding="utf-8"))
        outputs_dir = output_dir / "raw-outputs"
        logs_dir = output_dir / "call-logs"
        executions_dir = output_dir / "call-executions"
        outputs_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        executions_dir.mkdir(exist_ok=True)
        output_path = outputs_dir / f"{case_ref}.txt"
        envelopes_dir = output_dir / "codex-envelopes"
        envelopes_dir.mkdir(exist_ok=True)
        envelope_path = envelopes_dir / f"{case_ref}.json"
        log_path = logs_dir / f"{case_ref}.log"
        execution_path = executions_dir / f"{case_ref}.json"
        if output_path.exists() or envelope_path.exists() or execution_path.exists():
            raise FileExistsError(f"immutable batch output already exists for {case_ref}")
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
            "gpt-5.6-sol",
            "-c",
            'model_reasoning_effort="high"',
            "-o",
            str(envelope_path),
            "--output-schema",
            str(output_dir / "codex-envelope-schema.json"),
        ]
        command.append("-")
        response_schema = json.loads(
            (output_dir / packet["response_schema_path"]).read_text(encoding="utf-8")
        )
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
                    _candidate_prompt(packet, response_schema).encode("utf-8")
                ),
                timeout=timeout_s,
            )
            timed_out = False
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            timed_out = True
        ended = time.time()
        log_path.write_bytes(
            b"STDOUT\n" + stdout + b"\nSTDERR\n" + stderr
        )
        envelope_error = ""
        if envelope_path.exists():
            try:
                envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
                raw_output = envelope["model_output_text"]
                if not isinstance(raw_output, str):
                    raise TypeError("model_output_text is not a string")
                output_path.write_text(raw_output, encoding="utf-8")
            except Exception as exc:
                envelope_error = f"{type(exc).__name__}: {exc}"
        execution = {
            "schema_version": 1,
            "case_ref": case_ref,
            "attempt_count": 1,
            "hidden_retry": False,
            "started_epoch_s": started,
            "ended_epoch_s": ended,
            "latency_s": ended - started,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "output_present": output_path.exists(),
            "output_sha256": _sha256(output_path.read_bytes()) if output_path.exists() else "",
            "codex_envelope_present": envelope_path.exists(),
            "codex_envelope_sha256": _sha256(envelope_path.read_bytes()) if envelope_path.exists() else "",
            "codex_envelope_error": envelope_error,
            "log_sha256": _sha256(log_path.read_bytes()),
        }
        execution_path.write_text(
            json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return execution


async def run_batch(output_dir: Path, *, concurrency: int, timeout_s: float) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text(encoding="utf-8"))
    index = json.loads((output_dir / "packet-index.json").read_text(encoding="utf-8"))
    if len(index) != identity["scenario_count"]:
        raise ValueError("packet index count drift")
    if (output_dir / "raw-outputs").exists() or (output_dir / "call-executions").exists():
        raise FileExistsError("batch has existing execution artifacts; interrupted batches are not resumed")
    source_before = production_source_identity()
    if source_before != identity["source"]:
        raise ValueError("production source changed after packet freeze")
    harness_before = harness_file_identity()
    if harness_before != identity["harness"]["files"]:
        raise ValueError("qualification harness changed after packet freeze")
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
        )
        results.append(result)
        completed += 1
        if completed % 25 == 0 or completed == len(index):
            print(f"fast-planner qualification progress {completed}/{len(index)}", flush=True)

    await asyncio.gather(*(tracked(item) for item in index))
    source_after = production_source_identity()
    harness_after = harness_file_identity()
    stability = {
        "schema_version": 1,
        "source_before": source_before,
        "source_after": source_after,
        "harness_before": harness_before,
        "harness_after": harness_after,
        "stable": (
            source_before == source_after == identity["source"]
            and harness_before == harness_after == identity["harness"]["files"]
        ),
        "completed_calls": len(results),
        "successful_processes": sum(
            1 for item in results if item["exit_code"] == 0 and not item["timed_out"]
        ),
        "timeouts": sum(1 for item in results if item["timed_out"]),
    }
    (output_dir / "source-stability.json").write_text(
        json.dumps(stability, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not stability["stable"]:
        raise ValueError("production source changed during immutable batch")
    return stability


def _target_checks(
    expectation: dict[str, Any],
    *,
    disposition: str,
    capability_ids: list[str],
    reuse_ids: list[str],
    scope_ids: list[str],
    coverage: str,
) -> list[str]:
    errors: list[str] = []
    if disposition not in expectation["accepted_dispositions"]:
        errors.append(f"disposition={disposition!r} outside accepted region")
    missing_capabilities = set(expectation["required_capability_ids"]) - set(capability_ids)
    if missing_capabilities:
        errors.append("missing required capabilities: " + ",".join(sorted(missing_capabilities)))
    forbidden_capabilities = set(expectation["forbidden_capability_ids"]) & set(capability_ids)
    if forbidden_capabilities:
        errors.append("selected forbidden capabilities: " + ",".join(sorted(forbidden_capabilities)))
    missing_reuse = set(expectation["required_reuse_activity_ids"]) - set(reuse_ids)
    if missing_reuse:
        errors.append("missing retained Work reuse: " + ",".join(sorted(missing_reuse)))
    forbidden_reuse = set(expectation["forbidden_reuse_activity_ids"]) & set(reuse_ids)
    if forbidden_reuse:
        errors.append("reused forbidden retained Work: " + ",".join(sorted(forbidden_reuse)))
    expected_scope = expectation["expected_goal_ids"] or expectation["expected_responsibility_refs"]
    if set(scope_ids) != set(expected_scope):
        errors.append(f"scope drift actual={sorted(scope_ids)} expected={sorted(expected_scope)}")
    if coverage != "complete" and capability_ids:
        errors.append("non-complete result carries executable Work")
    return errors


async def _adjudicate_one(
    case: dict[str, Any],
    raw_text: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    runtime_variant = case["input"]["runtime_variant"]
    expectation = case["target"]["reference_region"]
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    catalog = StaticCatalog(materialize_catalog(case["input"]))
    replay = ReplayModel(raw_text)
    resolver = FastPlannerResolver(replay, catalog, max_contract_repairs=0)
    schema_errors: list[str] = []
    host_accepted = False
    host_error = ""
    disposition = ""
    coverage = ""
    capability_ids: list[str] = []
    reuse_ids: list[str] = []
    scope_ids: list[str] = []
    normalized_fields: list[str] = []
    raw_value: Any = None
    previous_level = logging.getLogger("chromie.agent.fast_planner").level
    logging.getLogger("chromie.agent.fast_planner").setLevel(logging.CRITICAL)
    try:
        if runtime_variant == "streaming_advance":
            try:
                presentation, terminal = parse_fast_stream_document(raw_text)
                raw_value = {
                    "presentation_commit": presentation,
                    "terminal_result": terminal,
                }
                schema_errors = [
                    error.message
                    for error in Draft202012Validator(schema).iter_errors(raw_value)
                ][:20]
            except Exception as exc:
                schema_errors = [f"{type(exc).__name__}: {exc}"]
            frames = [frame async for frame in resolver.stream_advance(request)]
            terminal_frame = next(
                (item for item in frames if isinstance(item, FastPlannerStreamTerminal)),
                None,
            )
            failure_frame = next(
                (item for item in frames if isinstance(item, FastPlannerStreamFailure)),
                None,
            )
            if terminal_frame is not None:
                advance = terminal_frame.advance
                host_accepted = failure_frame is None
                disposition = advance.disposition
                coverage = advance.coverage
                capability_ids = [
                    item.capability_id
                    for item in advance.activities
                    if item.role == "capability"
                ]
                scope_ids = list(advance.covered_responsibility_refs)
                if advance.metadata.get("authoritative_arg_repairs"):
                    normalized_fields.append("authoritative_arg_repairs")
            else:
                host_error = failure_frame.reason if failure_frame is not None else "missing terminal frame"
        else:
            try:
                raw_value = json.loads(raw_text)
                schema_errors = [
                    error.message
                    for error in Draft202012Validator(schema).iter_errors(raw_value)
                ][:20]
            except Exception as exc:
                schema_errors = [f"{type(exc).__name__}: {exc}"]
            plan = await resolver.resolve(request)
            fallback = plan.metadata.get("resolver") == "fast_planner" and plan.metadata.get("authority") == "advisory"
            host_accepted = not fallback
            if fallback:
                host_error = str(plan.escalation_reason or plan.metadata.get("error") or "fast planner fallback")
            disposition = plan.disposition
            coverage = plan.coverage
            capability_ids = [item.capability_id for item in plan.steps]
            reuse_ids = [item.reuse_activity_id for item in plan.steps if item.reuse_activity_id]
            scope_ids = list(plan.goal_ids)
            for key in (
                "parameter_provenance_normalization",
                "terminal_response_accounting_normalization",
            ):
                if plan.metadata.get(key):
                    normalized_fields.append(key)
    except Exception as exc:
        host_error = f"{type(exc).__name__}: {exc}"
    finally:
        logging.getLogger("chromie.agent.fast_planner").setLevel(previous_level)
    target_errors = _target_checks(
        expectation,
        disposition=disposition,
        capability_ids=capability_ids,
        reuse_ids=reuse_ids,
        scope_ids=scope_ids,
        coverage=coverage,
    )
    hard_pass = (
        not schema_errors
        and host_accepted
        and replay.calls == 1
        and not normalized_fields
        and not target_errors
    )
    return {
        "schema_version": 1,
        "scenario_id": case["id"],
        "case_ref": _case_ref(case["id"]),
        "runtime_variant": runtime_variant,
        "language": case["input"]["language"],
        "category": case["category"],
        "split": case["split"],
        "transport": {"complete": bool(raw_text), "candidate_call_count": 1},
        "schema": {"accepted": not schema_errors, "errors": schema_errors},
        "host": {
            "accepted_primary_result": host_accepted,
            "error": host_error,
            "model_call_count": replay.calls,
            "normalization_fields": normalized_fields,
        },
        "observed": {
            "disposition": disposition,
            "coverage": coverage,
            "capability_ids": capability_ids,
            "reuse_activity_ids": reuse_ids,
            "scope_ids": scope_ids,
        },
        "target_region": {"hard_errors": target_errors},
        "hard_pass": hard_pass,
        "semantic_review": {
            "status": "pending_same_model_posthoc_review",
            "semantic_facts": expectation["semantic_facts"],
            "forbidden_claims": expectation["forbidden_claims"],
        },
    }


async def adjudicate_batch(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text(encoding="utf-8"))
    stability = json.loads((output_dir / "source-stability.json").read_text(encoding="utf-8"))
    if not stability.get("stable") or stability.get("completed_calls") != identity["scenario_count"]:
        raise ValueError("batch is incomplete or source-unstable")
    cases_by_id = {case["id"]: case for case in load_cases()}
    index = json.loads((output_dir / "packet-index.json").read_text(encoding="utf-8"))
    adjudications_dir = output_dir / "adjudication"
    if adjudications_dir.exists():
        raise FileExistsError("adjudication already exists for immutable batch")
    adjudications_dir.mkdir()
    counts: Counter[str] = Counter()
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    language_counts: dict[str, Counter[str]] = defaultdict(Counter)
    runtime_counts: dict[str, Counter[str]] = defaultdict(Counter)
    failure_examples: list[dict[str, Any]] = []
    for item in index:
        case = cases_by_id[item["scenario_id"]]
        packet = json.loads((output_dir / item["packet_path"]).read_text(encoding="utf-8"))
        schema = json.loads((output_dir / packet["response_schema_path"]).read_text(encoding="utf-8"))
        raw_path = output_dir / "raw-outputs" / f"{item['case_ref']}.txt"
        raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
        result = await _adjudicate_one(case, raw_text, schema)
        (adjudications_dir / f"{item['case_ref']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verdict = "pass" if result["hard_pass"] else "fail"
        counts[verdict] += 1
        if result["schema"]["accepted"]:
            counts["schema_accepted"] += 1
        if result["host"]["accepted_primary_result"]:
            counts["host_accepted"] += 1
        if result["host"]["normalization_fields"]:
            counts["host_normalized"] += 1
        category_counts[result["category"]][verdict] += 1
        language_counts[result["language"]][verdict] += 1
        runtime_counts[result["runtime_variant"]][verdict] += 1
        if verdict == "fail" and len(failure_examples) < 100:
            failure_examples.append({
                "scenario_id": result["scenario_id"],
                "schema_errors": result["schema"]["errors"],
                "host_error": result["host"]["error"],
                "normalization_fields": result["host"]["normalization_fields"],
                "target_errors": result["target_region"]["hard_errors"],
            })
    summary = {
        "schema_version": 1,
        "batch_label": identity["label"],
        "scenario_count": identity["scenario_count"],
        "source_stable": stability["stable"],
        "hard_verdicts": dict(counts),
        "by_category": {key: dict(value) for key, value in sorted(category_counts.items())},
        "by_language": {key: dict(value) for key, value in sorted(language_counts.items())},
        "by_runtime_variant": {key: dict(value) for key, value in sorted(runtime_counts.items())},
        "failure_examples": failure_examples,
        "semantic_review_status": "pending_same_model_posthoc_review",
        "evidence_ceiling": "Same-model offline Codex surrogate over exact rendered prompts/dynamic Schemas; not deployed Ollama, service, voice, simulator, hardware, independent review, or release evidence.",
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
    run = subparsers.add_parser("run")
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--timeout-s", type=float, default=600.0)
    adjudicate = subparsers.add_parser("adjudicate")
    adjudicate.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        result = validate_dataset()
    elif args.command == "prepare":
        result = asyncio.run(prepare_batch(args.output_dir, label=args.label))
    elif args.command == "run":
        result = asyncio.run(run_batch(args.output_dir, concurrency=args.concurrency, timeout_s=args.timeout_s))
    else:
        result = asyncio.run(adjudicate_batch(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
