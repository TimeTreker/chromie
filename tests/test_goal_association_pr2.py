from __future__ import annotations

import asyncio
import unittest

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import GoalAssociationResolver
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


def request(text: str, *, active_goals=None, history=None, language="zh-CN"):
    return AgentRunRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        route_decision=RouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm"),
        context={"active_goal_snapshots": active_goals or [], "history": history or []},
    )


def active_goal(goal_id: str, description: str):
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "status": "open",
        "goal": {
            "goal_id": goal_id,
            "version": 1,
            "description": description,
            "source_text": description,
            "beneficiary": "user",
            "constraints": {},
            "success_criteria": [],
            "metadata": {},
        },
        "open_information_gaps": [],
        "commitment_state": "none",
        "last_user_update": description,
        "metadata": {},
    }


class GoalAssociationResolverTests(unittest.TestCase):
    def test_associates_followup_before_creating_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.96, "reason_summary": "The user refined the coffee goal."}], "new_goals": [], "confidence": 0.96, "reason_summary": "Continuity before creation."})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual([item.relationship for item in result.associations], ["modify"])
        self.assertEqual(result.associations[0].target_goal_ids, ["goal-coffee"])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.metadata["authority"], "advisory")

    def test_can_update_existing_goal_and_create_independent_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.91}], "new_goals": [{"description": "Report the current weather.", "source_text": "顺便查一下天气。", "beneficiary": "user", "constraints": {}, "success_criteria": ["Current weather is reported."], "metadata": {}}], "confidence": 0.91})
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
        self.assertIn("Each new_goals item contains only description", ollama.prompts[1][0])

    def test_ambiguous_reference_returns_natural_clarification_only(self):
        ollama = FakeOllama({"associations": [], "new_goals": [], "clarification": "你是说咖啡不用了，还是天气也不用查了？", "confidence": 0.58})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("算了，不用了。", active_goals=[active_goal("goal-coffee", "Get coffee"), active_goal("goal-weather", "Check weather")])))
        self.assertEqual(result.clarification, "你是说咖啡不用了，还是天气也不用查了？")
        self.assertEqual(result.associations, [])
        self.assertNotIn("goal-coffee", result.clarification)

    def test_unknown_goal_target_is_rejected_and_falls_back_to_clarification(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-invented"], "confidence": 0.99}], "new_goals": [], "confidence": 0.99})
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
        self.assertNotIn("continues, modifies", prompt)
        schema = kwargs["response_format"]
        self.assertIsInstance(schema, dict)
        self.assertEqual(
            set(schema["properties"]),
            {"associations", "new_goals", "clarification", "confidence", "reason_summary"},
        )
        self.assertEqual(
            set(schema["$defs"]["GoalAssociationModelGoal"]["properties"]),
            {"description"},
        )
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
        self.assertEqual(len(schema["oneOf"]), 2)
        self.assertEqual(
            schema["oneOf"][0]["properties"]["clarification"]["minLength"],
            1,
        )
        self.assertEqual(
            schema["oneOf"][0]["properties"]["new_goals"]["maxItems"],
            0,
        )
        self.assertEqual(
            schema["oneOf"][1]["properties"]["clarification"]["maxLength"],
            0,
        )
        self.assertEqual(
            schema["oneOf"][1]["properties"]["new_goals"]["minItems"],
            1,
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("contract intentionally has no associations field", prompt)
        self.assertIn("one new goal for each independently satisfiable user responsibility", prompt)
        self.assertIn("standalone social interaction", prompt)
        self.assertIn("physical action and a conversational answer are independent goals", prompt)
        self.assertNotIn("Apply continuity before creation", ollama.prompts[0][1]["system"])
        self.assertIn("association with existing work is impossible", ollama.prompts[0][1]["system"])

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


if __name__ == "__main__":
    unittest.main()
