from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle
from orchestrator.runtime.playback_transport import PlaybackTransport, transport_for

ROOT = Path(__file__).resolve().parents[1]


class PlaybackTransportExtractionTests(unittest.TestCase):
    def test_transport_is_owned_by_playback_lifecycle(self) -> None:
        lifecycle = PlaybackDeliveryLifecycle()
        host = SimpleNamespace(_playback_state=lambda: lifecycle)

        first = transport_for(host)
        second = transport_for(host)

        self.assertIsInstance(first, PlaybackTransport)
        self.assertIs(first, second)
        self.assertIs(lifecycle.transport, first)

    def test_provider_and_output_implementation_left_composition_root(self) -> None:
        orchestrator_source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        transport_source = (
            ROOT / "orchestrator" / "runtime" / "playback_transport.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("websockets.connect(self.tts_url", orchestrator_source)
        self.assertNotIn("sd.OutputStream(", orchestrator_source)
        self.assertIn("websockets.connect(host.tts_url", transport_source)
        self.assertIn("sd.OutputStream(", transport_source)

    def test_playback_transport_is_the_only_transport_owner(self) -> None:
        from orchestrator.orchestrator import VoiceAssistant

        for name in (
            "ensure_output_stream",
            "abort_output_stream",
            "play_audio",
            "enqueue_playback_skip",
            "playback_worker",
            "play_one_order",
            "synthesize_one",
            "close_output_stream",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(VoiceAssistant, name),
                    f"{name} must stay on PlaybackTransport instead of regrowing "
                    "a compatibility-only VoiceAssistant facade",
                )
                self.assertTrue(hasattr(PlaybackTransport, name))

        transport_source = (
            ROOT / "orchestrator" / "runtime" / "playback_transport.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "host.ensure_output_stream(",
            "host.abort_output_stream(",
            "host.play_audio(",
            "host.enqueue_playback_skip(",
            "host.play_one_order(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, transport_source)

        orchestrator_source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("def trace_session_async", orchestrator_source)
        self.assertIn(
            "playback_transport_for(self).synthesize_one",
            orchestrator_source,
        )
        self.assertIn(
            "playback_transport_for(self).playback_worker",
            orchestrator_source,
        )



if __name__ == "__main__":
    unittest.main()


class PlaybackCompletionEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_transport_completion_or_interrupt_qualifies_delivery(self):
        import asyncio
        for outcome in ("completed", "failed", "interrupted"):
            with self.subTest(outcome=outcome):
                from contextlib import nullcontext
                lifecycle = PlaybackDeliveryLifecycle()
                lifecycle.create_playback_start_waiter(generation=1, order=0, session_id="sid")
                event = lifecycle.register_turn_speech_event(session_id="sid", generation=1, orders=[0],
                    normalized_text="Hello.", stage="result", purpose="answer", communicative_activity_ids=["speech-a"])
                def resolve(generation, order, sid, **kwargs):
                    return lifecycle.resolve_playback_start_waiter(generation=generation, order=order, session_id=sid, **kwargs)
                host = SimpleNamespace(_playback_state=lambda: lifecycle, playback_start_key=lifecycle.key,
                    cancelled_playback_orders=set(), is_stale_playback=lambda *args: False,
                    sessions=SimpleNamespace(state={"sid": {}}, trace_mark=lambda *args, **kwargs: None, trace_context=lambda *args: nullcontext()),
                    output_rate=16000, session_log=lambda *args, **kwargs: None,
                    resolve_playback_start_waiter=resolve, save_audio=lambda *args, **kwargs: None,
                    maybe_session_done=lambda *args: None, is_playing_audio=False)
                transport = PlaybackTransport(host)
                started, finish = asyncio.Event(), asyncio.Event()
                async def play(*args):
                    started.set()
                    await finish.wait()
                    if outcome == "failed":
                        raise RuntimeError("output failed")
                    if outcome == "interrupted":
                        raise asyncio.CancelledError()
                async def abort():
                    pass
                transport.play_audio, transport.abort_output_stream = play, abort
                playback = asyncio.create_task(transport.play_one_order(1, 0, b"\x00\x00", 16000, "sid"))
                await asyncio.wait_for(started.wait(), timeout=1)
                self.assertEqual(event["status"], "playback_started")
                self.assertEqual(lifecycle.delivered_turn_speech_events("sid"), [])
                receipt = {"speech_event_id": event["event_id"], "generation": 1, "orders": [0]}
                verified = asyncio.create_task(lifecycle.wait_for_speech_completion("sid", receipt, timeout_s=1))
                await asyncio.sleep(0)
                self.assertFalse(verified.done())
                finish.set()
                await playback
                self.assertEqual(await verified, outcome == "completed")
                self.assertEqual(event["status"], "playback_completed" if outcome == "completed" else "playback_interrupted")
