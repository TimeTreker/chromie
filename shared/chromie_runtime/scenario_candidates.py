"""Scenario-candidate runtime events derived from reviewed runtime evidence.

A candidate is a proposal, never an executable regression or training sample.
Human approval is required before promotion. The immutable event preserves the
candidate together with the episode/evaluation evidence used to derive it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .runtime_events import persist_runtime_event

SCENARIO_CANDIDATE_EVENT_TYPE = "chromie.scenario_candidate"
SCENARIO_CANDIDATE_EVENT_SUBTYPE = "experience_mined"


def persist_scenario_candidate_event(
    *,
    candidate: Mapping[str, Any],
    episode: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    candidate_path: str | Path | None = None,
    event_root: str | Path | None = None,
    trigger_root: str | Path | None = None,
) -> dict[str, Any]:
    """Persist a pending-review scenario candidate as an immutable event."""

    scenario_id = str(candidate.get("id") or "").strip()
    if not scenario_id:
        raise ValueError("scenario candidate must contain a non-empty id")

    review = candidate.get("review")
    promotion = candidate.get("promotion")
    if not isinstance(review, Mapping) or not review.get("requires_human_review"):
        raise ValueError("scenario candidate must require human review")
    if str(review.get("status") or "") != "pending_human_review":
        raise ValueError("new scenario candidate must be pending human review")
    if not isinstance(promotion, Mapping):
        raise ValueError("scenario candidate must declare promotion policy")
    if any(
        bool(promotion.get(key))
        for key in ("regression_allowed", "training_allowed", "auto_promotion_allowed")
    ):
        raise ValueError("unreviewed scenario candidate cannot be promoted")

    episode_id = str(episode.get("episode_id") or review.get("source_episode_id") or "")
    evaluation_id = str(
        evaluation.get("evaluation_id") or review.get("source_evaluation_id") or ""
    )
    conversation_id = str(
        episode.get("conversation_id") or review.get("source_conversation_id") or ""
    )
    attributes = {
        "scenario_id": scenario_id,
        "suite": str(candidate.get("suite") or ""),
        "level": str(candidate.get("level") or ""),
        "review_status": "pending_human_review",
        "requires_human_review": True,
        "auto_promotion_allowed": False,
        "candidate_path": str(candidate_path or ""),
        "failure_tags": list(evaluation.get("failure_tags") or []),
        "overall_score": evaluation.get("overall_score"),
    }
    correlations = {
        "scenario_id": scenario_id,
        "episode_id": episode_id,
        "evaluation_id": evaluation_id,
        "conversation_id": conversation_id,
    }
    return persist_runtime_event(
        event_type=SCENARIO_CANDIDATE_EVENT_TYPE,
        event_subtype=SCENARIO_CANDIDATE_EVENT_SUBTYPE,
        severity=_severity(evaluation),
        producer="chromie.experience_evaluator",
        payloads={
            "scenario_candidate.json": dict(candidate),
            "source_episode.json": dict(episode),
            "source_evaluation.json": dict(evaluation),
        },
        attributes=attributes,
        correlations=correlations,
        derivation={
            "derived_from_episode": bool(episode_id),
            "derived_from_evaluation": bool(evaluation_id),
            "requires_human_review": True,
            "scenario_auto_promotion_allowed": False,
            "training_auto_promotion_allowed": False,
        },
        event_root=event_root,
        trigger_root=trigger_root,
    )


def _severity(evaluation: Mapping[str, Any]) -> str:
    severity = str(evaluation.get("severity") or "").strip().lower()
    return severity if severity in {"minor", "major", "critical"} else "info"
