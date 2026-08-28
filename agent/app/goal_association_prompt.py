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
from .prompt_projection import bounded_json

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
    responsibilities_json = bounded_json(
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in request.responsibilities
        ],
        4200,
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
        "a standalone social act is one speech Goal. One lookup and the requested "
        "judgment of that same evidence are one Goal. Acquisition, carrying, return, "
        "and handoff are stages of one requested physical delivery, not sibling Goals.\n\n"
        "Preserve the supplied Responsibility WHAT output_mode exactly in the canonical Goal. "
        "information keeps one information resource_responsibility when grounded "
        "information acquisition is the human outcome; stateful_effect keeps ordinary "
        "typed bindings and no information resource. This semantic preservation never "
        "selects a Capability, provider, executable operation, or Plan. Preserve every supplied material "
        "binding verbatim, including counts, durations, speeds, directions, targets, "
        "severity, thresholds, negation, comparison, and scope. For a non-resource "
        "Goal, put these in top-level typed bindings; the action itself may remain in "
        "description. Do not claim completion or choose a Capability. "
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
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
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
            "source_text": goal.get("source_text"),
            "bindings": (goal.get("object") or {}).get("bindings", {}),
            "output_mode": metadata.get("output_mode"),
            "open_information_gaps": snapshot.get(
                "open_information_gaps", []
            ),
            "last_user_update": snapshot.get("last_user_update"),
        }
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
        "Map every GI local_ref exactly once to either one association or one new "
        "Goal; never merge independent effects or add progress, acknowledgement, "
        "delivery, personality, or implementation Goals. Verify GI relationship "
        "and target_goal_ids against the supplied candidates rather than recency or "
        "lexical overlap. For unchanged unfinished/recoverable work use continue. "
        "Use resume only for paused work. Use reference for retrieval, restatement, "
        "explanation, comparison, or another answer from retained Goal meaning "
        "without lifecycle change. A new reaction, feeling, evaluation, practical "
        "decision, or independently satisfiable conversation is a new speech Goal. "
        "Use clarify only when this turn supplies missing Goal meaning; confirm and "
        "reject apply only to a pending proposal. Copy relationship exactly from "
        "continue, modify, clarify, confirm, reject, cancel, pause, resume, merge, "
        "split, or reference. Target only supplied Goal IDs.\n\n"
        "An association preserves the existing Goal's description, typed bindings, "
        "and output_mode. It cannot rewrite a material entity "
        "or parameter. If current meaning changes one, create one complete replacement "
        "Goal and put the old ID in supersedes_goal_ids. If current meaning is "
        "independent, create a new Goal without reopening the old one. A recent "
        "terminal Goal may be referenced but not reopened. Preserve unresolved human "
        "meaning in the narrowest provisional Goal; Fast Planner alone decides any "
        "question.\n\n"
        "For a new Goal, preserve every material binding exactly and preserve the GI "
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
        "Return only the exact GoalAssociationModelOutput JSON: decision, "
        "associations, new_goals, referent_updates, resolved_references, confidence, "
        "and compact reason_summary. Use decision=associate for continuity and "
        "decision=create_goals for independent or replacement work.\n\n"
        f"{identity_section}"
        f"{identity_contract}"
        f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
        "Candidate Goal semantic evidence JSON:\n"
        f"{bounded_json(association_goal_projection(candidate_goals), 2600)}\n\n"
        "GI Responsibility evidence JSON:\n"
        f"{bounded_json(responsibilities, 2600)}\n\n"
        "GI unresolved-meaning evidence JSON:\n"
        f"{bounded_json(request.interpretation_unresolved, 800)}\n\n"
        "Goal interaction evidence JSON:\n"
        f"{bounded_json(context.get('interaction_context') or {}, 900)}\n\n"
        "Scoped discourse referents JSON:\n"
        f"{bounded_json(discourse_referents(request), 1400)}\n\n"
        "Accepted dialogue JSON:\n"
        f"{bounded_json(association_dialogue_projection(history), 1400)}\n\n"
        f"Language hint: {request.language or 'auto'}\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
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

    # The remaining source below is retained temporarily while the compact
    # existing-Goal prompt is validated against the canonical behavior suite.
    context = request.context if isinstance(request.context, dict) else {}
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    if output_type is GoalSegmentationModelOutput:
        state_instructions = (
            "There are no active or retained recent Goals, so no existing-goal relationship is possible and the contract intentionally has no associations field. "
            "Segment the authoritative user turn into independent new Goals. When GI preserves unresolved material meaning, create the narrowest source-grounded provisional Goal without inventing the missing referent or scope; Fast Planner owns any clarification decision. "
        )
        output_instructions = (
            "Return only JSON with decision, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
            "Use decision=create_goals and preserve each source-grounded Responsibility, including a provisional Goal whose exact referent or scope remains unresolved. Do not author a question or decide input-resolution policy. "
            "The decoder enforces the exact GoalSegmentationModelOutput JSON Schema. "
        )
    else:
        state_instructions = (
            "Resolve continuity before creation using semantic reasoning. "
            "For continuity with an existing goal, emit an associations item with source_responsibility_refs, relationship, target_goal_ids, confidence, reason_summary, the applicable updated_description, and resolved_gap_ids fields. Goal Association owns canonical Goal continuity only: do not decide whether Work must be reused, replaced, cancelled, or replanned; Fast Planner owns that judgment from the committed Goal and actual Work state. "
            "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"merge\",\"split\",\"reference\"]. "
            "Use continue only when the current turn advances unchanged unfinished active or recoverable work. Use reference when the current turn asks to retrieve, restate, explain, compare, verify, or otherwise answer from a retained Goal without changing its meaning or lifecycle. Do not use continue or reference merely because the topic overlaps with a previous Goal. When the latest turn is a social reaction, acknowledgement, personal feeling, practical decision, conversational evaluation, empathy-seeking comment, or another independently satisfiable communicative act, create a fresh vocal_output Goal that captures that latest intent; prior delivered information remains context for that answer. Use modify only when the same Responsibility is being refined and include updated_description or resolved_gap_ids. When the user abandons that Responsibility for a genuinely different outcome, return decision=create_goals with a new Goal whose supersedes_goal_ids names the old Goal; never mutate the old Goal through an association. The association relationship clarify means the current user turn supplies missing information for a Goal and must include updated_description or resolved_gap_ids; it never means that the user is asking Chromie for more explanation. When GI preserves unresolved material meaning, create or associate the narrowest source-grounded provisional Goal without inventing that meaning; Fast Planner alone decides whether and how to ask. "
            "Use confirm only when the current turn approves a pending proposal for the targeted Goal, and use reject only when it declines that proposal. "
            "Associations may target only IDs from the bounded candidate-goal list. A recent terminal Goal may be referenced without reopening or changing its terminal lifecycle state. "
            "An association cannot rewrite an existing Goal's typed material bindings. When your semantic judgment is that the current user meaning changes a material entity or parameter, preserve the old Goal and return decision=create_goals with a complete replacement Goal and authoritative bindings. "
        )
        output_instructions = (
            "Return only JSON with decision, associations, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
            "Use decision=associate for continuity or decision=create_goals for independent work, including provisional source-grounded Goals with unresolved meaning retained outside this DTO for Planner. New Goals may copy related_goal_ids from the bounded active Goal list when that relationship helps later reasoning; this contextual relationship does not itself reopen or add the retained Goal to the current responsibility. "
            "The decoder enforces the exact GoalAssociationModelOutput JSON Schema. "
        )
    return (
        state_instructions
        + "Goal Association receives provider-neutral Responsibility evidence, not a route or intent classification. "
        "Each Responsibility also carries GI's context-grounded Goal relationship and target_goal_ids. Verify those proposals against the complete candidate Goal list and authoritative turn; preserve a correct answer to a pending Planner clarification as a Goal update instead of interpreting its short surface as a new Goal. Goal Association remains the sole canonical commit authority and may resolve a supplied pending gap only through its canonical association update. "
        "No compatibility label may force a clarification branch or attach the turn to an existing Goal. "
        "Create or associate a Goal for every source-grounded human Responsibility even when GI reports bounded unresolved meaning or Fast Planner later finds a missing execution input. That provisional Goal persists while Fast Planner asks the user. Goal Association never selects or words a clarification Activity and never creates a planning InformationGap. "
        + "The model-facing contract is deliberately small. "
        "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
        "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, capabilities, or plans. Referent IDs may only be copied from the supplied discourse context; new referent IDs are Host-generated.\n\n"
        "Create one new goal for each independently satisfiable user responsibility. Copy every owning GI local_ref into that Goal's source_responsibility_refs; every GI Responsibility ref must map to exactly one association or new Goal. The authoritative user turn plus Responsibility evidence are the only sources of human Responsibility here; Fast Planner Activity is HOW authored concurrently and must never become, justify, or be copied into a sibling Goal. Responsibility conservation is strict: never create an extra Goal for acknowledgement, progress, response delivery, personality, or any other outcome that is absent from the authoritative Responsibility evidence. Emit exactly one new_goals item containing source_responsibility_refs, description, typed bindings, and an optional provider-neutral resource_responsibility for each responsibility. "
        "Every new Goal must declare one exact canonical output_mode that preserves the human-facing WHAT modality. It is not an execution lane, provider requirement, or Work decision. GI information/stateful_effect are preserved as provider-neutral WHAT categories; neither selects a concrete Capability or declares that provider Work is required. Media playback may also declare its exact media_operation; non-media Goals may omit media_operation and the Host supplies none. "
        "When Responsibility evidence includes output_mode, preserve its human-level "
        "WHAT while using the canonical Goal projection enforced by the decoder: "
        "information -> information + information resource when applicable; stateful_effect -> "
        "stateful_effect without an information resource; every other explicit mode is "
        "copied exactly. Goal Association must not reinterpret or weaken the WHAT, and "
        "this projection never chooses a concrete Capability/provider. "
        "Use output_mode=speech for an ordinary authored conversational response, including a greeting, empathy, reassurance, restatement, explanation from supplied context, or acknowledgement of a person's feeling. The need to think or formulate words never makes ordinary conversation information. A person's report of their own state never becomes body_action, information, or stateful_effect unless the authoritative Responsibility separately asks Chromie to learn something or change the world. Preserve speaker, experiencer, actor, and addressee ownership exactly. "
        f"{_EXECUTION_CONTRACT_PROMPT} "
        "The eventual spoken delivery of information or an effect result remains part of that same Goal, never an additional speech Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
        "A requested manner, mood, persona, or social presentation attached to a substantive action or other effect is a constraint on how that effect should be expressed, not a second Goal. Keep it in the substantive Goal description. It becomes a separate vocal Goal only when the user independently asks to hear positive authored content or a vocal performance that remains satisfiable without the substantive effect. "
        "A standalone social interaction such as a greeting, thanks, reassurance request, casual check-in, reaction, personal feeling, evaluation, or practical decision is itself one satisfiable conversational Goal: respond naturally to that current social act. This remains true when the act is grounded in information delivered by a previous Goal. Prior evidence may support the answer, but it does not replace the latest communicative responsibility. Do not treat it as an empty turn or fold it into an already completed task merely because the topic is related. "
        "A new question about what Chromie previously said is a fresh speech Goal whose owed outcome is for Chromie to repeat or summarize the most recent accepted assistant/Chromie dialogue utterance. It references that utterance as content but does not continue, resume, or modify the old Goal merely because the old response supplies the answer. Never reverse this into asking the user to repeat, and never substitute the user's earlier utterance or current question for Chromie's delivered words. "
        "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
        "Information acquisition and a requested interpretation of that same evidence are one Goal when one result can satisfy both. Multiple requested aspects derived from one information result remain one information responsibility when the same result satisfies them. Do not split evidence acquisition, requested result aspects, or interpretation of that result into separate Goals. "
        "A physical action and a conversational answer or spoken performance are independent goals when the answer or performance is genuinely requested. Separate independently requested outcomes that can be accepted or rejected on their own. However, acquisition and delivery stages that together constitute one human responsibility are one Goal: navigating/searching, locating, grasping or retrieving, carrying, returning, and handing over are provider-owned stages of one physical resource delivery; external search, evidence retrieval, evaluation, and spoken explanation are stages of one information resource delivery. Do not split those implementation stages into separate Goals unless the user independently requests one stage as its own outcome. A simple acknowledgement, confirmation, willingness statement, or progress prelude for capability work is not a separate vocal_output Goal; it is prospective conversational output attached to the existing responsibility and every cognitive stage must use Interaction Context to avoid repeating an already fulfilled act. Before returning, verify that every independently satisfiable user responsibility appears in exactly one new_goals item: no merged unrelated outcomes and no duplicated responsibility across Goals. "
        "Every Goal must first state resource_kind as the explicit resource discriminator: none for non-resource outcomes, physical_object only for acquisition and physical handover of a distinct concrete object, or information for an information outcome. The declared discriminator and resource_responsibility kind must match exactly. For a responsibility whose human-level outcome is to obtain something and make it available to a recipient, include exactly one nested resource_responsibility. It is the sole writable resource authority. A physical_object resource means a distinct concrete object that exists independently of Chromie's body motion and whose acquisition plus handover completes the human outcome. It is never a generic wrapper for embodied work: locomotion, body motion, gaze, blinking, waving, turning, posture, and gestures are non-resource body_action Goals, use resource_kind=none, keep resource_responsibility absent, and preserve their material semantic parameters in top-level bindings. For kind=information, use output_mode=information, classify the provider-neutral information_domain from the evidence actually needed (local_clock, weather_forecast, external_grounded_information, direct_environment_perception, or private_runtime_information). Weather conditions and forecasts—including rain or precipitation, temperature, hot/cold, wind, humidity, and sky conditions—are always weather_forecast; external_grounded_information is only a public fact with no more specific owned domain. Write every requested query fact—location, time, requested aspect, comparison, threshold, or other answer-shaping scope—exactly once in query_scope. Current nearby person/object/event presence is direct_environment_perception, never weather merely because both concern outside. Its source object is intentionally narrow: source.status=provider_resolved delegates public/external source selection; source.status=unknown preserves an unavailable local/private/runtime source; source.status=known is only for a user- or discourse-named information source and then source_name is required. Never copy query_scope facts into source. For kind=physical_object, use output_mode=body_action and delivery_mode=physical_handover; identity and quantity live at resource_responsibility.description/quantity, while source.acquisition_bindings is the only writable location/distance/direction/route surface. When the user or a resolved discourse referent supplies any spatial acquisition fact, source.status must be known and acquisition_bindings must preserve every supplied distance, direction, location, or route. Preserve separately supplied GI bindings separately, but never decompose one GI-owned composite binding into model-normalized fragments: one location binding such as a relative place plus approximate distance remains one exact location/relative_location acquisition binding with its complete source value. source.status=unknown is valid only when no acquisition grounding was supplied. source.description is summary only and any numeric fact in it must also exist in acquisition_bindings. Resource Goals keep top-level bindings empty. No flat compatibility copy is created. resource_responsibility must never name or imply a Capability, provider implementation, website, search engine, coordinates, grasp pose, execution mode, or plan. Human-readable descriptions never override typed fields. "
        "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. Keep source-grounded temporal wording as human semantic scope rather than translating it into provider date/day-part parameters. One compound source expression may remain one temporal_scope binding; separately stated independent scopes remain separate semantic constraints. Never silently narrow broader, historical, comparative, or otherwise scoped meaning. If the intended scope is materially ambiguous, preserve it in a provisional Goal without choosing a narrower interpretation. "
        "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. First identify every material indirect referring expression, then require a unique value from that authority order before writing a resolved binding or supplied referent. Imperative grammar and a plausible generic noun such as device, object, person, task, or setting are never reference evidence. If two or more contextual candidates remain plausible, or none is supplied, preserve the unresolved reference in the provisional Goal description without selecting a candidate; Fast Planner owns the narrow clarification decision. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
        "When the user introduces or explicitly corrects a salient entity, emit referent_updates only when the required discourse-index provenance is available. Use operation=correct with non-empty target_referent_ids copied from supplied discourse context when a new value supersedes an earlier referent; never emit an unscoped correction when no target referent ID was supplied. The canonical Goal association and typed bindings still preserve a correction even when no discourse-index update can be authored. The old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
        "Use resolved_references only for indirect references whose denotation is uniquely selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, omit the invented binding/reference and preserve a provisional Goal instead. "
        "Each non-resource Goal must include top-level typed bindings for material entities and parameters already resolved here, including explicit counts, durations, speeds, directions, and targets. For a qualitative speed, use the provider-neutral canonical value slow, normal, or quick; retain more specific severity or intensity as a separate binding rather than hiding it in an inflected speed phrase. Preserve an explicit quantitative speed with its value and units. The action/effect itself belongs in the Goal description; it does not need a duplicate action binding when that exact source value is already retained there. A resource Goal keeps top-level bindings empty and owns every material resource fact only in resource_responsibility. For information, query_scope is the one query-fact surface. Preserve each resolved answer-shaping fact there exactly once as its own typed binding, including spatial, temporal, comparison, threshold, or requested-result scope when supplied. For physical acquisition, use the canonical name and entity_type distance/distance for a separately supplied distance and direction/direction for a separately supplied direction. A relative spatial place uses location/relative_location, including when its one authoritative GI value contains an inseparable approximate distance; generic labels such as measurement or string are not canonical substitutes for a known typed fact. Preserve every explicit severity, intensity, magnitude, threshold, subtype, negation, or comparison qualifier that changes satisfactory completion. Never generalize a narrower request. Downstream planners read the canonical resource directly; no persisted flat projection exists. "
        "For a location named directly in the final authoritative user turn, copy the complete location value verbatim as one contiguous span in the user's language. Never translate, transliterate, shorten, or expand a directly named location. A directly supplied location is a resolved semantic binding, not a claim that provider canonicalization has already succeeded. Do not ask the user for administrative granularity merely because multiple real-world places might share that value; create the fully bound Goal and let the downstream Capability resolve the exact value or report provider ambiguity. When the user's intended location is genuinely underdetermined in the dialogue, preserve that unresolved scope in the provisional Goal and leave clarification selection to Fast Planner. Only an indirect reference resolved from a supplied referent may use the referent's canonical value instead. For an indirect location, copy the supplied referent_id into both the location binding and resolved_references, and copy the indirect user surface into resolved_references.surface_form. "
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
        "Goal Association must not author a clarification question, input-source policy, or planning InformationGap. Put only compact Goal-state rationale in reason_summary.\n\n"
        + output_instructions
        + "Each new_goals object contains description, output_mode, optional media_operation, bindings, explicit resource_kind, optional resource_responsibility, related_goal_ids only when retained Goals remain relevant context, and supersedes_goal_ids only when the old Responsibility is genuinely abandoned and replaced by this new independently owed outcome. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. resource_kind is the exact discriminator for resource_responsibility; resource_responsibility is provider-neutral and must follow the contract above. A vocal Goal must never carry resource_responsibility merely because rendering needs a provider. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
        "Owner-approved Chromie identity JSON:\n"
        f"{identity_json}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{personality_json}\n\n"
        + "Bounded active goals JSON:\n"
        f"{bounded_json(candidate_goals, 6500)}\n\n"
        "Responsibility evidence JSON (Core-authored provider-neutral semantic handoff from Goal Interpretation. These are not canonical Goals. Preserve the WHAT and material bindings; use the authoritative user turn, discourse, retained Goal state, and Situation only to associate continuity or identify a real representation mismatch, never to silently rewrite the Responsibility. Goal Association alone decides create/continue/modify/supersede canonical Goal state. Never infer a Capability, provider, execution method, executable argument, or response wording here):\n"
        f"{bounded_json([item.model_dump(mode='json', exclude_none=True) for item in request.responsibilities], 4200)}\n\n"
        "Bounded active task/progress snapshots JSON:\n"
        f"{bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
        f"{goal_progress_communication_prompt('Goal Association')}\n\n"
        "Goal-scoped Interaction Context JSON (append-only facts about what Chromie already associated, planned, said, committed, completed, or failed; owner and event_type preserve evidence strength). Use it to identify the still-needed Goal/continuity delta. Generated or scheduled speech is not heard speech, and planned or committed work is not completed work. Do not reopen, repeat, or recreate an already fulfilled responsibility unless the current turn explicitly repeats it or new failure, correction, changed state, evidence, or clarification requires a new delta:\n"
        f"{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
        "Scoped discourse referents JSON:\n"
        f"{bounded_json(discourse_referents(request), 6500)}\n\n"
        "Discourse focus stack JSON (most recent/foreground last):\n"
        f"{bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
        "Recent conversation JSON:\n"
        f"{bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
        "Recent conversation is accepted dialogue evidence for ellipsis, pronouns, corrections, and other follow-up meaning. Bounded Goal and Task state is stronger evidence of already-validated semantic continuity when it exists. A newer accepted turn whose metadata says semantic_status=failed or terminal_without_canonical_goal remains valid recent conversational evidence even though it has no canonical Goal; do not skip it solely because an older Goal is canonical. If an earlier admitted turn has not yet produced canonical Goal state, dialogue may still resolve the current reference, but never invent a Goal ID or pretend uncommitted work is canonical.\n\n"
        "Tool-result contents are intentionally absent at this boundary. Resolve references and Goal bindings from user semantics, scoped referents, candidate Goals, and dialogue only. A later Planner may explicitly retrieve an exact verified memory record after bindings are fixed. "
        "For an open safe-read Goal whose bound Work is scheduled, running, or recoverable, associate a semantic follow-up with that exact Goal when appropriate; do not answer from another task's result. "
        "Do not reason from prior routing labels, planner states, validation failures, fallback states, or other runtime diagnostics; they are not user-semantic evidence.\n\n"
        f"Language hint: {request.language or 'auto'}\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
        f"FINAL CANDIDATE GOAL IDS JSON:\n{bounded_json([item.get('goal_id') for item in candidate_goals], 1600)}"
    )


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
    return (
        f"The previous {contract_name} JSON object is mechanically malformed. "
        "This is the only same-stage DTO repair. Preserve every semantic claim "
        "already present in the previous object: decision, relationship, Goal "
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
    rendered = build_prompt(
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
        "score, or replace the decision. Return only the corrected JSON object."
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
        "Apply continuity before creation. Resolve references from current user meaning, scoped discourse referents/focus, bounded candidate Goals and their bindings, and dialogue context. Candidate Goals may be active, recoverable, or recently terminal; referencing a terminal Goal does not reopen it. Tool-result memory is not reference-resolution authority. Status follow-ups about an unfinished lookup should associate with the bound task; if its safe read is recoverable, preserve the exact skill arguments for retry. Do not treat another task's evidence as completion. "
        "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
        "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
        "Conversational framing attached to substantive work is not a separate Goal; a standalone social interaction remains one conversational Goal. A new reaction, feeling, evaluation, acknowledgement, or practical decision after a prior result is a current conversational responsibility, not continuation of the completed lookup. One lookup and an interpretation requested as part of that same lookup are one Goal. "
        "You are advisory only and never execute or commit. Return JSON only."
    )
