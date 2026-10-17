"""Lifecycle mechanics shared by the TTS model process workers.

Standard library only: every TTS image copies this file beside the worker
module that uses it.
"""

from __future__ import annotations

import asyncio
import multiprocessing
from contextlib import suppress
from multiprocessing.connection import Connection


class ProcessWorkerLifecycle:
    """Singleton lock, liveness and graceful stop for one model child process.

    Subclasses own ``_process``, ``_connection`` and ``_async_lock`` and define
    ``_terminate_sync`` for their own state reset.
    """

    _process: multiprocessing.Process | None
    _connection: Connection | None
    _async_lock: asyncio.Lock | None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def _stop_sync(self) -> None:
        if self.is_alive and self._connection is not None:
            with suppress(BrokenPipeError, EOFError, OSError):
                self._connection.send({"type": "shutdown"})
                if self._connection.poll(2.0):
                    self._connection.recv()
        self._terminate_sync()

    def _terminate_sync(self) -> None:
        raise NotImplementedError
