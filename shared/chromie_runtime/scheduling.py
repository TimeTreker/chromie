from __future__ import annotations

import asyncio
from collections.abc import Iterable
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

    def __init__(self, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.max_concurrency = max_concurrency
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0
        self._serial_active = False
        self._serial_waiters = 0
        self._active_resources: set[str] = set()

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
        await self._admit(can_run_parallel=can_run_parallel, resources=resources)
        try:
            yield
        finally:
            await self._release(can_run_parallel=can_run_parallel, resources=resources)

    async def _admit(self, *, can_run_parallel: bool, resources: frozenset[str]) -> None:
        async with self._condition:
            self._waiting += 1
            if not can_run_parallel:
                self._serial_waiters += 1
            try:
                await self._condition.wait_for(
                    lambda: not self._serial_active
                    and self._active < self.max_concurrency
                    and resources.isdisjoint(self._active_resources)
                    and (self._serial_waiters == 0 if can_run_parallel else self._active == 0)
                )
                self._active += 1
                self._active_resources.update(resources)
                if not can_run_parallel:
                    self._serial_active = True
            finally:
                self._waiting -= 1
                if not can_run_parallel:
                    self._serial_waiters -= 1
                self._condition.notify_all()

    async def _release(self, *, can_run_parallel: bool, resources: frozenset[str]) -> None:
        async with self._condition:
            self._active -= 1
            self._active_resources.difference_update(resources)
            if not can_run_parallel:
                self._serial_active = False
            self._condition.notify_all()
