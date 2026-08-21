from __future__ import annotations

import unittest

from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.runtime.observability_recording import (
    record_cognitive_gateway_evidence,
    record_cognitive_runtime_evidence,
    record_execution_experience_safely,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.user_turn import UserTurnEnvelope


class _FailingRecorder:
    def record(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("runtime journal unavailable")

    def record_gateway(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("gateway journal unavailable")


class ObservabilityRecordingPolicyTests(unittest.TestCase):
    def test_execution_recording_adds_semantic_failure_metadata(self) -> None:
        response = InteractionResponse(
            status="error",
            speech=[],
            capabilities=[],
            metadata={
                "semantic_status": "failed",
                "semantic_failure_stage": "goal_interpretation",
                "semantic_failure_class": "InterpretationUnavailableError",
                "semantic_failure_error": "invalid interpretation",
            },
        )
        captured = {}

        record_execution_experience_safely(
            response=response,
            execution=None,
            session_id="sid-test",
            confirmed_request_ids=None,
            prepare_response=lambda value, **_kwargs: value,
            record_experience=lambda **kwargs: captured.update(kwargs),
            session_log=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(
            captured["errors"],
            [
                "goal_interpretation:InterpretationUnavailableError: "
                "invalid interpretation"
            ],
        )

    def test_execution_recording_failure_is_contained(self) -> None:
        response = InteractionResponse(
            status="ok",
            speech=[],
            capabilities=[],
        )
        logs = []

        record_execution_experience_safely(
            response=response,
            execution=None,
            session_id="sid-test",
            confirmed_request_ids=None,
            prepare_response=lambda value, **_kwargs: value,
            record_experience=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("journal unavailable")
            ),
            session_log=lambda *args: logs.append(args),
        )

        self.assertEqual(len(logs), 1)
        self.assertIn("experience_prepare_failed", logs[0][1])

    def test_runtime_evidence_failure_is_fail_soft(self) -> None:
        logs = []
        resolution = CognitiveRuntimeResolution(
            mode="report_only",
            status="report_only",
        )

        record_cognitive_runtime_evidence(
            _FailingRecorder(),
            resolution,
            session_id="sid-test",
            user_text="hello",
            session_log=lambda *args: logs.append(args),
        )

        self.assertEqual(len(logs), 1)
        self.assertIn("cognitive_runtime_evidence_failed", logs[0][1])

    def test_gateway_evidence_failure_is_fail_soft(self) -> None:
        logs = []
        envelope = UserTurnEnvelope.model_validate(
            {
                "schema_version": 1,
                "turn_id": "turn-test",
                "session_id": "sid-test",
                "conversation_id": "conversation-test",
                "received_at": "2026-08-21T00:00:00+00:00",
                "channel": "text",
                "original_input": {"text": "hello"},
                "normalized_input": {"text": "hello", "language": "en"},
                "quality": {"source": "text", "usable": True},
                "attention": {
                    "disposition": "admit",
                    "source": "test",
                    "confidence": 1.0,
                    "reason": "test",
                },
                "reflex": {
                    "schema_version": 1,
                    "matched": False,
                    "action": "continue",
                    "trigger": "none",
                    "interrupt_current": False,
                },
                "context_refs": [],
                "admission": "admit",
            }
        )

        record_cognitive_gateway_evidence(
            _FailingRecorder(),
            envelope,
            user_text="hello",
            session_log=lambda *args: logs.append(args),
        )

        self.assertEqual(len(logs), 1)
        self.assertIn("cognitive_gateway_evidence_failed", logs[0][1])


if __name__ == "__main__":
    unittest.main()
