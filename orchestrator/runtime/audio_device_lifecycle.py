"""Runtime lifecycle for OS-default-following audio devices.

This module owns only Host-mechanical device transition policy: detecting a
validated system-default change, queuing it, and applying it at input/output
stream boundaries.  It does not decide user meaning, speech content, interruption
scope, or whether a device-backed Activity should exist.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def set_input_device_params(host: Any, params: dict[str, Any]) -> None:
    host.input_params = params
    host.input_rate = params["rate"]
    host.input_channels = params["channels"]
    host.input_device = params["device"]
    host.input_block_size = params["blocksize"]
    host.input_latency = params["latency"]


def set_output_device_params(host: Any, params: dict[str, Any]) -> None:
    host.output_params = params
    host.output_rate = params["rate"]
    host.output_channels = params["channels"]
    host.output_device = params["device"]
    host.output_latency = params["latency"]


def uses_followed_system_default(host: Any, kind: str) -> bool:
    mode = host.audio_input_mode if kind == "input" else host.audio_output_mode
    return mode == "device" and host.audio_mgr.follows_system_default(kind)


async def refresh_system_default_audio_devices(
    host: Any,
    *,
    force_kinds: set[str] | None = None,
) -> set[str]:
    """Queue validated stream changes for OS-default-following directions."""

    forced = force_kinds or set()
    queued: set[str] = set()
    async with host._audio_device_refresh_lock:
        for kind in ("input", "output"):
            if not uses_followed_system_default(host, kind):
                continue
            getter = (
                host.audio_mgr.get_input_params
                if kind == "input"
                else host.audio_mgr.get_output_params
            )
            try:
                candidate = await asyncio.to_thread(getter)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if host._audio_device_errors.get(kind) != error:
                    logger.warning(
                        "Could not refresh OS-default %s device; keeping "
                        "the current stream until a valid default appears: %s",
                        kind,
                        error,
                    )
                host._audio_device_errors[kind] = error
                continue

            previous_error = host._audio_device_errors.pop(kind, None)
            if previous_error is not None:
                logger.info("OS-default %s device is available again", kind)
            current = host.input_params if kind == "input" else host.output_params
            pending = (
                host._pending_input_params
                if kind == "input"
                else host._pending_output_params
            )
            if pending is not None and not host.audio_mgr.device_params_changed(
                pending,
                candidate,
            ):
                continue
            changed = host.audio_mgr.device_params_changed(current, candidate)
            if kind not in forced and not changed:
                continue
            logger.info(
                "OS-default %s device change detected: old=%s(%r) new=%s(%r) "
                "signal=%s",
                kind,
                current.get("name", "unknown"),
                current.get("device"),
                candidate.get("name", "unknown"),
                candidate.get("device"),
                "os_metadata" if kind in forced else "portaudio_default",
            )
            if kind == "input":
                host._pending_input_params = candidate
                host._input_device_change_event.set()
            else:
                host._pending_output_params = candidate
            queued.add(kind)
    return queued


async def audio_device_monitor(host: Any) -> None:
    """Poll portable defaults and consume read-only PipeWire change events."""

    async def collect_pipewire_changes() -> None:
        try:
            async for kind in host.audio_mgr.watch_system_default_changes():
                try:
                    host._audio_default_change_queue.put_nowait(kind)
                except asyncio.QueueFull:
                    # Polling still detects a concrete PortAudio identity
                    # change. A full queue already contains refresh work.
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "PipeWire default-device notifications stopped; portable "
                "PortAudio polling remains active: %s",
                exc,
            )

    pipewire_task = asyncio.create_task(collect_pipewire_changes())
    try:
        await refresh_system_default_audio_devices(host)
        while True:
            forced: set[str] = set()
            try:
                kind = await asyncio.wait_for(
                    host._audio_default_change_queue.get(),
                    timeout=1.0,
                )
                forced.add(kind)
                while not host._audio_default_change_queue.empty():
                    forced.add(host._audio_default_change_queue.get_nowait())
            except asyncio.TimeoutError:
                pass
            await refresh_system_default_audio_devices(
                host,
                force_kinds=forced,
            )
    finally:
        pipewire_task.cancel()
        await asyncio.gather(pipewire_task, return_exceptions=True)


async def apply_pending_input_device_change(host: Any) -> bool:
    """Activate a queued input device after the old stream has closed."""

    async with host._audio_device_refresh_lock:
        params = host._pending_input_params
        host._pending_input_params = None
        host._input_device_change_event.clear()
    if params is None:
        return False

    dropped_frames = 0
    while not host.mic_queue.empty():
        try:
            host.mic_queue.get_nowait()
            dropped_frames += 1
        except asyncio.QueueEmpty:
            break
    host.vad.reset()
    host._vad_leftover = b""
    duck_state = host._playback_state()
    if duck_state.output_duck_generation is not None:
        # Local import avoids making the audio-device policy own playback
        # transport construction while still releasing an old-device duck.
        from .playback_transport import transport_for as playback_transport_for

        await playback_transport_for(host).resume_output_after_duck(
            generation=duck_state.output_duck_generation,
            session_id=duck_state.output_duck_session_id,
            reason="input_device_change",
        )
    host._vad_segment_started_during_playback = False
    host._vad_segment_playback_generation = None
    set_input_device_params(host, params)
    logger.info(
        "Audio input switched to OS default: name=%s device=%r rate=%s "
        "channels=%s discarded_old_frames=%s",
        params.get("name", "unknown"),
        params.get("device"),
        params.get("rate"),
        params.get("channels"),
        dropped_frames,
    )
    return True


async def apply_pending_output_device_change(host: Any) -> bool:
    """Close the old output so the next ordered audio uses the new default."""

    async with host._audio_device_refresh_lock:
        params = host._pending_output_params
        host._pending_output_params = None
    if params is None:
        return False

    async with host.output_write_lock:
        async with host.output_stream_lock:
            stream = host.output_stream
            if stream is not None:

                def stop_and_close() -> None:
                    try:
                        stream.stop()
                    except Exception as exc:
                        logger.debug(
                            "Old output stream stop failed during device switch: %s",
                            exc,
                        )
                    try:
                        stream.close()
                    except Exception as exc:
                        logger.debug(
                            "Old output stream close failed during device switch: %s",
                            exc,
                        )

                await asyncio.to_thread(stop_and_close)
                if host.output_stream is stream:
                    host.output_stream = None
            set_output_device_params(host, params)
    logger.info(
        "Audio output switched to OS default: name=%s device=%r rate=%s "
        "channels=%s",
        params.get("name", "unknown"),
        params.get("device"),
        params.get("rate"),
        params.get("channels"),
    )
    return True
