"""ASR, routed-turn, and protective-reflex lifecycle ownership.

This boundary coordinates asyncio tasks and queues. It does not infer user
intent or decide interruption semantics; those decisions arrive as explicit
scope and reason inputs from the Cognitive Gateway/runtime.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import TypeAlias


PendingVadAudio: TypeAlias = bytes | tuple[bytes, bool, int | None]


@dataclass
class InputTurnLifecycle:
    active_asr_task: asyncio.Task | None = None
    active_turn_task: asyncio.Task | None = None
    active_turn_tasks: dict[asyncio.Task, str] = field(default_factory=dict)
    turn_cancellation_reasons: dict[asyncio.Task, str] = field(
        default_factory=dict
    )
    active_reflex_task: asyncio.Task | None = None
    concurrent_protective_reflex_tasks: set[asyncio.Task] = field(
        default_factory=set
    )
    pending_turn_after_reflex: deque[tuple[str, str]] = field(
        default_factory=deque
    )
    pending_vad_audio: PendingVadAudio | None = None

    def has_active_protective_reflex(
        self,
        *,
        excluding: asyncio.Task | None = None,
    ) -> bool:
        primary = self.active_reflex_task
        if primary is not None and primary is not excluding and not primary.done():
            return True
        return any(
            task is not excluding and not task.done()
            for task in self.concurrent_protective_reflex_tasks
        )

    def register_turn(
        self,
        task: asyncio.Task,
        session_id: str,
        *,
        protective_reflex: bool = False,
        concurrent_reflex: bool = False,
    ) -> None:
        self.active_turn_tasks[task] = session_id
        if concurrent_reflex:
            self.concurrent_protective_reflex_tasks.add(task)
        else:
            self.active_turn_task = task
        if protective_reflex and not concurrent_reflex:
            self.active_reflex_task = task

    def unregister_turn(
        self,
        task: asyncio.Task,
    ) -> tuple[str | None, bool, bool]:
        was_primary_reflex = self.active_reflex_task is task
        was_concurrent_reflex = task in self.concurrent_protective_reflex_tasks
        self.concurrent_protective_reflex_tasks.discard(task)
        self.active_turn_tasks.pop(task, None)
        cancellation_reason = self.turn_cancellation_reasons.pop(task, None)
        if self.active_turn_task is task:
            self.active_turn_task = next(
                (
                    candidate
                    for candidate in reversed(list(self.active_turn_tasks.keys()))
                    if not candidate.done()
                ),
                None,
            )
        if was_primary_reflex:
            self.active_reflex_task = None
        return cancellation_reason, was_primary_reflex, was_concurrent_reflex

    def request_turn_cancellation(
        self,
        *,
        excluding: asyncio.Task | None,
        cancel_all: bool,
        reason: str,
    ) -> tuple[str, ...]:
        protected = {
            task
            for task in {
                self.active_reflex_task,
                *self.concurrent_protective_reflex_tasks,
            }
            if task is not None
        }
        candidates = [
            (task, session_id)
            for task, session_id in self.active_turn_tasks.items()
            if task is not excluding
            and task not in protected
            and not task.done()
        ]
        if not cancel_all and candidates:
            candidates = candidates[-1:]
        cancelled: list[str] = []
        for task, session_id in candidates:
            self.turn_cancellation_reasons[task] = reason
            task.cancel()
            cancelled.append(session_id)
        return tuple(cancelled)

    def queue_turn_after_reflex(self, user_text: str, session_id: str) -> int:
        self.pending_turn_after_reflex.append((user_text, session_id))
        return len(self.pending_turn_after_reflex)

    def drain_turns_after_reflex(self) -> list[tuple[str, str]]:
        pending = list(self.pending_turn_after_reflex)
        self.pending_turn_after_reflex.clear()
        return pending

    def queue_pending_vad_audio(self, audio: PendingVadAudio) -> bool:
        replaced = self.pending_vad_audio is not None
        self.pending_vad_audio = audio
        return replaced

    def take_pending_vad_audio(self) -> PendingVadAudio | None:
        pending = self.pending_vad_audio
        self.pending_vad_audio = None
        return pending

    def register_asr_task(self, task: asyncio.Task) -> None:
        self.active_asr_task = task

    def complete_asr_task(self, task: asyncio.Task) -> None:
        if self.active_asr_task is task:
            self.active_asr_task = None

    def shutdown_tasks(self) -> tuple[asyncio.Task, ...]:
        tasks: set[asyncio.Task] = set(self.active_turn_tasks)
        if self.active_turn_task is not None:
            tasks.add(self.active_turn_task)
        if self.active_asr_task is not None:
            tasks.add(self.active_asr_task)
        tasks.update(self.concurrent_protective_reflex_tasks)
        if self.active_reflex_task is not None:
            tasks.add(self.active_reflex_task)
        for task in tasks:
            if not task.done():
                task.cancel()
        return tuple(tasks)

    def reset(self) -> None:
        self.active_asr_task = None
        self.active_turn_task = None
        self.active_turn_tasks.clear()
        self.turn_cancellation_reasons.clear()
        self.active_reflex_task = None
        self.concurrent_protective_reflex_tasks.clear()
        self.pending_turn_after_reflex.clear()
        self.pending_vad_audio = None
