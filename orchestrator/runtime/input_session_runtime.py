"""Microphone, ASR, routed-turn, and idle-session transport mechanics.

This collaborator owns input/session mechanics after the Host has supplied
configuration and model-owned semantic authorities. It does not infer intent,
choose interruption scope, or author conversational content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

import numpy as np

from orchestrator.audio_injection import read_audio_packet
from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from orchestrator.runtime.session import now_ms
from shared.chromie_contracts.reflex import DEFAULT_REFLEX_FILTER
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

logger = logging.getLogger(__name__)

VAD_TRACE_MODULE = TraceModule(
    name="orchestrator.vad",
    component_type="audio_input",
    implementation="InputSessionRuntime",
)
ASR_TRACE_MODULE = TraceModule(
    name="orchestrator.asr",
    component_type="speech_recognition",
    implementation="InputSessionRuntime",
)


def _sounddevice() -> Any:
    import sounddevice as sd

    return sd


class InputSessionRuntime:
    """Input transport and task orchestration behind InputTurnLifecycle."""

    def __init__(self, host: Any) -> None:
        self.host = host

    async def _begin_playback_duck(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> None:
        host = self.host
        state = host._playback_state()
        started_ms = now_ms()
        if not state.begin_output_duck(
            generation=generation,
            session_id=session_id,
            started_ms=started_ms,
        ):
            return

        confirmation_timeout_s = max(
            0.001,
            (float(host.max_vad_utterance_ms) / 1000.0)
            + float(host.asr_timeout_s),
        )

        async def release_after_timeout() -> None:
            await asyncio.sleep(confirmation_timeout_s)
            await self._release_playback_duck(
                generation=generation,
                session_id=session_id,
                reason="confirmation_timeout",
            )

        state.output_duck_timeout_task = asyncio.create_task(
            release_after_timeout()
        )
        await playback_transport_for(host).pause_output_for_duck(
            generation=generation,
            session_id=session_id,
        )

    async def _release_playback_duck(
        self,
        *,
        generation: int | None,
        session_id: str | None,
        reason: str,
    ) -> None:
        if generation is None:
            return
        playback_state = getattr(self.host, "_playback_state", None)
        if not callable(playback_state):
            return
        await playback_transport_for(self.host).resume_output_after_duck(
            generation=generation,
            session_id=session_id,
            reason=reason,
        )

    def mic_callback(self, indata, frames, time_info, status):
        host = self.host
        if status:
            logger.warning("Microphone status: %s", status)
        if host.loop is None:
            return
        audio = indata.copy()

        def enqueue_audio():
            if host.mic_queue.full():
                try:
                    host.mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                host.mic_queue.put_nowait(audio)
            except asyncio.QueueFull:
                pass

        host.loop.call_soon_threadsafe(enqueue_audio)

    async def handle_vad_audio(
        self,
        audio: bytes,
        *,
        started_during_playback: bool = False,
        playback_generation_at_start: int | None = None,
    ):
        host = self.host
        playback_state = host._playback_state()
        current_session_id = getattr(host, "session_id", None)
        duck_session_id = (
            playback_state.output_duck_session_id
            if playback_generation_at_start is not None
            and playback_state.output_duck_generation
            == playback_generation_at_start
            else current_session_id
        )
        duration_ms = (len(audio) / (host.target_asr_rate * 2)) * 1000.0
        duration = duration_ms / 1000.0
        rms = float(np.sqrt(np.mean(np.square(np.frombuffer(audio, dtype=np.int16).astype(np.float32))))) if audio else 0.0
        if duration_ms >= host.max_vad_utterance_ms:
            logger.warning(
                "VAD speech ended but discarded at hard maximum: duration=%.2fs max_audio_ms=%s",
                duration,
                host.max_vad_utterance_ms,
            )
            await self._release_playback_duck(
                generation=playback_generation_at_start,
                session_id=duck_session_id,
                reason="hard_maximum",
            )
            return
        if duration_ms < host.min_audio_ms:
            logger.warning("VAD speech ended but skipped: duration=%.2fs min_audio_ms=%s", duration, host.min_audio_ms)
            await self._release_playback_duck(
                generation=playback_generation_at_start,
                session_id=duck_session_id,
                reason="short_audio",
            )
            return
        playback_contaminated = bool(
            started_during_playback or host.is_playing_audio
        )
        effective_min_rms = (
            host.barge_in_min_rms if playback_contaminated else host.min_rms
        )
        if rms < effective_min_rms:
            logger.warning(
                "VAD speech ended but skipped: duration=%.2fs RMS=%.1f "
                "min_rms=%.1f playing=%s started_during_playback=%s "
                "playback_generation_at_start=%s current_generation=%s",
                duration,
                rms,
                effective_min_rms,
                host.is_playing_audio,
                started_during_playback,
                playback_generation_at_start,
                host.playback_generation,
            )
            await self._release_playback_duck(
                generation=playback_generation_at_start,
                session_id=duck_session_id,
                reason="low_rms",
            )
            return

        playback_candidate = bool(
            started_during_playback
            and playback_generation_at_start is not None
            and playback_state.output_duck_matches(
                playback_generation_at_start,
                duck_session_id,
            )
        )
        session_id = duck_session_id if playback_candidate else host.create_session()
        if not session_id:
            await self._release_playback_duck(
                generation=playback_generation_at_start,
                session_id=None,
                reason="missing_playback_session",
            )
            playback_candidate = False
            session_id = host.create_session()
        with host.sessions.trace_context(session_id):
            runtime_tracer.mark(
                module=VAD_TRACE_MODULE,
                name="vad_validated",
                kind="audio_input",
                attributes={
                    "audio_duration_ms": round(duration_ms, 3),
                    "audio_bytes": len(audio),
                    "rms": round(rms, 3),
                    "playing_audio": bool(host.is_playing_audio),
                    "started_during_playback": bool(started_during_playback),
                    "playback_generation_at_start": playback_generation_at_start,
                },
            )
            if playback_candidate:
                host.session_log(
                    session_id,
                    "vad_playback_candidate_validated: audio=%.2fs rms=%.1f "
                    "bytes=%s playback_generation_at_start=%s",
                    duration,
                    rms,
                    len(audio),
                    playback_generation_at_start,
                )
            else:
                host.session_log(session_id, "vad_valid_end: audio=%.2fs rms=%.1f bytes=%s", duration, rms, len(audio))
                host.save_audio(audio, "input", session_id=session_id)
                host.sessions.capture_input_audio(
                    session_id,
                    audio,
                    sample_rate_hz=host.target_asr_rate,
                    channels=1,
                )
                # A validated new input turn invalidates old speech output, but
                # it cannot yet decide Goal, body, or global cancellation scope.
                host._invalidate_output_state(
                    cancel_cognitive_work=False,
                )
                host._schedule_output_abort(
                    new_session_id=session_id,
                    log_event=True,
                )

            try:
                async with runtime_tracer.span(
                    module=ASR_TRACE_MODULE,
                    operation="transcribe",
                    kind="model_call",
                    attributes={
                        "audio_duration_ms": round(duration_ms, 3),
                        "audio_bytes": len(audio),
                        "timeout_ms": round(host.asr_timeout_s * 1000.0, 3),
                    },
                ) as asr_span:
                    if host.asr_ws is None or getattr(host.asr_ws, "close_code", None) is not None:
                        reconnect_start_ms = now_ms()
                        await host.connect_services()
                        reconnect_ms = now_ms() - reconnect_start_ms
                        asr_span.set_attribute("reconnect_ms", round(reconnect_ms, 3))
                        host.session_log(session_id, "asr_reconnect_done: reconnect_ms=%.1f", reconnect_ms)

                    asr_start_ms = now_ms()
                    host.session_log(session_id, "asr_send_start: audio_ms=%.1f bytes=%s", duration_ms, len(audio))
                    await host.asr_ws.send(audio)
                    send_ms = now_ms() - asr_start_ms
                    asr_span.set_attribute("send_ms", round(send_ms, 3))
                    host.session_log(session_id, "asr_send_done: send_ms=%.1f", send_ms)
                    resp = await asyncio.wait_for(host.asr_ws.recv(), timeout=host.asr_timeout_s)
                    asr_done_ms = now_ms()
                    result = json.loads(resp)
                    asr_span.set_attribute("result_type", str(result.get("type") or "unknown"))
                    if result.get("type") == "error":
                        asr_span.set_status("error")
                        host.session_log(session_id, "asr_error: asr_ms=%.1f error=%s", asr_done_ms - asr_start_ms, result)
                        if playback_candidate:
                            await self._release_playback_duck(
                                generation=playback_generation_at_start,
                                session_id=session_id,
                                reason="asr_error",
                            )
                        return
                    if result.get("type") == "final":
                        user_text = result.get("text", "").strip()
                        asr_span.set_attribute("text_chars", len(user_text))
                        runtime_tracer.mark(
                            module=ASR_TRACE_MODULE,
                            name="asr_final_available",
                            kind="milestone",
                            attributes={"text_chars": len(user_text)},
                        )
                        if not playback_candidate:
                            host.session_log(session_id, "asr_final: asr_ms=%.1f text_chars=%s text=%r", asr_done_ms - asr_start_ms, len(user_text), user_text)
                        likely_echo, echo_ratio, echo_coverage = host._likely_tts_echo(
                            user_text,
                            playback_generation_at_start=(
                                playback_generation_at_start
                                if started_during_playback
                                else None
                            ),
                        )
                        if likely_echo:
                            host.session_log(
                                session_id,
                                "asr_tts_echo_suppressed: generation=%s ratio=%.3f "
                                "coverage=%.3f text=%r",
                                playback_generation_at_start,
                                echo_ratio,
                                echo_coverage,
                                user_text,
                            )
                            if playback_candidate:
                                await self._release_playback_duck(
                                    generation=playback_generation_at_start,
                                    session_id=session_id,
                                    reason="likely_tts_echo",
                                )
                            else:
                                state = host.sessions.state.get(session_id)
                                if state is not None:
                                    state["llm_done"] = True
                                host.maybe_session_done(session_id)
                            return
                        if user_text:
                            if playback_candidate:
                                confirmation_started_ms = now_ms()
                                await host.abort_output_stream()
                                host._invalidate_output_state(
                                    cancel_cognitive_work=False,
                                )
                                confirmed_speech_to_silence_ms = (
                                    now_ms() - confirmation_started_ms
                                )
                                new_session_id = host.create_session()
                                with host.sessions.trace_context(new_session_id):
                                    host.session_log(
                                        new_session_id,
                                        "vad_valid_end: audio=%.2fs rms=%.1f bytes=%s "
                                        "started_during_playback=true",
                                        duration,
                                        rms,
                                        len(audio),
                                    )
                                    host.save_audio(
                                        audio,
                                        "input",
                                        session_id=new_session_id,
                                    )
                                    host.sessions.capture_input_audio(
                                        new_session_id,
                                        audio,
                                        sample_rate_hz=host.target_asr_rate,
                                        channels=1,
                                    )
                                    host.session_log(
                                        new_session_id,
                                        "asr_final: asr_ms=%.1f text_chars=%s text=%r",
                                        asr_done_ms - asr_start_ms,
                                        len(user_text),
                                        user_text,
                                    )
                                    host.session_log(
                                        new_session_id,
                                        "barge_in_external_speech_confirmed: "
                                        "scope=output_only cancel_cognitive_work=false "
                                        "playback_generation_at_start=%s "
                                        "confirmed_speech_to_silence_ms=%.1f",
                                        playback_generation_at_start,
                                        confirmed_speech_to_silence_ms,
                                    )
                                session_id = new_session_id
                            host._launch_routed_turn(user_text, session_id)
                        else:
                            host.session_log(session_id, "asr_empty_text")
                            if playback_candidate:
                                await self._release_playback_duck(
                                    generation=playback_generation_at_start,
                                    session_id=session_id,
                                    reason="asr_empty",
                                )
                    elif playback_candidate:
                        await self._release_playback_duck(
                            generation=playback_generation_at_start,
                            session_id=session_id,
                            reason="unsupported_asr_result",
                        )
            except Exception as exc:
                if playback_candidate:
                    await self._release_playback_duck(
                        generation=playback_generation_at_start,
                        session_id=session_id,
                        reason="asr_exception",
                    )
                host.session_log(session_id, "asr_exception: error=%s", exc)
                logger.error("%s ASR error: %s", session_id, exc, exc_info=True)
                try:
                    if host.asr_ws:
                        await host.asr_ws.close()
                except Exception as close_exc:
                    logger.debug(
                        "%s Best-effort ASR websocket close failed: %s",
                        session_id,
                        close_exc,
                    )
                host.asr_ws = None

    def _has_active_protective_reflex(
        self,
        *,
        excluding: asyncio.Task | None = None,
    ) -> bool:
        host = self.host
        return host._input_turn_state().has_active_protective_reflex(
            excluding=excluding
        )

    def _cancel_active_routed_turns(
        self,
        *,
        excluding: asyncio.Task | None,
        cancel_all: bool,
        reason: str,
    ) -> tuple[str, ...]:
        host = self.host
        """Cancel routed work only after an explicit scoped decision."""

        cancelled_session_ids = host._input_turn_state().request_turn_cancellation(
            excluding=excluding,
            cancel_all=cancel_all,
            reason=reason,
        )
        for session_id in cancelled_session_ids:
            host.session_log(
                session_id or None,
                "routed_turn_cancellation_requested: reason=%s scope=%s",
                reason,
                "all" if cancel_all else "foreground",
            )
        return cancelled_session_ids

    def _launch_routed_turn(self, user_text: str, session_id: str) -> None:
        host = self.host
        reflex_candidate = DEFAULT_REFLEX_FILTER.evaluate(user_text)
        if host._has_active_protective_reflex():
            if reflex_candidate.action == "interrupt":
                # A new deterministic protective input is independent of an
                # older protective operation. It must not wait behind output
                # cleanup or provider I/O, and an ordinary queued turn must
                # never be able to replace it.
                task = asyncio.create_task(
                    host.handle_routed_text(user_text, session_id)
                )
                lifecycle = host._input_turn_state()
                lifecycle.register_turn(
                    task,
                    session_id,
                    protective_reflex=True,
                    concurrent_reflex=True,
                )

                def protective_done(completed: asyncio.Task) -> None:
                    host._on_routed_turn_done(
                        completed,
                        session_id,
                        concurrent_reflex=True,
                    )

                task.add_done_callback(protective_done)
                host.session_log(
                    session_id,
                    "protective_reflex_launched_concurrently: scope=%s",
                    reflex_candidate.cancellation_scope,
                )
                return
            queue_depth = host._input_turn_state().queue_turn_after_reflex(
                user_text,
                session_id,
            )
            host.session_log(
                session_id,
                "turn_queued_behind_cognitive_gateway_reflex: queue_depth=%s",
                queue_depth,
            )
            return

        task = asyncio.create_task(host.handle_routed_text(user_text, session_id))
        is_reflex = reflex_candidate.action == "interrupt"
        host._input_turn_state().register_turn(
            task,
            session_id,
            protective_reflex=is_reflex,
        )
        if is_reflex:
            # Marked at launch time so a following utterance cannot cancel it
            # before the coroutine reaches its first instruction.
            host._protective_reflex_failure = False
        task.add_done_callback(
            lambda completed, sid=session_id: host._on_routed_turn_done(
                completed,
                sid,
            )
        )

    def _on_routed_turn_done(
        self,
        task: asyncio.Task,
        session_id: str,
        *,
        concurrent_reflex: bool = False,
    ) -> None:
        host = self.host
        lifecycle = host._input_turn_state()
        was_concurrent_hint = concurrent_reflex or task in (
            lifecycle.concurrent_protective_reflex_tasks
        )
        (
            cancellation_reason,
            was_primary_reflex,
            was_concurrent_reflex,
        ) = lifecycle.unregister_turn(task)
        was_concurrent_reflex = was_concurrent_reflex or was_concurrent_hint
        was_reflex = was_primary_reflex or was_concurrent_reflex
        completed_ok = False
        if task.cancelled():
            host.session_log(
                session_id,
                "turn_cancelled: reason=%s",
                cancellation_reason or "external_or_cleanup",
            )
            state = host.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            host.maybe_session_done(session_id)
        else:
            try:
                task.result()
                completed_ok = True
            except Exception as exc:  # pragma: no cover - defensive callback logging
                logger.error(
                    "%s routed turn failed outside normal handler: %s",
                    session_id,
                    exc,
                    exc_info=True,
                )

        if not was_reflex:
            return
        if not completed_ok:
            host._protective_reflex_failure = True
        if host._has_active_protective_reflex():
            return
        pending = host._input_turn_state().drain_turns_after_reflex()
        protective_failed = bool(
            getattr(host, "_protective_reflex_failure", False)
        )
        host._protective_reflex_failure = False
        if not pending:
            return
        if not protective_failed:
            for pending_text, pending_session_id in pending:
                host.session_log(
                    pending_session_id,
                    "turn_released_after_cognitive_gateway_reflex",
                )
                host._launch_routed_turn(pending_text, pending_session_id)
            return
        for _, pending_session_id in pending:
            host.session_log(
                pending_session_id,
                "turn_dropped_after_failed_cognitive_gateway_reflex",
            )
            state = host.sessions.state.get(pending_session_id)
            if state is not None:
                state["llm_done"] = True
            host.maybe_session_done(pending_session_id)

    def _queue_vad_utterance(
        self,
        audio: bytes,
        *,
        started_during_playback: bool = False,
        playback_generation_at_start: int | None = None,
    ) -> None:
        host = self.host
        queued: bytes | tuple[bytes, bool, int | None]
        if started_during_playback or playback_generation_at_start is not None:
            queued = (
                audio,
                bool(started_during_playback),
                playback_generation_at_start,
            )
        else:
            queued = audio
        lifecycle = host._input_turn_state()
        active = lifecycle.active_asr_task
        if active is not None and not active.done():
            replaced = lifecycle.queue_pending_vad_audio(queued)
            logger.info(
                "ASR is processing; queued latest utterance%s",
                " and replaced older pending audio" if replaced else "",
            )
            return
        task = asyncio.create_task(
            host.handle_vad_audio(
                audio,
                started_during_playback=started_during_playback,
                playback_generation_at_start=playback_generation_at_start,
            )
        )
        lifecycle.register_asr_task(task)
        task.add_done_callback(host._on_asr_task_done)

    def _on_asr_task_done(self, task: asyncio.Task) -> None:
        host = self.host
        lifecycle = host._input_turn_state()
        lifecycle.complete_asr_task(task)
        if not task.cancelled():
            try:
                task.result()
            except Exception as exc:  # pragma: no cover - handle_vad_audio logs normally
                logger.error("ASR task failed: %s", exc, exc_info=True)
        pending = lifecycle.take_pending_vad_audio()
        if pending:
            if isinstance(pending, tuple) and len(pending) == 3:
                (
                    pending_audio,
                    pending_started_playing,
                    pending_generation,
                ) = pending
            else:
                # Compatibility for tests and old in-process embeddings that
                # populated the pre-provenance bytes-only queue directly.
                pending_audio = pending
                pending_started_playing = False
                pending_generation = None
            if pending_started_playing or pending_generation is not None:
                host._queue_vad_utterance(
                    pending_audio,
                    started_during_playback=pending_started_playing,
                    playback_generation_at_start=pending_generation,
                )
            else:
                host._queue_vad_utterance(pending_audio)

    async def _feed_vad_pcm16(self, pcm_16k: bytes) -> None:
        host = self.host
        frame_bytes_target = int(
            host.target_asr_rate * host.frame_duration_ms / 1000
        ) * 2
        buffered = host._vad_leftover + pcm_16k
        offset = 0
        while offset + frame_bytes_target <= len(buffered):
            frame = buffered[offset : offset + frame_bytes_target]
            offset += frame_bytes_target
            started, ended, vad_audio = host.vad.process_chunk(frame)
            if started:
                host._vad_segment_started_during_playback = bool(
                    host.is_playing_audio
                )
                host._vad_segment_playback_generation = host.playback_generation
                logger.info(
                    "VAD detected voice: playing=%s playback_generation=%s",
                    host._vad_segment_started_during_playback,
                    host._vad_segment_playback_generation,
                )
                if host._vad_segment_started_during_playback:
                    await self._begin_playback_duck(
                        generation=host._vad_segment_playback_generation,
                        session_id=getattr(host, "session_id", None),
                    )
            if ended and vad_audio:
                started_during_playback = bool(
                    host._vad_segment_started_during_playback
                )
                playback_generation_at_start = (
                    host._vad_segment_playback_generation
                )
                host._vad_segment_started_during_playback = False
                host._vad_segment_playback_generation = None
                if getattr(host.vad, "last_end_reason", None) == "max_duration":
                    logger.warning(
                        "VAD force-closed and discarded an overlong utterance: duration_limit_ms=%s bytes=%s",
                        host.max_vad_utterance_ms,
                        len(vad_audio),
                    )
                    await self._release_playback_duck(
                        generation=playback_generation_at_start,
                        session_id=(
                            host._playback_state().output_duck_session_id
                        ),
                        reason="hard_maximum",
                    )
                else:
                    host._queue_vad_utterance(
                        vad_audio,
                        started_during_playback=started_during_playback,
                        playback_generation_at_start=(
                            playback_generation_at_start
                        ),
                    )
            elif ended:
                await self._release_playback_duck(
                    generation=host._vad_segment_playback_generation,
                    session_id=host._playback_state().output_duck_session_id,
                    reason="empty_vad_end",
                )
                host._vad_segment_started_during_playback = False
                host._vad_segment_playback_generation = None
        host._vad_leftover = buffered[offset:]
        await asyncio.sleep(0)

    async def mic_stream(self):
        host = self.host
        logger.info("Opening microphone with sounddevice")
        host.loop = asyncio.get_running_loop()
        while True:
            await host._apply_pending_input_device_change()
            sd = _sounddevice()
            try:
                with sd.InputStream(
                    samplerate=host.input_rate,
                    channels=host.input_channels,
                    dtype="float32",
                    blocksize=host.input_block_size,
                    device=host.input_device,
                    latency=host.input_latency,
                    callback=host.mic_callback,
                ):
                    logger.info(
                        "Microphone started: name=%s device=%r rate=%s channels=%s",
                        host.input_params.get("name", "unknown"),
                        host.input_device,
                        host.input_rate,
                        host.input_channels,
                    )
                    logger.info("Audio input started: mode=device")
                    while not host._input_device_change_event.is_set():
                        try:
                            audio = await asyncio.wait_for(
                                host.mic_queue.get(),
                                timeout=0.5,
                            )
                        except asyncio.TimeoutError:
                            continue
                        pcm_16k = host.prepare_mic_chunk_for_asr(audio)
                        await host._feed_vad_pcm16(pcm_16k)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not host.audio_mgr.follows_system_default("input"):
                    raise
                logger.warning(
                    "OS-default microphone stream failed; waiting for the "
                    "current valid system default: %s",
                    exc,
                )
                await host._refresh_system_default_audio_devices(
                    force_kinds={"input"},
                )
                await asyncio.sleep(1.0)

    async def injected_audio_stream(self):
        host = self.host
        """Consume framed PCM16 utterances from stdin for acceptance testing.

        The binary framing is intentionally available only through inherited
        stdin. It does not open a network control port in normal operation.
        Each packet is treated as microphone input and still passes through
        Chromie's VAD and ASR path.
        """

        logger.info("Audio input started: mode=stdin protocol=CAUD/v1")
        while True:
            packet = await asyncio.to_thread(read_audio_packet, sys.stdin.buffer)
            if packet is None:
                logger.info("Injected audio input reached EOF")
                return
            samples = np.frombuffer(packet.pcm16, dtype=np.int16)
            if packet.channels > 1:
                samples = samples.reshape(-1, packet.channels).mean(axis=1).astype(
                    np.int16
                )
            pcm = samples.astype(np.int16, copy=False).tobytes()
            pcm_16k = host.resample_int16_bytes(
                pcm,
                packet.sample_rate,
                host.target_asr_rate,
            )
            duration_ms = len(pcm_16k) / (host.target_asr_rate * 2) * 1000.0
            logger.info(
                "Injected audio received: source_rate=%s channels=%s bytes=%s "
                "resampled_ms=%.1f",
                packet.sample_rate,
                packet.channels,
                len(packet.pcm16),
                duration_ms,
            )
            await host._feed_vad_pcm16(pcm_16k)
            # Ensure the VAD sees enough trailing silence to close the utterance.
            configured_vad_silence_ms = int(
                getattr(
                    getattr(
                        getattr(host, "host_settings", None),
                        "audio_input",
                        None,
                    ),
                    "vad_silence_ms",
                    650,
                )
            )
            silence_ms = max(900, configured_vad_silence_ms + 150)
            silence = b"\x00\x00" * int(
                host.target_asr_rate * silence_ms / 1000
            )
            await host._feed_vad_pcm16(silence)

    async def _session_idle_sweeper(self) -> None:
        host = self.host
        session_settings = getattr(
            getattr(host, "host_settings", None),
            "session",
            None,
        )
        interval_s = float(getattr(session_settings, "idle_sweep_s", 5.0))
        idle_timeout_ms = float(
            getattr(session_settings, "idle_timeout_ms", 120000.0)
        )
        loop = asyncio.get_running_loop()
        expected_wake = loop.time() + interval_s
        while True:
            await asyncio.sleep(interval_s)
            actual_wake = loop.time()
            event_loop_lag_ms = max(0.0, (actual_wake - expected_wake) * 1000.0)
            expected_wake = actual_wake + interval_s
            host.sessions.sample_active_resources(
                event_loop_lag_ms=event_loop_lag_ms,
                attributes={
                    "playback_queue_depth": host.playback_queue.qsize(),
                    "mic_queue_depth": host.mic_queue.qsize(),
                    "active_synthesis_tasks": len(host.active_synthesis_tasks),
                },
            )
            await host._sample_accelerator_resources(reason="periodic")
            host.sessions.checkpoint_active_traces()
            host.sessions.finalize_idle_sessions(idle_timeout_ms=idle_timeout_ms)



def input_session_runtime_for(host: Any) -> InputSessionRuntime:
    lifecycle = host._input_turn_state()
    runtime = lifecycle.runtime
    if not isinstance(runtime, InputSessionRuntime):
        runtime = InputSessionRuntime(host)
        lifecycle.runtime = runtime
    return runtime
