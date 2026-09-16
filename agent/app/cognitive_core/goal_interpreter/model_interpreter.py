from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from ...clients.ollama_client import OllamaGenerationError
from ...clients.sglang_protocol import (
    build_sglang_chat_payload,
    sglang_to_completion_evidence,
)
from ...inference_compute import goal_interpreter_compute_class
from ...settings import agent_service_settings

try:
    from chromie_contracts.memory import role_memory_context
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.memory import role_memory_context

try:
    from chromie_contracts.user_turn import user_turn_source_tokens
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.user_turn import user_turn_source_tokens


try:
    from chromie_runtime.ollama_non_thinking import (
        OllamaNonThinkingViolation,
        enforce_non_thinking_ollama_response,
    )
    from chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        new_llm_call_id,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from chromie_runtime.log_colors import colorize_for_cli
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime.ollama_non_thinking import (
        OllamaNonThinkingViolation,
        enforce_non_thinking_ollama_response,
    )
    from shared.chromie_runtime.llm_diagnostics import (
        log_llm_call_evidence,
        new_llm_call_id,
        ollama_completion_diagnostics,
        ollama_prompt_preflight_diagnostics,
    )
    from shared.chromie_runtime.log_colors import colorize_for_cli

from ...prompt_projection import bounded_json, required_json
from .errors import InterpretationUnavailableError
from .schema import (
    GoalInterpretationDecision,
    GoalInterpretationRequest,
)


logger = logging.getLogger("chromie.agent.goal_interpreter.llm")


_CONTEXT_OMIT_KEYS = {
    # Correlation labels belong to request/log joins, never human meaning.
    "conversation_id",
    "session_id",
    "turn_id",
    "sid",
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
    # Runtime target identity/direction is Planner realization evidence. GI may
    # understand the current-turn person/addressee meaning, but must never copy
    # an opaque target_ref or scene geometry into provider-neutral WHAT.
    "active_user_target",
    "planner_auxiliary_social_context",
    # The exact source wording is projected once in its dedicated provenance
    # block.  Do not duplicate the full Gateway envelope as ambient context.
    "user_turn_envelope",
    "source_turn_provenance",
}

# These keys belong either to downstream lifecycle/HOW authority or to the retired
# route/intent compatibility architecture. They are never semantic evidence for GI.
_FORBIDDEN_CONTEXT_KEYS = frozenset(
    {
        "supersedes_goal_ids",
        "covers_goal_ids",
        "plan_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
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
        "speak_first",
        "progress",
        "response_text",
        "memory_update",
        "task_id",
        "goal_id",
        "plan_id",
    }
)


class _GoalInterpretationAuthorityViolation(ValueError):
    """Goal Interpretation attempted to claim downstream identity/authority."""


class _GoalInterpretationSemanticStructureViolation(
    _GoalInterpretationAuthorityViolation
):
    """The DTO shape is valid but does not preserve atomic source meaning."""


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
    if text.startswith("```"):
        fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence is None:
            raise ValueError("incomplete model JSON fence")
        text = fence.group(1)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate model JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite model JSON value: {value}")

    value = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("model response JSON is not an object")
    return value


def _source_tokens(text: str) -> list[dict[str, Any]]:
    """Compatibility-free shared transport tokenization for source provenance."""

    return user_turn_source_tokens(text)


def _goal_interpretation_source_turn_provenance(
    request: GoalInterpretationRequest,
) -> dict[str, Any]:
    """Return exact admitted wording once, without ambient Gateway metadata."""

    original_text = request.text
    envelope = request.turn_envelope
    if envelope is not None:
        original_text = envelope.original_input.text
    else:
        context_envelope = request.context.get("user_turn_envelope")
        if isinstance(context_envelope, dict):
            original_input = context_envelope.get("original_input")
            candidate = (
                original_input.get("text")
                if isinstance(original_input, dict)
                else None
            )
            if (
                isinstance(candidate, str)
                and candidate
                and " ".join(candidate.strip().split()) == request.text
            ):
                original_text = candidate
    return {
        "original_text": original_text,
        "speaker_role": "user",
        "addressee": "Chromie",
        "authority": "read_only_source_provenance",
    }


def _validate_primary_source_evidence(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Validate primary GI citations without interpreting or repairing WHAT."""

    tokens = _source_tokens(request.text)
    by_ref = {str(item["ref"]): item for item in tokens}
    index_by_ref = {
        str(item["ref"]): index for index, item in enumerate(tokens)
    }
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return

    cited_spans: list[tuple[int, int, str]] = []
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        local_ref = str(item.get("local_ref") or f"index:{index}").strip()
        evidence = item.get("source_evidence")
        if not isinstance(evidence, dict):
            raise ValueError(
                "primary Goal Interpretation Responsibility lacks source_evidence: "
                f"{local_ref}"
            )
        start_ref = str(evidence.get("source_start_token_ref") or "").strip()
        end_ref = str(evidence.get("source_end_token_ref") or "").strip()
        if start_ref not in by_ref or end_ref not in by_ref:
            raise ValueError(
                "primary Goal Interpretation source_evidence cited an unknown "
                f"authoritative token ref: {local_ref}:{start_ref}:{end_ref}"
            )
        start = index_by_ref[start_ref]
        end = index_by_ref[end_ref]
        if start > end:
            raise ValueError(
                "primary Goal Interpretation source_evidence token endpoints are "
                f"reversed: {local_ref}:{start_ref}:{end_ref}"
            )
        cited_spans.append((start, end, local_ref))

    cited_spans.sort()
    for (_, previous_end, previous_ref), (start, _, current_ref) in zip(
        cited_spans,
        cited_spans[1:],
        strict=False,
    ):
        if start <= previous_end:
            raise _GoalInterpretationSemanticStructureViolation(
                "primary Goal Interpretation independent Responsibility source spans "
                f"overlap: {previous_ref}:{current_ref}"
            )


def _bounded_json(value: Any, *, max_chars: int = 4000) -> str:
    return bounded_json(value, max_chars)


def _bounded_json_array(value: list[Any], *, max_chars: int = 4000) -> str:
    return bounded_json(value, max_chars)


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
                "task_id": str(item.get("task_id") or ""),
                "goal_id": str(
                    semantic_goal.get("goal_id") or item.get("goal_id") or ""
                ),
                "goal_version": item.get("goal_version"),
                "status": str(item.get("status") or "open"),
                "goal": {
                    "description": str(semantic_goal.get("description") or "")[:240],
                    "beneficiary": semantic_goal.get("beneficiary"),
                    "object": semantic_goal.get("object") if isinstance(semantic_goal.get("object"), dict) else {},
                    "constraints": semantic_goal.get("constraints") if isinstance(semantic_goal.get("constraints"), dict) else {},
                },
                "open_information_gaps": [
                    {
                        "gap_id": str(gap.get("gap_id") or "")[:160],
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
    active = context.get("active_goal_snapshots")
    recent = context.get("recent_goal_snapshots")
    raw = [
        *(active if isinstance(active, list) else []),
        *(recent if isinstance(recent, list) else []),
    ]
    compact: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        metadata = goal.get("metadata") if isinstance(goal.get("metadata"), dict) else {}
        description = str(goal.get("description") or item.get("description") or "").strip()
        if not description:
            continue
        goal_id = str(item.get("goal_id") or goal.get("goal_id") or "")
        if not goal_id or goal_id in seen:
            continue
        seen.add(goal_id)
        compact.append(
            {
                "goal_id": goal_id,
                "goal_version": item.get("goal_version") or goal.get("version"),
                "responsibility_status": str(
                    item.get("responsibility_status")
                    or goal.get("responsibility_status")
                    or "open"
                ),
                "goal": {
                    "description": description[:240],
                    "object": goal.get("object") if isinstance(goal.get("object"), dict) else {},
                    "constraints": goal.get("constraints") if isinstance(goal.get("constraints"), dict) else {},
                    "output_mode": metadata.get("output_mode"),
                },
                "open_information_gaps": [
                    {
                        "gap_id": str(gap.get("gap_id") or "")[:160],
                        "description": str(gap.get("description") or "")[:160],
                        "preferred_resolution": gap.get("preferred_resolution"),
                    }
                    for gap in (item.get("open_information_gaps") or [])[:4]
                    if isinstance(gap, dict)
                ],
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


def _most_recent_assistant_utterance(
    context: dict[str, Any],
) -> dict[str, Any] | None:
    """Expose one accepted speaker-role fact without interpreting the new turn."""

    for item in reversed(_compact_recent_dialogue(context)):
        if item.get("role") == "assistant":
            return {
                "status": "available",
                "speaker": "Chromie",
                "role": "assistant",
                "text": item["text"],
            }
    return None


def _admitted_turn_clock(request: GoalInterpretationRequest) -> str | None:
    """Project the trusted Gateway receipt instant, never a guessed local timezone."""
    if request.turn_envelope is not None:
        return request.turn_envelope.received_at.isoformat()
    envelope = request.context.get("user_turn_envelope")
    raw = envelope.get("received_at") if isinstance(envelope, dict) else None
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo is not None else None


def _goal_interpretation_prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = _context_without_prompt_globals(context)
    memory = prompt_context.get("session_memory")
    if isinstance(memory, dict):
        prompt_context["session_memory"] = {
            key: value
            for key, value in memory.items()
            if key not in {"recent_user_request", "recent_assistant_response", "extracted_memory", "memory_summary", "durable_profile_memory"}
        }
    prompt_context.pop("extracted_memory", None)
    prompt_context.pop("memory_summary", None)
    return prompt_context


def _goal_interpretation_identity_context(mind: Any) -> str:
    identity: dict[str, Any] = {}
    if isinstance(mind, dict):
        raw_identity = mind.get("identity")
        if isinstance(raw_identity, dict):
            identity.update(
                {
                    key: raw_identity.get(key)
                    for key in (
                        "name",
                        "kind",
                        "age_description",
                        "family_role",
                        "model_identity_boundary",
                    )
                    if raw_identity.get(key) not in (None, "", [], {})
                }
            )
        self_model = mind.get("self_model")
        speaker = self_model.get("speaker_entity") if isinstance(self_model, dict) else None
        if isinstance(speaker, dict):
            for key in ("name", "kind"):
                if speaker.get(key) not in (None, "", [], {}):
                    identity[key] = speaker.get(key)
    profile = {"self_identity": identity or {"name": "Chromie"}}
    return (
        f"{required_json(profile, max_chars=1200, label='Goal Interpretation identity')}\n"
        "These semantic self facts may resolve identity or self-reference. "
        "Presentation style and internal profile identifiers are intentionally absent."
    )


class OllamaGoalInterpreter:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        deep_model: str | None = None,
        inference_provider: str = "ollama",
        sglang_url: str | None = None,
        sglang_priority_step: int = 100,
        timeout_ms: int,
        num_ctx: int = 4096,
        num_predict: int = 512,
        keep_alive: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.inference_provider = str(inference_provider or "ollama").strip().casefold()
        if self.inference_provider not in {"ollama", "sglang"}:
            raise ValueError(f"unsupported Goal Interpreter provider: {self.inference_provider!r}")
        self.sglang_url = str(sglang_url or "").rstrip("/")
        self.sglang_priority_step = max(1, int(sglang_priority_step))
        self.model = model
        self.deep_model = str(deep_model or model).strip() or model
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

    def build_system_prompt(self, request: GoalInterpretationRequest) -> str:
        return self.load_system_prompt()

    def build_interpretation_user_prompt(
        self, request: GoalInterpretationRequest
    ) -> str:
        mind = request.context.get("mind", {})
        session_context = _without_goal_interpretation_authority(
            _goal_interpretation_prompt_context(request.context)
        )
        recent_dialogue = _compact_recent_dialogue(request.context)
        prior_assistant_utterance = _most_recent_assistant_utterance(request.context)
        prior_assistant_context = (
            "Context-only most recent accepted Chromie/assistant utterance JSON "
            "(evidence, not a current-turn obligation):"
            f"{_bounded_json(prior_assistant_utterance, max_chars=420)}\n"
            if prior_assistant_utterance is not None
            else ""
        )
        clock = _admitted_turn_clock(request)
        clock_context = (
            "Trusted Gateway receipt instant (context, never the user's local timezone): "
            + clock + "\nPreserve the user's scheduling meaning in the outcome. "
            "Planner owns time conversion and activation planning.\n"
            if clock is not None else ""
        )
        return (
            "Current Turn:\n"
            "IMMUTABLE SOURCE TURN JSON (exact Gateway wording; read-only; "
            "Goal Interpretation owns current-turn WHAT):\n"
            f"{json.dumps(_goal_interpretation_source_turn_provenance(request), ensure_ascii=False, separators=(',', ':'))}\n"
            f"language_hint={request.language or 'auto'}\n\n"
            f"{clock_context}"
            "Authoritative source tokens (cite inclusive refs in each "
            "Responsibility.source_evidence):\n"
            f"{_bounded_json(_source_tokens(request.text), max_chars=5000)}\n\n"
            "Bounded Identity Context:\n"
            f"{_goal_interpretation_identity_context(mind)}\n\n"
            "Semantic Continuity Context:\n"
            f"{role_memory_context(request.context, role='gi')}"
            f"Bounded session/world context JSON:{_bounded_json(session_context, max_chars=900)}\n"
            "Interaction context JSON:"
            f"{_bounded_json(_without_goal_interpretation_authority(request.context.get('interaction_context') or {}), max_chars=2400)}\n"
            "Recent accepted dialogue JSON:"
            f"{_bounded_json_array(recent_dialogue, max_chars=1800)}\n"
            f"{prior_assistant_context}"
            "Retained active/recent Goal semantics with commit-safe identity and Planner-owned pending gaps JSON:"
            f"{_bounded_json_array(_compact_active_goal_snapshots(request.context), max_chars=1400)}\n"
            "Active Task/Activity progress with identity and pending clarification JSON:"
            f"{_bounded_json_array(_compact_active_task_snapshots(request.context), max_chars=1400)}\n\n"
            "Apply the system WHAT-only contract to this authoritative turn and bounded "
            "semantic Context. Return one complete schema-valid JSON decision only."
        )

    @staticmethod
    def _goal_interpretation_response_schema(
        *, admitted_turn: str = "",
    ) -> dict[str, Any]:
        """Expose complete meaning and provenance, without downstream contracts.

        The shared Responsibility also carries retained canonical projections used
        by other owners. None of those defaults grant GI model-write authority.
        """
        schema = GoalInterpretationDecision.model_json_schema()
        schema["required"] = ["confidence", "responsibilities", "unresolved"]
        item = schema["$defs"]["CognitiveResponsibilityProposal"]
        fields = ("local_ref", "output_mode", "outcome", "confidence", "source_evidence")
        item["properties"] = {name: item["properties"][name] for name in fields}
        item["required"] = list(fields)
        item["properties"]["outcome"]["description"] = (
            "Complete natural-language user request with every material detail, in the source language. "
            "Never a category name, code or underscore-separated identifier."
        )
        item["properties"]["output_mode"]["description"] = (
            "Expected human result type only; the complete request belongs in outcome."
        )
        item["properties"]["output_mode"]["enum"].remove("unspecified")
        item["properties"]["output_mode"].pop("default", None)
        item["properties"]["local_ref"] = {
            "type": "string", "enum": [f"r{i}" for i in range(1, 13)],
        }
        item["properties"]["source_evidence"] = {
            "$ref": "#/$defs/ResponsibilitySourceEvidence",
        }
        schema["properties"]["responsibilities"]["maxItems"] = 12
        token_refs = [token["ref"] for token in _source_tokens(admitted_turn)]
        if token_refs:
            evidence = schema["$defs"]["ResponsibilitySourceEvidence"]
            for name in evidence["properties"]:
                evidence["properties"][name] = {"type": "string", "enum": token_refs}
        return schema

    def build_interpretation_payload(
        self, request: GoalInterpretationRequest
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.build_system_prompt(request)},
                {"role": "user", "content": self.build_interpretation_user_prompt(request)},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            "format": self._goal_interpretation_response_schema(admitted_turn=request.text),
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        return payload

    def build_deep_interpretation_payload(
        self, request: GoalInterpretationRequest,
    ) -> dict[str, Any]:
        """One source-based depth delegation; never review a previous GI answer."""
        payload = self.build_interpretation_payload(request)
        payload["model"] = self.deep_model
        payload["messages"][0]["content"] += (
            "\n\nDeep Goal Interpretation: resolve consequential ambiguity from the "
            "original turn and bounded context only. Preserve uncertainty when that "
            "evidence is insufficient. Keep the same intent-only contract. Missing "
            "capability inputs and execution choices belong to Planner."
        )
        return payload

    @staticmethod
    def _requires_deep_semantic_interpretation(
        decision: GoalInterpretationDecision,
    ) -> bool:
        """Escalate only genuinely unresolved meaning within GI authority.

        A schema-valid compound result is not ambiguous merely because it preserves
        multiple independently satisfiable outcomes. Source-provenance
        validation protects the handoff; Planner owns HOW
        complexity after the accepted WHAT handoff.
        """

        return bool(decision.unresolved)

    @staticmethod
    def _validate_interpretation_content(
        request: GoalInterpretationRequest,
        content: str,
        *,
        response_schema: dict[str, Any] | None = None,
    ) -> GoalInterpretationDecision:
        parsed = _extract_json_object(content)
        if set(parsed) - {"confidence", "responsibilities", "unresolved"}:
            raise _GoalInterpretationAuthorityViolation("GI output contains fields outside intent authority")
        proposals = parsed.get("responsibilities")
        fields = {"local_ref", "outcome", "output_mode", "confidence", "source_evidence"}
        for item in proposals if isinstance(proposals, list) else []:
            if not isinstance(item, dict):
                continue  # Closed DTO handles malformed objects.
            if set(item) - fields:
                raise _GoalInterpretationAuthorityViolation(
                    "GI owns complete intent only; downstream fields are forbidden: "
                    + ",".join(sorted(set(item) - fields))
                )
            if "source_evidence" not in item:
                raise ValueError("GI Responsibility lacks source_evidence")
            if fields - set(item):
                raise ValueError("GI requires authored intent, confidence and source evidence")
            if item["output_mode"] == "unspecified":
                raise ValueError("GI must state the requested result type")
            for name in ("local_ref", "outcome", "output_mode"):
                if not isinstance(item[name], str) or not item[name].strip():
                    raise ValueError(f"Goal Interpretation requires authored {name}")
            if item["local_ref"] not in {f"r{i}" for i in range(1, 13)}:
                raise ValueError("GI requires a declared turn-local Responsibility reference")
            if isinstance(item["confidence"], bool) or not isinstance(item["confidence"], (int, float)):
                raise ValueError("GI requires numeric Responsibility confidence")
        decision = GoalInterpretationDecision.model_validate(parsed)
        _validate_primary_source_evidence(request, parsed)
        return decision

    async def _accept_or_deepen_interpretation(
        self,
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
    ) -> GoalInterpretationDecision:
        if not self._requires_deep_semantic_interpretation(decision):
            return decision
        logger.info(
            "goal_interpretation_deep_escalation sid=%s reason=%s",
            request.sid,
            "material_unresolved_responsibility_meaning",
        )
        try:
            payload = self.build_deep_interpretation_payload(request)
            data = await self._chat_logged(
                payload,
                stage="goal_interpretation_deep",
                request=request,
            )
            decision = self._validate_interpretation_content(
                request,
                str(data.get("message", {}).get("content") or ""),
                response_schema=payload["format"],
            )
            return decision
        except Exception as exc:
            raise InterpretationUnavailableError(
                "invalid_deep_goal_interpretation: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    async def interpret_goal(
        self, request: GoalInterpretationRequest
    ) -> GoalInterpretationDecision:
        try:
            payload = self.build_interpretation_payload(request)
            data = await self._chat_logged(
                payload,
                stage="goal_interpretation",
                request=request,
            )
        except Exception as exc:
            raise InterpretationUnavailableError(
                f"goal_interpreter_error:{type(exc).__name__}: {exc}"
            ) from exc

        content = str(data.get("message", {}).get("content") or "")
        try:
            decision = self._validate_interpretation_content(request, content, response_schema=payload["format"])
            return await self._accept_or_deepen_interpretation(request, decision)
        except _GoalInterpretationSemanticStructureViolation as exc:
            logger.warning(
                "Fast Goal Interpretation lost primary semantic/source structure "
                "sid=%s error=%s; failing closed",
                request.sid,
                exc,
            )
            raise InterpretationUnavailableError(
                "invalid_primary_goal_interpretation_semantics: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        except _GoalInterpretationAuthorityViolation as exc:
            logger.warning(
                "Fast Goal Interpretation crossed semantic authority sid=%s "
                "error=%s; failing closed",
                request.sid,
                exc,
            )
            raise InterpretationUnavailableError(
                "invalid_primary_goal_interpretation_authority: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        except (ValueError, ValidationError) as exc:
            logger.warning(
                "Invalid WHAT-only Goal Interpretation DTO sid=%s error=%s "
                "content=%r; failing closed",
                request.sid,
                exc,
                content[:500],
            )
            raise InterpretationUnavailableError(
                "invalid_primary_goal_interpretation_contract: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

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
            "compute_class": goal_interpreter_compute_class(stage).value,
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
        if self.inference_provider == "sglang":
            return await self._chat_logged(
                {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": "Reply with exactly one word: ready"}
                    ],
                    "stream": False,
                    # This readiness probe still traverses the ordinary completion
                    # diagnostics used by semantic GI calls.  A one-token SGLang
                    # cap necessarily reports finish_reason=length before the
                    # provider can emit its normal terminal marker, which is
                    # correctly indistinguishable from truncation at that shared
                    # boundary.  Give the one-word probe enough headroom to reach
                    # an ordinary terminal stop instead of weakening truncation
                    # rejection for real cognition.
                    "options": {
                        "temperature": 0,
                        "num_ctx": self.num_ctx,
                        "num_predict": 8,
                    },
                },
                stage="startup_warm",
            )
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
                provider_data = response.json()
                data = enforce_non_thinking_ollama_response(
                    provider_data, structured_output=False
                ).response
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
        if self.inference_provider == "sglang":
            if not self.sglang_url:
                raise OllamaGenerationError(
                    "Goal Interpreter SGLang URL is not configured",
                    failure_class="provider_configuration",
                    failure_domain="inference_transport",
                    architecture_attribution="not_evaluated",
                    retryable=False,
                )
            wire_payload = build_sglang_chat_payload(
                model=str(payload.get("model") or self.model),
                messages=[dict(item) for item in payload.get("messages") or [] if isinstance(item, dict)],
                compute_class=goal_interpreter_compute_class(stage),
                options=options,
                response_format=payload.get("format", "text"),
                stream=False,
                priority_step=self.sglang_priority_step,
            )
            async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
                response = await client.post(f"{self.sglang_url}/chat/completions", json=wire_payload)
                response.raise_for_status()
                provider_data = response.json()
            data = sglang_to_completion_evidence(provider_data)
            self._validate_completion(payload, data, stage=stage)
            return data
        async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            provider_data = response.json()
        try:
            boundary = enforce_non_thinking_ollama_response(
                provider_data, structured_output=bool(payload.get("format"))
            )
        except OllamaNonThinkingViolation as exc:
            raise OllamaGenerationError(
                str(exc),
                failure_class="thinking_output_violation",
                failure_domain="provider_contract",
                architecture_attribution="ollama_or_model_template",
                retryable=True,
                details={
                    "purpose": f"goal_interpreter:{stage}",
                    "model": payload.get("model") or self.model,
                    "violation": exc.reason,
                    "result_trusted": False,
                    "new_execution_allowed": False,
                },
            ) from exc
        data = boundary.response
        if boundary.recovered:
            logger.warning(
                "goal_interpreter_non_thinking_boundary_recovered stage=%s model=%s recovery=%s",
                stage,
                payload.get("model") or self.model,
                boundary.recovery,
            )
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
                transport=f"{self.inference_provider}.chat",
                request=payload,
                response=None,
                status="failed",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                correlations={
                    "sid": request.sid if request is not None else None,
                    "compute_class": goal_interpreter_compute_class(stage).value,
                },
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
            transport=f"{self.inference_provider}.chat",
            request=payload,
            response=data,
            status="accepted",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            correlations={
                "sid": request.sid if request is not None else None,
                "compute_class": goal_interpreter_compute_class(stage).value,
            },
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
