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
    SituationInterpretation,
    SituationRevisionObservation,
    SituationProjection,
    SituationSourceRef,
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _bounded(value: Any, *, limit: int) -> str:
    return _normalized(value)[: max(1, int(limit))]


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


def _evidence_source_reference(item: dict[str, Any], index: int) -> SituationSourceRef:
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
    owner = source or "orchestrator.conversation_state"
    return SituationSourceRef(
        kind="evidence",
        reference_id=reference_id or f"evidence_{index}",
        owner=owner,
    )


def _source_refs(
    values: Iterable[SituationSourceRef],
    *,
    limit: int,
) -> list[SituationSourceRef]:
    out: list[SituationSourceRef] = []
    seen: set[str] = set()
    for item in values:
        if item.reference_id in seen:
            continue
        seen.add(item.reference_id)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _interpretation_id(
    *,
    subject_ref: str,
    relation: str,
    value: str,
    source_ref: str,
) -> str:
    encoded = json.dumps(
        {
            "subject_ref": subject_ref,
            "relation": relation,
            "value": value,
            "source_ref": source_ref,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"situation_interpretation_{hashlib.sha256(encoded).hexdigest()[:20]}"


def _provider_state_interpretations(
    *,
    request_id: str,
    goal_ids: list[str],
    source_ref: str,
    provider_state: dict[str, Any],
) -> list[SituationInterpretation]:
    """Project only source-stated provider implications into current Situation.

    This deliberately performs no semantic inference about the Goal.  A provider
    saying a request is blocked/waiting/degraded can become a current Situation
    interpretation because that state is directly relevant to active Work; Host
    does not infer user intent, Goal satisfaction, recovery policy, or next Work.
    """

    subject_ref = f"capability_request:{_normalized(request_id)}"
    if len(subject_ref) > 200:
        subject_ref = (
            "capability_request:"
            f"{hashlib.sha256(subject_ref.encode('utf-8')).hexdigest()[:32]}"
        )
    interpretations: list[SituationInterpretation] = []

    def add(relation: str, value: Any, *, subject: str = subject_ref) -> None:
        if len(interpretations) >= 12:
            return
        normalized_value = _bounded(value, limit=240)
        if not normalized_value:
            return
        interpretations.append(
            SituationInterpretation(
                interpretation_id=_interpretation_id(
                    subject_ref=subject,
                    relation=relation,
                    value=normalized_value,
                    source_ref=source_ref,
                ),
                subject_ref=subject,
                relation=relation,
                value=normalized_value,
                epistemic_status="established",
                relevance_goal_ids=goal_ids,
                source_refs=[source_ref],
            )
        )

    for key in ("status", "state", "phase", "condition", "waiting_for"):
        if key in provider_state:
            add(f"runtime.{key}", provider_state.get(key))
    for key in ("blocked", "degraded", "paused", "recovering"):
        if provider_state.get(key) is True:
            add("runtime.condition", key)

    member_status = provider_state.get("member_status")
    if isinstance(member_status, dict):
        for member_id, member_state in member_status.items():
            member_subject = (
                f"{subject_ref}:member:{_normalized(member_id)}"
                if _normalized(member_id)
                else subject_ref
            )
            if len(member_subject) > 200:
                member_subject = (
                    f"{subject_ref[:150]}:member:"
                    f"{hashlib.sha256(member_subject.encode('utf-8')).hexdigest()[:32]}"
                )
            add(
                "runtime.member_status",
                member_state,
                subject=member_subject,
            )
    return interpretations


def build_situation_projection(
    *,
    context: dict[str, Any] | None,
    turn_id: str,
    focus_goal_ids: Iterable[str] | None = None,
    revision: int = 1,
    source_refs: Iterable[SituationSourceRef] | None = None,
    interpretations: Iterable[SituationInterpretation] | None = None,
) -> SituationProjection:
    """Reconstruct one bounded live Situation from current authoritative projections.

    This function has no persistence and owns no source facts.  Goal/Evidence/
    Memory/provider objects remain authoritative in their existing owners.  The
    returned Situation may retain only their bounded references plus current
    implications explicitly supplied by a trusted ingress.
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
    evidence_sources = [
        _evidence_source_reference(item, index)
        for index, item in enumerate(recent_evidence[-8:])
        if isinstance(item, dict)
    ]

    explicit_sources = list(source_refs or [])
    bounded_sources = _source_refs(
        [*explicit_sources, *evidence_sources],
        limit=16,
    )
    allowed_source_refs = {item.reference_id for item in bounded_sources}
    bounded_interpretations = [
        item
        for item in list(interpretations or [])[:12]
        if set(item.source_refs).issubset(allowed_source_refs)
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
        source_refs=bounded_sources,
        interpretations=bounded_interpretations,
    )


def build_provider_state_situation_observation(
    *,
    context: dict[str, Any] | None,
    turn_id: str,
    goal_ids: Iterable[str],
    dispatch_id: str,
    request_id: str,
    capability_id: str,
    provider_id: str,
    sequence: int,
    provider_state: dict[str, Any],
) -> SituationRevisionObservation:
    """Admit one bounded live provider-state transition as Situation input.

    Provider progress is independently trusted for its own Runtime state domain but
    is not Evidence of Goal satisfaction or of external-world facts.  The ingress
    therefore records it as ``runtime_state`` provenance and creates only direct,
    revisable interpretations of the source-stated request state.
    """

    normalized_goals = _unique(goal_ids, limit=8)
    if not normalized_goals:
        raise ValueError("provider Situation ingress requires at least one Goal")
    normalized_request_id = _normalized(request_id)
    if not normalized_request_id:
        raise ValueError("provider Situation ingress requires request_id")
    normalized_dispatch_id = _normalized(dispatch_id)
    source_ref_id = (
        f"runtime-state:{normalized_dispatch_id or 'dispatch'}:"
        f"{normalized_request_id}:{max(1, int(sequence))}"
    )
    if len(source_ref_id) > 200:
        encoded = source_ref_id.encode("utf-8")
        source_ref_id = (
            f"runtime-state:{hashlib.sha256(encoded).hexdigest()[:32]}"
        )
    source = SituationSourceRef(
        kind="runtime_state",
        reference_id=source_ref_id,
        owner=(
            _bounded(provider_id, limit=160)
            or "orchestrator.interaction_runtime"
        ),
    )
    provider_interpretations = _provider_state_interpretations(
        request_id=normalized_request_id,
        goal_ids=normalized_goals,
        source_ref=source_ref_id,
        provider_state=dict(provider_state),
    )
    if not provider_interpretations:
        raise ValueError("provider Situation ingress requires meaningful state")
    projection = build_situation_projection(
        context=context,
        turn_id=turn_id,
        focus_goal_ids=normalized_goals,
        revision=max(1, int(sequence)),
        source_refs=[source],
        interpretations=provider_interpretations,
    )
    observation_id = (
        f"situation_observation:{normalized_dispatch_id or 'dispatch'}:"
        f"{normalized_request_id}:{max(1, int(sequence))}"
    )
    if len(observation_id) > 200:
        encoded = observation_id.encode("utf-8")
        observation_id = (
            f"situation_observation:{hashlib.sha256(encoded).hexdigest()[:32]}"
        )
    return SituationRevisionObservation(
        observation_id=observation_id,
        source_id=(
            _bounded(provider_id, limit=160)
            or _bounded(capability_id, limit=160)
            or "orchestrator.interaction_runtime"
        ),
        source_revision=max(1, int(sequence)),
        goal_ids=normalized_goals,
        source_refs=[source_ref_id],
        projection=projection,
    )


def situation_revision_cognition_mode(
    observation: SituationRevisionObservation,
) -> str:
    """Select cognition depth from the admitted Situation delta, not its trigger name.

    This is a bounded mechanical readiness judgment.  It does not choose Work or
    interpret user meaning.  No-op is represented by no CognitiveOpportunity;
    ``local`` means the trusted owner state is worth retaining/logging but does
    not justify an LLM pass.
    """

    values = {
        _normalized(item.value).casefold()
        for item in observation.projection.interpretations
        if item.source_refs
    }
    relations = {
        _normalized(item.relation).casefold()
        for item in observation.projection.interpretations
    }
    severe = {"blocked", "degraded", "failed", "error", "unsafe"}
    if values.intersection(severe):
        return "slow"
    if values.intersection({"paused", "needs_attention"}):
        return "fast"
    if values.intersection({"waiting", "recovering", "running"}):
        return "local"
    if relations and relations.issubset({"runtime.phase", "runtime.member_status"}):
        return "local"
    return "fast"


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
    source_by_ref = {
        item.reference_id: item for item in observation.projection.source_refs
    }
    evidence_refs = [
        source_ref
        for source_ref in observation.source_refs
        if source_by_ref[source_ref].kind == "evidence"
    ]
    return CognitiveOpportunity.create(
        trigger="situation_revision",
        goal_ids=list(observation.goal_ids),
        evidence_refs=evidence_refs,
        reason_codes=["trusted_situation_revision"],
        recommended_cognition=situation_revision_cognition_mode(observation),
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
    "build_provider_state_situation_observation",
    "build_situation_projection",
    "derive_situation_revision_opportunity",
    "drain_due_time_conditions_once",
    "run_time_condition_wake_loop",
    "situation_revision_cognition_mode",
]
