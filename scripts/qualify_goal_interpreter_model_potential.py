#!/usr/bin/env python3
"""Screen raw model potential for Chromie's Goal Interpretation authority.

This probe deliberately does not call the production Goal Interpreter prompt,
DTO normalizer, or Host validator.  It keeps the semantic oracle and native
Ollama structured decoding, but uses a smaller model-neutral wire contract so
model selection can be separated from production-contract compatibility.
Passing this probe does not qualify a model for the deployed GI workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qualify_vllm_provider import (  # noqa: E402
    DEFAULT_GOAL_INTERPRETER_MANIFEST,
    QualificationFailure,
    _evaluate_goal_interpreter_case_dimensions,
    _git_dirty,
    _git_revision,
    _load_goal_interpreter_manifest,
    _write_json,
)

DEFAULT_OUTPUT_ROOT = (
    ROOT / ".chromie" / "acceptance" / "model-qualification" / "gi-model-potential"
)
PROMPT_CONTRACT_ID = "chromie.gi_model_potential.v2"

DIMENSION_NAMES = (
    "decomposition",
    "outcome",
    "output_mode",
    "bindings",
    "coordination",
    "unresolved",
)

OUTPUT_MODES = [
    "unspecified",
    "speech",
    "styled_speech",
    "recitation",
    "singing",
    "humming",
    "nonverbal_vocalization",
    "body_action",
    "media_playback",
    "information",
    "stateful_effect",
    "other",
]

BINDING_DIMENSIONS = [
    "actor",
    "addressee",
    "experiencer",
    "entity",
    "item",
    "proposition",
    "preference",
    "attribute",
    "time",
    "time_scope",
    "duration",
    "speed",
    "quantity",
    "count",
    "distance",
    "direction",
    "location",
    "severity",
    "intensity",
    "magnitude",
    "threshold",
    "subtype",
    "polarity",
    "comparison",
    "recipient",
]

SYSTEM_PROMPT = """You are evaluating only WHAT a person asks Chromie to achieve.
Return one complete JSON object matching the supplied schema. Do not plan execution,
select tools, capabilities, providers, APIs, or response wording.

Rules:
1. Emit one Responsibility for each independently satisfiable requested positive effect,
   in source order. Coordinated body, vocal, information, and state effects stay separate.
2. One predicate with modifiers remains one Responsibility. Put every explicit modifier
   in that Responsibility's bindings; never turn duration, count, direction, distance,
   speed, location, time scope, or threshold into another Responsibility.
3. Each binding uses exactly one semantic dimension. Calendar or relative periods use
   time_scope; elapsed lengths use duration; cutoffs use threshold; people and objects
   use entity or recipient, never location. Use JSON numbers for explicit numeric values
   when possible, otherwise preserve an exact source-language expression. Preserve entity,
   location, and relative time_scope surfaces in the source language; never invent a date
   for a relative expression when no reference date is supplied. A qualitative adjective
   without an elapsed-time unit is not duration.
4. The outcome must name the actual requested predicate or proposition. Never write only
   'perform an action', 'provide information', or another generic category. A question
   about whether P is true preserves P as the proposition to determine.
5. output_mode meanings are strict: body_action means locomotion, posture, gaze, gesture,
   manipulation, carrying, or handover; singing means Chromie performs a song; speech means
   an immediate conversational utterance; information means determining or supplying facts;
   stateful_effect means a durable or future change outside the body, never a physical action.
6. Use coordination only for explicit sequence or parallel relations. It references the
   zero-based Responsibility indexes in source order.
7. unresolved contains only genuine ambiguity about WHAT, scope, or a referent. Use [] when
   the requested meaning is clear. Missing
   tools, units, providers, or execution details are not semantic uncertainty.
8. Preserve an unfamiliar proper-name-like source surface verbatim as entity and report
   uncertainty about what it refers to; never guess that it means weather, a place, a tool,
   or another familiar category.
9. Do not add acknowledgements for fillers, politeness, thanks, or question punctuation.
"""


def _response_schema() -> dict[str, Any]:
    scalar = {
        "anyOf": [
            {"type": "string", "minLength": 1},
            {"type": "number"},
            {"type": "boolean"},
        ]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["responsibilities", "coordination", "unresolved"],
        "properties": {
            "responsibilities": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["outcome", "output_mode", "bindings"],
                    "properties": {
                        "outcome": {"type": "string", "minLength": 1},
                        "output_mode": {
                            "type": "string",
                            "enum": OUTPUT_MODES,
                            "description": (
                                "WHAT modality only. body_action covers all physical "
                                "locomotion, posture, gaze, gesture, manipulation, and "
                                "handover; stateful_effect excludes physical actions."
                            ),
                        },
                        "bindings": {
                            "type": "array",
                            "maxItems": len(BINDING_DIMENSIONS),
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["dimension", "value"],
                                "properties": {
                                    "dimension": {
                                        "type": "string",
                                        "enum": BINDING_DIMENSIONS,
                                        "description": (
                                            "Use entity for a person, object, service, or "
                                            "unknown name; recipient for a receiver; "
                                            "location for a place; time_scope for a calendar "
                                            "or relative period; duration for elapsed time; "
                                            "count for repetitions; direction for path or "
                                            "orientation; threshold for a comparison cutoff."
                                        ),
                                    },
                                    "value": scalar,
                                },
                            },
                        },
                    },
                },
            },
            "coordination": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "responsibility_indexes"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["parallel", "sequence"]},
                        "responsibility_indexes": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 12,
                            "items": {"type": "integer", "minimum": 0, "maximum": 11},
                        },
                    },
                },
            },
            "unresolved": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string", "minLength": 1},
                "description": (
                    "Only genuine ambiguity about WHAT, scope, or a referent; [] when "
                    "the requested meaning is clear."
                ),
            },
        },
    }


def _user_prompt(case: dict[str, Any]) -> str:
    return "Interpret only the following immutable user turn.\n" + json.dumps(
        {
            "text": case["text"],
            "language_hint": case.get("language") or "auto",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _project_candidate_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_responsibilities = payload.get("responsibilities")
    if not isinstance(raw_responsibilities, list) or not raw_responsibilities:
        raise QualificationFailure("candidate responsibilities must be a non-empty array")

    decision_responsibilities: list[dict[str, Any]] = []
    wire_responsibilities: list[dict[str, Any]] = []
    for index, item in enumerate(raw_responsibilities):
        if not isinstance(item, dict):
            raise QualificationFailure(f"candidate responsibility {index} is not an object")
        raw_bindings = item.get("bindings")
        if not isinstance(raw_bindings, list):
            raise QualificationFailure(
                f"candidate responsibility {index} bindings are not an array"
            )
        binding_items: dict[str, Any] = {}
        for binding_index, binding in enumerate(raw_bindings):
            if not isinstance(binding, dict):
                raise QualificationFailure(
                    f"candidate responsibility {index} binding {binding_index} is not an object"
                )
            dimension = str(binding.get("dimension") or "").strip()
            if dimension not in BINDING_DIMENSIONS:
                raise QualificationFailure(
                    f"candidate responsibility {index} has unknown binding dimension {dimension!r}"
                )
            if dimension in binding_items:
                raise QualificationFailure(
                    f"candidate responsibility {index} duplicates binding dimension {dimension}"
                )
            if "value" not in binding:
                raise QualificationFailure(
                    f"candidate responsibility {index} binding {dimension} lacks value"
                )
            binding_items[dimension] = binding["value"]
        local_ref = f"r{index + 1}"
        decision_responsibilities.append(
            {
                "local_ref": local_ref,
                "outcome": item.get("outcome"),
                "output_mode": item.get("output_mode"),
            }
        )
        wire_responsibilities.append(
            {
                "local_ref": local_ref,
                "outcome": item.get("outcome"),
                "output_mode": item.get("output_mode"),
                "binding_items": binding_items,
            }
        )

    raw_coordination = payload.get("coordination")
    if not isinstance(raw_coordination, list):
        raise QualificationFailure("candidate coordination is not an array")
    coordination: list[dict[str, Any]] = []
    for relation_index, relation in enumerate(raw_coordination):
        if not isinstance(relation, dict):
            raise QualificationFailure(f"candidate coordination {relation_index} is not an object")
        indexes = relation.get("responsibility_indexes")
        if not isinstance(indexes, list) or any(
            not isinstance(value, int) or value < 0 or value >= len(wire_responsibilities)
            for value in indexes
        ):
            raise QualificationFailure(
                f"candidate coordination {relation_index} has invalid indexes"
            )
        coordination.append(
            {
                "kind": relation.get("kind"),
                "refs": [wire_responsibilities[value]["local_ref"] for value in indexes],
            }
        )

    unresolved = payload.get("unresolved")
    if not isinstance(unresolved, list):
        raise QualificationFailure("candidate unresolved is not an array")
    decision = {
        "responsibilities": decision_responsibilities,
        "unresolved": unresolved,
    }
    wire = {
        "responsibilities": wire_responsibilities,
        "coordination": coordination,
    }
    return decision, wire


async def _model_identity(client: httpx.AsyncClient, model: str) -> dict[str, Any]:
    response = await client.get("/api/tags")
    response.raise_for_status()
    models = response.json().get("models") or []
    for item in models:
        if isinstance(item, dict) and item.get("name") == model:
            return {
                "name": model,
                "digest": item.get("digest"),
                "size_bytes": item.get("size"),
                "modified_at": item.get("modified_at"),
                "details": item.get("details"),
            }
    raise QualificationFailure(f"model {model!r} is not installed in Ollama")


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_goal_interpreter_manifest(args.manifest)
    timeout = httpx.Timeout(None)
    async with httpx.AsyncClient(base_url=args.ollama_url, timeout=timeout) as client:
        identity = await _model_identity(client, args.model)
        results: list[dict[str, Any]] = []
        started_at = datetime.now(timezone.utc).isoformat()
        for repeat_index in range(args.repeats):
            for case in manifest["cases"]:
                started = time.perf_counter()
                item: dict[str, Any] = {
                    "id": case["id"],
                    "group": case["group"],
                    "repeat_index": repeat_index,
                    "status": "fail",
                    "dimension_status": {name: "unproven" for name in DIMENSION_NAMES},
                }
                raw_content = ""
                try:
                    response = await client.post(
                        "/api/chat",
                        json={
                            "model": args.model,
                            "stream": False,
                            "think": False,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": _user_prompt(case)},
                            ],
                            "format": _response_schema(),
                            "options": {
                                "temperature": args.temperature,
                                "top_p": args.top_p,
                                "num_ctx": args.num_ctx,
                                "num_predict": args.num_predict,
                            },
                            "keep_alive": args.keep_alive,
                        },
                    )
                    response.raise_for_status()
                    provider_payload = response.json()
                    raw_content = str((provider_payload.get("message") or {}).get("content") or "")
                    if (provider_payload.get("message") or {}).get("thinking"):
                        raise QualificationFailure("reasoning channel exposed")
                    if provider_payload.get("done_reason") not in (None, "stop"):
                        raise QualificationFailure(
                            "generation did not stop cleanly: "
                            + str(provider_payload.get("done_reason"))
                        )
                    candidate = json.loads(raw_content)
                    if not isinstance(candidate, dict):
                        raise QualificationFailure("candidate response is not a JSON object")
                    decision, wire = _project_candidate_payload(candidate)
                    dimension_findings = _evaluate_goal_interpreter_case_dimensions(
                        case, decision, wire
                    )
                    item["dimension_status"] = {
                        name: (
                            "unproven" if findings is None else "pass" if not findings else "fail"
                        )
                        for name, findings in dimension_findings.items()
                    }
                    item["dimension_errors"] = {
                        name: findings for name, findings in dimension_findings.items() if findings
                    }
                    errors = [
                        error
                        for findings in dimension_findings.values()
                        if findings is not None
                        for error in findings
                    ]
                    if errors:
                        raise QualificationFailure("; ".join(errors))
                    item["status"] = "pass"
                    item["candidate"] = candidate
                    item["provider_metrics"] = {
                        key: provider_payload.get(key)
                        for key in (
                            "total_duration",
                            "load_duration",
                            "prompt_eval_count",
                            "prompt_eval_duration",
                            "eval_count",
                            "eval_duration",
                            "done_reason",
                        )
                    }
                except Exception as exc:
                    item["error"] = {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                    item["raw_content"] = raw_content
                item["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
                results.append(item)
                print(
                    f"{item['status'].upper()} repeat={repeat_index} "
                    f"case={case['id']} elapsed_ms={item['elapsed_ms']:.0f}",
                    flush=True,
                )

    failures = [item for item in results if item["status"] != "pass"]
    dimension_summary = {
        name: {
            status: sum(1 for item in results if item["dimension_status"][name] == status)
            for status in ("pass", "fail", "unproven")
        }
        for name in DIMENSION_NAMES
    }
    return {
        "schema_version": 1,
        "evidence_class": "isolated_goal_interpreter_model_potential",
        "claim_boundary": (
            "Model potential under a simplified GI semantic contract; excludes the "
            "production GI prompt, DTO normalizer, Host validator, GA, Planner, TTS, "
            "simulator, target, and robot evidence."
        ),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git_revision(),
        "git_dirty": _git_dirty(),
        "provider": "ollama_native_chat",
        "provider_url": args.ollama_url,
        "model_identity": identity,
        "settings": {
            "think": False,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "num_ctx": args.num_ctx,
            "num_predict": args.num_predict,
            "keep_alive": args.keep_alive,
        },
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "response_schema_sha256": hashlib.sha256(
            json.dumps(
                _response_schema(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "qualification_id": manifest["qualification_id"],
        "manifest_path": manifest["manifest_path"],
        "manifest_sha256": manifest["manifest_sha256"],
        "repeats": args.repeats,
        "status": "pass" if not failures else "fail",
        "trial_count": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "dimension_summary": dimension_summary,
        "cases": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_GOAL_INTERPRETER_MANIFEST)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--num-predict", type=int, default=1024)
    parser.add_argument("--keep-alive", default="24h")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    output = args.output
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_model = args.model.replace(":", "-").replace("/", "-")
        output = DEFAULT_OUTPUT_ROOT / f"{safe_model}-{stamp}.json"
    evidence = asyncio.run(_run(args))
    _write_json(output, evidence)
    print(
        json.dumps(
            {
                "output": str(output),
                "status": evidence["status"],
                "passed": evidence["passed"],
                "failed": evidence["failed"],
                "trial_count": evidence["trial_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
