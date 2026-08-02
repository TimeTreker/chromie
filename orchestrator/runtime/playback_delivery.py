"""Playback delivery state and current-turn speech provenance.

The collaborator owns transport lifecycle facts only: order allocation, playback
barriers, cancellation, and whether speech actually started. It never decides
whether two utterances mean the same thing; later model stages receive the
playback-qualified speech events and make that semantic judgment.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable


PlaybackKey = tuple[int, int, str | None]
PendingAudio = tuple[int, bytes, int, str | None, str | None]


@dataclass
class PlaybackDeliveryLifecycle:
    """Mutable lifecycle state for one VoiceAssistant runtime."""

    next_playback_order: int = 0
    synthesis_order: int = 0
    playback_generation: int = 0
    pending_audio: dict[int, PendingAudio] = field(default_factory=dict)
    tts_text_by_generation: dict[int, list[str]] = field(default_factory=dict)
    playback_start_waiters: dict[PlaybackKey, asyncio.Future[bool]] = field(
        default_factory=dict
    )
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
    transport: Any | None = None

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
    ) -> dict[str, Any] | None:
        sid = str(session_id or "").strip()
        text = str(normalized_text or "").strip()
        if not sid or not orders or not text:
            return None
        event_seed = f"{sid}|{generation}|{orders[0]}|{stage}|{purpose}|{text}"
        event_id = "speech_event_" + hashlib.sha256(
            event_seed.encode("utf-8")
        ).hexdigest()[:20]
        event = {
            "event_id": event_id,
            "session_id": sid,
            "stage": str(stage or ""),
            "purpose": str(purpose or ""),
            "status": "scheduled",
            "text": text,
            "route": str(route or ""),
            "intent": str(intent or ""),
            "commitment": str(commitment or ""),
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
        return event

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
        self.synthesis_order = 0
        self.next_playback_order = 0
        self.pending_audio.clear()
        self.cancelled_playback_orders.clear()

    def begin_new_generation(self) -> int:
        self.playback_generation += 1
        self.reset_order_state()
        return self.playback_generation
