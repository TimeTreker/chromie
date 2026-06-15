from __future__ import annotations

import unittest
from unittest.mock import patch

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteRequest


class _Catalog:
    def __init__(self, result: CapabilityCatalogResult) -> None:
        self.result = result

    async def search(self, **kwargs):
        del kwargs
        return self.result


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


if __name__ == "__main__":
    unittest.main()
