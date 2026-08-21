from __future__ import annotations

import asyncio
import json
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle
from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle
from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from orchestrator.runtime.session import SessionTracker, now_ms


class _Asr:
    close_code = None

    def __init__(self, text: str) -> None:
        self.text = text
        self.sent: list[bytes] = []

    async def send(self, audio: bytes) -> None:
        self.sent.append(audio)

    async def recv(self) -> str:
        return json.dumps({"type": "final", "text": self.text})

    async def close(self) -> None:
        return None


class _StartOnlyVad:
    last_end_reason = None

    def process_chunk(self, frame: bytes) -> tuple[bool, bool, bytes]:
        del frame
        return True, False, b""


class BargeInDuckingTests(unittest.IsolatedAsyncioTestCase):
    def _assistant(self, *, asr_text: str) -> tuple[VoiceAssistant, str, list[tuple[str | None, str]]]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_delivery = PlaybackDeliveryLifecycle(
            playback_generation=3
        )
        assistant.input_turn_lifecycle = InputTurnLifecycle()
        assistant.sessions = SessionTracker(enabled=True)
        old_session_id = assistant.sessions.create()
        assistant.is_playing_audio = True
        assistant.audio_output_mode = "discard"
        assistant.discard_playback_realtime = False
        assistant.max_vad_utterance_ms = 20_000
        assistant.asr_timeout_s = 1.0
        assistant.target_asr_rate = 16_000
        assistant.min_audio_ms = 100
        assistant.min_rms = 120.0
        assistant.barge_in_min_rms = 350.0
        assistant.asr_ws = _Asr(asr_text)
        assistant._tts_text_by_generation = {
            3: ["Chromie is reading the current response aloud."]
        }
        logs: list[tuple[str | None, str]] = []

        def session_log(
            self: VoiceAssistant,
            sid: str | None,
            message: str,
            *args: Any,
        ) -> None:
            logs.append((sid, message % args if args else message))
            self.sessions.log(sid, message, *args)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.save_audio = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )
        return assistant, old_session_id, logs

    async def test_vad_start_ducks_before_the_utterance_ends(self) -> None:
        assistant, old_session_id, logs = self._assistant(asr_text="unused")
        assistant.vad = _StartOnlyVad()
        assistant.frame_duration_ms = 30
        assistant._vad_leftover = b""

        def reject_completed_utterance(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            raise AssertionError("utterance must remain open")

        input_session_runtime_for(assistant)._queue_vad_utterance = MethodType(
            reject_completed_utterance,
            input_session_runtime_for(assistant),
        )
        frame = b"\x00\x00" * 480

        await input_session_runtime_for(assistant)._feed_vad_pcm16(frame)

        state = assistant._playback_state()
        self.assertTrue(state.output_duck_matches(3, old_session_id))
        self.assertEqual(assistant.playback_generation, 3)
        self.assertTrue(
            any(
                sid == old_session_id
                and "playback_duck_started:" in message
                and "cancel_cognitive_work=false" in message
                for sid, message in logs
            )
        )
        await input_session_runtime_for(assistant)._release_playback_duck(
            generation=3,
            session_id=old_session_id,
            reason="test_cleanup",
        )

    async def test_likely_echo_resumes_the_same_generation_without_a_new_turn(self) -> None:
        spoken = "Chromie is reading the current response aloud."
        assistant, old_session_id, logs = self._assistant(asr_text=spoken)
        routes: list[tuple[str, str]] = []
        input_session_runtime_for(assistant)._launch_routed_turn = MethodType(
            lambda self, text, sid: routes.append((text, sid)),
            input_session_runtime_for(assistant),
        )
        invalidations: list[bool] = []
        assistant._invalidate_output_state = MethodType(
            lambda self, *, cancel_cognitive_work=True: invalidations.append(
                cancel_cognitive_work
            ),
            assistant,
        )
        runtime = input_session_runtime_for(assistant)
        await runtime._begin_playback_duck(
            generation=3,
            session_id=old_session_id,
        )
        audio = int(1000).to_bytes(2, "little", signed=True) * 16_000

        await runtime.handle_vad_audio(
            audio,
            started_during_playback=True,
            playback_generation_at_start=3,
        )

        self.assertEqual(assistant.sessions.current_sid, old_session_id)
        self.assertEqual(assistant.playback_generation, 3)
        self.assertFalse(assistant._playback_state().output_duck_matches(3, old_session_id))
        self.assertEqual(invalidations, [])
        self.assertEqual(routes, [])
        self.assertTrue(
            any("reason=likely_tts_echo" in message for _sid, message in logs)
        )

    async def test_confirmed_external_speech_aborts_output_only_then_routes(self) -> None:
        assistant, old_session_id, logs = self._assistant(asr_text="Stop talking.")
        invalidations: list[bool] = []
        aborts: list[float] = []
        routes: list[tuple[str, str]] = []

        def invalidate(
            self: VoiceAssistant,
            *,
            cancel_cognitive_work: bool = True,
        ) -> None:
            invalidations.append(cancel_cognitive_work)
            self.playback_generation += 1
            self._playback_state().cancel_output_duck()

        async def abort_output(self: VoiceAssistant) -> None:
            if not self.host._playback_state().output_duck_matches(3, old_session_id):
                raise AssertionError(
                    "output generation must remain ducked until the stream is silent"
                )
            aborts.append(now_ms())

        assistant._invalidate_output_state = MethodType(invalidate, assistant)
        playback_transport_for(assistant).abort_output_stream = MethodType(
            abort_output, playback_transport_for(assistant)
        )
        input_session_runtime_for(assistant)._launch_routed_turn = MethodType(
            lambda self, text, sid: routes.append((text, sid)),
            input_session_runtime_for(assistant),
        )
        runtime = input_session_runtime_for(assistant)
        await runtime._begin_playback_duck(
            generation=3,
            session_id=old_session_id,
        )
        audio = int(1000).to_bytes(2, "little", signed=True) * 16_000

        await runtime.handle_vad_audio(
            audio,
            started_during_playback=True,
            playback_generation_at_start=3,
        )

        new_session_id = assistant.sessions.current_sid
        self.assertNotEqual(new_session_id, old_session_id)
        self.assertEqual(invalidations, [False])
        self.assertEqual(len(aborts), 1)
        self.assertEqual(routes, [("Stop talking.", new_session_id)])
        self.assertEqual(assistant.playback_generation, 4)
        self.assertIsNone(assistant._playback_state().output_duck_generation)
        self.assertTrue(
            any(
                sid == new_session_id
                and "barge_in_external_speech_confirmed:" in message
                and "scope=output_only" in message
                and "cancel_cognitive_work=false" in message
                and "confirmed_speech_to_silence_ms=" in message
                for sid, message in logs
            )
        )

    async def test_confirmation_timeout_resumes_without_invalidating_output(self) -> None:
        assistant, old_session_id, logs = self._assistant(asr_text="unused")
        assistant.max_vad_utterance_ms = 1
        assistant.asr_timeout_s = 0.001

        await input_session_runtime_for(assistant)._begin_playback_duck(
            generation=3,
            session_id=old_session_id,
        )
        await asyncio.wait_for(
            assistant._playback_state().output_duck_released.wait(),
            timeout=0.1,
        )

        self.assertEqual(assistant.playback_generation, 3)
        self.assertTrue(
            any(
                "playback_duck_released:" in message
                and "reason=confirmation_timeout" in message
                for _sid, message in logs
            )
        )

    async def test_device_duck_aborts_then_restarts_the_same_stream(self) -> None:
        assistant, old_session_id, _logs = self._assistant(asr_text="unused")
        assistant.audio_output_mode = "device"
        assistant.output_write_lock = asyncio.Lock()
        assistant.output_stream_lock = asyncio.Lock()

        class _Stream:
            aborts = 0
            starts = 0

            def abort(self) -> None:
                self.aborts += 1

            def start(self) -> None:
                self.starts += 1

        stream = _Stream()
        assistant.output_stream = stream
        state = assistant._playback_state()
        state.begin_output_duck(
            generation=3,
            session_id=old_session_id,
            started_ms=now_ms(),
        )

        transport = playback_transport_for(assistant)
        await transport.pause_output_for_duck(
            generation=3,
            session_id=old_session_id,
        )
        await transport.resume_output_after_duck(
            generation=3,
            session_id=old_session_id,
            reason="likely_noise",
        )

        self.assertEqual(stream.aborts, 1)
        self.assertEqual(stream.starts, 1)
        self.assertIs(assistant.output_stream, stream)
        self.assertIsNone(state.output_duck_generation)


if __name__ == "__main__":
    unittest.main()
