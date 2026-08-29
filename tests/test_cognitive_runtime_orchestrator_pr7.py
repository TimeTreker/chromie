from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
from shared.chromie_contracts.user_turn import AttentionReviewResult
from shared.chromie_contracts.interaction import InteractionResponse


def _core_and_envelope(text: str, *, sid: str, language: str = "en-US"):
    gateway = CognitiveGateway()
    capture = gateway.capture(
        text,
        session_id=sid,
        conversation_id=f"conversation-{sid}",
        channel="text",
        language=language,
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
            confidence=1.0,
            source="test",
            reason="orchestrator runtime test input",
        ),
    )
    core = CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=0.95,
        language=language,
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": text,
                "bindings": {},
                "confidence": 0.95,
            }
        ],
    )
    return core, envelope


class _State:
    def __init__(self):
        self.user_turns = []
        self.agent_results = []

    def record_user_turn(self, *args, **kwargs):
        self.user_turns.append((args, kwargs))

    def record_interaction_response(self, *args, **kwargs):
        self.agent_results.append((args, kwargs))

    def active_task_snapshots(self):
        return []


class _InteractionRuntime:
    def __init__(self):
        self.prepared = []

    def prepare_response(self, response, *, session_id):
        self.prepared.append((response, session_id))
        return response


class OrchestratorCognitiveRuntimeTests(unittest.TestCase):
    @staticmethod
    def _assistant(resolution: CognitiveRuntimeResolution):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.cognitive_runtime_mode = "apply"
        assistant.enable_agent = True
        assistant.enable_interaction_response = True
        assistant.conversation_state = _State()
        assistant.interaction_runtime = _InteractionRuntime()
        assistant.cognitive_evidence = type("Evidence", (), {"record": lambda *args, **kwargs: None})()
        assistant.session_log = lambda *args, **kwargs: None
        assistant._experience_context = lambda **kwargs: {"source": "test"}
        assistant._apply_cognitive_goal_state = lambda *args, **kwargs: []
        assistant._record_cognitive_runtime_evidence = lambda *args, **kwargs: None
        assistant._launch_interaction_calls = []
        assistant._launch_interaction = lambda *args, **kwargs: assistant._launch_interaction_calls.append((args, kwargs))
        assistant._auxiliary_schedule_calls = []

        class _CognitiveRuntime:
            def schedule_resolution_auxiliary_activities(self, *args, **kwargs):
                if not assistant._launch_interaction_calls:
                    raise AssertionError(
                        "auxiliary Activity was scheduled before primary launch"
                    )
                assistant._auxiliary_schedule_calls.append((args, kwargs))

        assistant.cognitive_runtime = _CognitiveRuntime()

        async def run_pipeline(*args, **kwargs):
            return resolution

        async def confirm(*args, **kwargs):
            return False

        assistant._run_cognitive_runtime_pipeline = run_pipeline
        assistant._stage_interaction_confirmation = confirm
        return assistant

    def test_applied_resolution_uses_trusted_prepare_and_launch(self):
        response = InteractionResponse(
            speech=[{"text": "你好。", "timing": "immediate"}],
            metadata={"source": "goal_driven_cognitive_runtime"},
        )
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            interaction_response=response,
            timings_ms={"total": 12.0},
        )
        assistant = self._assistant(resolution)
        core, turn_envelope = _core_and_envelope("你好。", sid="sid", language="zh-CN")

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="你好。",
                session_id="sid",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=turn_envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(len(assistant.interaction_runtime.prepared), 1)
        self.assertEqual(len(assistant.conversation_state.user_turns), 1)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        self.assertEqual(len(assistant._launch_interaction_calls), 1)
        self.assertEqual(len(assistant._auxiliary_schedule_calls), 1)
        prepared_response = assistant.interaction_runtime.prepared[0][0]
        self.assertEqual(prepared_response.metadata["turn_id"], "sid")
        self.assertEqual(
            prepared_response.metadata["user_turn_envelope_schema_version"],
            1,
        )
        self.assertEqual(
            prepared_response.metadata["user_turn_envelope"]["turn_id"],
            "sid",
        )
        recorded_metadata = assistant.conversation_state.user_turns[0][1][
            "metadata"
        ]
        self.assertEqual(
            recorded_metadata["user_turn_envelope"]["turn_id"],
            "sid",
        )

    def test_apply_uses_responsibility_only_core_and_defers_first_wording_to_planner(self):
        response = InteractionResponse(
            speech=[{"text": "北京今天没有雨。", "timing": "after_capabilities"}],
            metadata={"source": "goal_driven_cognitive_runtime"},
        )
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            interaction_response=response,
            timings_ms={"total": 68000.0},
        )
        assistant = self._assistant(resolution)
        events = []

        async def run_pipeline(*args, **kwargs):
            del args, kwargs
            events.append("runtime_started")
            return resolution

        assistant._run_cognitive_runtime_pipeline = run_pipeline
        self.assertFalse(hasattr(assistant, "_schedule_fast" + "_first_response"))
        core, envelope = _core_and_envelope(
            "今天北京下雨了没有？", sid="sid-weather", language="zh-CN"
        )
        core = CoreInterpretationResult.model_validate(
            {
                **core.model_dump(mode="json"),
                "responsibilities": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell whether it is raining in Beijing today.",
                        "bindings": {"location": "北京", "time": "today"},
                        "confidence": 0.95,
                    }
                ],
            }
        )

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="今天北京下雨了没有？",
                session_id="sid-weather",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=1400.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(events, ["runtime_started"])
        self.assertTrue(assistant._launch_interaction_calls[0][1]["reset_playback"])

    def test_active_named_goal_cancel_fails_closed_before_state_mutation(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        class State:
            max_pending_tasks = 8
            apply_calls = 0

            def active_goal_snapshots(self, *, limit):
                return [
                    {
                        "goal_id": "goal-delivery",
                        "status": "running",
                        "metadata": {
                            "interaction_id": "interaction-delivery",
                            "canonical_plan_id": "plan-delivery",
                            "canonical_plan_fingerprint": "fingerprint-delivery",
                            "remaining_request_ids": ["deliver-request"],
                        },
                    }
                ]

            def apply_goal_association_resolution(self, *args, **kwargs):
                self.apply_calls += 1
                return []

        assistant.conversation_state = State()
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            goal_association=GoalAssociationResolution(
                resolution_status="resolved",
                turn_id="turn-cancel-delivery",
                associations=[
                    {
                        "association_id": "assoc-cancel-delivery",
                        "relationship": "cancel",
                        "target_goal_ids": ["goal-delivery"],
                        "confidence": 0.95,
                    }
                ],
                confidence=0.95,
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "active_goal_cancellation_requires_runtime_dispatch",
        ):
            assistant._apply_cognitive_goal_state(
                resolution,
                session_id="sid-cancel",
                user_text="Cancel the delivery.",
            )
        self.assertEqual(assistant.conversation_state.apply_calls, 0)

    def test_active_named_goal_cancel_returns_truthful_safe_response(self):
        response = InteractionResponse(
            speech=[{"text": "Cancelled.", "timing": "immediate"}],
            metadata={"source": "goal_driven_cognitive_runtime"},
        )
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            interaction_response=response,
            goal_association=GoalAssociationResolution(
                resolution_status="resolved",
                turn_id="turn-cancel-delivery",
                associations=[
                    {
                        "association_id": "assoc-cancel-delivery",
                        "relationship": "cancel",
                        "target_goal_ids": ["goal-delivery"],
                        "confidence": 0.95,
                    }
                ],
                confidence=0.95,
            ),
        )
        assistant = self._assistant(resolution)

        class State(_State):
            max_pending_tasks = 8

            def __init__(self):
                super().__init__()
                self.apply_calls = 0

            def active_goal_snapshots(self, *, limit):
                return [
                    {
                        "goal_id": "goal-delivery",
                        "status": "running",
                        "metadata": {
                            "interaction_id": "interaction-delivery",
                            "canonical_plan_id": "plan-delivery",
                            "canonical_plan_fingerprint": (
                                "fingerprint-delivery"
                            ),
                            "remaining_request_ids": ["deliver-request"],
                        },
                    }
                ]

            def apply_goal_association_resolution(self, *args, **kwargs):
                self.apply_calls += 1
                return []

        state = State()
        assistant.conversation_state = state
        del assistant._apply_cognitive_goal_state
        core, envelope = _core_and_envelope("Cancel the delivery.", sid="sid-cancel")

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="Cancel the delivery.",
                session_id="sid-cancel",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())

        self.assertEqual(state.apply_calls, 0)
        self.assertEqual(len(state.agent_results), 1)
        safe_response = state.agent_results[0][0][1]
        self.assertEqual(
            safe_response.metadata["source"],
            "host_goal_cancellation_operational_fail_safe",
        )
        self.assertIn("don't assume it stopped", safe_response.speech[0].text)
        self.assertEqual(
            safe_response.metadata["goal_cancellation_evidence"]["status"],
            "not_cancelled",
        )
        self.assertEqual(len(assistant._launch_interaction_calls), 1)
        recorded_resolution = state.user_turns[0][1]["metadata"][
            "cognitive_runtime_resolution"
        ]
        self.assertEqual(recorded_resolution["status"], "error")
        self.assertEqual(
            recorded_resolution["metadata"]["host_commit_status"],
            "rejected",
        )

    def test_chat_apply_needs_no_legacy_route_label(self):
        response = InteractionResponse(
            speech=[{"text": "Could you clarify?", "timing": "immediate"}],
            metadata={"source": "goal_driven_cognitive_runtime"},
        )
        resolution = CognitiveRuntimeResolution(
            mode="apply", status="applied", interaction_response=response
        )
        assistant = self._assistant(resolution)
        core, envelope = _core_and_envelope(
            "Please help me work this out.", sid="sid-chat"
        )

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="Please help me work this out.",
                session_id="sid-chat",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(len(assistant.interaction_runtime.prepared), 1)

    def test_host_has_no_post_response_social_attention_bridge(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self.assertFalse(hasattr(assistant, "_queue_response_social_attention"))

    def test_confirmation_held_primary_does_not_schedule_auxiliary_activity(self):
        response = InteractionResponse(
            speech=[{"text": "Please confirm.", "timing": "immediate"}],
            requires_confirmation=True,
            metadata={"source": "goal_driven_cognitive_runtime"},
        )
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            interaction_response=response,
        )
        assistant = self._assistant(resolution)

        async def hold_confirmation(*args, **kwargs):
            return True

        assistant._stage_interaction_confirmation = hold_confirmation
        core, envelope = _core_and_envelope("Please do it.", sid="sid-confirm")

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="Please do it.",
                session_id="sid-confirm",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(assistant._launch_interaction_calls, [])
        self.assertEqual(assistant._auxiliary_schedule_calls, [])

    def test_cognitive_failure_uses_deterministic_fail_closed_response(self):
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            fallback_reason="foreground_deadline_exceeded",
            timings_ms={"total": 15.0},
        )
        assistant = self._assistant(resolution)
        async def settle(*args, **kwargs):
            return True

        core, envelope = _core_and_envelope("眨眼。", sid="sid", language="zh-CN")

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="眨眼。",
                session_id="sid",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(len(assistant.conversation_state.user_turns), 1)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        safe_response = assistant.conversation_state.agent_results[0][0][1]
        self.assertEqual(
            safe_response.metadata["source"],
            "host_cognitive_core_exception_safe_fallback",
        )
        self.assertEqual(
            safe_response.speech[0].text,
            "咦，刚才没接上。你再跟我说一遍嘛。",
        )
        self.assertEqual(safe_response.metadata["effect_execution"], "not_authorized")
        self.assertEqual(len(assistant._launch_interaction_calls), 1)


    def test_cognitive_failure_preserves_existing_planner_speech_playback(self):
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            fallback_reason="foreground_deadline_exceeded",
            timings_ms={"total": 15000.0},
            metadata={
                "failure_stage": "cognitive_runtime_foreground",
                "failure_class": "foreground_deadline_exceeded",
            },
        )
        assistant = self._assistant(resolution)
        event = assistant._register_turn_speech_event(
            session_id="sid-timeout",
            turn_id="sid-timeout",
            generation=2,
            orders=[4],
            text="好，我去看看。",
            stage="fast_first",
            purpose="acknowledge_and_check",
            communicative_activity_ids=["progress_weather"],
        )
        assert event is not None
        event["status"] = "playback_started"
        core, envelope = _core_and_envelope(
            "查一下天气。", sid="sid-timeout", language="zh-CN"
        )

        async def run():
            handled = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="查一下天气。",
                session_id="sid-timeout",
                context={"history": []},
                core_interpretation=core,
                core_interpretation_latency_ms=10.0,
                turn_envelope=envelope,
            )
            self.assertTrue(handled)

        asyncio.run(run())
        self.assertEqual(len(assistant._launch_interaction_calls), 0)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        recorded_response = assistant.conversation_state.agent_results[0][0][1]
        self.assertEqual(recorded_response.speech, [])
        self.assertTrue(
            recorded_response.metadata["user_visible_fallback_suppressed"]
        )
        self.assertEqual(
            recorded_response.metadata["fallback_suppression_reason"],
            "planner_communication_already_committed",
        )




if __name__ == "__main__":
    unittest.main()
