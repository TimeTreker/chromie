from __future__ import annotations

import unittest

from agent.app.capabilities.validator import normalize_args_for_schema, validate_args_for_schema


class CapabilityArgsValidatorTests(unittest.TestCase):
    def test_normalizes_schema_enum_adverbs_recursively(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "string",
                    "enum": ["slow", "normal", "medium", "quick", "fast_limited"],
                },
                "nested": {
                    "type": "object",
                    "properties": {
                        "pace": {
                            "type": "string",
                            "enum": ["slow", "normal"],
                        }
                    },
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pace": {
                                "type": "string",
                                "enum": ["normal", "quick"],
                            }
                        },
                    },
                },
            },
        }

        normalized, changed = normalize_args_for_schema(
            {
                "speed": "quickly",
                "nested": {"pace": "slowly"},
                "steps": [{"pace": "normal speed"}],
                "unknown": "quickly",
            },
            schema,
        )

        self.assertTrue(changed)
        self.assertEqual(normalized["speed"], "quick")
        self.assertEqual(normalized["nested"]["pace"], "slow")
        self.assertEqual(normalized["steps"][0]["pace"], "normal")
        self.assertEqual(normalized["unknown"], "quickly")

    def test_preserves_unmatched_enum_values_for_runtime_validation(self) -> None:
        normalized, changed = normalize_args_for_schema(
            {"speed": "reckless"},
            {
                "type": "object",
                "properties": {
                    "speed": {
                        "type": "string",
                        "enum": ["slow", "normal", "quick"],
                    }
                },
            },
        )

        self.assertFalse(changed)
        self.assertEqual(normalized["speed"], "reckless")

    def test_reports_unknown_fields_when_schema_forbids_them(self) -> None:
        errors = validate_args_for_schema(
            {"duration_s": 5.0},
            {
                "type": "object",
                "properties": {"speed": {"type": "string"}},
                "additionalProperties": False,
            },
        )

        self.assertEqual(errors, ["args has unknown fields: ['duration_s']"])

    def test_reports_nested_enum_and_required_errors(self) -> None:
        errors = validate_args_for_schema(
            {"speed": "reckless", "steps": [{}]},
            {
                "type": "object",
                "properties": {
                    "speed": {"type": "string", "enum": ["slow", "normal"]},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"duration_s": {"type": "number"}},
                            "required": ["duration_s"],
                        },
                    },
                },
            },
        )

        self.assertIn("args.speed must be one of ['slow', 'normal']", errors)
        self.assertIn("args.steps[0] is missing required field 'duration_s'", errors)


if __name__ == "__main__":
    unittest.main()
