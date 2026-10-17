from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import patch

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.shutdown_lifecycle import shutdown_voice_assistant
from tests.voice_assistant_test_support import bare_voice_assistant


class _Closable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _HttpSession(_Closable):
    pass


class ShutdownLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_cancels_owned_tasks_clears_pending_input_and_closes_resources(self) -> None:
        assistant = bare_voice_assistant()
        assistant.playback_delivery.playback_start_waiters = {}
        assistant.playback_delivery.active_synthesis_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant.input_turn_lifecycle.active_asr_task = asyncio.create_task(asyncio.Event().wait())
        assistant.input_turn_lifecycle.active_turn_task = asyncio.create_task(asyncio.Event().wait())
        assistant.input_turn_lifecycle.active_reflex_task = asyncio.create_task(asyncio.Event().wait())
        assistant.input_turn_lifecycle.concurrent_protective_reflex_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant.input_turn_lifecycle.pending_turn_after_reflex.append(("later", "sid-later"))
        assistant.input_turn_lifecycle.pending_vad_audio = b"partial"
        assistant.output_abort_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant.active_cognitive_runtime_tasks = {
            asyncio.create_task(asyncio.Event().wait()): "detached-state-reentry"
        }
        assistant.observability_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant.session_idle_sweeper_task = asyncio.create_task(
            asyncio.Event().wait()
        )
        assistant.audio_device_monitor_task = asyncio.create_task(
            asyncio.Event().wait()
        )
        assistant.playback_delivery.playback_task = asyncio.create_task(asyncio.Event().wait())
        duck_timeout_task = asyncio.create_task(asyncio.Event().wait())
        assistant.playback_delivery.output_duck_timeout_task = duck_timeout_task
        assistant.asr_ws = _Closable()
        assistant.http_session = _HttpSession()
        audio_closed: list[bool] = []
        assistant.audio_mgr = types.SimpleNamespace(
            close=lambda: audio_closed.append(True)
        )
        assistant.sessions = None
        output_closed: list[bool] = []

        owned_tasks = {
            *assistant.playback_delivery.active_synthesis_tasks,
            assistant.input_turn_lifecycle.active_asr_task,
            assistant.input_turn_lifecycle.active_turn_task,
            assistant.input_turn_lifecycle.active_reflex_task,
            *assistant.input_turn_lifecycle.concurrent_protective_reflex_tasks,
            *assistant.output_abort_tasks,
            *assistant.active_cognitive_runtime_tasks,
            *assistant.observability_tasks,
            assistant.session_idle_sweeper_task,
            assistant.audio_device_monitor_task,
            assistant.playback_delivery.playback_task,
            duck_timeout_task,
        }

        async def close_output_stream() -> None:
            output_closed.append(True)

        await shutdown_voice_assistant(
            assistant,
            close_output_stream=close_output_stream,
        )
        await asyncio.sleep(0)

        self.assertTrue(all(task.cancelled() for task in owned_tasks))
        self.assertEqual(list(assistant.input_turn_lifecycle.pending_turn_after_reflex), [])
        self.assertIsNone(assistant.input_turn_lifecycle.pending_vad_audio)
        self.assertEqual(output_closed, [True])
        self.assertTrue(assistant.asr_ws.closed)
        self.assertTrue(assistant.http_session.closed)
        self.assertEqual(audio_closed, [True])

    async def test_final_telemetry_failure_does_not_block_session_finalization(self) -> None:
        assistant = bare_voice_assistant()
        assistant.playback_delivery.playback_start_waiters = {}
        assistant.sessions = types.SimpleNamespace(
            finalized=[],
            finalize_active_sessions=lambda *, reason: assistant.sessions.finalized.append(reason),
        )

        class FailingSampler:
            async def sample(self, *, reason: str) -> None:
                self.assertEqual(reason, "session_finish")
                raise RuntimeError("telemetry unavailable")

            def __init__(self, test_case: ShutdownLifecycleTests) -> None:
                self.assertEqual = test_case.assertEqual

        assistant.accelerator_sampler = FailingSampler(self)
        assistant.audio_device_monitor_task = None
        assistant.output_abort_tasks = set()
        assistant.observability_tasks = set()
        assistant.session_idle_sweeper_task = None
        assistant.playback_delivery.playback_task = None
        assistant.asr_ws = None
        assistant.http_session = None
        assistant.audio_mgr = types.SimpleNamespace(close=lambda: None)

        async def close_output_stream() -> None:
            return None

        await shutdown_voice_assistant(
            assistant,
            close_output_stream=close_output_stream,
        )

        self.assertEqual(
            assistant.sessions.finalized,
            ["orchestrator_cleanup"],
        )

    async def test_playback_worker_starts_one_session_idle_sweeper_that_shutdown_cancels(self) -> None:
        assistant = bare_voice_assistant()
        sweeper_starts: list[asyncio.Event] = []

        class _InputSessionRuntime:
            async def _session_idle_sweeper(self) -> None:
                stop = asyncio.Event()
                sweeper_starts.append(stop)
                await stop.wait()

        class _PlaybackTransport:
            async def playback_worker(self) -> None:
                await asyncio.Event().wait()

        with patch(
            "orchestrator.orchestrator.input_session_runtime_for",
            return_value=_InputSessionRuntime(),
        ), patch(
            "orchestrator.orchestrator.playback_transport_for",
            return_value=_PlaybackTransport(),
        ):
            for _ in range(5):
                assistant.ensure_playback_worker()
                await asyncio.sleep(0)
            sweeper = assistant.session_idle_sweeper_task
            self.assertEqual(len(sweeper_starts), 1)

            sweeper_starts[0].set()
            await sweeper
            assistant.ensure_playback_worker()
            await asyncio.sleep(0)
            self.assertEqual(len(sweeper_starts), 2)
            self.assertIsNot(assistant.session_idle_sweeper_task, sweeper)

        sweepers = [
            task
            for task in asyncio.all_tasks()
            if task.get_coro().__qualname__.endswith("_session_idle_sweeper")
        ]
        self.assertEqual(sweepers, [assistant.session_idle_sweeper_task])

        assistant.playback_delivery.playback_start_waiters = {}
        assistant.sessions = types.SimpleNamespace(finalize_active_sessions=lambda *, reason: None)
        assistant.accelerator_sampler = None
        assistant.audio_device_monitor_task = None
        assistant.output_abort_tasks = set()
        assistant.observability_tasks = set()
        assistant.asr_ws = None
        assistant.http_session = None
        assistant.audio_mgr = types.SimpleNamespace(close=lambda: None)

        async def close_output_stream() -> None:
            return None

        await shutdown_voice_assistant(assistant, close_output_stream=close_output_stream)
        await asyncio.gather(*sweepers, return_exceptions=True)
        self.assertTrue(all(task.cancelled() for task in sweepers))


if __name__ == "__main__":
    unittest.main()
