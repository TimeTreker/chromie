from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(frozen=True)
class ResourceArbiterSnapshot:
    max_concurrency: int
    active_count: int
    waiting_count: int
    serial_active: bool
    serial_waiters: int


class ResourceArbiter:
    """Bound in-process work and serialize declared shared resources."""

    def __init__(self, max_concurrency: int, *, vocal_reservation: int = 0) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if vocal_reservation < 0:
            raise ValueError("vocal_reservation cannot be negative")
        self.max_concurrency = max_concurrency
        self._vocal_reservation = min(vocal_reservation, max_concurrency - 1)
        self._active_lanes: dict[str, int] = {}
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0
        self._serial_active = False
        self._serial_waiters = 0
        self._active_resources: set[str] = set()
        self._pending: dict[str, list[tuple[object, Callable[[], bool]]]] = {}

    def _enqueue(self, lanes: Iterable[str], ready: Callable[[], bool]) -> object:
        token = object()
        for lane in lanes:
            self._pending.setdefault(lane, []).append((token, ready))
        return token

    def _has_turn(self, token: object, lanes: Iterable[str]) -> bool:
        # FIFO among eligible waiters in each required lane. A resource-blocked
        # head holds no slot and cannot block unrelated Activity work.
        for lane in lanes:
            for candidate, ready in self._pending[lane]:
                if candidate is token:
                    break
                if ready():
                    return False
        return True

    def _dequeue(self, token: object, lanes: Iterable[str]) -> None:
        for lane in lanes:
            self._pending[lane] = [item for item in self._pending[lane] if item[0] is not token]
        self._condition.notify_all()

    @property
    def active_count(self) -> int:
        return self._active

    def snapshot(self) -> ResourceArbiterSnapshot:
        return ResourceArbiterSnapshot(
            max_concurrency=self.max_concurrency,
            active_count=self._active,
            waiting_count=self._waiting,
            serial_active=self._serial_active,
            serial_waiters=self._serial_waiters,
        )

    @asynccontextmanager
    async def claim(
        self,
        *,
        can_run_parallel: bool = True,
        exclusive_group: str | None = None,
        resource_claims: Iterable[str] = (),
        lane: str = "",
    ) -> AsyncIterator[None]:
        # Exact names share one process-local lock domain. Claim the whole set
        # atomically with capacity, so a waiter holds neither a partial resource
        # set nor a slot that disjoint work could use.
        if isinstance(resource_claims, (str, bytes)):
            raise ValueError("resource_claims must be a collection of resource names")
        resources = frozenset(resource_claims)
        if any(not isinstance(name, str) or not name or name != name.strip() for name in resources):
            raise ValueError("resource_claims must contain non-empty exact resource names")
        if exclusive_group:
            resources = resources.union((exclusive_group,))
        await self._admit(can_run_parallel=can_run_parallel, resources=resources, lane=lane)
        try:
            yield
        finally:
            await self._release(can_run_parallel=can_run_parallel, resources=resources, lane=lane)

    async def _admit(self, *, can_run_parallel: bool, resources: frozenset[str], lane: str) -> None:
        async with self._condition:
            self._waiting += 1
            if not can_run_parallel:
                self._serial_waiters += 1
            def ready() -> bool:
                return (not self._serial_active
                        and self._active < self.max_concurrency
                        and self._lane_available(lane)
                        and resources.isdisjoint(self._active_resources)
                        and (self._serial_waiters == 0 if can_run_parallel else self._active == 0))
            token = self._enqueue((lane,), ready)
            try:
                await self._condition.wait_for(lambda: ready() and self._has_turn(token, (lane,)))
                self._active += 1
                self._active_lanes[lane] = self._active_lanes.get(lane, 0) + 1
                self._active_resources.update(resources)
                if not can_run_parallel:
                    self._serial_active = True
            finally:
                self._waiting -= 1
                if not can_run_parallel:
                    self._serial_waiters -= 1
                self._dequeue(token, (lane,))

    async def _release(self, *, can_run_parallel: bool, resources: frozenset[str], lane: str) -> None:
        async with self._condition:
            self._active -= 1
            self._active_lanes[lane] -= 1
            self._active_resources.difference_update(resources)
            if not can_run_parallel:
                self._serial_active = False
            self._condition.notify_all()

    def _lane_available(self, lane: str, extra: int = 1) -> bool:
        limit = (1 if lane == "vocal" else self.max_concurrency - self._vocal_reservation
                 if lane == "activity" else self.max_concurrency)
        return self._active_lanes.get(lane, 0) + extra <= limit

    @asynccontextmanager
    async def claim_group(self, members: list[tuple[str, str, frozenset[str]]], *, optional: set[str]):
        """Atomically reserve required members; omit busy optional decoration."""
        if len({item[0] for item in members}) != len(members):
            raise ValueError("coordination member IDs must be unique")
        required = [item for item in members if item[0] not in optional]
        if not required or len(required) > self.max_concurrency:
            raise ValueError("coordination group exceeds Runtime capacity")
        resources: set[str] = set()
        lane_counts: dict[str, int] = {}
        for _, lane, claims in required:
            if resources.intersection(claims):
                raise ValueError("coordination members have conflicting resources")
            resources.update(claims)
            lane_counts[lane] = lane_counts.get(lane, 0) + 1
        if lane_counts.get("vocal", 0) > 1 or lane_counts.get("activity", 0) > self.max_concurrency - self._vocal_reservation:
            raise ValueError("coordination group exceeds lane capacity")
        accepted = {item[0] for item in required}
        async with self._condition:
            self._waiting += 1
            lanes = tuple(lane_counts)
            def ready() -> bool:
                return (not self._serial_active and self._serial_waiters == 0
                        and self._active + len(required) <= self.max_concurrency
                        and resources.isdisjoint(self._active_resources)
                        and all(self._lane_available(lane, count) for lane, count in lane_counts.items()))
            token = self._enqueue(lanes, ready)
            try:
                await self._condition.wait_for(lambda: ready() and self._has_turn(token, lanes))
                for identity, lane, claims in members:
                    if identity not in optional:
                        continue
                    extra = lane_counts.get(lane, 0) + 1
                    if (self._active + len(accepted) < self.max_concurrency
                            and self._lane_available(lane, extra)
                            and claims.isdisjoint(resources | self._active_resources)):
                        accepted.add(identity)
                        resources.update(claims)
                        lane_counts[lane] = extra
                self._active += len(accepted)
                self._active_resources.update(resources)
                for lane, count in lane_counts.items():
                    self._active_lanes[lane] = self._active_lanes.get(lane, 0) + count
            finally:
                self._waiting -= 1
                self._dequeue(token, lanes)
        owned = {identity: (lane, claims) for identity, lane, claims in members if identity in accepted}
        async def release_member(identity: str) -> None:
            async with self._condition:
                item = owned.pop(identity, None)
                if item is None:
                    return
                lane, claims = item
                self._active -= 1
                self._active_resources.difference_update(claims)
                self._active_lanes[lane] -= 1
                self._condition.notify_all()
        try:
            yield accepted, release_member
        finally:
            for identity in list(owned):
                await release_member(identity)
