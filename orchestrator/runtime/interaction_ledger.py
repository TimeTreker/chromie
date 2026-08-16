"""Append-only interaction facts and bounded Goal-scoped cognition context."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

from shared.chromie_contracts.execution_outcome import ExecutionOutcomeBundle
from shared.chromie_contracts.interaction import CapabilityRequest, CapabilityResult
from shared.chromie_contracts.interaction_ledger import (
    InteractionContextProjection,
    InteractionEventDomain,
    InteractionEventOwner,
    InteractionEventType,
    InteractionLedgerEvent,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint


_ACTIVITY_EVENT_BY_STATUS: dict[str, InteractionEventType] = {
    "completed": "activity_completed",
    "partial": "activity_partial",
    "failed": "activity_failed",
    "cancelled": "activity_cancelled",
    "timed_out": "activity_timed_out",
    "refused": "activity_refused",
    "not_run": "activity_not_run",
}
_VOCAL_ACTION_EVENT_BY_STATUS: dict[str, InteractionEventType] = {
    "completed": "vocal_action_completed",
    "partial": "vocal_action_partial",
    "failed": "vocal_action_failed",
    "cancelled": "vocal_action_cancelled",
    "timed_out": "vocal_action_timed_out",
    "refused": "vocal_action_refused",
    "not_run": "vocal_action_not_run",
}
_SOCIAL_EVENT_BY_STATUS: dict[str, InteractionEventType] = {
    "completed": "social_decoration_completed",
    "failed": "social_decoration_failed",
    "cancelled": "social_decoration_cancelled",
    "timed_out": "social_decoration_timed_out",
    "refused": "social_decoration_refused",
    "not_run": "social_decoration_not_run",
}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalized_ids(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalized_text(item)
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _stable_event_id(*parts: Any) -> str:
    payload = json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "interaction_event_" + hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:24]


class InteractionLedger:
    """Bounded append-only journal of facts authored by existing owners.

    Entries are immutable and replay-safe. The ledger does not infer semantic
    equivalence or execution success; its typed append methods accept only the
    records produced by the owner that is authoritative for that event kind.
    """

    def __init__(self, *, max_events_per_session: int = 160) -> None:
        if max_events_per_session < 16:
            raise ValueError("max_events_per_session must be at least 16")
        self.max_events_per_session = int(max_events_per_session)
        self._events: dict[str, deque[InteractionLedgerEvent]] = {}
        self._event_by_id: dict[str, dict[str, InteractionLedgerEvent]] = {}
        self._event_receipts: dict[
            str,
            dict[str, tuple[str, int, datetime]],
        ] = {}
        self._next_sequence: dict[str, int] = {}

    def append(
        self,
        *,
        session_id: str,
        owner: InteractionEventOwner,
        domain: InteractionEventDomain,
        event_type: InteractionEventType,
        state: str,
        subject_id: str,
        event_id: str,
        turn_id: str = "",
        interaction_id: str = "",
        goal_ids: Iterable[str] = (),
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        capability_id: str = "",
        speech_act: str = "",
        text: str = "",
        evidence_refs: Iterable[str] = (),
        occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InteractionLedgerEvent:
        sid = _normalized_text(session_id)
        if not sid:
            raise ValueError("interaction ledger event requires session_id")
        normalized_event_id = _normalized_text(event_id)
        if not normalized_event_id:
            raise ValueError("interaction ledger event requires event_id")
        candidate = {
            "owner": owner,
            "domain": domain,
            "event_type": event_type,
            "state": _normalized_text(state),
            "subject_id": _normalized_text(subject_id),
            "turn_id": _normalized_text(turn_id),
            "interaction_id": _normalized_text(interaction_id),
            "goal_ids": _normalized_ids(list(goal_ids)),
            "canonical_plan_id": _normalized_text(canonical_plan_id),
            "canonical_plan_fingerprint": _normalized_text(
                canonical_plan_fingerprint
            ),
            "capability_id": _normalized_text(capability_id),
            "speech_act": _normalized_text(speech_act),
            "text": _normalized_text(text),
            "evidence_refs": _normalized_ids(list(evidence_refs)),
            "metadata": deepcopy(metadata or {}),
        }
        candidate_signature = hashlib.sha256(
            json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        by_id = self._event_by_id.setdefault(sid, {})
        receipts = self._event_receipts.setdefault(sid, {})
        receipt = receipts.get(normalized_event_id)
        if receipt is not None:
            retained_signature, retained_sequence, retained_time = receipt
            if retained_signature != candidate_signature:
                raise ValueError(
                    "interaction ledger replay changed an immutable event"
                )
            existing = by_id.get(normalized_event_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            return InteractionLedgerEvent(
                event_id=normalized_event_id,
                sequence=retained_sequence,
                session_id=sid,
                occurred_at=retained_time,
                **candidate,
            )

        sequence = self._next_sequence.get(sid, 0) + 1
        event = InteractionLedgerEvent(
            event_id=normalized_event_id,
            sequence=sequence,
            session_id=sid,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            **candidate,
        )
        events = self._events.setdefault(sid, deque())
        if len(events) >= self.max_events_per_session:
            removed = events.popleft()
            by_id.pop(removed.event_id, None)
        events.append(event)
        by_id[event.event_id] = event
        receipts[event.event_id] = (
            candidate_signature,
            sequence,
            event.occurred_at,
        )
        self._next_sequence[sid] = sequence
        return event.model_copy(deep=True)

    def record_playback_event(
        self,
        event: dict[str, Any],
    ) -> InteractionLedgerEvent | None:
        status = _normalized_text(event.get("status"))
        event_type_by_status: dict[str, InteractionEventType] = {
            "scheduled": "speech_scheduled",
            "playback_started": "speech_playback_started",
            "playback_completed": "speech_playback_started",
            "not_delivered": "speech_not_delivered",
        }
        event_type = event_type_by_status.get(status)
        speech_event_id = _normalized_text(event.get("event_id"))
        session_id = _normalized_text(event.get("session_id"))
        if event_type is None or not speech_event_id or not session_id:
            return None
        ledger_event_id = _stable_event_id(
            "playback_delivery",
            session_id,
            speech_event_id,
            status,
        )
        return self.append(
            session_id=session_id,
            owner="playback_delivery",
            domain="vocal",
            event_type=event_type,
            state=status,
            subject_id=speech_event_id,
            event_id=ledger_event_id,
            turn_id=_normalized_text(event.get("turn_id")),
            goal_ids=_normalized_ids(event.get("source_goal_ids")),
            canonical_plan_id=_normalized_text(
                event.get("canonical_plan_id")
            ),
            canonical_plan_fingerprint=_normalized_text(
                event.get("canonical_plan_fingerprint")
            ),
            speech_act=_normalized_text(
                event.get("purpose") or event.get("speech_act")
            ),
            text=_normalized_text(event.get("text")),
            evidence_refs=[speech_event_id],
            metadata={
                "delivery_role": _normalized_text(
                    event.get("delivery_role")
                ),
                "claims": _normalized_ids(event.get("claims")),
                "commitment": _normalized_text(event.get("commitment")),
                "must_not_claim_completion": event.get(
                    "must_not_claim_completion"
                ),
                "playback_reason": _normalized_text(
                    event.get("playback_reason")
                ),
            },
        )

    def record_goal_association(
        self,
        *,
        session_id: str,
        turn_id: str,
        interaction_id: str,
        association_id: str,
        goal_ids: Iterable[str],
        relationships: Iterable[str],
    ) -> InteractionLedgerEvent:
        normalized_goals = _normalized_ids(list(goal_ids))
        normalized_relationships = _normalized_ids(list(relationships))
        subject_id = _normalized_text(association_id) or _stable_event_id(
            session_id,
            turn_id,
            normalized_goals,
            normalized_relationships,
        )
        return self.append(
            session_id=session_id,
            owner="cognitive_runtime",
            domain="cognition",
            event_type="goal_associated",
            state="resolved",
            subject_id=subject_id,
            event_id=_stable_event_id(
                "goal_associated",
                session_id,
                turn_id,
                subject_id,
            ),
            turn_id=turn_id,
            interaction_id=interaction_id,
            goal_ids=normalized_goals,
            metadata={"relationships": normalized_relationships},
        )

    def record_plan(
        self,
        *,
        session_id: str,
        turn_id: str,
        interaction_id: str,
        plan: CanonicalPlan,
    ) -> InteractionLedgerEvent:
        fingerprint = canonical_plan_fingerprint(plan)
        return self.append(
            session_id=session_id,
            owner="cognitive_runtime",
            domain="cognition",
            event_type="plan_resolved",
            state=plan.disposition,
            subject_id=plan.plan_id,
            event_id=_stable_event_id(
                "plan_resolved",
                session_id,
                turn_id,
                plan.plan_id,
                fingerprint,
            ),
            turn_id=turn_id,
            interaction_id=interaction_id,
            goal_ids=plan.goal_ids,
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            metadata={
                "planner_tier": plan.planner_tier,
                "step_count": len(plan.steps),
                "disposition": plan.disposition,
            },
        )

    def record_committed_requests(
        self,
        *,
        session_id: str,
        turn_id: str,
        interaction_id: str,
        requests: Iterable[CapabilityRequest],
    ) -> list[InteractionLedgerEvent]:
        recorded: list[InteractionLedgerEvent] = []
        for request in requests:
            metadata = request.metadata
            social = metadata.get("auxiliary_social_attention") is True
            vocal = (
                metadata.get("execution_lane") == "vocal" and not social
            )
            event_type: InteractionEventType = (
                "social_decoration_committed"
                if social
                else "vocal_action_committed"
                if vocal
                else "activity_committed"
            )
            domain: InteractionEventDomain = (
                "social_attention"
                if social
                else "vocal"
                if vocal
                else "activity"
            )
            plan_id = _normalized_text(metadata.get("canonical_plan_id"))
            fingerprint = _normalized_text(
                metadata.get("canonical_plan_fingerprint")
            )
            recorded.append(
                self.append(
                    session_id=session_id,
                    owner="trusted_capability_runtime",
                    domain=domain,
                    event_type=event_type,
                    state="committed",
                    subject_id=request.request_id,
                    event_id=_stable_event_id(
                        event_type,
                        session_id,
                        request.request_id,
                        plan_id,
                        fingerprint,
                    ),
                    turn_id=turn_id,
                    interaction_id=interaction_id,
                    goal_ids=_normalized_ids(
                        metadata.get("source_goal_ids")
                    ),
                    canonical_plan_id=plan_id,
                    canonical_plan_fingerprint=fingerprint,
                    capability_id=request.capability_id,
                    evidence_refs=[request.request_id],
                    metadata={
                        "timing": request.timing,
                        "social_attention_purpose": metadata.get(
                            "social_attention_purpose"
                        ),
                    },
                )
            )
        return recorded

    def record_execution_outcome(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        session_id: str,
    ) -> list[InteractionLedgerEvent]:
        validated = ExecutionOutcomeBundle.model_validate(bundle)
        evidence_by_id = {
            item.evidence_id: item for item in validated.evidence
        }
        recorded: list[InteractionLedgerEvent] = []
        for outcome in validated.goal_outcomes:
            goal_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in outcome.evidence_ids
            ]
            capability_ids = _normalized_ids(
                [item.capability_id for item in goal_evidence]
            )
            execution_lanes = _normalized_ids(
                [
                    item.metadata.get("execution_lane")
                    for item in goal_evidence
                ]
            )
            vocal = execution_lanes == ["vocal"]
            event_type = (
                _VOCAL_ACTION_EVENT_BY_STATUS[outcome.status]
                if vocal
                else _ACTIVITY_EVENT_BY_STATUS[outcome.status]
            )
            domain: InteractionEventDomain = (
                "vocal" if vocal else "activity"
            )
            evidence_refs = [
                validated.outcome_id,
                *outcome.evidence_ids,
                *[item.request_id for item in goal_evidence],
            ]
            recorded.append(
                self.append(
                    session_id=session_id,
                    owner="execution_closure",
                    domain=domain,
                    event_type=event_type,
                    state=outcome.status,
                    subject_id=f"{validated.outcome_id}:{outcome.goal_id}",
                    event_id=_stable_event_id(
                        event_type,
                        session_id,
                        validated.outcome_id,
                        outcome.goal_id,
                    ),
                    turn_id=validated.turn_id,
                    interaction_id=validated.interaction_id,
                    goal_ids=[outcome.goal_id],
                    canonical_plan_id=validated.canonical_plan_id,
                    canonical_plan_fingerprint=(
                        validated.canonical_plan_fingerprint
                    ),
                    capability_id=(
                        capability_ids[0]
                        if len(capability_ids) == 1
                        else ""
                    ),
                    evidence_refs=evidence_refs,
                    metadata={
                        "capability_ids": capability_ids,
                        "execution_lanes": execution_lanes,
                        "completed_step_ids": list(
                            outcome.completed_step_ids
                        ),
                        "unresolved_step_ids": list(
                            outcome.unresolved_step_ids
                        ),
                        "reason_codes": list(outcome.reason_codes),
                    },
                )
            )
        return recorded

    def record_social_results(
        self,
        *,
        session_id: str,
        turn_id: str,
        interaction_id: str,
        requests: Iterable[CapabilityRequest],
        results: Iterable[CapabilityResult],
    ) -> list[InteractionLedgerEvent]:
        requests_by_id = {
            item.request_id: item
            for item in requests
            if item.metadata.get("auxiliary_social_attention") is True
        }
        recorded: list[InteractionLedgerEvent] = []
        for result in results:
            request = requests_by_id.get(result.request_id)
            if request is None:
                continue
            normalized_status = _normalized_text(result.status)
            event_type = _SOCIAL_EVENT_BY_STATUS.get(
                normalized_status,
                "social_decoration_failed",
            )
            metadata = request.metadata
            evidence_refs = [request.request_id]
            if result.trace_id:
                evidence_refs.append(result.trace_id)
            recorded.append(
                self.append(
                    session_id=session_id,
                    owner="trusted_capability_runtime",
                    domain="social_attention",
                    event_type=event_type,
                    state=normalized_status or "failed",
                    subject_id=request.request_id,
                    event_id=_stable_event_id(
                        event_type,
                        session_id,
                        request.request_id,
                        normalized_status,
                    ),
                    turn_id=turn_id,
                    interaction_id=interaction_id,
                    goal_ids=_normalized_ids(
                        metadata.get("source_goal_ids")
                    ),
                    canonical_plan_id=_normalized_text(
                        metadata.get("canonical_plan_id")
                    ),
                    canonical_plan_fingerprint=_normalized_text(
                        metadata.get("canonical_plan_fingerprint")
                    ),
                    capability_id=request.capability_id,
                    evidence_refs=evidence_refs,
                    occurred_at=result.finished_at,
                    metadata={
                        "reason_code": result.reason_code,
                        "message": result.message,
                    },
                )
            )
        return recorded

    def events(self, session_id: str) -> list[InteractionLedgerEvent]:
        return [
            event.model_copy(deep=True)
            for event in self._events.get(_normalized_text(session_id), ())
        ]

    def context(
        self,
        session_id: str,
        *,
        goal_ids: Iterable[str] = (),
        turn_id: str = "",
        limit: int = 48,
    ) -> InteractionContextProjection:
        sid = _normalized_text(session_id)
        requested_goals = _normalized_ids(list(goal_ids))
        goal_set = set(requested_goals)
        normalized_turn_id = _normalized_text(turn_id)
        selected: list[InteractionLedgerEvent] = []
        for event in self.events(sid):
            if goal_set:
                if goal_set.intersection(event.goal_ids):
                    selected.append(event)
                elif (
                    not event.goal_ids
                    and normalized_turn_id
                    and event.turn_id == normalized_turn_id
                ):
                    selected.append(event)
            else:
                selected.append(event)
        selected = selected[-max(1, int(limit)) :]

        projected_events = [self._prompt_event(item) for item in selected]
        already_spoken = [
            item
            for item in projected_events
            if item["event_type"] == "speech_playback_started"
        ]
        latest_by_subject = {
            item["subject_id"]: item for item in projected_events
        }
        pending_speech = [
            item
            for item in latest_by_subject.values()
            if item["event_type"] == "speech_scheduled"
        ]
        activity = [
            item
            for item in projected_events
            if item["domain"] == "activity"
        ]
        vocal_actions = [
            item
            for item in projected_events
            if item["event_type"].startswith("vocal_action_")
        ]
        social_decorations = [
            item
            for item in projected_events
            if item["domain"] == "social_attention"
        ]
        goal_history = [
            item
            for item in projected_events
            if item["domain"] == "cognition"
        ]
        unresolved: list[dict[str, Any]] = []
        terminal_evidence_refs = {
            evidence_ref
            for item in projected_events
            if (
                item["event_type"].startswith("activity_")
                and item["event_type"] != "activity_committed"
            )
            or (
                item["event_type"].startswith("vocal_action_")
                and item["event_type"] != "vocal_action_committed"
            )
            for evidence_ref in item["evidence_refs"]
        }
        for item in latest_by_subject.values():
            waiting_for = ""
            if item["event_type"] == "speech_scheduled":
                waiting_for = "speech_playback_start"
            elif item["event_type"] == "activity_committed":
                if item["subject_id"] not in terminal_evidence_refs:
                    waiting_for = "activity_terminal_result"
            elif item["event_type"] == "vocal_action_committed":
                if item["subject_id"] not in terminal_evidence_refs:
                    waiting_for = "vocal_action_terminal_result"
            elif item["event_type"] == "social_decoration_committed":
                waiting_for = "social_decoration_terminal_result"
            if waiting_for:
                unresolved.append(
                    {
                        "subject_id": item["subject_id"],
                        "goal_ids": item["goal_ids"],
                        "waiting_for": waiting_for,
                    }
                )

        return InteractionContextProjection(
            session_id=sid,
            goal_ids=requested_goals,
            event_count=len(projected_events),
            events=projected_events,
            already_spoken=already_spoken,
            pending_speech=pending_speech,
            activity=activity,
            vocal_actions=vocal_actions,
            social_decorations=social_decorations,
            goal_history=goal_history,
            unresolved=unresolved,
        )

    @staticmethod
    def _prompt_event(event: InteractionLedgerEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "turn_id": event.turn_id,
            "interaction_id": event.interaction_id,
            "owner": event.owner,
            "domain": event.domain,
            "event_type": event.event_type,
            "state": event.state,
            "goal_ids": list(event.goal_ids),
            "canonical_plan_id": event.canonical_plan_id,
            "canonical_plan_fingerprint": (
                event.canonical_plan_fingerprint
            ),
            "subject_id": event.subject_id,
            "capability_id": event.capability_id,
            "speech_act": event.speech_act,
            "text": event.text,
            "evidence_refs": list(event.evidence_refs),
            "occurred_at": event.occurred_at.isoformat(),
            "metadata": dict(event.metadata),
        }


__all__ = ["InteractionLedger"]
