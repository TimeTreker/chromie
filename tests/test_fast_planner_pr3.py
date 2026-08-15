from __future__ import annotations

import asyncio
import unittest

from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_contract import (
    PlannerModelOutput,
    goal_association_prompt_projection,
    validate_external_response_evidence_boundary,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from agent.app.schema import AgentRunRequest, RouteDecision
from agent.app.capabilities.catalog import CatalogCapability
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerAdvanceModelOutput,
)
from shared.chromie_runtime.llm_diagnostics import ollama_prompt_preflight_diagnostics


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
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(capability_id="soridormi.blink_eyes", agent_id="capability_agent", description="Blink eyes", input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]}, route="robot_action", available=True, interaction_executable=True, prompt_tier="common"),
            CatalogCapability(capability_id="soridormi.walk_forward", agent_id="capability_agent", description="Walk forward", input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]}, route="robot_action", available=True, interaction_executable=True, prompt_tier="common"),
            CatalogCapability(
                capability_id="soridormi.walk_velocity",
                agent_id="capability_agent",
                description="Walk at an exact velocity",
                input_schema={
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number"},
                        "vy_mps": {"type": "number"},
                        "yaw_radps": {"type": "number"},
                        "duration_s": {"type": "number", "minimum": 0.1},
                    },
                    "required": ["vx_mps", "duration_s"],
                },
                route="robot_action",
                available=True,
                interaction_executable=True,
                prompt_tier="common",
            ),
            CatalogCapability(capability_id="chromie.speak", agent_id="capability_agent", description="Speak text", input_schema={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}, route="chat", available=True, interaction_executable=True, prompt_tier="common"),
        ]

    async def prompt_entries(self, **kwargs):
        return self.items


class AdvanceCatalogMustNotBeRead(FakeCatalog):
    async def prompt_entries(self, **kwargs):
        del kwargs
        raise AssertionError(
            "pre-Goal Fast Planner advancement must not read the Capability catalog"
        )


class GranularResourceCatalog(FakeCatalog):
    def __init__(self):
        super().__init__()
        self.items.extend(
            [
                CatalogCapability(
                    capability_id="soridormi.acquire_resource",
                    agent_id="capability_agent",
                    description="Acquire a physical resource.",
                    input_schema={"type": "object", "properties": {}},
                    route="robot_action",
                    available=True,
                    interaction_executable=True,
                    prompt_tier="common",
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
                    input_schema={"type": "object", "properties": {}},
                    route="robot_action",
                    available=True,
                    interaction_executable=True,
                    prompt_tier="common",
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

    async def prompt_entries(self, **kwargs):
        return self.items


class CompleteResourceCatalog(FakeCatalog):
    def __init__(self):
        super().__init__()
        self.items.append(
            CatalogCapability(
                capability_id="soridormi.acquire_and_deliver_resource",
                agent_id="capability_agent",
                description="Acquire and deliver a physical resource.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "resource": {"type": "object"},
                        "source": {"type": "object"},
                        "recipient": {"type": "object"},
                    },
                    "required": ["resource", "source", "recipient"],
                    "additionalProperties": False,
                },
                route="robot_action",
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                hints={
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["physical_object"],
                        "delivery_modes": ["physical_handover"],
                    },
                    "resource_contract": {
                        "plan_requires": [],
                        "plan_provides": [
                            "resource_acquired",
                            "resource_delivered",
                        ],
                        "completion_requires": [
                            "resource_acquired",
                            "resource_delivered",
                        ],
                    },
                },
            )
        )

    async def prompt_entries(self, **kwargs):
        return self.items


def request(text: str, route="robot_action", *, goal_ids=None, goal_metadata=None):
    goal_ids = list(goal_ids or [])
    new_goals = [
        {
            "goal_id": goal_id,
            "description": f"Goal {goal_id}",
            "source_text": text,
            "constraints": {},
            "success_criteria": [],
            "metadata": dict(goal_metadata or {}),
        }
        for goal_id in goal_ids
    ]
    return AgentRunRequest(
        sid="sid-pr3",
        text=text,
        language="zh-CN",
        route_decision=RouteDecision(route=route, intent="test", confidence=0.9, source="llm"),
        context={
            "active_goal_snapshots": [],
            "goal_association_resolution": {
                "associations": [],
                "new_goals": new_goals,
            },
        },
        history=[],
    )


def exact_satisfaction(goal_ids: list[str], rationale: str = "Exact plan coverage.") -> dict:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": list(goal_ids),
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": rationale,
    }


def unsatisfied_satisfaction(goal_ids: list[str], rationale: str) -> dict:
    return {
        "score": 0.0,
        "status": "unsatisfied",
        "satisfied_goal_ids": [],
        "unmet_goal_ids": list(goal_ids),
        "unmet_requirements": [rationale],
        "rationale": rationale,
    }


def execute_step(
    step_id: str,
    capability_id: str,
    args: dict,
    goal_ids: list[str],
    reason: str,
) -> dict:
    return {
        "step_id": step_id,
        "capability_id": capability_id,
        "args": args,
        "timing": "sequential",
        "source_goal_ids": list(goal_ids),
        "reason_summary": reason,
    }


def execute_outcome(goal_id: str, step_ids: list[str], reason: str) -> dict:
    return {
        "disposition": "execute",
        "coverage": "complete",
        "response_text": "",
        "unresolved": [],
        "step_ids": list(step_ids),
        "satisfaction": exact_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def respond_outcome(goal_id: str, text: str, reason: str) -> dict:
    return {
        "disposition": "respond",
        "coverage": "complete",
        "response_text": text,
        "unresolved": [],
        "step_ids": [],
        "satisfaction": exact_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def escalate_outcome(goal_id: str, reason: str) -> dict:
    return {
        "disposition": "escalate",
        "coverage": "uncertain",
        "response_text": "",
        "unresolved": [reason],
        "step_ids": [],
        "satisfaction": unsatisfied_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def multi_goal_plan(
    *,
    disposition: str,
    coverage: str,
    goal_summary: str,
    steps: list[dict],
    goal_outcomes: dict[str, dict],
    goal_satisfaction: dict,
    response_text: str = "",
    escalation_reason: str = "",
    unresolved: list[str] | None = None,
    parameter_resolutions: list[dict] | None = None,
    confidence: float = 0.97,
) -> dict:
    return {
        "disposition": disposition,
        "coverage": coverage,
        "confidence": confidence,
        "goal_summary": goal_summary,
        "response_text": response_text,
        "steps": steps,
        "escalation_reason": escalation_reason,
        "unresolved": list(unresolved or []),
        "parameter_resolutions": list(parameter_resolutions or []),
        "goal_outcomes": goal_outcomes,
        "goal_satisfaction": goal_satisfaction,
        "plan_relation": "exact",
        "user_confirmation_required": False,
    }


def retained_weather_followup_fixture() -> tuple[dict, AgentRunRequest]:
    goal_id = "goal-weather"
    evidence_first = "重庆今天有雷雨和冰雹，而且降雨概率很大。所以需要带伞。"
    primary = {
        "disposition": "respond",
        "coverage": "complete",
        "confidence": 1.0,
        "goal_summary": "Decide whether an umbrella is needed.",
        "response_text": evidence_first,
        "steps": [],
        "goal_outcomes": {
            goal_id: {
                "disposition": "respond",
                "coverage": "complete",
                "response_text": evidence_first,
                "unresolved": [],
                "step_ids": [],
                "satisfaction": exact_satisfaction([goal_id]),
                "rationale": "The retained weather result supports the decision.",
            }
        },
        "goal_satisfaction": exact_satisfaction([goal_id]),
    }
    planner_request = request(
        "那我出门需要带伞吗？",
        route="chat",
        goal_ids=[],
    )
    context = dict(planner_request.context)
    context["goal_association_resolution"] = {
        "associations": [
            {
                "association_id": "association-weather-followup",
                "relationship": "continue",
                "target_goal_ids": [goal_id],
                "confidence": 1.0,
                "reason_summary": (
                    "The latest turn asks for a practical decision from the retained result."
                ),
                "goal_update": {
                    "description": "Decide whether the person needs an umbrella."
                },
            }
        ],
        "new_goals": [],
    }
    context["recent_goal_snapshots"] = [
        {
            "goal_id": goal_id,
            "goal": {
                "description": "Check today's weather in Chongqing.",
                "source_text": "重庆今天会下雨吗？",
            },
        }
    ]
    context["history"] = [
        {
            "role": "assistant",
            "text": "重庆今天有雷雨和冰雹，而且降雨概率很大。",
            "metadata": {
                "source": "evidence_bound_tool_result_interpretation",
                "evidence_bound": True,
                "source_goal_ids": [goal_id],
                "canonical_plan_id": "plan-weather",
            },
        }
    ]
    return primary, planner_request.model_copy(update={"context": context})


class PlannerVocalResponsibilityTests(unittest.TestCase):
    @staticmethod
    def vocal_goal(*, output_mode: str, provider_required: bool) -> list[dict]:
        return [
            {
                "goal_id": "goal-vocal",
                "description": "Perform the requested vocal output.",
                "metadata": {
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "output_mode": output_mode,
                    "provider_required": provider_required,
                },
            }
        ]

    def test_planner_projection_preserves_typed_vocal_metadata(self):
        projection = goal_association_prompt_projection(
            {
                "goal_association_resolution": {
                    "new_goals": self.vocal_goal(
                        output_mode="singing",
                        provider_required=True,
                    )
                }
            }
        )

        self.assertEqual(
            projection["new_goals"][0]["metadata"],
            {
                "responsibility_kind": "vocal_output",
                "execution_lane": "vocal",
                "output_mode": "singing",
                "provider_required": True,
            },
        )

    def test_generic_respond_cannot_close_singing_goal(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 1.0,
                "response_text": "啦啦啦。",
                "steps": [],
                "goal_outcomes": {
                    "goal-vocal": {
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "啦啦啦。",
                        "step_ids": [],
                    }
                },
                "goal_satisfaction": exact_satisfaction(["goal-vocal"]),
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "cannot be completed by response_text",
        ):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=self.vocal_goal(
                    output_mode="singing",
                    provider_required=True,
                ),
            )

    def test_singing_goal_can_report_exact_unavailability(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "unavailable",
                "coverage": "uncertain",
                "confidence": 1.0,
                "response_text": "",
                "steps": [],
                "goal_outcomes": {
                    "goal-vocal": {
                        "disposition": "unavailable",
                        "coverage": "uncertain",
                        "response_text": "",
                        "unresolved": [
                            "No registered provider advertises singing mode."
                        ],
                        "step_ids": [],
                    }
                },
            }
        )

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=self.vocal_goal(
                output_mode="singing",
                provider_required=True,
            ),
        )

    def test_singing_unavailability_may_carry_truthful_response_text(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "unavailable",
                "coverage": "uncertain",
                "confidence": 1.0,
                "response_text": "I can't sing with the available capabilities.",
                "steps": [],
                "goal_outcomes": {
                    "goal-vocal": {
                        "disposition": "unavailable",
                        "coverage": "uncertain",
                        "response_text": "I can't sing with the available capabilities.",
                        "unresolved": ["No singing provider is registered."],
                        "step_ids": [],
                    }
                },
            }
        )

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=self.vocal_goal(
                output_mode="singing",
                provider_required=True,
            ),
        )
        self.assertIn("can't sing", output.response_text)

    def test_ordinary_speech_still_uses_respond_outcome(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 1.0,
                "response_text": "你好。",
                "steps": [],
                "goal_outcomes": {
                    "goal-vocal": {
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "你好。",
                        "step_ids": [],
                    }
                },
                "goal_satisfaction": exact_satisfaction(["goal-vocal"]),
            }
        )

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=self.vocal_goal(
                output_mode="speech",
                provider_required=False,
            ),
        )


class CanonicalPlanContractTests(unittest.TestCase):
    def test_complete_execute_plan_cannot_retain_top_level_unresolved_work(self):
        goal_id = "goal-resource"
        reason = "Acquire and deliver one resource."
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary=reason,
            steps=[
                execute_step(
                    "acquire-and-deliver",
                    "soridormi.acquire_and_deliver_resource",
                    {
                        "resource": {
                            "kind": "physical_object",
                            "description": "one cup of water",
                        },
                        "source": {"status": "provider_resolved"},
                        "recipient": {"description": "requester"},
                    },
                    [goal_id],
                    reason,
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(
                    goal_id,
                    ["acquire-and-deliver"],
                    reason,
                )
            },
            goal_satisfaction=exact_satisfaction([goal_id], reason),
            unresolved=[goal_id],
        )

        with self.assertRaisesRegex(
            ValueError,
            "complete execute or respond planner output must not retain unresolved work",
        ):
            validate_planner_model_output(
                raw,
                planner_tier="fast",
                expected_goal_ids_for_turn=[goal_id],
            )

    def test_effectful_goal_cannot_be_declared_satisfied_with_zero_steps(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Walk forward for fifteen seconds.",
            "response_text": "Done.",
            "steps": [],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {},
            "goal_satisfaction": exact_satisfaction(["goal-walk"]),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=["goal-walk"],
        )

        with self.assertRaisesRegex(
            ValueError,
            "unresolved effectful goal requires an executable step",
        ):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-walk",
                        "metadata": {
                            "responsibility_kind": "executable_action",
                            "execution_lane": "activity",
                            "output_mode": "physical_action",
                            "provider_required": True,
                        },
                    }
                ],
            )

    def test_effectful_goal_accepts_explicit_unavailability_without_steps(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "unavailable",
                "coverage": "uncertain",
                "confidence": 1.0,
                "response_text": "",
                "steps": [],
                "goal_outcomes": {
                    "goal-walk": {
                        "disposition": "unavailable",
                        "coverage": "uncertain",
                        "response_text": "",
                        "unresolved": ["No available walking provider."],
                        "step_ids": [],
                    }
                },
            }
        )

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=[
                {
                    "goal_id": "goal-walk",
                    "metadata": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "physical_action",
                        "provider_required": True,
                    },
                }
            ],
        )

    def test_capability_dependent_goal_cannot_be_completed_by_respond_outcome(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Answer with current weather.",
            "response_text": "内乡今天有雷雨。",
            "steps": [],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {},
            "goal_satisfaction": exact_satisfaction(["goal-weather"]),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=["goal-weather"],
        )

        with self.assertRaisesRegex(
            ValueError,
            "capability_dependent goal cannot use disposition=respond",
        ):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-weather",
                        "metadata": {
                            "responsibility_kind": "capability_dependent"
                        },
                    }
                ],
            )

    def test_capability_dependent_goal_can_respond_from_exact_delivered_evidence(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Restate completed weather evidence.",
            "response_text": "现在有雷雨。",
            "steps": [],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {},
            "goal_satisfaction": exact_satisfaction(["goal-weather"]),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=["goal-weather"],
        )

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=[
                {
                    "goal_id": "goal-weather",
                    "metadata": {"responsibility_kind": "capability_dependent"},
                }
            ],
            context={
                "history": [
                    {
                        "role": "assistant",
                        "text": "内乡现在有雷雨。",
                        "metadata": {
                            "evidence_bound": True,
                            "source": "evidence_bound_tool_result_interpretation",
                            "source_goal_ids": ["goal-weather"],
                        },
                    }
                ]
            },
        )

    def test_partial_plan_cannot_carry_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="fast", disposition="escalate", coverage="partial", confidence=0.5, escalation_reason="compound", steps=[{"step_id":"s","capability_id":"soridormi.walk_forward","args":{"duration_s":15}}])

    def test_complete_execute_requires_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="fast", disposition="execute", coverage="complete", confidence=0.9)

    def test_response_plan_cannot_hide_executable_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(
                plan_id="p",
                planner_tier="fast",
                disposition="respond",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-joke"],
                response_text="A joke.",
                steps=[{
                    "step_id": "wrong",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-joke"],
                }],
            )

    def test_simple_chat_can_be_complete_response(self):
        plan = CanonicalPlan(plan_id="p", planner_tier="fast", disposition="respond", coverage="complete", confidence=0.9, response_text="你好。")
        self.assertEqual(plan.response_text, "你好。")

    def test_fast_mixed_plan_is_valid_for_execute_and_respond_outcomes(self):
        plan = CanonicalPlan(
            plan_id="p-fast-mixed",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-blink", "goal-joke"],
            steps=[{
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
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
                    "response_text": "A short joke.",
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
        )
        self.assertEqual(plan.disposition, "mixed")


class PlannerStructuralNormalizationTests(unittest.TestCase):
    def test_single_response_goal_outcome_populates_redundant_top_level_fields(self):
        output = validate_planner_model_output(
            {
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 0.95,
                "steps": [],
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                },
                "goal_outcomes": {
                    "goal-weather": {
                        "response_text": "I can help with that.",
                        "step_ids": [],
                    }
                },
            },
            planner_tier="fast",
            expected_goal_ids_for_turn=["goal-weather"],
        )

        self.assertEqual(output.response_text, "I can help with that.")
        outcome = output.goal_outcomes["goal-weather"]
        self.assertEqual(outcome.disposition, "respond")
        self.assertEqual(outcome.coverage, "complete")


    def test_step_outcome_links_follow_model_authored_step_ownership(self):
        output = validate_planner_model_output(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "response_text": "",
                "steps": [
                    {
                        "step_id": "walk-step",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-walk"],
                    },
                    {
                        "step_id": "blink-step",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-blink"],
                    },
                ],
                "goal_outcomes": {
                    "goal-walk": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "step_ids": ["walk-step"],
                        "satisfaction": exact_satisfaction(["goal-walk"]),
                    },
                    "goal-sing": {
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "啦啦啦，今天一起向前走。",
                        "step_ids": ["walk-step"],
                        "satisfaction": exact_satisfaction(["goal-sing"]),
                    },
                    "goal-blink": {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "step_ids": ["ghost-step"],
                        "satisfaction": exact_satisfaction(["goal-blink"]),
                    },
                },
                "goal_satisfaction": exact_satisfaction(
                    ["goal-walk", "goal-sing", "goal-blink"]
                ),
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [],
                "plan_relation": "exact",
                "user_confirmation_required": False,
            },
            planner_tier="fast",
            expected_goal_ids_for_turn=[
                "goal-walk",
                "goal-sing",
                "goal-blink",
            ],
        )

        self.assertEqual(output.disposition, "mixed")
        self.assertEqual(output.goal_outcomes["goal-walk"].step_ids, ["walk-step"])
        self.assertEqual(output.goal_outcomes["goal-sing"].step_ids, [])
        self.assertEqual(output.goal_outcomes["goal-blink"].step_ids, ["blink-step"])

    def test_transport_normalization_does_not_assign_an_unowned_execute_goal(self):
        with self.assertRaisesRegex(
            ValueError,
            "execute goal outcome requires complete coverage and step_ids",
        ):
            validate_planner_model_output(
                {
                    "disposition": "execute",
                    "coverage": "complete",
                    "confidence": 1.0,
                    "response_text": "",
                    "steps": [
                        {
                            "step_id": "walk-step",
                            "capability_id": "soridormi.walk_forward",
                            "args": {"duration_s": 15.0},
                            "timing": "sequential",
                            "source_goal_ids": ["goal-walk"],
                        }
                    ],
                    "goal_outcomes": {
                        "goal-walk": {
                            "disposition": "execute",
                            "coverage": "complete",
                            "response_text": "",
                            "step_ids": ["walk-step"],
                            "satisfaction": exact_satisfaction(["goal-walk"]),
                        },
                        "goal-unowned": {
                            "disposition": "execute",
                            "coverage": "complete",
                            "response_text": "",
                            "step_ids": ["invented"],
                            "satisfaction": exact_satisfaction(["goal-unowned"]),
                        },
                    },
                    "goal_satisfaction": exact_satisfaction(
                        ["goal-walk", "goal-unowned"]
                    ),
                    "escalation_reason": "",
                    "unresolved": [],
                    "parameter_resolutions": [],
                    "plan_relation": "exact",
                    "user_confirmation_required": False,
                },
                planner_tier="fast",
                expected_goal_ids_for_turn=["goal-walk", "goal-unowned"],
            )


class FastPlannerResolverTests(unittest.TestCase):
    def test_pre_goal_advance_can_complete_clear_greeting_without_goal_association(self):
        ollama = FakeOllama(
            {
                "covered_responsibility_refs": ["greeting"],
                "immediate_vocal_activity": {
                    "activity_id": "activity-greeting",
                    "role": "complete_response",
                    "response_text": "嗨～",
                    "speech_act": "greeting",
                    "source_responsibility_refs": ["greeting"],
                },
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = AgentRunRequest(
            sid="turn-greeting",
            text="你好",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat", intent="greeting", confidence=0.98, source="llm"
            ),
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "bindings": {},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.98,
                    }
                ],
                "active_goal_snapshots": [],
                "interaction_context": {},
            },
            history=[],
        )

        advance = asyncio.run(FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request))

        self.assertIsInstance(advance, FastPlannerAdvance)
        self.assertEqual(advance.continuations, [])
        self.assertEqual(advance.immediate_vocal_activity.response_text, "嗨～")
        self.assertEqual(advance.immediate_vocal_activity.role, "complete_response")
        self.assertIn("Responsibility evidence", ollama.prompts[0][0])

    def test_pre_goal_advance_preserves_profile_context_topology(self):
        ollama = FakeOllama(
            {
                "covered_responsibility_refs": ["greeting"],
                "immediate_vocal_activity": {
                    "activity_id": "activity-greeting",
                    "role": "complete_response",
                    "response_text": "嗨～",
                    "speech_act": "greeting",
                    "source_responsibility_refs": ["greeting"],
                },
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = AgentRunRequest(
            sid="turn-greeting-profile-context",
            text="你好",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat", intent="greeting", confidence=0.98, source="llm"
            ),
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.98,
                    }
                ]
            },
            history=[],
        )

        asyncio.run(
            FastPlannerResolver(
                ollama,
                AdvanceCatalogMustNotBeRead(),
                num_ctx=32768,
            ).resolve_advance(run_request)
        )

        self.assertEqual(ollama.prompts[0][1]["options"]["num_ctx"], 32768)

    def test_pre_goal_advance_does_not_depend_on_capability_catalog(self):
        ollama = FakeOllama(
            {
                "covered_responsibility_refs": ["greeting"],
                "immediate_vocal_activity": {
                    "activity_id": "activity-greeting",
                    "role": "complete_response",
                    "response_text": "嗨～",
                    "speech_act": "greeting",
                    "source_responsibility_refs": ["greeting"],
                },
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = AgentRunRequest(
            sid="turn-greeting-no-catalog",
            text="你好",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat", intent="greeting", confidence=0.98, source="llm"
            ),
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "bindings": {},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.98,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, AdvanceCatalogMustNotBeRead()).resolve_advance(
                run_request
            )
        )

        self.assertEqual(advance.continuations, [])
        rendered = str(ollama.prompts[0][0])
        self.assertNotIn("Common capability awareness", rendered)
        self.assertNotIn("soridormi.walk_forward", rendered)

    def test_pre_goal_weather_prompt_fits_declared_four_k_context_budget(self):
        resolver = FastPlannerResolver(FakeOllama({}), AdvanceCatalogMustNotBeRead())
        responsibility = {
            "local_ref": "weather",
            "outcome": "Tell the user whether it will rain in Chongqing tonight.",
            "bindings": {
                "location": "Chongqing",
                "date": "2026-08-15",
                "time": "night",
            },
            "completion_requires_work": True,
            "completion_requires_fresh_evidence": True,
            "confidence": 0.95,
        }
        run_request = AgentRunRequest(
            sid="turn-weather-budget",
            text="你好，今天重庆晚上有没有雨啊？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool", intent="weather_lookup", confidence=0.95, source="llm"
            ),
            context={
                "responsibility_proposals": [responsibility],
                "active_goal_snapshots": [],
                "interaction_context": {},
                "mind": {
                    "owner_approved": True,
                    "profile_id": "chromie_default_mind",
                    "version": "0.6.1",
                    "identity": {
                        "name": "Chromie",
                        "kind": "human child",
                        "age_description": "6 years old",
                        "family_role": "the family's secretary",
                        "short_self_description": (
                            "I'm Chromie. I'm six years old, I'm a human girl, and "
                            "I'm our family's little secretary."
                        ),
                        # Deliberately huge unrelated policy fields must not inflate
                        # this latency-critical prompt.
                        "identity_answer_guidance": "x" * 4000,
                        "model_identity_boundary": "y" * 4000,
                    },
                    "personality_expression": {
                        "owner_approved": True,
                        "core_traits": [
                            "smart",
                            "curious",
                            "warm",
                            "cute",
                            "direct",
                            "simple",
                            "playful",
                            "innocent",
                        ],
                        "spoken_style": (
                            "Speak in short, natural, age-appropriate sentences. "
                            "Sound bright and emotionally alive."
                        ),
                        "tool_use_style": (
                            "When checking or doing something, speak as a child "
                            "responding to a person, not as a status monitor."
                        ),
                        "maturity_boundary": "z" * 4000,
                    },
                },
            },
            history=[],
        )
        responsibilities = [CognitiveResponsibilityProposal.model_validate(responsibility)]
        prompt = resolver._advance_layered_prompt(
            run_request,
            responsibilities=responsibilities,
        )
        system = resolver._advance_system_prompt()
        diagnostics = ollama_prompt_preflight_diagnostics(
            prompt_chars=len(str(prompt)),
            system_chars=len(system),
            options={"num_ctx": 4096, "num_predict": 384},
            chars_per_token=2.0,
            safety_margin_tokens=2048,
        )

        self.assertLess(len(str(prompt)), 2600)
        self.assertFalse(
            any(item.event == "llm_prompt_budget_exceeded" for item in diagnostics),
            diagnostics,
        )
        self.assertNotIn("identity_answer_guidance", str(prompt))
        self.assertNotIn("Common capability awareness", str(prompt))

    def test_pre_goal_advance_model_schema_requires_explicit_decision_fields(self):
        schema = FastPlannerAdvanceModelOutput.model_json_schema()

        self.assertEqual(
            set(schema["required"]),
            {
                "covered_responsibility_refs",
                "immediate_vocal_activity",
                "continuations",
                "confidence",
                "unresolved",
                "reason_summary",
            },
        )

    def test_pre_goal_advance_invalid_weather_output_fails_soft_into_goal_association(self):
        # Retained live regression: qwen3:4b once emitted only this Activity,
        # omitted the continuation/coverage decision, and mislabeled progress as
        # a complete response. Fast advancement must not kill the weather work.
        ollama = FakeOllama(
            {
                "immediate_vocal_activity": {
                    "activity_id": "vocal_response",
                    "role": "complete_response",
                    "response_text": "I'm checking the weather for Chongqing tonight!",
                    "speech_act": "completing_response",
                    "source_responsibility_refs": ["weather"],
                }
            }
        )
        run_request = AgentRunRequest(
            sid="turn-weather-invalid-advance",
            text="今天重庆晚上会不会下大雨？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat", intent="weather_query", confidence=0.96, source="llm"
            ),
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user whether it will rain in Chongqing tonight.",
                        "bindings": {"location": "重庆", "time": "今晚"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.continuations, ["goal_association"])
        self.assertIsNone(advance.immediate_vocal_activity)
        self.assertEqual(
            advance.metadata["advance_status"],
            "fallback_to_goal_association",
        )
        self.assertEqual(
            advance.metadata["failure_class"],
            "fast_advance_contract_invalid",
        )

    def test_pre_goal_advance_accepts_weather_progress_with_goal_association(self):
        ollama = FakeOllama(
            {
                "covered_responsibility_refs": ["weather"],
                "immediate_vocal_activity": {
                    "activity_id": "activity-weather-progress",
                    "role": "progress",
                    "response_text": "我看看今晚会不会下大雨～",
                    "speech_act": "acknowledge",
                    "source_responsibility_refs": ["weather"],
                },
                "continuations": ["goal_association"],
                "confidence": 0.95,
                "unresolved": [],
                "reason_summary": "Fresh weather evidence is still required.",
            }
        )
        run_request = AgentRunRequest(
            sid="turn-weather-progress",
            text="今天重庆晚上会不会下大雨？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat", intent="weather_query", confidence=0.96, source="llm"
            ),
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user whether it will rain in Chongqing tonight.",
                        "bindings": {"location": "重庆", "time": "今晚"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.continuations, ["goal_association"])
        self.assertIsNotNone(advance.immediate_vocal_activity)
        self.assertEqual(advance.immediate_vocal_activity.role, "progress")
        self.assertIn("Language hint: zh-CN", str(ollama.prompts[0][0]))

    def test_pre_goal_advance_deep_planner_also_requires_goal_association(self):
        with self.assertRaisesRegex(ValueError, "Deep Planner continuation requires Goal Association"):
            FastPlannerAdvance.model_validate(
                {
                    "turn_id": "turn-complex",
                    "covered_responsibility_refs": ["fetch-water"],
                    "continuations": ["deep_planner"],
                    "confidence": 0.9,
                }
            )

    def test_prompt_receives_goal_scoped_interaction_context(self):
        planner_request = request(
            "Walk forward for fifteen seconds.",
            goal_ids=["goal-walk"],
        )
        planner_request.context["interaction_context"] = {
            "events": [{"event_id": "ledger-fast-marker"}]
        }
        prompt = FastPlannerResolver(
            FakeOllama({}),
            FakeCatalog(),
        )._prompt(
            planner_request,
            [],
            response_schema={},
        )

        self.assertIn("ledger-fast-marker", prompt)
        self.assertIn("plan only the still-needed conversational and effectful delta", prompt)

    def test_effectful_zero_step_false_satisfaction_escalates_without_same_tier_repair(self):
        invalid = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Walk forward for fifteen seconds.",
            "response_text": "I did it.",
            "steps": [],
            "goal_outcomes": {},
            "goal_satisfaction": exact_satisfaction(["goal-walk"]),
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        ollama = ScriptedOllama([invalid, invalid])
        run_request = request(
            "Walk forward for fifteen seconds.",
            goal_ids=["goal-walk"],
        )
        context = dict(run_request.context)
        association = dict(context["goal_association_resolution"])
        association["new_goals"] = [
            {
                **association["new_goals"][0],
                "metadata": {
                    "responsibility_kind": "executable_action",
                    "execution_lane": "activity",
                    "output_mode": "physical_action",
                    "provider_required": True,
                },
            }
        ]
        context["goal_association_resolution"] = association

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.metadata["path_classification"], "semantic_escalation")
        self.assertEqual(plan.escalation_reason, "fast_planner_semantic_validation_failed")
        self.assertIn(
            "unresolved effectful goal requires an executable step",
            plan.metadata["error"],
        )

    def test_missing_resource_provider_escalates_without_hard_model_failure(self):
        goal_id = "goal-resource"
        reason = "Fetch and hand over the red mug."
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary=reason,
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    [goal_id],
                    reason,
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(goal_id, ["walk"], reason)
            },
            goal_satisfaction=exact_satisfaction([goal_id], reason),
        )
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
            FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(
            plan.escalation_reason,
            "resource_responsibility_capability_unavailable",
        )
        self.assertEqual(plan.steps, [])
        self.assertTrue(plan.metadata["resource_contract_unavailable"])
        self.assertNotIn("failure_class", plan.metadata)

    def test_granular_resource_catalog_escalates_to_deep_composition(self):
        goal_id = "goal-resource"
        reason = "Fetch and hand over the red mug."
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary=reason,
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    [goal_id],
                    reason,
                )
            ],
            goal_outcomes={goal_id: execute_outcome(goal_id, ["walk"], reason)},
            goal_satisfaction=exact_satisfaction([goal_id], reason),
        )
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

        ollama = FakeOllama(raw)
        plan = asyncio.run(
            FastPlannerResolver(ollama, GranularResourceCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(
            plan.escalation_reason,
            "resource_responsibility_composition_required",
        )
        self.assertEqual(plan.steps, [])
        self.assertTrue(plan.metadata["resource_composition_required"])
        self.assertFalse(plan.metadata["execution_allowed"])

    def test_voice_log_resource_plan_grounds_nested_distance_and_quantity(self):
        goal_id = "goal-water"
        reason = "从前方100米处拿一杯水并送给用户。"
        resource = {
            "kind": "physical_object",
            "description": "一杯水",
            "quantity": "1",
            "attributes": {},
        }
        source = {
            "status": "known",
            "description": "前方100米处",
            "bindings": {
                "distance": {
                    "name": "distance",
                    "entity_type": "distance",
                    "value": "100m",
                    "confidence": 1.0,
                },
                "direction": {
                    "name": "direction",
                    "entity_type": "direction",
                    "value": "前方",
                    "confidence": 1.0,
                },
            },
        }
        recipient = {"description": "用户", "referent_id": None}
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary=reason,
            steps=[
                execute_step(
                    "fetch-water",
                    "soridormi.acquire_and_deliver_resource",
                    {
                        "resource": resource,
                        "source": source,
                        "recipient": recipient,
                    },
                    [goal_id],
                    reason,
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(goal_id, ["fetch-water"], reason)
            },
            goal_satisfaction=exact_satisfaction([goal_id], reason),
            parameter_resolutions=[],
        )
        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": "The complete resource capability preserves the one responsibility.",
        }
        run_request = request(
            "去往前走个100米，帮我拿杯水过来。",
            goal_ids=[goal_id],
        )
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": goal_id,
                    "description": reason,
                    "source_text": run_request.text,
                    "object": {
                        "bindings": {
                            "distance": source["bindings"]["distance"],
                            "direction": source["bindings"]["direction"],
                        }
                    },
                    "resource_responsibility": {
                        "schema_version": 1,
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource": resource,
                        "source": source,
                        "recipient": recipient,
                        "delivery_mode": "physical_handover",
                        "metadata": {},
                    },
                    "metadata": {"responsibility_kind": "executable_action"},
                }
            ],
        }
        ollama = ScriptedOllama([raw, coverage_review])

        plan = asyncio.run(
            FastPlannerResolver(ollama, CompleteResourceCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(
            [step.capability_id for step in plan.steps],
            ["soridormi.acquire_and_deliver_resource"],
        )
        self.assertEqual(plan.steps[0].args["source"], source)
        self.assertEqual(plan.steps[0].args["resource"], resource)
        self.assertEqual(plan.parameter_resolutions, [])
        self.assertIn(
            "do not emit parameter_resolutions for their nested fields",
            ollama.prompts[0][0],
        )

    def test_schema_invalid_capability_args_get_bounded_model_repair(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.94,
            "goal_ids": ["goal-walk"],
            "goal_summary": "Walk briefly.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"velocity": 0.1, "duration_s": 1.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = {
            **invalid,
            "steps": [
                {
                    **invalid["steps"][0],
                    "args": {"vx_mps": 0.1, "duration_s": 1.0},
                }
            ],
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("Walk briefly.", goal_ids=["goal-walk"])
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].args, {"vx_mps": 0.1, "duration_s": 1.0})
        self.assertIn("invalid_args", ollama.prompts[1][0])
        self.assertIn("vx_mps", ollama.prompts[1][0])
        step_schema = ollama.prompts[0][1]["response_format"]["$defs"][
            "PlannerModelStep"
        ]
        velocity_branch = next(
            branch
            for branch in step_schema["oneOf"]
            if branch["properties"]["capability_id"]["enum"]
            == ["soridormi.walk_velocity"]
        )
        self.assertEqual(
            velocity_branch["properties"]["args"]["required"],
            ["vx_mps", "duration_s"],
        )

    def test_unrepaired_capability_args_are_not_marked_complete(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.94,
            "goal_ids": ["goal-walk"],
            "goal_summary": "Walk briefly.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"velocity": 0.1, "duration_s": 1.0},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }

        plan = asyncio.run(
            FastPlannerResolver(
                FakeOllama(invalid),
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve(request("Walk briefly.", goal_ids=["goal-walk"]))
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(
            plan.metadata["validation_feedback"][0]["capability_id"],
            "soridormi.walk_velocity",
        )

    def test_simple_blink_produces_complete_direct_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.94,"goal_ids":["goal-blink"],"goal_summary":"blink four times","steps":[{"step_id":"blink","capability_id":"soridormi.blink_eyes","args":{"count":4},"timing":"sequential","source_goal_ids":["goal-blink"]}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("眨四下眼睛。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.coverage, "complete")
        self.assertEqual(plan.steps[0].capability_id, "soridormi.blink_eyes")
        self.assertEqual(plan.metadata["authority"], "advisory")

    def test_compatibility_chat_route_cannot_suppress_canonical_body_goal(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.96,
            "goal_summary": "blink twice",
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": "The exact blink capability completely covers the canonical body Goal.",
        }
        ollama = ScriptedOllama([raw, coverage_review])
        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Blink twice.",
                    route="chat",
                    goal_ids=["goal-blink"],
                    goal_metadata={
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "body_action",
                        "provider_required": True,
                    },
                )
            )
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual([step.capability_id for step in plan.steps], ["soridormi.blink_eyes"])
        schema = ollama.prompts[0][1]["response_format"]
        self.assertNotEqual(schema["properties"]["steps"].get("maxItems"), 0)
        self.assertIn("soridormi.blink_eyes", ollama.prompts[0][0])
        self.assertNotIn("Goal Interpretation advisory JSON", ollama.prompts[0][0])
        self.assertNotIn("authoritative source route", ollama.prompts[0][0].casefold())

    def test_simple_chat_produces_complete_response(self):
        raw = multi_goal_plan(
            disposition="respond",
            coverage="complete",
            goal_summary="greet",
            response_text="你好。",
            steps=[],
            goal_outcomes={
                "goal-greet": respond_outcome("goal-greet", "你好。", "Direct greeting.")
            },
            goal_satisfaction=exact_satisfaction(["goal-greet"]),
        )
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("你好。", route="chat", goal_ids=["goal-greet"], goal_metadata={"responsibility_kind": "vocal_output", "output_mode": "speech", "provider_required": False})))
        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.steps, [])



    def test_fast_clarification_is_a_terminal_valid_outcome(self):
        raw = {
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.9,
            "goal_summary": "Clarify the requested place.",
            "response_text": "Which place do you mean?",
            "steps": [],
            "escalation_reason": "",
            "unresolved": ["location"],
            "parameter_resolutions": [],
            "goal_outcomes": {
                "goal-place": {
                    "disposition": "clarify",
                    "coverage": "partial",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": [],
                    "satisfaction": {
                        "score": 0.0,
                        "status": "partial",
                        "satisfied_goal_ids": [],
                        "unmet_goal_ids": ["goal-place"],
                        "unmet_requirements": ["location"],
                        "rationale": "The location is unresolved.",
                    },
                    "rationale": "The location is unresolved.",
                }
            },
            "goal_satisfaction": {
                "score": 0.0,
                "status": "partial",
                "satisfied_goal_ids": [],
                "unmet_goal_ids": ["goal-place"],
                "unmet_requirements": ["location"],
                "rationale": "The location is unresolved.",
            },
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
        output = validate_planner_model_output(
            raw, planner_tier="fast", expected_goal_ids_for_turn=["goal-place"]
        )
        self.assertEqual(output.disposition, "clarify")
        self.assertEqual(
            output.goal_outcomes["goal-place"].response_text,
            "Which place do you mean?",
        )
        self.assertEqual(output.goal_satisfaction.status, "unsatisfied")

    def test_unresolved_safe_read_cannot_become_direct_factual_response(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 1.0,
                "response_text": "It rained 2 mm.",
                "steps": [],
                "goal_outcomes": {
                    "goal-weather": {
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "It rained 2 mm.",
                        "unresolved": [],
                        "step_ids": [],
                        "satisfaction": {
                            "score": 1.0,
                            "status": "exact",
                            "satisfied_goal_ids": ["goal-weather"],
                            "unmet_goal_ids": [],
                            "unmet_requirements": [],
                            "rationale": "Claims a weather result.",
                        },
                        "rationale": "Claims a weather result.",
                    }
                },
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-weather"],
                    "unmet_goal_ids": [],
                    "unmet_requirements": [],
                    "rationale": "Claims a weather result.",
                },
            }
        )
        context = {
            "active_goal_snapshots": [
                {
                    "goal_id": "goal-weather",
                    "metadata": {
                        "execution_binding": {
                            "execution_outcome_status": "failed",
                            "retryable_safe_read": True,
                            "planned_skills": [
                                {
                                    "capability_id": "chromie.weather.lookup",
                                    "safety_class": "safe_read",
                                    "retryable_safe_read": True,
                                }
                            ],
                        }
                    },
                }
            ]
        }
        with self.assertRaisesRegex(
            ValueError, "external_read_response_requires_completed_or_verified_evidence"
        ):
            validate_external_response_evidence_boundary(output, context=context)

        index_only_context = {
            "verified_tool_memory_index": [
                {
                    "evidence_id": "evidence-weather",
                    "tool_id": "chromie.weather.lookup",
                    "status": "completed",
                    "request_args": {"location": "Beijing", "date": "today"},
                    "goal_ids": ["goal-weather"],
                }
            ],
            "history": [],
        }
        with self.assertRaisesRegex(
            ValueError,
            "external_read_response_requires_evidence_bound_dialogue_or_retrieval",
        ):
            validate_external_response_evidence_boundary(
                output,
                context=index_only_context,
            )

        index_only_context["history"] = [
            {
                "role": "assistant",
                "text": "Beijing is hot: 28°C and feels like 33°C.",
                "metadata": {
                    "source": "evidence_bound_tool_result_interpretation",
                    "evidence_bound": True,
                    "source_goal_ids": ["goal-weather"],
                    "canonical_plan_id": "plan-weather",
                },
            }
        ]
        validate_external_response_evidence_boundary(
            output,
            context=index_only_context,
        )

    def test_chat_route_schema_is_response_only(self):
        raw = multi_goal_plan(
            disposition="respond",
            coverage="complete",
            goal_summary="greet",
            response_text="Hello!",
            steps=[],
            goal_outcomes={
                "goal-greet": respond_outcome("goal-greet", "Hello!", "Direct greeting.")
            },
            goal_satisfaction=exact_satisfaction(["goal-greet"]),
        )
        ollama = FakeOllama(raw)
        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("Hello.", route="chat", goal_ids=["goal-greet"], goal_metadata={"responsibility_kind": "vocal_output", "output_mode": "speech", "provider_required": False})
            )
        )
        self.assertEqual(plan.disposition, "respond")
        schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 0)
        self.assertEqual(
            schema["properties"]["disposition"]["enum"],
            ["respond", "clarify", "escalate"],
        )
        self.assertIn("response_text", schema["required"])
        self.assertIn("escalation_reason", schema["required"])
        self.assertIn("goal_outcomes", schema["required"])
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["required"],
            ["goal-greet"],
        )
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["minProperties"],
            1,
        )
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["maxProperties"],
            1,
        )

    def test_contract_repair_receives_all_compound_shape_defects(self):
        invalid = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 0.95,
            "response_text": "Done.",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
            "goal_satisfaction": {"score": 1.0, "status": "substantial"},
        }
        repaired = {
            **multi_goal_plan(
                disposition="escalate",
                coverage="uncertain",
                confidence=0.95,
                goal_summary="Walk for one second, then blink twice.",
                steps=[],
                goal_outcomes={
                    "goal-walk": escalate_outcome(
                        "goal-walk",
                        "Compound request requires deeper planning.",
                    ),
                    "goal-blink": escalate_outcome(
                        "goal-blink",
                        "Compound request requires deeper planning.",
                    ),
                },
                goal_satisfaction=unsatisfied_satisfaction(
                    ["goal-walk", "goal-blink"],
                    "Compound request requires deep multi-goal accounting.",
                ),
                escalation_reason=(
                    "Compound request requires deep multi-goal accounting."
                ),
                unresolved=["goal-walk", "goal-blink"],
            )
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk for one second, then blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        repair_prompt = ollama.prompts[1][0]
        self.assertIn("goal satisfaction score is inconsistent with status", repair_prompt)
        self.assertIn("respond planner output must not carry executable steps", repair_prompt)
        self.assertIn("complete multi-goal planner output requires goal_outcomes", repair_prompt)
        self.assertIn("regenerate one fresh complete model-authored plan object", repair_prompt)
        self.assertIn(
            "Previous Fast Planner output when doing a mechanical DTO regeneration:\nnull",
            repair_prompt,
        )

    def test_compound_walk_and_blink_escalates_without_partial_steps(self):
        raw = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.88,
            goal_summary="walk while blinking",
            steps=[],
            goal_outcomes={
                "goal-walk": escalate_outcome(
                    "goal-walk", "concurrency feasibility"
                ),
                "goal-blink": escalate_outcome(
                    "goal-blink", "blink timing requires deeper planning"
                ),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-walk", "goal-blink"],
                "compound_goal_requires_full_planning",
            ),
            escalation_reason="compound_goal_requires_full_planning",
            unresolved=["concurrency feasibility", "blink count"],
        )
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("往前走15秒，同时眨眼。", goal_ids=["goal-walk", "goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertIn("concurrency feasibility", plan.unresolved)
        self.assertEqual(
            {item.disposition for item in plan.goal_outcomes},
            {"escalate"},
        )
        self.assertEqual(plan.metadata["path_classification"], "semantic_escalation")

    def test_coordinated_action_review_blocks_single_step_overclaim(self):
        raw = {
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
                    "reason_summary": "Walk for the requested duration.",
                }
            ],
            "goal_satisfaction": exact_satisfaction(["goal-action"]),
        }
        run_request = request(
            "Walk for 15 seconds while blinking and singing.",
            goal_ids=["goal-action"],
        )
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
        ollama = ScriptedOllama(
            [
                raw,
                {
                    "decision": "reject",
                    "confidence": 1.0,
                    "uncovered_requirements": ["blinking", "singing"],
                    "reason": "The proposed Plan contains only walking.",
                },
            ]
        )

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertEqual(
            plan.escalation_reason,
            "coordinated_action_coverage_incomplete",
        )
        self.assertEqual(plan.unresolved, ["blinking", "singing"])
        self.assertFalse(plan.metadata["execution_allowed"])
        self.assertIn("ordinary world knowledge", ollama.prompts[1][0])
        self.assertIn("supplied Capability contracts", ollama.prompts[1][0])
        self.assertNotIn("walking is not running", ollama.prompts[1][0])

    def test_embodied_coverage_review_rejects_walk_step_as_fetch_and_return(self):
        goal_ids = ["goal-distance", "goal-water", "goal-return"]
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Move 50 metres, fetch water, and return.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 50.0},
                    goal_ids,
                    "Use the movement capability for the whole request.",
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(
                    goal_id,
                    ["walk"],
                    "The one movement step covers this responsibility.",
                )
                for goal_id in goal_ids
            },
            goal_satisfaction=exact_satisfaction(goal_ids),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "value": 50.0,
                    "strategy": "user_supplied",
                    "source_goal_ids": ["goal-distance"],
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied the user's number.",
                }
            ],
        )
        run_request = request(
            "你能往前给我跑个50米，帮我拿杯水，然后回来吗？",
            goal_ids=goal_ids,
        )
        context = dict(run_request.context)
        context["goal_association_resolution"] = {
            "associations": [],
            "new_goals": [
                {
                    "goal_id": "goal-distance",
                    "description": "往前移动50米。",
                    "source_text": run_request.text,
                    "object": {
                        "bindings": {
                            "distance": {
                                "name": "distance",
                                "entity_type": "distance",
                                "value": "50米",
                            }
                        }
                    },
                    "metadata": {"responsibility_kind": "executable_action"},
                },
                {
                    "goal_id": "goal-water",
                    "description": "拿一杯水。",
                    "source_text": run_request.text,
                    "object": {"bindings": {}},
                    "metadata": {"responsibility_kind": "executable_action"},
                },
                {
                    "goal_id": "goal-return",
                    "description": "返回用户身边。",
                    "source_text": run_request.text,
                    "object": {"bindings": {}},
                    "metadata": {"responsibility_kind": "executable_action"},
                },
            ],
        }
        ollama = ScriptedOllama(
            [
                raw,
                {
                    "decision": "reject",
                    "confidence": 1.0,
                    "uncovered_requirements": [
                        "exact 50-metre distance",
                        "fetching water",
                        "returning",
                    ],
                    "reason": (
                        "walk_forward is duration-based movement and does not "
                        "implement distance measurement, object pickup, or return."
                    ),
                },
            ]
        )

        resolved = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                run_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(resolved.disposition, "escalate")
        self.assertEqual(resolved.steps, [])
        self.assertEqual(
            resolved.escalation_reason,
            "coordinated_action_coverage_incomplete",
        )
        self.assertEqual(
            resolved.unresolved,
            ["exact 50-metre distance", "fetching water", "returning"],
        )
        review_prompt = ollama.prompts[1][0]
        self.assertIn("ordinary world knowledge", review_prompt)
        self.assertIn("supplied Capability contracts", review_prompt)
        self.assertIn("Do not infer undeclared effects", review_prompt)
        self.assertNotIn("object acquisition", review_prompt)
        self.assertNotIn("walking is not running", review_prompt)

    def test_parallel_plan_without_declared_provider_support_escalates(self):
        goal_ids = ["goal-walk", "goal-blink"]
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk while blinking.",
            steps=[
                {
                    **execute_step(
                        "walk",
                        "soridormi.walk_forward",
                        {"duration_s": 15.0},
                        ["goal-walk"],
                        "Walk for 15 seconds.",
                    ),
                    "timing": "parallel",
                },
                {
                    **execute_step(
                        "blink",
                        "soridormi.blink_eyes",
                        {"count": 2},
                        ["goal-blink"],
                        "Blink twice.",
                    ),
                    "timing": "parallel",
                },
            ],
            goal_outcomes={
                "goal-walk": execute_outcome("goal-walk", ["walk"], "Walk."),
                "goal-blink": execute_outcome("goal-blink", ["blink"], "Blink."),
            },
            goal_satisfaction=exact_satisfaction(goal_ids),
        )

        plan = asyncio.run(
            FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(
                request(
                    "Walk for 15 seconds while blinking.",
                    goal_ids=goal_ids,
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(
            plan.escalation_reason,
            "parallel_execution_contract_unavailable",
        )
        self.assertFalse(plan.metadata["execution_allowed"])
        self.assertEqual(len(plan.metadata["parallel_contract_errors"]), 2)

    def test_multi_goal_fast_schema_requires_complete_model_authored_plan(self):
        raw = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.9,
            goal_summary="Two independent goals.",
            steps=[],
            goal_outcomes={
                "goal-a": escalate_outcome("goal-a", "Goal A needs Deep Planner."),
                "goal-b": escalate_outcome("goal-b", "Goal B needs Deep Planner."),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-a", "goal-b"], "Deep planning is required."
            ),
            escalation_reason="heterogeneous multi-goal request requires deep planning",
            unresolved=["goal-a", "goal-b"],
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Handle both requested goals.",
                    goal_ids=["goal-a", "goal-b"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(schema["title"], "FastPlannerMultiGoalPlanOutput")
        self.assertIn("goal_outcomes", schema["required"])
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["required"],
            ["goal-a", "goal-b"],
        )
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["minProperties"], 2
        )
        self.assertIn("mixed", schema["properties"]["disposition"]["enum"])
        self.assertIn(
            "escalate",
            schema["$defs"]["PlannerModelGoalOutcome"]["properties"]
            ["disposition"]["enum"],
        )
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 2)
        goal_a_outcome = schema["properties"]["goal_outcomes"]["properties"][
            "goal-a"
        ]
        goal_a_satisfaction = goal_a_outcome["properties"]["satisfaction"][
            "anyOf"
        ][0]
        self.assertEqual(
            goal_a_satisfaction["properties"]["satisfied_goal_ids"]["items"][
                "enum"
            ],
            ["goal-a"],
        )
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_goal_ids"]["items"][
                "enum"
            ],
            ["goal-a"],
        )
        self.assertEqual(goal_a_outcome["properties"]["step_ids"]["maxItems"], 1)
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_goal_ids"]["maxItems"], 0
        )
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_requirements"]["maxItems"],
            0,
        )
        self.assertEqual(
            schema["properties"]["goal_satisfaction"]["anyOf"][0][
                "properties"
            ]["satisfied_goal_ids"]["minItems"],
            2,
        )
        self.assertLess(
            list(schema["properties"]).index("goal_outcomes"),
            list(schema["properties"]).index("steps"),
        )
        self.assertLess(
            list(schema["properties"]).index("goal_outcomes"),
            list(schema["properties"]).index("disposition"),
        )
        aggregate_branches = schema["allOf"][0]["anyOf"]
        mixed_branches = [
            branch
            for branch in aggregate_branches
            if branch["properties"]["disposition"]["enum"] == ["mixed"]
        ]
        self.assertEqual(len(mixed_branches), 2)
        self.assertTrue(
            all(
                branch["properties"]["steps"]["maxItems"] == 1
                for branch in mixed_branches
            )
        )
        self.assertEqual(
            set(schema["$defs"]["PlannerModelStep"]["required"]),
            {
                "step_id",
                "capability_id",
                "args",
                "timing",
                "source_goal_ids",
                "reason_summary",
            },
        )
        self.assertEqual(schema["properties"]["goal_summary"]["maxLength"], 240)
        self.assertEqual(
            schema["$defs"]["PlannerModelStep"]["properties"]
            ["reason_summary"]["maxLength"],
            160,
        )
        self.assertEqual(
            schema["$defs"]["PlannerModelGoalOutcome"]["properties"]
            ["rationale"]["maxLength"],
            200,
        )
        self.assertEqual(
            schema["$defs"]["PlannerGoalSatisfaction"]["properties"]
            ["rationale"]["maxLength"],
            200,
        )
        self.assertNotIn(
            "source_ref",
            schema["$defs"]["PlanParameterResolution"]["properties"],
        )
        self.assertEqual(
            set(schema["$defs"]["PlanParameterResolution"]["required"]),
            {
                "step_id",
                "parameter",
                "strategy",
                "value",
                "confidence",
                "blocking",
                "rationale",
                "source_goal_ids",
            },
        )
        self.assertIn("one short sentence each", ollama.prompts[0][0])

    def test_explicit_numeric_grounding_mismatch_escalates_without_same_tier_repair(self):
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk for two seconds and blink.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-walk"],
                    "Walk forward.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 1},
                    ["goal-blink"],
                    "Blink once.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk is covered."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "The blink is covered."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"]
            ),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 1.0,
                    "confidence": 0.99,
                    "blocking": False,
                    "rationale": "Copied from the goal.",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        repaired = {
            **invalid,
            "steps": [
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk forward.",
                ),
                invalid["steps"][1],
            ],
            "parameter_resolutions": [
                {
                    **invalid["parameter_resolutions"][0],
                    "value": "2.0",
                }
            ],
        }
        ollama = ScriptedOllama([invalid, repaired])
        run_request = request(
            "Walk forward for 2 seconds, then blink.",
            goal_ids=["goal-walk", "goal-blink"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(run_request)
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.metadata["path_classification"], "contract_failure")
        self.assertEqual(plan.escalation_reason, "fast_planner_authoritative_grounding_failed")
        self.assertIn(
            "explicit numeric goal value has no matching user_supplied",
            plan.metadata["error"],
        )

    def test_numeric_grounding_accepts_stable_source_goal_provenance(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk forward for two seconds.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk forward for the requested duration.",
                )
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk is covered."
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-walk"]),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 2.0,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied from the authoritative goal.",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        ollama = FakeOllama(raw)
        run_request = request(
            "Walk forward for 2 seconds.",
            goal_ids=["goal-walk"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(run_request)
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].args["duration_s"], 2.0)
        self.assertEqual(len(ollama.prompts), 1)

    def test_exact_velocity_and_duration_use_goal_ids_without_text_copy(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk at the requested velocity and duration.",
            steps=[
                execute_step(
                    "soridormi.walk_velocity",
                    "soridormi.walk_velocity",
                    {
                        "vx_mps": 0.2,
                        "vy_mps": 0.0,
                        "yaw_radps": 0.0,
                        "duration_s": 20.000000000000004,
                    },
                    ["goal-walk"],
                    "Use the exact requested speed and duration.",
                )
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk",
                    ["soridormi.walk_velocity"],
                    "The exact movement is covered.",
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-walk"]),
            parameter_resolutions=[
                {
                    "step_id": "soridormi.walk_velocity",
                    "parameter": "vx_mps",
                    "strategy": "user_supplied",
                    "value": 0.2,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "The Goal supplies the velocity.",
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "soridormi.walk_velocity",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 20.0,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "The Goal supplies the duration.",
                    "source_goal_ids": ["goal-walk"],
                },
            ],
        )
        ollama = FakeOllama(raw)
        run_request = request(
            "Walk forward at 0.2 meters per second for 20 seconds.",
            goal_ids=["goal-walk"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward at 0.2 meters per second for 20 seconds."

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(run_request)
        )

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].capability_id, "soridormi.walk_velocity")
        self.assertEqual(plan.steps[0].args["vx_mps"], 0.2)
        self.assertEqual(plan.steps[0].args["duration_s"], 20.000000000000004)
        self.assertEqual(len(ollama.prompts), 1)
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertNotIn(
            "source_ref",
            response_schema["$defs"]["PlanParameterResolution"]["properties"],
        )

    def test_numeric_grounding_rejects_wrong_source_goal(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk forward for two seconds.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk forward for the requested duration.",
                )
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk is covered."
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-walk"]),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 2.0,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied from the authoritative goal.",
                    "source_goal_ids": ["goal-other"],
                }
            ],
        )
        run_request = request(
            "Walk forward for 2 seconds.",
            goal_ids=["goal-walk"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw),
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve(run_request)
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertIn(
            "parameter resolution references unknown goal IDs",
            plan.metadata["error"],
        )

    def test_dotted_step_id_is_unambiguous_in_parameter_repair_feedback(self):
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk forward for two seconds.",
            steps=[
                {
                    **execute_step(
                        "soridormi.walk_velocity",
                        "soridormi.walk_forward",
                        {"duration_s": 2.0},
                        ["goal-walk"],
                        "Walk forward for the requested duration.",
                    ),
                    "timing": "sequential",
                }
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk",
                    ["soridormi.walk_velocity"],
                    "The walk is covered.",
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-walk"]),
            parameter_resolutions=[
                {
                    "step_id": "soridormi.walk_velocity",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": "2 seconds",
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied from the authoritative goal.",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        repaired = {
            **invalid,
            "parameter_resolutions": [
                {
                    **invalid["parameter_resolutions"][0],
                    "value": 2.0,
                }
            ],
        }
        ollama = ScriptedOllama([invalid, repaired])
        run_request = request(
            "Walk forward for 2 seconds.",
            goal_ids=["goal-walk"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(run_request)
        )

        repair_prompt = ollama.prompts[1][0]
        self.assertEqual(plan.disposition, "execute")
        self.assertIn(
            "step_id='soridormi.walk_velocity', parameter='duration_s'",
            repair_prompt,
        )
        self.assertNotIn(
            "soridormi.walk_velocity.duration_s",
            repair_prompt,
        )

    def test_verified_result_repair_keeps_bindings_nested_in_material_args(self):
        catalog = FakeCatalog()
        catalog.items.append(
            CatalogCapability(
                capability_id="chromie.memory.retrieve_verified_tool_result",
                agent_id="chromie.memory",
                description="Retrieve one exact verified tool result.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "evidence_id": {"type": "string"},
                        "tool_id": {"type": "string"},
                        "material_args": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["evidence_id", "tool_id", "material_args"],
                    "additionalProperties": False,
                },
                route="tool",
                available=True,
                interaction_executable=True,
                prompt_tier="common",
            )
        )
        step = execute_step(
            "retrieve-weather",
            "chromie.memory.retrieve_verified_tool_result",
            {
                "evidence_id": "evidence-weather",
                "tool_id": "chromie.weather.lookup",
                "material_args": {"location": "河南省内乡县", "date": "today"},
            },
            ["goal-weather"],
            "Retrieve the exact prior weather result.",
        )
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Retrieve the prior weather result.",
            steps=[step],
            goal_outcomes={
                "goal-weather": execute_outcome(
                    "goal-weather",
                    ["retrieve-weather"],
                    "The exact result is retrievable.",
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-weather"]),
            parameter_resolutions=[
                {
                    "step_id": "retrieve-weather",
                    "parameter": "location",
                    "strategy": "observed_context",
                    "value": "河南省内乡县",
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Resolved by Goal Association.",
                    "source_goal_ids": ["goal-weather"],
                }
            ],
        )
        repaired = {**invalid, "parameter_resolutions": []}
        ollama = ScriptedOllama([invalid, repaired])
        run_request = request(
            "刚才那个天气结果，简单告诉我现在有没有下雨。",
            route="tool",
            goal_ids=["goal-weather"],
        )
        goal = run_request.context["goal_association_resolution"]["new_goals"][0]
        goal["object"] = {
            "bindings": {
                "location": {"value": "河南省内乡县"},
                "date": {"value": "today"},
            }
        }
        run_request.context["verified_tool_memory_index"] = [
            {
                "evidence_id": "evidence-weather",
                "tool_id": "chromie.weather.lookup",
                "request_args": {"location": "河南省内乡县", "date": "today"},
                "goal_ids": ["goal-weather"],
            }
        ]

        plan = asyncio.run(FastPlannerResolver(ollama, catalog).resolve(run_request))

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].args["material_args"]["location"], "河南省内乡县")
        self.assertEqual(plan.parameter_resolutions, [])
        self.assertIn(
            "do not emit separate location or date parameter_resolutions",
            ollama.prompts[1][0],
        )

    def test_single_parallel_labeled_step_requires_provider_parallel_metadata(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk forward.",
            response_text="好，我知道啦，我先看看怎么安排。",
            steps=[
                {
                    **execute_step(
                        "walk",
                        "soridormi.walk_forward",
                        {"duration_s": 2.0},
                        ["goal-walk"],
                        "Walk forward.",
                    ),
                    "timing": "parallel",
                }
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk is covered."
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-walk"]),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 2.0,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Copied from the authoritative goal.",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        run_request = request(
            "Walk forward for 2 seconds.",
            goal_ids=["goal-walk"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(
                run_request
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.escalation_reason, "parallel_execution_contract_unavailable")
        self.assertEqual(plan.response_text, "好，我知道啦，我先看看怎么安排。")
        self.assertEqual(
            plan.metadata["retained_progress_response_text"]["status"],
            "undelivered_advisory",
        )
        self.assertEqual(
            plan.metadata["parallel_contract_errors"][0]["type"],
            "parallel_capability_not_declared_safe",
        )
        self.assertEqual(
            plan.metadata["parallel_contract_errors"][0]["parallel_step_count"],
            1,
        )

    def test_multi_goal_fast_execute_terminates_without_repair(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            confidence=0.97,
            goal_summary="Execute two ordered physical goals.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-walk"],
                    "Execute the first physical goal.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-blink"],
                    "Execute the second physical goal.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk step covers this goal."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "The blink step covers this goal."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"],
                "Both physical goals are fully planned.",
            ),
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk forward for one second, then blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.planner_tier, "fast")
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual([step.step_id for step in plan.steps], ["walk", "blink"])
        self.assertTrue(plan.metadata["model_authored_steps"])
        self.assertFalse(plan.metadata["host_semantic_compilation"])
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        self.assertEqual(len(ollama.prompts), 1)

    def test_multi_goal_fast_mixed_terminates_without_deep_planning(self):
        raw = multi_goal_plan(
            disposition="mixed",
            coverage="complete",
            confidence=0.98,
            goal_summary="Execute one goal and answer another.",
            response_text="A concise model-authored answer.",
            steps=[
                execute_step(
                    "physical-step",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-action"],
                    "Execute the physical goal exactly.",
                )
            ],
            goal_outcomes={
                "goal-action": execute_outcome(
                    "goal-action",
                    ["physical-step"],
                    "The physical step covers the action goal.",
                ),
                "goal-answer": respond_outcome(
                    "goal-answer",
                    "A concise model-authored answer.",
                    "Answer the conversational goal directly.",
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-action", "goal-answer"],
                "Both goals are fully planned.",
            ),
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Complete the physical goal and answer the other goal.",
                    goal_ids=["goal-action", "goal-answer"],
                )
            )
        )

        self.assertEqual(plan.planner_tier, "fast")
        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(
            plan.goal_outcomes[1].response_text,
            "A concise model-authored answer.",
        )
        self.assertEqual(plan.steps[0].step_id, "physical-step")
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        self.assertEqual(len(ollama.prompts), 1)

    def test_mixed_aggregate_repair_is_constrained_by_model_authored_outcomes(self):
        initial = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Execute one goal and answer another.",
            response_text="A concise model-authored answer.",
            steps=[
                execute_step(
                    "physical-step",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-action"],
                    "Execute the physical goal exactly.",
                )
            ],
            goal_outcomes={
                "goal-action": execute_outcome(
                    "goal-action", ["physical-step"], "Physical goal plan."
                ),
                "goal-answer": respond_outcome(
                    "goal-answer", "A concise answer.", "Answer goal plan."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-action", "goal-answer"]
            ),
        )
        ollama = ScriptedOllama([initial])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Complete both abstract goals.",
                    goal_ids=["goal-action", "goal-answer"],
                )
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertNotIn("contract_repair_succeeded", plan.metadata)
        first_schema = ollama.prompts[0][1]["response_format"]
        self.assertIn("execute", first_schema["properties"]["disposition"]["enum"])

    def test_low_confidence_complete_claim_is_forced_to_escalate(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.51,"goal_ids":["goal-blink"],"steps":[{"capability_id":"soridormi.blink_eyes","args":{"count":3}}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog(), min_confidence=0.8).resolve(request("眨眼。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])

    def test_non_common_or_non_executable_skill_escalates(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.95,"goal_ids":["goal-action"],"steps":[{"step_id":"invented","capability_id":"invented.skill","args":{},"source_goal_ids":["goal-action"]}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("做点什么。", goal_ids=["goal-action"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.escalation_reason, "step_not_in_executable_common_catalog")

    def test_prompt_defines_complete_coverage_not_skill_matching(self):
        ollama = FakeOllama(
            multi_goal_plan(
                disposition="respond",
                coverage="complete",
                goal_summary="greet",
                response_text="你好。",
                steps=[],
                goal_outcomes={
                    "goal-greet": respond_outcome("goal-greet", "你好。", "Direct greeting.")
                },
                goal_satisfaction=exact_satisfaction(["goal-greet"]),
            )
        )
        planner_request = request("你好。", route="chat", goal_ids=["goal-greet"], goal_metadata={"responsibility_kind": "vocal_output", "output_mode": "speech", "provider_required": False})
        context = dict(planner_request.context)
        context["history"] = [
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
        planner_request = planner_request.model_copy(update={"context": context})
        asyncio.run(FastPlannerResolver(ollama, FakeCatalog()).resolve(planner_request))
        prompt = ollama.prompts[0][0]
        self.assertIn("Finding one matching capability is not complete coverage", prompt)
        self.assertIn("zero steps", prompt)
        self.assertIn("Delivered evidence-bound dialogue JSON", prompt)
        self.assertIn("北京现在约28℃", prompt)
        system = ollama.prompts[0][1]["system"]
        self.assertIn("verified-memory index is provenance only", system)
        self.assertIn("preserve every measurement and condition exactly", system)

    def test_prompt_keeps_latest_social_reaction_above_retained_weather_answer(self):
        ollama = FakeOllama({
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "response_text": "嗯，那就快走吧，记得带伞。",
            "steps": [],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-reaction"],
            },
        })
        planner_request = request(
            "是得赶紧走啊。",
            route="chat",
            goal_ids=["goal-reaction"],
        )
        context = dict(planner_request.context)
        context["history"] = [
            {
                "role": "assistant",
                "text": "重庆现在有雷雨伴随冰雹的预报。",
                "metadata": {"evidence_bound": True},
            }
        ]
        planner_request = planner_request.model_copy(update={"context": context})

        asyncio.run(FastPlannerResolver(ollama, FakeCatalog()).resolve(planner_request))

        prompt = ollama.prompts[0][0]
        self.assertIn("FINAL AUTHORITATIVE USER TURN owns the current communicative act", prompt)
        self.assertIn("must not replace what the person just meant", prompt)
        self.assertIn("Do not replay the previous task answer", prompt)
        self.assertIn("first sentence directly state the requested decision", prompt)
        self.assertIn("never begin by restating prior evidence", prompt)
        self.assertIn("at most one short supporting clause", prompt)

    def test_retained_evidence_followup_gets_bounded_decision_first_review(self):
        goal_id = "goal-weather"
        evidence_first = "重庆今天有雷雨和冰雹，而且降雨概率很大。所以需要带伞。"
        decision_first = "需要带伞，因为重庆今天有雷雨和冰雹。"
        primary = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Decide whether an umbrella is needed.",
            "response_text": evidence_first,
            "steps": [],
            "goal_outcomes": {
                goal_id: {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": evidence_first,
                    "unresolved": [],
                    "step_ids": [],
                    "satisfaction": exact_satisfaction([goal_id]),
                    "rationale": "The retained weather result supports the decision.",
                }
            },
            "goal_satisfaction": exact_satisfaction([goal_id]),
        }
        review = {
            "decision": "revise",
            "confidence": 1.0,
            "response_text": decision_first,
            "goal_responses": [
                {"goal_id": goal_id, "response_text": decision_first}
            ],
            "reason": "The original response replayed evidence before answering the decision.",
        }
        ollama = ScriptedOllama([primary])
        reviewer = ScriptedOllama([review])
        planner_request = request(
            "那我出门需要带伞吗？",
            route="chat",
            goal_ids=[],
        )
        context = dict(planner_request.context)
        context["goal_association_resolution"] = {
            "associations": [
                {
                    "association_id": "association-weather-followup",
                    "relationship": "continue",
                    "target_goal_ids": [goal_id],
                    "confidence": 1.0,
                    "reason_summary": "The latest turn asks for a practical decision from the retained result.",
                    "goal_update": {
                        "description": "Decide whether the person needs an umbrella."
                    },
                }
            ],
            "new_goals": [],
        }
        context["recent_goal_snapshots"] = [
            {
                "goal_id": goal_id,
                "goal": {
                    "description": "Check today's weather in Chongqing.",
                    "source_text": "重庆今天会下雨吗？",
                },
            }
        ]
        context["history"] = [
            {
                "role": "assistant",
                "text": "重庆今天有雷雨和冰雹，而且降雨概率很大。",
                "metadata": {
                    "source": "evidence_bound_tool_result_interpretation",
                    "evidence_bound": True,
                    "source_goal_ids": [goal_id],
                    "canonical_plan_id": "plan-weather",
                },
            }
        ]

        plan = asyncio.run(
            FastPlannerResolver(
                ollama,
                FakeCatalog(),
                communication_reviewer=reviewer,
            ).resolve(
                planner_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.response_text, decision_first)
        self.assertEqual(plan.goal_outcomes[0].response_text, decision_first)
        self.assertEqual(plan.metadata["communication_review"]["status"], "revised")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(len(reviewer.prompts), 1)
        review_prompt, review_options = reviewer.prompts[0]
        self.assertIn("communicative act directly", review_prompt)
        self.assertIn("delivered_evidence_bound_dialogue", review_prompt)
        self.assertEqual(
            review_options["prompt_family"],
            "fast_planner.communication_review",
        )
        review_schema = review_options["response_format"]
        self.assertNotIn(
            "minLength",
            review_schema["properties"]["response_text"],
        )
        self.assertNotIn(
            "minLength",
            review_schema["$defs"]["PlannerCommunicationGoalResponse"][
                "properties"
            ]["response_text"],
        )

    def test_retained_evidence_review_failure_escalates_without_effects(self):
        primary, planner_request = retained_weather_followup_fixture()

        plan = asyncio.run(
            FastPlannerResolver(
                ScriptedOllama([primary]),
                FakeCatalog(),
                communication_reviewer=ScriptedOllama(
                    [RuntimeError("review service unavailable")]
                ),
            ).resolve(planner_request)
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertEqual(
            plan.escalation_reason,
            "followup_communication_review_unavailable",
        )
        self.assertEqual(plan.unresolved, ["latest_communicative_act_unreviewed"])
        self.assertFalse(plan.metadata["execution_allowed"])
        self.assertEqual(plan.metadata["path_classification"], "coverage_review_failure")

    def test_multi_goal_prompt_preserves_explicit_in_range_arguments(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Two exact actions.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk for the supplied duration.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-blink"],
                    "Blink the supplied count.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "Walk goal covered."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "Blink goal covered."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"]
            ),
        )
        ollama = FakeOllama(raw)

        asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk for 2 seconds and blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        prompt = ollama.prompts[0][0]
        self.assertIn("copy it exactly", prompt)
        self.assertIn("never silently replace it with a schema default", prompt)
        self.assertIn("Catalog defaults are only for parameters", prompt)
        self.assertIn("A material adjustment must use a non-exact plan_relation", prompt)

    def test_uses_dynamic_schema_for_goal_and_capability_ids(self):
        ollama = FakeOllama({
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink"],
            },
        })

        asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("blink twice", goal_ids=["goal-blink"])
            )
        )

        schema = ollama.prompts[0][1]["response_format"]
        self.assertIsInstance(schema, dict)
        self.assertEqual(schema["title"], "FastPlannerModelOutput")
        self.assertNotIn("oneOf", schema)
        self.assertNotIn("planner_tier", schema["properties"])
        self.assertNotIn("goal_ids", schema["properties"])
        self.assertIn("confidence", schema["required"])
        self.assertIn("goal_satisfaction", schema["required"])
        step_schema = schema["$defs"]["PlannerModelStep"]
        self.assertIn("source_goal_ids", step_schema["required"])
        self.assertEqual(
            step_schema["properties"]["capability_id"]["enum"],
            [
                "soridormi.blink_eyes",
                "soridormi.walk_forward",
                "soridormi.walk_velocity",
            ],
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("FINAL AUTHORITATIVE USER TURN", prompt)
        self.assertIn("FINAL CANONICAL GOALS JSON", prompt)
        self.assertNotIn(
            "chromie.speak",
            step_schema["properties"]["capability_id"]["enum"],
        )

    def test_response_transport_step_is_repaired_to_conversational_response(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "steps": [{
                "step_id": "say",
                "capability_id": "chromie.speak",
                "args": {"text": "A short joke."},
                "source_goal_ids": ["goal-joke"],
            }],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = multi_goal_plan(
            disposition="respond",
            coverage="complete",
            goal_summary="Tell a short joke.",
            response_text="A short joke.",
            steps=[],
            goal_outcomes={
                "goal-joke": respond_outcome(
                    "goal-joke", "A short joke.", "Direct conversational response."
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-joke"]),
        )
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("Tell me a short joke.", route="chat", goal_ids=["goal-joke"], goal_metadata={"responsibility_kind": "vocal_output", "output_mode": "speech", "provider_required": False})
            )
        )

        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.steps, [])
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("generic response transport", ollama.prompts[1][0])

    def test_live_branch_minimal_escalation_repairs_under_flat_contract(self):
        branch_minimal = {
            "planner_tier": "fast",
            "disposition": "escalate",
            "coverage": "partial",
            "steps": [],
            "escalation_reason": "compound request requires deep planning",
        }
        repaired = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.9,
            goal_summary="Two goals require Deep Planner.",
            steps=[],
            goal_outcomes={
                "goal-walk": escalate_outcome(
                    "goal-walk", "The first goal requires deeper planning."
                ),
                "goal-blink": escalate_outcome(
                    "goal-blink", "The second goal requires deeper planning."
                ),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-walk", "goal-blink"],
                "The Fast Planner cannot safely complete the plan.",
            ),
            escalation_reason="compound request requires deep planning",
            unresolved=["goal-walk", "goal-blink"],
        )
        ollama = ScriptedOllama([branch_minimal, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk forward, then blink.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.goal_ids, ["goal-walk", "goal-blink"])
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        schema = ollama.prompts[0][1]["response_format"]
        self.assertNotIn("oneOf", schema)
        self.assertEqual(schema["title"], "FastPlannerMultiGoalPlanOutput")
        self.assertEqual(ollama.prompts[1][1]["response_format"], schema)
        repair_prompt = ollama.prompts[1][0]
        self.assertGreater(
            repair_prompt.index("FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON"),
            repair_prompt.index("FINAL CANONICAL GOALS JSON"),
        )

    def test_same_user_text_follows_different_model_authored_plans(self):
        """The host must not map words in the utterance to fixed actions."""

        text = "Carry out both abstract goals."
        first = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="First model-authored plan.",
            steps=[
                execute_step(
                    "s1",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-a"],
                    "Model selected walking for goal A.",
                ),
                execute_step(
                    "s2",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-b"],
                    "Model selected blinking for goal B.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["s1"], "Goal A plan."),
                "goal-b": execute_outcome("goal-b", ["s2"], "Goal B plan."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )
        second = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Second model-authored plan.",
            steps=[
                execute_step(
                    "s1-alt",
                    "soridormi.blink_eyes",
                    {"count": 1},
                    ["goal-a"],
                    "Model selected blinking for goal A.",
                ),
                execute_step(
                    "s2-alt",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-b"],
                    "Model selected walking for goal B.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["s1-alt"], "Goal A plan."),
                "goal-b": execute_outcome("goal-b", ["s2-alt"], "Goal B plan."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )

        request_value = request(text, goal_ids=["goal-a", "goal-b"])
        plan_one = asyncio.run(
            FastPlannerResolver(FakeOllama(first), FakeCatalog()).resolve(
                request_value
            )
        )
        plan_two = asyncio.run(
            FastPlannerResolver(FakeOllama(second), FakeCatalog()).resolve(
                request_value
            )
        )

        self.assertEqual(
            [step.capability_id for step in plan_one.steps],
            ["soridormi.walk_forward", "soridormi.blink_eyes"],
        )
        self.assertEqual(
            [step.capability_id for step in plan_two.steps],
            ["soridormi.blink_eyes", "soridormi.walk_forward"],
        )
        self.assertNotEqual(
            [step.step_id for step in plan_one.steps],
            [step.step_id for step in plan_two.steps],
        )

    def test_multi_goal_host_does_not_generate_missing_step_ids(self):
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Invalid plan missing a model-authored step ID.",
            steps=[
                {
                    "step_id": "",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-a"],
                    "reason_summary": "Missing identifier must not be repaired locally.",
                },
                execute_step(
                    "valid-b",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-b"],
                    "Valid second step.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["missing"], "Invalid link."),
                "goal-b": execute_outcome("goal-b", ["valid-b"], "Valid link."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )
        ollama = FakeOllama(invalid)
        plan = asyncio.run(
            FastPlannerResolver(
                ollama,
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve(request("Abstract request.", goal_ids=["goal-a", "goal-b"]))
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.metadata["path_classification"], "contract_failure")
        self.assertEqual(plan.steps, [])

    def test_legacy_step_shape_requires_one_model_revision_without_local_mapping(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "capability_id": "soridormi.blink_eyes",
                "parameters": {"count": 2},
            }],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink"],
            },
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("blink twice", goal_ids=["goal-blink"])
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(plan.steps[0].capability_id, "soridormi.blink_eyes")
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn("capability_id", ollama.prompts[1][0])
        self.assertIn("extra_forbidden", ollama.prompts[1][0])

    def test_model_failure_escalates_safely(self):
        plan = asyncio.run(FastPlannerResolver(FakeOllama(RuntimeError("offline")), FakeCatalog()).resolve(request("眨眼。")))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.metadata["status"], "escalate")
        self.assertEqual(plan.metadata["path_classification"], "contract_failure")


class OrchestratorFastPlannerTests(unittest.TestCase):
    def test_report_only_schedules_without_changing_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        class Client:
            async def resolve_fast_plan(self, *args, **kwargs):
                return CanonicalPlan(plan_id="p", planner_tier="fast", disposition="respond", coverage="complete", confidence=0.9, response_text="hi")

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_mode = "report_only"
            assistant.fast_planner_timeout_ms = 1000
            assistant.enable_agent = True
            assistant.agent_client = Client()
            assistant.fast_planner_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None
            decision = ODecision(route="chat", intent="conversation", confidence=0.8, source="llm")
            reviewed = assistant._schedule_fast_planner_report(object(), user_text="hello", session_id="sid", context={"history":[]}, decision=decision)
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(reviewed.metadata["fast_planner_resolution"]["status"], "scheduled")
            await asyncio.gather(*list(assistant.fast_planner_report_tasks))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
