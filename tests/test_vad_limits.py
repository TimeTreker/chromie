from __future__ import annotations

import unittest

from orchestrator.vad import VAD


class VadLimitTests(unittest.TestCase):
    def test_continuous_voice_force_closes_at_maximum(self) -> None:
        vad = VAD(
            mode=0,
            sample_rate=16000,
            frame_duration_ms=30,
            silence_timeout_ms=300,
            pre_roll_ms=0,
            max_utterance_ms=90,
        )
        vad.vad = None
        frame = (b"\x01\x00") * 480

        started, ended, audio = vad.process_chunk(frame)
        self.assertTrue(started)
        self.assertFalse(ended)
        self.assertIsNone(audio)

        vad.process_chunk(frame)
        _, ended, audio = vad.process_chunk(frame)

        self.assertTrue(ended)
        self.assertIsNotNone(audio)
        self.assertEqual(vad.last_end_reason, "max_duration")
        self.assertFalse(vad.in_speech)

    def test_normal_silence_end_reports_silence_reason(self) -> None:
        vad = VAD(
            mode=0,
            sample_rate=16000,
            frame_duration_ms=30,
            silence_timeout_ms=60,
            pre_roll_ms=0,
            max_utterance_ms=1000,
        )
        vad.vad = None
        speech = (b"\x01\x00") * 480
        silence = b"\x00\x00" * 480

        vad.process_chunk(speech)
        vad.process_chunk(silence)
        _, ended, audio = vad.process_chunk(silence)

        self.assertTrue(ended)
        self.assertIsNotNone(audio)
        self.assertEqual(vad.last_end_reason, "silence")


if __name__ == "__main__":
    unittest.main()
