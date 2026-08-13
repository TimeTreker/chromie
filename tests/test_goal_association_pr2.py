from __future__ import annotations

import asyncio
import unittest

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import (
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalAssociationResolver,
    GoalResponsibilityCoverageReview,
    GoalSegmentationModelOutput,
)
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution


class GoalExecutionContractTests(unittest.TestCase):
    def test_responsibility_coverage_cannot_accept_overmerged_independent_outcomes(self):
        with self.assertRaisesRegex(ValueError, "over-merged"):
            GoalResponsibilityCoverageReview.model_validate(
                responsibility_coverage(
                    responsibility_item("walk", 0),
                    responsibility_item("sing", 0),
                )
            )

    def test_singing_derives_vocal_provider_contract(self):
        goal = GoalAssociationModelGoal.model_validate(
            {
                "description": "边走边唱歌",
                "output_mode": "singing",
                "bindings": [],
            }
        )

        self.assertEqual(goal.responsibility_kind, "vocal_output")
        self.assertEqual(goal.execution_lane, "vocal")
        self.assertTrue(goal.provider_required)

    def test_output_mode_is_required(self):
        with self.assertRaisesRegex(ValueError, "output_mode"):
            GoalAssociationModelGoal.model_validate(
                {
                    "description": "Say hello",
                    "bindings": [],
                }
            )

    def test_host_execution_projection_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            GoalAssociationModelGoal.model_validate(
                {
                    "description": "Sing a song",
                    "output_mode": "singing",
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "provider_required": True,
                    "bindings": [],
                }
            )

    def test_output_mode_derives_ordinary_speech_contract(self):
        goal = GoalAssociationModelGoal.model_validate(
            {
                "description": "Say hello",
                "output_mode": "speech",
                "bindings": [],
            }
        )

        self.assertEqual(goal.responsibility_kind, "vocal_output")
        self.assertEqual(goal.execution_lane, "vocal")
        self.assertFalse(goal.provider_required)

    def test_vocal_goal_rejects_resource_responsibility(self):
        with self.assertRaisesRegex(ValueError, "not resource acquisition"):
            GoalAssociationModelGoal.model_validate(
                {
                    "description": "Sing a song",
                    "output_mode": "singing",
                    "bindings": [],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "a song",
                        "source_status": "unknown",
                        "recipient_description": "requester",
                        "delivery_mode": "spoken_explanation",
                    },
                }
            )

    def test_physical_delivery_keeps_resource_responsibility(self):
        goal = GoalAssociationModelGoal.model_validate(
            {
                "description": "Bring the requester a bottle of water",
                "output_mode": "body_action",
                "bindings": [],
                "resource_responsibility": {
                    "resource_kind": "physical_object",
                    "resource_description": "a bottle of water",
                    "source_status": "unknown",
                    "recipient_description": "requester",
                    "delivery_mode": "physical_handover",
                },
            }
        )

        self.assertIsNotNone(goal.resource_responsibility)

    def test_live_decoder_schema_exposes_semantic_mode_not_host_invariants(self):
        schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
        )
        goal_schema = schema["$defs"]["GoalAssociationModelGoal"]
        required = set(goal_schema["required"])
        properties = set(goal_schema["properties"])

        self.assertIn("output_mode", required)
        self.assertNotIn("responsibility_kind", properties)
        self.assertNotIn("execution_lane", properties)
        self.assertNotIn("provider_required", properties)
        output_description = goal_schema["properties"]["output_mode"]["description"]
        self.assertIn("Semantic work that completes this Goal", output_description)
        self.assertIn("capability_work", output_description)

    def test_output_mode_materializes_host_execution_invariants(self):
        goal = GoalAssociationModelGoal.model_validate(
            {
                "description": "Check tomorrow's weather in Shanghai",
                "output_mode": "capability_work",
                "bindings": [],
            }
        )

        self.assertEqual(goal.responsibility_kind, "capability_dependent")
        self.assertEqual(goal.execution_lane, "activity")
        self.assertTrue(goal.provider_required)
        self.assertEqual(goal.media_operation, "none")


class FakeOllama:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ScriptedOllama:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if not self.payloads:
            raise AssertionError("unexpected extra model call")
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


def binding_audit(*bindings_by_goal):
    return {
        "goal_bindings": [
            {
                "candidate_goal_index": index,
                "bindings": bindings,
                "reason_summary": (
                    "Explicit material bindings audited for this Goal."
                ),
            }
            for index, bindings in enumerate(bindings_by_goal)
        ],
        "reason_summary": "All candidate Goal bindings were audited.",
    }


def responsibility_item(
    source_excerpt,
    *goal_indices,
    role="responsibility",
    coverage="covered",
    independently_satisfiable=True,
):
    return {
        "source_excerpt": source_excerpt,
        "role": role,
        "coverage": coverage,
        "independently_satisfiable": (
            independently_satisfiable if role == "responsibility" else False
        ),
        "candidate_goal_indices": list(goal_indices),
    }


def responsibility_coverage(*items, decision="accept"):
    return {
        "decision": decision,
        "items": list(items),
        "reason_summary": "Candidate Goals account for the audited user meaning.",
    }


def request(
    text: str,
    *,
    active_goals=None,
    history=None,
    language="zh-CN",
    discourse_referents=None,
    discourse_focus=None,
    recent_tool_evidence=None,
    recent_goals=None,
    route="chat",
    intent="conversation",
    progress_candidates=None,
):
    return AgentRunRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        route_decision=RouteDecision(
            route=route,
            intent=intent,
            confidence=0.8,
            source="llm",
        ),
        context={
            "active_goal_snapshots": active_goals or [],
            "recent_goal_snapshots": recent_goals or [],
            "history": history or [],
            "discourse_referents": discourse_referents or [],
            "discourse_focus": discourse_focus or [],
            "recent_tool_evidence": recent_tool_evidence or [],
            "progress_candidates": progress_candidates or [],
        },
    )


def active_goal(
    goal_id: str,
    description: str,
    *,
    bindings=None,
    work_status="open",
    responsibility_status="open",
):
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "responsibility_status": responsibility_status,
        "work_status": work_status,
        "goal": {
            "goal_id": goal_id,
            "version": 1,
            "responsibility_status": responsibility_status,
            "description": description,
            "source_text": description,
            "beneficiary": "user",
            "object": {"bindings": bindings or {}},
            "constraints": {},
            "success_criteria": [],
            "metadata": {},
        },
        "open_information_gaps": [],
        "last_user_update": description,
        "metadata": {},
    }


class GoalAssociationModelOutputTests(unittest.TestCase):
    def test_association_only_create_goals_branch_normalizes_to_associate(self):
        output = GoalAssociationModelOutput.model_validate(
            {
                "decision": "create_goals",
                "associations": [
                    {
                        "relationship": "modify",
                        "target_goal_ids": ["goal-restaurant"],
                        "confidence": 1.0,
                        "reason_summary": "The user supplied the missing location.",
                        "updated_description": (
                            "Recommend restaurants near Chongqing Longxing Tianjie."
                        ),
                        "requires_replan": True,
                    }
                ],
                "new_goals": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "Update the existing Goal.",
            }
        )

        self.assertEqual(output.decision, "associate")
        self.assertEqual(len(output.associations), 1)


class GoalAssociationResolverTests(unittest.TestCase):
    def test_resource_source_resegmentation_preserves_one_delivery_goal(self):
        invalid = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Pick up the red mug and hand it to me.",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "object_color",
                            "entity_type": "color",
                            "value": "red",
                            "confidence": 1.0,
                        },
                        {
                            "name": "object_type",
                            "entity_type": "physical_object",
                            "value": "mug",
                            "confidence": 1.0,
                        },
                    ],
                    "resource_responsibility": {
                        "resource_kind": "physical_object",
                        "resource_description": "red mug",
                        "source_status": "known",
                        "delivery_mode": "physical_handover",
                    },
                }
            ],
            "confidence": 1.0,
        }
        corrected = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": (
                        "Acquire and hand me the red mug, then report completion."
                    ),
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "object_color",
                            "entity_type": "color",
                            "value": "red",
                            "confidence": 1.0,
                        },
                        {
                            "name": "object_type",
                            "entity_type": "physical_object",
                            "value": "mug",
                            "confidence": 1.0,
                        },
                    ],
                    "resource_responsibility": {
                        "resource_kind": "physical_object",
                        "resource_description": "red mug",
                        "source_status": "unknown",
                        "delivery_mode": "physical_handover",
                    },
                },
                {
                    "description": "Tell me when the handoff is finished.",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        adjudication = {
            "candidate_decisions": [
                {
                    "candidate_goal_index": 0,
                    "completion_mode": "positive_effect",
                    "audible_content_summary": "",
                    "final_goal_description": corrected["new_goals"][0][
                        "description"
                    ],
                    "reason_summary": "The resource handoff is the positive effect.",
                },
                {
                    "candidate_goal_index": 1,
                    "completion_mode": "capability_result_delivery_only",
                    "audible_content_summary": "",
                    "final_goal_description": "",
                    "reason_summary": (
                        "The completion report depends on the handoff result."
                    ),
                },
            ],
            "reason_summary": (
                "The physical Goal owns its contingent completion delivery."
            ),
        }
        coverage = responsibility_coverage(
            responsibility_item("Pick up the red mug and hand it to me", 0),
            responsibility_item(
                "tell me when you have finished",
                0,
                role="constraint",
                independently_satisfiable=False,
            ),
        )
        ollama = ScriptedOllama(
            [invalid, corrected, corrected, adjudication, coverage]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Pick up the red mug and hand it to me, then tell me when "
                    "you have finished.",
                    language="en-US",
                    route="robot_action",
                    intent="semantic_capability_planning",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 5)
        self.assertEqual(len(result.new_goals), 1)
        responsibility = result.new_goals[0].resource_responsibility
        self.assertIsNotNone(responsibility)
        assert responsibility is not None
        self.assertEqual(responsibility.source.status, "unknown")
        self.assertEqual(responsibility.delivery_mode, "physical_handover")
        self.assertIn("report completion", result.new_goals[0].description)
        review_prompt = ollama.prompts[2][0]
        self.assertIn("provider-owned stages", review_prompt)
        self.assertIn("Do not split pickup and handoff", review_prompt)
        self.assertIn("not an independently satisfiable vocal_output", review_prompt)
        self.assertIn("DTO to review JSON", review_prompt)
        self.assertNotIn("No previous Goal DTO is supplied", review_prompt)
        self.assertEqual(
            ollama.prompts[3][1]["prompt_family"],
            "goal_association.independence_adjudication",
        )

    def test_invalid_known_resource_source_uses_exact_contract_revision(self):
        invalid = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Put the item over there.",
                    "output_mode": "body_action",
                    "media_operation": "none",
                    "bindings": [],
                    "resource_responsibility": {
                        "resource_kind": "physical_object",
                        "resource_description": "the item",
                        "source_status": "known",
                        "delivery_mode": "physical_handover",
                    },
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.9,
            "reason_summary": "The item is the resource.",
        }
        clarified = {
            "decision": "clarify",
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "Which item do you mean, and where should I put it?",
            "confidence": 0.7,
            "reason_summary": "The resource and its source are unresolved.",
        }
        ollama = ScriptedOllama([invalid, clarified])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Could you put that over there?",
                    language="en-US",
                    route="robot_action",
                    intent="capability:soridormi.look_at_person",
                )
            )
        )

        self.assertEqual(result.clarification, clarified["clarification"])
        self.assertEqual(len(ollama.prompts), 2)
        prompt, kwargs = ollama.prompts[1]
        self.assertEqual(
            kwargs["prompt_family"],
            "goal_association.repair",
        )
        self.assertIn("known resource source requires", prompt)
        self.assertIn("Previous model output JSON", prompt)
        self.assertIn('"source_status":"known"', prompt)
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "schema_constrained_model_revision",
        )

    def test_information_query_location_cannot_be_used_as_known_source(self):
        invalid = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Find good restaurants near Chongqing Longxing Paradise Walk.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "重庆龙兴天街",
                            "confidence": 1.0,
                        }
                    ],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "nearby good restaurants",
                        "source_status": "known",
                        "source_binding_names": ["location"],
                        "delivery_mode": "spoken_explanation",
                    },
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.95,
            "reason_summary": "Need current local restaurant information.",
        }
        corrected = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Find good restaurants near Chongqing Longxing Paradise Walk.",
                    "output_mode": "capability_work",
                    "bindings": invalid["new_goals"][0]["bindings"],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "nearby good restaurants",
                        "source_status": "provider_resolved",
                        "source_description": "current external place information",
                        "delivery_mode": "spoken_explanation",
                    },
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.95,
            "reason_summary": "The location scopes the query; the provider resolves the source.",
        }
        ollama = ScriptedOllama([invalid, corrected])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "帮我找重庆龙兴天街附近好吃的餐厅。",
                    route="tool",
                    intent="capability:chromie.external_information.retrieve",
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        responsibility = result.new_goals[0].resource_responsibility
        self.assertIsNotNone(responsibility)
        assert responsibility is not None
        self.assertEqual(responsibility.source.status, "provider_resolved")
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["value"],
            "重庆龙兴天街",
        )
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "query-scope location bindings as source evidence",
            ollama.prompts[1][0],
        )

    def test_resource_lookup_and_derived_answer_are_resegmented_as_one_goal(self):
        bindings = [
            {
                "name": "location",
                "entity_type": "city",
                "value": "上海",
                "confidence": 1.0,
            },
            {
                "name": "date_scope",
                "entity_type": "temporal_scope",
                "value": "明天",
                "confidence": 1.0,
            },
        ]
        responsibility = {
            "resource_kind": "information",
            "resource_description": "weather forecast for Shanghai tomorrow",
            "source_status": "unknown",
            "delivery_mode": "spoken_explanation",
        }
        duplicated = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check the weather forecast for Shanghai for tomorrow to determine if heavy rain is expected.",
                    "output_mode": "capability_work",
                    "bindings": bindings,
                    "resource_responsibility": responsibility,
                },
                {
                    "description": "Answer whether it will rain heavily in Shanghai tomorrow based on the retrieved weather information.",
                    "output_mode": "capability_work",
                    "bindings": [],
                },
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "The model incorrectly split evidence acquisition from result delivery.",
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check tomorrow's Shanghai forecast and answer whether heavy rain is expected.",
                    "output_mode": "capability_work",
                    "bindings": bindings,
                    "resource_responsibility": responsibility,
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "The information resource Goal owns evidence acquisition and its derived answer.",
        }
        ollama = ScriptedOllama([duplicated, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "诶，明天上海会下大雨吗？",
                    route="tool",
                    intent="capability:chromie.weather.lookup",
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "resource_result_delivery_split_review",
            result.metadata["semantic_review"]["triggers"],
        )
        self.assertEqual(
            ollama.prompts[1][1]["prompt_family"],
            "goal_association.semantic_resegmentation",
        )
        self.assertIn(
            "delivery owned by that resource Goal",
            ollama.prompts[1][0],
        )
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])

    def test_tool_route_spoken_only_output_gets_fresh_responsibility_review(self):
        spoken_only = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Recommend a noodle restaurant open now.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.9,
            "reason_summary": "Answer conversationally.",
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Find a noodle restaurant that is open now.",
                    "output_mode": "capability_work",
                    "media_operation": "none",
                    "bindings": [],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "a current open noodle restaurant",
                        "source_status": "provider_resolved",
                        "source_description": "current external place information",
                        "delivery_mode": "spoken_explanation",
                    },
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "Current opening status requires fresh evidence.",
        }
        ollama = ScriptedOllama([spoken_only, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Find me a noodle restaurant that's open right now.",
                    language="en-US",
                    route="tool",
                    intent="capability:chromie.weather.lookup",
                )
            )
        )

        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "capability_dependent",
        )
        self.assertEqual(len(ollama.prompts), 2)
        prompt, kwargs = ollama.prompts[1]
        self.assertEqual(kwargs["prompt_family"], "goal_association.semantic_resegmentation")
        self.assertIn("tool_route_spoken_responsibility_review", prompt)
        self.assertIn("No previous Goal DTO is supplied", prompt)

    def test_recommendation_route_spoken_only_output_gets_fresh_evidence_review(self):
        spoken_only = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Recommend a noodle restaurant open now.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.9,
            "reason_summary": "Answer conversationally.",
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Find a noodle restaurant that is open now.",
                    "output_mode": "capability_work",
                    "media_operation": "none",
                    "bindings": [],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "a current open noodle restaurant",
                        "source_status": "provider_resolved",
                        "source_description": "current external place information",
                        "delivery_mode": "spoken_explanation",
                    },
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "Current opening status requires fresh evidence.",
        }
        ollama = ScriptedOllama([spoken_only, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Recommend a noodle restaurant that is open right now.",
                    language="en-US",
                    route="chat",
                    intent="recommendation",
                )
            )
        )

        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "capability_dependent",
        )
        self.assertEqual(len(ollama.prompts), 2)
        prompt, kwargs = ollama.prompts[1]
        self.assertEqual(kwargs["prompt_family"], "goal_association.semantic_resegmentation")
        self.assertIn("recommendation_route_spoken_responsibility_review", prompt)
        self.assertIn("No previous Goal DTO is supplied", prompt)

    def test_prompt_distinguishes_resource_identity_from_source_and_binds_counts(self):
        ollama = FakeOllama(
            {
                "decision": "clarify",
                "new_goals": [],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "Which object do you mean?",
                "confidence": 0.7,
                "reason_summary": "The object is unresolved.",
            }
        )

        asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Put that over there, then blink twice.", language="en-US")
            )
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("Resource identity is not source evidence", prompt)
        self.assertIn("source_description or source_binding_names is mandatory", prompt)
        self.assertIn("normalize its binding value to the equivalent numeric string", prompt)
        self.assertIn("Description text alone is not parameter provenance", prompt)


    def test_compound_walk_sing_blink_is_freshly_resegmented_with_typed_modes(self):
        initial = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "往前走15秒。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "边走边唱歌。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "同时眨眼睛。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "往前走15秒。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "边走边唱歌。",
                    "output_mode": "singing",
                    "bindings": [],
                },
                {
                    "description": "同时眨眼睛。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        audited_bindings = binding_audit(
            [
                {
                    "name": "duration_s",
                    "entity_type": "duration_seconds",
                    "value": "15",
                    "confidence": 1.0,
                }
            ],
            [],
            [],
        )
        coverage = responsibility_coverage(
            responsibility_item("往前走个15秒", 0),
            responsibility_item("边走边唱歌", 1),
            responsibility_item("眨眼睛", 2),
            responsibility_item(
                "你好",
                role="framing",
                independently_satisfiable=False,
            ),
        )
        ollama = ScriptedOllama([initial, reviewed, coverage, audited_bindings])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。",
                    language="zh-CN",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 4)
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])
        self.assertNotIn('"output_mode":"body_action"', ollama.prompts[1][0])
        self.assertEqual(
            [
                (
                    goal.metadata["execution_lane"],
                    goal.metadata["output_mode"],
                    goal.metadata["provider_required"],
                )
                for goal in result.new_goals
            ],
            [
                ("activity", "body_action", True),
                ("vocal", "singing", True),
                ("activity", "body_action", True),
            ],
        )
        self.assertIsNone(result.new_goals[1].resource_responsibility)
        self.assertEqual(
            result.new_goals[0].object["bindings"]["duration_s"]["value"],
            "15",
        )
        self.assertEqual(
            result.metadata["binding_audit"]["strategy"],
            "model_owned_material_parameter_audit",
        )
        self.assertEqual(
            result.metadata["responsibility_coverage"]["final_decision"],
            "accept",
        )
        projection = result.prompt_projection()
        self.assertEqual(
            projection["new_goals"][1]["metadata"],
            {
                "responsibility_kind": "vocal_output",
                "execution_lane": "vocal",
                "output_mode": "singing",
                "provider_required": True,
                "media_operation": "none",
            },
        )

    def test_responsibility_coverage_rejects_persistently_collapsed_compound_goal(self):
        collapsed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "往前走15秒，同时唱歌和眨眼睛。",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "duration_s",
                            "entity_type": "duration_seconds",
                            "value": "15",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "confidence": 1.0,
        }
        rejected_coverage = responsibility_coverage(
            responsibility_item("往前走个15秒", 0),
            responsibility_item(
                "边走边唱歌",
                coverage="missing",
            ),
            responsibility_item(
                "眨眼睛",
                coverage="missing",
            ),
            decision="reject",
        )
        resegmented = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "往前走15秒。",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "duration_s",
                            "entity_type": "duration_seconds",
                            "value": "15",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "边走边唱歌。",
                    "output_mode": "singing",
                    "bindings": [],
                },
                {
                    "description": "同时眨眼睛。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        accepted_coverage = responsibility_coverage(
            responsibility_item("往前走个15秒", 0),
            responsibility_item("边走边唱歌", 1),
            responsibility_item("眨眼睛", 2),
        )
        ollama = ScriptedOllama(
            [
                collapsed,
                collapsed,
                rejected_coverage,
                resegmented,
                accepted_coverage,
                binding_audit([], [], []),
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。",
                    language="zh-CN",
                )
            )
        )

        self.assertEqual(
            [goal.metadata["output_mode"] for goal in result.new_goals],
            ["body_action", "singing", "body_action"],
        )
        self.assertEqual(
            result.metadata["responsibility_coverage"],
            {
                "attempted": True,
                "succeeded": True,
                "strategy": "independent_model_coverage_audit",
                "initial_decision": "reject",
                "final_decision": "accept",
                "resegmented": True,
                "attempt_count": 2,
                "item_count": 3,
            },
        )
        self.assertEqual(
            [kwargs["prompt_family"] for _, kwargs in ollama.prompts],
            [
                "goal_association.primary",
                "goal_association.semantic_resegmentation",
                "goal_association.responsibility_coverage",
                "goal_association.responsibility_resegmentation",
                "goal_association.responsibility_coverage_recheck",
                "goal_association.binding_audit",
            ],
        )
        coverage_prompt = ollama.prompts[2][0]
        self.assertIn("independently satisfiable responsibility", coverage_prompt)
        self.assertIn("provider availability", coverage_prompt)
        resegmentation_prompt = ollama.prompts[3][0]
        self.assertIn("responsibility-coverage audit JSON", resegmentation_prompt)
        self.assertIn("No previous Goal DTO is supplied", resegmentation_prompt)

    def test_legacy_host_execution_fields_require_schema_repair(self):
        invalid = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Say hello.",
                    "output_mode": "speech",
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "provider_required": False,
                    "bindings": [],
                }
            ],
            "confidence": 1.0,
        }
        repaired = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Say hello.",
                    "output_mode": "speech",
                    "bindings": [],
                }
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([invalid, repaired])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Say hello.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        repair_prompt, repair_kwargs = ollama.prompts[1]
        self.assertEqual(repair_kwargs["prompt_family"], "goal_association.repair")
        self.assertIn("Extra inputs are not permitted", repair_prompt)
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "schema_constrained_model_revision",
        )
        self.assertEqual(result.new_goals[0].metadata["output_mode"], "speech")
        self.assertEqual(result.new_goals[0].metadata["execution_lane"], "vocal")
        self.assertFalse(result.new_goals[0].metadata["provider_required"])


    def test_empty_optional_referent_introduction_does_not_discard_weather_goal(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "Check Chongqing weather tomorrow.",
                        "output_mode": "capability_work",
                        "bindings": [
                            {
                                "name": "location",
                                "entity_type": "place",
                                "value": "重庆",
                                "confidence": 1.0,
                            },
                            {
                                "name": "date",
                                "entity_type": "date",
                                "value": "明天",
                                "confidence": 1.0,
                            },
                        ],
                        "resource_responsibility": {
                            "resource_kind": "information",
                            "resource_description": "重庆明天的天气",
                            "source_status": "provider_resolved",
                            "source_description": "current weather information",
                            "source_binding_names": ["location", "date"],
                            "recipient_description": "requester",
                            "delivery_mode": "spoken_explanation",
                        },
                    }
                ],
                "referent_updates": [
                    {
                        "operation": "introduce",
                        "target_referent_ids": [],
                        "target_goal_ids": [],
                        "confidence": 1.0,
                    }
                ],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "One information acquisition responsibility.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "帮我查一下重庆明天是晴天还是阴天。",
                    route="tool",
                    intent="capability:chromie.weather.lookup",
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        responsibility = result.new_goals[0].resource_responsibility
        self.assertIsNotNone(responsibility)
        assert responsibility is not None
        self.assertEqual(responsibility.resource.kind, "information")
        self.assertNotIn(
            "responsibility_variant",
            responsibility.model_dump(mode="json"),
        )
        self.assertEqual(
            responsibility.source.bindings["location"]["value"],
            "重庆",
        )
        recovery = result.metadata["optional_contract_recovery"]
        self.assertEqual(recovery["dropped_count"], 1)
        self.assertEqual(len(ollama.prompts), 1)

    def test_preassociation_clarify_route_does_not_force_goal_loss(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": (
                            "Recommend interesting places near the user."
                        ),
                        "output_mode": "capability_work",
                        "bindings": [],
                    }
                ],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": (
                    "The desired outcome is clear; capability planning may ask "
                    "for a location binding later."
                ),
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "帮我推荐附近好玩的地方。",
                    route="clarify",
                    intent="clarify_missing_location",
                )
            )
        )

        self.assertEqual(result.clarification, "")
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].description,
            "Recommend interesting places near the user.",
        )
        prompt, kwargs = ollama.prompts[0]
        self.assertIn(
            "pre-association route and intent are advisory only", prompt
        )
        self.assertNotIn(
            "an admitted clarify route requires", prompt
        )
        self.assertEqual(
            kwargs["response_format"]["properties"]["decision"]["enum"],
            ["create_goals", "clarify"],
        )

    def test_preassociation_clarify_route_can_still_ask_for_semantic_clarification(self):
        ollama = FakeOllama(
            {
                "decision": "clarify",
                "new_goals": [],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "你想找吃饭的地方，还是游玩的地方？",
                "confidence": 0.8,
                "reason_summary": "The requested outcome itself is ambiguous.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "附近有什么好地方？",
                    route="clarify",
                    intent="clarify_uncertain_request",
                )
            )
        )

        self.assertEqual(
            result.clarification,
            "你想找吃饭的地方，还是游玩的地方？",
        )
        self.assertEqual(result.new_goals, [])

    def test_repeated_ungrounded_location_becomes_material_clarification(self):
        invented_local = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "查询并告知用户今天的本地天气。",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "本地",
                            "confidence": 1.0,
                        },
                        {
                            "name": "date",
                            "entity_type": "date",
                            "value": "今天",
                            "confidence": 1.0,
                        },
                    ],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "查询今天的天气。",
        }
        invented_current = {
            **invented_local,
            "new_goals": [
                {
                    "description": "查询并告知用户当前位置今天的天气。",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "当前位置",
                            "confidence": 1.0,
                        },
                        {
                            "name": "date",
                            "entity_type": "date",
                            "value": "今天",
                            "confidence": 1.0,
                        },
                    ],
                }
            ],
        }
        clarified = {
            "decision": "clarify",
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "你想查哪里的天气？",
            "confidence": 1.0,
            "reason_summary": "查询地点没有从当前输入或上下文中确定。",
        }
        ollama = ScriptedOllama(
            [invented_local, invented_current, clarified]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "你好，今天天气怎么样？",
                    language="zh-CN",
                    route="tool",
                    intent="capability:chromie.weather.lookup",
                    progress_candidates=[
                        {
                            "candidate_id": "progress-weather",
                            "kind": "capability",
                            "capability_id": "chromie.weather.lookup",
                            "args": {"location": "本地", "date": "today"},
                            "intent": "chromie.weather.lookup",
                            "confidence": 0.95,
                        }
                    ],
                )
            )
        )

        self.assertEqual(result.clarification, "你想查哪里的天气？")
        self.assertEqual(result.new_goals, [])
        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(
            ollama.prompts[1][1]["prompt_family"],
            "goal_association.semantic_contract_resegmentation",
        )
        self.assertEqual(
            ollama.prompts[2][1]["prompt_family"],
            "goal_association.material_binding_clarification",
        )
        clarification_schema = ollama.prompts[2][1]["response_format"]
        self.assertEqual(
            clarification_schema["properties"]["decision"]["enum"],
            ["clarify"],
        )
        self.assertEqual(
            clarification_schema["properties"]["new_goals"]["maxItems"],
            0,
        )
        self.assertIn(
            "material semantic information required to define what Chromie owes",
            ollama.prompts[2][0],
        )
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "model_owned_material_binding_clarification",
        )
        self.assertEqual(
            result.metadata["contract_repair"]["attempt_count"],
            2,
        )

    def test_explicit_location_binding_repairs_non_verbatim_model_value(self):
        mistranslated = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check whether it is raining in Xiang County.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "place",
                            "value": "Xiang County, Henan Province",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "confidence": 1.0,
        }
        repaired = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check whether it is raining in 河南省内乡县.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "place",
                            "value": "河南省内乡县",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([mistranslated, repaired])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("河南省内乡县现在下雨了吗？")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["value"],
            "河南省内乡县",
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("verbatim", ollama.prompts[1][0])

    def test_indirect_location_repair_requires_copied_referent_provenance(self):
        neixiang = {
            "referent_id": "ref-neixiang",
            "entity_type": "location",
            "canonical_value": "内乡",
            "scope_kind": "conversation",
            "scope_ids": [],
            "status": "foreground",
            "confidence": 1.0,
            "source_turn_id": "turn-neixiang",
            "source_goal_ids": [],
        }
        missing_provenance = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "查询今天内乡是否下雨。",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "内乡",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "confidence": 1.0,
        }
        repaired = {
            **missing_provenance,
            "new_goals": [
                {
                    "description": "查询今天内乡是否下雨。",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "内乡",
                            "referent_id": "ref-neixiang",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "resolved_references": [
                {
                    "surface_form": "那边",
                    "entity_type": "location",
                    "resolved_value": "内乡",
                    "source": "discourse_referent",
                    "referent_id": "ref-neixiang",
                    "confidence": 1.0,
                    "reason_summary": "内乡是当前前景地点。",
                }
            ],
        }
        ollama = ScriptedOllama([missing_provenance, repaired])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "今天那边下雨了吗？",
                    discourse_referents=[neixiang],
                    discourse_focus=["ref-neixiang"],
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.resolved_references[0].resolved_value, "内乡")
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["referent_id"],
            "ref-neixiang",
        )
        self.assertIn(
            "copy the supplied referent_id into both the location binding and "
            "resolved_references",
            ollama.prompts[1][0],
        )

    def test_capability_result_delivery_is_not_a_duplicate_spoken_goal(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "Look up today's weather.",
                            "output_mode": "capability_work",
                            "bindings": [
                                {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "Neixiang County",
                                    "confidence": 1.0,
                                }
                            ],
                        },
                        {
                            "description": "Say the weather naturally.",
                            "output_mode": "speech",
                            "bindings": [
                                {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "Neixiang County",
                                    "confidence": 1.0,
                                }
                            ],
                        },
                    ],
                    "confidence": 1.0,
                },
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "Look up and answer with today's weather.",
                            "output_mode": "capability_work",
                            "bindings": [
                                {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "Neixiang County",
                                    "confidence": 1.0,
                                }
                            ],
                        }
                    ],
                    "confidence": 1.0,
                },
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("How is today's weather in Neixiang County?", language="en-US")
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "capability_dependent",
        )
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("A trigger is not proof", ollama.prompts[1][0])
        self.assertIn("Do not use phrase matching", ollama.prompts[1][0])
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )

    def test_mixed_stable_knowledge_uses_fresh_model_resegmentation(self):
        initial = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Determine why the Moon shines.",
                    "output_mode": "capability_work",
                    "media_operation": "none",
                    "bindings": [],
                },
                {
                    "description": "Remind the user to go to bed early tonight.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Explain that the Moon reflects sunlight.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                },
                {
                    "description": "Remind the user to go to bed early tonight.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([initial, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Tell me why the Moon shines, then remind me to go to bed early tonight.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["vocal_output", "vocal_output"],
        )
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])
        self.assertNotIn("Determine why the Moon shines", ollama.prompts[1][0])

    def test_invalid_followup_location_uses_fresh_model_resegmentation(self):
        initial = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Look up whether rain in Chongqing requires an umbrella.",
                    "output_mode": "capability_work",
                    "media_operation": "none",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "Chongqing",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Answer whether the user needs an umbrella.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Answer whether the prior rain report means an umbrella is useful.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                }
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([initial, reviewed, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Do I need an umbrella when I go out?",
                    language="en-US",
                    active_goals=[
                        active_goal(
                            "goal-weather",
                            "Report today's weather in Chongqing.",
                            bindings={
                                "location": {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "Chongqing",
                                    "confidence": 1.0,
                                }
                            },
                            work_status="done",
                            responsibility_status="satisfied",
                        )
                    ],
                    history=[
                        {
                            "role": "assistant",
                            "content": "There are thunderstorms in Chongqing today.",
                        }
                    ],
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "vocal_output",
        )
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])
        self.assertNotIn("Look up whether rain", ollama.prompts[1][0])

    def test_embodied_request_separates_movement_but_keeps_resource_delivery(self):
        merged = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "跑出50米并帮用户拿一杯水，然后返回。",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "回应用户的请求。",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "往前移动50米。",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "distance",
                            "entity_type": "distance",
                            "value": "50米",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "拿一杯水并带回给用户。",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "resource",
                            "entity_type": "physical_object",
                            "value": "一杯水",
                            "confidence": 1.0,
                        }
                    ],
                    "resource_responsibility": {
                        "resource_kind": "physical_object",
                        "resource_description": "一杯水",
                        "source_status": "unknown",
                        "recipient_description": "用户",
                        "delivery_mode": "physical_handover",
                    },
                },
            ],
            "confidence": 1.0,
        }
        coverage = responsibility_coverage(
            responsibility_item("往前给我跑个50米", 0),
            responsibility_item("帮我拿杯水，然后回来", 1),
        )
        ollama = ScriptedOllama([merged, reviewed, coverage])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("你能往前给我跑个50米，帮我拿杯水，然后回来吗？")
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["往前移动50米。", "拿一杯水并带回给用户。"],
        )
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["executable_action", "executable_action"],
        )
        self.assertEqual(
            result.metadata["semantic_review"]["triggers"],
            ["embodied_responsibility_decomposition"],
        )
        review_prompt = ollama.prompts[1][0]
        self.assertIn("acknowledgement, confirmation", review_prompt)
        self.assertIn("provider-owned stages", review_prompt)
        self.assertIn("Do not split pickup and handoff", review_prompt)
        self.assertIn("Identity shapes expression only", review_prompt)

    def test_negative_speech_constraint_stays_with_embodied_goal(self):
        initial = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Nod twice.",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "count",
                            "entity_type": "number",
                            "value": "2",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Acknowledge that no more weather details will be given.",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Nod twice without giving more weather details.",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "count",
                            "entity_type": "number",
                            "value": "2",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "confidence": 1.0,
        }
        adjudication = {
            "candidate_decisions": [
                {
                    "candidate_goal_index": 0,
                    "completion_mode": "positive_effect",
                    "audible_content_summary": "",
                    "final_goal_description": (
                        "Nod twice without giving more weather details."
                    ),
                    "reason_summary": "The requested nod is a positive body effect.",
                },
                {
                    "candidate_goal_index": 1,
                    "completion_mode": "silence_or_omission_only",
                    "audible_content_summary": "",
                    "final_goal_description": "Do not give more weather details.",
                    "reason_summary": (
                        "Compliance consists only of omitting more weather details."
                    ),
                },
            ],
            "reason_summary": (
                "The nod is independently requested; the prohibition is a delivery "
                "constraint rather than spoken content."
            ),
        }
        coverage = responsibility_coverage(
            responsibility_item("nod twice", 0),
            responsibility_item(
                "do not give me more weather details",
                0,
                role="constraint",
                independently_satisfiable=False,
            ),
        )
        ollama = ScriptedOllama([initial, initial, adjudication, coverage])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Now nod twice, and do not give me more weather details.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].description,
            "Nod twice without giving more weather details.",
        )
        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "executable_action",
        )
        self.assertEqual(len(ollama.prompts), 4)
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_goal_independence_adjudication",
        )
        self.assertEqual(result.metadata["semantic_review"]["attempt_count"], 2)
        review_prompt = ollama.prompts[1][0]
        self.assertIn("No previous Goal DTO is supplied", review_prompt)
        self.assertNotIn("Acknowledge that no more weather", review_prompt)
        self.assertIn("not a request for a verbal acknowledgement", review_prompt)
        self.assertIn("do not create a sibling", review_prompt)
        self.assertIn("omitting its typed binding is invalid", review_prompt)
        self.assertIn("description text alone is never enough", review_prompt)
        adjudication_prompt = ollama.prompts[2][0]
        self.assertIn("if the body action occurred", adjudication_prompt)
        self.assertIn("sets a boundary on delivery", adjudication_prompt)
        self.assertIn("every zero-based candidate Goal", adjudication_prompt)
        self.assertIn("positive words, information", adjudication_prompt)
        self.assertIn("silence_or_omission_only", adjudication_prompt)
        self.assertIn(
            "goal_association.independence_adjudication",
            ollama.prompts[2][1]["prompt_family"],
        )
        adjudication_schema = ollama.prompts[2][1]["response_format"]
        self.assertEqual(
            adjudication_schema["$defs"][
                "GoalIndependenceCandidateDecision"
            ]["properties"]["candidate_goal_index"]["enum"],
            [0, 1],
        )
        self.assertEqual(
            adjudication_schema["$defs"][
                "GoalIndependenceCandidateDecision"
            ]["required"],
            [
                "candidate_goal_index",
                "completion_mode",
                "audible_content_summary",
                "final_goal_description",
                "reason_summary",
            ],
        )

    def test_independence_adjudication_preserves_requested_authored_content(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Blink twice.",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "count",
                            "entity_type": "number",
                            "value": "2",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Tell a short joke.",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        adjudication = {
            "candidate_decisions": [
                {
                    "candidate_goal_index": 0,
                    "completion_mode": "positive_effect",
                    "audible_content_summary": "",
                    "final_goal_description": "Blink twice.",
                    "reason_summary": "The requested blink is a positive body effect.",
                },
                {
                    "candidate_goal_index": 1,
                    "completion_mode": "independently_requested_authored_content",
                    "audible_content_summary": "A short joke.",
                    "final_goal_description": "Tell a short joke.",
                    "reason_summary": "The user positively requested a joke to hear.",
                },
            ],
            "reason_summary": "Both outcomes are independently requested.",
        }
        coverage = responsibility_coverage(
            responsibility_item("Blink twice", 0),
            responsibility_item("tell me a short joke", 1),
        )
        ollama = ScriptedOllama([mixed, mixed, adjudication, coverage])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Blink twice and tell me a short joke.", language="en-US")
            )
        )

        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Blink twice.", "Tell a short joke."],
        )
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["executable_action", "vocal_output"],
        )

    def test_independent_spoken_performance_survives_model_semantic_review(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Look up today's weather in Neixiang County.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "Neixiang County",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Sing a short song.",
                    "output_mode": "singing",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        adjudication = {
            "candidate_decisions": [
                {
                    "candidate_goal_index": 0,
                    "completion_mode": "positive_effect",
                    "audible_content_summary": "",
                    "final_goal_description": mixed["new_goals"][0]["description"],
                    "reason_summary": "Weather lookup is the capability outcome.",
                },
                {
                    "candidate_goal_index": 1,
                    "completion_mode": "independently_requested_authored_content",
                    "audible_content_summary": "A short song.",
                    "final_goal_description": mixed["new_goals"][1]["description"],
                    "reason_summary": "The song is independently requested content.",
                },
            ],
            "reason_summary": "Both independently requested outcomes are preserved.",
        }
        coverage = responsibility_coverage(
            responsibility_item("Check today's weather in Neixiang County", 0),
            responsibility_item("sing a short song", 1),
        )
        ollama = ScriptedOllama([mixed, mixed, coverage])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Check today's weather in Neixiang County and sing a short song.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["capability_dependent", "vocal_output"],
        )
        self.assertEqual(result.new_goals[1].metadata["output_mode"], "singing")
        self.assertIn("such as a song, joke", ollama.prompts[1][0])
        self.assertEqual(
            ollama.prompts[2][1]["prompt_family"],
            "goal_association.responsibility_coverage",
        )

    def test_capability_result_recommendation_is_owned_by_capability_goal(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check tomorrow's weather in Shanghai.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "Shanghai",
                            "confidence": 1.0,
                        },
                        {
                            "name": "date",
                            "entity_type": "date",
                            "value": "tomorrow",
                            "confidence": 1.0,
                        },
                    ],
                },
                {
                    "description": "Recommend whether to take an umbrella.",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        adjudication = {
            "candidate_decisions": [
                {
                    "candidate_goal_index": 0,
                    "completion_mode": "positive_effect",
                    "audible_content_summary": "",
                    "final_goal_description": mixed["new_goals"][0]["description"],
                    "reason_summary": "Fresh weather evidence is required.",
                },
                {
                    "candidate_goal_index": 1,
                    "completion_mode": "capability_result_delivery_only",
                    "audible_content_summary": "",
                    "final_goal_description": "",
                    "reason_summary": (
                        "The umbrella recommendation depends on the weather result."
                    ),
                },
            ],
            "reason_summary": (
                "The capability Goal owns both evidence acquisition and delivery."
            ),
        }
        ollama = ScriptedOllama([mixed, mixed, adjudication])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Check tomorrow's weather in Shanghai and tell me whether I "
                    "should take an umbrella.",
                    language="en-US",
                    route="tool",
                    intent="capability:chromie.weather.lookup",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "capability_dependent",
        )
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_goal_independence_adjudication",
        )
        self.assertIn(
            "capability_result_delivery_only",
            ollama.prompts[2][0],
        )
        self.assertIn(
            "contingent completion report",
            ollama.prompts[2][0],
        )
        self.assertIn(
            "pending work has finished depends on execution evidence",
            ollama.prompts[2][1]["system"],
        )

    def test_compound_mixed_goal_triggers_binding_audit_without_host_word_rules(self):
        self.assertTrue(
            GoalAssociationResolver._binding_audit_required(
                {
                    "new_goals": [
                        {
                            "description": "Blink twice.",
                            "output_mode": "body_action",
                            "bindings": [],
                        },
                        {
                            "description": "Explain why leaves change color.",
                            "output_mode": "speech",
                            "bindings": [],
                        },
                    ]
                }
            )
        )
        self.assertFalse(
            GoalAssociationResolver._binding_audit_required(
                {
                    "new_goals": [
                        {
                            "description": "Blink.",
                            "output_mode": "body_action",
                            "bindings": [],
                        }
                    ]
                }
            )
        )

    def test_compound_numeric_binding_audit_recovers_duration(self):
        segmented = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Turn in place.",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "Look at the user for 2 seconds.",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        audited_bindings = binding_audit(
            [],
            [
                {
                    "name": "duration_s",
                    "entity_type": "duration_seconds",
                    "value": "2",
                    "confidence": 1.0,
                }
            ],
        )
        coverage = responsibility_coverage(
            responsibility_item("Turn in place", 0),
            responsibility_item("look at me for two seconds", 1),
        )
        ollama = ScriptedOllama([segmented, coverage, audited_bindings])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Turn in place, then look at me for two seconds.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(
            ollama.prompts[2][1]["prompt_family"],
            "goal_association.binding_audit",
        )
        self.assertEqual(
            result.new_goals[1].object["bindings"]["duration_s"]["value"],
            "2",
        )
        self.assertEqual(
            result.metadata["binding_audit"]["strategy"],
            "model_owned_material_parameter_audit",
        )
        audit_schema = ollama.prompts[2][1]["response_format"]
        self.assertEqual(
            audit_schema["$defs"]["GoalBindingAuditItem"]["properties"]
            ["candidate_goal_index"]["enum"],
            [0, 1],
        )

    def test_failed_model_semantic_review_fails_closed(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Look up today's weather.",
                    "output_mode": "capability_work",
                    "bindings": [],
                },
                {
                    "description": "Say the result.",
                    "output_mode": "speech",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([mixed, "not-json"])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Check the weather and tell me the result.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.metadata["status"], "model_contract_failed")
        self.assertTrue(result.metadata["semantic_review_attempted"])
        self.assertFalse(result.metadata["semantic_review_succeeded"])
        self.assertEqual(result.new_goals, [])
        self.assertTrue(result.clarification)

    def test_material_correction_after_contract_repair_gets_bound_replacement_goal(self):
        initial = {
            "decision": "associate",
            "associations": [
                {
                    "relationship": "replace",
                    "target_goal_ids": ["goal-weather"],
                    "updated_description": "Check today's weather in Neixiang.",
                    "confidence": 1.0,
                }
            ],
            "new_goals": [],
            "referent_updates": [
                {
                    "operation": "correct",
                    "target_referent_ids": [],
                    "confidence": 1.0,
                }
            ],
            "resolved_references": [],
            "confidence": 1.0,
        }
        repaired = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Check today's weather in Neixiang.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {"name": "location", "entity_type": "place", "value": "内乡", "confidence": 1.0},
                        {"name": "date", "entity_type": "date", "value": "today", "confidence": 1.0},
                    ],
                    "supersedes_goal_ids": ["goal-weather"],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Check today's weather in Neixiang.",
                    "output_mode": "capability_work",
                    "supersedes_goal_ids": ["goal-weather"],
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "place",
                            "value": "内乡",
                            "confidence": 1.0,
                        },
                        {
                            "name": "date",
                            "entity_type": "date",
                            "value": "today",
                            "confidence": 1.0,
                        },
                    ],
                }
            ],
            "referent_updates": [
                {
                    "operation": "introduce",
                    "entity_type": "place",
                    "canonical_value": "内乡",
                    "scope_kind": "goal",
                    "confidence": 1.0,
                }
            ],
            "resolved_references": [],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([initial, repaired, reviewed])
        existing_bindings = {
            "location": {
                "name": "location",
                "entity_type": "place",
                "value": "重庆",
                "confidence": 1.0,
            },
            "date": {
                "name": "date",
                "entity_type": "date",
                "value": "today",
                "confidence": 1.0,
            },
        }

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "不是重庆，我说的是内乡。",
                    active_goals=[
                        active_goal(
                            "goal-weather",
                            "Check today's weather in Chongqing.",
                            bindings=existing_bindings,
                        )
                    ],
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertEqual(result.associations, [])
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["value"],
            "内乡",
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn(
            "single_new_goal_with_retained_context",
            result.metadata["semantic_review"]["triggers"],
        )
        self.assertEqual(result.new_goals[0].supersedes_goal_ids, ["goal-weather"])
        self.assertIn("provenance-stable", ollama.prompts[2][0])
        self.assertIn("Do not infer a correction from words", ollama.prompts[2][0])

    def test_failed_semantic_review_preserves_successful_repair_evidence(self):
        repaired = {
            "decision": "associate",
            "associations": [
                {
                    "relationship": "modify",
                    "target_goal_ids": ["goal-weather"],
                    "updated_description": "Check today's weather in Neixiang.",
                    "confidence": 1.0,
                }
            ],
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([{}, repaired, "not-json"])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "不是重庆，我说的是内乡。",
                    active_goals=[
                        active_goal(
                            "goal-weather",
                            "Check today's weather in Chongqing.",
                        )
                    ],
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 3)
        self.assertTrue(result.metadata["contract_repair_attempted"])
        self.assertTrue(result.metadata["contract_repair_succeeded"])
        self.assertTrue(result.metadata["semantic_review_attempted"])
        self.assertFalse(result.metadata["semantic_review_succeeded"])
        self.assertIn("semantic review", result.reason_summary.lower())
        self.assertEqual(result.new_goals, [])

    def test_action_collection_review_repairs_merged_and_duplicated_goals(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "Walk while blinking and singing.",
                            "output_mode": "body_action",
                            "bindings": [
                                {
                                    "name": "actions",
                                    "entity_type": "physical_action_set",
                                    "value": "walking, blinking, singing",
                                    "confidence": 1.0,
                                }
                            ],
                        },
                        {"description": "Sing a song.", "output_mode": "singing", "bindings": []},
                    ],
                    "confidence": 1.0,
                },
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "Walk forward for 15 seconds.",
                            "output_mode": "body_action",
                            "bindings": [],
                        },
                        {
                            "description": "Blink eyes.",
                            "output_mode": "body_action",
                            "bindings": [],
                        },
                        {
                            "description": "Sing a song.",
                            "output_mode": "singing",
                            "bindings": [],
                        },
                    ],
                    "confidence": 1.0,
                },
                responsibility_coverage(
                    responsibility_item("Walk for 15 seconds", 0),
                    responsibility_item("blinking", 1),
                    responsibility_item("singing", 2),
                ),
                binding_audit(
                    [
                        {
                            "name": "duration_s",
                            "entity_type": "duration_seconds",
                            "value": "15",
                            "confidence": 1.0,
                        }
                    ],
                    [],
                    [],
                ),
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Walk for 15 seconds while blinking and singing.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 4)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            [
                "Walk forward for 15 seconds.",
                "Blink eyes.",
                "Sing a song.",
            ],
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )
        self.assertIn("No previous Goal DTO is supplied", ollama.prompts[1][0])
        self.assertNotIn("physical_action_set", ollama.prompts[1][0])
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["executable_action", "executable_action", "vocal_output"],
        )
        self.assertEqual(
            result.new_goals[0].object["bindings"]["duration_s"]["value"],
            "15",
        )
        goal_schema = ollama.prompts[0][1]["response_format"]["$defs"][
            "GoalAssociationModelGoal"
        ]
        self.assertIn("output_mode", goal_schema["required"])
        self.assertNotIn("responsibility_kind", goal_schema["properties"])

    def test_three_executable_actions_trigger_review_and_preserve_spoken_performance(self):
        initial = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": (
                        "Walk forward for 15 seconds while singing and blinking."
                    ),
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "duration",
                            "entity_type": "time_duration",
                            "value": "15 seconds",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Sing while walking forward.",
                    "output_mode": "body_action",
                    "bindings": [],
                },
                {
                    "description": "Blink eyes while walking forward.",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        reviewed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Walk forward for 15 seconds.",
                    "output_mode": "body_action",
                    "bindings": [
                        {
                            "name": "duration",
                            "entity_type": "time_duration",
                            "value": "15 seconds",
                            "confidence": 1.0,
                        }
                    ],
                },
                {
                    "description": "Sing while walking forward.",
                    "output_mode": "singing",
                    "bindings": [],
                },
                {
                    "description": "Blink eyes while walking forward.",
                    "output_mode": "body_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        coverage = responsibility_coverage(
            responsibility_item("往前走个15秒", 0),
            responsibility_item("边走边唱歌", 1),
            responsibility_item("眨眼睛", 2),
        )
        ollama = ScriptedOllama(
            [initial, reviewed, coverage, binding_audit([], [], [])]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。")
            )
        )

        self.assertEqual(len(ollama.prompts), 4)
        self.assertEqual(
            result.metadata["semantic_review"]["triggers"],
            ["multi_embodied_responsibility_review"],
        )
        self.assertEqual(
            [
                (
                    goal.metadata["responsibility_kind"],
                    goal.metadata["execution_lane"],
                    goal.metadata["output_mode"],
                    goal.metadata["provider_required"],
                )
                for goal in result.new_goals
            ],
            [
                ("executable_action", "activity", "body_action", True),
                ("vocal_output", "vocal", "singing", True),
                ("executable_action", "activity", "body_action", True),
            ],
        )
        review_prompt, review_kwargs = ollama.prompts[1]
        self.assertIn("No previous Goal DTO is supplied", review_prompt)
        self.assertNotIn("DTO to review JSON", review_prompt)
        self.assertIn("semantic work and evidence that complete", review_prompt)
        self.assertIn("vocal performance", review_prompt)
        self.assertEqual(
            review_kwargs["prompt_family"],
            "goal_association.semantic_resegmentation",
        )
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_fresh_goal_resegmentation",
        )

    def test_associates_followup_before_creating_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.96, "reason_summary": "The user refined the coffee goal.", "updated_description": "Get iced coffee"}], "new_goals": [], "confidence": 0.96, "reason_summary": "Continuity before creation."})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual([item.relationship for item in result.associations], ["modify"])
        self.assertEqual(result.associations[0].target_goal_ids, ["goal-coffee"])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.metadata["authority"], "advisory")

    def test_can_update_existing_goal_and_create_independent_new_goal(self):
        ollama = FakeOllama(
            {
                "associations": [
                    {
                        "relationship": "modify",
                        "target_goal_ids": ["goal-coffee"],
                        "confidence": 0.91,
                        "updated_description": "Get iced coffee",
                    }
                ],
                "new_goals": [
                    {
                        "description": "Report the current weather.",
                        "output_mode": "capability_work",
                    }
                ],
                "confidence": 0.91,
            }
        )
        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "咖啡要冰的，顺便查一下天气。",
                    active_goals=[active_goal("goal-coffee", "Get coffee")],
                )
            )
        )
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].description, "Report the current weather.")
        self.assertTrue(result.new_goals[0].goal_id.startswith("goal_"))

    def test_model_goal_transport_noise_is_rejected_and_host_owns_canonical_fields(self):
        noisy = {
            "new_goals": [
                {
                    "id": "goal_1",
                    "source_text": "model-authored source",
                    "constraints": {"invented": True},
                    "success_criteria": ["model-authored criterion"],
                    "description": "Respond to the greeting",
                    "output_mode": "speech",
                }
            ],
            "confidence": 0.94,
        }
        repaired = {
            "new_goals": [
                {
                    "description": "Respond to the greeting",
                    "output_mode": "speech",
                }
            ],
            "confidence": 0.94,
        }
        ollama = ScriptedOllama([noisy, repaired])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Hello.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(ollama.prompts[1][1]["prompt_family"], "goal_association.repair")
        self.assertEqual([goal.description for goal in result.new_goals], ["Respond to the greeting"])
        self.assertTrue(result.new_goals[0].goal_id.startswith("goal_"))
        self.assertNotEqual(result.new_goals[0].goal_id, "goal_1")
        self.assertEqual(result.new_goals[0].source_text, "Hello.")
        self.assertEqual(result.new_goals[0].constraints, {})
        self.assertEqual(result.new_goals[0].success_criteria, ["Respond to the greeting"])
        self.assertEqual(result.metadata["model_contract"], "GoalSegmentationModelOutput")
        self.assertTrue(result.metadata["host_generated_identifiers"])


    def test_missing_minimal_description_uses_one_model_repair(self):
        ollama = ScriptedOllama([
            {
                "new_goals": [
                    {"open_semantic_description": "Walk forward for one second"},
                    {"open_semantic_description": "Blink twice"},
                ],
                "confidence": 0.9,
            },
            {
                "new_goals": [
                    {"description": "Walk forward for one second", "output_mode": "body_action"},
                    {"description": "Blink twice", "output_mode": "body_action"},
                ],
                "confidence": 0.9,
            },
            responsibility_coverage(
                responsibility_item("Walk forward for one second", 0),
                responsibility_item("Blink twice", 1),
            ),
            binding_audit([], []),
        ])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Walk forward for one second, then blink twice.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 4)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Walk forward for one second", "Blink twice"],
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("open_semantic_description", ollama.prompts[1][0])
        self.assertIn(
            "Each new_goals item contains description, output_mode, optional media_operation, bindings, optional supersedes_goal_ids, and optional provider-neutral resource_responsibility only",
            ollama.prompts[1][0],
        )


    def test_direct_explicit_location_uses_binding_and_referent_update(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "查询今晚重庆天气并判断是否炎热。",
                        "output_mode": "capability_work",
                        "bindings": [
                            {
                                "name": "location",
                                "entity_type": "location",
                                "value": "重庆",
                                "confidence": 1.0,
                            },
                            {
                                "name": "time_scope",
                                "entity_type": "time",
                                "value": "tonight",
                                "confidence": 1.0,
                            },
                        ],
                    }
                ],
                "referent_updates": [
                    {
                        "operation": "introduce",
                        "entity_type": "location",
                        "canonical_value": "重庆",
                        "scope_kind": "goal",
                        "confidence": 1.0,
                        "reason_summary": "重庆是用户当前明确指定并且后续可能引用的地点。",
                    }
                ],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "The user explicitly named the weather location.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("今天晚上重庆热不热？")
            )
        )

        self.assertEqual(result.new_goals[0].object["bindings"]["location"]["value"], "重庆")
        self.assertEqual(result.resolved_references, [])
        self.assertEqual(result.referent_updates[0].referent.canonical_value, "重庆")
        prompt = ollama.prompts[0][0]
        self.assertIn("Do not emit resolved_references for an ordinary explicit entity mention", prompt)

    def test_missing_resolved_reference_confidence_uses_contract_repair(self):
        neixiang = {
            "referent_id": "ref-neixiang",
            "entity_type": "location",
            "canonical_value": "内乡",
            "scope_kind": "conversation",
            "scope_ids": [],
            "status": "foreground",
            "confidence": 1.0,
            "source_turn_id": "turn-neixiang",
            "source_goal_ids": [],
        }
        ollama = ScriptedOllama(
            [
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "查询今天内乡是否下雨。",
                            "output_mode": "capability_work",
                            "bindings": [
                                {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "内乡",
                                    "referent_id": "ref-neixiang",
                                    "confidence": 1.0,
                                }
                            ],
                        }
                    ],
                    "referent_updates": [],
                    "resolved_references": [
                        {
                            "surface_form": "那边",
                            "entity_type": "location",
                            "resolved_value": "内乡",
                            "source": "discourse_referent",
                            "referent_id": "ref-neixiang",
                        }
                    ],
                    "clarification": "",
                    "confidence": 1.0,
                    "reason_summary": "Resolve the foreground place.",
                },
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "查询今天内乡是否下雨。",
                            "output_mode": "capability_work",
                            "bindings": [
                                {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "内乡",
                                    "referent_id": "ref-neixiang",
                                    "confidence": 1.0,
                                }
                            ],
                        }
                    ],
                    "referent_updates": [],
                    "resolved_references": [
                        {
                            "surface_form": "那边",
                            "entity_type": "location",
                            "resolved_value": "内乡",
                            "source": "discourse_referent",
                            "referent_id": "ref-neixiang",
                            "confidence": 1.0,
                            "reason_summary": "内乡是当前前景地点。",
                        }
                    ],
                    "clarification": "",
                    "confidence": 1.0,
                    "reason_summary": "Resolve the foreground place.",
                },
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "今天那边下雨了没有？",
                    discourse_referents=[neixiang],
                    discourse_focus=["ref-neixiang"],
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.resolved_references[0].confidence, 1.0)
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("Every resolved reference and referent update must include explicit confidence", ollama.prompts[1][0])

    def test_location_correction_creates_scoped_referent_and_goal_binding(self):
        chongqing = {
            "referent_id": "ref-chongqing",
            "entity_type": "location",
            "canonical_value": "重庆",
            "scope_kind": "goal",
            "scope_ids": ["goal-chongqing-weather"],
            "status": "foreground",
            "confidence": 1.0,
            "source_turn_id": "turn-chongqing",
            "source_goal_ids": ["goal-chongqing-weather"],
        }
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "确认用户纠正的地点是内乡。",
                        "output_mode": "speech",
                        "bindings": [
                            {
                                "name": "location",
                                "entity_type": "location",
                                "value": "内乡",
                                "confidence": 1.0,
                            }
                        ],
                    }
                ],
                "referent_updates": [
                    {
                        "operation": "correct",
                        "entity_type": "location",
                        "canonical_value": "内乡",
                        "target_referent_ids": ["ref-chongqing"],
                        "scope_kind": "conversation",
                        "confidence": 1.0,
                        "reason_summary": "用户明确纠正地点为内乡。",
                    }
                ],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "The current discourse location was corrected.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "不是重庆，是一个地名叫内乡。",
                    discourse_referents=[chongqing],
                    discourse_focus=["ref-chongqing"],
                )
            )
        )

        self.assertEqual(len(result.referent_updates), 1)
        update = result.referent_updates[0]
        self.assertEqual(update.operation, "correct")
        self.assertEqual(update.target_referent_ids, ["ref-chongqing"])
        self.assertEqual(update.referent.canonical_value, "内乡")
        binding = result.new_goals[0].object["bindings"]["location"]
        self.assertEqual(binding["value"], "内乡")
        self.assertEqual(binding["referent_id"], update.referent.referent_id)

    def test_candidate_goal_location_clarification_gets_semantic_review(self):
        chongqing = {
            "referent_id": "ref-chongqing",
            "entity_type": "location",
            "canonical_value": "重庆",
            "scope_kind": "goal",
            "scope_ids": ["goal-chongqing-weather"],
            "status": "foreground",
            "confidence": 1.0,
            "source_turn_id": "turn-chongqing",
            "source_goal_ids": ["goal-chongqing-weather"],
        }
        proposed_clarification = {
            "decision": "clarify",
            "associations": [],
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "Which Neixiang do you mean?",
            "confidence": 1.0,
            "reason_summary": "The provider may find more than one place.",
        }
        reviewed = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "查询用户纠正后的内乡天气。",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "location",
                            "value": "内乡",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            "referent_updates": [
                {
                    "operation": "correct",
                    "entity_type": "location",
                    "canonical_value": "内乡",
                    "target_referent_ids": ["ref-chongqing"],
                    "scope_kind": "conversation",
                    "confidence": 1.0,
                    "reason_summary": "用户直接提供了新的地点绑定。",
                }
            ],
            "resolved_references": [],
            "clarification": "",
            "confidence": 1.0,
            "reason_summary": "The exact replacement binding can be resolved downstream.",
        }
        ollama = ScriptedOllama([proposed_clarification, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "不是重庆，我说的是内乡。",
                    active_goals=[
                        active_goal(
                            "goal-chongqing-weather",
                            "查询重庆今天的天气。",
                            bindings={
                                "location": {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "重庆",
                                    "confidence": 1.0,
                                }
                            },
                        )
                    ],
                    discourse_referents=[chongqing],
                    discourse_focus=["ref-chongqing"],
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            result.metadata["semantic_review"]["triggers"],
            ["candidate_goal_clarification_continuity"],
        )
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["value"],
            "内乡",
        )
        self.assertEqual(result.referent_updates[0].operation, "correct")
        self.assertIn("provider canonicalization", ollama.prompts[1][0])

    def test_pronoun_resolves_from_foreground_referent_not_stale_tool_evidence(self):
        chongqing = {
            "referent_id": "ref-chongqing",
            "entity_type": "location",
            "canonical_value": "重庆",
            "scope_kind": "goal",
            "scope_ids": ["goal-chongqing-weather"],
            "status": "background",
            "confidence": 1.0,
            "source_turn_id": "turn-chongqing",
            "source_goal_ids": ["goal-chongqing-weather"],
        }
        neixiang = {
            "referent_id": "ref-neixiang",
            "entity_type": "location",
            "canonical_value": "内乡",
            "scope_kind": "conversation",
            "scope_ids": [],
            "status": "foreground",
            "confidence": 1.0,
            "source_turn_id": "turn-neixiang",
            "source_goal_ids": [],
            "supersedes_referent_ids": ["ref-chongqing"],
        }
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "查询今天内乡是否下雨。",
                        "output_mode": "capability_work",
                        "bindings": [
                            {
                                "name": "location",
                                "entity_type": "location",
                                "value": "内乡",
                                "referent_id": "ref-neixiang",
                                "confidence": 1.0,
                            },
                            {
                                "name": "date",
                                "entity_type": "date",
                                "value": "today",
                                "confidence": 1.0,
                            },
                        ],
                    }
                ],
                "referent_updates": [],
                "resolved_references": [
                    {
                        "surface_form": "那边",
                        "entity_type": "location",
                        "resolved_value": "内乡",
                        "source": "discourse_referent",
                        "referent_id": "ref-neixiang",
                        "confidence": 1.0,
                        "reason_summary": "内乡是当前前景地点。",
                    }
                ],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "The foreground location resolves the reference.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "今天那边下雨了没有？",
                    discourse_referents=[chongqing, neixiang],
                    discourse_focus=["ref-chongqing", "ref-neixiang"],
                    recent_tool_evidence=[
                        {
                            "evidence_id": "old-chongqing",
                            "tool_id": "chromie.weather.lookup",
                            "request_args": {"location": "重庆", "date": "today"},
                            "data": {"condition": "雷雨", "precipitation_probability": 65},
                        }
                    ],
                    history=[
                        {"role": "user", "text": "不是重庆，是一个地名叫内乡。"},
                        {"role": "assistant", "text": "我明白了，内乡是河南省的一个县。"},
                    ],
                )
            )
        )

        self.assertEqual(result.resolved_references[0].resolved_value, "内乡")
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["value"],
            "内乡",
        )
        prompt = ollama.prompts[0][0]
        self.assertIn('"canonical_value":"内乡"', prompt)
        self.assertNotIn("old-chongqing", prompt)
        self.assertNotIn('"condition":"雷雨"', prompt)

    def test_last_task_reference_is_associated_by_llm_semantics(self):
        ollama = FakeOllama(
            {
                "decision": "associate",
                "associations": [
                    {
                        "relationship": "reference",
                        "target_goal_ids": ["goal-weather"],
                        "confidence": 0.98,
                        "reason_summary": (
                            "The user's phrase refers to the previously described "
                            "weather task in the supplied active Goal context."
                        ),
                    }
                ],
                "new_goals": [],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "",
                "confidence": 0.98,
                "reason_summary": "The model semantically selected the referenced Goal.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Please continue the last task I told you.",
                    language="en-US",
                    active_goals=[
                        active_goal("goal-coffee", "Order an iced coffee"),
                        active_goal("goal-weather", "Check the weather in Neixiang"),
                    ],
                    history=[
                        {"role": "user", "text": "Check the weather in Neixiang."},
                        {"role": "assistant", "text": "I will check it."},
                    ],
                )
            )
        )

        self.assertEqual(len(result.associations), 1)
        self.assertEqual(result.associations[0].relationship, "reference")
        self.assertEqual(
            result.associations[0].target_goal_ids,
            ["goal-weather"],
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("the last task I told you", prompt)
        self.assertIn("not from a Host phrase table", prompt)
        self.assertIn('"goal_id":"goal-weather"', prompt)
        self.assertIn('"goal_id":"goal-coffee"', prompt)

    def test_social_reaction_after_completed_weather_is_a_fresh_spoken_goal(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "associations": [],
                "new_goals": [
                    {
                        "description": "回应用户认为26度有点冷并准备赶紧离开的反应。",
                        "output_mode": "speech",
                        "bindings": [],
                    }
                ],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": (
                    "The latest turn is a new conversational reaction and practical "
                    "decision; the completed weather result is supporting context."
                ),
            }
        )
        completed = active_goal(
            "goal-weather",
            "判断重庆一会儿是否会下大雨。",
            work_status="done",
                            responsibility_status="satisfied",
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "是得赶紧走啊。",
                    recent_goals=[completed],
                    history=[
                        {"role": "assistant", "text": "重庆有雷雨和冰雹预报。"},
                    ],
                )
            )
        )

        self.assertEqual(result.associations, [])
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.new_goals[0].metadata["responsibility_kind"],
            "vocal_output",
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("latest turn is a social reaction", prompt)
        self.assertIn("prior delivered information remains context", prompt)
        self.assertIn("Do not use continue or reference merely because the topic overlaps", prompt)

    def test_recent_terminal_goal_remains_a_bounded_association_candidate(self):
        ollama = FakeOllama(
            {
                "decision": "associate",
                "associations": [
                    {
                        "relationship": "reference",
                        "target_goal_ids": ["goal-weather"],
                        "confidence": 0.99,
                        "reason_summary": "The follow-up asks about the retained weather Goal.",
                    }
                ],
                "new_goals": [],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "",
                "confidence": 0.99,
                "reason_summary": "Continuity with the recent completed lookup.",
            }
        )
        completed = active_goal(
            "goal-weather",
            "Check today's weather in Beijing",
            work_status="done",
                            responsibility_status="satisfied",
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "So is it hot or not?",
                    language="en-US",
                    recent_goals=[completed],
                    history=[
                        {"role": "user", "text": "Check today's weather in Beijing."},
                        {"role": "assistant", "text": "Beijing is hot today."},
                    ],
                )
            )
        )

        self.assertEqual(result.associations[0].target_goal_ids, ["goal-weather"])
        self.assertEqual(result.new_goals, [])
        prompt = ollama.prompts[0][0]
        self.assertIn("retained recent terminal Goal", prompt)
        self.assertIn('"responsibility_status":"satisfied"', prompt)

    def test_schema_forbids_reference_objects_without_supplied_referents(self):
        schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
        )

        self.assertEqual(
            schema["properties"]["resolved_references"]["maxItems"],
            0,
        )

    def test_ambiguous_reference_returns_natural_clarification_only(self):
        ollama = FakeOllama({"associations": [], "new_goals": [], "clarification": "你是说咖啡不用了，还是天气也不用查了？", "confidence": 0.58})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("算了，不用了。", active_goals=[active_goal("goal-coffee", "Get coffee"), active_goal("goal-weather", "Check weather")])))
        self.assertEqual(result.clarification, "你是说咖啡不用了，还是天气也不用查了？")
        self.assertEqual(result.associations, [])
        self.assertNotIn("goal-coffee", result.clarification)

    def test_unknown_goal_target_is_rejected_and_falls_back_to_clarification(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-invented"], "confidence": 0.99, "updated_description": "Get iced coffee"}], "new_goals": [], "confidence": 0.99})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)
        self.assertEqual(result.metadata["status"], "needs_clarification")

    def test_prompt_requires_continuity_before_creation_and_no_plan_step_goals(self):
        ollama = FakeOllama({"associations": [{"relationship": "continue", "target_goal_ids": ["goal-a"], "confidence": 0.9}], "new_goals": [], "confidence": 0.9})
        asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("继续。", active_goals=[active_goal("goal-a", "Do A")])
            )
        )
        prompt, kwargs = ollama.prompts[0]
        self.assertIn("Resolve continuity before creation", prompt)
        self.assertIn("Do not split implementation steps into goals", prompt)
        self.assertIn("host owns all IDs", prompt)
        self.assertIn('relationship must be copied exactly from ["continue","modify","clarify"', prompt)
        self.assertIn("clarify means the current user turn supplies missing information", prompt)
        self.assertIn("Use reference when the current turn asks to retrieve, restate", prompt)
        self.assertIn("Do not use continue or reference merely because the topic overlaps", prompt)
        self.assertNotIn("continues, modifies", prompt)
        schema = kwargs["response_format"]
        self.assertIsInstance(schema, dict)
        self.assertEqual(
            set(schema["properties"]),
            {"decision", "associations", "new_goals", "referent_updates", "resolved_references", "clarification", "confidence", "reason_summary"},
        )
        self.assertEqual(
            schema["properties"]["decision"]["enum"],
            ["associate", "create_goals", "clarify"],
        )
        self.assertIn("decision", schema["required"])
        self.assertNotIn("oneOf", schema)
        self.assertEqual(
            set(schema["$defs"]["GoalAssociationModelGoal"]["properties"]),
            {
                "description",
                "output_mode",
                "media_operation",
                "bindings",
                "resource_responsibility",
                "progress_candidate_ids",
                "related_goal_ids",
                "supersedes_goal_ids",
            },
        )
        resolved_reference_schema = schema["$defs"]["GoalAssociationModelResolvedReference"]
        self.assertEqual(
            resolved_reference_schema["properties"]["source"]["enum"],
            ["discourse_referent", "active_goal_binding"],
        )
        self.assertIn("referent_id", resolved_reference_schema["required"])
        self.assertIn("confidence", resolved_reference_schema["required"])
        referent_update_schema = schema["$defs"]["GoalAssociationModelReferentUpdate"]
        self.assertIn("confidence", referent_update_schema["required"])

        self.assertEqual(
            schema["$defs"]["GoalAssociationModelAssociation"]["properties"]["relationship"]["enum"],
            [
                "continue",
                "modify",
                "clarify",
                "confirm",
                "reject",
                "cancel",
                "pause",
                "resume",
                "merge",
                "split",
                "reference",
            ],
        )


    def test_progress_candidate_ids_are_decoder_constrained_and_materialized(self):
        candidate = {
            "candidate_id": "progress-weather-today",
            "kind": "capability",
            "capability_id": "chromie.weather.lookup",
            "args": {"location": "Chongqing", "date": "today"},
            "intent": "chromie.weather.lookup",
            "confidence": 0.99,
        }
        payload = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Check today's Chongqing weather and answer whether heavy rain is expected.",
                    "output_mode": "capability_work",
                    "bindings": [
                        {
                            "name": "location",
                            "entity_type": "place",
                            "value": "Chongqing",
                            "confidence": 1.0,
                        },
                        {
                            "name": "date",
                            "entity_type": "temporal_scope",
                            "value": "today",
                            "confidence": 1.0,
                        },
                    ],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "today's Chongqing weather",
                        "source_status": "provider_resolved",
                        "delivery_mode": "spoken_explanation",
                    },
                    "progress_candidate_ids": ["progress-weather-today"],
                    "related_goal_ids": ["goal-dinner"],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.98,
            "reason_summary": "The current read directly supports the new weather Goal and informs dinner planning.",
        }
        ollama = FakeOllama(payload)

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Will it rain heavily in Chongqing today?",
                    language="en-US",
                    route="tool",
                    intent="chromie.weather.lookup",
                    active_goals=[active_goal("goal-dinner", "Go out for dinner tonight")],
                    progress_candidates=[candidate],
                )
            )
        )

        schema = ollama.prompts[0][1]["response_format"]
        goal_properties = schema["$defs"]["GoalAssociationModelGoal"]["properties"]
        self.assertEqual(
            goal_properties["progress_candidate_ids"]["items"]["enum"],
            ["progress-weather-today"],
        )
        self.assertEqual(
            goal_properties["related_goal_ids"]["items"]["enum"],
            ["goal-dinner"],
        )
        self.assertEqual(len(result.new_goals), 1)
        goal = result.new_goals[0]
        self.assertEqual(goal.related_goal_ids, ["goal-dinner"])
        self.assertEqual(len(result.progress_bindings), 1)
        self.assertEqual(result.progress_bindings[0].candidate_id, "progress-weather-today")
        self.assertEqual(result.progress_bindings[0].goal_ids, [goal.goal_id])

    def test_native_response_progress_binds_only_to_spoken_goal(self):
        candidate = {
            "candidate_id": "progress-native-answer",
            "kind": "native_response",
            "response_text": "I'm Chromie!",
            "speech_act": "answer",
            "intent": "identity_question",
            "confidence": 0.99,
        }
        payload = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Answer the user's identity question.",
                    "output_mode": "speech",
                    "media_operation": "none",
                    "bindings": [],
                    "progress_candidate_ids": ["progress-native-answer"],
                    "related_goal_ids": [],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.99,
            "reason_summary": "The ready native response directly satisfies the new spoken Goal.",
        }
        ollama = FakeOllama(payload)

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "What is your name?",
                    language="en-US",
                    route="chat",
                    intent="identity_question",
                    progress_candidates=[candidate],
                )
            )
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(len(result.progress_bindings), 1)
        self.assertEqual(result.progress_bindings[0].candidate_id, "progress-native-answer")
        self.assertEqual(
            result.progress_bindings[0].goal_ids,
            [result.new_goals[0].goal_id],
        )

    def test_unknown_progress_candidate_is_rejected(self):
        payload = {
            "decision": "create_goals",
            "associations": [],
            "new_goals": [
                {
                    "description": "Check today's Chongqing weather.",
                    "output_mode": "capability_work",
                    "bindings": [],
                    "resource_responsibility": {
                        "resource_kind": "information",
                        "resource_description": "today's Chongqing weather",
                        "source_status": "provider_resolved",
                        "delivery_mode": "spoken_explanation",
                    },
                    "progress_candidate_ids": ["invented-progress"],
                    "related_goal_ids": [],
                }
            ],
            "referent_updates": [],
            "resolved_references": [],
            "clarification": "",
            "confidence": 0.9,
            "reason_summary": "invalid candidate reference",
        }
        ollama = ScriptedOllama(
            [
                payload,
                {
                    "decision": "clarify",
                    "associations": [],
                    "new_goals": [],
                    "referent_updates": [],
                    "resolved_references": [],
                    "clarification": "I need to verify what information to retrieve.",
                    "confidence": 0.6,
                    "reason_summary": "The progress reference was invalid.",
                },
            ]
        )
        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Check the weather.",
                    language="en-US",
                    route="tool",
                    intent="chromie.weather.lookup",
                    progress_candidates=[],
                )
            )
        )
        self.assertFalse(result.progress_bindings)
        self.assertTrue(result.clarification)

    def test_invalid_enum_uses_one_schema_constrained_model_repair(self):
        ollama = ScriptedOllama(
            [
                {
                    "associations": [
                        {
                            "relationship": "continues",
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.95,
                        }
                    ],
                    "confidence": 0.95,
                },
                {
                    "associations": [
                        {
                            "relationship": "continue",
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.95,
                        }
                    ],
                    "confidence": 0.95,
                },
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("继续。", active_goals=[active_goal("goal-a", "Do A")])
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.associations[0].relationship, "continue")
        self.assertEqual(
            result.metadata["contract_repair"]["strategy"],
            "schema_constrained_model_revision",
        )
        repair_prompt, repair_kwargs = ollama.prompts[1]
        self.assertIn('"continues"', repair_prompt)
        self.assertIn("literal_error", repair_prompt)
        self.assertIn("GoalAssociationModelOutput JSON Schema", repair_prompt)
        self.assertIsInstance(repair_kwargs["response_format"], dict)

    def test_explanation_followup_repairs_delta_free_clarify_to_reference(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "associate",
                    "associations": [
                        {
                            "relationship": "clarify",
                            "target_goal_ids": ["goal-weather"],
                            "confidence": 1.0,
                            "reason_summary": (
                                "The user asks for a definitive judgment from the "
                                "weather evidence already delivered."
                            ),
                        }
                    ],
                    "new_goals": [],
                    "referent_updates": [],
                    "resolved_references": [],
                    "clarification": "",
                    "confidence": 1.0,
                    "reason_summary": "The turn follows up on the retained Goal.",
                },
                {
                    "decision": "associate",
                    "associations": [
                        {
                            "relationship": "reference",
                            "target_goal_ids": ["goal-weather"],
                            "confidence": 1.0,
                            "reason_summary": (
                                "The user asks for an interpretation of evidence "
                                "already delivered for this Goal."
                            ),
                        }
                    ],
                    "new_goals": [],
                    "referent_updates": [],
                    "resolved_references": [],
                    "clarification": "",
                    "confidence": 1.0,
                    "reason_summary": "Reference the retained Goal without changing it.",
                },
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "So is it hot or not?",
                    recent_goals=[
                        active_goal(
                            "goal-weather",
                            "Check whether today's weather in Beijing is hot.",
                            work_status="done",
                            responsibility_status="satisfied",
                        )
                    ],
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.associations[0].relationship, "reference")
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn(
            "relationship=clarify requires updated_description or resolved_gap_ids",
            ollama.prompts[1][0],
        )

    def test_failed_model_repair_fails_closed_without_a_third_call(self):
        invalid = {
            "associations": [
                {
                    "relationship": "continues",
                    "target_goal_ids": ["goal-a"],
                    "confidence": 0.95,
                }
            ],
            "confidence": 0.95,
        }
        ollama = ScriptedOllama([invalid, invalid])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("继续。", active_goals=[active_goal("goal-a", "Do A")])
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.metadata["status"], "model_contract_failed")
        self.assertEqual(result.metadata["failure_class"], "structured_output_validation")
        self.assertTrue(result.metadata["contract_repair_attempted"])
        self.assertFalse(result.metadata["contract_repair_succeeded"])
        initial_ref = result.metadata["initial_raw_output_ref"]
        self.assertGreater(initial_ref["chars"], 0)
        self.assertRegex(initial_ref["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("initial_raw_output", result.metadata)
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)

    def test_no_active_goals_schema_forbids_associations_and_requires_new_goal_or_clarification(self):
        ollama = FakeOllama({
            "new_goals": [{
                "description": "Blink twice",
                "output_mode": "body_action",
                "source_text": "Blink twice",
                "constraints": {},
                "success_criteria": ["Blink twice"],
            }],
            "clarification": "",
            "confidence": 0.95,
        })

        asyncio.run(GoalAssociationResolver(ollama).resolve(request("Blink twice", language="en-US")))

        schema = ollama.prompts[0][1]["response_format"]
        self.assertNotIn("associations", schema["properties"])
        self.assertNotIn("GoalAssociationModelAssociation", schema.get("$defs", {}))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["decision"]["enum"],
            ["create_goals", "clarify"],
        )
        self.assertIn("decision", schema["required"])
        self.assertIn("new_goals", schema["required"])
        self.assertIn("clarification", schema["required"])
        self.assertNotIn("oneOf", schema)
        prompt = ollama.prompts[0][0]
        self.assertIn("contract intentionally has no associations field", prompt)
        self.assertIn("one new goal for each independently satisfiable user responsibility", prompt)
        self.assertIn("standalone social interaction", prompt)
        self.assertIn(
            "physical action and a conversational answer or spoken performance are independent goals",
            prompt,
        )
        self.assertIn("acquisition and delivery stages that together constitute one human responsibility are one Goal", prompt)
        self.assertIn("external search, evidence retrieval, evaluation, and spoken explanation", prompt)
        self.assertNotIn("Apply continuity before creation", ollama.prompts[0][1]["system"])
        self.assertIn("association with existing work is impossible", ollama.prompts[0][1]["system"])
        self.assertIn(
            "Conversational framing attached to a substantive responsibility",
            ollama.prompts[0][1]["system"],
        )
        self.assertIn(
            "one evidence acquisition satisfies both a factual lookup",
            ollama.prompts[0][1]["system"],
        )

    def test_empty_greeting_segmentation_repairs_to_one_conversational_goal(self):
        ollama = ScriptedOllama(
            [
                {
                    "new_goals": [],
                    "clarification": "",
                    "confidence": 0.95,
                    "reason_summary": "No responsibilities to segment.",
                },
                {
                    "new_goals": [
                        {"description": "Respond naturally to the user's greeting", "output_mode": "speech"}
                    ],
                    "clarification": "",
                    "confidence": 0.98,
                    "reason_summary": "The greeting is one conversational goal.",
                },
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Hello.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.clarification, "")
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Respond naturally to the user's greeting"],
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("standalone social interaction", ollama.prompts[1][0])

    def test_no_active_goal_fabricated_association_repairs_under_segmentation_contract(self):
        invalid_live_output = {
            "associations": [
                {
                    "relationship": "continue",
                    "target_goal_ids": [],
                    "confidence": 1.0,
                    "reason_summary": "Continuity with no active goals",
                }
            ]
        }
        ollama = ScriptedOllama(
            [
                invalid_live_output,
                {
                    "new_goals": [
                        {"description": "Look at the user for two seconds", "output_mode": "body_action"},
                        {"description": "Blink twice", "output_mode": "body_action"},
                    ],
                    "clarification": "",
                    "confidence": 0.96,
                    "reason_summary": "Two independent requested actions.",
                },
                responsibility_coverage(
                    responsibility_item("Look at me for two seconds", 0),
                    responsibility_item("blink twice", 1),
                ),
                binding_audit([], []),
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Look at me for two seconds, then blink twice.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 4)
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertEqual(result.associations, [])
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Look at the user for two seconds", "Blink twice"],
        )
        for _, kwargs in ollama.prompts:
            self.assertNotIn("associations", kwargs["response_format"]["properties"])
        self.assertIn("Existing-goal associations are structurally invalid", ollama.prompts[1][0])

    def test_no_active_goal_repeated_fabrication_fails_closed_with_relevant_clarification(self):
        invalid_live_output = {
            "associations": [
                {
                    "relationship": "continue",
                    "target_goal_ids": [],
                    "confidence": 1.0,
                }
            ]
        }
        ollama = ScriptedOllama([invalid_live_output, invalid_live_output])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Nod twice, then blink once.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.metadata["status"], "model_contract_failed")
        self.assertEqual(
            result.metadata["contract_schema"],
            "GoalSegmentationModelOutput",
        )
        self.assertEqual(result.associations, [])
        self.assertEqual(result.new_goals, [])
        self.assertNotIn("already doing", result.clarification)
        self.assertIn("rephrase", result.clarification)

    def test_no_active_goal_can_return_clarification_without_association(self):
        ollama = FakeOllama(
            {
                "new_goals": [],
                "clarification": "Which object should I look at?",
                "confidence": 0.55,
                "reason_summary": "The target is ambiguous.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Look at it.", language="en-US")
            )
        )

        self.assertEqual(result.associations, [])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.clarification, "Which object should I look at?")

    def test_create_goals_discriminant_ignores_inactive_clarification_branch(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {"description": "Check today's weather in Chongqing", "output_mode": "capability_work"}
                ],
                "clarification": (
                    "The request is already explicit; this explanatory text belongs "
                    "to no user-facing clarification branch."
                ),
                "confidence": 0.96,
                "reason_summary": "One explicit information goal.",
            }
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("今天重庆热不热？", language="zh-CN")
            )
        )

        self.assertEqual(result.clarification, "")
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Check today's weather in Chongqing"],
        )
        self.assertEqual(len(ollama.prompts), 1)
        prompt = ollama.prompts[0][0]
        self.assertNotIn("Cognitive Core interpretation output", prompt)
        self.assertIn("runtime diagnostics", prompt)

    def test_dynamic_schema_limits_existing_targets_to_active_goal_ids(self):
        ollama = FakeOllama({
            "associations": [{
                "relationship": "continue",
                "target_goal_ids": ["goal-a"],
                "confidence": 0.95,
            }],
            "new_goals": [],
            "clarification": "",
            "confidence": 0.95,
        })

        asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("continue", active_goals=[active_goal("goal-a", "Do A")], language="en-US")
            )
        )

        schema = ollama.prompts[0][1]["response_format"]
        association_schema = schema["$defs"]["GoalAssociationModelAssociation"]
        self.assertEqual(
            association_schema["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-a"],
        )
        self.assertEqual(
            association_schema["properties"]["target_goal_ids"]["minItems"],
            1,
        )

    def test_model_failure_is_safe_and_advisory(self):
        ollama = FakeOllama(RuntimeError("offline"))
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("继续。", active_goals=[active_goal("goal-a", "Do A")])))
        self.assertEqual(result.metadata["status"], "model_unavailable")
        self.assertFalse(result.metadata["contract_repair_attempted"])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)

    def test_truncation_failure_reports_domain_without_causal_attribution(self):
        error = OllamaGenerationError(
            "structured JSON output was truncated",
            failure_class="output_truncated",
            failure_domain="llm_budget",
            architecture_attribution="not_evaluated",
            retryable=True,
            details={"done_reason": "length", "num_predict": 512},
        )

        result = asyncio.run(
            GoalAssociationResolver(FakeOllama(error)).resolve(request("继续。"))
        )

        self.assertEqual(result.metadata["status"], "model_unavailable")
        self.assertEqual(result.metadata["failure_class"], "output_truncated")
        self.assertEqual(result.metadata["failure_domain"], "llm_budget")
        self.assertEqual(result.metadata["architecture_attribution"], "not_evaluated")
        self.assertEqual(result.metadata["done_reason"], "length")

    def test_resolution_contract_rejects_clarification_mixed_with_changes(self):
        with self.assertRaises(ValueError):
            GoalAssociationResolution(turn_id="turn-1", clarification="Which one?", new_goals=[{"goal_id": "goal-new", "description": "New goal", "source_text": "New goal", "beneficiary": "user", "constraints": {}, "success_criteria": [], "metadata": {}}])


class OrchestratorGoalAssociationTests(unittest.TestCase):
    def test_report_only_schedules_without_changing_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision

        class Client:
            async def resolve_goal_association(self, *args, **kwargs):
                return GoalAssociationResolution(turn_id="turn-report", associations=[{"association_id": "assoc-report", "relationship": "continue", "target_goal_ids": ["goal-a"], "confidence": 0.9}], confidence=0.9)

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.goal_association_mode = "report_only"
            assistant.goal_association_timeout_ms = 1000
            assistant.enable_agent = True
            assistant.agent_client = Client()
            assistant.goal_association_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None
            decision = OrchestratorRouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm")
            reviewed = assistant._schedule_goal_association_report(object(), user_text="继续。", session_id="sid", context={"history": [], "active_goal_snapshots": [active_goal("goal-a", "Do A")]}, decision=decision)
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(reviewed.metadata["goal_association_resolution"]["status"], "scheduled")
            pending = list(assistant.goal_association_report_tasks)
            if pending:
                await asyncio.gather(*pending)
        asyncio.run(run())

    def test_off_is_noop(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.goal_association_mode = "off"
        assistant.enable_agent = True
        decision = OrchestratorRouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm")
        reviewed = assistant._schedule_goal_association_report(object(), user_text="hello", session_id="sid", context={"active_goal_snapshots": []}, decision=decision)
        self.assertIs(reviewed, decision)


    def test_substantive_request_framing_does_not_create_style_goals(self) -> None:
        resolver = GoalAssociationResolver(FakeOllama({}))  # type: ignore[arg-type]
        tool_request = AgentRunRequest(
            sid="style-goal-guard",
            text="你好，帮我查重庆天气热不热。",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool",
                intent="weather.lookup",
                confidence=0.95,
                source="llm",
            ),
            context={
                "active_goal_snapshots": [],
                "history": [],
                "interaction_context": {
                    "events": [{"event_id": "ledger-goal-marker"}]
                },
            },
        )
        prompt = resolver._build_prompt(
            tool_request,
            [],
            output_type=GoalSegmentationModelOutput,
        )

        self.assertIn("politeness preamble", prompt)
        self.assertIn("identity and personality shape expression only", prompt)
        self.assertIn("one Goal when one capability result can satisfy both", prompt)
        self.assertIn("not by the channel used later to report that outcome", prompt)
        self.assertIn(
            "output_mode is the completion discriminant",
            prompt,
        )
        self.assertIn(
            "The fact that a capability result will later be spoken",
            prompt,
        )
        self.assertNotIn(
            "capability_dependent/activity/capability_work/true",
            prompt,
        )
        self.assertIn("ledger-goal-marker", prompt)
        system_prompt = resolver._system_prompt(GoalSegmentationModelOutput)
        self.assertIn(
            "Conversational framing attached to a substantive responsibility",
            system_prompt,
        )
        self.assertIn(
            "one evidence acquisition satisfies both a factual lookup",
            system_prompt,
        )


if __name__ == "__main__":
    unittest.main()
