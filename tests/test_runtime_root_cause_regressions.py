from __future__ import annotations

from agent.app import planner_validation
from agent.app import planner_deep_validation
from agent.app import planner_fast_validation
from agent.app import planner_schema
from agent.app import planner_prompt as planner_prompt

import inspect
import unittest

from types import MethodType
from typing import Any

from agent.app.goal_association import GoalAssociationResolver
from agent.app.planner_model_contract import PlannerModelOutput
from agent.app.planner_schema import (
    canonical_goal_binding_argument_response_schema,
    canonical_plan_response_schema,
    fast_multi_goal_response_schema,
)
from agent.app.planner_validation import (
    explicit_numeric_goal_values,
    information_goal_ids_without_declared_provider,
    qualify_capability_catalog_for_information_domains,
    validate_goal_responsibility_outcomes,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)
from tests.cognitive_work_test_support import cognitive_work_request
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from shared.chromie_contracts.interaction import CapabilityRequest
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.plan import canonical_plan_fingerprint


class _SequenceOllama:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.schemas: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt
        self.schemas.append(kwargs["response_format"])
        return self.replies.pop(0)


def _clarify_request() -> CognitiveWorkRequest:
    return cognitive_work_request(
        sid="clarify-authority",
        text="F.",
        language="en-US",
    )


def _allows_null(node: Any) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "null":
            return True
        return any(_allows_null(value) for value in node.values())
    if isinstance(node, list):
        return any(_allows_null(value) for value in node)
    return False


class RuntimeRootCauseRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_fast_validation_exposes_no_host_argument_restoration(self) -> None:
        self.assertFalse(
            hasattr(
                planner_fast_validation,
                "restore_required_capability_args_from_responsibilities",
            )
        )

    def test_typed_information_domain_qualifies_deep_planner_catalog(self) -> None:
        capabilities = [
            {
                "capability_id": "chromie.weather.lookup",
                "hints": {"semantic_scope": {"domain": "weather_forecast"}},
            },
            {
                "capability_id": "chromie.environment.observe",
                "hints": {
                    "semantic_scope": {
                        "domain": "direct_environment_perception",
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                    }
                },
            },
            {
                "capability_id": "chromie.memory.retrieve_verified_tool_result",
                "hints": {"semantic_scope": {}},
            },
        ]
        goals = [
            {
                "goal_id": "goal-presence",
                "resource_responsibility": {
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource": {
                        "kind": "information",
                        "attributes": {
                            "information_domain": {"value": "direct_environment_perception"}
                        },
                    },
                },
            }
        ]

        qualified = qualify_capability_catalog_for_information_domains(
            capabilities,
            authoritative_goals=goals,
        )

        self.assertEqual(
            [item["capability_id"] for item in qualified],
            [
                "chromie.environment.observe",
                "chromie.memory.retrieve_verified_tool_result",
            ],
        )
        broad_goal = [
            {
                "goal_id": "goal-broad-read",
                "resource_responsibility": {
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource": {
                        "kind": "information",
                        "attributes": {
                            "information_domain": {"value": "external_grounded_information"}
                        },
                    },
                },
            }
        ]
        self.assertEqual(
            qualify_capability_catalog_for_information_domains(
                capabilities,
                authoritative_goals=broad_goal,
            ),
            [capabilities[2]],
        )
        self.assertEqual(
            [
                item["capability_id"]
                for item in qualify_capability_catalog_for_information_domains(
                    capabilities,
                    authoritative_goals=broad_goal,
                    retained_capability_ids={"chromie.weather.lookup"},
                )
            ],
            [
                "chromie.weather.lookup",
                "chromie.memory.retrieve_verified_tool_result",
            ],
        )
        self.assertEqual(
            information_goal_ids_without_declared_provider(
                qualified,
                authoritative_goals=goals,
            ),
            set(),
        )
        self.assertEqual(
            information_goal_ids_without_declared_provider(
                [capabilities[0], capabilities[2]],
                authoritative_goals=goals,
            ),
            {"goal-presence"},
        )

        unavailable_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-presence"],
            allowed_capability_ids=[],
            requires_execution=True,
            unavailable_information_goal_ids=["goal-presence"],
        )
        self.assertEqual(
            unavailable_schema["properties"]["disposition"]["enum"],
            ["unavailable", "refused"],
        )
        unavailable_outcome = unavailable_schema["properties"]["goal_outcomes"]["properties"][
            "goal-presence"
        ]
        self.assertEqual(
            unavailable_outcome["properties"]["disposition"]["enum"],
            ["unavailable", "refused"],
        )
        self.assertEqual(
            unavailable_outcome["properties"]["response_text"]["minLength"],
            1,
        )

        incomplete_resource_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-mug"],
            allowed_capability_ids=["soridormi.acquire_resource"],
            requires_execution=True,
            unavailable_resource_goal_ids=["goal-mug"],
        )
        self.assertEqual(
            incomplete_resource_schema["properties"]["disposition"]["enum"],
            ["unavailable", "refused"],
        )
        incomplete_resource_outcome = incomplete_resource_schema["properties"]["goal_outcomes"][
            "properties"
        ]["goal-mug"]
        self.assertEqual(
            incomplete_resource_outcome["properties"]["disposition"]["enum"],
            ["unavailable", "refused"],
        )
        self.assertEqual(
            incomplete_resource_outcome["properties"]["step_ids"]["maxItems"],
            0,
        )

        mixed_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk", "goal-sing"],
            allowed_capability_ids=["soridormi.walk_forward"],
            requires_execution=True,
            provider_vocal_goal_ids=["goal-sing"],
        )
        self.assertIn(
            "mixed",
            mixed_schema["properties"]["disposition"]["enum"],
        )
        walk_outcome = mixed_schema["properties"]["goal_outcomes"]["properties"]["goal-walk"]
        self.assertIn(
            "execute",
            walk_outcome["properties"]["disposition"]["enum"],
        )
        sing_outcome = mixed_schema["properties"]["goal_outcomes"]["properties"]["goal-sing"]
        self.assertNotIn(
            "execute",
            sing_outcome["properties"]["disposition"]["enum"],
        )
        self.assertTrue(
            any(
                branch.get("properties", {}).get("disposition", {}).get("enum") == ["execute"]
                and branch.get("properties", {}).get("step_ids", {}).get("minItems") == 1
                for clause in walk_outcome["allOf"]
                for branch in clause.get("anyOf", [])
            )
        )
        self.assertTrue(
            any(
                branch.get("properties", {}).get("disposition", {}).get("enum") == ["mixed"]
                and branch.get("properties", {}).get("steps", {}).get("minItems") == 1
                for clause in mixed_schema["allOf"]
                for branch in clause.get("anyOf", [])
            )
        )

        single_fast = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )
        self.assertTrue(
            any(
                branch.get("properties", {}).get("disposition", {}).get("enum")
                and "escalate"
                in branch.get("properties", {}).get("disposition", {}).get("enum", [])
                and "exact"
                not in branch.get("properties", {})
                .get("goal_satisfaction", {})
                .get("properties", {})
                .get("status", {})
                .get("enum", [])
                for clause in single_fast["allOf"]
                for branch in clause.get("anyOf", [])
            )
        )
        self.assertEqual(
            sing_outcome["properties"]["step_ids"]["maxItems"],
            0,
        )

    def test_semantic_coverage_rejection_does_not_trigger_safety_revision(self) -> None:
        feedback = [
            {
                "type": "coordinated_action_coverage_incomplete",
                "uncovered_requirements": ["truthfully disclose unavailable singing"],
                "reason": "The Plan promises a performance marked unavailable.",
            }
        ]

        self.assertFalse(planner_validation.requires_safety_revision(feedback))
        self.assertFalse(hasattr(planner_deep_validation, "safety_revision_contract_errors"))
        self.assertFalse(hasattr(planner_schema, "deep_safety_revision_response_schema"))

    def test_planner_schema_requires_confirmation_for_material_adjustment(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk"],
            allowed_capability_ids=["soridormi.walk_forward"],
        )
        relation_constraint = next(
            item
            for item in schema["allOf"]
            if any(
                "plan_relation" in branch.get("properties", {}) for branch in item.get("anyOf", [])
            )
        )
        exact, adjusted = relation_constraint["anyOf"]

        self.assertNotIn(
            "user_confirmation_required",
            exact["properties"],
        )
        self.assertEqual(
            adjusted["properties"]["user_confirmation_required"]["enum"],
            [True],
        )
        self.assertEqual(adjusted["properties"]["response_text"]["minLength"], 1)

        fast = canonical_plan_response_schema(
            planner_tier="fast",
            expected_goal_ids=["goal-walk"],
            allowed_capability_ids=["soridormi.walk_forward"],
            requires_execution=True,
        )
        nonexact_satisfaction = next(
            item
            for item in fast["allOf"]
            if item.get("if", {}).get("properties", {}).get("plan_relation", {}).get("enum")
            == ["safe_adjustment", "alternative"]
        )
        self.assertEqual(
            nonexact_satisfaction["then"]["properties"]["goal_satisfaction"]["properties"][
                "status"
            ]["enum"],
            ["substantial"],
        )
        self.assertEqual(
            nonexact_satisfaction["then"]["properties"]["goal_outcomes"]["properties"]["goal-walk"][
                "properties"
            ]["satisfaction"]["properties"]["status"]["enum"],
            ["substantial"],
        )

    def test_planner_schema_keeps_time_conditions_and_provider_confirmation(self) -> None:
        for planner_tier in ("fast", "deep"):
            schema = canonical_plan_response_schema(
                planner_tier=planner_tier,
                expected_goal_ids=["goal-reminder"],
                allowed_capability_ids=["chromie.reminder.create"],
                confirmation_required_capability_ids=["chromie.reminder.create"],
            )
            self.assertIn("time_conditions", schema["properties"])
            self.assertIn("time_conditions", schema["required"])
            confirmation_constraint = next(
                item
                for item in schema["allOf"]
                if item.get("then", {})
                .get("properties", {})
                .get("user_confirmation_required", {})
                .get("enum")
                == [True]
            )
            self.assertEqual(
                confirmation_constraint["if"]["properties"]["steps"]["contains"]["properties"][
                    "capability_id"
                ]["enum"],
                ["chromie.reminder.create"],
            )

    def test_goal_binding_schema_uses_provider_numeric_json_type(self) -> None:
        base = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-blink"],
            allowed_capability_ids=["soridormi.blink_eyes"],
            capability_input_schemas={
                "soridormi.blink_eyes": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                        }
                    },
                    "required": ["count"],
                    "additionalProperties": False,
                }
            },
        )
        schema = canonical_goal_binding_argument_response_schema(
            base,
            authoritative_goals=[
                {
                    "goal_id": "goal-blink",
                    "object": {
                        "bindings": {
                            "count": {
                                "entity_type": "count",
                                "value": "4",
                            }
                        }
                    },
                }
            ],
        )
        branch = schema["$defs"]["PlannerModelStep"]["oneOf"][0]
        self.assertEqual(
            branch["properties"]["args"]["properties"]["count"]["const"],
            4,
        )

    def test_fast_escalation_outcome_schema_forbids_response_text(self) -> None:
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-wave"],
            allowed_capability_ids=[],
        )
        outcome = schema["properties"]["goal_outcomes"]["properties"]["goal-wave"]
        escalation = next(
            branch["then"]
            for branch in outcome["allOf"]
            if branch.get("if", {}).get("properties", {}).get("disposition", {}).get("enum")
            == ["escalate"]
        )
        self.assertEqual(
            escalation["properties"]["response_text"]["maxLength"],
            0,
        )

    def test_fast_multi_goal_schema_keeps_effectful_goals_out_of_response(self) -> None:
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-speech", "goal-blink", "goal-wave"],
            allowed_capability_ids=["soridormi.blink_eyes"],
            response_goal_ids=["goal-speech"],
            effectful_goal_ids=["goal-blink", "goal-wave"],
        )
        assignment_clause = next(
            clause
            for clause in schema["allOf"]
            if any(
                "goal_outcomes" in branch.get("properties", {})
                for branch in clause.get("anyOf", [])
            )
        )
        branches = assignment_clause["anyOf"]

        self.assertFalse(
            any(
                branch["properties"]["goal_outcomes"]["properties"]["goal-wave"]["properties"][
                    "disposition"
                ]["enum"]
                == ["respond"]
                for branch in branches
            )
        )
        terminal = next(
            branch
            for branch in branches
            if branch["properties"]["disposition"]["enum"] == ["mixed"]
        )
        self.assertEqual(terminal["properties"]["coverage"]["enum"], ["complete"])
        self.assertEqual(
            terminal["properties"]["goal_outcomes"]["properties"]["goal-blink"]["properties"][
                "coverage"
            ]["enum"],
            ["complete"],
        )
        escalation = next(
            branch
            for branch in branches
            if branch["properties"]["disposition"]["enum"] == ["escalate"]
        )
        self.assertEqual(
            escalation["properties"]["coverage"]["enum"],
            ["partial", "uncertain"],
        )

    def test_numeric_provenance_uses_typed_bindings_not_iso_date_fragments(self) -> None:
        self.assertEqual(
            explicit_numeric_goal_values(
                [
                    {
                        "goal_id": "goal-reminder",
                        "description": "Create it at 2026-09-04T18:30:00+08:00.",
                        "object": {
                            "bindings": {
                                "due_at": {
                                    "entity_type": "due_time",
                                    "value": "2026-09-04T18:30:00+08:00",
                                },
                                "count": {
                                    "entity_type": "count",
                                    "value": "2",
                                },
                            }
                        },
                    }
                ]
            ),
            {"goal-reminder": [2]},
        )

    def test_ready_at_binding_constrains_goal_time_condition(self) -> None:
        base = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
            capability_input_schemas={
                "chromie.weather.lookup": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                    "additionalProperties": False,
                }
            },
        )
        schema = canonical_goal_binding_argument_response_schema(
            base,
            authoritative_goals=[
                {
                    "goal_id": "goal-weather",
                    "object": {
                        "bindings": {
                            "ready_at": {
                                "entity_type": "due_time",
                                "value": "2026-09-04T19:00:00+08:00",
                            }
                        }
                    },
                }
            ],
        )
        condition = schema["properties"]["time_conditions"]["items"]["oneOf"][0]
        self.assertEqual(condition["properties"]["goal_id"]["const"], "goal-weather")
        self.assertEqual(condition["properties"]["due_at_ms"]["const"], 1788519600000)

    def test_execute_outcome_null_response_is_rejected_without_normalization(self) -> None:
        with self.assertRaises(ValueError):
            PlannerModelOutput.model_validate(
                {
                    "disposition": "mixed",
                    "coverage": "complete",
                    "confidence": 1.0,
                    "response_text": None,
                    "steps": [
                        {
                            "step_id": "walk",
                            "capability_id": "soridormi.walk_forward",
                            "args": {"duration_s": 15},
                            "timing": "sequential",
                            "source_goal_ids": ["goal-walk"],
                        }
                    ],
                    "goal_outcomes": {
                        "goal-walk": {
                            "disposition": "execute",
                            "coverage": "complete",
                            "response_text": None,
                            "step_ids": ["walk"],
                        },
                        "goal-song": {
                            "disposition": "respond",
                            "coverage": "complete",
                            "response_text": "我给你唱一段。",
                            "step_ids": [],
                        },
                    },
                    "goal_satisfaction": {"score": 1.0, "status": "exact"},
                }
            )

    def test_spoken_goal_schema_and_validator_forbid_executable_ownership(self) -> None:
        fast_schema = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-walk", "goal-song"],
            allowed_capability_ids=["soridormi.walk_forward"],
            response_goal_ids=["goal-song"],
        )
        deep_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk", "goal-song"],
            allowed_capability_ids=["soridormi.walk_forward"],
            response_goal_ids=["goal-song"],
        )
        self.assertEqual(
            fast_schema["properties"]["goal_outcomes"]["properties"]["goal-song"]["properties"][
                "disposition"
            ]["enum"],
            ["respond", "clarify", "escalate"],
        )
        for schema in (fast_schema, deep_schema):
            outcome = schema["properties"]["goal_outcomes"]["properties"]["goal-song"]
            self.assertEqual(outcome["properties"]["step_ids"]["maxItems"], 0)
        self.assertEqual(
            deep_schema["properties"]["goal_outcomes"]["properties"]["goal-song"]["properties"][
                "disposition"
            ]["enum"],
            ["respond"],
        )
        self.assertEqual(
            deep_schema["properties"]["goal_outcomes"]["properties"]["goal-song"]["properties"][
                "response_text"
            ]["minLength"],
            1,
        )

    def test_single_goal_fast_schema_enforces_respond_text_before_host_dto(self) -> None:
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-status"],
            allowed_capability_ids=[],
        )

        aggregate_constraint = next(
            branch
            for branch in schema["allOf"]
            if isinstance(branch.get("anyOf"), list)
            and any(
                item.get("properties", {}).get("disposition", {}).get("enum") == ["respond"]
                for item in branch["anyOf"]
            )
        )
        respond_branch = next(
            branch
            for branch in aggregate_constraint["anyOf"]
            if branch["properties"]["disposition"]["enum"] == ["respond"]
        )
        self.assertEqual(
            respond_branch["properties"]["response_text"]["minLength"],
            1,
        )
        self.assertEqual(
            respond_branch["properties"]["goal_outcomes"]["properties"]["goal-status"][
                "properties"
            ]["response_text"]["minLength"],
            1,
        )

        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-song"],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The proposed capability would complete the goal.",
        }
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "steps": [
                    {
                        "step_id": "wrong-song-step",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-song"],
                    }
                ],
                "goal_outcomes": {
                    "goal-song": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["wrong-song-step"],
                        "satisfaction": satisfaction,
                        "rationale": "Incorrectly assigns motion to speech.",
                    }
                },
                "goal_satisfaction": satisfaction,
            }
        )
        with self.assertRaisesRegex(
            ValueError, "provider-required vocal goal requires exact capability_id"
        ):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-song",
                        "metadata": {"output_mode": "singing"},
                    }
                ],
            )

        tool_schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-lookup", "goal-joke"],
            allowed_capability_ids=["chromie.weather.lookup"],
            requires_execution=True,
            response_goal_ids=["goal-joke"],
        )
        self.assertIn("mixed", tool_schema["properties"]["disposition"]["enum"])
        joke_outcome = tool_schema["properties"]["goal_outcomes"]["properties"]["goal-joke"]
        self.assertEqual(joke_outcome["properties"]["disposition"]["enum"], ["respond"])
        self.assertNotIn("oneOf", joke_outcome)
        self.assertEqual(
            set(joke_outcome["required"]),
            {
                "disposition",
                "coverage",
                "response_text",
                "unresolved",
                "step_ids",
                "satisfaction",
                "rationale",
            },
        )

    def test_deep_schema_constrains_nonparallel_timing_and_nonexecute_confirmation(
        self,
    ) -> None:
        schema = planner_schema.deep_plan_response_schema(
            ["goal-walk"],
            allowed_capability_ids=["soridormi.walk_forward"],
            capability_input_schemas={
                "soridormi.walk_forward": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number"}},
                    "required": ["duration_s"],
                    "additionalProperties": False,
                }
            },
            nonparallel_capability_ids=["soridormi.walk_forward"],
        )
        step_branch = schema["$defs"]["PlannerModelStep"]["oneOf"][0]
        self.assertEqual(
            step_branch["properties"]["timing"]["enum"],
            ["sequential"],
        )
        confirmation_constraint = next(
            item
            for item in schema["allOf"]
            if item.get("if", {}).get("properties", {}).get("disposition", {}).get("enum")
            == ["respond", "clarify", "unavailable", "refused", "escalate"]
        )
        self.assertEqual(
            confirmation_constraint["then"]["properties"]["user_confirmation_required"]["enum"],
            [False],
        )

    async def test_preassociation_uncertainty_does_not_give_ga_question_authority(self) -> None:
        ollama = _SequenceOllama(
            [
                {
                    "decision": "create_goals",
                    "new_goals": [
                        {
                            "source_responsibility_refs": ["test_responsibility"],
                            "description": "Respond naturally to F.",
                            "output_mode": "speech",
                        }
                    ],
                    "confidence": 1.0,
                    "reason_summary": "Treat the fragment as conversation.",
                }
            ]
        )
        resolution = await GoalAssociationResolver(ollama).resolve(  # type: ignore[arg-type]
            _clarify_request()
        )

        self.assertEqual(resolution.associations, [])
        self.assertFalse(hasattr(resolution, "clarification"))
        self.assertEqual(len(resolution.new_goals), 1)
        self.assertEqual(
            resolution.new_goals[0].description,
            "Respond naturally to F.",
        )
        self.assertEqual(len(ollama.schemas), 1)
        self.assertEqual(
            ollama.schemas[0]["properties"]["decision"]["enum"],
            ["create_goals"],
        )
        self.assertGreater(
            ollama.schemas[0]["properties"]["new_goals"]["maxItems"],
            0,
        )

    def test_single_goal_fast_schema_requires_model_authored_outcome(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="fast",
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
        )
        outcomes = schema["properties"]["goal_outcomes"]

        self.assertEqual(outcomes["required"], ["goal-weather"])
        self.assertEqual(outcomes["minProperties"], 1)
        self.assertEqual(outcomes["maxProperties"], 1)
        self.assertFalse(_allows_null(schema["properties"]["goal_satisfaction"]))

    def test_tool_route_planner_schema_requires_terminal_limitation_speech(self) -> None:
        fast = fast_multi_goal_response_schema(
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )
        deep = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )

        self.assertEqual(
            fast["properties"]["disposition"]["enum"],
            ["execute", "clarify", "escalate"],
        )
        self.assertEqual(fast["properties"]["response_text"]["maxLength"], 800)
        exact_response_constraint = next(
            item
            for item in fast["allOf"]
            if item.get("if", {}).get("properties", {}).get("plan_relation", {}).get("const")
            == "exact"
        )
        self.assertEqual(
            exact_response_constraint["then"]["properties"]["response_text"]["maxLength"],
            0,
        )
        fast_outcome = fast["properties"]["goal_outcomes"]["properties"]["goal-weather"]
        self.assertEqual(
            fast_outcome["properties"]["disposition"]["enum"],
            ["execute", "clarify", "escalate"],
        )
        self.assertEqual(
            fast_outcome["properties"]["response_text"]["maxLength"],
            0,
        )

        self.assertEqual(
            deep["properties"]["disposition"]["enum"],
            ["execute", "clarify", "unavailable", "refused"],
        )
        self.assertEqual(deep["properties"]["response_text"]["maxLength"], 800)
        terminal_response_branch = next(
            item
            for item in deep["allOf"]
            if any(
                branch.get("properties", {}).get("disposition", {}).get("enum")
                == ["clarify", "unavailable", "refused"]
                for branch in item.get("anyOf", [])
            )
        )
        limitation = terminal_response_branch["anyOf"][1]
        self.assertEqual(
            limitation["properties"]["response_text"]["minLength"],
            1,
        )
        deep_outcome = deep["properties"]["goal_outcomes"]["properties"]["goal-weather"]
        self.assertNotIn(
            "maxLength",
            deep_outcome["properties"]["response_text"],
        )
        outcome_terminal_branch = next(
            item
            for item in deep_outcome["allOf"]
            if any(
                branch.get("properties", {}).get("disposition", {}).get("enum")
                == ["clarify", "unavailable", "refused"]
                for branch in item.get("anyOf", [])
            )
        )
        self.assertEqual(
            outcome_terminal_branch["anyOf"][0]["properties"]["response_text"]["maxLength"],
            0,
        )
        self.assertEqual(
            outcome_terminal_branch["anyOf"][1]["properties"]["response_text"]["minLength"],
            1,
        )
        self.assertNotIn(
            ["respond"],
            [
                branch.get("properties", {}).get("disposition", {}).get("enum")
                for branch in deep_outcome.get("oneOf", [])
            ],
        )

    def test_planner_model_output_requires_explicit_timing_for_every_step(self) -> None:
        for step_count in (1, 2):
            steps = [
                {
                    "step_id": f"step-{index}",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-blink"],
                }
                for index in range(step_count)
            ]
            raw = {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "steps": steps,
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-blink"],
                },
            }
            for planner_tier in ("fast", "deep"):
                with (
                    self.subTest(planner_tier=planner_tier, step_count=step_count),
                    self.assertRaisesRegex(ValueError, "timing"),
                ):
                    planner_validation.validate_planner_model_output(
                        raw,
                        planner_tier=planner_tier,
                        expected_goal_ids_for_turn=["goal-blink"],
                    )

            for step in steps:
                step["timing"] = "sequential"
            for planner_tier in ("fast", "deep"):
                validated = planner_validation.validate_planner_model_output(
                    raw,
                    planner_tier=planner_tier,
                    expected_goal_ids_for_turn=["goal-blink"],
                )
                self.assertTrue(all(step.timing == "sequential" for step in validated.steps))

    def test_safe_read_parallel_timing_is_exactly_provenanced(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-weather",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-weather"],
            goal_summary="Check the weather.",
            steps=[
                {
                    "step_id": "lookup",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["lookup"],
                }
            ],
        )
        fingerprint = canonical_plan_fingerprint(plan)
        request = CapabilityRequest(
            request_id="weather-request",
            capability_id="chromie.weather.lookup",
            args={"location": "重庆", "date": "today"},
            timing="parallel",
            requires_confirmation=False,
            metadata={
                "source": "goal_driven_canonical_plan",
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "step_id": "lookup",
                "source_goal_ids": ["goal-weather"],
                "safety_class": "safe_read",
                "retryable_safe_read": True,
                "parallel_with_vocal": True,
                "canonical_timing": "sequential",
                "effective_timing": "parallel",
                "runtime_timing_adjustment": "safe_read_parallel",
            },
        )

        planned, _, _ = ExecutionOutcomeReconciler._planned_requests(
            plan,
            fingerprint=fingerprint,
            requests=[request],
        )
        self.assertEqual(planned["lookup"].timing, "parallel")

        forged = request.model_copy(
            deep=True,
            update={
                "metadata": {
                    **request.metadata,
                    "runtime_timing_adjustment": "none",
                }
            },
        )
        with self.assertRaisesRegex(ValueError, "timing does not match"):
            ExecutionOutcomeReconciler._planned_requests(
                plan,
                fingerprint=fingerprint,
                requests=[forged],
            )

    def test_wake_up_greeting_rejects_incomplete_clause(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "complete punctuated"):
            VoiceAssistant._validate_runtime_ready_greeting_completion("六点半啦，我困了，你吃晚")
        self.assertEqual(
            VoiceAssistant._validate_runtime_ready_greeting_completion("嗨，我醒啦！"),
            "嗨，我醒啦！",
        )

    def test_wake_up_prompt_uses_grounded_time_without_unverified_state(self) -> None:
        assistant = object.__new__(VoiceAssistant)
        assistant.runtime_ready_greeting_language = "zh-CN"
        assistant._owner_identity_json = lambda: "{}"  # type: ignore[method-assign]
        assistant._owner_mind_summary = lambda: "{}"  # type: ignore[method-assign]
        prompt = assistant._runtime_ready_greeting_prompt()

        self.assertIn("Grounded local temporal context JSON", prompt)
        self.assertIn("local_period", prompt)
        self.assertIn("Do not quote the exact clock time", prompt)
        self.assertIn("Do not invent meals, hunger, sleepiness, weather", prompt)
        self.assertIn("Do not ask a question or end mid-clause", prompt)

    async def test_vad_segment_started_during_playback_keeps_barge_in_threshold(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.target_asr_rate = 16000
        assistant.max_vad_utterance_ms = 20000
        assistant.min_audio_ms = 100
        assistant.min_rms = 120.0
        assistant.barge_in_min_rms = 350.0
        assistant.is_playing_audio = False
        assistant.playback_generation = 2
        created: list[str] = []

        def create_session(self: VoiceAssistant) -> str:
            created.append("created")
            return "unexpected"

        assistant.create_session = MethodType(create_session, assistant)
        audio = int(200).to_bytes(2, "little", signed=True) * 16000

        await input_session_runtime_for(assistant).handle_vad_audio(
            audio,
            started_during_playback=True,
            playback_generation_at_start=1,
        )

        self.assertEqual(created, [])

    def test_tts_echo_match_rejects_concatenated_robot_speech(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._tts_text_by_generation = {
            4: [
                "我会先眨两下眼睛，再往前走15秒。",
                "刚才没成功。",
            ]
        }

        likely, ratio, coverage = assistant._likely_tts_echo(
            "我会先眨两下眼睛，再往前走15秒，刚才没成功。",
            playback_generation_at_start=4,
        )

        self.assertTrue(likely)
        self.assertGreaterEqual(ratio, 0.78)
        self.assertGreaterEqual(coverage, 0.88)

    def test_tts_echo_match_uses_best_chunk_for_asr_distortion(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._tts_text_by_generation = {
            4: [
                "Once upon a time, a long,",
                "long time ago, the Moon was very lonely in the big, dark sky.",
                "It did not have any friends to play with.",
            ]
        }

        likely, ratio, _ = assistant._likely_tts_echo(
            "Once upon a time along says why.",
            playback_generation_at_start=4,
        )

        self.assertTrue(likely)
        self.assertGreaterEqual(ratio, 0.78)

    def test_tts_echo_match_keeps_real_barge_in(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant._tts_text_by_generation = {5: ["我会先眨两下眼睛，再往前走15秒。"]}

        likely, _, _ = assistant._likely_tts_echo(
            "停一下，我不是让你先眨眼。",
            playback_generation_at_start=5,
        )

        self.assertFalse(likely)

    def test_planner_prompts_preserve_requested_concurrency(self) -> None:
        fast_source = inspect.getsource(planner_prompt.fast_plan_prompt)
        deep_source = inspect.getsource(planner_prompt.deep_plan_prompt)
        for source in (fast_source, deep_source):
            self.assertIn(
                "Never silently rewrite simultaneous independent actions as before/after actions",
                source,
            )
            self.assertIn("timing=parallel", source)
            self.assertIn("Every executable step must explicitly include timing", source)
            self.assertIn("Never satisfy a prohibition", source)

    def test_deep_tool_schema_inlines_required_goal_outcome_fields(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-weather"],
            allowed_capability_ids=["chromie.weather.lookup"],
            requires_execution=True,
        )
        outcome = schema["properties"]["goal_outcomes"]["properties"]["goal-weather"]

        self.assertNotIn("$ref", outcome)
        self.assertEqual(
            set(outcome["required"]),
            {
                "disposition",
                "coverage",
                "response_text",
                "unresolved",
                "step_ids",
                "satisfaction",
                "rationale",
            },
        )
        self.assertNotIn(
            "respond",
            outcome["properties"]["disposition"]["enum"],
        )
        self.assertNotIn(
            "respond",
            schema["properties"]["disposition"]["enum"],
        )
        self.assertFalse(_allows_null(schema["properties"]["goal_satisfaction"]))


if __name__ == "__main__":
    unittest.main()
