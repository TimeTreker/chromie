from __future__ import annotations

import unittest
from unittest.mock import patch

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest


class _Catalog:
    def __init__(self, result: CapabilityCatalogResult) -> None:
        self.result = result

    async def search(self, **kwargs):
        del kwargs
        return self.result


class _LlmRouter:
    def __init__(self, decision: RouteDecision) -> None:
        self.decision = decision
        self.calls = 0
        self.request: RouteRequest | None = None

    async def route(self, request: RouteRequest) -> RouteDecision:
        self.calls += 1
        self.request = request
        return self.decision


class RouterCapabilityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_match_routes_to_capability_agent(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="move forward",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "conversation_agent", "safety_agent", "speaker_agent"],
            catalog_version=4,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward.",
                    "score": 0.91,
                    "interaction_executable": True,
                }
            ],
        )
        with patch.object(main, "capability_catalog", _Catalog(result)):
            decision = await main.route(RouteRequest(text="Move forward."))

        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.route, "robot_action")
        self.assertIn("capability_agent", decision.agents)
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent"],
        )
        self.assertEqual(
            decision.metadata["task_list"][0]["task_type"],
            "task.execute_skill",
        )
        self.assertEqual(
            decision.metadata["task_list"][0]["capability_id"],
            "soridormi.walk_forward",
        )
        self.assertEqual(
            decision.candidate_capabilities[0]["capability_id"],
            "soridormi.walk_forward",
        )

    async def test_catalog_miss_does_not_use_legacy_robot_phrase_rule_by_default(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(query="turn your head left", matched=False)
        with patch.object(main, "capability_catalog", _Catalog(result)):
            decision = await main.route(RouteRequest(text="Turn your head left."))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")

    async def test_conversation_does_not_become_robot_action_from_weak_catalog_match(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="i think the sun is hot and round do you agree with me",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "conversation_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=4,
            matches=[
                {
                    "capability_id": "soridormi.turn_in_place",
                    "agent_id": "soridormi.skill",
                    "description": "Rotate left or right with near-zero forward velocity.",
                    "score": 0.165,
                    "interaction_executable": True,
                }
            ],
        )
        with patch.object(main, "capability_catalog", _Catalog(result)), patch.object(
            main.settings, "mode", "rules_only"
        ):
            decision = await main.route(
                RouteRequest(text="I think the sun is hot and round, do you agree with me?")
            )

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")

    async def test_stop_now_is_priority_interrupt(self) -> None:
        from router.app import main

        decision = await main.route(RouteRequest(text="Stop now."))

        self.assertEqual(decision.route, "interrupt")
        self.assertTrue(decision.interrupt_current)
        self.assertFalse(decision.needs_agent)
        self.assertFalse(decision.should_speak)
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter"],
        )
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["task.cancel_current_action", "body.stop_motion"],
        )
        self.assertTrue(
            all(item["source_stage"] == "emergency_filter" for item in decision.metadata["task_list"])
        )

    async def test_routes_endpoint_lists_quick_and_deep_lanes(self) -> None:
        from router.app import main

        payload = await main.routes()

        self.assertIn("chat", payload["routes"])
        self.assertEqual(payload["mode"], main.settings.mode)
        lanes = {item["id"]: item for item in payload["lanes"]}
        self.assertIn("emergency_filter", lanes)
        self.assertIn("quick_intent", lanes)
        self.assertIn("deep_thought", lanes)
        self.assertFalse(lanes["emergency_filter"]["llm"])
        self.assertIn("interrupt", lanes["emergency_filter"]["routes"])
        self.assertIn("robot_action", lanes["quick_intent"]["routes"])
        self.assertIn("deep_thought", lanes["deep_thought"]["routes"])

    async def test_chat_catalog_match_does_not_select_speech_tool_as_intent(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="tell me a joke",
            matched=True,
            suggested_route="chat",
            suggested_agents=["capability_agent", "conversation_agent", "speaker_agent"],
            catalog_version=4,
            matches=[
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message.",
                    "score": 0.41,
                    "interaction_executable": False,
                }
            ],
        )
        with patch.object(main, "capability_catalog", _Catalog(result)), patch.object(
            main.settings, "mode", "rules_only"
        ):
            decision = await main.route(RouteRequest(text="Tell me a joke."))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertNotEqual(decision.intent, "capability:chromie.speak")
        self.assertIn("conversation_agent", decision.agents)

    async def test_hybrid_router_lets_llm_handle_speech_before_semantic_fallback(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="go ahead and sing a song for me",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.62,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.91,
                language="en-US",
                source="llm",
                reason="creative speech request",
            )
        )

        def fail_semantic(*_args, **_kwargs):
            raise AssertionError("semantic fallback should not run after a valid LLM decision")

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router), patch.object(
            main, "semantic_robot_decision", fail_semantic
        ):
            decision = await main.route(RouteRequest(text="Go ahead and sing a song for me."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("conversation_agent", decision.agents)
        assert llm_router.request is not None
        self.assertEqual(
            llm_router.request.context["candidate_capabilities"][0]["capability_id"],
            "soridormi.walk_velocity",
        )

    async def test_hybrid_router_delegates_low_confidence_quick_route_to_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="请向前走十秒，然后点头两次。",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod the head yes.",
                    "score": 0.72,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="unknown",
                confidence=0.50,
                language="auto",
                source="llm",
                reason="route-only JSON",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="请向前走十秒，然后点头两次。"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertEqual(decision.language, "zh-CN")
        self.assertIn("quick router confidence", decision.reason or "")
        self.assertIn("quick_route=robot_action", decision.reason or "")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertFalse(decision.metadata["thinking_ack_allowed"])
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent", "deep_thought"],
        )
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            [
                "cognition.delegate_deep_thought",
                "cognition.deep_think",
            ],
        )
        self.assertEqual(
            [item["capability_id"] for item in decision.candidate_capabilities],
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )

    async def test_hybrid_router_recovers_llm_interrupt_robot_action_after_emergency_filter(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk forward and blink",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes.",
                    "score": 0.82,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="interrupt",
                confidence=0.0,
                language="en-US",
                source="llm",
                reason="interrupted",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="please walk forward for 10 seconds and blink your eyes")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "robot_action")
        self.assertFalse(decision.interrupt_current)
        self.assertTrue(decision.needs_agent)
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertIn("recovered as robot_action", decision.reason or "")
        self.assertIn("quick_reason=interrupted", decision.reason or "")
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent"],
        )
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["task.execute_robot_action"],
        )
        self.assertEqual(
            [item["capability_id"] for item in decision.candidate_capabilities],
            ["soridormi.walk_velocity", "soridormi.blink_eyes"],
        )

    async def test_hybrid_router_does_not_recover_discourse_marker_as_robot_action(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="go ahead and sing a song for me",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.62,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="interrupt",
                confidence=0.0,
                language="en-US",
                source="llm",
                reason="interrupted",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Go ahead and sing a song for me."))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertEqual(decision.source, "fallback")
        self.assertFalse(decision.interrupt_current)
        self.assertIn("recovered as chat", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_hybrid_router_recovers_appearance_compliment_as_chat(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="you look beautiful don't you",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.look_at_person",
                    "agent_id": "soridormi.skill",
                    "description": "Turn head toward a structured person target direction.",
                    "score": 0.62,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="interrupt",
                confidence=0.0,
                language="en-US",
                source="llm",
                reason="interrupted by a request to use the capability catalog",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="You look beautiful, don't you?"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertEqual(decision.source, "fallback")
        self.assertFalse(decision.interrupt_current)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertIn("conversation_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertIn("recovered as chat", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_hybrid_router_uses_semantic_actions_only_when_explicitly_enabled(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="请向前走十秒，然后点头两次。",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod the head yes.",
                    "score": 0.72,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.walk_velocity",
                confidence=0.91,
                language="auto",
                source="llm",
                reason="quick route selected a body skill",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main.settings, "allow_semantic_action_fallback", True
        ), patch.object(main, "capability_catalog", _Catalog(result)), patch.object(
            main, "llm_router", llm_router
        ):
            decision = await main.route(RouteRequest(text="请向前走十秒，然后点头两次。"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "compound_robot_action")
        self.assertEqual(
            [item["capability_id"] for item in decision.actions],
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 10.0)
        self.assertEqual(decision.actions[1]["args"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
