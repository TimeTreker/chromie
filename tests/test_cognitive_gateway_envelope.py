from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from agent.app.cognitive_core.goal_interpreter.schema import GoalInterpretationRequest
from agent.app.goal_association_prompt import immutable_source_turn_prompt as ga_source_prompt
from agent.app.planner_prompt import immutable_source_turn_prompt as planner_source_prompt
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
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)
from shared.chromie_contracts.reflex import ReflexOutcome
from shared.chromie_contracts.user_turn import (
    AttentionFinding,
    InputQualityEvidence,
    NormalizedTurnInput,
    OriginalTurnInput,
    UserTurnEnvelope,
    UserTurnSourceSpan,
    resolve_user_turn_source_span,
    user_turn_source_tokens,
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

    def test_source_spans_dereference_the_same_immutable_envelope(self) -> None:
        envelope = self._envelope(
            original_input=OriginalTurnInput(text="Walk at 0.2 speed for ten seconds"),
            normalized_input=NormalizedTurnInput(
                text="Walk at 0.2 speed for ten seconds", language="en-US",
            ),
        )
        tokens = user_turn_source_tokens(envelope)
        normalized = envelope.normalized_input.text
        start = normalized.index("0.2 speed")
        end = start + len("0.2 speed")
        covered = [item for item in tokens if item["start"] < end and item["end"] > start]
        span = UserTurnSourceSpan(
            source_start_token_ref=covered[0]["ref"],
            source_end_token_ref=covered[-1]["ref"],
        )
        self.assertEqual(resolve_user_turn_source_span(envelope, span), "0.2 speed")
        with self.assertRaisesRegex(ValueError, "unknown token ref"):
            resolve_user_turn_source_span(
                envelope, UserTurnSourceSpan(
                    source_start_token_ref="t999", source_end_token_ref="t999",
                ),
            )

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

    def test_gi_ga_and_planner_reference_the_same_envelope_source(self) -> None:
        envelope = self._envelope()
        gi_request = GoalInterpretationRequest(
            sid=envelope.session_id,
            text=envelope.normalized_input.text,
            language=envelope.normalized_input.language,
            turn_envelope=envelope,
        )
        self.assertEqual(gi_request.turn_envelope, envelope)

        work_request = CognitiveWorkRequest(
            sid=envelope.session_id,
            text=envelope.normalized_input.text,
            language=envelope.normalized_input.language,
            context={"user_turn_envelope": envelope.model_dump(mode="json")},
            responsibilities=[
                CognitiveResponsibilityProposal(
                    local_ref="r1",
                    outcome="Greet Chromie",
                    output_mode="speech",
                    confidence=1.0,
                )
            ],
        )
        self.assertEqual(work_request.turn_envelope, envelope)
        work_wire = work_request.model_dump(mode="json")
        self.assertNotIn("turn_envelope", work_wire)
        self.assertEqual(
            work_wire["context"]["user_turn_envelope"]["turn_id"],
            envelope.turn_id,
        )
        provenance = work_request.source_turn_provenance
        self.assertEqual(provenance["turn_id"], envelope.turn_id)
        self.assertEqual(provenance["original_text"], envelope.original_input.text)

        ga_prompt = ga_source_prompt(work_request)
        planner_prompt = planner_source_prompt(work_request)
        self.assertIn(envelope.original_input.text, ga_prompt)
        self.assertIn(envelope.original_input.text, planner_prompt)
        self.assertNotIn(envelope.turn_id, planner_prompt)
        self.assertIn('"source_tokens"', planner_prompt)
        self.assertNotIn(provenance["original_text_sha256"], planner_prompt)
        self.assertNotIn(provenance["original_text_sha256"], ga_prompt)

    def test_semantic_requests_reject_envelope_transport_mismatch(self) -> None:
        envelope = self._envelope()
        with self.assertRaisesRegex(ValidationError, "text does not match UserTurnEnvelope"):
            GoalInterpretationRequest(
                sid=envelope.session_id,
                text="Different words",
                language=envelope.normalized_input.language,
                turn_envelope=envelope,
            )
        with self.assertRaisesRegex(ValidationError, "session does not match UserTurnEnvelope"):
            CognitiveWorkRequest(
                sid="different-session",
                text=envelope.normalized_input.text,
                language=envelope.normalized_input.language,
                context={"user_turn_envelope": envelope.model_dump(mode="json")},
                responsibilities=[
                    CognitiveResponsibilityProposal(
                        local_ref="r1",
                        outcome="Greet Chromie",
                        output_mode="speech",
                        confidence=1.0,
                    )
                ],
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


def test_literal_source_span_canonicalization_stays_inside_selected_span() -> None:
    from shared.chromie_contracts.user_turn import (
        UserTurnSourceSpan, canonical_literal_user_turn_source_span,
        resolve_user_turn_source_span,
    )

    source = "walk ahead at 0.2 speed for 10 seconds and then turn left"
    broad = UserTurnSourceSpan(
        source_start_token_ref="t6", source_end_token_ref="t13"
    )
    narrowed = canonical_literal_user_turn_source_span(source, broad, "left")
    assert resolve_user_turn_source_span(source, narrowed) == "left"
    assert narrowed.source_start_token_ref == narrowed.source_end_token_ref


def test_literal_source_span_canonicalization_preserves_ambiguous_selection() -> None:
    from shared.chromie_contracts.user_turn import (
        UserTurnSourceSpan, canonical_literal_user_turn_source_span,
    )

    source = "left then left"
    broad = UserTurnSourceSpan(
        source_start_token_ref="t0", source_end_token_ref="t2"
    )
    assert canonical_literal_user_turn_source_span(source, broad, "left") == broad
