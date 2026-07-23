from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_gateway import (
    GatewayCoreCompatibilityAdapter,
    USER_TURN_ENVELOPE_CONTEXT_KEY,
)
from orchestrator.runtime.cognitive_runtime import (
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    CognitiveRuntimeResolution,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.schemas.route import RouteDecision
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
                    intent="stop_current_output",
                    confidence=1.0,
                    language="en-US",
                    priority="urgent",
                    interrupt_current=True,
                )
            )


class GatewayCoreCompatibilityAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = GatewayCoreCompatibilityAdapter(
            clock=lambda: datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc)
        )

    def test_admitted_route_preserves_correlations_and_context_provenance(self) -> None:
        capture = self.adapter.capture(
            "  Hello   Chromie  ",
            session_id="turn-1",
            conversation_id="conversation-1",
            channel="text",
        )
        context = {
            "history": [{"role": "user", "text": "Earlier"}],
            "active_goal_snapshots": [{"goal_id": "goal-1"}],
            "interaction_engagement": {"active": True},
            "robot_state": {"available": False, "source": "host_orchestrator"},
        }
        decision = RouteDecision(
            route="chat",
            intent="greeting",
            confidence=0.92,
            source="llm",
            language="en-US",
        )

        envelope = self.adapter.for_route(
            capture,
            context=context,
            decision=decision,
        )
        projection = self.adapter.project_for_core(
            envelope,
            legacy_text="  Hello   Chromie  ",
            legacy_session_id="turn-1",
            context=context,
        )

        self.assertEqual(envelope.turn_id, "turn-1")
        self.assertEqual(envelope.session_id, "turn-1")
        self.assertEqual(envelope.conversation_id, "conversation-1")
        self.assertEqual(envelope.admission, "admit")
        self.assertEqual(envelope.original_input.text, "  Hello   Chromie  ")
        self.assertEqual(projection.text, "Hello Chromie")
        self.assertEqual(projection.sid, "turn-1")
        self.assertEqual(projection.language, "en-US")
        self.assertEqual(
            projection.context[USER_TURN_ENVELOPE_CONTEXT_KEY]["turn_id"],
            "turn-1",
        )
        self.assertNotIn(USER_TURN_ENVELOPE_CONTEXT_KEY, context)
        self.assertEqual(
            {item.context_type for item in envelope.context_refs},
            {
                "history",
                "active_goal_snapshots",
                "interaction_engagement",
                "robot_state",
            },
        )
        self.assertTrue(
            all(item.freshness == "current" for item in envelope.context_refs)
        )
        self.assertTrue(
            all(item.source.startswith("orchestrator.") for item in envelope.context_refs)
        )

    def test_ambient_ignore_is_suppressed_without_inventing_a_reflex(self) -> None:
        capture = self.adapter.capture(
            "The television is still on.",
            session_id="turn-2",
            conversation_id="conversation-1",
            channel="voice",
        )
        decision = RouteDecision(
            route="ignore",
            intent="ambient_speech",
            confidence=0.95,
            source="llm",
            should_speak=False,
            reason="inactive speech was not addressed to Chromie",
            metadata={
                "semantic_addressedness_gate": True,
                "addressedness_confidence": 0.95,
            },
        )

        envelope = self.adapter.for_route(
            capture,
            context={"history": []},
            decision=decision,
        )

        self.assertEqual(envelope.admission, "suppress")
        self.assertEqual(envelope.attention.disposition, "suppress")
        self.assertEqual(envelope.reflex.action, "continue")
        with self.assertRaisesRegex(ValueError, "requires admitted input"):
            self.adapter.project_for_core(
                envelope,
                legacy_text=capture.original_text,
                legacy_session_id=capture.session_id,
                context={},
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
            lane="chat",
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


class GatewayCoreHostIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_rejects_a_suppressed_envelope_before_any_agent_call(
        self,
    ) -> None:
        adapter = GatewayCoreCompatibilityAdapter()
        capture = adapter.capture(
            "Background television speech.",
            session_id="turn-suppressed",
            conversation_id="conversation-core",
            channel="text",
        )
        decision = RouteDecision(
            route="ignore",
            intent="ambient_speech",
            confidence=0.95,
            source="llm",
            should_speak=False,
        )
        envelope = adapter.for_route(
            capture,
            context={"history": []},
            decision=decision,
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=object(),
            adapter=object(),
            policy=CognitiveRuntimePolicy(mode="report_only"),
        )

        with self.assertRaisesRegex(ValueError, "only admitted"):
            await coordinator.resolve(
                object(),
                text="Background television speech.",
                sid="turn-suppressed",
                route_decision=decision,
                context={"history": []},
                history=[],
                language="en-US",
                turn_envelope=envelope,
            )

    async def test_host_projects_the_envelope_into_the_core_without_router_mutation(
        self,
    ) -> None:
        adapter = GatewayCoreCompatibilityAdapter(
            clock=lambda: datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc)
        )
        capture = adapter.capture(
            "  Hello   Chromie  ",
            session_id="turn-core",
            conversation_id="conversation-core",
            channel="text",
        )
        envelope = adapter.for_direct(
            capture,
            context={"history": []},
            source="test.direct",
            reason="test admitted input",
        )
        decision = RouteDecision(
            route="chat",
            intent="greeting",
            confidence=0.9,
            source="llm",
            language="en-US",
        )
        captured: dict = {}

        class _CognitiveRuntime:
            async def resolve(self, session, **kwargs):
                captured.update(kwargs)
                return CognitiveRuntimeResolution(
                    mode="report_only",
                    status="report_only",
                    lane="chat",
                )

        class _Sessions:
            def update_trace_correlations(self, *args, **kwargs):
                return None

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.cognitive_gateway = adapter
        assistant.cognitive_runtime_mode = "report_only"
        assistant.cognitive_runtime_timeout_ms = 1000
        assistant.cognitive_runtime = _CognitiveRuntime()
        assistant.sessions = _Sessions()
        assistant.session_log = lambda *args, **kwargs: None

        resolution = await assistant._run_cognitive_runtime_pipeline(
            object(),
            user_text="  Hello   Chromie  ",
            session_id="turn-core",
            context={"history": []},
            decision=decision,
            record_evidence=False,
            turn_envelope=envelope,
        )

        self.assertEqual(captured["text"], "Hello Chromie")
        self.assertEqual(captured["sid"], "turn-core")
        self.assertIs(captured["turn_envelope"], envelope)
        self.assertEqual(
            captured["context"][USER_TURN_ENVELOPE_CONTEXT_KEY]["turn_id"],
            "turn-core",
        )
        self.assertIs(resolution.turn_envelope, envelope)


if __name__ == "__main__":
    unittest.main()
