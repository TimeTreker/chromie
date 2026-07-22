from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant


class _SlowFastFirstCache:
    enabled = True
    ready_count = 0

    async def prime_missing(self, **_kwargs: object) -> dict[str, int]:
        await asyncio.sleep(1.0)
        return {"loaded": 0, "generated": 1, "failed": 0}


class OrchestratorStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_first_total_timeout_is_nonfatal(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.fast_first_audio_cache = _SlowFastFirstCache()
        assistant.fast_first_audio_prime_timeout_ms = 1
        assistant.tts_url = "ws://tts"
        assistant.speaker_id = "default"
        assistant.asr_url = "ws://asr"
        assistant.target_asr_rate = 16000

        stats = await assistant._prime_fast_first_audio()

        self.assertEqual(stats, {"loaded": 0, "generated": 0, "failed": 1})


if __name__ == "__main__":
    unittest.main()
