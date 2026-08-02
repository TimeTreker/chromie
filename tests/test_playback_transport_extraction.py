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

    def test_host_methods_are_compatibility_delegates(self) -> None:
        from orchestrator.orchestrator import VoiceAssistant

        for name in (
            "ensure_output_stream",
            "abort_output_stream",
            "close_output_stream",
            "play_audio",
            "enqueue_playback_skip",
            "playback_worker",
        ):
            with self.subTest(name=name):
                source = inspect.getsource(getattr(VoiceAssistant, name))
                self.assertIn("playback_transport_for(self)", source)
        orchestrator_source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "return await playback_transport_for(self).play_one_order",
            orchestrator_source,
        )
        self.assertIn(
            "return await playback_transport_for(self).synthesize_one",
            orchestrator_source,
        )


if __name__ == "__main__":
    unittest.main()
