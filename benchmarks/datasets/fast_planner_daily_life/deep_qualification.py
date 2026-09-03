#!/usr/bin/env python3
"""Validate and qualify the frozen Deep Planner daily-life contrast corpus."""

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

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.deep_planner import DeepPlannerResolver  # noqa: E402
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest  # noqa: E402
from shared.chromie_contracts.control import GoalCancellationEvidence  # noqa: E402
from shared.chromie_contracts.goal import GoalAssociationResolution  # noqa: E402
from shared.chromie_contracts.tool_result import ToolResultEvidence  # noqa: E402
from .qualification import (  # noqa: E402
    CATALOG_ROOT,
    CaptureModel,
    ReplayModel,
    StaticCatalog,
    _activity_ids,
    _json_bytes,
    _sha256,
    _target_checks,
    materialize_catalog,
)


DATASET_ROOT = ROOT / "benchmarks/datasets/fast_planner_daily_life"
SCENARIO_ROOT = DATASET_ROOT / "deep_scenarios"
MANIFEST_PATH = DATASET_ROOT / "deep_dataset.json"
DATASET_ID = "chromie.deep_planner_daily_life.v1"
RUNTIME_VARIANTS = {"deep_primary", "deep_reentry"}
CAPACITIES = {
    "compound_constrained_multi_goal_work",
    "fast_escalation_without_candidate_leakage",
    "blocked_degraded_failed_or_unsafe_reentry",
    "plan_revision_after_changed_truth",
    "resource_or_concurrency_conflict_alternative",
    "consequential_ambiguity_clarification",
    "incomplete_observation_acquisition",
    "confirmation_and_cancellation_revision",
    "complex_agent_skill_composition",
    "no_change_or_no_safe_plan",
}
PRODUCTION_TRANSACTION_FILES = (
    ROOT / "agent/app/deep_planner.py",
    ROOT / "agent/app/capabilities/catalog.py",
    ROOT / "agent/app/planner_context.py",
    ROOT / "agent/app/planner_deep_validation.py",
    ROOT / "agent/app/planner_fallback.py",
    ROOT / "agent/app/planner_grounding.py",
    ROOT / "agent/app/planner_model_contract.py",
    ROOT / "agent/app/planner_prompt.py",
    ROOT / "agent/app/planner_schema.py",
    ROOT / "agent/app/planner_validation.py",
    ROOT / "agent/app/agent_skills/disclosure.py",
    ROOT / "shared/chromie_contracts/core_interpretation.py",
    ROOT / "shared/chromie_contracts/goal.py",
    ROOT / "shared/chromie_contracts/plan.py",
    ROOT / "shared/chromie_contracts/resource.py",
)
HARNESS_FILES = (Path(__file__).resolve(), MANIFEST_PATH, CATALOG_ROOT / "common_v1.json")


def scenario_paths() -> list[Path]:
    return sorted(SCENARIO_ROOT.glob("*/*/*.json"))


def load_cases() -> list[dict[str, Any]]:
    cases = []
    for path in scenario_paths():
        case = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != case.get("id"):
            raise ValueError(f"{path}: scenario id/path drift")
        cases.append(case)
    return cases


def scenario_tree_digest() -> str:
    digest = hashlib.sha256()
    for path in scenario_paths():
        digest.update(path.relative_to(DATASET_ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_identity() -> dict[str, Any]:
    files = {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in PRODUCTION_TRANSACTION_FILES
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--binary", "--", *files],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {
        "git_revision": revision,
        "production_files": files,
        "production_files_sha256": _sha256(_json_bytes(files)),
        "production_tracked_diff_sha256": _sha256(diff),
    }


def harness_identity() -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes()) for path in HARNESS_FILES}


def case_ref(case_id: str) -> str:
    return f"case_{_sha256(case_id)[:24]}"


async def build_transaction(case: dict[str, Any]) -> dict[str, Any]:
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    capture = CaptureModel()
    resolver = DeepPlannerResolver(capture, StaticCatalog(materialize_catalog(case["input"])))
    previous = logging.getLogger("chromie.agent.deep_planner").level
    logging.getLogger("chromie.agent.deep_planner").setLevel(logging.CRITICAL)
    try:
        await resolver.resolve(request)
    finally:
        logging.getLogger("chromie.agent.deep_planner").setLevel(previous)
    if len(capture.calls) != 1:
        raise ValueError(f"{case['id']}: expected one Deep primary call, got {len(capture.calls)}")
    call = capture.calls[0]
    schema = call.get("response_format")
    if not isinstance(schema, dict):
        raise ValueError(f"{case['id']}: dynamic Deep Schema missing")
    Draft202012Validator.check_schema(schema)
    return {
        "system_prompt": str(call.get("system") or ""),
        "user_prompt": str(call["prompt"]),
        "response_schema": schema,
        "options": call.get("options") or {},
        "production_prompt_family": call.get("prompt_family") or "",
        "prompt_identity": {
            "system_sha256": _sha256(str(call.get("system") or "")),
            "user_sha256": _sha256(str(call["prompt"])),
            "schema_sha256": _sha256(_json_bytes(schema)),
        },
    }


async def validate_dataset() -> dict[str, Any]:
    cases = load_cases()
    errors: list[str] = []
    counts: Counter[str] = Counter()
    contrast: dict[str, set[str]] = defaultdict(set)
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "")
        try:
            if case.get("schema_version") != 1 or case.get("dataset_id") != DATASET_ID:
                raise ValueError("scenario contract drift")
            if not case_id or case_id in seen:
                raise ValueError("missing or duplicate id")
            seen.add(case_id)
            variant = case["input"]["runtime_variant"]
            if variant not in RUNTIME_VARIANTS or case["category"] != variant:
                raise ValueError("runtime/category drift")
            request = CognitiveWorkRequest.model_validate(case["input"]["request"])
            raw_resolution = request.context.get("goal_association_resolution")
            resolution = GoalAssociationResolution.model_validate(raw_resolution)
            if raw_resolution != resolution.prompt_projection():
                raise ValueError("Goal Association projection is not exact production shape")
            if request.sid != case_id or request.language != case["input"]["language"]:
                raise ValueError("request identity drift")
            if request.context.get("fast_plan_resolution") or request.context.get(
                "runtime_validator_feedback"
            ):
                raise ValueError("Deep input contains Fast candidate/feedback")
            result_reentry = request.context.get("result_evidence_reentry")
            cancellation_reentry = request.context.get("goal_cancellation_reentry")
            if isinstance(result_reentry, dict):
                terminal_evidence = [
                    ToolResultEvidence.model_validate(item)
                    for item in request.context.get("trusted_terminal_evidence") or []
                ]
                execution_truth = request.context.get("trusted_execution_outcome")
                if not isinstance(execution_truth, dict):
                    raise ValueError("Deep result re-entry lacks Host-projected execution truth")
                scoped_goals = {str(value) for value in result_reentry.get("source_goal_ids") or []}
                scoped_evidence = {
                    str(value) for value in result_reentry.get("evidence_refs") or []
                }
                if {item.evidence_id for item in terminal_evidence} != scoped_evidence:
                    raise ValueError("Deep terminal Evidence/re-entry scope drift")
                truth_goals = {
                    str(item.get("goal_id") or "")
                    for item in execution_truth.get("goal_outcomes") or []
                    if isinstance(item, dict)
                }
                truth_evidence = {
                    str(item.get("evidence_id") or "")
                    for item in execution_truth.get("evidence") or []
                    if isinstance(item, dict)
                }
                if truth_goals != scoped_goals or truth_evidence != scoped_evidence:
                    raise ValueError("Deep execution truth/re-entry scope drift")
            if isinstance(cancellation_reentry, dict):
                cancellation_evidence = [
                    GoalCancellationEvidence.model_validate(item)
                    for item in request.context.get("trusted_goal_cancellation_evidence") or []
                ]
                scoped_evidence = {
                    str(value) for value in cancellation_reentry.get("evidence_refs") or []
                }
                if {item.evidence_id for item in cancellation_evidence} != scoped_evidence:
                    raise ValueError("Deep cancellation Evidence/re-entry scope drift")
            capacity = case["adversarial_design"]["primary_capacity_id"]
            if capacity not in CAPACITIES:
                raise ValueError("unknown Deep capacity")
            language = case["input"]["language"]
            if language not in {"en-US", "zh-CN"}:
                raise ValueError("unsupported language")
            condition = case["adversarial_design"]["condition"]
            member = f"{condition}-{'en' if language == 'en-US' else 'zh'}"
            contrast[case["contrast_set"]["id"]].add(member)
            if case["review"]["training_eligible"] or case["review"]["independent_semantic_review"]:
                raise ValueError("unreviewed case claims promotion")
            expectation = case["target"]["reference_region"]
            expected_goals = [goal.goal_id for goal in resolution.new_goals]
            if expectation["expected_goal_ids"] != expected_goals:
                raise ValueError("Goal oracle drift")
            if variant == "deep_reentry":
                scope = request.planner_reentry_scope
                if (
                    scope is None
                    or list(scope.goal_ids) != expected_goals
                    or list(scope.evidence_refs) != expectation["required_evidence_refs"]
                ):
                    raise ValueError("Deep re-entry scope drift")
            elif request.planner_reentry_scope is not None:
                raise ValueError("Deep primary carries re-entry scope")
            if set(expectation["required_reuse_activity_ids"]) - _activity_ids(request.context):
                raise ValueError("reuse target absent from context")
            transaction = await build_transaction(case)
            encoded = transaction["user_prompt"] + json.dumps(
                transaction["response_schema"], sort_keys=True
            )
            for forbidden in ("fast_plan_resolution", "runtime_validator_feedback"):
                if forbidden in encoded:
                    raise ValueError(f"Deep prompt leaks {forbidden}")
            if "target" in transaction or "reference_region" in transaction:
                raise ValueError("target leaked into candidate packet")
            for capability_id in expectation["required_capability_ids"]:
                if capability_id not in encoded:
                    raise ValueError(
                        f"required Capability absent from transaction: {capability_id}"
                    )
            counts[f"language:{language}"] += 1
            counts[f"variant:{variant}"] += 1
            counts[f"capacity:{capacity}"] += 1
            counts[f"condition:{condition}"] += 1
        except Exception as exc:
            errors.append(f"{case_id}: {type(exc).__name__}: {exc}")
    for key, members in contrast.items():
        if members != {"supported-en", "supported-zh", "boundary-en", "boundary-zh"}:
            errors.append(f"{key}: incomplete contrast {sorted(members)}")
    if errors:
        raise ValueError("Deep Planner corpus validation failed:\n" + "\n".join(errors[:100]))
    manifest = json.loads(MANIFEST_PATH.read_text())
    summary = {
        "scenario_count": len(cases),
        "contrast_set_count": len(contrast),
        "languages": {
            k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("language:")
        },
        "runtime_variants": {
            k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("variant:")
        },
        "capacities": {
            k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("capacity:")
        },
        "conditions": {
            k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("condition:")
        },
        "scenario_tree_sha256": scenario_tree_digest(),
    }
    if (
        summary["scenario_count"] != manifest["coverage_contract"]["scenario_count"]
        or summary["scenario_tree_sha256"] != manifest["asset_contract"]["scenario_tree_sha256"]
    ):
        raise ValueError("Deep manifest asset/count drift")
    return summary


async def prepare(output_dir: Path, label: str, only_cases: list[str]) -> dict[str, Any]:
    await validate_dataset()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True)
    (output_dir / "packets").mkdir()
    (output_dir / "schemas").mkdir()
    envelope_schema = {
        "type": "object",
        "properties": {"model_output_text": {"type": "string"}},
        "required": ["model_output_text"],
        "additionalProperties": False,
    }
    (output_dir / "codex-envelope-schema.json").write_text(
        json.dumps(envelope_schema, indent=2, sort_keys=True) + "\n"
    )
    cases = load_cases()
    selected = set(only_cases)
    if selected:
        unknown = selected - {c["id"] for c in cases}
        if unknown:
            raise ValueError("unknown --only-case IDs: " + ",".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in selected]
    index = []
    identities = {}
    paths = {p.stem: p for p in scenario_paths()}
    for position, case in enumerate(cases, 1):
        transaction = await build_transaction(case)
        ref = case_ref(case["id"])
        sha = transaction["prompt_identity"]["schema_sha256"]
        schema_path = output_dir / "schemas" / f"{sha}.json"
        if not schema_path.exists():
            schema_path.write_text(
                json.dumps(
                    transaction["response_schema"], ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n"
            )
        packet = {
            "schema_version": 1,
            "case_ref": ref,
            "system_prompt": transaction["system_prompt"],
            "user_prompt": transaction["user_prompt"],
            "response_schema_path": schema_path.relative_to(output_dir).as_posix(),
            "production_prompt_family": transaction["production_prompt_family"],
            "production_options": transaction["options"],
            "prompt_identity": transaction["prompt_identity"],
            "target_blind": True,
        }
        packet_path = output_dir / "packets" / f"{ref}.json"
        packet_path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        index.append(
            {
                "position": position,
                "case_ref": ref,
                "scenario_id": case["id"],
                "scenario_path": paths[case["id"]].relative_to(ROOT).as_posix(),
                "packet_path": packet_path.relative_to(output_dir).as_posix(),
            }
        )
        identities[ref] = transaction["prompt_identity"]
    identity = {
        "schema_version": 1,
        "label": label,
        "issue": "https://github.com/TimeTreker/chromie/issues/35",
        "dataset_id": DATASET_ID,
        "scenario_count": len(cases),
        "selected_scenario_ids": [c["id"] for c in cases],
        "scenario_tree_sha256": scenario_tree_digest(),
        "source": source_identity(),
        "harness": {
            "files": harness_identity(),
            "python": sys.version,
            "codex_cli": subprocess.run(
                ["codex", "--version"], check=True, capture_output=True, text=True
            ).stdout.strip(),
        },
        "inference": {
            "authority": "Codex CLI same-model offline surrogate",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "candidate_calls_per_scenario": 1,
            "retry_policy": "none",
            "same_model_non_independent": True,
        },
        "prompt_identity_index_sha256": _sha256(_json_bytes(identities)),
        "candidate_packet_policy": "Deep system/user/schema only; Fast candidate, target, rubric, and expected result excluded",
    }
    (output_dir / "packet-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "batch-identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return identity


def candidate_prompt(packet: dict[str, Any], schema: dict[str, Any]) -> str:
    return (
        "Execute this one Deep Planner semantic transaction. Do not inspect files, run tools, discuss the task, or add benchmark commentary. Treat SYSTEM PROMPT as the role instruction and USER PROMPT as the complete authoritative transaction.\n\nSYSTEM PROMPT\n"
        + packet["system_prompt"]
        + "\n\nUSER PROMPT\n"
        + packet["user_prompt"]
        + "\n\nDYNAMIC PRODUCTION RESPONSE SCHEMA\n"
        + json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n\nReturn one transport envelope with exactly model_output_text. That string contains only the raw JSON object required by the Schema."
    )


async def run_one(
    output_dir: Path, item: dict[str, Any], semaphore: asyncio.Semaphore, timeout_s: float
) -> dict[str, Any]:
    async with semaphore:
        packet = json.loads((output_dir / item["packet_path"]).read_text())
        schema = json.loads((output_dir / packet["response_schema_path"]).read_text())
        ref = item["case_ref"]
        for name in ("raw-outputs", "call-logs", "call-executions", "codex-envelopes"):
            (output_dir / name).mkdir(exist_ok=True)
        envelope = output_dir / "codex-envelopes" / f"{ref}.json"
        raw_path = output_dir / "raw-outputs" / f"{ref}.txt"
        log = output_dir / "call-logs" / f"{ref}.log"
        execution = output_dir / "call-executions" / f"{ref}.json"
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
            str(output_dir / "codex-empty-workdir"),
            "-m",
            "gpt-5.6-sol",
            "-c",
            'model_reasoning_effort="high"',
            "-o",
            str(envelope),
            "--output-schema",
            str(output_dir / "codex-envelope-schema.json"),
            "-",
        ]
        (output_dir / "codex-empty-workdir").mkdir(exist_ok=True)
        started = time.time()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(candidate_prompt(packet, schema).encode()), timeout=timeout_s
            )
            timed_out = False
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            timed_out = True
        ended = time.time()
        log.write_bytes(b"STDOUT\n" + stdout + b"\nSTDERR\n" + stderr)
        envelope_error = ""
        if envelope.exists():
            try:
                value = json.loads(envelope.read_text())["model_output_text"]
                if not isinstance(value, str):
                    raise TypeError("model_output_text is not a string")
                raw_path.write_text(value)
            except Exception as exc:
                envelope_error = f"{type(exc).__name__}: {exc}"
        result = {
            "schema_version": 1,
            "case_ref": ref,
            "attempt_count": 1,
            "hidden_retry": False,
            "started_epoch_s": started,
            "ended_epoch_s": ended,
            "latency_s": ended - started,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "output_present": raw_path.exists(),
            "output_sha256": _sha256(raw_path.read_bytes()) if raw_path.exists() else "",
            "codex_envelope_present": envelope.exists(),
            "codex_envelope_error": envelope_error,
            "log_sha256": _sha256(log.read_bytes()),
        }
        execution.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result


async def run(output_dir: Path, concurrency: int, timeout_s: float) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text())
    index = json.loads((output_dir / "packet-index.json").read_text())
    if (
        source_identity() != identity["source"]
        or harness_identity() != identity["harness"]["files"]
    ):
        raise ValueError("source/harness changed after freeze")
    semaphore = asyncio.Semaphore(max(1, concurrency))
    completed = 0
    results = []

    async def tracked(item: dict[str, Any]) -> None:
        nonlocal completed
        results.append(await run_one(output_dir, item, semaphore, timeout_s))
        completed += 1
        if completed % 10 == 0 or completed == len(index):
            print(f"deep-planner qualification progress {completed}/{len(index)}", flush=True)

    await asyncio.gather(*(tracked(item) for item in index))
    after_source = source_identity()
    after_harness = harness_identity()
    stable = after_source == identity["source"] and after_harness == identity["harness"]["files"]
    result = {
        "schema_version": 1,
        "source_before": identity["source"],
        "source_after": after_source,
        "harness_before": identity["harness"]["files"],
        "harness_after": after_harness,
        "stable": stable,
        "completed_calls": len(results),
        "successful_processes": sum(
            1 for x in results if x["exit_code"] == 0 and not x["timed_out"]
        ),
        "timeouts": sum(1 for x in results if x["timed_out"]),
    }
    (output_dir / "source-stability.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    if not stable:
        raise ValueError("source changed during Deep batch")
    return result


async def adjudicate_one(
    case: dict[str, Any], raw_text: str, schema: dict[str, Any]
) -> dict[str, Any]:
    request = CognitiveWorkRequest.model_validate(case["input"]["request"])
    replay = ReplayModel(raw_text)
    resolver = DeepPlannerResolver(replay, StaticCatalog(materialize_catalog(case["input"])))
    schema_errors = []
    raw_value = None
    try:
        raw_value = json.loads(raw_text)
        schema_errors = [
            error.message for error in Draft202012Validator(schema).iter_errors(raw_value)
        ][:20]
    except Exception as exc:
        schema_errors = [f"{type(exc).__name__}: {exc}"]
    previous = logging.getLogger("chromie.agent.deep_planner").level
    logging.getLogger("chromie.agent.deep_planner").setLevel(logging.CRITICAL)
    try:
        plan = await resolver.resolve(request)
        error = ""
    except Exception as exc:
        plan = None
        error = f"{type(exc).__name__}: {exc}"
    finally:
        logging.getLogger("chromie.agent.deep_planner").setLevel(previous)
    accepted = bool(
        plan is not None
        and plan.goal_outcomes
        and not plan.metadata.get("failure_class")
        and not plan.metadata.get("error_type")
    )
    capability_ids = [s.capability_id for s in plan.steps] if plan else []
    reuse = [s.reuse_activity_id for s in plan.steps if s.reuse_activity_id] if plan else []
    purposes = [s.step_purpose for s in plan.steps] if plan else []
    expected = case["target"]["reference_region"]
    target_errors = _target_checks(
        expected,
        disposition=plan.disposition if plan else "",
        capability_ids=capability_ids,
        reuse_ids=reuse,
        scope_ids=list(plan.goal_ids) if plan else [],
        coverage=plan.coverage if plan else "",
        has_complete_response=bool(plan and plan.response_text.strip()),
        plan_relation=str(plan.metadata.get("plan_relation") or "") if plan else "",
        confirmation_required=plan.metadata.get("user_confirmation_required") if plan else None,
        time_condition_count=len(plan.time_conditions) if plan else 0,
    )
    for purpose in expected.get("required_step_purposes", []):
        if purpose not in purposes:
            target_errors.append(f"missing required step_purpose: {purpose}")
    normalizations = []
    if plan and plan.metadata.get("parameter_provenance_normalization"):
        normalizations.append("parameter_provenance_normalization")
    hard_pass = not schema_errors and accepted and replay.calls == 1 and not target_errors
    return {
        "schema_version": 1,
        "scenario_id": case["id"],
        "case_ref": case_ref(case["id"]),
        "runtime_variant": case["input"]["runtime_variant"],
        "language": case["input"]["language"],
        "category": case["category"],
        "split": case["split"],
        "transport": {"complete": bool(raw_text), "candidate_call_count": 1},
        "schema": {"accepted": not schema_errors, "errors": schema_errors},
        "host": {
            "accepted_primary_result": accepted,
            "error": error
            or (
                ""
                if accepted
                else str(
                    plan.metadata.get("reason") or plan.metadata.get("error") or "deep fallback"
                )
                if plan
                else "missing plan"
            ),
            "model_call_count": replay.calls,
            "normalization_fields": normalizations,
        },
        "observed": {
            "disposition": plan.disposition if plan else "",
            "coverage": plan.coverage if plan else "",
            "capability_ids": capability_ids,
            "reuse_activity_ids": reuse,
            "scope_ids": list(plan.goal_ids) if plan else [],
            "has_complete_response": bool(plan and plan.response_text.strip()),
            "plan_relation": str(plan.metadata.get("plan_relation") or "") if plan else "",
            "confirmation_required": plan.metadata.get("user_confirmation_required")
            if plan
            else None,
            "step_purposes": purposes,
        },
        "target_region": {"hard_errors": target_errors},
        "hard_pass": hard_pass,
        "semantic_review": {
            "status": "pending_same_model_posthoc_review",
            "semantic_facts": expected["semantic_facts"],
            "forbidden_claims": expected["forbidden_claims"],
        },
    }


async def adjudicate(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    identity = json.loads((output_dir / "batch-identity.json").read_text())
    stability = json.loads((output_dir / "source-stability.json").read_text())
    if (
        not stability["stable"]
        or stability["completed_calls"] != identity["scenario_count"]
        or stability["successful_processes"] != identity["scenario_count"]
        or stability["timeouts"]
    ):
        raise ValueError("incomplete Deep batch")
    if (
        source_identity() != identity["source"]
        or harness_identity() != identity["harness"]["files"]
    ):
        raise ValueError("source/harness changed before adjudication")
    cases = {c["id"]: c for c in load_cases()}
    index = json.loads((output_dir / "packet-index.json").read_text())
    outdir = output_dir / "adjudication"
    outdir.mkdir()
    counts = Counter()
    by_variant = defaultdict(Counter)
    by_language = defaultdict(Counter)
    failures = []
    for item in index:
        case = cases[item["scenario_id"]]
        packet = json.loads((output_dir / item["packet_path"]).read_text())
        schema = json.loads((output_dir / packet["response_schema_path"]).read_text())
        raw_path = output_dir / "raw-outputs" / f"{item['case_ref']}.txt"
        result = await adjudicate_one(
            case, raw_path.read_text() if raw_path.exists() else "", schema
        )
        (outdir / f"{item['case_ref']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        verdict = "pass" if result["hard_pass"] else "fail"
        counts[verdict] += 1
        counts["schema_accepted"] += int(result["schema"]["accepted"])
        counts["host_accepted"] += int(result["host"]["accepted_primary_result"])
        by_variant[result["runtime_variant"]][verdict] += 1
        by_language[result["language"]][verdict] += 1
        if verdict == "fail":
            failures.append(
                {
                    "scenario_id": result["scenario_id"],
                    "schema_errors": result["schema"]["errors"],
                    "host_error": result["host"]["error"],
                    "target_errors": result["target_region"]["hard_errors"],
                }
            )
    summary = {
        "schema_version": 1,
        "batch_label": identity["label"],
        "scenario_count": identity["scenario_count"],
        "source_stable": True,
        "hard_verdicts": dict(counts),
        "by_runtime_variant": {k: dict(v) for k, v in sorted(by_variant.items())},
        "by_language": {k: dict(v) for k, v in sorted(by_language.items())},
        "failure_examples": failures,
        "semantic_review_status": "pending_same_model_posthoc_review",
        "evidence_ceiling": "Same-model offline Codex surrogate over exact Deep prompt/Schema/DTO/Host validation; not deployed Ollama, independent review, voice, simulator, hardware, training, or release evidence.",
    }
    (output_dir / "adjudication-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--label", required=True)
    prep.add_argument("--only-case", action="append", default=[])
    runner = sub.add_parser("run")
    runner.add_argument("--output-dir", type=Path, required=True)
    runner.add_argument("--concurrency", type=int, default=8)
    runner.add_argument("--timeout-s", type=float, default=600)
    adj = sub.add_parser("adjudicate")
    adj.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        result = asyncio.run(validate_dataset())
    elif args.command == "prepare":
        result = asyncio.run(prepare(args.output_dir, args.label, args.only_case))
    elif args.command == "run":
        result = asyncio.run(run(args.output_dir, args.concurrency, args.timeout_s))
    else:
        result = asyncio.run(adjudicate(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
