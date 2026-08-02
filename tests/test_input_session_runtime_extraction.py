from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.input_session_runtime import (
    InputSessionRuntime,
    input_session_runtime_for,
)
from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle

ROOT = Path(__file__).resolve().parents[1]
class InputSessionRuntimeExtractionTests(unittest.TestCase):
    def test_runtime_is_owned_by_input_turn_lifecycle(self) -> None:
        host = SimpleNamespace(input_turn_lifecycle=InputTurnLifecycle())
        host._input_turn_state = lambda: host.input_turn_lifecycle

        first = input_session_runtime_for(host)
        second = input_session_runtime_for(host)

        self.assertIsInstance(first, InputSessionRuntime)
        self.assertIs(first, second)
        self.assertIs(host.input_turn_lifecycle.runtime, first)

    def test_microphone_and_asr_transport_left_composition_root(self) -> None:
        root_source = (ROOT / "orchestrator" / "orchestrator.py").read_text(encoding="utf-8")
        runtime_source = (ROOT / "orchestrator" / "runtime" / "input_session_runtime.py").read_text(encoding="utf-8")

        self.assertNotIn("sd.InputStream(", root_source)
        self.assertNotIn("await self.asr_ws.recv()", root_source)
        self.assertNotIn("read_audio_packet", root_source)
        self.assertIn("sd.InputStream(", runtime_source)
        self.assertIn("host.asr_ws.recv()", runtime_source)
        self.assertIn("read_audio_packet", runtime_source)

    def test_public_host_input_methods_are_thin_delegates(self) -> None:
        source = (ROOT / "orchestrator" / "orchestrator.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "VoiceAssistant"
        )
        names = {
            "mic_callback",
            "handle_vad_audio",
            "_has_active_protective_reflex",
            "_cancel_active_routed_turns",
            "_launch_routed_turn",
            "_on_routed_turn_done",
            "_queue_vad_utterance",
            "_on_asr_task_done",
            "_feed_vad_pcm16",
            "mic_stream",
            "injected_audio_stream",
            "_session_idle_sweeper",
        }
        methods = {
            node.name: node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        }
        self.assertEqual(set(methods), names)
        for name, method in methods.items():
            self.assertEqual(
                len(method.body),
                1,
                f"VoiceAssistant.{name} regained input/session mechanics",
            )
            self.assertIsInstance(method.body[0], ast.Return)
            rendered = ast.unparse(method.body[0])
            self.assertIn("input_session_runtime_for(self)", rendered)

    def test_lifecycle_owns_microphone_buffering_state(self) -> None:
        lifecycle = InputTurnLifecycle()
        self.assertIsNone(lifecycle.loop)
        self.assertEqual(lifecycle.mic_queue.maxsize, 50)
        self.assertEqual(lifecycle.vad_leftover, b"")
        self.assertFalse(lifecycle.vad_segment_started_during_playback)
        self.assertIsNone(lifecycle.vad_segment_playback_generation)

    def test_input_runtime_does_not_import_semantic_conversation_state(self) -> None:
        source = (ROOT / "orchestrator" / "runtime" / "input_session_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("conversation_state", source)
        self.assertNotIn("GoalAssociation", source)
        self.assertNotIn("CanonicalPlan", source)

    def test_voice_assistant_compatibility_aliases_resolve_to_lifecycle(self) -> None:
        host = VoiceAssistant.__new__(VoiceAssistant)
        host.input_turn_lifecycle = InputTurnLifecycle()

        self.assertIs(host.mic_queue, host.input_turn_lifecycle.mic_queue)
        host._vad_leftover = b"abc"
        self.assertEqual(host.input_turn_lifecycle.vad_leftover, b"abc")


if __name__ == "__main__":
    unittest.main()
