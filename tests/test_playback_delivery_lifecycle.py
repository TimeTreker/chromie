from __future__ import annotations

import asyncio
import unittest

from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle


class PlaybackDeliveryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_is_visible_only_after_playback_starts(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        lifecycle.create_playback_start_waiter(
            generation=2,
            order=4,
            session_id="sid",
        )
        lifecycle.register_turn_speech_event(
            session_id="sid",
            generation=2,
            orders=[4],
            normalized_text="好呀，我去看看。",
            stage="fast_first",
            purpose="acknowledge_pending_lookup",
        )
        self.assertEqual(lifecycle.delivered_turn_speech_events("sid"), [])

        self.assertTrue(
            lifecycle.resolve_playback_start_waiter(
                generation=2,
                order=4,
                session_id="sid",
                started=True,
                reason="playback_start",
            )
        )
        delivered = lifecycle.delivered_turn_speech_events("sid")
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["status"], "playback_started")

    async def test_timeout_does_not_cancel_late_barrier_future(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        waiter = lifecycle.create_playback_start_waiter(
            generation=1,
            order=0,
            session_id="sid",
        )
        started = await lifecycle.wait_for_playback_start(
            generation=1,
            order=0,
            session_id="sid",
            timeout_s=0.001,
        )
        self.assertFalse(started)
        self.assertFalse(waiter.cancelled())
        self.assertFalse(waiter.done())

    async def test_cancelled_order_is_typed_and_resolves_barrier(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        lifecycle.create_playback_start_waiter(
            generation=5,
            order=8,
            session_id="sid",
        )
        self.assertTrue(
            lifecycle.cancel_order_before_start(
                generation=5,
                order=8,
                session_id="sid",
                reason="superseded",
            )
        )
        self.assertIn((5, 8, "sid"), lifecycle.cancelled_playback_orders)

    def test_generation_reset_clears_order_state(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle(
            next_playback_order=3,
            synthesis_order=4,
            playback_generation=7,
        )
        lifecycle.pending_audio[3] = (7, b"pcm", 24000, "sid", None)
        lifecycle.cancelled_playback_orders.add((7, 2, "sid"))

        self.assertEqual(lifecycle.begin_new_generation(), 8)
        self.assertEqual(lifecycle.next_playback_order, 0)
        self.assertEqual(lifecycle.synthesis_order, 0)
        self.assertEqual(lifecycle.pending_audio, {})
        self.assertEqual(lifecycle.cancelled_playback_orders, set())
