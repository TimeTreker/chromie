from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from shared.chromie_contracts.situation import (
    SituationConditionRef,
    SituationEvidenceRef,
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


__all__ = ["build_situation_projection"]
