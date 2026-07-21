from __future__ import annotations

import unittest

from scripts.outcome_observations import (
    collect_llm_integrity_violations,
    collect_observations,
    validate_expected_observations,
)


class OutcomeObservationTests(unittest.TestCase):
    def _summary(self) -> dict:
        return {
            "interaction_response": {
                "skills": [
                    {
                        "request_id": "req-blink",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2, "open_duration_s": 0.18},
                        "metadata": {
                            "source_goal_ids": ["goal-blink"],
                            "source": "goal_driven_canonical_plan",
                        },
                    },
                    {
                        "request_id": "req-attention",
                        "skill_id": "soridormi.look_at_person",
                        "args": {"target_ref": "current_speaker", "duration_s": 2.0},
                        "metadata": {
                            "auxiliary_social_attention": True,
                            "behavior_domain": "social_attention",
                        },
                    },
                ],
                "speech": [
                    {
                        "id": "speech-1",
                        "text": "I am listening.",
                        "metadata": {"phase": "final"},
                    }
                ],
            },
            "execution": {
                "results": [
                    {"request_id": "req-blink", "status": "completed"},
                    {"request_id": "req-attention", "status": "completed"},
                    {"request_id": "speech-1", "status": "completed"},
                ]
            },
            "cognitive_runtime": {
                "response_composition": {
                    "composition": {
                        "social_attention_plan": {
                            "purpose": "listening",
                            "speech_expression": {
                                "mode": "adapt",
                                "style": "warm",
                                "pacing": "slower",
                            },
                        }
                    }
                }
            },
        }

    def test_normalizes_capabilities_into_user_observable_events(self) -> None:
        observations = collect_observations(self._summary())

        self.assertEqual(observations[0]["type"], "social_attention.blink")
        self.assertEqual(
            observations[0]["args"],
            {"count": 2, "open_duration_s": 0.18},
        )
        self.assertEqual(observations[0]["interaction_role"], "explicit_user_goal")
        self.assertEqual(observations[1]["type"], "social_attention.gaze")
        self.assertEqual(observations[1]["interaction_role"], "auxiliary_expression")
        self.assertTrue(any(item["type"] == "speech.output" for item in observations))
        self.assertTrue(
            any(item["type"] == "social_attention.speech_expression" for item in observations)
        )

    def test_expected_observations_are_skill_id_independent(self) -> None:
        observations = collect_observations(self._summary())
        errors = validate_expected_observations(
            observations,
            [
                {"type": "social_attention.blink", "args": {"count": 2}},
                {"type": "speech.output"},
            ],
            sequence=["social_attention.blink", "speech.output"],
        )

        self.assertEqual(errors, [])

    def test_argument_ranges_capture_direction_without_freezing_safe_defaults(self) -> None:
        observations = [
            {
                "type": "locomotion.turn",
                "args": {"yaw_radps": -0.15, "duration_s": 2.0},
            }
        ]

        errors = validate_expected_observations(
            observations,
            [
                {
                    "type": "locomotion.turn",
                    "arg_ranges": {"yaw_radps": {"max": -0.000001}},
                }
            ],
        )

        self.assertEqual(errors, [])
        wrong_direction = validate_expected_observations(
            [
                {
                    "type": "locomotion.turn",
                    "args": {"yaw_radps": 0.15},
                }
            ],
            [
                {
                    "type": "locomotion.turn",
                    "arg_ranges": {"yaw_radps": {"max": -0.000001}},
                }
            ],
        )
        self.assertTrue(any("locomotion.turn" in item for item in wrong_direction))

    def test_sequence_uses_execution_receipts_not_plan_order(self) -> None:
        summary = self._summary()
        summary["execution"]["results"] = [
            {"request_id": "req-attention", "status": "completed"},
            {"request_id": "req-blink", "status": "completed"},
            {"request_id": "speech-1", "status": "completed"},
        ]

        observations = collect_observations(summary)
        actual_types = [item["type"] for item in observations]

        self.assertEqual(actual_types[:2], ["social_attention.gaze", "social_attention.blink"])
        errors = validate_expected_observations(
            observations,
            [],
            sequence=["social_attention.blink", "social_attention.gaze"],
        )
        self.assertTrue(any("order mismatch" in error for error in errors))

    def test_llm_integrity_gate_detects_timeout_and_truncation(self) -> None:
        summary = self._summary()
        summary["session_state"] = {
            "workflow_events": [
                {
                    "event": "llm_output_truncated",
                    "message": "done_reason=length",
                    "stage": "response_composer",
                }
            ]
        }
        summary["cognitive_runtime"]["metadata"] = {
            "stage_diagnostics": [
                {
                    "stage": "fast_planner",
                    "failure_class": "timeout",
                    "failure_domain": "llm_transport",
                }
            ]
        }

        violations = collect_llm_integrity_violations(summary)

        events = {item["event"] for item in violations}
        self.assertIn("llm_output_truncated", events)
        self.assertIn("timeout", events)

    def test_contract_failure_without_truncation_is_diagnostic_not_integrity_failure(self) -> None:
        summary = self._summary()
        summary["cognitive_runtime"]["metadata"] = {
            "stage_diagnostics": [
                {
                    "stage": "fast_planner",
                    "failure_class": "structured_output_validation",
                    "failure_domain": "model_contract",
                }
            ]
        }

        self.assertEqual(collect_llm_integrity_violations(summary), [])


if __name__ == "__main__":
    unittest.main()
