from __future__ import annotations

from typing import Any, Iterable

from shared.chromie_contracts.cognitive_activation import (
    CognitiveActivationContext,
    CognitiveActivationDecision,
)
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal


def _unique(values: Iterable[Any], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


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

    scoped_responsibilities = list(responsibilities or [])[:12]
    responsibility_refs = _unique(
        (item.local_ref for item in scoped_responsibilities), limit=12
    )
    normalized_goal_ids = _unique(goal_ids or [], limit=8)
    normalized_source_refs = _unique(source_refs or [], limit=24)
    normalized_authorities = _unique(allowed_authorities, limit=2)
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
        state=dict(state or {}),
    )
    session = await host.get_http_session()
    try:
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
