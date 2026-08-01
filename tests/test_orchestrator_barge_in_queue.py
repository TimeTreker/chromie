from __future__ import annotations

import asyncio
import sys
import types
import unittest
from types import MethodType
from typing import Any

for module_name in ("aiohttp", "numpy", "sounddevice", "websockets"):
    if module_name not in sys.modules:
        sys.modules[module_name] = types.ModuleType(module_name)
if "scipy" not in sys.modules:
    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("signal")  # type: ignore[attr-defined]
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = scipy.signal  # type: ignore[attr-defined]

from orchestrator.orchestrator import VoiceAssistant


class OrchestratorBargeInQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_asr_keeps_latest_utterance_instead_of_dropping_it(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        blocker = asyncio.Event()
        active = asyncio.create_task(blocker.wait())
        assistant.active_asr_task = active
        assistant._pending_vad_audio = None

        assistant._queue_vad_utterance(b"first")
        assistant._queue_vad_utterance(b"latest")

        self.assertEqual(assistant._pending_vad_audio, b"latest")
        self.assertIs(assistant.active_asr_task, active)

        active.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await active

    async def test_completed_asr_immediately_starts_queued_latest_utterance(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._pending_vad_audio = b"queued"
        seen: list[bytes] = []

        def queue(self: VoiceAssistant, audio: bytes) -> None:
            seen.append(audio)

        assistant._queue_vad_utterance = MethodType(queue, assistant)

        async def done() -> None:
            return None

        task = asyncio.create_task(done())
        await task
        assistant.active_asr_task = task

        assistant._on_asr_task_done(task)

        self.assertIsNone(assistant.active_asr_task)
        self.assertIsNone(assistant._pending_vad_audio)
        self.assertEqual(seen, [b"queued"])

    async def test_new_routed_turn_preserves_prior_turn_and_runs_both_texts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        release_first = asyncio.Event()
        first_started = asyncio.Event()
        assistant.active_turn_task = None
        assistant.active_turn_tasks = {}
        assistant.active_reflex_task = None
        assistant.concurrent_protective_reflex_tasks = set()
        seen: list[tuple[str, str]] = []

        async def handle(
            self: VoiceAssistant,
            text: str,
            session_id: str,
        ) -> None:
            seen.append((text, session_id))
            if session_id == "sid-first":
                first_started.set()
                await release_first.wait()

        assistant.sessions = types.SimpleNamespace(
            state={"sid-first": {}, "sid-latest": {}}
        )
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )
        assistant.maybe_session_done = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )
        assistant.handle_routed_text = MethodType(handle, assistant)

        assistant._launch_routed_turn("first request", "sid-first")
        first = assistant.active_turn_task
        assert first is not None
        await first_started.wait()
        assistant._launch_routed_turn("latest request", "sid-latest")
        latest = assistant.active_turn_task
        assert latest is not None
        await latest
        await asyncio.sleep(0)

        self.assertFalse(first.cancelled())
        self.assertEqual(
            seen,
            [
                ("first request", "sid-first"),
                ("latest request", "sid-latest"),
            ],
        )
        release_first.set()
        await first
        await asyncio.sleep(0)
        self.assertEqual(assistant.active_turn_tasks, {})
        self.assertIsNone(assistant.active_turn_task)

    async def test_scoped_control_cancels_only_foreground_routed_turn(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        first = asyncio.create_task(asyncio.Event().wait())
        foreground = asyncio.create_task(asyncio.Event().wait())
        assistant.active_turn_task = foreground
        assistant.active_turn_tasks = {
            first: "sid-first",
            foreground: "sid-foreground",
        }
        assistant.active_reflex_task = None
        assistant.concurrent_protective_reflex_tasks = set()
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        cancelled = assistant._cancel_active_routed_turns(
            excluding=None,
            cancel_all=False,
            reason="core_authorized_test",
        )
        await asyncio.sleep(0)

        self.assertEqual(cancelled, ("sid-foreground",))
        self.assertFalse(first.cancelled())
        self.assertTrue(foreground.cancelled())

        first.cancel()
        await asyncio.gather(first, foreground, return_exceptions=True)

    async def test_core_authorized_interrupt_targets_foreground_interaction(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        directives: list[Any] = []

        class _Runtime:
            async def cancel_scope(self, directive: Any) -> None:
                directives.append(directive)

        async def interrupt_output(
            self: VoiceAssistant,
            new_session_id: str | None = None,
            **kwargs: Any,
        ) -> None:
            del self, new_session_id, kwargs

        assistant.interrupt_output = MethodType(interrupt_output, assistant)
        assistant.interaction_runtime = _Runtime()
        assistant.active_interaction_id = "interaction-foreground"
        assistant.active_interaction_task = asyncio.create_task(
            asyncio.Event().wait()
        )
        assistant.playback_generation = 0
        assistant.session_log = MethodType(
            lambda self, *args, **kwargs: None,
            assistant,
        )

        task = assistant.active_interaction_task
        await assistant.interrupt("sid-core-interrupt")
        await asyncio.sleep(0)

        self.assertEqual(len(directives), 1)
        self.assertEqual(directives[0].requested_scope, "current_interaction")
        self.assertEqual(
            directives[0].foreground_interaction_id,
            "interaction-foreground",
        )
        self.assertTrue(task.cancelled())

    async def test_cleanup_cancels_asr_and_turn_tasks_and_clears_pending_audio(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.playback_start_waiters = {}
        assistant.active_llm_task = None
        assistant.active_synthesis_tasks = set()
        assistant.active_asr_task = asyncio.create_task(asyncio.Event().wait())
        assistant.active_turn_task = asyncio.create_task(asyncio.Event().wait())
        assistant._pending_vad_audio = b"queued"
        assistant.playback_task = None
        assistant.asr_ws = None
        assistant.http_session = None

        async def close_output_stream(self: VoiceAssistant) -> None:
            return None

        assistant.close_output_stream = MethodType(close_output_stream, assistant)
        assistant.audio_mgr = types.SimpleNamespace(close=lambda: None)

        asr_task = assistant.active_asr_task
        turn_task = assistant.active_turn_task
        await assistant.cleanup()
        await asyncio.sleep(0)

        self.assertTrue(asr_task.cancelled())
        self.assertTrue(turn_task.cancelled())
        self.assertIsNone(assistant._pending_vad_audio)


if __name__ == "__main__":
    unittest.main()
