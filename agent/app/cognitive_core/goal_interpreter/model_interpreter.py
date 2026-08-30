from __future__ import annotations

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

from ...prompt_projection import bounded_json
from .errors import InterpretationUnavailableError
from .schema import (
    GoalInterpretationDecision,
    GoalInterpretationRequest,
)


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


class _GoalInterpretationLocationProvenanceViolation(
    _GoalInterpretationAuthorityViolation
):
    """A location field crossed GI's exact source/context provenance boundary."""


class _GoalInterpretationSpeedProvenanceViolation(
    _GoalInterpretationSemanticStructureViolation
):
    """A speed field was invented or conflicts with another typed dimension."""


class _GoalInterpretationDurationProvenanceViolation(
    _GoalInterpretationSemanticStructureViolation
):
    """A duration field was invented or lost its source/context scalar."""


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


def _strip_bound_values_from_unresolved(parsed: dict[str, Any]) -> None:
    """Remove exact DTO self-contradictions without interpreting user meaning.

    A scalar value cannot simultaneously be a resolved binding and unresolved
    meaning in the same model-owned decision.  Removing only byte-equivalent
    normalized duplicates is a mechanical projection of that closed contract;
    every other unresolved item remains untouched.
    """

    responsibilities = parsed.get("responsibilities")
    unresolved = parsed.get("unresolved")
    if not isinstance(responsibilities, list) or not isinstance(unresolved, list):
        return

    def scalar_texts(value: Any) -> set[str]:
        if isinstance(value, str):
            normalized = " ".join(value.strip().casefold().split())
            return {normalized} if normalized else set()
        if isinstance(value, dict):
            return {
                text
                for nested in value.values()
                for text in scalar_texts(nested)
            }
        if isinstance(value, (list, tuple)):
            return {
                text for nested in value for text in scalar_texts(nested)
            }
        return set()

    bound_values = {
        text
        for item in responsibilities
        if isinstance(item, dict)
        for text in scalar_texts(item.get("bindings") or {})
    }
    parsed["unresolved"] = [
        item
        for item in unresolved
        if " ".join(str(item or "").strip().casefold().split())
        not in bound_values
    ]


def _strip_redundant_outcome_echo_bindings(parsed: dict[str, Any]) -> None:
    """Remove fields that duplicate the Responsibility's authoritative outcome.

    ``action``, ``activity``, ``effect``, and ``outcome`` are not material binding
    dimensions. Keeping a second free-form copy lets a merged candidate's wording
    contaminate freshly segmented siblings even though ``outcome`` already owns the
    observable effect. Goal Association already excludes these names from canonical
    bindings; normalize the same closed representation at the earlier owner.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for item in responsibilities:
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for raw_name in list(bindings):
            name = "_".join(
                str(raw_name).strip().casefold().replace("-", "_").split()
            )
            if name in {"action", "activity", "effect", "outcome"}:
                bindings.pop(raw_name, None)


_HIDDEN_EFFECT_OR_HOW_BINDING_TOKENS = {
    "action",
    "actions",
    "activity",
    "activities",
    "effect",
    "effects",
    "outcome",
    "outcomes",
    "capability",
    "capabilities",
    "skill",
    "skills",
    "provider",
    "providers",
    "execution",
    "executions",
}
_RETAINED_CONTEXT_EFFECT_BINDING_NAMES = {"previous_action", "prior_action"}


def _is_hidden_effect_or_how_binding_name(raw_name: Any) -> bool:
    normalized = "_".join(
        str(raw_name).strip().casefold().replace("-", "_").split()
    )
    if normalized in _RETAINED_CONTEXT_EFFECT_BINDING_NAMES:
        return False
    tokens = {token for token in normalized.split("_") if token}
    return bool(tokens & _HIDDEN_EFFECT_OR_HOW_BINDING_TOKENS)


def _reject_hidden_effect_or_how_bindings(parsed: dict[str, Any]) -> None:
    """Reject binding dimensions that conceal another effect or downstream HOW.

    Exact ``action``/``effect`` echoes are removed by the normalization above.
    Compound names such as ``concurrent_action`` can instead hide a missing
    sibling Responsibility, while Capability/Skill/provider/execution names cross
    GI's WHAT-only authority.  This is a mechanical field-name contract, not a
    phrase-to-intent rule; source-based deep GI gets the one allowed retry.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        bindings = item.get("bindings") if isinstance(item, dict) else None
        if not isinstance(bindings, dict):
            continue
        for raw_name in bindings:
            if _is_hidden_effect_or_how_binding_name(raw_name):
                raise _GoalInterpretationSemanticStructureViolation(
                    "Goal Interpretation binding conceals an observable effect or "
                    "downstream HOW field: "
                    f"responsibilities[{responsibility_index}].bindings.{raw_name}"
                )


_MALFORMED_BINDING_NAME = re.compile(r"[{}\[\]\"'“”‘’,:;/\\]")
_MALFORMED_BINDING_VALUE = re.compile(r"[\"”]\s*[:：]|//|/\*")
_CORRUPTED_COUNT_BINDING = re.compile(
    r"^\s*count\s*[\"'“”‘’]*\s*[:：]\s*([+-]?\d+)(?:\D|$)",
    re.IGNORECASE,
)


def _normalize_corrupted_count_binding_names(parsed: dict[str, Any]) -> None:
    """Recover one mechanically fused canonical ``count`` key/value pair.

    Some constrained decoders have returned a JSON object whose key contains the
    intended scalar, for example ``count”: 2, // ...`` with a null object value.
    This repair does not infer a count from language or accept aliases: it only
    separates the literal positive integer already embedded after the canonical
    ``count:`` prefix. The existing source-number and typed-count validators then
    prove that the recovered value is both requested and representable.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for item in responsibilities:
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict) or "count" in bindings:
            continue
        recoverable: list[tuple[Any, int]] = []
        for raw_name in bindings:
            match = _CORRUPTED_COUNT_BINDING.match(str(raw_name or ""))
            if match is None:
                continue
            value = int(match.group(1))
            if value > 0:
                recoverable.append((raw_name, value))
        if len(recoverable) != 1:
            continue
        raw_name, value = recoverable[0]
        bindings.pop(raw_name)
        bindings["count"] = value


def _reject_malformed_binding_names(parsed: dict[str, Any]) -> None:
    """Reject provider text that leaked JSON or commentary into a key.

    Binding names identify semantic dimensions; JSON punctuation, quote marks,
    comment delimiters, and embedded field syntax cannot be part of that
    identifier.  Rejecting this mechanical corruption at Goal Interpretation
    lets its single DTO-repair attempt regenerate the object before malformed
    keys reach Goal Association as apparently meaningful semantics.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for raw_name in bindings:
            name = " ".join(str(raw_name or "").strip().split())
            if not name or len(name) > 80 or _MALFORMED_BINDING_NAME.search(name):
                raise ValueError(
                    "malformed Goal Interpretation binding name at "
                    f"responsibilities[{responsibility_index}].bindings: {name!r}"
                )


def _reject_malformed_binding_values(parsed: dict[str, Any]) -> None:
    """Reject provider JSON/comment syntax fused into a scalar value.

    Human-semantic values may contain ordinary punctuation, including numeric
    times such as ``12:30``.  A quote immediately followed by a field separator
    or a comment opener, however, is mechanically leaked serialization syntax,
    not a semantic surface.  Failing this at the DTO boundary lets the existing
    one-shot contract repair regenerate the object before the corrupt field can
    become a canonical Goal binding.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        bindings = item.get("bindings") if isinstance(item, dict) else None
        if not isinstance(bindings, dict):
            continue
        for raw_name, raw_value in bindings.items():
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value_index, value in enumerate(values):
                if not isinstance(value, str) or not _MALFORMED_BINDING_VALUE.search(
                    value
                ):
                    continue
                suffix = f"[{value_index}]" if isinstance(raw_value, list) else ""
                raise ValueError(
                    "malformed Goal Interpretation binding value at "
                    f"responsibilities[{responsibility_index}].bindings."
                    f"{raw_name}{suffix}: {value!r}"
                )


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
    invalid translated location impossible to emit when a short fresh turn has
    no bounded semantic-context location to preserve. Longer or continuity-rich
    turns retain the normal validator and fail closed without growing an
    unbounded response schema.
    """

    surface = " ".join(str(text or "").strip().split())
    if not surface or len(surface) > 40:
        return []
    normalized_surface = _normalized_turn_echo(surface)
    values = {
        surface[start:end]
        for start in range(len(surface))
        for end in range(start + 1, len(surface) + 1)
        if _normalized_turn_echo(surface[start:end]) != normalized_surface
    }
    return sorted(values, key=lambda value: (len(value), value))


def _source_tokens(text: str) -> list[dict[str, Any]]:
    """Expose bounded exact source units for primary-result provenance.

    Latin/digit runs stay readable as words, CJK characters remain independently
    citable, and punctuation is retained. Whitespace is recovered from the source
    slice between the first and last cited token; no semantic tokenization occurs.
    """

    source = " ".join(str(text or "").strip().split())
    tokens: list[dict[str, Any]] = []
    index = 0

    def is_cjk(char: str) -> bool:
        codepoint = ord(char)
        return (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
        )

    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        start = index
        char = source[index]
        if is_cjk(char):
            index += 1
        elif char.isalnum() or char == "_":
            index += 1
            while index < len(source):
                candidate = source[index]
                if is_cjk(candidate) or not (
                    candidate.isalnum() or candidate in {"_", "'", "’"}
                ):
                    break
                index += 1
        else:
            index += 1
        tokens.append(
            {
                "ref": f"t{len(tokens)}",
                "surface": source[start:index],
                "start": start,
                "end": index,
            }
        )
    return tokens


def _goal_interpretation_source_turn_provenance(
    request: GoalInterpretationRequest,
) -> dict[str, Any]:
    """Return exact admitted wording once, without ambient Gateway metadata."""

    original_text = request.text
    envelope = request.context.get("user_turn_envelope")
    if isinstance(envelope, dict):
        original_input = envelope.get("original_input")
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


def _reject_noncanonical_count_bindings(parsed: dict[str, Any]) -> None:
    """Require typed repetition counts to use provider-neutral JSON integers.

    Goal Interpretation owns the semantic reading of a count expression. Once it
    chooses a count binding, the binding name supplies the type and its value has
    one canonical representation. This gate does not interpret source wording; it
    only rejects a mechanically malformed typed DTO so the model's single allowed
    same-stage repair can regenerate the semantic value.
    """

    legacy_count_names = {"item_count", "repetition_count"}
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for raw_name, value in bindings.items():
            name = "_".join(
                str(raw_name).strip().casefold().replace("-", "_").split()
            )
            if name in legacy_count_names:
                raise ValueError(
                    "non-canonical count binding name: "
                    f"responsibilities[{responsibility_index}].bindings.{raw_name}; "
                    "use bindings.count"
                )
            if name != "count":
                continue
            valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
            if not valid:
                raise ValueError(
                    "typed count bindings require a canonical positive JSON integer: "
                    f"responsibilities[{responsibility_index}].bindings.{raw_name}="
                    f"{value!r}"
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
    """Return exact provider-neutral WHAT facts for retained Goals."""

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
        contracts[goal_id] = {"output_mode": output_mode} if output_mode else {}
    return contracts


def _reject_continuity_completion_contract_mismatch(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject a continue/resume DTO that changes the retained WHAT modality."""

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
        expected = contracts[target_id].get("output_mode")
        if expected and item.get("output_mode") != expected:
            raise _GoalInterpretationAuthorityViolation(
                f"responsibilities[{index}] relationship={relationship!r} "
                f"changes retained Goal {target_id!r} output_mode: "
                f"expected={expected!r} actual={item.get('output_mode')!r}"
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
    semantic continuity context. A primary violation fails closed; the one
    designated Deep interpretation may use a same-stage mechanical decoder
    constraint, never a semantic review of rejected wording.
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
        location_alias_qualifiers = {
            "area",
            "place",
            "scope",
            "spatial",
            "target",
        }
        location_aliases: list[str] = []
        for raw_name in bindings:
            normalized_name = str(raw_name).casefold()
            if normalized_name == "location":
                continue
            name_tokens = {
                token
                for token in re.sub(
                    r"(?<=[a-z0-9])(?=[A-Z])|[^A-Za-z0-9]+",
                    " ",
                    str(raw_name),
                ).casefold().split()
            }
            # Reject names that merely rename the location dimension.  A
            # compound key that also names another independently typed semantic
            # dimension (for example location_direction) is not a location
            # alias; its own grounding is handled by the ordinary binding
            # contract instead of being misclassified here.
            if (
                "location" in name_tokens
                and name_tokens - {"location"} <= location_alias_qualifiers
            ):
                location_aliases.append(str(raw_name))
        if location_aliases:
            raise _GoalInterpretationAuthorityViolation(
                "Goal Interpretation location meaning must use the canonical "
                f"bindings.location field; noncanonical location binding name(s) "
                f"at responsibilities[{index}]: {location_aliases!r}. Regenerate "
                "from the authoritative turn without renaming the typed dimension."
            )
        raw_location = bindings.get("location")
        if raw_location is not None and not isinstance(raw_location, str):
            raise _GoalInterpretationLocationProvenanceViolation(
                "Goal Interpretation location binding must be one exact "
                "source/context string scalar: "
                f"responsibilities[{index}].bindings.location={raw_location!r}."
            )
        if not isinstance(raw_location, str):
            continue
        location = " ".join(raw_location.strip().split())
        if not location:
            continue
        folded = location.casefold()
        if folded in current_turn or folded in contextual_values:
            continue
        raise _GoalInterpretationLocationProvenanceViolation(
            "Goal Interpretation location binding has no authoritative surface "
            f"provenance: responsibilities[{index}].bindings.location={location!r}. "
            "A directly named location must copy the exact current-turn user-language "
            "surface; an indirect location must already exist in bounded semantic context."
        )


def _is_noncanonical_speed_binding_name(raw_name: str) -> bool:
    normalized_name = str(raw_name).strip().casefold()
    if normalized_name == "speed":
        return False
    name_tokens = set(
        re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])|[^A-Za-z0-9]+",
            " ",
            str(raw_name),
        )
        .casefold()
        .split()
    )
    speed_dimension_tokens = {"speed", "pace", "velocity"}
    speed_alias_qualifiers = {"level", "mode", "setting", "value"}
    return bool(
        name_tokens & speed_dimension_tokens
        and name_tokens - speed_dimension_tokens <= speed_alias_qualifiers
    )


def _reject_unprovenanced_speed_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject speed values that lack source/context evidence or are spatial aliases.

    The host does not decide which wording means a pace. It only enforces the
    model-facing typed contract: a model-authored speed scalar must be copied
    from the authoritative turn or bounded semantic continuity context, and the
    same scalar cannot simultaneously occupy the location dimension. A
    violation requires fresh source interpretation rather than mutation of the
    rejected semantics.
    """

    current_turn = " ".join((request.text or "").strip().split()).casefold()
    contextual_values = _semantic_context_string_values(request.context)
    source_numbers = _decimal_values(request.text)
    context_numbers = {
        number
        for key in _GOAL_INTERPRETATION_PROVENANCE_CONTEXT_KEYS
        for number in _decimal_values(request.context.get(key))
    }
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        speed_aliases = [
            str(raw_name)
            for raw_name in bindings
            if _is_noncanonical_speed_binding_name(str(raw_name))
        ]
        if speed_aliases:
            raise _GoalInterpretationSpeedProvenanceViolation(
                "Goal Interpretation speed meaning must use the canonical "
                f"bindings.speed field; noncanonical speed binding name(s) at "
                f"responsibilities[{index}]: {speed_aliases!r}. Regenerate from "
                "the authoritative turn without renaming the typed dimension."
            )
        if "speed" not in bindings:
            continue
        raw_speed = bindings.get("speed")
        speed_values = raw_speed if isinstance(raw_speed, list) else [raw_speed]
        raw_location = bindings.get("location")
        location = (
            " ".join(raw_location.strip().split()).casefold()
            if isinstance(raw_location, str)
            else ""
        )
        for value_index, scalar in enumerate(speed_values):
            suffix = f"[{value_index}]" if isinstance(raw_speed, list) else ""
            if isinstance(scalar, bool) or not isinstance(
                scalar, (str, int, float, Decimal)
            ):
                raise _GoalInterpretationSpeedProvenanceViolation(
                    "Goal Interpretation speed binding must be a source-backed "
                    "pace or velocity scalar: "
                    f"responsibilities[{index}].bindings.speed{suffix}={scalar!r}."
                )
            if isinstance(scalar, str):
                speed = " ".join(scalar.strip().split())
                folded = speed.casefold()
                if location and folded == location:
                    raise _GoalInterpretationSpeedProvenanceViolation(
                        "Goal Interpretation assigned the same source surface to "
                        "conflicting typed dimensions: "
                        f"responsibilities[{index}].bindings.location and speed "
                        f"both equal {speed!r}. Direction/location is never speed."
                    )
                if speed and (folded in current_turn or folded in contextual_values):
                    continue
            else:
                try:
                    numeric_speed = Decimal(str(scalar))
                except InvalidOperation:
                    numeric_speed = None
                if numeric_speed is not None and (
                    numeric_speed in source_numbers or numeric_speed in context_numbers
                ):
                    continue
            raise _GoalInterpretationSpeedProvenanceViolation(
                "Goal Interpretation speed binding has no authoritative surface "
                "provenance: "
                f"responsibilities[{index}].bindings.speed{suffix}={scalar!r}. "
                "Speed must preserve an explicitly supplied pace or velocity surface; "
                "omit it when the authoritative meaning supplies none."
            )


def _strip_mechanically_unprovenanced_speed_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Drop speed only when source/context mechanics prove it was invented.

    This does not decide which wording means a pace. It removes an optional model
    field only when its scalar is absent from both authoritative source and bounded
    semantic context, or when it duplicates the already-owned location scalar.
    The remaining WHAT still passes every normal validator.
    """

    current_turn = " ".join((request.text or "").strip().split()).casefold()
    contextual_values = _semantic_context_string_values(request.context)
    source_numbers = _decimal_values(request.text)
    context_numbers = {
        number
        for key in _GOAL_INTERPRETATION_PROVENANCE_CONTEXT_KEYS
        for number in _decimal_values(request.context.get(key))
    }
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for item in responsibilities:
        bindings = item.get("bindings") if isinstance(item, dict) else None
        if not isinstance(bindings, dict) or "speed" not in bindings:
            continue
        raw_speed = bindings.get("speed")
        if isinstance(raw_speed, bool):
            bindings.pop("speed", None)
            continue
        if isinstance(raw_speed, (int, float, Decimal)):
            try:
                numeric_speed = Decimal(str(raw_speed))
            except InvalidOperation:
                numeric_speed = None
            if numeric_speed not in source_numbers | context_numbers:
                bindings.pop("speed", None)
            continue
        if not isinstance(raw_speed, str):
            continue
        speed = " ".join(raw_speed.strip().split())
        folded = speed.casefold()
        raw_location = bindings.get("location")
        location = (
            " ".join(raw_location.strip().split()).casefold()
            if isinstance(raw_location, str)
            else ""
        )
        if (location and folded == location) or not (
            speed and (folded in current_turn or folded in contextual_values)
        ):
            bindings.pop("speed", None)


def _reject_unprovenanced_duration_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Require duration to remain one typed scalar with safe string provenance.

    Numeric duration is GI-owned semantic normalization: number words in the
    admitted language may legitimately become a JSON number.  The cited source
    span carries its provenance, while the explicit-Arabic-number guard below
    separately prevents literal numeric values from being dropped or rewritten.
    Trusted code can mechanically verify only string copies here; it must not
    reinterpret number words to challenge GI's semantic authority.
    """

    current_turn = " ".join((request.text or "").strip().split()).casefold()
    contextual_values = _semantic_context_string_values(request.context)
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for index, item in enumerate(responsibilities):
        bindings = item.get("bindings") if isinstance(item, dict) else None
        if not isinstance(bindings, dict) or "duration" not in bindings:
            continue
        duration = bindings.get("duration")
        if isinstance(duration, bool) or not isinstance(
            duration, (str, int, float, Decimal)
        ):
            raise _GoalInterpretationDurationProvenanceViolation(
                "Goal Interpretation duration binding must remain one scalar "
                "source value, never a nested provider-shaped object: "
                f"responsibilities[{index}].bindings.duration={duration!r}."
            )
        if isinstance(duration, str):
            normalized = " ".join(duration.strip().split()).casefold()
            if normalized and (
                normalized in current_turn or normalized in contextual_values
            ):
                continue
        else:
            continue
        raise _GoalInterpretationDurationProvenanceViolation(
            "Goal Interpretation duration binding has no authoritative surface "
            "provenance: "
            f"responsibilities[{index}].bindings.duration={duration!r}. "
            "Duration must preserve one explicitly supplied elapsed-time scalar."
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
    Responsibility, that exact whole-turn scalar is envelope redundancy rather
    than hidden structure.

    The rule is intentionally narrow. Embodied, information, stateful, media,
    authored-vocal, or multi-Responsibility interpretations retain the fail-closed
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


def _goal_ids_awaiting_user_clarification(context: dict[str, Any]) -> set[str]:
    """Return Goal IDs with an explicit unresolved ask-user information gap."""

    snapshots: list[Any] = []
    for key in (
        "active_goal_snapshots",
        "recent_goal_snapshots",
        "active_task_snapshots",
        "active_task_contexts",
    ):
        value = context.get(key)
        if isinstance(value, list):
            snapshots.extend(value)
    current = context.get("current_task_context")
    if isinstance(current, dict):
        snapshots.append(current)

    goal_ids: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        gaps = snapshot.get("open_information_gaps")
        if not isinstance(gaps, list) or not any(
            isinstance(gap, dict)
            and gap.get("resolved") is not True
            and gap.get("blocking") is not False
            and str(gap.get("preferred_resolution") or "").strip()
            == "ask_user"
            for gap in gaps
        ):
            continue
        semantic_goal = (
            snapshot.get("semantic_goal")
            if isinstance(snapshot.get("semantic_goal"), dict)
            else {}
        )
        goal = (
            snapshot.get("goal")
            if isinstance(snapshot.get("goal"), dict)
            else {}
        )
        for candidate in (
            snapshot.get("goal_id"),
            semantic_goal.get("goal_id"),
            goal.get("goal_id"),
        ):
            goal_id = " ".join(str(candidate or "").strip().split())
            if goal_id:
                goal_ids.add(goal_id)
    return goal_ids


def _is_atomic_context_backed_clarification(
    request: GoalInterpretationRequest,
    responsibilities: list[Any],
    item: dict[str, Any],
) -> bool:
    """Recognize the DTO shape where the whole short turn may be one binding."""

    if len(responsibilities) != 1 or item.get("relationship") != "clarify":
        return False
    target_goal_ids = item.get("target_goal_ids")
    if not isinstance(target_goal_ids, list) or len(target_goal_ids) != 1:
        return False
    target_goal_id = " ".join(str(target_goal_ids[0] or "").strip().split())
    return target_goal_id in _goal_ids_awaiting_user_clarification(request.context)


def _reject_transport_echo_bindings(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Reject a whole admitted turn masquerading as an atomic semantic binding.

    Whole-turn copying can conceal collapsed multi-effect meaning, so it remains
    a fail-closed semantic-structure violation. The one mechanical exception is
    a single ``relationship=clarify`` Responsibility targeting exactly one Goal
    whose bounded Context contains an unresolved ask-user information gap. A short
    elliptical answer can then legitimately be identical to one binding surface.
    Exact request-language echoes are sanitized separately as mechanically
    removable envelope noise.
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
        atomic_clarification = _is_atomic_context_backed_clarification(
            request, responsibilities, item
        )
        for binding_name, value in bindings.items():
            values = value if isinstance(value, list) else [value]
            for value_index, scalar in enumerate(values):
                if not isinstance(scalar, str):
                    continue
                normalized = _normalized_turn_echo(scalar)
                if not (turn_echo and normalized == turn_echo):
                    continue
                if atomic_clarification:
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
    sibling_relation_names = {
        "after",
        "before",
        "follows",
        "parallel_with",
        "precedes",
    }
    simultaneous_relation_names = {
        "alongside",
        "concurrent_with",
        "parallel_with",
        "simultaneity",
        "simultaneous_with",
        "with",
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
                or normalized_name in sibling_relation_names
                or normalized_name in simultaneous_relation_names
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
            # A boolean attached to an explicitly relation-shaped field is only
            # structural coordination evidence.  Once sibling Responsibilities
            # already expose the independently observable effects, true/false
            # cannot conceal another action phrase and is safe to retain as a
            # human-semantic timing constraint.
            if (
                len(local_refs) > 1
                and normalized_name in simultaneous_relation_names
                and isinstance(value, bool)
            ):
                continue
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation coordination bindings must contain only exact "
                "sibling local_ref values; free-form effect wording can conceal a "
                f"missing Responsibility at responsibilities[{responsibility_index}]"
                f".bindings.{binding_name}."
            )


def _append_sibling_relation(
    bindings: dict[str, Any],
    relation_name: str,
    sibling_refs: list[str],
) -> None:
    existing = bindings.get(relation_name)
    values = (
        [str(item) for item in existing]
        if isinstance(existing, list)
        else [str(existing)] if existing not in (None, "") else []
    )
    bindings[relation_name] = list(dict.fromkeys([*values, *sibling_refs]))


def _normalize_model_interpretation_projection(parsed: dict[str, Any]) -> None:
    """Mechanically lower the one-call model wire shape into the canonical DTO.

    GI remains the sole author of every relation and numeric dimension.  This
    adapter only moves those already-authored typed values into the legacy
    canonical binding representation consumed by GA and Planner.
    """

    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for item in responsibilities:
        if not isinstance(item, dict) or "binding_items" not in item:
            continue
        binding_items = item.pop("binding_items")
        if not isinstance(binding_items, dict):
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation binding_items must be one sparse typed object"
            )
        bindings = item.setdefault("bindings", {})
        if not isinstance(bindings, dict) or bindings:
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation cannot mix binding_items with bindings"
            )
        for raw_name, value in binding_items.items():
            name = str(raw_name or "").strip()
            if not name or name != raw_name or name in bindings:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Goal Interpretation binding names must be canonical, non-empty, "
                    "and unique"
                )
            bindings[name] = value
    by_ref = {
        str(item.get("local_ref") or "").strip(): item
        for item in responsibilities
        if isinstance(item, dict) and str(item.get("local_ref") or "").strip()
    }
    coordination = parsed.pop("coordination", [])
    if not isinstance(coordination, list):
        raise _GoalInterpretationSemanticStructureViolation(
            "Goal Interpretation coordination must be one typed list"
        )
    for group in coordination:
        if not isinstance(group, dict):
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation coordination item must be one typed object"
            )
        kind = str(group.get("kind") or "").strip()
        refs = [str(item).strip() for item in group.get("refs") or []]
        if (
            kind not in {"parallel", "sequence"}
            or len(refs) < 2
            or len(set(refs)) != len(refs)
            or any(ref not in by_ref for ref in refs)
        ):
            raise _GoalInterpretationSemanticStructureViolation(
                "Goal Interpretation coordination requires parallel/sequence and "
                "at least two unique emitted Responsibility refs"
            )
        if kind == "parallel":
            for ref in refs:
                item = by_ref[ref]
                bindings = item.setdefault("bindings", {})
                _append_sibling_relation(
                    bindings,
                    "parallel_with",
                    [sibling for sibling in refs if sibling != ref],
                )
        else:
            for previous_ref, ref in zip(refs, refs[1:], strict=False):
                item = by_ref[ref]
                bindings = item.setdefault("bindings", {})
                _append_sibling_relation(bindings, "after", [previous_ref])



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


def _reject_unavailable_or_mismatched_prior_assistant_utterance(
    request: GoalInterpretationRequest,
    parsed: dict[str, Any],
) -> None:
    """Keep prior-speech evidence exact and absent when no such evidence exists."""

    prior = _most_recent_assistant_utterance(request.context)
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return
    for responsibility_index, item in enumerate(responsibilities):
        if not isinstance(item, dict):
            continue
        bindings = item.get("bindings")
        if not isinstance(bindings, dict):
            continue
        for raw_name, value in bindings.items():
            name = "_".join(
                str(raw_name).strip().casefold().replace("-", "_").split()
            )
            if name != "prior_assistant_utterance":
                continue
            if prior is None:
                raise _GoalInterpretationAuthorityViolation(
                    "prior_assistant_utterance was emitted without an accepted prior "
                    f"assistant utterance at responsibilities[{responsibility_index}]"
                )
            if value != prior["text"]:
                raise _GoalInterpretationAuthorityViolation(
                    "prior_assistant_utterance must equal the exact supplied prior text at "
                    f"responsibilities[{responsibility_index}]"
                )


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
        f"{_bounded_json(profile, max_chars=420)}\n"
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

    def build_system_prompt(self, request: GoalInterpretationRequest) -> str:
        """Project only contract sections made relevant by supplied Context.

        This projection follows already-authoritative schema/context presence. It
        neither classifies the utterance nor chooses semantic fields, so the model
        remains the sole WHAT authority while common new turns avoid unrelated
        Goal-continuity and prior-utterance instructions.
        """

        sections = [self.load_system_prompt()]
        if _canonical_goal_ids_from_context(request.context):
            sections.append(
                "Goal continuity is exposed for this request. Copy one exact "
                "schema-allowed relationship token and exact supplied Goal IDs. "
                "Use new for an independent Responsibility; use another relationship "
                "only when the current turn semantically targets supplied Goal meaning. "
                "Never attach an unrelated outcome because a Goal is visible. Preserve "
                "negation and lifecycle meaning: ceasing, rejecting, cancelling, or "
                "pausing supplied active Goal meaning is not a new positive performance "
                "or an invented opposite action. Continuation or resumption preserves "
                "the supplied Goal's output mode. Pending clarification Context may "
                "resolve an elliptical reply, but Goal Interpretation never creates or "
                "resolves a Planner InformationGap."
            )
        prior = _most_recent_assistant_utterance(request.context)
        if prior is not None:
            sections.append(
                "The schema exposes prior_assistant_utterance for this request. When the "
                "person asks what Chromie most recently said, create a new speech "
                "Responsibility to repeat or report the exact accepted assistant "
                "utterance supplied in Context and bind it as prior_assistant_utterance. "
                "Never substitute the current user turn, an unavailable marker, a "
                "paraphrase, or an old Goal relationship."
            )
        return "\n\n".join(sections)

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
            "Most recent accepted Chromie/assistant utterance JSON:"
            f"{_bounded_json(prior_assistant_utterance, max_chars=420)}\n"
            if prior_assistant_utterance is not None
            else ""
        )
        return (
            "Current Turn:\n"
            "IMMUTABLE SOURCE TURN JSON (exact Gateway wording; read-only; "
            "Goal Interpretation owns current-turn WHAT):\n"
            f"{json.dumps(_goal_interpretation_source_turn_provenance(request), ensure_ascii=False, separators=(',', ':'))}\n"
            f"language_hint={request.language or 'auto'}\n\n"
            "Authoritative source tokens (cite inclusive refs in each "
            "Responsibility.source_evidence):\n"
            f"{_bounded_json(_source_tokens(request.text), max_chars=5000)}\n\n"
            "Bounded Identity Context:\n"
            f"{_goal_interpretation_identity_context(mind)}\n\n"
            "Semantic Continuity Context:\n"
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
        *,
        forbidden_unresolved_values: tuple[str, ...] = (),
        new_relationship_only: bool = False,
        allowed_goal_ids: tuple[str, ...] = (),
        prior_assistant_utterance: str | None = None,
        admitted_turn: str = "",
        exact_location_surfaces: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        schema = GoalInterpretationDecision.model_json_schema()
        schema["additionalProperties"] = False
        schema["required"] = ["confidence", "responsibilities", "unresolved"]
        unresolved = schema.get("properties", {}).get("unresolved")
        if isinstance(unresolved, dict):
            unresolved["description"] = (
                "Only genuine material uncertainty about WHAT outcome, scope, "
                "relationship, or referent the human means. Use [] for clear meaning. "
                "Never list fillers, hesitation, politeness, missing units or provider "
                "details, unknown external answers, or a value already preserved in "
                "binding_items. Do not invent an alternative speaker/addressee reading "
                "when the supplied provenance identifies user -> Chromie."
            )
            unresolved_items = unresolved.get("items")
            if isinstance(unresolved_items, dict):
                unresolved_items["description"] = (
                    "One concise human-meaning uncertainty that the user can resolve; "
                    "never a label for filler/disfluency or an execution question."
                )
        confidence_values = [0.0, 0.25, 0.5, 0.75, 1.0]
        aggregate_confidence = schema.get("properties", {}).get("confidence")
        if isinstance(aggregate_confidence, dict):
            aggregate_confidence.pop("minimum", None)
            aggregate_confidence.pop("maximum", None)
            aggregate_confidence["enum"] = confidence_values
            aggregate_confidence["description"] = (
                "Required confidence evidence selected from the bounded numeric "
                "scale 0, 0.25, 0.5, 0.75, or 1."
            )
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
            local_refs = [f"r{index}" for index in range(1, 13)]
            required = [
                "local_ref",
                "outcome",
                "bindings",
                "output_mode",
                "relationship",
                "target_goal_ids",
                "confidence",
                "source_evidence",
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
                    "or rejected on its own requires a sibling Responsibility. For "
                    "one predicate, duration, speed, direction, distance, count, intensity, "
                    "and other modifiers belong in bindings and never become sibling "
                    "outcomes. Mentioning a modifier in outcome prose does not preserve "
                    "it: every material modifier must also appear under its typed "
                    "binding_items key. For "
                    "body_action, name the actual source predicate such as locomote, "
                    "turn, gaze, blink, nod, gesture, carry, or hand over; never emit "
                    "'perform a body action'. For information, name the proposition or "
                    "subject to determine rather than only 'provide information'. For "
                    "speech, describe the communicative obligation or proposition; never "
                    "write the exact utterance, which Planner alone authors."
                )
            local_ref = responsibility.get("properties", {}).get("local_ref")
            if isinstance(local_ref, dict):
                local_ref.pop("minLength", None)
                local_ref.pop("maxLength", None)
                local_ref["enum"] = local_refs
                local_ref["description"] = (
                    "One turn-local mechanical reference from r1 through r12. "
                    "It is not a Goal, Task, Plan, Activity, or provider identity."
                )
            source_tokens = _source_tokens(admitted_turn)
            source_token_refs = [str(item["ref"]) for item in source_tokens]
            source_evidence = responsibility.get("properties", {}).get(
                "source_evidence"
            )
            if isinstance(source_evidence, dict):
                source_evidence.pop("anyOf", None)
                source_evidence.pop("default", None)
                source_evidence.clear()
                source_evidence.update(
                    {
                        "$ref": "#/$defs/ResponsibilitySourceEvidence",
                        "description": (
                            "Required primary-result citation of the exact inclusive "
                            "authoritative-turn token span grounding this one outcome."
                        ),
                    }
                )
            evidence_definition = schema.get("$defs", {}).get(
                "ResponsibilitySourceEvidence"
            )
            if isinstance(evidence_definition, dict):
                evidence_definition["required"] = [
                    "source_start_token_ref",
                    "source_end_token_ref",
                ]
                evidence_definition["additionalProperties"] = False
                for field_name in (
                    "source_start_token_ref",
                    "source_end_token_ref",
                ):
                    field_schema = evidence_definition.get("properties", {}).get(
                        field_name
                    )
                    if isinstance(field_schema, dict):
                        field_schema.pop("minLength", None)
                        field_schema.pop("maxLength", None)
                        field_schema["enum"] = source_token_refs
                        field_schema["description"] = (
                            "First token of only this Responsibility's positive "
                            "predicate; exclude shared coordination and sibling tokens."
                            if field_name == "source_start_token_ref"
                            else "Last token of only this Responsibility's positive "
                            "predicate; exclude shared coordination and sibling tokens."
                        )
            bindings = responsibility.get("properties", {}).get("bindings")
            if isinstance(bindings, dict):
                # Ollama does not reliably enforce propertyNames on an open object.
                # Advertising forbidden names with sentinel const values also gives a
                # small structured decoder legal ways to emit the exact HOW/envelope
                # fields the contract rejects. Keep the canonical DTO dictionary, but
                # close its model-facing vocabulary around provider-neutral human
                # semantic dimensions. Deep/source recovery may narrow this same set;
                # no runtime Capability or case-specific phrase enters the schema.
                bindings.pop("propertyNames", None)
                bindings["additionalProperties"] = False
                bindings["description"] = (
                    "Zero or more material human-semantic dimensions using only the "
                    "typed properties exposed here. Observable effects belong in sibling "
                    "Responsibility outcomes; DTO fields, HOW, provider, Capability, "
                    "execution, and explanatory prose are not bindings."
                )
                binding_properties: dict[str, Any] = {}
                bindings["properties"] = binding_properties
                binding_properties["count"] = {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Canonical positive JSON integer for an item or repetition "
                        "quantity only; never use count for duration, time, distance, "
                        "speed, or another measured dimension. Never emit aliases, "
                        "number words, or numeric strings."
                    ),
                }
                source_backed_string: dict[str, Any] = {
                    "type": "string",
                    "minLength": 1,
                }
                schema_definitions = schema.setdefault("$defs", {})
                schema_definitions["SourceBackedBindingString"] = source_backed_string
                binding_properties["location"] = {
                    "$ref": "#/$defs/SourceBackedBindingString",
                    "description": (
                        "One exact source/context place or spatial-target string. Trusted "
                        "code validates exact source/context provenance."
                    ),
                }
                if exact_location_surfaces:
                    binding_properties["location"] = {
                        "type": "string",
                        "enum": list(exact_location_surfaces),
                        "description": (
                            "If present, copy one exact contiguous surface from the "
                            "authoritative current turn. This closed spelling constraint "
                            "does not decide whether any surface is a location."
                        ),
                    }
                binding_properties["duration"] = {
                    "anyOf": [
                        {"$ref": "#/$defs/SourceBackedBindingString"},
                        {"type": "number"},
                    ],
                    "description": (
                        "Elapsed length only, such as a source expression meaning for N "
                        "seconds/minutes. Use the normalized JSON number N or one exact "
                        "source/context string; this value owns the complete elapsed-span meaning. "
                        "Whenever the source explicitly supplies elapsed length, emit duration; "
                        "outcome prose alone is not binding evidence. "
                        "Never put elapsed length in count, time, time_scope, threshold, "
                        "comparison, or quantity."
                    ),
                }
                binding_properties["speed"] = {
                    "anyOf": [
                        {"$ref": "#/$defs/SourceBackedBindingString"},
                        {"type": "number"},
                    ],
                    "description": (
                        "Explicit pace or velocity only, represented as a JSON number or "
                        "exact source/context string. A missing physical unit does not "
                        "make an explicitly supplied speed scalar unresolved."
                    ),
                }
                schema_definitions["SemanticBindingScalar"] = {
                    "anyOf": [
                        {"type": "string", "minLength": 1},
                        {"type": "number"},
                        {"type": "boolean"},
                        {
                            "type": "array",
                            "items": {
                                "anyOf": [
                                    {"type": "string", "minLength": 1},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                ]
                            },
                            "minItems": 1,
                            "maxItems": 12,
                        },
                    ],
                }
                dimension_descriptions = {
                    "entity": (
                        "Exact person, organization, object, product, service, title, or "
                        "unknown proper-name-like referent that the predicate is about. "
                        "Preserve an unfamiliar name here without guessing its category."
                    ),
                    "direction": (
                        "Explicit path or orientation direction only, such as left, right, "
                        "ahead, toward, or an equivalent source-grounded direction."
                    ),
                    "time": (
                        "One source-grounded instant or clock point, such as now or at a "
                        "stated clock time. Never use for an interval, elapsed duration, "
                        "comparison cutoff, or category."
                    ),
                    "time_scope": (
                        "One exact source/context calendar, relative-time, or interval scope, "
                        "such as tonight, tomorrow, this week, or during a stated period. "
                        "Preserve its source language and surface rather than translating or "
                        "normalizing it. Never place temporal scope in time, subtype, "
                        "threshold, or comparison."
                    ),
                    "threshold": (
                        "An explicit cutoff for a comparison or condition only, such as "
                        "at least N, above N, below N, or until a stated condition. "
                        "Never use for a time scope, duration, speed, count, category, "
                        "or ordinary value."
                    ),
                    "subtype": (
                        "An explicitly supplied categorical kind of the predicate or "
                        "entity only. Never use for time, duration, speed, count, a whole "
                        "action, or an inferred provider category."
                    ),
                    "recipient": (
                        "The explicitly named beneficiary or receiver of a transferred or "
                        "communicated result. Never use a place, action actor, gaze target, "
                        "or Chromie itself unless the source explicitly names it as receiver."
                    ),
                }
                for semantic_name in (
                    "actor",
                    "addressee",
                    "experiencer",
                    "entity",
                    "item",
                    "quantity",
                    "distance",
                    "direction",
                    "time",
                    "time_scope",
                    "severity",
                    "intensity",
                    "magnitude",
                    "threshold",
                    "subtype",
                    "polarity",
                    "comparison",
                    "recipient",
                    "proposition",
                    "preference",
                    "attribute",
                ):
                    description = dimension_descriptions.get(semantic_name)
                    binding_properties[semantic_name] = {
                        "$ref": "#/$defs/SemanticBindingScalar",
                        "description": description
                        or (
                            "One source/context-backed human-semantic scalar or short "
                            "scalar list; never a nested execution/provider object or "
                            "explanation."
                        ),
                    }
                binding_properties = {
                    name: binding_properties[name]
                    for name in (
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
                    )
                }
                bindings["properties"] = binding_properties
                if prior_assistant_utterance is not None:
                    binding_properties["prior_assistant_utterance"] = {
                        "const": prior_assistant_utterance,
                        "description": (
                            "The exact most recent accepted assistant utterance supplied "
                            "by bounded dialogue context; never paraphrase or truncate it."
                        ),
                    }
                else:
                    binding_properties.pop("prior_assistant_utterance", None)
                responsibility_properties = responsibility.get("properties", {})
                responsibility_properties.pop("bindings", None)
                responsibility_properties["binding_items"] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": binding_properties,
                    "description": (
                        "Sparse material facts for this one predicate, keyed once by "
                        "semantic dimension. Emit only entailed keys and no defaults. "
                        "A magnitude and its natural-language unit are one typed value. "
                        "Every material modifier remains required here even when outcome "
                        "prose already mentions it. "
                        "Modifiers such as speed and duration remain keys on the same "
                        "Responsibility; relations belong only in top-level coordination."
                    ),
                }
                responsibility["required"] = [
                    "binding_items" if name == "bindings" else name
                    for name in responsibility.get("required", [])
                ]
            item_confidence = responsibility.get("properties", {}).get("confidence")
            if isinstance(item_confidence, dict):
                item_confidence.pop("minimum", None)
                item_confidence.pop("maximum", None)
                item_confidence["enum"] = confidence_values
                item_confidence["description"] = (
                    "Confidence in this one Responsibility selected from the bounded "
                    "numeric scale 0, 0.25, 0.5, 0.75, or 1."
                )
            output_mode = responsibility.get("properties", {}).get("output_mode")
            if isinstance(output_mode, dict):
                output_mode.pop("enum", None)
                output_mode_variants = [
                    {
                        "const": "singing",
                        "description": (
                            "A requested act for Chromie to sing or perform a song, "
                            "with or without lyrics. Never use media_playback for the "
                            "performer's own singing."
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
                        "const": "information",
                        "description": (
                            "The person wants Chromie to determine or provide information; "
                            "this does not decide whether fresh acquisition is needed."
                        ),
                    },
                    {
                        "const": "stateful_effect",
                        "description": (
                            "A durable or future state change outside embodiment, such as "
                            "recording, scheduling, changing a setting, or sending later. "
                            "Never use this for locomotion, posture, gaze, gesture, "
                            "physical manipulation, carrying, or handover; those are "
                            "body_action even when their physical result lasts."
                        ),
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
                        "description": (
                            "Only control or playback of existing recorded media. Never "
                            "use this for Chromie to sing, hum, recite, or otherwise "
                            "perform vocally."
                        ),
                    },
                ]
                output_mode["oneOf"] = output_mode_variants
                output_mode["description"] = (
                    "Provider-neutral WHAT category for this one atomic outcome. "
                    "Use speech for an ordinary conversational obligation whose semantic "
                    "content is fixed by supplied bounded context. Planner alone authors "
                    "the exact utterance. "
                    "Use information for a factual answer not fixed by that semantic "
                    "context; this category does not decide whether or how Planner acquires "
                    "Evidence. Embodied, vocal-performance, "
                    "media, and state-changing requests retain their exact modes even when "
                    "expressed in dialogue. Use stateful_effect only for durable/future "
                    "state changes outside embodiment; every physical motion, posture, gaze, "
                    "gesture, manipulation, carrying, or handover is body_action. These "
                    "categories never decide work, fresh Evidence, a "
                    "Capability, provider, or response transport. Singing or a song is "
                    "singing; blinking/locomotion are body_action; ordinary conversational "
                    "words are speech. No catch-all mode is available: choose the exact "
                    "source-grounded category."
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
            # Keep the decoder surface identical to the WHAT-only Pydantic contract.
            # Work/evidence readiness is deliberately absent: Planner derives it later
            # from canonical Goal state, trusted Evidence, and available Capabilities.
            responsibility["additionalProperties"] = False
        local_refs = [f"r{index}" for index in range(1, 13)]
        properties = schema.setdefault("properties", {})
        properties["coordination"] = {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["parallel", "sequence"],
                        "description": (
                            "parallel means every listed Responsibility overlaps; "
                            "sequence means refs are in exact requested order."
                        ),
                    },
                    "refs": {
                        "type": "array",
                        "items": {"type": "string", "enum": local_refs},
                        "minItems": 2,
                        "maxItems": 12,
                        "uniqueItems": True,
                        "description": (
                            "At least two unique emitted Responsibility local_ref "
                            "values. A singleton or self-edge is impossible."
                        ),
                    },
                },
                "required": ["kind", "refs"],
            },
            "description": (
                "Typed relations between independently satisfiable Responsibilities. "
                "Use [] when there is no requested concurrency or order. Relations "
                "never belong inside semantic bindings."
            ),
        }
        if "coordination" not in schema["required"]:
            schema["required"].append("coordination")
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
        prior = _most_recent_assistant_utterance(request.context)
        exact_location_surfaces = (
            tuple(_short_exact_surface_substrings(request.text))
            if not _semantic_context_string_values(request.context)
            else ()
        )
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
            "format": self._goal_interpretation_response_schema(
                new_relationship_only=not bool(
                    _canonical_goal_ids_from_context(request.context)
                ),
                allowed_goal_ids=_canonical_goal_ids_from_context(request.context),
                prior_assistant_utterance=(
                    prior["text"] if prior is not None else None
                ),
                admitted_turn=request.text,
                exact_location_surfaces=exact_location_surfaces,
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
        prior = _most_recent_assistant_utterance(request.context)
        payload = self.build_interpretation_payload(request)
        payload["format"] = self._goal_interpretation_response_schema(
            forbidden_unresolved_values=forbidden_unresolved_values,
            new_relationship_only=not bool(
                _canonical_goal_ids_from_context(request.context)
            ),
            allowed_goal_ids=_canonical_goal_ids_from_context(request.context),
            prior_assistant_utterance=(
                prior["text"] if prior is not None else None
            ),
            admitted_turn=request.text,
            exact_location_surfaces=(
                tuple(_short_exact_surface_substrings(request.text))
                if not _semantic_context_string_values(request.context)
                else ()
            ),
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
                    self.build_system_prompt(request)
                    + "\n\nDTO Repair: return one corrected WHAT-only Goal Interpretation JSON object. "
                    "For every closed string field, copy one exact protocol token from "
                    "the schema; never inflect, conjugate, translate, or paraphrase it. "
                    "Remove every field outside the schema. Never translate a rejected "
                    "route/intent/Capability/Activity/Work/Plan/provider field into another "
                    "implementation hint. Preserve only the human outcome, material semantic "
                    "bindings, supplied Goal relationships, "
                    "the exact provider-neutral output_mode, confidence, and genuine "
                    "semantic uncertainty. Never create/resolve an InformationGap or "
                    "choose input-source/default/clarification policy. A directly named "
                    "entity binding must copy the exact "
                    "current-turn surface; never translate or transliterate it. Provider timezone "
                    "or clock-range choices for an already-preserved relative time are not semantic "
                    "uncertainty. Any place or spatial-location meaning must use the canonical "
                    "binding name location; never rename the dimension to a location alias. "
                    "The request-envelope language tag and the whole Latest "
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
                    self.build_system_prompt(request)
                    + "\n\nDeep Goal Interpretation: use broader reasoning over the "
                    "authoritative turn and bounded semantic context, but keep exactly "
                    "the same WHAT-only authority and output schema. Reconsider only "
                    "genuine consequential ambiguity in the person's intended outcome, "
                    "scope, Goal relationship, or referent. Preserve unresolved meaning "
                    "when the source does not determine it. A missing execution input or "
                    "external answer is not semantic ambiguity. Do not create or resolve "
                    "an InformationGap; do not choose ask_user, context, observation, "
                    "query, default, Work, a Capability, provider, or executable arguments. "
                    "This source-based pass must complete atomic decomposition and "
                    "primary source grounding before JSON: "
                    "count every independently observable effect related by coordination "
                    "grammar in any language. If the source "
                    "coordinates N effects that a person could accept or reject separately, "
                    "responsibilities must contain N sibling items. Never hide one effect "
                    "inside another item's outcome or binding. A coordination binding may "
                    "contain only exact sibling local_ref values, not words naming an action. "
                    "Check semantic provenance before returning: every explicit current-turn "
                    "entity, identity, number, and continuity binding must preserve the exact "
                    "authoritative source or supplied typed Context. Never translate, "
                    "transliterate, infer, or copy a transport/runtime identifier into a "
                    "semantic binding. "
                    "Keep binding dimensions exact: duration is elapsed time, while speed "
                    "is only an explicitly requested pace or velocity. Never invent a "
                    "normal/default speed, and never place a duration phrase, repetition "
                    "word, action verb, or direction under speed. Omit speed when the "
                    "person supplied no pace or velocity meaning. "
                    "Preserve the WHAT modality as one semantic unit: use output_mode=speech "
                    "for ordinary conversation whose answer is already entailed by supplied "
                    "bounded semantic context and needs only authored wording. Use "
                    "output_mode=information for a factual answer not fixed by that semantic "
                    "context; do not decide whether or how Planner acquires Evidence. "
                    "Speech applies only when the requested observable outcome itself is "
                    "ordinary authored conversation; embodied, vocal-performance, media, "
                    "and state-changing requests retain their exact modes. Use "
                    "stateful_effect only for durable/future "
                    "state changes outside embodiment. Locomotion, posture, gaze, gesture, "
                    "physical manipulation, carrying, and handover are body_action even "
                    "when their result changes physical state. Never decide here whether "
                    "work, fresh Evidence, a Capability, "
                    "or provider is required. "
                    "Classify declarative context before counting outcomes: an explanation, "
                    "personal situation, or stated future plan is not another "
                    "Responsibility unless the source actually asks Chromie to confirm, "
                    "acknowledge, remember, record, schedule, monitor, or act on it. "
                    "Preserve negation as negation. A cessation or prohibition that "
                    "targets supplied active work may relate to that exact Goal, but "
                    "never becomes a new positive embodiment or an invented opposite "
                    "posture. A clause that only excludes replay of already-terminal "
                    "recent work is constraint/context when independent current outcomes "
                    "remain; use supplied lifecycle evidence rather than phrase matching. "
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
                    "responsibilities must equal that count. Before returning, verify that "
                    "every speed binding is backed by explicit pace or velocity meaning; "
                    "duration, count, action, and direction are never speed."
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
            if exact_surfaces and isinstance(responsibility_schema, dict):
                binding_schema = responsibility_schema.get("properties", {}).get(
                    "binding_items"
                )
                if isinstance(binding_schema, dict):
                    binding_properties = binding_schema.setdefault("properties", {})
                    if constrain_location_provenance:
                        binding_properties["location"] = {
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

        return bool(decision.unresolved)

    @staticmethod
    def _validate_interpretation_content(
        request: GoalInterpretationRequest,
        content: str,
    ) -> GoalInterpretationDecision:
        parsed = _extract_json_object(content)
        _normalize_model_interpretation_projection(parsed)
        _normalize_mechanical_goal_interpretation_dto(parsed)
        _strip_bound_values_from_unresolved(parsed)
        # Planner/route fields are an authority violation rather than a generic
        # malformed DTO and therefore fail closed without a semantic repair call.
        _reject_planner_shaped_goal_interpretation(parsed)
        # Validate the model DTO's closed mechanical shape before semantic
        # provenance checks choose an escalation path.  Otherwise one response
        # containing both an envelope echo and an out-of-range confidence value
        # is misreported as a semantic violation and cannot use the one permitted
        # same-stage DTO repair.
        GoalInterpretationDecision.model_validate(parsed)
        _validate_primary_source_evidence(request, parsed)
        _reject_canonical_goal_identity_refs(request, parsed)
        _reject_unknown_goal_refs(request, parsed)
        _reject_continuity_completion_contract_mismatch(request, parsed)
        _reject_unprovenanced_location_bindings(request, parsed)
        _strip_mechanically_unprovenanced_speed_bindings(request, parsed)
        _reject_unprovenanced_speed_bindings(request, parsed)
        _reject_unprovenanced_duration_bindings(request, parsed)
        _reject_runtime_identity_bindings(request, parsed)
        _reject_unavailable_or_mismatched_prior_assistant_utterance(request, parsed)
        _strip_language_envelope_bindings(request, parsed)
        _strip_redundant_conversational_turn_echo_bindings(request, parsed)
        _strip_redundant_outcome_echo_bindings(parsed)
        _reject_hidden_effect_or_how_bindings(parsed)
        _normalize_corrupted_count_binding_names(parsed)
        _reject_malformed_binding_names(parsed)
        _reject_malformed_binding_values(parsed)
        _reject_transport_echo_bindings(request, parsed)
        _reject_untyped_coordination_bindings(parsed)
        _reject_dropped_explicit_numeric_bindings(request, parsed)
        _reject_noncanonical_count_bindings(parsed)
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
            "material_unresolved_responsibility_meaning",
        )
        try:
            data = await self._chat_logged(
                self.build_deep_interpretation_payload(request),
                stage="goal_interpretation_deep",
                request=request,
            )
            try:
                decision = self._validate_interpretation_content(
                    request,
                    str(data.get("message", {}).get("content") or ""),
                )
            except _GoalInterpretationLocationProvenanceViolation:
                # Deep GI already owns the semantic delegation. A translated or
                # otherwise unprovenanced location is a mechanically invalid DTO,
                # so use the one permitted same-stage repair with an exact-source
                # decoder constraint. No semantic state has been accepted yet.
                repaired = await self._chat_logged(
                    self.build_deep_interpretation_payload(
                        request,
                        constrain_location_provenance=True,
                    ),
                    stage="goal_interpretation_deep_contract_repair",
                    request=request,
                )
                decision = self._validate_interpretation_content(
                    request,
                    str(repaired.get("message", {}).get("content") or ""),
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
