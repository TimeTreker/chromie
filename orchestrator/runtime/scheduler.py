from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class ScheduledSpeech:
    order: int
    text: str = field(compare=False)
    sid: str | None = field(default=None, compare=False)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


class OrderedSpeechScheduler:
    def __init__(self):
        self._order = 0
        self._lock = asyncio.Lock()

    async def next(self, text: str, sid: str | None = None, **metadata: Any) -> ScheduledSpeech:
        async with self._lock:
            item = ScheduledSpeech(order=self._order, text=text, sid=sid, metadata=metadata)
            self._order += 1
            return item

    async def reset(self) -> None:
        async with self._lock:
            self._order = 0


class CoordinatedStartError(RuntimeError):
    """A declared execution group could not reach its common start boundary."""


class CoordinatedStart:
    """One Runtime-owned preparation barrier; it never chooses semantic members."""

    def __init__(self, members: set[str], optional: set[str]) -> None:
        self.members = members
        self.optional = optional
        self.ready_members: set[str] = set()
        self.dropped: set[str] = set()
        self.ready_at: dict[str, float] = {}
        self.released_at: float | None = None
        self.error: str | None = None
        self._released = asyncio.Event()

    async def ready(self, member: str) -> None:
        if member not in self.members:
            raise CoordinatedStartError("unknown coordination member")
        if self.released_at is None and self.error is None:
            self.ready_members.add(member)
            self.ready_at[member] = asyncio.get_running_loop().time()
            if self.members - self.optional <= self.ready_members:
                self.dropped.update(self.optional - self.ready_members)
                self.released_at = asyncio.get_running_loop().time()
                self._released.set()
        await self._released.wait()
        if self.error is not None or member in self.dropped:
            raise CoordinatedStartError(self.error or "optional_member_not_ready_at_start")

    def finished(self, member: str) -> None:
        if self.released_at is not None or self.error is not None:
            return
        if member in self.optional:
            self.dropped.add(member)
            self.optional.discard(member)
            self.members.discard(member)
        else:
            self.error = "required_member_failed_before_start"
            self._released.set()

    def abort(self) -> None:
        if self.released_at is None:
            self.error = "coordination_cancelled_before_start"
            self._released.set()


@dataclass
class ExecutionStart:
    group: CoordinatedStart
    member: str

    resources: asyncio.Future[set[str]] | None = None

    async def ready(self) -> None:
        await self.group.ready(self.member)

    async def wait_resources(self) -> None:
        if self.resources is not None and self.member not in await asyncio.shield(self.resources):
            raise CoordinatedStartError("optional_member_resource_unavailable")


current_execution_start: ContextVar[ExecutionStart | None] = ContextVar("execution_start", default=None)
