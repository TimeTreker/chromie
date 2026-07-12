from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.app.capabilities.catalog import CapabilityCatalog
from tests.test_capability_catalog_service import _Invoker, _registry
from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest
from tests.test_router_capability_routing import _Catalog, _LlmRouter


class ForwardMotionRecovery0806Tests(unittest.IsolatedAsyncioTestCase):
    async def test_chinese_forward_motion_ranks_live_walk_skill(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search("你往前走个15秒。", language="zh-CN")

        self.assertTrue(result.matched)
        self.assertEqual(result.suggested_route, "robot_action")
        self.assertEqual(result.matches[0].capability_id, "soridormi.walk_forward")
        self.assertTrue(result.matches[0].interaction_executable)

    async def test_router_does_not_phrase_match_generic_motion_to_a_skill(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="你往前走个15秒。",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=23,
            matches=[],
        )
        snapshot = {
            "catalog_version": 23,
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Human-facing wrapper for walking forward safely.",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["physical_motion"],
                    "safety_class": "physical_motion",
                    "requires_confirmation": True,
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod yes as a social acknowledgement.",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["physical_motion"],
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="physical_motion",
                confidence=1.0,
                language="zh-CN",
                source="llm",
                reason="quick router did not select an exact skill",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="你往前走个15秒。", language="zh-CN"))

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "semantic_capability_planning")
        self.assertIn("capability_agent", decision.agents)
        self.assertNotIn("catalog_affordance_recovery", decision.metadata)
        self.assertEqual(
            decision.metadata["desired_abilities"][0]["ability_id"],
            "unresolved_effectful_goal",
        )

    async def test_missing_forward_motion_speech_uses_user_language(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="你往前走个15秒。",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=24,
            matches=[],
        )
        snapshot = {
            "catalog_version": 24,
            "capabilities": [
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod yes as a social acknowledgement.",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["physical_motion"],
                    "route": "robot_action",
                    "prompt_tier": "common",
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="physical_motion",
                confidence=1.0,
                language="auto",
                source="llm",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="你往前走个15秒。"))

        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "semantic_capability_planning")
        self.assertTrue(decision.language.startswith("zh"))
        self.assertIsNone(decision.speak_first)
        self.assertEqual(
            decision.metadata["desired_abilities"][0]["ability_id"],
            "unresolved_effectful_goal",
        )
        self.assertEqual(
            decision.metadata["capability_grounding"]["status"],
            "unresolved_requires_planner",
        )


if __name__ == "__main__":
    unittest.main()
