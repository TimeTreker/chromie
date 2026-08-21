"""TTS provider and ordered output transport for the VoiceAssistant Host.

This collaborator owns provider I/O and output delivery mechanics. It receives
only already-authorized speech and never decides semantic content, ordering
policy, or interruption authority.
"""

from __future__ import annotations

import asyncio
import json
import logging
import inspect
from functools import wraps
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import websockets

from .audio_device_lifecycle import apply_pending_output_device_change
from .session import now_ms
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

logger = logging.getLogger(__name__)


TTS_TRACE_MODULE = TraceModule(
    name="orchestrator.tts",
    component_type="audio",
    implementation="PlaybackTransport",
)
PLAYBACK_TRACE_MODULE = TraceModule(
    name="orchestrator.audio_playback",
    component_type="audio",
    implementation="PlaybackTransport",
)


def _trace_session_async(module: TraceModule, operation: str, session_arg: str):
    """Instrument an async PlaybackTransport method on the Host session trace."""

    def decorate(function):
        @wraps(function)
        async def wrapped(self, *args, **kwargs):
            bound = inspect.signature(function).bind(self, *args, **kwargs)
            bound.apply_defaults()
            session_id = bound.arguments.get(session_arg)
            host = self.host
            with host.sessions.trace_context(session_id):
                async with runtime_tracer.span(
                    module=module,
                    operation=operation,
                    attributes={"session_id": session_id or ""},
                ):
                    return await function(self, *args, **kwargs)

        return wrapped

    return decorate


@dataclass
class ProviderPcmStream:
    """One authorized TTS order delivered as provider PCM becomes available."""

    source_rate: int
    chunks: asyncio.Queue[bytes | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=8)
    )
    retained_audio: bytearray = field(default_factory=bytearray)
    error_reason: str | None = None
    cancelled: bool = False
    finished: bool = False

    async def feed(self, pcm: bytes) -> None:
        if self.cancelled or self.finished or not pcm:
            return
        self.retained_audio.extend(pcm)
        await self.chunks.put(bytes(pcm))

    async def finish(self, reason: str | None = None) -> None:
        if self.finished:
            return
        self.error_reason = reason
        self.finished = True
        await self.chunks.put(None)

    def cancel(self, reason: str) -> None:
        self.cancelled = True
        self.error_reason = reason
        if not self.finished:
            self.finished = True
            self.chunks.put_nowait(None)

    async def read(self) -> bytes | None:
        return await self.chunks.get()

    @property
    def audio_bytes(self) -> bytes:
        return bytes(self.retained_audio)


def _sounddevice() -> Any:
    import sounddevice as sd

    return sd


class PlaybackTransport:
    """Provider/output transport behind the playback lifecycle contract."""

    def __init__(self, host: Any) -> None:
        self.host = host

    async def ensure_output_stream(self):
        host = self.host
        if host.output_stream is not None:
            return
        async with host.output_stream_lock:
            if host.output_stream is not None:
                return
            sd = _sounddevice()
            host.output_stream = sd.OutputStream(
                samplerate=host.output_rate,
                channels=host.output_channels,
                dtype="int16",
                device=host.output_device,
                latency=host.output_latency,
                blocksize=host.output_params.get("blocksize", 0),
            )
            host.output_stream.start()
            logger.info(
                "Output stream opened: device=%s rate=%s channels=%s latency=%s",
                host.output_device,
                host.output_rate,
                host.output_channels,
                host.output_latency,
            )

    async def pause_output_for_duck(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> float | None:
        host = self.host
        state = host._playback_state()
        if not state.output_duck_matches(generation, session_id):
            return None
        pause_error = ""
        if host.audio_output_mode == "device":
            async with host.output_write_lock:
                async with host.output_stream_lock:
                    stream = host.output_stream
                    if (
                        stream is not None
                        and state.output_duck_matches(generation, session_id)
                    ):
                        try:
                            await asyncio.to_thread(stream.abort)
                        except Exception as exc:
                            pause_error = type(exc).__name__
                            logger.warning(
                                "Failed to pause output stream for VAD duck: %s",
                                exc,
                            )
        duck_started_ms = state.output_duck_started_ms
        latency_ms = (
            max(0.0, now_ms() - duck_started_ms)
            if duck_started_ms is not None
            else 0.0
        )
        if state.output_duck_matches(generation, session_id):
            host.session_log(
                session_id,
                "playback_duck_started: generation=%s "
                "vad_start_to_duck_ms=%.1f cancel_cognitive_work=false "
                "pause_error=%s",
                generation,
                latency_ms,
                pause_error or "none",
            )
        return latency_ms

    async def resume_output_after_duck(
        self,
        *,
        generation: int,
        session_id: str | None,
        reason: str,
    ) -> bool:
        host = self.host
        state = host._playback_state()
        if not state.output_duck_matches(generation, session_id):
            return False
        resume_error = ""
        if host.audio_output_mode == "device":
            async with host.output_write_lock:
                async with host.output_stream_lock:
                    stream = host.output_stream
                    if (
                        stream is not None
                        and state.output_duck_matches(generation, session_id)
                    ):
                        try:
                            await asyncio.to_thread(stream.start)
                        except Exception as exc:
                            resume_error = type(exc).__name__
                            logger.warning(
                                "Failed to resume output stream after VAD duck: %s",
                                exc,
                            )
        started_ms = state.release_output_duck(
            generation=generation,
            session_id=session_id,
        )
        if started_ms is None:
            return False
        host.session_log(
            session_id,
            "playback_duck_released: generation=%s reason=%s "
            "duck_duration_ms=%.1f resume_error=%s",
            generation,
            reason,
            max(0.0, now_ms() - started_ms),
            resume_error or "none",
        )
        return not resume_error

    async def wait_for_output_duck_release(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> None:
        host = self.host
        state = host._playback_state()
        while state.output_duck_matches(generation, session_id):
            await state.output_duck_released.wait()
        if host.is_stale_playback(generation, session_id):
            raise asyncio.CancelledError("Playback invalidated while output was ducked")

    async def abort_output_stream(self):
        host = self.host
        async with host.output_write_lock:
            async with host.output_stream_lock:
                if host.output_stream is None:
                    return
                stream = host.output_stream

                def abort_and_close() -> None:
                    try:
                        stream.abort()
                    except Exception as exc:
                        logger.warning(
                            "Failed to abort output stream: %s",
                            exc,
                        )
                    try:
                        stream.close()
                    except Exception as exc:
                        logger.warning(
                            "Failed to close output stream after abort: %s",
                            exc,
                        )

                try:
                    await asyncio.to_thread(abort_and_close)
                finally:
                    if host.output_stream is stream:
                        host.output_stream = None

    async def close_output_stream(self):
        host = self.host
        async with host.output_write_lock:
            async with host.output_stream_lock:
                if host.output_stream is None:
                    return
                try:
                    host.output_stream.stop()
                except Exception as exc:
                    logger.debug(
                        "Best-effort output stream stop failed during close: %s",
                        exc,
                    )
                try:
                    host.output_stream.close()
                except Exception as exc:
                    logger.debug(
                        "Best-effort output stream close failed: %s",
                        exc,
                    )
                host.output_stream = None

    async def play_audio(self, audio_bytes: bytes, source_rate: Optional[int], generation: int, session_id: Optional[str]):
        host = self.host
        if host.audio_output_mode == "device":
            await apply_pending_output_device_change(host)
        pcm = host.resample_int16_bytes(audio_bytes, source_rate or host.default_tts_rate, host.output_rate)
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return
        if host.audio_output_mode == "discard":
            frames_per_chunk = max(
                1,
                int(host.output_rate * host.playback_chunk_ms / 1000),
            )
            for offset in range(0, samples.size, frames_per_chunk):
                await self.wait_for_output_duck_release(
                    generation=generation,
                    session_id=session_id,
                )
                if host.is_stale_playback(generation, session_id):
                    raise asyncio.CancelledError(
                        "Discarded playback interrupted by newer session"
                    )
                if host.discard_playback_realtime:
                    chunk_frames = min(frames_per_chunk, samples.size - offset)
                    await asyncio.sleep(chunk_frames / host.output_rate)
                else:
                    await asyncio.sleep(0)
            return
        output = host.mono_to_output_channels(samples)
        await self.wait_for_output_duck_release(
            generation=generation,
            session_id=session_id,
        )
        await self.ensure_output_stream()
        stream = host.output_stream
        if stream is None:
            raise RuntimeError("Output stream is not available")
        frames_per_chunk = max(1, int(host.output_rate * host.playback_chunk_ms / 1000))
        for offset in range(0, len(output), frames_per_chunk):
            await self.wait_for_output_duck_release(
                generation=generation,
                session_id=session_id,
            )
            if host.is_stale_playback(generation, session_id):
                await self.abort_output_stream()
                raise asyncio.CancelledError("Playback interrupted by newer session")
            chunk = output[offset : offset + frames_per_chunk]
            async with host.output_write_lock:
                if host.output_stream is not stream:
                    raise asyncio.CancelledError("Output stream changed during playback")
                if host.is_stale_playback(generation, session_id):
                    raise asyncio.CancelledError("Playback interrupted by newer session")
                await asyncio.to_thread(stream.write, chunk)
        # If the OS changed output while this ordered item was playing, close
        # the old stream now. The next item will open on the new default.
        await apply_pending_output_device_change(host)

    async def enqueue_playback_skip(self, generation: int, order: int, session_id: Optional[str], reason: str):
        host = self.host
        if host.is_stale_playback(generation, session_id):
            host.session_log(
                session_id,
                "playback_skip_drop_stale: order=%s reason=%s generation=%s current_generation=%s current_sid=%s",
                order,
                reason,
                generation,
                host.playback_generation,
                host.session_id,
            )
            return
        await host.playback_queue.put((generation, order, b"", host.default_tts_rate, session_id, reason))

    async def playback_worker(self):
        host = self.host
        while True:
            item = await host.playback_queue.get()
            if not item:
                continue
            generation = item[0]
            if generation is None:
                break
            generation, order, audio, source_rate, session_id, skip_reason = item
            if host.is_stale_playback(generation, session_id):
                host.resolve_playback_start_waiter(
                    generation,
                    order,
                    session_id,
                    started=False,
                    reason="stale_before_order",
                )
                host._playback_state().resolve_playback_release_waiter(
                    generation=generation,
                    order=order,
                    session_id=session_id,
                    reason="stale_before_order",
                )
                host.session_log(session_id, "playback_drop_stale_before_order: order=%s", order)
                continue
            if order != host.next_playback_order:
                host.pending_audio[order] = (generation, audio, source_rate, session_id, skip_reason)
                continue
            try:
                played = await self.play_one_order(
                    generation, order, audio, source_rate, session_id, skip_reason
                )
            finally:
                host._playback_state().resolve_playback_release_waiter(
                    generation=generation,
                    order=order,
                    session_id=session_id,
                    reason="playback_order_terminal",
                )
            if played:
                host.next_playback_order += 1
            while host.next_playback_order in host.pending_audio:
                ng, na, nsr, nsid, nreason = host.pending_audio.pop(host.next_playback_order)
                if host.is_stale_playback(ng, nsid):
                    pending_order = host.next_playback_order
                    host.resolve_playback_start_waiter(
                        ng,
                        pending_order,
                        nsid,
                        started=False,
                        reason="stale_pending_order",
                    )
                    host._playback_state().resolve_playback_release_waiter(
                        generation=ng,
                        order=pending_order,
                        session_id=nsid,
                        reason="stale_pending_order",
                    )
                    host.next_playback_order += 1
                    continue
                pending_order = host.next_playback_order
                try:
                    played = await self.play_one_order(
                        ng, pending_order, na, nsr, nsid, nreason
                    )
                finally:
                    host._playback_state().resolve_playback_release_waiter(
                        generation=ng,
                        order=pending_order,
                        session_id=nsid,
                        reason="playback_order_terminal",
                    )
                if played:
                    host.next_playback_order += 1
                else:
                    break

    @_trace_session_async(PLAYBACK_TRACE_MODULE, "play_one_order", "session_id")
    async def play_one_order(self, generation: int, order: int, audio: bytes | ProviderPcmStream, source_rate: int, session_id: Optional[str], skip_reason: Optional[str] = None) -> bool:
        host = self.host
        key = host.playback_start_key(generation, order, session_id)
        cancelled_orders = getattr(host, "cancelled_playback_orders", set())
        if key in cancelled_orders:
            cancelled_orders.discard(key)
            if isinstance(audio, ProviderPcmStream):
                audio.cancel("cancelled_before_playback")
            host.session_log(
                session_id,
                "playback_skip_cancelled: order=%s generation=%s",
                order,
                generation,
            )
            host.maybe_session_done(session_id)
            return True
        if host.is_stale_playback(generation, session_id):
            host.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=False,
                reason="stale_playback",
            )
            return False
        state = host.sessions.state.get(session_id or "")
        first_stream_chunk: bytes | None = None
        if isinstance(audio, ProviderPcmStream):
            source_rate = audio.source_rate
            while first_stream_chunk is None:
                if audio.finished and audio.chunks.empty():
                    break
                if host.is_stale_playback(generation, session_id):
                    audio.cancel("stale_before_first_pcm")
                    host.resolve_playback_start_waiter(
                        generation,
                        order,
                        session_id,
                        started=False,
                        reason="stale_before_first_pcm",
                    )
                    return False
                try:
                    first_stream_chunk = await asyncio.wait_for(audio.read(), timeout=0.1)
                except TimeoutError:
                    continue
            if first_stream_chunk is None:
                skip_reason = audio.error_reason or skip_reason or "tts_empty_audio"
        if (isinstance(audio, bytes) and not audio) or (
            isinstance(audio, ProviderPcmStream) and first_stream_chunk is None
        ):
            reason = skip_reason or "empty_audio"
            host.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=False,
                reason=reason,
            )
            if state is not None:
                if reason in {"tts_error", "tts_exception", "playback_exception"}:
                    state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
                else:
                    state["skipped_tts"] = int(state.get("skipped_tts", 0)) + 1
            host.session_log(session_id, "playback_skip_empty: order=%s reason=%s", order, reason)
            host.maybe_session_done(session_id)
            return True

        initial_audio = first_stream_chunk if isinstance(audio, ProviderPcmStream) else audio
        if initial_audio is None:
            reason = "playback_missing_initial_pcm"
            host.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=False,
                reason=reason,
            )
            if state is not None:
                state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
            host.session_log(
                session_id,
                "playback_skip_empty: order=%s reason=%s",
                order,
                reason,
            )
            host.maybe_session_done(session_id)
            return True
        audio_ms = (len(initial_audio) / (source_rate * 2)) * 1000.0 if source_rate else 0.0
        host.sessions.trace_mark(
            session_id,
            "first_audio_playback" if not state or not state.get("trace_first_audio_marked") else "audio_playback_started",
            kind="user_observable",
            attributes={"order": order, "audio_ms": round(audio_ms, 3)},
        )
        if state is not None:
            state["trace_first_audio_marked"] = True
        host.session_log(
            session_id,
            "playback_start: order=%s source_rate=%s output_rate=%s audio_ms=%.1f generation=%s",
            order,
            source_rate,
            host.output_rate,
            audio_ms,
            generation,
        )
        host.resolve_playback_start_waiter(
            generation,
            order,
            session_id,
            started=True,
            reason="playback_start",
        )
        playback_start_ms = now_ms()
        try:
            host.is_playing_audio = True
            try:
                if isinstance(audio, ProviderPcmStream):
                    chunk = first_stream_chunk
                    while chunk is not None:
                        await self.play_audio(chunk, source_rate, generation, session_id)
                        chunk = await audio.read()
                else:
                    await self.play_audio(audio, source_rate, generation, session_id)
            finally:
                host.is_playing_audio = False
        except asyncio.CancelledError:
            host.session_log(session_id, "playback_aborted_by_interrupt: order=%s playback_ms=%.1f generation=%s", order, now_ms() - playback_start_ms, generation)
            return False
        except Exception as exc:
            await self.abort_output_stream()
            if state is not None:
                state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
            host.session_log(session_id, "playback_exception: order=%s playback_ms=%.1f error=%s", order, now_ms() - playback_start_ms, exc)
            logger.error("Playback exception: %s", exc, exc_info=True)
            host.maybe_session_done(session_id)
            return True

        playback_ms = now_ms() - playback_start_ms
        if host.is_stale_playback(generation, session_id):
            host.session_log(session_id, "playback_aborted_by_interrupt: order=%s playback_ms=%.1f generation=%s", order, playback_ms, generation)
            return False
        retained_audio = audio.audio_bytes if isinstance(audio, ProviderPcmStream) else audio
        if isinstance(audio, ProviderPcmStream) and audio.error_reason:
            if state is not None:
                state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
            host.session_log(
                session_id,
                "playback_stream_incomplete: order=%s reason=%s bytes=%s generation=%s",
                order,
                audio.error_reason,
                len(retained_audio),
                generation,
            )
        if state is not None:
            state["played_tts"] = int(state.get("played_tts", 0)) + 1
        host.session_log(session_id, "playback_end: order=%s playback_ms=%.1f played_tts=%s", order, playback_ms, state.get("played_tts", 0) if state else "unknown")
        host.save_audio(retained_audio, "output", session_id=session_id)
        host.maybe_session_done(session_id)
        return True

    @_trace_session_async(TTS_TRACE_MODULE, "synthesize_one", "session_id")
    async def synthesize_one(self, text: str, order: int, session_id: Optional[str], generation: int):
        host = self.host
        text = host.normalize_tts_candidate(text)
        if not host.is_valid_tts_text(text):
            host.session_log(session_id, "tts_skip_invalid_sentence: order=%s chars=%s text=%r", order, len(text), text)
            await self.enqueue_playback_skip(generation, order, session_id, "invalid_tts_text")
            return
        if host.is_stale_playback(generation, session_id):
            return
        async with host.synthesis_semaphore:
            request_id = f"{session_id}-{order}"
            tts_start_ms = now_ms()
            max_attempts = max(1, host.tts_ws_retries)
            retry_delay = max(0, host.tts_ws_retry_delay_ms) / 1000.0
            last_error: Exception | None = None
            host.session_log(session_id, "tts_request_start: order=%s chars=%s generation=%s retries=%s text=%r", order, len(text), generation, max_attempts, text)
            for attempt in range(1, max_attempts + 1):
                if host.is_stale_playback(generation, session_id):
                    return
                try:
                    async with websockets.connect(host.tts_url, max_size=10**7, open_timeout=10, ping_interval=20, ping_timeout=20) as ws:
                        await ws.send(json.dumps({"type": "synthesize_stream", "text": text, "speaker_id": host.speaker_id, "request_id": request_id}, ensure_ascii=False))
                        stream: ProviderPcmStream | None = None
                        total_audio_bytes = 0
                        source_rate = host.default_tts_rate
                        async for msg in ws:
                            if host.is_stale_playback(generation, session_id):
                                if stream is not None:
                                    await stream.finish("stale_playback")
                                return
                            if isinstance(msg, bytes):
                                if msg and stream is None:
                                    stream = ProviderPcmStream(source_rate=source_rate)
                                    state = host.sessions.state.get(session_id or "")
                                    if state is not None:
                                        state["queued_tts"] = int(state.get("queued_tts", 0)) + 1
                                    await host.playback_queue.put(
                                        (generation, order, stream, source_rate, session_id, None)
                                    )
                                    first_pcm_latency_ms = now_ms() - tts_start_ms
                                    host.sessions.trace_mark(
                                        session_id,
                                        "tts_first_provider_pcm",
                                        attributes={
                                            "order": order,
                                            "attempt": attempt,
                                            "first_chunk_bytes": len(msg),
                                            "source_rate": source_rate,
                                            "request_latency_ms": round(first_pcm_latency_ms, 3),
                                        },
                                    )
                                    host.session_log(
                                        session_id,
                                        "tts_first_provider_pcm: order=%s attempt=%s/%s tts_ms=%.1f bytes=%s source_rate=%s generation=%s",
                                        order,
                                        attempt,
                                        max_attempts,
                                        first_pcm_latency_ms,
                                        len(msg),
                                        source_rate,
                                        generation,
                                    )
                                total_audio_bytes += len(msg)
                                if stream is not None:
                                    await stream.feed(msg)
                                continue
                            data = json.loads(msg)
                            msg_type = data.get("type")
                            if msg_type == "start":
                                source_rate = int(data.get("sample_rate") or host.default_tts_rate)
                                host.sessions.trace_mark(
                                    session_id,
                                    "tts_stream_started",
                                    attributes={"order": order, "attempt": attempt, "source_rate": source_rate},
                                )
                                host.session_log(session_id, "tts_stream_start: order=%s attempt=%s/%s source_rate=%s output_rate=%s generation=%s", order, attempt, max_attempts, source_rate, host.output_rate, generation)
                                continue
                            if msg_type == "error":
                                host.session_log(session_id, "tts_error: order=%s attempt=%s/%s tts_ms=%.1f error=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, data.get("message"))
                                if stream is not None:
                                    await stream.finish("tts_error")
                                else:
                                    await self.enqueue_playback_skip(generation, order, session_id, "tts_error")
                                host.maybe_session_done(session_id)
                                return
                            if msg_type == "end":
                                provider_metadata = data.get("provider")
                                if not isinstance(provider_metadata, dict):
                                    provider_metadata = {}
                                model_artifacts = provider_metadata.get("model_artifacts")
                                if not isinstance(model_artifacts, list):
                                    model_artifacts = []
                                provider_revision_summary = ",".join(
                                    f"{artifact.get('kind')}={artifact.get('revision')}"
                                    for artifact in model_artifacts
                                    if isinstance(artifact, dict)
                                    and artifact.get("kind")
                                    and artifact.get("revision")
                                )
                                host.sessions.trace_mark(
                                    session_id,
                                    "tts_stream_finished",
                                    attributes={
                                        "order": order,
                                        "attempt": attempt,
                                        "audio_bytes": total_audio_bytes,
                                        "source_rate": source_rate,
                                        "queue_wait_seconds": float(data.get("queue_wait_seconds") or 0.0),
                                        "generate_seconds": float(data.get("generate_seconds") or 0.0),
                                        "provider_id": provider_metadata.get("provider_id"),
                                        "provider_implementation": provider_metadata.get("implementation"),
                                        "provider_model_revisions": provider_revision_summary,
                                    },
                                )
                                host.session_log(session_id, "tts_stream_end: order=%s attempt=%s/%s tts_ms=%.1f bytes=%s source_rate=%s generation=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, total_audio_bytes, source_rate, generation)
                                host.session_log(
                                    session_id,
                                    "tts_server_metrics: order=%s provider=%s implementation=%s model_revisions=%s audio_s=%.3f generate_s=%.3f model_s=%.3f codec_s=%.3f pcm_s=%.3f queue_s=%.3f rtf=%s codec_device=%s quantization=%s context=%s prompt_tokens=%s generated_tokens=%s headroom=%s limit_reached=%s",
                                    order,
                                    provider_metadata.get("provider_id"),
                                    provider_metadata.get("implementation"),
                                    provider_revision_summary,
                                    float(data.get("audio_seconds") or 0.0),
                                    float(data.get("generate_seconds") or 0.0),
                                    float(data.get("model_generate_seconds") or 0.0),
                                    float(data.get("codec_decode_seconds") or 0.0),
                                    float(data.get("pcm_conversion_seconds") or 0.0),
                                    float(data.get("queue_wait_seconds") or 0.0),
                                    data.get("realtime_factor"),
                                    data.get("audio_codec_device"),
                                    data.get("quantization"),
                                    data.get("context_size"),
                                    data.get("model_prompt_tokens"),
                                    data.get("model_generated_tokens"),
                                    data.get("generation_headroom_tokens"),
                                    data.get("generation_limit_reached"),
                                )
                                if stream is not None:
                                    await stream.finish()
                                else:
                                    await self.enqueue_playback_skip(generation, order, session_id, "tts_empty_audio")
                                host.maybe_session_done(session_id)
                                return
                        raise RuntimeError("TTS websocket closed before end message")
                except asyncio.CancelledError:
                    if "stream" in locals() and stream is not None:
                        await stream.finish("synthesis_cancelled")
                    raise
                except Exception as exc:
                    if "stream" in locals() and stream is not None:
                        await stream.finish("tts_stream_exception")
                        host.maybe_session_done(session_id)
                        return
                    last_error = exc
                    host.session_log(session_id, "tts_ws_attempt_failed: order=%s attempt=%s/%s tts_ms=%.1f error=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, exc)
                    if attempt < max_attempts:
                        await asyncio.sleep(retry_delay)
            logger.error("TTS error after retries: %s", last_error, exc_info=True)
            await self.enqueue_playback_skip(generation, order, session_id, "tts_exception")
            host.maybe_session_done(session_id)



def transport_for(host: Any) -> PlaybackTransport:
    state = host._playback_state()
    transport = state.transport
    if not isinstance(transport, PlaybackTransport):
        transport = PlaybackTransport(host)
        state.transport = transport
    return transport
