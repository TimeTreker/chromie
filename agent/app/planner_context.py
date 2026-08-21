from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.goal import GoalAssociationResolution
    from chromie_contracts.interaction import MEDIA_CAPABILITY_IDS
    from chromie_contracts.situation import SituationProjection
    from chromie_contracts.tool_result import ToolResultEvidence
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.goal import GoalAssociationResolution
    from shared.chromie_contracts.interaction import MEDIA_CAPABILITY_IDS
    from shared.chromie_contracts.situation import SituationProjection
    from shared.chromie_contracts.tool_result import ToolResultEvidence

def goal_association_prompt_projection(
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the closed Goal Association projection permitted in prompts.

    The maintained runtime supplies a validated ``GoalAssociationResolution``.
    Tests and compatibility callers may provide an older partial dictionary, so
    the dictionary path uses the same explicit allowlist without inventing
    missing fields or accepting diagnostic metadata.
    """

    raw = (context or {}).get("goal_association_resolution")
    if raw is None:
        return {}
    if isinstance(raw, GoalAssociationResolution):
        return raw.prompt_projection()
    if not isinstance(raw, dict):
        raise ValueError("goal_association_resolution must be an object")

    top_level_keys = (
        "schema_version",
        "turn_id",
        "confidence",
        "reason_summary",
    )
    association_keys = (
        "schema_version",
        "association_id",
        "relationship",
        "target_goal_ids",
        "confidence",
        "reason_summary",
        "ambiguity_summary",
        "goal_update",
        "resolved_gap_ids",
    )
    goal_keys = (
        "schema_version",
        "goal_id",
        "version",
        "description",
        "source_text",
        "beneficiary",
        "object",
        "constraints",
        "success_criteria",
        "resource_responsibility",
    )
    projection = {key: copy.deepcopy(raw[key]) for key in top_level_keys if key in raw}
    projection["associations"] = [
        {key: copy.deepcopy(item[key]) for key in association_keys if key in item}
        for item in raw.get("associations") or []
        if isinstance(item, dict)
    ]
    goals: list[dict[str, Any]] = []
    for item in raw.get("new_goals") or []:
        if not isinstance(item, dict):
            continue
        goal = {key: copy.deepcopy(item[key]) for key in goal_keys if key in item}
        metadata = item.get("metadata")
        projected_metadata = (
            {
                key: copy.deepcopy(metadata[key])
                for key in (
                    "responsibility_kind",
                    "execution_lane",
                    "output_mode",
                    "provider_required",
                )
                if key in metadata
            }
            if isinstance(metadata, dict)
            else {}
        )
        if projected_metadata:
            goal["metadata"] = projected_metadata
        goals.append(goal)
    projection["new_goals"] = goals
    referent_keys = (
        "schema_version",
        "referent_id",
        "entity_type",
        "canonical_value",
        "aliases",
        "scope_kind",
        "scope_ids",
        "status",
        "confidence",
        "source_turn_id",
        "source_goal_ids",
        "supersedes_referent_ids",
        "reason_summary",
    )
    update_keys = (
        "operation",
        "target_referent_ids",
        "confidence",
        "reason_summary",
    )
    referent_updates: list[dict[str, Any]] = []
    for item in raw.get("referent_updates") or []:
        if not isinstance(item, dict):
            continue
        update = {key: copy.deepcopy(item[key]) for key in update_keys if key in item}
        referent = item.get("referent")
        if isinstance(referent, dict):
            update["referent"] = {
                key: copy.deepcopy(referent[key]) for key in referent_keys if key in referent
            }
        referent_updates.append(update)
    projection["referent_updates"] = referent_updates
    resolved_reference_keys = (
        "surface_form",
        "entity_type",
        "resolved_value",
        "source",
        "referent_id",
        "confidence",
        "reason_summary",
    )
    projection["resolved_references"] = [
        {key: copy.deepcopy(item[key]) for key in resolved_reference_keys if key in item}
        for item in raw.get("resolved_references") or []
        if isinstance(item, dict)
    ]
    serialized = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(serialized) > 65_536:
        raise ValueError("Goal Association prompt projection exceeds 65536 UTF-8 bytes")
    return projection

def expected_goal_ids(context: dict[str, Any] | None) -> list[str]:
    """Return the ordered canonical goal IDs accepted by Goal Association."""

    association = (context or {}).get("goal_association_resolution")
    if not isinstance(association, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = " ".join(str(value or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)

    for item in association.get("associations") or []:
        if not isinstance(item, dict):
            continue
        for goal_id in item.get("target_goal_ids") or []:
            add(goal_id)
    for item in association.get("new_goals") or []:
        if isinstance(item, dict):
            add(item.get("goal_id"))
    return ordered

def canonical_goal_grounding(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build a compact immutable grounding block for planner prompts.

    Goal Association owns which goals exist. Planners receive only those IDs and
    their human-facing semantics; internal implementation concepts are omitted.
    """

    context = context or {}
    association = context.get("goal_association_resolution")
    active = [
        *(context.get("active_goal_snapshots") or []),
        *(context.get("recent_goal_snapshots") or []),
    ]
    active_by_id: dict[str, dict[str, Any]] = {}
    for item in active:
        if not isinstance(item, dict):
            continue
        goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        if goal_id:
            active_by_id[goal_id] = {
                "goal_id": goal_id,
                "description": goal.get("description") or item.get("last_user_update") or "",
                "source_text": goal.get("source_text") or item.get("last_user_update") or "",
                "constraints": goal.get("constraints") or {},
                "success_criteria": goal.get("success_criteria") or [],
                "object": goal.get("object") or {},
                **(
                    {
                        "resource_responsibility": goal[
                            "resource_responsibility"
                        ]
                    }
                    if isinstance(goal.get("resource_responsibility"), dict)
                    and goal["resource_responsibility"]
                    else {}
                ),
                "metadata": goal.get("metadata") or {},
            }

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(association, dict):
        for item in association.get("associations") or []:
            if not isinstance(item, dict):
                continue
            for raw_id in item.get("target_goal_ids") or []:
                goal_id = " ".join(str(raw_id or "").strip().split())
                if goal_id and goal_id not in seen:
                    seen.add(goal_id)
                    result.append(active_by_id.get(goal_id, {"goal_id": goal_id}))
        for item in association.get("new_goals") or []:
            if not isinstance(item, dict):
                continue
            goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
            if not goal_id or goal_id in seen:
                continue
            seen.add(goal_id)
            result.append(
                {
                    "goal_id": goal_id,
                    "description": item.get("description") or "",
                    "source_text": item.get("source_text") or "",
                    "constraints": item.get("constraints") or {},
                    "success_criteria": item.get("success_criteria") or [],
                    "object": item.get("object") or {},
                    **(
                        {
                            "resource_responsibility": item[
                                "resource_responsibility"
                            ]
                        }
                        if isinstance(item.get("resource_responsibility"), dict)
                        and item["resource_responsibility"]
                        else {}
                    ),
                    "metadata": item.get("metadata") or {},
                }
            )
    return result

def _goal_execution_metadata(goal: dict[str, Any]) -> tuple[str, str, bool]:
    metadata = goal.get("metadata")
    if not isinstance(metadata, dict):
        return "", "", False
    return (
        str(metadata.get("responsibility_kind") or "").strip(),
        str(metadata.get("output_mode") or "").strip(),
        bool(metadata.get("provider_required")),
    )

def planner_response_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return direct Vocal Goals completed by ordinary authored speech.

    Mode-specific vocal performance is deliberately excluded.  It remains in
    the Vocal lane but requires exact provider evidence and cannot be closed
    by a generic ``respond`` outcome.
    """

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        if (
            goal_id
            and responsibility_kind == "vocal_output"
            and output_mode in {"", "speech"}
            and not provider_required
        ):
            result.add(goal_id)
    return result

def planner_effectful_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Goals that require provider evidence or an explicit terminal block.

    Goal Association already owns these typed responsibility declarations.  The
    validator does not infer an effect from user wording or select a Capability;
    it only prevents a planner from declaring such a Goal satisfied through an
    ordinary response while emitting no executable work.
    """

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        if not goal_id or not isinstance(metadata, dict):
            continue
        responsibility_kind = str(
            metadata.get("responsibility_kind") or ""
        ).strip()
        if (
            responsibility_kind in {"executable_action", "capability_dependent"}
            or bool(metadata.get("provider_required"))
        ):
            result.add(goal_id)
    return result

def planner_goal_execution_requirements(
    authoritative_goals: list[dict[str, Any]],
) -> tuple[bool, bool]:
    """Derive Planner execution shape only from canonical Goal semantics.

    Goal Interpretation is provider-neutral WHAT evidence and must
    never grant or suppress executable capability access. Goal Association owns the
    typed completion contract; planners may tighten their decoder surface from that
    canonical truth only.

    Returns ``(response_only, requires_execution)``. ``requires_execution`` is the
    decoder-tightening flag for canonical ``capability_dependent`` work (the semantic
    successor to the old tool route). Other provider-backed Activity/Vocal Goals retain
    the normal mixed-response schema and are still enforced by Goal outcome validation.
    """

    goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
    }
    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    capability_work_goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and isinstance(goal.get("metadata"), dict)
        and str(goal["metadata"].get("responsibility_kind") or "").strip()
        == "capability_dependent"
    }
    response_only = bool(goal_ids) and goal_ids.issubset(response_goal_ids)
    requires_execution = bool(capability_work_goal_ids)
    return response_only, requires_execution

def planner_provider_vocal_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Vocal Goals that require mode-specific provider evidence."""

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        if (
            goal_id
            and responsibility_kind == "vocal_output"
            and output_mode not in {"", "speech"}
            and provider_required
        ):
            result.add(goal_id)
    return result

def planner_provider_media_goal_operations(
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, str]:
    """Return exact media lifecycle operations owned by Activity Goals."""

    result: dict[str, str] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        metadata = goal.get("metadata")
        operation = (
            str(metadata.get("media_operation") or "").strip() if isinstance(metadata, dict) else ""
        )
        if (
            goal_id
            and responsibility_kind == "executable_action"
            and output_mode == "media_playback"
            and provider_required
        ):
            if operation not in MEDIA_CAPABILITY_IDS:
                raise ValueError(f"media_playback Goal requires exact media_operation: {goal_id}")
            result[goal_id] = operation
    return result

def result_evidence_reentry_goal_ids(
    context: dict[str, Any] | None,
) -> set[str]:
    """Return Goals bound to Host-admitted terminal tool Evidence.

    This boundary validates the immutable evidence DTO and its correlation refs;
    it never interprets result content or decides response wording.  It gives the
    same Planner that requested the work permission to answer the exact Goals
    after Trusted Capability Runtime has returned their evidence.
    """

    if not isinstance(context, dict):
        return set()
    reentry = context.get("result_evidence_reentry")
    raw_evidence = context.get("trusted_terminal_evidence")
    if not isinstance(reentry, dict) or not isinstance(raw_evidence, list):
        return set()
    try:
        evidence = [ToolResultEvidence.model_validate(item) for item in raw_evidence]
    except (ValidationError, ValueError, TypeError):
        return set()
    if not evidence:
        return set()
    evidence_ids = {item.evidence_id for item in evidence}
    referenced_ids = {
        normalized
        for value in reentry.get("evidence_refs") or []
        if (normalized := " ".join(str(value or "").strip().split()))
    }
    if referenced_ids and not referenced_ids.issubset(evidence_ids):
        return set()
    return {
        normalized
        for value in reentry.get("source_goal_ids") or []
        if (normalized := " ".join(str(value or "").strip().split()))
    }

def situation_prompt_projection(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return only a validated bounded Situation projection for model prompts."""

    current = context if isinstance(context, dict) else {}
    raw = current.get("situation")
    if not isinstance(raw, dict):
        return {}
    try:
        return SituationProjection.model_validate(raw).prompt_projection()
    except ValidationError:
        return {}

def evidence_bound_dialogue(
    context: dict[str, Any] | None,
    *,
    fallback_history: list[dict[str, Any]] | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Return delivered, Host-marked post-execution speech for Goal continuity."""

    context = context or {}
    history = context.get("history")
    if not isinstance(history, list):
        history = fallback_history if isinstance(fallback_history, list) else []
    out: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if (
            metadata.get("evidence_bound") is not True
            or str(metadata.get("source") or "").strip()
            != "evidence_bound_tool_result_interpretation"
        ):
            continue
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue
        out.append(
            {
                "text": text[:1200],
                "source_goal_ids": [
                    normalized
                    for value in metadata.get("source_goal_ids") or []
                    if (normalized := " ".join(str(value or "").strip().split()))
                ][:8],
                "canonical_plan_id": str(metadata.get("canonical_plan_id") or "")[:200],
                "source": "evidence_bound_tool_result_interpretation",
            }
        )
    return out[-max(1, int(limit)) :]
