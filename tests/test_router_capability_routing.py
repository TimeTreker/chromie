from __future__ import annotations

import unittest
from unittest.mock import patch

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteDecision, RouteRequest
from shared.chromie_contracts.task_proposal import TaskProposal


class _Catalog:
    def __init__(
        self,
        result: CapabilityCatalogResult,
        *,
        snapshot: dict | None = None,
    ) -> None:
        self.result = result
        self.snapshot_data = snapshot or {}

    async def search(self, **kwargs):
        del kwargs
        return self.result

    async def snapshot(self):
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
        with patch.object(main.settings, "mode", "rules_only"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ):
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
        proposal = TaskProposal.model_validate(decision.metadata["task_proposals"][0])
        self.assertEqual(proposal.skill_id, "soridormi.walk_forward")
        self.assertEqual(proposal.state, "advisory")
        self.assertTrue(proposal.effectful)
        self.assertEqual(
            decision.metadata["route_merge"]["strategy"],
            "safety_filter_then_quick_intent",
        )
        self.assertEqual(decision.metadata["route_merge"]["task_proposal_count"], 1)
        self.assertEqual(decision.metadata["route_merge"]["final_route"], "robot_action")
        self.assertEqual(decision.metadata["route_merge"]["selected_stage"], "quick_intent")
        self.assertEqual(decision.metadata["route_merge"]["task_count"], 1)
        self.assertEqual(
            decision.candidate_capabilities[0]["capability_id"],
            "soridormi.walk_forward",
        )

    async def test_hybrid_deep_thought_for_direct_motion_recovers_to_catalog_robot_action(self) -> None:
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
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("capability_agent", decision.agents)
        self.assertIn("safety_agent", decision.agents)
        self.assertEqual(decision.metadata["recovered_from_route"], "deep_thought")

    async def test_hybrid_chat_for_chinese_blink_asr_recovers_to_catalog_robot_action(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="眨两小眼睛。",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=13,
            matches=[
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "score": 0.87,
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
                confidence=0.90,
                language="zh-CN",
                source="llm",
                reason="quick router treated the ASR phrase as conversation",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="眨两小眼睛。", language="zh-CN"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertEqual(decision.metadata["recovered_from_route"], "chat")
        self.assertEqual(
            decision.metadata["task_list"][0]["capability_id"],
            "soridormi.blink_eyes",
        )

    async def test_hybrid_llm_selects_skill_from_common_prompt_catalog_without_search_match(self) -> None:
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

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result, snapshot=snapshot)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="眨两小眼睛。", language="zh-CN"))

        assert llm_router.request is not None
        self.assertIn("prompt_capabilities_common", llm_router.request.context)
        self.assertEqual(
            llm_router.request.context["prompt_capabilities_common"][0]["capability_id"],
            "soridormi.blink_eyes",
        )
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertEqual(
            decision.metadata["task_list"][0]["capability_id"],
            "soridormi.blink_eyes",
        )
        self.assertIn(
            "soridormi.blink_eyes",
            [item["capability_id"] for item in decision.candidate_capabilities],
        )

    async def test_hybrid_wrong_low_score_robot_action_for_chinese_blink_is_corrected(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="眨两小眼睛。",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=14,
            matches=[
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "score": 0.87,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.03,
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
                confidence=0.90,
                language="zh-CN",
                source="llm",
                reason="quick router selected walking from a noisy Chinese blink phrase",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="眨两小眼睛。", language="zh-CN"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.blink_eyes")
        self.assertIn("corrected low-score capability selection", decision.reason or "")
        self.assertEqual(
            decision.metadata["task_list"][0]["capability_id"],
            "soridormi.blink_eyes",
        )

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
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.intent, "general_conversation")
        assert llm_router.request is not None
        self.assertEqual(llm_router.request.context["candidate_capabilities"], [])

    async def test_hybrid_mode_delegates_catalog_robot_candidates_after_llm_fallback(self) -> None:
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
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        self.assertNotIn("capability_agent", decision.agents)
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("LLM router unavailable", decision.reason or "")
        self.assertIn("delegating catalog-bounded robot request", decision.reason or "")
        self.assertEqual(
            decision.candidate_capabilities[0]["capability_id"],
            "soridormi.walk_velocity",
        )
        self.assertNotIn(
            "task.execute_skill",
            [item["task_type"] for item in decision.metadata["task_list"]],
        )

    async def test_hybrid_llm_fallback_for_chinese_blink_delegates_without_catalog_skill(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="眨两小眼睛。",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=15,
            matches=[
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the robot eyes visibly.",
                    "score": 0.86,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.walk_velocity",
                    "agent_id": "soridormi.skill",
                    "description": "Track a bounded body velocity command.",
                    "score": 0.03,
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
                language="zh-CN",
                source="fallback",
                reason="llm unavailable",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="眨两小眼睛。", language="zh-CN"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_router_unavailable")
        self.assertNotIn("conversation_agent", decision.agents)
        self.assertIn("delegating catalog-bounded robot request", decision.reason or "")
        task_types = [item["task_type"] for item in decision.metadata["task_list"]]
        self.assertIn("cognition.deep_think", task_types)
        self.assertNotIn("task.execute_skill", task_types)
        self.assertNotIn(
            "capability_id",
            decision.metadata["task_list"][0],
        )

    async def test_rules_only_catalog_decision_ignores_weak_factual_word_overlap(self) -> None:
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
        self.assertEqual(decision.intent, "general_conversation")

    async def test_hybrid_llm_fallback_ignores_weak_factual_word_overlap(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="i think the moon is not round do you agree with me",
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
        llm_router = _LlmRouter(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=0.45,
                language="en-US",
                source="fallback",
                reason="invalid_llm_router_response: no JSON object in model response",
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(text="I think the moon is not round. Do you agree with me?")
            )

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")
        self.assertEqual(decision.intent, "general_conversation")

    async def test_main_validator_does_not_phrase_override_llm_robot_action(self) -> None:
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
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.source, "llm")
        self.assertIn("capability_agent", decision.agents)

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
            ["task.cancel_current_action", "body.stop_motion", "speech.answer"],
        )
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

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
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

    async def test_hybrid_router_preserves_low_score_candidates_for_semantic_recovery(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="往前走个15秒。",
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=10,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Human-facing wrapper for natural walking requests.",
                    "score": 0.0,
                    "available": True,
                    "interaction_executable": True,
                    "effects": ["physical_motion"],
                    "route": "robot_action",
                }
            ],
        )
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
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(RouteRequest(text="往前走个15秒。", language="zh-CN"))

        self.assertEqual(llm_router.calls, 1)
        assert llm_router.request is not None
        self.assertEqual(
            llm_router.request.context["candidate_capabilities"][0]["capability_id"],
            "soridormi.walk_forward",
        )
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
        self.assertEqual(
            [item["capability_id"] for item in decision.candidate_capabilities],
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )

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

    async def test_hybrid_router_recovers_complex_deep_thought_direct_motion(self) -> None:
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
        self.assertEqual(decision.source, "catalog")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_forward")
        self.assertIn("capability_agent", decision.agents)
        self.assertEqual(decision.metadata["recovered_from_route"], "deep_thought")
        self.assertEqual(
            decision.metadata["recovered_from_intent"],
            "deep_thought_complex_reasoning",
        )

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

    async def test_llm_fallback_does_not_use_catalog_motion_for_social_compliment(self) -> None:
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

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.intent, "general_conversation")
        self.assertEqual(decision.source, "fallback")
        self.assertIn("speech-only social", decision.reason or "")
        self.assertEqual(
            [item["task_type"] for item in decision.metadata["task_list"]],
            ["speech.answer"],
        )

    async def test_catalog_chat_does_not_swallow_explicit_deep_thought_request(self) -> None:
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
        self.assertEqual(decision.intent, "deep_thought_planning")
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
            main, "capability_catalog", _Catalog(result)
        ), patch.object(
            main, "llm_router", llm_router
        ):
            decision = await main.route(RouteRequest(text="请向前走十秒，然后点头两次。"))

        self.assertEqual(llm_router.calls, 1)
        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "capability:soridormi.walk_velocity")
        self.assertEqual(decision.actions, [])
        self.assertEqual(
            decision.candidate_capabilities[0]["capability_id"],
            "soridormi.walk_velocity",
        )

    async def test_hybrid_router_accepts_llm_compound_common_actions_with_speech(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk forward, tell a joke, then blink",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=21,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.88,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message through TTS.",
                    "score": 0.42,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the simulated social eyes.",
                    "score": 0.76,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="compound_common_catalog_task",
                confidence=0.87,
                language="en-US",
                source="llm",
                actions=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 20},
                        "sequence": 0,
                        "timing": "sequential",
                        "confidence": 0.91,
                    },
                    {
                        "capability_id": "chromie.speak",
                        "args": {
                            "text": "Why did the robot cross the room? To get to the charging side.",
                            "style": "brief",
                        },
                        "sequence": 1,
                        "timing": "parallel",
                        "confidence": 0.86,
                    },
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 6},
                        "sequence": 2,
                        "timing": "sequential",
                        "confidence": 0.88,
                    },
                ],
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text=(
                        "Please walk forward for 20 seconds, after that blink your "
                        "little eyes 6 times, tell me a joke when you are walking."
                    )
                )
            )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "compound_common_catalog_task")
        self.assertEqual(
            [item["capability_id"] for item in decision.actions],
            ["soridormi.walk_forward", "chromie.speak", "soridormi.blink_eyes"],
        )
        self.assertEqual(decision.actions[1]["timing"], "parallel")
        self.assertEqual(
            [item["confidence"] for item in decision.actions],
            [0.91, 0.86, 0.88],
        )
        self.assertEqual(decision.metadata["quick_router_action_count"], 3)
        self.assertTrue(decision.metadata["quick_router_compound_tasks"])
        self.assertEqual(decision.metadata["quick_router_action_min_confidence"], 0.86)
        task_list = decision.metadata["task_list"]
        self.assertEqual(
            [item["task_type"] for item in task_list],
            ["task.execute_skill", "speech.speak", "task.execute_skill"],
        )
        self.assertEqual(task_list[1]["capability_id"], "chromie.speak")
        self.assertEqual(task_list[1]["confidence"], 0.86)
        proposals = [
            TaskProposal.model_validate(item)
            for item in decision.metadata["task_proposals"]
        ]
        self.assertEqual(
            [item.skill_id for item in proposals],
            ["soridormi.walk_forward", "chromie.speak", "soridormi.blink_eyes"],
        )
        self.assertEqual(proposals[1].metadata["confidence"], 0.86)
        self.assertFalse(proposals[1].effectful)

    async def test_hybrid_router_delegates_low_confidence_action_in_compound_plan(self) -> None:
        from router.app import main

        result = CapabilityCatalogResult(
            query="walk forward, tell a joke, then blink",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
            catalog_version=22,
            matches=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "agent_id": "soridormi.skill",
                    "description": "Walk forward for a bounded duration.",
                    "score": 0.88,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "chromie.speak",
                    "agent_id": "chromie.speech",
                    "description": "Speak a short message through TTS.",
                    "score": 0.42,
                    "available": True,
                    "interaction_executable": True,
                },
                {
                    "capability_id": "soridormi.blink_eyes",
                    "agent_id": "soridormi.skill",
                    "description": "Blink the simulated social eyes.",
                    "score": 0.76,
                    "available": True,
                    "interaction_executable": True,
                },
            ],
        )
        llm_router = _LlmRouter(
            RouteDecision(
                route="robot_action",
                agents=["capability_agent", "safety_agent", "speaker_agent"],
                intent="compound_common_catalog_task",
                confidence=0.87,
                language="en-US",
                source="llm",
                actions=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 20},
                        "sequence": 0,
                        "timing": "sequential",
                        "confidence": 0.89,
                    },
                    {
                        "capability_id": "chromie.speak",
                        "args": {
                            "text": "I can try a joke while walking.",
                            "style": "brief",
                        },
                        "sequence": 1,
                        "timing": "parallel",
                        "confidence": 0.31,
                    },
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 6},
                        "sequence": 2,
                        "timing": "sequential",
                        "confidence": 0.84,
                    },
                ],
            )
        )

        with patch.object(main.settings, "mode", "hybrid"), patch.object(
            main, "capability_catalog", _Catalog(result)
        ), patch.object(main, "llm_router", llm_router):
            decision = await main.route(
                RouteRequest(
                    text=(
                        "Please walk forward for 20 seconds, blink six times, "
                        "and tell me a joke while walking."
                    )
                )
            )

        self.assertEqual(decision.source, "llm")
        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        self.assertEqual(decision.speak_first, "Give me a moment to think that through.")
        self.assertIn("action[1] confidence 0.31 below threshold", decision.reason or "")
        self.assertTrue(decision.metadata["thinking_ack_allowed"])
        self.assertEqual(
            decision.metadata["thinking_ack_source"],
            "quick_validator_default_speak_first",
        )
        review = decision.metadata["quick_router_review_request"]
        self.assertEqual(review["execution_state"], "not_committed")
        self.assertEqual(review["quick_route"], "robot_action")
        self.assertEqual(review["quick_actions"][1]["confidence"], 0.31)
        self.assertEqual(
            [item["skill_id"] for item in review["quick_task_proposals"]],
            ["soridormi.walk_forward", "chromie.speak", "soridormi.blink_eyes"],
        )
        task_types = [item["task_type"] for item in decision.metadata["task_list"]]
        self.assertEqual(
            task_types,
            ["cognition.delegate_deep_thought", "speech.thinking_ack", "cognition.deep_think"],
        )
        self.assertNotIn("task.execute_skill", task_types)
        self.assertNotIn("speech.speak", task_types)


if __name__ == "__main__":
    unittest.main()
