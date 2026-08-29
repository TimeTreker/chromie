from __future__ import annotations

import ast
import json
import re
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

_TTS_ORDER_RE = re.compile(r"\border=(\d+)\b")
_TTS_TEXT_RE = re.compile(r"\btext=(.+)$")


def _completed_tts_playback(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exact speech which the retained Host workflow says was played.

    Detached result re-entry can schedule speech after the initial interaction
    response has already been materialized.  The session workflow is the Host's
    delivery authority for that speech; reconstructing it here keeps the
    acceptance oracle from treating audible completion wording as absent.
    """

    session = summary.get("session_state")
    if not isinstance(session, dict):
        return []
    events = [
        item
        for item in session.get("workflow_events") or []
        if isinstance(item, dict)
    ]
    completed_orders: set[int] = set()
    for item in events:
        if item.get("event") != "playback_end":
            continue
        match = _TTS_ORDER_RE.search(str(item.get("message") or ""))
        if match:
            completed_orders.add(int(match.group(1)))

    delivered: list[dict[str, Any]] = []
    for event_index, item in enumerate(events):
        if item.get("event") != "tts_schedule":
            continue
        message = str(item.get("message") or "")
        order_match = _TTS_ORDER_RE.search(message)
        text_match = _TTS_TEXT_RE.search(message)
        if not order_match or not text_match:
            continue
        order = int(order_match.group(1))
        if order not in completed_orders:
            continue
        try:
            text = ast.literal_eval(text_match.group(1).strip())
        except (SyntaxError, ValueError):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        delivered.append(
            {
                "order": order,
                "event_index": event_index,
                "elapsed_ms": item.get("elapsed_ms"),
                "text": text.strip(),
            }
        )
    return delivered


@lru_cache(maxsize=4)
def load_behavior_map(path: str | Path = DEFAULT_BEHAVIOR_MAP) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported observable behavior map schema")
    behaviors = payload.get("behaviors")
    if not isinstance(behaviors, dict):
        raise ValueError("observable behavior map requires behaviors object")
    return {
        str(capability_id): dict(value)
        for capability_id, value in behaviors.items()
        if isinstance(value, dict)
    }


def observation_type_for_capability(
    capability_id: str,
    behavior_map: dict[str, dict[str, Any]] | None = None,
) -> str:
    behavior_map = behavior_map or load_behavior_map()
    definition = behavior_map.get(str(capability_id or ""), {})
    return str(definition.get("type") or f"capability.{capability_id}")


def collect_observations(
    summary: dict[str, Any],
    *,
    behavior_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize user-observable speech and completed Capability effects.

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
    timings = summary.get("timings_ms")
    timings = timings if isinstance(timings, dict) else {}
    try:
        capability_receipt_lower_bound_ms = float(timings.get("agent_ms"))
    except (TypeError, ValueError):
        capability_receipt_lower_bound_ms = None

    observations: list[dict[str, Any]] = []
    for planned_sequence, skill in enumerate(response.get("capabilities") or []):
        if not isinstance(skill, dict):
            continue
        capability_id = str(
            skill.get("capability_id") or ""
        )
        if not capability_id:
            continue
        definition = behavior_map.get(capability_id, {})
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
            if metadata.get("auxiliary_plan_activity") is True
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
                "type": str(definition.get("type") or f"capability.{capability_id}"),
                "domain": str(definition.get("domain") or "capability"),
                "status": status,
                "interaction_role": role,
                "capability_id": capability_id,
                "args": observed_args,
                "request_id": skill.get("request_id"),
                "planned_sequence": planned_sequence,
                **(
                    {
                        "_chronology_elapsed_ms": capability_receipt_lower_bound_ms
                        + execution_order.get(request_id, planned_sequence) * 0.001
                    }
                    if receipt is not None
                    and capability_receipt_lower_bound_ms is not None
                    else {}
                ),
            }
        )

    delivered_tts = _completed_tts_playback(summary)
    matched_delivery_indices: set[int] = set()
    capability_count = len(response.get("capabilities") or [])
    for planned_sequence, speech in enumerate(response.get("speech") or []):
        if not isinstance(speech, dict):
            continue
        text = str(speech.get("text") or "").strip()
        if not text:
            continue
        metadata = speech.get("metadata") if isinstance(speech.get("metadata"), dict) else {}
        speech_id = str(speech.get("id") or "")
        normalized_text = " ".join(text.split()).casefold()
        matching_deliveries = [
            (index, item)
            for index, item in enumerate(delivered_tts)
            if index not in matched_delivery_indices
            and " ".join(str(item.get("text") or "").split()).casefold()
            in normalized_text
        ]
        matched_delivery_indices.update(index for index, _item in matching_deliveries)
        delivery_elapsed_ms = next(
            (
                item.get("elapsed_ms")
                for _index, item in matching_deliveries
                if item.get("elapsed_ms") is not None
            ),
            None,
        )
        observations.append(
            {
                "sequence": execution_order.get(
                    speech_id,
                    fallback_order + capability_count + planned_sequence,
                ),
                "type": "speech.output",
                "domain": "speech",
                "status": "completed"
                if matching_deliveries
                or str(speech.get("id") or "") in execution_by_request
                or not execution_by_request
                else "planned",
                "interaction_role": "task_response",
                "text": text,
                "metadata": metadata,
                "planned_sequence": planned_sequence,
                **(
                    {"_chronology_elapsed_ms": delivery_elapsed_ms}
                    if delivery_elapsed_ms is not None
                    else {}
                ),
            }
        )

    for playback_index, playback in enumerate(delivered_tts):
        if playback_index in matched_delivery_indices:
            continue
        observations.append(
            {
                "sequence": fallback_order + capability_count + playback["order"],
                "type": "speech.output",
                "domain": "speech",
                "status": "completed",
                "interaction_role": "task_response",
                "text": playback["text"],
                "metadata": {
                    "source": "session_tts_playback",
                    "tts_order": playback["order"],
                    "workflow_event_index": playback["event_index"],
                    "elapsed_ms": playback["elapsed_ms"],
                },
                "planned_sequence": playback["order"],
                "_chronology_elapsed_ms": playback["elapsed_ms"],
            }
        )

    if any(item.get("_chronology_elapsed_ms") is not None for item in observations):
        observations.sort(
            key=lambda item: (
                0 if item.get("_chronology_elapsed_ms") is not None else 1,
                float(item.get("_chronology_elapsed_ms") or 0.0),
                int(item.get("sequence", 0)),
                str(item.get("type") or ""),
            )
        )
    else:
        observations.sort(
            key=lambda item: (
                int(item.get("sequence", 0)),
                str(item.get("type") or ""),
            )
        )
    for item in observations:
        item.pop("_chronology_elapsed_ms", None)
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

    for key in ("cognitive_runtime", "interaction_response"):
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
