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
