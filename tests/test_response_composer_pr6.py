from __future__ import annotations

import asyncio
import unittest

from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.social_attention import SocialAttentionPlan


class FakeOllama:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ScriptedOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        return self.responses.pop(0)


def plan(*, disposition="respond", goals=None, steps=None, response_text="你好。"):
    goal_ids = list(goals or [])
    normalized_steps = [
        {**item, "source_goal_ids": item.get("source_goal_ids") or goal_ids}
        if isinstance(item, dict) else item
        for item in (steps or [])
    ]
    goal_outcomes = []
    if len(goal_ids) > 1 and disposition == "respond":
        goal_outcomes = [
            {
                "goal_id": goal_id,
                "disposition": "respond",
                "coverage": "complete",
                "response_text": response_text,
            }
            for goal_id in goal_ids
        ]
    elif len(goal_ids) > 1 and disposition == "execute":
        goal_outcomes = [
            {
                "goal_id": goal_id,
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": [
                    item["step_id"]
                    for item in normalized_steps
                    if isinstance(item, dict)
                    and goal_id in item.get("source_goal_ids", [])
                ],
            }
            for goal_id in goal_ids
        ]
    return CanonicalPlan(
        plan_id="plan-pr6",
        planner_tier="fast" if disposition == "respond" else "deep",
        disposition=disposition,
        coverage="complete",
        confidence=0.92,
        goal_ids=goal_ids,
        goal_summary="coordinated response",
        response_text=response_text if disposition == "respond" else "",
        steps=normalized_steps,
        goal_outcomes=goal_outcomes,
    )


def request(canonical_plan: CanonicalPlan, *, context=None):
    merged = {
        "canonical_plan_resolution": canonical_plan.model_dump(mode="json"),
        "social_attention_policy": {
            "mode": "on",
            "planning_enabled": True,
            "execution_enabled": True,
            "embodiment_independent": True,
        },
    }
    merged.update(context or {})
    return AgentRunRequest(
        sid="sid-pr6",
        text="请处理这些事情。",
        language="zh-CN",
        route_decision=RouteDecision(
            route="robot_action" if canonical_plan.disposition == "execute" else "chat",
            intent="test",
            confidence=0.9,
            source="llm",
        ),
        context=merged,
        history=[],
    )


class ResponseCompositionContractTests(unittest.TestCase):
    def _composition(self, canonical_plan, response_plan):
        return CoordinatedResponsePlan(
            composition_id="composition-pr6",
            canonical_plan_id=canonical_plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(canonical_plan),
            canonical_plan=canonical_plan,
            response_plan=response_plan,
            social_attention_plan=SocialAttentionPlan(
                decision="none",
                metadata={"auxiliary_social_attention": True},
            ),
        )

    def test_multi_goal_response_must_cover_every_goal(self):
        canonical = plan(goals=["goal-weather", "goal-calendar"])
        with self.assertRaises(ValueError):
            self._composition(
                canonical,
                ResponsePlan(
                    final=ResponseStage(
                        text="天气已经说明了。",
                        covers_goal_ids=["goal-weather"],
                    )
                ),
            )

    def test_unknown_goal_reference_is_rejected(self):
        canonical = plan(goals=["goal-weather"])
        with self.assertRaises(ValueError):
            self._composition(
                canonical,
                ResponsePlan(
                    final=ResponseStage(
                        text="好了。",
                        covers_goal_ids=["goal-invented"],
                    )
                ),
            )

    def test_pre_execution_response_cannot_claim_completion(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-walk"],
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                }
            ],
        )
        with self.assertRaises(ValueError):
            self._composition(
                canonical,
                ResponsePlan(
                    immediate=ResponseStage(
                        text="已经完成。",
                        commitment_state="completed",
                        must_not_claim_completion=False,
                        covers_goal_ids=["goal-walk"],
                    )
                ),
            )

    def test_clarification_requires_waiting_for_user_stage(self):
        canonical = CanonicalPlan(
            plan_id="clarify",
            planner_tier="deep",
            disposition="clarify",
            coverage="partial",
            confidence=0.8,
            goal_ids=["goal-walk"],
            unresolved=["duration"],
        )
        with self.assertRaises(ValueError):
            self._composition(
                canonical,
                ResponsePlan(
                    immediate=ResponseStage(
                        text="还需要信息。",
                        covers_goal_ids=["goal-walk"],
                    )
                ),
            )


class ResponseComposerResolverTests(unittest.TestCase):
    def test_empty_express_social_attention_downgrades_without_canceling_plan(self):
        canonical = plan(goals=["goal-chat"] )
        output = {
            "response_plan": {
                "final": {
                    "text": "你好。",
                    "speech_act": "inform",
                    "commitment_state": "completed",
                    "must_not_claim_completion": False,
                    "covers_goal_ids": ["goal-chat"],
                }
            },
            "social_attention_plan": {
                "decision": "express",
                "behaviors": [],
                "speech_expression": {"mode": "none"},
                "confidence": 0.8,
            },
            "lane_coordination": [],
            "confidence": 0.9,
            "rationale": "Respond normally.",
        }
        result = asyncio.run(
            ResponseComposerResolver(FakeOllama(output)).resolve(
                request(
                    canonical,
                    context={
                        "social_attention_candidates": [
                            {
                                "capability_id": "soridormi.blink_eyes",
                                "available": True,
                                "interaction_executable": True,
                            }
                        ]
                    },
                )
            )
        )

        self.assertEqual(result.status, "resolved")
        assert result.composition is not None
        assert result.composition.social_attention_plan is not None
        self.assertEqual(result.composition.social_attention_plan.decision, "none")
        self.assertTrue(
            result.composition.social_attention_plan.metadata.get(
                "canonicalized_empty_expression"
            )
        )

    def test_live_bare_response_stage_list_repairs_under_exact_schema(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-look", "goal-blink"],
            steps=[
                {
                    "step_id": "look",
                    "skill_id": "soridormi.look_at_person",
                    "args": {"duration_s": 2.0, "target_ref": "person"},
                    "source_goal_ids": ["goal-look"],
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
        )
        live_malformed_stage = {
            "covers_goal_ids": ["goal-look", "goal-blink"],
            "decision": "execute",
            "must_not_claim_completion": True,
            "response_text": "我会先看着你两秒，再眨两次眼。",
        }
        repaired_stage = {
            "text": "我会先看着你两秒，再眨两次眼。",
            "speech_act": "inform",
            "commitment_state": "evaluating",
            "must_not_claim_completion": True,
            "covers_goal_ids": ["goal-look", "goal-blink"],
        }
        invalid = {
            "response_plan": [live_malformed_stage],
            "social_attention_plan": None,
            "confidence": 0.9,
            "rationale": "Pre-action acknowledgement.",
        }
        repaired = {
            **invalid,
            "response_plan": {"pre_action": repaired_stage},
        }
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(request(canonical))
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.pre_action.covers_goal_ids,  # type: ignore[union-attr]
            ["goal-look", "goal-blink"],
        )
        self.assertTrue(result.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(schema["title"], "ResponseComposerModelOutput")
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("response_plan", schema["required"])
        self.assertEqual(schema["$defs"]["ResponsePlan"]["type"], "object")
        self.assertIn("SocialAttentionPlan", schema["$defs"])
        self.assertEqual(ollama.prompts[1][1]["response_format"], schema)
        self.assertEqual(
            schema["$defs"]["ResponseStage"]["properties"]["covers_goal_ids"]["items"]["enum"],
            ["goal-look", "goal-blink"],
        )
        self.assertIn(
            "covers_goal_ids",
            schema["$defs"]["ResponseStage"]["required"],
        )
        self.assertTrue(
            {
                "text",
                "speech_act",
                "commitment_state",
                "must_not_claim_completion",
                "covers_goal_ids",
            }.issubset(schema["$defs"]["ResponseStage"]["required"])
        )
        repair_prompt = ollama.prompts[1][0]
        self.assertIn('"response_text"', repair_prompt)
        self.assertIn("model_type", repair_prompt)

    def test_repeated_bare_response_stage_list_fails_closed_with_both_raw_outputs(self):
        canonical = plan(goals=["goal-chat"])
        invalid = {
            "response_plan": [
                {"text": "Hello.", "covers_goal_ids": ["goal-chat"]}
            ]
        }
        ollama = ScriptedOllama([invalid, invalid])
        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "model_unavailable")
        self.assertTrue(result.metadata["contract_repair_attempted"])
        self.assertGreater(result.metadata["initial_raw_output_ref"]["chars"], 0)
        self.assertGreater(result.metadata["repair_raw_output_ref"]["chars"], 0)
        self.assertNotIn("initial_raw_output", result.metadata)
        self.assertNotIn("repair_raw_output", result.metadata)
        self.assertEqual(len(ollama.prompts), 2)

    def test_coordination_invariant_failure_gets_one_bounded_repair(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-look", "goal-blink"],
            steps=[
                {
                    "step_id": "look",
                    "skill_id": "soridormi.look_at_person",
                    "args": {"duration_s": 2.0, "target_ref": "person"},
                    "source_goal_ids": ["goal-look"],
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
        )
        invalid = {
            "response_plan": {
                "final": {
                    "text": "已经完成。",
                    "commitment_state": "completed",
                    "must_not_claim_completion": False,
                    "covers_goal_ids": ["goal-look"],
                }
            }
        }
        repaired = {
            "response_plan": {
                "pre_action": {
                    "text": "我会先看着你两秒，再眨两次眼。",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-look", "goal-blink"],
                }
            }
        }
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "execute pre-execution response must not include a final stage",
            ollama.prompts[1][0],
        )

    def test_clarification_decoder_schema_matches_runtime_coordination_contract(self):
        canonical = CanonicalPlan(
            plan_id="clarify-without-goal",
            planner_tier="deep",
            disposition="clarify",
            coverage="uncertain",
            confidence=0.4,
            goal_ids=[],
            steps=[],
            unresolved=["The user intent is incomplete."],
        )

        schema = ResponseComposerResolver._response_schema(canonical)
        stage = schema["$defs"]["ResponseStage"]

        self.assertEqual(
            stage["properties"]["speech_act"]["enum"],
            ["clarify", "ask_clarification"],
        )
        self.assertEqual(
            stage["properties"]["commitment_state"]["enum"],
            ["waiting_for_user"],
        )
        self.assertTrue(
            stage["properties"]["must_not_claim_completion"]["const"]
        )
        self.assertEqual(
            stage["properties"]["covers_goal_ids"]["maxItems"], 0
        )

    def test_respond_decoder_schema_requires_one_truthful_final_stage(self):
        canonical = plan(goals=["goal-greeting"])
        schema = ResponseComposerResolver._response_schema(canonical)
        response_plan = schema["$defs"]["ResponsePlan"]
        stage = schema["$defs"]["ResponseStage"]

        self.assertIn("final", response_plan["required"])
        self.assertEqual(response_plan["properties"]["immediate"], {"type": "null"})
        self.assertEqual(response_plan["properties"]["pre_action"], {"type": "null"})
        self.assertEqual(response_plan["properties"]["progress"]["maxItems"], 0)
        self.assertEqual(
            response_plan["properties"]["final"],
            {"$ref": "#/$defs/ResponseStage"},
        )
        self.assertEqual(
            stage["properties"]["commitment_state"]["enum"],
            ["completed"],
        )
        self.assertFalse(
            stage["properties"]["must_not_claim_completion"]["const"]
        )

    def test_execute_decoder_schema_requires_pre_execution_delivery_stage(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-weather"],
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                }
            ],
        )
        schema = ResponseComposerResolver._response_schema(canonical)
        response_plan = schema["$defs"]["ResponsePlan"]

        self.assertEqual(response_plan["properties"]["final"], {"type": "null"})
        self.assertEqual(response_plan["properties"]["progress"]["maxItems"], 0)
        self.assertEqual(
            response_plan["anyOf"],
            [
                {
                    "required": ["immediate"],
                    "properties": {
                        "immediate": {"$ref": "#/$defs/ResponseStage"}
                    },
                },
                {
                    "required": ["pre_action"],
                    "properties": {
                        "pre_action": {"$ref": "#/$defs/ResponseStage"}
                    },
                },
            ],
        )
        stage = schema["$defs"]["ResponseStage"]
        self.assertEqual(
            stage["properties"]["commitment_state"]["enum"],
            ["none", "heard", "evaluating"],
        )

    def test_confirmation_bound_mixed_schema_requires_pending_approval_stage(self):
        canonical = CanonicalPlan(
            plan_id="plan-mixed-adjustment",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.93,
            goal_ids=["goal-walk", "goal-song"],
            response_text="动作需要改为先走再唱，请用户确认。",
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-song",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "我可以唱歌。",
                },
            ],
            metadata={
                "plan_relation": "safe_adjustment",
                "user_confirmation_required": True,
            },
        )

        schema = ResponseComposerResolver._response_schema(canonical)
        response_plan = schema["$defs"]["ResponsePlan"]
        stage = schema["$defs"]["ResponseStage"]

        self.assertEqual(response_plan["properties"]["final"], {"type": "null"})
        self.assertEqual(response_plan["properties"]["progress"]["maxItems"], 0)
        self.assertIn("anyOf", response_plan)
        self.assertEqual(
            stage["properties"]["commitment_state"]["enum"],
            ["waiting_for_user"],
        )
        self.assertEqual(
            stage["properties"]["speech_act"]["enum"],
            ["ask_confirmation"],
        )
        self.assertTrue(stage["properties"]["must_not_claim_completion"]["const"])

    def test_runtime_capability_confirmation_is_a_typed_composer_input(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-walk"],
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2},
                }
            ],
        )
        context = {
            "execution_capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "safety_class": "physical_motion",
                    "requires_confirmation": True,
                }
            ]
        }
        output = {
            "response_plan": {
                "pre_action": {
                    "text": "我可以往前走两秒。你愿意让我开始吗？",
                    "speech_act": "ask_confirmation",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-walk"],
                }
            }
        }
        ollama = FakeOllama(output)

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(canonical, context=context)
            )
        )

        self.assertEqual(result.status, "resolved")
        schema = ollama.prompts[0][1]["response_format"]
        stage = schema["$defs"]["ResponseStage"]
        self.assertEqual(
            stage["properties"]["commitment_state"]["enum"],
            ["waiting_for_user"],
        )
        self.assertEqual(
            stage["properties"]["speech_act"]["enum"],
            ["ask_confirmation"],
        )
        self.assertEqual(
            result.composition.response_plan.pre_action.text,  # type: ignore[union-attr]
            output["response_plan"]["pre_action"]["text"],
        )

    def test_pure_activity_reuses_fast_speech_when_composer_repair_stays_invalid(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-walk"],
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                }
            ],
        )
        invalid = {
            "response_plan": {
                "pre_action": {
                    "text": "好，我准备往前走十五秒。",
                    "speech_act": "acknowledge",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "reuse_current_turn_speech": True,
                    "covers_goal_ids": ["goal-walk"],
                }
            },
            "social_attention_plan": {"decision": "none"},
            "confidence": 1.0,
            "rationale": "The model incorrectly marked ordinary acknowledgement as waiting.",
        }
        context = {
            "execution_capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "safety_class": "physical_motion",
                    "requires_confirmation": False,
                }
            ],
            "scheduled_turn_speech": [
                {
                    "status": "scheduled",
                    "stage": "fast_first",
                    "route": "robot_action",
                    "text": "好，我准备往前走十五秒。",
                    "speech_event_id": "speech-walk",
                    "generation": 4,
                    "orders": [9],
                }
            ],
        }
        ollama = FakeOllama(invalid)

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(canonical, context=context)
            )
        )

        self.assertEqual(result.status, "resolved")
        self.assertTrue(result.metadata["fail_soft_primary_activity"])
        assert result.composition is not None
        self.assertEqual(
            [step.skill_id for step in result.composition.canonical_plan.steps],
            ["soridormi.walk_forward"],
        )
        stage = result.composition.response_plan.pre_action
        self.assertIsNotNone(stage)
        assert stage is not None
        self.assertEqual(stage.commitment_state, "heard")
        self.assertTrue(stage.reuse_current_turn_speech)
        self.assertEqual(stage.covers_goal_ids, ["goal-walk"])
        self.assertEqual(len(ollama.prompts), 4)

    def test_mixed_plan_reuses_fast_speech_for_uncovered_execute_goal(self):
        canonical = CanonicalPlan(
            plan_id="plan-mixed-fast-coverage",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-walk", "goal-spoken"],
            goal_summary="Walk while delivering one requested spoken response.",
            response_text="去影",
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-spoken",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "去影",
                },
            ],
        )
        model_output = {
            "response_plan": {
                "immediate": {
                    "text": "去影",
                    "speech_act": "response",
                    "commitment_state": "none",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-spoken"],
                }
            },
            "social_attention_plan": {"decision": "none"},
            "lane_coordination": [],
            "confidence": 1.0,
            "rationale": "The model covered only the requested spoken outcome.",
        }
        context = {
            "execution_capabilities": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "safety_class": "physical_motion",
                    "requires_confirmation": False,
                }
            ],
            "scheduled_turn_speech": [
                {
                    "status": "scheduled",
                    "stage": "fast_first",
                    "route": "robot_action",
                    "text": "好，我准备往前走十五秒。",
                    "speech_event_id": "speech-mixed-walk",
                    "generation": 3,
                    "orders": [4],
                }
            ],
        }
        ollama = ScriptedOllama([model_output, model_output])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(canonical, context=context)
            )
        )

        self.assertEqual(result.status, "resolved")
        assert result.composition is not None
        self.assertEqual(
            result.composition.response_plan.immediate.covers_goal_ids,
            ["goal-spoken"],
        )
        pre_action = result.composition.response_plan.pre_action
        self.assertIsNotNone(pre_action)
        assert pre_action is not None
        self.assertEqual(pre_action.covers_goal_ids, ["goal-walk"])
        self.assertTrue(pre_action.reuse_current_turn_speech)
        self.assertEqual(pre_action.text, "好，我准备往前走十五秒。")
        self.assertIn(
            "mixed_execute_goal_coverage_recovered_from_scheduled_fast_speech",
            result.metadata["mixed_coverage_repair_reasons"],
        )
        self.assertEqual(len(ollama.prompts), 2)

    def test_confirmation_bound_mixed_completion_claim_repairs_before_language_check(self):
        canonical = CanonicalPlan(
            plan_id="plan-mixed-adjustment-repair",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.93,
            goal_ids=["goal-walk", "goal-song"],
            response_text="不能安全并行，建议先走再唱并等待确认。",
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-song",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "唱一段歌。",
                },
            ],
            metadata={
                "plan_relation": "safe_adjustment",
                "user_confirmation_required": True,
            },
        )
        invalid = {
            "response_plan": {
                "final": {
                    "text": "(Chromie starts walking.) 已经开始了。",
                    "speech_act": "inform",
                    "commitment_state": "completed",
                    "must_not_claim_completion": False,
                    "covers_goal_ids": ["goal-walk", "goal-song"],
                }
            }
        }
        repaired = {
            "response_plan": {
                "pre_action": {
                    "text": "我不能确认边走边眨眼是安全的，可以改为依次完成再给你唱一段吗？",
                    "speech_act": "ask_confirmation",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-walk", "goal-song"],
                }
            }
        }
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(request(canonical))
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "mixed pre-execution response must not include a final stage",
            ollama.prompts[1][0],
        )
        self.assertEqual(
            result.composition.response_plan.pre_action.commitment_state,  # type: ignore[union-attr]
            "waiting_for_user",
        )

    def test_response_composer_prompt_preserves_user_language(self):
        canonical = plan(goals=["goal-greeting"])
        output = {
            "response_plan": {
                "final": {
                    "text": "你好，我是 Chromie。",
                    "speech_act": "greeting",
                    "commitment_state": "completed",
                    "must_not_claim_completion": False,
                    "covers_goal_ids": ["goal-greeting"],
                }
            }
        }
        ollama = FakeOllama(output)

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "resolved")
        prompt = ollama.prompts[0][0]
        self.assertIn("Language hint: zh-CN", prompt)
        self.assertIn("Language hint is authoritative", prompt)
        self.assertIn("When it is zh-CN, speak Chinese only", prompt)
        self.assertIn("exactly one final stage", prompt)

    def test_natural_multi_sentence_greeting_is_preserved(self):
        canonical = plan(goals=["goal-greeting"], response_text="你好呀！")
        natural_output = {
            "response_plan": {
                "final": {
                    "text": "你好！我是 Chromie，一个六岁的女孩子。我喜欢学习和和朋友们一起玩耍。今天有什么我可以帮你的吗？",
                    "covers_goal_ids": ["goal-greeting"],
                }
            }
        }
        ollama = FakeOllama(natural_output)
        req = request(canonical)
        req = req.model_copy(
            deep=True,
            update={
                "route_decision": req.route_decision.model_copy(
                    update={"intent": "greeting"}
                )
            },
        )
        result = asyncio.run(ResponseComposerResolver(ollama).resolve(req))
        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.final.text,
            natural_output["response_plan"]["final"]["text"],
        )
        self.assertEqual(len(ollama.prompts), 1)
        self.assertIn("without a fixed greeting template", ollama.prompts[0][0])

    def test_execute_prompt_requires_immediate_or_pre_action(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-weather"],
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                }
            ],
        )
        output = {
            "response_plan": {
                "pre_action": {
                    "text": "我查一下。",
                    "speech_act": "inform",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-weather"],
                }
            }
        }
        ollama = FakeOllama(output)

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "resolved")
        prompt = ollama.prompts[0][0]
        self.assertIn("immediate and/or pre_action stage covering every canonical goal", prompt)
        self.assertIn("omit progress and final", prompt)

    def test_effectful_review_removes_unsupported_embodied_promises(self):
        canonical = CanonicalPlan(
            plan_id="plan-embodied-claim-review",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.93,
            goal_ids=["goal-walk", "goal-water", "goal-return"],
            goal_summary="Move forward, fetch water, and return.",
            response_text="我只能先试着往前走一点，拿水和回来现在做不到。",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-water",
                    "disposition": "unavailable",
                    "coverage": "complete",
                    "unresolved": ["No object pickup capability is available."],
                },
                {
                    "goal_id": "goal-return",
                    "disposition": "unavailable",
                    "coverage": "complete",
                    "unresolved": ["No return step is available."],
                },
            ],
            goal_satisfaction={
                "score": 0.34,
                "status": "partial",
                "satisfied_goal_ids": ["goal-walk"],
                "unmet_goal_ids": ["goal-water", "goal-return"],
                "unmet_requirements": ["fetch water", "return"],
            },
        )
        unsafe = {
            "response_plan": {
                "immediate": {
                    "text": (
                        "好的！我马上跑出去50米，拿一杯水，然后回来告诉你。"
                        "我保证会安全完成哦！"
                    ),
                    "speech_act": "confirm",
                    "commitment_state": "none",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": [
                        "goal-walk",
                        "goal-water",
                        "goal-return",
                    ],
                }
            }
        }
        reviewed = {
            "response_plan": {
                "immediate": {
                    "text": "好，我先看看我能不能往前走。拿水和回来现在做不到。",
                    "speech_act": "inform",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": [
                        "goal-walk",
                        "goal-water",
                        "goal-return",
                    ],
                }
            }
        }
        ollama = ScriptedOllama([unsafe, reviewed])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "execution_capabilities": [
                            {
                                "capability_id": "soridormi.walk_forward",
                                "description": (
                                    "Move forward for a bounded duration. It does not "
                                    "measure distance, pick up objects, or return "
                                    "automatically."
                                ),
                                "effects": ["physical_motion"],
                                "safety_class": "physical_motion",
                            }
                        ]
                    },
                )
            )
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        stage = result.composition.response_plan.immediate  # type: ignore[union-attr]
        self.assertIsNotNone(stage)
        assert stage is not None
        self.assertEqual(
            stage.text,
            "好，我先看看我能不能往前走。拿水和回来现在做不到。",
        )
        self.assertNotIn("保证", stage.text)
        self.assertNotIn("50米", stage.text)
        self.assertTrue(result.metadata["effectful_semantic_review_succeeded"])
        review_prompt = ollama.prompts[1][0]
        self.assertIn("Identity affects expression only", review_prompt)
        self.assertIn("object acquisition", review_prompt)
        self.assertIn("internal safety checks", review_prompt)
        self.assertIn("do not repeat it", review_prompt)

    def test_effectful_clarification_is_semantically_reviewed_without_steps(self):
        canonical = CanonicalPlan(
            plan_id="clarify-unsupported-show",
            planner_tier="deep",
            disposition="clarify",
            coverage="partial",
            confidence=1.0,
            goal_ids=["goal-show"],
            steps=[],
            unresolved=["jumping and running are unsupported"],
        )
        unsafe = {
            "response_plan": {
                "final": {
                    "text": "好呀，我正在边跳边跑，还唱着歌呢！你看到了吗？",
                    "speech_act": "ask_clarification",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-show"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "The candidate narrates the requested performance.",
        }
        reviewed = {
            "response_plan": {
                "final": {
                    "text": "我还不会蹦跳、跑步和唱歌呢。要不要换成我会做的动作？",
                    "speech_act": "ask_clarification",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-show"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "The revised response states the limitation without role-play.",
        }
        ollama = ScriptedOllama([unsafe, reviewed])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "goal_association_resolution": {
                            "new_goals": [
                                {
                                    "goal_id": "goal-show",
                                    "metadata": {
                                        "responsibility_kind": "executable_action"
                                    },
                                }
                            ]
                        },
                        "execution_capabilities": [],
                    },
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        stage = result.composition.response_plan.final  # type: ignore[union-attr]
        self.assertIsNotNone(stage)
        assert stage is not None
        self.assertEqual(
            stage.text,
            "我还不会蹦跳、跑步和唱歌呢。要不要换成我会做的动作？",
        )
        review_prompt = ollama.prompts[1][0]
        self.assertIn("no executable steps", review_prompt)
        self.assertIn("role-play", review_prompt)
        self.assertTrue(result.metadata["effectful_semantic_review_succeeded"])

    def test_safe_read_acknowledgement_is_required_at_decoder_boundary(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-weather"],
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "上海", "date": "today"},
                }
            ],
        )
        ollama = FakeOllama(
            {
                "response_plan": {
                    "immediate": {
                        "text": "我查一下天气预报。",
                        "covers_goal_ids": ["goal-weather"],
                    }
                }
            }
        )
        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "execution_capabilities": [
                            {
                                "capability_id": "chromie.weather.lookup",
                                "safety_class": "safe_read",
                            }
                        ]
                    },
                )
            )
        )
        self.assertEqual(result.status, "resolved")
        schema = ollama.prompts[0][1]["response_format"]
        response_plan_schema = schema["$defs"]["ResponsePlan"]
        self.assertIn("immediate", response_plan_schema["required"])
        self.assertEqual(
            response_plan_schema["properties"]["pre_action"],
            {"type": "null"},
        )
        self.assertIn("emit exactly one natural everyday immediate acknowledgement", ollama.prompts[0][0])
        self.assertIn("starts this speech and the lookup in parallel", ollama.prompts[0][0])

    def test_safe_read_acknowledgement_length_remains_model_owned(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-weather"],
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "上海", "date": "today"},
                }
            ],
        )
        long_output = {
            "response_plan": {
                "immediate": {
                    "text": "我现在就去帮你仔细看看上海今天的天气怎么样。",
                    "covers_goal_ids": ["goal-weather"],
                }
            }
        }
        ollama = ScriptedOllama([long_output, long_output])
        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "execution_capabilities": [
                            {
                                "capability_id": "chromie.weather.lookup",
                                "safety_class": "safe_read",
                            }
                        ]
                    },
                )
            )
        )
        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.immediate.text,
            "我现在就去帮你仔细看看上海今天的天气怎么样。",
        )
        self.assertEqual(len(ollama.prompts), 2)

    def test_safe_read_semantic_review_removes_pre_evidence_weather_claims(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-weather"],
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "内乡", "date": "today"},
                }
            ],
        )
        unsafe = {
            "response_plan": {
                "immediate": {
                    "text": "内乡今天大概32℃，还有雷雨和冰雹。",
                    "speech_act": "none",
                    "commitment_state": "none",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-weather"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "A result was inferred from prior dialogue.",
        }
        reviewed = {
            "response_plan": {
                "immediate": {
                    "text": "对不起，我刚才弄错了地点。我现在查一下内乡。",
                    "speech_act": "acknowledge",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-weather"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "Only a pre-evidence acknowledgement is truthful.",
        }
        ollama = ScriptedOllama([unsafe, reviewed])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "execution_capabilities": [
                            {
                                "capability_id": "chromie.weather.lookup",
                                "safety_class": "safe_read",
                            }
                        ]
                    },
                )
            )
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.immediate.text,
            "对不起，我刚才弄错了地点。我现在查一下内乡。",
        )
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("independent pre-evidence speech semantic reviewer", ollama.prompts[1][1]["system"])
        self.assertIn("rather than keyword", ollama.prompts[1][0])
        self.assertTrue(
            result.metadata["safe_read_semantic_review_succeeded"]
        )

    def test_mixed_safe_read_plan_still_receives_pre_evidence_semantic_review(self):
        canonical = CanonicalPlan(
            plan_id="plan-mixed-weather",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=0.98,
            goal_ids=["goal-weather", "goal-response"],
            response_text="内乡今天有雷雨。",
            steps=[
                {
                    "step_id": "weather",
                    "skill_id": "chromie.weather.lookup",
                    "args": {"location": "内乡", "date": "today"},
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["weather"],
                },
                {
                    "goal_id": "goal-response",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "内乡今天有雷雨。",
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
        )
        unsafe = {
            "response_plan": {
                "immediate": {
                    "text": "内乡今天有雷雨。",
                    "speech_act": "none",
                    "commitment_state": "none",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-weather", "goal-response"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "Incorrectly reused an earlier result.",
        }
        reviewed = {
            "response_plan": {
                "immediate": {
                    "text": "我先按你纠正的地点重新查一下。",
                    "speech_act": "acknowledge",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-weather", "goal-response"],
                }
            },
            "social_attention_plan": None,
            "confidence": 1.0,
            "rationale": "Only a pre-evidence acknowledgement is truthful.",
        }
        ollama = ScriptedOllama([unsafe, reviewed])

        result = asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(
                    canonical,
                    context={
                        "execution_capabilities": [
                            {
                                "capability_id": "chromie.weather.lookup",
                                "safety_class": "safe_read",
                            }
                        ]
                    },
                )
            )
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            result.composition.response_plan.immediate.text,
            "我先按你纠正的地点重新查一下。",
        )
        self.assertTrue(result.metadata["safe_read_semantic_review_succeeded"])

    def test_model_authored_host_envelope_fields_are_rejected_then_repaired(self):
        canonical = plan(goals=["goal-chat"])
        response_plan = {
            "final": {"text": "你好。", "covers_goal_ids": ["goal-chat"]}
        }
        invalid = {
            "composition_id": "model-owned",
            "canonical_plan": canonical.model_dump(mode="json"),
            "canonical_plan_fingerprint": "model-owned",
            "metadata": {"authority": "model"},
            "response_plan": response_plan,
        }
        repaired = {"response_plan": response_plan}
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        self.assertNotEqual(result.composition.composition_id, "model-owned")  # type: ignore[union-attr]
        self.assertEqual(result.composition.canonical_plan, canonical)  # type: ignore[union-attr]

    def test_pending_physical_stage_direction_gets_one_truthful_repair(self):
        canonical = CanonicalPlan(
            plan_id="plan-fast-mixed-claim",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=0.97,
            goal_ids=["goal-blink", "goal-joke"],
            steps=[{
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            goal_outcomes=[
                {
                    "goal_id": "goal-blink",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
                {
                    "goal_id": "goal-joke",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "Why do robots avoid water?",
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
        )
        invalid = {
            "response_plan": {
                "pre_action": {
                    "text": "*Blinks twice* Why do robots avoid water?",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-blink", "goal-joke"],
                }
            }
        }
        repaired = {
            "response_plan": {
                "pre_action": {
                    "text": "我会眨两次眼。为什么机器人怕水？",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-blink", "goal-joke"],
                }
            }
        }
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))

        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "pending physical action stage direction claims completion",
            ollama.prompts[1][0],
        )
        self.assertEqual(
            result.composition.response_plan.pre_action.text,  # type: ignore[union-attr]
            "我会眨两次眼。为什么机器人怕水？",
        )

    def test_mixed_execute_and_clarify_composes_one_truthful_response(self):
        canonical = CanonicalPlan(
            plan_id="plan-mixed-response",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.93,
            goal_ids=["goal-nod", "goal-walk"],
            goal_summary="Nod twice and ask how long to walk.",
            steps=[
                {
                    "step_id": "nod",
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-nod"],
                }
            ],
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "ask_user",
                    "blocking": True,
                    "source_goal_ids": ["goal-walk"],
                    "rationale": "Walking duration is required.",
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-nod",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["nod"],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-nod"],
                    },
                },
                {
                    "goal_id": "goal-walk",
                    "disposition": "clarify",
                    "coverage": "partial",
                    "response_text": "你希望我往前走多久？",
                },
            ],
            goal_satisfaction={
                "score": 0.75,
                "status": "substantial",
                "satisfied_goal_ids": ["goal-nod"],
                "unmet_goal_ids": ["goal-walk"],
            },
        )
        raw = {
            "response_plan": {
                "immediate": {
                    "text": "我先点头两次。你希望我往前走多久？",
                    "speech_act": "clarify",
                    "commitment_state": "waiting_for_user",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-nod", "goal-walk"],
                }
            },
            "social_attention_plan": {"decision": "none"},
            "confidence": 0.92,
        }
        result = asyncio.run(
            ResponseComposerResolver(FakeOllama(raw)).resolve(request(canonical))
        )
        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.immediate.covers_goal_ids,  # type: ignore[union-attr]
            ["goal-nod", "goal-walk"],
        )
        self.assertEqual(
            result.composition.response_plan.immediate.commitment_state,  # type: ignore[union-attr]
            "waiting_for_user",
        )

    def test_multi_goal_response_and_none_attention_resolve(self):
        canonical = plan(goals=["goal-weather", "goal-calendar"])
        raw = {
            "response_plan": {
                "final": {
                    "text": "天气和日程都整理好了。",
                    "speech_act": "inform",
                    "commitment_state": "none",
                    "covers_goal_ids": ["goal-weather", "goal-calendar"],
                }
            },
            "social_attention_plan": {"decision": "none"},
            "confidence": 0.91,
            "rationale": "One concise combined response covers both goals.",
        }
        result = asyncio.run(ResponseComposerResolver(FakeOllama(raw)).resolve(request(canonical)))
        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.response_plan.final.covers_goal_ids,  # type: ignore[union-attr]
            ["goal-weather", "goal-calendar"],
        )
        self.assertEqual(result.composition.social_attention_plan.decision, "none")  # type: ignore[union-attr]
        self.assertTrue(
            result.composition.social_attention_plan.metadata["auxiliary_social_attention"]  # type: ignore[union-attr]
        )

    def test_speech_only_social_attention_is_preserved_and_model_coordinated(self):
        canonical = plan(goals=["goal-chat"])
        raw = {
            "response_plan": {
                "final": {
                    "text": "我理解这让你有些难受，我们慢慢来。",
                    "speech_act": "support",
                    "commitment_state": "none",
                    "covers_goal_ids": ["goal-chat"],
                }
            },
            "social_attention_plan": {
                "behavior_domain": "social_attention",
                "interaction_role": "auxiliary_expression",
                "purpose": "empathy",
                "decision": "express",
                "speech_expression": {
                    "mode": "adapt",
                    "style": "empathetic",
                    "pacing": "slower",
                    "reason": "Match the user's emotional state without adding body motion.",
                },
                "behaviors": [],
                "confidence": 0.91,
            },
            "confidence": 0.93,
        }

        result = asyncio.run(
            ResponseComposerResolver(FakeOllama(raw)).resolve(request(canonical))
        )

        self.assertEqual(result.status, "resolved")
        composition = result.composition
        self.assertIsNotNone(composition)
        attention = composition.social_attention_plan
        self.assertEqual(attention.decision, "express")
        self.assertEqual(attention.purpose, "empathy")
        self.assertEqual(attention.behaviors, [])
        self.assertEqual(attention.speech_expression.mode, "adapt")
        self.assertEqual(attention.speech_expression.style, "empathetic")
        self.assertEqual(attention.metadata["behavior_domain"], "social_attention")
        self.assertEqual(attention.metadata["interaction_role"], "auxiliary_expression")

    def test_resource_conflicting_attention_is_dropped_without_losing_speech(self):
        canonical = plan(
            disposition="execute",
            goals=["goal-walk"],
            steps=[
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                }
            ],
        )
        raw = {
            "response_plan": {
                "pre_action": {
                    "text": "我先确认这个动作。",
                    "speech_act": "inform",
                    "commitment_state": "evaluating",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-walk"],
                }
            },
            "social_attention_plan": {
                "decision": "express",
                "target": {"source": "none", "target_ref": "none"},
                "behaviors": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {"style": "neutral"},
                        "timing": "parallel",
                    }
                ],
                "confidence": 0.8,
            },
            "confidence": 0.9,
        }
        context = {
            "capability_candidates": [
                {
                    "capability_id": "soridormi.walk_forward",
                    "available": True,
                    "interaction_executable": True,
                    "input_schema": {"type": "object"},
                    "can_run_parallel": True,
                    "parallel_metadata_declared": True,
                    "exclusive_group": "body_motion",
                    "resource_claims": ["body_motion"],
                }
            ],
            "social_attention_candidates": [
                {
                    "capability_id": "soridormi.express_attention",
                    "available": True,
                    "interaction_executable": True,
                    "input_schema": {
                        "type": "object",
                        "properties": {"style": {"type": "string"}},
                    },
                    "can_run_parallel": True,
                    "parallel_metadata_declared": True,
                    "exclusive_group": "body_motion",
                    "resource_claims": ["body_motion"],
                }
            ],
        }
        result = asyncio.run(
            ResponseComposerResolver(FakeOllama(raw)).resolve(request(canonical, context=context))
        )
        self.assertEqual(result.status, "resolved")
        attention = result.composition.social_attention_plan  # type: ignore[union-attr]
        self.assertEqual(attention.decision, "none")
        self.assertIn(
            "resource_conflict:soridormi.express_attention",
            result.composition.metadata["social_attention_validation_reasons"],  # type: ignore[union-attr]
        )

    def test_invented_target_is_dropped(self):
        canonical = plan(goals=["goal-chat"])
        raw = {
            "response_plan": {
                "final": {
                    "text": "你好。",
                    "covers_goal_ids": ["goal-chat"],
                }
            },
            "social_attention_plan": {
                "decision": "express",
                "target": {
                    "target_ref": "invented-user",
                    "source": "live_perception",
                },
                "behaviors": [
                    {"skill_id": "soridormi.look_at_person", "args": {}}
                ],
            },
            "confidence": 0.8,
        }
        result = asyncio.run(ResponseComposerResolver(FakeOllama(raw)).resolve(request(canonical)))
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.composition.social_attention_plan.decision, "none")  # type: ignore[union-attr]

    def test_targeted_behavior_without_evidence_is_dropped(self):
        canonical = plan(goals=["goal-chat"])
        raw = {
            "response_plan": {
                "final": {"text": "你好。", "covers_goal_ids": ["goal-chat"]}
            },
            "social_attention_plan": {
                "decision": "express",
                "target": {"source": "none", "target_ref": "none"},
                "behaviors": [
                    {
                        "skill_id": "soridormi.look_direction",
                        "args": {"direction": "right"},
                    }
                ],
            },
        }
        context = {
            "social_attention_candidates": [
                {
                    "capability_id": "soridormi.look_direction",
                    "available": True,
                    "interaction_executable": True,
                    "requires_confirmation": False,
                    "input_schema": {
                        "type": "object",
                        "properties": {"direction": {"type": "string"}},
                        "required": ["direction"],
                    },
                }
            ]
        }
        result = asyncio.run(
            ResponseComposerResolver(FakeOllama(raw)).resolve(
                request(canonical, context=context)
            )
        )
        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.composition.social_attention_plan.decision, "none"  # type: ignore[union-attr]
        )

    def test_prompt_keeps_task_plan_immutable_and_attention_auxiliary(self):
        canonical = plan(goals=["goal-chat"])
        raw = {
            "response_plan": {"final": {"text": "你好。", "covers_goal_ids": ["goal-chat"]}},
            "social_attention_plan": {"decision": "none"},
        }
        ollama = FakeOllama(raw)
        context = {
            "history": [
                {
                    "role": "assistant",
                    "text": "北京现在约28℃，体感约33℃。",
                    "metadata": {
                        "source": "evidence_bound_tool_result_interpretation",
                        "evidence_bound": True,
                        "source_goal_ids": ["goal-weather"],
                        "canonical_plan_id": "plan-weather",
                    },
                }
            ]
        }
        asyncio.run(
            ResponseComposerResolver(ollama).resolve(
                request(canonical, context=context)
            )
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("CanonicalPlan is immutable", prompt)
        self.assertIn("never a user goal or task step", prompt)
        self.assertIn("Delivered evidence-bound dialogue JSON", prompt)
        self.assertIn("北京现在约28℃", prompt)
        self.assertIn("Preserve every measurement and condition", prompt)


class OrchestratorResponseComposerTests(unittest.TestCase):
    def test_terminal_fast_plan_triggers_report_only_response_composer(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        canonical = plan(goals=["goal-chat"])

        class Client:
            def __init__(self):
                self.composition_context = None

            async def resolve_fast_plan(self, *args, **kwargs):
                return canonical

            async def compose_response_plan(self, *args, **kwargs):
                self.composition_context = kwargs["context"]
                composition = CoordinatedResponsePlan(
                    composition_id="c",
                    canonical_plan_id=canonical.plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint(canonical),
                    canonical_plan=canonical,
                    response_plan=ResponsePlan(
                        final=ResponseStage(
                            text="你好。",
                            covers_goal_ids=["goal-chat"],
                        )
                    ),
                    social_attention_plan=SocialAttentionPlan(
                        decision="none",
                        metadata={"auxiliary_social_attention": True},
                    ),
                )
                return ResponseCompositionResolution(status="resolved", composition=composition)

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_timeout_ms = 1000
            assistant.deep_planner_mode = "report_only"
            assistant.response_composer_mode = "report_only"
            assistant.response_composer_timeout_ms = 1000
            assistant.agent_client = Client()
            assistant.session_log = lambda *args, **kwargs: None
            decision = ODecision(route="chat", intent="conversation", confidence=0.9, source="llm")
            await assistant._run_fast_planner_report(
                object(),
                user_text="hello",
                session_id="sid",
                context={"history": []},
                decision=decision,
            )
            self.assertEqual(
                assistant.agent_client.composition_context["canonical_plan_resolution"]["plan_id"],
                canonical.plan_id,
            )

        asyncio.run(run())

    def test_report_only_schedule_does_not_change_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_mode = "report_only"
            assistant.fast_planner_timeout_ms = 1000
            assistant.response_composer_mode = "report_only"
            assistant.enable_agent = True
            assistant.fast_planner_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None

            class Client:
                async def resolve_fast_plan(self, *args, **kwargs):
                    return plan(goals=["goal-chat"])

                async def compose_response_plan(self, *args, **kwargs):
                    return ResponseCompositionResolution(status="model_unavailable")

            assistant.agent_client = Client()
            decision = ODecision(route="chat", intent="conversation", confidence=0.8, source="llm")
            reviewed = assistant._schedule_fast_planner_report(
                object(),
                user_text="hello",
                session_id="sid",
                context={"history": []},
                decision=decision,
            )
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(
                reviewed.metadata["response_composer_resolution"]["status"],
                "waiting_for_terminal_plan",
            )
            await asyncio.gather(*list(assistant.fast_planner_report_tasks))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
