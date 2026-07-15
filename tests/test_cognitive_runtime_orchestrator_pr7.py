from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.schemas.route import RouteDecision
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

        async def run():
            handled, returned = await assistant._try_apply_cognitive_runtime(
                object(),
                user_text="你好。",
                session_id="sid",
                context={"history": []},
                decision=decision,
                router_latency_ms=10.0,
            )
            self.assertTrue(handled)
            self.assertEqual(returned.route, "chat")

        asyncio.run(run())
        self.assertEqual(len(assistant.interaction_runtime.prepared), 1)
        self.assertEqual(len(assistant.conversation_state.user_turns), 1)
        self.assertEqual(len(assistant.conversation_state.agent_results), 1)
        self.assertEqual(len(assistant._launch_interaction_calls), 1)

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


if __name__ == "__main__":
    unittest.main()
