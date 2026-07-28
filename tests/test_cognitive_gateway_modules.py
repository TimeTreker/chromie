from __future__ import annotations

import unittest
from datetime import datetime, timezone

from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from orchestrator.runtime.cognitive_gateway_modules import (
    AttentionReview,
    ContextAssembly,
    InputNormalization,
    ProtectiveReflex,
    TurnAdmission,
)
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.route import RouteDecision
from shared.chromie_contracts.user_turn import (
    AttentionReviewResult,
    CoreTurnRequest,
)


class CognitiveGatewayModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = lambda: datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)

    def test_five_modules_are_physically_distinct(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)

        self.assertIsInstance(gateway.input_normalization, InputNormalization)
        self.assertIsInstance(gateway.protective_reflex, ProtectiveReflex)
        self.assertIsInstance(gateway.attention_review, AttentionReview)
        self.assertIsInstance(gateway.context_assembly, ContextAssembly)
        self.assertIsInstance(gateway.turn_admission, TurnAdmission)

    def test_normalization_preserves_original_and_changes_whitespace_only(self) -> None:
        normalizer = InputNormalization(clock=self.clock)
        capture = normalizer.capture(
            "  Hello   Chromie  ",
            session_id="turn-1",
            conversation_id="conversation-1",
            channel="text",
        )

        self.assertEqual(capture.original_text, "  Hello   Chromie  ")
        self.assertEqual(capture.normalized_text, "Hello Chromie")
        self.assertEqual(capture.received_at, self.clock())

    def test_normalization_resolves_spoken_language_from_script(self) -> None:
        normalizer = InputNormalization(clock=self.clock)

        chinese = normalizer.capture(
            "今天重庆热不热？",
            session_id="turn-zh",
            conversation_id="conversation-1",
            channel="voice",
        )
        english = normalizer.capture(
            "How warm is Chongqing?",
            session_id="turn-en",
            conversation_id="conversation-1",
            channel="voice",
        )
        explicit = normalizer.capture(
            "Chromie",
            session_id="turn-explicit",
            conversation_id="conversation-1",
            channel="voice",
            language="zh-CN",
        )

        self.assertEqual(chinese.language, "zh-CN")
        self.assertEqual(english.language, "en-US")
        self.assertEqual(explicit.language, "zh-CN")

    def test_protective_reflex_precedes_attention_or_core(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Emergency stop!",
            session_id="turn-stop",
            conversation_id="conversation-1",
            channel="text",
        )

        self.assertEqual(capture.reflex_candidate.action, "interrupt")
        envelope = gateway.for_reflex(capture)
        self.assertEqual(envelope.admission, "reflex_and_admit")
        self.assertEqual(envelope.reflex.cancellation_scope, "global_emergency")

    def test_context_assembly_is_digest_bound_and_source_attributed(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Hello",
            session_id="turn-context",
            conversation_id="conversation-context",
            channel="text",
        )
        snapshot = gateway.assemble_context(
            capture,
            {
                "history": [{"role": "user", "text": "Earlier"}],
                "active_goal_snapshots": [{"goal_id": "goal-1"}],
                "interaction_engagement": {"active": True, "gate_enabled": True},
            },
        )

        self.assertEqual(snapshot.turn_id, capture.turn_id)
        self.assertEqual(len(snapshot.digest), 64)
        self.assertEqual(
            {reference.context_type for reference in snapshot.references},
            {"history", "active_goal_snapshots", "interaction_engagement"},
        )

    def test_attention_contract_contains_no_semantic_route_or_plan(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Are you there?",
            session_id="turn-attention",
            conversation_id="conversation-attention",
            channel="text",
        )
        snapshot = gateway.assemble_context(
            capture,
            {"interaction_engagement": {"active": False, "gate_enabled": True}},
        )
        request = gateway.attention_request(capture, snapshot)
        payload = request.model_dump(mode="json")

        self.assertNotIn("route", payload)
        self.assertNotIn("intent", payload)
        self.assertNotIn("capability", payload)
        self.assertNotIn("plan", payload)

    def test_attention_result_must_match_context_snapshot(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Hello",
            session_id="turn-binding",
            conversation_id="conversation-binding",
            channel="text",
        )
        snapshot = gateway.assemble_context(capture, {})
        review = AttentionReviewResult(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest="0" * 64,
            disposition="admit",
            speech_act="greeting",
            confidence=0.99,
            source="test",
            reason="mismatched evidence",
        )

        with self.assertRaisesRegex(ValueError, "context digest"):
            gateway.admit_attention(capture, snapshot, review)

    def test_core_interpretation_binds_compatibility_projection(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Hello",
            session_id="turn-core",
            conversation_id="conversation-core",
            channel="text",
        )
        snapshot = gateway.assemble_context(capture, {})
        envelope = gateway.admit_attention(
            capture,
            snapshot,
            AttentionReviewResult(
                turn_id=capture.turn_id,
                session_id=capture.session_id,
                context_digest=snapshot.digest,
                disposition="admit",
                speech_act="greeting",
                confidence=0.99,
                source="test",
                reason="direct greeting",
            ),
        )
        decision = RouteDecision(
            route="chat",
            intent="greeting",
            confidence=0.93,
            language="en-US",
            source="llm",
        )

        interpretation = CoreInterpretationResult.from_route_decision(
            envelope=envelope,
            decision=decision,
        )

        self.assertEqual(interpretation.authority, "goal_driven_cognitive_core")
        self.assertEqual(interpretation.lane, "chat")
        self.assertEqual(
            interpretation.route_decision_projection().intent,
            "greeting",
        )
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            interpretation.model_copy(
                update={"projection_digest": "0" * 64}
            ).model_validate(
                {
                    **interpretation.model_dump(mode="json"),
                    "projection_digest": "0" * 64,
                }
            )

    def test_core_request_requires_an_admitted_envelope(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Nearby meeting narration.",
            session_id="turn-suppress",
            conversation_id="conversation-suppress",
            channel="text",
        )
        snapshot = gateway.assemble_context(capture, {})
        envelope = gateway.admit_attention(
            capture,
            snapshot,
            AttentionReviewResult(
                turn_id=capture.turn_id,
                session_id=capture.session_id,
                context_digest=snapshot.digest,
                disposition="suppress",
                speech_act="narration",
                confidence=0.95,
                source="test",
                reason="ambient",
            ),
        )

        with self.assertRaisesRegex(ValueError, "only admitted"):
            CoreTurnRequest(
                turn_envelope=envelope,
                context_snapshot=snapshot,
            )


if __name__ == "__main__":
    unittest.main()
