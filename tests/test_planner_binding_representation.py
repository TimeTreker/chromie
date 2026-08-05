from __future__ import annotations

import unittest

from agent.app.planner_contract import (
    PlannerModelOutput,
    validate_explicit_numeric_parameter_grounding,
    validate_goal_binding_argument_grounding,
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


def _weather_output(*, resolution_value=None, aspects=None) -> PlannerModelOutput:
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
                    "args": {"aspects": list(aspects or ASPECTS)},
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


class PlannerBindingRepresentationTests(unittest.TestCase):
    def test_typed_list_binding_accepts_equivalent_json_array_argument(self):
        validate_goal_binding_argument_grounding(
            _weather_output(),
            authoritative_goals=[_weather_goal()],
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
