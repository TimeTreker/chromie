from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from .goal_progress_communication import goal_progress_communication_prompt
from .clients.ollama_client import LayeredPrompt
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    owner_approved_identity_context,
)
from .goal_association_contract import (
    _EXECUTION_CONTRACT_PROMPT,
    _GOAL_SEGMENTATION_IDENTITY_CONTRACT,
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
)
from .prompt_projection import bounded_json, required_json

try:
    from chromie_contracts.memory import role_memory_context
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.memory import role_memory_context


try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
    from chromie_contracts.discourse import DiscourseReferent
    from chromie_contracts.situation import SituationProjection
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.discourse import DiscourseReferent
    from shared.chromie_contracts.situation import SituationProjection


logger = logging.getLogger("chromie.agent.goal_association.prompt")


# Goal Association prompt projection only. This module does not invoke a model,
# mutate canonical Goal state, or commit continuity decisions.


def immutable_source_turn_prompt(request: CognitiveWorkRequest) -> str:
    """Expose exact source evidence while keeping GI/GA authority explicit."""

    source = request.source_turn_provenance
    projection = json.dumps(
        {
            "original_text": source["original_text"],
            "authority": source["authority"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "IMMUTABLE SOURCE TURN JSON (read-only; GI Responsibilities own "
        "current-turn WHAT; GA owns continuity, never silent semantic repair):\n"
        f"{projection}"
    )

def discourse_referents(request: CognitiveWorkRequest) -> list[dict[str, Any]]:
    context = request.context if isinstance(request.context, dict) else {}
    raw = context.get("discourse_referents")
    if not isinstance(raw, list):
        raw = []
    out: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:24]):
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                DiscourseReferent.model_validate(item).model_dump(
                    mode="json",
                    exclude_none=True,
                )
            )
        except ValidationError as exc:
            logger.debug(
                "Ignoring malformed discourse referent index=%s error=%s",
                index,
                exc,
            )
            continue
    return out


def situation_projection(request: CognitiveWorkRequest) -> dict[str, Any]:
    context = request.context if isinstance(request.context, dict) else {}
    raw = context.get("situation")
    if not isinstance(raw, dict):
        return {}
    try:
        return SituationProjection.model_validate(raw).prompt_projection()
    except ValidationError as exc:
        logger.debug("Ignoring malformed Situation projection error=%s", exc)
        return {}


def build_segmentation_prompt(
    request: CognitiveWorkRequest,
) -> str:
    """Render the complete no-candidate Goal contract without continuity prose.

    The former shared prompt repeated association, planning, resource, and
    coverage rules even when no Goal existed to associate.  Besides making the
    semantic boundary harder to review, that forced qualified small models into
    a much larger context allocation.  This prompt keeps the same authorities
    and failure semantics while stating each no-candidate rule once.
    """

    context = request.context if isinstance(request.context, dict) else {}
    identity_json = goal_segmentation_identity_json(context)
    identity_contract = (
        _GOAL_SEGMENTATION_IDENTITY_CONTRACT
        if identity_json != "null"
        else ""
    )
    responsibilities_json = required_json(
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in request.responsibilities
        ],
        16000,
        label="GI Responsibility evidence",
    )
    return (
        "There are no active or retained recent Goals. Association is impossible; "
        "create new Goals only. Goal Association receives provider-neutral "
        "Responsibility evidence, not a route, Capability, plan, or response draft. "
        "The authoritative user turn and the supplied GI Responsibilities are the "
        "only sources of owed human outcomes. Fast Planner Activity is HOW authored "
        "concurrently and must never become, justify, or be copied into a Goal. "
        "Responsibility conservation is strict: create exactly one Goal for each "
        "independently satisfiable Responsibility, copy its local_ref into "
        "source_responsibility_refs, and neither merge independent effects nor add "
        "acknowledgement, progress, delivery, personality, or implementation Goals. "
        "A manner, prohibition, timing, or social-presentation modifier stays on the "
        "outcome it constrains. A greeting attached to substantive work is framing; "
        "a standalone social act is one speech Goal. "
        "Information acquisition and a requested interpretation of that same evidence "
        "are one Goal. Acquisition, carrying, return, "
        "and handoff are stages of one requested physical delivery, not sibling Goals.\n\n"
        "Preserve the supplied Responsibility WHAT output_mode exactly in the canonical Goal. "
        "information keeps one information resource_responsibility when grounded "
        "information acquisition is the human outcome; stateful_effect keeps ordinary "
        "typed bindings and no information resource. This semantic preservation never "
        "selects a Capability, provider, executable operation, or Plan. Preserve every supplied material "
        "binding verbatim, including counts, durations, speeds, directions, targets, "
        "severity, thresholds, negation, comparison, and scope. For a non-resource "
        "Goal, put these in top-level typed bindings; the action remains in GI outcome. "
        "Do not emit a Goal description: Host inherits it and success_criteria from GI. "
        "Do not claim completion or choose a Capability. "
        f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
        "Use resource_responsibility only when obtaining and making a resource "
        "available to a recipient is the human outcome. A physical_object is a "
        "distinct concrete object independent of Chromie's body and requires "
        "acquisition plus physical_handover. Locomotion, gaze, blinking, gesture, "
        "turning, posture, and other self-motion are non-resource body_action Goals; "
        "never describe Chromie's body, position, displacement, or motion as an "
        "object to acquire or hand over. A physical resource keeps top-level bindings "
        "empty; its identity/quantity belong to description/quantity and its supplied "
        "location, distance, direction, and route belong in source.acquisition_bindings. "
        "Preserve separately supplied GI bindings separately, but never decompose one "
        "GI-owned composite binding: retain its complete source value in one typed "
        "acquisition binding. Supplied spatial grounding requires "
        "source.status=known; source.status=unknown is allowed only when none was "
        "supplied.\n\n"
        "An information resource uses output_mode=information and one exact "
        "information_domain: local_clock, weather_forecast, "
        "external_grounded_information, direct_environment_perception, or "
        "private_runtime_information. Its query_scope is the sole owner of location, "
        "time, aspects, comparisons, and thresholds: a resolved place is a "
        "query_scope binding named location, with time and requested result aspects "
        "as separate bindings. Current nearby people/objects/events require "
        "direct_environment_perception, not weather. A public source uses "
        "source.status=provider_resolved; source.status=unknown preserves an "
        "unavailable local/private/runtime source; source.status=known is only for an "
        "explicitly named source. Never invent location, timezone, source, provider, "
        "device, coordinates, or another query fact. Preserve source-grounded "
        "temporal wording as human semantic scope in query_scope. A compound natural "
        "expression stays intact instead of being decomposed into Capability date, period, "
        "or clock-range arguments. A duration remains duration. Never narrow broader "
        "temporal scope.\n\n"
        "Resolve a pronoun, demonstrative, ellipsis, correction, or task mention only "
        "from explicit current meaning, a supplied scoped discourse referent, a "
        "candidate binding, or accepted dialogue, in that order. There are no "
        "candidate Goals in this request. If evidence does not select one meaning, "
        "keep the narrowest source-grounded provisional Goal and do not invent the "
        "referent; Fast Planner owns any clarification. resolved_references may copy "
        "only a supplied referent_id. Ordinary explicit mentions are bindings, not "
        "resolved references. referent_updates require supplied provenance; never "
        "invent IDs. Tool results and runtime diagnostics are not semantic authority.\n\n"
        f"{identity_contract}"
        "The Host owns IDs, versions, lifecycle, source text, persistence, plans, and "
        "canonical construction. Emit none of those fields. Return only the exact "
        "GoalSegmentationModelOutput JSON Schema: decision=create_goals, new_goals, "
        "referent_updates, resolved_references, confidence, and compact reason_summary. "
        "Goal Association never executes, commits, asks a question, creates a planning "
        "InformationGap, or pretends work is complete.\n\n"
        "Owner-approved Chromie identity JSON:\n"
        f"{identity_json}\n\n"
        + "Responsibility evidence JSON:\n"
        f"{responsibilities_json}\n\n"
        "GI unresolved-meaning evidence JSON:\n"
        f"{bounded_json(request.interpretation_unresolved, 1600)}\n\n"
        "Scoped discourse referents JSON:\n"
        f"{bounded_json(discourse_referents(request), 3000)}\n\n"
        "Recent accepted conversation JSON (reference evidence only):\n"
        f"{bounded_json((context.get('history') or request.history or [])[-6:], 2600)}\n\n"
        f"Language hint: {request.language or 'auto'}\n"
        f"{immutable_source_turn_prompt(request)}"
    )


def goal_segmentation_identity_json(context: dict[str, Any]) -> str:
    """Project identity facts Goal semantics can own, excluding voice style."""

    source = owner_approved_identity_context(context)
    identity = source.get("identity")
    if not isinstance(identity, dict):
        return "null"
    compact_identity = {
        key: identity[key]
        for key in (
            "entity_id",
            "name",
            "kind",
            "gender",
            "pronouns",
            "age_description",
            "family_role",
            "family_context_boundary",
        )
        if key in identity and identity[key] not in (None, "", [], {})
    }
    payload: dict[str, Any] = {
        "owner_approved": True,
        "identity": compact_identity,
    }
    self_model = source.get("self_model")
    if isinstance(self_model, dict):
        compact_self_model = {
            key: self_model[key]
            for key in (
                "perceiving_entity_id",
                "acting_entity_id",
                "body_owner_entity_id",
            )
            if key in self_model and self_model[key] not in (None, "")
        }
        if compact_self_model:
            payload["self_model"] = compact_self_model
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def association_goal_projection(
    candidate_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only semantic continuity evidence owned by Goal Association."""

    projected: list[dict[str, Any]] = []
    for snapshot in candidate_goals:
        if not isinstance(snapshot, dict):
            continue
        goal = snapshot.get("goal")
        goal = goal if isinstance(goal, dict) else {}
        metadata = goal.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        item = {
            "goal_id": snapshot.get("goal_id") or goal.get("goal_id"),
            "responsibility_status": (
                snapshot.get("responsibility_status")
                or goal.get("responsibility_status")
            ),
            "work_status": snapshot.get("work_status"),
            "description": goal.get("description"),
            "goal_version": goal.get("version"),
            "success_criteria": goal.get("success_criteria") or [goal.get("description")],
            "constraints": goal.get("constraints"),
            "resource_responsibility": goal.get("resource_responsibility"),
            "requirement_sources": metadata.get("requirement_sources"),
            "source_text": goal.get("source_text"),
            "object": goal.get("object"),
            "output_mode": metadata.get("output_mode"),
            "open_information_gaps": snapshot.get(
                "open_information_gaps", []
            ),
            "last_user_update": snapshot.get("last_user_update"),
        }
        # Requirements already carry the complete WHAT; remove only exact
        # duplicate text, never truncate the version-addressed selection surface.
        if item["success_criteria"] == [item["description"]]:
            item.pop("description")
        for field in ("source_text", "last_user_update"):
            if item.get(field) == goal.get("description"):
                item.pop(field, None)
        projected.append(
            {
                key: value
                for key, value in item.items()
                if value not in (None, "", [], {})
            }
        )
    return projected


def association_dialogue_projection(history: Any) -> list[dict[str, Any]]:
    """Remove runtime envelopes while retaining accepted dialogue meaning."""

    if not isinstance(history, list):
        return []
    projected: list[dict[str, Any]] = []
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = " ".join(str(item.get("text") or "").strip().split())
        if role not in {"user", "assistant"} or not text:
            continue
        compact: dict[str, Any] = {"role": role, "text": text[:320]}
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            semantic_status = str(
                metadata.get("semantic_status") or ""
            ).strip()
            if semantic_status:
                compact["semantic_status"] = semantic_status
        projected.append(compact)
    return projected


def build_association_prompt(
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
) -> str:
    """Render existing-Goal continuity without unrelated planning prose."""

    context = request.context if isinstance(request.context, dict) else {}
    identity_json = goal_segmentation_identity_json(context)
    identity_section = (
        "Owner-approved Chromie identity JSON:\n"
        f"{identity_json}\n\n"
    )
    identity_contract = (
        _GOAL_SEGMENTATION_IDENTITY_CONTRACT
        if identity_json != "null"
        else ""
    )
    responsibilities = [
        item.model_dump(mode="json", exclude_none=True)
        for item in request.responsibilities
    ]
    history = context.get("history") or request.history or []
    return (
        "Resolve canonical Goal continuity from the authoritative user turn, GI "
        "Responsibilities, bounded candidate Goals, scoped referents, and accepted "
        "dialogue. This boundary owns Goal association/creation only: never choose "
        "a Capability, Plan, execution method, response wording, clarification "
        "policy, or completion claim. The Host owns IDs, versions, persistence, "
        "lifecycle mechanics, and canonical construction.\n\n"
        "Resolve each GI Responsibility independently in this order, then verify that "
        "every GI Responsibility ref must map to exactly one association or new Goal: (1) when "
        "both the source directly says a specific candidate must stop and it presents the "
        "new outcome as that candidate's substitute, while GI supplies relationship=new "
        "with no target_goal_ids, emit a replacement new_goal with only that candidate in "
        "supersedes_goal_ids; if either replacement condition is missing, row (1) is "
        "forbidden. (2) For a supplied non-new relationship "
        "with target_goal_ids, emit an association with that exact relationship and those "
        "targets when source and candidate evidence confirm it; (3) for relationship=new "
        "with no target_goal_ids and without both replacement conditions, emit the default "
        "independent new_goal "
        "with empty supersedes_goal_ids and related_goal_ids. Candidate presence, topic "
        "overlap, recency, or having only one candidate is never enough to turn row (3) "
        "into an association. Never invert source polarity: an instruction to keep, retain, "
        "preserve, or continue the old Goal, or its equivalent in any language, means that "
        "Goal must not stop. The invariant is retain_old=true implies "
        "supersedes_goal_ids=[]; superseding requires retain_old=false. These collections "
        "are not mutually exclusive: a turn that "
        "continues retained work and adds an independent Responsibility must emit both in "
        "one complete result, preserving each Responsibility's own local_ref; never reuse "
        "one ref for another. Verify GI relationship and target_goal_ids against the "
        "authoritative source and supplied candidates. Never merge independent effects or "
        "add progress, acknowledgement, delivery, personality, or implementation Goals. "
        "For unchanged unfinished/recoverable work use continue. "
        "Use resume only for paused work. Use reference for retrieval, restatement, "
        "explanation, comparison, or another answer from retained Goal meaning "
        "without lifecycle change. A new reaction, feeling, evaluation, practical "
        "decision, or independently satisfiable conversation is a new speech Goal. "
        "Use clarify only when this turn supplies missing Goal meaning; confirm and "
        "reject apply only to a pending proposal. Copy relationship exactly from "
        "continue, modify, clarify, confirm, reject, cancel, pause, resume, merge, "
        "split, or reference. Target only supplied Goal IDs. A modify association "
        "must supply requirement_changes with target_goal_id, zero-based "
        "replace_requirement_indices into supplied success_criteria, and current "
        "source_responsibility_refs. Empty indices add; unselected requirements remain. "
        "Replace only requirements completely restated by current GI; never substitute "
        "a partial fragment for a long Goal. Host copies outcomes and derives description/criteria. "
        "clarify supplies changes or resolved_gap_ids. binding_changes copy one exact GI "
        "source_binding/source_responsibility_ref to a named path under object, constraints "
        "or resource_responsibility; unselected fields remain. Keep those fields consistent "
        "with GI. Never author updated_description or success_criteria. Rationale "
        "does not mutate Goal meaning. Association confidence measures certainty "
        "about Goal ownership and the continuity relationship, not whether linked "
        "Planner input gaps are resolved or the Goal is executable. Keep "
        "resolved_gap_ids empty when resolution is unproven, but do not lower an "
        "otherwise explicit targeted association's confidence for that reason.\n\n"
        "An association preserves unselected Goal requirements, provenance and resource "
        "fields. Source-bound requirement_changes may refine the retained Responsibility; "
        "GA does not decide whether its Work must be reused or cancelled. "
        "Explicit lifecycle replacement or abandonment remains replacement even when the "
        "new outcome's WHAT, modality, or entity is wholly different. Apply replacement "
        "only to that explicit same-Responsibility case; a separate new Responsibility is "
        "independent. Source evidence that the retained Goal must remain while the new "
        "outcome is additional or separate is decisive coexistence evidence and forbids "
        "replacement: keep "
        "supersedes_goal_ids empty and leave the retained Goal untouched. Put an ID in "
        "supersedes_goal_ids only when direct source evidence commands that Goal to stop, "
        "be abandoned, or be replaced; a different entity or output_mode alone is not "
        "replacement. Replacement never overrides a supplied association relationship or "
        "its target_goal_ids. In particular, merge and split remain associations rather "
        "than replacement Goals. A superseded ID belongs only in supersedes_goal_ids and must "
        "never also appear in related_goal_ids; related_goal_ids retains only "
        "non-replacement context. If current meaning is genuinely independent, create "
        "a new Goal without reopening the old one. A recent "
        "terminal Goal may be referenced but not reopened. Preserve unresolved human "
        "meaning in the narrowest provisional Goal; Fast Planner alone decides any "
        "question.\n\n"
        "For a new Goal, emit its source_responsibility_refs, never a description. Host "
        "inherits the exact GI outcome and successful-outcome requirements. Preserve every material binding exactly and preserve the GI "
        "WHAT modality exactly: information keeps one information resource_responsibility "
        "when the outcome is grounded information acquisition; stateful_effect keeps "
        "ordinary typed bindings and no information resource; every other explicit "
        "output_mode is copied exactly. "
        "Use resource_responsibility only when the owed outcome is to acquire and "
        "make a resource available. A physical_object is a concrete object independent "
        "of Chromie's body and uses physical_handover; locomotion, gaze, blinking, "
        "gesture, and posture are non-resource body_action. An information resource "
        "uses information and keeps location, time, aspects, comparisons, and "
        "thresholds in query_scope. Never invent a source, location, provider, device, "
        "timezone, or execution fact. Directly named entities preserve the exact "
        "current-turn surface. resolved_references and referent_updates may copy only "
        "supplied referent IDs.\n\n"
        "Return only the exact GoalAssociationModelOutput JSON. Emit associations and "
        "new_goals as the sole authoritative per-Responsibility continuity result, then "
        "referent_updates, resolved_references, confidence, and a compact "
        "non-authoritative reason_summary describing the emitted result. Do not emit a "
        "branch decision.\n\n"
        f"{identity_section}"
        f"{identity_contract}"
        f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
        "Candidate Goal semantic evidence JSON:\n"
        f"{required_json(association_goal_projection(candidate_goals), 2600, label='Goal requirement evidence')}\n\n"
        "GI Responsibility evidence JSON:\n"
        f"{required_json(responsibilities, 16000, label='GI Responsibility evidence')}\n\n"
        "GI unresolved-meaning evidence JSON:\n"
        f"{bounded_json(request.interpretation_unresolved, 800)}\n\n"
        "Goal interaction evidence JSON:\n"
        f"{bounded_json(context.get('interaction_context') or {}, 900)}\n\n"
        "Scoped discourse referents JSON:\n"
        f"{bounded_json(discourse_referents(request), 1400)}\n\n"
        "Accepted dialogue JSON:\n"
        f"{bounded_json(association_dialogue_projection(history), 1400)}\n\n"
        f"Language hint: {request.language or 'auto'}\n"
        f"{immutable_source_turn_prompt(request)}\n\n"
        "FINAL CANDIDATE GOAL IDS JSON:\n"
        f"{bounded_json([item.get('goal_id') for item in candidate_goals], 900)}"
    )


def build_prompt(
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
    *,
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
) -> str:
    if output_type is GoalSegmentationModelOutput:
        return build_segmentation_prompt(request)
    return build_association_prompt(request, candidate_goals)


def build_repair_prompt(
    *,
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
    turn_id: str,
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    raw: dict[str, Any],
    validation_error: str,
) -> str:
    """Render the one mechanical DTO repair without reopening semantics."""

    del request, candidate_goals, turn_id
    contract_name = (
        "GoalSegmentationModelOutput"
        if output_type is GoalSegmentationModelOutput
        else "GoalAssociationModelOutput"
    )
    semantic_fields = (
        "decision, new Goal ownership"
        if output_type is GoalSegmentationModelOutput
        else "association and new Goal ownership"
    )
    return (
        f"The previous {contract_name} JSON object is mechanically malformed. "
        "This is the only same-stage DTO repair. Preserve every semantic claim "
        f"already present in the previous object: {semantic_fields}, relationship, Goal "
        "ownership, source Responsibility refs, target Goal IDs, descriptions, "
        "output modes, bindings and values, resource meaning, referent choices, "
        "confidence, and rationale. Do not re-read or reinterpret the user, "
        "re-segment Responsibilities, add or remove a Goal, choose a different "
        "continuity relation, or repair a grounding/conservation judgment. Make only "
        "mechanical JSON-contract corrections identified by the validation errors, "
        "such as removing an extra key, restoring a required empty container, or "
        "correcting an object/array/scalar shape without changing its value. If the "
        "object cannot satisfy the schema without changing semantics, do not invent "
        "replacement meaning; trusted validation will fail closed. Return exactly "
        "one JSON object and no commentary.\n\n"
        "Previous model output JSON:\n"
        f"{bounded_json(raw, 7000)}\n\n"
        "Exact mechanical validation errors JSON:\n"
        f"{validation_error}"
    )


def layered_prompt(
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
    *,
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    identity_json = goal_segmentation_identity_json(context)
    identity_world = (
        "Owner-approved Chromie identity JSON:\n"
        f"{identity_json}\n\n"
    )
    identity_contracts = (
        (_GOAL_SEGMENTATION_IDENTITY_CONTRACT,)
        if identity_json != "null"
        else ()
    )
    rendered = role_memory_context(context, role="ga") + build_prompt(
        request,
        candidate_goals,
        output_type=output_type,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            *identity_contracts,
            _EXECUTION_CONTRACT_PROMPT,
        ),
    )


def layered_repair_prompt(
    *,
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
    turn_id: str,
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    raw: dict[str, Any],
    validation_error: str,
) -> LayeredPrompt:
    rendered = build_repair_prompt(
        request=request,
        candidate_goals=candidate_goals,
        turn_id=turn_id,
        output_type=output_type,
        raw=raw,
        validation_error=validation_error,
    )
    return LayeredPrompt.promote(rendered)


def repair_system_prompt(
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
) -> str:
    contract_name = (
        "Goal Segmentation"
        if output_type is GoalSegmentationModelOutput
        else "Goal Association"
    )
    return (
        f"You perform one mechanical JSON repair for {contract_name}. Preserve "
        "all authored semantics exactly; never reinterpret, resegment, review, "
        "score, or replace the semantic result. Return only the corrected JSON object."
    )


def system_prompt(
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
) -> str:
    if output_type is GoalSegmentationModelOutput:
        return (
            "You are Chromie's Goal Segmentation model. No active or retained recent Goal IDs exist, so association with existing work is impossible. "
            "Use semantic reasoning to resolve current-turn references from scoped discourse context and preserve independently satisfiable user responsibilities as separate new Goals, but never turn plan steps into goals. "
            "Conversational framing attached to a substantive responsibility is not independently satisfiable work: do not create a separate Goal for its greeting or politeness preamble. A standalone social interaction remains one conversational Goal. "
            "When one evidence acquisition satisfies both a factual lookup and the requested interpretation of its result, preserve them as one Goal. "
            "Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
            "You are advisory only and never execute or commit. Return JSON only."
        )
    return (
        "You are Chromie's Goal Association and Segmentation model. Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
        "Produce one complete candidate-aware result; existing-Goal associations and independent new Goals may coexist in that result. "
        "Apply continuity before creation. Resolve references from current user meaning, scoped discourse referents/focus, bounded candidate Goals and their bindings, and dialogue context. Candidate Goals may be active, recoverable, or recently terminal; referencing a terminal Goal does not reopen it. Tool-result memory is not reference-resolution authority. Status follow-ups about an unfinished lookup should associate with the bound task; if its safe read is recoverable, preserve the exact skill arguments for retry. Do not treat another task's evidence as completion. "
        "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
        "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
        "Conversational framing attached to substantive work is not a separate Goal; a standalone social interaction remains one conversational Goal. A new reaction, feeling, evaluation, acknowledgement, or practical decision after a prior result is a current conversational responsibility, not continuation of the completed lookup. One lookup and an interpretation requested as part of that same lookup are one Goal. "
        "You are advisory only and never execute or commit. Return JSON only."
    )
