from __future__ import annotations

import unittest

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
)


class _Outcome:
    def __init__(self, *, status: str = "success", output: dict | None = None, error: str | None = None) -> None:
        self.status = status
        self.output = output or {}
        self.error = error


class _Invoker:
    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, tool_name: str, arguments: dict, *, context=None):
        del arguments, context
        self.calls += 1
        if tool_name != "soridormi.skill.list":
            raise AssertionError(tool_name)
        return _Outcome(
            output={
                "mode": "sim",
                "skills": [
                    {
                        "skill_id": "nod_yes",
                        "version": "1.0.0",
                        "description": "Visible repeated bounded head pitch motion for yes/acknowledgement.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "number", "minimum": 2, "maximum": 8},
                                "duration_s": {"type": "number", "minimum": 1.0, "maximum": 10.0},
                            },
                        },
                        "available": True,
                        "effects": ["physical_motion"],
                        "safety_class": "physical_motion",
                        "requires_confirmation": False,
                    },
                    {
                        "skill_id": "shake_no",
                        "version": "1.0.0",
                        "description": "Visible repeated bounded head yaw motion for no/decline.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "number", "minimum": 2, "maximum": 8},
                                "duration_s": {"type": "number", "minimum": 1.0, "maximum": 10.0},
                            },
                        },
                        "available": True,
                        "effects": ["physical_motion"],
                        "safety_class": "physical_motion",
                        "requires_confirmation": False,
                    },
                    {
                        "skill_id": "walk_forward",
                        "version": "1.0.0",
                        "description": "Walk forward a short distance at a safe speed.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "duration_s": {"type": "number", "minimum": 0.1, "maximum": 5.0},
                                "speed": {"type": "number", "minimum": 0.0, "maximum": 0.2},
                            },
                            "required": ["duration_s"],
                        },
                        "available": True,
                        "requires_confirmation": True,
                    },
                    {
                        "skill_id": "blink_eyes",
                        "version": "1.0.0",
                        "description": "Blink the simulated social eyes.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "count": {"type": "number", "minimum": 1, "maximum": 6, "default": 2},
                            },
                        },
                        "available": True,
                        "effects": ["visual_expression"],
                        "safety_class": "low_risk_action",
                        "requires_confirmation": False,
                    }
                ],
            }
        )


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="soridormi-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List named robot skills.",
                                effects=["read_only"],
                                safety_class="safe_read",
                            )
                        ],
                    )
                ],
            )
        ]
    )


def _registry_with_planning_tool() -> CapabilityRegistry:
    return CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="soridormi-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List named robot skills.",
                                effects=["read_only"],
                                safety_class="safe_read",
                            )
                        ],
                    ),
                    AgentManifest(
                        agent_id="soridormi.motion",
                        tags=["soridormi", "motion", "robot"],
                        tools=[
                            ToolCapability(
                                name="soridormi.motion.create_plan",
                                agent_id="soridormi.motion",
                                description=(
                                    "Create a motion plan to walk forward at a requested "
                                    "speed for a requested duration."
                                ),
                                effects=["planning_only", "creates_plan"],
                                safety_class="planning_only",
                            )
                        ],
                    ),
                ],
            )
        ]
    )


class CapabilityCatalogServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_refreshes_live_named_skills_and_routes_motion(self) -> None:
        invoker = _Invoker()
        catalog = CapabilityCatalog(_registry(), live_invoker=invoker, min_score=0.10)

        result = await catalog.search("move forward slowly for one second", language="en")

        self.assertTrue(result.matched)
        self.assertEqual(result.suggested_route, "robot_action")
        self.assertIn("capability_agent", result.suggested_agents)
        self.assertTrue(
            any(
                match.capability_id == "soridormi.walk_forward"
                and match.interaction_executable
                and match.invocation_kind == "named_skill"
                for match in result.matches
            )
        )
        self.assertEqual(invoker.calls, 1)

    async def test_physical_live_skill_requires_confirmation_despite_sim_exemption(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search(
            "Please perform a nodding gesture two times.",
            language="en",
            prefer_interaction_executable=True,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.matches[0].capability_id, "soridormi.nod_yes")
        self.assertTrue(result.matches[0].requires_confirmation)

    async def test_chinese_head_shake_query_returns_live_skill_context_without_rule_match(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search(
            "你能摇头吗",
            language="zh-CN",
            prefer_interaction_executable=True,
        )

        self.assertFalse(result.matched)
        self.assertEqual(result.suggested_route, "chat")
        self.assertTrue(
            any(
                match.capability_id == "soridormi.shake_no"
                and match.interaction_executable
                for match in result.matches
            )
        )

    async def test_chinese_blink_query_ranks_live_blink_skill_first(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search(
            "眨两小眼睛。",
            language="zh-CN",
            prefer_interaction_executable=True,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.suggested_route, "robot_action")
        self.assertEqual(result.matches[0].capability_id, "soridormi.blink_eyes")
        self.assertGreaterEqual(result.matches[0].score, 0.80)
        self.assertFalse(result.matches[0].requires_confirmation)

    async def test_prefers_relevant_executable_skill_over_planning_only_tool(self) -> None:
        catalog = CapabilityCatalog(
            _registry_with_planning_tool(),
            live_invoker=_Invoker(),
            min_score=0.10,
        )

        result = await catalog.search(
            "Walk forward at 0.15 speed for 5 seconds.",
            language="en",
            prefer_interaction_executable=True,
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.matches[0].capability_id, "soridormi.walk_forward")
        self.assertTrue(result.matches[0].interaction_executable)
        self.assertTrue(
            any(
                match.capability_id == "soridormi.motion.create_plan"
                and not match.interaction_executable
                for match in result.matches
            )
        )

    async def test_inventory_question_still_returns_catalog_context(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search("What can you do?", language="en")

        self.assertFalse(result.matched)
        self.assertTrue(result.matches)
        self.assertTrue(any(match.interaction_executable for match in result.matches))

    async def test_identity_question_apostrophe_s_does_not_match_duration_schema(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        result = await catalog.search("Who are you? What's your name?", language="en")

        self.assertFalse(result.matched)
        self.assertEqual(result.suggested_route, "chat")
        self.assertFalse(any(match.score >= 0.10 for match in result.matches))

    async def test_context_distinguishes_executable_from_planning_only(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        context = await catalog.llm_context(text="walk forward", language="en")

        self.assertIn("soridormi.walk_forward", context)
        self.assertIn("interaction-executable", context)
        self.assertIn("never invent capabilities", context.lower())


if __name__ == "__main__":
    unittest.main()
