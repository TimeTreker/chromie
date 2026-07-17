from __future__ import annotations

import unittest
from unittest.mock import patch

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest


class _Catalog:
    def __init__(
        self,
        result: CapabilityCatalogResult,
        *,
        snapshot: dict | None = None,
    ) -> None:
        self.result = result
        self.snapshot_data = snapshot or {}
        self.search_calls = 0
        self.snapshot_calls = 0

    async def search(self, **kwargs):
        del kwargs
        self.search_calls += 1
        return self.result

    async def snapshot(self, *, refresh: bool = False):
        del refresh
        self.snapshot_calls += 1
        return self.snapshot_data


class _LlmRouter:
    def __init__(
        self,
        decision: RouteDecision,
        *,
        interrupt_review_decision: RouteDecision | None = None,
    ) -> None:
        self.decision = decision
        self.interrupt_review_decision = interrupt_review_decision
        self.calls = 0
        self.interrupt_review_calls = 0
        self.request: RouteRequest | None = None
        self.interrupt_review_request: RouteRequest | None = None

    async def route(self, request: RouteRequest) -> RouteDecision:
        self.calls += 1
        self.request = request
        return self.decision

    async def review_after_priority_interrupt(
        self,
        request: RouteRequest,
        interrupt_decision: RouteDecision,
    ) -> RouteDecision:
        del interrupt_decision
        self.interrupt_review_calls += 1
        self.interrupt_review_request = request
        return self.interrupt_review_decision or self.decision


class RouterCapabilityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_rules_only_catalog_match_does_not_route_to_capability_agent(self) -> None:
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
        with patch.object(main.settings, "mode", "rules_only"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ):
            decision = await main.route(RouteRequest(text="Move forward."))

        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertNotIn("capability_agent", decision.agents)
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent"],
        )
        self.assertEqual(
            decision.metadata["task_list"][0]["task_type"],
            "speech.answer",
        )
        self.assertEqual(
            decision.metadata["route_merge"]["strategy"],
            "safety_filter_then_quick_intent",
        )
        self.assertEqual(decision.metadata["route_merge"]["task_proposal_count"], 1)
        self.assertEqual(decision.metadata["route_merge"]["final_route"], "chat")
        self.assertEqual(decision.metadata["route_merge"]["selected_stage"], "quick_intent")
        self.assertEqual(decision.metadata["route_merge"]["task_count"], 1)

    async def test_hybrid_deep_thought_for_direct_motion_keeps_model_route(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk forward quickly",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=12,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.88,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought",
                confidence=0.90,
                language="en-US",
                source="llm",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Walk forward for 15 seconds, quickly.")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.intent, "deep_thought")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertNotIn("recovered_from_route", decision.metadata)

    async def test_hybrid_llm_accepts_skill_from_compact_catalog_without_search_match(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="眨两小眼睛。",
            matched=False,
            suggested_route="chat",
            catalog_version=21,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.03,
                    "available": True,
                    "interaction_executable": True,
                    "prompt_tier": "common",
                }
            ],
        )
        snapshot = {
            "catalog_version": 21,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["visual_expression"],
                    "safety_class": "low_risk_action",
                    "requires_confirmation": False,
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "number",
                                "minimum": 1,
                                "maximum": 6,
                                "default": 2,
                            }
                        },
                    },
                },
                {
                    "capability_id": "soridormi.motion.calibrate_floor",
                    "agent_id": "soridormi.motion",
                    "description": "Rare calibration workflow.",
                    "route": "robot_action",
                    "prompt_tier": "rare",
                    "available": True,
                    "interaction_executable": False,
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.blink_eyes",
                confidence=0.86,
                language="zh-CN",
                source="llm",
                reason="selected from common catalog by meaning",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", catalog
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="眨两小眼睛。", language="zh-CN"))

        assert llm_router.request is not None
        self.assertEqual(catalog.snapshot_calls, 1)
        self.assertEqual(catalog.search_calls, 0)
        self.assertIn("common_ability_catalog", llm_router.request.context)
        self.assertIn("common_ability_ids", llm_router.request.context)
        self.assertIn("prompt_capabilities_common", llm_router.request.context)
        self.assertIn("prompt_capabilities_all", llm_router.request.context)
        self.assertEqual(
            llm_router.request.context["common_ability_catalog"][0]["capability_id"],
            "soridormi.blink_eyes",
        )
        self.assertEqual(
            llm_router.request.context["common_ability_ids"],
            ["soridormi.blink_eyes"],
        )
        self.assertEqual(
            llm_router.request.context["prompt_capabilities_common"][0]["capability_id"],
            "soridormi.blink_eyes",
        )
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)

    async def test_hybrid_llm_normalizes_unique_compact_catalog_suffix_without_search_match(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Please blink your eyes twice.",
            matched=False,
            suggested_route="chat",
            catalog_version=22,
            matches=[],
        )
        snapshot = {
            "catalog_version": 22,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["visual_expression"],
                    "safety_class": "low_risk_action",
                    "requires_confirmation": False,
                    "input_schema": {
                        "type": "object",
                        "properties": {"count": {"type": "number", "default": 2}},
                    },
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="blink eyes",
                confidence=0.9,
                language="en-US",
                source="llm",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main,
            "capability_catalog",
            catalog,
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Please blink your eyes twice.", language="en-US")
            )

        self.assertEqual(catalog.search_calls, 0)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("validator normalized catalog capability intent", decision.reason or "")

    async def test_hybrid_llm_delegates_rare_catalog_skill_from_fast_router(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Run floor calibration.",
            matched=False,
            suggested_route="chat",
            catalog_version=23,
            matches=[],
        )
        snapshot = {
            "catalog_version": 23,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["visual_expression"],
                    "safety_class": "low_risk_action",
                    "requires_confirmation": False,
                },
                {
                    "capability_id": "soridormi.motion.calibrate_floor",
                    "description": "Rare floor calibration workflow.",
                    "route": "robot_action",
                    "prompt_tier": "rare",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["physical_motion"],
                    "safety_class": "guarded_operation",
                    "requires_confirmation": True,
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.motion.calibrate_floor",
                confidence=0.91,
                language="en-US",
                source="llm",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main,
            "capability_catalog",
            catalog,
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Run floor calibration.", language="en-US")
            )

        assert llm_router.request is not None
        self.assertEqual(catalog.search_calls, 0)
        self.assertEqual(
            llm_router.request.context["common_ability_ids"],
            ["soridormi.blink_eyes"],
        )
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertIn("outside the fast common ability catalog", decision.reason or "")
        self.assertNotIn("capability_agent", decision.agents)

    async def test_hybrid_llm_excludes_locked_common_catalog_skill_from_fast_router(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Run floor calibration.",
            matched=False,
            suggested_route="chat",
            catalog_version=24,
            matches=[],
        )
        snapshot = {
            "catalog_version": 24,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["visual_expression"],
                    "safety_class": "low_risk_action",
                    "requires_confirmation": False,
                },
                {
                    "capability_id": "soridormi.motion.calibrate_floor",
                    "description": "Locked safety-sensitive calibration workflow.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "prompt_tier_locked": True,
                    "prompt_tier_source": "safety_lock",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["commissioning_no_motion"],
                    "safety_class": "guarded_operation",
                    "requires_confirmation": True,
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.motion.calibrate_floor",
                confidence=0.91,
                language="en-US",
                source="llm",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main,
            "capability_catalog",
            catalog,
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Run floor calibration.", language="en-US")
            )

        assert llm_router.request is not None
        self.assertEqual(
            llm_router.request.context["common_ability_ids"],
            ["soridormi.blink_eyes"],
        )
        self.assertEqual(
            llm_router.request.context["full_ability_catalog"][1]["capability_id"],
            "soridormi.motion.calibrate_floor",
        )
        self.assertEqual(decision.route, "deep_thought")
        self.assertIn("outside the fast common ability catalog", decision.reason or "")

    async def test_catalog_miss_does_not_use_legacy_robot_phrase_rule_by_default(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(query="turn your head left", matched=False)
        with patch.object(main.settings, "mode", "rules_only"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ):
            decision = await main.route(RouteRequest(text="Turn your head left."))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")

    async def test_hybrid_mode_does_not_use_legacy_phrase_rules_after_llm_fallback(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(query="turn left", matched=False)
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="llm unavailable",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main.settings, "rules_first", True
        ), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="turn left"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        assert llm_router.request is not None
        self.assertEqual(llm_router.request.context["candidate_capabilities"], [])

    async def test_hybrid_mode_ignores_query_matches_after_llm_fallback(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="what's your name",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=9,
            matches=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.56,
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
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="llm unavailable",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="What's your name?"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        self.assertNotIn("capability_agent", decision.agents)
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("LLM router unavailable", decision.reason or "")
        self.assertIn("delegating to deep_thought", decision.reason or "")
        self.assertEqual(decision.candidate_capabilities, [])
        self.assertNotIn(
            "task.execute_skill",
            [item["task_type"] for item in decision.metadata["task_list"]],
        )

    async def test_main_validator_rejects_generic_llm_robot_action(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="i mean do you know if the sun is round or rectangular",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=4,
            matches=[
                {
                    "capability_id": "soridormi.turn_in_place",
                    "agent_id": "soridormi.skill",
                    "description": "Rotate left or right with near-zero forward velocity.",
                    "score": 0.72,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="robot_action",
                confidence=0.72,
                language="en-US",
                source="llm",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="I mean, do you know if the sun is round or rectangular?")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")
        self.assertNotIn("capability_agent", decision.agents)
        self.assertIn("llm_robot_action_missing_catalog_skill", decision.reason or "")

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
        self.assertEqual(decision.metadata["route_merge"]["strategy"], "safety_interrupt")
        self.assertEqual(decision.metadata["route_merge"]["final_route"], "interrupt")
        self.assertEqual(decision.metadata["route_merge"]["selected_stage"], "emergency_filter")
        self.assertEqual(decision.metadata["route_merge"]["task_count"], 2)

    async def test_priority_interrupt_can_be_semantically_confirmed_by_second_router(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(query="stop now", matched=False, matches=[])
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
            ),
            interrupt_review_decision=RouteDecision(
                route="interrupt",
                agents=[],
                intent="stop_current_output",
                confidence=0.98,
                language="en-US",
                source="llm",
                reason="The user really asked to stop.",
            ),
        )
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main.settings, "post_interrupt_review_enabled", True
        ), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Stop now."))

        self.assertEqual(decision.route, "interrupt")
        self.assertTrue(decision.interrupt_current)
        self.assertEqual(llm_router.calls, 0)
        self.assertEqual(llm_router.interrupt_review_calls, 1)
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "post_interrupt_review"],
        )
        self.assertEqual(decision.metadata["post_interrupt_review"]["status"], "confirmed")
        self.assertNotIn("post_interrupt_decision", decision.metadata)
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["task.cancel_current_action", "body.stop_motion"],
        )
        self.assertEqual(
            decision.metadata["route_merge"]["strategy"],
            "safety_interrupt_then_semantic_review",
        )
        self.assertEqual(decision.metadata["route_merge"]["selected_stage"], "emergency_filter")
        self.assertEqual(decision.metadata["route_merge"]["proposal_count"], 2)
        self.assertEqual(
            decision.metadata["route_merge"]["task_source_stages"],
            ["emergency_filter"],
        )

    async def test_priority_interrupt_can_record_corrected_second_router_task(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(query="stop", matched=False, matches=[])
        llm_router = _LlmRouter(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="stop_current_output",
                confidence=0.99,
                language="en-US",
                source="llm",
            ),
            interrupt_review_decision=RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="explain_phrase",
                confidence=0.86,
                language="en-US",
                source="llm",
                speak_first="Sorry, I heard that as a stop command; I will answer the phrase instead.",
                reason="The user was asking about the phrase stop by.",
            ),
        )
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main.settings, "post_interrupt_review_enabled", True
        ), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text="Stop.",
                    context={"asr_alternatives": ["Stop by the table means what?"]},
                )
            )

        self.assertEqual(decision.route, "interrupt")
        self.assertTrue(decision.interrupt_current)
        self.assertEqual(decision.metadata["post_interrupt_review"]["status"], "corrected")
        correction = decision.metadata["post_interrupt_decision"]
        self.assertEqual(correction["route"], "chat")
        self.assertEqual(correction["intent"], "explain_phrase")
        self.assertIn("Sorry", correction["speak_first"])
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["task.cancel_current_action", "body.stop_motion", "speech.fast_reply"],
        )
        self.assertTrue(decision.metadata["task_list"][2]["direct_to_tts"])
        self.assertEqual(decision.metadata["task_list"][2]["context_profile"], "fast_minimal")
        self.assertEqual(
            [item["source_stage"] for item in decision.metadata["task_list"]],
            ["emergency_filter", "emergency_filter", "post_interrupt_review"],
        )
        self.assertEqual(
            decision.metadata["route_merge"]["strategy"],
            "safety_interrupt_then_semantic_review",
        )
        self.assertEqual(decision.metadata["route_merge"]["final_route"], "interrupt")
        self.assertEqual(decision.metadata["route_merge"]["selected_stage"], "emergency_filter")
        self.assertEqual(decision.metadata["route_merge"]["task_count"], 3)
        self.assertEqual(
            decision.metadata["route_merge"]["task_source_stages"],
            ["emergency_filter", "post_interrupt_review"],
        )

    async def test_routes_endpoint_lists_quick_and_deep_lanes(self) -> None:
        from router.app import main

        payload = await main.routes()

        self.assertIn("chat", payload["routes"])
        self.assertEqual(payload["mode"], main.settings.mode)
        lanes = {item["id"]: item for item in payload["lanes"]}
        self.assertIn("emergency_filter", lanes)
        self.assertIn("quick_intent", lanes)
        self.assertIn("route_validation", lanes)
        self.assertIn("post_interrupt_review", lanes)
        self.assertIn("deep_thought", lanes)
        self.assertFalse(lanes["emergency_filter"]["llm"])
        self.assertIn("interrupt", lanes["emergency_filter"]["routes"])
        self.assertIn("robot_action", lanes["quick_intent"]["routes"])
        self.assertFalse(lanes["route_validation"]["llm"])
        self.assertIn("interrupt", lanes["post_interrupt_review"]["routes"])
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

    async def test_hybrid_router_uses_common_catalog_snapshot_for_semantic_recovery(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="往前走个15秒。",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=10,
            matches=[],
        )
        snapshot = {
            "catalog_version": 10,
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Human-facing wrapper for natural walking requests.",
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
                intent="capability:soridormi.walk_forward",
                confidence=0.86,
                language="zh-CN",
                source="llm",
                reason="semantic review recovered walking intent",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="往前走个15秒。", language="zh-CN"))

        self.assertEqual(llm_router.calls, 1)
        assert llm_router.request is not None
        self.assertEqual(
            llm_router.request.context["common_ability_catalog"][0]["capability_id"],
            "soridormi.walk_forward",
        )
        self.assertEqual(llm_router.request.context["candidate_capabilities"], [])
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)
        self.assertEqual(
            decision.candidate_capabilities[0]["capability_id"],
            "soridormi.walk_forward",
        )

    async def test_hybrid_router_delegates_low_confidence_body_command_to_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walking forward quickly until i tell you stop",
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
        snapshot = {
            "catalog_version": 8,
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "available": True,
                    "interaction_executable": True,
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod the head yes.",
                    "available": True,
                    "interaction_executable": True,
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
            ],
        }
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
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Walking forward quickly until I tell you stop.")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertEqual(decision.language, "en-US")
        self.assertIn("quick router confidence", decision.reason or "")
        self.assertIn("quick_route=robot_action", decision.reason or "")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent", "deep_thought"],
        )
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["cognition.delegate_deep_thought", "cognition.deep_think"],
        )
        self.assertCountEqual(
            [item["capability_id"] for item in decision.candidate_capabilities],
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )

    async def test_schema_invalid_quick_actions_handoff_to_capability_planner(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk at 0.2 speed for 10 seconds and nod twice",
            matched=False,
            suggested_route="chat",
            catalog_version=30,
            matches=[],
        )
        snapshot = {
            "catalog_version": 30,
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_velocity",
                    "description": "Track a bounded body velocity command.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "vx_mps": {"type": "number"},
                            "duration_s": {"type": "number"},
                        },
                        "additionalProperties": False,
                    },
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "description": "Visible yes nod.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "input_schema": {
                        "type": "object",
                        "properties": {"count": {"type": "number"}},
                        "additionalProperties": False,
                    },
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="compound_common_catalog_task",
                confidence=0.91,
                language="en-US",
                source="llm",
                actions=[
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"speed": "0.2", "duration": "10"},
                        "sequence": 0,
                    },
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                        "sequence": 1,
                    },
                ],
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Walk at 0.2 speed for 10 seconds and nod twice.")
            )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "compound_common_catalog_task")
        self.assertEqual(decision.actions, [])
        self.assertIn("capability_agent", decision.agents)
        self.assertEqual(
            decision.metadata["quick_router_action_handoff"]["status"],
            "planner_required",
        )
        self.assertIn(
            "unknown args",
            " ".join(decision.metadata["quick_router_action_handoff"]["errors"]),
        )
        self.assertNotIn("deepthinking_agent", decision.agents)

    async def test_validator_does_not_infer_compound_plan_from_user_phrase(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left",
            matched=False,
            suggested_route="chat",
            catalog_version=35,
            matches=[],
        )
        snapshot = {
            "catalog_version": 35,
            "capabilities": [
                {
                    "capability_id": "chromie.speak",
                    "description": "Speak to the user.",
                    "route": "chat",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.walk_velocity",
                    "description": "Track a bounded body velocity command.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "description": "Visible yes nod.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.turn_in_place",
                    "description": "Rotate left or right in place.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="chromie.speak",
                confidence=0.95,
                language="en-US",
                source="llm",
                metadata={
                    "route_items": [
                        {
                            "route": "robot_action",
                            "intent": "chromie.speak",
                            "confidence": 0.95,
                            "lane": "skill_runtime",
                            "context_profile": "capability_safety",
                        }
                    ]
                },
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text=(
                        "walk ahead at 0.2 speed for 10 seconds and then "
                        "nod your head twice, then turn left"
                    ),
                    language="en-US",
                )
            )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertEqual(decision.actions, [])
        self.assertNotIn("quick_router_action_handoff", decision.metadata)
        self.assertNotIn("compound_common_catalog_task", str(decision.metadata))

    async def test_hybrid_low_confidence_handoff_uses_llm_speak_first_thinking_ack(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="figure out the safe way to help me with this setup",
            matched=False,
            suggested_route="chat",
            catalog_version=22,
            matches=[],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="unknown",
                confidence=0.44,
                language="en-US",
                source="llm",
                speak_first="Give me a moment to think that through.",
                reason="common catalog did not clearly fit",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Figure out the safe way to help me with this setup.")
            )

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertEqual(decision.speak_first, "Give me a moment to think that through.")
        self.assertTrue(decision.metadata["thinking_ack_allowed"])
        self.assertEqual(decision.metadata["thinking_ack_source"], "quick_llm_speak_first")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["cognition.delegate_deep_thought", "speech.thinking_ack", "cognition.deep_think"],
        )
        thinking_task = next(
            item
            for item in decision.metadata["task_list"]
            if item["task_type"] == "speech.thinking_ack"
        )
        self.assertEqual(thinking_task["text"], "Give me a moment to think that through.")

    async def test_hybrid_router_keeps_llm_deep_thought_without_phrase_recovery(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="hey groomy walking forward for 10 seconds quickly please",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_low_confidence",
                confidence=0.55,
                language="auto",
                source="llm",
                reason="quick model was uncertain",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Hey, Groomy, walking forward for 10 seconds quickly, please.")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertFalse(decision.metadata["thinking_ack_allowed"])
        self.assertIn(
            "cognition.deep_think",
            [item["task_type"] for item in decision.metadata["task_list"]],
        )
        self.assertNotIn(
            "speech.thinking_ack",
            [item["task_type"] for item in decision.metadata["task_list"]],
        )

    async def test_hybrid_router_keeps_complex_deep_thought_direct_motion(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="wal forward for 15 seconds quickly",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_complex_reasoning",
                confidence=0.90,
                language="en-US",
                source="llm",
                reason="quick route treated this as complex reasoning",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Wal forward for 15 seconds, quickly."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_complex_reasoning")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertNotIn("recovered_from_route", decision.metadata)

    async def test_hybrid_router_keeps_planning_text_in_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="make a plan to walk forward safely",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.91,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_planning",
                confidence=0.82,
                language="en-US",
                source="llm",
                reason="explicit planning request",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Make a plan to walk forward safely."))

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_planning")
        self.assertIn("deepthinking_agent", decision.agents)

    async def test_hybrid_router_delegates_low_confidence_without_catalog_match_to_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="build an unusual robot latency strategy",
            matched=False,
            catalog_version=8,
            matches=[],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="unknown",
                confidence=0.50,
                language="auto",
                source="llm",
                reason="weak quick intent",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Build an unusual robot latency strategy."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertIn("quick router confidence", decision.reason or "")
        self.assertIn("deepthinking_agent", decision.agents)
        self.assertFalse(decision.metadata["thinking_ack_allowed"])

    async def test_hybrid_router_keeps_low_confidence_simple_chat_out_of_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Hello, how are you doing?",
            matched=False,
            catalog_version=8,
            matches=[],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="unknown",
                confidence=0.0,
                language="en-US",
                source="llm",
                reason="weak quick intent",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Hello, how are you doing?"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("conversation_agent", decision.agents)
        self.assertNotIn("deepthinking_agent", decision.agents)

    async def test_hybrid_router_treats_chat_speak_skill_as_output_channel(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Hello, how are you.",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=8,
            matches=[],
        )
        snapshot = {
            "catalog_version": 8,
            "capabilities": [
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message to the user through TTS.",
                    "route": "chat",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["user_interaction", "audio_output"],
                    "safety_class": "low_risk_action",
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="capability:chromie.speak",
                confidence=0.95,
                language="en-US",
                source="llm",
                reason="review model corrected speech-only greeting",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Hello, how are you."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("chromie.speak as chat output channel", decision.reason or "")
        self.assertIn("conversation_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)

    async def test_hybrid_router_treats_robot_action_speak_skill_as_chat(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="How are you.",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=25,
            matches=[],
        )
        snapshot = {
            "catalog_version": 25,
            "capabilities": [
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message to the user through TTS.",
                    "route": "chat",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["user_interaction", "audio_output"],
                    "safety_class": "low_risk_action",
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:chromie.speak",
                confidence=1.0,
                language="en-US",
                source="llm",
                reason="bad quick-router speech skill route",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="How are you.", language="en-US"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertEqual(decision.actions, [])
        self.assertIn("chromie.speak as chat output channel", decision.reason or "")
        self.assertIn("conversation_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)

    async def test_hybrid_router_corrects_generic_robot_action_when_catalog_says_chat(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Hello.",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.03,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="robot_action",
                confidence=1.0,
                language="en-US",
                source="llm",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Hello."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertIn("conversation_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertIn("llm_robot_action_missing_catalog_skill", decision.reason or "")

    async def test_hybrid_router_accepts_exact_robot_action_from_compact_catalog(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Hello, are you.",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=8,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.03,
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        )
        snapshot = {
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the simulated social eyes.",
                    "score": 0.0,
                    "available": True,
                    "interaction_executable": True,
                    "prompt_tier": "common",
                    "route": "robot_action",
                }
            ]
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.blink_eyes",
                confidence=1.0,
                language="en-US",
                source="llm",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", catalog
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Hello, are you."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(catalog.search_calls, 0)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)

    async def test_hybrid_router_normalizes_raw_skill_id_robot_action_from_compact_catalog(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Walk forward for 15 seconds, please.",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=8,
            matches=[],
        )
        snapshot = {
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Human-facing wrapper for natural walking requests.",
                    "score": 0.0,
                    "available": True,
                    "interaction_executable": True,
                    "prompt_tier": "common",
                    "route": "robot_action",
                }
            ]
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="soridormi.walk_forward",
                confidence=0.92,
                language="en-US",
                source="llm",
            )
        )

        catalog = _Catalog(result, snapshot=snapshot)
        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", catalog
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="Walk forward for 15 seconds, please."))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(catalog.search_calls, 0)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("validator normalized exact capability intent", decision.reason or "")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)

    async def test_hybrid_router_does_not_recover_invalid_llm_interrupt_through_catalog(self) -> None:
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
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertFalse(decision.interrupt_current)
        self.assertTrue(decision.needs_agent)
        self.assertIn("conversation_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual(
            [item["stage"] for item in decision.metadata["route_stage_outputs"]],
            ["emergency_filter", "quick_intent"],
        )
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_invalid_interrupt_recovery_does_not_use_catalog_for_discourse_marker(self) -> None:
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
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_invalid_interrupt_recovery_does_not_use_catalog_for_appearance_statement(self) -> None:
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
        self.assertIn("conversation_agent", decision.agents)
        self.assertIn("speaker_agent", decision.agents)
        self.assertIn("deterministic-only route interrupt", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_llm_fallback_delegates_social_compliment_without_catalog_motion(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="you look beautiful don't you",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=9,
            matches=[
                {
                    "capability_id": "soridormi.bow",
                    "agent_id": "soridormi.skill",
                    "description": "Perform a small social bow gesture.",
                    "score": 0.52,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="llm_router_error:ReadTimeout",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="You look beautiful, don't you?"))

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        self.assertEqual(decision.source, "fallback")
        self.assertIn("delegating to deep_thought", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["cognition.delegate_deep_thought", "cognition.deep_think"],
        )

    async def test_quick_router_fallback_delegates_to_deep_thought_without_phrase_rules(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="please think carefully and split the work to add long-term memory",
            matched=True,
            suggested_route="chat",
            suggested_agents=["conversation_agent", "speaker_agent"],
            catalog_version=10,
            matches=[
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message to the user.",
                    "score": 0.42,
                    "available": True,
                    "interaction_executable": False,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="llm_router_error:ReadTimeout",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text="Please think carefully and split the work to add long-term memory to Chromie."
                )
            )

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        self.assertEqual(decision.source, "fallback")
        self.assertFalse(decision.metadata.get("thinking_ack_allowed", True))

    async def test_hybrid_router_does_not_synthesize_actions_with_semantic_parser(self) -> None:
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
        snapshot = {
            "catalog_version": 8,
            "capabilities": [
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "available": True,
                    "interaction_executable": True,
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "agent_id": "soridormi.skill",
                    "description": "Nod the head yes.",
                    "available": True,
                    "interaction_executable": True,
                    "route": "robot_action",
                    "prompt_tier": "common",
                },
            ],
        }
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
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(
            main, "llm_router", llm_router
        ):
            decision = await main.route(RouteRequest(text="请向前走十秒，然后点头两次。"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_velocity")
        self.assertEqual(decision.actions, [])
        self.assertIn(
            "soridormi.walk_velocity",
            [item["capability_id"] for item in decision.candidate_capabilities],
        )


    async def test_short_asr_fragment_robot_action_is_downgraded_to_clarify(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="B.",
            matched=False,
            suggested_route="chat",
            catalog_version=31,
            matches=[],
        )
        snapshot = {
            "catalog_version": 31,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["visual_expression"],
                    "safety_class": "low_risk_action",
                    "requires_confirmation": False,
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.blink_eyes",
                confidence=0.95,
                language="en-US",
                source="llm",
                reason="badly over-confident fragment match",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="B.", language="en-US"))

        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.intent, "clarify_insufficient_information")
        self.assertEqual(decision.confidence, 0.0)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertNotIn("safety_agent", decision.agents)
        self.assertIn("I only heard", decision.speak_first or "")
        self.assertEqual(
            decision.metadata["confidence_calibration"]["status"],
            "downgraded_to_clarify",
        )
        self.assertEqual(
            decision.metadata["confidence_calibration"]["model_intent"],
            "capability:soridormi.blink_eyes",
        )

    async def test_short_asr_fragment_chat_is_downgraded_to_clarify(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="B.",
            matched=False,
            suggested_route="chat",
            catalog_version=36,
            matches=[],
        )
        snapshot = {
            "catalog_version": 36,
            "capabilities": [
                {
                    "capability_id": "chromie.speak",
                    "description": "Speak to the user.",
                    "route": "chat",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.95,
                language="en-US",
                source="llm",
                reason="model treated an isolated letter as conversation",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="B.", language="en-US"))

        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.intent, "clarify_insufficient_information")
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("I only heard", decision.speak_first or "")
        self.assertEqual(
            decision.metadata["confidence_calibration"]["reason"],
            "isolated_low_information_asr_fragment",
        )

    async def test_llm_unavailable_short_asr_fragment_clarifies_without_deep_thought(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="B.",
            matched=False,
            suggested_route="chat",
            catalog_version=34,
            matches=[],
        )
        snapshot = {
            "catalog_version": 34,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="llm_router_error:ReadTimeout",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="B.", language="en-US"))

        self.assertEqual(decision.route, "clarify")
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.intent, "clarify_insufficient_information")
        self.assertNotIn("deepthinking_agent", decision.agents)
        self.assertNotIn("capability_agent", decision.agents)
        self.assertIn("I only heard", decision.speak_first or "")
        calibration = decision.metadata["confidence_calibration"]
        self.assertEqual(calibration["status"], "downgraded_to_clarify")
        self.assertIn("llm_router_unavailable", calibration["reason"])

    async def test_short_fragment_with_strong_followup_context_is_not_downgraded(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="B.",
            matched=False,
            suggested_route="chat",
            catalog_version=32,
            matches=[],
        )
        snapshot = {
            "catalog_version": 32,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.blink_eyes",
                confidence=0.95,
                language="en-US",
                source="llm",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text="B.",
                    language="en-US",
                    context={"awaiting_user_choice": True},
                )
            )

        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("capability_agent", decision.agents)

    async def test_missing_body_skill_tells_user_without_substitution(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="Please fly up to the ceiling.",
            matched=False,
            suggested_route="chat",
            catalog_version=33,
            matches=[],
        )
        snapshot = {
            "catalog_version": 33,
            "capabilities": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "route": "robot_action",
                    "prompt_tier": "common",
                    "available": True,
                    "interaction_executable": True,
                }
            ],
        }
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="capability:soridormi.fly_up",
                confidence=0.92,
                language="en-US",
                source="llm",
                reason="model invented unavailable flying skill",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="Please fly up to the ceiling.", language="en-US")
            )

        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "semantic_capability_planning")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)
        self.assertIsNone(decision.speak_first)
        self.assertEqual(
            decision.metadata["desired_abilities"][0]["status"],
            "semantic_planning_required",
        )
        self.assertEqual(
            decision.metadata["capability_grounding"]["status"],
            "unresolved_requires_planner",
        )
        self.assertEqual(
            decision.metadata["router_semantic_handoff"]["authority"],
            "advisory",
        )



if __name__ == "__main__":
    unittest.main()
