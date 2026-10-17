from __future__ import annotations

import logging
from typing import Any

from .clients.ollama_client import llm_failure_metadata
from .planner_context import planner_goal_context
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.plan import CanonicalPlan, SocialCommunicationNeed, communication_need_id

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
    Capability. The Goal stays unmet and Social Cognition says so honestly: each
    Goal carries a Planner result need, the same one a streamed limitation carries
    (live 2026-10-12: a re-entry limitation without one left only silence).
    """

    goal_context = planner_goal_context(
        request.context if isinstance(request.context, dict) else {},
        reentry_scope=request.planner_reentry_scope,
    )
    request_refs = {item.local_ref for item in request.responsibilities}
    refs_by_goal = {
        str(goal.get("goal_id")): [
            str(ref) for ref in goal.get("source_responsibility_refs") or [] if str(ref) in request_refs
        ]
        for goal in goal_context.authoritative_goals if isinstance(goal, dict)
    }
    needs = [
        SocialCommunicationNeed(
            need_id=communication_need_id(plan_id, goal_id), owner="planner", kind="result",
            reference_id=plan_id, source_goal_ids=[goal_id],
            source_responsibility_refs=refs_by_goal.get(goal_id, []),
            facts={"goal_id": goal_id, "disposition": "unavailable", "coverage": "uncertain",
                   "unresolved": list(unresolved or []),
                   "rationale": ("Chromie did not reach a plan she could commit to this time; "
                                 "no ability is known to be missing."),
                   "capability_known_missing": False},
        )
        for goal_id in goal_context.expected_goal_ids
    ]
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
        goal_ids=list(goal_context.expected_goal_ids),
        response_text="",
        steps=[],
        unresolved=list(unresolved or []),
        communication_needs=needs,
        metadata=detail,
    )
