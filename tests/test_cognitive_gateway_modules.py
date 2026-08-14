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
                    {"role": "user", "text": "Wait until I say Chromie before responding."},
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


    def test_core_interpretation_materializes_exact_progress_candidates_across_routes(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Look up the reference status, then move forward.",
            session_id="turn-progress",
            conversation_id="conversation-progress",
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
                speech_act="request",
                confidence=0.99,
                source="test",
                reason="direct request",
            ),
        )
        decision = RouteDecision.model_validate(
            {
                "route": "robot_action",
                "intent": "compound_request",
                "confidence": 0.98,
                "language": "en-US",
                "source": "llm",
                "routes": [
                    {
                        "route": "tool",
                        "intent": "chromie.reference.lookup",
                        "capability_id": "chromie.reference.lookup",
                        "args": {"query": "current status"},
                        "confidence": 0.98,
                    },
                    {
                        "route": "tool",
                        "intent": "chromie.reference.lookup",
                        "capability_id": "chromie.reference.lookup",
                        "args": {"query": "current status"},
                        "confidence": 0.98,
                    },
                    {
                        "route": "robot_action",
                        "intent": "soridormi.walk_forward",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"distance_m": 1.0},
                        "confidence": 0.96,
                    },
                ],
            }
        )

        interpretation = CoreInterpretationResult.from_route_decision(
            envelope=envelope,
            decision=decision,
        )

        self.assertEqual(len(interpretation.progress_candidates), 2)
        by_capability = {item.capability_id: item for item in interpretation.progress_candidates}
        self.assertEqual(
            by_capability["chromie.reference.lookup"].args,
            {"query": "current status"},
        )
        self.assertEqual(
            by_capability["soridormi.walk_forward"].args,
            {"distance_m": 1.0},
        )
        self.assertTrue(
            all(item.kind == "capability" for item in interpretation.progress_candidates)
        )
        self.assertTrue(
            all(item.candidate_id.startswith("progress_") for item in interpretation.progress_candidates)
        )

    def test_core_interpretation_materializes_native_conversation_progress(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "What is your name?",
            session_id="turn-native",
            conversation_id="conversation-native",
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
                speech_act="question",
                confidence=0.99,
                source="test",
                reason="direct question",
            ),
        )
        decision = RouteDecision(
            route="chat",
            intent="identity_question",
            confidence=0.97,
            language="en-US",
            source="llm",
        )

        interpretation = CoreInterpretationResult.from_route_decision(
            envelope=envelope,
            decision=decision,
            progress_proposals=[
                {
                    "kind": "native_response",
                    "response_text": "I'm Chromie!",
                    "speech_act": "answer",
                    "intent": "identity_question",
                    "confidence": 0.98,
                }
            ],
        )

        self.assertEqual(len(interpretation.progress_candidates), 1)
        candidate = interpretation.progress_candidates[0]
        self.assertEqual(candidate.kind, "native_response")
        self.assertEqual(candidate.response_text, "I'm Chromie!")
        self.assertEqual(candidate.speech_act, "answer")
        self.assertFalse(candidate.capability_id)
        self.assertEqual(candidate.args, {})

    def test_native_response_progress_requires_conversational_scope(self) -> None:
        gateway = CognitiveGateway(clock=self.clock)
        capture = gateway.capture(
            "Move forward.",
            session_id="turn-native-reject",
            conversation_id="conversation-native-reject",
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
                speech_act="request",
                confidence=0.99,
                source="test",
                reason="direct request",
            ),
        )
        decision = RouteDecision(
            route="robot_action",
            intent="move",
            confidence=0.97,
            language="en-US",
            source="llm",
        )

        interpretation = CoreInterpretationResult.from_route_decision(
            envelope=envelope,
            decision=decision,
            progress_proposals=[
                {
                    "kind": "native_response",
                    "response_text": "Sure, I moved.",
                    "speech_act": "answer",
                    "confidence": 0.98,
                }
            ],
        )

        self.assertEqual(interpretation.progress_candidates, [])

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
