from __future__ import annotations

import asyncio
import unittest

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import (
    GoalAssociationModelOutput,
    GoalAssociationResolver,
    GoalSegmentationModelOutput,
)
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution


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
        },
    )


def active_goal(goal_id: str, description: str, *, bindings=None, status="open"):
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "status": status,
        "goal": {
            "goal_id": goal_id,
            "version": 1,
            "description": description,
            "source_text": description,
            "beneficiary": "user",
            "object": {"bindings": bindings or {}},
            "constraints": {},
            "success_criteria": [],
            "metadata": {},
        },
        "open_information_gaps": [],
        "commitment_state": "none",
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
    def test_preassociation_clarify_route_does_not_force_goal_loss(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": (
                            "Recommend interesting places near the user."
                        ),
                        "responsibility_kind": "capability_dependent",
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

    def test_explicit_location_binding_repairs_non_verbatim_model_value(self):
        mistranslated = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Check whether it is raining in Xiang County.",
                    "responsibility_kind": "capability_dependent",
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
                    "responsibility_kind": "capability_dependent",
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
                    "responsibility_kind": "capability_dependent",
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
                    "responsibility_kind": "capability_dependent",
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
                            "responsibility_kind": "capability_dependent",
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
                            "responsibility_kind": "spoken_response",
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
                            "responsibility_kind": "capability_dependent",
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
        self.assertEqual(
            result.metadata["semantic_review"]["strategy"],
            "model_owned_goal_association_review",
        )

    def test_embodied_request_is_split_and_acknowledgement_is_not_a_goal(self):
        merged = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "跑出50米并帮用户拿一杯水，然后返回。",
                    "responsibility_kind": "executable_action",
                    "bindings": [],
                },
                {
                    "description": "回应用户的请求。",
                    "responsibility_kind": "spoken_response",
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
                    "responsibility_kind": "executable_action",
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
                    "description": "拿一杯水。",
                    "responsibility_kind": "executable_action",
                    "bindings": [],
                },
                {
                    "description": "返回用户身边。",
                    "responsibility_kind": "executable_action",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([merged, reviewed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("你能往前给我跑个50米，帮我拿杯水，然后回来吗？")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["往前移动50米。", "拿一杯水。", "返回用户身边。"],
        )
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["executable_action", "executable_action", "executable_action"],
        )
        self.assertEqual(
            result.metadata["semantic_review"]["triggers"],
            ["embodied_responsibility_decomposition"],
        )
        review_prompt = ollama.prompts[1][0]
        self.assertIn("acknowledgement, confirmation", review_prompt)
        self.assertIn("acquiring or manipulating an object", review_prompt)
        self.assertIn("Identity shapes expression only", review_prompt)

    def test_independent_spoken_performance_survives_model_semantic_review(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Look up today's weather in Neixiang County.",
                    "responsibility_kind": "capability_dependent",
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
                    "responsibility_kind": "spoken_response",
                    "bindings": [],
                },
            ],
            "confidence": 1.0,
        }
        ollama = ScriptedOllama([mixed, mixed])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Check today's weather in Neixiang County and sing a short song.",
                    language="en-US",
                )
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["capability_dependent", "spoken_response"],
        )
        self.assertIn("such as a song, joke", ollama.prompts[1][0])

    def test_failed_model_semantic_review_fails_closed(self):
        mixed = {
            "decision": "create_goals",
            "new_goals": [
                {
                    "description": "Look up today's weather.",
                    "responsibility_kind": "capability_dependent",
                    "bindings": [],
                },
                {
                    "description": "Say the result.",
                    "responsibility_kind": "spoken_response",
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
                    "responsibility_kind": "capability_dependent",
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
        self.assertEqual(
            result.metadata["semantic_review"]["triggers"],
            ["existing_goal_semantic_update"],
        )
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
                            "bindings": [
                                {
                                    "name": "actions",
                                    "entity_type": "physical_action_set",
                                    "value": "walking, blinking, singing",
                                    "confidence": 1.0,
                                }
                            ],
                        },
                        {"description": "Sing a song.", "bindings": []},
                    ],
                    "confidence": 1.0,
                },
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "description": "Walk forward for 15 seconds.",
                            "responsibility_kind": "executable_action",
                            "bindings": [],
                        },
                        {
                            "description": "Blink eyes.",
                            "responsibility_kind": "executable_action",
                            "bindings": [],
                        },
                        {
                            "description": "Sing a song.",
                            "responsibility_kind": "spoken_response",
                            "bindings": [],
                        },
                    ],
                    "confidence": 1.0,
                },
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

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            [
                "Walk forward for 15 seconds.",
                "Blink eyes.",
                "Sing a song.",
            ],
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("physical_action_set", ollama.prompts[1][0])
        self.assertEqual(
            [goal.metadata["responsibility_kind"] for goal in result.new_goals],
            ["executable_action", "executable_action", "spoken_response"],
        )
        goal_schema = ollama.prompts[0][1]["response_format"]["$defs"][
            "GoalAssociationModelGoal"
        ]
        self.assertIn("responsibility_kind", goal_schema["required"])

    def test_associates_followup_before_creating_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.96, "reason_summary": "The user refined the coffee goal.", "updated_description": "Get iced coffee"}], "new_goals": [], "confidence": 0.96, "reason_summary": "Continuity before creation."})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual([item.relationship for item in result.associations], ["modify"])
        self.assertEqual(result.associations[0].target_goal_ids, ["goal-coffee"])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.metadata["authority"], "advisory")

    def test_can_update_existing_goal_and_create_independent_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.91, "updated_description": "Get iced coffee"}], "new_goals": [{"description": "Report the current weather.", "source_text": "顺便查一下天气。", "beneficiary": "user", "constraints": {}, "success_criteria": ["Current weather is reported."], "metadata": {}}], "confidence": 0.91})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("咖啡要冰的，顺便查一下天气。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].description, "Report the current weather.")
        self.assertTrue(result.new_goals[0].goal_id.startswith("goal_"))

    def test_model_transport_noise_is_ignored_and_host_owns_canonical_fields(self):
        ollama = FakeOllama({
            "new_goals": [
                {
                    "id": "goal_1",
                    "constraints": [],
                    "source_text": "Look at me for two seconds",
                    "success_criteria": "User is observed",
                    "description": "Look at the user for two seconds",
                },
                {
                    "id": "goal_2",
                    "constraints": [],
                    "description": "Blink twice",
                },
            ],
            "confidence": 0.94,
        })

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Look at me for two seconds, then blink twice.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Look at the user for two seconds", "Blink twice"],
        )
        self.assertTrue(all(goal.goal_id.startswith("goal_") for goal in result.new_goals))
        self.assertNotIn("goal_1", [goal.goal_id for goal in result.new_goals])
        self.assertTrue(all(goal.constraints == {} for goal in result.new_goals))
        self.assertTrue(
            all(
                goal.source_text == "Look at me for two seconds, then blink twice."
                for goal in result.new_goals
            )
        )
        self.assertEqual(
            [goal.success_criteria for goal in result.new_goals],
            [["Look at the user for two seconds"], ["Blink twice"]],
        )
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
                    {"description": "Walk forward for one second"},
                    {"description": "Blink twice"},
                ],
                "confidence": 0.9,
            },
        ])

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Walk forward for one second, then blink twice.", language="en-US")
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            [goal.description for goal in result.new_goals],
            ["Walk forward for one second", "Blink twice"],
        )
        self.assertTrue(result.metadata["contract_repair"]["succeeded"])
        self.assertIn("open_semantic_description", ollama.prompts[1][0])
        self.assertIn(
            "Each new_goals item contains description, responsibility_kind, and bindings only",
            ollama.prompts[1][0],
        )


    def test_direct_explicit_location_uses_binding_and_referent_update(self):
        ollama = FakeOllama(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "查询今晚重庆天气并判断是否炎热。",
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
                    "responsibility_kind": "capability_dependent",
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
                        "responsibility_kind": "spoken_response",
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
            status="done",
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
            "spoken_response",
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
        completed = active_goal("goal-weather", "Check today's weather in Beijing")
        completed["status"] = "done"
        completed["commitment_state"] = "completed"

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
        self.assertIn('"status":"done"', prompt)

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
            {"description", "responsibility_kind", "bindings"},
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
                "replace",
                "merge",
                "split",
                "reference",
            ],
        )

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
                            status="done",
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
        self.assertIn("continues", result.metadata["initial_raw_output"])
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)

    def test_no_active_goals_schema_forbids_associations_and_requires_new_goal_or_clarification(self):
        ollama = FakeOllama({
            "new_goals": [{
                "description": "Blink twice",
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
        self.assertIn("including actions requested simultaneously", prompt)
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
                        {"description": "Respond naturally to the user's greeting"}
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
                        {"description": "Look at the user for two seconds"},
                        {"description": "Blink twice"},
                    ],
                    "clarification": "",
                    "confidence": 0.96,
                    "reason_summary": "Two independent requested actions.",
                },
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

        self.assertEqual(len(ollama.prompts), 2)
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
                    {"description": "Check today's weather in Chongqing"}
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
            context={"active_goal_snapshots": [], "history": []},
        )
        prompt = resolver._build_prompt(
            tool_request,
            [],
            output_type=GoalSegmentationModelOutput,
        )

        self.assertIn("politeness preamble", prompt)
        self.assertIn("identity and personality shape expression only", prompt)
        self.assertIn("one Goal when one capability result can satisfy both", prompt)
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
