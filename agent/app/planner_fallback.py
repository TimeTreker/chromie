from __future__ import annotations

import logging
from typing import Any

from .clients.ollama_client import llm_failure_metadata
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



def _failure_detail(error: Exception | None) -> dict[str, Any]:
    if error is None:
        return {}
    return {
        "error_type": type(error).__name__,
        "error": str(error)[:300],
        **llm_failure_metadata(error),
    }


def materialize_planner_failure(
    plan_id: str,
    request: CognitiveWorkRequest,
    reason: str,
    *,
    response_text: str = "",
    unresolved: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> CanonicalPlan:
    """A rejected or unavailable Planner result: it fails closed and is never repaired.

    The Orchestrator stops the Planner path on ``path_classification=contract_failure``;
    no other model call re-plans the same decision (principles 30 and 31).
    """

    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "fast_planner",
            "status": "failed",
            "authority": "advisory",
            "path_classification": "contract_failure",
            "execution_allowed": False,
            "retryable": False,
            "reason": reason,
            **_failure_detail(error),
        }
    )
    retained_progress = " ".join(str(response_text or "").strip().split())
    if retained_progress:
        detail["retained_progress_response_text"] = {
            "status": "undelivered_advisory",
            "reason": reason,
        }
    detail.setdefault("failure_class", reason)
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="fast",
        disposition="unavailable",
        coverage="uncertain",
        confidence=0.0,
        goal_ids=_request_goal_ids(request),
        goal_summary=request.text,
        response_text=retained_progress,
        steps=[],
        unresolved=list(unresolved or []),
        metadata=detail,
    )


def materialize_planner_unavailable(
    plan_id: str,
    request: CognitiveWorkRequest,
    reason: str,
    *,
    unresolved: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CanonicalPlan:
    """Return a terminal limitation without asking a fake question.

    Missing provider ability, or a plan the Planner itself judged inadequate, is not
    user-semantic ambiguity; additional user detail cannot create an absent
    Capability. The Goal stays unmet and Social Cognition says so honestly.
    """

    detail = dict(metadata or {})
    detail.update(
        {
            "resolver": "fast_planner",
            "status": "unavailable",
            "authority": "advisory",
            "path_classification": "terminal",
            "execution_allowed": False,
            "reason": reason,
        }
    )
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="fast",
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
