from __future__ import annotations

from agent.app import planner_validation
from agent.app import planner_schema
from agent.app import planner_prompt as planner_prompt

import asyncio
import unittest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.planner_validation import (
    qualify_capability_catalog_for_output_modes,
    validate_planner_model_output,
)
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from tests.cognitive_work_test_support import cognitive_work_request
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


class DeepPlannerMixedAccountingNormalizationTests(unittest.TestCase):
    def test_output_mode_qualification_removes_information_tools_from_body_work(self):
        capabilities = [
            {
                "capability_id": "soridormi.walk_forward",
                "effects": ["physical_motion"],
            },
            {
                "capability_id": "chromie.clock.local",
                "route": "tool",
                "semantic_scope": {
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource_kinds": ["information"],
                },
            },
        ]
        goals = [
            {"goal_id": "walk", "metadata": {"output_mode": "body_action"}},
            {"goal_id": "sing", "metadata": {"output_mode": "singing"}},
        ]

        qualified = qualify_capability_catalog_for_output_modes(
            capabilities,
            authoritative_goals=goals,
        )

        self.assertEqual(
            [item["capability_id"] for item in qualified],
            ["soridormi.walk_forward"],
        )

    def test_preserves_outcomes_and_drops_only_unowned_placeholder_step(self):
        raw = {
            "disposition": "mixed",
            "coverage": "partial",
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "step_ids": ["walk"],
                },
                "goal-sing": {
                    "disposition": "unavailable",
                    "step_ids": [],
                },
            },
            "steps": [
                {"step_id": "walk", "capability_id": "soridormi.walk_forward"},
                {"step_id": "placeholder", "capability_id": "chromie.memory.retrieve"},
            ],
        }

        normalized, repairs = (
            DeepPlannerResolver._normalize_mixed_goal_outcome_accounting(
                raw,
                expected_goal_ids=["goal-walk", "goal-sing"],
            )
        )

        self.assertEqual(normalized["coverage"], "complete")
        self.assertEqual(
            [item["step_id"] for item in normalized["steps"]],
            ["walk"],
        )
        self.assertEqual(normalized["goal_outcomes"], raw["goal_outcomes"])
        self.assertTrue(any(item["path"] == "coverage" for item in repairs))
        self.assertTrue(
            any(item.get("step_id") == "placeholder" for item in repairs)
        )

    def test_does_not_normalize_incomplete_goal_map(self):
        raw = {
            "disposition": "mixed",
            "coverage": "partial",
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "step_ids": ["walk"],
                }
            },
            "steps": [{"step_id": "walk"}],
        }

        normalized, repairs = (
            DeepPlannerResolver._normalize_mixed_goal_outcome_accounting(
                raw,
                expected_goal_ids=["goal-walk", "goal-sing"],
            )
        )

        self.assertEqual(normalized, raw)
        self.assertEqual(repairs, [])

    def test_explicit_per_goal_outcomes_repair_redundant_aggregate_fields(self):
        raw = {
            "disposition": "execute",
            "coverage": "partial",
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "step_ids": ["walk"],
                    "satisfaction": {
                        "score": 0.95,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-walk"],
                        "unmet_goal_ids": ["goal-walk"],
                        "unmet_requirements": ["execution still pending"],
                    },
                },
                "goal-sing": {
                    "disposition": "unavailable",
                    "step_ids": [],
                    "satisfaction": {
                        "score": 0.0,
                        "status": "unsatisfied",
                        "satisfied_goal_ids": [],
                        "unmet_goal_ids": ["goal-sing"],
                        "unmet_requirements": ["sing"],
                    },
                },
            },
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk", "goal-sing"],
                },
                {
                    "step_id": "decorative",
                    "capability_id": "soridormi.look_direction",
                    "source_goal_ids": ["goal-walk", "goal-sing"],
                },
            ],
            "goal_satisfaction": {
                "score": 0.95,
                "status": "exact",
                "satisfied_goal_ids": ["goal-walk"],
                "unmet_goal_ids": ["goal-sing"],
                "unmet_requirements": ["sing"],
            },
        }

        normalized, repairs = (
            DeepPlannerResolver._normalize_mixed_goal_outcome_accounting(
                raw,
                expected_goal_ids=["goal-walk", "goal-sing"],
            )
        )

        self.assertEqual(normalized["disposition"], "mixed")
        self.assertEqual(normalized["coverage"], "complete")
        self.assertEqual(
            normalized["goal_outcomes"]["goal-walk"]["satisfaction"][
                "unmet_goal_ids"
            ],
            [],
        )
        self.assertEqual(
            normalized["goal_outcomes"]["goal-walk"]["satisfaction"][
                "unmet_requirements"
            ],
            [],
        )
        self.assertEqual(
            normalized["steps"],
            [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        self.assertEqual(
            normalized["goal_satisfaction"]["score"],
            0.475,
        )
        self.assertEqual(
            normalized["goal_satisfaction"]["status"],
            "partial",
        )
        self.assertGreaterEqual(len(repairs), 6)


class FullCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(
                capability_id="soridormi.walk_forward", agent_id="capability_agent",
                description="Walk forward", effects=["physical_motion"], available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]},
                can_run_parallel=False, parallel_metadata_declared=True,
                exclusive_group="base_motion", resource_claims=["base_motion"],
            ),
            CatalogCapability(
                capability_id="soridormi.blink_eyes", agent_id="capability_agent",
                description="Blink eyes", effects=["visual_expression"], available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]},
                can_run_parallel=True, parallel_metadata_declared=True,
                exclusive_group="eye_expression", resource_claims=["eye_expression"],
            ),
            CatalogCapability(
                capability_id="soridormi.look_at_person", agent_id="capability_agent",
                description="Look at a person", effects=["physical_motion"], available=True,
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
                description="Observe doorway", effects=["read_only"], available=True,
                interaction_executable=True, prompt_tier="rare",
                input_schema={"type":"object","properties":{}},
            ),
            CatalogCapability(
                capability_id="chromie.speak", agent_id="capability_agent",
                description="Speak text", effects=["user_interaction", "audio_output"], available=True,
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


class GranularResourceCatalog(FullCatalog):
    def __init__(self):
        super().__init__()
        self.items.extend(
            [
                CatalogCapability(
                    capability_id="soridormi.acquire_resource",
                    agent_id="capability_agent",
                    description="Acquire a physical resource.",
                    effects=["physical_motion", "object_manipulation"],
                    available=True,
                    interaction_executable=True,
                    prompt_tier="common",
                    input_schema={"type": "object", "properties": {}},
                    hints={
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                        },
                        "resource_contract": {
                            "plan_requires": [],
                            "plan_provides": ["resource_acquired"],
                            "completion_requires": ["resource_acquired"],
                        },
                    },
                ),
                CatalogCapability(
                    capability_id="soridormi.deliver_resource",
                    agent_id="capability_agent",
                    description="Deliver an acquired physical resource.",
                    effects=["physical_motion", "object_manipulation"],
                    available=True,
                    interaction_executable=True,
                    prompt_tier="common",
                    input_schema={"type": "object", "properties": {}},
                    hints={
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                            "delivery_modes": ["physical_handover"],
                        },
                        "resource_contract": {
                            "plan_requires": ["resource_acquired"],
                            "plan_provides": ["resource_delivered"],
                            "completion_requires": ["resource_delivered"],
                        },
                    },
                ),
            ]
        )


def request(text="往前走15秒，然后眨眼。", *, goal_ids=None) -> CognitiveWorkRequest:
    goal_ids = list(goal_ids or ["goal-action"])
    return cognitive_work_request(
        sid="sid-pr4", text=text, language="zh-CN",
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
    def test_canonical_body_goal_is_planned_from_goal_state(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "goal_summary": "Blink twice.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-blink"],
                    "reason_summary": "Blink twice as requested.",
                }
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["blink"],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-blink"],
                        "unmet_goal_ids": [],
                        "unmet_requirements": [],
                        "rationale": "Exact body action coverage.",
                    },
                    "rationale": "Exact body action coverage.",
                }
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink"],
                "unmet_goal_ids": [],
                "unmet_requirements": [],
                "rationale": "Exact body action coverage.",
            },
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        run_request = request("Blink twice.", goal_ids=["goal-blink"])
        goal = run_request.context["goal_association_resolution"]["new_goals"][0]
        goal["metadata"] = {
            "responsibility_kind": "executable_action",
            "execution_lane": "activity",
            "output_mode": "body_action",
            "provider_required": True,
        }
        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": "The exact blink capability completely covers the canonical body Goal.",
        }
        ollama = SequencedOllama([raw, coverage_review])

        plan = asyncio.run(DeepPlannerResolver(ollama, FullCatalog()).resolve(run_request))

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual([step.capability_id for step in plan.steps], ["soridormi.blink_eyes"])
        schema = ollama.prompts[0][1]["response_format"]
        self.assertNotEqual(schema["properties"]["steps"].get("maxItems"), 0)
        self.assertNotIn("authoritative source route", ollama.prompts[0][0].casefold())

    def test_effectful_zero_step_false_satisfaction_fails_closed_without_same_tier_repair(self):
        invalid = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Walk forward for fifteen seconds.",
            "response_text": "I did it.",
            "steps": [],
            "goal_outcomes": {},
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-walk"],
                "unmet_goal_ids": [],
                "unmet_requirements": [],
                "rationale": "Incorrectly declares the physical Goal complete.",
            },
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        ollama = SequencedOllama([invalid, invalid])
        run_request = request(
            "Walk forward for fifteen seconds.",
            goal_ids=["goal-walk"],
        )
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-walk",
                    "description": "Walk forward for fifteen seconds.",
                    "source_text": "Walk forward for fifteen seconds.",
                    "metadata": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "physical_action",
                        "provider_required": True,
                    },
                }
            ],
        }

        plan = asyncio.run(
            DeepPlannerResolver(
                ollama,
                FullCatalog(),
                max_contract_repairs=1,
            ).resolve(run_request.model_copy(update={"context": context}))
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertFalse(plan.metadata["contract_repair_attempted"])
        self.assertEqual(plan.metadata["reason"], "deep_planner_semantic_validation_failed")
        self.assertIn(
            "unresolved effectful goal requires an executable step",
            plan.metadata["error"],
        )

    def test_missing_resource_provider_clarifies_without_hard_model_failure(self):
        goal_id = "goal-resource"
        reason = "Fetch and hand over the red mug."
        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": reason,
        }
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": reason,
            "response_text": "",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "timing": "sequential",
                    "source_goal_ids": [goal_id],
                    "reason_summary": reason,
                }
            ],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {
                goal_id: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["walk"],
                    "satisfaction": satisfaction,
                    "rationale": reason,
                }
            },
            "goal_satisfaction": satisfaction,
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        run_request = request(reason, goal_ids=[goal_id])
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": goal_id,
                    "description": reason,
                    "source_text": reason,
                    "resource_responsibility": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource": {
                            "kind": "physical_object",
                            "description": "red mug",
                        },
                        "source": {"status": "unknown"},
                        "recipient": {"description": "requester"},
                        "delivery_mode": "physical_handover",
                    },
                    "metadata": {"responsibility_kind": "executable_action"},
                }
            ],
        }

        plan = asyncio.run(
            DeepPlannerResolver(SequencedOllama([raw]), FullCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "unavailable")
        self.assertEqual(plan.steps, [])
        self.assertEqual(
            plan.metadata["reason"],
            "resource_responsibility_capability_unavailable",
        )
        self.assertTrue(plan.metadata["resource_contract_unavailable"])
        self.assertNotIn("failure_class", plan.metadata)

    def test_deep_planner_composes_advertised_granular_resource_capabilities(self):
        goal_id = "goal-resource"
        reason = "Fetch and hand over the red mug."
        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The advertised resource chain covers acquisition and delivery.",
        }
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": reason,
            "response_text": "",
            "steps": [
                {
                    "step_id": "acquire",
                    "capability_id": "soridormi.acquire_resource",
                    "args": {},
                    "timing": "sequential",
                    "source_goal_ids": [goal_id],
                    "reason_summary": "Acquire the requested resource.",
                },
                {
                    "step_id": "deliver",
                    "capability_id": "soridormi.deliver_resource",
                    "args": {},
                    "timing": "sequential",
                    "source_goal_ids": [goal_id],
                    "reason_summary": "Deliver the acquired resource.",
                },
            ],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {
                goal_id: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["acquire", "deliver"],
                    "satisfaction": satisfaction,
                    "rationale": "Both advertised capability contracts are required.",
                }
            },
            "goal_satisfaction": satisfaction,
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        run_request = request(reason, goal_ids=[goal_id])
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": goal_id,
                    "description": reason,
                    "source_text": reason,
                    "resource_responsibility": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource": {
                            "kind": "physical_object",
                            "description": "red mug",
                        },
                        "source": {"status": "unknown"},
                        "recipient": {"description": "requester"},
                        "delivery_mode": "physical_handover",
                    },
                    "metadata": {"responsibility_kind": "executable_action"},
                }
            ],
        }

        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": (
                "The advertised acquire and delivery steps jointly cover the "
                "resource responsibility."
            ),
        }
        plan = asyncio.run(
            DeepPlannerResolver(
                SequencedOllama([raw, coverage_review]),
                GranularResourceCatalog(),
            ).resolve(run_request.model_copy(update={"context": context}))
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(
            [step.capability_id for step in plan.steps],
            ["soridormi.acquire_resource", "soridormi.deliver_resource"],
        )
        self.assertNotEqual(plan.metadata.get("execution_allowed"), False)

    def test_prior_validator_capability_contract_precedes_catalog_truncation(self):
        run_request = request("Walk briefly.")
        context = dict(run_request.context)
        context["runtime_validator_feedback"] = [
            {
                "type": "invalid_args",
                "capability_id": "soridormi.walk_forward",
                "errors": ["args has unknown fields: ['speed']"],
            }
        ]
        capabilities = [
            {
                "capability_id": f"rare.capability_{index}",
                "description": "x" * 500,
                "input_schema": {"type": "object", "properties": {}},
            }
            for index in range(40)
        ]
        capabilities.append(
            {
                "capability_id": "soridormi.walk_forward",
                "description": "Walk using the exact provider contract.",
                "input_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number"}},
                    "required": ["duration_s"],
                    "additionalProperties": False,
                },
            }
        )

        prompt = planner_prompt.deep_plan_prompt(
            run_request.model_copy(update={"context": context}),
            capabilities,
            feedback=[],
            response_schema={},
            expected_goal_ids=["goal-action"],
        )

        catalog_section = prompt.split(
            "Executable capability catalog JSON:\n",
            1,
        )[1].split("Verified tool-memory index JSON", 1)[0]
        self.assertIn("soridormi.walk_forward", catalog_section)
        self.assertIn("duration_s", catalog_section)
        self.assertIn("additionalProperties", catalog_section)
        self.assertLess(
            catalog_section.index("soridormi.walk_forward"),
            catalog_section.index("rare.capability_0"),
        )

    def test_compact_catalog_keeps_terminal_numeric_capability_visible(self):
        capabilities = [
            {
                "capability_id": f"soridormi.action_{index:02d}",
                "description": "Bounded robot action.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "duration_s": {
                            "type": "number",
                            "minimum": 0.5,
                            "maximum": 20.0,
                        }
                    },
                    "additionalProperties": False,
                },
                "route": "robot_action",
                "requires_confirmation": False,
                "effects": ["physical_motion"],
                "safety_class": "guarded_motion",
                "can_run_parallel": False,
                "parallel_metadata_declared": True,
                "exclusive_group": "base_motion",
                "resource_claims": ["base_motion"],
                "execution_constraints": {
                    "control_coupling": "primary_body_controller",
                    "parallel_safe_with": [],
                    "safety_preemption": "safe_hold",
                },
                "hints": {
                    "when_to_use": "Bounded robot action.",
                    "examples": "x" * 2000,
                    "concurrency": {"duplicated": "x" * 2000},
                },
            }
            for index in range(17)
        ]
        capabilities.append(
            {
                **capabilities[-1],
                "capability_id": "soridormi.walk_velocity",
                "description": "Track a bounded body velocity command.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {
                            "type": "number",
                            "minimum": -0.03,
                            "maximum": 0.25,
                        }
                    },
                    "additionalProperties": False,
                },
                "hints": {
                    "when_to_use": "Track a bounded body velocity command.",
                    "when_not_to_use": "Do not use for static observation.",
                    "concurrency": {"duplicated": "x" * 5000},
                },
            }
        )

        prompt = planner_prompt.deep_plan_prompt(
            request("Walk at an explicit numeric velocity."),
            capabilities,
            feedback=[],
            response_schema={},
            expected_goal_ids=["goal-action"],
        )
        catalog_section = prompt.split(
            "Executable capability catalog JSON:\n",
            1,
        )[1].split("Verified tool-memory index JSON", 1)[0]

        self.assertLessEqual(len(catalog_section.strip()), 12003)
        self.assertIn("soridormi.walk_velocity", catalog_section)
        self.assertIn("vx_mps", catalog_section)
        self.assertIn('"maximum":0.25', catalog_section)
        self.assertIn("Do not use for static observation.", catalog_section)
        self.assertNotIn("duplicated", catalog_section)

    def test_clear_goal_without_matching_capability_is_unavailable_not_clarify(self):
        planner_request = request(
            "Find a restaurant that is open now near People's Square."
        )
        planner_request.context["interaction_context"] = {
            "events": [{"event_id": "ledger-deep-marker"}]
        }
        prompt = planner_prompt.deep_plan_prompt(
            planner_request,
            [],
            feedback=[],
            response_schema={},
            expected_goal_ids=["goal-action"],
        )

        self.assertIn(
            "Clarification is only for ambiguous user meaning or missing material information that the user can supply",
            prompt,
        )
        self.assertIn(
            "no exact available capability covers the required outcome, return unavailable",
            prompt,
        )
        self.assertIn("Required response language: zh-CN", prompt)
        self.assertIn(
            "Do not switch languages merely because internal Goals",
            prompt,
        )
        self.assertIn("ledger-deep-marker", prompt)

    def test_resolution_mismatch_feedback_carries_selected_capability_schema(self):
        feedback = DeepPlannerResolver._validation_error_items(
            ValueError(
                "parameter resolution references an argument absent from its step"
            ),
            raw={
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"duration_s": 10.0},
                    }
                ],
                "parameter_resolutions": [
                    {
                        "step_id": "walk",
                        "parameter": "vx_mps",
                        "strategy": "safe_default",
                        "value": 0.2,
                        "source_goal_ids": ["goal-action"],
                    }
                ],
            },
            expected_goal_ids_for_turn=["goal-action"],
            capability_payload=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "vx_mps": {
                                "type": "number",
                                "minimum": -0.03,
                                "maximum": 0.25,
                            }
                        },
                        "additionalProperties": False,
                    },
                }
            ],
        )

        mismatch = next(
            item
            for item in feedback
            if item["type"] == "parameter_resolution_argument_mismatch"
        )
        self.assertEqual(mismatch["capability_id"], "soridormi.walk_velocity")
        self.assertEqual(mismatch["parameter"], "vx_mps")
        self.assertEqual(mismatch["resolution_value"], 0.2)
        self.assertEqual(
            mismatch["capability_input_schema"]["properties"]["vx_mps"][
                "maximum"
            ],
            0.25,
        )
        self.assertIn("strategy user_supplied", mismatch["corrective_contract"])

        schema = planner_schema.deep_plan_response_schema(
            ["goal-action"],
            allowed_capability_ids=["soridormi.walk_velocity"],
            capability_input_schemas={
                "soridormi.walk_velocity": mismatch["capability_input_schema"]
            },
        )
        tightened = planner_schema.deep_contract_revision_response_schema(
            schema,
            feedback=feedback,
        )
        self.assertIn(
            "vx_mps",
            tightened["$defs"]["PlannerModelStep"]["oneOf"][0][
                "properties"
            ]["args"]["required"],
        )

    def test_numeric_repair_feedback_rejects_default_strategy_for_goal_value(self):
        feedback = DeepPlannerResolver._validation_error_items(
            ValueError(
                "explicit numeric goal value has no matching user_supplied "
                "parameter resolution"
            ),
            raw={
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2},
                    }
                ],
                "parameter_resolutions": [
                    {
                        "step_id": "walk",
                        "parameter": "vx_mps",
                        "strategy": "safe_default",
                        "value": 0.2,
                        "source_goal_ids": ["goal-action"],
                    }
                ],
            },
            expected_goal_ids_for_turn=["goal-action"],
        )

        mismatch = next(
            item
            for item in feedback
            if item["type"] == "explicit_numeric_resolution_strategy_mismatch"
        )
        self.assertEqual(mismatch["actual_strategy"], "safe_default")
        self.assertIn("strategy user_supplied", mismatch["corrective_contract"])

    def test_numeric_repair_feedback_forbids_borrowing_sibling_goal_value(self):
        feedback = DeepPlannerResolver._validation_error_items(
            ValueError(
                "numeric user_supplied parameter resolution is not present in "
                "its authoritative source Goal"
            ),
            raw={
                "steps": [
                    {
                        "step_id": "turn",
                        "capability_id": "soridormi.turn_in_place",
                        "args": {"duration_s": 2.0},
                    }
                ],
                "parameter_resolutions": [
                    {
                        "step_id": "turn",
                        "parameter": "duration_s",
                        "strategy": "user_supplied",
                        "value": 2.0,
                        "source_goal_ids": ["goal-turn"],
                    }
                ],
            },
            expected_goal_ids_for_turn=["goal-turn", "goal-look"],
            capability_payload=[
                {
                    "capability_id": "soridormi.turn_in_place",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "duration_s": {
                                "type": "number",
                                "default": 2.0,
                            }
                        },
                    },
                }
            ],
        )

        mismatch = next(
            item
            for item in feedback
            if item["type"] == "unsupported_user_supplied_provenance"
        )
        self.assertEqual(mismatch["source_goal_ids"], ["goal-turn"])
        self.assertEqual(mismatch["catalog_parameter_schema"]["default"], 2.0)
        self.assertIn("Never borrow a sibling Goal", mismatch["corrective_contract"])
        self.assertIn("strategy schema_default", mismatch["corrective_contract"])

    def test_deep_decoder_requires_explicit_step_timing(self):
        schema = planner_schema.deep_plan_response_schema(
            ["goal-walk", "goal-blink"],
            allowed_capability_ids=[
                "soridormi.walk_forward",
                "soridormi.blink_eyes",
            ],
        )

        required = schema["$defs"]["PlannerModelStep"]["required"]
        self.assertIn("timing", required)
        self.assertIn("reason_summary", required)
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 8)
        self.assertIn(
            "never duplicate a step",
            schema["properties"]["steps"]["description"],
        )

    def test_deep_decoder_enforces_exact_capability_argument_bounds(self):
        schema = planner_schema.deep_plan_response_schema(
            ["goal-turn"],
            allowed_capability_ids=["soridormi.turn_in_place"],
            capability_input_schemas={
                "soridormi.turn_in_place": {
                    "type": "object",
                    "properties": {
                        "yaw_radps": {
                            "type": "number",
                            "minimum": -0.2,
                            "maximum": 0.2,
                        }
                    },
                    "additionalProperties": False,
                }
            },
        )

        branch = schema["$defs"]["PlannerModelStep"]["oneOf"][0]
        self.assertIn("timing", branch["required"])
        self.assertIn("source_goal_ids", branch["required"])
        self.assertEqual(
            branch["properties"]["capability_id"]["enum"],
            ["soridormi.turn_in_place"],
        )
        self.assertEqual(
            branch["properties"]["args"]["properties"]["yaw_radps"][
                "maximum"
            ],
            0.2,
        )
        self.assertFalse(branch["properties"]["args"]["additionalProperties"])

    def test_fast_parallel_safety_feedback_specializes_first_deep_attempt(self):
        adjusted = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Walk safely after user approval.",
            "response_text": "I cannot verify overlap safety; may I walk first?",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
            "plan_relation": "safe_adjustment",
            "user_confirmation_required": True,
        }
        run_request = request("Walk while blinking.")
        context = dict(run_request.context)
        context["fast_plan_resolution"] = {
            "disposition": "escalate",
            "coverage": "uncertain",
            "steps": [],
            "metadata": {
                "executable_step_count": 2,
                "parallel_contract_errors": [
                    {
                        "type": "parallel_capability_not_declared_safe",
                        "capability_id": "soridormi.walk_forward",
                    }
                ]
            },
        }
        ollama = SequencedOllama([adjusted])

        result = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(result.metadata["plan_relation"], "safe_adjustment")
        self.assertTrue(result.metadata["user_confirmation_required"])
        schema = ollama.prompts[0][1]["response_format"]
        adjustment = schema["allOf"][-1]["anyOf"][0]
        self.assertEqual(
            adjustment["properties"]["plan_relation"]["enum"],
            ["safe_adjustment", "alternative"],
        )
        self.assertIn(
            "parallel_capability_not_declared_safe",
            ollama.prompts[0][0],
        )

    def test_single_parallel_labeled_step_does_not_force_adjustment(self):
        feedback = DeepPlannerResolver._initial_safety_feedback(
            {
                "fast_plan_resolution": {
                    "metadata": {
                        "executable_step_count": 1,
                        "parallel_contract_errors": [
                            {
                                "type": "parallel_capability_not_declared_safe",
                                "capability_id": "chromie.weather.lookup",
                            }
                        ],
                    }
                }
            }
        )

        self.assertEqual(feedback, [])

        singleton_feedback = [
            {
                "type": "parallel_capability_not_declared_safe",
                "capability_id": "soridormi.walk_forward",
                "parallel_step_count": 1,
            }
        ]
        self.assertFalse(
            planner_validation.requires_safety_revision(singleton_feedback)
        )
        self.assertFalse(
            planner_validation.requires_sequential_safety_revision(
                singleton_feedback
            )
        )

    def test_single_parallel_label_is_canonicalized_without_model_repair(self):
        parallel = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Walk forward.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = {
            **parallel,
            "steps": [{**parallel["steps"][0], "timing": "sequential"}],
        }
        ollama = SequencedOllama([parallel, repaired])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                request("Walk forward.")
            )
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].timing, "sequential")
        self.assertEqual(plan.metadata["plan_relation"], "exact")
        self.assertFalse(plan.metadata["user_confirmation_required"])
        self.assertFalse(plan.metadata["contract_repair_attempted"])

    def test_mixed_plan_does_not_require_duplicate_per_goal_satisfaction(self):
        goal_ids = ["goal-blink", "goal-song"]
        raw = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step-blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-blink"],
                },
                "goal-song": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "啦啦啦。",
                    "step_ids": [],
                },
            },
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": goal_ids,
            },
        }

        plan = asyncio.run(
            DeepPlannerResolver(SequencedOllama([raw]), FullCatalog()).resolve(
                request("Blink and sing.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(plan.metadata["attempt_count"], 1)
        self.assertTrue(
            all(outcome.satisfaction is None for outcome in plan.goal_outcomes)
        )

    def test_coverage_review_receives_safe_adjustment_confirmation_contract(self):
        from agent.app.planner_audit import review_coordinated_action_plan_coverage

        goal_ids = ["goal-walk", "goal-blink", "goal-song"]
        plan = CanonicalPlan(
            plan_id="safe-adjustment",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=1.0,
            goal_ids=goal_ids,
            response_text="I can do those actions one after the other. Is that okay?",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15},
                    "timing": "sequential",
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
                    "goal_id": "goal-blink",
                    "disposition": "unavailable",
                    "coverage": "uncertain",
                },
                {
                    "goal_id": "goal-song",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "La la la.",
                },
            ],
            goal_satisfaction={
                "score": 0.75,
                "status": "substantial",
                "satisfied_goal_ids": ["goal-walk", "goal-song"],
                "unmet_goal_ids": ["goal-blink"],
            },
            metadata={
                "plan_relation": "safe_adjustment",
                "user_confirmation_required": True,
            },
        )
        ollama = SequencedOllama(
            [
                {
                    "decision": "accept",
                    "confidence": 1.0,
                    "uncovered_requirements": [],
                    "reason": "The adjustment is explicit and confirmation-bound.",
                }
            ]
        )

        review = asyncio.run(
            review_coordinated_action_plan_coverage(
                ollama,
                request_text="Walk and blink together, and sing.",
                language="en-US",
                authoritative_goals=[{"goal_id": item} for item in goal_ids],
                plan=plan,
                capabilities=[],
                num_ctx=4096,
            )
        )

        self.assertEqual(review.decision, "accept")
        prompt = ollama.prompts[0][0]
        self.assertIn('"plan_relation":"safe_adjustment"', prompt)
        self.assertIn('"user_confirmation_required":true', prompt)
        self.assertIn("ordinary world knowledge", prompt)
        self.assertIn("supplied Capability contracts", prompt)
        self.assertIn("Do not broaden a Capability", prompt)
        self.assertIn("confirmation-bound plan relation", prompt)
        self.assertNotIn("walking is not running", prompt)
        self.assertIn(
            "coverage=complete on a mixed Plan",
            prompt,
        )
        self.assertIn(
            "source_text repeats the whole multi-effect turn",
            prompt,
        )
        review_schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(
            review_schema["properties"]["uncovered_requirements"]["items"][
                "maxLength"
            ],
            320,
        )
        self.assertEqual(review_schema["properties"]["reason"]["maxLength"], 600)

    def test_semantic_coverage_rejection_is_terminal_without_deep_replan(self):
        goal_ids = ["goal-walk", "goal-sing"]
        run_request = request(
            "Walk while singing.",
            goal_ids=goal_ids,
        )
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-walk",
                    "description": "Walk forward.",
                    "source_text": "Walk while singing.",
                    "metadata": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "body_action",
                        "provider_required": True,
                    },
                },
                {
                    "goal_id": "goal-sing",
                    "description": "Sing while walking.",
                    "source_text": "Walk while singing.",
                    "metadata": {
                        "responsibility_kind": "vocal_output",
                        "execution_lane": "vocal",
                        "output_mode": "singing",
                        "provider_required": True,
                    },
                },
            ],
        }
        run_request = run_request.model_copy(update={"context": context})

        def mixed_plan():
            return {
                "disposition": "mixed",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Walk while singing.",
                "response_text": "I can walk, but I can't sing right now.",
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-walk"],
                        "reason_summary": "Walk for the requested duration.",
                    }
                ],
                "escalation_reason": "",
                "unresolved": ["singing provider unavailable"],
                "parameter_resolutions": [],
                "goal_outcomes": {
                    "goal-walk": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["walk"],
                        "satisfaction": {
                            "score": 1.0,
                            "status": "exact",
                            "satisfied_goal_ids": ["goal-walk"],
                            "unmet_goal_ids": [],
                            "unmet_requirements": [],
                            "rationale": "The walking step covers this goal.",
                        },
                        "rationale": "The walking step owns this goal.",
                    },
                    "goal-sing": {
                        "disposition": "unavailable",
                        "coverage": "partial",
                        "response_text": "",
                        "unresolved": ["singing provider unavailable"],
                        "step_ids": [],
                        "satisfaction": {
                            "score": 0.0,
                            "status": "unsatisfied",
                            "satisfied_goal_ids": [],
                            "unmet_goal_ids": ["goal-sing"],
                            "unmet_requirements": ["singing provider unavailable"],
                            "rationale": "No exact singing provider is registered.",
                        },
                        "rationale": "No exact singing provider is registered.",
                    },
                },
                "goal_satisfaction": {
                    "score": 0.5,
                    "status": "partial",
                    "satisfied_goal_ids": ["goal-walk"],
                    "unmet_goal_ids": ["goal-sing"],
                    "unmet_requirements": ["singing provider unavailable"],
                    "rationale": "Walking is covered but singing is unavailable.",
                },
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }

        ollama = SequencedOllama(
            [
                mixed_plan(),
                {
                    "decision": "reject",
                    "confidence": 1.0,
                    "uncovered_requirements": [
                        "The selected movement does not fully implement the body mode."
                    ],
                    "reason": "The body action needs semantic regeneration.",
                },
                mixed_plan(),
                {
                    "decision": "accept",
                    "confidence": 1.0,
                    "uncovered_requirements": [],
                    "reason": "The unavailable Goal is explicit and remains unmet.",
                },
            ]
        )

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                run_request
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["reason"], "coordinated_action_coverage_incomplete")
        self.assertFalse(plan.metadata["execution_allowed"])
        self.assertIn("The selected movement does not fully implement the body mode.", plan.unresolved)

    def test_full_catalog_exact_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.91,"goal_ids":["goal-action"],"goal_summary":"walk then blink","steps":[
            {"step_id":"walk","capability_id":"soridormi.walk_forward","args":{"duration_s":15},"timing":"sequential","source_goal_ids":["goal-action"]},
            {"step_id":"blink","capability_id":"soridormi.blink_eyes","args":{"count":4},"timing":"sequential","source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        catalog = FullCatalog()
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([raw]), catalog).resolve(request()))
        self.assertEqual(plan.planner_tier, "deep")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(catalog.scopes, ["all"])
        self.assertEqual(plan.metadata["attempt_count"], 1)

    def test_coordinated_action_review_rejection_is_terminal(self):
        partial = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_ids": ["goal-action"],
            "goal_summary": "Walk while blinking and singing.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        rejected = {
            "decision": "reject",
            "confidence": 1.0,
            "uncovered_requirements": ["blinking", "singing"],
            "reason": "The proposed Plan contains only walking.",
        }
        adjusted_partial = {
            **partial,
            "response_text": "I cannot verify parallel safety; may I walk first?",
            "plan_relation": "safe_adjustment",
            "user_confirmation_required": True,
        }
        run_request = request("Walk while blinking and singing.")
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-action",
                    "description": "Walk while blinking and singing.",
                    "object": {
                        "bindings": {
                            "actions": {
                                "name": "actions",
                                "entity_type": "action_list",
                                "value": "walking, blinking, singing",
                            }
                        }
                    },
                }
            ],
        }
        ollama = SequencedOllama(
            [partial, rejected, adjusted_partial, rejected]
        )

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertIn("blinking", plan.unresolved)
        self.assertIn("singing", plan.unresolved)
        self.assertFalse(plan.metadata["execution_allowed"])
        self.assertEqual(plan.metadata["reason"], "coordinated_action_coverage_incomplete")
        self.assertIn(
            "Optional coordinated expression belongs to the separate Social Attention owner",
            ollama.prompts[0][0],
        )
        self.assertIn("separate Social Attention owner", ollama.prompts[1][0])

    def test_invalid_first_plan_is_revised_once_in_same_tier(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"goal_ids":["goal-action"],"steps":[
            {"step_id":"blink","capability_id":"soridormi.blink_eyes","args":{"count":99},"source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        revised = {"disposition":"execute","coverage":"complete","confidence":0.93,"goal_ids":["goal-action"],"steps":[
            {"step_id":"blink","capability_id":"soridormi.blink_eyes","args":{"count":4},"source_goal_ids":["goal-action"]}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        ollama = SequencedOllama([invalid, revised])
        plan = asyncio.run(DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(request("眨眼。")))
        self.assertEqual(plan.steps[0].args["count"], 4)
        self.assertEqual(plan.metadata["attempt_count"], 2)
        self.assertIn("invalid_args", ollama.prompts[1][0])
        self.assertNotIn("Fast Planner decides again", ollama.prompts[1][0])

    def test_explicit_numeric_goal_missing_provenance_is_normalized_without_replan(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        run_request = request("Walk for 2 seconds.")
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk for 2 seconds."
        ollama = SequencedOllama([invalid])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(run_request)
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(len(plan.steps), 1)
        self.assertFalse(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(plan.steps[0].args, {"duration_s": 2.0})
        normalization = plan.metadata["numeric_provenance_normalization"]
        self.assertTrue(normalization["semantic_plan_unchanged"])
        self.assertEqual(normalization["repairs"][0]["step_id"], "walk")

    def test_numeric_provenance_repair_cannot_rewrite_plan_semantics(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        run_request = request("Walk for 2 seconds.")
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk for 2 seconds."
        ollama = SequencedOllama([invalid])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog()).resolve(run_request)
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].args, {"duration_s": 2.0})

    def test_unsafe_parallel_plan_fails_closed_without_deep_replan(self):
        parallel = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "goal_ids": ["goal-action"],
            "goal_summary": "Walk while blinking.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-action"],
                },
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-action"],
                },
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        revised = {
            **parallel,
            "steps": [
                {**parallel["steps"][0], "timing": "sequential"},
                {**parallel["steps"][1], "timing": "sequential"},
            ],
            "plan_relation": "alternative",
            "user_confirmation_required": True,
            "response_text": "I can do those safely one after the other.",
        }
        ollama = SequencedOllama([parallel, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                request("Walk while blinking.")
            )
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["reason"], "deep_planner_semantic_validation_rejected")
        self.assertIn(
            "parallel_capability_not_declared_safe",
            [item["type"] for item in plan.metadata["validation_feedback"]],
        )

    def test_contract_repair_reports_hidden_multi_goal_defects_together(self):
        goal_ids = ["goal-walk", "goal-blink"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
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
        ollama = SequencedOllama([invalid])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                request("Walk for one second, then blink twice.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(
            [item.step_ids for item in plan.goal_outcomes],
            [["walk"], ["blink"]],
        )
        self.assertEqual(len(ollama.prompts), 1)
        self.assertFalse(plan.metadata["contract_repair_attempted"])

    def test_contract_repair_exposes_missing_mixed_response_text(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
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
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                request("Blink twice and tell me a short joke.", goal_ids=goal_ids)
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(plan.goal_outcomes[1].disposition, "respond")
        repair_prompt = ollama.prompts[1][0]
        self.assertIn("respond goal outcome requires complete coverage and response_text", repair_prompt)
        self.assertIn("execute goal outcome requires complete coverage and step_ids", repair_prompt)
        self.assertIn("actual answer text now", repair_prompt)

    def test_vocal_compound_repair_preserves_body_execution_and_unavailability(self):
        goal_ids = ["goal-walk", "goal-sing", "goal-blink"]
        run_request = request(
            "你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。",
            goal_ids=goal_ids,
        )
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-walk",
                    "description": "Walk forward for 15 seconds.",
                    "metadata": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "body_action",
                        "provider_required": True,
                    },
                },
                {
                    "goal_id": "goal-sing",
                    "description": "Sing while walking.",
                    "metadata": {
                        "responsibility_kind": "vocal_output",
                        "execution_lane": "vocal",
                        "output_mode": "singing",
                        "provider_required": True,
                    },
                },
                {
                    "goal_id": "goal-blink",
                    "description": "Blink while walking.",
                    "metadata": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "body_action",
                        "provider_required": True,
                    },
                },
            ],
        }
        run_request = run_request.model_copy(update={"context": context})
        steps = [
            {
                "step_id": "walk",
                "capability_id": "soridormi.walk_forward",
                "args": {"duration_s": 15.0},
                "timing": "parallel",
                "source_goal_ids": ["goal-walk"],
                "reason_summary": "Walk for the requested duration.",
            },
            {
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "timing": "parallel",
                "source_goal_ids": ["goal-blink"],
                "reason_summary": "Blink during the walk.",
            },
        ]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_summary": "Walk, sing, and blink together.",
            "response_text": "",
            "steps": steps,
            "escalation_reason": "",
            "unresolved": ["singing provider unavailable"],
            "parameter_resolutions": [],
            "goal_outcomes": {
                "goal-walk": {
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["walk"],
                    "satisfaction": None,
                    "rationale": "The walking step owns this goal.",
                },
                "goal-sing": {
                    "coverage": "partial",
                    "response_text": "",
                    "unresolved": ["singing provider unavailable"],
                    "step_ids": [],
                    "satisfaction": None,
                    "rationale": "No exact singing provider is registered.",
                },
                "goal-blink": {
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["blink"],
                    "satisfaction": None,
                    "rationale": "The blinking step owns this goal.",
                },
            },
            "goal_satisfaction": {
                "score": 0.95,
                "status": "exact",
                "satisfied_goal_ids": ["goal-walk", "goal-blink"],
                "unmet_goal_ids": ["goal-sing"],
                "unmet_requirements": ["singing provider unavailable"],
                "rationale": "Body work is covered but singing is unavailable.",
            },
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        exact = lambda goal_id: {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The owned step prospectively satisfies this goal.",
        }
        repaired = {
            **invalid,
            "confidence": 1.0,
            "response_text": "I can walk and blink, but I can't sing right now.",
            "parameter_resolutions": [
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 15.0,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied from the authoritative walking Goal.",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["walk"],
                    "satisfaction": exact("goal-walk"),
                    "rationale": "The walking step owns this goal.",
                },
                "goal-sing": {
                    "disposition": "unavailable",
                    "coverage": "partial",
                    "response_text": "",
                    "unresolved": ["singing provider unavailable"],
                    "step_ids": [],
                    "satisfaction": {
                        "score": 0.0,
                        "status": "unsatisfied",
                        "satisfied_goal_ids": [],
                        "unmet_goal_ids": ["goal-sing"],
                        "unmet_requirements": ["singing provider unavailable"],
                        "rationale": "No exact singing provider is registered.",
                    },
                    "rationale": "No exact singing provider is registered.",
                },
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["blink"],
                    "satisfaction": exact("goal-blink"),
                    "rationale": "The blinking step owns this goal.",
                },
            },
            "goal_satisfaction": {
                "score": 0.67,
                "status": "partial",
                "satisfied_goal_ids": ["goal-walk", "goal-blink"],
                "unmet_goal_ids": ["goal-sing"],
                "unmet_requirements": ["singing provider unavailable"],
                "rationale": "Body work is covered but singing is unavailable.",
            },
        }
        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": "Walking and blinking each have an exact owned step.",
        }
        catalog = FullCatalog()
        catalog.items[0] = catalog.items[0].model_copy(
            update={"can_run_parallel": True}
        )
        ollama = SequencedOllama([invalid, repaired, coverage_review])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, catalog, max_contract_repairs=1).resolve(
                run_request
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(
            [outcome.disposition for outcome in plan.goal_outcomes],
            ["execute", "unavailable", "execute"],
        )
        self.assertEqual(
            [step.capability_id for step in plan.steps],
            ["soridormi.walk_forward", "soridormi.blink_eyes"],
        )
        self.assertEqual(plan.goal_satisfaction.status, "partial")
        self.assertEqual(plan.goal_satisfaction.unmet_goal_ids, ["goal-sing"])
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn(
            "An unavailable provider-backed vocal mode remains wholly unavailable",
            ollama.prompts[0][0],
        )
        self.assertIn(
            "without promising a substitute effect",
            ollama.prompts[0][0],
        )
        self.assertIn(
            "Complete plan coverage means every Goal has an explicit outcome",
            ollama.prompts[1][0],
        )
        self.assertIn(
            "deep goal outcome requires one legal explicit disposition",
            ollama.prompts[1][0],
        )
        self.assertNotIn(
            "unavailable and refused goal outcomes must not reference steps",
            ollama.prompts[1][0],
        )
        schema = ollama.prompts[0][1]["response_format"]
        vocal_outcome = schema["properties"]["goal_outcomes"]["properties"][
            "goal-sing"
        ]
        walk_outcome = schema["properties"]["goal_outcomes"]["properties"][
            "goal-walk"
        ]
        self.assertEqual(
            walk_outcome["properties"]["step_ids"]["maxItems"],
            1,
        )
        self.assertIn(
            "Optional or decorative effects require their own authoritative Goal",
            walk_outcome["properties"]["step_ids"]["description"],
        )
        self.assertEqual(
            vocal_outcome["properties"]["disposition"]["enum"],
            ["clarify", "unavailable", "refused"],
        )
        self.assertEqual(
            vocal_outcome["properties"]["response_text"]["maxLength"],
            800,
        )
        step_branches = schema["$defs"]["PlannerModelStep"]["oneOf"]
        self.assertTrue(step_branches)
        for branch in step_branches:
            self.assertNotIn(
                "goal-sing",
                branch["properties"]["source_goal_ids"]["items"]["enum"],
            )
        self.assertIn(
            "cannot be performed with the available capabilities",
            vocal_outcome["properties"]["response_text"]["description"],
        )
        self.assertIn(
            "Never claim or promise",
            vocal_outcome["properties"]["response_text"]["description"],
        )
        self.assertEqual(
            vocal_outcome["properties"]["step_ids"]["maxItems"],
            0,
        )
        self.assertEqual(schema["properties"]["response_text"]["maxLength"], 800)


    def test_missing_goal_outcomes_mixed_plan_repairs_under_required_schema(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
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
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
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


    def test_chat_route_schema_rejects_effectful_outcomes(self):
        schema = planner_schema.deep_plan_response_schema(
            ["goal-greet"], response_only=True
        )
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 0)
        self.assertEqual(
            schema["properties"]["disposition"]["enum"],
            ["respond", "clarify", "unavailable", "refused"],
        )
        outcome = schema["$defs"]["PlannerModelGoalOutcome"]
        self.assertNotIn("execute", outcome["properties"]["disposition"]["enum"])

    def test_deep_adapter_preserves_execute_response_text_for_later_delta_review(self):
        resolver = DeepPlannerResolver(SequencedOllama([]), FullCatalog())
        normalized = resolver._normalize(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Walk forward for 15 seconds.",
                "response_text": "好，我可以先做这个动作。",
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15},
                        "source_goal_ids": ["goal-action"],
                    }
                ],
                "goal_outcomes": {
                    "goal-action": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "好，我可以先做这个动作。",
                        "step_ids": ["walk"],
                    }
                },
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-action"],
                    "unmet_goal_ids": [],
                    "unmet_requirements": [],
                },
                "plan_relation": "exact",
                "user_confirmation_required": False,
            },
            request=request(goal_ids=["goal-action"]),
            plan_id="plan-transport-normalization",
            expected_goal_ids_for_turn=["goal-action"],
        )

        self.assertEqual(normalized["response_text"], "好，我可以先做这个动作。")
        self.assertEqual(
            normalized["goal_outcomes"][0]["response_text"],
            "好，我可以先做这个动作。",
        )
        self.assertEqual(
            normalized["steps"][0]["capability_id"],
            "soridormi.walk_forward",
        )

    def test_model_outcome_accepts_execute_response_text_before_materialization(self):
        output = validate_planner_model_output(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 0.95,
                "response_text": "Hello!",
                "steps": [
                    {
                        "step_id": "blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-greet"],
                    }
                ],
                "goal_outcomes": {
                    "goal-greet": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "Hello!",
                        "unresolved": [],
                        "step_ids": ["blink"],
                        "satisfaction": {
                            "score": 1.0,
                            "status": "exact",
                            "satisfied_goal_ids": ["goal-greet"],
                            "unmet_goal_ids": [],
                            "unmet_requirements": [],
                            "rationale": "Complete.",
                        },
                        "rationale": "Greet and blink.",
                    }
                },
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-greet"],
                    "unmet_goal_ids": [],
                    "unmet_requirements": [],
                    "rationale": "Complete.",
                },
                "plan_relation": "exact",
                "user_confirmation_required": False,
            },
            planner_tier="deep",
            expected_goal_ids_for_turn=["goal-greet"],
        )
        self.assertEqual(output.response_text, "Hello!")
        self.assertEqual(output.goal_outcomes["goal-greet"].response_text, "Hello!")

    def test_goal_outcome_schema_uses_exact_unique_goal_key_map(self):
        schema = planner_schema.deep_plan_response_schema(["goal-look", "goal-blink"])

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
        self.assertEqual(
            set(schema["$defs"]["PlannerModelGoalOutcome"]["required"]),
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
        for goal_id in ("goal-look", "goal-blink"):
            outcome = outcomes["properties"][goal_id]
            self.assertNotIn("oneOf", outcome)
            self.assertEqual(
                outcome["properties"]["disposition"]["enum"],
                [
                    "respond",
                    "execute",
                    "clarify",
                    "unavailable",
                    "refused",
                ],
            )
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
        self.assertIn("plan_relation", schema["properties"])
        self.assertIn("user_confirmation_required", schema["properties"])

    def test_exact_live_branch_minimal_plan_repairs_and_host_materializes_goal_ids(self):
        goal_ids = ["goal_2691cf9a52bfcaf9eefd", "goal_b027e0b6aae39d61e48f"]
        steps = [
            {
                "step_id": "step_look_at_user",
                "capability_id": "soridormi.look_at_person",
                "args": {"duration_s": 2.0, "target_ref": "person"},
                "timing": "sequential",
                "source_goal_ids": [goal_ids[0]],
                "reason_summary": "Look at the user for two seconds.",
            },
            {
                "step_id": "step_blink_twice",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "timing": "sequential",
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
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
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
                    "capability_id": "soridormi.blink_eyes",
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
                max_contract_repairs=1,
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
        repair_ref = plan.metadata["repair_raw_output_ref"]
        self.assertGreater(repair_ref["chars"], 0)
        self.assertTrue(repair_ref["digest"].startswith("sha256:"))
        self.assertNotIn("initial_raw_output", plan.metadata)
        self.assertNotIn("repair_raw_output", plan.metadata)

    def test_live_blink_and_joke_speech_step_repairs_to_mixed_respond_outcome(self):
        goal_ids = ["goal-blink", "goal-joke"]
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "steps": [
                {
                    "step_id": "step_blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-blink"],
                },
                {
                    "step_id": "step_joke",
                    "capability_id": "chromie.speak",
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
        self.assertEqual([step.capability_id for step in plan.steps], ["soridormi.blink_eyes"])
        self.assertEqual(
            [outcome.disposition for outcome in plan.goal_outcomes],
            ["execute", "respond"],
        )
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("Generic speech transport is never an executable", ollama.prompts[1][0])
        skill_enum = ollama.prompts[0][1]["response_format"]["$defs"][
            "PlannerModelStep"
        ]["properties"]["capability_id"]["enum"]
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
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-blink"],
                },
                {
                    "step_id": "step_neutral",
                    "capability_id": "soridormi.look_at_person",
                    "args": {"duration_s": 2.0, "target_ref": "person"},
                    "timing": "sequential",
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
                    "capability_id": "soridormi.blink_eyes",
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
                    "capability_id": "soridormi.blink_eyes",
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
                "capability_id": "soridormi.look_at_person",
                "args": {"duration_s": 2.0, "target_ref": "person"},
                "timing": "sequential",
                "source_goal_ids": ["goal-look"],
            },
            {
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "timing": "sequential",
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
                    "capability_id": "soridormi.blink_eyes",
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
                    "capability_id": "soridormi.blink_eyes",
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
                    "capability_id": "soridormi.blink_eyes",
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
                    "capability_id": "soridormi.blink_eyes",
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
        ollama = SequencedOllama([invalid])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(req)
        )

        self.assertEqual(plan.goal_outcomes[0].step_ids, ["blink"])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertFalse(plan.metadata["contract_repair_attempted"])

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
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-look"],
                },
                {
                    "step_id": "status",
                    "capability_id": "rare.observe_doorway",
                    "args": {},
                    "timing": "sequential",
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
                    "capability_id": "soridormi.blink_eyes",
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
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(req)
        )

        self.assertEqual(plan.goal_ids, ["goal-look"])
        self.assertEqual(len(plan.steps), 1)
        self.assertIn("goal_ids_do_not_match_goal_association", ollama.prompts[1][0])
        self.assertIn("Do not create goals for internal status checks", ollama.prompts[0][0])

    def test_transport_failure_does_not_consume_contract_retry(self):
        error = OllamaGenerationError(
            "model timed out",
            failure_class="timeout",
            failure_domain="inference_transport",
            architecture_attribution="not_evaluated",
            retryable=True,
        )
        ollama = SequencedOllama([error])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
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
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
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
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-action"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = SequencedOllama([invalid, revised])

        plan = asyncio.run(
            DeepPlannerResolver(ollama, FullCatalog(), max_contract_repairs=1).resolve(
                request("眨两下眼。")
            )
        )

        self.assertEqual(plan.steps[0].capability_id, "soridormi.blink_eyes")
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
                max_contract_repairs=0,
            ).resolve(request("眨两下眼。"))
        )

        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["reason"], "deep_planner_model_contract_failed")
        self.assertFalse(plan.metadata["contract_repair_attempted"])

    def test_repeated_invalid_plan_fails_closed_without_steps(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"goal_ids":["goal-action"],"steps":[
            {"capability_id":"invented.skill","args":{}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([invalid, invalid]), FullCatalog(), max_contract_repairs=1).resolve(request()))
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
                    "capability_id": "soridormi.blink_eyes",
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




if __name__ == "__main__":
    unittest.main()
