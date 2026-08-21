from __future__ import annotations

import asyncio
import types
import unittest

from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.runtime.observability_recording import (
    record_cognitive_gateway_evidence,
    record_cognitive_runtime_evidence,
    record_execution_experience_safely,
    sample_accelerator_resources,
    schedule_accelerator_sample,
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


    def test_accelerator_sample_records_only_observability_truth(self) -> None:
        async def run():
            calls: list[str] = []
            active_samples: list[dict] = []
            per_session: list[tuple[str, dict]] = []

            class Sampler:
                async def sample(self, *, reason: str):
                    calls.append(reason)
                    return {"sample_reason": reason, "available": True}

            sessions = types.SimpleNamespace(
                record_active_resource_sample=lambda **kwargs: active_samples.append(kwargs),
                record_resource_sample=lambda sid, **kwargs: per_session.append((sid, kwargs)),
            )
            host = types.SimpleNamespace(
                accelerator_sampler=Sampler(),
                sessions=sessions,
            )

            active = await sample_accelerator_resources(host, reason="periodic")
            scoped = await sample_accelerator_resources(
                host,
                reason="session_start",
                session_ids=["sid-a", "sid-b"],
            )
            return calls, active_samples, per_session, active, scoped

        calls, active_samples, per_session, active, scoped = asyncio.run(run())

        self.assertEqual(calls, ["periodic", "session_start"])
        self.assertEqual(active["sample_reason"], "periodic")
        self.assertEqual(scoped["sample_reason"], "session_start")
        self.assertEqual(len(active_samples), 1)
        self.assertEqual([sid for sid, _ in per_session], ["sid-a", "sid-b"])
        self.assertEqual(active_samples[0]["name"], "accelerator_resource_sample")

    def test_accelerator_schedule_tracks_detached_observability_task(self) -> None:
        async def run():
            release = asyncio.Event()

            class Sampler:
                def should_sample(self, reason: str) -> bool:
                    return reason == "session_start"

                async def sample(self, *, reason: str):
                    await release.wait()
                    return {"sample_reason": reason}

            recorded: list[tuple[str, dict]] = []
            host = types.SimpleNamespace(
                accelerator_sampler=Sampler(),
                sessions=types.SimpleNamespace(
                    record_resource_sample=lambda sid, **kwargs: recorded.append((sid, kwargs)),
                    record_active_resource_sample=lambda **_kwargs: None,
                ),
                observability_tasks=set(),
            )

            schedule_accelerator_sample(
                host,
                reason="session_start",
                session_ids=["sid-test"],
            )
            self.assertEqual(len(host.observability_tasks), 1)
            task = next(iter(host.observability_tasks))
            release.set()
            await task
            await asyncio.sleep(0)
            return host, recorded

        host, recorded = asyncio.run(run())
        self.assertEqual(recorded[0][0], "sid-test")
        self.assertEqual(host.observability_tasks, set())

    def test_accelerator_schedule_is_optional_without_running_loop(self) -> None:
        host = types.SimpleNamespace(
            accelerator_sampler=types.SimpleNamespace(
                should_sample=lambda _reason: True,
            ),
            observability_tasks=set(),
        )
        schedule_accelerator_sample(host, reason="session_start")
        self.assertEqual(host.observability_tasks, set())

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
