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

    def test_speech_event_identity_is_structured_not_wording_based(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        first = lifecycle.register_turn_speech_event(
            session_id="sid",
            generation=2,
            orders=[4],
            normalized_text="I will check that.",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="weather_query",
            commitment="checking_only",
        )
        second = lifecycle.register_turn_speech_event(
            session_id="sid",
            generation=2,
            orders=[4],
            normalized_text="Okay, let me look.",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="weather_query",
            commitment="checking_only",
        )

        assert first is not None and second is not None
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["text"], second["text"])

        other_goal = lifecycle.register_turn_speech_event(
            session_id="sid",
            generation=2,
            orders=[4],
            normalized_text="Okay, let me look.",
            stage="fast_first",
            purpose="acknowledge_and_check",
            route="tool",
            intent="weather_query",
            commitment="checking_only",
            source_goal_ids=["goal-other"],
        )
        assert other_goal is not None
        self.assertNotEqual(first["event_id"], other_goal["event_id"])

    async def test_delivered_event_preserves_goal_plan_and_claim_provenance(
        self,
    ) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        lifecycle.create_playback_start_waiter(
            generation=3,
            order=7,
            session_id="sid",
        )
        event = lifecycle.register_turn_speech_event(
            session_id="sid",
            turn_id="turn-weather",
            generation=3,
            orders=[7],
            normalized_text="I will check the weather.",
            stage="pre_action",
            purpose="acknowledge_and_check",
            commitment="evaluating",
            source_goal_ids=["goal-weather", "goal-weather"],
            canonical_plan_id="plan-weather",
            canonical_plan_fingerprint="fingerprint-weather",
            delivery_role="response",
            claims=["checking", "checking"],
            must_not_claim_completion=True,
        )
        assert event is not None
        self.assertEqual(event["status"], "scheduled")
        self.assertEqual(event["turn_id"], "turn-weather")
        self.assertEqual(event["source_goal_ids"], ["goal-weather"])
        self.assertEqual(event["claims"], ["checking"])

        lifecycle.resolve_playback_start_waiter(
            generation=3,
            order=7,
            session_id="sid",
            started=True,
            reason="playback_start",
        )
        delivered = lifecycle.delivered_turn_speech_events("sid")
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["canonical_plan_id"], "plan-weather")
        self.assertEqual(
            delivered[0]["canonical_plan_fingerprint"],
            "fingerprint-weather",
        )
        self.assertTrue(delivered[0]["must_not_claim_completion"])

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

    async def test_personal_voice_release_is_distinct_from_playback_start(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        lifecycle.create_playback_start_waiter(
            generation=6,
            order=2,
            session_id="sid",
        )
        lifecycle.create_playback_release_waiter(
            generation=6,
            order=2,
            session_id="sid",
        )
        lifecycle.resolve_playback_start_waiter(
            generation=6,
            order=2,
            session_id="sid",
            started=True,
            reason="playback_start",
        )

        self.assertFalse(
            await lifecycle.wait_for_playback_release(
                generation=6,
                order=2,
                session_id="sid",
                timeout_s=0.001,
            )
        )
        lifecycle.resolve_playback_release_waiter(
            generation=6,
            order=2,
            session_id="sid",
            reason="playback_order_terminal",
        )
        self.assertTrue(
            await lifecycle.wait_for_playback_release(
                generation=6,
                order=2,
                session_id="sid",
                timeout_s=0.001,
            )
        )

    async def test_generation_invalidation_releases_a_pending_output_duck(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle(playback_generation=7)
        lifecycle.begin_output_duck(
            generation=7,
            session_id="sid",
            started_ms=1.0,
        )
        waiter = asyncio.create_task(lifecycle.output_duck_released.wait())

        self.assertEqual(lifecycle.begin_new_generation(), 8)
        await asyncio.wait_for(waiter, timeout=0.1)

        self.assertIsNone(lifecycle.output_duck_generation)
        self.assertTrue(lifecycle.output_duck_released.is_set())
