from __future__ import annotations

import logging
from typing import Any

from .clients.ollama_client import OllamaGenerationError, llm_failure_metadata
from .planner_context import expected_goal_ids
from . import planner_validation as _planner_validation
try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
try:
    from chromie_contracts.plan import CanonicalPlan, FastPlannerAdvance
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan, FastPlannerAdvance
try:
    from chromie_runtime.llm_diagnostics import cognition_text_reference
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference

logger = logging.getLogger("chromie.agent.planner_fallback")


def materialize_fast_advance_fail_safe(
    request: CognitiveWorkRequest,
    *,
    responsibility_refs: list[str],
    error: Exception,
    raw_output: Any,
    committed_communicative_activities: list[Any] | None = None,
    allow_progress_salvage: bool = True,
) -> FastPlannerAdvance:
    inference_failure = isinstance(error, OllamaGenerationError)
    failure = (
        llm_failure_metadata(error)
        if inference_failure
        else {
            "failure_class": "fast_advance_contract_invalid",
            "failure_domain": "model_contract",
            "architecture_attribution": "not_evaluated",
            "retryable": True,
        }
    )
    logger.warning(
        "fast_planner_advance_fail_safe sid=%s error_type=%s error=%s "
        "failure_class=%s raw_output_ref=%s",
        request.sid,
        type(error).__name__,
        error,
        failure["failure_class"],
        cognition_text_reference(raw_output),
    )
    progress_activities = (
        _planner_validation.validated_fail_safe_progress(
            raw_output,
            responsibility_refs=responsibility_refs,
        )
        if allow_progress_salvage
        else []
    )
    retained_communicative_activities = list(
        committed_communicative_activities or []
    )
    retained_ids = {
        item.activity_id for item in retained_communicative_activities
    }
    for item in progress_activities:
        if item.activity_id in retained_ids:
            continue
        retained_communicative_activities.append(item)
        retained_ids.add(item.activity_id)
    return FastPlannerAdvance(
        turn_id=str(request.sid or "turn-fast-advance"),
        disposition="unavailable",
        coverage="uncertain",
        covered_responsibility_refs=responsibility_refs,
        activities=retained_communicative_activities,
        continuations=[],
        confidence=0.0,
        unresolved=[
            "Fast Planner Activity Plan unavailable; Responsibility preserved "
            "for one canonical Fast Planner revision after Goal Association."
        ],
        reason_summary=(
            "Discard the invalid Fast Planner output without executing it."
        ),
        metadata={
            "semantic_authority": "deterministic_fail_safe",
            "phase": "responsibility_activity_planning",
            "execution_authority": "none",
            "advance_status": "canonical_fast_revision_required",
            "raw_output_ref": cognition_text_reference(raw_output),
            "error_type": type(error).__name__,
            "error": str(error)[:300],
            "salvaged_progress_activity_ids": [
                item.activity_id for item in retained_communicative_activities
            ],
            "progress_salvage_suppressed_by_first_response_decision": (
                not allow_progress_salvage
            ),
            **failure,
        },
    )

def materialize_fast_escalation(
    plan_id: str,
    request: CognitiveWorkRequest,
    reason: str,
    *,
    response_text: str = "",
    unresolved: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    error: Exception | None = None,
    path_classification: str = "semantic_escalation",
) -> CanonicalPlan:
    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "fast_planner",
            "status": "escalate",
            "authority": "advisory",
            "path_classification": path_classification,
        }
    )
    if error is not None:
        detail.update(
            {
                "error_type": type(error).__name__,
                "error": str(error)[:300],
                **llm_failure_metadata(error),
            }
        )
    context = request.context if isinstance(request.context, dict) else {}
    retained_progress = " ".join(str(response_text or "").strip().split())
    if retained_progress:
        detail["retained_progress_response_text"] = {
            "status": "undelivered_advisory",
            "reason": reason,
        }
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="fast",
        disposition="escalate",
        coverage="uncertain",
        confidence=0.0,
        goal_ids=expected_goal_ids(context),
        goal_summary=request.text,
        response_text=retained_progress,
        steps=[],
        escalation_reason=reason,
        unresolved=list(unresolved or []),
        metadata=detail,
    )

def materialize_deep_unavailable(
    plan_id: str,
    request: CognitiveWorkRequest,
    reason: str,
    *,
    unresolved: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    error: Exception | None = None,
    attempts: int = 1,
    max_contract_repairs: int = 1,
) -> CanonicalPlan:
    """Return a terminal capability limitation without asking a fake question.

    Missing provider ability is not user-semantic ambiguity. Additional user
    detail cannot create an absent Capability, so Deep Planning reports the
    limitation and authors only honest conversational next steps.
    """

    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "deep_planner",
            "status": "unavailable",
            "authority": "advisory",
            "attempt_count": attempts,
            "max_contract_repairs": max_contract_repairs,
            "reason": reason,
        }
    )
    if error is not None:
        detail.update(
            {
                "error_type": type(error).__name__,
                "error": str(error)[:300],
                **llm_failure_metadata(error),
            }
        )
    context = request.context if isinstance(request.context, dict) else {}
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="unavailable",
        coverage="uncertain",
        confidence=0.0,
        goal_summary=request.text,
        goal_ids=expected_goal_ids(context),
        response_text="",
        steps=[],
        unresolved=list(unresolved or []),
        metadata=detail,
    )

def materialize_deep_clarify(
    plan_id: str,
    request: CognitiveWorkRequest,
    reason: str,
    *,
    unresolved: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    error: Exception | None = None,
    attempts: int = 1,
    max_contract_repairs: int = 1,
) -> CanonicalPlan:
    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "deep_planner",
            "status": "clarify",
            "authority": "advisory",
            "attempt_count": attempts,
            "max_contract_repairs": max_contract_repairs,
            "reason": reason,
        }
    )
    if error is not None:
        detail.update(
            {
                "error_type": type(error).__name__,
                "error": str(error)[:300],
                **llm_failure_metadata(error),
            }
        )
    context = request.context if isinstance(request.context, dict) else {}
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="clarify",
        coverage="uncertain",
        confidence=0.0,
        goal_summary=request.text,
        goal_ids=expected_goal_ids(context),
        response_text="",
        steps=[],
        unresolved=list(unresolved or []),
        metadata=detail,
    )
