from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from ...clients.ollama_client import OllamaGenerationError
from ...settings import agent_service_settings

try:
    from chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        new_llm_call_id,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.log_colors import colorize_for_cli
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        new_llm_call_id,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.log_colors import colorize_for_cli

from .fallback import fallback_decision
from .schema import FastProgressProposal, RouteDecision, RouteRequest, finalize_decision


def _raise_if_llm_budget_failure(exc: Exception) -> None:
    """Never reinterpret prompt/output truncation as user-semantic uncertainty."""

    if (
        isinstance(exc, OllamaGenerationError)
        and exc.failure_domain == "llm_budget"
    ):
        raise exc


logger = logging.getLogger("chromie.agent.goal_interpreter.llm")


ROUTE_NAMES = {
    "chat",
    "deep_thought",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
}

DETERMINISTIC_ONLY_ROUTES = {"interrupt"}
MODEL_IGNORE_INTENTS = {"not_addressed", "ambient_speech"}
DIRECTED_SPEECH_ACTS = {"question", "request", "imperative", "greeting"}
SUPPRESSIBLE_INACTIVE_SPEECH_ACTS = {
    "ambient_report",
    "dictation",
    "narration",
    "reply",
}
ROUTE_ITEM_PRIMARY_RANK = {
    "interrupt": 0,
    "robot_action": 1,
    "deep_thought": 2,
    "tool": 3,
    "memory": 4,
    "clarify": 5,
    "chat": 6,
    "ignore": 7,
}
REVIEW_STAGES = {
    "addressedness_review",
}


PLACEHOLDER_CAPABILITY_INTENTS = {
    "capability",
    "capability:",
    "capability_id",
    "<capability_id>",
    "<exact capability_id>",
    "<exact skill_id>",
    "capability:<capability_id>",
    "capability:<exact capability_id>",
    "capability:<exact skill_id>",
}


def interaction_engagement(request: RouteRequest) -> dict[str, Any]:
    raw = request.context.get("interaction_engagement")
    return raw if isinstance(raw, dict) else {}


def is_allowed_model_ignore(
    request: RouteRequest,
    decision: RouteDecision,
    *,
    min_confidence: float = 0.72,
) -> bool:
    """Accept semantic ambient-speech rejection only outside engagement."""

    engagement = interaction_engagement(request)
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    speech_act = str(metadata.get("addressedness_speech_act") or "").strip().casefold()
    return bool(
        decision.route == "ignore"
        and str(decision.intent or "").strip().casefold() in MODEL_IGNORE_INTENTS
        and metadata.get("semantic_addressedness_gate") is True
        and speech_act in SUPPRESSIBLE_INACTIVE_SPEECH_ACTS
        and engagement.get("gate_enabled") is True
        and engagement.get("active") is False
        and float(decision.confidence) >= min_confidence
    )


def is_disallowed_model_control_route(
    request: RouteRequest,
    decision: RouteDecision,
) -> bool:
    return bool(
        decision.route == "interrupt"
        or decision.route == "ignore"
        and not is_allowed_model_ignore(request, decision)
    )

_AGENT_GOAL_INTERPRETER_CONTEXT_OMIT_KEYS = {
    "candidate_capabilities",
    "common_ability_catalog",
    "common_ability_ids",
    "full_ability_catalog",
    "prompt_capabilities_common",
    "prompt_capabilities_all",
    "prompt_catalog_scope",
    "mind",
    "core_principles",
    "long_term_goals",
    "experience_tuning_policy",
    "conversation",
    "history",
    "task_contexts",
    "active_task_contexts",
    "active_task_snapshots",
    "recent_goal_snapshots",
    "current_task_context",
}


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON object from raw model text, tolerating markdown fences."""

    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model response")

    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response JSON is not an object")
    return value


def _compact_candidate_capabilities(candidates: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        description = " ".join(str(item.get("description") or "").split())
        if len(description) > 160:
            description = description[:160].rstrip() + "..."
        compact.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "route": str(item.get("route") or ""),
                "interaction_executable": bool(item.get("interaction_executable")),
                "available": item.get("available") is not False,
                "effects": list(item.get("effects") or [])[:4],
                "score": item.get("score"),
                "description": description,
            }
        )
    return compact


def _review_capabilities_from_request(request: RouteRequest) -> list[dict[str, Any]]:
    """Return a lossless, candidate-first recovery view of supplied abilities.

    Query matches are useful ordering evidence, while the common and full
    snapshots are authoritative availability context.  A semantic-route guess
    must not turn that narrowing into catalog destruction: later model review
    needs both the best matches and the remaining supplied affordances in order
    to correct an earlier route mistake.
    """

    capabilities: list[dict[str, Any]] = []
    capability_indexes: dict[str, int] = {}
    seen_anonymous: set[str] = set()
    for key in (
        "candidate_capabilities",
        "prompt_capabilities_common",
        "prompt_capabilities_all",
        "common_ability_catalog",
        "full_ability_catalog",
    ):
        value = request.context.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            capability_id = str(
                item.get("capability_id") or item.get("skill_id") or ""
            ).strip()
            if capability_id and capability_id in capability_indexes:
                index = capability_indexes[capability_id]
                merged = dict(capabilities[index])
                for field, value in item.items():
                    if field not in merged or value not in (None, "", [], {}):
                        merged[field] = value
                capabilities[index] = merged
                continue
            if not capability_id:
                identity = json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                if identity in seen_anonymous:
                    continue
                seen_anonymous.add(identity)
            else:
                capability_indexes[capability_id] = len(capabilities)
            capabilities.append(item)
    return capabilities


def _capability_ids_from_request(request: RouteRequest) -> set[str]:
    return {
        capability_id
        for item in _review_capabilities_from_request(request)
        if (
            capability_id := str(
                item.get("capability_id") or item.get("skill_id") or ""
            ).strip()
        )
    }


def _capability_route_lookup_from_request(request: RouteRequest) -> dict[str, str]:
    routes: dict[str, str] = {}
    for item in _review_capabilities_from_request(request):
        capability_id = str(
            item.get("capability_id") or item.get("skill_id") or ""
        ).strip()
        route = str(item.get("route") or "").strip()
        if capability_id and route in ROUTE_NAMES and capability_id not in routes:
            routes[capability_id] = route
    return routes


def _route_intent_contract_conflict(
    request: RouteRequest,
    decision: RouteDecision,
) -> str | None:
    """Return a structural route/intent conflict without interpreting user text.

    No semantic repair follows this guard. It only detects that the model's
    own output contradicts a declared route contract so the turn can fail closed.
    """

    intent = str(decision.intent or "").strip()
    if intent in ROUTE_NAMES and intent != decision.route:
        return "route_name_intent_mismatch"
    capability_id = _known_capability_id(intent, _capability_ids_from_request(request))
    if capability_id:
        expected_route = _route_for_capability_id(capability_id, request)
        if decision.route != expected_route:
            return "capability_intent_route_mismatch"
    return None


def _has_executable_non_chat_affordance(request: RouteRequest) -> bool:
    for item in _review_capabilities_from_request(request):
        if str(item.get("route") or "") not in {
            "memory",
            "robot_action",
            "tool",
        }:
            continue
        if item.get("available") is False:
            continue
        if item.get("interaction_executable") is False:
            continue
        return True
    return False


def _route_for_capability_id(capability_id: str, request: RouteRequest) -> str:
    if not capability_id:
        return "robot_action"
    route = _capability_route_lookup_from_request(request).get(capability_id)
    return route if route in ROUTE_NAMES else "robot_action"


def _known_capability_id(text: Any, capability_ids: set[str]) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.startswith("capability:"):
        value = value.split(":", 1)[1].strip()
    if value in capability_ids:
        return value
    # Small fast models sometimes append a non-authoritative semantic hint to
    # an otherwise exact catalog identity, for example ``skill.id|speed=quick``.
    # Accept only an exact supplied ID before the separator. The suffix is audit
    # context only: it is never executable arguments or execution authority.
    if "|" in value:
        prefix = value.split("|", 1)[0].strip()
        if prefix in capability_ids:
            return prefix
    return ""




def _compact_schema_field(
    name: str,
    prop: dict[str, Any],
    *,
    include_value_contracts: bool = False,
) -> str:
    parts = [str(name)]
    type_value = prop.get("type")
    if isinstance(type_value, list):
        type_text = "|".join(str(item) for item in type_value[:3])
    elif isinstance(type_value, str):
        type_text = type_value
    else:
        type_text = ""
    if type_text:
        parts.append(type_text)
    enum = prop.get("enum")
    if isinstance(enum, list) and enum:
        parts.append("enum=" + "|".join(str(item) for item in enum[:4]))
    unit = prop.get("unit") or prop.get("units")
    if isinstance(unit, str) and unit.strip():
        parts.append(f"unit={unit.strip()[:24]}")
    if include_value_contracts:
        for key, label in (
            ("minimum", "min"),
            ("maximum", "max"),
            ("exclusiveMinimum", "exclusive_min"),
            ("exclusiveMaximum", "exclusive_max"),
            ("default", "default"),
        ):
            value = prop.get(key)
            if isinstance(value, (str, int, float, bool)):
                parts.append(f"{label}={str(value)[:32]}")
    return ":".join(parts)


def _compact_prompt_capabilities(
    candidates: Any,
    *,
    limit: int = 96,
    include_value_contracts: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        if item.get("prompt_tier_locked") is True:
            continue
        capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
        if not capability_id:
            continue
        description = " ".join(str(item.get("description") or "").split())
        if len(description) > 28:
            description = description[:28].rstrip() + "..."
        schema = item.get("input_schema") if isinstance(item.get("input_schema"), dict) else {}
        args: list[str] = []
        required = schema.get("required") if isinstance(schema, dict) else []
        if not isinstance(required, list):
            required = []
        required_set = {str(value) for value in required if isinstance(value, str)}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if isinstance(properties, dict):
            for name, prop in list(properties.items())[:3]:
                if not isinstance(prop, dict):
                    continue
                enum = prop.get("enum")
                unit = prop.get("unit") or prop.get("units")
                has_value_contract = include_value_contracts and any(
                    key in prop
                    for key in (
                        "minimum",
                        "maximum",
                        "exclusiveMinimum",
                        "exclusiveMaximum",
                        "default",
                    )
                )
                if (
                    str(name) not in required_set
                    and not (isinstance(enum, list) and enum)
                    and not (isinstance(unit, str) and unit.strip())
                    and not has_value_contract
                ):
                    continue
                field = _compact_schema_field(
                    str(name),
                    prop,
                    include_value_contracts=include_value_contracts,
                )
                if str(name) in required_set:
                    field += ":required"
                args.append(field)
        effects = [
            str(effect).strip()
            for effect in list(item.get("effects") or [])[:3]
            if str(effect).strip()
        ]
        entry: dict[str, Any] = {
            "capability_id": capability_id,
            "route": str(item.get("route") or ""),
        }
        if description:
            entry["desc"] = description
        if effects:
            entry["effect"] = effects[0]
        safety = str(item.get("safety_class") or "")[:32]
        if safety:
            entry["safety"] = safety
        if bool(item.get("requires_confirmation", False)):
            entry["confirm"] = True
        if item.get("interaction_executable") is False:
            entry["exec"] = False
        required_args = [str(value) for value in required if isinstance(value, str)][:6]
        if required_args:
            entry["required_args"] = required_args
        if args:
            entry["args"] = args
        compact.append(entry)
    return compact


def _compact_prompt_capability_lines(entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        capability_id = str(entry.get("capability_id") or "").strip()
        if not capability_id:
            continue
        parts = [capability_id]
        route = str(entry.get("route") or "").strip()
        if route and route != "robot_action":
            parts.append(f"route={route}")
        desc = str(entry.get("desc") or "").strip()
        if desc:
            parts.append(f"desc={desc}")
        effect = str(entry.get("effect") or "").strip()
        if effect and effect != "physical_motion":
            parts.append(f"effect={effect}")
        safety = str(entry.get("safety") or "").strip()
        if safety:
            parts.append(f"safety={safety}")
        if entry.get("confirm") is True:
            parts.append("confirm")
        if entry.get("exec") is False:
            parts.append("exec=false")
        required_args = entry.get("required_args")
        if isinstance(required_args, list) and required_args:
            parts.append(
                "required_args=" + ",".join(str(value) for value in required_args[:4])
            )
        args = entry.get("args")
        if isinstance(args, list) and args:
            parts.append("args=" + ";".join(str(value) for value in args[:3]))
        lines.append("|".join(parts))
    return lines


def _bounded_json(value: Any, *, max_chars: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        text = json.dumps(str(value), ensure_ascii=False)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def _bounded_json_array(value: list[Any], *, max_chars: int = 4000) -> str:
    items: list[Any] = []
    for item in value:
        candidate = [*items, item]
        text = json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if len(text) > max_chars:
            break
        items.append(item)
    return json.dumps(
        items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )



def _short_hash(value: Any) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(value)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _json_log(value: Any, *, max_chars: int = 1600) -> str:
    return _bounded_json(value, max_chars=max_chars)


def _metadata_keys(value: Any) -> list[str]:
    return sorted(str(key) for key in value.keys()) if isinstance(value, dict) else []


def _payload_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return [message for message in messages if isinstance(message, dict)]


def _payload_message_texts(payload: dict[str, Any]) -> tuple[str, str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    all_parts: list[str] = []
    for message in _payload_messages(payload):
        content = str(message.get("content") or "")
        all_parts.append(content)
        role = str(message.get("role") or "")
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    system = "\n".join(system_parts)
    user = "\n".join(user_parts)
    return system, user, "\n".join(all_parts)


def _prompt_feature_flags(text: str) -> dict[str, bool]:
    lowered = text.casefold()
    return {
        "has_fast_speech_contract": "fast_speech" in lowered,
        "has_tool_route_contract": "valid routes:" in lowered and "tool" in lowered,
        "has_external_lookup_guidance": "current external facts" in lowered
        and "trusted lookup capability" in lowered,
        "has_no_topic_mapping_guidance": "do not map a topic keyword" in lowered,
    }


def _route_item_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _raw_interpreter_output_summary(content: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "raw_chars": len(content or ""),
        "raw_hash": _short_hash(content or ""),
        "has_json": False,
        "raw_route": None,
        "raw_intent": None,
        "raw_confidence": None,
        "raw_fast_speech_present": False,
        "raw_routes_count": 0,
        "raw_metadata_keys": [],
    }
    try:
        parsed = _extract_json_object(content or "")
    except Exception as exc:
        summary["parse_error"] = f"{type(exc).__name__}: {exc}"
        return summary
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    route_items = _route_items_from_parsed(parsed)
    summary.update(
        {
            "has_json": True,
            "raw_route": str(parsed.get("route") or ""),
            "raw_intent": str(parsed.get("intent") or ""),
            "raw_confidence": parsed.get("confidence"),
            "raw_routes_count": len(route_items),
            "raw_actions_count": _route_item_count(parsed.get("actions")),
            "raw_fast_speech_present": isinstance(parsed.get("fast_speech"), (dict, str))
            or any(isinstance(item.get("fast_speech"), (dict, str)) for item in route_items)
            or isinstance(metadata.get("fast_speech"), (dict, str)),
            "raw_metadata_keys": _metadata_keys(metadata),
            "raw_weather_query_present": isinstance(metadata.get("weather_query"), dict)
            or any(
                isinstance(
                    (item.get("metadata") if isinstance(item.get("metadata"), dict) else {}).get("weather_query"),
                    dict,
                )
                for item in route_items
            ),
            "raw_tool_name": metadata.get("tool_name"),
        }
    )
    return summary


def _catalog_observability_profile(request: RouteRequest | None) -> dict[str, Any]:
    if request is None:
        return {}
    context = request.context if isinstance(request.context, dict) else {}
    common = context.get("common_ability_catalog") or context.get("prompt_capabilities_common") or []
    full = context.get("full_ability_catalog") or context.get("prompt_capabilities_all") or []
    candidates = context.get("candidate_capabilities") or []
    if not isinstance(common, list):
        common = []
    if not isinstance(full, list):
        full = []
    if not isinstance(candidates, list):
        candidates = []

    def capability_ids(items: list[Any]) -> list[str]:
        ids: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
            if capability_id:
                ids.append(capability_id)
        return ids

    def filtered_ids(items: list[Any], needle: str) -> list[str]:
        found: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(
                str(item.get(key) or "")
                for key in (
                    "capability_id",
                    "skill_id",
                    "route",
                    "contract",
                    "description",
                    "effects",
                    "safety_class",
                )
            ).casefold()
            if needle in haystack:
                capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
                if capability_id:
                    found.append(capability_id)
        return found

    common_ids = capability_ids(common)
    return {
        "common_ability_count": len(common),
        "full_ability_count": len(full),
        "candidate_capability_count": len(candidates),
        "common_catalog_hash": _short_hash(_bounded_json(common, max_chars=50000)),
        "common_ability_sample": common_ids[:10],
        "tool_like_ability_ids": filtered_ids(common, "tool")[:10],
        "weather_like_ability_ids": filtered_ids(common, "weather")[:10],
    }


def _context_without_prompt_globals(context: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in (context or {}).items()
        if key not in _AGENT_GOAL_INTERPRETER_CONTEXT_OMIT_KEYS
    }


def _compact_active_task_snapshots(
    context: dict[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    raw = context.get("active_task_snapshots")
    if not isinstance(raw, list) or not raw:
        raw = context.get("active_task_contexts")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        semantic_goal = item.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            semantic_goal = {
                "description": item.get("goal") or item.get("task_type") or "task",
                "constraints": item.get("constraints") if isinstance(item.get("constraints"), dict) else {},
            }
        gaps = item.get("open_information_gaps")
        if not isinstance(gaps, list):
            gaps = [
                {"description": value, "blocking": True}
                for value in (item.get("pending_questions") or [])
                if isinstance(value, str)
            ]
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        execution_binding = metadata.get("execution_binding")
        if not isinstance(execution_binding, dict):
            execution_binding = {}
        compact.append(
            {
                "task_id": str(item.get("task_id") or ""),
                "status": str(item.get("status") or "open"),
                "goal_version": int(item.get("goal_version") or semantic_goal.get("version") or 1),
                "plan_version": int(item.get("plan_version") or 0),
                "goal": {
                    "description": str(semantic_goal.get("description") or "")[:240],
                    "beneficiary": semantic_goal.get("beneficiary"),
                    "object": semantic_goal.get("object") if isinstance(semantic_goal.get("object"), dict) else {},
                    "constraints": semantic_goal.get("constraints") if isinstance(semantic_goal.get("constraints"), dict) else {},
                },
                "open_information_gaps": [
                    {
                        "gap_id": str(gap.get("gap_id") or ""),
                        "description": str(gap.get("description") or "")[:160],
                        "preferred_resolution": gap.get("preferred_resolution"),
                    }
                    for gap in gaps[:4]
                    if isinstance(gap, dict)
                ],
                "commitment_state": item.get("commitment_state"),
                "last_user_update": str(
                    item.get("last_user_update")
                    or item.get("last_meaningful_user_turn")
                    or ""
                )[:220],
                "execution_binding": execution_binding,
            }
        )
    return compact


def _compact_active_goal_snapshots(
    context: dict[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    raw = context.get("active_goal_snapshots")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        goal_id = str(item.get("goal_id") or goal.get("goal_id") or "").strip()
        if not goal_id:
            continue
        compact.append(
            {
                "goal_id": goal_id,
                "responsibility_status": str(
                    item.get("responsibility_status")
                    or goal.get("responsibility_status")
                    or "open"
                ),
                "work_status": str(item.get("work_status") or ""),
                "goal": {
                    "description": str(goal.get("description") or "")[:240],
                    "object": (
                        goal.get("object")
                        if isinstance(goal.get("object"), dict)
                        else {}
                    ),
                    "constraints": (
                        goal.get("constraints")
                        if isinstance(goal.get("constraints"), dict)
                        else {}
                    ),
                },
                "last_user_update": str(item.get("last_user_update") or "")[:220],
            }
        )
    return compact


def _compact_recent_goal_snapshots(
    context: dict[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    raw = context.get("recent_goal_snapshots")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        goal_id = str(item.get("goal_id") or goal.get("goal_id") or "").strip()
        if not goal_id:
            continue
        compact.append(
            {
                "goal_id": goal_id,
                "status": str(item.get("status") or ""),
                "goal": {
                    "description": str(goal.get("description") or "")[:240],
                    "object": (
                        goal.get("object")
                        if isinstance(goal.get("object"), dict)
                        else {}
                    ),
                },
                "commitment_state": item.get("commitment_state"),
                "last_user_update": str(item.get("last_user_update") or "")[:220],
            }
        )
    return compact


def _compact_verified_tool_memory_index(
    context: dict[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Project only verified-result provenance, never provider result contents."""

    raw = context.get("verified_tool_memory_index")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        tool_id = str(item.get("tool_id") or "").strip()
        if not evidence_id or not tool_id:
            continue
        request_args = item.get("request_args")
        compact.append(
            {
                "evidence_id": evidence_id,
                "tool_id": tool_id,
                "status": str(item.get("status") or ""),
                "request_args": request_args if isinstance(request_args, dict) else {},
                "age_ms": item.get("age_ms"),
                "goal_ids": list(item.get("goal_ids") or [])[:8],
                "source": "verified_tool_memory_index",
            }
        )
    return compact


def _goal_interpretation_prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = _context_without_prompt_globals(context)
    memory = prompt_context.get("session_memory")
    if isinstance(memory, dict):
        prompt_context["session_memory"] = {
            key: value
            for key, value in memory.items()
            if key not in {"recent_user_request", "recent_assistant_response"}
        }
    return prompt_context


def _compact_recent_dialogue(
    context: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Project bounded accepted dialogue without reintroducing full session state.

    Goal Interpretation needs nearby conversational evidence for follow-ups such
    as pronouns, ellipsis, corrections, and "that one" references.  The full
    conversation object remains excluded from the fast prompt; this projection
    keeps only user/assistant surface text plus small provenance fields.
    """

    raw = context.get("history")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, int(limit)) :]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        # Suppressed ambient input is retained by the Host for auditability but
        # is not conversational evidence for semantic continuity.
        if role == "user" and str(item.get("route") or "").strip() == "ignore":
            continue
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        projected = {
            "role": role,
            "text": text[:260],
        }
        sid = " ".join(str(item.get("sid") or "").strip().split())
        if sid:
            projected["sid"] = sid
        if role == "user":
            route = " ".join(str(item.get("route") or "").strip().split())
            intent = " ".join(str(item.get("intent") or "").strip().split())
            if route:
                projected["route"] = route
            if intent:
                projected["intent"] = intent
            semantic_status = " ".join(
                str(metadata.get("semantic_status") or "").strip().split()
            )
            if semantic_status:
                projected["semantic_status"] = semantic_status
            failure_stage = " ".join(
                str(metadata.get("semantic_failure_stage") or "").strip().split()
            )
            if failure_stage:
                projected["semantic_failure_stage"] = failure_stage
            if "canonical_goal_committed" in metadata:
                projected["canonical_goal_committed"] = bool(
                    metadata.get("canonical_goal_committed")
                )
        else:
            source = " ".join(str(metadata.get("source") or "").strip().split())
            if source:
                projected["source"] = source
        compact.append(projected)
    return compact


def _goal_interpretation_fast_context_section(mind: Any) -> str:
    """Minimal context for the fast Goal Interpreter.

    The fast Goal Interpreter should decide whether a task needs the full mind profile;
    it should not always pay for worldview/lifeview/valueview tokens itself.
    Deepthinking and capability prompts still receive richer mind context.
    """

    identity: dict[str, Any] = {}
    voice: dict[str, Any] = {}
    if isinstance(mind, dict):
        raw_identity = mind.get("identity")
        if isinstance(raw_identity, dict):
            identity.update(
                {
                    key: raw_identity.get(key)
                    for key in (
                        "entity_id",
                        "name",
                        "kind",
                        "age_description",
                        "family_role",
                    )
                    if raw_identity.get(key) not in (None, "", [], {})
                }
            )
        self_model = mind.get("self_model")
        speaker = self_model.get("speaker_entity") if isinstance(self_model, dict) else None
        if isinstance(speaker, dict):
            for key in ("entity_id", "name", "kind"):
                if speaker.get(key) not in (None, "", [], {}):
                    identity[key] = speaker.get(key)
        identity["profile_id"] = mind.get("profile_id")
        identity["version"] = mind.get("version")
        personality = mind.get("personality_expression")
        if isinstance(personality, dict) and personality.get("owner_approved") is True:
            voice = {
                key: personality.get(key)
                for key in (
                    "spoken_style",
                    "tool_use_style",
                    "maturity_boundary",
                )
                if personality.get(key) not in (None, "", [], {})
            }
    profile = {
        "identity": identity or {"entity_id": "chromie", "name": "Chromie"},
        "voice": voice,
    }
    return (
        "Fast Goal Interpretation Context:\n"
        f"{_bounded_json(profile, max_chars=1150)}\n"
        "This voice governs fast_speech. "
        "The full owner-approved mind profile, worldview, lifeview, valueview, "
        "long-term goals, and core principles remain downstream. "
        "Pick context_profile: fast_minimal, session_compact, capability_safety, full_mind."
    )


def _goal_interpretation_global_context_section(mind: Any) -> str:
    if not isinstance(mind, dict) or not mind:
        mind = {}
    identity = mind.get("identity") if isinstance(mind.get("identity"), dict) else {}
    self_model = mind.get("self_model") if isinstance(mind.get("self_model"), dict) else {}
    core_principles = mind.get("core_principles", [])
    long_term_goals = mind.get("long_term_goals", [])
    summary = " ".join(str(mind.get("prompt_summary") or "").split())
    if len(summary) > 240:
        summary = summary[:240].rstrip() + "..."
    profile = {
        "profile_id": mind.get("profile_id"),
        "version": mind.get("version"),
        "owner_approved": mind.get("owner_approved"),
    }

    return (
        "Mind Profile:\n"
        f"{_bounded_json(profile, max_chars=180)}\n"
        "Self Model:\n"
        f"{_bounded_json(self_model or {'speaker_entity': identity}, max_chars=520)}\n"
        "Worldview:\n"
        "- Chromie's owner-approved first-person identity is the human child and family role in the Self Model. Implementation and embodiment metadata are outside her ordinary self-concept and speech. Use only supplied runtime evidence for abilities and outcomes.\n"
        "Lifeview:\n"
        f"{_bounded_json(long_term_goals or 'not supplied', max_chars=240)}\n"
        "Valueview:\n"
        f"{_bounded_json(core_principles or 'not supplied', max_chars=360)}\n"
        "Core Runtime Principles:\n"
        "- Infer from meaning/context/abilities/schemas, not phrase rules.\n"
        "- Memory and preferences guide interpretation; they never authorize side effects.\n"
        "- Never invent abilities or raw motor/joint/actuator/controller-array/torque commands.\n"
        "Owner-Approved Mind Summary:\n"
        f"{summary or 'not supplied'}"
    )


def _route_items_from_parsed(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw = parsed.get("routes")
    if raw is None:
        metadata = parsed.get("metadata")
        if isinstance(metadata, dict):
            raw = metadata.get("route_items") or metadata.get("routes")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _dominant_route_from_items(items: list[dict[str, Any]]) -> str:
    routes = [
        str(item.get("route") or "").strip()
        for item in items
        if str(item.get("route") or "").strip() in ROUTE_NAMES
    ]
    if not routes:
        return ""
    return min(routes, key=lambda route: ROUTE_ITEM_PRIMARY_RANK.get(route, 99))


def _first_route_item_intent(items: list[dict[str, Any]], route: str) -> str:
    for item in items:
        if str(item.get("route") or "").strip() == route:
            intent = str(item.get("intent") or "").strip()
            if intent:
                return intent
    return ""


def _is_placeholder_capability_intent(intent: str) -> bool:
    return (intent or "").strip().lower() in PLACEHOLDER_CAPABILITY_INTENTS


class OllamaGoalInterpreter:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        timeout_ms: int,
        review_timeout_ms: int | None = None,
        confidence_threshold: float,
        num_ctx: int = 4096,
        num_predict: int = 512,
        keep_alive: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout_s = max(0.1, timeout_ms / 1000.0)
        self.review_timeout_s = max(
            0.1,
            (review_timeout_ms if review_timeout_ms is not None else timeout_ms) / 1000.0,
        )
        self.confidence_threshold = confidence_threshold
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(32, num_predict)
        self.prompt_chars_per_token_estimate = (
            agent_service_settings.llm_prompt_chars_per_token_estimate
        )
        self.context_safety_margin_tokens = (
            agent_service_settings.llm_context_safety_margin_tokens
        )
        self.keep_alive = (keep_alive or "").strip() or None
        self.prompt_path = prompt_path or Path(__file__).parent / "prompts" / "goal_interpreter_system.txt"
        self.debug_raw_output = agent_service_settings.goal_interpreter_debug_raw
        self.debug_prompt = agent_service_settings.goal_interpreter_debug_prompt

    def load_system_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning("Goal Interpreter system prompt not found: %s", self.prompt_path)
            return (
                "You are Chromie's routing classifier. Return only a JSON object "
                "matching the provided schema."
            )

    def build_user_prompt(self, request: RouteRequest) -> str:
        prompt_capabilities = request.context.get("common_ability_catalog", [])
        if not prompt_capabilities:
            prompt_capabilities = request.context.get("prompt_capabilities_common", [])
        compact_prompt_capabilities = _compact_prompt_capabilities(prompt_capabilities)
        common_ability_ids = [
            item["capability_id"]
            for item in compact_prompt_capabilities
            if item.get("capability_id")
        ]
        common_ability_catalog_json = _bounded_json_array(
            _compact_prompt_capability_lines(compact_prompt_capabilities),
            max_chars=2200,
        )
        mind = request.context.get("mind", {})
        session_context = _goal_interpretation_prompt_context(request.context)
        context_json = _bounded_json(session_context, max_chars=520)
        interaction_context_json = _bounded_json(
            request.context.get("interaction_context") or {},
            max_chars=3200,
        )
        recent_dialogue_json = _bounded_json_array(
            _compact_recent_dialogue(request.context),
            max_chars=1800,
        )
        active_tasks_json = _bounded_json_array(
            _compact_active_task_snapshots(request.context),
            max_chars=1800,
        )
        active_goals_json = _bounded_json_array(
            _compact_active_goal_snapshots(request.context),
            max_chars=1500,
        )
        recent_goals_json = _bounded_json_array(
            _compact_recent_goal_snapshots(request.context),
            max_chars=1400,
        )
        recent_goals_section = (
            f"Recent Terminal Goal Snapshot JSON:{recent_goals_json}\n\n"
            if recent_goals_json != "[]"
            else ""
        )
        return (
            "Global Context Group:\n"
            f"{_goal_interpretation_fast_context_section(mind)}\n\n"
            "Session Context Group:\n"
            f"language={request.language or 'auto'} sid={request.sid or ''}\n"
            f"Bounded session, memory, task, and robot/world context JSON:{context_json}\n"
            f"Recent Interaction Context JSON:{interaction_context_json}\n"
            f"Recent Accepted Dialogue JSON:{recent_dialogue_json}\n"
            f"Active Goal Snapshot JSON:{active_goals_json}\n"
            f"Active Task/Progress Snapshot JSON:{active_tasks_json}\n\n"
            f"{recent_goals_section}"
            "Current Job:\n"
            "fast goal-interpretation and lane proposer with readiness candidates. The deterministic emergency/noise filter ran. Decide from meaning, bounded context. This is bounded cognitive evidence, not final goal meaning. Return calibrated confidence; never execute or authorize side effects. Terminal references do not reopen Goals. Memory write=memory; recall=chat. If current Mind/context fully answers ordinary conversation, put it only in progress as kind=native_response; otherwise do not answer.\n\n"
            "Task Context Group:\n"
            f"Latest user input: {request.text}\n"
            f"Common ability IDs: {_bounded_json(common_ability_ids, max_chars=420)}\n"
            f"Common Ability Catalog JSON: {common_ability_catalog_json}\n"
            "Task Continuity:\n"
            "Use bounded dialogue, active/recent Goals, task progress, discourse, and Interaction Context; resolve by meaning, not lexical shortcuts, and emit the still-needed delta. Keep newer failed/goal-less dialogue salient. fast_speech is the first Goal Progress Communication milestone: normally one tiny polite acknowledgement; missing results limit claims, not responsiveness. An external truth check may acknowledge checking but never assert its result before evidence. Omit for an immediate answer, equivalent notification delivered/pending, silence, or repetition. Heard speech/trusted terminal effects are done; scheduled/planned work is not. Preserve exact corrected bindings; clarify real ambiguity.\n"
            "Capability Affordance Proposal:\n"
            "Treat the Common Ability Catalog as a compact body/tool affordance interface: proposals, not authoritative grounding and not a phrase table. capability_inquiry=abilities; availability=chat; execution=robot_action. Bind exact methods. One parameterized capability may leave args to CapabilityAgent; compound capabilities may use actions[]. Isolated letters and low-information ASR fragments clarify; missing/ambiguous methods keep an open goal for CapabilityAgent. Capability progress requires grounded Goal meaning: material entities/parameters defining the owed outcome must come from user input or bounded context. Otherwise omit capability progress; never guess/default them or imply checking/execution started. Planner handles execution only after the outcome is defined. If current Mind/context fully answers conversation, progress may use kind=native_response with complete answer+speech_act; never while external/private/runtime evidence, memory retrieval, unresolved references, effects, or deeper reasoning remain. Current external facts use trusted lookup by meaning/context: route=tool, intent=capability:<exact capability_id>. Missing ability -> non-executable ability proposals in metadata.desired_abilities. Never invent args, claim completion, or emit low-level controls.\n\n"
            "Cost Function:\n"
            "Speech-only conversation and capability availability=chat; catalog execution=robot_action; lookup=tool; planning=deep_thought; ambiguity=clarify. Never return interrupt or ignore; a separate focused addressedness stage owns ambient suppression.\n\n"
            "Output Contract:\n"
            "Return one compact JSON object. Required keys: route, intent, confidence, fast_speech, progress. fast_speech is brief speech or null for immediate, duplicate, or silent turns. Use owner-approved child/family voice in first-person speech, never customer-service/workflow/status/processing narration. For effectful work it is generic willingness/checking only: omit material task parameters and exact methods until downstream grounding; progress is advisory, not proof of executability. Never claim an unobserved result, execution, or completion. Host derives typed claim fields. memory write=memory; recall=chat; durable memory needs current-turn consent. routes[] split responsibilities; actions[] use exact IDs/args (\"confidence\":0.0 means unknown). semantic_task_operations may advise create/update/resolve/replan against supplied task IDs. Omit agents, metadata, candidate_capabilities, explanations unless needed. Never output placeholder intents, hidden reasoning, free-form progress narration outside fast_speech, scratchpad, markdown, or text outside JSON."
        )

    @staticmethod
    def _route_response_schema() -> dict[str, Any]:
        schema = RouteDecision.model_json_schema()
        properties = schema.get("properties", {})
        progress_definition = schema.get("$defs", {}).get("FastProgressProposal")
        if isinstance(progress_definition, dict):
            progress_definition["allOf"] = [
                {
                    "if": {
                        "properties": {"kind": {"const": "capability"}},
                        "required": ["kind"],
                    },
                    "then": {
                        "properties": {
                            "capability_id": {"type": "string", "minLength": 1},
                            "response_text": {"type": "string", "maxLength": 0},
                        },
                        "required": ["capability_id"],
                    },
                },
                {
                    "if": {
                        "properties": {"kind": {"const": "native_response"}},
                        "required": ["kind"],
                    },
                    "then": {
                        "properties": {
                            "capability_id": {"type": "string", "maxLength": 0},
                            "args": {"type": "object", "maxProperties": 0},
                            "response_text": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 600,
                            },
                        },
                        "required": ["response_text"],
                    },
                },
            ]
        # The model must explicitly decide whether a first progress notification
        # exists. Speech itself remains optional; silence is represented by JSON
        # null rather than by omitting the responsibility. Keep the model-facing
        # choice semantic and small: the Host materializes the deterministic
        # claim envelope after decoding.
        progress = properties.get("progress")
        if isinstance(progress, dict):
            progress["description"] = (
                "Required bounded readiness proposals. Use [] when no part is already "
                "safe/complete enough to progress from current cognition. native_response "
                "is a substantive conversational answer, never a progress acknowledgement."
            )
        properties["fast_speech"] = {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 120},
                {"type": "null"},
            ],
            "description": (
                "Required Goal Progress Communication decision: one brief natural "
                "person-to-person prospective utterance, or null for intentional silence; "
                "never a task/process/workflow status label."
            ),
        }
        schema["required"] = list(
            dict.fromkeys(
                [
                    *(schema.get("required") or []),
                    "route",
                    "intent",
                    "confidence",
                    "fast_speech",
                    "progress",
                ]
            )
        )
        source = properties.get("source")
        if isinstance(source, dict):
            source.clear()
            source.update({"type": "string", "const": "llm"})
        return schema

    @staticmethod
    def _addressedness_response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "addressed": {"type": "boolean"},
                "speech_act": {
                    "type": "string",
                    "enum": [
                        "question",
                        "request",
                        "imperative",
                        "greeting",
                        "reply",
                        "ambient_report",
                        "dictation",
                        "narration",
                        "unclear",
                    ],
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["addressed", "speech_act", "confidence"],
            "additionalProperties": False,
        }

    def build_payload(self, request: RouteRequest, *, relaxed_json: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.load_system_prompt()},
                {"role": "user", "content": self.build_user_prompt(request)},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        payload["format"] = self._route_response_schema()
        return payload

    def build_contract_repair_payload(
        self,
        request: RouteRequest,
        *,
        previous_content: str,
        validation_error: Exception,
    ) -> dict[str, Any]:
        payload = self.build_payload(request)
        payload["messages"] = [
            {
                "role": "system",
                "content": (
                    self.load_system_prompt()
                    + "\n\nContract Repair: The previous RouteDecision failed the "
                    "Host-owned typed contract. Return one corrected complete "
                    "RouteDecision JSON object. Preserve valid semantic judgments, "
                    "but revise every field named by the exact validation errors. "
                    "Do not infer durable-memory consent, a Capability, a route, or "
                    "an effect from the errors. Session memory is ephemeral and must "
                    "omit consent_basis and retention_days. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    self.build_user_prompt(request)
                    + "\n\nPrevious model output:\n"
                    + str(previous_content or "")[:5000]
                    + "\n\nExact typed validation errors:\n"
                    + str(validation_error)[:6000]
                ),
            },
        ]
        return payload

    def build_addressedness_review_payload(
        self,
        request: RouteRequest,
    ) -> dict[str, Any]:
        """Build a small binary semantic gate on the warm fast model."""

        engagement_json = _bounded_json(interaction_engagement(request), max_chars=500)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": self._addressedness_response_schema(),
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You classify whether the latest transcript is directed to a nearby "
                        "robot named Chromie. Host evidence says there is no active "
                        "conversation. First classify speech_act, then decide addressed from "
                        "the utterance's addressee and subject, never from keywords. Questions, "
                        "requests, imperatives, greetings, and Chromie's name are addressed "
                        "even when the robot's name or the pronoun 'you' is omitted. A short "
                        "reply without an active exchange may be unaddressed. Third-person reports, "
                        "dictation, meeting talk, or narration without a second-person "
                        "addressee are ambient. Delivery to this classifier is not evidence "
                        "of addressedness. If genuinely unclear, use addressed=true.\n"
                        "Semantic contrasts:\n"
                        "User asks 'How are you?' -> addressed=true.\n"
                        "User says '请帮我打开灯。' -> addressed=true.\n"
                        "User greets '你好。' -> addressed=true.\n"
                        "With no active exchange, isolated 'Yeah.' -> "
                        "speech_act=reply and addressed=false.\n"
                        "Nearby speaker reports '他们明天讨论传感器数据。' -> addressed=false.\n"
                        "Nearby speaker narrates 'She said the model runs locally.' -> "
                        "addressed=false.\n"
                        "The speech_act must be question, request, imperative, greeting, "
                        "reply, ambient_report, dictation, narration, or unclear. "
                        "Return only addressed, speech_act, and calibrated confidence as JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Host engagement JSON: {engagement_json}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Latest transcript: {request.text}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                # Keep the same runner context as quick_intent. Ollama keys a
                # loaded runner by context size; changing it here reloads the
                # model and turns a subsecond binary review into multi-second
                # latency on every inactive turn.
                "num_ctx": self.num_ctx,
                "num_predict": 32,
            },
        }

    def _log_payload_profile(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: RouteRequest | None = None,
    ) -> None:
        system_text, user_text, all_text = _payload_message_texts(payload)
        profile = {
            "stage": stage,
            "sid": request.sid if request is not None else None,
            "model": payload.get("model"),
            "prompt_chars": self._payload_prompt_chars(payload),
            "system_chars": len(system_text),
            "user_chars": len(user_text),
            "system_hash": _short_hash(system_text),
            "user_hash": _short_hash(user_text),
            "num_predict": (payload.get("options") or {}).get("num_predict"),
            "num_ctx": (payload.get("options") or {}).get("num_ctx"),
            **_prompt_feature_flags(all_text),
            **_catalog_observability_profile(request),
        }
        logger.info("goal_interpreter_prompt_profile %s", _json_log(profile, max_chars=2200))
        if self.debug_prompt:
            logger.info(
                "goal_interpreter_prompt_debug stage=%s sid=%s system=%r user=%r",
                stage,
                request.sid if request is not None else None,
                system_text[:12000],
                user_text[:12000],
            )

    def _log_response_summary(
        self,
        data: dict[str, Any],
        *,
        stage: str,
        request: RouteRequest | None = None,
    ) -> None:
        content = str(data.get("message", {}).get("content") or "")
        summary = {
            "stage": stage,
            "sid": request.sid if request is not None else None,
            "model": data.get("model"),
            "done": data.get("done"),
            "done_reason": data.get("done_reason"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            **_raw_interpreter_output_summary(content),
        }
        logger.info("goal_interpreter_llm_raw_summary %s", _json_log(summary, max_chars=2200))
        if self.debug_raw_output:
            logger.info(
                "goal_interpreter_llm_raw_output stage=%s sid=%s raw=%r",
                stage,
                request.sid if request is not None else None,
                content[:8000],
            )

    def _log_decision_summary(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        stage: str,
        raw_summary: dict[str, Any] | None = None,
    ) -> None:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        summary = {
            "stage": stage,
            "sid": request.sid,
            "raw_route": (raw_summary or {}).get("raw_route"),
            "raw_intent": (raw_summary or {}).get("raw_intent"),
            "raw_fast_speech_present": (raw_summary or {}).get("raw_fast_speech_present"),
            "raw_routes_count": (raw_summary or {}).get("raw_routes_count"),
            "final_route": decision.route,
            "final_intent": decision.intent,
            "final_confidence": decision.confidence,
            "final_fast_speech_present": decision.fast_speech is not None,
            "final_routes_count": len(decision.routes or []),
            "metadata_keys": sorted(str(key) for key in metadata.keys())[:24],
            "changed_route": bool(raw_summary and (raw_summary.get("raw_route") not in {None, "", decision.route})),
            "changed_intent": bool(raw_summary and (raw_summary.get("raw_intent") not in {None, "", decision.intent})),
            "reason": decision.reason,
        }
        logger.info("goal_interpreter_normalize_result %s", _json_log(summary, max_chars=2200))

    async def warm_model(self, *, timeout_s: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": "Reply with exactly one word: ready",
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_ctx": self.num_ctx,
                "num_predict": 1,
            },
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        call_id = new_llm_call_id("goal_interpreter")
        started = time.perf_counter()
        data: dict[str, Any] | None = None
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s or max(self.timeout_s, 0.1),
                trust_env=False,
            ) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate", json=payload
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, TypeError, OllamaGenerationError) as exc:
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose="goal_interpreter",
                stage="startup_warm",
                transport="ollama.generate",
                request=payload,
                response=data,
                status="failed",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={},
                error={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise
        log_llm_call_evidence(
            logger,
            call_id=call_id,
            purpose="goal_interpreter",
            stage="startup_warm",
            transport="ollama.generate",
            request=payload,
            response=data,
            status="accepted",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            correlations={},
        )
        return data

    async def _chat(self, payload: dict[str, Any], *, stage: str) -> dict[str, Any]:
        timeout_s = self.review_timeout_s if stage in REVIEW_STAGES else self.timeout_s
        options = dict(payload.get("options") or {})
        prompt_chars = self._payload_prompt_chars(payload)
        preflight = ollama_prompt_preflight_diagnostics(
            prompt_chars=prompt_chars,
            options=options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        )
        for diagnostic in preflight:
            logger.log(
                diagnostic.level,
                "%s",
                colorize_for_cli(diagnostic.render(), diagnostic.level),
            )
        blocking_preflight = next(
            (
                item
                for item in preflight
                if item.event == "llm_prompt_budget_exceeded"
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking_preflight is not None:
            raise OllamaGenerationError(
                f"Goal Interpreter request rejected before inference: {blocking_preflight.render()}",
                failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": f"goal_interpreter:{stage}",
                    "model": payload.get("model") or self.model,
                    "stage": stage,
                    **blocking_preflight.fields,
                    "automatic_retry_allowed": False,
                    "context_reduction_allowed": False,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                    "_incident_evidence": {"request": payload},
                },
            )

        async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        self._validate_completion(payload, data, stage=stage)
        return data

    def _validate_completion(
        self,
        payload: dict[str, Any],
        data: dict[str, Any],
        *,
        stage: str,
    ) -> None:
        """Apply one output-budget policy to chat and generate transports."""

        options = dict(payload.get("options") or {})
        prompt_chars = self._payload_prompt_chars(payload)
        completion = ollama_completion_diagnostics(
            options=options,
            data=data,
            prompt_chars=prompt_chars,
        )
        for diagnostic in completion:
            logger.log(
                diagnostic.level,
                "%s",
                colorize_for_cli(diagnostic.render(), diagnostic.level),
            )
        blocking_completion = next(
            (
                item
                for item in completion
                if item.event in {"llm_output_truncated", "llm_prompt_truncated"}
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking_completion is not None:
            failure_class = (
                "output_truncated"
                if blocking_completion.event == "llm_output_truncated"
                else "prompt_truncated"
            )
            raise OllamaGenerationError(
                f"Goal Interpreter result rejected: {blocking_completion.render()}",
                failure_class=failure_class,
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": f"goal_interpreter:{stage}",
                    "model": payload.get("model") or self.model,
                    "stage": stage,
                    **blocking_completion.fields,
                    "automatic_retry_allowed": False,
                    "context_reduction_allowed": False,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                    "_incident_evidence": {
                        "request": payload,
                        "response": data,
                    },
                },
            )

    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: RouteRequest | None = None,
    ) -> dict[str, Any]:
        call_id = new_llm_call_id("goal_interpreter")
        started = time.perf_counter()
        self._log_payload_profile(payload, stage=stage, request=request)
        try:
            try:
                data = await self._chat(payload, stage=stage)
            except TypeError as exc:
                if "unexpected keyword argument 'stage'" not in str(exc):
                    raise
                data = await self._chat(payload)  # type: ignore[call-arg]
        except (httpx.HTTPError, ValueError, TypeError, OllamaGenerationError) as exc:
            log_llm_call_evidence(
                logger,
                call_id=call_id,
                purpose="goal_interpreter",
                stage=stage,
                transport="ollama.chat",
                request=payload,
                response=None,
                status="failed",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={"sid": request.sid if request is not None else None},
                error={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise
        self._log_response_summary(data, stage=stage, request=request)
        content = str(data.get("message", {}).get("content") or "")
        parsed_output: Any = None
        try:
            parsed_output = _extract_json_object(content)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
            pass
        log_llm_call_evidence(
            logger,
            call_id=call_id,
            purpose="goal_interpreter",
            stage=stage,
            transport="ollama.chat",
            request=payload,
            response=data,
            status="accepted",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            correlations={"sid": request.sid if request is not None else None},
            parsed_output=parsed_output,
        )
        return data

    @staticmethod
    def _payload_prompt_chars(payload: dict[str, Any]) -> int:
        total = 0
        for message in payload.get("messages") or []:
            if isinstance(message, dict):
                total += len(str(message.get("content") or ""))
        return total

    def _decision_from_response(
        self,
        request: RouteRequest,
        data: dict[str, Any],
        *,
        stage: str = "llm",
        allow_bounded_contract_recovery: bool = False,
    ) -> RouteDecision:
        content = data.get("message", {}).get("content", "")
        raw_summary = _raw_interpreter_output_summary(str(content or ""))
        parsed = _extract_json_object(content)
        if allow_bounded_contract_recovery:
            recovered_paths = self._remove_durable_fields_from_session_memory(parsed)
            if recovered_paths:
                metadata = parsed.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["contract_recovery"] = {
                    "strategy": "remove_durable_fields_from_explicit_session_memory",
                    "recovered_paths": recovered_paths,
                }
                parsed["metadata"] = metadata
                logger.warning(
                    "goal_interpreter_session_memory_contract_recovered "
                    "sid=%s stage=%s paths=%s",
                    request.sid,
                    stage,
                    recovered_paths,
                )
            discarded_progress_paths = self._discard_invalid_progress_proposals(parsed)
            if discarded_progress_paths:
                metadata = parsed.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                prior_recovery = metadata.get("contract_recovery")
                progress_recovery = {
                    "strategy": "discard_invalid_advisory_progress",
                    "recovered_paths": discarded_progress_paths,
                }
                if isinstance(prior_recovery, dict):
                    metadata["contract_recovery"] = {
                        "strategy": "bounded_contract_recovery",
                        "recoveries": [prior_recovery, progress_recovery],
                    }
                else:
                    metadata["contract_recovery"] = progress_recovery
                parsed["metadata"] = metadata
                logger.warning(
                    "goal_interpreter_invalid_progress_discarded "
                    "sid=%s stage=%s paths=%s",
                    request.sid,
                    stage,
                    discarded_progress_paths,
                )
        route_items = _route_items_from_parsed(parsed)
        dominant_route = _dominant_route_from_items(route_items)
        if "route" not in parsed and dominant_route:
            parsed["route"] = dominant_route
            item_intent = _first_route_item_intent(route_items, dominant_route)
            if item_intent and "intent" not in parsed:
                parsed["intent"] = item_intent
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned route_items; goal interpreter selected a compatible route result"
        if route_items:
            metadata = parsed.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.setdefault("route_items", route_items)
            parsed["metadata"] = metadata
        route_from_intent = str(parsed.get("intent") or "").strip()
        supplied_capability_ids = _capability_ids_from_request(request)
        route_value = str(parsed.get("route") or "").strip()
        routed_capability_id = _known_capability_id(route_value, supplied_capability_ids)
        intent_capability_id = _known_capability_id(route_from_intent, supplied_capability_ids)
        if "route" not in parsed and route_from_intent in ROUTE_NAMES:
            parsed["route"] = route_from_intent
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned intent-only route JSON; goal interpreter normalized route"
        elif "route" not in parsed and intent_capability_id:
            parsed["route"] = _route_for_capability_id(intent_capability_id, request)
            parsed["intent"] = f"capability:{intent_capability_id}"
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned intent-only capability JSON; goal interpreter normalized capability route"
        elif route_value and route_value not in ROUTE_NAMES and (
            routed_capability_id or intent_capability_id
        ):
            selected_capability_id = routed_capability_id or intent_capability_id
            parsed["route"] = _route_for_capability_id(selected_capability_id, request)
            parsed["intent"] = f"capability:{selected_capability_id}"
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned capability/skill id in route field; goal interpreter normalized capability route"
        elif intent_capability_id:
            if "|" in route_from_intent:
                metadata = parsed.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["non_authoritative_capability_intent_hint"] = (
                    route_from_intent.split("|", 1)[1].strip()[:160]
                )
                parsed["metadata"] = metadata
            parsed["route"] = _route_for_capability_id(intent_capability_id, request)
            parsed["intent"] = f"capability:{intent_capability_id}"
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned exact capability id as intent; goal interpreter normalized capability intent"
        if "confidence" not in parsed and parsed.get("route") not in {"interrupt", "ignore"}:
            parsed["confidence"] = max(0.72, self.confidence_threshold)
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned route-only JSON; goal interpreter applied default confidence"
        decision = RouteDecision.model_validate(parsed)
        finalized = finalize_decision(decision, request, source="llm")
        self._log_decision_summary(request, finalized, stage=stage, raw_summary=raw_summary)
        return finalized

    @staticmethod
    def _remove_durable_fields_from_session_memory(
        parsed: dict[str, Any],
    ) -> list[str]:
        """Remove only non-authoritative durable fields from explicit session memory.

        This recovery runs only after one model-owned typed repair attempt. It
        preserves the model's session/ephemeral/remember semantics and can only
        reduce persistence authority; contradictory profile, durable, forget, or
        clear operations continue to fail the typed contract.
        """

        recovered: list[str] = []
        containers: list[tuple[str, dict[str, Any]]] = [("memory_update", parsed)]
        routes = parsed.get("routes")
        if isinstance(routes, list):
            containers.extend(
                (f"routes[{index}].memory_update", item)
                for index, item in enumerate(routes)
                if isinstance(item, dict)
            )
        for path, container in containers:
            proposal = container.get("memory_update")
            if not isinstance(proposal, dict):
                continue
            if str(proposal.get("scope") or "session") != "session":
                continue
            if str(proposal.get("operation") or "remember") != "remember":
                continue
            if str(proposal.get("persistence_policy") or "ephemeral") != "ephemeral":
                continue
            for field in ("consent_basis", "retention_days"):
                if proposal.get(field) is not None:
                    proposal.pop(field, None)
                    recovered.append(f"{path}.{field}")
        return recovered

    @staticmethod
    def _discard_invalid_progress_proposals(parsed: dict[str, Any]) -> list[str]:
        """Fail closed per advisory progress item during one mechanical DTO retry.

        Fast progress is optional cognitive evidence, never a Goal or execution
        authorization.  Dropping an invalid item preserves the valid route
        judgment without guessing a missing field or manufacturing readiness.
        """

        raw_progress = parsed.get("progress")
        if not isinstance(raw_progress, list):
            return []
        retained: list[Any] = []
        discarded: list[str] = []
        for index, item in enumerate(raw_progress):
            try:
                FastProgressProposal.model_validate(item)
            except (ValidationError, ValueError, TypeError):
                discarded.append(f"progress[{index}]")
            else:
                retained.append(item)
        if discarded:
            parsed["progress"] = retained
        return discarded

    def _semantic_contract_error(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> str | None:
        """Return one terminal semantic-contract error without re-deciding meaning.

        The fast Goal Interpreter owns this one candidate. Deterministic code may
        reject contradictions and placeholders, but it does not call another model
        to rewrite the candidate. Low confidence remains explicit evidence for the
        existing Deep Thinking handoff in ``engine.py``.
        """

        if is_disallowed_model_control_route(request, decision):
            return (
                f"deterministic-only route {decision.route!r} was returned after "
                "the Gateway/emergency filter had already passed"
            )
        conflict = _route_intent_contract_conflict(request, decision)
        if conflict is not None:
            return conflict
        if (
            decision.route == "robot_action"
            and _is_placeholder_capability_intent(decision.intent)
        ):
            return "robot_action_placeholder_capability_intent"
        if (
            decision.route == "robot_action"
            and not decision.actions
            and str(decision.intent or "").strip() in {"", "unknown", "robot_action"}
        ):
            return "robot_action_missing_semantic_intent"
        return None

    async def _review_inactive_addressedness(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        """Review every inactive first turn before committing it to speech.

        The observed collapse changed labels across runs (capability inquiry,
        self-description, and generic chat). Addressedness therefore cannot be
        gated on a particular proposed intent. The reviewer may suppress a turn
        only with the narrow ambient-speech contract; otherwise the quick
        decision is preserved and normal route validation continues.
        """

        engagement = interaction_engagement(request)
        if (
            engagement.get("gate_enabled") is not True
            or engagement.get("active") is not False
            or decision.route == "interrupt"
        ):
            return decision
        try:
            reviewed = await self._chat_logged(
                self.build_addressedness_review_payload(request),
                stage="addressedness_review",
                request=request,
            )
            message = reviewed.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            reviewed_payload = _extract_json_object(str(content or ""))
            addressed = reviewed_payload.get("addressed")
            speech_act = str(reviewed_payload.get("speech_act") or "").strip().casefold()
            confidence = float(reviewed_payload.get("confidence"))
            if (
                not isinstance(addressed, bool)
                or speech_act
                not in DIRECTED_SPEECH_ACTS | SUPPRESSIBLE_INACTIVE_SPEECH_ACTS | {"unclear"}
                or not 0.0 <= confidence <= 1.0
            ):
                raise ValueError("invalid addressedness response")
        except Exception as exc:
            logger.warning(
                "inactive addressedness review failed sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return decision
        # Ambient suppression is intentionally fail-open. The model's typed
        # speech act owns addressedness semantics; punctuation is not a Host
        # substitute for that decision.
        if addressed or confidence < 0.72:
            return decision
        fail_open_reason = ""
        if speech_act in DIRECTED_SPEECH_ACTS:
            fail_open_reason = "direct_speech_act"
        elif speech_act == "unclear":
            fail_open_reason = "unclear_speech_act"
        elif speech_act not in SUPPRESSIBLE_INACTIVE_SPEECH_ACTS:
            fail_open_reason = "unsupported_speech_act"
        if fail_open_reason:
            logger.info(
                "inactive addressedness review failed open sid=%s reason=%s "
                "speech_act=%s confidence=%.2f route=%s intent=%s",
                request.sid,
                fail_open_reason,
                speech_act,
                confidence,
                decision.route,
                decision.intent,
            )
            return decision
        return finalize_decision(
            RouteDecision(
                route="ignore",
                intent="ambient_speech",
                confidence=confidence,
                language=request.language or decision.language or "auto",
                priority=decision.priority,
                needs_agent=False,
                should_speak=False,
                reason="reviewed inactive turn as unaddressed ambient speech",
                source="llm",
                metadata={
                    "semantic_addressedness_gate": True,
                    "addressedness_confidence": confidence,
                    "addressedness_speech_act": speech_act,
                    "host_engagement_evidence": engagement.get("evidence"),
                },
            ),
            request,
            source="llm",
        )

    async def route(self, request: RouteRequest) -> RouteDecision:
        """Run one fast interpretation with at most one mechanical DTO repair.

        Ordinary semantic output is never rewritten by a second Goal Interpreter.
        Low confidence remains explicit and is delegated by ``engine.py`` to the
        existing Deep Thinking path. Structural contradictions fail closed; they
        become reflection/evaluation evidence rather than an online repair chain.
        """

        payload = self.build_payload(request)
        invocation_families = ["goal_interpreter.primary"]
        contract_repair_attempted = False

        try:
            data = await self._chat_logged(
                payload,
                stage="quick_intent",
                request=request,
            )
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            logger.warning(
                "Ollama Goal Interpreter request failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return fallback_decision(
                request,
                reason=f"goal_interpreter_error:{type(exc).__name__}: {exc}",
            )

        content = str(data.get("message", {}).get("content") or "")
        try:
            decision = self._decision_from_response(
                request,
                data,
                stage="quick_intent",
            )
        except (ValueError, ValidationError) as exc:
            contract_repair_attempted = True
            invocation_families.append("goal_interpreter.dto_repair")
            logger.warning(
                "Invalid Goal Interpreter DTO: %s; content=%r",
                exc,
                content[:500],
            )
            try:
                repaired = await self._chat_logged(
                    self.build_contract_repair_payload(
                        request,
                        previous_content=content,
                        validation_error=exc,
                    ),
                    stage="quick_intent_contract_repair",
                    request=request,
                )
                decision = self._decision_from_response(
                    request,
                    repaired,
                    stage="quick_intent_contract_repair",
                    allow_bounded_contract_recovery=True,
                )
            except Exception as repair_exc:
                _raise_if_llm_budget_failure(repair_exc)
                logger.warning(
                    "Goal Interpreter DTO repair failed: %s",
                    repair_exc,
                )
                return fallback_decision(
                    request,
                    reason=(
                        "invalid_goal_interpreter_response_after_one_dto_repair: "
                        f"{type(repair_exc).__name__}: {repair_exc}"
                    ),
                )

        semantic_error = self._semantic_contract_error(request, decision)
        if semantic_error is not None:
            return fallback_decision(
                request,
                reason=f"goal_interpreter_semantic_contract_failed:{semantic_error}",
            )

        # Maintained requests are already admitted by Cognitive Gateway. Keep the
        # legacy inactive addressedness review only for explicit compatibility
        # callers and historical replays; it is not an ordinary repair path.
        if request.context.get("gateway_admission_complete") is not True:
            decision = await self._review_inactive_addressedness(request, decision)
            semantic_error = self._semantic_contract_error(request, decision)
            if semantic_error is not None:
                return fallback_decision(
                    request,
                    reason=(
                        "goal_interpreter_compatibility_review_contract_failed:"
                        f"{semantic_error}"
                    ),
                )

        metadata = dict(decision.metadata or {})
        metadata["goal_interpreter_transaction"] = {
            "logical_invocation_count": len(invocation_families),
            "logical_invocation_budget": 2,
            "prompt_families": invocation_families,
            "contract_repair_attempted": contract_repair_attempted,
            "semantic_repair_attempted": False,
            "terminal_state": "accepted",
        }
        return decision.model_copy(update={"metadata": metadata})
