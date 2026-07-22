from __future__ import annotations

import asyncio
import tempfile
import unittest
import wave
from pathlib import Path

from orchestrator.runtime.fast_first_audio import (
    CachedFastFirstAudio,
    FastFirstAudioCache,
    FastFirstCue,
)


class FastFirstAudioCacheTests(unittest.IsolatedAsyncioTestCase):
    def test_route_and_language_select_semantic_cue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp)
            self.assertEqual(
                cache.cue_for(
                    route="tool",
                    language="zh-CN",
                    user_text="北京天气怎么样？",
                ),
                FastFirstCue("checking", "zh", "稍等一下。"),
            )
            self.assertEqual(
                cache.cue_for(
                    route="robot_action",
                    language="en-US",
                    user_text="Walk forward.",
                ),
                FastFirstCue("planning", "en", "Let me check that."),
            )
            self.assertIsNone(
                cache.cue_for(
                    route="chat",
                    language="en-US",
                    user_text="Hello.",
                )
            )

    def test_existing_wav_loads_into_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp)
            cue = FastFirstCue("checking", "en", "One moment.")
            path = cache._cache_path(cue, "default")
            path.parent.mkdir(parents=True, exist_ok=True)
            pcm = b"\x01\x00" * 320
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)

            loaded = cache.load_existing(speaker_id="default")
            audio = cache.get(
                route="tool",
                language="en-US",
                user_text="Check the weather.",
            )

            self.assertEqual(loaded, 1)
            self.assertIsNotNone(audio)
            assert audio is not None
            self.assertEqual(audio.pcm16, pcm)
            self.assertEqual(audio.sample_rate, 16000)

    async def test_prime_missing_persists_generated_audio(self) -> None:
        cues = (FastFirstCue("checking", "en", "One moment."),)
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp, cues=cues)

            async def fake_synthesize(
                cue: FastFirstCue,
                *,
                tts_url: str,
                speaker_id: str,
            ) -> tuple[bytes, int]:
                self.assertEqual(cue, cues[0])
                self.assertEqual(tts_url, "ws://tts")
                self.assertEqual(speaker_id, "default")
                return b"\x02\x00" * 400, 16000

            cache._synthesize_cue = fake_synthesize  # type: ignore[method-assign]

            async def fake_identity(*, tts_url: str, speaker_id: str) -> str:
                self.assertEqual(tts_url, "ws://tts")
                self.assertEqual(speaker_id, "default")
                cache._cache_identity = "provider-a"
                return cache._cache_identity

            cache._resolve_cache_identity = fake_identity  # type: ignore[method-assign]
            stats = await cache.prime_missing(
                tts_url="ws://tts",
                speaker_id="default",
            )

            self.assertEqual(stats, {"loaded": 0, "generated": 1, "failed": 0})
            self.assertEqual(cache.ready_count, 1)
            generated = list(Path(tmp).glob("*.wav"))
            self.assertEqual(len(generated), 1)

            second = FastFirstAudioCache(tmp, cues=cues)
            second._cache_identity = cache._cache_identity
            self.assertEqual(second.load_existing(speaker_id="default"), 1)
            audio = second.get(route="tool", language="en-US")
            self.assertIsInstance(audio, CachedFastFirstAudio)

    async def test_prime_rejects_prompt_leakage_before_persisting(self) -> None:
        cues = (FastFirstCue("checking", "zh", "稍等一下。"),)
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp, cues=cues, max_cue_seconds=10.0)

            async def fake_identity(*, tts_url: str, speaker_id: str) -> str:
                del tts_url, speaker_id
                cache._cache_identity = "oute-mixed"
                return cache._cache_identity

            async def fake_synthesize(
                cue: FastFirstCue,
                *,
                tts_url: str,
                speaker_id: str,
            ) -> tuple[bytes, int]:
                del cue, tts_url, speaker_id
                return b"\x02\x00" * 16000, 16000

            async def fake_transcribe(**kwargs: object) -> str:
                del kwargs
                return "Hello, I'm Chromie. I'm happy to explore the world with you."

            cache._resolve_cache_identity = fake_identity  # type: ignore[method-assign]
            cache._synthesize_cue = fake_synthesize  # type: ignore[method-assign]
            cache._transcribe_audio = fake_transcribe  # type: ignore[method-assign]

            stats = await cache.prime_missing(
                tts_url="ws://tts",
                speaker_id="chromie_mixed",
                asr_url="ws://asr",
            )

            self.assertEqual(stats, {"loaded": 0, "generated": 0, "failed": 1})
            self.assertEqual(cache.ready_count, 0)
            self.assertEqual(list(Path(tmp).glob("*.wav")), [])

    async def test_prime_regenerates_once_after_content_rejection(self) -> None:
        cues = (FastFirstCue("thinking", "en", "Let me think."),)
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp, cues=cues, generation_attempts=2)
            syntheses = 0
            transcriptions = iter(("unrelated enrollment speech", "Let me think."))

            async def fake_identity(*, tts_url: str, speaker_id: str) -> str:
                del tts_url, speaker_id
                cache._cache_identity = "cosyvoice"
                return cache._cache_identity

            async def fake_synthesize(
                cue: FastFirstCue,
                *,
                tts_url: str,
                speaker_id: str,
            ) -> tuple[bytes, int]:
                nonlocal syntheses
                del cue, tts_url, speaker_id
                syntheses += 1
                return b"\x02\x00" * 16000, 16000

            async def fake_transcribe(**kwargs: object) -> str:
                del kwargs
                return next(transcriptions)

            cache._resolve_cache_identity = fake_identity  # type: ignore[method-assign]
            cache._synthesize_cue = fake_synthesize  # type: ignore[method-assign]
            cache._transcribe_audio = fake_transcribe  # type: ignore[method-assign]

            stats = await cache.prime_missing(
                tts_url="ws://tts",
                speaker_id="default",
                asr_url="ws://asr",
            )

            self.assertEqual(stats, {"loaded": 0, "generated": 1, "failed": 0})
            self.assertEqual(syntheses, 2)
            self.assertEqual(cache.ready_count, 1)
            self.assertEqual(len(list(Path(tmp).glob("*.wav"))), 1)

    async def test_synthesis_timeout_aborts_remaining_generation_without_retry(self) -> None:
        cues = (
            FastFirstCue("checking", "en", "One moment."),
            FastFirstCue("thinking", "en", "Let me think."),
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp, cues=cues, generation_attempts=2)
            syntheses = 0

            async def fake_identity(*, tts_url: str, speaker_id: str) -> str:
                del tts_url, speaker_id
                cache._cache_identity = "slow-candidate"
                return cache._cache_identity

            async def fake_synthesize(
                cue: FastFirstCue,
                *,
                tts_url: str,
                speaker_id: str,
            ) -> tuple[bytes, int]:
                nonlocal syntheses
                del cue, tts_url, speaker_id
                syntheses += 1
                raise asyncio.TimeoutError

            cache._resolve_cache_identity = fake_identity  # type: ignore[method-assign]
            cache._synthesize_cue = fake_synthesize  # type: ignore[method-assign]

            stats = await cache.prime_missing(
                tts_url="ws://tts",
                speaker_id="default",
            )

            self.assertEqual(stats, {"loaded": 0, "generated": 0, "failed": 1})
            self.assertEqual(syntheses, 1)
            self.assertEqual(cache.ready_count, 0)

    def test_provider_identity_changes_cache_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = FastFirstAudioCache(tmp)
            cue = FastFirstCue("checking", "en", "One moment.")
            cache._cache_identity = "oute"
            oute_path = cache._cache_path(cue, "default")
            cache._cache_identity = "cosyvoice"
            cosy_path = cache._cache_path(cue, "default")

            self.assertNotEqual(oute_path, cosy_path)


if __name__ == "__main__":
    unittest.main()
