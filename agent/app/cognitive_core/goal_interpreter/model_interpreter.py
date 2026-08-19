from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
from decimal import Decimal, InvalidOperation
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


def _normalize_mechanical_goal_interpretation_dto(
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Normalize provider-shaped JSON containers without changing semantics.

    Some structured-output backends serialize a free-form JSON object as an
    array of ``{name|key, value}`` entries. The representation is mechanically
    isomorphic only when every entry has one unique explicit key, so normalize
    exactly that form and leave every ambiguous/malformed variant for normal
    contract rejection. A missing aggregate confidence is likewise derivable
    without interpretation when every Responsibility already carries one.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return parsed

    for item in responsibilities:
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, list):
            continue
        normalized: dict[str, Any] = {}
        valid = True
        for entry in bindings:
            if not isinstance(entry, dict):
                valid = False
                break
            name_values = [entry[key] for key in ("name", "key") if key in entry]
            if (
                len(name_values) != 1
                or "value" not in entry
                or not set(entry).issubset({"name", "key", "value"})
            ):
                valid = False
                break
            name = " ".join(str(name_values[0] or "").strip().split())
            if not name or name in normalized:
                valid = False
                break
            normalized[name] = entry["value"]
        if valid:
            item["bindings"] = normalized

    if "confidence" not in parsed:
        confidence_values = [
            item.get("confidence")
            for item in responsibilities
            if isinstance(item, dict)
        ]
        if confidence_values and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in confidence_values
        ):
            parsed["confidence"] = min(float(value) for value in confidence_values)
    return parsed


_EXPLICIT_NUMERIC_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])")


def _decimal_values(value: Any) -> set[Decimal]:
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, (int, float, Decimal)):
        try:
            return {Decimal(str(value))}
        except InvalidOperation:
            return set()
    if isinstance(value, str):
        result: set[Decimal] = set()
        for token in _EXPLICIT_NUMERIC_TOKEN.findall(value):
            try:
                result.add(Decimal(token))
            except InvalidOperation:
                continue
        return result
    if isinstance(value, dict):
        return {
            number
            for item in value.values()
            for number in _decimal_values(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            number
            for item in value
            for number in _decimal_values(item)
        }
    return set()


def _short_exact_surface_substrings(text: str) -> list[str]:
    """Enumerate exact source slices for a bounded decoder constraint.

    This does not identify an entity or choose its meaning. It only makes an
    invalid translated location impossible to emit during short source-based
    recovery. Longer turns retain the normal validator and fail closed without
    growing an unbounded response schema.
    """

    surface = " ".join(str(text or "").strip().split())
    if not surface or len(surface) > 40:
        return []
    values = {
        surface[start:end]
        for start in range(len(surface))
        for end in range(start + 1, len(surface) + 1)
    }
    return sorted(values, key=lambda value: (len(value), value))


def _reject_dropped_explicit_numeric_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Require explicit user quantities to survive the WHAT handoff exactly."""

    source_numbers = _decimal_values(request.text)
    if not source_numbers:
        return
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    binding_numbers = {
        number
        for item in responsibilities
        if isinstance(item, dict)
        for number in _decimal_values(item.get("bindings"))
    }
    missing = sorted(source_numbers - binding_numbers)
    if missing:
        raise _GoalInterpretationAuthorityViolation(
            "Goal Interpretation dropped or rewrote explicit numeric user binding(s): "
            + ",".join(str(value) for value in missing)
        )


def _reject_planner_shaped_goal_interpretation(parsed: dict[str, Any]) -> None:
    """Fail closed if the model attempts route/HOW/response authority."""

    for field in _FORBIDDEN_MODEL_OUTPUT_FIELDS:
        if field in parsed:
            raise _GoalInterpretationAuthorityViolation(
                f"Goal Interpretation output contains downstream-owned field {field!r}"
            )
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        for field in ("information_gaps", "resolved_gap_ids"):
            if field in item:
                raise _GoalInterpretationAuthorityViolation(
                    "Goal Interpretation responsibility "
                    f"{index} contains Planner-owned field {field!r}"
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


def _reject_fresh_evidence_output_mode_contradictions(
    parsed: dict[str, Any],
) -> None:
    """Reject a semantic completion contract the decoder failed to enforce."""

    contradictions: list[str] = []
    for index, responsibility in enumerate(parsed.get("responsibilities") or []):
        if not isinstance(responsibility, dict):
            continue
        if responsibility.get("completion_requires_fresh_evidence") is not True:
            continue
        output_mode = " ".join(
            str(responsibility.get("output_mode") or "").strip().split()
        )
        if not output_mode:
            # Current decoder schemas require the field. Retained pre-contract
            # fixtures may omit it and remain subject to Pydantic's legacy default;
            # this semantic contradiction check concerns an explicit downgrade.
            continue
        if output_mode != "capability_work":
            contradictions.append(
                f"responsibilities[{index}].output_mode={output_mode!r}"
            )
    if contradictions:
        raise _GoalInterpretationAuthorityViolation(
            "fresh-evidence Responsibilities cannot be downgraded to an ordinary "
            "observable channel: " + ", ".join(contradictions)
        )


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


def _reject_unknown_goal_refs(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Require GI Goal-continuity references to copy supplied Context exactly."""

    known_goal_ids: set[str] = set()
    for key in (
        "active_goal_snapshots",
        "recent_goal_snapshots",
        "active_task_snapshots",
        "active_task_contexts",
    ):
        raw = request.context.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            for id_key in ("goal_id", "task_id", "source_task_id"):
                value = " ".join(str(item.get(id_key) or "").strip().split())
                if value:
                    known_goal_ids.add(value)
            goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
            value = " ".join(str(goal.get("goal_id") or "").strip().split())
            if value:
                known_goal_ids.add(value)
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        target_ids = item.get("target_goal_ids") or []
        unknown_goals = sorted(
            str(value) for value in target_ids if str(value) not in known_goal_ids
        )
        if unknown_goals:
            raise _GoalInterpretationAuthorityViolation(
                f"responsibilities[{index}] targets unknown Goal IDs: "
                + ",".join(unknown_goals)
            )


def _continuity_goal_contracts(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return exact provider-neutral completion facts for retained Goals."""

    contracts: dict[str, dict[str, Any]] = {}
    active = context.get("active_goal_snapshots")
    recent = context.get("recent_goal_snapshots")
    raw = [
        *(active if isinstance(active, list) else []),
        *(recent if isinstance(recent, list) else []),
    ]
    for item in raw:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        goal_id = " ".join(
            str(item.get("goal_id") or goal.get("goal_id") or "").strip().split()
        )
        if not goal_id:
            continue
        metadata = goal.get("metadata") if isinstance(goal.get("metadata"), dict) else {}
        output_mode = " ".join(str(metadata.get("output_mode") or "").split())
        contract: dict[str, Any] = {}
        if output_mode:
            contract["output_mode"] = output_mode
        if "completion_requires_work" in metadata:
            contract["completion_requires_work"] = bool(
                metadata["completion_requires_work"]
            )
        elif metadata.get("provider_required") is True:
            # Legacy retained Goals predate explicit GI completion flags. A
            # provider-required effect still cannot become immediate speech.
            contract["completion_requires_work"] = True
        if "completion_requires_fresh_evidence" in metadata:
            contract["completion_requires_fresh_evidence"] = bool(
                metadata["completion_requires_fresh_evidence"]
            )
        contracts[goal_id] = contract
    return contracts


def _reject_continuity_completion_contract_mismatch(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject a pure continue/resume DTO that changes the retained effect.

    This is an exact cross-field contract check, not a new semantic decision:
    the model selected one supplied Goal identity and declared that the person
    wants to continue or resume it. Such a relationship cannot silently turn
    retained work into an ordinary immediate speech Responsibility.
    """

    contracts = _continuity_goal_contracts(request.context)
    if not contracts:
        return
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        relationship = str(item.get("relationship") or "").strip()
        target_ids = item.get("target_goal_ids")
        if relationship not in {"continue", "resume"} or not isinstance(
            target_ids, list
        ):
            continue
        known_targets = [
            target_id
            for raw_target_id in target_ids
            if (target_id := str(raw_target_id).strip()) in contracts
        ]
        if len(known_targets) != 1:
            continue
        target_id = known_targets[0]
        expected = contracts[target_id]
        for field in (
            "output_mode",
            "completion_requires_work",
            "completion_requires_fresh_evidence",
        ):
            if field not in expected:
                continue
            actual = item.get(field)
            if actual != expected[field]:
                raise _GoalInterpretationAuthorityViolation(
                    f"responsibilities[{index}] relationship={relationship!r} "
                    f"changes retained Goal {target_id!r} {field}: "
                    f"expected={expected[field]!r} actual={actual!r}"
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
    semantic continuity context. A violation requires one fresh source-based
    interpretation, never same-stage DTO repair of the rejected semantics.
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


def _reject_runtime_identity_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject runtime correlation identity copied into human-semantic bindings.

    Correlation IDs are present so logs and requests can be joined. They are not
    semantic context. This gate compares only model-authored scalar values with
    exact runtime-owned identities; it does not infer or repair user meaning.
    """

    runtime_identities = {
        " ".join(str(request.sid or "").strip().split()).casefold(),
    }
    envelope = request.context.get("user_turn_envelope")
    if isinstance(envelope, dict):
        for key in ("turn_id", "session_id"):
            value = " ".join(str(envelope.get(key) or "").strip().split())
            if value:
                runtime_identities.add(value.casefold())
    runtime_identities.discard("")
    if not runtime_identities:
        return

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for binding_name, value in bindings.items():
            values = value if isinstance(value, list) else [value]
            for value_index, scalar in enumerate(values):
                if not isinstance(scalar, str):
                    continue
                normalized = " ".join(scalar.strip().split()).casefold()
                if normalized not in runtime_identities:
                    continue
                suffix = f"[{value_index}]" if isinstance(value, list) else ""
                raise _GoalInterpretationAuthorityViolation(
                    "Goal Interpretation binding copied runtime correlation identity: "
                    f"responsibilities[{responsibility_index}].bindings."
                    f"{binding_name}{suffix}. Runtime/session IDs are not human "
                    "semantic evidence."
                )


_TURN_ECHO_EDGE_PUNCTUATION = " \t\r\n.!?…。！？；;，,：:\"'“”‘’"


def _normalized_turn_echo(value: str) -> str:
    """Normalize only envelope-equivalent surface form, not semantic meaning."""

    return " ".join(
        value.strip(_TURN_ECHO_EDGE_PUNCTUATION).strip().casefold().split()
    )


def _strip_language_envelope_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Mechanically discard an exact request-language echo from GI bindings.

    ``request.language`` is transport metadata, not WHAT evidence. Models may
    nevertheless copy the exact tag (for example ``zh-CN``) into a generic
    ``language`` binding on otherwise valid greetings and chat turns. That is
    harmless envelope pollution, so remove only the exact copied scalar instead
    of escalating or failing the whole interpretation.

    This boundary deliberately does *not* infer or rewrite semantic language
    facts: exact language-tag strings that occur literally in the user's turn are
    retained, and all other binding values are untouched.
    """

    language = " ".join(str(request.language or "").strip().casefold().split())
    if not language:
        return
    literal_turn = (request.text or "").casefold()
    if language in literal_turn:
        return
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for item in responsibilities:
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for binding_name, value in list(bindings.items()):
            if isinstance(value, str):
                normalized = " ".join(value.strip().casefold().split())
                if normalized == language:
                    bindings.pop(binding_name, None)
                continue
            if not isinstance(value, list):
                continue
            filtered = [
                scalar
                for scalar in value
                if not (
                    isinstance(scalar, str)
                    and " ".join(scalar.strip().casefold().split()) == language
                )
            ]
            if not filtered:
                bindings.pop(binding_name, None)
            elif len(filtered) != len(value):
                bindings[binding_name] = filtered


def _strip_redundant_conversational_turn_echo_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Discard a whole-turn echo only for one already-atomic speech Responsibility.

    A model may redundantly preserve a short acknowledgement such as ``Yeah.`` in
    ``bindings.user_input`` even though the same single conversational WHAT is
    already carried by ``outcome``.  For one explicit ``output_mode=speech``
    Responsibility with no downstream work or fresh-evidence requirement, that
    exact whole-turn scalar is envelope redundancy rather than hidden structure.

    The rule is intentionally narrow.  Embodied, capability, media, authored-vocal,
    multi-Responsibility, or work-requiring interpretations retain the fail-closed
    whole-turn guard below because an opaque copied turn can conceal coordinated
    independently satisfiable effects.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list) or len(responsibilities) != 1:
        return
    item = responsibilities[0]
    if not isinstance(item, dict):
        return
    if str(item.get("output_mode") or "") != "speech":
        return
    if item.get("completion_requires_work") is not False:
        return
    if item.get("completion_requires_fresh_evidence") is not False:
        return
    bindings = item.get("bindings")
    if not isinstance(bindings, dict):
        return
    turn_echo = _normalized_turn_echo(request.text or "")
    if not turn_echo:
        return
    for binding_name, value in list(bindings.items()):
        if isinstance(value, str):
            if _normalized_turn_echo(value) == turn_echo:
                bindings.pop(binding_name, None)
            continue
        if not isinstance(value, list):
            continue
        filtered = [
            scalar
            for scalar in value
            if not (
                isinstance(scalar, str)
                and _normalized_turn_echo(scalar) == turn_echo
            )
        ]
        if not filtered:
            bindings.pop(binding_name, None)
        elif len(filtered) != len(value):
            bindings[binding_name] = filtered


def _reject_transport_echo_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject a whole admitted turn masquerading as an atomic semantic binding.

    Whole-turn copying can conceal collapsed multi-effect meaning, so it remains
    a fail-closed semantic-structure violation. Exact request-language echoes are
    sanitized separately as mechanically removable envelope noise.
    """

    turn_echo = _normalized_turn_echo(request.text or "")
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for binding_name, value in bindings.items():
            values = value if isinstance(value, list) else [value]
            for value_index, scalar in enumerate(values):
                if not isinstance(scalar, str):
                    continue
                normalized = _normalized_turn_echo(scalar)
                if not (turn_echo and normalized == turn_echo):
                    continue
                suffix = f"[{value_index}]" if isinstance(value, list) else ""
                raise _GoalInterpretationSemanticStructureViolation(
                    "Goal Interpretation binding copied request-envelope data instead "
                    f"of an atomic semantic fact: responsibilities[{responsibility_index}]"
                    f".bindings.{binding_name}{suffix} copied the whole admitted turn."
                )


def _reject_untyped_coordination_bindings(parsed: dict[str, Any]) -> None:
    """Require coordination edges to reference sibling Responsibilities.

    A free-form action phrase hidden in a coordination binding can collapse an
    independently observable effect while leaving a schema-shaped DTO.  Exact
    turn-local references make the relation auditable without interpreting the
    phrase at this mechanical boundary.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    local_refs = {
        str(item.get("local_ref") or "").strip()
        for item in responsibilities
        if isinstance(item, dict) and str(item.get("local_ref") or "").strip()
    }
    relation_tokens = {
        "concurrent",
        "concurrently",
        "parallel",
        "simultaneous",
        "simultaneously",
        "together",
    }
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        own_ref = str(item.get("local_ref") or "").strip()
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for binding_name, value in bindings.items():
            normalized_name = "_".join(
                str(binding_name).strip().casefold().replace("-", "_").split()
            )
            scalar_values = value if isinstance(value, list) else [value]
            normalized_scalar_values = {
                "_".join(
                    str(candidate).strip().casefold().replace("-", "_").split()
                )
                for candidate in scalar_values
                if str(candidate).strip()
            }
            if not (
                "coordinat" in normalized_name
                or "combin" in normalized_name
                or "simultan" in normalized_name
                or normalized_name
                in {"alongside", "concurrent_with", "parallel_with", "with"}
                or (
                    normalized_name == "mode"
                    and normalized_scalar_values.issubset(relation_tokens)
                )
            ):
                continue
            normalized_values = {
                str(candidate).strip()
                for candidate in scalar_values
                if str(candidate).strip()
            }
            if (
                normalized_values
                and normalized_values.issubset(local_refs - {own_ref})
            ):
                continue
            # A controlled relation value is structural timing evidence and
            # cannot conceal another effect's wording. It is safe only when the
            # DTO already exposes multiple sibling Responsibilities.
            if (
                len(local_refs) > 1
                and normalized_scalar_values
                and normalized_scalar_values.issubset(relation_tokens)
            ):
                continue
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation coordination bindings must contain only exact "
                "sibling local_ref values; free-form effect wording can conceal a "
                f"missing Responsibility at responsibilities[{responsibility_index}]"
                f".bindings.{binding_name}."
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
                    "completion_requires_work": metadata.get(
                        "completion_requires_work",
                        True if metadata.get("provider_required") is True else None,
                    ),
                    "completion_requires_fresh_evidence": metadata.get(
                        "completion_requires_fresh_evidence"
                    ),
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


def _most_recent_assistant_utterance(context: dict[str, Any]) -> dict[str, Any]:
    """Expose one accepted speaker-role fact without interpreting the new turn."""

    for item in reversed(_compact_recent_dialogue(context)):
        if item.get("role") == "assistant":
            return {
                "status": "available",
                "speaker": "Chromie",
                "role": "assistant",
                "text": item["text"],
            }
    return {"status": "unavailable"}


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
        deep_model: str | None = None,
        timeout_ms: int,
        num_ctx: int = 4096,
        num_predict: int = 512,
        keep_alive: str | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
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
            "Most recent accepted Chromie/assistant utterance JSON:"
            f"{_bounded_json(_most_recent_assistant_utterance(request.context), max_chars=420)}\n"
            "Retained active/recent Goal semantics with commit-safe identity and Planner-owned pending gaps JSON:"
            f"{_bounded_json_array(_compact_active_goal_snapshots(request.context), max_chars=1400)}\n"
            "Active Task/Activity progress with identity and pending clarification JSON:"
            f"{_bounded_json_array(_compact_active_task_snapshots(request.context), max_chars=1400)}\n\n"
            "Interpret contextual WHAT. For every Responsibility, copy exactly one "
            "relationship protocol token from new, continue, modify, clarify, confirm, "
            "reject, cancel, pause, resume, merge, split, or reference, and copy exact "
            "target Goal IDs. Never inflect, conjugate, translate, or paraphrase a "
            "relationship token. A short answer to a pending clarification supplies the "
            "applicable semantic binding and relates to that Goal; it is not an isolated "
            "new request. Do not create, resolve, classify, or copy an InformationGap. "
            "Do not decide that a Capability/execution parameter is missing or choose "
            "ask_user, context, observation, query, or default. Missing execution inputs "
            "belong to Fast Planner. External Evidence is fresh Evidence, not semantic "
            "uncertainty or a value to ask the user for. Goal Association will verify and "
            "commit the Goal relationship. "
            "Preserve speaker and actor perspective: the user's first person belongs "
            "to the user, while second-person references addressed to Chromie belong "
            "to Chromie. A question about what Chromie just said uses the most recent "
            "accepted assistant utterance from dialogue and is new conversational work, "
            "not continuation of the prior utterance's Goal. "
            "A declarative statement that explains why a requested answer matters, "
            "describes the person's situation, or states a future plan is context "
            "unless the person also asks Chromie to do something with it. Never invent "
            "a Responsibility to confirm, acknowledge, remember, record, schedule, "
            "monitor, or act on that statement. "
            "A Responsibility that continues or resumes one supplied Goal must preserve "
            "that Goal's provider-neutral output_mode, completion_requires_work, and "
            "completion_requires_fresh_evidence contract. Continuation of body action, "
            "media, information work, or vocal performance never becomes ordinary "
            "speech merely because the current turn is a short reference. "
            "Preserve deictic spatial meaning such as here/there, inside/outside, "
            "ahead/behind, and equivalent expressions in any language as an exact "
            "current-turn location or direction binding when it changes the outcome. "
            "Return responsibilities, confidence, and unresolved semantic uncertainty. "
            "For directly named entities, preserve "
            "the exact current-turn user-language surface in bindings; never translate or "
            "provider-canonicalize it. Perform a literal surface audit before returning: "
            "The request-envelope language tag and the whole Latest user input are not "
            "semantic bindings; never copy either into bindings as a substitute for "
            "atomic material facts. A coordination binding may contain only exact "
            "sibling local_ref values, never another effect's free-form wording. "
            "every current-turn named or deictic location binding value must occur as "
            "one exact contiguous substring in Latest user input. For this rule the "
            "authoritative input is "
            f"{json.dumps(request.text, ensure_ascii=False)}; a translated equivalent "
            "does not occur there and is invalid. Preserve every explicit Arabic "
            "numeric token from Latest user input verbatim in an atomic material "
            "binding; never spell it out, translate it, round it, or replace it with "
            "a default. Before choosing a completion branch, audit whether trusted "
            "Context already contains the complete answer evidence. If an external, "
            "private, runtime, observed, or changing fact is requested but absent, "
            "set output_mode=capability_work, completion_requires_work=true, and "
            "completion_requires_fresh_evidence=true. The input being a question or "
            "the result eventually being spoken never makes absent evidence into "
            "output_mode=speech. No route, intent, response wording, Activity, Work, "
            "Plan, Capability, Tool, provider, executable args, or input-resolution "
            "strategy. Copy only Goal IDs explicitly supplied in Context."
        )

    @staticmethod
    def _goal_interpretation_response_schema(
        *,
        forbidden_unresolved_values: tuple[str, ...] = (),
        new_relationship_only: bool = False,
        allowed_goal_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        schema = GoalInterpretationDecision.model_json_schema()
        schema["additionalProperties"] = False
        schema["required"] = ["confidence", "responsibilities", "unresolved"]
        if forbidden_unresolved_values:
            unresolved = schema.get("properties", {}).get("unresolved")
            if isinstance(unresolved, dict):
                unresolved["items"] = {
                    "type": "string",
                    "not": {"enum": list(forbidden_unresolved_values)},
                }
        responsibility = schema.get("$defs", {}).get(
            "CognitiveResponsibilityProposal"
        )
        if isinstance(responsibility, dict):
            required = [
                "local_ref",
                "outcome",
                "bindings",
                "output_mode",
                "relationship",
                "target_goal_ids",
                "completion_requires_work",
                "completion_requires_fresh_evidence",
                "confidence",
            ]
            if new_relationship_only:
                properties = responsibility.get("properties")
                if isinstance(properties, dict):
                    properties.pop("relationship", None)
                    properties.pop("target_goal_ids", None)
                    properties.pop("schema_version", None)
                required = [
                    item
                    for item in required
                    if item not in {"relationship", "target_goal_ids"}
                ]
            responsibility["required"] = required
            outcome = responsibility.get("properties", {}).get("outcome")
            if isinstance(outcome, dict):
                outcome["description"] = (
                    "Exactly one independently satisfiable provider-neutral outcome. "
                    "Never combine coordinated positive effects: each embodied, vocal, "
                    "media, information, or conversational effect that can be accepted "
                    "or rejected on its own requires a sibling Responsibility."
                )
            output_mode = responsibility.get("properties", {}).get("output_mode")
            if isinstance(output_mode, dict):
                output_mode.pop("enum", None)
                output_mode_variants = [
                    {
                        "const": "singing",
                        "description": (
                            "A requested act of singing or song, with or without lyrics."
                        ),
                    },
                    {
                        "const": "body_action",
                        "description": "Locomotion, gaze, blink, gesture, or posture.",
                    },
                    {
                        "const": "speech",
                        "description": (
                            "An immediate conversational answer requiring no absent "
                            "external, private, runtime, observed, or changing evidence."
                        ),
                    },
                    {
                        "const": "capability_work",
                        "description": "Fresh information or persistent world-state work.",
                    },
                    {
                        "const": "styled_speech",
                        "description": (
                            "Spoken words with emotion/style but no song or melody."
                        ),
                    },
                    {
                        "const": "recitation",
                        "description": "Recitation of authored text, not singing.",
                    },
                    {
                        "const": "humming",
                        "description": "Requested humming without words.",
                    },
                    {
                        "const": "nonverbal_vocalization",
                        "description": (
                            "A non-speech voice sound such as laughing, sighing, or "
                            "coughing; excludes singing, songs, melody, lyrics, and humming."
                        ),
                    },
                    {
                        "const": "media_playback",
                        "description": "Control or playback of existing media.",
                    },
                ]
                output_mode["oneOf"] = output_mode_variants
                output_mode["description"] = (
                    "Provider-neutral completion category for this one atomic outcome, "
                    "not its eventual response transport. Fresh external information "
                    "is capability_work even when Chromie will later speak the grounded "
                    "answer; speech is only an immediate ordinary answer authored from "
                    "supplied trusted context without fresh acquisition or downstream "
                    "work. "
                    "Singing or a song is singing, never styled_speech, speech, "
                    "nonverbal_vocalization, capability_work, or body_action. "
                    "nonverbal_vocalization excludes singing, songs, melody, lyrics, "
                    "and humming. styled_speech means spoken "
                    "words with requested emotion/style but no melody or song. "
                    "Blinking/locomotion are body_action; ordinary conversation is "
                    "speech. No catch-all mode "
                    "is available: choose the exact source-grounded category."
                )
            relationship = responsibility.get("properties", {}).get(
                "relationship"
            )
            if isinstance(relationship, dict):
                relationship.pop("enum", None)
                relationship["oneOf"] = [
                    {
                        "const": value,
                        "description": description,
                    }
                    for value, description in (
                        ("continue", "Advance the same unfinished Goal unchanged."),
                        ("modify", "Change material meaning of the same Goal."),
                        ("clarify", "Supply missing meaning for the same Goal."),
                        ("confirm", "Approve a pending proposal for the Goal."),
                        ("reject", "Decline a pending proposal for the Goal."),
                        ("cancel", "Cancel the supplied Goal."),
                        ("pause", "Pause the supplied Goal."),
                        ("resume", "Resume a paused supplied Goal."),
                        ("merge", "Merge multiple supplied Goals."),
                        ("split", "Split one supplied Goal into distinct Goals."),
                        ("reference", "Refer to supplied Goal meaning without changing it."),
                        ("new", "Create a genuinely independent Responsibility."),
                    )
                ]
                relationship["description"] = (
                    "Copy exactly one canonical relationship token; never inflect, "
                    "pluralize, or paraphrase it."
                )
            target_goal_ids = responsibility.get("properties", {}).get(
                "target_goal_ids"
            )
            if isinstance(target_goal_ids, dict) and allowed_goal_ids:
                target_goal_ids["items"] = {
                    "type": "string",
                    "enum": sorted(allowed_goal_ids),
                }
                target_goal_ids["uniqueItems"] = True
            if not new_relationship_only:
                responsibility.setdefault("allOf", []).append(
                    {
                        "if": {
                            "properties": {"relationship": {"const": "new"}},
                            "required": ["relationship"],
                        },
                        "then": {
                            "properties": {"target_goal_ids": {"maxItems": 0}}
                        },
                        "else": {
                            "properties": {"target_goal_ids": {"minItems": 1}},
                            "required": ["target_goal_ids"],
                        },
                    }
                )
            # Ollama's structured decoder accepted an object that violated an
            # if/then dependency here. Its grammar also treats a nested object
            # oneOf as the complete object shape rather than intersecting it with
            # sibling properties, so each disjoint branch must repeat the complete
            # Responsibility contract. Complete disjoint branches make both an
            # illegal fresh-evidence + speech tuple and an illegal downstream-work
            # + speech tuple unrepresentable without dropping semantic fields.
            base_properties = responsibility.pop("properties")
            branch_required = responsibility.pop("required")
            responsibility.pop("additionalProperties", None)
            fresh_properties = copy.deepcopy(base_properties)
            fresh_properties["completion_requires_fresh_evidence"] = {
                "const": True,
                "description": (
                    "The correct answer needs absent external, private, runtime, "
                    "observed, or changing evidence."
                ),
            }
            fresh_properties["completion_requires_work"] = {
                "const": True,
                "description": "Evidence acquisition remains after this interpretation.",
            }
            fresh_properties["output_mode"] = {
                "const": "capability_work",
                "description": (
                    "Provider-neutral fresh evidence acquisition, even when the "
                    "grounded result will later be spoken."
                ),
            }
            immediate_speech_properties = copy.deepcopy(base_properties)
            immediate_speech_properties["completion_requires_fresh_evidence"] = {
                "const": False
            }
            immediate_speech_properties["completion_requires_work"] = {
                "const": False,
                "description": "No evidence acquisition or downstream effect remains.",
            }
            immediate_speech_properties["output_mode"] = {
                "const": "speech",
                "description": (
                    "Immediate ordinary conversation whose answer does not depend on "
                    "absent external, private, runtime, observed, or changing evidence."
                ),
            }
            non_fresh_work_properties = copy.deepcopy(base_properties)
            non_fresh_work_properties["completion_requires_fresh_evidence"] = {
                "const": False
            }
            non_fresh_work_properties["completion_requires_work"] = {"const": True}
            work_output_mode = copy.deepcopy(base_properties["output_mode"])
            work_output_mode["oneOf"] = [
                item
                for item in work_output_mode.get("oneOf", [])
                if item.get("const") != "speech"
            ]
            non_fresh_work_properties["output_mode"] = work_output_mode
            responsibility["oneOf"] = [
                {
                    "title": "Absent external or changing evidence",
                    "type": "object",
                    "properties": fresh_properties,
                    "required": branch_required,
                    "additionalProperties": False,
                },
                {
                    "title": "Immediate answer with no evidence acquisition",
                    "type": "object",
                    "properties": immediate_speech_properties,
                    "required": branch_required,
                    "additionalProperties": False,
                },
                {
                    "title": "Non-fresh downstream work",
                    "type": "object",
                    "properties": non_fresh_work_properties,
                    "required": branch_required,
                    "additionalProperties": False,
                },
            ]
        return schema

    @staticmethod
    def _already_bound_unresolved_values(
        validation_error: Exception,
    ) -> tuple[str, ...]:
        if not isinstance(validation_error, ValidationError):
            return ()

        def scalar_texts(value: Any) -> set[str]:
            if isinstance(value, str):
                normalized = " ".join(value.strip().casefold().split())
                return {normalized} if normalized else set()
            if isinstance(value, dict):
                return {
                    text
                    for item in value.values()
                    for text in scalar_texts(item)
                }
            if isinstance(value, (list, tuple)):
                return {
                    text
                    for item in value
                    for text in scalar_texts(item)
                }
            return set()

        rejected_values: set[str] = set()
        for error in validation_error.errors(include_url=False):
            if "already-bound semantic values are not unresolved" not in str(
                error.get("msg") or ""
            ):
                continue
            rejected = error.get("input")
            if not isinstance(rejected, dict):
                continue
            bound_values = {
                text
                for item in rejected.get("responsibilities") or []
                if isinstance(item, dict)
                for text in scalar_texts(item.get("bindings") or {})
            }
            rejected_values.update(
                value
                for item in rejected.get("unresolved") or []
                if (value := " ".join(str(item or "").strip().split()))
                and value.casefold() in bound_values
            )
        return tuple(sorted(rejected_values))

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
            "format": self._goal_interpretation_response_schema(
                new_relationship_only=not bool(
                    _canonical_goal_ids_from_context(request.context)
                ),
                allowed_goal_ids=_canonical_goal_ids_from_context(request.context),
            ),
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
        del previous_content
        forbidden_unresolved_values = self._already_bound_unresolved_values(
            validation_error
        )
        payload = self.build_interpretation_payload(request)
        payload["format"] = self._goal_interpretation_response_schema(
            forbidden_unresolved_values=forbidden_unresolved_values,
            new_relationship_only=not bool(
                _canonical_goal_ids_from_context(request.context)
            ),
            allowed_goal_ids=_canonical_goal_ids_from_context(request.context),
        )
        bound_uncertainty_repair = (
            " The rejected DTO copied already-resolved binding values into top-level "
            "unresolved. Preserve those bindings and remove those exact values from "
            "unresolved; retain only genuine uncertainty about WHAT the user means."
            if forbidden_unresolved_values
            else ""
        )
        payload["messages"] = [
            {
                "role": "system",
                "content": (
                    self.load_system_prompt()
                    + "\n\nDTO Repair: return one corrected WHAT-only Goal Interpretation JSON object. "
                    "For every closed string field, copy one exact protocol token from "
                    "the schema; never inflect, conjugate, translate, or paraphrase it. "
                    "Remove every field outside the schema. Never translate a rejected "
                    "route/intent/Capability/Activity/Work/Plan/provider field into another "
                    "implementation hint. Preserve only the human outcome, material semantic "
                    "bindings, supplied Goal relationships, "
                    "the exact provider-neutral output_mode, "
                    "work/fresh-evidence requirements, confidence, and genuine "
                    "semantic uncertainty. Never create/resolve an InformationGap or "
                    "choose input-source/default/clarification policy. A directly named "
                    "entity binding must copy the exact "
                    "current-turn surface; never translate or transliterate it. Provider timezone "
                    "or clock-range choices for an already-preserved relative time are not semantic "
                    "uncertainty. The request-envelope language tag and the whole Latest "
                    "user input are not semantic bindings. Decompose each independently "
                    "observable requested effect into a sibling Responsibility and bind "
                    "only its atomic material facts."
                    + bound_uncertainty_repair
                    + " Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    self.build_interpretation_user_prompt(request)
                    + "\n\nThe previous output violated the WHAT-only typed contract. "
                    "Regenerate from the authoritative user meaning and bounded semantic "
                    "context above. Copy identities only from supplied Context; do not copy "
                    "any field, identifier, wording, or implementation hint from the "
                    "rejected output. Return only the new "
                    "schema object."
                ),
            },
        ]
        return payload

    def build_deep_interpretation_payload(
        self,
        request: GoalInterpretationRequest,
        *,
        constrain_location_provenance: bool = False,
    ) -> dict[str, Any]:
        """Build one source-based Deep GI escalation with unchanged authority.

        The accepted Fast DTO is deliberately absent.  Deep Goal Interpretation
        re-reads the authoritative turn and bounded semantic context instead of
        reviewing or repairing prior model wording.
        """

        payload = self.build_interpretation_payload(request)
        payload["model"] = self.deep_model
        # The deeper source-based pass is a separate semantic invocation, not
        # provider chain-of-thought. Qwen can spend the entire bounded structured-
        # output budget in provider thinking and return no DTO, so keep that
        # transport mode disabled just like every other maintained JSON boundary.
        payload["think"] = False
        payload["messages"] = [
            {
                "role": "system",
                "content": (
                    self.load_system_prompt()
                    + "\n\nDeep Goal Interpretation: use broader reasoning over the "
                    "authoritative turn and bounded semantic context, but keep exactly "
                    "the same WHAT-only authority and output schema. Reconsider only "
                    "genuine consequential ambiguity in the person's intended outcome, "
                    "scope, Goal relationship, or referent. Preserve unresolved meaning "
                    "when the source does not determine it. A missing execution input or "
                    "external answer is not semantic ambiguity. Do not create or resolve "
                    "an InformationGap; do not choose ask_user, context, observation, "
                    "query, default, Work, a Capability, provider, or executable arguments. "
                    "This source-based pass must complete an atomicity audit before JSON: "
                    "count every independently observable effect coordinated by while, "
                    "simultaneously, Chinese 边…边…, or equivalent grammar. If the source "
                    "coordinates N effects that a person could accept or reject separately, "
                    "responsibilities must contain N sibling items. Never hide one effect "
                    "inside another item's outcome or binding. A coordination binding may "
                    "contain only exact sibling local_ref values, not words naming an action. "
                    "Audit semantic provenance before returning: every explicit current-turn "
                    "entity, identity, number, and continuity binding must preserve the exact "
                    "authoritative source or supplied typed Context. Never translate, "
                    "transliterate, infer, or copy a transport/runtime identifier into a "
                    "semantic binding. "
                    "Audit the completion contract as one semantic unit: when correct "
                    "completion requires fresh external/private/runtime/observed evidence, "
                    "set completion_requires_fresh_evidence=true, "
                    "completion_requires_work=true, and output_mode=capability_work. "
                    "Never label that evidence work as ordinary speech merely because its "
                    "result will later be spoken. "
                    "Audit declarative context before counting outcomes: an explanation, "
                    "personal situation, or stated future plan is not another "
                    "Responsibility unless the source actually asks Chromie to confirm, "
                    "acknowledge, remember, record, schedule, monitor, or act on it. "
                    "Return one final JSON object only."
                ),
            },
            {
                "role": "user",
                "content": (
                    self.build_interpretation_user_prompt(request)
                    + "\n\nPerform one fresh Deep interpretation from the source above. "
                    "No prior interpretation DTO is supplied or authoritative. First count "
                    "the source's independently observable effects; the final number of "
                    "responsibilities must equal that count."
                ),
            },
        ]
        if constrain_location_provenance:
            exact_surfaces = _short_exact_surface_substrings(request.text)
            responsibility_schema = (
                payload.get("format", {})
                .get("$defs", {})
                .get("CognitiveResponsibilityProposal", {})
            )
            branches = (
                responsibility_schema.get("oneOf", [])
                if isinstance(responsibility_schema, dict)
                else []
            )
            if exact_surfaces:
                for branch in branches:
                    binding_schema = (
                        branch.get("properties", {}).get("bindings")
                        if isinstance(branch, dict)
                        else None
                    )
                    if not isinstance(binding_schema, dict):
                        continue
                    binding_schema.setdefault("properties", {})["location"] = {
                        "type": "string",
                        "enum": exact_surfaces,
                        "description": (
                            "If location is present, copy one exact contiguous source "
                            "surface; never translate or transliterate it."
                        ),
                    }
        return payload

    @staticmethod
    def _requires_deep_semantic_interpretation(
        decision: GoalInterpretationDecision,
    ) -> bool:
        """Escalate only genuinely unresolved meaning within GI authority.

        A schema-valid compound result is not ambiguous merely because it preserves
        multiple independently satisfiable outcomes. Atomicity and numeric-binding
        validators protect dropped effects before this boundary; Planner owns HOW
        complexity after the accepted WHAT handoff.
        """

        if decision.unresolved:
            return True
        fresh_evidence_count = sum(
            1
            for responsibility in decision.responsibilities
            if responsibility.completion_requires_fresh_evidence
        )
        return fresh_evidence_count > 1

    @staticmethod
    def _validate_interpretation_content(
        request: GoalInterpretationRequest,
        content: str,
    ) -> GoalInterpretationDecision:
        parsed = _extract_json_object(content)
        _normalize_mechanical_goal_interpretation_dto(parsed)
        _reject_planner_shaped_goal_interpretation(parsed)
        _reject_fresh_evidence_output_mode_contradictions(parsed)
        _reject_canonical_goal_identity_refs(request, parsed)
        _reject_unknown_goal_refs(request, parsed)
        _reject_continuity_completion_contract_mismatch(request, parsed)
        _reject_unprovenanced_location_bindings(request, parsed)
        _reject_runtime_identity_bindings(request, parsed)
        _strip_language_envelope_bindings(request, parsed)
        _strip_redundant_conversational_turn_echo_bindings(request, parsed)
        _reject_transport_echo_bindings(request, parsed)
        _reject_untyped_coordination_bindings(parsed)
        _reject_dropped_explicit_numeric_bindings(request, parsed)
        return GoalInterpretationDecision.model_validate(parsed)

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
            (
                "material_unresolved_responsibility_meaning"
                if decision.unresolved
                else "multiple_fresh_evidence_responsibility_claims"
            ),
        )
        try:
            data = await self._chat_logged(
                self.build_deep_interpretation_payload(request),
                stage="goal_interpretation_deep",
                request=request,
            )
            return self._validate_interpretation_content(
                request,
                str(data.get("message", {}).get("content") or ""),
            )
        except Exception as exc:
            raise InterpretationUnavailableError(
                "invalid_deep_goal_interpretation: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

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
            raise InterpretationUnavailableError(
                f"goal_interpreter_error:{type(exc).__name__}: {exc}"
            ) from exc

        content = str(data.get("message", {}).get("content") or "")
        try:
            decision = self._validate_interpretation_content(request, content)
            return await self._accept_or_deepen_interpretation(request, decision)
        except _GoalInterpretationSemanticStructureViolation as exc:
            logger.warning(
                "Fast Goal Interpretation lost atomic source structure sid=%s "
                "error=%s; escalating once from source",
                request.sid,
                exc,
            )
            try:
                deep = await self._chat_logged(
                    self.build_deep_interpretation_payload(request),
                    stage="goal_interpretation_deep",
                    request=request,
                )
                return self._validate_interpretation_content(
                    request,
                    str(deep.get("message", {}).get("content") or ""),
                )
            except Exception as deep_exc:
                raise InterpretationUnavailableError(
                    "invalid_deep_goal_interpretation_after_source_structure_loss: "
                    f"{type(deep_exc).__name__}: {deep_exc}"
                ) from deep_exc
        except _GoalInterpretationAuthorityViolation as exc:
            logger.warning(
                "Fast Goal Interpretation crossed semantic authority sid=%s "
                "error=%s; escalating once from source",
                request.sid,
                exc,
            )
            try:
                deep = await self._chat_logged(
                    self.build_deep_interpretation_payload(
                        request,
                        constrain_location_provenance=True,
                    ),
                    stage="goal_interpretation_deep",
                    request=request,
                )
                decision = self._validate_interpretation_content(
                    request,
                    str(deep.get("message", {}).get("content") or ""),
                )
                return await self._accept_or_deepen_interpretation(request, decision)
            except Exception as deep_exc:
                raise InterpretationUnavailableError(
                    "invalid_deep_goal_interpretation_after_authority_violation: "
                    f"{type(deep_exc).__name__}: {deep_exc}"
                ) from deep_exc
        except (ValueError, ValidationError) as exc:
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
                decision = self._validate_interpretation_content(
                    request,
                    str(repaired.get("message", {}).get("content") or ""),
                )
                return await self._accept_or_deepen_interpretation(request, decision)
            except Exception as repair_exc:
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
