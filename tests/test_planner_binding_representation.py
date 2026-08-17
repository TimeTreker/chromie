from __future__ import annotations

import unittest

from agent.app.planner_contract import (
    EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
    PlannerDTOContractError,
    PlannerModelOutput,
    normalize_schema_default_parameter_provenance,
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


def _weather_output(*, resolution_value=None, aspects=None, extra_args=None) -> PlannerModelOutput:
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
                        **dict(extra_args or {}),
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
    attributes["time_frame"] = {
        "entity_type": "day_part",
        "value": "tonight",
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


class PlannerBindingRepresentationTests(unittest.TestCase):
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
                    }
                ],
            )

        message = str(raised.exception)
        self.assertIn("value=0.2", message)
        self.assertIn("value=10", message)

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

    def test_information_step_rejects_calendar_date_that_omits_day_part(self):
        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "omits authoritative temporal scope",
        ):
            validate_goal_binding_argument_grounding(
                _weather_output(extra_args={"date": "today"}),
                authoritative_goals=[_information_weather_goal()],
            )

    def test_information_step_preserves_exact_day_part_argument(self):
        validate_goal_binding_argument_grounding(
            _weather_output(
                extra_args={"date": "today", "period": "tonight"}
            ),
            authoritative_goals=[_information_weather_goal()],
        )

    def test_information_step_preserves_exact_afternoon_argument(self):
        goal = _information_weather_goal()
        goal["resource_responsibility"]["resource"]["attributes"]["time_frame"] = {
            "entity_type": "day_part",
            "value": "afternoon",
        }
        validate_goal_binding_argument_grounding(
            _weather_output(
                extra_args={"date": "today", "period": "afternoon"}
            ),
            authoritative_goals=[goal],
        )

    def test_information_step_preserves_compound_date_and_day_part(self):
        goal = _information_weather_goal()
        attributes = goal["resource_responsibility"]["resource"]["attributes"]
        attributes["date"] = {
            "entity_type": "date",
            "value": "today",
        }
        attributes["time_frame"] = {
            "entity_type": "day_part",
            "value": "evening",
        }

        validate_goal_binding_argument_grounding(
            _weather_output(
                extra_args={"date": "today", "period": "evening"}
            ),
            authoritative_goals=[goal],
        )

    def test_information_step_rejects_omitted_compound_date_dimension(self):
        goal = _information_weather_goal()
        attributes = goal["resource_responsibility"]["resource"]["attributes"]
        attributes["date"] = {
            "entity_type": "date",
            "value": "today",
        }
        attributes["time_frame"] = {
            "entity_type": "day_part",
            "value": "evening",
        }

        with self.assertRaisesRegex(
            PlannerDTOContractError,
            "value='today'",
        ):
            validate_goal_binding_argument_grounding(
                _weather_output(extra_args={"period": "evening"}),
                authoritative_goals=[goal],
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


if __name__ == "__main__":
    unittest.main()
