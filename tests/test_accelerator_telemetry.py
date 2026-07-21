from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest import mock

from orchestrator.runtime.session import SessionTracker
from shared.chromie_runtime.accelerator_telemetry import (
    ACCELERATOR_SAMPLE_MODULE,
    AcceleratorTelemetryConfig,
    AcceleratorTelemetrySampler,
    parse_nvidia_smi_csv,
)


class AcceleratorTelemetryTests(unittest.TestCase):
    def test_parse_nvidia_smi_csv_and_aggregates(self) -> None:
        devices = parse_nvidia_smi_csv(
            "0, GPU-1, RTX 5090, 75, 40, 32768, 8192, 24576, 61, 350.5\n"
            "1, GPU-2, RTX 4090, 25, 15, 24576, 4096, 20480, 54, 220.0\n"
        )

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["index"], 0)
        self.assertEqual(devices[0]["gpu_utilization_percent"], 75.0)
        self.assertEqual(devices[0]["memory_used_bytes"], 8192 * 1024 * 1024)
        self.assertEqual(devices[1]["power_w"], 220.0)

    def test_async_sampler_caches_without_blocking_event_loop_contract(self) -> None:
        calls: list[float] = []

        def collector(timeout_s: float):
            calls.append(timeout_s)
            time.sleep(0.002)
            return {
                "available": True,
                "provider": "fake",
                "provider_status": "ok",
                "accelerator_device_count": 1,
                "accelerator_gpu_utilization_max_percent": 55.0,
            }

        async def run():
            sampler = AcceleratorTelemetrySampler(
                AcceleratorTelemetryConfig(
                    mode="periodic",
                    provider="auto",
                    timeout_ms=100,
                    min_interval_s=60.0,
                ),
                collector=collector,
            )
            first = await sampler.sample(reason="periodic")
            second = await sampler.sample(reason="periodic")
            cached = sampler.cached_sample(reason="session_finish")
            return first, second, cached

        first, second, cached = asyncio.run(run())

        self.assertEqual(len(calls), 1)
        self.assertFalse(first["sample_cached"])
        self.assertTrue(second["sample_cached"])
        self.assertTrue(cached["sample_cached"])
        self.assertEqual(cached["sample_reason"], "session_finish")
        self.assertIn("sample_age_ms", cached)

    def test_session_mode_ignores_periodic_sampling(self) -> None:
        sampler = AcceleratorTelemetrySampler(
            AcceleratorTelemetryConfig(mode="session", provider="auto")
        )
        self.assertTrue(sampler.should_sample("session_start"))
        self.assertTrue(sampler.should_sample("session_finish"))
        self.assertFalse(sampler.should_sample("periodic"))

    def test_session_tracker_records_cached_accelerator_boundaries(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            tracker.register_resource_snapshot_provider(
                module=ACCELERATOR_SAMPLE_MODULE,
                name="accelerator_resource_sample",
                provider=lambda *, reason: {
                    "sample_reason": reason,
                    "sample_cached": True,
                    "accelerator_device_count": 1,
                },
            )
            sid = tracker.create()
            tracker.state[sid]["llm_done"] = True
            tracker.maybe_done(sid)
            snapshot = tracker.state[sid]["runtime_trace_snapshot"]

        samples = [
            item
            for item in snapshot.trace["items"]
            if item["module"]["name"] == "chromie.runtime.accelerator"
        ]
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0]["attributes"]["sample_reason"], "session_start")
        self.assertEqual(samples[1]["attributes"]["sample_reason"], "session_finish")


if __name__ == "__main__":
    unittest.main()
