from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest import mock

from orchestrator.audio_device_manager import AudioDeviceManager


class FakeSoundDevice:
    class Defaults:
        device = (4, 5)

    def __init__(self) -> None:
        self.default = self.Defaults()
        self.queries: list[tuple[object, str]] = []
        self.checks: list[tuple[str, dict[str, object]]] = []
        self.devices: dict[object, dict[str, object]] = {
            4: {
                "name": "OS Default Microphone",
                "default_samplerate": 48000,
                "max_input_channels": 2,
            },
            5: {
                "name": "OS Default Headphones",
                "default_samplerate": 48000,
                "max_output_channels": 2,
            },
            "USB microphone": {
                "name": "USB microphone",
                "default_samplerate": 44100,
                "max_input_channels": 1,
            },
            9: {
                "name": "USB headphones",
                "default_samplerate": 44100,
                "max_output_channels": 2,
            },
        }

    def query_devices(self, *, device: object, kind: str) -> dict[str, object]:
        self.queries.append((device, kind))
        try:
            return self.devices[device]
        except KeyError as exc:
            raise ValueError("unknown device") from exc

    def check_input_settings(self, **kwargs: object) -> None:
        self.checks.append(("input", kwargs))

    def check_output_settings(self, **kwargs: object) -> None:
        self.checks.append(("output", kwargs))


class AudioDeviceManagerTests(unittest.TestCase):
    def test_constructor_does_not_import_sounddevice(self) -> None:
        script = (
            "import sys; "
            "sys.modules['sounddevice'] = None; "
            "from orchestrator.audio_device_manager import AudioDeviceManager; "
            "AudioDeviceManager(); "
            "print('ok')"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_unset_devices_resolve_and_validate_os_defaults(self) -> None:
        fake = FakeSoundDevice()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "orchestrator.audio_device_manager._sounddevice",
                return_value=fake,
            ),
        ):
            manager = AudioDeviceManager()
            input_params = manager.get_input_params()
            output_params = manager.get_output_params()

        self.assertEqual(input_params["device"], 4)
        self.assertEqual(input_params["selection_source"], "system_default")
        self.assertEqual(output_params["device"], 5)
        self.assertEqual(output_params["selection_source"], "system_default")
        self.assertEqual(fake.queries, [(4, "input"), (5, "output")])
        self.assertEqual(
            fake.checks,
            [
                (
                    "input",
                    {
                        "device": 4,
                        "channels": 1,
                        "dtype": "float32",
                        "samplerate": 48000,
                    },
                ),
                (
                    "output",
                    {
                        "device": 5,
                        "channels": 2,
                        "dtype": "int16",
                        "samplerate": 48000,
                    },
                ),
            ],
        )

    def test_explicit_devices_remain_authoritative(self) -> None:
        fake = FakeSoundDevice()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "ORCH_INPUT_DEVICE": "USB microphone",
                    "ORCH_OUTPUT_DEVICE": "9",
                },
                clear=True,
            ),
            mock.patch(
                "orchestrator.audio_device_manager._sounddevice",
                return_value=fake,
            ),
        ):
            manager = AudioDeviceManager()
            input_params = manager.get_input_params()
            output_params = manager.get_output_params()

        self.assertEqual(input_params["device"], "USB microphone")
        self.assertEqual(input_params["selection_source"], "configured")
        self.assertEqual(output_params["device"], 9)
        self.assertEqual(output_params["selection_source"], "configured")

    def test_invalid_explicit_device_does_not_silently_fall_back(self) -> None:
        fake = FakeSoundDevice()
        with (
            mock.patch.dict(
                os.environ,
                {"ORCH_INPUT_DEVICE": "missing microphone"},
                clear=True,
            ),
            mock.patch(
                "orchestrator.audio_device_manager._sounddevice",
                return_value=fake,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "configured input audio device.*unavailable",
            ):
                AudioDeviceManager().get_input_params()

    def test_missing_system_default_fails_with_direction(self) -> None:
        fake = FakeSoundDevice()
        fake.default.device = (-1, 5)
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "orchestrator.audio_device_manager._sounddevice",
                return_value=fake,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "No system-default input audio device",
            ):
                AudioDeviceManager().get_input_params()

    def test_selected_device_must_support_configured_channels(self) -> None:
        fake = FakeSoundDevice()
        fake.devices[4]["max_input_channels"] = 0
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "orchestrator.audio_device_manager._sounddevice",
                return_value=fake,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "provides 0 channel.*but 1 are required",
            ):
                AudioDeviceManager().get_input_params()


if __name__ == "__main__":
    unittest.main()
