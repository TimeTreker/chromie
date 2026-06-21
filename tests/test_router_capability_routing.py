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

    async def test_routes_endpoint_lists_quick_and_deep_lanes(self) -> None:
        from router.app import main

        payload = await main.routes()

        self.assertIn("chat", payload["routes"])
        self.assertEqual(payload["mode"], main.settings.mode)
        lanes = {item["id"]: item for item in payload["lanes"]}
        self.assertIn("quick_control", lanes)
        self.assertIn("deep_reasoning", lanes)
        self.assertFalse(lanes["quick_control"]["llm"])
        self.assertIn("interrupt", lanes["quick_control"]["routes"])
        self.assertIn("robot_action", lanes["deep_reasoning"]["routes"])

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


if __name__ == "__main__":
    unittest.main()
