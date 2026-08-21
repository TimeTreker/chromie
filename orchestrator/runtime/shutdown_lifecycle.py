"""Mechanical VoiceAssistant shutdown sequencing.

This module owns only Host teardown mechanics: finalize retained session traces,
cancel in-process tasks, close transports, and release audio resources. It does
not decide Goal cancellation, interpret user intent, author speech, or create
new Evidence. Runtime/Provider cancellation caused by an explicit user control
must already have followed its normal trusted path before process teardown.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any


logger = logging.getLogger(__name__)


async def _cancel_and_drain(task: asyncio.Task[Any] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def _cancel_tasks(tasks: set[asyncio.Task[Any]] | list[asyncio.Task[Any]]) -> None:
    for task in list(tasks):
        if not task.done():
            task.cancel()


async def shutdown_voice_assistant(
    host: Any,
    *,
    close_output_stream: Callable[[], Awaitable[None]],
) -> None:
    """Release one VoiceAssistant runtime without acquiring semantic authority."""

    sessions = getattr(host, "sessions", None)
    if sessions is not None:
        try:
            await host._sample_accelerator_resources(reason="session_finish")
        except Exception as exc:  # diagnostics must never block process teardown
            logger.debug(
                "Final accelerator telemetry sample failed: %s",
                type(exc).__name__,
            )
        sessions.finalize_active_sessions(reason="orchestrator_cleanup")

    host.resolve_all_playback_start_waiters(
        started=False,
        reason="cleanup",
    )

    playback_state = getattr(host, "playback_delivery", None)
    if playback_state is not None:
        playback_state.cancel_output_duck()

    await _cancel_and_drain(getattr(host, "audio_device_monitor_task", None))

    _cancel_tasks(set(getattr(host, "active_synthesis_tasks", set())))

    input_lifecycle = getattr(host, "input_turn_lifecycle", None)
    shutdown_tasks = getattr(input_lifecycle, "shutdown_tasks", None)
    if callable(shutdown_tasks):
        shutdown_tasks()
        input_lifecycle.active_reflex_task = None
        input_lifecycle.pending_turn_after_reflex.clear()
        input_lifecycle.pending_vad_audio = None
    else:
        # Minimal test/diagnostic hosts may not have constructed the collaborator.
        active_asr_task = getattr(host, "active_asr_task", None)
        if active_asr_task is not None and not active_asr_task.done():
            active_asr_task.cancel()
        active_turn_task = getattr(host, "active_turn_task", None)
        if active_turn_task is not None and not active_turn_task.done():
            active_turn_task.cancel()

    output_abort_tasks = list(getattr(host, "output_abort_tasks", set()))
    _cancel_tasks(output_abort_tasks)
    if output_abort_tasks:
        await asyncio.gather(*output_abort_tasks, return_exceptions=True)

    sweeper = getattr(host, "session_idle_sweeper_task", None)
    if sweeper is not None and not sweeper.done():
        sweeper.cancel()

    _cancel_tasks(set(getattr(host, "observability_tasks", set())))

    playback_task = getattr(host, "playback_task", None)
    if playback_task is not None and not playback_task.done():
        await host.playback_queue.put((None, None, None, None, None, None))
        playback_task.cancel()

    await close_output_stream()

    asr_ws = getattr(host, "asr_ws", None)
    if asr_ws is not None:
        await asr_ws.close()

    http_session = getattr(host, "http_session", None)
    if http_session is not None and not http_session.closed:
        await http_session.close()

    audio_mgr = getattr(host, "audio_mgr", None)
    if audio_mgr is not None:
        audio_mgr.close()
