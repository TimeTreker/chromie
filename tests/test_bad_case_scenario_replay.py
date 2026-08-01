from __future__ import annotations

import asyncio
import unittest

from agent.app.agents.base import AgentServices
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest, RouteDecision as AgentRouteDecision
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.schemas.route import RouteDecision, RouteItem
from agent.app.cognitive_core.goal_interpreter.engine import (
    _guard_low_information_side_effect,
)
from agent.app.cognitive_core.goal_interpreter.rules import route_by_priority_rules
from agent.app.cognitive_core.goal_interpreter.schema import RouteDecision as GoalInterpreterRouteDecision, RouteRequest, finalize_decision
from shared.chromie_contracts.interaction import InteractionResponse


class BadCaseScenarioReplayTests(unittest.TestCase):
    """Replay user-visible bad cases from the July 9 robot logs.

    These tests are intentionally scenario-shaped: they assert the visible turn
    contract, not only an isolated schema helper.  The goal is to catch the
    classes of failures where Chromie understood a turn locally but then spoke
    or routed in a non-human way.
    """

    def test_low_information_w_is_terminal_clarification_not_body_cue(self) -> None:
        request = RouteRequest(text="W.", language="en-US")
        bad_llm_decision = finalize_decision(
            GoalInterpreterRouteDecision(
                route="robot_action",
                agents=["speaker_agent"],
                intent="soridormi.blink_eyes",
                confidence=0.95,
                speak_first='I only heard "W.". What would you like me to do?',
                source="llm",
            ),
            request,
            source="llm",
        )

        guarded = _guard_low_information_side_effect(request, bad_llm_decision)

        self.assertIsNotNone(guarded)
        assert guarded is not None
        self.assertEqual(guarded.route, "clarify")
        self.assertEqual(guarded.intent, "clarify_insufficient_information")
        self.assertEqual(guarded.agents, ["speaker_agent"])
        self.assertFalse(any(item.route == "robot_action" for item in guarded.routes))
        self.assertNotIn("soridormi.express_attention", str(guarded.metadata))

    def test_completed_retained_task_does_not_authorize_tiny_fragment_motion(self) -> None:
        request = RouteRequest(
            text="I.",
            language="en-US",
            context={
                "pending_tasks": [
                    {
                        "task_id": "task-old",
                        "status": "done",
                        "goal": "blink once",
                    }
                ]
            },
        )
        bad_llm_decision = finalize_decision(
            GoalInterpreterRouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent"],
                intent="soridormi.blink_eyes",
                confidence=0.93,
                source="llm",
            ),
            request,
            source="llm",
        )

        guarded = _guard_low_information_side_effect(request, bad_llm_decision)

        self.assertIsNotNone(guarded)
        assert guarded is not None
        self.assertEqual(guarded.route, "clarify")
        self.assertEqual(guarded.intent, "clarify_insufficient_information")
        self.assertFalse(any(item.route == "robot_action" for item in guarded.routes))

    def test_uncommitted_effect_requires_model_repair_independent_of_wording(self) -> None:
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        for text in ("好的，我这就往前走十五秒。", "I cannot do that safely."):
            with self.subTest(text=text):
                response = InteractionResponse(
                    speech=[{"text": text}],
                    skills=[],
                    metadata={
                        "language": "zh-CN",
                        "route_final": "deep_thought",
                        "deepthinking_proposed_effect_task_count": 1,
                        "deepthinking_valid_effect_task_count": 0,
                    },
                )

                prepared = coordinator.prepare_response(
                    response,
                    session_id="sid-walk",
                )

                self.assertEqual(prepared.speech, [])
                self.assertTrue(prepared.metadata.get("truth_reconciled"))
                self.assertTrue(
                    prepared.metadata.get(
                        "truth_reconciliation_requires_model_repair"
                    )
                )

    def test_gratitude_is_not_resolved_by_deterministic_phrase_routing(self) -> None:
        decision = route_by_priority_rules(
            RouteRequest(text="Thank you.", language="en-US")
        )

        self.assertIsNone(decision)

    def test_gratitude_ack_is_terminal_in_agent_runtime(self) -> None:
        decision = AgentRouteDecision(
            route="chat",
            agents=["speaker_agent"],
            intent="gratitude_acknowledgement",
            confidence=1.0,
            speak_first="You're welcome.",
            should_speak=True,
            source="rules",
        )
        runtime = AgentRuntime(AgentServices(use_llm=False))
        request = AgentRunRequest(
            text="Thank.",
            language="en-US",
            route_decision=decision,
            context={"pending_tasks": [{"skill_id": "soridormi.walk_forward"}]},
        )

        result = asyncio.run(runtime.run(request))

        self.assertEqual([item.text for item in result.speak_immediate], ["You're welcome."])
        self.assertEqual(result.actions, [])
        self.assertFalse(result.requires_confirmation)
        self.assertTrue(any("skipped agent rewrite" in item for item in result.trace))


if __name__ == "__main__":
    unittest.main()
