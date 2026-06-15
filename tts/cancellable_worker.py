from __future__ import annotations

import asyncio
import logging
import multiprocessing
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
            await asyncio.to_thread(self._start_sync)

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock():
            if not self.is_alive:
                await asyncio.to_thread(self._start_sync)

            response_task = asyncio.create_task(
                asyncio.to_thread(self._request_sync, payload)
            )
            try:
                # Shield the blocking recv task so caller cancellation reaches
                # this method without discarding the handle needed to unwind it.
                return await asyncio.shield(response_task)
            except asyncio.CancelledError:
                # A cancelled asyncio waiter cannot stop synchronous native model
                # code. Terminate the owning process, wait for the blocked recv to
                # unwind, then start a clean worker before releasing the lock.
                await asyncio.shield(asyncio.to_thread(self._terminate_sync))
                with suppress(Exception, asyncio.CancelledError):
                    await asyncio.shield(response_task)
                try:
                    await asyncio.shield(asyncio.to_thread(self._start_sync))
                except Exception:
                    logger.exception("Failed to restart cancelled worker %s", self._name)
                self.restart_count += 1
                raise
            except (BrokenPipeError, EOFError, OSError):
                await asyncio.to_thread(self._terminate_sync)
                await asyncio.to_thread(self._start_sync)
                self.restart_count += 1
                raise

    async def stop(self) -> None:
        async with self._lock():
            await asyncio.to_thread(self._stop_sync)

    def _start_sync(self) -> None:
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

        if not parent.poll(self._startup_timeout_s):
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

    def _request_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._connection is None:
            raise RuntimeError(f"{self._name} is not started")
        self._connection.send(payload)
        response = self._connection.recv()
        if not isinstance(response, dict):
            raise RuntimeError(f"{self._name} returned a non-object response")
        return response

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
