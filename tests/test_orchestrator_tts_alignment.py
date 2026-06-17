from __future__ import annotations

import asyncio
import sys
import types
import unittest
from types import MethodType
from typing import Any

for module_name in ("aiohttp", "numpy", "sounddevice", "websockets"):
    if module_name not in sys.modules:
        sys.modules[module_name] = types.ModuleType(module_name)
if "scipy" not in sys.modules:
    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("signal")  # type: ignore[attr-defined]
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = scipy.signal  # type: ignore[attr-defined]

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.session import SessionTracker


class OrchestratorTtsAlignmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_interaction_speech_can_wait_until_playback_starts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            del text
            await asyncio.sleep(0)
            self.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=True,
                reason="test_playback_start",
            )

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)

        result = await assistant._schedule_interaction_speech(
            {
                "text": "La la, walking with you.",
                "metadata": {
                    "session_id": session_id,
                    "wait_for_playback_start": True,
                    "playback_start_timeout_ms": 500,
                },
            }
        )

        self.assertTrue(result["scheduled"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(result["order"], 0)
        self.assertEqual(assistant.playback_start_waiters, {})

    async def test_interaction_speech_splits_long_text_into_ordered_chunks(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.order_lock = asyncio.Lock()
        assistant.synthesis_order = 0
        assistant.playback_generation = 0
        assistant.active_synthesis_tasks = set()
        assistant.playback_start_waiters = {}
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 20
        assistant.tts_min_chunk_chars = 1
        assistant.tts_flush_chars = 160
        seen: list[tuple[int, str]] = []

        def session_log(self: VoiceAssistant, sid: str | None, message: str, *args: Any) -> None:
            self.sessions.log(sid, message, *args)

        async def synthesize_one(
            self: VoiceAssistant,
            text: str,
            order: int,
            session_id: str | None,
            generation: int,
        ) -> None:
            seen.append((order, text))
            if order == 0:
                self.resolve_playback_start_waiter(
                    generation,
                    order,
                    session_id,
                    started=True,
                    reason="test_playback_start",
                )
            await asyncio.sleep(0)

        assistant.session_log = MethodType(session_log, assistant)
        assistant.synthesize_one = MethodType(synthesize_one, assistant)

        result = await assistant._schedule_interaction_speech(
            {
                "text": "First chunk. Second chunk. Third chunk.",
                "metadata": {
                    "session_id": session_id,
                    "wait_for_playback_start": True,
                    "playback_start_timeout_ms": 500,
                },
            }
        )
        pending = list(assistant.active_synthesis_tasks)
        if pending:
            await asyncio.gather(*pending)

        self.assertTrue(result["scheduled"])
        self.assertTrue(result["playback_started"])
        self.assertEqual(result["chunks"], 3)
        self.assertEqual(result["orders"], [0, 1, 2])
        self.assertEqual(
            seen,
            [
                (0, "First chunk."),
                (1, "Second chunk."),
                (2, "Third chunk."),
            ],
        )

    async def test_tts_splitter_groups_tiny_fragments_without_swallowing_long_chunk(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.tts_text_chunking_enabled = True
        assistant.tts_chunk_chars = 80
        assistant.tts_min_chunk_chars = 40
        assistant.tts_flush_chars = 160

        chunks = assistant.split_tts_text(
            "Too fast. Walking normally. "
            "La la, tiny steps and circuits bright, I am walking through the light."
        )

        self.assertEqual(
            chunks,
            [
                "Too fast. Walking normally.",
                "La la, tiny steps and circuits bright, I am walking through the light.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
