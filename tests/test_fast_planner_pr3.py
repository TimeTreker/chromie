from __future__ import annotations

from agent.app import planner_schema
from agent.app import planner_prompt as planner_prompt

import asyncio
import copy
import json
import unittest

from pydantic import ValidationError

from agent.app.fast_planner import FastPlannerResolver
from agent.app import planner_fast_validation
from agent.app.planner_model_contract import (
    PlannerCoverageReview,
    PlannerDTOContractError,
    PlannerModelOutput,
    is_planner_step_capability,
)
from agent.app.planner_schema import canonical_goal_binding_argument_response_schema
from agent.app.planner_context import goal_association_prompt_projection
from agent.app.planner_validation import (
    normalize_common_planner_output,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from agent.app.capabilities.catalog import CatalogCapability
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerAdvanceModelOutput,
    FastPlannerClarificationAct,
    FastPlannerCompleteResponseAct,
    FastPlannerProgressAct,
)
from shared.chromie_contracts.tool_result import canonical_value_sha256
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


def _truth_certificate(
    decision: str = "accept", **violations: bool
) -> dict[str, object]:
    certificate: dict[str, object] = {
        "has_unverified_result_or_completion_claim": False,
        "has_ungrounded_method_or_world_claim": False,
        "has_semantic_perspective_contradiction": False,
        "has_epistemic_strength_contradiction": False,
        "has_execution_status_contradiction": False,
        "has_out_of_scope_goal_claim": False,
        "decision": decision,
    }
    certificate.update(violations)
    return certificate


class FakeCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(capability_id="soridormi.blink_eyes", agent_id="capability_agent", description="Blink eyes", input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]}, effects=["physical_motion"], available=True, interaction_executable=True, prompt_tier="common", can_run_parallel=True, parallel_metadata_declared=True, exclusive_group="body.face", resource_claims=["body.face"]),
            CatalogCapability(capability_id="soridormi.walk_forward", agent_id="capability_agent", description="Walk forward", input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]}, effects=["physical_motion"], available=True, interaction_executable=True, prompt_tier="common", can_run_parallel=True, parallel_metadata_declared=True, exclusive_group="body.primary_motion", resource_claims=["body.primary_motion"]),
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
                effects=["physical_motion"],
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                can_run_parallel=True,
                parallel_metadata_declared=True,
                exclusive_group="body.primary_motion",
                resource_claims=["body.primary_motion"],
            ),
            CatalogCapability(capability_id="chromie.speak", agent_id="capability_agent", description="Speak text", input_schema={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}, available=True, interaction_executable=True, prompt_tier="common"),
        ]

    async def prompt_entries(self, **kwargs):
        return self.items


class MissingParallelMetadataCatalog(FakeCatalog):
    def __init__(self):
        super().__init__()
        self.items = [
            item.model_copy(
                update={
                    "can_run_parallel": None,
                    "parallel_metadata_declared": False,
                    "exclusive_group": None,
                    "resource_claims": [],
                }
            )
            if item.capability_id.startswith("soridormi.")
            else item
            for item in self.items
        ]


class WeatherCatalog(FakeCatalog):
    def __init__(self):
        super().__init__()
        self.items.append(
            CatalogCapability(
                capability_id="chromie.weather.lookup",
                agent_id="chromie.weather",
                description="Retrieve current or short-range weather.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string", "default": "today"},
                        "period": {
                            "type": "string",
                            "default": "day",
                            "x-chromie-entity-type": "day_part",
                        },
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                can_run_parallel=True,
                parallel_metadata_declared=True,
                resource_claims=(),
                effects=(),
                safety_class="safe_read",
                hints={
                    "side_effect_free": True,
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                    },
                },
            )
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
                effects=["physical_motion"],
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



def _test_what_mode(text: str, *, goal_metadata: dict | None = None) -> str:
    configured = str((goal_metadata or {}).get("output_mode") or "").strip()
    if configured:
        return configured
    lowered = str(text or "").casefold()
    if any(token in lowered for token in ("weather", "天气", "下雨", "rain", "temperature", "温度", "check", "determine whether")):
        return "information"
    if any(token in lowered for token in ("hello", "你好", "greet", "joke", "笑话", "feel", "feeling", "tired", "累")):
        return "speech"
    return "body_action"


def _work_request(**kwargs):
    context = dict(kwargs.pop("context", {}) or {})
    responsibilities = kwargs.pop("responsibilities", None)
    if responsibilities is None:
        responsibilities = context.pop("responsibility_proposals", None)
    if not responsibilities:
        text = str(kwargs.get("text") or "")
        responsibilities = [
            {
                "local_ref": "r1",
                "outcome": text or "satisfy the current user outcome",
                "bindings": {},
                "output_mode": _test_what_mode(text),
                "confidence": 0.9,
            }
        ]
    normalized_responsibilities = []
    for item in responsibilities:
        payload = dict(item) if isinstance(item, dict) else item.model_dump(mode="json")
        payload.setdefault("output_mode", _test_what_mode(str(payload.get("outcome") or kwargs.get("text") or "")))
        normalized_responsibilities.append(payload)
    return CognitiveWorkRequest(
        **kwargs,
        responsibilities=normalized_responsibilities,
        interpretation_confidence=0.9,
        context=context,
    )

def request(text: str, *, goal_ids=None, goal_metadata=None):
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
    return CognitiveWorkRequest(
        sid="sid-pr3",
        text=text,
        language="zh-CN",
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": text,
                "bindings": {},
                "output_mode": _test_what_mode(text, goal_metadata=goal_metadata),
                "confidence": 0.9,
            }
        ],
        interpretation_confidence=0.9,
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


def retained_weather_followup_fixture() -> tuple[dict, CognitiveWorkRequest]:
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
    def vocal_goal(*, output_mode: str) -> list[dict]:
        return [
            {
                "goal_id": "goal-vocal",
                "description": "Perform the requested vocal output.",
                "metadata": {"output_mode": output_mode},
            }
        ]

    def test_planner_projection_preserves_typed_vocal_metadata(self):
        projection = goal_association_prompt_projection(
            {
                "goal_association_resolution": {
                    "new_goals": self.vocal_goal(
                        output_mode="singing",
                    )
                }
            }
        )

        self.assertEqual(
            projection["new_goals"][0]["metadata"],
            {"output_mode": "singing"},
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
                ),
            )

    def test_singing_goal_can_report_exact_unavailability(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "unavailable",
                "coverage": "uncertain",
                "confidence": 1.0,
                "response_text": "I can't sing right now.",
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
            ),
        )


class CanonicalPlanContractTests(unittest.TestCase):
    def test_coverage_review_cannot_accept_a_reported_semantic_mismatch(self):
        with self.assertRaisesRegex(
            ValidationError,
            "accepted coverage cannot report a semantic mismatch",
        ):
            PlannerCoverageReview.model_validate(
                {
                    "decision": "accept",
                    "confidence": 1.0,
                    "semantic_mismatch_found": True,
                    "uncovered_requirements": [],
                    "reason": "The selected effect is only an approximation.",
                }
            )

        schema = planner_schema.planner_coverage_review_response_schema()
        self.assertIn("semantic_mismatch_found", schema["required"])
        accepted_branch = schema["allOf"][-1]["anyOf"][0]["properties"]
        self.assertFalse(accepted_branch["semantic_mismatch_found"]["const"])

    def test_single_goal_fast_escalation_uses_advertised_per_goal_contract(self):
        goal_id = "goal-weather"
        raw = multi_goal_plan(
            disposition="escalate",
            coverage="partial",
            confidence=0.9,
            goal_summary="Fresh weather evidence requires deeper planning.",
            steps=[],
            goal_outcomes={
                goal_id: escalate_outcome(
                    goal_id, "Fresh provider evidence is still required."
                )
            },
            goal_satisfaction=unsatisfied_satisfaction(
                [goal_id], "Fresh provider evidence is still required."
            ),
            escalation_reason="fresh provider evidence requires deep planning",
            unresolved=["fresh provider evidence"],
        )

        output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=[goal_id],
        )

        self.assertEqual(output.disposition, "escalate")
        self.assertEqual(set(output.goal_outcomes), {goal_id})
        self.assertEqual(output.goal_satisfaction.status, "unsatisfied")

    def test_stop_remains_a_deterministic_control_not_a_planner_step(self):
        self.assertFalse(is_planner_step_capability("soridormi.stop"))
        self.assertFalse(is_planner_step_capability("chromie.speak"))
        self.assertTrue(is_planner_step_capability("soridormi.walk_forward"))

    def test_typed_capability_scope_uses_goal_value_or_provider_default(self):
        base_schema = {
            "$defs": {
                "PlannerModelStep": {
                    "oneOf": [
                        {
                            "properties": {
                                "args": {
                                    "properties": {
                                        "period": {
                                            "type": "string",
                                            "enum": ["day", "evening", "night"],
                                            "default": "day",
                                            "x-chromie-entity-type": "day_part",
                                        }
                                    },
                                    "required": [],
                                }
                            }
                        }
                    ]
                }
            }
        }
        whole_day_goal = {
            "goal_id": "goal-weather",
            "object": {
                "bindings": {
                    "date": {
                        "entity_type": "date",
                        "value": "tomorrow",
                    }
                }
            },
        }
        whole_day_schema = canonical_goal_binding_argument_response_schema(
            base_schema,
            authoritative_goals=[whole_day_goal],
        )
        whole_day_args = whole_day_schema["$defs"]["PlannerModelStep"]["oneOf"][
            0
        ]["properties"]["args"]
        self.assertEqual(
            whole_day_args["properties"]["period"],
            {"const": "day"},
        )
        self.assertNotIn("period", whole_day_args["required"])

        evening_goal = copy.deepcopy(whole_day_goal)
        evening_goal["object"]["bindings"]["scope"] = {
            "entity_type": "day_part",
            "value": "evening",
        }
        evening_schema = canonical_goal_binding_argument_response_schema(
            base_schema,
            authoritative_goals=[evening_goal],
        )
        evening_args = evening_schema["$defs"]["PlannerModelStep"]["oneOf"][0][
            "properties"
        ]["args"]
        self.assertEqual(
            evening_args["properties"]["period"],
            {"const": "evening"},
        )
        self.assertIn("period", evening_args["required"])

    def test_typed_capability_scope_rejects_invented_narrower_value(self):
        goal_id = "goal-weather"
        output = PlannerModelOutput.model_validate(
            multi_goal_plan(
                disposition="execute",
                coverage="complete",
                goal_summary="Check tomorrow's weather.",
                steps=[
                    execute_step(
                        "weather",
                        "chromie.weather.lookup",
                        {"date": "tomorrow", "period": "night"},
                        [goal_id],
                        "Read the requested forecast.",
                    )
                ],
                goal_outcomes={
                    goal_id: execute_outcome(
                        goal_id,
                        ["weather"],
                        "The weather lookup covers the Goal.",
                    )
                },
                goal_satisfaction=exact_satisfaction([goal_id]),
            )
        )
        authoritative_goals = [
            {
                "goal_id": goal_id,
                "object": {
                    "bindings": {
                        "date": {
                            "entity_type": "date",
                            "value": "tomorrow",
                        }
                    }
                },
            }
        ]
        capabilities = [
            {
                "capability_id": "chromie.weather.lookup",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "period": {
                            "type": "string",
                            "enum": ["day", "evening", "night"],
                            "default": "day",
                            "x-chromie-entity-type": "day_part",
                        },
                    },
                },
            }
        ]

        with self.assertRaisesRegex(
            ValueError,
            "invented unsupported semantic scope",
        ):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=authoritative_goals,
                capabilities=capabilities,
            )

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
                        "metadata": {"output_mode": "body_action"},
                    }
                ],
            )

    def test_effectful_goal_accepts_explicit_unavailability_without_steps(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "unavailable",
                "coverage": "uncertain",
                "confidence": 1.0,
                "response_text": "I can't walk right now.",
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
                        "output_mode": "body_action",
                    },
                }
            ],
        )

    def test_stateful_effect_goal_cannot_be_completed_by_respond_outcome(self):
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
            "stateful_effect goal cannot use disposition=respond",
        ):
            validate_goal_responsibility_outcomes(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-weather",
                        "metadata": {"output_mode": "stateful_effect"},
                    }
                ],
            )

    def test_information_goal_can_respond_from_exact_delivered_evidence(self):
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
                    "metadata": {"output_mode": "information"},
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

    def test_information_goal_can_respond_from_exact_terminal_reentry(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Answer with current weather evidence.",
            "response_text": "今晚降雨概率最高约76%。",
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
        data = {
            "location": "重庆",
            "forecast_period": {
                "scope": "night",
                "precipitation_probability_max": 76.0,
            },
        }

        validate_goal_responsibility_outcomes(
            output,
            authoritative_goals=[
                {
                    "goal_id": "goal-weather",
                    "metadata": {"output_mode": "information"},
                }
            ],
            context={
                "result_evidence_reentry": {
                    "source_goal_ids": ["goal-weather"],
                    "evidence_refs": ["evidence-weather"],
                },
                "trusted_terminal_evidence": [
                    {
                        "evidence_id": "evidence-weather",
                        "tool_id": "chromie.weather.lookup",
                        "status": "completed",
                        "data": data,
                        "output_sha256": canonical_value_sha256(data),
                    }
                ],
            },
        )

    def test_terminal_reentry_with_bad_digest_cannot_authorize_response(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Answer with current weather evidence.",
            "response_text": "今晚降雨概率最高约76%。",
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

        authoritative_goals = [
            {
                "goal_id": "goal-weather",
                "metadata": {"output_mode": "information"},
                "resource_responsibility": {
                    "resource": {"kind": "information"}
                },
            }
        ]
        with self.assertRaisesRegex(
            ValueError,
            "external_read_response_requires_completed_or_verified_evidence",
        ):
            validate_external_response_evidence_boundary(
                output,
                authoritative_goals=authoritative_goals,
                context={
                    "result_evidence_reentry": {
                        "source_goal_ids": ["goal-weather"],
                        "evidence_refs": ["evidence-weather"],
                    },
                    "trusted_terminal_evidence": [
                        {
                            "evidence_id": "evidence-weather",
                            "tool_id": "chromie.weather.lookup",
                            "status": "completed",
                            "data": {"location": "重庆"},
                            "output_sha256": "0" * 64,
                        }
                    ],
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
                    "timing": "sequential",
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
                "timing": "sequential",
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
    def test_exact_reentry_responses_override_stale_source_plan_aggregate(self):
        raw = {
            "disposition": "mixed",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Report retained completion evidence.",
            "response_text": "Stale limitation from an unscoped sibling Goal.",
            "steps": [],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "I completed the walk.",
                    "unresolved": [],
                    "step_ids": [],
                    "satisfaction": exact_satisfaction(["goal-walk"]),
                    "rationale": "The retained execution evidence proves the walk completed.",
                },
                "goal-blink": {
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "I completed the blink.",
                    "unresolved": [],
                    "step_ids": [],
                    "satisfaction": exact_satisfaction(["goal-blink"]),
                    "rationale": "The retained execution evidence proves the blink completed.",
                },
            },
            "goal_satisfaction": {
                "score": 2 / 3,
                "status": "partial",
                "satisfied_goal_ids": ["goal-walk", "goal-blink"],
                "unmet_goal_ids": ["goal-blink"],
                "unmet_requirements": ["singing"],
                "rationale": "Stale source-plan accounting.",
            },
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }

        normalized, repairs = normalize_common_planner_output(
            raw,
            authoritative_goals=[
                {"goal_id": "goal-walk"},
                {"goal_id": "goal-blink"},
            ],
            capability_payload=[],
        )

        self.assertEqual(normalized["disposition"], "respond")
        self.assertEqual(
            normalized["response_text"],
            "I completed the walk. I completed the blink.",
        )
        self.assertEqual(
            normalized["goal_satisfaction"]["satisfied_goal_ids"],
            ["goal-walk", "goal-blink"],
        )
        self.assertEqual(normalized["goal_satisfaction"]["unmet_goal_ids"], [])
        self.assertEqual(normalized["goal_satisfaction"]["unmet_requirements"], [])
        self.assertTrue(repairs["terminal_response_goal_outcome_accounting"])
        validated = validate_planner_model_output(
            normalized,
            planner_tier="fast",
            expected_goal_ids_for_turn=["goal-walk", "goal-blink"],
        )
        self.assertEqual(validated.disposition, "respond")

    def test_unanimous_nonexecuting_outcome_drops_stale_execution_mechanics(self):
        raw = {
            "disposition": "unavailable",
            "coverage": "complete",
            "confidence": 0.9,
            "goal_summary": "Weather evidence is unavailable.",
            "response_text": "I could not obtain the weather evidence.",
            "steps": [{"step_id": "stale"}],
            "parameter_resolutions": [{"step_id": "stale"}],
            "time_conditions": [{"kind": "stale"}],
            "goal_outcomes": {
                "goal-weather": {
                    "disposition": "unavailable",
                    "coverage": "complete",
                }
            },
            "plan_relation": "safe_adjustment",
            "user_confirmation_required": True,
        }

        normalized, repairs = normalize_common_planner_output(
            raw,
            authoritative_goals=[{"goal_id": "goal-weather"}],
            capability_payload=[],
        )

        self.assertEqual(normalized["plan_relation"], "exact")
        self.assertFalse(normalized["user_confirmation_required"])
        self.assertEqual(normalized["steps"], [])
        self.assertEqual(normalized["parameter_resolutions"], [])
        self.assertEqual(normalized["time_conditions"], [])
        self.assertTrue(repairs["nonexecuting_plan_mechanics"])

    def test_numeric_capability_argument_string_is_mechanically_typed(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "steps": [
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"vx_mps": "0.2", "duration_s": "10"},
                }
            ],
        }
        capability_payload = [
            {
                "capability_id": "soridormi.walk_velocity",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number"},
                        "duration_s": {"type": "integer"},
                    },
                },
            }
        ]

        normalized, repairs = normalize_common_planner_output(
            raw,
            authoritative_goals=[],
            capability_payload=capability_payload,
        )

        self.assertEqual(normalized["steps"][0]["args"], {"vx_mps": 0.2, "duration_s": 10})
        self.assertEqual(len(repairs["capability_argument_types"]), 2)

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
    def test_capability_repair_feedback_keeps_distinct_argument_failures(self):
        error = planner_fast_validation.CapabilityArgumentValidationError(
            [
                {
                    "type": "invalid_args",
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_velocity",
                    "errors": ["args.vx_mps expected number"],
                },
                {
                    "type": "invalid_args",
                    "step_id": "turn",
                    "capability_id": "soridormi.turn_in_place",
                    "errors": ["args.yaw_radps exceeds maximum"],
                },
            ]
        )

        items = planner_fast_validation.planner_validation_error_items(
            error,
            raw={},
            planner_tier="fast",
            expected_goal_ids_for_turn=[],
            include_canonical_plan_diagnostics=False,
        )

        self.assertEqual([item["step_id"] for item in items], ["walk", "turn"])

    def test_terminal_evidence_reentry_survives_final_plan_validation(self):
        response_text = "今晚重庆降雨概率最高约76%，不是确定会下雨。"
        raw = multi_goal_plan(
            disposition="respond",
            coverage="complete",
            goal_summary="Answer the weather question from trusted terminal evidence.",
            response_text=response_text,
            steps=[],
            goal_outcomes={
                "goal-weather": respond_outcome(
                    "goal-weather",
                    response_text,
                    "Trusted terminal weather evidence answers the Goal.",
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-weather"]),
        )
        data = {
            "location": "重庆",
            "forecast_period": {
                "scope": "night",
                "precipitation_probability_max": 76.0,
            },
        }
        planner_request = request(
            "今晚重庆会不会下雨？",
            goal_ids=["goal-weather"],
            goal_metadata={"output_mode": "information"},
        )
        context = dict(planner_request.context)
        context.update(
            {
                "result_evidence_reentry": {
                    "source_goal_ids": ["goal-weather"],
                    "evidence_refs": ["evidence-weather"],
                },
                "trusted_terminal_evidence": [
                    {
                        "evidence_id": "evidence-weather",
                        "tool_id": "chromie.weather.lookup",
                        "status": "completed",
                        "data": data,
                        "output_sha256": canonical_value_sha256(data),
                    }
                ],
                "trusted_execution_outcome": {
                    "aggregate_status": "completed",
                    "goal_outcomes": [
                        {
                            "goal_id": "goal-weather",
                            "status": "completed",
                            "evidence_ids": ["evidence-weather"],
                            "completion_qualification": {
                                "required": False,
                                "established": True,
                            },
                        }
                    ],
                },
            }
        )
        planner_request = planner_request.model_copy(update={"context": context})

        ollama = ScriptedOllama([raw, _truth_certificate()])
        plan = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve(planner_request)
        )

        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.response_text, response_text)
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        planning_prompt = str(ollama.prompts[0][0])
        self.assertIn(
            "original user turn and source Plan are historical provenance",
            planning_prompt,
        )
        self.assertIn("FINAL TRUSTED EXECUTION OUTCOME JSON", planning_prompt)
        self.assertIn(
            "describe that exact source-Plan effect as completed",
            planning_prompt,
        )
        self.assertNotIn(
            "At least one canonical Goal requires provider/effect evidence.",
            planning_prompt,
        )
        self.assertEqual(ollama.prompts[0][1]["options"]["num_predict"], 2048)
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertIn(
            "a probability below 100% remains a possibility/probability",
            response_schema["properties"]["response_text"]["description"],
        )
        self.assertEqual(
            ollama.prompts[1][1]["prompt_family"],
            "fast_planner.evidence_response.truth_check",
        )
        truth_prompt = str(ollama.prompts[1][0])
        self.assertIn("Trusted execution outcome JSON", truth_prompt)
        self.assertIn("Critical claim-type boundary", truth_prompt)
        self.assertIn("Minimal authoritative source-Plan projection", truth_prompt)
        self.assertNotIn("selected_agent_skills", truth_prompt)
        self.assertIn('"goal_id":"goal-weather"', truth_prompt)
        self.assertIn(
            "Do not set that flag when the candidate makes no probability",
            truth_prompt,
        )
        self.assertIn("completion qualification", truth_prompt)
        self.assertEqual(ollama.prompts[1][1]["options"]["num_predict"], 128)
        self.assertEqual(
            plan.metadata["evidence_response_truth_qualification"],
            _truth_certificate(),
        )

    def test_terminal_evidence_wording_that_upgrades_probability_is_rejected(self):
        response_text = "重庆今晚降雨概率76%，所以会下雨。"
        raw = multi_goal_plan(
            disposition="respond",
            coverage="complete",
            goal_summary="Answer the weather question from trusted evidence.",
            response_text=response_text,
            steps=[],
            goal_outcomes={
                "goal-weather": respond_outcome(
                    "goal-weather",
                    response_text,
                    "Trusted weather evidence answers the Goal.",
                )
            },
            goal_satisfaction=exact_satisfaction(["goal-weather"]),
        )
        data = {
            "location": "重庆",
            "forecast_period": {
                "scope": "night",
                "precipitation_probability_max": 76.0,
            },
        }
        planner_request = request(
            "今晚重庆会不会下雨？",
            goal_ids=["goal-weather"],
            goal_metadata={"output_mode": "information"},
        )
        context = dict(planner_request.context)
        context.update(
            {
                "result_evidence_reentry": {
                    "source_goal_ids": ["goal-weather"],
                    "evidence_refs": ["evidence-weather"],
                },
                "trusted_terminal_evidence": [
                    {
                        "evidence_id": "evidence-weather",
                        "tool_id": "chromie.weather.lookup",
                        "status": "completed",
                        "data": data,
                        "output_sha256": canonical_value_sha256(data),
                    }
                ],
            }
        )
        planner_request = planner_request.model_copy(update={"context": context})
        ollama = ScriptedOllama(
            [
                raw,
                _truth_certificate(
                    "reject", has_unverified_result_or_completion_claim=True
                ),
            ]
        )

        plan = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve(planner_request)
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(
            plan.escalation_reason,
            "fast_planner_evidence_response_truth_rejected",
        )
        self.assertEqual(plan.response_text, "")
        self.assertEqual(
            plan.metadata["evidence_response_truth_qualification"],
            _truth_certificate(
                "reject", has_unverified_result_or_completion_claim=True
            ),
        )

    def test_first_response_is_planner_authored_in_a_small_language_bound_contract(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "text": "我先查一下重庆今天上午的天气。",
                        "progress_kind": "check_information",
                    },
                },
                _truth_certificate(),
            ]
        )
        request = _work_request(
            sid="turn-weather-first-response",
            text="今天上午重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing this morning",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "morning",
                    },
                    "confidence": 0.96,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_first_response(
                request
            )
        )

        self.assertEqual(result.activity.text, "我先查一下重庆今天上午的天气。")
        self.assertTrue(result.activity.activity_id.startswith("progress_"))
        self.assertEqual(result.activity.role, "progress")
        self.assertEqual(result.activity.truth_stage, "pre_evidence")
        prompt, kwargs = ollama.prompts[0]
        rendered = prompt.render() if hasattr(prompt, "render") else str(prompt)
        self.assertEqual(kwargs["options"]["num_predict"], 256)
        self.assertIn("✅", kwargs["options"]["stop"])
        self.assertIn("Required response language: zh-CN", rendered)
        self.assertIn("never emit a role field", rendered)
        self.assertNotIn("role=progress", rendered)
        self.assertNotIn("role=complete_response", rendered)
        schema = kwargs["response_format"]
        progress = schema["$defs"]["FastPlannerProgressAct"]
        self.assertEqual(
            progress["properties"]["progress_kind"]["enum"],
            ["acknowledge_work", "check_information", "perform_action"],
        )
        self.assertNotIn("timing", progress["properties"])
        self.assertEqual(
            list(progress["properties"])[:3],
            ["progress_kind", "text"],
        )
        self.assertNotIn("source_responsibility_refs", progress["properties"])
        self.assertNotIn("role", progress["properties"])
        self.assertNotIn("activity_id", progress["properties"])
        self.assertNotIn("truth_stage", progress["properties"])
        self.assertNotIn("speech_act", progress["properties"])
        self.assertEqual(set(progress["required"]), set(progress["properties"]))
        self.assertEqual(set(progress["required"]), {"progress_kind", "text"})
        self.assertEqual(progress["properties"]["text"]["maxLength"], 32)
        self.assertEqual(
            progress["properties"]["text"]["pattern"],
            r"^[^?？]*$",
        )
        self.assertEqual(kwargs["options"]["num_predict"], 256)
        self.assertEqual(kwargs["options"]["num_ctx"], 6144)
        _, truth_kwargs = ollama.prompts[1]
        self.assertEqual(
            truth_kwargs["prompt_family"],
            "fast_planner.first_response.truth_check",
        )
        self.assertEqual(truth_kwargs["options"]["num_predict"], 128)
        self.assertEqual(truth_kwargs["options"]["num_ctx"], 8192)
        self.assertEqual(result.metadata["truth_qualification_call_count"], 1)

    def test_gateway_qualified_greeting_skips_redundant_truth_llm(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "activity_id": "greeting-response",
                        "role": "complete_response",
                        "text": "你好呀！",
                        "source_responsibility_refs": ["greeting"],
                    }
                }
            ]
        )
        request = _work_request(
            sid="turn-fast-greeting",
            text="你好。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "greeting",
                    "outcome": "greet the user warmly",
                    "bindings": {},
                    "output_mode": "speech",
                    "confidence": 0.98,
                }
            ],
            context={
                "user_turn_envelope": {
                    "attention": {"speech_act": "greeting"}
                }
            },
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_first_response(
                request
            )
        )

        self.assertIsNotNone(result.activity)
        self.assertEqual(result.activity.text, "你好呀！")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(result.metadata["truth_qualification_call_count"], 0)
        self.assertEqual(
            result.metadata["truth_qualification_owner"],
            "trusted_gateway_greeting_contract",
        )
        self.assertEqual(
            result.metadata["truth_qualification"], _truth_certificate()
        )

    def test_first_response_receives_resolved_target_goal_meaning_for_continuation(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "continue the previous action",
                "bindings": {"direction": "forward", "duration": "10 seconds"},
                "output_mode": "body_action",
                "relationship": "continue",
                "target_goal_ids": ["goal-walk"],
                "confidence": 0.96,
            }
        )
        request = _work_request(
            sid="turn-continue-first-response",
            text="刚才那个事情继续。",
            language="zh-CN",
            responsibilities=[responsibility.model_dump(mode="json")],
            context={
                "active_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "last_user_update": "你往前走 10 秒。",
                        "goal": {
                            "goal_id": "goal-walk",
                            "description": "move forward for 10 seconds",
                            "source_text": "你往前走 10 秒。",
                            "object": {
                                "bindings": {
                                    "direction": {"value": "forward"},
                                    "duration": {"value": "10 seconds"},
                                }
                            },
                        },
                    },
                    {
                        "goal_id": "goal-unrelated",
                        "goal": {"description": "report the weather"},
                    },
                ]
            },
        )

        prompt = str(
            planner_prompt.fast_first_response_prompt(
                request,
                responsibilities=[responsibility],
            )
        )

        self.assertIn("Resolved target Goal semantics", prompt)
        self.assertIn("你往前走 10 秒。", prompt)
        self.assertIn("move forward for 10 seconds", prompt)
        self.assertNotIn("goal-unrelated", prompt)
        self.assertIn("must name that concrete resolved", prompt)
        self.assertIn("preserve the supplied relationship", prompt)
        self.assertIn("continuation or resumption", prompt)
        self.assertIn("generic stand-in", prompt)
        self.assertIn("use prospective grammar", prompt)
        self.assertIn("require Runtime commitment", prompt)
        schema = planner_schema.fast_first_response_response_schema(
            ["walk"],
            responsibilities=[responsibility],
            language="zh-CN",
        )
        text_contract = schema["$defs"]["FastPlannerProgressAct"]["properties"][
            "text"
        ]["description"]
        self.assertIn("never use an onset or progressive predicate", text_contract)
        self.assertIn('"relationship":"continue"', text_contract)
        self.assertIn("continue the previous action", text_contract)
        truth_prompt = str(
            planner_prompt.fast_first_response_truth_prompt(
                request,
                activity=FastPlannerProgressAct.model_validate(
                    {
                        "activity_id": "continue-progress",
                        "role": "progress",
                        "text": "好，我这就往前走十秒。",
                        "progress_kind": "perform_action",
                        "source_responsibility_refs": ["walk"],
                    }
                ),
                responsibilities=[responsibility],
                trusted_evidence=[],
            )
        )
        self.assertIn("semantic relationship reversal", truth_prompt)
        self.assertIn("relationship=continue", truth_prompt)
        self.assertIn("claim a later truth stage", truth_prompt)

    def test_first_response_model_specialization_does_not_change_fast_planner_authority(self):
        first_response_ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "text": "我先查一下重庆今晚的天气。",
                        "progress_kind": "check_information",
                    }
                }
            ]
        )
        planning_ollama = ScriptedOllama(
            [
                _truth_certificate(),
                {
                    "disposition": "execute",
                    "coverage": "complete",
                    "covered_responsibility_refs": ["weather"],
                    "activities": [
                        {
                            "activity_id": "weather_lookup",
                            "role": "capability",
                            "capability_id": "chromie.weather.lookup",
                            "args": {
                                "location": "重庆",
                                "date": "today",
                                "period": "night",
                            },
                            "source_responsibility_refs": ["weather"],
                        }
                    ],
                    "continuations": [],
                    "confidence": 0.96,
                    "unresolved": [],
                    "reason_summary": "Check the requested weather.",
                }
            ]
        )
        request = _work_request(
            sid="turn-specialized-fast-phases",
            text="今天晚上重庆热不热？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether Chongqing is hot tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
        )
        resolver = FastPlannerResolver(
            planning_ollama,
            WeatherCatalog(),
            first_response_ollama=first_response_ollama,
            first_response_num_ctx=32768,
        )

        first_response = asyncio.run(resolver.resolve_first_response(request))
        advance_request = request.model_copy(
            update={
                "context": {
                    **request.context,
                    "fast_planner_first_response": first_response.model_dump(
                        mode="json"
                    ),
                }
            }
        )
        advance = asyncio.run(resolver.resolve_advance(advance_request))

        self.assertEqual(first_response.metadata["semantic_authority"], "fast_planner_model")
        self.assertEqual(advance.metadata["semantic_authority"], "fast_planner_model")
        self.assertEqual(len(first_response_ollama.prompts), 1)
        self.assertEqual(first_response_ollama.prompts[0][1]["options"]["num_ctx"], 32768)
        self.assertEqual(len(planning_ollama.prompts), 2)
        self.assertEqual(planning_ollama.prompts[0][1]["options"]["num_ctx"], 8192)
        self.assertEqual(
            first_response_ollama.prompts[0][1]["prompt_family"],
            "fast_planner.first_response",
        )
        self.assertEqual(
            planning_ollama.prompts[0][1]["prompt_family"],
            "fast_planner.first_response.truth_check",
        )
        self.assertEqual(
            planning_ollama.prompts[1][1]["prompt_family"],
            "fast_planner.advance",
        )

    def test_shared_fast_model_keeps_truth_check_in_bounded_first_response_context(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "text": "好，我这就继续往前走 10 秒。",
                        "progress_kind": "perform_action",
                    }
                },
                _truth_certificate(),
            ]
        )
        request = _work_request(
            sid="turn-shared-fast-first-response-context",
            text="刚才那个事情继续。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "continue moving forward for 10 seconds",
                    "bindings": {"direction": "forward", "duration": "10 seconds"},
                    "output_mode": "body_action",
                    "confidence": 0.96,
                }
            ],
        )
        resolver = FastPlannerResolver(
            ollama,
            WeatherCatalog(),
            first_response_num_ctx=6144,
            truth_num_ctx=6144,
            num_ctx=24576,
        )

        first_response = asyncio.run(resolver.resolve_first_response(request))

        self.assertIsNotNone(first_response.activity)
        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(ollama.prompts[0][1]["options"]["num_ctx"], 6144)
        self.assertEqual(ollama.prompts[1][1]["options"]["num_ctx"], 6144)

    def test_bounded_truth_model_specialization_keeps_fast_planning_authority(self):
        planning_ollama = ScriptedOllama([])
        author_ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "text": "好，我这就继续往前走 10 秒。",
                        "progress_kind": "perform_action",
                    }
                }
            ]
        )
        truth_ollama = ScriptedOllama([_truth_certificate()])
        request = _work_request(
            sid="turn-specialized-fast-truth",
            text="刚才那个事情继续。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "continue moving forward for 10 seconds",
                    "bindings": {"direction": "forward", "duration": "10 seconds"},
                    "output_mode": "body_action",
                    "confidence": 0.96,
                }
            ],
        )
        resolver = FastPlannerResolver(
            planning_ollama,
            WeatherCatalog(),
            first_response_ollama=author_ollama,
            first_response_num_ctx=6144,
            truth_ollama=truth_ollama,
            truth_num_ctx=6144,
            num_ctx=32768,
        )

        first_response = asyncio.run(resolver.resolve_first_response(request))

        self.assertIsNotNone(first_response.activity)
        self.assertEqual(first_response.metadata["semantic_authority"], "fast_planner_model")
        self.assertEqual(len(author_ollama.prompts), 1)
        self.assertEqual(len(truth_ollama.prompts), 1)
        self.assertEqual(len(planning_ollama.prompts), 0)
        self.assertEqual(
            truth_ollama.prompts[0][1]["prompt_family"],
            "fast_planner.first_response.truth_check",
        )
        self.assertEqual(truth_ollama.prompts[0][1]["options"]["num_ctx"], 6144)

    def test_bundle_false_weather_result_is_rejected_without_rewriting_or_retry(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "activity_id": "weather_ack",
                        "role": "progress",
                        "text": "我刚刚查了天气，重庆今晚应该会下雨哦！",
                        "progress_kind": "check_information",
                        "source_responsibility_refs": ["weather"],
                    }
                },
                _truth_certificate(
                    "reject", has_unverified_result_or_completion_claim=True
                ),
            ]
        )
        request = _work_request(
            sid="turn-bundle-c6732fcc",
            text="今晚重庆会不会下雨哦？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_first_response(
                request
            )
        )

        self.assertIsNone(result.activity)
        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            result.metadata["semantic_authority"],
            "fast_planner_truth_rejection",
        )
        self.assertEqual(
            result.metadata["truth_qualification"],
            _truth_certificate(
                "reject", has_unverified_result_or_completion_claim=True
            ),
        )
        truth_prompt = str(ollama.prompts[1][0])
        self.assertIn("immutable activity.text", truth_prompt)
        self.assertIn(
            "future-oriented grammar may announce intended checking or action",
            truth_prompt,
        )
        self.assertIn(
            "Set each of the audit flags explicitly",
            truth_prompt,
        )
        author_prompt = str(ollama.prompts[0][0])
        self.assertIn(
            "no check, execution, or fresh Evidence has happened",
            author_prompt,
        )
        self.assertIn("hobbies, practice, preferences", author_prompt)
        author_schema = ollama.prompts[0][1]["response_format"]
        progress_schema = author_schema["$defs"]["FastPlannerProgressAct"]
        self.assertIn("before any work or Evidence exists", progress_schema["properties"]["text"]["description"])

    def test_first_response_truth_qualification_failure_fails_closed_once(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "activity_id": "weather_ack",
                        "role": "progress",
                        "text": "我先查一下。",
                        "progress_kind": "check_information",
                        "source_responsibility_refs": ["weather"],
                    }
                },
                {
                    "decision": "accept",
                    "violations": [],
                    "confidence": 0.4,
                },
            ]
        )
        request = _work_request(
            sid="turn-weather-uncertain-truth",
            text="今晚重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {"location": "重庆", "time": "tonight"},
                    "confidence": 0.96,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_first_response(
                request
            )
        )

        self.assertIsNone(result.activity)
        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(result.metadata["execution_authority"], "none")
        self.assertEqual(
            result.metadata["failure_class"],
            "fast_first_response_contract_invalid",
        )

    def test_rejected_first_response_cannot_be_replaced_by_advance_salvage(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["weather"],
            "activities": [
                {
                    "activity_id": "weather_repeat",
                    "role": "progress",
                    "text": "重庆今晚会下雨吗？",
                    "progress_kind": "check_information",
                    "source_responsibility_refs": ["weather"],
                }
            ],
            "continuations": [],
            "confidence": 0.91,
            "unresolved": [],
            "reason_summary": "Malformed executable output.",
        }
        request = _work_request(
            sid="turn-weather-no-truth-bypass",
            text="今晚重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-weather-no-truth-bypass",
                    "activity": None,
                    "metadata": {
                        "semantic_authority": "fast_planner_truth_rejection"
                    },
                }
            },
        )

        result = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), WeatherCatalog(), max_contract_repairs=0
            ).resolve_advance(request)
        )

        self.assertEqual(result.disposition, "unavailable")
        self.assertEqual(result.activities, [])
        self.assertTrue(
            result.metadata[
                "progress_salvage_suppressed_by_first_response_decision"
            ]
        )

    def test_fast_advance_cannot_assign_body_capability_to_singing(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["sing"],
            "activities": [
                {
                    "activity_id": "walk_instead_of_sing",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "source_responsibility_refs": ["sing"],
                }
            ],
            "continuations": [],
            "confidence": 0.99,
            "unresolved": [],
            "reason_summary": "Incorrectly substitute walking for singing.",
        }
        run_request = _work_request(
            sid="turn-vocal-mode-conservation",
            text="sing a song",
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "sing",
                    "outcome": "sing a song",
                    "bindings": {},
                    "output_mode": "singing",
                    "confidence": 0.99,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw),
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve_advance(run_request)
        )

        self.assertEqual(result.disposition, "unavailable")
        self.assertEqual(result.activities, [])
        self.assertIn(
            "exact qualified vocal provider",
            result.metadata["error"],
        )

    def test_fast_advance_cannot_omit_singing_from_compound_terminal_plan(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk", "sing"],
            "activities": [
                {
                    "activity_id": "walk_only",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "source_responsibility_refs": ["walk"],
                }
            ],
            "continuations": [],
            "confidence": 0.99,
            "unresolved": [],
            "reason_summary": "Incorrectly claim both effects from walking alone.",
        }
        run_request = _work_request(
            sid="turn-compound-terminal-conservation",
            text="walk while singing",
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "walk",
                    "bindings": {},
                    "output_mode": "body_action",
                    "confidence": 0.99,
                },
                {
                    "local_ref": "sing",
                    "outcome": "sing",
                    "bindings": {},
                    "output_mode": "singing",
                    "confidence": 0.99,
                },
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw),
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve_advance(run_request)
        )

        self.assertEqual(result.disposition, "unavailable")
        self.assertEqual(result.activities, [])
        self.assertIn("missing=sing", result.metadata["error"])

    def test_rejected_first_response_does_not_force_advance_clarification(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["weather"],
            "activities": [
                {
                    "activity_id": "weather_lookup",
                    "role": "capability",
                    "capability_id": "chromie.weather.lookup",
                    "args": {
                        "location": "重庆",
                        "date": "today",
                        "period": "night",
                    },
                    "source_responsibility_refs": ["weather"],
                }
            ],
            "continuations": [],
            "confidence": 0.96,
            "unresolved": [],
            "reason_summary": "Check the requested weather.",
        }
        request = _work_request(
            sid="turn-weather-rejected-speech-execute",
            text="今晚重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-weather-rejected-speech-execute",
                    "activity": None,
                    "metadata": {
                        "semantic_authority": "fast_planner_truth_rejection"
                    },
                }
            },
        )
        ollama = FakeOllama(raw)

        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(request)
        )

        self.assertEqual(result.disposition, "execute")
        self.assertEqual([item.role for item in result.activities], ["capability"])
        advance_prompt = str(ollama.prompts[0][0])
        self.assertIn(
            "bounded first-response phase completed with no committed speech",
            advance_prompt,
        )
        self.assertTrue(
            any(
                item.get("if", {})
                .get("properties", {})
                .get("disposition", {})
                .get("enum")
                == ["execute", "mixed"]
                for item in ollama.prompts[0][1]["response_format"]["allOf"]
            )
        )
        self.assertEqual(
            ollama.prompts[0][1]["response_format"]["properties"]["activities"]
            ["items"]["oneOf"],
            [
                {"$ref": "#/$defs/FastPlannerCapabilityActivity"},
                {"$ref": "#/$defs/FastPlannerClarificationAct"},
            ],
        )

    def test_advance_cannot_replace_explicit_quantity_with_capability_default(self):
        class DefaultedWalkCatalog:
            async def prompt_entries(self, **kwargs):
                return [
                    CatalogCapability(
                        capability_id="soridormi.walk_forward",
                        agent_id="capability_agent",
                        description="Walk forward for a bounded duration.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "speed": {
                                    "type": "string",
                                    "enum": ["normal", "quick"],
                                    "default": "normal",
                                },
                                "duration_s": {
                                    "type": "number",
                                    "minimum": 0.5,
                                    "maximum": 20.0,
                                    "default": 2.0,
                                },
                            },
                            "additionalProperties": False,
                        },
                        effects=["physical_motion"],
                        available=True,
                        interaction_executable=True,
                        prompt_tier="common",
                    )
                ]

        first = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk"],
            "activities": [
                {
                    "activity_id": "walk-forward",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {},
                    "source_responsibility_refs": ["walk"],
                    "timing": "sequential",
                }
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Walk forward for the requested duration.",
        }
        ollama = ScriptedOllama([first])
        request = _work_request(
            sid="turn-explicit-duration-not-default",
            text="你往前走 10 秒。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "move forward for ten seconds",
                    "bindings": {
                        "direction": "forward",
                        "duration": "10 seconds",
                    },
                    "output_mode": "body_action",
                    "confidence": 0.95,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, DefaultedWalkCatalog()).resolve_advance(
                request
            )
        )

        self.assertEqual(result.disposition, "unavailable")
        self.assertEqual(result.activities, [])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertIn("omitted explicit numeric", result.metadata["error"])
        self.assertNotIn("contract_revision_attempted", result.metadata)

    def test_committed_first_response_is_merged_without_reauthoring(self):
        ollama = FakeOllama(
            {
                "disposition": "execute",
                "coverage": "complete",
                "covered_responsibility_refs": ["weather"],
                "activities": [
                    {
                        "activity_id": "weather_lookup",
                        "role": "capability",
                        "capability_id": "chromie.weather.lookup",
                        "args": {
                            "location": "重庆",
                            "date": "today",
                            "period": "morning",
                        },
                        "source_responsibility_refs": ["weather"],
                    }
                ],
                "continuations": [],
                "confidence": 0.96,
                "unresolved": [],
                "reason_summary": "Check the requested weather.",
            }
        )
        request = _work_request(
            sid="turn-weather-merged",
            text="今天上午重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing this morning",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "morning",
                    },
                    "confidence": 0.96,
                }
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-weather-merged",
                    "activity": {
                        "activity_id": "weather_ack",
                        "role": "progress",
                        "text": "我先查一下。",
                        "progress_kind": "check_information",
                        "source_responsibility_refs": ["weather"],
                    },
                }
            },
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(request)
        )

        self.assertEqual(
            [activity.role for activity in result.activities],
            ["progress", "capability"],
        )
        self.assertEqual(result.activities[0].text, "我先查一下。")
        schema = ollama.prompts[0][1]["response_format"]
        encoded_items = json.dumps(
            schema["properties"]["activities"]["items"], sort_keys=True
        )
        self.assertNotIn("FastPlannerProgressAct", encoded_items)

    @staticmethod
    def _clarification_output(
        *,
        source_kind: str,
        source_reference: str,
        required_for: list[str],
        sources_considered: list[str],
    ) -> dict:
        return {
            "disposition": "clarify",
            "coverage": "partial",
            "covered_responsibility_refs": ["weather"],
            "activities": [
                {
                    "activity_id": "clarify-weather",
                    "role": "clarification",
                    "text": "你想查哪个地点的天气？",
                    "speech_act": "ask_clarification",
                    "source_responsibility_refs": ["weather"],
                    "information_gaps": [
                        {
                            "gap_id": "gap-weather",
                            "description": "A material input is still missing.",
                            "blocking": True,
                            "required_for": required_for,
                            "preferred_resolution": "ask_user",
                            "source_kind": source_kind,
                            "source_reference": source_reference,
                            "resolution_sources_considered": sources_considered,
                        }
                    ],
                }
            ],
            "continuations": [],
            "confidence": 0.91,
            "unresolved": ["A material input is still missing."],
            "reason_summary": "The user can resolve the remaining blocker.",
        }

    def test_first_activity_plan_can_complete_clear_greeting_while_ga_runs(self):
        ollama = FakeOllama(
            {
                "disposition": "respond",
                "coverage": "complete",
                "covered_responsibility_refs": ["greeting"],
                "activities": [
                    {
                        "activity_id": "activity-greeting",
                        "role": "complete_response",
                        "text": "你好呀！",
                        "speech_act": "greeting",
                        "source_responsibility_refs": ["greeting"],
                    }
                ],
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = _work_request(
            sid="turn-greeting",
            text="你好",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "bindings": {},
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
        self.assertFalse(hasattr(advance.activities[0], "response_text"))
        self.assertEqual(advance.activities[0].role, "complete_response")
        self.assertIn("Responsibility evidence", ollama.prompts[0][0])
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertIn("FastPlannerCompleteResponseAct", str(response_schema))

    def test_complete_response_act_cannot_hide_wording_in_speech_act(self):
        with self.assertRaises(ValidationError):
            FastPlannerCompleteResponseAct(
                activity_id="activity-greeting",
                role="complete_response",
                text="你好呀，我很高兴见到你。",
                speech_act="你好呀，我很高兴见到你。",
                source_responsibility_refs=["greeting"],
            )

    def test_clarification_act_uses_closed_communicative_function(self):
        with self.assertRaises(ValidationError):
            FastPlannerClarificationAct(
                activity_id="ask-tea",
                role="clarification",
                text="你想喝什么茶？",
                speech_act="你想喝什么茶？",
                source_responsibility_refs=["tea"],
                information_gaps=[
                    {
                        "gap_id": "gap-tea-kind",
                        "description": "Which kind of tea should be brought?",
                        "blocking": True,
                        "required_for": ["tea_kind"],
                        "preferred_resolution": "ask_user",
                        "source_kind": "execution_input",
                        "source_reference": "chromie.tea.bring",
                        "resolution_sources_considered": [
                            "authoritative_context",
                            "capability_schema",
                        ],
                    }
                ],
            )

    def test_semantic_clarification_must_cite_exact_gi_unresolved_meaning(self):
        unresolved = "The intended device is not identified."
        raw = self._clarification_output(
            source_kind="unresolved_meaning",
            source_reference=unresolved,
            required_for=["device_referent"],
            sources_considered=["authoritative_context"],
        )
        run_request = _work_request(
            sid="turn-semantic-gap",
            text="Turn it off.",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "turn off the device the user means",
                    "bindings": {},
                    "confidence": 0.72,
                }
            ],
            interpretation_unresolved=[unresolved],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), FakeCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "clarify")
        gap = advance.activities[0].information_gaps[0]
        self.assertEqual(gap.source_kind, "unresolved_meaning")
        self.assertEqual(gap.source_reference, unresolved)

    def test_invented_semantic_clarification_source_fails_closed(self):
        raw = self._clarification_output(
            source_kind="unresolved_meaning",
            source_reference="A device color is unknown.",
            required_for=["device_color"],
            sources_considered=["authoritative_context"],
        )
        run_request = _work_request(
            sid="turn-invented-semantic-gap",
            text="Turn it off.",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "turn off the device the user means",
                    "bindings": {},
                    "confidence": 0.72,
                }
            ],
            interpretation_unresolved=["The intended device is not identified."],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), FakeCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertEqual(
            advance.metadata["failure_class"], "fast_advance_contract_invalid"
        )
        self.assertIn("exact GI unresolved meaning", advance.metadata["error"])

    def test_missing_weather_location_is_a_planner_execution_input_gap(self):
        raw = self._clarification_output(
            source_kind="execution_input",
            source_reference="chromie.weather.lookup",
            required_for=["location"],
            sources_considered=[
                "authoritative_context",
                "trusted_observation",
                "capability_schema",
            ],
        )
        run_request = _work_request(
            sid="turn-weather-missing-location",
            text="Will it rain today?",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "tell the user whether it will rain today",
                    "bindings": {"date": "today"},
                    "confidence": 0.94,
                }
            ],
            interpretation_unresolved=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), WeatherCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "clarify")
        gap = advance.activities[0].information_gaps[0]
        self.assertEqual(gap.source_kind, "execution_input")
        self.assertEqual(gap.source_reference, "chromie.weather.lookup")
        self.assertEqual(gap.required_for, ["location"])

    def test_fast_advance_rejects_invented_required_weather_location(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["clock"],
            "activities": [
                {
                    "activity_id": "clock-progress",
                    "role": "progress",
                    "text": "我看看现在几点。",
                    "progress_kind": "check_information",
                    "source_responsibility_refs": ["clock"],
                },
                {
                    "activity_id": "wrong-weather-lookup",
                    "role": "capability",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "user's current location"},
                    "source_responsibility_refs": ["clock"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Wrongly use weather for clock time.",
        }
        run_request = _work_request(
            sid="turn-clock-wrong-weather",
            text="帮我看看现在几点。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "clock",
                    "outcome": "determine the current local time",
                    "bindings": {},
                    "confidence": 0.96,
                }
            ],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), WeatherCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertFalse(
            any(activity.role == "capability" for activity in advance.activities)
        )
        self.assertIn(
            "cannot invent an unbound required Capability input",
            advance.metadata["error"],
        )

    def test_first_response_truth_contract_rejects_invented_instrument(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "clock",
                "outcome": "determine the current local time",
                "bindings": {},
                "confidence": 0.96,
            }
        )
        run_request = _work_request(
            sid="turn-clock-truth-contract",
            text="帮我看看现在几点。",
            language="zh-CN",
            responsibilities=[responsibility.model_dump(mode="json")],
        )
        activity = FastPlannerProgressAct.model_validate(
            {
                "activity_id": "clock-progress",
                "role": "progress",
                "text": "我得先看看手机屏幕，现在几点呢？",
                "progress_kind": "check_information",
                "source_responsibility_refs": ["clock"],
            }
        )

        prompt = str(
            planner_prompt.fast_first_response_truth_prompt(
                run_request,
                activity=activity,
                responsibilities=[responsibility],
                trusted_evidence=[],
            )
        )

        self.assertIn("invents a physical instrument", prompt)
        self.assertIn("never say Chromie will look at a phone", prompt)
        self.assertIn("assigns Chromie's owed action to the human", prompt)
        self.assertIn("unrequested joint-participation wording", prompt)
        self.assertIn("look outside or use direct perception", prompt)
        self.assertIn("concrete method claim", planner_prompt.fast_first_response_truth_system_prompt())
        self.assertIn(
            "in a human command addressed to Chromie, Chromie is the commanded actor",
            planner_prompt.fast_first_response_truth_system_prompt(),
        )
        self.assertIn(
            "first-person subject is the correct actor",
            planner_prompt.fast_first_response_truth_system_prompt(),
        )
        self.assertIn(
            "makes the human a co-participant",
            planner_prompt.fast_first_response_truth_system_prompt(),
        )
        author_prompt = str(
            planner_prompt.fast_first_response_prompt(
                run_request,
                responsibilities=[responsibility],
            )
        )
        self.assertIn("An imperative addressed to Chromie makes Chromie the actor", author_prompt)
        self.assertIn("Chromie's first-person intention", author_prompt)
        self.assertIn("invitation, accompaniment, or joint activity", author_prompt)
        self.assertIn("preliminary promise would be duplicative", author_prompt)
        self.assertIn("prospective intention", prompt)
        self.assertIn("I checked", prompt)
        self.assertIn("我查过/我查了一下", prompt)
        self.assertIn(
            "has_unverified_result_or_completion_claim=true",
            planner_prompt.fast_first_response_truth_system_prompt(),
        )

        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "progress_kind": "check_information",
                        "text": activity.text,
                    }
                },
                _truth_certificate(
                    "reject", has_ungrounded_method_or_world_claim=True
                ),
            ]
        )
        result = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_first_response(
                run_request
            )
        )

        self.assertIsNone(result.activity)
        self.assertEqual(
            result.metadata["semantic_authority"],
            "fast_planner_truth_rejection",
        )
        truth_schema = ollama.prompts[1][1]["response_format"]
        self.assertEqual(
            truth_schema["required"],
            [
                "has_unverified_result_or_completion_claim",
                "has_ungrounded_method_or_world_claim",
                "has_semantic_perspective_contradiction",
                "has_epistemic_strength_contradiction",
                "has_execution_status_contradiction",
                "has_out_of_scope_goal_claim",
                "decision",
            ],
        )
        self.assertIn("has_semantic_perspective_contradiction", truth_schema["properties"])
        self.assertIn("has_execution_status_contradiction", truth_schema["properties"])
        self.assertIn("has_epistemic_strength_contradiction", truth_schema["properties"])
        self.assertIn("has_out_of_scope_goal_claim", truth_schema["properties"])
        self.assertIn("has_out_of_scope_goal_claim", truth_schema["required"])

    def test_first_response_schema_avoids_provider_think_control_token(self):
        schema = planner_schema.fast_first_response_response_schema(
            ["walk"],
            language="zh-CN",
        )

        progress = schema["$defs"]["FastPlannerProgressAct"]
        self.assertEqual(
            progress["properties"]["progress_kind"]["enum"],
            ["acknowledge_work", "check_information", "perform_action"],
        )
        self.assertNotIn("think", str(schema))

    def test_unresolved_meaning_keeps_first_response_silent_until_clarification(self):
        ollama = ScriptedOllama([])
        run_request = _work_request(
            sid="turn-ambiguous-name",
            text="帮我找天信",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "ambiguous-target",
                    "outcome": "resolve what 天信 refers to before choosing work",
                    "bindings": {},
                    "confidence": 0.55,
                }
            ],
        ).model_copy(update={"interpretation_unresolved": ["天信指代不明确"]})

        result = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_first_response(
                run_request
            )
        )

        self.assertIsNone(result.activity)
        self.assertEqual(ollama.prompts, [])
        self.assertEqual(
            result.metadata["semantic_authority"],
            "fast_planner_unresolved_meaning_contract",
        )
        self.assertEqual(result.metadata["unresolved_meaning_count"], 1)

    def test_qualification_first_response_uses_non_truncating_output_budget(self):
        ollama = ScriptedOllama(
            [
                {"activity": None},
            ]
        )
        run_request = _work_request(
            sid="turn-qualification-output-budget",
            text="Please walk and blink.",
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "walk forward",
                    "bindings": {},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                }
            ],
        )

        asyncio.run(
            FastPlannerResolver(
                ollama,
                FakeCatalog(),
                num_predict=4096,
                cognitive_budget_profile="qualification",
            ).resolve_first_response(run_request)
        )

        self.assertEqual(ollama.prompts[0][1]["options"]["num_predict"], 4096)
        self.assertIn("_```json", ollama.prompts[0][1]["options"]["stop"])
        self.assertIn("}```json", ollama.prompts[0][1]["options"]["stop"])
        self.assertIn("\n```json", ollama.prompts[0][1]["options"]["stop"])
        self.assertIn("```", ollama.prompts[0][1]["options"]["stop"])

    def test_first_response_schema_cannot_complete_information_before_evidence(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "weather",
                "outcome": "determine whether it will rain in Chongqing this afternoon",
                "bindings": {"location": "重庆", "time": "下午"},
                "output_mode": "information",
                "confidence": 0.99,
            }
        )

        schema = planner_schema.fast_first_response_response_schema(
            ["weather"],
            responsibilities=[responsibility],
            language="zh-CN",
        )

        activity_refs = {
            item["$ref"]
            for item in schema["properties"]["activity"]["anyOf"]
            if "$ref" in item
        }
        self.assertEqual(
            activity_refs,
            {"#/$defs/FastPlannerProgressAct"},
        )

    def test_first_response_schema_keeps_completion_for_conversational_speech(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "greeting",
                "outcome": "reciprocate the user's greeting",
                "bindings": {},
                "output_mode": "speech",
                "confidence": 0.99,
            }
        )

        schema = planner_schema.fast_first_response_response_schema(
            ["greeting"],
            responsibilities=[responsibility],
            language="zh-CN",
        )

        activity_refs = {
            item["$ref"]
            for item in schema["properties"]["activity"]["anyOf"]
            if "$ref" in item
        }
        self.assertEqual(
            activity_refs,
            {"#/$defs/FastPlannerCompleteResponseAct"},
        )

    def test_first_response_rejects_reversing_the_humans_feeling(self):
        ollama = ScriptedOllama(
            [
                {
                    "activity": {
                        "activity_id": "tired-response",
                        "role": "complete_response",
                        "text": "我有点累，那我们先休息一下吧？",
                        "speech_act": "inform",
                        "source_responsibility_refs": ["tired"],
                    }
                },
                _truth_certificate(
                    "reject", has_semantic_perspective_contradiction=True
                ),
            ]
        )
        run_request = _work_request(
            sid="turn-human-tired",
            text="我有点累。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "tired",
                    "outcome": "acknowledge that the human feels tired",
                    "bindings": {"experiencer": "human"},
                    "confidence": 0.96,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_first_response(
                run_request
            )
        )

        self.assertIsNone(result.activity)
        self.assertEqual(
            result.metadata["truth_qualification"],
            _truth_certificate(
                "reject", has_semantic_perspective_contradiction=True
            ),
        )
        self.assertIn(
            "human's first person never becomes Chromie's first person",
            str(ollama.prompts[0][0]),
        )

    def test_qualified_immediate_conversation_never_opens_capability_selection(self):
        run_request = _work_request(
            sid="turn-immediate-social",
            text="我有点累。",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "tired",
                    "outcome": "acknowledge that the human feels tired",
                    "bindings": {"experiencer": "human"},
                    "confidence": 0.96,
                }
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-immediate-social",
                    "activity": {
                        "activity_id": "tired-response",
                        "role": "complete_response",
                        "text": "那你先歇一会儿吧，我陪着你。",
                        "speech_act": "inform",
                        "source_responsibility_refs": ["tired"],
                    },
                }
            },
        )
        ollama = ScriptedOllama([])

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "respond")
        self.assertEqual([item.role for item in advance.activities], ["complete_response"])
        self.assertEqual(ollama.prompts, [])
        self.assertTrue(advance.metadata["immediate_conversation_terminal"])

    def test_execution_input_gap_must_name_real_unbound_required_parameter(self):
        raw = self._clarification_output(
            source_kind="execution_input",
            source_reference="chromie.weather.lookup",
            required_for=["humidity"],
            sources_considered=["authoritative_context", "capability_schema"],
        )
        run_request = _work_request(
            sid="turn-weather-fake-required-input",
            text="Will it rain today?",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "tell the user whether it will rain today",
                    "bindings": {"date": "today"},
                    "confidence": 0.94,
                }
            ],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), WeatherCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertIn("required Capability inputs", advance.metadata["error"])

    def test_bundle_weather_result_is_not_a_user_resolvable_input_gap(self):
        invalid_clarification = self._clarification_output(
            source_kind="execution_input",
            source_reference="chromie.weather.lookup",
            required_for=["weather_condition"],
            sources_considered=["authoritative_context", "capability_schema"],
        )
        invalid_clarification["activities"][0]["text"] = (
            "我已经查到重庆今晚的天气情况啦！"
        )
        ollama = ScriptedOllama([invalid_clarification])
        run_request = _work_request(
            sid="turn-bundle-c6732fcc-advance",
            text="今晚重庆会不会下雨哦？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(
                run_request
            )
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertEqual(advance.activities, [])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertIn("required Capability inputs", advance.metadata["error"])
        self.assertNotIn("contract_revision_attempted", advance.metadata)

    def test_planner_cannot_ask_for_weather_location_already_bound_by_gi(self):
        raw = self._clarification_output(
            source_kind="execution_input",
            source_reference="chromie.weather.lookup",
            required_for=["location"],
            sources_considered=["authoritative_context", "capability_schema"],
        )
        run_request = _work_request(
            sid="turn-weather-location-bound",
            text="Will it rain in Chongqing today?",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "tell the user whether it will rain in Chongqing today",
                    "bindings": {"location": "重庆", "date": "today"},
                    "confidence": 0.96,
                }
            ],
        )

        advance = asyncio.run(
            FastPlannerResolver(
                FakeOllama(raw), WeatherCatalog(), max_contract_repairs=0
            ).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertIn("already-bound input", advance.metadata["error"])

    def test_first_activity_plan_preserves_profile_context_topology(self):
        ollama = FakeOllama(
            {
                "disposition": "respond",
                "coverage": "complete",
                "covered_responsibility_refs": ["greeting"],
                "activities": [
                    {
                        "activity_id": "activity-greeting",
                        "role": "complete_response",
                        "text": "你好呀！",
                        "speech_act": "greeting",
                        "source_responsibility_refs": ["greeting"],
                    }
                ],
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = _work_request(
            sid="turn-greeting-profile-context",
            text="你好",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "confidence": 0.98,
                    }
                ]
            },
            history=[],
        )

        asyncio.run(
            FastPlannerResolver(
                ollama,
                FakeCatalog(),
                num_ctx=32768,
            ).resolve_advance(run_request)
        )

        self.assertEqual(ollama.prompts[0][1]["options"]["num_ctx"], 32768)

    def test_first_activity_plan_receives_executable_capability_catalog(self):
        ollama = FakeOllama(
            {
                "disposition": "respond",
                "coverage": "complete",
                "covered_responsibility_refs": ["greeting"],
                "activities": [
                    {
                        "activity_id": "activity-greeting",
                        "role": "complete_response",
                        "text": "你好呀！",
                        "speech_act": "greeting",
                        "source_responsibility_refs": ["greeting"],
                    }
                ],
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Clear harmless greeting can be completed now.",
            }
        )
        run_request = _work_request(
            sid="turn-greeting-no-catalog",
            text="你好",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "greeting",
                        "outcome": "Socially reciprocate the user's greeting.",
                        "bindings": {},
                        "confidence": 0.98,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(
                run_request
            )
        )

        self.assertEqual(advance.continuations, [])
        rendered = str(ollama.prompts[0][0])
        self.assertIn("Executable common Capability catalog", rendered)
        self.assertIn("soridormi.walk_forward", rendered)

    def test_fast_planner_prompt_uses_gateway_original_user_wording(self):
        responsibility = {
            "local_ref": "weather",
            "outcome": "determine whether Chongqing is hot tonight",
            "bindings": {
                "location": "重庆",
                "temporal_scope": "今晚",
            },
            "confidence": 0.95,
        }
        run_request = _work_request(
            sid="turn-original-source",
            text="今晚，重庆热不热？",
            language="zh-CN",
            responsibilities=[responsibility],
            context={
                "user_turn_envelope": {
                    "original_input": {"text": "  今晚，重庆热不热？  "}
                },
                "active_goal_snapshots": [],
                "interaction_context": {},
            },
            history=[],
        )
        prompt = planner_prompt.fast_advance_layered_prompt(
            run_request,
            responsibilities=[
                CognitiveResponsibilityProposal.model_validate(responsibility)
            ],
            capabilities=[],
        )

        self.assertEqual(run_request.text, "今晚，重庆热不热？")
        self.assertEqual(
            run_request.original_user_text, "  今晚，重庆热不热？  "
        )
        self.assertIn("Current user turn:\n  今晚，重庆热不热？  ", str(prompt))

    def test_first_activity_weather_prompt_fits_declared_context_budget(self):
        responsibility = {
            "local_ref": "weather",
            "outcome": "Tell the user whether it will rain in Chongqing tonight.",
            "bindings": {
                "location": "Chongqing",
                "temporal_scope": "今天晚上",
            },
            "confidence": 0.95,
        }
        run_request = _work_request(
            sid="turn-weather-budget",
            text="你好，今天重庆晚上有没有雨啊？",
            language="zh-CN",
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
        prompt = planner_prompt.fast_advance_layered_prompt(
            run_request,
            responsibilities=responsibilities,
            capabilities=[],
        )
        system = planner_prompt.fast_advance_system_prompt()
        diagnostics = ollama_prompt_preflight_diagnostics(
            prompt_chars=len(str(prompt)),
            system_chars=len(system),
            options={"num_ctx": 8192, "num_predict": 384},
            chars_per_token=2.0,
            safety_margin_tokens=2048,
        )

        self.assertLess(len(str(prompt)), 7000)
        self.assertFalse(
            any(item.event == "llm_prompt_budget_exceeded" for item in diagnostics),
            diagnostics,
        )
        self.assertNotIn("identity_answer_guidance", str(prompt))
        self.assertIn("Executable common Capability catalog", str(prompt))
        self.assertIn(
            "GI bindings are resolved human-semantic input evidence",
            str(prompt),
        )
        self.assertIn("argument_realization", str(prompt))
        self.assertIn(
            "physical-object acquisition, handover, body gestures, or attention motions "
            "cannot acquire external information",
            str(prompt),
        )
        self.assertIn("do not invent a semantic clarification", str(prompt))

    def test_first_activity_plan_schema_requires_explicit_decision_fields(self):
        schema = planner_schema.fast_advance_response_schema(["weather"])

        self.assertEqual(
            set(schema["required"]),
            {
                "covered_responsibility_refs",
                "disposition",
                "coverage",
                "activities",
                "continuations",
                "confidence",
                "unresolved",
                "reason_summary",
            },
        )
        for activity_contract in (
            "FastPlannerCompleteResponseAct",
            "FastPlannerClarificationAct",
            "FastPlannerProgressAct",
            "FastPlannerCapabilityActivity",
        ):
            activity_schema = schema["$defs"][activity_contract]
            self.assertIn("role", activity_schema["required"])
            self.assertNotIn("default", activity_schema["properties"]["role"])
            refs = activity_schema["properties"]["source_responsibility_refs"]
            self.assertEqual(refs["items"]["enum"], ["weather"])
        covered = schema["properties"]["covered_responsibility_refs"]
        self.assertEqual(covered["items"]["enum"], ["weather"])
        self.assertEqual(covered["minItems"], 1)
        self.assertEqual(covered["maxItems"], 1)
        self.assertTrue(covered["uniqueItems"])
        gap = schema["$defs"]["PlannerInformationGap"]
        self.assertEqual(
            gap["properties"]["preferred_resolution"],
            {"const": "ask_user", "type": "string"},
        )
        self.assertEqual(gap["properties"]["blocking"]["const"], True)
        self.assertEqual(gap["properties"]["resolved"]["const"], False)

    def test_first_activity_plan_keeps_late_catalog_semantics_visible(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "weather",
                "outcome": "Determine whether it will rain this morning.",
                "bindings": {
                    "location": "重庆",
                    "date": "today",
                    "day_part": "morning",
                },
                "confidence": 0.96,
            }
        )
        bulky = [
            {
                "capability_id": f"soridormi.synthetic_{index}",
                "description": "Physical action. " + ("x" * 1200),
                "input_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "default": 1}},
                },
                "effects": ["physical_motion"],
                "hints": {"when_to_use": "A body action. " + ("y" * 1200)},
            }
            for index in range(14)
        ]
        weather = WeatherCatalog().items[-1]
        capabilities = bulky + [
            {
                "capability_id": weather.capability_id,
                "description": weather.description,
                "input_schema": weather.input_schema,
                "requires_confirmation": weather.requires_confirmation,
                "can_run_parallel": weather.can_run_parallel,
                "parallel_metadata_declared": weather.parallel_metadata_declared,
                "resource_claims": list(weather.resource_claims),
                "effects": list(weather.effects),
                "safety_class": weather.safety_class,
                "side_effect_free": True,
                "hints": {
                    "when_to_use": "Use for weather forecast questions.",
                    "when_not_to_use": "Do not use for local person presence.",
                    "semantic_type": "weather_lookup",
                    "semantic_scope": {
                        "domain": "weather_forecast",
                        "resource_kinds": ["information"],
                        "supported_temporal_scopes": ["morning"],
                    },
                },
            }
        ]
        run_request = _work_request(
            sid="turn-late-weather-capability",
            text="今天上午重庆会不会下雨？",
            responsibilities=[responsibility.model_dump(mode="json")],
        )

        prompt = str(
            planner_prompt.fast_advance_layered_prompt(
                run_request,
                responsibilities=[responsibility],
                capabilities=capabilities,
            )
        )

        self.assertIn('\"capability_id\":\"chromie.weather.lookup\"', prompt)
        self.assertIn('\"domain\":\"weather_forecast\"', prompt)
        self.assertIn('"when_not_to_use":"Do not use for local person presence."', prompt)
        self.assertNotIn("...\n\nCover every Responsibility", prompt)
        self.assertIn(
            "The absence of fresh result Evidence is the reason to execute a matching "
            "read Capability",
            prompt,
        )
        self.assertIn(
            "Match required arguments from GI bindings by meaning, not only by identical "
            "field name",
            prompt,
        )

    def test_fresh_external_evidence_schema_excludes_completion(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "weather",
                "outcome": "Describe today's daytime weather in Chongqing.",
                "bindings": {
                    "location": "重庆",
                    "date": "today",
                    "time_of_day": "白天",
                },
                "confidence": 0.96,
            }
        )
        capability = WeatherCatalog().items[-1]
        capability_payload = [
            {
                "capability_id": capability.capability_id,
                "input_schema": capability.input_schema,
            }
        ]

        schema = planner_schema.fast_advance_response_schema(
            ["weather"],
            responsibilities=[responsibility],
            capabilities=capability_payload,
        )

        activity_refs = {
            item["$ref"]
            for item in schema["properties"]["activities"]["items"]["oneOf"]
        }
        self.assertEqual(
            activity_refs,
            {
                "#/$defs/FastPlannerProgressAct",
                "#/$defs/FastPlannerClarificationAct",
                "#/$defs/FastPlannerCapabilityActivity",
            },
        )
        capability_schema = schema["$defs"]["FastPlannerCapabilityActivity"]
        self.assertEqual(
            capability_schema["properties"]["capability_id"]["enum"],
            ["chromie.weather.lookup"],
        )
        encoded_capability_schema = json.dumps(capability_schema, sort_keys=True)
        self.assertIn('"period"', encoded_capability_schema)
        self.assertNotIn('"reason_summary"', encoded_capability_schema)
        self.assertNotIn('"allOf"', encoded_capability_schema)
        self.assertIn('"args"', encoded_capability_schema)
        self.assertTrue(
            any(
                item.get("then", {})
                .get("properties", {})
                .get("activities", {})
                .get("minContains")
                == 1
                for item in schema["allOf"]
            )
        )

    def test_fresh_evidence_missing_input_keeps_planner_resolution_branches(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "weather",
                "outcome": "Describe today's weather at the requested location.",
                "bindings": {"date": "today"},
                "confidence": 0.96,
            }
        )

        schema = planner_schema.fast_advance_response_schema(
            ["weather"],
            responsibilities=[responsibility],
        )

        activity_refs = {
            item["$ref"]
            for item in schema["properties"]["activities"]["items"]["oneOf"]
        }
        self.assertEqual(
            activity_refs,
            {
                "#/$defs/FastPlannerProgressAct",
                "#/$defs/FastPlannerClarificationAct",
                "#/$defs/FastPlannerCapabilityActivity",
            },
        )

    def test_capability_schema_excludes_ordinary_speech_responsibility_refs(self):
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(
                {
                    "local_ref": "blink",
                    "outcome": "Blink twice",
                    "bindings": {"count": 2},
                    "output_mode": "body_action",
                    "confidence": 0.98,
                }
            ),
            CognitiveResponsibilityProposal.model_validate(
                {
                    "local_ref": "joke",
                    "outcome": "Tell a short joke",
                    "bindings": {"length": "short"},
                    "output_mode": "speech",
                    "confidence": 0.98,
                }
            ),
        ]

        schema = planner_schema.fast_advance_response_schema(
            ["blink", "joke"],
            responsibilities=responsibilities,
        )

        capability_refs = schema["$defs"]["FastPlannerCapabilityActivity"][
            "properties"
        ]["source_responsibility_refs"]["items"]["enum"]
        response_refs = schema["$defs"]["FastPlannerCompleteResponseAct"][
            "properties"
        ]["source_responsibility_refs"]["items"]["enum"]
        self.assertEqual(capability_refs, ["blink"])
        self.assertEqual(response_refs, ["joke"])

    def test_body_action_schema_is_discriminator_first_and_excludes_completion(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "Walk forward for ten seconds",
                "bindings": {"direction": "forward", "duration": "10 seconds"},
                "output_mode": "body_action",
                "confidence": 0.98,
            }
        )

        schema = planner_schema.fast_advance_response_schema(
            ["walk"],
            responsibilities=[responsibility],
        )

        activity_refs = [
            item["$ref"]
            for item in schema["properties"]["activities"]["items"]["oneOf"]
        ]
        self.assertEqual(
            activity_refs,
            [
                "#/$defs/FastPlannerCapabilityActivity",
                "#/$defs/FastPlannerClarificationAct",
                "#/$defs/FastPlannerProgressAct",
            ],
        )
        for contract_name in (
            "FastPlannerCapabilityActivity",
            "FastPlannerClarificationAct",
            "FastPlannerProgressAct",
        ):
            self.assertEqual(
                next(iter(schema["$defs"][contract_name]["properties"])),
                "role",
            )

    def test_primary_capability_schema_requires_catalog_shaped_args(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "Walk forward for ten seconds",
                "bindings": {"direction": "forward", "duration": 10},
                "output_mode": "body_action",
                "confidence": 0.98,
            }
        )
        schema = planner_schema.fast_advance_response_schema(
            ["walk"],
            responsibilities=[responsibility],
            capabilities=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "duration_s": {
                                "type": "number",
                                "minimum": 0.5,
                                "default": 2.0,
                            }
                        },
                        "additionalProperties": False,
                    },
                }
            ],
        )

        capability = schema["$defs"]["FastPlannerCapabilityActivity"]
        self.assertIn("args", capability["required"])
        self.assertEqual(len(capability["oneOf"]), 1)
        branch = capability["oneOf"][0]
        self.assertEqual(
            branch["properties"]["capability_id"]["enum"],
            ["soridormi.walk_forward"],
        )
        self.assertIn("duration_s", branch["properties"]["args"]["properties"])

    def test_execute_revision_cannot_invent_progress_not_selected_initially(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "Walk forward",
                "bindings": {"direction": "forward"},
                "output_mode": "body_action",
                "confidence": 0.98,
            }
        )
        base = planner_schema.fast_advance_response_schema(
            ["walk"],
            responsibilities=[responsibility],
        )

        revision = planner_schema.fast_advance_revision_response_schema(
            base,
            {
                "disposition": "execute",
                "activities": [
                    {
                        "activity_id": "wrong-terminal",
                        "role": "complete_response",
                        "text": "I will walk forward.",
                        "source_responsibility_refs": ["walk"],
                    }
                ],
            },
            committed_communicative=False,
            capabilities=[],
            responsibilities=[responsibility],
        )

        self.assertEqual(
            revision["properties"]["activities"]["items"]["oneOf"],
            [{"$ref": "#/$defs/FastPlannerCapabilityActivity"}],
        )

    def test_complete_response_cannot_terminally_cover_body_action(self):
        invalid = {
            "disposition": "respond",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk"],
            "activities": [
                {
                    "activity_id": "wrong-spoken-terminal",
                    "role": "complete_response",
                    "text": "I will walk forward now.",
                    "source_responsibility_refs": ["walk"],
                }
            ],
            "continuations": [],
            "confidence": 0.98,
            "unresolved": [],
            "reason_summary": "The response covers the body action.",
        }
        request = _work_request(
            sid="turn-body-spoken-terminal",
            text="Walk forward.",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "Walk forward",
                    "bindings": {"direction": "forward"},
                    "output_mode": "body_action",
                    "confidence": 0.98,
                }
            ],
        )

        result = asyncio.run(
            FastPlannerResolver(FakeOllama(invalid), FakeCatalog()).resolve_advance(
                request
            )
        )

        self.assertEqual(result.disposition, "unavailable")
        self.assertEqual(result.activities, [])
        self.assertIn("ordinary speech Responsibility", result.metadata["error"])

    def test_malformed_execute_revision_requires_capability_activities(self):
        initial = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "activity_id": "cap_walk_forward_001",
                    "role": "capability",
                    "args": {"duration_s": 10},
                    "source_responsibility_refs": ["r1"],
                },
                {
                    "activity_id": "cap_blink_eyes_001",
                    "role": "capability",
                    "args": {"count": 1},
                    "source_responsibility_refs": ["r2"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Use matching body capabilities.",
        }
        repaired = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "activity_id": "walk",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 10},
                    "source_responsibility_refs": ["r1"],
                },
                {
                    "activity_id": "blink",
                    "role": "capability",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_responsibility_refs": ["r2"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Use matching body capabilities.",
        }
        request = _work_request(
            sid="turn-live-workdag-revision",
            text="Walk forward for 10 seconds and blink once.",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "Walk forward for 10 seconds",
                    "bindings": {"direction": "forward", "duration_s": 10},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "Blink once",
                    "bindings": {"action": "blink", "count": 1},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
        )
        ollama = ScriptedOllama([initial, repaired])

        result = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(request)
        )

        self.assertEqual(result.disposition, "execute")
        self.assertEqual([item.role for item in result.activities], ["capability"] * 2)
        revision_schema = ollama.prompts[1][1]["response_format"]
        self.assertEqual(
            revision_schema["properties"]["activities"]["items"]["oneOf"],
            [{"$ref": "#/$defs/FastPlannerCapabilityActivity"}],
        )
        revision_prompt = str(ollama.prompts[1][0])
        self.assertNotIn("requires at least one step", revision_prompt)
        self.assertNotIn("requires goal_satisfaction", revision_prompt)
        self.assertNotIn("requires an explicit goal_outcomes", revision_prompt)

    def test_failed_first_response_does_not_suppress_advance_response(self):
        ollama = FakeOllama(
            {
                "disposition": "mixed",
                "coverage": "complete",
                "covered_responsibility_refs": ["blink", "joke"],
                "activities": [
                    {
                        "activity_id": "blink-twice",
                        "role": "capability",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "sequential",
                        "source_responsibility_refs": ["blink"],
                    },
                    {
                        "activity_id": "tell-joke",
                        "role": "complete_response",
                        "text": "Why did the robot nap? It needed to recharge.",
                        "source_responsibility_refs": ["joke"],
                    },
                ],
                "continuations": [],
                "confidence": 0.98,
                "unresolved": [],
                "reason_summary": "Blink and deliver the requested joke.",
            }
        )
        run_request = _work_request(
            sid="turn-failed-first-response",
            text="Blink twice and tell me a short joke.",
            responsibilities=[
                {
                    "local_ref": "blink",
                    "outcome": "Blink twice",
                    "bindings": {"count": 2},
                    "output_mode": "body_action",
                    "confidence": 0.98,
                },
                {
                    "local_ref": "joke",
                    "outcome": "Tell a short joke",
                    "bindings": {"length": "short"},
                    "output_mode": "speech",
                    "confidence": 0.98,
                },
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-failed-first-response",
                    "activity": None,
                    "metadata": {
                        "semantic_authority": "deterministic_fail_safe",
                        "failure_class": "output_truncated",
                    },
                }
            },
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.disposition, "mixed")
        self.assertEqual(
            [activity.role for activity in advance.activities],
            ["capability", "complete_response"],
        )
        activity_refs = {
            item["$ref"]
            for item in ollama.prompts[0][1]["response_format"]["properties"]
            ["activities"]["items"]["oneOf"]
        }
        self.assertIn("#/$defs/FastPlannerCompleteResponseAct", activity_refs)
        self.assertNotIn("#/$defs/FastPlannerProgressAct", activity_refs)
        self.assertIn(
            "first-response phase failed closed",
            str(ollama.prompts[0][0]),
        )

    def test_committed_body_progress_is_not_advertised_again_in_advance_schema(self):
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "continue moving forward for 10 seconds",
                "bindings": {"direction": "forward", "duration": "10 seconds"},
                "output_mode": "body_action",
                "confidence": 0.96,
            }
        )

        schema = planner_schema.fast_advance_response_schema(
            ["walk"],
            responsibilities=[responsibility],
            capabilities=[
                {
                    "capability_id": "soridormi.walk_forward",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "duration_s": {"type": "number", "minimum": 0.1}
                        },
                    },
                }
            ],
            interpretation_unresolved=[],
            committed_communicative=True,
        )

        activity_refs = {
            item["$ref"]
            for item in schema["properties"]["activities"]["items"]["oneOf"]
        }
        self.assertNotIn("#/$defs/FastPlannerProgressAct", activity_refs)
        self.assertNotIn("#/$defs/FastPlannerCompleteResponseAct", activity_refs)
        self.assertIn("#/$defs/FastPlannerCapabilityActivity", activity_refs)
        self.assertIn("#/$defs/FastPlannerClarificationAct", activity_refs)
        self.assertEqual(schema["properties"]["activities"]["maxItems"], 1)
        gap = schema["$defs"]["PlannerInformationGap"]["properties"]
        self.assertEqual(
            gap["source_kind"],
            {"const": "execution_input", "type": "string"},
        )
        self.assertEqual(
            gap["source_reference"]["enum"],
            ["soridormi.walk_forward"],
        )
        self.assertEqual(gap["required_for"]["minItems"], 1)

    def test_semantic_advance_violation_fails_closed_without_dto_revision(self):
        initial = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["weather"],
            "activities": [
                {
                    "activity_id": "misclassified-progress",
                    "role": "clarification",
                    "text": "我先看看。",
                    "source_responsibility_refs": ["weather"],
                    "information_gaps": [
                        {
                            "gap_id": "weather-result",
                            "description": "Weather result is not known yet.",
                            "required_for": ["weather_result"],
                            "preferred_resolution": "ask_user",
                            "source_kind": "unresolved_meaning",
                            "source_reference": "weather",
                            "resolution_sources_considered": [
                                "authoritative_context"
                            ],
                        }
                    ],
                }
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Execute the matching weather lookup.",
        }
        first_response = {
            "turn_id": "turn-weather-execute-revision",
            "activity": {
                "activity_id": "weather-progress",
                "role": "progress",
                "text": "我先查一下。",
                "progress_kind": "check_information",
                "source_responsibility_refs": ["weather"],
            },
        }
        request = _work_request(
            sid="turn-weather-execute-revision",
            text="今晚重庆会不会下雨？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing tonight",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "day_part": "night",
                    },
                    "confidence": 0.96,
                }
            ],
            context={"fast_planner_first_response": first_response},
        )
        ollama = ScriptedOllama([initial])

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(request)
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertEqual(
            [activity.role for activity in advance.activities],
            ["progress"],
        )
        self.assertEqual(len(ollama.prompts), 1)
        self.assertNotIn("contract_revision_attempted", advance.metadata)
        self.assertIn("clarification", advance.metadata["error"])

    def test_singleton_parallel_capability_group_gets_one_dto_revision(self):
        initial = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk", "blink"],
            "activities": [
                {
                    "activity_id": "walk-step",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "timing": "parallel",
                    "source_responsibility_refs": ["walk"],
                },
                {
                    "activity_id": "blink-step",
                    "role": "capability",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_responsibility_refs": ["blink"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Perform both ordered actions.",
        }
        revised = copy.deepcopy(initial)
        revised["activities"][0]["timing"] = "sequential"
        run_request = _work_request(
            sid="turn-singleton-parallel-revision",
            text="Walk for one second, then blink twice.",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "walk for one second",
                    "bindings": {"duration_s": 1.0},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "blink",
                    "outcome": "blink twice",
                    "bindings": {"count": 2},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
        )
        ollama = ScriptedOllama([initial, revised])

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual([item.timing for item in advance.activities], ["sequential", "sequential"])
        self.assertTrue(advance.metadata["contract_revision_attempted"])
        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(
            ollama.prompts[1][1]["prompt_family"],
            "fast_planner.advance.revision",
        )
        self.assertIn("singleton", str(ollama.prompts[1][0]))

    def test_parallel_resource_conflict_gets_one_dto_revision(self):
        initial = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk", "velocity"],
            "activities": [
                {
                    "activity_id": "walk-step",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "timing": "parallel",
                    "source_responsibility_refs": ["walk"],
                },
                {
                    "activity_id": "velocity-step",
                    "role": "capability",
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"vx_mps": 0.2, "duration_s": 2.0},
                    "timing": "parallel",
                    "source_responsibility_refs": ["velocity"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Perform the two motions.",
        }
        revised = copy.deepcopy(initial)
        for activity in revised["activities"]:
            activity["timing"] = "sequential"
        run_request = _work_request(
            sid="turn-parallel-resource-revision",
            text="Walk, then use velocity control.",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "walk for one second",
                    "bindings": {"duration_s": 1.0, "before": "velocity"},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "velocity",
                    "outcome": "move at velocity for two seconds",
                    "bindings": {"vx_mps": 0.2, "duration_s": 2.0},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
        )
        ollama = ScriptedOllama([initial, revised])

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(
            [item.timing for item in advance.activities],
            ["sequential", "sequential"],
        )
        self.assertTrue(advance.metadata["contract_revision_attempted"])
        self.assertIn("parallel_resource_claim_conflict", str(ollama.prompts[1][0]))

    def test_typed_responsibility_order_rejects_compatible_parallel_timing(self):
        initial = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["walk", "blink"],
            "activities": [
                {
                    "activity_id": "walk-step",
                    "role": "capability",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "timing": "parallel",
                    "source_responsibility_refs": ["walk"],
                },
                {
                    "activity_id": "blink-step",
                    "role": "capability",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "parallel",
                    "source_responsibility_refs": ["blink"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Perform both actions.",
        }
        revised = copy.deepcopy(initial)
        for activity in revised["activities"]:
            activity["timing"] = "sequential"
        run_request = _work_request(
            sid="turn-typed-order-revision",
            text="Walk for one second, then blink twice.",
            responsibilities=[
                {
                    "local_ref": "walk",
                    "outcome": "walk for one second",
                    "bindings": {"duration_s": 1.0, "before": "blink"},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "blink",
                    "outcome": "blink twice",
                    "bindings": {"count": 2, "after": "walk"},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
        )
        ollama = ScriptedOllama([initial, revised])

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(
            [item.timing for item in advance.activities],
            ["sequential", "sequential"],
        )
        self.assertTrue(advance.metadata["contract_revision_attempted"])
        self.assertIn("must precede", str(ollama.prompts[1][0]))

    def test_daytime_weather_can_check_and_speak_in_parallel(self):
        ollama = FakeOllama(
            {
                "disposition": "execute",
                "coverage": "complete",
                "covered_responsibility_refs": ["weather"],
                "activities": [
                    {
                        "activity_id": "activity-weather-progress",
                        "role": "progress",
                        "text": "我看看。",
                        "progress_kind": "check_information",
                        "speech_act": "acknowledge_and_check",
                        "timing": "parallel",
                        "source_responsibility_refs": ["weather"],
                    },
                    {
                        "activity_id": "activity-weather-lookup",
                        "role": "capability",
                        "capability_id": "chromie.weather.lookup",
                        "args": {
                            "location": "重庆",
                            "date": "today",
                            "period": "day",
                        },
                        "timing": "parallel",
                        "source_responsibility_refs": ["weather"],
                        "reason_summary": "Check the requested daytime weather.",
                    },
                ],
                "continuations": [],
                "confidence": 0.95,
                "unresolved": [],
                "reason_summary": "The request is complete and needs fresh evidence.",
            }
        )
        run_request = _work_request(
            sid="turn-weather-daytime-progress",
            text="你好，今天重庆白天天气怎么样啊？",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user today's daytime weather in Chongqing.",
                        "bindings": {
                            "location": "重庆",
                            "date": "today",
                            "time_of_day": "白天",
                        },
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(run_request)
        )

        self.assertEqual([item.role for item in advance.activities], ["progress", "capability"])
        self.assertEqual(advance.activities[1].args["period"], "day")
        self.assertEqual(advance.continuations, [])

    def test_invalid_first_activity_plan_is_discarded_for_one_canonical_fast_revision(self):
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
        run_request = _work_request(
            sid="turn-weather-invalid-advance",
            text="今天重庆晚上会不会下大雨？",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user whether it will rain in Chongqing tonight.",
                        "bindings": {"location": "重庆", "time": "今晚"},
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.continuations, [])
        self.assertEqual(advance.activities, [])
        self.assertEqual(
            advance.metadata["advance_status"],
            "canonical_fast_revision_required",
        )
        self.assertEqual(
            advance.metadata["failure_class"],
            "fast_advance_contract_invalid",
        )

    def test_invalid_advance_retains_one_independently_valid_progress_act(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["weather"],
            "activities": [
                {
                    "activity_id": "weather-progress-1",
                    "role": "progress",
                    "text": "我看看。",
                    "progress_kind": "check_information",
                    "speech_act": "acknowledge_and_check",
                    "timing": "parallel",
                    "source_responsibility_refs": ["weather"],
                },
                {
                    "activity_id": "weather-progress-duplicate",
                    "role": "progress",
                    "text": "我看看。",
                    "progress_kind": "check_information",
                    "speech_act": "acknowledge_and_check",
                    "timing": "parallel",
                    "source_responsibility_refs": ["weather"],
                },
            ],
            "continuations": ["deep_planner"],
            "confidence": 0.94,
            "unresolved": [],
            "reason_summary": "The weather lookup should continue in Deep Planner.",
        }
        run_request = _work_request(
            sid="turn-weather-invalid-continuation",
            text="哎，今天上午重庆会不会下雨？",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Determine whether it will rain in Chongqing this morning.",
                        "bindings": {
                            "location": "重庆",
                            "date": "today",
                            "time_of_day": "上午",
                        },
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(FakeOllama(invalid), WeatherCatalog()).resolve_advance(
                run_request
            )
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertEqual(advance.continuations, [])
        self.assertEqual(len(advance.activities), 1)
        self.assertEqual(advance.activities[0].role, "progress")
        self.assertEqual(
            advance.activities[0].speech_act,
            "acknowledge_and_check",
        )
        self.assertEqual(
            advance.metadata["salvaged_progress_activity_ids"],
            ["weather-progress-1"],
        )

    def test_fail_safe_collapses_duplicate_activity_ids(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "activity_id": "duplicate-progress",
                    "role": "progress",
                    "text": "向前跑15秒",
                    "progress_kind": "perform_action",
                    "source_responsibility_refs": ["r1"],
                },
                {
                    "activity_id": "duplicate-progress",
                    "role": "progress",
                    "text": "边跑边唱歌",
                    "progress_kind": "perform_action",
                    "source_responsibility_refs": ["r2"],
                },
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Invalid progress-only terminal plan.",
        }
        run_request = _work_request(
            sid="turn-duplicate-progress-ids",
            text="Run forward and sing.",
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "run forward",
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "sing",
                    "output_mode": "singing",
                    "confidence": 0.95,
                },
            ],
        )

        advance = asyncio.run(
            FastPlannerResolver(FakeOllama(invalid), WeatherCatalog()).resolve_advance(
                run_request
            )
        )

        self.assertEqual(advance.disposition, "unavailable")
        self.assertEqual(
            [item.activity_id for item in advance.activities],
            ["duplicate-progress"],
        )

    def test_advance_restores_required_weather_location_from_gi_bindings(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1", "r2"],
            "activities": [
                {
                    "activity_id": "weather_lookup",
                    "role": "capability",
                    "capability_id": "chromie.weather.lookup",
                    "source_responsibility_refs": ["r1", "r2"],
                }
            ],
            "continuations": [],
            "confidence": 0.95,
            "unresolved": [],
            "reason_summary": "Check the requested weather.",
        }
        request = _work_request(
            sid="turn-weather-required-arg-grounding",
            text="今天晚上重庆会不会下大雨，温度高不高？",
            language="zh-CN",
            responsibilities=[
                {
                    "local_ref": "r1",
                    "outcome": "determine whether it rains heavily in Chongqing tonight",
                    "bindings": {"location": "重庆", "time": "今天晚上"},
                    "output_mode": "information",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "determine whether Chongqing is hot tonight",
                    "bindings": {"location": "重庆", "time": "今天晚上"},
                    "output_mode": "information",
                    "confidence": 0.95,
                },
            ],
            context={
                "fast_planner_first_response": {
                    "turn_id": "turn-weather-required-arg-grounding",
                    "activity": {
                        "activity_id": "weather-progress",
                        "role": "progress",
                        "text": "好，我看看重庆今晚的天气。",
                        "progress_kind": "check_information",
                        "source_responsibility_refs": ["r1", "r2"],
                    },
                }
            },
        )
        ollama = ScriptedOllama([raw])

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(request)
        )

        capability = next(
            activity for activity in advance.activities if activity.role == "capability"
        )
        self.assertEqual(capability.args, {"location": "重庆"})
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(
            advance.metadata["authoritative_arg_repairs"][0]["parameter"],
            "location",
        )

    def test_first_activity_plan_can_check_weather_and_speak_in_parallel(self):
        ollama = FakeOllama(
            {
                "disposition": "execute",
                "coverage": "complete",
                "covered_responsibility_refs": ["weather"],
                "activities": [
                    {
                        "activity_id": "activity-weather-progress",
                        "role": "progress",
                        "text": "我看看。",
                        "progress_kind": "check_information",
                        "speech_act": "acknowledge_and_check",
                        "timing": "parallel",
                        "source_responsibility_refs": ["weather"],
                    },
                    {
                        "activity_id": "activity-weather-lookup",
                        "role": "capability",
                        "capability_id": "chromie.weather.lookup",
                        "args": {
                            "location": "重庆",
                            "date": "today",
                            "period": "evening",
                        },
                        "timing": "parallel",
                        "source_responsibility_refs": ["weather"],
                        "reason_summary": "Check the requested weather.",
                    },
                ],
                "continuations": [],
                "confidence": 0.95,
                "unresolved": [],
                "reason_summary": "Fresh weather evidence is still required.",
            }
        )
        run_request = _work_request(
            sid="turn-weather-progress",
            text="今天重庆晚上会不会下大雨？",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user whether it will rain in Chongqing tonight.",
                        "bindings": {"location": "重庆", "time": "今晚"},
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, WeatherCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.continuations, [])
        self.assertEqual([item.role for item in advance.activities], ["progress", "capability"])
        self.assertEqual(advance.activities[0].progress_kind, "check_information")
        self.assertEqual(advance.activities[1].args["period"], "evening")
        self.assertFalse(hasattr(advance.activities[0], "response_text"))
        self.assertIn("Language hint: zh-CN", str(ollama.prompts[0][0]))
        response_schema = ollama.prompts[0][1]["response_format"]
        self.assertIn("FastPlannerProgressAct", str(response_schema))
        self.assertIn("FastPlannerCapabilityActivity", str(response_schema))

    def test_progress_activity_cannot_smuggle_unsupported_weather_result_text(self):
        ollama = FakeOllama(
            {
                "disposition": "execute",
                "coverage": "complete",
                "covered_responsibility_refs": ["weather"],
                "activities": [
                    {
                        "activity_id": "activity-weather-fake-result",
                        "role": "progress",
                        "text": "重庆今天温度是28摄氏度哦！",
                        "progress_kind": "check_information",
                        "response_text": "重庆今天温度是28摄氏度哦！",
                        "speech_act": "inform",
                        "source_responsibility_refs": ["weather"],
                    },
                    {
                        "activity_id": "activity-weather-lookup",
                        "role": "capability",
                        "capability_id": "chromie.weather.lookup",
                        "args": {"location": "重庆", "date": "today"},
                        "source_responsibility_refs": ["weather"],
                    },
                ],
                "continuations": [],
                "confidence": 0.95,
                "unresolved": [],
                "reason_summary": "Fresh weather evidence is still required.",
            }
        )
        run_request = _work_request(
            sid="turn-weather-fake-result",
            text="今天重庆温度多高？",
            language="zh-CN",
            context={
                "responsibility_proposals": [
                    {
                        "local_ref": "weather",
                        "outcome": "Tell the user today's Chongqing temperature.",
                        "bindings": {"location": "重庆", "time": "today"},
                        "confidence": 0.96,
                    }
                ]
            },
            history=[],
        )

        advance = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve_advance(run_request)
        )

        self.assertEqual(advance.continuations, [])
        self.assertEqual(advance.activities, [])
        self.assertEqual(
            advance.metadata["failure_class"],
            "fast_advance_contract_invalid",
        )

    def test_deep_planner_is_only_a_fast_activity_plan_complexity_continuation(self):
        advance = FastPlannerAdvance.model_validate(
            {
                "turn_id": "turn-complex",
                "disposition": "escalate",
                "coverage": "uncertain",
                "covered_responsibility_refs": ["fetch-water"],
                "activities": [],
                "continuations": ["deep_planner"],
                "confidence": 0.9,
                "unresolved": ["multi-step physical dependencies"],
            }
        )
        self.assertEqual(advance.continuations, ["deep_planner"])

    def test_prompt_receives_goal_scoped_interaction_context(self):
        planner_request = request(
            "Walk forward for fifteen seconds.",
            goal_ids=["goal-walk"],
        )
        planner_request.context["interaction_context"] = {
            "events": [{"event_id": "ledger-fast-marker"}]
        }
        prompt = planner_prompt.fast_plan_prompt(
            planner_request,
            [],
            response_schema={},
        )

        self.assertIn("ledger-fast-marker", prompt)
        self.assertIn("plan only the still-needed conversational and effectful delta", prompt)

    def test_canonical_revision_prompt_exposes_provisional_safe_work_for_reuse_decision(
        self,
    ):
        planner_request = request(
            "Check Chongqing weather today.",
            goal_ids=["goal-weather"],
        )
        planner_request.context["existing_work_activities"] = [
            {
                "activity_id": "weather-provisional",
                "role": "capability",
                "capability_id": "chromie.weather.lookup",
                "args": {"location": "重庆", "date": "today"},
                "timing": "parallel",
                "source_responsibility_refs": ["weather"],
            }
        ]

        prompt = planner_prompt.fast_plan_prompt(
            planner_request,
            [],
            response_schema={},
        )

        self.assertIn("Existing retained or provisional Runtime Activities JSON", prompt)
        self.assertIn("weather-provisional", prompt)
        self.assertIn("may already be running or completed", prompt)
        self.assertIn("step.reuse_activity_id", prompt)
        self.assertIn("validate the explicit selection mechanically", prompt)

    def test_provisional_reuse_requires_explicit_exact_activity_identity(self):
        output = PlannerModelOutput.model_validate(
            multi_goal_plan(
                disposition="execute",
                coverage="complete",
                goal_summary="Check Chongqing weather today.",
                steps=[
                    {
                        **execute_step(
                            "weather-step",
                            "chromie.weather.lookup",
                            {"location": "重庆", "date": "today"},
                            ["goal-weather"],
                            "Reuse the already-running exact lookup.",
                        ),
                        "timing": "parallel",
                        "reuse_activity_id": "weather-provisional",
                    }
                ],
                goal_outcomes={
                    "goal-weather": execute_outcome(
                        "goal-weather",
                        ["weather-step"],
                        "The selected lookup covers the Goal.",
                    )
                },
                goal_satisfaction=exact_satisfaction(["goal-weather"]),
            )
        )
        context = {
            "existing_work_activities": [
                {
                    "activity_id": "weather-provisional",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "重庆", "date": "today"},
                    "timing": "parallel",
                }
            ]
        }

        planner_fast_validation.validate_work_reuse_selection(
            output,
            context=context,
        )

        changed = output.model_copy(deep=True)
        changed.steps[0].args["location"] = "内乡"
        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "changes immutable args",
        ):
            planner_fast_validation.validate_work_reuse_selection(
                changed,
                context=context,
            )

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
                "metadata": {"output_mode": "body_action"},
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
                    "metadata": {"output_mode": "body_action"},
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
                    "metadata": {"output_mode": "body_action"},
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
                    "metadata": {"output_mode": "body_action"},
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
                    goal_ids=["goal-blink"],
                    goal_metadata={
                        "output_mode": "body_action",
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
        coverage_payload = json.loads(str(ollama.prompts[1][0]))
        self.assertEqual(
            [
                item["capability_id"]
                for item in coverage_payload["executable_capabilities"]
            ],
            ["soridormi.blink_eyes"],
        )
        self.assertNotIn(
            "soridormi.walk_velocity",
            json.dumps(coverage_payload, sort_keys=True),
        )
        self.assertIn(
            "Runtime owns confirmation",
            coverage_payload["responsibility"],
        )

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
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("你好。", goal_ids=["goal-greet"], goal_metadata={"output_mode": "speech"})))
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
                            "planned_capabilities": [
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

        terminal_data = {
            "capability_id": "soridormi.walk_forward",
            "completed": True,
            "no_motion": False,
        }
        evidence_reentry_context = {
            **index_only_context,
            "result_evidence_reentry": {
                "source_goal_ids": ["goal-weather"],
                "evidence_refs": ["evidence-weather"],
            },
            "trusted_terminal_evidence": [
                {
                    "evidence_id": "evidence-weather",
                    "tool_id": "soridormi.walk_forward",
                    "status": "completed",
                    "data": terminal_data,
                    "output_sha256": canonical_value_sha256(terminal_data),
                }
            ],
        }
        validate_external_response_evidence_boundary(
            output,
            context=evidence_reentry_context,
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
                request("Hello.", goal_ids=["goal-greet"], goal_metadata={"output_mode": "speech"})
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
                    "metadata": {"output_mode": "body_action"},
                },
                {
                    "goal_id": "goal-water",
                    "description": "拿一杯水。",
                    "source_text": run_request.text,
                    "object": {"bindings": {}},
                    "metadata": {"output_mode": "body_action"},
                },
                {
                    "goal_id": "goal-return",
                    "description": "返回用户身边。",
                    "source_text": run_request.text,
                    "object": {"bindings": {}},
                    "metadata": {"output_mode": "body_action"},
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
            FastPlannerResolver(
                FakeOllama(raw), MissingParallelMetadataCatalog()
            ).resolve(
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
        self.assertIn(
            "Response text is audible language, never a stage direction",
            ollama.prompts[0][0],
        )

    def test_explicit_numeric_grounding_mismatch_requires_deeper_semantic_plan(self):
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
        ollama = ScriptedOllama([invalid])
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
        self.assertEqual(plan.metadata["path_classification"], "semantic_escalation")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertFalse(plan.metadata["contract_repair_attempted"])
        self.assertEqual(
            plan.metadata["validation_feedback"][0]["type"],
            "authoritative_grounding_mismatch",
        )

    def test_weather_temporal_binding_omission_receives_one_dto_repair(self):
        goal_id = "goal-weather"
        initial = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Check Chongqing weather tonight.",
            steps=[
                execute_step(
                    "weather",
                    "chromie.weather.lookup",
                    {"location": "重庆", "units": "metric"},
                    [goal_id],
                    "Retrieve the requested weather.",
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(
                    goal_id, ["weather"], "The weather lookup covers the Goal."
                )
            },
            goal_satisfaction=exact_satisfaction([goal_id]),
        )
        repaired = {
            **initial,
            "steps": [
                execute_step(
                    "weather",
                    "chromie.weather.lookup",
                    {
                        "location": "重庆",
                        "date": "today",
                        "period": "night",
                        "units": "metric",
                    },
                    [goal_id],
                    "Retrieve the requested weather.",
                )
            ],
            "parameter_resolutions": [
                {
                    "step_id": "weather",
                    "parameter": "date",
                    "strategy": "semantic_realization",
                    "value": "today",
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Realized the human temporal scope for this Capability.",
                    "source_goal_ids": [goal_id],
                },
                {
                    "step_id": "weather",
                    "parameter": "period",
                    "strategy": "semantic_realization",
                    "value": "night",
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": "Realized the human temporal scope for this Capability.",
                    "source_goal_ids": [goal_id],
                },
            ],
        }
        catalog = FakeCatalog()
        catalog.items.append(
            CatalogCapability(
                capability_id="chromie.weather.lookup",
                agent_id="chromie.weather",
                description="Retrieve current or short-range weather.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string", "enum": ["today", "tomorrow"]},
                        "period": {
                            "type": "string",
                            "enum": ["day", "morning", "afternoon", "evening", "night"],
                        },
                        "units": {"type": "string", "enum": ["metric", "imperial", "auto"]},
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                hints={
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                        "delivery_modes": ["spoken_explanation"],
                    },
                    "argument_realization": {
                        "temporal_scope": {
                            "source_entity_type": "temporal_scope",
                            "planner_owned": True,
                            "arguments": ["date", "period"],
                            "minimum_arguments": 1,
                            "contract": (
                                "Realize source-grounded human temporal scope into "
                                "Capability-local date and period arguments."
                            ),
                        }
                    },
                    "resource_contract": {
                        "plan_requires": [],
                        "plan_provides": ["resource_acquired"],
                        "final_delivery_owner": "planner_communicative_activity",
                    },
                },
            )
        )
        run_request = request(
            "今晚重庆天气怎么样？",
            goal_ids=[goal_id],
            goal_metadata={"output_mode": "information"},
        )
        canonical_goal = run_request.context["goal_association_resolution"][
            "new_goals"
        ][0]
        canonical_goal.update(
            {
                "description": "Report Chongqing weather tonight.",
                "resource_responsibility": {
                    "schema_version": 1,
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource": {
                        "kind": "information",
                        "description": "Chongqing weather tonight",
                        "quantity": "",
                        "attributes": {
                            "location": {
                                "name": "location",
                                "entity_type": "city",
                                "value": "重庆",
                                "confidence": 1.0,
                            },
                            "temporal_scope": {
                                "name": "temporal_scope",
                                "entity_type": "temporal_scope",
                                "value": "今晚",
                                "confidence": 1.0,
                            },
                        },
                    },
                    "source": {
                        "status": "provider_resolved",
                        "description": "",
                        "bindings": {},
                    },
                    "recipient": {"description": "requester"},
                    "delivery_mode": "spoken_explanation",
                    "metadata": {},
                },
            }
        )
        coverage_review = {
            "decision": "accept",
            "confidence": 1.0,
            "uncovered_requirements": [],
            "reason": "The repaired lookup preserves the source-grounded temporal scope.",
        }
        ollama = ScriptedOllama([initial, repaired, coverage_review])

        plan = asyncio.run(FastPlannerResolver(ollama, catalog).resolve(run_request))

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.steps[0].args["date"], "today")
        self.assertEqual(plan.steps[0].args["period"], "night")
        self.assertEqual(len(ollama.prompts), 3)
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn(
            "did not realize authoritative semantic scope",
            str(ollama.prompts[1][0]),
        )
        repair_system = str(ollama.prompts[1][1])
        self.assertIn(
            "trusted code projects only uniquely derivable duplicate provenance",
            repair_system,
        )
        self.assertIn("Do not relabel a transformed value", repair_system)
        repair_prompt = str(ollama.prompts[1][0])
        self.assertIn(
            "trusted code projects semantic_realization provenance",
            repair_prompt,
        )

    def test_declared_semantic_realization_provenance_is_host_projected(self):
        goal_id = "goal-weather"
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Check Chongqing weather tonight.",
            steps=[
                execute_step(
                    "weather",
                    "chromie.weather.lookup",
                    {
                        "location": "重庆",
                        "date": "today",
                        "period": "night",
                        "units": "metric",
                    },
                    [goal_id],
                    "Retrieve the requested weather.",
                )
            ],
            goal_outcomes={
                goal_id: execute_outcome(
                    goal_id, ["weather"], "The lookup covers the Goal."
                )
            },
            goal_satisfaction=exact_satisfaction([goal_id]),
            parameter_resolutions=[],
        )
        catalog = FakeCatalog()
        catalog.items.append(
            CatalogCapability(
                capability_id="chromie.weather.lookup",
                agent_id="chromie.weather",
                description="Retrieve current or short-range weather.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string", "enum": ["today", "tomorrow"]},
                        "period": {"type": "string", "enum": ["day", "night"]},
                        "units": {"type": "string", "enum": ["metric", "auto"]},
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                hints={
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                        "delivery_modes": ["spoken_explanation"],
                    },
                    "argument_realization": {
                        "temporal_scope": {
                            "source_entity_type": "temporal_scope",
                            "planner_owned": True,
                            "arguments": ["date", "period"],
                            "minimum_arguments": 1,
                        }
                    },
                    "resource_contract": {
                        "plan_requires": [],
                        "plan_provides": ["resource_acquired"],
                        "final_delivery_owner": "planner_communicative_activity",
                    },
                },
            )
        )
        run_request = request(
            "今晚重庆天气怎么样？",
            goal_ids=[goal_id],
            goal_metadata={"output_mode": "information"},
        )
        canonical_goal = run_request.context["goal_association_resolution"][
            "new_goals"
        ][0]
        canonical_goal.update(
            {
                "description": "Report Chongqing weather tonight.",
                "resource_responsibility": {
                    "schema_version": 1,
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource": {
                        "kind": "information",
                        "description": "Chongqing weather tonight",
                        "quantity": "",
                        "attributes": {
                            "location": {
                                "name": "location",
                                "entity_type": "city",
                                "value": "重庆",
                                "confidence": 1.0,
                            },
                            "temporal_scope": {
                                "name": "temporal_scope",
                                "entity_type": "temporal_scope",
                                "value": "今晚",
                                "confidence": 1.0,
                            },
                        },
                    },
                    "source": {"status": "provider_resolved", "description": "", "bindings": {}},
                    "recipient": {"description": "requester"},
                    "delivery_mode": "spoken_explanation",
                    "metadata": {},
                },
            }
        )
        ollama = ScriptedOllama(
            [
                raw,
                {
                    "decision": "accept",
                    "confidence": 1.0,
                    "uncovered_requirements": [],
                    "reason": "The declared realization preserves the temporal scope.",
                },
            ]
        )

        plan = asyncio.run(FastPlannerResolver(ollama, catalog).resolve(run_request))

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(len(ollama.prompts), 2)
        by_parameter = {item.parameter: item for item in plan.parameter_resolutions}
        self.assertEqual(by_parameter["date"].strategy, "semantic_realization")
        self.assertEqual(by_parameter["period"].strategy, "semantic_realization")
        self.assertEqual(by_parameter["date"].source_goal_ids, [goal_id])
        self.assertTrue(
            plan.metadata["parameter_provenance_normalization"][
                "semantic_plan_unchanged"
            ]
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

    def test_missing_numeric_provenance_is_normalized_without_replan(self):
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
            parameter_resolutions=[],
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
        self.assertEqual(plan.steps[0].args, {"duration_s": 2.0})
        self.assertEqual(len(ollama.prompts), 1)
        self.assertTrue(
            plan.metadata["parameter_provenance_normalization"][
                "semantic_plan_unchanged"
            ]
        )

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
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                hints={
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                    }
                },
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
            "do not emit separate parameter_resolutions for them",
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
            FastPlannerResolver(
                FakeOllama(raw), MissingParallelMetadataCatalog()
            ).resolve(run_request)
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

    def test_low_confidence_complete_plan_is_not_rejected_by_confidence_alone(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            confidence=0.01,
            goal_summary="Blink three times.",
            steps=[execute_step("blink", "soridormi.blink_eyes", {"count": 3}, ["goal-blink"], "Blink as requested.")],
            goal_outcomes={"goal-blink": execute_outcome("goal-blink", ["blink"], "The blink action exactly covers the Goal.")},
            goal_satisfaction=exact_satisfaction(["goal-blink"]),
        )
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("眨眼。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(len(plan.steps), 1)

    def test_non_common_or_non_executable_skill_escalates(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.95,"goal_ids":["goal-action"],"steps":[{"step_id":"invented","capability_id":"invented.skill","args":{},"timing":"sequential","source_goal_ids":["goal-action"]}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
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
        planner_request = request("你好。", goal_ids=["goal-greet"], goal_metadata={"output_mode": "speech"})
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

    def test_retained_evidence_followup_is_owned_by_single_planner_pass(self):
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
        ollama = ScriptedOllama([primary])
        planner_request = request(
            "那我出门需要带伞吗？",
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
            ).resolve(
                planner_request.model_copy(update={"context": context})
            )
        )

        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.response_text, primary["response_text"])
        self.assertEqual(
            plan.goal_outcomes[0].response_text,
            primary["goal_outcomes"][goal_id]["response_text"],
        )
        self.assertNotIn("communication_review", plan.metadata)
        self.assertEqual(len(ollama.prompts), 1)

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
                "timing": "sequential",
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
                "timing": "sequential",
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
                request("Tell me a short joke.", goal_ids=["goal-joke"], goal_metadata={"output_mode": "speech"})
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
                "timing": "sequential",
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





    def test_first_activity_decoder_exposes_capability_speech_and_clarification(self):
        schema = FastPlannerAdvanceModelOutput.model_json_schema()
        encoded = str(schema)
        self.assertIn("FastPlannerProgressAct", encoded)
        self.assertIn("FastPlannerCapabilityActivity", encoded)
        self.assertIn("FastPlannerClarificationAct", encoded)
        self.assertIn("FastPlannerCompleteResponseAct", encoded)

    def test_first_activity_contract_cannot_author_sentence_wording(self):
        schema = FastPlannerAdvanceModelOutput.model_json_schema()
        self.assertNotIn("response_text", json.dumps(schema, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
