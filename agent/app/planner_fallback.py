from __future__ import annotations

import logging
from typing import Any

from .clients.ollama_client import OllamaGenerationError, llm_failure_metadata
from .planner_context import planner_goal_context
try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.planner_fallback")


def _request_goal_ids(request: CognitiveWorkRequest) -> list[str]:
    """Return the exact Planner scope, including typed state re-entry bounds."""

    context = request.context if isinstance(request.context, dict) else {}
    return list(
        planner_goal_context(
            context,
            reentry_scope=request.planner_reentry_scope,
        ).expected_goal_ids
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
        goal_ids=_request_goal_ids(request),
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
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="unavailable",
        coverage="uncertain",
        confidence=0.0,
        goal_summary=request.text,
        goal_ids=_request_goal_ids(request),
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
) -> CanonicalPlan:
    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "deep_planner",
            "status": "clarify",
            "authority": "advisory",
            "attempt_count": attempts,
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
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="deep",
        disposition="clarify",
        coverage="uncertain",
        confidence=0.0,
        goal_summary=request.text,
        goal_ids=_request_goal_ids(request),
        response_text="",
        steps=[],
        unresolved=list(unresolved or []),
        metadata=detail,
    )
