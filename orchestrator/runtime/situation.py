from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Iterable

from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.situation import (
    CognitiveOpportunity,
    GoalTimeCondition,
    SituationConditionRef,
    SituationEvidenceRef,
    SituationRevisionObservation,
    SituationProjection,
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _unique(values: Iterable[Any], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalized(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _evidence_reference(item: dict[str, Any], index: int) -> SituationEvidenceRef:
    for key in (
        "evidence_id",
        "execution_outcome_id",
        "request_id",
        "tool_call_id",
        "interaction_id",
        "event_id",
    ):
        value = _normalized(item.get(key))
        if value:
            reference_id = value
            break
    else:
        encoded = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        reference_id = f"situation_evidence_{hashlib.sha256(encoded).hexdigest()[:20]}"

    source = _normalized(item.get("source") or item.get("owner") or "")
    if "execution" in source.casefold() or item.get("execution_outcome_id"):
        kind = "execution_evidence"
    elif "interaction" in source.casefold() or item.get("event_id"):
        kind = "interaction_evidence"
    elif item.get("tool_id") or item.get("tool_call_id") or item.get("request_id"):
        kind = "tool_evidence"
    else:
        kind = "other_evidence"
    owner = source or "orchestrator.conversation_state"
    return SituationEvidenceRef(
        kind=kind,
        reference_id=reference_id or f"evidence_{index}",
        owner=owner,
    )


def build_situation_projection(
    *,
    context: dict[str, Any] | None,
    turn_id: str,
    focus_goal_ids: Iterable[str] | None = None,
    revision: int = 1,
) -> SituationProjection:
    """Reconstruct one bounded live Situation from current authoritative projections.

    This function has no persistence and owns no source facts.  It intentionally
    emits references/working-set identity only; Goal/Evidence/Memory/provider
    objects remain authoritative in their existing owners.
    """

    current = context if isinstance(context, dict) else {}
    active = current.get("active_goal_snapshots")
    if not isinstance(active, list):
        active = []

    active_goal_ids: list[str] = []
    conditions: list[SituationConditionRef] = []
    for snapshot in active:
        if not isinstance(snapshot, dict):
            continue
        goal_id = _normalized(snapshot.get("goal_id"))
        if goal_id:
            active_goal_ids.append(goal_id)
        gaps = snapshot.get("open_information_gaps")
        if not isinstance(gaps, list) or not goal_id:
            continue
        for gap in gaps:
            if len(conditions) >= 12:
                break
            if not isinstance(gap, dict) or gap.get("resolved") is True:
                continue
            condition_id = _normalized(gap.get("gap_id") or gap.get("description"))
            if not condition_id:
                continue
            conditions.append(
                SituationConditionRef(
                    goal_id=goal_id,
                    condition_id=condition_id,
                    resolution=_normalized(gap.get("preferred_resolution") or "unknown"),
                )
            )

    discourse_focus = current.get("discourse_focus")
    if not isinstance(discourse_focus, list):
        discourse_focus = []

    recent_evidence = current.get("recent_tool_evidence")
    if not isinstance(recent_evidence, list):
        recent_evidence = []
    evidence_refs = [
        _evidence_reference(item, index)
        for index, item in enumerate(recent_evidence[-8:])
        if isinstance(item, dict)
    ]

    selected_goals = (
        _unique(focus_goal_ids, limit=8)
        if focus_goal_ids is not None
        else _unique(active_goal_ids, limit=8)
    )
    return SituationProjection.create(
        turn_id=_normalized(turn_id),
        revision=max(1, int(revision)),
        focus_goal_ids=selected_goals,
        discourse_focus_ids=_unique(discourse_focus[-8:], limit=8),
        unresolved_conditions=conditions,
        evidence_refs=evidence_refs,
    )


def derive_situation_revision_opportunity(
    observation: SituationRevisionObservation,
    *,
    previous_situation_digest: str = "",
) -> CognitiveOpportunity | None:
    """Derive Planner readiness from one trusted live-Situation observation.

    The producer is delta-driven: replaying the same Situation digest is a no-op.
    Source trust/admission belongs to the caller that constructs the typed observation;
    this function neither observes the world nor invents Evidence.
    """

    previous = _normalized(previous_situation_digest)
    if previous and previous == observation.projection.digest:
        return None
    return CognitiveOpportunity.create(
        trigger="situation_revision",
        goal_ids=list(observation.goal_ids),
        evidence_refs=list(observation.evidence_refs),
        reason_codes=["trusted_situation_revision"],
        recommended_cognition="fast",
        situation_digest=observation.projection.digest,
    )


async def apply_due_time_condition_opportunity(
    host: Any,
    due_item: dict[str, Any],
) -> str:
    """Reactivate the same Planner for one due structured time condition.

    Wall-clock readiness is a trusted mechanical state transition, not Evidence and
    not a fabricated user turn. The due item must therefore retain exact Planner/Goal
    binding plus original GI Responsibility provenance. Missing provenance fails
    closed after the one-shot condition is consumed; Host never reconstructs WHAT
    from Goal prose and never authors a response or Activity.
    """

    try:
        condition = GoalTimeCondition.model_validate(due_item.get("condition") or {})
        opportunity = CognitiveOpportunity.model_validate(
            due_item.get("opportunity") or {}
        )
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(item)
            for item in due_item.get("responsibilities") or []
            if isinstance(item, dict)
        ]
    except (TypeError, ValueError) as exc:
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=invalid_due_payload "
            "error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        return "invalid_due_payload"

    if opportunity.trigger != "time_condition":
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=wrong_trigger trigger=%s",
            opportunity.trigger,
        )
        return "wrong_trigger"
    if condition.goal_id not in opportunity.goal_ids:
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=goal_binding_mismatch "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "goal_binding_mismatch"
    if not responsibilities:
        host.session_log(
            None,
            "time_condition_reentry_suppressed: reason=missing_responsibility_provenance "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "missing_responsibility_provenance"

    source_text = _normalized(due_item.get("source_text"))
    if not source_text:
        host.session_log(
            None,
            "time_condition_reentry_suppressed: reason=missing_source_text "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "missing_source_text"

    planner_response = await host._planner_state_reentry_response(
        source_response=None,
        canonical_plan=None,
        user_request=source_text,
        language=_normalized(due_item.get("language")) or "auto",
        goal_ids=list(opportunity.goal_ids),
        evidence_goal_ids=[],
        evidence_refs=[],
        session_id=None,
        phase="time_condition_reentry",
        context_updates={
            "time_condition": condition.model_dump(mode="json"),
            "cognitive_opportunity": opportunity.prompt_projection(),
        },
        fast_workflow_stage="fast_planner_time_condition_reentry",
        deep_workflow_stage="planner_deep_pass_time_condition_reentry",
        response_source="fast_planner_time_condition_reentry",
        responsibilities_override=responsibilities,
    )
    if planner_response is None:
        host.session_log(
            None,
            "time_condition_reentry_no_change: condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "no_change"

    apply_status = await host._apply_planner_reentry_response(
        planner_response,
        session_id=None,
    )
    host.session_log(
        None,
        "time_condition_reentry_done: condition_id=%s goal_id=%s apply=%s",
        condition.condition_id,
        condition.goal_id,
        apply_status,
    )
    return str(apply_status or "applied")


async def drain_due_time_conditions_once(
    host: Any,
    *,
    now_ms: int | None = None,
) -> list[str]:
    """Consume and process the currently due structured wake conditions once."""

    due = host.conversation_state.due_time_condition_opportunities(now_ms=now_ms)
    statuses: list[str] = []
    for item in due:
        try:
            statuses.append(await apply_due_time_condition_opportunity(host, item))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            host.session_log(
                None,
                "time_condition_reentry_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            statuses.append("planner_reentry_failed")
    return statuses


async def run_time_condition_wake_loop(
    host: Any,
    *,
    max_idle_sleep_s: float = 0.5,
) -> None:
    """Mechanically wake cognition when a durable Goal time condition becomes due.

    This is deliberately not an ambient thinking loop. With no due condition it
    performs no cognition, model call, Goal interpretation, or world polling. It
    only checks ConversationState's structured wall-clock records and sleeps.
    """

    idle_sleep = max(0.05, float(max_idle_sleep_s))
    while True:
        next_due = host.conversation_state.next_time_condition_due_ms()
        now = int(time.time() * 1000.0)
        if next_due is None:
            await asyncio.sleep(idle_sleep)
            continue
        delay_s = max(0.0, (int(next_due) - now) / 1000.0)
        if delay_s > 0.0:
            await asyncio.sleep(min(idle_sleep, delay_s))
            continue
        await drain_due_time_conditions_once(host, now_ms=now)


__all__ = [
    "apply_due_time_condition_opportunity",
    "build_situation_projection",
    "derive_situation_revision_opportunity",
    "drain_due_time_conditions_once",
    "run_time_condition_wake_loop",
]
