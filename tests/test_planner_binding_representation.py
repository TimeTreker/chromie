from __future__ import annotations

import unittest

from jsonschema import Draft202012Validator

from agent.app.planner_prompt import EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT
from agent.app.planner_model_contract import (
    PlannerDTOContractError,
    PlannerModelOutput,
)
from agent.app.planner_schema import (
    canonical_goal_binding_argument_response_schema,
    canonical_plan_response_schema,
)
from agent.app.planner_validation import (
    normalize_common_planner_output,
    normalize_detached_parameter_resolutions,
    normalize_schema_default_parameter_provenance,
    qualify_capability_catalog_for_typed_binding_values,
    validate_explicit_numeric_parameter_grounding,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
)


ASPECTS = ["temperature", "rain", "air conditioning need"]


def _satisfaction(goal_id: str) -> dict:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": [goal_id],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The planned lookup exactly covers the goal.",
    }


def _weather_output(
    *,
    resolution_value=None,
    aspects=None,
    extra_args=None,
    semantic_realizations=(),
) -> PlannerModelOutput:
    goal_id = "goal-weather"
    parameter_resolutions = []
    if resolution_value is not None:
        parameter_resolutions.append(
            {
                "step_id": "weather",
                "parameter": "aspects",
                "strategy": "user_supplied",
                "value": resolution_value,
                "confidence": 1.0,
                "blocking": False,
                "rationale": "Copied from the authoritative Goal binding.",
                "source_goal_ids": [goal_id],
            }
        )
    realized_args = dict(extra_args or {})
    for parameter in semantic_realizations:
        parameter_resolutions.append(
            {
                "step_id": "weather",
                "parameter": parameter,
                "strategy": "semantic_realization",
                "value": realized_args[parameter],
                "confidence": 1.0,
                "blocking": False,
                "rationale": (
                    "Realized the source-grounded human temporal scope under "
                    "the selected Capability contract."
                ),
                "source_goal_ids": [goal_id],
            }
        )
    return PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Look up tonight's Chongqing weather.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {
                        "aspects": list(aspects or ASPECTS),
                        **realized_args,
                    },
                    "timing": "sequential",
                    "source_goal_ids": [goal_id],
                    "reason_summary": "Fetch the requested weather aspects.",
                }
            ],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": parameter_resolutions,
            "goal_outcomes": {
                goal_id: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["weather"],
                    "satisfaction": _satisfaction(goal_id),
                    "rationale": "The lookup is the exact required capability.",
                }
            },
            "goal_satisfaction": _satisfaction(goal_id),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
    )


def _weather_goal() -> dict:
    return {
        "goal_id": "goal-weather",
        "description": "Check temperature, rain, and air conditioning need.",
        "source_text": "今天晚上重庆热不热，要不要开空调？",
        "object": {
            "bindings": {
                "aspects": {
                    "entity_type": "list",
                    "value": "temperature, rain, air conditioning need",
                }
            }
        },
        "success_criteria": [],
    }


def _information_weather_goal() -> dict:
    goal = _weather_goal()
    attributes = dict(goal["object"]["bindings"])
    attributes["temporal_scope"] = {
        "entity_type": "temporal_scope",
        "value": "今晚",
    }
    goal["object"]["bindings"] = {}
    goal["resource_responsibility"] = {
        "responsibility_type": "acquire_and_deliver_resource",
        "resource": {
            "kind": "information",
            "description": "Chongqing weather tonight",
            "attributes": attributes,
        },
        "source": {"status": "provider_resolved"},
        "recipient": {"description": "requester"},
        "delivery_mode": "spoken_explanation",
    }
    return goal


def _weather_capability_with_temporal_realization() -> dict:
    return {
        "capability_id": "chromie.weather.lookup",
        "hints": {
            "argument_realization": {
                "temporal_scope": {
                    "source_entity_type": "temporal_scope",
                    "planner_owned": True,
                    "arguments": ["date", "period"],
                    "minimum_arguments": 1,
                    "contract": (
                        "Interpret source-grounded human temporal scope after this "
                        "Capability is selected; a current-local-night scope realizes "
                        "as date=today and period=night."
                    ),
                }
            }
        },
    }


class PlannerBindingRepresentationTests(unittest.TestCase):
    def test_numeric_prompt_requires_quantitative_pace_argument(self):
        self.assertIn(
            "enum labels never preserve an explicit quantitative pace",
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        )

    def test_decoder_projects_exact_same_name_speed_binding(self):
        base = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-walk"],
            allowed_capability_ids=["soridormi.walk_forward"],
            capability_input_schemas={
                "soridormi.walk_forward": {
                    "type": "object",
                    "properties": {
                        "speed": {
                            "type": "string",
                            "enum": ["slow", "normal", "quick"],
                        },
                        "duration_s": {"type": "number"},
                    },
                    "additionalProperties": False,
                }
            },
        )
        schema = canonical_goal_binding_argument_response_schema(
            base,
            authoritative_goals=[
                {
                    "goal_id": "goal-walk",
                    "object": {
                        "bindings": {
                            "speed": {
                                "entity_type": "speed",
                                "value": "quick",
                            }
                        }
                    },
                }
            ],
        )
        branch = schema["$defs"]["PlannerModelStep"]["oneOf"][0]
        args = branch["properties"]["args"]

        self.assertEqual(args["properties"]["speed"], {"const": "quick"})
        self.assertIn("speed", args["required"])

    def test_same_name_supported_goal_binding_cannot_be_omitted(self):
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_forward",
                        "args": {},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-walk"],
                    }
                ],
                "goal_satisfaction": _satisfaction("goal-walk"),
            }
        )
        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "omitted same-name authoritative Goal binding",
        ):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=[
                    {
                        "goal_id": "goal-walk",
                        "object": {
                            "bindings": {
                                "speed": {
                                    "entity_type": "speed",
                                    "value": "quick",
                                }
                            }
                        },
                    }
                ],
                capabilities=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "speed": {
                                    "type": "string",
                                    "enum": ["slow", "normal", "quick"],
                                }
                            },
                        },
                    }
                ],
            )

    def test_numeric_grounding_prompt_forbids_sibling_goal_borrowing(self):
        self.assertIn(
            "Never borrow a numeric literal or typed binding from a sibling Goal",
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        )
        self.assertIn(
            "strategy=schema_default and no source_goal_ids",
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        )

    def test_exact_catalog_default_repairs_false_user_provenance_only(self):
        raw = {
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
        }
        normalized, repairs = normalize_schema_default_parameter_provenance(
            raw,
            authoritative_goals=[
                {
                    "goal_id": "goal-turn",
                    "description": "Turn in place.",
                    "success_criteria": ["Turn in place."],
                    "object": {},
                },
                {
                    "goal_id": "goal-look",
                    "description": "Look at me for 2 seconds.",
                    "success_criteria": ["Look at me for 2 seconds."],
                    "object": {
                        "bindings": {
                            "duration_s": {
                                "entity_type": "duration_seconds",
                                "value": "2",
                            }
                        }
                    },
                },
            ],
            capability_payload=[
                {
                    "capability_id": "soridormi.turn_in_place",
                    "input_schema": {
                        "properties": {
                            "duration_s": {"type": "number", "default": 2.0}
                        }
                    },
                }
            ],
        )

        resolution = normalized["parameter_resolutions"][0]
        self.assertEqual(resolution["strategy"], "schema_default")
        self.assertEqual(resolution["source_goal_ids"], [])
        self.assertEqual(len(repairs), 1)
        self.assertEqual(raw["parameter_resolutions"][0]["strategy"], "user_supplied")

    def test_detached_weather_time_resolution_is_removed_without_rewriting_step(self):
        raw = {
            "steps": [
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {
                        "location": "重庆",
                        "date": "today",
                        "period": "morning",
                        "units": "metric",
                    },
                }
            ],
            "parameter_resolutions": [
                {
                    "step_id": "weather",
                    "parameter": "location",
                    "strategy": "user_supplied",
                    "value": "重庆",
                    "blocking": False,
                    "source_goal_ids": ["goal-weather"],
                },
                {
                    "step_id": "weather",
                    "parameter": "time",
                    "strategy": "user_supplied",
                    "value": "morning",
                    "blocking": False,
                    "source_goal_ids": ["goal-weather"],
                },
            ],
        }

        normalized, repairs = normalize_detached_parameter_resolutions(raw)

        self.assertEqual(normalized["steps"], raw["steps"])
        self.assertEqual(
            [item["parameter"] for item in normalized["parameter_resolutions"]],
            ["location"],
        )
        self.assertEqual(
            repairs,
            [
                {
                    "normalization": "detached_parameter_resolution_removed",
                    "step_id": "weather",
                    "parameter": "time",
                    "step_argument_keys": ["date", "location", "period", "units"],
                    "equivalent_step_argument_keys": ["period"],
                }
            ],
        )
        self.assertEqual(len(raw["parameter_resolutions"]), 2)

    def test_blocking_resolution_without_step_argument_is_not_removed(self):
        raw = {
            "steps": [
                {
                    "step_id": "weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"date": "today"},
                }
            ],
            "parameter_resolutions": [
                {
                    "step_id": "weather",
                    "parameter": "location",
                    "strategy": "ask_user",
                    "value": None,
                    "blocking": True,
                    "source_goal_ids": ["goal-weather"],
                }
            ],
        }

        normalized, repairs = normalize_detached_parameter_resolutions(raw)

        self.assertEqual(normalized, raw)
        self.assertEqual(repairs, [])

    def test_nondefault_value_does_not_repair_false_user_provenance(self):
        raw = {
            "steps": [
                {
                    "step_id": "turn",
                    "capability_id": "soridormi.turn_in_place",
                    "args": {"duration_s": 3.0},
                }
            ],
            "parameter_resolutions": [
                {
                    "step_id": "turn",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 3.0,
                    "source_goal_ids": ["goal-turn"],
                }
            ],
        }
        normalized, repairs = normalize_schema_default_parameter_provenance(
            raw,
            authoritative_goals=[
                {"goal_id": "goal-turn", "description": "Turn in place."}
            ],
            capability_payload=[
                {
                    "capability_id": "soridormi.turn_in_place",
                    "input_schema": {
                        "properties": {
                            "duration_s": {"type": "number", "default": 2.0}
                        }
                    },
                }
            ],
        )

        self.assertEqual(
            normalized["parameter_resolutions"][0]["strategy"],
            "user_supplied",
        )
        self.assertEqual(repairs, [])

    def test_numeric_grounding_reports_all_missing_goal_values_together(self):
        goal_id = "goal-walk"
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Walk at 0.2 for 10 seconds.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Execute the requested bounded walk.",
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
                        "satisfaction": _satisfaction(goal_id),
                        "rationale": "The walk capability covers the request.",
                    }
                },
                "goal_satisfaction": _satisfaction(goal_id),
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

        with self.assertRaises(ValueError) as raised:
            validate_explicit_numeric_parameter_grounding(
                output,
                authoritative_goals=[
                    {
                        "goal_id": goal_id,
                        "description": "Walk at 0.2 speed for 10 seconds.",
                        "success_criteria": [],
                        "object": {
                            "bindings": {
                                "speed": {"value": 0.2},
                                "duration": {"value": 10.0},
                            }
                        },
                    }
                ],
            )

        message = str(raised.exception)
        self.assertIn("value=0.2", message)
        self.assertIn("value=10", message)

    def test_numeric_grounding_distinguishes_missing_work_argument_from_provenance(self):
        goal_id = "goal-walk"
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Walk at 0.2 for 10 seconds.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"duration_s": 10.0},
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Execute the requested bounded walk.",
                    }
                ],
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [
                    {
                        "step_id": "walk",
                        "parameter": "duration_s",
                        "strategy": "user_supplied",
                        "value": 10.0,
                        "source_goal_ids": [goal_id],
                    }
                ],
                "goal_outcomes": {
                    goal_id: {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["walk"],
                        "satisfaction": _satisfaction(goal_id),
                        "rationale": "The walk capability covers the request.",
                    }
                },
                "goal_satisfaction": _satisfaction(goal_id),
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "explicit numeric Goal value is absent from every executable step argument",
        ):
            validate_explicit_numeric_parameter_grounding(
                output,
                authoritative_goals=[
                    {
                        "goal_id": goal_id,
                        "description": "Walk at 0.2 speed for 10 seconds.",
                        "success_criteria": [],
                        "object": {
                            "bindings": {
                                "speed": {"value": 0.2},
                                "duration": {"value": 10.0},
                            }
                        },
                    }
                ],
            )

    def test_exact_structured_resource_numeric_scope_needs_no_flat_resolution(self):
        goal_id = "goal-milk"
        resource = {
            "kind": "physical_object",
            "description": "bottle of milk",
            "quantity": "1",
            "attributes": {},
        }
        source = {
            "status": "known",
            "description": "ahead of you about 50 meters",
            "bindings": {
                "location": {
                    "name": "location",
                    "entity_type": "relative_location",
                    "value": "ahead of you about 50 meters",
                    "confidence": 1.0,
                }
            },
        }
        recipient = {"description": "requester", "referent_id": None}
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Bring the milk.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "fetch",
                        "capability_id": "soridormi.acquire_and_deliver_resource",
                        "args": {
                            "resource": resource,
                            "source": source,
                            "recipient": recipient,
                        },
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Acquire and deliver the resource.",
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
                        "step_ids": ["fetch"],
                        "satisfaction": _satisfaction(goal_id),
                        "rationale": "The exact resource contract is executable.",
                    }
                },
                "goal_satisfaction": _satisfaction(goal_id),
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

        validate_explicit_numeric_parameter_grounding(
            output,
            authoritative_goals=[
                {
                    "goal_id": goal_id,
                    "description": (
                        "bring a bottle of milk from ahead of you about 50 meters"
                    ),
                    "source_text": (
                        "there is a bottle of milk ahead of you about 50 meters, "
                        "please bring it to me"
                    ),
                    "success_criteria": [],
                    "resource_responsibility": {
                        "resource": resource,
                        "source": source,
                        "recipient": recipient,
                        "delivery_mode": "physical_handover",
                    },
                }
            ],
        )

    def test_numeric_user_supplied_resolution_rejects_false_goal_provenance(self):
        goal_id = "goal-walk"
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Walk at 0.2 for 10 seconds.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "walk",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {
                            "vx_mps": 0.2,
                            "duration_s": 10.0,
                            "yaw_radps": 0.15,
                        },
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Execute the requested bounded walk.",
                    }
                ],
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [
                    {
                        "step_id": "walk",
                        "parameter": "vx_mps",
                        "strategy": "user_supplied",
                        "value": 0.2,
                        "confidence": 1.0,
                        "blocking": False,
                        "rationale": "Copied from the Goal.",
                        "source_goal_ids": [goal_id],
                    },
                    {
                        "step_id": "walk",
                        "parameter": "duration_s",
                        "strategy": "user_supplied",
                        "value": 10.0,
                        "confidence": 1.0,
                        "blocking": False,
                        "rationale": "Copied from the Goal.",
                        "source_goal_ids": [goal_id],
                    },
                    {
                        "step_id": "walk",
                        "parameter": "yaw_radps",
                        "strategy": "user_supplied",
                        "value": 0.15,
                        "confidence": 1.0,
                        "blocking": False,
                        "rationale": "Incorrectly attributed to the Goal.",
                        "source_goal_ids": [goal_id],
                    },
                ],
                "goal_outcomes": {
                    goal_id: {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["walk"],
                        "satisfaction": _satisfaction(goal_id),
                        "rationale": "The walk capability covers the request.",
                    }
                },
                "goal_satisfaction": _satisfaction(goal_id),
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "not present in its authoritative source Goal",
        ):
            validate_explicit_numeric_parameter_grounding(
                output,
                authoritative_goals=[
                    {
                        "goal_id": goal_id,
                        "description": "Walk at 0.2 speed for 10 seconds.",
                        "success_criteria": [],
                    }
                ],
            )

    def test_worded_count_uses_typed_numeric_binding_as_provenance(self):
        goal_id = "goal-blink"
        output = PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Blink twice.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Blink the requested count.",
                    }
                ],
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [
                    {
                        "step_id": "blink",
                        "parameter": "count",
                        "strategy": "user_supplied",
                        "value": 2,
                        "confidence": 1.0,
                        "blocking": False,
                        "rationale": "Copied from the typed Goal binding.",
                        "source_goal_ids": [goal_id],
                    }
                ],
                "goal_outcomes": {
                    goal_id: {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["blink"],
                        "satisfaction": _satisfaction(goal_id),
                        "rationale": "The blink capability covers the request.",
                    }
                },
                "goal_satisfaction": _satisfaction(goal_id),
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )
        goal = {
            "goal_id": goal_id,
            "description": "Blink twice.",
            "success_criteria": [],
            "object": {
                "bindings": {
                    "count": {
                        "entity_type": "count",
                        "value": "2",
                    }
                }
            },
        }

        validate_explicit_numeric_parameter_grounding(
            output,
            authoritative_goals=[goal],
        )
        validate_goal_binding_argument_grounding(
            output,
            authoritative_goals=[goal],
        )

    def test_typed_list_binding_accepts_equivalent_json_array_argument(self):
        validate_goal_binding_argument_grounding(
            _weather_output(),
            authoritative_goals=[_weather_goal()],
        )

    def test_information_step_rejects_provider_temporal_args_without_realization_contract(self):
        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "omits authoritative temporal scope",
        ):
            validate_goal_binding_argument_grounding(
                _weather_output(
                    extra_args={"date": "today", "period": "night"},
                    semantic_realizations=("date", "period"),
                ),
                authoritative_goals=[_information_weather_goal()],
            )

    def test_information_step_accepts_capability_owned_temporal_realization(self):
        validate_goal_binding_argument_grounding(
            _weather_output(
                extra_args={"date": "today", "period": "night"},
                semantic_realizations=("date", "period"),
            ),
            authoritative_goals=[_information_weather_goal()],
            capabilities=[_weather_capability_with_temporal_realization()],
        )

    def test_information_step_requires_planner_provenance_for_semantic_realization(self):
        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "semantic realization requires explicit Planner provenance",
        ):
            validate_goal_binding_argument_grounding(
                _weather_output(
                    extra_args={"date": "today", "period": "night"},
                ),
                authoritative_goals=[_information_weather_goal()],
                capabilities=[_weather_capability_with_temporal_realization()],
            )

    def test_information_step_accepts_declared_fixed_temporal_scope(self):
        goal = _information_weather_goal()
        goal["resource_responsibility"]["resource"]["attributes"] = {
            "time": {
                "entity_type": "time",
                "value": "now",
            }
        }
        output = _weather_output()
        output.steps[0].capability_id = "chromie.clock.local"
        output.steps[0].args = {}

        validate_goal_binding_argument_grounding(
            output,
            authoritative_goals=[goal],
            capabilities=[
                {
                    "capability_id": "chromie.clock.local",
                    "hints": {
                        "semantic_scope": {
                            "fixed_temporal_scope": {
                                "entity_types": ["time"],
                                "values": ["now"],
                            }
                        }
                    },
                }
            ],
        )

    def test_local_clock_fixed_now_scope_accepts_source_language_temporal_value(self):
        goal = _information_weather_goal()
        goal["resource_responsibility"]["resource"]["attributes"] = {
            "information_domain": {
                "entity_type": "information_domain",
                "value": "local_clock",
            },
            "time": {"entity_type": "temporal_scope", "value": "现在"},
        }
        output = _weather_output()
        output.steps[0].capability_id = "chromie.clock.local"
        output.steps[0].args = {}

        validate_goal_binding_argument_grounding(
            output,
            authoritative_goals=[goal],
            capabilities=[
                {
                    "capability_id": "chromie.clock.local",
                    "hints": {
                        "semantic_scope": {
                            "domain": "local_clock",
                            "fixed_temporal_scope": {
                                "entity_types": ["time", "temporal_scope"],
                                "values": ["now"],
                            },
                        }
                    },
                }
            ],
        )

    def test_typed_list_binding_accepts_chinese_list_separators(self):
        goal = _weather_goal()
        goal["object"]["bindings"]["aspects"]["value"] = (
            "temperature、rain；air conditioning need"
        )
        validate_goal_binding_argument_grounding(
            _weather_output(),
            authoritative_goals=[goal],
        )

    def test_typed_capability_argument_rejects_omitted_numeric_speed(self):
        goal = _weather_goal()
        goal["object"]["bindings"] = {
            "speed": {"entity_type": "speed", "value": "0.2"}
        }
        output = _weather_output(extra_args={"duration_s": 10.0})
        output.steps[0].capability_id = "soridormi.walk_velocity"

        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "omitted authoritative typed Goal binding",
        ):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=[goal],
                capabilities=[
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "vx_mps": {
                                    "type": "number",
                                    "x-chromie-entity-type": "speed",
                                },
                                "duration_s": {"type": "number"},
                            },
                        },
                    }
                ],
            )

    def test_numeric_speed_omits_qualitative_capability_but_keeps_numeric_one(self):
        goal = _weather_goal()
        goal["object"]["bindings"] = {
            "speed": {"entity_type": "speed", "value": "0.2"}
        }
        capabilities = [
            {
                "capability_id": "soridormi.walk_forward",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "speed": {
                            "type": "string",
                            "enum": ["slow", "normal", "quick"],
                        }
                    },
                },
            },
            {
                "capability_id": "soridormi.walk_velocity",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {
                            "type": "number",
                            "minimum": -0.03,
                            "maximum": 0.25,
                            "x-chromie-entity-type": "speed",
                        }
                    },
                },
            },
        ]

        qualified = qualify_capability_catalog_for_typed_binding_values(
            capabilities,
            authoritative_goals=[goal],
        )

        self.assertEqual(
            [item["capability_id"] for item in qualified],
            ["soridormi.walk_velocity"],
        )

    def test_typed_list_binding_still_rejects_different_items(self):
        with self.assertRaisesRegex(
            ValueError,
            "planner step argument contradicts authoritative Goal binding",
        ):
            validate_goal_binding_argument_grounding(
                _weather_output(
                    aspects=["temperature", "humidity", "air conditioning need"]
                ),
                authoritative_goals=[_weather_goal()],
            )

    def test_parameter_resolution_accepts_same_typed_list_in_string_form(self):
        validate_explicit_numeric_parameter_grounding(
            _weather_output(
                resolution_value="temperature, rain, air conditioning need"
            ),
            authoritative_goals=[_weather_goal()],
        )

    def test_string_user_supplied_resolution_requires_typed_goal_binding(self):
        raw = _weather_output().model_dump(mode="python")
        raw["steps"][0]["args"]["location"] = "重庆"
        raw["parameter_resolutions"].append(
            {
                "step_id": "weather",
                "parameter": "location",
                "strategy": "user_supplied",
                "value": "重庆",
                "confidence": 1.0,
                "blocking": False,
                "rationale": "Claimed as user supplied.",
                "source_goal_ids": ["goal-weather"],
            }
        )
        output = PlannerModelOutput.model_validate(raw)

        with self.assertRaisesRegex(
            ValueError,
            "not present in authoritative typed Goal bindings",
        ):
            validate_user_supplied_parameter_provenance(
                output,
                authoritative_goals=[_weather_goal()],
            )

    def test_string_user_supplied_resolution_cannot_replace_typed_location(self):
        goal = _weather_goal()
        goal["object"]["bindings"]["location"] = {
            "entity_type": "location",
            "value": "上海",
        }
        raw = _weather_output().model_dump(mode="python")
        raw["steps"][0]["args"]["location"] = "重庆"
        raw["parameter_resolutions"].append(
            {
                "step_id": "weather",
                "parameter": "location",
                "strategy": "user_supplied",
                "value": "重庆",
                "confidence": 1.0,
                "blocking": False,
                "rationale": "Claimed as user supplied.",
                "source_goal_ids": ["goal-weather"],
            }
        )
        with self.assertRaisesRegex(
            ValueError,
            "not present in authoritative typed Goal bindings",
        ):
            validate_user_supplied_parameter_provenance(
                PlannerModelOutput.model_validate(raw),
                authoritative_goals=[goal],
            )

        raw["steps"][0]["args"]["location"] = "上海"
        raw["parameter_resolutions"][-1]["value"] = "上海"
        validate_user_supplied_parameter_provenance(
            PlannerModelOutput.model_validate(raw),
            authoritative_goals=[goal],
        )

    def test_scalar_string_is_not_split_without_list_shape_evidence(self):
        output = _weather_output(aspects=["temperature", "rain"])
        output.steps[0].args["label"] = ["alpha", "beta"]
        goal = _weather_goal()
        goal["object"]["bindings"]["label"] = {
            "entity_type": "text",
            "value": "alpha, beta",
        }
        with self.assertRaisesRegex(
            ValueError,
            "planner step argument contradicts authoritative Goal binding",
        ):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=[goal],
            )

    def test_count_provenance_preserves_declared_argument_identity(self):
        for binding_name in ("count", "repeats"):
            for mapping in ("absent", "named", "typed", "declared"):
                with self.subTest(binding=binding_name, mapping=mapping):
                    goal = _weather_goal()
                    goal["object"]["bindings"] = {
                        binding_name: {"entity_type": "count", "value": 2}
                    }
                    output = _weather_output()
                    step = output.steps[0]
                    step.args = {"duration_s": 2.0}
                    properties = {"duration_s": {"type": "number", "default": 2}}
                    capability = {"capability_id": step.capability_id,
                                  "input_schema": {"properties": properties}}
                    parameter = "count" if mapping == "named" else "repetitions"
                    if mapping != "absent":
                        properties[parameter] = {"type": "integer", "default": 2}
                        step.args[parameter] = 2
                    if mapping == "typed":
                        properties[parameter]["x-chromie-entity-type"] = "count"
                    if mapping == "declared":
                        capability["hints"] = {"argument_realization": {"repeat": {
                            "source_entity_type": "count", "arguments": [parameter],
                            "minimum_arguments": 1,
                        }}}
                    raw = output.model_dump(mode="json")
                    normalized, _ = normalize_common_planner_output(
                        raw, authoritative_goals=[goal], capability_payload=[capability]
                    )
                    self.assertEqual(normalized["steps"], raw["steps"])
                    self.assertNotIn("duration_s", {
                        item["parameter"] for item in normalized["parameter_resolutions"]
                    })
                    admitted = PlannerModelOutput.model_validate(normalized)
                    if mapping == "absent":
                        with self.assertRaisesRegex(ValueError, "no declared count input"):
                            validate_goal_binding_argument_grounding(
                                admitted, authoritative_goals=[goal], capabilities=[capability]
                            )
                    else:
                        validate_goal_binding_argument_grounding(
                            admitted, authoritative_goals=[goal], capabilities=[capability]
                        )
                        validate_explicit_numeric_parameter_grounding(
                            admitted, authoritative_goals=[goal]
                        )
                        self.assertEqual(normalized["parameter_resolutions"][0]["parameter"], parameter)

    def test_equal_count_and_duration_keep_independent_provenance(self):
        goal = _weather_goal()
        goal["object"]["bindings"] = {
            "count": {"entity_type": "count", "value": 2},
            "duration_s": {"entity_type": "duration", "value": 2.0},
        }
        output = _weather_output()
        output.steps[0].args = {"count": 2, "duration_s": 2.0}
        capability = {"capability_id": output.steps[0].capability_id,
                      "input_schema": {"properties": {
                          "count": {"type": "integer"}, "duration_s": {"type": "number"}
                      }}}
        normalized, _ = normalize_common_planner_output(
            output.model_dump(mode="json"), authoritative_goals=[goal],
            capability_payload=[capability],
        )
        self.assertEqual({item["parameter"] for item in normalized["parameter_resolutions"]},
                         {"count", "duration_s"})
        admitted = PlannerModelOutput.model_validate(normalized)
        validate_goal_binding_argument_grounding(
            admitted, authoritative_goals=[goal], capabilities=[capability]
        )
        validate_explicit_numeric_parameter_grounding(admitted, authoritative_goals=[goal])

        # The same raw parameter claim is false when duration was never supplied.
        del goal["object"]["bindings"]["duration_s"]
        again, _ = normalize_common_planner_output(
            normalized, authoritative_goals=[goal], capability_payload=[capability]
        )
        with self.assertRaisesRegex(ValueError, "provenance crosses count identity"):
            validate_goal_binding_argument_grounding(
                PlannerModelOutput.model_validate(again),
                authoritative_goals=[goal], capabilities=[capability],
            )

    def test_structured_resource_count_is_not_execution_repetition(self):
        goal = _information_weather_goal()
        resource = goal["resource_responsibility"]["resource"]
        resource["attributes"] = {"count": {"entity_type": "count", "value": 2}}
        output = _weather_output()
        output.steps[0].args = {"resource": resource}
        capability = {"capability_id": output.steps[0].capability_id,
                      "input_schema": {"properties": {"resource": {"type": "object"}}}}
        validate_goal_binding_argument_grounding(
            output, authoritative_goals=[goal], capabilities=[capability]
        )
        validate_explicit_numeric_parameter_grounding(output, authoritative_goals=[goal])

    def test_count_decoder_restricts_ownership_without_removing_sibling_capability(self):
        goal = _weather_goal()
        goal["object"]["bindings"] = {"count": {"entity_type": "count", "value": 2}}
        other = {"goal_id": "goal-other", "object": {"bindings": {}}}
        capability = {"capability_id": "provider.action", "input_schema": {
            "type": "object", "properties": {"duration_s": {"type": "number"}},
            "additionalProperties": False,
        }}
        base = canonical_plan_response_schema(
            planner_tier="fast", expected_goal_ids=[goal["goal_id"], other["goal_id"]],
            allowed_capability_ids=[capability["capability_id"]],
            capability_input_schemas={capability["capability_id"]: capability["input_schema"]},
        )
        schema = canonical_goal_binding_argument_response_schema(
            base, authoritative_goals=[goal, other], capabilities=[capability]
        )
        Draft202012Validator.check_schema(schema)
        branch = schema["$defs"]["PlannerModelStep"]["oneOf"][0]
        step = _weather_output().steps[0].model_dump(mode="json")
        step.update(capability_id=capability["capability_id"], args={"duration_s": 2})
        self.assertFalse(Draft202012Validator(branch).is_valid(step))
        step["source_goal_ids"] = [other["goal_id"]]
        Draft202012Validator(branch).validate(step)

        single_base = canonical_plan_response_schema(
            planner_tier="fast", expected_goal_ids=[goal["goal_id"]],
            allowed_capability_ids=[capability["capability_id"]],
            capability_input_schemas={capability["capability_id"]: capability["input_schema"]},
        )
        single = canonical_goal_binding_argument_response_schema(
            single_base, authoritative_goals=[goal], capabilities=[capability]
        )
        Draft202012Validator.check_schema(single)
        self.assertEqual(single["properties"]["steps"]["maxItems"], 0)


if __name__ == "__main__":
    unittest.main()
