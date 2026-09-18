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
    """Expose exact source evidence while keeping UMI/GA authority explicit."""

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
        "IMMUTABLE SOURCE TURN JSON (read-only; UMI Responsibilities own "
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


def build_segmentation_prompt(request: CognitiveWorkRequest) -> str:
    """No candidate Goals: preserve each supplied goal-scoped intent in one new Goal."""
    return build_association_prompt(request, [])


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
    request: CognitiveWorkRequest, candidate_goals: list[dict[str, Any]],
) -> str:
    """UMI owns meaning; GA chooses canonical identity and continuity only."""
    return (
        "Associate the complete accepted UMI Responsibilities with the supplied bounded "
        "candidate Goals. Runtime supplies only Responsibilities whose continuity_scope is "
        "goal. Every supplied Responsibility ref must occur exactly once across associations "
        "and new_goals. Never invent a Goal for turn-local conversation. Preserve compound "
        "meaning intact; Planner decomposes Activities. "
        "Choose continuity from accepted meaning, candidate requirements, retained state and "
        "dialogue. Candidate presence, lexical overlap or recency alone is insufficient. "
        "Candidates may include restored cross-session persistent Goals; their presence only "
        "makes them eligible for comparison. GA alone decides canonical continuity identity. "
        "UMI does not supply relationship labels or Goal IDs; you own that judgment. "
        "Use exact supplied IDs. Only candidates with responsibility_status=open may "
        "receive continue/modify/clarify/confirm/reject/cancel/pause/resume/merge/split. "
        "A retained non-open Goal is historical continuity evidence only: it may be "
        "targeted by relationship=reference for retrieval/restatement/explanation/comparison, "
        "but it must never absorb a fresh Responsibility or be reopened. An independent "
        "current obligation becomes a new Goal even when a terminal Goal is nearby in time. "
        "For changed requirements, select the exact target and replaced requirement indices; "
        "Host inherits complete new requirements from cited UMI outcomes. Keep unrelated "
        "retained requirements. Supersede a Goal only when accepted meaning explicitly "
        "replaces it; an additional Responsibility leaves it intact. A replaced Goal must "
        "not also be listed as related context. "
        "No candidates means new_goals only. Emit source_responsibility_refs, related_goal_ids "
        "and supersedes_goal_ids for each new Goal. Host supplies descriptions and IDs. "
        "Host inherits UMI's expected result type unchanged. Do not extract duration, "
        "direction, count, speed, resource fields, or reclassify output modes or other "
        "execution details. Planner owns parameter realization and Work. "
        "A UMI meaning uncertainty is not a request to ask the user. You may list its exact "
        "local_ref in resolved_meaning_uncertainty_refs only when the selected canonical "
        "Goal itself supplies the missing continuity meaning for every cited Responsibility. "
        "Never resolve uncertainty from lexical similarity, general memory, guessed intent, "
        "external facts, or execution assumptions. Leave every other uncertainty unresolved; "
        "later cognition decides whether clarification is actually required. SC owns wording. "
        "Return the supplied schema only.\n\n"
        "Candidate Goal evidence JSON:\n"
        + required_json(association_goal_projection(candidate_goals), None, label="Goal requirement evidence")
        + "\nUMI Responsibilities JSON:\n"
        + required_json([
            {"local_ref": item.local_ref, "outcome": item.outcome,
             "confidence": item.confidence, "output_mode": item.output_mode,
             "continuity_scope": item.continuity_scope,
             "source_evidence": item.source_evidence.model_dump() if item.source_evidence else None}
            for item in request.responsibilities
        ], None, label="UMI Responsibility evidence")
        + "\nUMI semantic uncertainty JSON:\n" + bounded_json([item.model_dump(mode="json") for item in request.meaning_uncertainties], 1600)
        + "\nScoped discourse referents JSON:\n" + bounded_json(discourse_referents(request), 1400)
        + "\nAccepted dialogue JSON:\n"
        + bounded_json(association_dialogue_projection(request.history or request.context.get("history") or []), 1400)
        + "\n" + immutable_source_turn_prompt(request)
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
        "ownership, source Responsibility refs, target Goal IDs, requirement changes, "
        "output modes, bindings and values, resource meaning, referent choices, "
        "confidence, and rationale. Do not re-read or reinterpret the user, "
        "re-segment Responsibilities, add or remove a Goal, choose a different "
        "continuity relation, or repair a grounding/conservation judgment. Make only "
        "mechanical JSON-contract corrections identified by the validation errors, "
        "limited to wrapping an existing object in a singleton array or unwrapping "
        "a singleton object array where that exact container is required. Preserve "
        "all fields, values, array order, and cardinality. Never remove unknown keys, "
        "invent missing fields, replace null/scalar content, or change wording. If the "
        "object cannot satisfy the schema without changing semantics, do not invent "
        "replacement meaning; trusted validation will fail closed. Return exactly "
        "one JSON object and no commentary.\n\n"
        "Previous model output JSON:\n"
        f"{required_json(raw, 7000, label='GA primary result for mechanical repair')}\n\n"
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
    rendered = identity_world + "\n".join(identity_contracts) + "\n" + role_memory_context(context, role="ga") + build_prompt(
        request,
        candidate_goals,
        output_type=output_type,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=identity_contracts,
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
            "Preserve each supplied goal-scoped UMI Responsibility as one new Goal, including compound intent. UMI owns current-turn meaning; do not resegment it or resolve its uncertainty. "
            "Conversational framing attached to a substantive responsibility is not independently satisfiable work: do not create a separate Goal for its greeting or politeness preamble. Turn-local conversational Responsibilities are handled by Social Cognition and must not be supplied here. "
            "When one evidence acquisition satisfies both a factual lookup and the requested interpretation of its result, preserve them as one Goal. "
            "Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
            "You are advisory only and never execute or commit. Return JSON only."
        )
    return (
        "You are Chromie's Goal Association and Segmentation model. Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
        "Produce one complete candidate-aware result; existing-Goal associations and independent new Goals may coexist in that result. "
        "Apply continuity before creation. Resolve references from current user meaning, scoped discourse referents/focus, bounded candidate Goals and their bindings, and dialogue context. Candidate Goals may be active, recoverable, or recently terminal. Only responsibility_status=open candidates may receive a continuity-changing relationship; a non-open retained Goal supports relationship=reference only and must never be reopened. A fresh unrelated Responsibility becomes a new Goal even when a recent terminal Goal exists. Tool-result memory is not reference-resolution authority. Status follow-ups about an unfinished lookup should associate with the bound task; if its safe read is recoverable, preserve the exact skill arguments for retry. Do not treat another task's evidence as completion. "
        "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
        "Preserve UMI Responsibility ownership, including compound intent; do not resegment, reclassify or repair its meaning. Planner decomposes Activities. "
        "Conversational framing attached to substantive work is not a separate Goal. Turn-local conversation never reaches GA. A new goal-scoped reaction, evaluation, or practical decision after a prior result is a new current responsibility rather than continuation of the completed lookup. One lookup and an interpretation requested as part of that same lookup are one Goal. "
        "You are advisory only and never execute or commit. Return JSON only."
    )
