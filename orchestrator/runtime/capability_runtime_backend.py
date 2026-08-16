from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class CapabilityRuntimeBackendHandle:
    """Opaque Runtime-backend submission reference.

    This identifier is implementation state only.  It is deliberately absent
    from CapabilityDispatchReceipt and every cognitive/provider-facing contract.
    """

    opaque_id: str


class CapabilityRuntimeBackend(Protocol):
    """Mechanism for keeping one Runtime-owned submission alive.

    The backend does not validate Capability requests, own canonical identity,
    publish lifecycle events, decide cancellation scope, or interpret results.
    Those remain CapabilityRuntime responsibilities.
    """

    backend_id: str

    def start_submission(
        self,
        runner: Callable[[], Awaitable[Any]],
        *,
        name: str,
    ) -> CapabilityRuntimeBackendHandle: ...

    async def wait_submission(
        self,
        handle: CapabilityRuntimeBackendHandle,
    ) -> Any: ...

    def cancel_submission(self, handle: CapabilityRuntimeBackendHandle) -> None: ...

    def submission_done(self, handle: CapabilityRuntimeBackendHandle) -> bool: ...

    def release_submission(self, handle: CapabilityRuntimeBackendHandle) -> None: ...


class InProcessAsyncioBackend:
    """Maintained default backend using Runtime-process ``asyncio`` tasks."""

    backend_id = "in_process_asyncio"

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def start_submission(
        self,
        runner: Callable[[], Awaitable[Any]],
        *,
        name: str,
    ) -> CapabilityRuntimeBackendHandle:
        opaque_id = uuid4().hex
        task = asyncio.create_task(runner(), name=name)
        self._tasks[opaque_id] = task
        return CapabilityRuntimeBackendHandle(opaque_id=opaque_id)

    async def wait_submission(
        self,
        handle: CapabilityRuntimeBackendHandle,
    ) -> Any:
        try:
            task = self._tasks[handle.opaque_id]
        except KeyError as exc:
            raise ValueError("unknown Capability Runtime backend submission") from exc
        return await task

    def cancel_submission(self, handle: CapabilityRuntimeBackendHandle) -> None:
        task = self._tasks.get(handle.opaque_id)
        if task is not None:
            task.cancel()

    def submission_done(self, handle: CapabilityRuntimeBackendHandle) -> bool:
        task = self._tasks.get(handle.opaque_id)
        return bool(task is not None and task.done())

    def release_submission(self, handle: CapabilityRuntimeBackendHandle) -> None:
        task = self._tasks.get(handle.opaque_id)
        if task is None:
            return
        if not task.done():
            raise RuntimeError("cannot release a live Capability Runtime submission")
        self._tasks.pop(handle.opaque_id, None)
