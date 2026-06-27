from __future__ import annotations

import argparse
import unittest

from router.app.schema import RouteDecision
from scripts.interaction_text_mujoco_check import (
    _apply_soridormi_skill_timeout,
    build_debug_summary,
    parse_expected_arg,
    safe_idle_errors,
    should_require_tts_speech,
    validate_contract,
)
from shared.chromie_contracts.interaction import InteractionResponse


class InteractionTextMujocoCheckTests(unittest.TestCase):
    def test_parse_expected_arg_accepts_json_scalars(self) -> None:
        self.assertEqual(parse_expected_arg("0:vx_mps=0.2"), (0, "vx_mps", 0.2))
        self.assertEqual(parse_expected_arg("1:count=2"), (1, "count", 2))
        self.assertEqual(parse_expected_arg("2:label=left"), (2, "label", "left"))

    def test_parse_expected_arg_rejects_bad_shape(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_expected_arg("vx_mps=0.2")

    def test_validate_contract_checks_ordered_skills_and_args(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "robot_action",
                "intent": "compound_robot_action",
                "confidence": 0.99,
                "language": "en-US",
                "source": "catalog",
                "actions": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                    },
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                    },
                    {
                        "capability_id": "soridormi.turn_in_place",
                        "args": {"yaw_radps": -0.12},
                    },
                ],
            }
        )
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {
                            "vx_mps": 0.2,
                            "vy_mps": 0.0,
                            "yaw_radps": 0.0,
                            "duration_s": 10.0,
                        },
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.turn_in_place",
                        "args": {"yaw_radps": -0.12},
                        "timing": "sequential",
                    },
                ]
            }
        )

        errors = validate_contract(
            route=route,
            response=response,
            expected_route=None,
            expected_skills=[
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.turn_in_place",
            ],
            expect_no_skills=False,
            expected_args=[
                (0, "vx_mps", 0.2),
                (0, "duration_s", 10.0),
                (1, "count", 2),
                (2, "yaw_radps", -0.12),
            ],
            arg_tolerance=1e-6,
        )

        self.assertEqual(errors, [])

    def test_validate_contract_accepts_agent_skills_when_router_has_no_actions(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "robot_action",
                "intent": "robot_action",
                "confidence": 0.81,
                "language": "en-US",
                "source": "llm",
                "actions": [],
            }
        )
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "sequential",
                    },
                ]
            }
        )

        errors = validate_contract(
            route=route,
            response=response,
            expected_route=None,
            expected_skills=[
                "soridormi.walk_velocity",
                "soridormi.blink_eyes",
            ],
            expect_no_skills=False,
            expected_args=[
                (0, "vx_mps", 0.2),
                (1, "count", 2),
            ],
            arg_tolerance=1e-6,
        )

        self.assertEqual(errors, [])

    def test_build_debug_summary_describes_route_stages_tasks_and_skills(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "deep_thought",
                "intent": "deep_thought_low_confidence",
                "confidence": 0.0,
                "language": "en-US",
                "source": "llm",
                "candidate_capabilities": [
                    {"capability_id": "soridormi.walk_velocity"},
                    {"capability_id": "soridormi.blink_eyes"},
                ],
                "metadata": {
                    "route_stage_outputs": [
                        {"stage": "emergency_filter", "status": "passed", "tasks": []},
                        {
                            "stage": "quick_intent",
                            "status": "delegated",
                            "route": "deep_thought",
                            "intent": "deep_thought_low_confidence",
                            "tasks": [
                                {
                                    "source_stage": "quick_intent",
                                    "task_type": "cognition.delegate_deep_thought",
                                    "priority": "normal",
                                }
                            ],
                        },
                    ],
                    "task_list": [
                        {
                            "source_stage": "quick_intent",
                            "task_type": "cognition.delegate_deep_thought",
                            "priority": "normal",
                        },
                        {
                            "source_stage": "deep_thought",
                            "task_type": "speech.thinking_ack",
                            "priority": "normal",
                        },
                    ],
                },
            }
        )
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "sequential",
                    }
                ],
                "speech": [{"text": "Let me think.", "timing": "immediate"}],
            }
        )

        summary = build_debug_summary(
            route=route,
            response=response,
            errors=["route='deep_thought', expected 'robot_action'"],
        )

        self.assertIn("route=deep_thought", summary["route"])
        self.assertEqual(
            summary["candidate_capabilities"],
            ["soridormi.walk_velocity", "soridormi.blink_eyes"],
        )
        self.assertTrue(
            any("quick_intent:delegated" in item for item in summary["stages"])
        )
        self.assertEqual(
            summary["task_list"],
            [
                "0:quick_intent:cognition.delegate_deep_thought priority=normal",
                "1:deep_thought:speech.thinking_ack priority=normal",
            ],
        )
        self.assertEqual(summary["skills"], ["soridormi.blink_eyes"])
        self.assertEqual(summary["speech_items"], 1)
        self.assertEqual(len(summary["errors"]), 1)

    def test_validate_contract_reports_mismatch(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "chat",
                "intent": "general_conversation",
                "confidence": 0.5,
                "language": "en-US",
                "source": "fallback",
            }
        )
        response = InteractionResponse()

        errors = validate_contract(
            route=route,
            response=response,
            expected_route=None,
            expected_skills=["soridormi.walk_velocity"],
            expect_no_skills=False,
            expected_args=[(0, "vx_mps", 0.2)],
            arg_tolerance=1e-6,
        )

        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(any("route=" in item for item in errors))
        self.assertTrue(any("interaction skills mismatch" in item for item in errors))

    def test_validate_contract_accepts_chat_without_soridormi_skills(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "chat",
                "intent": "general_conversation",
                "confidence": 0.91,
                "language": "en-US",
                "source": "llm",
            }
        )
        response = InteractionResponse.model_validate(
            {"speech": [{"text": "Here is a short song.", "timing": "immediate"}]}
        )

        errors = validate_contract(
            route=route,
            response=response,
            expected_route="chat",
            expected_skills=[],
            expect_no_skills=True,
            expected_args=[],
            arg_tolerance=1e-6,
        )

        self.assertEqual(errors, [])

    def test_safe_idle_errors_require_idle_non_emergency_status(self) -> None:
        self.assertEqual(
            safe_idle_errors(
                {
                    "active_task": None,
                    "emergency_stop": False,
                    "fallen": False,
                }
            ),
            [],
        )
        self.assertEqual(
            len(
                safe_idle_errors(
                    {
                        "active_task": {"plan_id": "x"},
                        "emergency_stop": True,
                        "fallen": True,
                    }
                )
            ),
            3,
        )

    def test_tts_speech_requirement_skips_interrupt_routes(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "interrupt",
                "intent": "stop_current_output",
                "confidence": 0.99,
                "language": "en-US",
                "source": "rules",
                "should_speak": False,
            }
        )

        self.assertFalse(should_require_tts_speech(route, require_speech=True))

    def test_tts_speech_requirement_keeps_normal_speech_routes(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "chat",
                "intent": "general_conversation",
                "confidence": 0.91,
                "language": "en-US",
                "source": "llm",
                "should_speak": True,
            }
        )

        self.assertTrue(should_require_tts_speech(route, require_speech=True))
        self.assertFalse(should_require_tts_speech(route, require_speech=False))

    def test_apply_soridormi_timeout_sets_request_timeouts(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "chromie.unrelated",
                        "args": {},
                        "timing": "sequential",
                        "timeout_ms": 1000,
                    },
                ]
            }
        )

        updated = _apply_soridormi_skill_timeout(response, 120.0)

        self.assertEqual(updated.skills[0].timeout_ms, 120000)
        self.assertEqual(updated.skills[1].timeout_ms, 1000)


if __name__ == "__main__":
    unittest.main()
