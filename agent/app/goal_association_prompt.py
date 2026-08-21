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
    GoalAssociationModelGoal,
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
        "Copy a supplied Responsibility output_mode exactly; it is the only "
        "model-authored execution discriminator. Preserve every supplied material "
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
        "location, distance, direction, and route belong separately in "
        "source.acquisition_bindings. Supplied spatial grounding requires "
        "source.status=known; source.status=unknown is allowed only when none was "
        "supplied.\n\n"
        "An information resource uses output_mode=capability_work and one exact "
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
            "completion_requires_work": metadata.get(
                "completion_requires_work"
            ),
            "completion_requires_fresh_evidence": metadata.get(
                "completion_requires_fresh_evidence"
            ),
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
        "output_mode, and completion contract. It cannot rewrite a material entity "
        "or parameter. If current meaning changes one, create one complete replacement "
        "Goal and put the old ID in supersedes_goal_ids. If current meaning is "
        "independent, create a new Goal without reopening the old one. A recent "
        "terminal Goal may be referenced but not reopened. Preserve unresolved human "
        "meaning in the narrowest provisional Goal; Fast Planner alone decides any "
        "question.\n\n"
        "For a new Goal, copy the GI output_mode and every material binding exactly. "
        "Use resource_responsibility only when the owed outcome is to acquire and "
        "make a resource available. A physical_object is a concrete object independent "
        "of Chromie's body and uses physical_handover; locomotion, gaze, blinking, "
        "gesture, and posture are non-resource body_action. An information resource "
        "uses capability_work and keeps location, time, aspects, comparisons, and "
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
        "Every new Goal must declare one exact output_mode that describes the semantic work completing the human outcome. output_mode is the only model-authored execution discriminator. Responsibility kind, execution lane, and provider requirement are Host-derived projections and are not fields in the model schema. Media playback may also declare its exact media_operation; non-media Goals may omit media_operation and the Host supplies none. "
        "When Responsibility evidence includes output_mode, copy that exact value "
        "to its one Goal. Goal Interpretation owns this provider-neutral completion "
        "modality; Goal Association must not reinterpret, weaken, or relabel it. "
        "Use output_mode=speech for an ordinary authored conversational response, including a greeting, empathy, reassurance, restatement, explanation from supplied context, or acknowledgement of a person's feeling. The need to think or formulate words never makes ordinary conversation capability_work. A person's report of their own state never becomes body_action or capability_work unless the authoritative Responsibility separately asks Chromie to change the world. Preserve speaker, experiencer, actor, and addressee ownership exactly. "
        f"{_EXECUTION_CONTRACT_PROMPT} "
        "The eventual spoken delivery of a capability result is part of that same capability_dependent Goal, never an additional vocal_output Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
        "A requested manner, mood, persona, or social presentation attached to a substantive action or other effect is a constraint on how that effect should be expressed, not a second Goal. Keep it in the substantive Goal description. It becomes a separate vocal Goal only when the user independently asks to hear positive authored content or a vocal performance that remains satisfiable without the substantive effect. "
        "A standalone social interaction such as a greeting, thanks, reassurance request, casual check-in, reaction, personal feeling, evaluation, or practical decision is itself one satisfiable conversational Goal: respond naturally to that current social act. This remains true when the act is grounded in information delivered by a previous Goal. Prior evidence may support the answer, but it does not replace the latest communicative responsibility. Do not treat it as an empty turn or fold it into an already completed task merely because the topic is related. "
        "A new question about what Chromie previously said is a fresh speech Goal whose owed outcome is for Chromie to repeat or summarize the most recent accepted assistant/Chromie dialogue utterance. It references that utterance as content but does not continue, resume, or modify the old Goal merely because the old response supplies the answer. Never reverse this into asking the user to repeat, and never substitute the user's earlier utterance or current question for Chromie's delivered words. "
        "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
        "Information acquisition and a requested interpretation of that same evidence are one Goal when one result can satisfy both. Multiple requested aspects derived from one information result remain one information responsibility when the same result satisfies them. Do not split evidence acquisition, requested result aspects, or interpretation of that result into separate Goals. "
        "A physical action and a conversational answer or spoken performance are independent goals when the answer or performance is genuinely requested. Separate independently requested outcomes that can be accepted or rejected on their own. However, acquisition and delivery stages that together constitute one human responsibility are one Goal: navigating/searching, locating, grasping or retrieving, carrying, returning, and handing over are provider-owned stages of one physical resource delivery; external search, evidence retrieval, evaluation, and spoken explanation are stages of one information resource delivery. Do not split those implementation stages into separate Goals unless the user independently requests one stage as its own outcome. A simple acknowledgement, confirmation, willingness statement, or progress prelude for capability work is not a separate vocal_output Goal; it is prospective conversational output attached to the existing responsibility and every cognitive stage must use Interaction Context to avoid repeating an already fulfilled act. Before returning, verify that every independently satisfiable user responsibility appears in exactly one new_goals item: no merged unrelated outcomes and no duplicated responsibility across Goals. "
        "For a responsibility whose human-level outcome is to obtain something and make it available to a recipient, include exactly one nested resource_responsibility. It is the sole writable resource authority and is discriminated by top-level kind. A physical_object resource means a distinct concrete object that exists independently of Chromie's body motion and whose acquisition plus handover completes the human outcome. It is never a generic wrapper for embodied work: locomotion, body motion, gaze, blinking, waving, turning, posture, and gestures are non-resource body_action Goals, keep resource_responsibility absent, and preserve their material semantic parameters in top-level bindings. For kind=information, use output_mode=capability_work, classify the provider-neutral information_domain from the evidence actually needed (local_clock, weather_forecast, external_grounded_information, direct_environment_perception, or private_runtime_information), and write every requested query fact—location, time, requested aspect, comparison, threshold, or other answer-shaping scope—exactly once in query_scope. Current nearby person/object/event presence is direct_environment_perception, never weather merely because both concern outside. Its source object is intentionally narrow: source.status=provider_resolved delegates public/external source selection; source.status=unknown preserves an unavailable local/private/runtime source; source.status=known is only for a user- or discourse-named information source and then source_name is required. Never copy query_scope facts into source. For kind=physical_object, use output_mode=body_action and delivery_mode=physical_handover; identity and quantity live at resource_responsibility.description/quantity, while source.acquisition_bindings is the only writable location/distance/direction/route surface. When the user or a resolved discourse referent supplies any spatial acquisition fact, source.status must be known and acquisition_bindings must preserve every supplied distance, direction, location, or route separately. source.status=unknown is valid only when no acquisition grounding was supplied. Preserve explicit distance and direction separately; source.description is summary only and any numeric fact in it must also exist in acquisition_bindings. Resource Goals keep top-level bindings empty. No flat compatibility copy is created. resource_responsibility must never name or imply a Capability, provider implementation, website, search engine, coordinates, grasp pose, execution mode, or plan. Human-readable descriptions never override typed fields. "
        "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. Keep source-grounded temporal wording as human semantic scope rather than translating it into provider date/day-part parameters. One compound source expression may remain one temporal_scope binding; separately stated independent scopes remain separate semantic constraints. Never silently narrow broader, historical, comparative, or otherwise scoped meaning. If the intended scope is materially ambiguous, preserve it in a provisional Goal without choosing a narrower interpretation. "
        "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. First identify every material indirect referring expression, then require a unique value from that authority order before writing a resolved binding or supplied referent. Imperative grammar and a plausible generic noun such as device, object, person, task, or setting are never reference evidence. If two or more contextual candidates remain plausible, or none is supplied, preserve the unresolved reference in the provisional Goal description without selecting a candidate; Fast Planner owns the narrow clarification decision. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
        "When the user introduces or explicitly corrects a salient entity, emit referent_updates only when the required discourse-index provenance is available. Use operation=correct with non-empty target_referent_ids copied from supplied discourse context when a new value supersedes an earlier referent; never emit an unscoped correction when no target referent ID was supplied. The canonical Goal association and typed bindings still preserve a correction even when no discourse-index update can be authored. The old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
        "Use resolved_references only for indirect references whose denotation is uniquely selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, omit the invented binding/reference and preserve a provisional Goal instead. "
        "Each non-resource Goal must include top-level typed bindings for material entities and parameters already resolved here, including explicit counts, durations, speeds, directions, and targets. For a qualitative speed, use the provider-neutral canonical value slow, normal, or quick; retain more specific severity or intensity as a separate binding rather than hiding it in an inflected speed phrase. Preserve an explicit quantitative speed with its value and units. The action/effect itself belongs in the Goal description; it does not need a duplicate action binding when that exact source value is already retained there. A resource Goal keeps top-level bindings empty and owns every material resource fact only in resource_responsibility. For information, query_scope is the one query-fact surface. Preserve each resolved answer-shaping fact there exactly once as its own typed binding, including spatial, temporal, comparison, threshold, or requested-result scope when supplied. For physical acquisition, use the canonical name and entity_type distance/distance for distance and direction/direction for direction. A relative spatial place may use location/relative_location; generic labels such as measurement or string are not canonical substitutes for a known typed fact. Preserve every explicit severity, intensity, magnitude, threshold, subtype, negation, or comparison qualifier that changes satisfactory completion. Never generalize a narrower request. Downstream planners read the canonical resource directly; no persisted flat projection exists. "
        "For a location named directly in the final authoritative user turn, copy the complete location value verbatim as one contiguous span in the user's language. Never translate, transliterate, shorten, or expand a directly named location. A directly supplied location is a resolved semantic binding, not a claim that provider canonicalization has already succeeded. Do not ask the user for administrative granularity merely because multiple real-world places might share that value; create the fully bound Goal and let the downstream Capability resolve the exact value or report provider ambiguity. When the user's intended location is genuinely underdetermined in the dialogue, preserve that unresolved scope in the provisional Goal and leave clarification selection to Fast Planner. Only an indirect reference resolved from a supplied referent may use the referent's canonical value instead. For an indirect location, copy the supplied referent_id into both the location binding and resolved_references, and copy the indirect user surface into resolved_references.surface_form. "
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
        "Goal Association must not author a clarification question, input-source policy, or planning InformationGap. Put only compact Goal-state rationale in reason_summary.\n\n"
        + output_instructions
        + "Each new_goals object contains description, output_mode, optional media_operation, bindings, optional resource_responsibility, related_goal_ids only when retained Goals remain relevant context, and supersedes_goal_ids only when the old Responsibility is genuinely abandoned and replaced by this new independently owed outcome. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. resource_responsibility is provider-neutral and must follow the contract above. A vocal Goal must never carry resource_responsibility merely because rendering needs a provider. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
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
    context = request.context if isinstance(request.context, dict) else {}
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    if output_type is GoalSegmentationModelOutput:
        contract_name = "Goal Segmentation"
        revision_action = "Re-evaluate the independent goal segmentation"
        state_instructions = (
            "There are no active or retained recent Goals. Existing-goal associations are structurally invalid and must not appear. "
            "Re-segment every independently satisfiable responsibility into new_goals. Preserve unresolved human-level meaning in the narrowest provisional Goal without inventing it; Fast Planner owns any question. "
            "A standalone social interaction is one conversational Goal and must not be returned as an empty goal list. A greeting attached to substantive work is framing, not a second Goal. Identity and personality shape wording only and never create a Goal. A lookup plus an interpretation derived from the same result is one Goal. "
        )
        output_instructions = (
            "The exact GoalSegmentationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
            "Return only decision, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
        )
    else:
        contract_name = "Goal Association"
        revision_action = "Re-evaluate the semantic associations"
        state_instructions = (
            "Re-evaluate continuity against only the supplied bounded candidate Goal IDs. "
            "The final authoritative user turn owns the current communicative responsibility. A completed task may supply context, but a reaction, feeling, evaluation, acknowledgement, or practical decision about that context is normally a fresh vocal_output Goal rather than continuation or reference. Existing Goal bindings are provenance-stable and cannot be changed by an association. If current user meaning changes a material binding, use decision=create_goals with one fully bound replacement Goal rather than a description-only association. "
        )
        output_instructions = (
            "The exact GoalAssociationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
            "Return only decision, associations, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
        )
    return (
        f"The previous minimal {contract_name} semantic DTO failed its exact contract. {revision_action} and "
        "return one corrected JSON object. Preserve valid semantic judgments, but revise every field needed to satisfy "
        "the schema and validation errors. Do not explain the correction and do not use synonym substitution rules.\n\n"
        + state_instructions
        + "Responsibility conservation remains authoritative during repair. Never add a Goal whose human outcome is absent from the supplied Responsibility evidence. In particular, a Fast-Planner progress acknowledgement or later response delivery is HOW around the existing Responsibility, not a sibling speech Goal. A physical_object resource is only a distinct concrete object whose acquisition and handover completes the responsibility; ordinary locomotion, body movement, gaze, blinking, waving, turning, posture, and gestures use output_mode=body_action with top-level semantic bindings and no resource_responsibility.\n\n"
        + f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        + "\n\nResolved references are only for indirect references bound to a supplied discourse referent or active Goal binding. Direct explicit entity mentions belong in Goal bindings and salient referent updates, not resolved_references. For an indirect location binding, copy the supplied referent_id into both the location binding and resolved_references, copy the indirect user surface into resolved_references.surface_form, and retain the referent canonical value. Every resolved reference and referent update must include explicit confidence.\n\nOwner-approved Chromie identity JSON:\n"
        + identity_json
        + "\n\nOwner-approved Personality Expression JSON:\n"
        + personality_json
        + "\n\n"
        + f"Latest user turn:\n{request.text}\n\n"
        "For a location named directly in that user turn, copy the complete location binding value verbatim as one contiguous span. Never translate, transliterate, shorten, or expand it. Responsibility evidence may contain a normalized or incorrectly translated spelling; the FINAL AUTHORITATIVE USER TURN owns the direct entity surface and must win. Do not ask the user for provider canonicalization or extra administrative granularity merely because multiple real-world places might share the supplied value; bind it exactly and let the downstream Capability resolve it or report provider ambiguity. Only an indirect reference resolved from a supplied referent may use the referent's canonical value.\n\n"
        "Bounded active goals JSON:\n"
        f"{bounded_json(candidate_goals, 7000)}\n\n"
        "Bounded live Situation projection JSON (soft/revisable relevance only):\n"
        f"{bounded_json(situation_projection(request), 3600)}\n\n"
        "Bounded active task/progress snapshots JSON:\n"
        f"{bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
        f"{goal_progress_communication_prompt('Goal Association')}\n\n"
        "Goal-scoped Interaction Context JSON:\n"
        f"{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
        "Scoped discourse referents JSON:\n"
        f"{bounded_json(discourse_referents(request), 6500)}\n\n"
        "Discourse focus stack JSON:\n"
        f"{bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
        "Recent conversation JSON:\n"
        f"{bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
        "Use recent conversation as accepted dialogue evidence for follow-up meaning, while bounded Goal and Task state remains the authority for already-validated semantic work. A newer failed or terminal-without-canonical-Goal dialogue turn remains relevant context and must not be skipped solely because an older Goal has canonical state. Never invent a Goal ID merely because dialogue implies an earlier turn is still being processed.\n\n"
        "Previous model output JSON:\n"
        f"{bounded_json(raw, 5000)}\n\n"
        "Exact validation errors JSON:\n"
        f"{validation_error}\n\n"
        + output_instructions
        + "Select exactly one Goal-state decision branch. Do not author clarification wording or planning gaps. Each new_goals item contains description, output_mode, optional media_operation, bindings, optional supersedes_goal_ids, and optional provider-neutral resource_responsibility only. Choose output_mode from the work that actually completes the Goal; the Host derives the internal responsibility class, lane, and provider-evidence requirement. media_playback requires one exact media_operation; non-media Goals may omit it. "
        + _EXECUTION_CONTRACT_PROMPT
        + " Preserve one nested resource_responsibility when the responsibility is genuinely to acquire and deliver a physical object or grounded information; never add it to a vocal performance or insert provider details. It is the sole writable resource authority. Use kind=information with output_mode=capability_work, an exact provider-neutral information_domain, query_scope for all requested information facts, and a narrow source object that can only delegate, remain unknown, or name one explicit information source. Classify present nearby people, objects, or events as direct_environment_perception, not weather_forecast. Use kind=physical_object with output_mode=body_action, delivery_mode=physical_handover, and source.acquisition_bindings as the sole spatial/acquisition fact surface. Never duplicate one fact across fields and never create top-level Goal bindings for a resource Goal. In physical acquisition bindings, distance uses name=distance and entity_type=distance, direction uses name=direction and entity_type=direction, and a relative place may use name=location and entity_type=relative_location. Generic measurement or string types do not replace these canonical types. Preserve human temporal scope in source-grounded semantic form, preferably entity_type=temporal_scope for a compound natural expression; do not derive Capability date/period enums or clock windows. Never repair missing human-level scope by inventing a default: preserve unresolved scope in a provisional Goal and leave the exact missing value unset. Preserve or repair explicit discourse resolution and referent updates; never use tool-result contents to infer a reference. "
        "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
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
    context = request.context if isinstance(request.context, dict) else {}
    identity_world = stable_identity_world_layer(context)
    rendered = build_repair_prompt(
        request=request,
        candidate_goals=candidate_goals,
        turn_id=turn_id,
        output_type=output_type,
        raw=raw,
        validation_error=validation_error,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            IDENTITY_SEMANTIC_CONTRACT,
            PERSONALITY_SEMANTIC_CONTRACT,
            _EXECUTION_CONTRACT_PROMPT,
        ),
    )


def stable_identity_world_layer(context: dict[str, Any]) -> str:
    return (
        "Owner-approved Chromie identity JSON:\n"
        f"{bounded_identity_json(context)}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{bounded_personality_json(context)}\n\n"
    )


def build_fresh_interpretation_prompt(
    *,
    request: CognitiveWorkRequest,
    candidate_goals: list[dict[str, Any]],
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    problems: list[str],
    preserve_unresolved_meaning: bool = False,
) -> str:
    terminal_instruction = (
        "The independent proof established that material meaning is unresolved. "
        "Preserve a provisional Goal for the source-grounded Responsibility without "
        "inventing the unresolved referent or scope. Goal Interpretation has already "
        "exposed the ambiguity to Fast Planner, which alone decides whether and how "
        "to ask; Goal Association must not author a clarification Activity or wording. "
        if preserve_unresolved_meaning
        else ""
    )
    return (
        build_prompt(
            request,
            candidate_goals,
            output_type=output_type,
        )
        + "\n\nAn independent source-grounded coverage proof rejected the "
        "first candidate set. Discard that candidate DTO as authority and perform "
        "one final fresh interpretation from the FINAL AUTHORITATIVE USER TURN. "
        "Do not discard independently supported current-turn Responsibility evidence: "
        "the Fast responsibility proposals rendered above remain provider-neutral "
        "semantic evidence and must be re-checked against the authoritative turn. "
        "The FINAL AUTHORITATIVE USER TURN remains the source for explicit material "
        "qualifiers: if a proposal or rejected candidate generalized away severity, "
        "intensity, magnitude, threshold, subtype, negation, comparison, quantity, or "
        "scope, restore that source-grounded WHAT in the final Goal representation. "
        "Planner Activity metadata is never a Responsibility source and must not be "
        "preserved as a Goal. "
        "Removing an unjustified sibling Goal never permits dropping a still-supported "
        "human Responsibility. The following compact defects are proof feedback, not "
        "Goal labels and not permission to copy a previous DTO:\n"
        + bounded_json(problems, 3000)
        + "\n"
        + "Typed proof feedback is structural, not optional prose. When it says "
        "required_goal_shape:ordinary, the corrected candidate must have no "
        "resource_responsibility. Preserve requested body motion, locomotion, "
        "gaze, gesture, posture, or vocal performance through its exact output_mode "
        "and top-level semantic bindings; none of those effects is an object to "
        "acquire and hand over. When the proof reports representation_mismatch for "
        "an embodied or vocal modality, re-read the source effect and use body_action "
        "for locomotion/gaze/blink/gesture/posture or the exact singing/recitation/"
        "humming/styled_speech/nonverbal_vocalization mode for an authored vocal "
        "performance. Keep each independently observable coordinated effect in its "
        "own Goal. When feedback lists required_output_mode, preserve that exact "
        "output_mode in the corrected candidate; descriptive prose cannot satisfy "
        "this typed requirement. When it says "
        "required_goal_shape:information_resource, the corrected candidate must "
        "carry one resource_responsibility object with kind=information; "
        "output_mode=capability_work or a descriptive sentence alone does not "
        "satisfy that shape. Its top-level bindings must be empty and all query "
        "facts must live in resource_responsibility.query_scope. When feedback "
        "lists required_information_domain, preserve that exact provider-neutral "
        "domain in resource_responsibility.information_domain; never relabel a "
        "nearby-person or local-observation need as weather, clock, or web research. "
        "Every query_scope item must preserve source-grounded human semantic "
        "scope. Temporal wording belongs here as the user's semantic constraint, "
        "not as Planner/Capability date, period, or clock-range arguments. Every "
        "query_scope item must "
        "be entailed by the FINAL AUTHORITATIVE USER TURN, supplied Responsibility "
        "evidence, or an explicitly resolved discourse referent. Never invent a "
        "provider prerequisite, placeholder, default, current location, source, "
        "device, or other query fact merely because it might help execution. A "
        "request for Chromie's current local clock time carries the supplied "
        "time=now fact; it does not imply a location query.\n"
        "For a physical resource, source-grounded distance, direction, location, "
        "or route feedback requires source.status=known plus one "
        "source.acquisition_bindings item for every supplied fact. unknown is not "
        "a placeholder for supplied spatial grounding, and prose cannot replace "
        "these typed bindings. Omit optional quantity unless a normalized positive "
        "numeric value is source-grounded.\n"
        + terminal_instruction
        + "Return one complete final DTO. This interpretation receives no "
        "contract repair; invalid or incomplete output fails closed."
    )


def responsibility_coverage_system_prompt() -> str:
    return (
        "You are Chromie's independent Goal responsibility-coverage auditor. "
        "Read the authoritative turn from scratch; candidate prose is not source "
        "evidence. Copy every source_excerpt only from an exact contiguous span of "
        "the FINAL AUTHORITATIVE USER TURN in its original language; never use a "
        "translation or paraphrase from Responsibility outcome or binding text. "
        "A positive observable outcome is a responsibility. Duration, "
        "distance, direction, order, manner, prohibition, temporal scope, and other "
        "conditions on that same outcome are constraints, never independently "
        "satisfiable responsibilities. That role distinction is only the audit "
        "shape: a constraint belongs on the same candidate Goal as the "
        "responsibility it modifies, normally through a typed binding, and does "
        "not need its own Goal. A constraint is covered when the candidate's "
        "typed binding preserves its meaning; do not call it a representation "
        "mismatch merely because the modifier also appears in the candidate "
        "description or the binding uses an equivalent normalized value. "
        "A reason or background event that only explains why the answer is useful "
        "and does not change which answer would be correct is context, not a "
        "constraint; context is covered without Goal ownership. Only background "
        "that changes valid completion is a constraint. Preserve temporal source "
        "wording as one human semantic constraint rather than decomposing it into "
        "provider-facing date/day-part fields. Coordinated effects are separate only when a "
        "person can judge each effect completed without the others. One evidence "
        "lookup and the requested judgment of its result remain one responsibility. "
        "Coordination grammar never demotes a positive effect to a constraint. If a "
        "coordinated clause mixes a relation or manner with another observable effect, "
        "give every effect its own role=responsibility item and put only the relation, "
        "order, or manner material in role=constraint. Never leave the action or effect "
        "word itself only in supporting_items. "
        "Use the exact required_output_mode: body_action for embodied effects; the "
        "exact singing/recitation/humming/styled_speech/nonverbal_vocalization mode "
        "for authored performance; media_playback for media control; capability_work "
        "for fresh evidence or persistent effects; and speech for ordinary dialogue. "
        "Wrong completion mode or resource shape is "
        "coverage=representation_mismatch. A physical resource means acquisition and "
        "handover of a distinct concrete object; body motion is not a physical "
        "resource. A state mutation or future delivery is a persistent effect, not "
        "information acquisition. For temporal constraints, coverage means the "
        "candidate preserves the source-grounded human scope without silently "
        "narrowing, translating, or decomposing it into Capability arguments. Use "
        "coverage=missing only when no candidate attempts the fragment and then use "
        "no candidate index. Use clarification_required only when supplied evidence "
        "cannot uniquely ground a material pronoun, demonstrative, ellipsis, "
        "correction, or other indirect reference. Do not plan, select Capabilities, "
        "execute, add Goals, or trust provider availability. Before returning, "
        "cross-check the JSON against reason_summary: when the reason says an effect "
        "is distinct, observable, standalone, independently satisfiable, or must have "
        "its own Goal/responsibility, that effect must appear in responsibility_items "
        "with role=responsibility and must not appear only in supporting_items. Return "
        "JSON only."
    )


def build_responsibility_coverage_prompt(
    *,
    request: CognitiveWorkRequest,
    raw: dict[str, Any],
) -> str:
    context = request.context if isinstance(request.context, dict) else {}
    raw_json = bounded_json(raw, 9000)
    if uses_compact_coverage_contract(request=request, raw=raw):
        return build_compact_responsibility_coverage_prompt(
            request=request,
            raw_json=raw_json,
        )
    responsibility_cross_check = [
        {
            "local_ref": item.local_ref,
            "outcome": item.outcome,
            "output_mode": item.output_mode,
        }
        for item in request.responsibilities
    ]
    return (
        "Audit whether this candidate Goal segmentation completely accounts for "
        "the authoritative user's current semantic responsibilities. This is an "
        "independent audit: candidate Goal wording is not evidence that the "
        "segmentation is complete by itself. Inspect the complete candidate DTO: "
        "description, output_mode, typed bindings, resource responsibility, and "
        "source/recipient fields are the evidence for what each candidate "
        "actually represents. Do not call a constraint missing when those fields "
        "materially preserve it on the Goal that it modifies.\n\n"
        "For each semantically material fragment of the current turn, emit one "
        "entry and copy source_excerpt as a verbatim contiguous span from "
        "the FINAL AUTHORITATIVE USER TURN. Use role=responsibility for a positive "
        "outcome Chromie owes, role=constraint for a modifier/prohibition/timing "
        "condition on such an outcome, role=context for reference/background that "
        "does not itself need completion, and role=framing for politeness or social "
        "preamble attached to substantive work. A stated preference, reason, "
        "candidate option, or background fact that changes what counts as a valid decision "
        "must be role=constraint and must map to the Goal whose result it constrains; "
        "it cannot be downgraded to context merely because it is not an independent "
        "outcome. Only incidental background that does not change valid completion is "
        "role=context. In particular, a reason or future event that merely explains "
        "why the requested answer will be useful is context when it does not alter "
        "the correctness or required shape of that answer. These facts are not "
        "independent responsibilities unless the user "
        "separately asks for an observable outcome for each. Stated preferences therefore "
        "remain material constraints when the user asks for a choice between them. A "
        "manner, mood, persona, or social-"
        "presentation modifier attached to a requested effect is role=constraint "
        "on that effect; it is not a second responsibility merely because speech "
        "could also convey the style. When a concrete effect is requested together "
        "with a broad desired social impression but no words, information, vocal "
        "performance, or second effect modality is specified, that impression is "
        "embodiment-wide framing on the concrete effect. Do not infer speech from "
        "an adjective, state directive, conjunction, or imperative grammar. Emit "
        "each semantic fragment once: never duplicate the same source_excerpt "
        "under both responsibility and constraint (or any other conflicting "
        "roles); decide its one actual role. Temporal wording is audited as a "
        "source-grounded constraint on the affected Goal. Preserve the human scope "
        "itself; do not require or infer provider date/day-part dimensions in this "
        "Goal-coverage stage. A duration remains a duration rather than becoming a "
        "calendar or local-day parameter.\n\n"
        "Set independently_satisfiable=true only when the user could reasonably "
        "judge that positive outcome completed even if sibling outcomes did not "
        "happen. A factual lookup and an interpretation requested from that same "
        "evidence form one responsibility when one result satisfies both. Multiple "
        "aspects requested from one information result likewise remain one "
        "responsibility when the same evidence satisfies them; answerable sub-aspects "
        "are not automatically independent outcomes. Represent their contiguous request as one "
        "responsibility and set independently_satisfiable=false. Every genuinely "
        "independently satisfiable responsibility must own its own "
        "Goal candidate. Do not collapse separately observable requested effects "
        "merely because they can overlap in time, share one sentence, or use a "
        "common provider. For acquire-and-deliver meaning, apply the inverse "
        "counterfactual too: navigation, distance, direction, locating, pickup, "
        "carrying, return, and handoff are not independent positive outcomes when "
        "the person would consider them satisfied by successful resource delivery "
        "and would not still require that stage for its own sake. In that case map "
        "the material fragment as a constraint on the one resource responsibility, "
        "not as ownership evidence for another Goal. Conversely, do "
        "not promote greeting/politeness framing, implementation steps, result "
        "delivery, or a negative speech boundary into a separate Goal.\n\n"
        "For coverage=covered, map a responsibility to exactly one candidate Goal "
        "index; a constraint may map to one or more affected Goal indices. Use "
        "coverage=missing only when a responsibility or constraint has no Goal "
        "candidate attempting to own it, and then candidate_goal_indices must be empty. "
        "If a candidate attempts to own the fragment but drops or generalizes a material "
        "qualifier, binding, result aspect, severity/intensity, threshold, subtype, "
        "comparison, or scope, use coverage=representation_mismatch and include that "
        "candidate index instead. Use clarification_required only when GI's supplied "
        "unresolved-meaning evidence says the human-level responsibility cannot be "
        "fully determined without asking the user; map it to the one provisional Goal "
        "that preserves that Responsibility. Context and framing "
        "acknowledge non-owed meaning rather than requiring ownership: they must "
        "always use coverage=covered, independently_satisfiable=false, and an "
        "empty candidate_goal_indices list. Never mark context or framing as "
        "missing. For a represented constraint, the expected shape is "
        "role=constraint, independently_satisfiable=false, coverage=covered, and "
        "the affected Goal index or indices. Never mark a constraint missing "
        "merely because it is not a responsibility, has no separate Goal, or is "
        "an instrumental provider stage; mark it missing only when no candidate "
        "DTO field preserves it on the outcome that it modifies. Coverage also "
        "requires the candidate's output_mode, resource shape, and observable "
        "completion meaning to match the requested responsibility. Use "
        "coverage=representation_mismatch when a state mutation or deferred effect "
        "(recording/updating something, scheduling a future notification, or sending "
        "something later) is represented as an information resource, when provider-"
        "backed evidence work is represented as ordinary speech, or when immediate "
        "reasoning/advice with no fresh evidence need is represented as external "
        "information acquisition. Also use representation_mismatch when an ordinary "
        "authored conversational response—such as greeting, empathy, reassurance, "
        "restatement, or acknowledgement of the person's feeling—is represented as "
        "capability_work or body_action. Preserve speaker and experiencer ownership; "
        "the person's first-person state never authorizes a robot effect. If the user "
        "asks what Chromie just said, the candidate must make Chromie repeat or "
        "summarize the supplied assistant utterance; a candidate that instead asks "
        "the user to repeat reverses speaker and addressee and is a representation "
        "mismatch. Every responsibility item must set required_goal_shape: "
        "information_resource for acquiring grounded external/private/runtime information, "
        "physical_resource for acquiring and handing over an object, persistent_effect "
        "for a deferred or state-changing Capability outcome, and ordinary otherwise. "
        "Only role=responsibility classifies the Goal shape. Every constraint, "
        "context, and framing item must set required_goal_shape=ordinary even when "
        "it modifies a non-ordinary Goal; map it to that Goal with candidate indices "
        "instead of repeating the Goal-shape classification. "
        "Every information_resource responsibility must also set exactly one "
        "required_information_domain: local_clock for Chromie's trusted current "
        "date/time, weather_forecast for weather, external_grounded_information "
        "for public facts/research, direct_environment_perception for current "
        "nearby people/objects/events, or private_runtime_information for other "
        "private live state. All non-information items must use none. Judge the "
        "needed evidence domain from the authoritative turn, never from currently "
        "available Capabilities or Agent Skills. A weather provider cannot turn a "
        "person-presence question into weather. "
        "A covered item is invalid when the typed candidate lacks that declared shape. "
        "Speech cannot cover requested body motion, media "
        "control, external evidence work, or a vocal performance. Every Goal "
        "candidate must be "
        "justified by at least one covered role=responsibility item; a constraint "
        "alone never justifies another Goal. Do not author a top-level verdict or "
        "unjustified-candidate inventory; trusted code derives both from the item "
        "judgments. A resource Goal's nested typed resource fields are authoritative; "
        "its human-readable description cannot supply or override a missing resource "
        "fact, and a material contradiction between summary and typed truth is not "
        "covered. For an information resource, requested location, time, and result "
        "aspects are covered only by resource_responsibility.query_scope; its narrow "
        "source object cannot own those query facts. Reject invented query "
        "dimensions too: every query_scope item must be entailed by the final user "
        "turn, supplied Responsibility bindings, or a resolved discourse referent. "
        "A guessed current location, timezone, provider prerequisite, placeholder, "
        "device, or source is a representation_mismatch even when it is called "
        "unspecified or copied from a larger non-location clause. Audit every "
        "supplied temporal scope as source-grounded human meaning. For an information "
        "Goal, resource_responsibility.query_scope must retain that scope without "
        "silently narrowing, translating, or converting it into provider arguments. "
        "A compound natural expression may remain one temporal_scope binding. If the "
        "candidate drops or changes that human scope, use coverage=representation_mismatch. "
        "For a physical resource, an "
        "acquisition location, distance, direction, or route constraint is covered "
        "only by resource_responsibility.source.acquisition_bindings. Descriptions "
        "are summary only. The schema deliberately exposes one writable owner per "
        "resource fact, so coverage must never infer a missing typed fact from prose. "
        "Classify the meaning in context; "
        "do not decide its role from a field name alone.\n\n"
        "Reference grounding is part of responsibility coverage. Before assigning "
        "coverage, explicitly identify each material indirect referring expression "
        "in the authoritative turn and audit its grounding independently. A material "
        "pronoun, demonstrative, ellipsis, correction, or other indirect "
        "reference is covered only when the candidate copies an explicit current-"
        "turn value or a supplied discourse referent with its referent_id. A "
        "candidate description that silently invents a generic object, device, "
        "person, task, or setting does not resolve the reference. Mark the "
        "containing responsibility or constraint clarification_required when the "
        "supplied evidence does not select exactly one meaning, including when "
        "multiple scene candidates remain plausible. Candidate prose alone cannot "
        "ground an indirect target; require the explicit current-turn value or the "
        "typed referent-backed binding before marking it covered.\n\n"
        "Do not add, remove, rename, plan, execute, or complete Goals. Do not use "
        "provider availability to decide whether a responsibility exists. An "
        "unavailable requested effect remains a responsibility. Cross-check every "
        "source-grounded authoritative GI Responsibility before returning: each "
        "positive effect entailed by the final turn needs a role=responsibility owner, "
        "even when it shares a coordinated clause or no provider can perform it.\n\n"
        "Authoritative Responsibility cross-check list (audit every entry against "
        "the source; do not silently omit an entry from the certificate):\n"
        f"{bounded_json(responsibility_cross_check, 2200)}\n\n"
        "Put every positive-outcome role=responsibility entry in the required "
        "responsibility_items array. Set independently_satisfiable=true only when "
        "that outcome can stand as a sibling Goal; one resource lookup whose "
        "requested judgment depends on the same result may remain false. Put "
        "role=constraint, context, and framing entries in supporting_items. Once independently observable component "
        "Responsibilities have been enumerated, never add the whole compound "
        "sentence as another Responsibility; coordination is not another outcome. "
        "For coordination grammar in any language, split the smallest exact "
        "contiguous source spans so each positive effect remains in "
        "responsibility_items; supporting_items may contain only the relation, order, "
        "or manner that modifies those effects. "
        "Every candidate Goal index must have a "
        "covered responsibility owner. Never return only constraints, even when "
        "the constraints are represented correctly. Keep a positive outcome and "
        "its temporal, location, manner, or prohibition constraints in separate audit "
        "entries when the source grammar permits, but never decompose one human "
        "temporal expression into Capability-facing fields. Also reject your own draft when reason_summary calls an "
        "effect distinct, observable, standalone, independently satisfiable, or in "
        "need of its own Goal/responsibility but the JSON places that effect only in "
        "supporting_items. The structured arrays, role, and coverage must express the "
        "same conclusion as reason_summary.\n\n"
        "Candidate Goal DTO JSON:\n"
        f"{bounded_json(raw, 9000)}\n\n"
        "Authoritative Responsibility evidence JSON (query facts may be "
        "normalized but never invented beyond this evidence and the final turn):\n"
        f"{bounded_json([item.model_dump(mode='json', exclude_none=True) for item in request.responsibilities], 3200)}\n\n"
        "GI unresolved-meaning evidence (the only authority for "
        "clarification_required coverage):\n"
        f"{bounded_json(request.interpretation_unresolved, 1600)}\n\n"
        "Recent conversation JSON (reference context only; current-turn Goal "
        "coverage must still be anchored by source_excerpt from the final turn):\n"
        f"{bounded_json((context.get('history') or request.history or [])[-6:], 3000)}\n\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
    )


def uses_compact_coverage_contract(
    *,
    request: CognitiveWorkRequest,
    raw: dict[str, Any],
) -> bool:
    """Select the bounded one-Responsibility transport shape mechanically."""

    context = request.context if isinstance(request.context, dict) else {}
    history = (context.get("history") or request.history or [])[-6:]
    return bool(
        len(request.responsibilities) == 1
        and not request.interpretation_unresolved
        and not history
        and not discourse_referents(request)
        and len(bounded_json(raw, 9000)) <= 2500
    )


def build_compact_responsibility_coverage_prompt(
    *,
    request: CognitiveWorkRequest,
    raw_json: str,
) -> str:
    """Audit one bounded, reference-free Responsibility without prompt repetition."""

    responsibility_json = bounded_json(
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in request.responsibilities
        ],
        3200,
    )
    return (
        "Independently audit the candidate DTO against the final user turn and GI "
        "Responsibility evidence. Emit each material source fragment exactly once. "
        "Every source_excerpt must be copied from an exact contiguous span of the "
        "FINAL AUTHORITATIVE USER TURN in its original language; never copy a "
        "translated or paraphrased Responsibility outcome or binding. "
        "Use role=responsibility only for the positive outcome Chromie owes. A "
        "duration, distance, direction, speed, location, order, simultaneity, manner, "
        "prohibition, temporal scope, threshold, comparison, severity, preference, or "
        "answer-shaping detail is role=constraint on that outcome and must set "
        "independently_satisfiable=false. Duration is never a second outcome. Stated "
        "preferences that changes what counts as a valid decision must be "
        "role=constraint. A reason or future event that merely explains why the "
        "requested answer is useful, without changing which answer is correct, is "
        "role=context, coverage=covered, and owns no Goal. Context and framing are "
        "not owed outcomes. Multiple aspects "
        "requested from one information result likewise remain one responsibility. "
        "Never duplicate the same span under conflicting roles. This role split "
        "describes the certificate, not separate Goal candidates: a constraint "
        "belongs on the same candidate as the responsibility it modifies. Inspect "
        "the candidate's typed bindings as authoritative candidate evidence. Mark "
        "a constraint covered when one of those bindings preserves its meaning, "
        "including an equivalent normalized value from the supplied Responsibility "
        "evidence. Do not report representation_mismatch merely because the "
        "modifier also appears in the candidate description or has no separate "
        "Goal; those are correct for a non-independent constraint.\n\n"
        "For coverage=covered, a responsibility maps to exactly one candidate index; "
        "a represented constraint maps to the affected candidate. If nothing attempts "
        "a material fragment use coverage=missing and candidate_goal_indices must be "
        "empty. If a candidate attempts it but drops or generalizes a material "
        "qualifier, binding, scope, threshold, or completion meaning, use "
        "coverage=representation_mismatch and include its index. "
        "clarification_required is allowed only from supplied GI unresolved evidence "
        "(none is supplied here). Every candidate must have one covered positive "
        "responsibility owner. Never return only constraints.\n\n"
        "Set required_output_mode to the exact requested modality and require an exact "
        "candidate output_mode match. Set required_goal_shape to information_resource "
        "for fresh information, physical_resource for acquiring and handing over a "
        "distinct concrete object, persistent_effect for deferred/state-changing "
        "work, and ordinary otherwise. Non-responsibility items always use ordinary. "
        "A state mutation or deferred effect represented as information, ordinary "
        "dialogue represented as capability work, or body motion represented as a "
        "physical object is a representation_mismatch. For information, set exact "
        "required_information_domain; non-information uses none. requested location, "
        "time, and result aspects are covered only by "
        "resource_responsibility.query_scope. Physical acquisition location, distance, "
        "direction, and route are covered only by source.acquisition_bindings. Prose "
        "cannot replace a typed fact. A temporal constraint is covered when the Goal "
        "preserves its source-grounded human scope; do not require date/period fields "
        "that belong to a later Capability realization.\n\n"
        "Reference grounding is part of responsibility coverage. Candidate prose that "
        "silently invents a generic object does not ground a reference; use "
        "clarification_required when multiple scene candidates remain plausible. No "
        "indirect-reference evidence is supplied in this bounded request.\n\n"
        "Put positive outcomes in responsibility_items and constraints/context/framing "
        "in supporting_items. Include required_goal_shape, "
        "required_information_domain, required_output_mode, exact verbatim contiguous "
        "source_excerpt, coverage, independently_satisfiable, and candidate_goal_indices. "
        "Before returning, audit field consistency: every positive outcome that can "
        "stand alone uses independently_satisfiable=true; each modifier uses the "
        "smallest distinct contiguous source span available; and every "
        "non-responsibility uses required_output_mode=none. "
        "Return the certificate JSON only.\n\n"
        "Candidate Goal DTO JSON:\n"
        f"{raw_json}\n\n"
        "Authoritative Responsibility evidence JSON:\n"
        f"{responsibility_json}\n\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
    )


def semantic_review_system_prompt(
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    *,
    fresh_resegmentation: bool = False,
) -> str:
    contract_name = (
        "Goal Segmentation"
        if output_type is GoalSegmentationModelOutput
        else "Goal Association"
    )
    return (
        f"You are Chromie's independent semantic reviewer for the "
        f"{contract_name} boundary. "
        + (
            "Perform a fresh segmentation from the authoritative user turn; "
            "no earlier Goal labels are evidence and none are available to copy. "
            if fresh_resegmentation
            else "Review the supplied DTO without assuming it is correct. "
        )
        + "Decide with model reasoning whether responsibilities are genuinely "
        "independent and classify each by its completion channel. An authored "
        "vocal performance belongs to vocal_output even when coordinated "
        "with embodied work. Return only the complete final DTO as JSON. The "
        "Host owns validation, IDs, lifecycle, and persistence and does not make "
        "this semantic choice."
    )


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
        f"You repair one minimal {contract_name} semantic DTO using semantic reasoning and the supplied exact JSON Schema. "
        "Return only the corrected JSON object. Do not add commentary, markdown, lexical mappings, or hidden reasoning."
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
