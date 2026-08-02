from __future__ import annotations

import asyncio
import unittest

from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle


class InputTurnLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.block = asyncio.Event()

    async def _worker(self) -> None:
        await self.block.wait()

    async def test_scoped_cancellation_targets_foreground_ordinary_turn(self) -> None:
        lifecycle = InputTurnLifecycle()
        first = asyncio.create_task(self._worker())
        second = asyncio.create_task(self._worker())
        lifecycle.register_turn(first, "sid-1")
        lifecycle.register_turn(second, "sid-2")

        cancelled = lifecycle.request_turn_cancellation(
            excluding=None,
            cancel_all=False,
            reason="semantic_interrupt",
        )
        self.assertEqual(cancelled, ("sid-2",))
        self.assertFalse(first.cancelled())
        await asyncio.sleep(0)
        self.assertTrue(second.cancelled())
        first.cancel()
        await asyncio.gather(first, second, return_exceptions=True)

    async def test_protective_reflex_is_never_cancelled_as_ordinary_work(self) -> None:
        lifecycle = InputTurnLifecycle()
        ordinary = asyncio.create_task(self._worker())
        reflex = asyncio.create_task(self._worker())
        lifecycle.register_turn(ordinary, "ordinary")
        lifecycle.register_turn(reflex, "reflex", protective_reflex=True)

        cancelled = lifecycle.request_turn_cancellation(
            excluding=None,
            cancel_all=True,
            reason="global_stop",
        )
        self.assertEqual(cancelled, ("ordinary",))
        await asyncio.sleep(0)
        self.assertFalse(reflex.cancelled())
        reflex.cancel()
        await asyncio.gather(ordinary, reflex, return_exceptions=True)

    async def test_pending_vad_queue_keeps_latest_audio(self) -> None:
        lifecycle = InputTurnLifecycle()
        self.assertFalse(lifecycle.queue_pending_vad_audio(b"first"))
        self.assertTrue(lifecycle.queue_pending_vad_audio(b"second"))
        self.assertEqual(lifecycle.take_pending_vad_audio(), b"second")
        self.assertIsNone(lifecycle.take_pending_vad_audio())

    async def test_unregister_returns_reason_and_next_foreground(self) -> None:
        lifecycle = InputTurnLifecycle()
        first = asyncio.create_task(self._worker())
        second = asyncio.create_task(self._worker())
        lifecycle.register_turn(first, "sid-1")
        lifecycle.register_turn(second, "sid-2")
        lifecycle.turn_cancellation_reasons[second] = "superseded"

        reason, primary, concurrent = lifecycle.unregister_turn(second)
        self.assertEqual(reason, "superseded")
        self.assertFalse(primary)
        self.assertFalse(concurrent)
        self.assertIs(lifecycle.active_turn_task, first)
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
