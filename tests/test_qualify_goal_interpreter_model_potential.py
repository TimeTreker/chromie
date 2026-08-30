from __future__ import annotations

import unittest

from jsonschema import Draft202012Validator

from scripts.qualify_goal_interpreter_model_potential import (
    BINDING_DIMENSIONS,
    OUTPUT_MODES,
    SYSTEM_PROMPT,
    _project_candidate_payload,
    _response_schema,
)
from scripts.qualify_vllm_provider import QualificationFailure


class GoalInterpreterModelPotentialTests(unittest.TestCase):
    def test_model_potential_prompt_uses_general_rules_not_case_literals(self) -> None:
        self.assertIn("unfamiliar proper-name-like source surface", SYSTEM_PROMPT)
        self.assertIn("never invent a date", SYSTEM_PROMPT)
        for literal in ("天信", "重庆", "上海", "眨两下", "five meters"):
            self.assertNotIn(literal, SYSTEM_PROMPT)

    def test_simplified_schema_excludes_production_mechanics(self) -> None:
        schema = _response_schema()
        Draft202012Validator.check_schema(schema)
        responsibility = schema["properties"]["responsibilities"]["items"]

        self.assertEqual(set(responsibility["required"]), {"outcome", "output_mode", "bindings"})
        self.assertNotIn("source_evidence", responsibility["properties"])
        self.assertNotIn("relationship", responsibility["properties"])
        self.assertEqual(responsibility["properties"]["output_mode"]["enum"], OUTPUT_MODES)
        dimension = responsibility["properties"]["bindings"]["items"]["properties"]["dimension"]
        self.assertEqual(dimension["enum"], BINDING_DIMENSIONS)

    def test_candidate_projection_preserves_binding_ownership_and_coordination(self) -> None:
        decision, wire = _project_candidate_payload(
            {
                "responsibilities": [
                    {
                        "outcome": "look at the user",
                        "output_mode": "body_action",
                        "bindings": [
                            {"dimension": "entity", "value": "我"},
                            {"dimension": "duration", "value": 3},
                        ],
                    },
                    {
                        "outcome": "blink eyes",
                        "output_mode": "body_action",
                        "bindings": [{"dimension": "count", "value": 2}],
                    },
                ],
                "coordination": [{"kind": "parallel", "responsibility_indexes": [0, 1]}],
                "unresolved": [],
            }
        )

        self.assertEqual(decision["responsibilities"][0]["local_ref"], "r1")
        self.assertEqual(
            wire["responsibilities"][0]["binding_items"],
            {"entity": "我", "duration": 3},
        )
        self.assertEqual(wire["coordination"], [{"kind": "parallel", "refs": ["r1", "r2"]}])

    def test_candidate_projection_rejects_duplicate_binding_dimensions(self) -> None:
        payload = {
            "responsibilities": [
                {
                    "outcome": "walk",
                    "output_mode": "body_action",
                    "bindings": [
                        {"dimension": "duration", "value": 3},
                        {"dimension": "duration", "value": 5},
                    ],
                }
            ],
            "coordination": [],
            "unresolved": [],
        }

        with self.assertRaisesRegex(QualificationFailure, "duplicates binding"):
            _project_candidate_payload(payload)


if __name__ == "__main__":
    unittest.main()
