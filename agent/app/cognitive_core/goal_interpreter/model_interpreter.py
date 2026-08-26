from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
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
    GoalInterpretationCoverageCertificate,
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


def _strip_certificate_owned_coordination_bindings(parsed: dict[str, Any]) -> None:
    """Discard provisional relation fields before audited certificate projection.

    This helper is used only for a fresh resegmentation whose independent atomic
    certificate already owns ordering/concurrency. Provider-written free-form
    sibling wording is therefore neither semantic authority nor useful input;
    ``_project_audited_atomic_contract`` restores the exact typed local refs before
    the result is accepted and revalidated.
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
            if (
                "coordinat" in name
                or "combin" in name
                or "simultan" in name
                or name
                in {
                    "after",
                    "alongside",
                    "before",
                    "concurrent_with",
                    "follows",
                    "parallel_with",
                    "precedes",
                    "with",
                }
            ):
                bindings.pop(raw_name, None)


_MALFORMED_BINDING_NAME = re.compile(r"[{}\[\]\"'“”‘’,:;/\\]")
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


def _coverage_source_tokens(text: str) -> list[dict[str, Any]]:
    """Expose bounded exact source units without asking a model to retype them.

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


def _materialize_coverage_source_excerpts(
    request: GoalInterpretationRequest,
    raw: dict[str, Any],
    *,
    decision: GoalInterpretationDecision | None = None,
) -> dict[str, Any]:
    """Derive exact audit excerpts from contiguous model-cited source tokens."""

    source = " ".join(str(request.text or "").strip().split())
    tokens = _coverage_source_tokens(source)
    by_ref = {str(item["ref"]): item for item in tokens}
    index_by_ref = {str(item["ref"]): index for index, item in enumerate(tokens)}
    exact_candidate_spans: dict[str, tuple[int, int]] = {}
    if decision is not None:
        folded_source = source.casefold()
        for responsibility in decision.responsibilities:
            candidate = " ".join(responsibility.outcome.strip().split())
            if not candidate:
                continue
            folded_candidate = candidate.casefold()
            starts: list[int] = []
            offset = 0
            while True:
                found = folded_source.find(folded_candidate, offset)
                if found < 0:
                    break
                starts.append(found)
                offset = found + 1
            if len(starts) != 1:
                continue
            start_char = starts[0]
            end_char = start_char + len(candidate)
            matching_tokens = [
                (start_index, end_index)
                for start_index, first in enumerate(tokens)
                for end_index, last in enumerate(tokens[start_index:], start_index)
                if int(first["start"]) == start_char
                and int(last["end"]) == end_char
            ]
            if len(matching_tokens) == 1:
                exact_candidate_spans[responsibility.local_ref] = matching_tokens[0]
    candidate_audit_owner_counts: dict[str, int] = {}
    for item in raw.get("responsibility_items") or []:
        if not isinstance(item, dict):
            continue
        candidate_refs = item.get("responsibility_refs")
        if not isinstance(candidate_refs, list):
            continue
        for candidate_ref in {
            str(value).strip() for value in candidate_refs if str(value).strip()
        }:
            candidate_audit_owner_counts[candidate_ref] = (
                candidate_audit_owner_counts.get(candidate_ref, 0) + 1
            )
    responsibility_span_items: list[tuple[dict[str, Any], int, int]] = []
    for collection_name in ("responsibility_items", "supporting_items"):
        items = raw.get(collection_name)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            # Source-excerpt input remains accepted by direct unit tests and old
            # retained evidence, but the live response schema below never exposes
            # this free-form field to the model.
            if isinstance(item.get("source_excerpt"), str):
                continue
            start_ref = str(item.pop("source_start_token_ref", "") or "").strip()
            end_ref = str(item.pop("source_end_token_ref", "") or "").strip()
            if not start_ref or not end_ref:
                # Compatibility for retained iteration-5 evidence and direct tests;
                # the live schema no longer exposes variable-length token lists.
                refs = item.pop("source_token_refs", None)
                if not isinstance(refs, list) or not refs:
                    raise _GoalInterpretationSemanticStructureViolation(
                        "Responsibility coverage must cite a source token span"
                    )
                start_ref = str(refs[0]).strip()
                end_ref = str(refs[-1]).strip()
            if start_ref not in by_ref or end_ref not in by_ref:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage cited unknown source token refs"
                )
            if index_by_ref[start_ref] > index_by_ref[end_ref]:
                # The model selected two exact authoritative endpoints but emitted
                # their mechanically typed order backwards. Reordering those cited
                # endpoints recovers the same unique source span without inventing,
                # translating, or reclassifying any semantic material.
                start_ref, end_ref = end_ref, start_ref
            if collection_name == "responsibility_items":
                candidate_refs = item.get("responsibility_refs")
                if isinstance(candidate_refs, list) and len(candidate_refs) == 1:
                    candidate_ref = str(candidate_refs[0]).strip()
                    exact_span = (
                        exact_candidate_spans.get(candidate_ref)
                        if candidate_audit_owner_counts.get(candidate_ref) == 1
                        else None
                    )
                    if exact_span is not None:
                        # The candidate's model-owned outcome is itself one unique,
                        # token-aligned verbatim source slice. Prefer that exact
                        # provenance over a decoder citation that swallowed a
                        # sibling predicate. This changes neither candidate owner,
                        # coverage, modality, nor relation. When several independent
                        # audit items cite one overmerged candidate, keep their
                        # model-cited disjoint source spans: replacing every item with
                        # the candidate's whole span would erase the very evidence
                        # needed for source-grounded resegmentation.
                        start_ref = str(tokens[exact_span[0]]["ref"])
                        end_ref = str(tokens[exact_span[1]]["ref"])
            first = by_ref[start_ref]
            last = by_ref[end_ref]
            item["source_excerpt"] = source[int(first["start"]):int(last["end"])]
            if collection_name == "responsibility_items":
                responsibility_span_items.append(
                    (item, index_by_ref[start_ref], index_by_ref[end_ref])
                )
    ordered_span_items = sorted(
        responsibility_span_items,
        key=lambda value: (value[1], value[2]),
    )
    # A coverage decoder occasionally includes the coordination token in both
    # adjacent positive spans (for example ``Nod twice, then`` and ``then blink
    # once``).  When both spans retain a non-empty exclusive source region, the
    # overlap has one mechanically unique source-order normalization: keep the
    # later span and end the earlier span immediately before it.  Containment or
    # identical spans remain invalid because trimming those would require a
    # semantic judgment about whether the model invented a second outcome.
    normalized_span_items: list[tuple[dict[str, Any], int, int]] = []
    for item, start, end in ordered_span_items:
        if normalized_span_items:
            previous_item, previous_start, previous_end = normalized_span_items[-1]
            if start <= previous_end:
                if previous_start < start and previous_end < end:
                    previous_end = start - 1
                    normalized_span_items[-1] = (
                        previous_item,
                        previous_start,
                        previous_end,
                    )
                else:
                    raise _GoalInterpretationSemanticStructureViolation(
                        "Independent Responsibility coverage source spans must not overlap"
                    )
        normalized_span_items.append((item, start, end))
    ordered_span_items = normalized_span_items
    for item, start, end in ordered_span_items:
        first = tokens[start]
        last = tokens[end]
        item["source_excerpt"] = source[int(first["start"]):int(last["end"])]
    for index, (_, left_start, left_end) in enumerate(ordered_span_items):
        for _, right_start, right_end in ordered_span_items[index + 1 :]:
            if max(left_start, right_start) <= min(left_end, right_end):
                raise _GoalInterpretationSemanticStructureViolation(
                    "Independent Responsibility coverage source spans must not overlap"
                )
    responsibility_items = raw.get("responsibility_items")
    responsibility_items = (
        responsibility_items if isinstance(responsibility_items, list) else []
    )
    if ordered_span_items:
        # Source position is already an authoritative mechanical property of each
        # model-cited span. Canonicalize array order and audit identity from those
        # positions instead of spending the single DTO repair on an otherwise
        # unchanged citation set. Remapping relation endpoints preserves the
        # model-authored relation; it does not infer or reclassify source meaning.
        prior_refs = [
            str(item.get("audit_ref") or "").strip()
            for item, _, _ in ordered_span_items
        ]
        ref_mapping = (
            {
                prior_ref: f"a{index + 1}"
                for index, prior_ref in enumerate(prior_refs)
            }
            if all(prior_refs) and len(set(prior_refs)) == len(prior_refs)
            else {}
        )
        responsibility_items[:] = [item for item, _, _ in ordered_span_items]
        for index, item in enumerate(responsibility_items):
            item["audit_ref"] = f"a{index + 1}"
        if ref_mapping:
            supporting_items = raw.get("supporting_items")
            for item in supporting_items if isinstance(supporting_items, list) else []:
                if not isinstance(item, dict):
                    continue
                related_refs = item.get("related_audit_refs")
                if isinstance(related_refs, list):
                    item["related_audit_refs"] = [
                        ref_mapping.get(str(value).strip(), str(value).strip())
                        for value in related_refs
                    ]
    for index, item in enumerate(responsibility_items):
        if isinstance(item, dict) and not str(item.get("audit_ref") or "").strip():
            item["audit_ref"] = f"a{index + 1}"
    supporting_items = raw.get("supporting_items")
    for item in supporting_items if isinstance(supporting_items, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") in {"context", "framing"}:
            # These schema roles are definitionally acknowledged without owning
            # a candidate Responsibility. Clear model-emitted ownership fields;
            # this is a closed mechanical projection, not semantic reclassification.
            item["coverage"] = "covered"
            item["responsibility_refs"] = []
            item["relation_kind"] = "none"
            item["related_audit_refs"] = []
        relation_kind = str(item.get("relation_kind") or "none")
        related_audit_refs = item.get("related_audit_refs")
        if not isinstance(related_audit_refs, list):
            item["related_audit_refs"] = []
        candidate_refs = item.get("responsibility_refs")
        candidate_refs = candidate_refs if isinstance(candidate_refs, list) else []
        candidate_audit_refs: set[str] = set()
        for candidate_ref in candidate_refs:
            matching_audit_refs = {
                str(responsibility_item.get("audit_ref") or "").strip()
                for responsibility_item in responsibility_items
                if isinstance(responsibility_item, dict)
                and str(candidate_ref).strip()
                in {
                    str(value).strip()
                    for value in responsibility_item.get("responsibility_refs") or []
                }
                and str(responsibility_item.get("audit_ref") or "").strip()
            }
            if len(matching_audit_refs) == 1:
                candidate_audit_refs.update(matching_audit_refs)
        if relation_kind != "none":
            # Both fields are typed references emitted by the same audit.  Some
            # constrained decoders put the earlier endpoint in candidate-owner
            # form and only the later endpoint in related_audit_refs.  Merge the
            # two explicit endpoint sets in authoritative source order; no
            # relation or endpoint is inferred from natural language here.
            cited_audit_refs = set(item["related_audit_refs"]) | candidate_audit_refs
            item["related_audit_refs"] = [
                str(responsibility_item.get("audit_ref") or "").strip()
                for responsibility_item in responsibility_items
                if str(responsibility_item.get("audit_ref") or "").strip()
                in cited_audit_refs
            ]
        if (
            str(item.get("role") or "") == "constraint"
            and str(item.get("coverage") or "") != "covered"
            and not item["related_audit_refs"]
        ):
            support_excerpt = str(item.get("source_excerpt") or "")
            overlapping_audit_refs = [
                str(responsibility_item.get("audit_ref") or "").strip()
                for responsibility_item in responsibility_items
                if support_excerpt
                and (
                    support_excerpt
                    in str(responsibility_item.get("source_excerpt") or "")
                    or str(responsibility_item.get("source_excerpt") or "")
                    in support_excerpt
                )
            ]
            if len(overlapping_audit_refs) == 1:
                # An uncovered supporting copy of exactly one positive span has
                # one mechanically unique positive audit owner.  Attaching that
                # already-emitted owner makes the DTO valid without changing its
                # coverage judgment or choosing a new semantic relation.
                item["related_audit_refs"] = overlapping_audit_refs
        if relation_kind != "none" and len(item["related_audit_refs"]) < 2:
            # ordered/parallel are relations among independently observable
            # outcomes. A model label attached to only one audited outcome is
            # definitionally a modifier, not a typed coordination relation.
            # Keep the cited constraint and its explicit atomic owner while
            # clearing only the impossible relation shape.
            item["relation_kind"] = "none"
        responsibility_items_by_ref = {
            str(responsibility_item.get("audit_ref") or "").strip(): responsibility_item
            for responsibility_item in responsibility_items
            if isinstance(responsibility_item, dict)
            and str(responsibility_item.get("audit_ref") or "").strip()
        }
        if set(item["related_audit_refs"]).issubset(responsibility_items_by_ref):
            # Candidate ownership is redundant with typed atomic audit refs.
            # Project it mechanically so resegmentation receives one owner for an
            # ordinary modifier and the exact endpoints for a typed relation.
            item["responsibility_refs"] = list(
                dict.fromkeys(
                    str(candidate_ref).strip()
                    for audit_ref in item["related_audit_refs"]
                    for candidate_ref in responsibility_items_by_ref[audit_ref].get(
                        "responsibility_refs", []
                    )
                    if str(candidate_ref).strip()
                )
            )
    return raw


def _project_audited_atomic_contract(
    decision: GoalInterpretationDecision,
    certificate: GoalInterpretationCoverageCertificate,
) -> GoalInterpretationDecision:
    """Project independently audited modality and coordination into fresh DTOs.

    The coverage model has already classified these source semantics and assigned
    stable audit refs. This projection performs no source-language interpretation:
    it only carries those typed claims across the fresh-resegmentation decoder
    boundary, whose nested conditional JSON-schema constraints are not reliably
    enforced by every supported Ollama grammar implementation.
    """

    modes_by_ref = {
        str(item.audit_ref).strip(): item.required_output_mode
        for item in certificate.responsibility_items
        if str(item.audit_ref).strip()
    }
    bindings_by_ref: dict[str, dict[str, Any]] = {
        audit_ref: {} for audit_ref in modes_by_ref
    }
    for relation in certificate.supporting_items:
        refs = [
            ref
            for ref in relation.related_audit_refs
            if ref in modes_by_ref
        ]
        if relation.relation_kind == "ordered" and len(refs) >= 2:
            for earlier_ref, later_ref in zip(refs, refs[1:], strict=False):
                bindings_by_ref[later_ref]["after"] = earlier_ref
        elif relation.relation_kind == "parallel" and len(refs) >= 2:
            for source_ref in refs:
                bindings_by_ref[source_ref]["parallel_with"] = [
                    ref for ref in refs if ref != source_ref
                ]

    payload = decision.model_dump(mode="python")
    for responsibility in payload["responsibilities"]:
        local_ref = str(responsibility.get("local_ref") or "").strip()
        if local_ref not in modes_by_ref:
            continue
        bindings = dict(responsibility.get("bindings") or {})
        for field in ("before", "after", "parallel_with"):
            bindings.pop(field, None)
        bindings.update(bindings_by_ref[local_ref])
        responsibility["bindings"] = bindings
        responsibility["output_mode"] = modes_by_ref[local_ref]
    return GoalInterpretationDecision.model_validate(payload)


def _project_audited_contract_onto_covered_candidates(
    decision: GoalInterpretationDecision,
    certificate: GoalInterpretationCoverageCertificate,
) -> GoalInterpretationDecision | None:
    """Project a bijective audit onto existing candidates without reinterpreting.

    When the independent audit already maps every atomic source outcome to one
    unique existing candidate, a missing typed relation or corrected output mode
    does not require a fresh semantic generation. The model-owned audit supplies
    those exact types; Host only copies its references into the corresponding
    candidate DTO. A non-bijective audit still requires source resegmentation.
    """

    candidate_refs = {item.local_ref for item in decision.responsibilities}
    audit_to_candidate: dict[str, str] = {}
    candidate_owners: set[str] = set()
    for item in certificate.responsibility_items:
        if (
            not item.independently_satisfiable
            or len(item.responsibility_refs) != 1
            or not item.audit_ref
        ):
            return None
        candidate_ref = item.responsibility_refs[0]
        if candidate_ref not in candidate_refs or candidate_ref in candidate_owners:
            return None
        audit_to_candidate[item.audit_ref] = candidate_ref
        candidate_owners.add(candidate_ref)
    if candidate_owners != candidate_refs:
        return None

    payload = decision.model_dump(mode="python")
    by_ref = {
        str(item.get("local_ref") or ""): item
        for item in payload.get("responsibilities") or []
        if isinstance(item, dict)
    }
    for item in certificate.responsibility_items:
        by_ref[audit_to_candidate[item.audit_ref]]["output_mode"] = (
            item.required_output_mode
        )
    for item in by_ref.values():
        bindings = dict(item.get("bindings") or {})
        for field in ("before", "after", "parallel_with"):
            bindings.pop(field, None)
        item["bindings"] = bindings
    for relation in certificate.supporting_items:
        refs = [
            audit_to_candidate[audit_ref]
            for audit_ref in relation.related_audit_refs
            if audit_ref in audit_to_candidate
        ]
        if relation.relation_kind == "ordered" and len(refs) >= 2:
            for earlier_ref, later_ref in zip(refs, refs[1:], strict=False):
                by_ref[later_ref]["bindings"]["after"] = earlier_ref
        elif relation.relation_kind == "parallel" and len(refs) >= 2:
            for candidate_ref in refs:
                by_ref[candidate_ref]["bindings"]["parallel_with"] = [
                    sibling_ref
                    for sibling_ref in refs
                    if sibling_ref != candidate_ref
                ]
    return GoalInterpretationDecision.model_validate(payload)


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

    count_names = {"count", "item_count", "repetition_count"}
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
            if name not in count_names:
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


def _goal_interpretation_binding_names(parsed: dict[str, Any]) -> list[str]:
    """Return validated candidate DTO field names without retaining its values."""

    names: list[str] = []
    responsibilities = parsed.get("responsibilities")
    if not isinstance(responsibilities, list):
        return names
    for item in responsibilities:
        bindings = item.get("bindings") if isinstance(item, dict) else None
        if not isinstance(bindings, dict):
            continue
        for raw_name in bindings:
            name = str(raw_name).strip()
            if (
                name
                and name not in names
                and not _is_noncanonical_speed_binding_name(name)
            ):
                names.append(name)
    return names


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
            "commit the Goal relationship. A semantically independent new outcome is "
            "relationship=new even when completed or recent Goals are present in "
            "Context. Use continue/modify/clarify/confirm/reference or another existing-"
            "Goal relationship only when the current turn actually refers to that same "
            "Goal; never attach an unrelated new request to the most recent Goal merely "
            "because its ID is available. "
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
            "that Goal's provider-neutral WHAT output_mode. Continuation of body action, "
            "media, information, stateful effect, or vocal performance never becomes "
            "ordinary speech merely because the current turn is a short reference. "
            "Preserve deictic spatial meaning such as here/there, inside/outside, "
            "ahead/behind, and equivalent expressions in any language as an exact "
            "current-turn location or direction binding when it changes the outcome. "
            "Any place or spatial-location meaning uses the one canonical binding name "
            "location; never rename that dimension to location_scope, target_location, "
            "place_location, or another alias. "
            "Use speed only when the person explicitly supplied pace or velocity meaning. "
            "Do not invent a normal/default speed, and never store a duration phrase, "
            "repetition word, action verb, or direction under speed; keep those in their "
            "own semantic dimensions. "
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
            "a default. Classify only the human-facing WHAT. Use output_mode=speech for "
            "ordinary conversation whose answer is already entailed by the supplied "
            "bounded semantic context and therefore needs only authored conversational "
            "wording. Use output_mode=information when the requested factual answer is "
            "not fixed by that semantic context, including external, changing, observed, "
            "or private-runtime information. This classifies the human-facing WHAT; it "
            "does not decide whether or how Planner acquires Evidence. Speech applies "
            "only when the requested observable outcome itself is ordinary authored "
            "conversation. An embodied, vocal-performance, media, or state-changing "
            "request never becomes speech merely because it was expressed in dialogue "
            "or can be described in words. Use "
            "output_mode=stateful_effect when the requested "
            "WHAT is a durable or future state change outside embodiment, such as recording, "
            "scheduling, changing a setting, or sending later. Locomotion, posture, "
            "gaze, gesture, physical manipulation, carrying, and handover remain "
            "body_action even when they change location or physical state. Preserve body, media, and vocal "
            "effects in their exact observable modes. Perform one final modality and "
            "atomicity audit across languages: grammatical fusion, shared aspect, or a "
            "while/during relation never merges independently observable locomotion and "
            "vocal performance into one outcome. Emit each independently judgeable effect "
            "as its own Responsibility and preserve their parallel relation. A request to "
            "acquire, carry, bring, fetch, retrieve, or hand over a physical object is one "
            "physical-delivery body_action Responsibility, never ordinary speech merely "
            "because the recipient is addressed in conversation. Do not decide whether downstream "
            "work, fresh Evidence, a Capability, or a provider is required; Planner owns "
            "that judgment from canonical Goal state, trusted Evidence, and available "
            "Capabilities. No route, intent, response wording, Activity, Work, "
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
            bindings = responsibility.get("properties", {}).get("bindings")
            if isinstance(bindings, dict):
                bindings["propertyNames"] = {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "pattern": r"^[^{}\[\]\"'“”‘’,:;/\\]+$",
                    "description": (
                        "A semantic dimension name only; never embed JSON syntax, "
                        "quotes, punctuation, comments, or another field in a key."
                    ),
                }
                binding_properties = bindings.setdefault("properties", {})
                for count_name in ("count", "item_count", "repetition_count"):
                    binding_properties[count_name] = {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Canonical positive JSON integer for a typed repetition "
                            "count; never emit number words or numeric strings."
                        ),
                    }
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
                        "description": "Control or playback of existing media.",
                    },
                ]
                output_mode["oneOf"] = output_mode_variants
                output_mode["description"] = (
                    "Provider-neutral WHAT category for this one atomic outcome. "
                    "Use speech for ordinary conversation whose answer is already entailed "
                    "by supplied bounded semantic context and needs only authored wording. "
                    "Use information for a factual answer not fixed by that semantic "
                    "context; this category does not decide whether or how Planner acquires "
                    "Evidence. Speech applies only when the requested observable outcome "
                    "itself is ordinary authored conversation. Embodied, vocal-performance, "
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
                "num_predict": self.num_predict,
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
        constrain_speed_provenance: bool = False,
        constrained_binding_names: list[str] | None = None,
        atomic_coverage_certificate: GoalInterpretationCoverageCertificate | None = None,
        source_structure_violation: str = "",
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
        independent_audit_items = [
            item
            for item in (
                atomic_coverage_certificate.responsibility_items
                if atomic_coverage_certificate is not None
                else []
            )
            if item.role == "responsibility"
            and item.independently_satisfiable
        ]
        supporting_audit_items = [
            item
            for item in (
                atomic_coverage_certificate.supporting_items
                if atomic_coverage_certificate is not None
                else []
            )
        ]
        deep_audit_refs = [
            str(item.audit_ref or f"a{index + 1}").strip()
            for index, item in enumerate(independent_audit_items)
        ]
        audit_payloads = [
            {
                **item.model_dump(mode="json"),
                "audit_ref": deep_audit_refs[index],
            }
            for index, item in enumerate(independent_audit_items)
        ]
        audit_refs_by_candidate: dict[str, list[str]] = {}
        for audit_ref, item in zip(
            deep_audit_refs, independent_audit_items, strict=True
        ):
            for candidate_ref in item.responsibility_refs:
                audit_refs_by_candidate.setdefault(candidate_ref, []).append(audit_ref)
        supporting_payloads: list[dict[str, Any]] = []
        related_audit_refs_by_index: list[list[str]] = []
        for item in supporting_audit_items:
            related_audit_refs = list(item.related_audit_refs)
            if item.relation_kind != "none" and not related_audit_refs:
                related_audit_refs = list(
                    dict.fromkeys(
                        audit_ref
                        for candidate_ref in item.responsibility_refs
                        for audit_ref in audit_refs_by_candidate.get(candidate_ref, [])
                    )
                )
            related_audit_refs_by_index.append(related_audit_refs)
            supporting_payloads.append(
                {
                    **item.model_dump(mode="json"),
                    "related_audit_refs": related_audit_refs,
                }
            )
        atomic_audit_contract = (
            "\n\nAn independent source-based atomic coverage audit has already "
            "identified the following independently satisfiable source outcomes. "
            "This is Goal Interpretation evidence, not a candidate plan and not a "
            "Capability hint. Emit exactly one sibling Responsibility per listed "
            "item, preserving its exact source span and required output mode. Do "
            "not merge two listed items into one outcome or binding.\n"
            + _bounded_json(
                audit_payloads,
                max_chars=5000,
            )
            + "\nThe same audit identified these non-outcome source constraints and "
            "context fragments. Preserve material ordering and concurrency in the "
            "fresh sibling Responsibilities: use before/after sibling-local-ref "
            "bindings for order and parallel_with sibling-local-ref bindings for "
            "requested concurrency. Every other constraint carries its exact owning "
            "positive audit refs; attach its material modifier only to those sibling "
            "Responsibilities and never copy it to an unlisted sibling. Use each "
            "positive item's audit_ref as the exact "
            "fresh Responsibility local_ref; it is turn-local audit identity, not a "
            "Goal identity.\n"
            + _bounded_json(
                supporting_payloads,
                max_chars=3000,
            )
            if independent_audit_items
            else ""
        )
        structure_feedback = (
            "\n\nThe earlier source-structure validator rejected a candidate before "
            "it could become semantic state. Re-read the source from scratch and make "
            "the fresh DTO avoid this general structural defect; do not copy or edit "
            "the rejected candidate:\n"
            + source_structure_violation[:1200]
            if source_structure_violation
            else ""
        )
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
                    "count every independently observable effect related by coordination "
                    "grammar in any language. If the source "
                    "coordinates N effects that a person could accept or reject separately, "
                    "responsibilities must contain N sibling items. Never hide one effect "
                    "inside another item's outcome or binding. A coordination binding may "
                    "contain only exact sibling local_ref values, not words naming an action. "
                    "Audit semantic provenance before returning: every explicit current-turn "
                    "entity, identity, number, and continuity binding must preserve the exact "
                    "authoritative source or supplied typed Context. Never translate, "
                    "transliterate, infer, or copy a transport/runtime identifier into a "
                    "semantic binding. "
                    "Keep binding dimensions exact: duration is elapsed time, while speed "
                    "is only an explicitly requested pace or velocity. Never invent a "
                    "normal/default speed, and never place a duration phrase, repetition "
                    "word, action verb, or direction under speed. Omit speed when the "
                    "person supplied no pace or velocity meaning. "
                    "Audit the WHAT modality as one semantic unit: use output_mode=speech "
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
                    "Audit declarative context before counting outcomes: an explanation, "
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
                    + atomic_audit_contract
                    + structure_feedback
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
                    + atomic_audit_contract
                    + structure_feedback
                ),
            },
        ]
        if independent_audit_items:
            responsibilities_schema = payload.get("format", {}).get(
                "properties", {}
            ).get("responsibilities")
            if isinstance(responsibilities_schema, dict):
                responsibilities_schema["minItems"] = len(independent_audit_items)
                responsibilities_schema["maxItems"] = len(independent_audit_items)
                responsibilities_schema["description"] = (
                    "Emit exactly one atomic Responsibility for each independent "
                    "source-audit item supplied in the prompt."
                )
            # The independent model-authored audit supplies exact source outcome
            # modality and typed relations. Project those claims into the one
            # permitted fresh source interpretation's decoder schema. Host code
            # neither discovers source semantics nor mutates the returned DTO.
            responsibility_model = payload.get("format", {}).get(
                "$defs", {}
            ).get("CognitiveResponsibilityProposal")
            if (
                len(deep_audit_refs) == len(set(deep_audit_refs))
                and isinstance(responsibility_model, dict)
            ):
                local_ref_schema = responsibility_model.get("properties", {}).get(
                    "local_ref"
                )
                if isinstance(local_ref_schema, dict):
                    local_ref_schema["enum"] = list(deep_audit_refs)
                required_bindings_by_ref: dict[str, dict[str, Any]] = {}
                for relation, refs in zip(
                    supporting_audit_items,
                    related_audit_refs_by_index,
                    strict=True,
                ):
                    if (
                        relation.relation_kind == "ordered"
                        and len(refs) >= 2
                        and set(refs).issubset(set(deep_audit_refs))
                    ):
                        for earlier_ref, later_ref in zip(
                            refs, refs[1:], strict=False
                        ):
                            required_bindings_by_ref.setdefault(later_ref, {})[
                                "after"
                            ] = earlier_ref
                    elif (
                        relation.relation_kind == "parallel"
                        and len(refs) >= 2
                        and set(refs).issubset(set(deep_audit_refs))
                    ):
                        for source_ref in refs:
                            required_bindings_by_ref.setdefault(source_ref, {})[
                                "parallel_with"
                            ] = [ref for ref in refs if ref != source_ref]
                relation_constraints = responsibility_model.setdefault("allOf", [])
                required_modes_by_ref = {
                    audit_ref: item.required_output_mode
                    for audit_ref, item in zip(
                        deep_audit_refs,
                        independent_audit_items,
                        strict=True,
                    )
                }
                for source_ref in deep_audit_refs:
                    required_bindings = required_bindings_by_ref.get(source_ref, {})
                    then_properties: dict[str, Any] = {
                        "output_mode": {
                            "const": required_modes_by_ref[source_ref]
                        }
                    }
                    if required_bindings:
                        then_properties["bindings"] = {
                            "type": "object",
                            "properties": {
                                name: {"const": value}
                                for name, value in required_bindings.items()
                            },
                            "required": list(required_bindings),
                        }
                    relation_constraints.append(
                        {
                            "if": {
                                "properties": {
                                    "local_ref": {"const": source_ref}
                                },
                                "required": ["local_ref"],
                            },
                            "then": {
                                "properties": then_properties
                            },
                        }
                    )
        if constrain_location_provenance or constrain_speed_provenance:
            exact_surfaces = _short_exact_surface_substrings(request.text)
            responsibility_schema = (
                payload.get("format", {})
                .get("$defs", {})
                .get("CognitiveResponsibilityProposal", {})
            )
            if exact_surfaces and isinstance(responsibility_schema, dict):
                binding_schema = responsibility_schema.get("properties", {}).get(
                    "bindings"
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
                        binding_schema["propertyNames"] = {
                            "anyOf": [
                                {"const": "location"},
                                {
                                    "not": {
                                        "pattern": (
                                            r"(?:^|[_\-\s])"
                                            r"[Ll][Oo][Cc][Aa][Tt][Ii][Oo][Nn]"
                                            r"(?:$|[_\-\s])"
                                        )
                                    }
                                },
                            ],
                            "description": (
                                "Location meaning has exactly one canonical binding name: "
                                "location. Other semantic dimensions remain writable."
                            ),
                        }
                    if constrain_speed_provenance:
                        recovery_binding_names = {
                            "after",
                            "before",
                            "count",
                            "item_count",
                            "location",
                            "parallel_with",
                            "repetition_count",
                            "speed",
                            *(constrained_binding_names or []),
                        }
                        for name in sorted(recovery_binding_names):
                            if not _is_noncanonical_speed_binding_name(name):
                                binding_properties.setdefault(name, {})
                        if constrained_binding_names is not None:
                            binding_schema["additionalProperties"] = False
                            binding_schema["description"] = (
                                "During source-based recovery, reuse only mechanically "
                                "validated candidate dimensions or the existing canonical "
                                "location, speed, count, and sibling-coordination fields. "
                                "Omit a dimension when the source does not support it."
                            )
                        binding_properties["speed"] = {
                            "anyOf": [
                                {"type": "string", "enum": exact_surfaces},
                                {"type": "number"},
                            ],
                            "description": (
                                "If speed is present, copy one exact contiguous source "
                                "pace/velocity surface or explicit numeric velocity; omit "
                                "speed when the source supplies no pace or velocity."
                            ),
                        }
                        forbidden_speed_binding_names = {"pace", "velocity"}
                        for dimension in ("speed", "pace", "velocity"):
                            for qualifier in ("level", "mode", "setting", "value"):
                                forbidden_speed_binding_names.add(
                                    f"{dimension}_{qualifier}"
                                )
                                forbidden_speed_binding_names.add(
                                    f"{qualifier}_{dimension}"
                                )
                        for alias in sorted(forbidden_speed_binding_names):
                            binding_properties[alias] = {
                                "const": "__forbidden_noncanonical_speed_binding__",
                                "description": (
                                    "Reserved invalid marker for a noncanonical speed "
                                    "binding name. Never emit this property; use speed "
                                    "only for source-backed pace/velocity meaning."
                                ),
                            }
                        speed_name_constraint = {
                            "anyOf": [
                                {"const": "speed"},
                                {
                                    "not": {
                                        "pattern": (
                                            r"^(?:"
                                            r"[Pp][Aa][Cc][Ee]|"
                                            r"[Vv][Ee][Ll][Oo][Cc][Ii][Tt][Yy]|"
                                            r"(?:[Ss][Pp][Ee][Ee][Dd]|"
                                            r"[Pp][Aa][Cc][Ee]|"
                                            r"[Vv][Ee][Ll][Oo][Cc][Ii][Tt][Yy])"
                                            r"(?:[_\-\s](?:"
                                            r"[Ll][Ee][Vv][Ee][Ll]|"
                                            r"[Mm][Oo][Dd][Ee]|"
                                            r"[Ss][Ee][Tt][Tt][Ii][Nn][Gg]|"
                                            r"[Vv][Aa][Ll][Uu][Ee]))+"
                                            r")$"
                                        )
                                    }
                                },
                            ],
                            "description": (
                                "Speed meaning has exactly one canonical binding name: "
                                "speed. Other semantic dimensions remain writable."
                            ),
                        }
                        if constrain_location_provenance:
                            binding_schema["propertyNames"] = {
                                "allOf": [
                                    binding_schema["propertyNames"],
                                    speed_name_constraint,
                                ]
                            }
                        else:
                            binding_schema["propertyNames"] = speed_name_constraint
        return payload

    @staticmethod
    def _responsibility_coverage_required(
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
    ) -> bool:
        """Audit candidates whose structured shape can conceal material effects.

        Multiple candidates and effect-bearing modes already require independent
        source coverage.  A single ``speech`` candidate also requires it when it
        carries material bindings or merely copies the entire admitted turn as its
        outcome. Those are provider-neutral structural signals that the item may be
        an undifferentiated task echo rather than an authored conversational reply,
        and they prevent a merged multimodal task from suppressing its own audit
        merely by being mislabeled as speech.
        """

        effect_modes = {
            "styled_speech",
            "recitation",
            "singing",
            "humming",
            "nonverbal_vocalization",
            "body_action",
            "media_playback",
            "stateful_effect",
            "other",
        }
        normalized_source = " ".join(request.text.strip().casefold().split())
        return len(decision.responsibilities) > 1 or any(
            item.output_mode in effect_modes
            or (item.output_mode == "speech" and bool(item.bindings))
            or (
                item.output_mode == "speech"
                and " ".join(item.outcome.strip().casefold().split())
                == normalized_source
            )
            for item in decision.responsibilities
        )

    def build_responsibility_coverage_payload(
        self,
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
        *,
        authoritative_atomic_certificate: GoalInterpretationCoverageCertificate
        | None = None,
    ) -> dict[str, Any]:
        """Build one independent, source-based atomic Responsibility audit."""

        candidate_refs = [item.local_ref for item in decision.responsibilities]
        schema = GoalInterpretationCoverageCertificate.model_json_schema()
        schema["additionalProperties"] = False
        schema["required"] = [
            "responsibility_items",
            "supporting_items",
            "reason_summary",
        ]
        for item_schema_name in (
            "GoalInterpretationResponsibilityCoverageItem",
            "GoalInterpretationSupportingCoverageItem",
        ):
            item_schema = schema.get("$defs", {}).get(item_schema_name)
            if not isinstance(item_schema, dict):
                continue
            item_schema["required"] = [
                "source_start_token_ref",
                "source_end_token_ref",
                "role",
                "coverage",
                "independently_satisfiable",
                "responsibility_refs",
                "required_output_mode",
                *(
                    ["relation_kind", "related_audit_refs"]
                    if item_schema_name
                    == "GoalInterpretationSupportingCoverageItem"
                    else ["audit_ref"]
                ),
            ]
            source_tokens = _coverage_source_tokens(request.text)
            properties = item_schema.setdefault("properties", {})
            properties.pop("source_excerpt", None)
            properties.pop("source_token_refs", None)
            token_ref_schema = {
                "type": "string",
                "enum": [str(item["ref"]) for item in source_tokens],
            }
            properties["source_start_token_ref"] = {
                **token_ref_schema,
                "description": "First inclusive token of one exact source span.",
            }
            properties["source_end_token_ref"] = {
                **token_ref_schema,
                "description": (
                    "Last inclusive token of the same exact source span; it must "
                    "not precede source_start_token_ref."
                ),
            }
            audit_refs = [f"a{index}" for index in range(1, 13)]
            if item_schema_name == "GoalInterpretationResponsibilityCoverageItem":
                properties["audit_ref"] = {
                    "type": "string",
                    "enum": audit_refs,
                    "description": (
                        "Unique identity for this positive source item. Use a1, a2, "
                        "and so on in source order."
                    ),
                }
            else:
                properties["related_audit_refs"] = {
                    "type": "array",
                    "maxItems": 12,
                    "uniqueItems": True,
                    "items": {"type": "string", "enum": audit_refs},
                    "description": (
                        "Cite the exact positive audit_ref values this constraint "
                        "modifies. Ordered/parallel relations cite all endpoints; "
                        "an ordinary duration, count, direction, manner, or style "
                        "constraint cites only its owning outcome. Context and "
                        "framing use an empty array."
                    ),
                }
            refs = item_schema.get("properties", {}).get("responsibility_refs")
            if isinstance(refs, dict):
                refs["items"] = {
                    "type": "string",
                    "enum": candidate_refs,
                }
                refs["uniqueItems"] = True
        candidates = [
            {
                "local_ref": item.local_ref,
                "outcome": item.outcome,
                "bindings": item.bindings,
                "output_mode": item.output_mode,
            }
            for item in decision.responsibilities
        ]
        semantic_continuity_context = {
            "recent_dialogue": _compact_recent_dialogue(request.context),
            "retained_goals": _compact_active_goal_snapshots(request.context),
            "active_tasks": _compact_active_task_snapshots(request.context),
        }
        retained_atomic_contract = (
            "\n\nRETAINED AUTHORITATIVE ATOMIC CONTRACT:\n"
            + _bounded_json(
                authoritative_atomic_certificate.model_dump(mode="json"),
                max_chars=6000,
            )
            + "\nThis is the accepted independent source audit that caused the fresh "
            "resegmentation. Keep every positive audit_ref, coherent source span, "
            "required_output_mode, and typed relation exactly fixed. This final pass "
            "audits whether the fresh candidate with the matching local_ref now owns "
            "that retained item; it must not reclassify or renumber the source."
            if authoritative_atomic_certificate is not None
            else ""
        )
        payload: dict[str, Any] = {
            "model": self.deep_model,
            "stream": False,
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Chromie's independent atomic Responsibility coverage "
                        "auditor inside Goal Interpretation. Read the authoritative user "
                        "turn from scratch within the supplied bounded semantic continuity "
                        "context. Candidate prose is not source evidence. The continuity "
                        "context is source evidence only for resolving an actual reference, "
                        "ellipsis, clarification, continuation, or resumption in the current "
                        "turn. A contextual continuation/resumption inherits the observable "
                        "outcome and provider-neutral mode of its exact retained Goal; do not "
                        "mark that outcome missing merely because the latest surface does not "
                        "repeat its action words. Cite "
                        "each coherent semantic source span only with "
                        "source_start_token_ref and "
                        "source_end_token_ref from the supplied source-token table. "
                        "Trusted code derives the exact excerpt; never retype, translate, "
                        "or correct source spelling. The token table is only a citation "
                        "mechanism; do not inventory or classify every token. Punctuation, "
                        "function words, and politeness need no standalone item. Cite a "
                        "complete semantically coherent outcome or constraint span rather "
                        "than splitting its words into fragments. A token, syllable, noun, "
                        "duration, connector, location marker, or partial verb phrase is "
                        "never independently satisfiable by itself. Count observable "
                        "predicate outcomes, not tokens: if your reason summary says the "
                        "turn asks for two actions, responsibility_items must contain two "
                        "complete action predicates, not an inventory of their characters. "
                        "A positive "
                        "observable outcome is role=responsibility. Duration, count, "
                        "distance, direction, ordering, timing, manner, style, prohibition, "
                        "and other modifiers are role=constraint on an outcome, not another "
                        "Responsibility. One action together with its duration, count, "
                        "direction, distance, manner, or style remains exactly one positive "
                        "outcome; never emit the modifier as another positive item. Put "
                        "every role=responsibility item only in "
                        "responsibility_items. Put every role=constraint, context, or "
                        "framing item only in supporting_items; those items must use "
                        "independently_satisfiable=false and required_output_mode=none "
                        "because they never inherit an outcome mode. Context and politeness "
                        "framing own no candidate. "
                        "A negative clause is not automatically a second positive body "
                        "outcome. Use supplied retained-Goal lifecycle evidence: a request "
                        "to cancel or pause currently active work remains an independently "
                        "owed relationship outcome, but wording that only prohibits replay "
                        "of already-terminal work is supporting constraint/context on the "
                        "still-positive current outcomes. Never classify an already-true "
                        "idle/no-replay state as new positive embodiment merely because an "
                        "action verb appears under negation. "
                        "Coordination grammar never demotes a positive effect to a constraint: "
                        "when a person can judge two effects completed independently, emit "
                        "two independently_satisfiable responsibility_items even when the "
                        "candidate merged them. Every independently satisfiable item must "
                        "map to exactly one candidate local_ref when a candidate attempts "
                        "that outcome. If one invalid candidate merged multiple outcomes, "
                        "cite that same candidate on each item so trusted validation can "
                        "reject the overmerge. Use coverage=missing when no candidate "
                        "attempts an outcome, representation_mismatch when a candidate has "
                        "the wrong atomic shape or output mode, and clarification_required "
                        "only for genuine unresolved human meaning. For a responsibility, "
                        "A shared broad mode never merges effects: locomotion, turning, gaze, "
                        "blinking, nodding, gesture, and posture are separate positive body "
                        "outcomes whenever each can be observed completed independently, "
                        "including when one occurs while or during another. "
                        "required_output_mode is the exact provider-neutral WHAT mode, "
                        "never a Capability or lane: singing or a song is singing; ordinary "
                        "conversational wording is speech. Content genre alone never creates "
                        "a performance mode: telling a joke, story, riddle, explanation, or "
                        "answer is speech unless the source explicitly requests singing, "
                        "melody, recitation, or another performance style. A requested musical vocal "
                        "performance is always singing in every language, even when no "
                        "lyrics are supplied and even though its result will eventually be "
                        "audible; it is never ordinary speech or a response-transport "
                        "choice. Locomotion, gaze, blink, gesture, "
                        "and posture are body_action. Assign each mode from that item's "
                        "own cited source span; never swap, rotate, or copy modes between "
                        "adjacent coordinated outcomes. A run/walk span is body_action "
                        "and a sing/song span is singing, including when they overlap in "
                        "time. Grammatical fusion, shared aspect, or a while/during relation "
                        "never makes those separately observable effects one predicate. A "
                        "request to acquire, carry, bring, fetch, retrieve, or hand over a "
                        "physical object is one physical-delivery body_action Responsibility, "
                        "not speech; acquisition, carrying, and handover are stages of that "
                        "one human outcome rather than separate Responsibilities. "
                        "Assign positive source items unique audit_ref values a1, a2, and "
                        "so on in source order. This is audit identity only, never a Goal ID. "
                        "Positive Responsibility source spans must be disjoint: cite only "
                        "the tokens that express that one effect and never include another "
                        "positive item's action tokens. Overlapping positive spans are an "
                        "invalid audit. "
                        "Ordering and concurrency words are material supporting constraints, "
                        "not disposable grammar. Put an ordered relation such as before, "
                        "after, then, next, followed by, or its equivalent in any language in "
                        "supporting_items. Put a simultaneous relation such as while, together, "
                        "simultaneously, at the same time, or its equivalent in any language in "
                        "supporting_items. Set relation_kind=ordered and list its candidate "
                        "responsibility_refs in source order for an ordered relation. Set "
                        "relation_kind=parallel and list the complete concurrent candidate "
                        "set for a simultaneous relation. For either typed relation, also "
                        "list the corresponding positive-item audit_ref values in "
                        "related_audit_refs. A duration, count, direction, distance, "
                        "manner, style, prohibition, or other ordinary constraint uses "
                        "relation_kind=none and cites only the exact positive audit_ref "
                        "values it modifies. Context and framing use "
                        "related_audit_refs=[]. "
                        "Do not type the same set of outcome audit refs as both ordered and "
                        "parallel. When a later effect begins during an ongoing effect, "
                        "parallel owns their overlap; onset wording is a non-relation "
                        "constraint rather than a contradictory ordered relation. "
                        "The relation source span must be cited even when "
                        "the candidate omitted it. A comma, punctuation, a plain conjunction "
                        "such as and/or, or list enumeration alone does not state order or "
                        "concurrency; use relation_kind=none unless the source semantically "
                        "states before/after/then/next or simultaneous overlap. "
                        "Do not plan, select Capabilities, add Goals, or repair candidates. "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "FINAL AUTHORITATIVE USER TURN:\n"
                        f"{request.text}\n\n"
                        "AUTHORITATIVE SOURCE TOKENS (cite refs; surfaces are evidence):\n"
                        f"{_bounded_json(_coverage_source_tokens(request.text), max_chars=5000)}\n\n"
                        "BOUNDED SEMANTIC CONTINUITY CONTEXT (reference resolution only):\n"
                        f"{_bounded_json(semantic_continuity_context, max_chars=4200)}\n\n"
                        "Candidate Responsibility DTOs (claims to audit, not source):\n"
                        f"{_bounded_json(candidates, max_chars=5000)}\n\n"
                        f"{retained_atomic_contract}\n\n"
                        "Final atomicity check: inspect each candidate outcome, its "
                        "bindings, and output_mode for multiple independently observable "
                        "effects. If one candidate combines effects with different WHAT "
                        "modes, emit one responsibility item per effect and cite that same "
                        "candidate ref on each item so the overmerge is rejected. Do not "
                        "call such a multimodal combination one outcome.\n\n"
                        "MODALITY COUNT IS AUTHORITATIVE: count the observable effects "
                        "again immediately before JSON. If one source predicate requests "
                        "both an embodied effect and a vocal performance, emit two positive "
                        "responsibility_items with their own exact modes even when the "
                        "candidate used one outcome, one broad mode, or stored the second "
                        "effect in a binding. The number of responsibility_items must equal "
                        "that final effect count.\n\n"
                        "Cite only coherent positive-outcome and material-constraint spans; "
                        "do not inventory the source-token table. Return the coverage "
                        "certificate."
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            "format": schema,
        }
        reason_summary = payload["format"].get("properties", {}).get(
            "reason_summary"
        )
        if isinstance(reason_summary, dict):
            reason_summary["maxLength"] = 280
            reason_summary["description"] = (
                "One short sentence naming only the coverage decision; do not quote "
                "or translate source text."
            )
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        return payload

    def build_responsibility_coverage_repair_payload(
        self,
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
        *,
        validation_error: Exception,
        authoritative_atomic_certificate: (
            GoalInterpretationCoverageCertificate | None
        ) = None,
    ) -> dict[str, Any]:
        """Regenerate one mechanically invalid audit from source, at most once."""

        payload = self.build_responsibility_coverage_payload(
            request,
            decision,
            authoritative_atomic_certificate=authoritative_atomic_certificate,
        )
        messages = payload.get("messages")
        if isinstance(messages, list) and len(messages) >= 2:
            system = messages[0]
            user = messages[-1]
            if isinstance(system, dict):
                system["content"] = (
                    str(system.get("content") or "")
                    + "\n\nCertificate DTO repair: regenerate the complete audit from "
                    "the authoritative source. Correct only the typed certificate "
                    "structure. Positive spans must be disjoint and numbered in source "
                    "order. The same endpoint set cannot be both ordered and parallel; "
                    "select the one source-grounded completion relation that preserves "
                    "overlap without contradiction. Do not repair or copy candidate "
                    "Responsibility wording. Return JSON only."
                )
            if isinstance(user, dict):
                user["content"] = (
                    str(user.get("content") or "")
                    + "\n\nThe previous certificate was mechanically invalid: "
                    + str(validation_error)[:500]
                    + ". Regenerate one fresh certificate from the source tokens."
                )
        return payload

    @staticmethod
    def _validate_responsibility_coverage_content(
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
        content: str,
    ) -> tuple[GoalInterpretationCoverageCertificate, list[str]]:
        raw = _extract_json_object(content)
        _materialize_coverage_source_excerpts(
            request,
            raw,
            decision=decision,
        )
        certificate = GoalInterpretationCoverageCertificate.model_validate(raw)
        by_ref = {item.local_ref: item for item in decision.responsibilities}
        normalized_turn = " ".join(request.text.strip().split())
        problems: list[str] = []
        independent_owner_counts: dict[str, int] = {}
        positively_owned: set[str] = set()
        audit_items_by_ref: dict[str, Any] = {}
        for index, item in enumerate(certificate.responsibility_items):
            audit_ref = str(item.audit_ref or f"a{index + 1}").strip()
            if not audit_ref or audit_ref in audit_items_by_ref:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage audit_ref values must be unique"
                )
            audit_items_by_ref[audit_ref] = item
        relation_kinds_by_audit_set: dict[frozenset[str], str] = {}
        for relation in certificate.supporting_items:
            if relation.relation_kind == "none":
                continue
            audit_set = frozenset(relation.related_audit_refs)
            prior_kind = relation_kinds_by_audit_set.setdefault(
                audit_set, relation.relation_kind
            )
            if prior_kind != relation.relation_kind:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage cannot type the same outcome set as both "
                    "ordered and parallel"
                )
        for item in certificate.responsibility_items + certificate.supporting_items:
            if item.source_excerpt not in normalized_turn:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage cited text outside the authoritative turn: "
                    f"{item.source_excerpt!r}"
                )
            unknown_refs = set(item.responsibility_refs) - set(by_ref)
            if unknown_refs:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage cited unknown candidate refs: "
                    + ",".join(sorted(unknown_refs))
                )
            punctuation_only = bool(item.source_excerpt) and all(
                char.isspace() or unicodedata.category(char).startswith("P")
                for char in item.source_excerpt
            )
            if (
                item.role in {"responsibility", "constraint"}
                and item.coverage not in {"covered", "clarification_required"}
                and not punctuation_only
            ):
                problems.append(
                    f"{item.coverage}:{item.role}:{item.source_excerpt}"
                )
            if item.role != "responsibility" or item.coverage not in {
                "covered",
                "clarification_required",
            }:
                continue
            if item.independently_satisfiable and len(item.responsibility_refs) != 1:
                problems.append(
                    "independent_responsibility_requires_one_owner:"
                    + item.source_excerpt
                )
            for candidate_ref in item.responsibility_refs:
                positively_owned.add(candidate_ref)
                if item.independently_satisfiable:
                    independent_owner_counts[candidate_ref] = (
                        independent_owner_counts.get(candidate_ref, 0) + 1
                    )
                if (
                    item.required_output_mode != "none"
                    and by_ref[candidate_ref].output_mode
                    != item.required_output_mode
                ):
                    problems.append(
                        "output_mode_mismatch:"
                        f"{candidate_ref}:{item.required_output_mode}:"
                        f"{by_ref[candidate_ref].output_mode}"
                    )
        for item in certificate.supporting_items:
            if item.relation_kind == "none":
                continue
            unknown_audit_refs = set(item.related_audit_refs) - set(
                audit_items_by_ref
            )
            if unknown_audit_refs:
                raise _GoalInterpretationSemanticStructureViolation(
                    "Responsibility coverage relation cited unknown audit refs: "
                    + ",".join(sorted(unknown_audit_refs))
                )
            related_items = [
                audit_items_by_ref[audit_ref]
                for audit_ref in item.related_audit_refs
            ]
            refs = [
                related.responsibility_refs[0]
                for related in related_items
                if len(related.responsibility_refs) == 1
            ]
            if len(item.related_audit_refs) < 2 or len(refs) < 2:
                problems.append(
                    f"{item.relation_kind}_relation_requires_two_candidate_refs:"
                    + item.source_excerpt
                )
                continue
            expected_relation_candidate_refs = list(dict.fromkeys(refs))
            if set(item.responsibility_refs) != set(
                expected_relation_candidate_refs
            ):
                problems.append(
                    "relation_candidate_ownership_mismatch:"
                    + item.source_excerpt
                )
            refs = expected_relation_candidate_refs
            if len(refs) < 2:
                problems.append(
                    f"{item.relation_kind}_relation_collapsed_candidate_owners:"
                    + item.source_excerpt
                )
                continue

            def sibling_refs(candidate_ref: str, relation_name: str) -> set[str]:
                raw_value = by_ref[candidate_ref].bindings.get(relation_name)
                values = raw_value if isinstance(raw_value, list) else [raw_value]
                return {
                    str(value).strip()
                    for value in values
                    if str(value or "").strip() in by_ref
                }

            if item.relation_kind == "ordered":
                for earlier_ref, later_ref in zip(
                    refs, refs[1:], strict=False
                ):
                    if (
                        later_ref
                        not in sibling_refs(earlier_ref, "before")
                        and earlier_ref
                        not in sibling_refs(later_ref, "after")
                    ):
                        problems.append(
                            "ordered_relation_not_preserved:"
                            f"{earlier_ref}:{later_ref}:{item.source_excerpt}"
                        )
            elif item.relation_kind == "parallel":
                for left_index, left_ref in enumerate(refs):
                    for right_ref in refs[left_index + 1 :]:
                        if (
                            right_ref
                            not in sibling_refs(left_ref, "parallel_with")
                            and left_ref
                            not in sibling_refs(right_ref, "parallel_with")
                        ):
                            problems.append(
                                "parallel_relation_not_preserved:"
                                f"{left_ref}:{right_ref}:{item.source_excerpt}"
                            )
        problems.extend(
            f"overmerged_independent_responsibilities:{candidate_ref}"
            for candidate_ref, count in sorted(independent_owner_counts.items())
            if count > 1
        )
        problems.extend(
            f"unjustified_responsibility:{candidate_ref}"
            for candidate_ref in sorted(set(by_ref) - positively_owned)
        )
        return certificate, problems

    async def _ensure_atomic_responsibility_coverage(
        self,
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
        *,
        allow_resegmentation: bool = True,
    ) -> GoalInterpretationDecision:
        if not self._responsibility_coverage_required(request, decision):
            return decision

        problems: list[str]
        coverage_certificate: GoalInterpretationCoverageCertificate | None = None
        try:
            audit = await self._chat_logged(
                self.build_responsibility_coverage_payload(request, decision),
                stage="goal_interpretation_responsibility_coverage",
                request=request,
            )
            coverage_certificate, problems = self._validate_responsibility_coverage_content(
                request,
                decision,
                str(audit.get("message", {}).get("content") or ""),
            )
        except (
            _GoalInterpretationSemanticStructureViolation,
            ValidationError,
        ) as exc:
            try:
                repaired_audit = await self._chat_logged(
                    self.build_responsibility_coverage_repair_payload(
                        request,
                        decision,
                        validation_error=exc,
                    ),
                    stage="goal_interpretation_responsibility_coverage_repair",
                    request=request,
                )
                coverage_certificate, problems = (
                    self._validate_responsibility_coverage_content(
                        request,
                        decision,
                        str(repaired_audit.get("message", {}).get("content") or ""),
                    )
                )
            except (
                httpx.HTTPError,
                ValueError,
                TypeError,
                OllamaGenerationError,
            ) as repair_exc:
                problems = [
                    "coverage_contract_invalid_after_one_dto_repair:"
                    f"{type(repair_exc).__name__}:{repair_exc}"
                ]
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            OllamaGenerationError,
        ) as exc:
            problems = [f"coverage_contract_invalid:{type(exc).__name__}:{exc}"]
        if not problems:
            return decision

        # An exact, binding-free speech echo is audited only because its flat
        # shape can conceal multiple coordinated effects. If the independent
        # source certificate found exactly one Responsibility and the sole
        # disagreement is its output modality, then the audit found no atomic
        # loss. Keep the original conversational DTO instead of letting a second
        # stochastic classifier relabel a simple turn as singing/body action.
        normalized_source = " ".join(request.text.strip().casefold().split())
        single_item = (
            decision.responsibilities[0]
            if len(decision.responsibilities) == 1
            else None
        )
        conversational_envelope_bindings = bool(single_item) and all(
            str(name).strip().casefold()
            in {"input", "message", "text", "user_input", "utterance"}
            and isinstance(value, str)
            and _normalized_turn_echo(value) in normalized_source
            for name, value in (single_item.bindings if single_item else {}).items()
        )
        if (
            single_item is not None
            and single_item.output_mode == "speech"
            and conversational_envelope_bindings
            and (
                " ".join(single_item.outcome.strip().casefold().split())
                == normalized_source
                or bool(single_item.bindings)
            )
            and coverage_certificate is not None
            and len(coverage_certificate.responsibility_items) == 1
            and all(problem.startswith("output_mode_mismatch:") for problem in problems)
        ):
            return decision

        if coverage_certificate is not None:
            projected = _project_audited_contract_onto_covered_candidates(
                decision,
                coverage_certificate,
            )
            if projected is not None:
                _, projected_problems = self._validate_responsibility_coverage_content(
                    request,
                    projected,
                    json.dumps(
                        coverage_certificate.model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                )
                if not projected_problems:
                    return projected

        if not allow_resegmentation:
            raise InterpretationUnavailableError(
                "invalid_goal_interpretation_after_atomic_coverage_audit: "
                + ";".join(problems)
            )

        logger.warning(
            "Goal Interpretation atomic coverage rejected sid=%s problems=%s; "
            "performing one fresh source-based resegmentation",
            request.sid,
            problems,
        )
        if coverage_certificate is None:
            # A malformed auxiliary audit has no authority to trigger a fresh
            # semantic interpretation.  Retrying the source without the typed
            # certificate only moves the failure downstream and reports the
            # misleading "missing certificate" symptom.
            raise InterpretationUnavailableError(
                "invalid_goal_interpretation_after_atomic_coverage_audit: "
                + ";".join(problems)
            )
        try:
            deep = await self._chat_logged(
                self.build_deep_interpretation_payload(
                    request,
                    atomic_coverage_certificate=coverage_certificate,
                    constrain_speed_provenance=True,
                    constrained_binding_names=list(
                        dict.fromkeys(
                            name
                            for responsibility in decision.responsibilities
                            for name in responsibility.bindings
                        )
                    ),
                ),
                stage="goal_interpretation_deep",
                request=request,
            )
            reconsidered = self._validate_interpretation_content(
                request,
                str(deep.get("message", {}).get("content") or ""),
                certificate_owns_coordination=True,
            )
            if coverage_certificate is not None:
                reconsidered = _project_audited_atomic_contract(
                    reconsidered,
                    coverage_certificate,
                )
            # The independent certificate is the semantic authority that caused
            # resegmentation.  Validate the projected result against that same
            # certificate; asking a second model audit here allowed a fresh,
            # contradictory classification to overrule the established owner.
            # ``source_excerpt`` is already trusted/materialized, so this pass is
            # deterministic contract validation rather than new interpretation.
            projected_certificate = coverage_certificate.model_dump(mode="json")
            for item in projected_certificate["responsibility_items"]:
                # ``coverage`` describes the rejected pre-resegmentation
                # candidate set. The fresh decoder is schema-bound to emit one
                # candidate per retained audit ref, and the projection above
                # fixes that candidate's mode and typed relations. Keeping the
                # old ``missing`` value while assigning its new owner creates a
                # self-contradictory DTO, so record the mechanically established
                # ownership before final validation.
                item["coverage"] = "covered"
                item["responsibility_refs"] = [item["audit_ref"]]
            for item in projected_certificate["supporting_items"]:
                # The source audit also owns constraint attachment.  Its DTO now
                # requires every uncovered constraint to cite the positive audit
                # owner(s), while the fresh decoder is constrained to use those
                # audit refs and receives the same modifier/relationship contract.
                # Record the resulting ownership without interpreting source text.
                item["coverage"] = "covered"
                item["responsibility_refs"] = list(
                    item.get("related_audit_refs") or []
                )
            _, final_problems = self._validate_responsibility_coverage_content(
                request,
                reconsidered,
                json.dumps(projected_certificate),
            )
            if final_problems:
                raise _GoalInterpretationSemanticStructureViolation(
                    "fresh Goal Interpretation failed final atomic coverage: "
                    + ";".join(final_problems)
                )
            return reconsidered
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            OllamaGenerationError,
        ) as exc:
            raise InterpretationUnavailableError(
                "invalid_goal_interpretation_after_atomic_coverage_resegmentation: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

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
        *,
        certificate_owns_coordination: bool = False,
    ) -> GoalInterpretationDecision:
        parsed = _extract_json_object(content)
        _normalize_mechanical_goal_interpretation_dto(parsed)
        _strip_bound_values_from_unresolved(parsed)
        _reject_planner_shaped_goal_interpretation(parsed)
        _reject_canonical_goal_identity_refs(request, parsed)
        _reject_unknown_goal_refs(request, parsed)
        _reject_continuity_completion_contract_mismatch(request, parsed)
        _reject_unprovenanced_location_bindings(request, parsed)
        _reject_unprovenanced_speed_bindings(request, parsed)
        _reject_runtime_identity_bindings(request, parsed)
        _strip_language_envelope_bindings(request, parsed)
        _strip_redundant_conversational_turn_echo_bindings(request, parsed)
        _strip_redundant_outcome_echo_bindings(parsed)
        _normalize_corrupted_count_binding_names(parsed)
        _reject_malformed_binding_names(parsed)
        _reject_transport_echo_bindings(request, parsed)
        if certificate_owns_coordination:
            _strip_certificate_owned_coordination_bindings(parsed)
        _reject_untyped_coordination_bindings(parsed)
        _reject_dropped_explicit_numeric_bindings(request, parsed)
        _reject_noncanonical_count_bindings(parsed)
        return GoalInterpretationDecision.model_validate(parsed)

    async def _accept_or_deepen_interpretation(
        self,
        request: GoalInterpretationRequest,
        decision: GoalInterpretationDecision,
        *,
        allow_coverage_resegmentation: bool = True,
    ) -> GoalInterpretationDecision:
        if not self._requires_deep_semantic_interpretation(decision):
            return await self._ensure_atomic_responsibility_coverage(
                request,
                decision,
                allow_resegmentation=allow_coverage_resegmentation,
            )
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
            return await self._ensure_atomic_responsibility_coverage(
                request,
                decision,
                allow_resegmentation=False,
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
            if "coordination bindings must contain only exact sibling" in str(exc):
                # The invalid relation field itself carries no trustworthy
                # semantic authority. Strip it and send the remaining candidate
                # directly to the independent atomic audit, which is the owner
                # that can count source effects and trigger one resegmentation.
                # This avoids spending the single deep delegation on a model
                # regeneration that can repeat the same malformed relation.
                try:
                    decision = self._validate_interpretation_content(
                        request,
                        content,
                        certificate_owns_coordination=True,
                    )
                    return await self._ensure_atomic_responsibility_coverage(
                        request,
                        decision,
                        allow_resegmentation=True,
                    )
                except Exception as audit_exc:
                    raise InterpretationUnavailableError(
                        "invalid_goal_interpretation_after_coordination_audit: "
                        f"{type(audit_exc).__name__}: {audit_exc}"
                    ) from audit_exc
            try:
                deep = await self._chat_logged(
                    self.build_deep_interpretation_payload(
                        request,
                        constrain_speed_provenance=True,
                        constrained_binding_names=_goal_interpretation_binding_names(
                            _extract_json_object(content)
                        ),
                        source_structure_violation=str(exc),
                    ),
                    stage="goal_interpretation_deep",
                    request=request,
                )
                decision = self._validate_interpretation_content(
                    request,
                    str(deep.get("message", {}).get("content") or ""),
                )
                return await self._ensure_atomic_responsibility_coverage(
                    request,
                    decision,
                    allow_resegmentation=False,
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
                return await self._accept_or_deepen_interpretation(
                    request,
                    decision,
                    allow_coverage_resegmentation=False,
                )
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
