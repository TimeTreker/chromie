from __future__ import annotations

import asyncio
import unittest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.planner_contract import validate_planner_model_output
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.plan import CanonicalPlan


class SequencedOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FullCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(
                capability_id="soridormi.walk_forward", agent_id="capability_agent",
                description="Walk forward", route="robot_action", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]},
                can_run_parallel=False, parallel_metadata_declared=True,
                exclusive_group="base_motion", resource_claims=["base_motion"],
            ),
            CatalogCapability(
                capability_id="soridormi.blink_eyes", agent_id="capability_agent",
                description="Blink eyes", route="robot_action", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]},
                can_run_parallel=True, parallel_metadata_declared=True,
                exclusive_group="eye_expression", resource_claims=["eye_expression"],
            ),
            CatalogCapability(
                capability_id="soridormi.look_at_person", agent_id="capability_agent",
                description="Look at a person", route="robot_action", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={
                    "type": "object",
                    "properties": {
                        "duration_s": {"type": "number", "minimum": 0.1},
                        "target_ref": {"type": "string"},
                    },
                    "required": ["duration_s", "target_ref"],
                },
            ),
            CatalogCapability(
                capability_id="rare.observe_doorway", agent_id="capability_agent",
                description="Observe doorway", route="tool", available=True,
                interaction_executable=True, prompt_tier="rare",
                input_schema={"type":"object","properties":{}},
            ),
            CatalogCapability(
                capability_id="chromie.speak", agent_id="capability_agent",
                description="Speak text", route="chat", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
        ]
        self.scopes = []

    async def prompt_entries(self, **kwargs):
        self.scopes.append(kwargs.get("scope"))
        return self.items


def request(text="往前走15秒，然后眨眼。", *, goal_ids=None):
    goal_ids = list(goal_ids or ["goal-action"])
    return AgentRunRequest(
        sid="sid-pr4", text=text, language="zh-CN",
        route_decision=RouteDecision(route="robot_action", intent="semantic_capability_planning", confidence=0.0, source="llm"),
        context={
            "fast_plan_resolution":{"disposition":"escalate","coverage":"partial","steps":[]},
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {"goal_id": goal_id, "description": f"Goal {goal_id}"}
                    for goal_id in goal_ids
                ],
            },
        }, history=[])


class CanonicalDeepPlanContractTests(unittest.TestCase):
    def test_deep_partial_plan_can_clarify_without_steps(self):
        plan = CanonicalPlan(plan_id="p", planner_tier="deep", disposition="clarify", coverage="partial", confidence=0.7, unresolved=["duration"])
        self.assertEqual(plan.disposition, "clarify")

    def test_deep_plan_cannot_escalate_back_to_fast(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="deep", disposition="escalate", coverage="uncertain", confidence=0.0, escalation_reason="retry fast")


class DeepPlannerResolverTests(unittest.TestCase):
    def test_full_catalog_exact_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.91,"goal_ids":["goal-action"],"goal_summary":"walk then blink","steps":[
            {"step_id":"walk","skill_id":"soridormi.walk_forward","args":{"duration_s":15},"source_goal_ids":["goal-action"]},
            {"step_id":"blink","skill_id":"soridormi.blink_eyes","args":{"count":4},"source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        catalog = FullCatalog()
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([raw]), catalog).resolve(request()))
        self.assertEqual(plan.planner_tier, "deep")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(catalog.scopes, ["all"])
        self.assertEqual(plan.metadata["attempt_count"], 1)

    def test_invalid_first_plan_is_revised_once_in_same_tier(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"goal_ids":["goal-action"],"steps":[
            {"step_id":"blink","skill_id":"soridormi.blink_eyes","args":{"count":99},"source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        revised = {"disposition":"execute","coverage":"complete","confidence":0.93,"goal_ids":["goal-action"],"steps":[
            {"step_id":"blink","skill_id":"soridormi.blink_eyes","args":{"count":4},"source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        ollama = SequencedOllama([invalid, revised])
        plan = asyncio.run(DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(request("眨眼。")))
        self.assertEqual(plan.steps[0].args["count"], 4)
        self.assertEqual(plan.metadata["attempt_count"], 2)
        self.assertIn("invalid_args", ollama.prompts[1][0])
        self.assertNotIn("Fast Planner decides again", ollama.prompts[1][0])

    def test_contract_repair_reports_hidden_multi_goal_defects_together(self):
        goal_ids = ["goal-walk", "goal-blink"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "satisfaction": {"score": 1.0, "status": "substantial"},
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "satisfaction": {"score": 1.0, "status": "substantial"},
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "substantial"},
        }
        repaired = {
            **invalid,
            "disposition": "execute",
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = SequencedOllama([invalid, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("Walk for one second, then blink twice.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual([item.step_ids for item in plan.goal_outcomes], [["walk"], ["blink"]])
        repair_prompt = ollama.prompts[1][0]
        self.assertIn("goal satisfaction score is inconsistent with status", repair_prompt)
        self.assertIn("execute goal outcome requires complete coverage and step_ids", repair_prompt)
        self.assertIn("top-level disposition must match per-goal outcome dispositions", repair_prompt)
        self.assertIn("regenerate one fresh complete object", repair_prompt)
        self.assertIn("Previous Deep Planner model output JSON, when doing a semantic runtime replan:\nnull", repair_prompt)

    def test_contract_repair_exposes_missing_mixed_response_text(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "satisfaction": {"score": 1.0, "status": "substantial"},
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "rationale": "A short joke will be provided later.",
                    "satisfaction": {"score": 1.0, "status": "substantial"},
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "substantial"},
        }
        repaired = {
            **invalid,
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "step_ids": [],
                    "response_text": "Why did the robot nap? It needed to recharge.",
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = SequencedOllama([invalid, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("Blink twice and tell me a short joke.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(plan.goal_outcomes[1].disposition, "respond")
        repair_prompt = ollama.prompts[1][0]
        self.assertIn("respond goal outcome requires complete coverage and response_text", repair_prompt)
        self.assertIn("execute goal outcome requires complete coverage and step_ids", repair_prompt)
        self.assertIn("actual answer text now", repair_prompt)


    def test_missing_goal_outcomes_mixed_plan_repairs_under_required_schema(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                    "reason_summary": "Execute the requested physical blink action.",
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        repaired = {
            **invalid,
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "Why did the robot take a break? It needed to recharge.",
                    "step_ids": [],
                    "satisfaction": {"score": 1.0, "status": "exact"},
                },
            },
        }
        ollama = SequencedOllama([invalid, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("Blink twice and tell me a short joke.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(
            [item.disposition for item in plan.goal_outcomes],
            ["execute", "respond"],
        )
        self.assertEqual(len(ollama.prompts), 2)
        for _, kwargs in ollama.prompts:
            schema = kwargs["response_format"]
            self.assertIn("goal_outcomes", schema["required"])
            self.assertEqual(
                schema["properties"]["goal_outcomes"]["required"],
                goal_ids,
            )

    def test_goal_outcome_schema_uses_exact_unique_goal_key_map(self):
        schema = DeepPlannerResolver._response_schema(["goal-look", "goal-blink"])

        outcomes = schema["properties"]["goal_outcomes"]
        self.assertEqual(outcomes["type"], "object")
        self.assertFalse(outcomes["additionalProperties"])
        self.assertEqual(outcomes["required"], ["goal-look", "goal-blink"])
        self.assertEqual(
            list(outcomes["properties"]),
            ["goal-look", "goal-blink"],
        )
        self.assertEqual(outcomes["minProperties"], 2)
        self.assertEqual(outcomes["maxProperties"], 2)
        self.assertEqual(schema["title"], "DeepPlannerModelOutput")
        self.assertNotIn("oneOf", schema)
        self.assertNotIn("goal_ids", schema["properties"])
        self.assertIn("confidence", schema["required"])
        self.assertIn("goal_satisfaction", schema["required"])
        self.assertIn("goal_outcomes", schema["required"])
        satisfaction_schema = schema["$defs"]["PlannerGoalSatisfaction"]
        self.assertIn(
            "not a measurement of whether execution has already happened",
            satisfaction_schema["properties"]["score"]["description"],
        )
        self.assertNotIn("goal_id", schema["$defs"]["PlannerModelGoalOutcome"]["properties"])
        self.assertNotIn("metadata", schema["properties"])
        self.assertNotIn(
            "metadata",
            schema["$defs"]["PlannerModelGoalOutcome"]["properties"],
        )
        self.assertNotIn(
            "metadata",
            schema["$defs"]["PlannerModelStep"]["properties"],
        )
        self.assertIn("plan_relation", schema["properties"])
        self.assertIn("user_confirmation_required", schema["properties"])

    def test_exact_live_branch_minimal_plan_repairs_and_host_materializes_goal_ids(self):
        goal_ids = ["goal_2691cf9a52bfcaf9eefd", "goal_b027e0b6aae39d61e48f"]
        steps = [
            {
                "step_id": "step_look_at_user",
                "skill_id": "soridormi.look_at_person",
                "args": {"duration_s": 2.0, "target_ref": "person"},
                "source_goal_ids": [goal_ids[0]],
                "reason_summary": "Look at the user for two seconds.",
            },
            {
                "step_id": "step_blink_twice",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": [goal_ids[1]],
                "reason_summary": "Blink twice.",
            },
        ]
        branch_minimal = {
            "planner_tier": "deep",
            "disposition": "execute",
            "coverage": "complete",
            "steps": steps,
        }
        repaired = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "steps": steps,
            "goal_outcomes": {
                goal_ids[0]: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_look_at_user"],
                },
                goal_ids[1]: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_blink_twice"],
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }
        ollama = SequencedOllama([branch_minimal, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request(
                    "Look at me for two seconds, then blink twice.",
                    goal_ids=goal_ids,
                )
            )
        )

        self.assertEqual(plan.goal_ids, goal_ids)
        self.assertEqual(
            [step.source_goal_ids for step in plan.steps],
            [[goal_ids[0]], [goal_ids[1]]],
        )
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertNotIn("oneOf", response_schema)
        self.assertEqual(ollama.prompts[1][1]["response_format"], response_schema)

    def test_multi_goal_step_ownership_is_never_filled_from_all_host_goals(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                }
            ],
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        plan = asyncio.run(
            DeepPlannerResolver(
                SequencedOllama([invalid, invalid]),
                FullCatalog(),
                max_replans=1,
            ).resolve(
                request(
                    "Walk and blink.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertIn("source_goal_ids", plan.metadata["initial_validation_errors"])
        self.assertTrue(plan.metadata["repair_raw_output"])
        self.assertNotIn("source_goal_ids", plan.metadata["repair_raw_output"])

    def test_live_blink_and_joke_speech_step_repairs_to_mixed_respond_outcome(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step_blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
                {
                    "step_id": "step_joke",
                    "skill_id": "chromie.speak",
                    "args": {"text": "Why don't robots panic? They keep their cache."},
                    "source_goal_ids": ["goal-joke"],
                },
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_blink"],
                },
                "goal-joke": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_joke"],
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }
        outcome_satisfaction = lambda goal_id: {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        }
        repaired = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [invalid["steps"][0]],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_blink"],
                    "satisfaction": outcome_satisfaction("goal-blink"),
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "step_ids": [],
                    "response_text": "Why don't robots panic? They keep their cache.",
                    "satisfaction": outcome_satisfaction("goal-joke"),
                },
            },
            "goal_satisfaction": invalid["goal_satisfaction"],
        }
        ollama = SequencedOllama([invalid, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(
                request(
                    "Blink twice and tell me a short joke.",
                    goal_ids=goal_ids,
                )
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual([step.skill_id for step in plan.steps], ["soridormi.blink_eyes"])
        self.assertEqual(
            [outcome.disposition for outcome in plan.goal_outcomes],
            ["execute", "respond"],
        )
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("owned by Response Composer", ollama.prompts[1][0])
        skill_enum = ollama.prompts[0][1]["response_format"]["$defs"][
            "PlannerModelStep"
        ]["properties"]["skill_id"]["enum"]
        self.assertNotIn("chromie.speak", skill_enum)

    def test_live_blink_and_joke_nested_metadata_repairs_to_minimal_keyed_outcomes(self):
        goal_ids = ["goal-joke", "goal-blink"]
        satisfaction = lambda goal_id: {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        }
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step_blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
                {
                    "step_id": "step_neutral",
                    "skill_id": "soridormi.look_at_person",
                    "args": {"duration_s": 2.0, "target_ref": "person"},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
            "goal_outcomes": {
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "Why did the robot cross the road? To recharge its batteries.",
                    "metadata": {"step_ids": []},
                    "satisfaction": satisfaction("goal-joke"),
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "metadata": {"step_ids": ["step_blink", "step_neutral"]},
                    "satisfaction": satisfaction("goal-blink"),
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }
        repaired = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [invalid["steps"][0]],
            # Intentionally reverse insertion order. The host must materialize
            # canonical outcomes in Goal Association's authoritative order.
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_blink"],
                    "satisfaction": satisfaction("goal-blink"),
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "step_ids": [],
                    "response_text": "Why did the robot cross the road? To recharge its batteries.",
                    "satisfaction": satisfaction("goal-joke"),
                },
            },
            "goal_satisfaction": invalid["goal_satisfaction"],
        }
        ollama = SequencedOllama([invalid, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(
                request(
                    "Blink twice and tell me a short joke.",
                    goal_ids=goal_ids,
                )
            )
        )

        self.assertEqual([outcome.goal_id for outcome in plan.goal_outcomes], goal_ids)
        self.assertEqual([step.step_id for step in plan.steps], ["step_blink"])
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn("extra_forbidden", ollama.prompts[1][0])
        self.assertIn("Keep the plan minimal", ollama.prompts[1][0])

    def test_per_goal_satisfaction_cannot_claim_another_goal(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step_blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step_blink"],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-joke"],
                    },
                },
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "A short joke.",
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-joke"],
                    },
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "per-goal outcome satisfaction may reference only",
        ):
            validate_planner_model_output(
                invalid,
                planner_tier="deep",
                expected_goal_ids_for_turn=goal_ids,
            )

    def test_supplied_goal_outcome_map_must_match_authoritative_keys(self):
        goal_ids = ["goal-blink", "goal-joke"]
        base = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step_blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }
        execute_outcome = {
            "disposition": "execute",
            "coverage": "complete",
            "step_ids": ["step_blink"],
        }
        invalid_maps = {
            "empty": {},
            "partial": {"goal-blink": execute_outcome},
            "unknown": {
                "goal-blink": execute_outcome,
                "goal-invented": execute_outcome,
            },
            "legacy-list": [
                {"goal_id": "goal-blink", **execute_outcome},
                {"goal_id": "goal-joke", **execute_outcome},
            ],
            "embedded-goal-id": {
                "goal-blink": {"goal_id": "goal-blink", **execute_outcome},
                "goal-joke": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "A short joke.",
                    "goal_id": "goal-joke",
                },
            },
        }

        for label, goal_outcomes in invalid_maps.items():
            with self.subTest(label=label), self.assertRaises((ValueError, TypeError)):
                validate_planner_model_output(
                    {**base, "goal_outcomes": goal_outcomes},
                    planner_tier="deep",
                    expected_goal_ids_for_turn=goal_ids,
                )

    def test_pending_execution_is_not_treated_as_an_unmet_planning_requirement(self):
        goal_ids = ["goal-look", "goal-blink"]
        steps = [
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
        ]
        misunderstood = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": steps,
            "goal_outcomes": {
                "goal-look": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["look"],
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "partial",
                "satisfied_goal_ids": [],
                "unmet_requirements": ["All goals are pending execution of steps."],
            },
        }
        repaired = {
            **misunderstood,
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
                "unmet_requirements": [],
            },
        }
        ollama = SequencedOllama([misunderstood, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(
                request("Look at me, then blink.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.goal_satisfaction.status, "exact")
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn("prospective plan adequacy", ollama.prompts[1][0])

    def test_typed_material_alternative_is_host_materialized_for_confirmation(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "response_text": "I can do the safe adjusted version. Shall I proceed?",
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-action"],
            },
            "plan_relation": "safe_adjustment",
            "user_confirmation_required": True,
        }

        plan = asyncio.run(
            DeepPlannerResolver(SequencedOllama([raw]), FullCatalog()).resolve(
                request("Blink safely.")
            )
        )

        self.assertEqual(plan.metadata["plan_relation"], "safe_adjustment")
        self.assertTrue(plan.metadata["user_confirmation_required"])
        self.assertNotIn("plan_relation", type(plan).model_fields)

    def test_material_alternative_without_confirmation_is_rejected(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
            "plan_relation": "alternative",
            "user_confirmation_required": False,
        }

        with self.assertRaisesRegex(ValueError, "require user confirmation"):
            validate_planner_model_output(
                raw,
                planner_tier="deep",
                expected_goal_ids_for_turn=["goal-action"],
            )

    def test_material_alternative_without_explanation_is_rejected(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
            "plan_relation": "alternative",
            "user_confirmation_required": True,
        }

        with self.assertRaisesRegex(ValueError, "require response_text"):
            validate_planner_model_output(
                raw,
                planner_tier="deep",
                expected_goal_ids_for_turn=["goal-action"],
            )

    def test_empty_execute_outcome_is_repaired_by_model_not_host(self):
        context = {
            "goal_association_resolution": {
                "new_goals": [
                    {"goal_id": "goal-blink", "description": "blink twice"}
                ],
                "associations": [],
            }
        }
        req = request("Blink twice.").model_copy(update={"context": context})
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-blink"],
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": [],
                }
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        revised = {
            **invalid,
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                }
            },
        }
        ollama = SequencedOllama([invalid, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(req)
        )

        self.assertEqual(plan.goal_outcomes[0].step_ids, ["blink"])
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "execute goal outcome requires complete coverage and step_ids",
            ollama.prompts[1][0],
        )
        self.assertTrue(plan.metadata["contract_repair_succeeded"])

    def test_invented_internal_goal_is_rejected_and_revised(self):
        context = {
            "goal_association_resolution": {
                "new_goals": [
                    {"goal_id": "goal-look", "description": "look at the user"}
                ],
                "associations": [],
            }
        }
        req = request("Look at me.").model_copy(update={"context": context})
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-look", "goal-check-status"],
            "steps": [
                {
                    "step_id": "look",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-look"],
                },
                {
                    "step_id": "status",
                    "skill_id": "rare.observe_doorway",
                    "args": {},
                    "source_goal_ids": ["goal-check-status"],
                },
            ],
            "goal_outcomes": {
                "goal-look": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["look"],
                },
                "goal-check-status": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["status"],
                },
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        revised = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-look"],
            "steps": [
                {
                    "step_id": "look",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-look"],
                }
            ],
            "goal_outcomes": {
                "goal-look": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["look"],
                }
            },
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = SequencedOllama([invalid, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(req)
        )

        self.assertEqual(plan.goal_ids, ["goal-look"])
        self.assertEqual(len(plan.steps), 1)
        self.assertIn("goal_ids_do_not_match_goal_association", ollama.prompts[1][0])
        self.assertIn("Do not create goals for internal status checks", ollama.prompts[0][0])

    def test_transport_failure_does_not_consume_semantic_replan(self):
        error = OllamaGenerationError(
            "model timed out",
            failure_class="timeout",
            failure_domain="inference_transport",
            architecture_attribution="not_evaluated",
            retryable=True,
        )
        ollama = SequencedOllama([error])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("眨眼。")
            )
        )

        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.metadata["attempt_count"], 1)
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.metadata["failure_class"], "timeout")

    def test_contract_validation_failure_can_replan_once(self):
        invalid = ["not", "an", "object"]
        revised = {
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.8,
            "steps": [],
            "unresolved": ["duration"],
        }
        ollama = SequencedOllama([invalid, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("往前走。")
            )
        )

        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.metadata["attempt_count"], 2)
        self.assertIn("canonical_plan_contract_validation_failure", ollama.prompts[1][0])

    def test_legacy_step_shape_is_repaired_by_schema_constrained_model_revision(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-action"],
            "steps": [
                {
                    "step_type": "skill_execution",
                    "capability_id": "soridormi.blink_eyes",
                    "parameters": {"count": 2},
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        revised = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-action"],
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = SequencedOllama([invalid, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(
                request("眨两下眼。")
            )
        )

        self.assertEqual(plan.steps[0].skill_id, "soridormi.blink_eyes")
        self.assertEqual(plan.steps[0].args, {"count": 2})
        self.assertTrue(plan.metadata["contract_repair_attempted"])
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertIsInstance(response_schema, dict)
        self.assertEqual(response_schema.get("title"), "DeepPlannerModelOutput")
        self.assertEqual(ollama.prompts[1][1]["response_format"], response_schema)
        self.assertIn('"capability_id"', ollama.prompts[1][0])
        self.assertIn("extra_forbidden", ollama.prompts[1][0])
        self.assertIn("DeepPlannerModelOutput JSON Schema", ollama.prompts[1][0])

    def test_legacy_step_shape_is_not_locally_rewritten(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-action"],
            "steps": [
                {
                    "capability_id": "soridormi.blink_eyes",
                    "parameters": {"count": 2},
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }

        plan = asyncio.run(
            DeepPlannerResolver(
                SequencedOllama([invalid]),
                FullCatalog(),
                max_replans=0,
            ).resolve(request("眨两下眼。"))
        )

        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["reason"], "deep_planner_model_contract_failed")
        self.assertFalse(plan.metadata["contract_repair_attempted"])

    def test_repeated_invalid_plan_fails_closed_without_steps(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"goal_ids":["goal-action"],"steps":[
            {"skill_id":"invented.skill","args":{}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([invalid, invalid]), FullCatalog(), max_replans=1).resolve(request()))
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["attempt_count"], 2)

    def test_missing_essential_parameter_can_return_specific_clarification(self):
        raw = {"disposition":"clarify","coverage":"partial","confidence":0.84,"goal_summary":"walk forward","response_text":"你希望我往前走多久？","steps":[],"unresolved":["walking duration"]}
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([raw]), FullCatalog()).resolve(request("往前走。")))
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertIn("walking duration", plan.unresolved)

    def test_prompt_is_terminal_and_uses_skills_as_leaves(self):
        ollama = SequencedOllama([{"disposition":"clarify","coverage":"uncertain","confidence":0.7,"steps":[],"unresolved":["target"]}])
        asyncio.run(DeepPlannerResolver(ollama, FullCatalog()).resolve(request("看看门口。")))
        prompt = ollama.prompts[0][0]
        system = ollama.prompts[0][1]["system"]
        self.assertIn("Deep planning is terminal", prompt)
        self.assertIn("never call or return to the Fast Planner", system)

    def test_mixed_plan_checks_executable_goal_not_global_average(self):
        raw = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_ids": ["goal-nod", "goal-coffee"],
            "goal_summary": "Nod and report coffee unavailable.",
            "steps": [
                {
                    "step_id": "nod",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-nod"],
                }
            ],
            "goal_outcomes": {
                "goal-nod": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["nod"],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-nod"],
                    },
                },
                "goal-coffee": {
                    "disposition": "unavailable",
                    "coverage": "uncertain",
                    "response_text": "Coffee preparation is unavailable.",
                    "satisfaction": {
                        "score": 0.0,
                        "status": "unsatisfied",
                        "unmet_goal_ids": ["goal-coffee"],
                    },
                },
            },
            "goal_satisfaction": {
                "score": 0.5,
                "status": "partial",
                "satisfied_goal_ids": ["goal-nod"],
                "unmet_goal_ids": ["goal-coffee"],
            },
        }
        plan = asyncio.run(
            DeepPlannerResolver(
                SequencedOllama([raw]),
                FullCatalog(),
                min_goal_satisfaction=0.75,
            ).resolve(request("点头并准备咖啡。", goal_ids=["goal-nod", "goal-coffee"]))
        )
        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual([item.disposition for item in plan.goal_outcomes], ["execute", "unavailable"])
        self.assertEqual(plan.metadata["attempt_count"], 1)


class OrchestratorDeepPlannerTests(unittest.TestCase):
    def test_fast_escalation_triggers_report_only_deep_planner(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        class Client:
            def __init__(self):
                self.deep_context = None
            async def resolve_fast_plan(self, *args, **kwargs):
                return CanonicalPlan(plan_id="fast", planner_tier="fast", disposition="escalate", coverage="partial", confidence=0.8, escalation_reason="compound", steps=[])
            async def resolve_deep_plan(self, *args, **kwargs):
                self.deep_context = kwargs["context"]
                return CanonicalPlan(plan_id="deep", planner_tier="deep", disposition="execute", coverage="complete", confidence=0.9, goal_ids=["goal-action"], steps=[{"step_id":"s1","skill_id":"soridormi.blink_eyes","args":{"count":3},"source_goal_ids":["goal-action"]}], metadata={"attempt_count":1})

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_timeout_ms = 1000
            assistant.deep_planner_mode = "report_only"
            assistant.deep_planner_timeout_ms = 2000
            assistant.agent_client = Client()
            assistant.session_log = lambda *args, **kwargs: None
            decision = ODecision(route="robot_action", intent="semantic_capability_planning", confidence=0.0, source="llm")
            await assistant._run_fast_planner_report(object(), user_text="walk and blink", session_id="sid", context={"history":[]}, decision=decision)
            self.assertEqual(assistant.agent_client.deep_context["fast_plan_resolution"]["plan_id"], "fast")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
