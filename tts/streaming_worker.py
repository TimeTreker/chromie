"""Restartable process worker for streaming native model responses."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from multiprocessing.connection import Connection
from typing import Any


logger = logging.getLogger(__name__)
TERMINAL_TYPES = {"complete", "error"}


class StreamingProcessWorker:
    """Keep one model in a child process and stream request events over a pipe.

    The target sends one ``ready`` object, then zero or more ``audio`` objects
    followed by exactly one ``complete`` or ``error`` object per request.
    Cancellation either drains one almost-complete request under a bounded
    grace period or terminates and reloads the process. Both paths complete
    before the singleton lock is released, so stale native work cannot leak
    audio or contaminate the next request after barge-in.
    """

    def __init__(
        self,
        target: Callable[[Connection], None],
        *,
        name: str,
        startup_timeout_s: float = 900.0,
        cancel_drain_timeout_s: float = 0.0,
        first_audio_timeout_s: float = 0.0,
        request_timeout_s: float = 0.0,
        cold_first_audio_timeout_s: float = 0.0,
        cold_request_timeout_s: float = 0.0,
        context_name: str = "spawn",
    ) -> None:
        self._target = target
        self._name = name
        self._startup_timeout_s = startup_timeout_s
        self._cancel_drain_timeout_s = max(0.0, cancel_drain_timeout_s)
        self._first_audio_timeout_s = max(0.0, first_audio_timeout_s)
        self._request_timeout_s = max(0.0, request_timeout_s)
        self._cold_first_audio_timeout_s = max(
            0.0, cold_first_audio_timeout_s
        )
        self._cold_request_timeout_s = max(0.0, cold_request_timeout_s)
        self._context = multiprocessing.get_context(context_name)
        self._process: multiprocessing.Process | None = None
        self._connection: Connection | None = None
        self._async_lock: asyncio.Lock | None = None
        self.restart_count = 0
        self.cancel_drain_count = 0
        self.cancel_restart_count = 0
        self.failure_restart_count = 0
        self.ready_payload: dict[str, Any] = {}
        self._worker_warmed = False

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    @property
    def worker_warmed(self) -> bool:
        return self._worker_warmed

    @property
    def cancellation_mode(self) -> str:
        if self._cancel_drain_timeout_s > 0:
            return "bounded_drain_then_restart_worker"
        return "terminate_and_restart_worker"

    def _lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    async def start(self) -> None:
        async with self._lock():
            if not self.is_alive:
                await self._start()

    async def stream(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        queued_at = time.monotonic()
        async with self._lock():
            queue_wait_seconds = time.monotonic() - queued_at
            if not self.is_alive:
                await self._start()
            connection = self._connection
            if connection is None:
                raise RuntimeError(f"{self._name} is not started")
            terminal_received = False
            first_audio_received = False
            cold_request = not self._worker_warmed
            first_audio_timeout_s = (
                self._cold_first_audio_timeout_s
                if cold_request and self._cold_first_audio_timeout_s > 0
                else self._first_audio_timeout_s
            )
            request_timeout_s = (
                self._cold_request_timeout_s
                if cold_request and self._cold_request_timeout_s > 0
                else self._request_timeout_s
            )
            started_at = time.monotonic()
            try:
                connection.send(payload)
                while True:
                    if connection.poll(0):
                        event = connection.recv()
                        if not isinstance(event, dict):
                            raise RuntimeError(
                                f"{self._name} returned a non-object stream event"
                            )
                        event = {
                            **event,
                            "worker_queue_wait_seconds": queue_wait_seconds,
                        }
                        event_type = str(event.get("type") or "")
                        if event_type == "ready":
                            # ``ready`` is a startup control event, never a
                            # synthesis result. A cancellation-time restart
                            # used to be shielded in a background task, which
                            # could release the singleton lock before startup
                            # consumed this message. Ignore the harmless
                            # control event defensively while restart now stays
                            # inside the lock below.
                            logger.warning(
                                "Discarded delayed startup event inside synthesis stream: %s",
                                self._name,
                            )
                            continue
                        if event_type == "error":
                            message = str(event.get("message") or "worker synthesis failed")
                            self._invalidate_after_failure(reason="worker_error")
                            raise RuntimeError(f"{self._name} failed: {message}")
                        if event_type == "audio":
                            first_audio_received = True
                        terminal_received = event_type in TERMINAL_TYPES
                        if event_type == "complete":
                            self._worker_warmed = True
                        yield event
                        if terminal_received:
                            return
                        continue

                    now = time.monotonic()
                    if (
                        not first_audio_received
                        and first_audio_timeout_s > 0
                        and now - started_at >= first_audio_timeout_s
                    ):
                        timeout = first_audio_timeout_s
                        self._invalidate_after_failure(reason="first_audio_timeout")
                        raise TimeoutError(
                            f"{self._name} produced no audio within {timeout:.1f}s"
                        )
                    if (
                        request_timeout_s > 0
                        and now - started_at >= request_timeout_s
                    ):
                        timeout = request_timeout_s
                        self._invalidate_after_failure(reason="request_timeout")
                        raise TimeoutError(
                            f"{self._name} did not complete within {timeout:.1f}s"
                        )
                    if self._connection is not connection or not self.is_alive:
                        exitcode = self._process.exitcode if self._process is not None else None
                        raise EOFError(
                            f"{self._name} closed before a terminal stream event "
                            f"(exitcode={exitcode})"
                        )
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                if not terminal_received:
                    await self._recover_after_cancellation(connection)
                raise
            except GeneratorExit:
                # A disconnected WebSocket can close the async generator while
                # the native child is still producing audio. Drain or restart
                # before releasing the singleton lock so stale pipe events can
                # never be mistaken for the next request.
                if not terminal_received:
                    await self._recover_after_cancellation(connection)
                raise
            except TimeoutError:
                # TimeoutError subclasses OSError; the timeout paths already
                # invalidated the worker with the more specific reason.
                raise
            except (BrokenPipeError, EOFError, OSError):
                self._invalidate_after_failure(reason="worker_transport_failure")
                raise

    async def _recover_after_cancellation(self, connection: Connection) -> None:
        if await self._drain_cancelled_request(connection):
            self.cancel_drain_count += 1
            logger.info(
                "Drained cancelled streaming request without reloading worker: %s",
                self._name,
            )
            return
        await self._restart_after_failure(cancelled=True)

    async def _drain_cancelled_request(self, connection: Connection) -> bool:
        """Discard one cancelled request up to its terminal worker event.

        Candidate-model inference is synchronous inside the child process. A
        short bounded drain lets an almost-complete request finish without a
        costly model reload. The connection remains private under ``_lock``;
        timeout, process death, malformed data, or I/O failure all fall back to
        the existing terminate-and-restart behavior.
        """

        if self._cancel_drain_timeout_s <= 0:
            return False
        deadline = time.monotonic() + self._cancel_drain_timeout_s
        try:
            while time.monotonic() < deadline:
                if connection.poll(0):
                    event = connection.recv()
                    if not isinstance(event, dict):
                        return False
                    if str(event.get("type") or "") in TERMINAL_TYPES:
                        return True
                    continue
                if self._connection is not connection or not self.is_alive:
                    return False
                await asyncio.sleep(0.01)
        except (BrokenPipeError, EOFError, OSError):
            return False
        return False

    def _invalidate_after_failure(self, *, reason: str) -> None:
        """Discard a poisoned worker and let the next request start a fresh one.

        Failure propagation must not wait for a heavyweight model reload. The
        next request enters ``stream`` under the singleton lock and calls
        ``_start`` before sending any payload, so no stale CUDA or pipe state is
        reused after OOM, process death, or a bounded synthesis timeout.
        """

        self._terminate_sync()
        self.restart_count += 1
        self.failure_restart_count += 1
        logger.error(
            "Invalidated streaming worker after %s; next request will start a fresh process: %s",
            reason,
            self._name,
        )

    async def _restart_after_failure(self, *, cancelled: bool) -> None:
        self._terminate_sync()
        try:
            # ``stream`` still owns the singleton lock here. Await startup in
            # this task so no background coroutine can consume the new pipe
            # after the lock has been released to the next request.
            await self._start()
        except Exception:
            logger.exception("Failed to restart streaming worker %s", self._name)
        self.restart_count += 1
        if cancelled:
            self.cancel_restart_count += 1
            logger.info("Restarted streaming worker after cancellation: %s", self._name)

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
        self._worker_warmed = False

        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if parent.poll(0):
                message = parent.recv()
                if not isinstance(message, dict) or message.get("type") != "ready":
                    self._terminate_sync()
                    detail = message.get("message") if isinstance(message, dict) else message
                    raise RuntimeError(f"{self._name} failed to start: {detail}")
                self.ready_payload = dict(message)
                return
            if not process.is_alive():
                self._terminate_sync()
                raise RuntimeError(f"{self._name} exited during startup")
            await asyncio.sleep(0.05)
        self._terminate_sync()
        raise TimeoutError(
            f"{self._name} did not become ready within {self._startup_timeout_s:.1f}s"
        )

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
        self.ready_payload = {}
        self._worker_warmed = False
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
