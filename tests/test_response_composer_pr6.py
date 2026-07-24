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
            "response_text": "I'll look at you for two seconds and then blink twice.",
        }
        repaired_stage = {
            "text": "I'll look at you for two seconds and then blink twice.",
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
        self.assertTrue(result.metadata["initial_raw_output"])
        self.assertTrue(result.metadata["repair_raw_output"])
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
                    "text": "Done.",
                    "commitment_state": "completed",
                    "must_not_claim_completion": False,
                    "covers_goal_ids": ["goal-look"],
                }
            }
        }
        repaired = {
            "response_plan": {
                "pre_action": {
                    "text": "I'll look at you for two seconds, then blink twice.",
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
        self.assertIn("does not cover all plan goals", ollama.prompts[1][0])

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

    def test_model_authored_host_envelope_fields_are_rejected_then_repaired(self):
        canonical = plan(goals=["goal-chat"])
        response_plan = {
            "final": {"text": "Hello.", "covers_goal_ids": ["goal-chat"]}
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
                    "text": "I'll blink twice. Why do robots avoid water?",
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
            "I'll blink twice. Why do robots avoid water?",
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
                        "args": {"target_yaw_rad": 0.8},
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
                        "properties": {"target_yaw_rad": {"type": "number"}},
                        "required": ["target_yaw_rad"],
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
        asyncio.run(ResponseComposerResolver(ollama).resolve(request(canonical)))
        prompt = ollama.prompts[0][0]
        self.assertIn("CanonicalPlan is immutable", prompt)
        self.assertIn("never a user goal or task step", prompt)


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
