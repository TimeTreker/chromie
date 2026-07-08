from __future__ import annotations

import unittest

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.local import chromie_capability_bundle
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


class _SafetyLockedInvoker:
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
                        "skill_id": "calibrate_floor",
                        "version": "1.0.0",
                        "description": "Run a guarded calibration workflow.",
                        "parameters_schema": {"type": "object", "properties": {}},
                        "available": True,
                        "effects": ["commissioning_no_motion"],
                        "safety_class": "guarded_operation",
                        "requires_confirmation": True,
                        "prompt_tier": "common",
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

    async def test_prompt_tiers_mark_common_skills_for_fast_router(self) -> None:
        catalog = CapabilityCatalog(_registry(), live_invoker=_Invoker(), min_score=0.10)

        common = await catalog.prompt_entries(scope="common")
        all_entries = await catalog.prompt_entries(scope="all")
        snapshot = await catalog.snapshot()

        common_ids = {item.capability_id for item in common}
        all_ids = {item.capability_id for item in all_entries}

        self.assertIn("soridormi.blink_eyes", common_ids)
        self.assertIn("soridormi.walk_forward", common_ids)
        self.assertIn("soridormi.skill.list", all_ids)
        self.assertNotIn("soridormi.skill.list", common_ids)
        blink = next(
            item
            for item in snapshot["capabilities"]
            if item["capability_id"] == "soridormi.blink_eyes"
        )
        self.assertEqual(blink["prompt_tier"], "common")
        self.assertFalse(blink["prompt_tier_locked"])
        self.assertEqual(blink["prompt_tier_source"], "preset")

    async def test_prompt_tiers_are_loaded_from_preset_data(self) -> None:
        catalog = CapabilityCatalog(
            _registry(),
            live_invoker=_Invoker(),
            min_score=0.10,
            prompt_tier_preset={
                "prompt_tiers": {
                    "soridormi.blink_eyes": {
                        "prompt_tier": "common",
                        "reason": "test preset only promotes blink",
                    }
                }
            },
        )

        common = await catalog.prompt_entries(scope="common")
        common_ids = {item.capability_id for item in common}
        blink = next(item for item in common if item.capability_id == "soridormi.blink_eyes")

        self.assertIn("soridormi.blink_eyes", common_ids)
        self.assertNotIn("soridormi.walk_forward", common_ids)
        self.assertEqual(blink.prompt_tier_source, "preset")
        self.assertEqual(blink.prompt_tier_reason, "test preset only promotes blink")

    async def test_prompt_tier_overrides_can_change_unlocked_entries(self) -> None:
        catalog = CapabilityCatalog(
            _registry(),
            live_invoker=_Invoker(),
            min_score=0.10,
            prompt_tier_overrides={
                "prompt_tiers": {
                    "soridormi.walk_forward": {
                        "prompt_tier": "rare",
                        "source": "experience",
                        "reason": "recent usage below common threshold",
                    },
                    "soridormi.skill.list": {
                        "prompt_tier": "common",
                        "source": "experience",
                        "reason": "used often in diagnostics",
                    },
                }
            },
        )

        common = await catalog.prompt_entries(scope="common")
        snapshot = await catalog.snapshot()
        common_ids = {item.capability_id for item in common}
        walk = next(
            item
            for item in snapshot["capabilities"]
            if item["capability_id"] == "soridormi.walk_forward"
        )
        skill_list = next(
            item
            for item in snapshot["capabilities"]
            if item["capability_id"] == "soridormi.skill.list"
        )

        self.assertNotIn("soridormi.walk_forward", common_ids)
        self.assertIn("soridormi.skill.list", common_ids)
        self.assertEqual(walk["prompt_tier"], "rare")
        self.assertEqual(walk["prompt_tier_source"], "experience")
        self.assertEqual(skill_list["prompt_tier"], "common")
        self.assertFalse(skill_list["prompt_tier_locked"])

    async def test_safety_locked_prompt_tier_cannot_be_promoted_to_fast_common(self) -> None:
        catalog = CapabilityCatalog(
            _registry(),
            live_invoker=_SafetyLockedInvoker(),
            min_score=0.10,
            prompt_tier_overrides={
                "prompt_tiers": {
                    "soridormi.calibrate_floor": {
                        "prompt_tier": "common",
                        "source": "experience",
                    }
                }
            },
        )

        common = await catalog.prompt_entries(scope="common")
        snapshot = await catalog.snapshot()
        common_ids = {item.capability_id for item in common}
        calibrate = next(
            item
            for item in snapshot["capabilities"]
            if item["capability_id"] == "soridormi.calibrate_floor"
        )

        self.assertNotIn("soridormi.calibrate_floor", common_ids)
        self.assertEqual(calibrate["prompt_tier"], "rare")
        self.assertTrue(calibrate["prompt_tier_locked"])
        self.assertEqual(calibrate["prompt_tier_source"], "safety_lock")
        self.assertIn("safety-sensitive", calibrate["prompt_tier_reason"])

    async def test_chromie_speak_is_common_and_executable_for_router_tasks(self) -> None:
        registry = CapabilityRegistry.from_bundles([chromie_capability_bundle()])
        catalog = CapabilityCatalog(registry, live_invoker=None, min_score=0.10)

        common = await catalog.prompt_entries(scope="common")
        speak = next(item for item in common if item.capability_id == "chromie.speak")

        self.assertEqual(speak.prompt_tier, "common")
        self.assertTrue(speak.interaction_executable)
        self.assertEqual(speak.route, "chat")

    async def test_weather_lookup_tool_is_common_router_visible_tool(self) -> None:
        registry = CapabilityRegistry.from_bundles([chromie_capability_bundle()])
        catalog = CapabilityCatalog(registry, live_invoker=None, min_score=0.10)

        common = await catalog.prompt_entries(scope="common")
        weather = next(item for item in common if item.capability_id == "chromie.weather.lookup")

        self.assertEqual(weather.route, "tool")
        self.assertEqual(weather.agent_id, "chromie.weather")
        self.assertEqual(weather.safety_class, "safe_read")
        self.assertFalse(weather.requires_confirmation)
        self.assertFalse(weather.prompt_tier_locked)
        self.assertFalse(weather.interaction_executable)
        self.assertIn("weather_lookup", weather.effects)
        self.assertIn("location", weather.input_schema.get("required", []))
        self.assertIn("tool", weather.tags)
        self.assertEqual(weather.prompt_tier, "common")
        self.assertEqual(weather.hints.get("tool_name"), "weather")

    async def test_chinese_weather_query_matches_weather_lookup_tool(self) -> None:
        registry = CapabilityRegistry.from_bundles([chromie_capability_bundle()])
        catalog = CapabilityCatalog(registry, live_invoker=None, min_score=0.10)

        result = await catalog.search("今天重庆天气怎么样？", language="zh-CN")

        self.assertTrue(result.matched)
        self.assertEqual(result.suggested_route, "tool")
        self.assertIn("tool_agent", result.suggested_agents)
        self.assertEqual(result.matches[0].capability_id, "chromie.weather.lookup")
        self.assertEqual(result.matches[0].route, "tool")

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
