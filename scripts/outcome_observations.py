from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BEHAVIOR_MAP = ROOT / "scenarios" / "observable_behaviors.json"

_HARD_LLM_FAILURE_CLASSES = {
    "deadline_exceeded",
    "input_truncated",
    "llm_input_truncated",
    "llm_output_truncated",
    "llm_prompt_truncated",
    "output_truncated",
    "prompt_truncated",
    "request_timeout",
    "stream_incomplete",
    "structured_output_incomplete",
    "timeout",
}
_HARD_LLM_EVENTS = {
    "llm_input_truncated",
    "llm_output_truncated",
    "llm_prompt_truncated",
    "llm_stream_incomplete",
}


@lru_cache(maxsize=4)
def load_behavior_map(path: str | Path = DEFAULT_BEHAVIOR_MAP) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported observable behavior map schema")
    behaviors = payload.get("behaviors")
    if not isinstance(behaviors, dict):
        raise ValueError("observable behavior map requires behaviors object")
    return {
        str(skill_id): dict(value)
        for skill_id, value in behaviors.items()
        if isinstance(value, dict)
    }


def observation_type_for_skill(
    skill_id: str,
    behavior_map: dict[str, dict[str, Any]] | None = None,
) -> str:
    behavior_map = behavior_map or load_behavior_map()
    definition = behavior_map.get(str(skill_id or ""), {})
    return str(definition.get("type") or f"capability.{skill_id}")


def collect_observations(
    summary: dict[str, Any],
    *,
    behavior_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize user-observable speech and embodied effects.

    The map translates runtime capability receipts into stable behavior types.
    It is a test oracle only; production planning never reads it.
    """

    behavior_map = behavior_map or load_behavior_map()
    response = summary.get("interaction_response")
    if not isinstance(response, dict):
        response = {}
    execution = summary.get("execution")
    if not isinstance(execution, dict):
        execution = {}
    execution_results = [
        item
        for item in execution.get("results") or []
        if isinstance(item, dict) and item.get("request_id")
    ]
    execution_by_request = {
        str(item.get("request_id") or ""): item for item in execution_results
    }
    execution_order = {
        str(item.get("request_id") or ""): index
        for index, item in enumerate(execution_results)
    }
    fallback_order = len(execution_order)

    observations: list[dict[str, Any]] = []
    for planned_sequence, skill in enumerate(response.get("skills") or []):
        if not isinstance(skill, dict):
            continue
        skill_id = str(skill.get("skill_id") or "")
        if not skill_id.startswith("soridormi."):
            continue
        definition = behavior_map.get(skill_id, {})
        metadata = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
        args = skill.get("args") if isinstance(skill.get("args"), dict) else {}
        arg_fields = definition.get("arg_fields")
        if not isinstance(arg_fields, list):
            arg_fields = list(args)
        observed_args = {key: args[key] for key in arg_fields if key in args}
        receipt = execution_by_request.get(str(skill.get("request_id") or ""))
        status = str((receipt or {}).get("status") or "planned")
        role = (
            "auxiliary_expression"
            if metadata.get("auxiliary_social_attention") is True
            else "explicit_user_goal"
            if metadata.get("source_goal_ids")
            else "task_execution"
        )
        request_id = str(skill.get("request_id") or "")
        observations.append(
            {
                "sequence": execution_order.get(
                    request_id,
                    fallback_order + planned_sequence,
                ),
                "type": str(definition.get("type") or f"capability.{skill_id}"),
                "domain": str(definition.get("domain") or "capability"),
                "status": status,
                "interaction_role": role,
                "capability_id": skill_id,
                "args": observed_args,
                "request_id": skill.get("request_id"),
                "planned_sequence": planned_sequence,
            }
        )

    skill_count = len(response.get("skills") or [])
    for planned_sequence, speech in enumerate(response.get("speech") or []):
        if not isinstance(speech, dict):
            continue
        text = str(speech.get("text") or "").strip()
        if not text:
            continue
        metadata = speech.get("metadata") if isinstance(speech.get("metadata"), dict) else {}
        speech_id = str(speech.get("id") or "")
        observations.append(
            {
                "sequence": execution_order.get(
                    speech_id,
                    fallback_order + skill_count + planned_sequence,
                ),
                "type": "speech.output",
                "domain": "speech",
                "status": "completed"
                if str(speech.get("id") or "") in execution_by_request
                or not execution_by_request
                else "planned",
                "interaction_role": "task_response",
                "text": text,
                "metadata": metadata,
                "planned_sequence": planned_sequence,
            }
        )

    cognitive = summary.get("cognitive_runtime")
    if not isinstance(cognitive, dict):
        cognitive = {}
    composition = cognitive.get("response_composition")
    if not isinstance(composition, dict):
        composition = {}
    coordinated = composition.get("composition")
    if not isinstance(coordinated, dict):
        coordinated = {}
    attention = coordinated.get("social_attention_plan")
    if not isinstance(attention, dict):
        attention = {}
    speech_expression = attention.get("speech_expression")
    if isinstance(speech_expression, dict) and speech_expression.get("mode") == "adapt":
        observations.append(
            {
                "sequence": max(
                    (int(item.get("sequence", -1)) for item in observations),
                    default=-1,
                ) + 1,
                "type": "social_attention.speech_expression",
                "domain": "social_attention",
                "status": "completed" if response.get("speech") else "planned",
                "interaction_role": "auxiliary_expression",
                "args": {
                    "purpose": attention.get("purpose"),
                    "style": speech_expression.get("style"),
                    "pacing": speech_expression.get("pacing"),
                },
            }
        )
    observations.sort(
        key=lambda item: (
            int(item.get("sequence", 0)),
            str(item.get("type") or ""),
        )
    )
    return observations


def collect_llm_integrity_violations(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Return hard failures for truncated, incomplete, or timed-out LLM calls."""

    violations: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(source: str, event: str, payload: dict[str, Any]) -> None:
        fingerprint = json.dumps(
            [source, event, payload.get("stage"), payload.get("failure_class"), payload.get("message")],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        violations.append({"source": source, "event": event, **payload})

    session = summary.get("session_state")
    if isinstance(session, dict):
        for item in session.get("workflow_events") or []:
            if not isinstance(item, dict):
                continue
            event = str(item.get("event") or "").strip()
            message = str(item.get("message") or "")
            lowered = message.casefold()
            if event in _HARD_LLM_EVENTS or any(
                token in lowered
                for token in (
                    "done_reason=length",
                    "finish_reason=length",
                    "num_predict_exhausted",
                    "prompt_eval_count_reached_num_ctx",
                    "stream_incomplete",
                )
            ):
                add("session_state.workflow_events", event or "llm_integrity_failure", dict(item))

    def scan_metadata(source: str, value: Any) -> None:
        if isinstance(value, dict):
            failure_class = str(value.get("failure_class") or "").strip().casefold()
            event = str(value.get("event") or "").strip().casefold()
            if failure_class in _HARD_LLM_FAILURE_CLASSES or event in _HARD_LLM_EVENTS:
                add(source, event or failure_class, dict(value))
            for key, nested in value.items():
                if key in {"initial_raw_output", "repair_raw_output"}:
                    continue
                scan_metadata(f"{source}.{key}", nested)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                scan_metadata(f"{source}[{index}]", nested)

    for key in ("cognitive_runtime", "route", "interaction_response"):
        scan_metadata(key, summary.get(key))
    return violations


def observation_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key in ("type", "domain", "status", "interaction_role"):
        wanted = expected.get(key)
        if wanted not in {None, ""} and actual.get(key) != wanted:
            return False
    expected_args = expected.get("args")
    if isinstance(expected_args, dict):
        actual_args = actual.get("args") if isinstance(actual.get("args"), dict) else {}
        for key, wanted in expected_args.items():
            if actual_args.get(key) != wanted:
                return False
    arg_ranges = expected.get("arg_ranges")
    if isinstance(arg_ranges, dict):
        actual_args = actual.get("args") if isinstance(actual.get("args"), dict) else {}
        for key, bounds in arg_ranges.items():
            actual_value = actual_args.get(key)
            if not isinstance(actual_value, (int, float)) or isinstance(actual_value, bool):
                return False
            if not isinstance(bounds, dict):
                return False
            minimum = bounds.get("min")
            maximum = bounds.get("max")
            if minimum is not None and actual_value < float(minimum):
                return False
            if maximum is not None and actual_value > float(maximum):
                return False
    return True


def validate_expected_observations(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    sequence: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    for item in expected:
        matches = [observation for observation in actual if observation_matches(observation, item)]
        minimum = int(item.get("min_occurrences", 1))
        maximum = item.get("max_occurrences")
        label = item.get("type") or item.get("domain") or item
        if len(matches) < minimum:
            errors.append(
                f"missing expected observation {label!r}: required {minimum}, found {len(matches)}"
            )
        if maximum is not None and len(matches) > int(maximum):
            errors.append(
                f"too many observations {label!r}: maximum {maximum}, found {len(matches)}"
            )

    if sequence:
        actual_types = [str(item.get("type") or "") for item in actual]
        cursor = 0
        for wanted in sequence:
            try:
                cursor = actual_types.index(wanted, cursor) + 1
            except ValueError:
                errors.append(
                    "observation order mismatch: expected subsequence "
                    + " -> ".join(sequence)
                    + "; actual "
                    + " -> ".join(actual_types)
                )
                break
    return errors
