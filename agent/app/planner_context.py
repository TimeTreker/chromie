from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.core_interpretation import PlannerReentryScope
    from chromie_contracts.control import GoalCancellationEvidence
    from chromie_contracts.goal import GoalAssociationResolution
    from chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        reject_forbidden_low_level_fields,
    )
    from chromie_contracts.situation import SituationProjection
    from chromie_contracts.tool_result import ToolResultEvidence
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import PlannerReentryScope
    from shared.chromie_contracts.control import GoalCancellationEvidence
    from shared.chromie_contracts.goal import GoalAssociationResolution
    from shared.chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        reject_forbidden_low_level_fields,
    )
    from shared.chromie_contracts.situation import SituationProjection
    from shared.chromie_contracts.tool_result import ToolResultEvidence


def goal_association_prompt_projection(
    context: dict[str, Any] | None,
    *,
    goal_ids: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Return the closed Goal Association projection permitted in prompts.

    The maintained runtime may supply either a validated ``GoalAssociationResolution``
    or its serialized context dictionary.  The dictionary path uses the same explicit
    allowlist without inventing missing fields or accepting diagnostic metadata.
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
                    "output_mode",
                    "media_operation",
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
    if goal_ids is not None:
        allowed = {
            " ".join(str(goal_id or "").strip().split())
            for goal_id in goal_ids
            if " ".join(str(goal_id or "").strip().split())
        }
        scoped_associations: list[dict[str, Any]] = []
        for item in projection["associations"]:
            target_goal_ids = [
                goal_id
                for value in item.get("target_goal_ids") or []
                if (goal_id := " ".join(str(value or "").strip().split())) in allowed
            ]
            goal_update = item.get("goal_update")
            update_goal_id = (
                " ".join(str(goal_update.get("goal_id") or "").strip().split())
                if isinstance(goal_update, dict)
                else ""
            )
            if not target_goal_ids and update_goal_id not in allowed:
                continue
            scoped = copy.deepcopy(item)
            scoped["target_goal_ids"] = target_goal_ids
            if update_goal_id and update_goal_id not in allowed:
                scoped.pop("goal_update", None)
            scoped_associations.append(scoped)
        projection["associations"] = scoped_associations
        projection["new_goals"] = [
            item
            for item in projection["new_goals"]
            if " ".join(str(item.get("goal_id") or "").strip().split()) in allowed
        ]
        projection["referent_updates"] = [
            item
            for item in projection["referent_updates"]
            if isinstance(item.get("referent"), dict)
            and allowed.intersection(
                " ".join(str(value or "").strip().split())
                for value in item["referent"].get("source_goal_ids") or []
            )
        ]
        projection["resolved_references"] = []
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
                    {"resource_responsibility": goal["resource_responsibility"]}
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
                        {"resource_responsibility": item["resource_responsibility"]}
                        if isinstance(item.get("resource_responsibility"), dict)
                        and item["resource_responsibility"]
                        else {}
                    ),
                    "metadata": item.get("metadata") or {},
                }
            )
    return result


def _goal_output_mode(goal: dict[str, Any]) -> str:
    metadata = goal.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("output_mode") or "").strip()


def planner_response_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Goals whose requested WHAT is ordinary authored speech."""

    return {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and _goal_output_mode(goal) == "speech"
    }


def planner_effectful_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return WHAT modalities that cannot be completed by ordinary response text.

    This is a Planner-side projection from canonical human-outcome modality, not a
    Goal-Association execution declaration. Information is deliberately excluded:
    Planner may answer it from supplied trusted context/evidence or may plan fresh
    acquisition when the current state requires that.
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
    }
    return {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and _goal_output_mode(goal) in effect_modes
    }


def planner_goal_execution_requirements(
    authoritative_goals: list[dict[str, Any]],
) -> tuple[bool, bool]:
    """Derive only decoder shape that follows mechanically from canonical WHAT.

    Ordinary speech-only Goals need no Capability surface. A durable/future
    ``stateful_effect`` cannot be satisfied by saying something now, so its planner
    schema requires an executable or explicit blocked outcome. Information remains a
    mixed case: current trusted context may already satisfy it, otherwise Planner may
    select fresh information Work.
    """

    goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
    }
    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    stateful_goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and _goal_output_mode(goal) == "stateful_effect"
    }
    response_only = bool(goal_ids) and goal_ids.issubset(response_goal_ids)
    requires_execution = bool(stateful_goal_ids)
    return response_only, requires_execution


def recoverable_result_reentry_goal_ids(
    context: dict[str, Any] | None,
) -> frozenset[str]:
    """Find exact result-reentry Goals whose failed safe read may be retried.

    Both independent Runtime facts must agree: trusted provider outcome marks the
    exact failed Capability retryable, and an active task binding marks its exact
    request recoverable and safe-read. Missing or contradictory fields fail closed.
    This opens an execution choice for Planner; it does not select the Capability.
    """

    context = context or {}
    outcome = context.get("trusted_execution_outcome")
    if not isinstance(outcome, dict):
        return frozenset()
    retryable_by_capability: dict[str, set[str]] = {}
    for item in outcome.get("evidence") or []:
        if not isinstance(item, dict) or item.get("status") != "failed":
            continue
        retryability = item.get("provider_retryability")
        if not isinstance(retryability, dict) or not (
            retryability.get("recoverable") is True and retryability.get("retryable") is True
        ):
            continue
        capability_id = " ".join(str(item.get("capability_id") or "").strip().split())
        if not capability_id:
            continue
        retryable_by_capability.setdefault(capability_id, set()).update(
            " ".join(str(value or "").strip().split())
            for value in item.get("source_goal_ids") or []
            if " ".join(str(value or "").strip().split())
        )

    recoverable: set[str] = set()
    for task in context.get("active_task_snapshots") or []:
        if not isinstance(task, dict) or task.get("status") != "recoverable":
            continue
        metadata = task.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        binding = metadata.get("execution_binding")
        if not isinstance(binding, dict) or binding.get("retryable_safe_read") is not True:
            continue
        recoverable_request_ids = {
            " ".join(str(value or "").strip().split())
            for value in binding.get("recoverable_request_ids") or []
            if " ".join(str(value or "").strip().split())
        }
        for planned in binding.get("planned_capabilities") or []:
            if not isinstance(planned, dict):
                continue
            request_id = " ".join(str(planned.get("request_id") or "").strip().split())
            capability_id = " ".join(str(planned.get("capability_id") or "").strip().split())
            if (
                request_id not in recoverable_request_ids
                or planned.get("retryable_safe_read") is not True
                or str(planned.get("safety_class") or "").strip() != "safe_read"
            ):
                continue
            planned_goal_ids = {
                " ".join(str(value or "").strip().split())
                for value in planned.get("source_goal_ids") or []
                if " ".join(str(value or "").strip().split())
            }
            recoverable.update(planned_goal_ids & retryable_by_capability.get(capability_id, set()))
    return frozenset(recoverable)


def planner_provider_vocal_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return requested vocal-performance Goals requiring exact provider evidence."""

    provider_vocal_modes = {
        "styled_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
    }
    return {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and _goal_output_mode(goal) in provider_vocal_modes
    }


def planner_provider_media_goal_operations(
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, str]:
    """Return exact media lifecycle operations requested by canonical WHAT."""

    result: dict[str, str] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        operation = (
            str(metadata.get("media_operation") or "").strip() if isinstance(metadata, dict) else ""
        )
        if goal_id and _goal_output_mode(goal) == "media_playback":
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


def goal_cancellation_evidence_reentry_goal_ids(
    context: dict[str, Any] | None,
) -> set[str]:
    """Return Goals bound to Host-admitted cancellation control Evidence.

    The cancellation mechanism owns only the factual transition. This helper
    validates the bounded Evidence and grants the existing Planner permission to
    communicate from that state; it does not interpret the result itself.
    """

    if not isinstance(context, dict):
        return set()
    reentry = context.get("goal_cancellation_reentry")
    raw_evidence = context.get("trusted_goal_cancellation_evidence")
    if not isinstance(reentry, dict) or not isinstance(raw_evidence, list):
        return set()
    try:
        evidence = [GoalCancellationEvidence.model_validate(item) for item in raw_evidence]
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
    evidence_goal_ids = {goal_id for item in evidence for goal_id in item.target_goal_ids}
    requested_goal_ids = {
        normalized
        for value in reentry.get("source_goal_ids") or []
        if (normalized := " ".join(str(value or "").strip().split()))
    }
    if requested_goal_ids and not requested_goal_ids.issubset(evidence_goal_ids):
        return set()
    return requested_goal_ids or evidence_goal_ids


@dataclass(frozen=True)
class PlannerGoalContext:
    """One immutable Goal/evidence projection shared by Fast and Deep Planner.

    Fast and Deep are cognition depths of one Planner authority.  The semantic
    meaning of the current Goal set, cancellation Evidence, and terminal-result
    re-entry therefore must not drift between pass-specific resolver code.
    """

    expected_goal_ids: tuple[str, ...]
    authoritative_goals: tuple[dict[str, Any], ...]
    cancellation_reentry_goal_ids: frozenset[str]
    result_reentry_goal_ids: frozenset[str]
    response_goal_ids: tuple[str, ...]
    response_only: bool
    requires_execution: bool


def planner_goal_context(
    context: dict[str, Any] | None,
    *,
    reentry_scope: PlannerReentryScope | None = None,
) -> PlannerGoalContext:
    """Project canonical Goal/evidence truth once for either Planner depth.

    Result-Evidence re-entry deliberately re-opens the executable catalog rather
    than forcing a response-only callback: after trusted state changes, the same
    Planner may answer, plan genuinely new follow-up Work, clarify, wait, or do
    nothing.  The Host's re-entry guard rejects replay of the completed Work.
    """

    current = context if isinstance(context, dict) else {}
    full_expected = tuple(expected_goal_ids(current))
    full_goals = canonical_goal_grounding(current)
    cancellation_goal_ids = frozenset(goal_cancellation_evidence_reentry_goal_ids(current))
    result_goal_ids = frozenset(result_evidence_reentry_goal_ids(current))
    if reentry_scope is not None:
        expected = tuple(reentry_scope.goal_ids)
        unknown = set(expected) - set(full_expected)
        if unknown:
            raise ValueError(
                "Planner re-entry scope references Goals absent from Goal Association: "
                + ",".join(sorted(unknown))
            )
        goals_by_id = {
            " ".join(str(goal.get("goal_id") or "").strip().split()): goal
            for goal in full_goals
            if isinstance(goal, dict)
        }
        missing_grounding = set(expected) - set(goals_by_id)
        if missing_grounding:
            raise ValueError(
                "Planner re-entry scope lacks canonical Goal grounding: "
                + ",".join(sorted(missing_grounding))
            )
        goals = [goals_by_id[goal_id] for goal_id in expected]
        scope_ids = frozenset(expected)
        if reentry_scope.trigger in {
            "capability_result_reentry",
            "post_execution",
        }:
            if result_goal_ids != scope_ids:
                raise ValueError(
                    "Planner result-Evidence re-entry context does not match typed scope"
                )
            result_goal_ids = scope_ids
            cancellation_goal_ids = frozenset()
        elif reentry_scope.trigger == "goal_cancellation_reentry":
            if cancellation_goal_ids != scope_ids:
                raise ValueError("Planner cancellation re-entry context does not match typed scope")
            cancellation_goal_ids = scope_ids
            result_goal_ids = frozenset()
        else:
            cancellation_goal_ids = frozenset()
            result_goal_ids = frozenset()
    else:
        expected = full_expected
        goals = full_goals
    response_only, requires_execution = planner_goal_execution_requirements(goals)
    response_goal_ids = set(planner_response_goal_ids(goals)) | set(cancellation_goal_ids)

    if cancellation_goal_ids:
        stateful_goal_ids = {
            str(goal.get("goal_id") or "").strip()
            for goal in goals
            if isinstance(goal, dict) and _goal_output_mode(goal) == "stateful_effect"
        }
        requires_execution = bool(stateful_goal_ids - set(cancellation_goal_ids))
        if set(cancellation_goal_ids) == set(expected):
            response_only = True

    if result_goal_ids and set(result_goal_ids) == set(expected):
        recoverable_goal_ids = set(recoverable_result_reentry_goal_ids(context)) & set(
            result_goal_ids
        )
        response_only = False
        requires_execution = bool(recoverable_goal_ids)
        response_goal_ids = set(expected) - recoverable_goal_ids

    return PlannerGoalContext(
        expected_goal_ids=expected,
        authoritative_goals=tuple(goals),
        cancellation_reentry_goal_ids=cancellation_goal_ids,
        result_reentry_goal_ids=result_goal_ids,
        response_goal_ids=tuple(sorted(response_goal_ids)),
        response_only=response_only,
        requires_execution=requires_execution,
    )


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


def gateway_speech_act(request: Any) -> str:
    """Return immutable Gateway speech-act evidence from the admitted turn envelope."""

    context = request.context if isinstance(request.context, dict) else {}
    envelope = context.get("user_turn_envelope")
    if not isinstance(envelope, dict):
        return ""
    attention = envelope.get("attention")
    if not isinstance(attention, dict):
        return ""
    return " ".join(str(attention.get("speech_act") or "").strip().split()).casefold()


def fast_capability_payload(item: Any, *, include_side_effect_free: bool = False) -> dict[str, Any]:
    """Project one catalog entry onto Fast Planner's read-only capability surface."""

    payload = {
        "capability_id": item.capability_id,
        "description": item.description,
        "input_schema": item.input_schema,
        "requires_confirmation": item.requires_confirmation,
        "can_run_parallel": item.can_run_parallel,
        "parallel_metadata_declared": item.parallel_metadata_declared,
        "exclusive_group": item.exclusive_group,
        "resource_claims": list(item.resource_claims),
        "effects": list(item.effects),
        "safety_class": item.safety_class,
        "behavior_domains": list(item.behavior_domains),
        "hints": dict(item.hints),
    }
    if include_side_effect_free:
        payload["side_effect_free"] = (item.hints or {}).get("side_effect_free") is True
    return payload


def deep_capability_payload(item: Any) -> dict[str, Any]:
    """Project one catalog entry onto Deep Planner's read-only capability surface."""

    return {
        "capability_id": item.capability_id,
        "description": item.description,
        "input_schema": item.input_schema,
        "available": item.available,
        "interaction_executable": item.interaction_executable,
        "requires_confirmation": item.requires_confirmation,
        "effects": item.effects,
        "safety_class": item.safety_class,
        "behavior_domains": list(item.behavior_domains),
        "can_run_parallel": item.can_run_parallel,
        "parallel_metadata_declared": item.parallel_metadata_declared,
        "exclusive_group": item.exclusive_group,
        "resource_claims": item.resource_claims,
        "execution_constraints": item.execution_constraints,
        "hints": dict(item.hints),
    }


def auxiliary_social_capability_payloads(entries: list[Any]) -> list[dict[str, Any]]:
    """Project only catalog-qualified optional social-decoration Capabilities.

    This is a read-only catalog filter. It does not decide that an expression is
    useful; the same primary Planner result makes that semantic choice. Requiring
    explicit behavior-domain and parallel-safety declarations keeps the model from
    borrowing an arbitrary body Capability for decoration.
    """

    projected: list[dict[str, Any]] = []
    for item in entries:
        domains = {
            str(value).strip().lower()
            for value in (getattr(item, "behavior_domains", None) or [])
            if str(value).strip()
        }
        if (
            not getattr(item, "available", False)
            or not getattr(item, "interaction_executable", False)
            or "social_attention" not in domains
            or bool(getattr(item, "requires_confirmation", False))
            or getattr(item, "can_run_parallel", None) is not True
            or not bool(getattr(item, "parallel_metadata_declared", False))
        ):
            continue
        input_schema = getattr(item, "input_schema", None)
        if not isinstance(input_schema, dict):
            continue
        try:
            reject_forbidden_low_level_fields(input_schema)
        except ValueError:
            continue
        projected.append(
            {
                "capability_id": str(item.capability_id),
                "description": str(item.description)[:180],
                "input_schema": copy.deepcopy(input_schema),
                "can_run_parallel": True,
                "parallel_metadata_declared": True,
                "exclusive_group": getattr(item, "exclusive_group", None),
                "resource_claims": list(getattr(item, "resource_claims", None) or []),
                "behavior_domains": ["social_attention"],
            }
        )
    return projected


def auxiliary_social_prompt_context(
    context: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the bounded scene/style/history input for Planner decoration."""

    mind = context.get("mind")
    raw_style = mind.get("social_interaction_style") if isinstance(mind, dict) else None
    style = (
        {
            key: raw_style[key]
            for key in ("expressiveness", "repetition_guidance", "restraint")
            if key in raw_style
        }
        if isinstance(raw_style, dict) and raw_style.get("owner_approved") is True
        else {}
    )
    target_evidence: dict[str, Any] = {"available": False}
    for key in (
        "auxiliary_social_target",
        "social_attention_target",
        "active_user_target",
        "perceived_user_target",
    ):
        value = context.get(key)
        if not isinstance(value, dict) or not value:
            continue
        explicit_source = str(value.get("source") or "").strip()
        source = (
            explicit_source
            if explicit_source in {"live_perception", "conversation_context"}
            else "live_perception"
            if "perception" in key or "perceived" in key
            else "conversation_context"
        )
        raw_target = value.get("target")
        target = dict(raw_target) if isinstance(raw_target, dict) else dict(value)
        target_evidence = {
            "available": True,
            "source": source,
            "target": {
                name: target[name]
                for name in (
                    "target_ref",
                    "relative_direction",
                    "confidence",
                    "evidence_refs",
                )
                if name in target
            },
        }
        break
    recent = [
        {
            key: item[key]
            for key in (
                "capability_id",
                "semantic_args",
                "social_function",
                "anchor_id",
                "execution_claim",
            )
            if key in item
        }
        for item in (context.get("recent_auxiliary_behavior_evidence") or [])[-12:]
        if isinstance(item, dict)
    ]
    return {
        "eligible_capabilities": candidates,
        "target_evidence": target_evidence,
        "social_interaction_style": style,
        "recent_auxiliary_behavior_evidence": recent,
        "max_activities": 3,
    }
