"""Playback delivery state and current-turn speech provenance.

The collaborator owns transport lifecycle facts only: order allocation, playback
barriers, cancellation, and whether speech started, completed, or was interrupted. It never decides
whether two utterances mean the same thing; later model stages receive the
playback-qualified speech events and make that semantic judgment.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable


PlaybackKey = tuple[int, int, str | None]
PendingAudio = tuple[int, Any, int, str | None, str | None]


@dataclass
class PlaybackDeliveryLifecycle:
    """Mutable lifecycle state for one VoiceAssistant runtime."""

    interaction_event_sink: Callable[[dict[str, Any]], Any] | None = None
    next_playback_order: int = 0
    synthesis_order: int = 0
    playback_generation: int = 0
    pending_audio: dict[int, PendingAudio] = field(default_factory=dict)
    tts_text_by_generation: dict[int, list[str]] = field(default_factory=dict)
    playback_start_waiters: dict[PlaybackKey, asyncio.Future[bool]] = field(
        default_factory=dict
    )
    playback_release_waiters: dict[PlaybackKey, asyncio.Future[bool]] = field(
        default_factory=dict
    )
    playback_released_keys: set[PlaybackKey] = field(default_factory=set)
    cancelled_playback_orders: set[PlaybackKey] = field(default_factory=set)
    turn_speech_events: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    turn_speech_event_by_playback_key: dict[PlaybackKey, str] = field(
        default_factory=dict
    )
    speech_order_facts: dict[PlaybackKey, list[tuple[str, str]]] = field(
        default_factory=dict
    )
    order_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    speech_submission_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    playback_queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    playback_task: asyncio.Task[Any] | None = None
    active_synthesis_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    synthesis_semaphore: asyncio.Semaphore | None = None
    output_stream: Any | None = None
    output_stream_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    output_write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    output_duck_generation: int | None = None
    output_duck_session_id: str | None = None
    output_duck_started_ms: float | None = None
    output_duck_released: asyncio.Event = field(default_factory=asyncio.Event)
    output_duck_timeout_task: asyncio.Task[Any] | None = None
    transport: Any | None = None

    def __post_init__(self) -> None:
        self.output_duck_released.set()

    @staticmethod
    def key(
        generation: int,
        order: int,
        session_id: str | None,
    ) -> PlaybackKey:
        return (int(generation), int(order), session_id)

    def reserve_order(
        self,
        *,
        session_id: str | None,
        is_stale: Callable[[int, str | None], bool],
    ) -> tuple[int, int] | None:
        """Reserve one synthesis order under the caller-held ``order_lock``."""

        generation = self.playback_generation
        if is_stale(generation, session_id):
            return None
        order = self.synthesis_order
        self.synthesis_order += 1
        return generation, order

    def create_playback_start_waiter(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
    ) -> asyncio.Future[bool]:
        key = self.key(generation, order, session_id)
        waiter = asyncio.get_running_loop().create_future()
        self.playback_start_waiters[key] = waiter
        return waiter

    def register_turn_speech_event(
        self,
        *,
        session_id: str | None,
        generation: int,
        orders: list[int],
        normalized_text: str,
        stage: str,
        purpose: str,
        commitment: str = "",
        fast_activity_id: str = "",
        communicative_activity_ids: list[str] | None = None,
        turn_id: str | None = None,
        source_goal_ids: list[str] | None = None,
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        goal_association_fingerprint: str = "",
        delivery_role: str = "response",
        claims: list[str] | None = None,
        must_not_claim_completion: bool | None = None,
        cognitive_opportunity_id: str = "",
        situation_signature: str = "",
        subject_refs: list[str] | None = None,
        origin_session_id: str | None = None,
    ) -> dict[str, Any] | None:
        sid = str(origin_session_id or session_id or "").strip()
        text = str(normalized_text or "").strip()
        if not sid or not orders or not text:
            return None
        normalized_turn_id = " ".join(str(turn_id or sid).strip().split())
        normalized_fast_activity_id = " ".join(
            str(fast_activity_id or "").strip().split()
        )
        normalized_activity_ids = self._normalized_text_values(
            communicative_activity_ids
        )
        if (
            normalized_fast_activity_id
            and normalized_fast_activity_id not in normalized_activity_ids
        ):
            normalized_activity_ids.append(normalized_fast_activity_id)
            normalized_activity_ids.sort()
        normalized_goal_ids = self._normalized_text_values(source_goal_ids)
        normalized_claims = self._normalized_text_values(claims)
        normalized_subject_refs = self._normalized_text_values(subject_refs)
        normalized_opportunity_id = " ".join(
            str(cognitive_opportunity_id or "").strip().split()
        )
        normalized_situation_signature = " ".join(
            str(situation_signature or "").strip().split()
        )
        normalized_plan_id = " ".join(str(canonical_plan_id or "").strip().split())
        normalized_plan_fingerprint = " ".join(
            str(canonical_plan_fingerprint or "").strip().split()
        )
        normalized_association_fingerprint = " ".join(
            str(goal_association_fingerprint or "").strip().split()
        )
        normalized_delivery_role = (
            " ".join(str(delivery_role or "response").strip().split()) or "response"
        )
        # ``event_id`` is semantic identity: one Planner Communicative Activity
        # remains one speech event even when transport is retried under a new
        # generation/order.  Transport correlation belongs to ``delivery_attempt_id``.
        # Wording is payload integrity rather than de-duplication identity.
        if normalized_activity_ids:
            event_identity = {
                "communicative_activity_ids": normalized_activity_ids,
                "session_id": sid,
                "turn_id": normalized_turn_id,
            }
        else:
            event_identity = {
                "canonical_plan_fingerprint": normalized_plan_fingerprint,
                "canonical_plan_id": normalized_plan_id,
                "claims": normalized_claims,
                "commitment": str(commitment or ""),
                "delivery_role": normalized_delivery_role,
                "goal_association_fingerprint": normalized_association_fingerprint,
                "must_not_claim_completion": must_not_claim_completion,
                "purpose": str(purpose or ""),
                "session_id": sid,
                "source_goal_ids": normalized_goal_ids,
                "stage": str(stage or ""),
                "turn_id": normalized_turn_id,
            }
        event_seed = json.dumps(
            event_identity,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        event_id = "speech_event_" + hashlib.sha256(
            event_seed.encode("utf-8")
        ).hexdigest()[:20]
        normalized_orders = [int(order) for order in orders]
        attempt_seed = json.dumps(
            {
                "event_id": event_id,
                "generation": int(generation),
                "orders": normalized_orders,
                "playback_session_id": session_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        delivery_attempt_id = "speech_attempt_" + hashlib.sha256(
            attempt_seed.encode("utf-8")
        ).hexdigest()[:20]
        attempt = {
            "delivery_attempt_id": delivery_attempt_id,
            "generation": int(generation),
            "orders": normalized_orders,
            "status": "scheduled",
            "playback_session_id": session_id,
            "order_states": {str(order): "scheduled" for order in normalized_orders},
        }
        events = self.turn_speech_events.setdefault(sid, [])
        existing = next(
            (item for item in reversed(events) if item.get("event_id") == event_id),
            None,
        )
        if existing is None:
            event = {
                "event_id": event_id,
                "delivery_attempt_id": delivery_attempt_id,
                "delivery_attempts": [attempt],
                "session_id": sid,
                "playback_session_id": session_id,
                "turn_id": normalized_turn_id,
                "stage": str(stage or ""),
                "purpose": str(purpose or ""),
                "status": "scheduled",
                "text": text,
                "commitment": str(commitment or ""),
                "source_goal_ids": normalized_goal_ids,
                "canonical_plan_id": normalized_plan_id,
                "canonical_plan_fingerprint": normalized_plan_fingerprint,
                "goal_association_fingerprint": normalized_association_fingerprint,
                "delivery_role": normalized_delivery_role,
                "fast_activity_id": normalized_fast_activity_id,
                "communicative_activity_ids": normalized_activity_ids,
                "claims": normalized_claims,
                "must_not_claim_completion": must_not_claim_completion,
                "cognitive_opportunity_id": normalized_opportunity_id,
                "situation_signature": normalized_situation_signature,
                "subject_refs": normalized_subject_refs,
                "generation": int(generation),
                "orders": normalized_orders,
            }
            events.append(event)
            if len(events) > 12:
                del events[:-12]
        else:
            if existing.get("text") != text:
                raise ValueError("Communicative Activity wording cannot change under one identity")
            if existing.get("delivery_attempt_id") == delivery_attempt_id:
                return existing
            event = existing
            event.pop("playback_reason", None)
            attempts = event.setdefault("delivery_attempts", [])
            if not any(
                item.get("delivery_attempt_id") == delivery_attempt_id
                for item in attempts
                if isinstance(item, dict)
            ):
                attempts.append(attempt)
                if len(attempts) > 8:
                    del attempts[:-8]
            event.update(
                {
                    "delivery_attempt_id": delivery_attempt_id,
                    "status": "scheduled",
                    "text": text,
                    "generation": int(generation),
                    "orders": normalized_orders,
                    "playback_session_id": session_id,
                }
            )
        for order in normalized_orders:
            self.turn_speech_event_by_playback_key[
                self.key(generation, order, session_id)
            ] = event_id
        self._publish_interaction_event(event)
        # Playback may finish while the caller is still scheduling later chunks.
        # Bind the retained transport facts after all orders have an Activity owner.
        for order in normalized_orders:
            for state, reason in self.speech_order_facts.get(
                self.key(generation, order, session_id), ()
            ):
                self._update_speech_order(
                    generation=generation, order=order, session_id=session_id,
                    state=state, reason=reason, retain_fact=False,
                )
        return event

    @staticmethod
    def _normalized_text_values(values: Any) -> list[str]:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple, set)):
            return []
        return sorted(
            {
                text
                for item in values
                if (text := " ".join(str(item or "").strip().split()))
            }
        )

    def find_turn_speech_event_for_activities(
        self,
        *,
        session_id: str | None,
        turn_id: str | None,
        communicative_activity_ids: list[str] | tuple[str, ...] | set[str],
        reusable_statuses: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return one already-scheduled semantic Communicative Activity event.

        This is an idempotency lookup, not semantic matching: callers must supply
        the exact Planner-owned Activity IDs.  Wording similarity never qualifies
        reuse.
        """

        sid = " ".join(str(session_id or "").strip().split())
        normalized_turn_id = " ".join(str(turn_id or sid).strip().split())
        activity_ids = self._normalized_text_values(communicative_activity_ids)
        if not sid or not activity_ids:
            return None
        statuses = reusable_statuses or {
            "scheduled",
            "playback_started",
            "playback_completed",
        }
        for event in reversed(self.turn_speech_events.get(sid, [])):
            if str(event.get("turn_id") or "") != normalized_turn_id:
                continue
            if self._normalized_text_values(
                event.get("communicative_activity_ids")
            ) != activity_ids:
                continue
            if str(event.get("status") or "") not in statuses:
                continue
            return dict(event)
        return None

    def _publish_interaction_event(self, event: dict[str, Any]) -> None:
        if self.interaction_event_sink is None:
            return
        self.interaction_event_sink(
            {
                **event,
                "orders": list(event.get("orders") or []),
                "source_goal_ids": list(
                    event.get("source_goal_ids") or []
                ),
                "claims": list(event.get("claims") or []),
                "communicative_activity_ids": list(
                    event.get("communicative_activity_ids") or []
                ),
                "delivery_attempts": [
                    dict(item)
                    for item in event.get("delivery_attempts") or []
                    if isinstance(item, dict)
                ],
            }
        )

    def update_turn_speech_event_for_playback(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        started: bool,
        reason: str,
    ) -> None:
        self._update_speech_order(
            generation=generation, order=order, session_id=session_id,
            state="playback_started" if started else "not_delivered", reason=reason,
        )

    def complete_turn_speech_order(
        self, *, generation: int, order: int, session_id: str | None,
        completed: bool, reason: str,
    ) -> None:
        """Record the actual terminal playback result, never a resource release."""
        self._update_speech_order(
            generation=generation, order=order, session_id=session_id,
            state="playback_completed" if completed else "not_delivered", reason=reason,
        )
        self.resolve_playback_release_waiter(generation=generation, order=order,
            session_id=session_id, reason=reason)

    async def wait_for_speech_completion(
        self, session_id: str | None, scheduled: dict[str, Any], *, timeout_s: float = 30.0,
    ) -> bool:
        """Qualify one exact delivery attempt after its scheduling/start receipt."""
        events = self.turn_speech_events.get(str(session_id or ""), [])
        event = next((item for item in reversed(events)
            if item.get("event_id") == scheduled.get("speech_event_id")), None)
        if event is None:
            return False
        generation = scheduled.get("generation")
        orders = scheduled.get("orders")
        if not isinstance(orders, list) or not orders or generation != event.get("generation") or orders != event.get("orders"):
            return False
        attempt_id = event.get("delivery_attempt_id")
        playback_session_id = event.get("playback_session_id", session_id)
        if event.get("status") == "playback_completed":
            return True
        if event.get("status") not in {"scheduled", "playback_started"}:
            return False
        for order in orders:
            key = self.key(generation, order, playback_session_id)
            if key not in self.playback_released_keys:
                self.create_playback_release_waiter(generation=generation, order=order, session_id=playback_session_id)
        await asyncio.gather(*(self.wait_for_playback_release(
            generation=generation, order=order, session_id=playback_session_id, timeout_s=timeout_s,
        ) for order in orders))
        return event.get("delivery_attempt_id") == attempt_id and event.get("status") == "playback_completed"

    def _update_speech_order(
        self, *, generation: int, order: int, session_id: str | None,
        state: str, reason: str, retain_fact: bool = True,
    ) -> None:
        key = self.key(generation, order, session_id)
        if retain_fact:
            facts = self.speech_order_facts.setdefault(key, [])
            if facts and facts[-1][0] != "playback_started":
                return
            if not facts or facts[-1][0] != state:
                facts.append((state, reason))
        event_id = self.turn_speech_event_by_playback_key.get(key)
        if not event_id:
            return
        # Physical playback may be detached from its original conversation session.
        # The exact playback key still binds it to one retained speech event.
        for event in (item for events in self.turn_speech_events.values() for item in reversed(events)):
            if event.get("event_id") != event_id:
                continue
            # A late callback from an old attempt cannot rewrite a current retry.
            if event.get("generation") != generation or order not in event.get("orders", []):
                self.turn_speech_event_by_playback_key.pop(key, None)
                return
            attempt = next((item for item in reversed(event.get("delivery_attempts", []))
                if item.get("delivery_attempt_id") == event.get("delivery_attempt_id")), None)
            if attempt is None:
                return
            states = attempt["order_states"]
            previous = states.get(str(order))
            if previous in {"playback_completed", "not_delivered", "playback_interrupted"}:
                return
            if state == "not_delivered" and previous == "playback_started":
                state = "playback_interrupted"
            states[str(order)] = state
            if state != "playback_started":
                self.turn_speech_event_by_playback_key.pop(key, None)
            values = set(states.values())
            heard = bool(values & {"playback_started", "playback_completed", "playback_interrupted"})
            if values == {"playback_completed"}:
                status = "playback_completed"
            elif values & {"scheduled", "playback_started"}:
                status = "playback_started" if heard else "scheduled"
            else:
                status = "playback_interrupted" if heard else "not_delivered"
            attempt["status"] = status
            if event.get("status") == status:
                return
            event["status"] = status
            event["playback_reason"] = str(reason or "")
            attempt["playback_reason"] = str(reason or "")
            self._publish_interaction_event(event)
            return

    def delivered_turn_speech_events(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        return [
            dict(event)
            for event in self.turn_speech_events.get(str(session_id or ""), [])
            if event.get("status") == "playback_completed"
        ]

    def resolve_playback_start_waiter(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        started: bool,
        reason: str,
    ) -> bool:
        key = self.key(generation, order, session_id)
        waiter = self.playback_start_waiters.pop(key, None)
        if waiter is None or waiter.done():
            return False
        waiter.set_result(started)
        self.update_turn_speech_event_for_playback(
            generation=generation,
            order=order,
            session_id=session_id,
            started=started,
            reason=reason,
        )
        return True

    def resolve_all_playback_start_waiters(
        self,
        *,
        started: bool,
        reason: str,
    ) -> list[PlaybackKey]:
        waiters = list(self.playback_start_waiters.items())
        self.playback_start_waiters.clear()
        resolved: list[PlaybackKey] = []
        for (generation, order, session_id), waiter in waiters:
            if waiter.done():
                continue
            waiter.set_result(started)
            self.update_turn_speech_event_for_playback(
                generation=generation,
                order=order,
                session_id=session_id,
                started=started,
                reason=reason,
            )
            resolved.append((generation, order, session_id))
        return resolved

    async def wait_for_playback_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        timeout_s: float,
    ) -> bool:
        waiter = self.playback_start_waiters.get(
            self.key(generation, order, session_id)
        )
        if waiter is None:
            return False
        try:
            return await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout_s)
        except TimeoutError:
            return False

    def create_playback_release_waiter(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
    ) -> asyncio.Future[bool]:
        key = self.key(generation, order, session_id)
        waiter = self.playback_release_waiters.get(key)
        if waiter is None or waiter.done():
            waiter = asyncio.get_running_loop().create_future()
            self.playback_release_waiters[key] = waiter
        return waiter

    def resolve_playback_release_waiter(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        reason: str,
    ) -> bool:
        key = self.key(generation, order, session_id)
        self.playback_released_keys.add(key)
        waiter = self.playback_release_waiters.pop(key, None)
        if waiter is None or waiter.done():
            return False
        waiter.set_result(True)
        return True

    def resolve_all_playback_release_waiters(self, *, reason: str) -> list[PlaybackKey]:
        keys = list(self.playback_release_waiters)
        for generation, order, session_id in keys:
            self.resolve_playback_release_waiter(
                generation=generation,
                order=order,
                session_id=session_id,
                reason=reason,
            )
        return keys

    async def wait_for_playback_release(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        timeout_s: float,
    ) -> bool:
        key = self.key(generation, order, session_id)
        if key in self.playback_released_keys:
            return True
        waiter = self.playback_release_waiters.get(key)
        if waiter is None:
            return False
        try:
            return await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout_s)
        except TimeoutError:
            return False

    def cancel_order_before_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        reason: str,
    ) -> bool:
        key = self.key(generation, order, session_id)
        waiter = self.playback_start_waiters.get(key)
        if waiter is None or waiter.done():
            return False
        self.cancelled_playback_orders.add(key)
        return self.resolve_playback_start_waiter(
            generation=generation,
            order=order,
            session_id=session_id,
            started=False,
            reason=reason,
        )

    def reset_order_state(self) -> None:
        for generation, order, session_id in list(self.turn_speech_event_by_playback_key):
            self.complete_turn_speech_order(generation=generation, order=order,
                session_id=session_id, completed=False, reason="output_reset")
        self.resolve_all_playback_release_waiters(reason="reset_order_state")
        self.playback_released_keys.clear()
        self.speech_order_facts.clear()
        self.synthesis_order = 0
        self.next_playback_order = 0
        self.pending_audio.clear()
        self.cancelled_playback_orders.clear()

    def begin_output_duck(
        self,
        *,
        generation: int,
        session_id: str | None,
        started_ms: float,
    ) -> bool:
        if self.output_duck_matches(generation, session_id):
            return False
        self.cancel_output_duck()
        self.output_duck_generation = int(generation)
        self.output_duck_session_id = session_id
        self.output_duck_started_ms = float(started_ms)
        self.output_duck_released.clear()
        return True

    def output_duck_matches(
        self,
        generation: int,
        session_id: str | None,
    ) -> bool:
        return (
            self.output_duck_generation == int(generation)
            and self.output_duck_session_id == session_id
        )

    def release_output_duck(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> float | None:
        if not self.output_duck_matches(generation, session_id):
            return None
        started_ms = self.output_duck_started_ms
        self.output_duck_generation = None
        self.output_duck_session_id = None
        self.output_duck_started_ms = None
        timeout_task = self.output_duck_timeout_task
        self.output_duck_timeout_task = None
        if (
            timeout_task is not None
            and timeout_task is not asyncio.current_task()
            and not timeout_task.done()
        ):
            timeout_task.cancel()
        self.output_duck_released.set()
        return started_ms

    def cancel_output_duck(self) -> None:
        self.output_duck_generation = None
        self.output_duck_session_id = None
        self.output_duck_started_ms = None
        timeout_task = self.output_duck_timeout_task
        self.output_duck_timeout_task = None
        if (
            timeout_task is not None
            and timeout_task is not asyncio.current_task()
            and not timeout_task.done()
        ):
            timeout_task.cancel()
        self.output_duck_released.set()

    def begin_new_generation(self) -> int:
        self.cancel_output_duck()
        self.playback_generation += 1
        self.reset_order_state()
        return self.playback_generation
