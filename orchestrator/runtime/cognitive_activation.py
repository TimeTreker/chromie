from __future__ import annotations

from typing import Any, Iterable

from shared.chromie_contracts.cognitive_activation import (
    CognitiveActivationContext,
    CognitiveActivationDecision,
)
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if text and text not in result:
            result.append(text)
    return result


def _compact_activation_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Project only facts needed to decide whether cognition should run.

    Activation owns no planning, Goal interpretation, or answer composition.  Passing
    full GA/Plan/Evidence envelopes here both duplicates downstream owner context and can
    exhaust the small activation model budget.  This projection retains identity, current
    lifecycle, unresolved Work, and the existence/status of fresh trusted state changes;
    the selected owner receives the full authoritative context after activation.
    Retain every supplied lifecycle row: a tail failure or pending obligation is
    material. Contract and model-transport budgets reject oversized requests rather
    than silently changing the scope or deciding which facts matter.
    """

    raw = state if isinstance(state, dict) else {}

    def rows(value: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in value if isinstance(item, dict)] \
            if isinstance(value, list) else []

    def select(item: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
        return {name: item[name] for name in names if name in item and item[name] not in (None, "", [], {})}

    compact: dict[str, Any] = {}

    association = raw.get('goal_association')
    if isinstance(association, dict):
        compact['goal_association'] = {
            'resolution_status': association.get('resolution_status'),
            'associations': [
                select(item, ('relationship','source_responsibility_refs','target_goal_ids','resolved_gap_ids'))
                for item in rows(association.get('associations'))
            ],
            'new_goals': [
                select(item, ('goal_id','source_responsibility_refs','description','responsibility_status'))
                for item in rows(association.get('new_goals'))
            ],
        }

    plan = raw.get('canonical_plan')
    if isinstance(plan, dict):
        compact['canonical_plan'] = {
            **select(plan, ('plan_id','disposition','coverage','goal_ids','planner_tier','goal_satisfaction')),
            'steps': [
                select(item, ('step_id','capability_id','source_goal_ids','timing','reuse_activity_id','step_purpose'))
                for item in rows(plan.get('steps'))
            ],
            'goal_outcomes': [
                select(item, ('goal_id','disposition','coverage','step_ids','unmet_requirements','satisfaction'))
                for item in rows(plan.get('goal_outcomes'))
            ],
            'communication_needs': [
                select(item, ('need_id','kind','source_goal_ids','delivery_phase'))
                for item in rows(plan.get('communication_needs'))
            ],
        }

    goal_state = raw.get('goal_state')
    if isinstance(goal_state, list):
        compact['goal_state'] = [
            select(item, ('goal_id','goal_version','responsibility_status','work_status','open_information_gaps'))
            for item in rows(goal_state)
        ]

    work = raw.get('existing_work_activities')
    if isinstance(work, list):
        compact['existing_work_activities'] = [
            select(item, ('activity_id','capability_id','status','state','timing','source_goal_ids','source_responsibility_refs'))
            for item in rows(work)
        ]

    situation = raw.get('situation')
    if isinstance(situation, dict):
        compact['situation'] = {
            **select(situation, ('revision','focus_goal_ids','digest','audience_refs')),
            'interpretations': [
                select(item, ('subject_ref','relation','value','epistemic_status','relevance_goal_ids'))
                for item in rows(situation.get('interpretations'))
            ],
        }

    change = raw.get('trusted_state_change')
    if isinstance(change, dict):
        projected: dict[str, Any] = {}
        outcome = change.get('trusted_execution_outcome')
        if isinstance(outcome, dict):
            projected['trusted_execution_outcome'] = {
                **select(outcome, ('outcome_id','aggregate_status')),
                'goal_outcomes': [
                    select(item, ('goal_id','status','evidence_ids','completed_step_ids','unresolved_step_ids','requires_planner_continuation','acquisition_step_ids','planned_satisfaction'))
                    for item in rows(outcome.get('goal_outcomes'))
                ],
            }
        terminal = change.get('trusted_terminal_evidence')
        if isinstance(terminal, list):
            projected['trusted_terminal_evidence'] = [
                select(item, ('evidence_id','tool_id','capability_id','status','source_goal_ids','reason_code'))
                for item in rows(terminal)
            ]
        for name in ('result_evidence_refs','planner_cancellation_capability_facts'):
            value = change.get(name)
            if isinstance(value, list):
                projected[name] = list(value)
        for name in ('result_evidence_reentry','trusted_provider_state_event','trusted_goal_cancellation_evidence'):
            value = change.get(name)
            if isinstance(value, dict):
                projected[name] = select(
                    value,
                    ('phase','source_goal_ids','evidence_refs','request_id','status','state','condition','waiting_for','blocked','degraded','paused','recovering','goal_id','cancelled'),
                )
        compact['trusted_state_change'] = projected

    # Situation's Memory owner has already filtered disclosure against the
    # trusted audience. Pending/delivered interaction distinguishes a new social
    # opportunity from one already being handled; neither can vanish at this gate.
    for name in ('memory_summary', 'relational_memory_selection', 'interaction_context'):
        if name in raw:
            compact[name] = raw[name]

    return compact


async def resolve_cognitive_activation(
    host: Any,
    *,
    trigger: str,
    allowed_authorities: list[str],
    goal_ids: list[str] | None = None,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    source_refs: list[str] | None = None,
    state: dict[str, Any] | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
) -> CognitiveActivationDecision | None:
    """Ask the bounded Activation model whether existing cognition should run now.

    Runtime authors only trusted scope/provenance and structurally legal authorities.
    Missing/unavailable activation cognition fails closed: callers do not infer an
    equivalent Planner/SC wake from the event type.
    """

    cognition_call = getattr(
        getattr(host, "agent_client", None),
        "resolve_cognitive_activation",
        None,
    )
    if not callable(cognition_call):
        if hasattr(host, "session_log"):
            host.session_log(
                session_id,
                "cognitive_activation_unavailable: trigger=%s",
                trigger,
            )
        return None

    try:
        scoped_responsibilities = list(responsibilities or [])
        responsibility_refs = _unique(
            item.local_ref for item in scoped_responsibilities
        )
        normalized_goal_ids = _unique(goal_ids or [])
        normalized_source_refs = _unique(source_refs or [])
        normalized_authorities = _unique(allowed_authorities)
        activation_request = CognitiveActivationContext(
            request_id=(
                request_id
                or "activation:"
                + ":".join(
                    [
                        trigger,
                        *(normalized_goal_ids or normalized_source_refs or ["state"]),
                    ]
                )
            )[:200],
            trigger=trigger,
            allowed_authorities=normalized_authorities,
            goal_ids=normalized_goal_ids,
            responsibility_refs=responsibility_refs,
            source_refs=normalized_source_refs,
            responsibilities=scoped_responsibilities,
            state=_compact_activation_state(state),
        )
        session = await host.get_http_session()
        decision = await cognition_call(
            session,
            request=activation_request,
            timeout_ms=max(
                10000,
                int(
                    getattr(
                        getattr(host, "cognitive_runtime_policy", None),
                        "fast_planner_timeout_ms",
                        10000,
                    )
                ),
            ),
        )
        decision.validate_request(activation_request)
    except Exception as exc:
        if hasattr(host, "session_log"):
            host.session_log(
                session_id,
                "cognitive_activation_failed: trigger=%s error_type=%s error=%s",
                trigger,
                type(exc).__name__,
                exc,
            )
        return None

    if hasattr(host, "session_log"):
        host.session_log(
            session_id,
            "cognitive_activation_done: trigger=%s requests=%s confidence=%.2f",
            trigger,
            ",".join(item.authority for item in decision.cognitive_requests)
            or "none",
            decision.confidence,
        )
    return decision


def activation_requested(
    decision: CognitiveActivationDecision | None,
    authority: str,
) -> bool:
    return decision is not None and any(
        item.authority == authority for item in decision.cognitive_requests
    )
