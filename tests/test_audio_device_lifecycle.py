from __future__ import annotations

import asyncio
import types
import unittest
from unittest import mock

from orchestrator.runtime.audio_device_lifecycle import (
    refresh_system_default_audio_devices,
    set_input_device_params,
    set_output_device_params,
    uses_followed_system_default,
)


class AudioDeviceLifecyclePolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_parameter_projection_is_mechanical(self) -> None:
        host = types.SimpleNamespace()
        input_params = {
            "rate": 44100,
            "channels": 1,
            "device": 8,
            "blocksize": 1323,
            "latency": "low",
        }
        output_params = {
            "rate": 48000,
            "channels": 2,
            "device": 9,
            "latency": "low",
        }

        set_input_device_params(host, input_params)
        set_output_device_params(host, output_params)

        self.assertEqual(host.input_params, input_params)
        self.assertEqual(host.input_device, 8)
        self.assertEqual(host.input_rate, 44100)
        self.assertEqual(host.output_params, output_params)
        self.assertEqual(host.output_device, 9)
        self.assertEqual(host.output_channels, 2)

    def test_follow_policy_requires_device_mode_and_system_default(self) -> None:
        host = types.SimpleNamespace(
            audio_input_mode="stdin",
            audio_output_mode="device",
            audio_mgr=types.SimpleNamespace(
                follows_system_default=lambda kind: kind == "output"
            ),
        )

        self.assertFalse(uses_followed_system_default(host, "input"))
        self.assertTrue(uses_followed_system_default(host, "output"))

    async def test_refresh_failure_keeps_current_device_and_records_diagnostic(self) -> None:
        current = {"name": "Current", "device": 4}
        host = types.SimpleNamespace(
            audio_input_mode="device",
            audio_output_mode="discard",
            audio_mgr=types.SimpleNamespace(
                follows_system_default=lambda kind: kind == "input",
                get_input_params=mock.Mock(side_effect=RuntimeError("device unavailable")),
                get_output_params=mock.Mock(),
                device_params_changed=mock.Mock(),
            ),
            input_params=current,
            output_params={},
            _audio_device_refresh_lock=asyncio.Lock(),
            _input_device_change_event=asyncio.Event(),
            _pending_input_params=None,
            _pending_output_params=None,
            _audio_device_errors={},
        )

        queued = await refresh_system_default_audio_devices(host)

        self.assertEqual(queued, set())
        self.assertEqual(host.input_params, current)
        self.assertIsNone(host._pending_input_params)
        self.assertIn("RuntimeError", host._audio_device_errors["input"])
        host.audio_mgr.get_output_params.assert_not_called()


if __name__ == "__main__":
    unittest.main()
