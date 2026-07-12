from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.fast_first_audio import (
    CachedFastFirstAudio,
    FastFirstAudioCache,
)
from orchestrator.runtime.session import SessionTracker
from orchestrator.schemas.route import RouteDecision


class FastFirstAudioHedgeTests(unittest.IsolatedAsyncioTestCase):
    def _assistant(self, *, hedge_ms: int = 20) -> tuple[VoiceAssistant, str]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_response_enabled = True
        assistant.fast_first_audio_hedge_ms = hedge_ms
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.next_playback_order = 0
        assistant.playback_generation = 0
        assistant.playback_queue = asyncio.Queue()
        assistant.pending_audio = {}
        assistant.playback_task = None
        assistant.playback_start_waiters = {}
        assistant.cancelled_playback_orders = set()
        assistant.active_synthesis_tasks = set()
        assistant.default_tts_rate = 16000
        assistant.output_rate = 16000
        assistant.output_channels = 1
        assistant.audio_output_mode = "discard"
        assistant.discard_playback_realtime = False
        assistant.playback_chunk_ms = 20
        assistant.is_playing_audio = False
        assistant.save_audio_enabled = False

        cache = FastFirstAudioCache(tempfile.mkdtemp())
        cache._audio[("checking", "en")] = CachedFastFirstAudio(
            purpose="checking",
            language="en",
            text="One moment.",
            pcm16=b"\x01\x00" * 160,
            sample_rate=16000,
            path=Path("cached.wav"),
        )
        cache._audio[("planning", "en")] = CachedFastFirstAudio(
            purpose="planning",
            language="en",
            text="Let me check that.",
            pcm16=b"\x02\x00" * 160,
            sample_rate=16000,
            path=Path("cached.wav"),
        )
        assistant.fast_first_audio_cache = cache
        return assistant, session_id

    async def test_final_ready_before_hedge_suppresses_cached_audio(self) -> None:
        assistant, session_id = self._assistant(hedge_ms=100)
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            language="en-US",
        )

        hedge = assistant._start_fast_first_audio_hedge(
            decision,
            "Check the weather.",
            session_id,
        )
        played = await assistant._settle_fast_first_audio_hedge(
            hedge,
            decision=decision,
            session_id=session_id,
        )

        self.assertFalse(played)
        self.assertTrue(assistant.playback_queue.empty())
        self.assertEqual(assistant.sessions.state[session_id]["scheduled_tts"], 0)

    async def test_cached_audio_is_queued_after_hedge_without_tts_request(self) -> None:
        assistant, session_id = self._assistant(hedge_ms=1)
        # Keep the queue unconsumed so final readiness can cancel the cached cue
        # before playback starts.
        assistant.ensure_playback_worker = MethodType(lambda self: None, assistant)
        decision = RouteDecision(
            route="robot_action",
            intent="capability:soridormi.walk_forward",
            language="en-US",
            speak_first="I will check whether I can do that safely.",
        )

        hedge = assistant._start_fast_first_audio_hedge(
            decision,
            "Walk forward.",
            session_id,
        )
        self.assertIsNotNone(hedge)
        await asyncio.sleep(0.02)
        assert hedge is not None
        self.assertTrue(hedge.done())
        self.assertIsNone(decision.speak_first)
        self.assertEqual(assistant.playback_queue.qsize(), 1)
        self.assertEqual(assistant.sessions.state[session_id]["scheduled_tts"], 1)

        played = await assistant._settle_fast_first_audio_hedge(
            hedge,
            decision=decision,
            session_id=session_id,
        )
        self.assertFalse(played)
        self.assertEqual(len(assistant.cancelled_playback_orders), 1)
        self.assertEqual(assistant.sessions.state[session_id]["skipped_tts"], 1)

    async def test_cached_audio_starts_without_generative_tts(self) -> None:
        assistant, session_id = self._assistant(hedge_ms=0)
        playback_started = asyncio.Event()
        seen_audio: list[bytes] = []

        async def play_audio(
            self: VoiceAssistant,
            audio_bytes: bytes,
            source_rate: int,
            generation: int,
            sid: str | None,
        ) -> None:
            del source_rate, generation, sid
            seen_audio.append(audio_bytes)
            playback_started.set()

        assistant.play_audio = MethodType(play_audio, assistant)
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            language="en-US",
        )

        hedge = assistant._start_fast_first_audio_hedge(
            decision,
            "Check the weather.",
            session_id,
        )
        self.assertIsNotNone(hedge)
        await asyncio.wait_for(playback_started.wait(), timeout=1.0)
        assert hedge is not None
        played = await assistant._settle_fast_first_audio_hedge(
            hedge,
            decision=decision,
            session_id=session_id,
        )

        self.assertTrue(played)
        self.assertEqual(len(seen_audio), 1)
        self.assertEqual(assistant.sessions.state[session_id]["played_tts"], 1)
        await assistant.playback_queue.put((None, None, None, None, None, None))
        if assistant.playback_task is not None:
            await asyncio.wait_for(assistant.playback_task, timeout=1.0)


if __name__ == "__main__":
    unittest.main()
