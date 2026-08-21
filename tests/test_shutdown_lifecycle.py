from __future__ import annotations

import asyncio
import types
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.shutdown_lifecycle import shutdown_voice_assistant


class _Closable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _HttpSession(_Closable):
    pass


class ShutdownLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_cancels_owned_tasks_clears_pending_input_and_closes_resources(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant.active_synthesis_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant.active_asr_task = asyncio.create_task(asyncio.Event().wait())
        assistant.active_turn_task = asyncio.create_task(asyncio.Event().wait())
        assistant.active_reflex_task = asyncio.create_task(asyncio.Event().wait())
        assistant.concurrent_protective_reflex_tasks = {
            asyncio.create_task(asyncio.Event().wait())
        }
        assistant._pending_turn_after_reflex.append(("later", "sid-later"))
        assistant._pending_vad_audio = b"partial"
        assistant.output_abort_tasks = {
            asyncio.create_task(asyncio.Event().wait())
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
        assistant.playback_task = asyncio.create_task(asyncio.Event().wait())
        duck_timeout_task = asyncio.create_task(asyncio.Event().wait())
        assistant._playback_state().output_duck_timeout_task = duck_timeout_task
        assistant.asr_ws = _Closable()
        assistant.http_session = _HttpSession()
        audio_closed: list[bool] = []
        assistant.audio_mgr = types.SimpleNamespace(
            close=lambda: audio_closed.append(True)
        )
        assistant.sessions = None
        output_closed: list[bool] = []

        owned_tasks = {
            *assistant.active_synthesis_tasks,
            assistant.active_asr_task,
            assistant.active_turn_task,
            assistant.active_reflex_task,
            *assistant.concurrent_protective_reflex_tasks,
            *assistant.output_abort_tasks,
            *assistant.observability_tasks,
            assistant.session_idle_sweeper_task,
            assistant.audio_device_monitor_task,
            assistant.playback_task,
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
        self.assertEqual(list(assistant._pending_turn_after_reflex), [])
        self.assertIsNone(assistant._pending_vad_audio)
        self.assertEqual(output_closed, [True])
        self.assertTrue(assistant.asr_ws.closed)
        self.assertTrue(assistant.http_session.closed)
        self.assertEqual(audio_closed, [True])

    async def test_final_telemetry_failure_does_not_block_session_finalization(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
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
        assistant.playback_task = None
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


if __name__ == "__main__":
    unittest.main()
