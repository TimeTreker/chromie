from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_gateway import (
    CognitiveGateway,
    USER_TURN_ENVELOPE_CONTEXT_KEY,
)
from orchestrator.runtime.cognitive_runtime import (
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    CognitiveRuntimeResolution,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.reflex import ReflexOutcome
from shared.chromie_contracts.user_turn import (
    AttentionFinding,
    InputQualityEvidence,
    NormalizedTurnInput,
    OriginalTurnInput,
    UserTurnEnvelope,
)


class UserTurnEnvelopeContractTests(unittest.TestCase):
    def _envelope(self, **updates) -> UserTurnEnvelope:
        values = {
            "turn_id": "turn-1",
            "session_id": "turn-1",
            "conversation_id": "conversation-1",
            "channel": "text",
            "received_at": datetime(2026, 7, 23, tzinfo=timezone.utc),
            "original_input": OriginalTurnInput(text="  Hello   Chromie  "),
            "normalized_input": NormalizedTurnInput(
                text="Hello Chromie",
                language="en-US",
            ),
            "quality": InputQualityEvidence(source="text", usable=True),
            "reflex": ReflexOutcome(language="en-US"),
            "attention": AttentionFinding(
                disposition="admit",
                source="test.attention",
                confidence=1.0,
            ),
            "admission": "admit",
        }
        values.update(updates)
        return UserTurnEnvelope(**values)

    def test_preserves_original_input_and_is_frozen(self) -> None:
        envelope = self._envelope()

        self.assertEqual(envelope.original_input.text, "  Hello   Chromie  ")
        self.assertEqual(envelope.normalized_input.text, "Hello Chromie")
        with self.assertRaises(ValidationError):
            envelope.turn_id = "another-turn"
        with self.assertRaises(ValidationError):
            envelope.original_input.text = "rewritten"
        with self.assertRaises(ValidationError):
            envelope.reflex.action = "ignore"

    def test_rejects_semantic_fields_and_input_substitution(self) -> None:
        payload = self._envelope().model_dump(mode="json")
        for field, value in (
            ("intent", "weather"),
            ("route", "tool"),
            ("selected_skill", "chromie.weather"),
            ("plan", {"steps": []}),
            ("response_text", "It is sunny."),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    UserTurnEnvelope.model_validate({**payload, field: value})

        with self.assertRaisesRegex(
            ValidationError,
            "semantic substitution is forbidden",
        ):
            self._envelope(
                normalized_input=NormalizedTurnInput(
                    text="Use the weather tool",
                    language="en-US",
                )
            )

    def test_admission_invariants_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "unusable input requires admission=unusable",
        ):
            self._envelope(
                quality=InputQualityEvidence(source="text", usable=False),
            )
        with self.assertRaisesRegex(
            ValidationError,
            "interrupt reflexes require",
        ):
            self._envelope(
                reflex=ReflexOutcome(
                    matched=True,
                    action="interrupt",
                    trigger="stop_command",
                    confidence=1.0,
                    language="en-US",
                    priority="urgent",
                    interrupt_current=True,
                    cancellation_scope="current_interaction",
                )
            )


class CognitiveGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = CognitiveGateway(
            clock=lambda: datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc)
        )



    def test_reflex_envelope_retains_stop_as_input(self) -> None:
        capture = self.adapter.capture(
            "Stop now.",
            session_id="turn-stop",
            conversation_id="conversation-1",
            channel="voice",
        )

        envelope = self.adapter.for_reflex(capture)

        self.assertEqual(envelope.admission, "reflex_and_admit")
        self.assertEqual(envelope.original_input.text, "Stop now.")
        self.assertEqual(envelope.reflex.action, "interrupt")
        self.assertTrue(envelope.reflex.interrupt_current)

    def test_cognitive_evidence_dual_records_the_envelope(self) -> None:
        capture = self.adapter.capture(
            "Hello.",
            session_id="turn-evidence",
            conversation_id="conversation-evidence",
            channel="text",
        )
        envelope = self.adapter.for_direct(
            capture,
            source="test.direct",
            reason="test admitted input",
        )
        resolution = CognitiveRuntimeResolution(
            mode="report_only",
            status="report_only",
            turn_envelope=envelope,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            recorder = CognitiveEvidenceRecorder(path)
            recorder.record(resolution, sid="turn-evidence", text="Hello.")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["user_turn_envelope"]["turn_id"],
            "turn-evidence",
        )
        self.assertEqual(
            payload["user_turn_envelope"]["admission"],
            "admit",
        )


if __name__ == "__main__":
    unittest.main()
