from __future__ import annotations

import asyncio
import unittest

from agent.app.agents.base import AgentServices
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest, RouteDecision as AgentRouteDecision
from orchestrator.runtime.deepthinking_policy import (
    DeepThinkingDelegationPolicy,
    DeepThinkingPolicyConfig,
)
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.schemas.route import RouteDecision, RouteItem
from router.app.main import (
    _guard_low_information_side_effect,
)
from router.app.schema import RouteDecision as RouterRouteDecision, RouteRequest, finalize_decision
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
            RouterRouteDecision(
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
            RouterRouteDecision(
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

    def test_duplicate_audit_route_items_do_not_make_exact_walk_compound(self) -> None:
        policy = DeepThinkingDelegationPolicy(DeepThinkingPolicyConfig())
        duplicated_route_item = {
            "route": "robot_action",
            "intent": "capability:soridormi.walk_forward",
            "confidence": 1.0,
            "skill_id": "soridormi.walk_forward",
        }
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="capability:soridormi.walk_forward",
            confidence=1.0,
            routes=[RouteItem(**duplicated_route_item)],
            metadata={"route_items": [dict(duplicated_route_item)]},
            source="llm",
        )

        delegation = policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertFalse(delegation.compound_action)
        self.assertNotIn("high_risk_physical_goal", delegation.reasons)

    def test_uncommitted_walk_speech_becomes_confirmation_not_execution_claim(self) -> None:
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        response = InteractionResponse(
            speech=[{"text": "好的，我这就往前走十五秒。"}],
            skills=[],
            metadata={"language": "zh-CN", "route_final": "deep_thought"},
        )

        prepared = coordinator.prepare_response(response, session_id="sid-walk")
        spoken = " ".join(item.text for item in prepared.speech)

        self.assertNotIn("我这就往前走", spoken)
        self.assertIn("需要先确认", spoken)
        self.assertTrue(prepared.metadata.get("truth_reconciled"))

    def test_router_has_no_phrase_routed_gratitude_shortcut(self) -> None:
        from pathlib import Path

        source = Path("router/app/main.py").read_text(encoding="utf-8")

        self.assertNotIn("_is_standalone_gratitude", source)
        self.assertNotIn("_gratitude_acknowledgement_decision", source)
        self.assertNotIn("_GRATITUDE_EN", source)

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
