from __future__ import annotations

import json
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
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CoreInterpretationResult,
)
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

    def test_context_assembly_deduplicates_conversation_aggregate(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Move forward.",
            session_id="turn-large-context",
            conversation_id="conversation-large-context",
            channel="text",
        )
        canonical_history = [{"role": "user", "text": "Canonical recent turn"}]
        snapshot = gateway.assemble_context(
            capture,
            {
                "conversation_id": "conversation-large-context",
                "history": canonical_history,
                "session_memory": {"memory_summary": "bounded memory"},
                "mind": {
                    "core_principles": [{"id": "truth", "statement": "be truthful"}],
                    "long_term_goals": [{"id": "help", "statement": "help the family"}],
                    "experience_tuning_policy": ["owner approval required"],
                },
                "core_principles": ["duplicate principle projection"],
                "long_term_goals": ["duplicate goal projection"],
                "experience_tuning_policy": ["duplicate tuning projection"],
                "memory_summary": "duplicate memory projection",
                "extracted_memory": [{"text": "duplicate extracted memory"}],
                "task_contexts": [{"metadata": {"blob": "x" * 270000}}],
                "conversation": {
                    "conversation_id": "conversation-large-context",
                    "history": [{"role": "user", "text": "stale aggregate turn"}],
                    "session_memory": {"memory_summary": "stale aggregate memory"},
                    "durable_profile_memory": {"entries": ["x" * 270000]},
                    "task_store": {"path": "x" * 270000},
                },
            },
        )

        self.assertNotIn("conversation", snapshot.context)
        self.assertEqual(snapshot.context["history"], canonical_history)
        self.assertEqual(
            snapshot.context["session_memory"],
            {"memory_summary": "bounded memory"},
        )
        self.assertNotIn("core_principles", snapshot.context)
        self.assertNotIn("long_term_goals", snapshot.context)
        self.assertNotIn("experience_tuning_policy", snapshot.context)
        self.assertNotIn("memory_summary", snapshot.context)
        self.assertNotIn("extracted_memory", snapshot.context)
        self.assertNotIn("task_contexts", snapshot.context)
        encoded = json.dumps(
            snapshot.context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        self.assertLess(len(encoded), 262144)

    def test_context_assembly_flattens_legacy_conversation_leaves(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Continue.",
            session_id="turn-legacy-context",
            conversation_id="conversation-legacy-context",
            channel="text",
        )
        snapshot = gateway.assemble_context(
            capture,
            {
                "conversation": {
                    "conversation_id": "conversation-legacy-context",
                    "history": [{"role": "user", "text": "Earlier"}],
                    "active_goal_snapshots": [{"goal_id": "goal-1"}],
                    "current_task_context": {"task_id": "task-1"},
                    "unrelated_aggregate_only_payload": "x" * 270000,
                }
            },
        )

        self.assertNotIn("conversation", snapshot.context)
        self.assertEqual(
            snapshot.context["history"],
            [{"role": "user", "text": "Earlier"}],
        )
        self.assertEqual(
            snapshot.context["active_goal_snapshots"],
            [{"goal_id": "goal-1"}],
        )
        self.assertEqual(
            snapshot.context["current_task_context"],
            {"task_id": "task-1"},
        )
        self.assertNotIn("unrelated_aggregate_only_payload", snapshot.context)

    def test_context_assembly_keeps_true_snapshot_size_limit_fail_closed(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Hello",
            session_id="turn-oversized-leaf",
            conversation_id="conversation-oversized-leaf",
            channel="text",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Gateway context snapshot exceeds 262144 bytes",
        ):
            gateway.assemble_context(
                capture,
                {"interaction_context": {"evidence": "x" * 270000}},
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
            {
                "interaction_engagement": {"active": False, "gate_enabled": True},
                "history": [
                    {
                        "role": "user",
                        "text": "Wait until I say Chromie before responding.",
                        "metadata": {"accepted_dialogue_evidence": True},
                    },
                    {"role": "assistant", "text": "Okay."},
                ],
            },
        )
        request = gateway.attention_request(capture, snapshot)
        payload = request.model_dump(mode="json")

        self.assertEqual(
            payload["recent_dialogue"],
            [
                {"role": "user", "text": "Wait until I say Chromie before responding."},
                {"role": "assistant", "text": "Okay."},
            ],
        )
        self.assertEqual(payload["channel"], "text")
        self.assertNotIn("route", payload)
        self.assertNotIn("intent", payload)
        self.assertNotIn("capability", payload)
        self.assertNotIn("plan", payload)

    def test_attention_recent_dialogue_excludes_gateway_suppressed_user_turns(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "你好。",
            session_id="turn-after-suppressed-room-speech",
            conversation_id="conversation-attention",
            channel="text",
        )
        snapshot = gateway.assemble_context(
            capture,
            {
                "interaction_engagement": {"active": False, "gate_enabled": True},
                "history": [
                    {
                        "role": "user",
                        "text": "你好。",
                        "metadata": {
                            "accepted_dialogue_evidence": False,
                            "source": "cognitive_gateway.attention_review_model",
                        },
                    },
                    {
                        "role": "user",
                        "text": "Wait until I say Chromie before responding.",
                        "metadata": {"accepted_dialogue_evidence": True},
                    },
                    {"role": "assistant", "text": "Okay."},
                ],
            },
        )

        request = gateway.attention_request(capture, snapshot)

        self.assertEqual(
            request.recent_dialogue,
            [
                {
                    "role": "user",
                    "text": "Wait until I say Chromie before responding.",
                },
                {"role": "assistant", "text": "Okay."},
            ],
        )

    def test_attention_speech_act_is_preserved_in_admitted_envelope(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Hello",
            session_id="turn-greeting",
            conversation_id="conversation-greeting",
            channel="text",
        )
        snapshot = gateway.assemble_context(capture, {})
        review = AttentionReviewResult(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest=snapshot.digest,
            disposition="admit",
            speech_act="greeting",
            confidence=0.99,
            source="test",
            reason="direct greeting",
        )

        envelope = gateway.admit_attention(capture, snapshot, review)

        self.assertIsNotNone(envelope.attention)
        assert envelope.attention is not None
        self.assertEqual(envelope.attention.speech_act, "greeting")

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

    def test_core_interpretation_is_responsibility_only(self) -> None:
        interpretation = CoreInterpretationResult(
            turn_id="turn-core",
            session_id="session-core",
            confidence=0.93,
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "socially reciprocate the greeting",
                    "bindings": {},
                    "confidence": 0.93,
                }
            ],
        )

        self.assertEqual(interpretation.authority, "goal_interpretation")
        dumped = interpretation.model_dump(mode="json")
        self.assertNotIn("route", dumped)
        self.assertNotIn("intent", dumped)
        self.assertNotIn("compatibility_projection", dumped)
        self.assertNotIn("projection_digest", dumped)
        self.assertNotIn("progress_candidates", dumped)

        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            CoreInterpretationResult.model_validate(
                {**dumped, "route": "chat", "intent": "greeting"}
            )


    def test_core_responsibility_rejects_activity_realization_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "Planner-owned field"):
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome="sing a song",
                bindings={
                    "song": "birthday song",
                    "realization": {
                        "execution_lane": "vocal",
                        "vocal_mode": "singing",
                    },
                },
                confidence=0.9,
            )

    def test_core_interpretation_keeps_responsibility_evidence_provider_neutral(self) -> None:
        interpretation = CoreInterpretationResult(
            turn_id="turn-progress",
            session_id="session-progress",
            confidence=0.98,
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "provide current reference status",
                    "bindings": {"subject": "reference status"},
                    "confidence": 0.98,
                },
                {
                    "local_ref": "r2",
                    "outcome": "move forward",
                    "bindings": {},
                    "confidence": 0.96,
                },
            ],
        )

        self.assertEqual(len(interpretation.responsibilities), 2)
        self.assertEqual(interpretation.responsibilities[0].local_ref, "r1")
        self.assertEqual(
            interpretation.responsibilities[0].bindings,
            {"subject": "reference status"},
        )
        dumped = interpretation.model_dump(mode="json")
        self.assertNotIn("capability_id", dumped["responsibilities"][0])
        self.assertNotIn("args", dumped["responsibilities"][0])
        self.assertNotIn("progress_candidates", dumped)

    def test_core_interpretation_does_not_author_native_progress(self) -> None:
        payload = {
            "turn_id": "turn-native",
            "session_id": "session-native",
            "confidence": 0.97,
            "language": "en-US",
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "answer the user's identity question",
                    "bindings": {},
                    "confidence": 0.97,
                }
            ],
            "progress_candidates": [
                {
                    "kind": "native_response",
                    "response_text": "I'm Chromie!",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            CoreInterpretationResult.model_validate(payload)

    def test_core_interpretation_does_not_accept_route_or_intent(self) -> None:
        payload = {
            "turn_id": "turn-no-route",
            "session_id": "session-no-route",
            "confidence": 0.97,
            "language": "en-US",
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward",
                    "bindings": {},
                    "confidence": 0.97,
                }
            ],
            "route": "robot_action",
            "intent": "move",
        }

        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            CoreInterpretationResult.model_validate(payload)

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
