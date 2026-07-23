from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_gateway import GatewayCoreCompatibilityAdapter
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse


class _State:
    def __init__(self):
        self.user_turns = []
        self.agent_results = []

    def record_user_turn(self, *args, **kwargs):
        self.user_turns.append((args, kwargs))

    def record_agent_result(self, *args, **kwargs):
        self.agent_results.append((args, kwargs))


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
        assistant.cognitive_fallback_policy = "fail_closed"
        assistant.cognitive_apply_lanes = frozenset({"chat", "robot_action", "mixed"})
        assistant.conversation_state = _State()
        assistant.interaction_runtime = _InteractionRuntime()
        assistant.cognitive_evidence = type("Evidence", (), {"record": lambda *args, **kwargs: None})()
        assistant.session_log = lambda *args, **kwargs: None
        assistant._start_fast_first_audio_hedge = lambda *args, **kwargs: None
        assistant._experience_context = lambda **kwargs: {"source": "test"}
        assistant._apply_cognitive_goal_state = lambda *args, **kwargs: []
        assistant._record_cognitive_runtime_evidence = lambda *args, **kwargs: None
        assistant._launch_interaction_calls = []
        assistant._launch_interaction = lambda *args, **kwargs: assistant._launch_interaction_calls.append((args, kwargs))

        async def run_pipeline(*args, **kwargs):
            return resolution

        async def settle(*args, **kwargs):
            return False

        async def confirm(*args, **kwargs):
            return False

        assistant._run_cognitive_runtime_pipeline = run_pipeline
        assistant._settle_fast_first_audio_hedge = settle
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
            lane="chat",
            interaction_response=response,
            timings_ms={"total": 12.0},
        )
        assistant = self._assistant(resolution)
        decision = RouteDecision(
            route="chat",
            intent="greeting",
            confidence=0.9,
            source="llm",
            language="zh-CN",
        )
        gateway = GatewayCoreCompatibilityAdapter()
        capture = gateway.capture(
            "你好。",
            session_id="sid",
            conversation_id="conversation-test",
            channel="text",
        )
        turn_envelope = gateway.for_route(
            capture,
            context={"history": []},
            decision=decision,
        )

        async def run():
            handled, returned = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="你好。",
                session_id="sid",
                context={"history": []},
                decision=decision,
                router_latency_ms=10.0,
                turn_envelope=turn_envelope,
            )
            self.assertTrue(handled)
            self.assertEqual(returned.route, "chat")

        asyncio.run(run())
        self.assertEqual(len(assistant.interaction_runtime.prepared), 1)
        self.assertEqual(len(assistant.conversation_state.user_turns), 1)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        self.assertEqual(len(assistant._launch_interaction_calls), 1)
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
            lane="chat",
            goal_association=GoalAssociationResolution(
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
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.9,
            source="llm",
        )

        with self.assertRaisesRegex(
            ValueError,
            "active_goal_cancellation_requires_runtime_dispatch",
        ):
            assistant._apply_cognitive_goal_state(
                resolution,
                session_id="sid-cancel",
                user_text="Cancel the delivery.",
                decision=decision,
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
            lane="chat",
            interaction_response=response,
            goal_association=GoalAssociationResolution(
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
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.9,
            source="llm",
            language="en-US",
        )
        returned_decisions = []

        async def run():
            handled, returned = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="Cancel the delivery.",
                session_id="sid-cancel",
                context={"history": []},
                decision=decision,
                router_latency_ms=10.0,
            )
            self.assertTrue(handled)
            returned_decisions.append(returned)

        asyncio.run(run())

        self.assertEqual(state.apply_calls, 0)
        self.assertEqual(len(state.agent_results), 1)
        safe_response = state.agent_results[0][0][1]
        self.assertEqual(
            safe_response.metadata["source"],
            "host_specific_goal_cancel_not_dispatched",
        )
        self.assertIn("did not mark it cancelled", safe_response.speech[0].text)
        self.assertEqual(len(assistant._launch_interaction_calls), 1)
        recorded_resolution = state.user_turns[0][1]["metadata"][
            "cognitive_runtime_resolution"
        ]
        self.assertEqual(recorded_resolution["status"], "error")
        self.assertEqual(
            recorded_resolution["metadata"]["host_commit_status"],
            "rejected",
        )
        self.assertEqual(
            returned_decisions[0].metadata[
                "cognitive_runtime_resolution"
            ]["metadata"]["host_commit_status"],
            "rejected",
        )

    def test_chat_lane_includes_clarify_and_deep_thought_routes(self):
        for route in ("clarify", "deep_thought"):
            with self.subTest(route=route):
                response = InteractionResponse(
                    speech=[{"text": "Could you clarify?", "timing": "immediate"}],
                    metadata={"source": "goal_driven_cognitive_runtime"},
                )
                resolution = CognitiveRuntimeResolution(
                    mode="apply",
                    status="applied",
                    lane="chat",
                    interaction_response=response,
                    timings_ms={"total": 12.0},
                )
                assistant = self._assistant(resolution)
                assistant.cognitive_apply_lanes = frozenset({"chat"})
                decision = RouteDecision(
                    route=route,
                    intent=route,
                    confidence=0.5,
                    source="llm",
                    language="en-US",
                )

                async def run():
                    handled, _ = await assistant._try_apply_cognitive_runtime(
                        object(),
                        user_text="Please help me work this out.",
                        session_id=f"sid-{route}",
                        context={"history": []},
                        decision=decision,
                        router_latency_ms=10.0,
                    )
                    self.assertTrue(handled)

                asyncio.run(run())
                self.assertEqual(len(assistant.interaction_runtime.prepared), 1)

    def test_cognitive_failure_is_handled_without_legacy_reentry(self):
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="robot_action",
            fallback_reason="lane_not_enabled_for_apply",
            timings_ms={"total": 15.0},
        )
        assistant = self._assistant(resolution)

        async def settle(*args, **kwargs):
            return True

        assistant._settle_fast_first_audio_hedge = settle
        decision = RouteDecision(
            route="robot_action",
            intent="capability:soridormi.blink_eyes",
            confidence=0.9,
            source="llm",
            language="zh-CN",
        )

        async def run():
            handled, returned = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="眨眼。",
                session_id="sid",
                context={"history": []},
                decision=decision,
                router_latency_ms=10.0,
            )
            self.assertTrue(handled)
            self.assertEqual(
                returned.metadata["cognitive_runtime_resolution"]["status"],
                "error",
            )

        asyncio.run(run())
        self.assertEqual(len(assistant.conversation_state.user_turns), 1)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        self.assertEqual(len(assistant._launch_interaction_calls), 1)

    def test_report_only_schedules_without_mutating_route(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.cognitive_runtime_mode = "report_only"
        assistant.enable_agent = True
        assistant.cognitive_runtime_report_tasks = set()
        assistant.session_log = lambda *args, **kwargs: None
        completed = asyncio.Event()

        async def report(*args, **kwargs):
            completed.set()

        assistant._run_cognitive_runtime_report = report
        decision = RouteDecision(
            route="chat", intent="greeting", confidence=0.9, source="llm"
        )

        async def run():
            updated = assistant._schedule_cognitive_runtime_report(
                object(),
                user_text="hello",
                session_id="sid",
                context={"active_goal_snapshots": []},
                decision=decision,
            )
            await asyncio.wait_for(completed.wait(), timeout=1.0)
            self.assertEqual(updated.route, decision.route)
            self.assertEqual(
                updated.metadata["cognitive_runtime_resolution"]["status"],
                "scheduled",
            )

        asyncio.run(run())

    def test_report_only_observes_routes_outside_apply_allowlist(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.cognitive_runtime_mode = "report_only"
        assistant.enable_agent = True
        assistant.cognitive_apply_lanes = frozenset({"chat", "robot_action"})
        assistant.cognitive_runtime_report_tasks = set()
        assistant.session_log = lambda *args, **kwargs: None
        completed = asyncio.Event()

        async def report(*args, **kwargs):
            completed.set()

        assistant._run_cognitive_runtime_report = report
        decision = RouteDecision(
            route="tool", intent="weather", confidence=0.9, source="llm"
        )

        async def run():
            updated = assistant._schedule_cognitive_runtime_report(
                object(),
                user_text="What is the weather?",
                session_id="sid",
                context={"active_goal_snapshots": []},
                decision=decision,
            )
            await asyncio.wait_for(completed.wait(), timeout=1.0)
            self.assertEqual(updated.route, "tool")
            self.assertEqual(
                updated.metadata["cognitive_runtime_resolution"]["status"],
                "scheduled",
            )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
