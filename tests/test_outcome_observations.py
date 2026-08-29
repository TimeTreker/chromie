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
                "capabilities": [
                    {
                        "request_id": "req-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "args": {"count": 2, "open_duration_s": 0.18},
                        "metadata": {
                            "source_goal_ids": ["goal-blink"],
                            "source": "goal_driven_canonical_plan",
                        },
                    },
                    {
                        "request_id": "req-attention",
                        "capability_id": "soridormi.look_at_person",
                        "args": {"target_ref": "current_speaker", "duration_s": 2.0},
                        "metadata": {
                            "auxiliary_plan_activity": True,
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
            "cognitive_runtime": {},
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

    def test_external_capability_completion_is_observable_evidence(self) -> None:
        summary = {
            "interaction_response": {
                "capabilities": [
                    {
                        "request_id": "req-weather",
                        "capability_id": "chromie.weather.lookup",
                        "args": {
                            "location": "重庆",
                            "date": "today",
                            "period": "morning",
                        },
                        "metadata": {"source_goal_ids": ["goal-weather"]},
                    }
                ],
                "speech": [],
            },
            "execution": {
                "results": [
                    {"request_id": "req-weather", "status": "completed"}
                ]
            },
        }

        observations = collect_observations(summary)

        self.assertEqual(len(observations), 1)
        self.assertEqual(
            observations[0]["type"],
            "capability.chromie.weather.lookup",
        )
        self.assertEqual(observations[0]["status"], "completed")
        self.assertEqual(observations[0]["args"]["period"], "morning")

    def test_argument_ranges_capture_direction_without_freezing_safe_defaults(self) -> None:
        observations = [
            {
                "type": "locomotion.turn",
                "args": {"yaw_radps": 0.15, "duration_s": 2.0},
            }
        ]

        errors = validate_expected_observations(
            observations,
            [
                {
                    "type": "locomotion.turn",
                    "arg_ranges": {"yaw_radps": {"min": 0.000001}},
                }
            ],
        )

        self.assertEqual(errors, [])
        wrong_direction = validate_expected_observations(
            [
                {
                    "type": "locomotion.turn",
                    "args": {"yaw_radps": -0.15},
                }
            ],
            [
                {
                    "type": "locomotion.turn",
                    "arg_ranges": {"yaw_radps": {"min": 0.000001}},
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
                    "stage": "planner_communicative_activity_validation",
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

    def test_completed_detached_tts_is_observed_from_host_workflow(self) -> None:
        summary = {"interaction_response": {"capabilities": [], "speech": []}}
        summary["session_state"] = {
            "workflow_events": [
                {
                    "event": "tts_schedule",
                    "elapsed_ms": 1200.0,
                    "message": "tts_schedule: order=0 chars=16 text='I blinked twice!'",
                },
                {
                    "event": "playback_end",
                    "elapsed_ms": 2400.0,
                    "message": "playback_end: order=0 played_tts=1",
                },
            ]
        }

        self.assertEqual(
            collect_observations(summary),
            [
                {
                    "sequence": 0,
                    "type": "speech.output",
                    "domain": "speech",
                    "status": "completed",
                    "interaction_role": "task_response",
                    "text": "I blinked twice!",
                    "metadata": {
                        "source": "session_tts_playback",
                        "tts_order": 0,
                        "workflow_event_index": 0,
                        "elapsed_ms": 1200.0,
                    },
                    "planned_sequence": 0,
                }
            ],
        )

    def test_tts_chunks_count_as_one_model_authored_speech_activity(self) -> None:
        summary = self._summary()
        summary["interaction_response"]["capabilities"] = []
        summary["interaction_response"]["speech"][0]["text"] = (
            "Why don't scientists trust atoms? Because they make up everything!"
        )
        summary["execution"]["results"] = []
        summary["session_state"] = {
            "workflow_events": [
                {
                    "event": "tts_schedule",
                    "elapsed_ms": 1000.0,
                    "message": (
                        "tts_schedule: order=0 "
                        'text="Why don\'t scientists trust atoms?"'
                    ),
                },
                {
                    "event": "tts_schedule",
                    "elapsed_ms": 1001.0,
                    "message": (
                        "tts_schedule: order=1 "
                        "text='Because they make up everything!'"
                    ),
                },
                {
                    "event": "playback_end",
                    "message": "playback_end: order=0 played_tts=1",
                },
                {
                    "event": "playback_end",
                    "message": "playback_end: order=1 played_tts=2",
                },
            ]
        }

        observations = collect_observations(summary)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["type"], "speech.output")
        self.assertEqual(observations[0]["status"], "completed")
        self.assertEqual(
            observations[0]["text"],
            "Why don't scientists trust atoms? Because they make up everything!",
        )

    def test_delivered_speech_before_capability_receipt_keeps_actual_chronology(self) -> None:
        summary = self._summary()
        summary["interaction_response"]["capabilities"] = [
            {
                "request_id": "req-weather",
                "capability_id": "chromie.weather.lookup",
                "args": {"location": "重庆"},
                "metadata": {"source_goal_ids": ["goal-weather"]},
            }
        ]
        summary["interaction_response"]["speech"] = []
        summary["execution"]["results"] = [
            {"request_id": "req-weather", "status": "completed"}
        ]
        summary["timings_ms"] = {"agent_ms": 74000.0}
        summary["session_state"] = {
            "workflow_events": [
                {
                    "event": "tts_schedule",
                    "elapsed_ms": 5300.0,
                    "message": "tts_schedule: order=0 text='I checked: rain is certain.'",
                },
                {
                    "event": "playback_end",
                    "elapsed_ms": 10500.0,
                    "message": "playback_end: order=0 played_tts=1",
                },
            ]
        }

        observations = collect_observations(summary)

        self.assertEqual(
            [item["type"] for item in observations],
            ["speech.output", "capability.chromie.weather.lookup"],
        )

    def test_scheduled_but_unplayed_tts_is_not_observed(self) -> None:
        summary = {"interaction_response": {"capabilities": [], "speech": []}}
        summary["session_state"] = {
            "workflow_events": [
                {
                    "event": "tts_schedule",
                    "message": "tts_schedule: order=0 text='not delivered'",
                }
            ]
        }

        self.assertEqual(collect_observations(summary), [])


if __name__ == "__main__":
    unittest.main()
