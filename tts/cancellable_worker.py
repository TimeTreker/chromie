from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from collections.abc import Callable
from contextlib import suppress
from multiprocessing.connection import Connection
from typing import Any

logger = logging.getLogger(__name__)


class RestartableProcessWorker:
    """Single-command process worker that restarts on request cancellation.

    The worker target must send one startup message over its Connection. A
    successful startup message is ``{"type": "ready"}``; any other message is
    treated as a startup failure. Each subsequent request must produce exactly
    one response.
    """

    def __init__(
        self,
        target: Callable[[Connection], None],
        *,
        name: str,
        startup_timeout_s: float = 600.0,
        context_name: str = "spawn",
    ) -> None:
        self._target = target
        self._name = name
        self._startup_timeout_s = startup_timeout_s
        self._context = multiprocessing.get_context(context_name)
        self._process: multiprocessing.Process | None = None
        self._connection: Connection | None = None
        self._async_lock: asyncio.Lock | None = None
        self.restart_count = 0

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    async def start(self) -> None:
        async with self._lock():
            if self.is_alive:
                return
            await self._start()

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock():
            if not self.is_alive:
                await self._start()

            try:
                return await self._request(payload)
            except asyncio.CancelledError:
                # A cancelled asyncio waiter cannot stop synchronous native model
                # code. Terminate the owning process, then start a clean worker
                # before releasing the lock.
                self._terminate_sync()
                try:
                    await asyncio.shield(self._start())
                except Exception:
                    logger.exception("Failed to restart cancelled worker %s", self._name)
                self.restart_count += 1
                raise
            except (BrokenPipeError, EOFError, OSError):
                self._terminate_sync()
                await self._start()
                self.restart_count += 1
                raise

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._connection is None:
            raise RuntimeError(f"{self._name} is not started")
        connection = self._connection
        connection.send(payload)
        while True:
            if connection.poll(0):
                response = connection.recv()
                break
            if self._connection is not connection:
                raise EOFError(f"{self._name} connection closed before response")
            await asyncio.sleep(0.05)
        if not isinstance(response, dict):
            raise RuntimeError(f"{self._name} returned a non-object response")
        return response

    async def stop(self) -> None:
        async with self._lock():
            self._stop_sync()

    async def _start(self) -> None:
        self._terminate_sync()
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(
            target=self._target,
            args=(child,),
            name=self._name,
            daemon=True,
        )
        process.start()
        child.close()
        self._process = process
        self._connection = parent

        deadline = time.monotonic() + self._startup_timeout_s
        ready = False
        while time.monotonic() < deadline:
            if parent.poll(0):
                ready = True
                break
            await asyncio.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        if not ready:
            self._terminate_sync()
            raise TimeoutError(
                f"{self._name} did not become ready within "
                f"{self._startup_timeout_s:.1f}s"
            )
        message = parent.recv()
        if not isinstance(message, dict) or message.get("type") != "ready":
            self._terminate_sync()
            detail = message.get("message") if isinstance(message, dict) else message
            raise RuntimeError(f"{self._name} failed to start: {detail}")

    def _stop_sync(self) -> None:
        if self.is_alive and self._connection is not None:
            with suppress(BrokenPipeError, EOFError, OSError):
                self._connection.send({"type": "shutdown"})
                if self._connection.poll(2.0):
                    self._connection.recv()
        self._terminate_sync()

    def _terminate_sync(self) -> None:
        connection = self._connection
        process = self._process
        self._connection = None
        self._process = None
        if connection is not None:
            with suppress(OSError):
                connection.close()
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=5.0)
            with suppress(Exception):
                process.close()
