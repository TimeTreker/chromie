from __future__ import annotations

import asyncio
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
        self._capacity = asyncio.Semaphore(max_concurrency)
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0
        self._serial_active = False
        self._serial_waiters = 0
        self._group_locks: dict[str, asyncio.Lock] = {}
        self._group_lock_guard = asyncio.Lock()

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
    ) -> AsyncIterator[None]:
        self._waiting += 1
        try:
            await self._capacity.acquire()
        finally:
            self._waiting -= 1
        admitted = False
        group_lock: asyncio.Lock | None = None
        group_acquired = False
        try:
            await self._admit(can_run_parallel=can_run_parallel)
            admitted = True
            if exclusive_group:
                group_lock = await self._get_group_lock(exclusive_group)
                await group_lock.acquire()
                group_acquired = True
            yield
        finally:
            if group_acquired and group_lock is not None:
                group_lock.release()
            if admitted:
                await self._release(can_run_parallel=can_run_parallel)
            self._capacity.release()

    async def _admit(self, *, can_run_parallel: bool) -> None:
        async with self._condition:
            if can_run_parallel:
                await self._condition.wait_for(
                    lambda: not self._serial_active and self._serial_waiters == 0
                )
                self._active += 1
                return
            self._serial_waiters += 1
            try:
                await self._condition.wait_for(
                    lambda: not self._serial_active and self._active == 0
                )
                self._serial_active = True
                self._active = 1
            finally:
                self._serial_waiters -= 1
                self._condition.notify_all()

    async def _release(self, *, can_run_parallel: bool) -> None:
        async with self._condition:
            self._active -= 1
            if not can_run_parallel:
                self._serial_active = False
            self._condition.notify_all()

    async def _get_group_lock(self, group: str) -> asyncio.Lock:
        async with self._group_lock_guard:
            return self._group_locks.setdefault(group, asyncio.Lock())
