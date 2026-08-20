#!/usr/bin/env python3
"""Run one normalized daily-conversation scenario through the safe live text path."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.interaction_text_mujoco_check import (  # noqa: E402
    build_parser as build_live_parser,
    run_check,
    run_check_sequence,
)


ARTIFACT_ROOT_ENV = "CHROMIE_DAILY_BENCHMARK_ARTIFACT_ROOT"
QUALITY_HEALTH_FIELDS = (
    "model",
    "deep_planner_model",
    "goal_association_model",
)
FAST_HEALTH_FIELDS = (
    "fast_planner_model",
    "social_attention_model",
)


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-.") or "scenario"


def _turns(inputs: Mapping[str, Any]) -> list[str]:
    text = inputs.get("text")
    turns = inputs.get("turns")
    if isinstance(text, str) and text.strip() and turns is None:
        return [text.strip()]
    if (
        isinstance(turns, list)
        and turns
        and all(isinstance(item, str) and item.strip() for item in turns)
        and text is None
    ):
        return [item.strip() for item in turns]
    raise ValueError("scenario inputs must contain either non-empty text or non-empty turns")


def _live_args(
    *,
    text: str,
    language: str | None,
    conversation_id: str,
    evidence_dir: Path,
) -> argparse.Namespace:
    argv = [
        text,
        "--no-speaker",
        "--preview-only",
        "--reject-internal-speech",
        "--conversation-id",
        conversation_id,
        "--evidence-dir",
        str(evidence_dir),
        "--timeout-s",
        "300",
    ]
    if language:
        argv.extend(("--language", language))
    return build_live_parser().parse_args(argv)


def _speech(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = summary.get("interaction_response")
    if not isinstance(response, Mapping):
        return []
    value = response.get("speech")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _agent_health(summary: Mapping[str, Any]) -> dict[str, Any]:
    evidence_dir = summary.get("evidence_dir")
    if not isinstance(evidence_dir, str):
        return {}
    path = Path(evidence_dir) / "agent_health.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _semantic_turn_record(summary: Mapping[str, Any]) -> dict[str, Any]:
    cognitive = summary.get("cognitive_runtime")
    if not isinstance(cognitive, Mapping):
        cognitive = {}
    response = summary.get("interaction_response")
    if not isinstance(response, Mapping):
        response = {}
    capabilities = response.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
    return {
        "input": summary.get("text"),
        "ok": summary.get("ok"),
        "speech": [item.get("text", "") for item in _speech(summary)],
        "goal_association": cognitive.get("goal_association"),
        "planner_metadata": cognitive.get("metadata"),
        "proposed_skills": [
            {
                "capability_id": item.get("capability_id"),
                "args": item.get("args"),
                "timing": item.get("timing"),
                "metadata": item.get("metadata"),
            }
            for item in capabilities
            if isinstance(item, Mapping)
        ],
        "errors": summary.get("errors", []),
    }


def _structural_invariants(
    required: Sequence[str], summaries: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    typed_ok = bool(summaries) and all(
        item.get("ok") is True and isinstance(item.get("interaction_response"), Mapping)
        for item in summaries
    )
    primary_act_ok = all(
        len(
            [
                item
                for item in _speech(summary)
                if item.get("metadata", {}).get("delivery_role") == "response"
            ]
        )
        <= 1
        for summary in summaries
    )
    runtime_identity_ok = all(
        summary.get("provenance", {}).get("runtime_identity", {}).get("complete") is True
        for summary in summaries
    )
    host_control_ok = all(summary.get("preview_only") is True for summary in summaries)
    known: dict[str, tuple[bool | None, str]] = {
        "typed_output_and_schema_boundaries_remain_valid": (
            typed_ok,
            "Live harness and typed InteractionResponse validation completed for every turn.",
        ),
        "one_primary_user_facing_act_per_turn": (
            primary_act_ok,
            "At most one response-role speech act was emitted per turn; semantic relevance remains for review.",
        ),
        "speech_claims_match_available_commitment_and_evidence": (
            None if typed_ok else False,
            "Typed claim/commitment fields passed the live boundary; spoken semantic truth remains for LLM review.",
        ),
        "chromie_identity_and_robotic_body_truth_remain_consistent": (
            None if runtime_identity_ok else False,
            "Runtime identity provenance was retained; response-level identity consistency remains for LLM review.",
        ),
        "deterministic_stop_cancel_emergency_and_silence_controls_remain_host_owned": (
            host_control_ok,
            "Scenario used the Host-owned text harness in preview-only mode; no effect execution was permitted.",
        ),
    }
    return {
        name: {
            "passed": known.get(name, (False, "Live adapter does not implement this invariant."))[
                0
            ],
            "detail": known.get(name, (False, "Live adapter does not implement this invariant."))[
                1
            ],
        }
        for name in required
    }


def _observation(
    request: Mapping[str, Any], summaries: Sequence[Mapping[str, Any]], case_dir: Path
) -> dict[str, Any]:
    scenario = request["scenario"]
    run_profile = request["run"]
    expected_model = run_profile.get("model")
    health = _agent_health(summaries[-1]) if summaries else {}
    quality_models = {name: health.get(name) for name in QUALITY_HEALTH_FIELDS}
    fast_models = {name: health.get(name) for name in FAST_HEALTH_FIELDS}
    quality_model_match = bool(expected_model) and all(
        value == expected_model for value in quality_models.values()
    )
    fast_model_match = all(value == "qwen3:4b" for value in fast_models.values())
    delivered_turns = [[item.get("text", "") for item in _speech(summary)] for summary in summaries]
    latency_ms = sum(
        float(summary.get("timings_ms", {}).get("total_ms") or 0.0) for summary in summaries
    )
    required = scenario.get("expectations", {}).get("invariants", [])
    runtime_ok = bool(summaries) and len(summaries) == len(_turns(scenario["inputs"]))
    runtime_ok = runtime_ok and all(summary.get("ok") is True for summary in summaries)
    model_topology_ok = quality_model_match and fast_model_match

    return {
        "scenario_id": scenario["id"],
        "primary_task_passed": False if not runtime_ok or not model_topology_ok else None,
        "primary_outcome": {
            "delivered_speech_by_turn": delivered_turns,
            "semantic_turn_records": [_semantic_turn_record(summary) for summary in summaries],
            "quality_model_health": quality_models,
            "fixed_fast_model_health": fast_models,
            "semantic_verdict": "pending_llm_review",
        },
        "auxiliary_behavior": {
            "preview_only": True,
            "speaker": False,
            "effect_execution": "disabled",
        },
        "behaviors": [],
        "evidence": [
            {
                "kind": "delivered_text",
                "turns": delivered_turns,
            },
            {
                "kind": "model_topology",
                "expected_quality_model": expected_model,
                "quality_model_match": quality_model_match,
                "fixed_fast_model": "qwen3:4b",
                "fixed_fast_model_match": fast_model_match,
            },
            {
                "kind": "live_runtime",
                "turns_requested": len(_turns(scenario["inputs"])),
                "turns_completed": len(summaries),
                "all_turns_ok": runtime_ok,
                "preview_only": True,
            },
        ],
        "invariant_results": _structural_invariants(required, summaries),
        "latency_ms": latency_ms,
        "artifacts": [str(case_dir)],
    }


async def _execute(request: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    scenario = request.get("scenario")
    if request.get("schema_version") != 1 or not isinstance(scenario, Mapping):
        raise ValueError("adapter request must use schema_version 1 and contain scenario")
    run_profile = request.get("run")
    if not isinstance(run_profile, Mapping):
        raise ValueError("adapter request must contain run profile")
    inputs = scenario.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("scenario inputs must be an object")
    texts = _turns(inputs)
    language = inputs.get("language")
    if language is not None and not isinstance(language, str):
        raise ValueError("scenario language must be a string or null")

    scenario_id = str(scenario.get("id", "scenario"))
    case_dir = artifact_root / _safe_id(scenario_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    conversation_id = f"daily-benchmark-{_safe_id(scenario_id)}"
    args = [
        _live_args(
            text=text,
            language=language,
            conversation_id=conversation_id,
            evidence_dir=(case_dir if len(texts) == 1 else case_dir / f"turn-{index:02d}"),
        )
        for index, text in enumerate(texts, start=1)
    ]
    with redirect_stdout(sys.stderr):
        if len(args) == 1:
            summaries = [await run_check(args[0])]
        else:
            summaries = await run_check_sequence(args, evidence_dir=case_dir)
    return _observation(request, summaries, case_dir)


def main() -> int:
    artifact_root_value = os.getenv(ARTIFACT_ROOT_ENV, "").strip()
    if not artifact_root_value:
        print(f"{ARTIFACT_ROOT_ENV} must name the retained artifact root", file=sys.stderr)
        return 2
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, Mapping):
            raise ValueError("adapter request must be a JSON object")
        observation = asyncio.run(_execute(request, Path(artifact_root_value).resolve()))
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"daily conversation live adapter error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(observation, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
