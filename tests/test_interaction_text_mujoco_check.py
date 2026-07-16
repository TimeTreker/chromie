from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from router.app.schema import RouteDecision
from scripts.interaction_text_mujoco_check import (
    INTERNAL_SPEECH_PATTERNS,
    _apply_soridormi_skill_timeout,
    _configure_environment,
    build_parser,
    build_debug_summary,
    collect_run_provenance,
    parse_expected_arg,
    safe_idle_errors,
    should_apply_cognitive_runtime,
    should_require_tts_speech,
    validate_contract,
    validate_speech_contract,
)
from shared.chromie_contracts.interaction import InteractionResponse


class InteractionTextMujocoCheckTests(unittest.TestCase):

    def test_goal_driven_runtime_is_default_with_explicit_legacy_opt_out(self) -> None:
        self.assertTrue(build_parser().parse_args([]).cognitive_runtime)
        self.assertFalse(
            build_parser().parse_args(["--no-cognitive-runtime"]).cognitive_runtime
        )
        self.assertEqual(
            build_parser()
            .parse_args(["--soridormi-repo", "/tmp/soridormi-checkout"])
            .soridormi_repo,
            "/tmp/soridormi-checkout",
        )

    def test_run_provenance_records_source_manifest_and_selected_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            manifest = root / "soridormi.json"
            manifest.write_text(
                '{"metadata":{"upstream_commit":"soridormi-abc"}}',
                encoding="utf-8",
            )
            soridormi_repo = root / "soridormi-checkout"
            with patch(
                "scripts.interaction_text_mujoco_check._git_text",
                side_effect=[
                    "chromie-def",
                    " M scripts/example.py",
                    "soridormi-abc",
                    "",
                ],
            ):
                provenance = collect_run_provenance(
                    manifest=manifest,
                    cognitive_runtime=True,
                    cognitive_apply_lanes="chat, robot_action",
                    soridormi_repo=soridormi_repo,
                    root=root,
                )

        self.assertEqual(provenance["chromie"]["revision"], "chromie-def")
        self.assertEqual(provenance["chromie"]["version"], "1.2.3")
        self.assertTrue(provenance["chromie"]["dirty"])
        self.assertEqual(
            provenance["soridormi"]["upstream_revision"],
            "soridormi-abc",
        )
        self.assertEqual(
            provenance["soridormi"]["checkout"],
            str(soridormi_repo.resolve()),
        )
        self.assertEqual(
            provenance["soridormi"]["checkout_revision"],
            "soridormi-abc",
        )
        self.assertFalse(provenance["soridormi"]["checkout_dirty"])
        self.assertEqual(
            provenance["semantic_runtime"],
            {
                "path": "goal_driven_cognitive_runtime",
                "configured_cognitive_runtime_mode": "apply",
                "cognitive_runtime_selected_for_route": True,
                "cognitive_apply_lanes": ["chat", "robot_action"],
            },
        )

    def test_cognitive_runtime_selection_matches_maintained_apply_lanes(self) -> None:
        robot_route = RouteDecision.model_validate(
            {
                "route": "robot_action",
                "intent": "robot_action",
                "confidence": 0.9,
                "source": "llm",
            }
        )
        clarify_route = RouteDecision.model_validate(
            {
                "route": "clarify",
                "intent": "clarify",
                "confidence": 0.5,
                "source": "llm",
            }
        )

        self.assertTrue(
            should_apply_cognitive_runtime(
                robot_route,
                enabled=True,
                apply_lanes="chat,robot_action",
            )
        )
        self.assertTrue(
            should_apply_cognitive_runtime(
                clarify_route,
                enabled=True,
                apply_lanes="chat,robot_action",
            )
        )
        self.assertFalse(
            should_apply_cognitive_runtime(
                robot_route,
                enabled=False,
                apply_lanes="chat,robot_action",
            )
        )

    def test_voice_mujoco_wrapper_exposes_runtime_selection(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "run_voice_mujoco_text_case.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("SEMANTIC_RUNTIME_FLAG=--cognitive-runtime", source)
        self.assertIn("--legacy-agent-runtime", source)
        self.assertIn('"$SEMANTIC_RUNTIME_FLAG"', source)

    def test_configure_environment_uses_isolated_conversation_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            args = argparse.Namespace(
                router_url="http://127.0.0.1:8091",
                agent_url="http://127.0.0.1:8092",
                auto_confirm_sim=True,
                speaker=False,
                manifest=Path("capabilities/soridormi.json"),
                cognitive_runtime=True,
                cognitive_apply_lanes="chat,robot_action",
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                conversation_id="ga-live-case-one",
            )

            _configure_environment(args, Path(temp_dir))

            self.assertEqual(os.environ["ORCH_CONVERSATION_ID"], "ga-live-case-one")
            self.assertEqual(os.environ["ORCH_COGNITIVE_RUNTIME_MODE"], "apply")
            self.assertEqual(os.environ["ORCH_COGNITIVE_EVIDENCE_ENABLED"], "1")

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
                            "task_type": "cognition.deep_think",
                            "priority": "normal",
                        },
                    ],
                    "thinking_ack_allowed": False,
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
                "1:deep_thought:cognition.deep_think priority=normal",
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

    def test_validate_speech_contract_rejects_internal_planner_leakage(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "speech": [
                    {
                        "text": (
                            "I'll walk forward quickly. Task Split: 1. "
                            "Execute soridormi.walk_forward now."
                        ),
                        "timing": "immediate",
                    }
                ]
            }
        )

        errors = validate_speech_contract(response, INTERNAL_SPEECH_PATTERNS)

        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("Task Split" in item for item in errors))
        self.assertTrue(any("soridormi" in item for item in errors))

    def test_validate_speech_contract_allows_natural_spoken_text(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "speech": [
                    {
                        "text": "Walking forward now. I will stop if anything looks unsafe.",
                        "timing": "immediate",
                    }
                ]
            }
        )

        errors = validate_speech_contract(response, INTERNAL_SPEECH_PATTERNS)

        self.assertEqual(errors, [])

    def test_safe_idle_errors_require_idle_non_emergency_status(self) -> None:
        self.assertEqual(
            safe_idle_errors(
                {
                    "safe_idle": True,
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
                        "safe_idle": False,
                        "active_task": {"plan_id": "x"},
                        "emergency_stop": True,
                        "fallen": True,
                    }
                )
            ),
            4,
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
