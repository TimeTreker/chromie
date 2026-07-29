from __future__ import annotations

import unittest

from agent.app.planner_contract import (
    canonical_goal_grounding,
    validate_goal_binding_argument_grounding,
    validate_planner_model_output,
)


def _satisfaction(goal_id: str) -> dict:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": [goal_id],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The plan exactly covers the resolved Goal.",
    }


def _execute_output(*, goal_id: str, skill_id: str, args: dict) -> dict:
    return {
        "goal_summary": "Query weather for the resolved location.",
        "goal_outcomes": {
            goal_id: {
                "disposition": "execute",
                "coverage": "complete",
                "response_text": "",
                "unresolved": [],
                "step_ids": ["weather-read-operation"],
                "satisfaction": _satisfaction(goal_id),
                "rationale": "Execute the grounded read.",
            }
        },
        "steps": [
            {
                "step_id": "weather-read-operation",
                "skill_id": skill_id,
                "args": args,
                "timing": "parallel",
                "source_goal_ids": [goal_id],
                "reason_summary": "Execute the grounded read.",
            }
        ],
        "goal_satisfaction": _satisfaction(goal_id),
        "disposition": "execute",
        "coverage": "complete",
        "confidence": 1.0,
        "response_text": "",
        "escalation_reason": "",
        "unresolved": [],
        "parameter_resolutions": [],
        "plan_relation": "exact",
        "user_confirmation_required": False,
    }


class ScopedReferentPlannerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.goal_id = "goal-neixiang-weather"
        self.context = {
            "active_goal_snapshots": [],
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": self.goal_id,
                        "description": "查询今天内乡是否下雨。",
                        "source_text": "今天那边下雨了没有？",
                        "constraints": {},
                        "success_criteria": ["告知用户今天内乡是否下雨。"],
                        "object": {
                            "bindings": {
                                "location": {
                                    "name": "location",
                                    "entity_type": "location",
                                    "value": "内乡",
                                    "referent_id": "ref-neixiang",
                                    "confidence": 1.0,
                                },
                                "date": {
                                    "name": "date",
                                    "entity_type": "date",
                                    "value": "today",
                                    "confidence": 1.0,
                                },
                            }
                        },
                    }
                ],
            },
        }

    def test_canonical_goal_grounding_preserves_typed_bindings(self) -> None:
        grounding = canonical_goal_grounding(self.context)
        self.assertEqual(
            grounding[0]["object"]["bindings"]["location"]["value"],
            "内乡",
        )

    def test_weather_step_cannot_replace_neixiang_with_chongqing(self) -> None:
        output = validate_planner_model_output(
            _execute_output(
                goal_id=self.goal_id,
                skill_id="chromie.weather.lookup",
                args={"location": "重庆", "date": "today"},
            ),
            planner_tier="fast",
            expected_goal_ids_for_turn=[self.goal_id],
        )
        with self.assertRaisesRegex(ValueError, "authoritative Goal binding"):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=canonical_goal_grounding(self.context),
            )

    def test_exact_neixiang_weather_step_is_accepted(self) -> None:
        output = validate_planner_model_output(
            _execute_output(
                goal_id=self.goal_id,
                skill_id="chromie.weather.lookup",
                args={"location": "内乡", "date": "today"},
            ),
            planner_tier="fast",
            expected_goal_ids_for_turn=[self.goal_id],
        )
        validate_goal_binding_argument_grounding(
            output,
            authoritative_goals=canonical_goal_grounding(self.context),
        )

    def test_memory_retrieval_requires_all_exact_goal_bindings(self) -> None:
        output = validate_planner_model_output(
            _execute_output(
                goal_id=self.goal_id,
                skill_id="chromie.memory.retrieve_verified_tool_result",
                args={
                    "evidence_id": "evidence-chongqing",
                    "tool_id": "chromie.weather.lookup",
                    "material_args": {"location": "重庆", "date": "today"},
                    "max_age_s": 900,
                },
            ),
            planner_tier="fast",
            expected_goal_ids_for_turn=[self.goal_id],
        )
        with self.assertRaisesRegex(ValueError, "verified-memory retrieval"):
            validate_goal_binding_argument_grounding(
                output,
                authoritative_goals=canonical_goal_grounding(self.context),
            )


if __name__ == "__main__":
    unittest.main()
