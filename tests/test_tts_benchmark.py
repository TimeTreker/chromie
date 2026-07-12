from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_tts",
    ROOT / "scripts" / "benchmark_tts.py",
)
assert SPEC is not None and SPEC.loader is not None
benchmark_tts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark_tts)


class TtsBenchmarkTests(unittest.TestCase):
    def test_summary_uses_observed_first_audio_and_server_stage_metrics(self) -> None:
        results = [
            {
                "observed_first_binary_seconds": 1.5,
                "observed_total_seconds": 2.0,
                "end": {
                    "audio_seconds": 1.0,
                    "generate_seconds": 1.2,
                    "model_generate_seconds": 0.9,
                    "codec_decode_seconds": 0.2,
                    "pcm_conversion_seconds": 0.01,
                    "realtime_factor": 1.2,
                    "generation_limit_reached": True,
                },
            },
            {
                "observed_first_binary_seconds": 0.5,
                "observed_total_seconds": 1.0,
                "end": {
                    "audio_seconds": 1.0,
                    "generate_seconds": 0.8,
                    "model_generate_seconds": 0.6,
                    "codec_decode_seconds": 0.1,
                    "pcm_conversion_seconds": 0.01,
                    "realtime_factor": 0.8,
                },
            },
        ]

        summary = benchmark_tts.summarize(results)

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["median_first_binary_seconds"], 1.0)
        self.assertEqual(summary["median_realtime_factor"], 1.0)
        self.assertEqual(summary["median_codec_decode_seconds"], 0.15)
        self.assertEqual(summary["generation_limit_reached_count"], 1)


if __name__ == "__main__":
    unittest.main()
