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

from .errors import InterpretationUnavailableError
from .schema import GoalInterpretationDecision, GoalInterpretationRequest


logger = logging.getLogger("chromie.agent.goal_interpreter.llm")


_CONTEXT_OMIT_KEYS = {
    "candidate_capabilities",
    "common_ability_catalog",
    "common_ability_ids",
    "full_ability_catalog",
    "prompt_capabilities_common",
    "prompt_capabilities_all",
    "prompt_catalog_scope",
    "capability_catalog_version",
    "mind",
    "core_principles",
    "long_term_goals",
    "experience_tuning_policy",
    "conversation",
    "history",
    "task_contexts",
    "active_task_contexts",
    "active_task_snapshots",
    "active_goal_snapshots",
    "active_pending_tasks",
    "recent_goal_snapshots",
    "current_task_context",
    "gateway_context_snapshot",
}

# These keys belong either to downstream lifecycle/HOW authority or to the retired
# route/intent compatibility architecture. They are never semantic evidence for GI.
_FORBIDDEN_CONTEXT_KEYS = frozenset(
    {
        "goal_id",
        "goal_ids",
        "source_goal_ids",
        "target_goal_ids",
        "supersedes_goal_ids",
        "covers_goal_ids",
        "task_id",
        "task_ids",
        "plan_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        "activity_id",
        "work_item_id",
        "execution_binding",
        "execution_lane",
        "provider_id",
        "capability_id",
        "skill_id",
        "tool_name",
        "route",
        "routes",
        "route_decision",
        "intent",
        "last_intent",
    }
)

_FORBIDDEN_MODEL_OUTPUT_FIELDS = frozenset(
    {
        "route",
        "routes",
        "intent",
        "agents",
        "actions",
        "candidate_capabilities",
        "capability_id",
        "skill_id",
        "tool_name",
        "provider_id",
        "activities",
        "activity",
        "primary_activity",
        "work",
        "work_items",
        "plan",
        "plan_steps",
        "steps",
        "execution_lane",
        "realization",
        "coordination",
        "fast_speech",
        "speak_first",
        "progress",
        "response_text",
        "memory_update",
        "task_id",
        "goal_id",
        "plan_id",
    }
)

_CANONICAL_GOAL_ID_KEYS = frozenset(
    {
        "goal_id",
        "goal_ids",
        "source_goal_ids",
        "target_goal_ids",
        "supersedes_goal_ids",
        "covers_goal_ids",
    }
)


class _GoalInterpretationAuthorityViolation(ValueError):
    """Goal Interpretation attempted to claim downstream identity/authority."""


def _raise_if_llm_budget_failure(exc: Exception) -> None:
    if isinstance(exc, OllamaGenerationError) and exc.failure_domain == "llm_budget":
        raise exc


def _without_goal_interpretation_authority(value: Any) -> Any:
    """Strip downstream authority and retired route classifications from context."""

    if isinstance(value, dict):
        return {
            key: _without_goal_interpretation_authority(item)
            for key, item in value.items()
            if str(key).strip().casefold() not in _FORBIDDEN_CONTEXT_KEYS
        }
    if isinstance(value, list):
        return [_without_goal_interpretation_authority(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_goal_interpretation_authority(item) for item in value)
    return value


def _extract_json_object(text: str) -> dict[str, Any]:
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


def _reject_planner_shaped_goal_interpretation(parsed: dict[str, Any]) -> None:
    """Fail closed if the model attempts route/HOW/response authority."""

    for field in _FORBIDDEN_MODEL_OUTPUT_FIELDS:
        if field in parsed:
            raise _GoalInterpretationAuthorityViolation(
                f"Goal Interpretation output contains downstream-owned field {field!r}"
            )


def _canonical_goal_ids_from_context(value: Any) -> set[str]:
    found: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                normalized = str(key).strip().casefold()
                if normalized == "goal_id":
                    candidate = str(item or "").strip()
                    if candidate:
                        found.add(candidate)
                elif normalized in _CANONICAL_GOAL_ID_KEYS:
                    values = item if isinstance(item, (list, tuple, set)) else [item]
                    for candidate in values:
                        text = str(candidate or "").strip()
                        if text:
                            found.add(text)
                collect(item)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                collect(item)

    collect(value)
    return found


def _reject_canonical_goal_identity_refs(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    canonical_goal_ids = _canonical_goal_ids_from_context(request.context)
    if not canonical_goal_ids:
        return
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        local_ref = str(item.get("local_ref") or "").strip()
        if local_ref and local_ref in canonical_goal_ids:
            raise _GoalInterpretationAuthorityViolation(
                "Goal Interpretation responsibilities"
                f"[{index}].local_ref reused canonical Goal identity {local_ref!r}; "
                "local_ref must be turn-local and Goal Association alone owns "
                "canonical Goal identity"
            )


_GOAL_INTERPRETATION_PROVENANCE_CONTEXT_KEYS = (
    "history",
    "discourse_referents",
    "discourse_focus",
    "active_goal_snapshots",
    "recent_goal_snapshots",
    "active_task_snapshots",
    "active_task_contexts",
    "current_task_context",
)


def _semantic_context_string_values(context: dict[str, Any]) -> set[str]:
    values: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                collect(item)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                collect(item)
        elif isinstance(node, str):
            text = " ".join(node.strip().split())
            if text:
                values.add(text.casefold())

    for key in _GOAL_INTERPRETATION_PROVENANCE_CONTEXT_KEYS:
        collect(context.get(key))
    return values


def _reject_unprovenanced_location_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject model-authored location spellings with no semantic provenance.

    This gate does not resolve or repair a location. It only verifies that the
    model copied a current-turn surface or a value already present in bounded
    semantic continuity context. One same-stage DTO repair may then regenerate
    from the authoritative turn.
    """

    current_turn = " ".join((request.text or "").strip().split()).casefold()
    contextual_values = _semantic_context_string_values(request.context)
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        raw_location = bindings.get("location")
        if not isinstance(raw_location, str):
            continue
        location = " ".join(raw_location.strip().split())
        if not location:
            continue
        folded = location.casefold()
        if folded in current_turn or folded in contextual_values:
            continue
        raise _GoalInterpretationAuthorityViolation(
            "Goal Interpretation location binding has no authoritative surface "
            f"provenance: responsibilities[{index}].bindings.location={location!r}. "
            "A directly named location must copy the exact current-turn user-language "
            "surface; an indirect location must already exist in bounded semantic context."
        )


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


def _payload_message_texts(payload: dict[str, Any]) -> tuple[str, str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    all_parts: list[str] = []
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return "", "", ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "")
        all_parts.append(content)
        role = str(message.get("role") or "")
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    return "\n".join(system_parts), "\n".join(user_parts), "\n".join(all_parts)


def _context_without_prompt_globals(context: dict[str, Any]) -> dict[str, Any]:
    filtered = {
        key: value
        for key, value in (context or {}).items()
        if key not in _CONTEXT_OMIT_KEYS
    }
    sanitized = _without_goal_interpretation_authority(filtered)
    return sanitized if isinstance(sanitized, dict) else {}


def _compact_active_task_snapshots(
    context: dict[str, Any], *, limit: int = 4
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
            semantic_goal = {"description": item.get("goal") or ""}
        gaps = item.get("open_information_gaps")
        if not isinstance(gaps, list):
            gaps = [
                {"description": value, "blocking": True}
                for value in (item.get("pending_questions") or [])
                if isinstance(value, str)
            ]
        compact.append(
            {
                "status": str(item.get("status") or "open"),
                "goal": {
                    "description": str(semantic_goal.get("description") or "")[:240],
                    "beneficiary": semantic_goal.get("beneficiary"),
                    "object": semantic_goal.get("object") if isinstance(semantic_goal.get("object"), dict) else {},
                    "constraints": semantic_goal.get("constraints") if isinstance(semantic_goal.get("constraints"), dict) else {},
                },
                "open_information_gaps": [
                    {
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
            }
        )
    return compact


def _compact_active_goal_snapshots(
    context: dict[str, Any], *, limit: int = 4
) -> list[dict[str, Any]]:
    raw = context.get("active_goal_snapshots")
    if not isinstance(raw, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        description = str(goal.get("description") or item.get("description") or "").strip()
        if not description:
            continue
        compact.append(
            {
                "responsibility_status": str(
                    item.get("responsibility_status")
                    or goal.get("responsibility_status")
                    or "open"
                ),
                "goal": {
                    "description": description[:240],
                    "object": goal.get("object") if isinstance(goal.get("object"), dict) else {},
                    "constraints": goal.get("constraints") if isinstance(goal.get("constraints"), dict) else {},
                },
                "last_user_update": str(item.get("last_user_update") or "")[:220],
            }
        )
    return compact


def _compact_recent_dialogue(
    context: dict[str, Any], *, limit: int = 6
) -> list[dict[str, Any]]:
    """Project only accepted surface dialogue; never retired route/intent labels."""

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
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if role == "user" and metadata.get("cognitive_gateway_admission") == "suppress":
            continue
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue
        projected: dict[str, Any] = {"role": role, "text": text[:260]}
        if role == "user":
            semantic_status = " ".join(str(metadata.get("semantic_status") or "").split())
            if semantic_status:
                projected["semantic_status"] = semantic_status
        else:
            source = " ".join(str(metadata.get("source") or "").split())
            if source:
                projected["source"] = source
        compact.append(projected)
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


def _goal_interpretation_identity_context(mind: Any) -> str:
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
                for key in ("spoken_style", "maturity_boundary")
                if personality.get(key) not in (None, "", [], {})
            }
    profile = {
        "identity": identity or {"entity_id": "chromie", "name": "Chromie"},
        "voice": voice,
    }
    return (
        f"{_bounded_json(profile, max_chars=1150)}\n"
        "This bounded owner-approved identity context may resolve self-reference or "
        "social meaning. It does not authorize response wording or downstream work."
    )


class OllamaGoalInterpreter:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        timeout_ms: int,
        num_ctx: int = 4096,
        num_predict: int = 512,
        keep_alive: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout_s = max(0.1, timeout_ms / 1000.0)
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(32, num_predict)
        self.prompt_chars_per_token_estimate = agent_service_settings.llm_prompt_chars_per_token_estimate
        self.context_safety_margin_tokens = agent_service_settings.llm_context_safety_margin_tokens
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
                "You are Chromie's Goal Interpretation model. Understand only WHAT the "
                "human means and return provider-neutral responsibilities, confidence, "
                "and unresolved semantic uncertainty as JSON."
            )

    def build_interpretation_user_prompt(
        self, request: GoalInterpretationRequest
    ) -> str:
        mind = request.context.get("mind", {})
        session_context = _without_goal_interpretation_authority(
            _goal_interpretation_prompt_context(request.context)
        )
        return (
            "Current Turn:\n"
            f"Latest user input: {request.text}\n"
            f"language={request.language or 'auto'} sid={request.sid or ''}\n\n"
            "Bounded Identity Context:\n"
            f"{_goal_interpretation_identity_context(mind)}\n\n"
            "Semantic Continuity Context:\n"
            f"Bounded session/world context JSON:{_bounded_json(session_context, max_chars=900)}\n"
            "Interaction context JSON:"
            f"{_bounded_json(_without_goal_interpretation_authority(request.context.get('interaction_context') or {}), max_chars=2400)}\n"
            "Recent accepted dialogue JSON:"
            f"{_bounded_json_array(_compact_recent_dialogue(request.context), max_chars=1800)}\n"
            "Active Goal semantics without canonical identity JSON:"
            f"{_bounded_json_array(_compact_active_goal_snapshots(request.context), max_chars=1400)}\n"
            "Active Task/progress semantics without lifecycle identity JSON:"
            f"{_bounded_json_array(_compact_active_task_snapshots(request.context), max_chars=1400)}\n\n"
            "Interpret only WHAT the human means. Return responsibilities, confidence, "
            "and unresolved semantic uncertainty. For directly named entities, preserve "
            "the exact current-turn user-language surface in bindings; never translate or "
            "provider-canonicalize it. No route, intent, response wording, Activity, Work, "
            "Plan, Capability, Tool, provider, executable args, or IDs."
        )

    @staticmethod
    def _goal_interpretation_response_schema() -> dict[str, Any]:
        schema = GoalInterpretationDecision.model_json_schema()
        schema["additionalProperties"] = False
        return schema

    def build_interpretation_payload(
        self, request: GoalInterpretationRequest
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.load_system_prompt()},
                {"role": "user", "content": self.build_interpretation_user_prompt(request)},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": min(self.num_predict, 768),
            },
            "format": self._goal_interpretation_response_schema(),
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        return payload

    def build_interpretation_repair_payload(
        self,
        request: GoalInterpretationRequest,
        *,
        previous_content: str,
        validation_error: Exception,
    ) -> dict[str, Any]:
        del previous_content, validation_error
        payload = self.build_interpretation_payload(request)
        payload["messages"] = [
            {
                "role": "system",
                "content": (
                    self.load_system_prompt()
                    + "\n\nDTO Repair: return one corrected WHAT-only Goal Interpretation JSON object. "
                    "Remove every field outside the schema. Never translate a rejected "
                    "route/intent/Capability/Activity/Work/Plan/provider field into another "
                    "implementation hint. Preserve only the human outcome, material semantic "
                    "bindings, work/fresh-evidence requirements, confidence, and genuine "
                    "semantic uncertainty. A directly named entity binding must copy the exact "
                    "current-turn surface; never translate or transliterate it. Provider timezone "
                    "or clock-range choices for an already-preserved relative time are not semantic "
                    "uncertainty. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    self.build_interpretation_user_prompt(request)
                    + "\n\nThe previous output violated the WHAT-only typed contract. "
                    "Regenerate from the authoritative user meaning and bounded semantic "
                    "context above. Do not copy any field, identifier, wording, or "
                    "implementation hint from the rejected output. Return only the new "
                    "schema object."
                ),
            },
        ]
        return payload

    async def interpret_goal(
        self, request: GoalInterpretationRequest
    ) -> GoalInterpretationDecision:
        try:
            data = await self._chat_logged(
                self.build_interpretation_payload(request),
                stage="goal_interpretation",
                request=request,
            )
        except Exception as exc:
            _raise_if_llm_budget_failure(exc)
            raise InterpretationUnavailableError(
                f"goal_interpreter_error:{type(exc).__name__}: {exc}"
            ) from exc

        content = str(data.get("message", {}).get("content") or "")
        try:
            parsed = _extract_json_object(content)
            _reject_planner_shaped_goal_interpretation(parsed)
            _reject_canonical_goal_identity_refs(request, parsed)
            _reject_unprovenanced_location_bindings(request, parsed)
            return GoalInterpretationDecision.model_validate(parsed)
        except (_GoalInterpretationAuthorityViolation, ValueError, ValidationError) as exc:
            logger.warning(
                "Invalid WHAT-only Goal Interpretation DTO sid=%s error=%s content=%r",
                request.sid,
                exc,
                content[:500],
            )
            try:
                repaired = await self._chat_logged(
                    self.build_interpretation_repair_payload(
                        request,
                        previous_content=content,
                        validation_error=exc,
                    ),
                    stage="goal_interpretation_contract_repair",
                    request=request,
                )
                parsed = _extract_json_object(str(repaired.get("message", {}).get("content") or ""))
                _reject_planner_shaped_goal_interpretation(parsed)
                _reject_canonical_goal_identity_refs(request, parsed)
                _reject_unprovenanced_location_bindings(request, parsed)
                return GoalInterpretationDecision.model_validate(parsed)
            except Exception as repair_exc:
                _raise_if_llm_budget_failure(repair_exc)
                raise InterpretationUnavailableError(
                    "invalid_goal_interpretation_after_one_dto_repair: "
                    f"{type(repair_exc).__name__}: {repair_exc}"
                ) from repair_exc

    def _log_payload_profile(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: GoalInterpretationRequest | None = None,
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
            "what_only_contract": all(
                token in all_text
                for token in ("WHAT", "responsibilities", "unresolved")
            ),
            "capability_catalog_present": "Common Ability Catalog" in all_text,
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
        request: GoalInterpretationRequest | None = None,
    ) -> None:
        content = str(data.get("message", {}).get("content") or "")
        parsed: dict[str, Any] | None = None
        try:
            parsed = _extract_json_object(content)
        except (ValueError, json.JSONDecodeError):
            pass
        summary = {
            "stage": stage,
            "sid": request.sid if request is not None else None,
            "model": data.get("model"),
            "done": data.get("done"),
            "done_reason": data.get("done_reason"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "json_object": parsed is not None,
            "responsibility_count": len(parsed.get("responsibilities") or []) if parsed else None,
            "confidence": parsed.get("confidence") if parsed else None,
            "unresolved_count": len(parsed.get("unresolved") or []) if parsed else None,
            "forbidden_fields": sorted(
                field for field in _FORBIDDEN_MODEL_OUTPUT_FIELDS if parsed and field in parsed
            ),
        }
        logger.info("goal_interpreter_llm_raw_summary %s", _json_log(summary, max_chars=2200))
        if self.debug_raw_output:
            logger.info(
                "goal_interpreter_llm_raw_output stage=%s sid=%s raw=%r",
                stage,
                request.sid if request is not None else None,
                content[:8000],
            )

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
                response = await client.post(f"{self.ollama_url}/api/generate", json=payload)
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
                error={"error_type": type(exc).__name__, "message": str(exc)},
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
        return data or {}

    async def _chat(self, payload: dict[str, Any], *, stage: str) -> dict[str, Any]:
        options = dict(payload.get("options") or {})
        prompt_chars = self._payload_prompt_chars(payload)
        preflight = ollama_prompt_preflight_diagnostics(
            prompt_chars=prompt_chars,
            options=options,
            chars_per_token=self.prompt_chars_per_token_estimate,
            safety_margin_tokens=self.context_safety_margin_tokens,
        )
        for diagnostic in preflight:
            logger.log(diagnostic.level, "%s", colorize_for_cli(diagnostic.render(), diagnostic.level))
        blocking = next(
            (
                item
                for item in preflight
                if item.event == "llm_prompt_budget_exceeded" and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking is not None:
            raise OllamaGenerationError(
                f"Goal Interpreter request rejected before inference: {blocking.render()}",
                failure_class="prompt_budget_exceeded",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": f"goal_interpreter:{stage}",
                    "model": payload.get("model") or self.model,
                    "stage": stage,
                    **blocking.fields,
                    "automatic_retry_allowed": False,
                    "context_reduction_allowed": False,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                    "_incident_evidence": {"request": payload},
                },
            )
        async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        self._validate_completion(payload, data, stage=stage)
        return data

    def _validate_completion(
        self, payload: dict[str, Any], data: dict[str, Any], *, stage: str
    ) -> None:
        options = dict(payload.get("options") or {})
        prompt_chars = self._payload_prompt_chars(payload)
        completion = ollama_completion_diagnostics(
            options=options,
            data=data,
            prompt_chars=prompt_chars,
        )
        for diagnostic in completion:
            logger.log(diagnostic.level, "%s", colorize_for_cli(diagnostic.render(), diagnostic.level))
        blocking = next(
            (
                item
                for item in completion
                if item.event in {"llm_output_truncated", "llm_prompt_truncated"}
                and item.level >= logging.ERROR
            ),
            None,
        )
        if blocking is not None:
            failure_class = "output_truncated" if blocking.event == "llm_output_truncated" else "prompt_truncated"
            raise OllamaGenerationError(
                f"Goal Interpreter result rejected: {blocking.render()}",
                failure_class=failure_class,
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
                details={
                    "purpose": f"goal_interpreter:{stage}",
                    "model": payload.get("model") or self.model,
                    "stage": stage,
                    **blocking.fields,
                    "automatic_retry_allowed": False,
                    "context_reduction_allowed": False,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                    "_incident_evidence": {"request": payload, "response": data},
                },
            )

    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request: GoalInterpretationRequest | None = None,
    ) -> dict[str, Any]:
        call_id = new_llm_call_id("goal_interpreter")
        started = time.perf_counter()
        self._log_payload_profile(payload, stage=stage, request=request)
        try:
            data = await self._chat(payload, stage=stage)
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
                error={"error_type": type(exc).__name__, "message": str(exc)},
            )
            raise
        self._log_response_summary(data, stage=stage, request=request)
        parsed_output: Any = None
        try:
            parsed_output = _extract_json_object(str(data.get("message", {}).get("content") or ""))
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
