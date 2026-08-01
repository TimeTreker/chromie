from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

from orchestrator.audio_device_manager import AudioDeviceManager

async def _to_thread_inline(function, /, *args, **kwargs):
    return function(*args, **kwargs)


def _new_voice_assistant():
    from orchestrator.orchestrator import VoiceAssistant

    return VoiceAssistant.__new__(VoiceAssistant)


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

    def test_default_following_and_device_identity_are_directional(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"ORCH_INPUT_DEVICE": "default", "ORCH_OUTPUT_DEVICE": "9"},
            clear=True,
        ):
            manager = AudioDeviceManager()

        self.assertTrue(manager.follows_system_default("input"))
        self.assertFalse(manager.follows_system_default("output"))
        self.assertFalse(
            manager.device_params_changed(
                {
                    "device": 4,
                    "name": "Microphone A",
                    "rate": 48000,
                    "channels": 1,
                },
                {
                    "device": 4,
                    "name": "Microphone A",
                    "rate": 48000,
                    "channels": 1,
                },
            )
        )
        self.assertTrue(
            manager.device_params_changed(
                {
                    "device": 4,
                    "name": "Microphone A",
                    "rate": 48000,
                    "channels": 1,
                },
                {
                    "device": 8,
                    "name": "USB microphone",
                    "rate": 48000,
                    "channels": 1,
                },
            )
        )

    def test_pipewire_default_metadata_updates_map_to_stream_direction(self) -> None:
        self.assertEqual(
            AudioDeviceManager.parse_pipewire_default_update(
                "update: id:0 key:'default.configured.audio.source' "
                "value:'{\"name\":\"usb-mic\"}' type:'Spa:String:JSON'"
            ),
            (
                "input",
                "default.configured.audio.source",
                '{"name":"usb-mic"}',
            ),
        )
        self.assertEqual(
            AudioDeviceManager.parse_pipewire_default_update(
                "update: id:0 key:'default.audio.sink' "
                "value:'{\"name\":\"usb-headphones\"}' type:'Spa:String:JSON'"
            ),
            ("output", "default.audio.sink", '{"name":"usb-headphones"}'),
        )
        self.assertIsNone(
            AudioDeviceManager.parse_pipewire_default_update(
                "update: id:0 key:'clock.force-rate' value:'0'"
            )
        )


class _FakeRuntimeAudioManager:
    def __init__(
        self,
        *,
        input_params: dict[str, object],
        output_params: dict[str, object],
    ) -> None:
        self.input_params = input_params
        self.output_params = output_params

    def follows_system_default(self, kind: str) -> bool:
        return kind in {"input", "output"}

    def get_input_params(self) -> dict[str, object]:
        return dict(self.input_params)

    def get_output_params(self) -> dict[str, object]:
        return dict(self.output_params)

    @staticmethod
    def device_params_changed(
        current: dict[str, object],
        candidate: dict[str, object],
    ) -> bool:
        return AudioDeviceManager.device_params_changed(current, candidate)


class _FakeVAD:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1


class _FakeOutputStream:
    def __init__(self) -> None:
        self.stopped = False
        self.closed = False

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class _FakePipeWireStdout:
    def __init__(self) -> None:
        self._lines = [
            b'Found "default" metadata 41\n',
            (
                b"update: id:0 key:'default.audio.source' "
                b"value:'{\"name\":\"built-in-mic\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
            (
                b"update: id:0 key:'default.audio.sink' "
                b"value:'{\"name\":\"built-in-output\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
        ]
        self._initial_gap_seen = False
        self._updates = [
            (
                b"update: id:0 key:'default.audio.source' "
                b"value:'{\"name\":\"usb-mic\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
            (
                b"update: id:0 key:'default.audio.sink' "
                b"value:'{\"name\":\"usb-headphones\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
        ]

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        if not self._initial_gap_seen:
            self._initial_gap_seen = True
            await asyncio.sleep(10)
        if self._updates:
            return self._updates.pop(0)
        await asyncio.sleep(10)
        return b""


class _FakePipeWireProcess:
    def __init__(self) -> None:
        self.stdout = _FakePipeWireStdout()
        self.returncode = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int:
        return 0


class _FakeLatePipeWireStdout:
    def __init__(self) -> None:
        self._lines = [
            b'Found "default" metadata 41\n',
            (
                b"update: id:0 key:'default.audio.source' "
                b"value:'{\"name\":\"built-in-mic\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
        ]
        self._initial_gap_seen = False
        self._updates = [
            (
                b"update: id:0 key:'default.audio.sink' "
                b"value:'{\"name\":\"built-in-output\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
            (
                b"update: id:0 key:'default.audio.sink' "
                b"value:'{\"name\":\"usb-headphones\"}' "
                b"type:'Spa:String:JSON'\n"
            ),
        ]

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        if not self._initial_gap_seen:
            self._initial_gap_seen = True
            await asyncio.sleep(10)
        if self._updates:
            return self._updates.pop(0)
        await asyncio.sleep(10)
        return b""


class _FakeLatePipeWireProcess(_FakePipeWireProcess):
    def __init__(self) -> None:
        super().__init__()
        self.stdout = _FakeLatePipeWireStdout()


class OrchestratorAudioDeviceFollowTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _params(
        *,
        name: str,
        device: int,
        rate: int = 48000,
        channels: int = 1,
    ) -> dict[str, object]:
        return {
            "name": name,
            "device": device,
            "selection_source": "system_default",
            "rate": rate,
            "channels": channels,
            "blocksize": 1440,
            "block_ms": 30,
            "latency": "low",
        }

    async def test_runtime_refresh_queues_changed_os_defaults(self) -> None:
        old_input = self._params(name="Built-in microphone", device=4)
        old_output = self._params(
            name="Built-in speakers",
            device=5,
            channels=2,
        )
        new_input = self._params(name="USB microphone", device=8)
        new_output = self._params(
            name="USB headphones",
            device=9,
            channels=2,
        )
        assistant = _new_voice_assistant()
        assistant.audio_input_mode = "device"
        assistant.audio_output_mode = "device"
        assistant.audio_mgr = _FakeRuntimeAudioManager(
            input_params=new_input,
            output_params=new_output,
        )
        assistant.input_params = old_input
        assistant.output_params = old_output
        assistant._audio_device_refresh_lock = asyncio.Lock()
        assistant._input_device_change_event = asyncio.Event()
        assistant._pending_input_params = None
        assistant._pending_output_params = None
        assistant._audio_device_errors = {}

        with mock.patch(
            "orchestrator.orchestrator.asyncio.to_thread",
            new=_to_thread_inline,
        ):
            await assistant._refresh_system_default_audio_devices()

        self.assertTrue(assistant._input_device_change_event.is_set())
        self.assertEqual(assistant._pending_input_params, new_input)
        self.assertEqual(assistant._pending_output_params, new_output)
        self.assertEqual(assistant.input_params, old_input)
        self.assertEqual(assistant.output_params, old_output)

    async def test_pipewire_monitor_ignores_baseline_then_yields_changes(self) -> None:
        process = _FakePipeWireProcess()

        async def create_process(*args, **kwargs):
            return process

        manager = AudioDeviceManager()
        with mock.patch(
            "orchestrator.audio_device_manager.asyncio.create_subprocess_exec",
            new=create_process,
        ):
            changes = manager.watch_system_default_changes()
            self.assertEqual(await anext(changes), "input")
            self.assertEqual(await anext(changes), "output")
            await changes.aclose()

        self.assertTrue(process.terminated)

    async def test_pipewire_monitor_treats_late_first_key_as_baseline(self) -> None:
        process = _FakeLatePipeWireProcess()

        async def create_process(*args, **kwargs):
            return process

        manager = AudioDeviceManager()
        with mock.patch(
            "orchestrator.audio_device_manager.asyncio.create_subprocess_exec",
            new=create_process,
        ):
            changes = manager.watch_system_default_changes()
            self.assertEqual(await anext(changes), "output")
            await changes.aclose()

        self.assertTrue(process.terminated)

    async def test_runtime_refresh_never_reselects_pinned_devices(self) -> None:
        assistant = _new_voice_assistant()
        assistant.audio_input_mode = "stdin"
        assistant.audio_output_mode = "device"
        assistant.audio_mgr = types.SimpleNamespace(
            follows_system_default=lambda kind: False,
            get_input_params=mock.Mock(side_effect=AssertionError("input queried")),
            get_output_params=mock.Mock(side_effect=AssertionError("output queried")),
        )
        assistant.input_params = {}
        assistant.output_params = self._params(
            name="Pinned headphones",
            device=9,
            channels=2,
        )
        assistant._audio_device_refresh_lock = asyncio.Lock()
        assistant._input_device_change_event = asyncio.Event()
        assistant._pending_input_params = None
        assistant._pending_output_params = None
        assistant._audio_device_errors = {}

        queued = await assistant._refresh_system_default_audio_devices(
            force_kinds={"input", "output"},
        )

        self.assertEqual(queued, set())
        self.assertIsNone(assistant._pending_input_params)
        self.assertIsNone(assistant._pending_output_params)
        assistant.audio_mgr.get_input_params.assert_not_called()
        assistant.audio_mgr.get_output_params.assert_not_called()

    async def test_input_switch_discards_cross_device_partial_audio(self) -> None:
        new_input = self._params(name="USB microphone", device=8, rate=44100)
        assistant = _new_voice_assistant()
        assistant._audio_device_refresh_lock = asyncio.Lock()
        assistant._input_device_change_event = asyncio.Event()
        assistant._input_device_change_event.set()
        assistant._pending_input_params = new_input
        assistant.mic_queue = asyncio.Queue()
        assistant.mic_queue.put_nowait(object())
        assistant.vad = _FakeVAD()
        assistant._vad_leftover = b"partial"
        assistant._vad_segment_started_during_playback = True
        assistant._vad_segment_playback_generation = 7

        changed = await assistant._apply_pending_input_device_change()

        self.assertTrue(changed)
        self.assertEqual(assistant.input_device, 8)
        self.assertEqual(assistant.input_rate, 44100)
        self.assertTrue(assistant.mic_queue.empty())
        self.assertEqual(assistant.vad.reset_count, 1)
        self.assertEqual(assistant._vad_leftover, b"")
        self.assertFalse(assistant._vad_segment_started_during_playback)
        self.assertIsNone(assistant._vad_segment_playback_generation)

    async def test_output_switch_closes_old_stream_before_next_playback(self) -> None:
        new_output = self._params(
            name="USB headphones",
            device=9,
            channels=2,
        )
        stream = _FakeOutputStream()
        assistant = _new_voice_assistant()
        assistant._audio_device_refresh_lock = asyncio.Lock()
        assistant.output_write_lock = asyncio.Lock()
        assistant.output_stream_lock = asyncio.Lock()
        assistant._pending_output_params = new_output
        assistant.output_stream = stream

        with mock.patch(
            "orchestrator.orchestrator.asyncio.to_thread",
            new=_to_thread_inline,
        ):
            changed = await assistant._apply_pending_output_device_change()

        self.assertTrue(changed)
        self.assertTrue(stream.stopped)
        self.assertTrue(stream.closed)
        self.assertIsNone(assistant.output_stream)
        self.assertEqual(assistant.output_device, 9)
        self.assertEqual(assistant.output_params, new_output)


if __name__ == "__main__":
    unittest.main()
