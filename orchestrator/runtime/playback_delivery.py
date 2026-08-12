"""Playback delivery state and current-turn speech provenance.

The collaborator owns transport lifecycle facts only: order allocation, playback
barriers, cancellation, and whether speech actually started. It never decides
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
    order_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
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
        route: str = "",
        intent: str = "",
        commitment: str = "",
        turn_id: str | None = None,
        source_goal_ids: list[str] | None = None,
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        goal_association_fingerprint: str = "",
        delivery_role: str = "response",
        claims: list[str] | None = None,
        must_not_claim_completion: bool | None = None,
    ) -> dict[str, Any] | None:
        sid = str(session_id or "").strip()
        text = str(normalized_text or "").strip()
        if not sid or not orders or not text:
            return None
        normalized_turn_id = " ".join(str(turn_id or sid).strip().split())
        normalized_goal_ids = self._normalized_text_values(source_goal_ids)
        normalized_claims = self._normalized_text_values(claims)
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
        # The event identity is a structured conversational-act and transport
        # correlation key. Wording is payload integrity, not de-duplication
        # identity, so changing punctuation or whitespace cannot define a new
        # delivered act.
        event_seed = json.dumps(
            {
                "canonical_plan_fingerprint": normalized_plan_fingerprint,
                "canonical_plan_id": normalized_plan_id,
                "claims": normalized_claims,
                "commitment": str(commitment or ""),
                "delivery_role": normalized_delivery_role,
                "generation": int(generation),
                "goal_association_fingerprint": normalized_association_fingerprint,
                "intent": str(intent or ""),
                "must_not_claim_completion": must_not_claim_completion,
                "order": int(orders[0]),
                "purpose": str(purpose or ""),
                "route": str(route or ""),
                "session_id": sid,
                "source_goal_ids": normalized_goal_ids,
                "stage": str(stage or ""),
                "turn_id": normalized_turn_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        event_id = "speech_event_" + hashlib.sha256(
            event_seed.encode("utf-8")
        ).hexdigest()[:20]
        event = {
            "event_id": event_id,
            "session_id": sid,
            "turn_id": normalized_turn_id,
            "stage": str(stage or ""),
            "purpose": str(purpose or ""),
            "status": "scheduled",
            "text": text,
            "route": str(route or ""),
            "intent": str(intent or ""),
            "commitment": str(commitment or ""),
            "source_goal_ids": normalized_goal_ids,
            "canonical_plan_id": normalized_plan_id,
            "canonical_plan_fingerprint": normalized_plan_fingerprint,
            "goal_association_fingerprint": normalized_association_fingerprint,
            "delivery_role": normalized_delivery_role,
            "claims": normalized_claims,
            "must_not_claim_completion": must_not_claim_completion,
            "generation": int(generation),
            "orders": [int(order) for order in orders],
        }
        events = self.turn_speech_events.setdefault(sid, [])
        events.append(event)
        if len(events) > 12:
            del events[:-12]
        self.turn_speech_event_by_playback_key[
            self.key(generation, orders[0], session_id)
        ] = event_id
        self._publish_interaction_event(event)
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
        key = self.key(generation, order, session_id)
        event_id = self.turn_speech_event_by_playback_key.pop(key, None)
        sid = str(session_id or "").strip()
        if not event_id or not sid:
            return
        for event in reversed(self.turn_speech_events.get(sid, [])):
            if event.get("event_id") != event_id:
                continue
            event["status"] = "playback_started" if started else "not_delivered"
            event["playback_reason"] = str(reason or "")
            self._publish_interaction_event(event)
            break

    def delivered_turn_speech_events(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        return [
            dict(event)
            for event in self.turn_speech_events.get(str(session_id or ""), [])
            if event.get("status") in {"playback_started", "playback_completed"}
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
        self.resolve_all_playback_release_waiters(reason="reset_order_state")
        self.playback_released_keys.clear()
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
