from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ...clients.ollama_client import OllamaGenerationError
from ...settings import agent_service_settings

try:
    from chromie_runtime.llm_diagnostics import (
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.log_colors import colorize_for_cli
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.llm_diagnostics import (
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.log_colors import colorize_for_cli

from .fallback import fallback_decision


def _raise_if_llm_budget_failure(exc: Exception) -> None:
    """Never reinterpret prompt/output truncation as user-semantic uncertainty."""

    if (
        isinstance(exc, OllamaGenerationError)
        and exc.failure_domain == "llm_budget"
    ):
        raise exc
from .schema import FastSpeech, RouteDecision, RouteRequest, finalize_decision


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
    "intent_review",
    "post_interrupt_review",
    "semantic_route_repair",
    "capability_grounding_review",
    "fast_speech_repair",
}


class SemanticRouteRepairDesiredAbility(BaseModel):
    """One understood but currently unavailable user ability request."""

    model_config = ConfigDict(extra="forbid")

    ability_id: str = Field(min_length=3, max_length=160)
    intent: str = Field(min_length=1, max_length=240)
    status: Literal["missing_ability"] = "missing_ability"
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class SemanticRouteRepairMetadata(BaseModel):
    """Bounded metadata allowed only for terminal missing-ability repair."""

    model_config = ConfigDict(extra="forbid")

    desired_abilities: list[SemanticRouteRepairDesiredAbility] = Field(
        min_length=1,
        max_length=4,
    )


class SemanticRouteRepairOutput(BaseModel):
    """Bounded semantic repair DTO with an honest missing-ability terminal."""

    model_config = ConfigDict(extra="forbid")

    route: str
    intent: str = Field(min_length=1, max_length=120)
    confidence: float = Field(ge=0.0, le=1.0)
    speak_first: str | None = Field(default=None, min_length=1, max_length=240)
    metadata: SemanticRouteRepairMetadata | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_missing_ability_intent(
        cls, value: Any
    ) -> Any:
        """Canonicalize model wording for the typed missing-ability branch.

        The semantic repair model may express the same branch with a nearby
        label (for example ``missing_or_supported_ability``).  Metadata carrying
        ``desired_abilities`` is already an unambiguous declaration that the
        model selected the missing-ability branch, so normalize it before the
        strict branch validator runs.  This is contract normalization only; it
        does not infer an ability from user text or catalog keywords.
        """

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        intent = "_".join(
            str(normalized.get("intent") or "")
            .strip()
            .casefold()
            .replace("-", "_")
            .split()
        )
        metadata = normalized.get("metadata")
        has_desired_abilities = (
            isinstance(metadata, dict)
            and isinstance(metadata.get("desired_abilities"), list)
            and bool(metadata.get("desired_abilities"))
        )
        missing_aliases = {
            "missing_or_unsupported_ability",
            "missing_or_supported_ability",
            "missing_ability",
            "unsupported_ability",
            "ability_unavailable",
            "capability_missing",
        }
        if has_desired_abilities or intent in missing_aliases:
            normalized["intent"] = "missing_or_unsupported_ability"
        return normalized

    @model_validator(mode="after")
    def validate_missing_ability_terminal(self) -> "SemanticRouteRepairOutput":
        is_missing = self.intent == "missing_or_unsupported_ability"
        if is_missing:
            if self.route != "clarify":
                raise ValueError(
                    "missing_or_unsupported_ability requires route=clarify"
                )
            if not str(self.speak_first or "").strip():
                raise ValueError(
                    "missing_or_unsupported_ability requires truthful speak_first"
                )
            if self.metadata is None or not self.metadata.desired_abilities:
                raise ValueError(
                    "missing_or_unsupported_ability requires desired_abilities"
                )
        elif self.metadata is not None:
            raise ValueError(
                "desired_abilities metadata is allowed only for missing ability"
            )
        return self


def _validate_missing_ability_output_against_catalog(
    output: SemanticRouteRepairOutput,
    request: RouteRequest,
) -> None:
    """Keep a missing-ability request distinct from available capabilities."""

    if (
        output.intent != "missing_or_unsupported_ability"
        or output.metadata is None
    ):
        return
    available_ids = _capability_ids_from_request(request)
    collisions = sorted(
        item.ability_id
        for item in output.metadata.desired_abilities
        if item.ability_id in available_ids
    )
    if collisions:
        raise ValueError(
            "missing ability_id must describe the absent user-facing ability, "
            "not reuse an available capability_id: "
            + ", ".join(collisions)
        )


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
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        value = request.context.get(key, [])
        if isinstance(value, list) and value:
            return value
    return []


def _capability_ids_from_request(request: RouteRequest) -> set[str]:
    capability_ids: set[str] = set()
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        value = request.context.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
            if capability_id:
                capability_ids.add(capability_id)
    return capability_ids


def _capability_route_lookup_from_request(request: RouteRequest) -> dict[str, str]:
    routes: dict[str, str] = {}
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        value = request.context.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
            route = str(item.get("route") or "").strip()
            if capability_id and route in ROUTE_NAMES and capability_id not in routes:
                routes[capability_id] = route
    return routes


def _route_intent_contract_conflict(
    request: RouteRequest,
    decision: RouteDecision,
) -> str | None:
    """Return a structural route/intent conflict without interpreting user text.

    Semantic repair is delegated to a model. This guard only notices that the
    model's own output contradicts a declared route contract.
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
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        items = request.context.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
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



FAST_SPEECH_REPAIR_ROUTES = {
    "tool",
    "robot_action",
    "deep_thought",
    "memory",
}

FAST_SPEECH_ROUTE_CONTRACTS = {
    "tool": ("acknowledge_and_check", "checking_only"),
    "robot_action": ("acknowledge", "prelude_only"),
    "deep_thought": ("thinking", "prelude_only"),
    "memory": ("acknowledge", "prelude_only"),
}


def _fast_speech_matches_route_contract(
    route: str,
    fast_speech: FastSpeech | None,
) -> bool:
    expected = FAST_SPEECH_ROUTE_CONTRACTS.get(route)
    if expected is None or fast_speech is None:
        return False
    purpose, commitment = expected
    return bool(str(fast_speech.text or "").strip()) and (
        fast_speech.purpose == purpose
        and fast_speech.commitment == commitment
        and fast_speech.claim_state == "none"
        and not fast_speech.claimed_capability_ids
        and not fast_speech.claimed_goal_ids
        and fast_speech.must_not_claim_completion is True
    )


def _decision_has_route_valid_fast_speech(decision: RouteDecision) -> bool:
    if _fast_speech_matches_route_contract(decision.route, decision.fast_speech):
        return True
    return any(
        _fast_speech_matches_route_contract(item.route, item.fast_speech)
        for item in (decision.routes or [])
    )


def _decision_needs_goal_interpretation_fast_speech(decision: RouteDecision) -> bool:
    if _decision_has_route_valid_fast_speech(decision):
        return False
    if decision.route in FAST_SPEECH_REPAIR_ROUTES:
        return True
    return any(item.route in FAST_SPEECH_REPAIR_ROUTES for item in (decision.routes or []))


def _pending_work_fast_speech_target_route(decision: RouteDecision) -> str:
    if decision.route in FAST_SPEECH_ROUTE_CONTRACTS:
        return decision.route
    return next(
        (
            item.route
            for item in (decision.routes or [])
            if item.route in FAST_SPEECH_ROUTE_CONTRACTS
        ),
        "deep_thought",
    )


def _decision_with_goal_interpretation_fast_speech(
    decision: RouteDecision,
    fast_speech: FastSpeech,
    *,
    reason_suffix: str,
    stage: str,
    replace_existing: bool = False,
) -> RouteDecision:
    updated_items = []
    attached_to_item = False
    for item in decision.routes or []:
        if (
            not attached_to_item
            and item.route in FAST_SPEECH_REPAIR_ROUTES
            and (
                replace_existing
                or not _fast_speech_matches_route_contract(
                    item.route,
                    item.fast_speech,
                )
            )
        ):
            item = item.model_copy(update={"fast_speech": fast_speech})
            attached_to_item = True
        updated_items.append(item)

    metadata = dict(decision.metadata or {})
    metadata.setdefault("fast_speech_repair", {})
    if isinstance(metadata["fast_speech_repair"], dict):
        metadata["fast_speech_repair"].update(
            {
                "stage": stage,
                "model_generated": True,
                "commitment": fast_speech.commitment,
                "purpose": fast_speech.purpose,
                "claim_state": fast_speech.claim_state,
                "claimed_capability_ids": list(fast_speech.claimed_capability_ids),
                "claimed_goal_ids": list(fast_speech.claimed_goal_ids),
            }
        )
    reason = (f"{decision.reason}; " if decision.reason else "") + reason_suffix
    return decision.model_copy(
        update={
            "fast_speech": fast_speech,
            "routes": updated_items,
            "metadata": metadata,
            "reason": reason,
        }
    )


def _decision_without_goal_interpretation_fast_speech(
    decision: RouteDecision,
    *,
    reason_suffix: str,
    stage: str,
) -> RouteDecision:
    previous_text = str(
        getattr(decision.fast_speech, "text", "") or ""
    ).strip()
    updated_items = [
        item.model_copy(update={"fast_speech": None})
        if item.route in FAST_SPEECH_REPAIR_ROUTES
        else item
        for item in (decision.routes or [])
    ]
    metadata = dict(decision.metadata or {})
    metadata["fast_speech_review"] = {
        "stage": stage,
        "model_reviewed": True,
        "speech_selected": False,
    }
    speak_first = decision.speak_first
    if previous_text and str(speak_first or "").strip() == previous_text:
        speak_first = None
    reason = (f"{decision.reason}; " if decision.reason else "") + reason_suffix
    return decision.model_copy(
        update={
            "fast_speech": None,
            "speak_first": speak_first,
            "routes": updated_items,
            "metadata": metadata,
            "reason": reason,
        }
    )


def _compact_schema_field(name: str, prop: dict[str, Any]) -> str:
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
    return ":".join(parts)


def _compact_prompt_capabilities(candidates: Any, *, limit: int = 96) -> list[dict[str, Any]]:
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
                if (
                    str(name) not in required_set
                    and not (isinstance(enum, list) and enum)
                    and not (isinstance(unit, str) and unit.strip())
                ):
                    continue
                field = _compact_schema_field(str(name), prop)
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


def _goal_interpretation_fast_context_section(mind: Any) -> str:
    """Minimal context for the fast Goal Interpreter.

    The fast Goal Interpreter should decide whether a task needs the full mind profile;
    it should not always pay for worldview/lifeview/valueview tokens itself.
    Deepthinking and capability prompts still receive richer mind context.
    """

    identity = {}
    if isinstance(mind, dict):
        self_model = mind.get("self_model")
        speaker = self_model.get("speaker_entity") if isinstance(self_model, dict) else None
        if isinstance(speaker, dict):
            identity = {
                "profile_id": mind.get("profile_id"),
                "version": mind.get("version"),
                "entity_id": speaker.get("entity_id"),
                "name": speaker.get("name"),
                "kind": speaker.get("kind"),
            }
        elif isinstance(mind.get("identity"), dict):
            raw_identity = mind["identity"]
            identity = {
                "profile_id": mind.get("profile_id"),
                "version": mind.get("version"),
                "entity_id": raw_identity.get("entity_id"),
                "name": raw_identity.get("name"),
                "kind": raw_identity.get("kind"),
                "age_description": raw_identity.get("age_description"),
                "identity_answer_guidance": raw_identity.get("identity_answer_guidance"),
            }
    return (
        "Fast Goal Interpretation Context:\n"
        f"{_bounded_json(identity or {'entity_id': 'chromie', 'name': 'Chromie'}, max_chars=180)}\n"
        "The full owner-approved mind profile, worldview, lifeview, valueview, "
        "long-term goals, and core principles are downstream only. "
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
        review_model: str | None = None,
        timeout_ms: int,
        review_timeout_ms: int | None = None,
        confidence_threshold: float,
        slow_review_recovery_enabled: bool = True,
        generic_chat_review_enabled: bool = True,
        pending_work_fast_speech_repair_enabled: bool = False,
        num_ctx: int = 4096,
        num_predict: int = 512,
        keep_alive: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.review_model = (review_model or "").strip()
        self.timeout_s = max(0.1, timeout_ms / 1000.0)
        self.review_timeout_s = max(
            0.1,
            (review_timeout_ms if review_timeout_ms is not None else timeout_ms) / 1000.0,
        )
        self.confidence_threshold = confidence_threshold
        self.slow_review_recovery_enabled = slow_review_recovery_enabled
        self.generic_chat_review_enabled = bool(generic_chat_review_enabled)
        self.pending_work_fast_speech_repair_enabled = bool(
            pending_work_fast_speech_repair_enabled
        )
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
        active_tasks_json = _bounded_json_array(
            _compact_active_task_snapshots(request.context),
            max_chars=1800,
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
            f"Active Task Snapshot JSON:{active_tasks_json}\n\n"
            f"{recent_goals_section}"
            "Current Job:\n"
            "fast goal-interpretation and lane proposer. The deterministic emergency/noise filter ran. Decide from meaning, bounded context. Terminal references do not reopen Goals. Memory writes use route=memory; supplied-memory recall uses route=chat. This is bounded cognitive evidence, not final goal meaning. Return calibrated confidence; do not answer, execute, or authorize side effects.\n\n"
            "Task Context Group:\n"
            f"Latest user input: {request.text}\n"
            f"Common ability IDs: {_bounded_json(common_ability_ids, max_chars=420)}\n"
            f"Common Ability Catalog JSON: {common_ability_catalog_json}\n"
            "Task Continuity:\n"
            "Use active and recent Goals semantically, never keywords, regexes, overlap, or recency alone. Safe-read status follow-ups preserve exact arguments and resume only without completed evidence; completed-Goal references use delivered evidence without reopening or rereading. New or corrected lookup bindings inherit the external-read responsibility and require fresh exact reads; never relabel old results. When the user supplies an exact replacement binding, preserve it verbatim. Provider canonicalization or ambiguity belongs to the capability, not this boundary. Clarify only genuinely underdetermined user meaning. One responsibility is one route item.\n"
            "Capability Affordance Proposal:\n"
            "Semantic first. Catalog is a compact body/tool affordance interface, not a phrase table. These are candidate proposals, not authoritative grounding. capability_inquiry is only for an inquiry about Chromie's bounded abilities; technical discussion about another person, model, vehicle, sensor, or system is not a Chromie capability inquiry. Distinguish an availability inquiry from a request to execute by the user's intended speech act and context: inquiries remain chat/capability_inquiry, while execution requests may use robot_action. Standalone social acts stay chat; social framing attached to a substantive request never replaces its substantive lane. Bind an exact capability only for an explicit execution method with one clear match. One parameterized capability may leave args to CapabilityAgent; compound explicit capabilities use ordered actions[]. Isolated letters and low-information ASR fragments clarify. Outcome requests with multiple methods or missing context use deep_thought with an open goal. For current external facts, choose a trusted lookup by meaning and context, not keywords. Exact match: route=tool and intent=capability:<exact capability_id>, not a domain label. Missing ability -> non-executable ability proposals in metadata.desired_abilities. Never claim completion or output raw motor/joint/actuator/controller-array/torque commands.\n\n"
            "Cost Function:\n"
            "Preserve task continuity before creating unnecessary tasks; update goals before plans. Speech-only conversation and capability availability inquiry=chat; requested catalog execution=robot_action; lookup=tool; situational planning=deep_thought; ambiguity=clarify. Never return interrupt or ignore; a separate focused addressedness stage owns bounded ambient suppression.\n\n"
            "Output Contract:\n"
            "Return one compact JSON object. Required keys: route, intent, confidence. route=memory writes; supplied-memory recall is route=chat. memory_update follows its typed schema: session/ephemeral by default; durable profile only with explicit current-turn consent. routes[] split responsibilities; actions[] carry exact capability_id, args, sequence, timing, confidence (\"confidence\":0.0 marks unknown) only for explicit capabilities. metadata.semantic_task_operations may contain operation_id, operation, target_task_ids, goal/goal_update, information_gaps, resolved_gap_ids, requires_replan, response_plan, confidence, reason_summary. create requires goal.description and source_text; later operations use supplied task IDs. Pending work may include optional process acknowledgement in fast_speech; silence is valid. Lifecycle pairs: tool=acknowledge_and_check/checking_only; robot_action=acknowledge/prelude_only; deep_thought=thinking/prelude_only; memory=acknowledge/prelude_only. Before Goals exist, use claim_state=none with empty claim IDs; never claim result, motion, memory commit, or completion. fast_speech/speak_first use human-like social warmth, not a program, programme, or backend. Omit agents, metadata, candidate_capabilities, explanations unless needed. No chain-of-thought, analysis, progress text, scratchpad, markdown, or text outside JSON."
        )

    @staticmethod
    def _fast_speech_choice_schema(
        *,
        purpose: str,
        commitment: str,
    ) -> dict[str, Any]:
        return {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "text",
                        "purpose",
                        "commitment",
                        "claim_state",
                        "claimed_capability_ids",
                        "claimed_goal_ids",
                        "must_not_claim_completion",
                    ],
                    "properties": {
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 120,
                        },
                        "purpose": {"type": "string", "enum": [purpose]},
                        "commitment": {
                            "type": "string",
                            "enum": [commitment],
                        },
                        "claim_state": {"type": "string", "const": "none"},
                        "claimed_capability_ids": {
                            "type": "array",
                            "maxItems": 0,
                            "items": {"type": "string"},
                        },
                        "claimed_goal_ids": {
                            "type": "array",
                            "maxItems": 0,
                            "items": {"type": "string"},
                        },
                        "must_not_claim_completion": {"const": True},
                    },
                },
            ]
        }

    def build_fast_speech_repair_payload(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> dict[str, Any]:
        target_route = _pending_work_fast_speech_target_route(decision)
        expected_purpose, expected_commitment = FAST_SPEECH_ROUTE_CONTRACTS[
            target_route
        ]
        decision_json = _bounded_json(
            decision.model_dump(mode="json", exclude_none=True),
            max_chars=2400,
        )
        abilities_json = _bounded_json(
            _compact_candidate_capabilities(
                _review_capabilities_from_request(request), limit=12
            ),
            max_chars=1800,
        )
        session_context = _bounded_json(
            _goal_interpretation_prompt_context(request.context),
            max_chars=1200,
        )
        mind_context = _bounded_json(request.context.get("mind", {}), max_chars=2200)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fast_speech"],
                "properties": {
                    "fast_speech": self._fast_speech_choice_schema(
                        purpose=expected_purpose,
                        commitment=expected_commitment,
                    )
                },
            },
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Current Job:\n"
                        "- You are Chromie's fast-speech repairer and author. Decide whether speaking immediately is useful; silence is a valid choice.\n"
                        f"- The current semantic lane is route={target_route}. Goal Association and planning have not happened yet.\n"
                        "- If you speak, choose the exact wording yourself from the supplied owner-approved mind and style context, current user turn, language, and situation. Do not use a universal or canned acknowledgement.\n"
                        "- Do not change route, intent, metadata, tool arguments, capabilities, or safety policy.\n\n"
                        "Authority Boundary:\n"
                        "- This is before authoritative Goals, Plans, authorization, execution, and results.\n"
                        "- The speech may acknowledge, wonder, think, or ask a genuinely needed clarification, but it must not semantically claim a capability, action plan, motion, exact distance, object handling, result, memory commit, safe completion, or completed responsibility.\n"
                        "- Identity and personality shape voice only; they never prove ability.\n- For read-only work, mention only exact model-authored bindings already present in the interpretation decision.\n"
                        "- Set claim_state=none and leave claimed_capability_ids and claimed_goal_ids empty.\n"
                        "- If no natural and useful sentence exists, return fast_speech=null.\n\n"
                        "Style Boundary:\n"
                        "- Apply the supplied mind/personality settings naturally. Chromie should sound like herself—a warm six-year-old child in her family—not customer service, an adult operator, or a robot status system.\n"
                        "- Do not announce her age or role unless the user asks about identity. Do not force childish vocabulary.\n"
                        "- Use semantic reasoning, never phrase matching or a fixed sentence template.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with exactly one key fast_speech.\n"
                        f"- If non-null, use purpose={expected_purpose}, commitment={expected_commitment}, claim_state=none, empty claim-ID arrays, and must_not_claim_completion=true.\n"
                        "- Do not output markdown, analysis, scratchpad, or text outside JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Latest user input: {request.text}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Owner-approved mind and style context JSON: {mind_context}\n"
                        f"Existing interpretation decision JSON: {decision_json}\n"
                        f"Bounded session context JSON: {session_context}\n"
                        f"Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0.35,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": min(256, max(96, self.num_predict)),
            },
        }

    def build_fast_speech_review_payload(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        candidate: FastSpeech,
    ) -> dict[str, Any]:
        target_route = _pending_work_fast_speech_target_route(decision)
        expected_purpose, expected_commitment = FAST_SPEECH_ROUTE_CONTRACTS[
            target_route
        ]
        mind_context = _bounded_json(request.context.get("mind", {}), max_chars=2200)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fast_speech"],
                "properties": {
                    "fast_speech": self._fast_speech_choice_schema(
                        purpose=expected_purpose,
                        commitment=expected_commitment,
                    )
                },
            },
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Chromie's independent fast-speech semantic and style reviewer. Goal Association and planning have not happened yet. Review meaning, not keywords.\n"
                        "- Decide whether the candidate should be preserved, naturally rewritten in Chromie's supplied style, or removed by returning null.\n"
                        "- The spoken text must agree with claim_state=none and empty capability/goal claim arrays. It must not imply that an action is planned, authorized, started, completed, safe, or within Chromie's ability.\n"
                        "- Do not replace every case with one standard acknowledgement. Silence is valid.\n"
                        "- Identity shapes expression only and never grants capability.\n"
                        "- Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Latest user input: {request.text}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Owner-approved mind and style context JSON: {mind_context}\n"
                        "Candidate fast_speech JSON: "
                        f"{_bounded_json(candidate.model_dump(mode='json'), max_chars=1800)}\n"
                        "Interpretation decision JSON: "
                        f"{_bounded_json(decision.model_dump(mode='json', exclude_none=True), max_chars=2600)}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": min(256, max(96, self.num_predict)),
            },
        }

    @staticmethod
    def _route_response_schema() -> dict[str, Any]:
        schema = RouteDecision.model_json_schema()
        properties = schema.get("properties", {})
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

    def build_intent_review_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = json.dumps(
            _compact_candidate_capabilities(
                _review_capabilities_from_request(request),
                limit=16,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_goal_interpretation_prompt_context(request.context), max_chars=2400)
        return {
            "model": self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": self._route_response_schema(),
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_goal_interpretation_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n\n"
                        "Current Job:\n"
                        "- You are now acting as Chromie's semantic route reviewer.\n"
                        "- Use semantic generalization from meaning, session context, and supplied common ability descriptions.\n"
                        "- Do not use phrase rules, and do not turn prompt wording into keyword rules.\n"
                        "- The deterministic emergency/noise filter already passed before this review.\n\n"
                        "Task Context Group:\n"
                        "- Review the latest user input and decide whether the quick route should be chat, deep_thought, robot_action, tool, memory, clarify, interrupt, or ignore.\n"
                        "- Body/head/gaze/motion/expression requests are robot_action when an available interaction_executable common ability can satisfy them.\n"
                        "- Capability questions can be polite requests; if the user is pragmatically asking Chromie to perform a listed physical action now, choose robot_action.\n"
                        "- capability_inquiry applies only when the user is asking about Chromie's abilities, not when discussing capabilities of another person, model, vehicle, sensor, or system.\n"
                        "- Identity, status, factual, greeting, joke, story, song, and other speech-only requests are chat unless a supplied executable Capability is explicitly selected.\n"
                        "- For external information, use tool only when the model selects an exact supplied Capability; domain methods come from disclosed Agent Skills, not Host topic rules.\n"
                        "- Never choose ignore. A separate focused addressedness stage owns bounded ambient suppression.\n"
                        "- Use working memory, task context, and recent action history for follow-up resolution, but not as authorization for side effects.\n"
                        "- Choose deep_thought for complex reasoning, debugging, design, implementation planning, or multi-step task-session work.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only. Required keys are route, intent, and confidence; metadata and fast_speech are allowed when they change downstream routing or immediate user acknowledgement.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify, interrupt, ignore.\n"
                        "- fast_speech, when present, must be a short process acknowledgement only. It must not claim completion, physical execution, memory commit, or a tool result.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- Never choose interrupt or ignore.\n"
                        "- If selecting a known common ability, set intent to capability:<exact capability_id>; otherwise use a short generic semantic intent."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

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

    def build_deterministic_route_repair_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = json.dumps(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_goal_interpretation_prompt_context(request.context), max_chars=2400)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_goal_interpretation_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n\n"
                        "Current Job:\n"
                        "- Repair a realtime robot route after the deterministic emergency/noise filter already passed.\n"
                        "- The fast goal interpreter incorrectly returned a deterministic-only route; choose the best non-deterministic route from semantic meaning, context, and common abilities.\n"
                        "- Decide from meaning and common ability descriptions, not phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- If the user is asking Chromie to perform an available interaction_executable physical capability now, choose robot_action.\n"
                        "- Use deep_thought for complex reasoning or planning that should leave the quick route path.\n\n"
                        "- Use task context and recent action history for follow-ups, but never as standalone authorization.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with required keys route, intent, and confidence. metadata and fast_speech are allowed for tool lookups.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify.\n"
                        "- fast_speech must be a short process acknowledgement only; never claim tool results, physical completion, or memory commit.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- Do not use interrupt or ignore.\n"
                        "- For a selected capability, set intent to capability:<exact capability_id>. Domain-specific bindings belong in the typed route item or metadata authored by the model.\n"
                        "- Confidence is semantic routing confidence; use at least 0.72 when the request clearly maps to a common ability."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

    def build_semantic_route_repair_payload(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        reason: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        # The common catalog is ordered by route, which intentionally places
        # tool affordances after common embodied actions.  Keep the complete
        # bounded common projection here: taking only the first few entries can
        # hide the exact affordance that made this semantic repair necessary.
        abilities_json = _bounded_json_array(
            _compact_prompt_capabilities(
                _review_capabilities_from_request(request),
                limit=24,
            ),
            max_chars=3600,
        )
        session_context = _bounded_json(
            _goal_interpretation_prompt_context(request.context),
            max_chars=900,
        )
        previous = {
            "route": decision.route,
            "intent": decision.intent,
            "confidence": decision.confidence,
        }
        recent_goals_json = _bounded_json_array(
            _compact_recent_goal_snapshots(request.context),
            max_chars=1400,
        )
        verified_tool_index_json = _bounded_json_array(
            _compact_verified_tool_memory_index(request.context),
            max_chars=1600,
        )
        mind = request.context.get("mind", {})
        global_context = _goal_interpretation_global_context_section(mind)
        return {
            "model": model or self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": SemanticRouteRepairOutput.model_json_schema(),
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{global_context}\n\n"
                        "Current Job:\n"
                        "Repair one semantic route from the latest user turn. "
                        "Runtime diagnostics and the rejected decision are not user-semantic evidence. "
                        "First understand the requested outcome independently of the catalog, then compare that outcome with exact supplied ability descriptions. "
                        "Return route, intent, and confidence, plus speak_first and metadata only for a terminal missing-ability result. "
                        "Valid routes are chat, deep_thought, robot_action, tool, memory, and clarify. "
                        "A standalone greeting or thanks remains chat, but social framing attached "
                        "to a substantive request must not replace the substantive lane. "
                        "A topical match to a Capability is not itself an execution request. When "
                        "the latest turn asks to interpret, clarify, or restate a retained completed "
                        "Goal and the bounded verified-tool index already contains its result "
                        "provenance, retain chat unless the user requests new bindings or fresh data. "
                        "A material binding correction to an external-read Goal requires a new exact read "
                        "when the corrected answer still depends on external facts. Never relabel an older "
                        "result with the corrected binding or present the old facts as the corrected entity's result. "
                        "When the latest turn supplies an exact replacement binding for that read, preserve it "
                        "verbatim and continue the existing lookup responsibility. Do not ask the user to perform "
                        "provider canonicalization or add administrative granularity merely because multiple "
                        "real-world matches might exist; the selected Capability must resolve the supplied value "
                        "or report its own ambiguity. "
                        "Use tool only when the model selects an exact supplied external-read Capability. "
                        "For an exact executable body capability, use robot_action and intent=capability:<exact supplied id>. "
                        "Never substitute the nearest topical Capability merely because it shares an entity or binding such as a location, date, number, or person. "
                        "Use the terminal missing-ability result only when the latest user turn itself asks Chromie for a clear lookup, recommendation, or action that no exact supplied Capability can perform. "
                        "A bare location, preference, entity name, correction, or other context statement is not a missing ability by itself; retain chat so Goal Association can decide whether it continues an earlier Goal or is independent. "
                        "When the requested outcome is clear but no exact supplied Capability can perform it, do not ask for parameters that cannot make an absent ability executable and do not imply that Chromie will check. "
                        "Return route=clarify, intent=missing_or_unsupported_ability, one brief truthful speak_first sentence in the user's language, and metadata.desired_abilities with status=missing_ability, a stable semantic ability_id, the understood intent, confidence, and reason. "
                        "The missing ability_id names the absent user-facing ability. It must not equal or reuse any capability_id in Supplied abilities JSON; for example, a restaurant request must not be recorded as chromie.weather.lookup merely because both use a location. "
                        "The terminal speak_first is the complete final response for this turn. It must not ask a follow-up question, request a location or preference, or end with a question mark. "
                        "Apply the owner-approved identity and personality from Global Context naturally. Chromie should sound like herself: a warm six-year-old child in her family, not customer service, an adult operator, or a software error message. "
                        "Prefer simple learning language such as '我现在还没学会这个呢' over formal system language such as '我无法直接查询'. Chromie may warmly hope to learn the ability later, but must not claim that learning has started or guarantee that the ability will be added. "
                        "Use intent=clarify_uncertain_request only when the user's meaning itself remains genuinely underdetermined, or when one exact supplied Capability exists but requires a user-provided binding before provider resolution. Never pair route=chat with a clarification intent. "
                        "No analysis, rationale, actions, markdown, or fields outside the declared schema."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Repair reason: {reason}\n"
                        f"Latest user input: {request.text}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Bounded context JSON: {session_context}\n"
                        f"Recent terminal Goal snapshot JSON: {recent_goals_json}\n"
                        f"Verified completed tool-memory index JSON: {verified_tool_index_json}\n"
                        f"Supplied abilities JSON: {abilities_json}\n"
                        f"Rejected minimal decision JSON: {_bounded_json(previous, max_chars=500)}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": 512,
            },
        }

    def build_placeholder_capability_repair_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = _bounded_json(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            max_chars=1800,
        )
        session_context = _bounded_json(_context_without_prompt_globals(request.context), max_chars=1400)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Current Job:\n"
                        "- Repair a malformed route for Chromie after the emergency/noise filter already passed.\n"
                        "- The fast goal interpreter returned robot_action with a placeholder capability intent instead of a real capability ID.\n"
                        "- Decide from semantic meaning, bounded context, and common abilities, not phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- Speech-only conversation and questions about whether an ability is available are chat; use a semantic intent such as capability_inquiry when appropriate.\n"
                        "- A request to perform an available interaction_executable physical capability now is robot_action. Decide inquiry versus execution from meaning and context, not phrase patterns.\n"
                        "- Use deep_thought for complex reasoning or planning.\n\n"
                        "- Use working memory, task context, and recent action history to resolve follow-ups, but not to authorize side effects.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with keys route, intent, and confidence.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- For robot_action with a selected skill, set intent to capability:<exact capability_id> from the common ability catalog.\n"
                        "- Never return placeholder intents such as capability or capability:<exact capability_id>.\n"
                        "- Confidence is semantic routing confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Latest user input: {request.text}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Bounded session context JSON: {session_context}\n"
                        f"Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

    def build_post_interrupt_review_payload(
        self,
        request: RouteRequest,
        interrupt_decision: RouteDecision,
    ) -> dict[str, Any]:
        abilities_json = _bounded_json(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            max_chars=1800,
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_context_without_prompt_globals(request.context), max_chars=1800)
        interrupt_json = _bounded_json(
            {
                "route": interrupt_decision.route,
                "intent": interrupt_decision.intent,
                "confidence": interrupt_decision.confidence,
                "reason": interrupt_decision.reason,
                "source": interrupt_decision.source,
            },
            max_chars=500,
        )
        return {
            "model": self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": "json",
            **({"keep_alive": self.keep_alive} if self.keep_alive else {}),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_goal_interpretation_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n"
                        f"- Already-applied emergency-filter decision JSON: {interrupt_json}\n\n"
                        "Current Job:\n"
                        "- You are Chromie's post-interrupt semantic reviewer.\n"
                        "- The host has already applied the deterministic interrupt/cancel lane immediately for safety.\n"
                        "- Your job is only to confirm that interpretation or propose the correct non-interrupt route if the text was misheard/misread.\n"
                        "- Decide from meaning, context, and supplied abilities; do not create phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- Choose interrupt when the user truly asked to stop, cancel, pause, be quiet, or halt current work.\n"
                        "- Choose a non-interrupt route when the text merely mentions stop, uses stop in another meaning, or asks for a different chat/tool/memory/body task.\n"
                        "- If correcting to robot_action, use intent capability:<exact capability_id> when a supplied common ability clearly fits.\n"
                        "- Physical actions are still only proposals; downstream planning and the Trusted Capability Runtime must validate and confirm them.\n\n"
                        "Output Contract:\n"
                        "- Return one compact RouteDecision JSON object.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify, interrupt, ignore.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- If the emergency interpretation was correct, return route=interrupt and intent=stop_current_output.\n"
                        "- If it was a misunderstanding, return the corrected non-interrupt route with confidence >= 0.72 when clear.\n"
                        "- For a correction, speak_first may contain one brief apology/correction sentence, but must not claim a physical action or tool side effect has executed."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": max(128, self.num_predict),
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
        async with httpx.AsyncClient(
            timeout=timeout_s or max(self.timeout_s, 0.1),
            trust_env=False,
        ) as client:
            response = await client.post(f"{self.ollama_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()

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
        return data


    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: RouteRequest | None = None,
    ) -> dict[str, Any]:
        self._log_payload_profile(payload, stage=stage, request=request)
        try:
            data = await self._chat(payload, stage=stage)
        except TypeError as exc:
            if "unexpected keyword argument 'stage'" not in str(exc):
                raise
            data = await self._chat(payload)  # type: ignore[call-arg]
        self._log_response_summary(data, stage=stage, request=request)
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
    ) -> RouteDecision:
        content = data.get("message", {}).get("content", "")
        raw_summary = _raw_interpreter_output_summary(str(content or ""))
        parsed = _extract_json_object(content)
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

    async def _review_route_only_robot_action(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        if not self.slow_review_recovery_enabled or not self.review_model:
            return decision
        if decision.route != "robot_action" or decision.intent.startswith("capability:") or decision.actions:
            return decision

        try:
            reviewed = await self._chat_logged(self.build_intent_review_payload(request), stage="intent_review", request=request)
            reviewed_decision = self._decision_from_response(request, reviewed, stage="intent_review")
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            raw_content = ""
            if isinstance(locals().get("reviewed"), dict):
                raw_content = str(reviewed.get("message", {}).get("content") or "")
            logger.warning(
                "LLM review model intent check failed: error_type=%s error=%s raw_chars=%s raw_hash=%s raw_preview=%r",
                type(exc).__name__,
                exc,
                len(raw_content),
                _short_hash(raw_content),
                raw_content[:240],
            )
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=(
                    "underspecified robot_action semantic review failed: "
                    f"{type(exc).__name__}"
                ),
            )

        if reviewed_decision.route != "robot_action":
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} overrode underspecified robot_action"
            logger.info(
                "LLM review model changed underspecified robot_action to %s",
                reviewed_decision.route,
            )
            return reviewed_decision
        if (
            reviewed_decision.intent.startswith("capability:")
            or reviewed_decision.actions
            or (
                reviewed_decision.intent
                and reviewed_decision.intent not in {"unknown", "robot_action"}
                and not _is_placeholder_capability_intent(reviewed_decision.intent)
            )
        ):
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} selected exact skill for underspecified robot_action"
            logger.info(
                "LLM review model completed underspecified robot_action as %s",
                reviewed_decision.intent,
            )
            return reviewed_decision
        return decision

    async def _review_generic_chat_affordance(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        """Semantically recheck every chat proposal against non-chat affordances.

        This is deliberately model-based.  The deterministic trigger observes
        only that the first model returned chat while the supplied catalog
        contains executable non-chat affordances. Intent labels are open-ended
        model output and cannot safely decide whether the recheck runs. The
        trigger does not inspect user words or choose a route by phrase rules.
        """

        if not self.generic_chat_review_enabled or not self.slow_review_recovery_enabled:
            return decision
        if decision.route != "chat":
            return decision
        if not _has_executable_non_chat_affordance(request):
            return decision

        try:
            reviewed = await self._chat_logged(
                self.build_semantic_route_repair_payload(
                    request,
                    decision,
                    reason="chat_or_social_framing_requires_capability_grounding_review",
                    model=self.review_model or self.model,
                ),
                stage="capability_grounding_review",
                request=request,
            )
            content = str(reviewed.get("message", {}).get("content") or "")
            minimal = SemanticRouteRepairOutput.model_validate(
                _extract_json_object(content)
            )
            reviewed_decision = finalize_decision(
                RouteDecision(
                    route=minimal.route,
                    intent=minimal.intent,
                    confidence=minimal.confidence,
                    language=request.language or "auto",
                    speak_first=minimal.speak_first,
                    metadata=(
                        minimal.metadata.model_dump(mode="json")
                        if minimal.metadata is not None
                        else {}
                    ),
                    source="llm",
                ),
                request,
                source="llm",
            )
        except Exception as exc:
            logger.warning(
                "generic chat capability review failed sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return decision

        conflict = _route_intent_contract_conflict(request, reviewed_decision)
        if conflict is not None:
            logger.warning(
                "generic chat capability review remained inconsistent sid=%s conflict=%s",
                request.sid,
                conflict,
            )
            return decision
        if is_disallowed_model_control_route(request, reviewed_decision):
            return decision
        if reviewed_decision.route != "clarify" and (
            reviewed_decision.confidence < self.confidence_threshold
        ):
            return decision
        if (
            reviewed_decision.route == "chat"
            and reviewed_decision.intent == decision.intent
        ):
            return decision

        metadata = dict(reviewed_decision.metadata or {})
        metadata["generic_chat_affordance_review"] = {
            "status": (
                "intent_corrected"
                if reviewed_decision.route == decision.route
                else "reclassified"
            ),
            "original_route": decision.route,
            "original_intent": decision.intent,
            "reviewed_route": reviewed_decision.route,
            "reviewed_intent": reviewed_decision.intent,
        }
        reviewed_decision = reviewed_decision.model_copy(update={"metadata": metadata})
        reviewed_decision.reason = (
            f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
        ) + "generic chat output rechecked against supplied executable affordances"
        logger.info(
            "generic chat capability review reclassified sid=%s original=%s/%s reviewed=%s/%s confidence=%.2f",
            request.sid,
            decision.route,
            decision.intent,
            reviewed_decision.route,
            reviewed_decision.intent,
            reviewed_decision.confidence,
        )
        return reviewed_decision

    async def _review_pending_fast_speech(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        target_route = _pending_work_fast_speech_target_route(decision)
        if target_route != "robot_action":
            return decision
        candidate = decision.fast_speech
        if not _fast_speech_matches_route_contract(target_route, candidate):
            candidate = next(
                (
                    item.fast_speech
                    for item in (decision.routes or [])
                    if item.route == target_route
                    and _fast_speech_matches_route_contract(
                        target_route, item.fast_speech
                    )
                ),
                None,
            )
        if candidate is None:
            return decision
        if not self.slow_review_recovery_enabled:
            return _decision_without_goal_interpretation_fast_speech(
                decision,
                reason_suffix="unreviewed embodied fast speech suppressed",
                stage="fast_speech_semantic_review_disabled",
            )
        logger.info(
            "goal_interpreter_fast_speech_review_start route=%s intent=%s sid=%s",
            decision.route,
            decision.intent,
            request.sid,
        )
        try:
            data = await self._chat_logged(
                self.build_fast_speech_review_payload(request, decision, candidate),
                stage="fast_speech_semantic_review",
                request=request,
            )
            parsed = _extract_json_object(
                str(data.get("message", {}).get("content") or "")
            )
            raw_fast_speech = parsed.get("fast_speech")
            if raw_fast_speech is None:
                logger.info(
                    "goal_interpreter_fast_speech_review_done route=%s intent=%s selected=false",
                    decision.route,
                    decision.intent,
                )
                return _decision_without_goal_interpretation_fast_speech(
                    decision,
                    reason_suffix="fast speech reviewer selected silence",
                    stage="fast_speech_semantic_review",
                )
            reviewed = FastSpeech.model_validate(raw_fast_speech)
            if not _fast_speech_matches_route_contract(target_route, reviewed):
                raise ValueError("reviewed fast_speech violates pre-plan claim contract")
        except Exception as exc:
            logger.warning(
                "goal_interpreter_fast_speech_review_failed route=%s intent=%s error=%s",
                decision.route,
                decision.intent,
                exc,
            )
            return _decision_without_goal_interpretation_fast_speech(
                decision,
                reason_suffix="invalid embodied fast speech suppressed",
                stage="fast_speech_semantic_review_failed",
            )
        reviewed_decision = _decision_with_goal_interpretation_fast_speech(
            decision,
            reviewed,
            reason_suffix="fast speech independently reviewed for semantic authority and style",
            stage="fast_speech_semantic_review",
            replace_existing=True,
        )
        metadata = dict(reviewed_decision.metadata or {})
        metadata["fast_speech_review"] = {
            "stage": "fast_speech_semantic_review",
            "model_reviewed": True,
            "speech_selected": True,
            "claim_state": reviewed.claim_state,
            "claimed_capability_ids": list(reviewed.claimed_capability_ids),
            "claimed_goal_ids": list(reviewed.claimed_goal_ids),
        }
        logger.info(
            "goal_interpreter_fast_speech_review_done route=%s intent=%s selected=true text_chars=%s",
            decision.route,
            decision.intent,
            len(reviewed.text),
        )
        return reviewed_decision.model_copy(update={"metadata": metadata})

    async def _repair_missing_fast_speech(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        prepared = decision
        if _decision_needs_goal_interpretation_fast_speech(decision):
            if not self.pending_work_fast_speech_repair_enabled:
                logger.info(
                    "goal_interpreter_fast_speech_missing route=%s intent=%s repair=pending_work_disabled",
                    decision.route,
                    decision.intent,
                )
            elif not self.slow_review_recovery_enabled:
                logger.info(
                    "goal_interpreter_fast_speech_missing route=%s intent=%s repair=disabled",
                    decision.route,
                    decision.intent,
                )
            else:
                logger.info(
                    "goal_interpreter_fast_speech_repair_start route=%s intent=%s sid=%s",
                    decision.route,
                    decision.intent,
                    request.sid,
                )
                try:
                    data = await self._chat_logged(
                        self.build_fast_speech_repair_payload(request, decision),
                        stage="fast_speech_repair",
                        request=request,
                    )
                    parsed = _extract_json_object(
                        str(data.get("message", {}).get("content") or "")
                    )
                    raw_fast_speech = parsed.get("fast_speech")
                    if raw_fast_speech is None:
                        logger.info(
                            "goal_interpreter_fast_speech_repair_done route=%s intent=%s added=false reason=model_selected_silence",
                            decision.route,
                            decision.intent,
                        )
                    else:
                        fast_speech = FastSpeech.model_validate(raw_fast_speech)
                        if not _fast_speech_matches_route_contract(
                            _pending_work_fast_speech_target_route(decision),
                            fast_speech,
                        ):
                            raise ValueError(
                                "model-authored fast_speech violates pre-plan claim contract"
                            )
                        prepared = _decision_with_goal_interpretation_fast_speech(
                            decision,
                            fast_speech,
                            reason_suffix="goal interpreter authored optional fast speech",
                            stage="fast_speech_repair",
                        )
                        logger.info(
                            "goal_interpreter_fast_speech_repair_done route=%s intent=%s added=true text_chars=%s",
                            decision.route,
                            decision.intent,
                            len(fast_speech.text),
                        )
                except Exception as exc:
                    logger.warning(
                        "goal_interpreter_fast_speech_repair_failed route=%s intent=%s error=%s",
                        decision.route,
                        decision.intent,
                        exc,
                    )
        return await self._review_pending_fast_speech(request, prepared)

    def _safe_semantic_clarification(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        reason: str,
    ) -> RouteDecision:
        metadata = {
            key: value
            for key, value in (decision.metadata or {}).items()
            if key
            not in {
                "route_items",
                "route_item_count",
                "route_stage_outputs",
                "task_list",
                "task_proposals",
                "route_merge",
                "tool_name",
                "tool_capability_id",
                "weather_query",
            }
        }
        metadata.update(
            {
                "llm_clarification_required": True,
                "semantic_route_repair": {
                    "status": "clarify",
                    "reason": reason,
                    "original_route": decision.route,
                    "original_intent": decision.intent,
                    "original_confidence": decision.confidence,
                },
                "thinking_ack_allowed": False,
            }
        )
        return finalize_decision(
            RouteDecision(
                route="clarify",
                agents=["speaker_agent"],
                intent="clarify_uncertain_request",
                confidence=min(float(decision.confidence), 0.45),
                language=request.language or decision.language or "auto",
                priority=decision.priority,
                needs_agent=True,
                should_speak=True,
                candidate_capabilities=list(decision.candidate_capabilities),
                reason=(f"{decision.reason}; " if decision.reason else "") + reason,
                source="llm",
                metadata=metadata,
            ),
            request,
            source="llm",
        )

    async def _repair_semantic_route(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        reason: str,
    ) -> RouteDecision:
        try:
            repaired = await self._chat_logged(
                self.build_semantic_route_repair_payload(
                    request,
                    decision,
                    reason=reason,
                ),
                stage="semantic_route_repair",
                request=request,
            )
            content = str(repaired.get("message", {}).get("content") or "")
            minimal = SemanticRouteRepairOutput.model_validate(
                _extract_json_object(content)
            )
            _validate_missing_ability_output_against_catalog(minimal, request)
            repaired_decision = finalize_decision(
                RouteDecision(
                    route=minimal.route,
                    intent=minimal.intent,
                    confidence=minimal.confidence,
                    language=request.language or "auto",
                    speak_first=minimal.speak_first,
                    metadata=(
                        minimal.metadata.model_dump(mode="json")
                        if minimal.metadata is not None
                        else {}
                    ),
                    source="llm",
                ),
                request,
                source="llm",
            )
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            logger.warning(
                "semantic route repair failed sid=%s reason=%s error_type=%s error=%s",
                request.sid,
                reason,
                type(exc).__name__,
                exc,
            )
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=f"{reason}; semantic repair failed",
            )

        conflict = _route_intent_contract_conflict(request, repaired_decision)
        if (
            repaired_decision.route == "deep_thought"
            and repaired_decision.intent in {"", "unknown", "deep_thought_low_confidence"}
        ):
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=f"{reason}; repaired decision remained semantically unresolved",
            )
        if conflict is not None:
            logger.warning(
                "semantic route repair remained inconsistent sid=%s conflict=%s route=%s intent=%s",
                request.sid,
                conflict,
                repaired_decision.route,
                repaired_decision.intent,
            )
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=f"{reason}; repaired decision still violates {conflict}",
            )
        if is_disallowed_model_control_route(request, repaired_decision):
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=f"{reason}; repair returned deterministic-only route",
            )
        if (
            repaired_decision.route != "clarify"
            and repaired_decision.confidence < self.confidence_threshold
        ):
            return self._safe_semantic_clarification(
                request,
                decision,
                reason=f"{reason}; repaired decision remained low confidence",
            )

        metadata = dict(repaired_decision.metadata or {})
        metadata["semantic_route_repair"] = {
            "status": "repaired",
            "reason": reason,
            "original_route": decision.route,
            "original_intent": decision.intent,
            "original_confidence": decision.confidence,
        }
        repaired_decision = repaired_decision.model_copy(update={"metadata": metadata})
        repair_model = self.review_model or self.model
        repaired_decision.reason = (
            f"{repaired_decision.reason}; " if repaired_decision.reason else ""
        ) + f"repair_model:{repair_model} semantic route repair after {reason}"
        logger.info(
            "semantic route repaired sid=%s reason=%s original=%s/%s repaired=%s/%s confidence=%.2f",
            request.sid,
            reason,
            decision.route,
            decision.intent,
            repaired_decision.route,
            repaired_decision.intent,
            repaired_decision.confidence,
        )
        return repaired_decision

    async def _repair_route_intent_contract(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        conflict = _route_intent_contract_conflict(request, decision)
        if conflict is None:
            return decision
        return await self._repair_semantic_route(
            request,
            decision,
            reason=conflict,
        )

    async def _review_ambiguous_deep_thought(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        if decision.route != "deep_thought":
            return decision
        ambiguous_shape = decision.intent in {"", "unknown"} and not decision.reason
        low_confidence = (
            decision.confidence < self.confidence_threshold
            or decision.intent == "deep_thought_low_confidence"
        )
        if not ambiguous_shape and not low_confidence:
            return decision

        reason = (
            "ambiguous_deep_thought_without_semantic_intent"
            if ambiguous_shape
            else "low_confidence_deep_thought_requires_semantic_review"
        )
        if self.slow_review_recovery_enabled and self.review_model:
            try:
                reviewed = await self._chat_logged(
                    self.build_intent_review_payload(request),
                    stage="intent_review",
                    request=request,
                )
                reviewed_decision = self._decision_from_response(
                    request,
                    reviewed,
                    stage="intent_review",
                )
            except Exception as exc:
                _raise_if_llm_budget_failure(exc)
                logger.warning(
                    "LLM review model uncertain deep_thought check failed: %s",
                    exc,
                )
            else:
                conflict = _route_intent_contract_conflict(request, reviewed_decision)
                review_resolved = not (
                    reviewed_decision.route == "deep_thought"
                    and reviewed_decision.intent
                    in {"", "unknown", "deep_thought_low_confidence"}
                )
                if (
                    conflict is None
                    and review_resolved
                    and not is_disallowed_model_control_route(
                        request,
                        reviewed_decision,
                    )
                    and (
                        reviewed_decision.route == "clarify"
                        or reviewed_decision.confidence >= self.confidence_threshold
                    )
                ):
                    review_label = (
                        "ambiguous deep_thought"
                        if ambiguous_shape
                        else "uncertain deep_thought"
                    )
                    reviewed_decision.reason = (
                        f"{reviewed_decision.reason}; "
                        if reviewed_decision.reason
                        else ""
                    ) + f"review_model:{self.review_model} reviewed {review_label}"
                    logger.info(
                        "LLM review model changed uncertain deep_thought to %s/%s",
                        reviewed_decision.route,
                        reviewed_decision.intent,
                    )
                    return reviewed_decision

        return await self._repair_semantic_route(
            request,
            decision,
            reason=reason,
        )

    async def _recover_deterministic_only_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        reason_prefix = (
            f"fast goal interpreter returned deterministic-only route {decision.route} "
            "after deterministic emergency/noise filter did not match"
        )
        if not self.slow_review_recovery_enabled:
            logger.info("%s; slow repair disabled; using safe chat fallback", reason_prefix)
            return fallback_decision(
                request,
                reason=f"{reason_prefix}; slow repair disabled",
            )
        if self.slow_review_recovery_enabled and self.review_model:
            try:
                reviewed = await self._chat_logged(self.build_intent_review_payload(request), stage="intent_review", request=request)
                reviewed_decision = self._decision_from_response(request, reviewed, stage="intent_review")
            except Exception as exc:
                _raise_if_llm_budget_failure(exc)
                logger.warning("LLM review model deterministic-only recovery failed: %s", exc)
            else:
                if not is_disallowed_model_control_route(
                    request,
                    reviewed_decision,
                ):
                    if reviewed_decision.confidence >= self.confidence_threshold:
                        reviewed_decision.reason = (
                            f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
                        ) + f"{reason_prefix}; review_model:{self.review_model} recovered fast-interpreter mistake"
                        logger.info(
                            "LLM review model recovered invalid deterministic-only route %s to %s",
                            decision.route,
                            reviewed_decision.route,
                        )
                        return reviewed_decision
                    logger.info(
                        "LLM review model returned low-confidence recovery %.2f for invalid %s; trying fast repair",
                        reviewed_decision.confidence,
                        decision.route,
                    )
        try:
            repaired = await self._chat_logged(self.build_deterministic_route_repair_payload(request), stage="deterministic_route_repair", request=request)
            repaired_decision = self._decision_from_response(request, repaired, stage="deterministic_route_repair")
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            logger.warning("LLM fast route repair failed: %s", exc)
        else:
            if not is_disallowed_model_control_route(request, repaired_decision):
                repaired_decision.reason = (
                    f"{repaired_decision.reason}; " if repaired_decision.reason else ""
                ) + f"{reason_prefix}; fast_model:{self.model} repaired fast-interpreter mistake"
                logger.info(
                    "LLM fast repair recovered invalid deterministic-only route %s to %s",
                    decision.route,
                    repaired_decision.route,
                )
                return repaired_decision
        logger.info(
            "Goal Interpreter model returned invalid deterministic-only route %s after priority filter; using safe chat fallback",
            decision.route,
        )
        return fallback_decision(request, reason=reason_prefix)

    async def _recover_placeholder_capability_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        reason_prefix = (
            "fast goal interpreter returned robot_action with placeholder capability intent "
            f"{decision.intent!r}"
        )
        if not self.slow_review_recovery_enabled:
            logger.info("%s; slow repair disabled; using safe chat fallback", reason_prefix)
            return fallback_decision(
                request,
                reason=f"{reason_prefix}; slow repair disabled",
            )
        try:
            repaired = await self._chat_logged(self.build_placeholder_capability_repair_payload(request), stage="placeholder_capability_repair", request=request)
            repaired_decision = self._decision_from_response(request, repaired, stage="placeholder_capability_repair")
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            logger.warning("LLM placeholder capability repair failed: %s", exc)
        else:
            if (
                not is_disallowed_model_control_route(request, repaired_decision)
                and not _is_placeholder_capability_intent(repaired_decision.intent)
            ):
                repaired_decision.reason = (
                    f"{repaired_decision.reason}; " if repaired_decision.reason else ""
                ) + f"{reason_prefix}; fast_model:{self.model} repaired placeholder capability intent"
                logger.info(
                    "LLM fast repair recovered placeholder capability intent to %s/%s",
                    repaired_decision.route,
                    repaired_decision.intent,
                )
                return repaired_decision
        logger.info("%s; using safe chat fallback", reason_prefix)
        return fallback_decision(request, reason=reason_prefix)

    async def review_after_priority_interrupt(
        self,
        request: RouteRequest,
        interrupt_decision: RouteDecision,
    ) -> RouteDecision:
        data = await self._chat_logged(
            self.build_post_interrupt_review_payload(request, interrupt_decision),
            stage="post_interrupt_review",
            request=request,
        )
        decision = self._decision_from_response(request, data, stage="post_interrupt_review")
        if decision.route == "interrupt":
            decision.intent = "stop_current_output"
            decision.reason = (
                f"{decision.reason}; " if decision.reason else ""
            ) + "post-interrupt review confirmed deterministic interrupt"
            return decision
        decision.reason = (
            f"{decision.reason}; " if decision.reason else ""
        ) + "post-interrupt review corrected deterministic interrupt"
        return decision

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
        # Ambient suppression is intentionally fail-open. A direct speech act,
        # an unclear act, or question punctuation contradicts addressed=false
        # and therefore cannot silently discard the already grounded route.
        # This is a structural interaction contract, not normal intent routing.
        direct_question_form = request.text.rstrip().endswith(("?", "？"))
        if addressed or confidence < 0.72:
            return decision
        fail_open_reason = ""
        if speech_act in DIRECTED_SPEECH_ACTS:
            fail_open_reason = "direct_speech_act"
        elif speech_act == "unclear":
            fail_open_reason = "unclear_speech_act"
        elif direct_question_form:
            fail_open_reason = "direct_question_form"
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

    def _low_confidence_deep_thought_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        reason_prefix: str | None = None,
    ) -> RouteDecision:
        candidates = decision.candidate_capabilities
        if not candidates:
            raw_candidates = request.context.get("common_ability_catalog", [])
            if not raw_candidates:
                raw_candidates = request.context.get("prompt_capabilities_common", [])
            if not raw_candidates:
                raw_candidates = request.context.get("full_ability_catalog", [])
            if not raw_candidates:
                raw_candidates = request.context.get("prompt_capabilities_all", [])
            candidates = raw_candidates if isinstance(raw_candidates, list) else []
        reason_parts = [
            reason_prefix
            or f"fast goal interpreter confidence {decision.confidence:.2f} below threshold {self.confidence_threshold:.2f}",
            f"quick_route={decision.route}",
            f"quick_intent={decision.intent}",
        ]
        if decision.reason:
            reason_parts.append(f"quick_reason={decision.reason}")
        inherited_metadata = {
            key: value
            for key, value in (decision.metadata or {}).items()
            if key
            not in {
                "route_items",
                "route_item_count",
                "route_stage_outputs",
                "task_list",
                "task_proposals",
                "route_merge",
            }
        }
        return finalize_decision(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_low_confidence",
                confidence=decision.confidence,
                language=decision.language or request.language or "auto",
                priority=decision.priority,
                speak_first=decision.speak_first,
                needs_agent=True,
                should_speak=True,
                candidate_capabilities=candidates,
                reason="; ".join(reason_parts),
                source="llm",
                metadata={
                    **inherited_metadata,
                    "thinking_ack_allowed": bool(decision.speak_first),
                    "thinking_ack_source": (
                        "quick_llm_speak_first" if decision.speak_first else "none"
                    ),
                },
            ),
            request,
            source="llm",
        )

    async def route(self, request: RouteRequest) -> RouteDecision:
        payload = self.build_payload(request)

        try:
            data = await self._chat_logged(payload, stage="quick_intent", request=request)
        except Exception as exc:
            logger.warning("Ollama Goal Interpreter request failed: %s: %s", type(exc).__name__, exc)
            if self.slow_review_recovery_enabled and self.review_model:
                try:
                    reviewed = await self._chat_logged(self.build_intent_review_payload(request), stage="intent_review", request=request)
                    reviewed_decision = self._decision_from_response(request, reviewed, stage="intent_review")
                except Exception as review_exc:
                    _raise_if_llm_budget_failure(review_exc)
                    logger.warning("LLM review model primary-error recovery failed: %s", review_exc)
                else:
                    if not is_disallowed_model_control_route(
                        request,
                        reviewed_decision,
                    ):
                        reviewed_decision.reason = (
                            f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
                        ) + f"primary goal interpreter error {type(exc).__name__}; review_model:{self.review_model} recovered route"
                        logger.info(
                            "LLM review model recovered primary goal interpreter error to %s/%s",
                            reviewed_decision.route,
                            reviewed_decision.intent,
                        )
                        return reviewed_decision
            _raise_if_llm_budget_failure(exc)
            return fallback_decision(
                request,
                reason=f"goal_interpreter_error:{type(exc).__name__}: {exc}",
            )

        content = ""
        try:
            content = data.get("message", {}).get("content", "")
            decision = self._decision_from_response(request, data, stage="quick_intent")
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid Goal Interpreter model response: %s; content=%r", exc, content[:500])
            try:
                relaxed = await self._chat_logged(self.build_payload(request, relaxed_json=True), stage="quick_intent_relaxed", request=request)
                decision = self._decision_from_response(request, relaxed, stage="quick_intent_relaxed")
                logger.info("Goal Interpreter model recovered with relaxed JSON response")
            except Exception as relaxed_exc:
                _raise_if_llm_budget_failure(relaxed_exc)
                logger.warning("Relaxed Goal Interpreter model retry failed: %s", relaxed_exc)
                return fallback_decision(request, reason=f"invalid_goal_interpreter_response: {exc}")

        if (
            decision.route == "deep_thought"
            and decision.intent in {"", "unknown"}
            and not decision.reason
        ):
            reviewed = await self._review_ambiguous_deep_thought(request, decision)
            if not (
                reviewed.route == "deep_thought"
                and reviewed.intent in {"", "unknown"}
                and not reviewed.reason
            ):
                decision = reviewed
            else:
                logger.info(
                    "Goal Interpreter model returned ambiguous deep_thought without intent or reason; using safe fallback"
                )
                return fallback_decision(
                    request,
                    reason="ambiguous_llm_deep_thought_without_intent_or_reason",
                )
        else:
            decision = await self._review_ambiguous_deep_thought(request, decision)
        decision = await self._review_route_only_robot_action(request, decision)
        # Route/intent contradictions are repaired by a semantic model. The
        # deterministic host checks only the model-authored contract and never
        # infers weather, tool, or physical intent from user-text keywords.
        decision = await self._repair_route_intent_contract(request, decision)
        # The deployed Core entry receives a Gateway-admitted envelope, so
        # addressedness has already been decided upstream. Preserve the old
        # reviewer only for explicit compatibility entrypoints and historical
        # replays that do not carry the admission marker.
        if request.context.get("gateway_admission_complete") is not True:
            decision = await self._review_inactive_addressedness(request, decision)
        decision = await self._review_generic_chat_affordance(request, decision)

        if decision.route == "ignore":
            if is_allowed_model_ignore(request, decision):
                return decision
            recovered = await self._recover_deterministic_only_decision(
                request,
                decision,
            )
            return await self._repair_missing_fast_speech(request, recovered)

        if decision.route in DETERMINISTIC_ONLY_ROUTES:
            recovered = await self._recover_deterministic_only_decision(request, decision)
            return await self._repair_missing_fast_speech(request, recovered)

        if decision.route == "robot_action" and _is_placeholder_capability_intent(decision.intent):
            recovered = await self._recover_placeholder_capability_decision(request, decision)
            return await self._repair_missing_fast_speech(request, recovered)

        return await self._repair_missing_fast_speech(request, decision)
