from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts.general_ability_acceptance import (
    DEFAULT_MANIFEST,
    LiveCaseRef,
    TextScenarioCase,
    _run_live_case,
    build_parser,
    level_a_keys,
    live_case_ids,
    load_manifest,
    main,
    manifest_summary,
    run_level_a,
    _live_case_namespace,
    select_ability_classes,
    validate_live_text_result,
    validate_manifest,
)
from scripts.interaction_text_mujoco_check import build_parser as build_text_check_parser


class GeneralAbilityAcceptanceTests(unittest.TestCase):
    def test_default_manifest_declares_core_ability_classes(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)

        ability_ids = {item.ability_id for item in manifest.ability_classes}

        self.assertIn("robust_intent_understanding", ability_ids)
        self.assertIn("stable_capability_grounding", ability_ids)
        self.assertIn("natural_uncertainty_handling", ability_ids)
        self.assertIn("composable_action_planning", ability_ids)
        self.assertIn("truthful_embodied_speech", ability_ids)
        self.assertIn("evidence_coverage_and_claim_discipline", ability_ids)
        self.assertIn("multi_goal_daily_life", ability_ids)
        self.assertIn(
            "evidence_bound_cognitive_turn_closure",
            ability_ids,
        )
        self.assertEqual(validate_manifest(manifest), [])
        self.assertGreaterEqual(len(level_a_keys(manifest.ability_classes)), 20)
        live_ids = live_case_ids(manifest.ability_classes)
        self.assertIn("wal_forward_typo_walk", live_ids)
        self.assertIn("multi_goal_look_then_blink", live_ids)
        self.assertIn("weather_then_chinese_walk_blink_song", live_ids)
        self.assertIn("beijing_rain_evidence_bound_result", live_ids)

    def test_live_validation_requires_structured_pending_work_speech(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="今天北京下雨了没有？",
            expected_routes=("tool",),
            require_speech=False,
            require_fast_speech=True,
            expected_fast_speech_purposes=("acknowledge_and_check",),
        )
        summary = {
            "route": {"route": "tool", "fast_speech": None},
            "interaction_response": {"speech": [], "skills": []},
            "preview_only": True,
            "cognitive_runtime": {},
        }

        missing = validate_live_text_result(case, summary)
        self.assertTrue(any("omitted" in item for item in missing))

        summary["route"]["fast_speech"] = {
            "text": "我看看北京今天会不会下雨。",
            "purpose": "acknowledge_and_check",
            "commitment": "checking_only",
            "must_not_claim_completion": True,
        }
        self.assertEqual(validate_live_text_result(case, summary), [])

    def test_live_validation_can_forbid_pre_effect_fast_speech(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="今天北京下雨了没有？",
            expected_routes=("tool",),
            require_speech=False,
            forbid_fast_speech=True,
        )
        summary = {
            "route": {
                "route": "tool",
                "fast_speech": {
                    "text": "北京今天已经下雨了。",
                    "purpose": "acknowledge_and_check",
                    "commitment": "checking_only",
                    "must_not_claim_completion": True,
                },
            },
            "interaction_response": {"speech": [], "skills": []},
            "preview_only": True,
            "cognitive_runtime": {},
        }

        errors = validate_live_text_result(case, summary)
        self.assertTrue(any("forbidden pre-effect" in item for item in errors))

        summary["route"]["fast_speech"] = None
        self.assertEqual(validate_live_text_result(case, summary), [])

    def test_manifest_rejects_contradictory_fast_speech_policy(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = manifest.ability_classes[0]
        contradictory = TextScenarioCase(
            case_id="contradictory",
            text="Check something.",
            require_fast_speech=True,
            forbid_fast_speech=True,
        )
        patched_ability = replace(
            ability,
            live_text_cases=(
                *ability.live_text_cases,
                LiveCaseRef(case=contradictory),
            ),
        )
        patched_manifest = replace(
            manifest,
            ability_classes=(patched_ability, *manifest.ability_classes[1:]),
        )

        errors = validate_manifest(patched_manifest, validate_level_a_sources=False)
        self.assertTrue(any("both required and forbidden" in item for item in errors))

    def test_retained_voice_incident_is_a_two_turn_live_episode(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "composable_action_planning"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "weather_then_chinese_walk_blink_song"
        )

        self.assertEqual(len(case.turns), 2)
        self.assertEqual(case.turns[0].case_id, "weather_context")
        self.assertEqual(case.turns[1].language, "zh-CN")
        self.assertEqual(case.turns[1].min_new_goal_count, 3)
        self.assertEqual(case.turns[1].min_goal_outcome_count, 3)
        self.assertEqual(
            case.turns[1].forbidden_plan_agent_skills,
            (
                "chromie.grounded-external-information",
                "chromie.weather-information",
            ),
        )

    def test_manifest_summary_labels_scope_and_counts(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)

        summary = manifest_summary(manifest)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["mode"], "check")
        self.assertGreater(summary["ability_class_count"], 0)
        self.assertGreater(summary["level_a_case_count"], 0)
        self.assertGreater(summary["live_text_case_count"], 0)

    def test_select_ability_classes_rejects_unknown_id(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)

        selected = select_ability_classes(manifest, ["deterministic_safety_controls"])

        self.assertEqual([item.ability_id for item in selected], ["deterministic_safety_controls"])
        with self.assertRaisesRegex(ValueError, "unknown ability class"):
            select_ability_classes(manifest, ["missing"])

    def test_level_a_runner_writes_rollup_for_selected_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "title": "test manifest",
                        "ability_classes": [
                            {
                                "id": "controls",
                                "title": "Controls",
                                "general_rule": "Stops must be deterministic.",
                                "minimum_level_a_cases": 1,
                                "root_cause_boundaries": ["GoalInterpreter/intent"],
                                "level_a_scenarios": [
                                    {
                                        "key": "goal_interpretation/polite_stop",
                                        "rationale": "Polite stop remains interrupt.",
                                    }
                                ],
                                "live_text_cases": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "--mode",
                    "level-a",
                    "--ability-manifest",
                    str(manifest_path),
                    "--no-write",
                ]
            )

            summary = run_level_a(args)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["evidence_level"], "A")
        self.assertIn("deterministic file-backed evidence", summary["claim_scope"])
        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["ability_classes"][0]["id"], "controls")
        self.assertEqual(summary["ability_classes"][0]["cases"][0]["key"], "goal_interpretation/polite_stop")


    def test_daily_multi_goal_level_a_class_passes(self) -> None:
        args = build_parser().parse_args(
            [
                "--mode",
                "level-a",
                "--ability-class",
                "multi_goal_daily_life",
                "--no-write",
            ]
        )

        summary = run_level_a(args)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["case_count"], 10)
        self.assertEqual(summary["passed"], 10)

    def test_evidence_bound_cognitive_turn_closure_level_a_class_passes(
        self,
    ) -> None:
        args = build_parser().parse_args(
            [
                "--mode",
                "level-a",
                "--ability-class",
                "evidence_bound_cognitive_turn_closure",
                "--no-write",
            ]
        )

        summary = run_level_a(args)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["evidence_level"], "A")
        self.assertEqual(summary["case_count"], 6)
        self.assertEqual(summary["passed"], 6)
        self.assertIn(
            "deterministic file-backed evidence",
            summary["claim_scope"],
        )

    def test_live_case_namespace_can_select_goal_driven_runtime(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = ability.live_text_cases[0].case
        args = build_parser().parse_args(
            [
                "--mode",
                "live-text",
                "--goal-driven-runtime",
                "apply",
                "--cognitive-apply-lanes",
                "robot_action",
                "--soridormi-repo",
                "/tmp/soridormi-checkout",
                "--no-write",
            ]
        )

        namespace = _live_case_namespace(args, case, Path("/tmp/multi-goal"))

        self.assertTrue(namespace.cognitive_runtime)
        self.assertEqual(namespace.cognitive_apply_lanes, "robot_action")
        self.assertEqual(namespace.soridormi_repo, "/tmp/soridormi-checkout")
        self.assertEqual(
            namespace.conversation_id,
            "ga-live-multi_goal_look_then_blink",
        )
        self.assertEqual(args.assertion_scope, "user-outcome")
        self.assertEqual(namespace.expect_skill, [])
        self.assertEqual(
            [item["type"] for item in case.expected_observations],
            ["social_attention.gaze", "social_attention.blink"],
        )

        full_args = build_parser().parse_args(
            ["--mode", "live-text", "--assertion-scope", "full"]
        )
        full_namespace = _live_case_namespace(
            full_args, case, Path("/tmp/multi-goal-full")
        )
        self.assertEqual(
            full_namespace.expect_skill,
            ["soridormi.look_at_person", "soridormi.blink_eyes"],
        )
        self.assertEqual(case.expected_terminal_planner_tier, "fast")
        self.assertEqual(case.expected_fast_planner_path, "terminal")
        self.assertFalse(case.expect_deep_planner_invoked)
        self.assertTrue(case.expect_no_fast_contract_failure)

    def test_live_validation_enforces_fast_terminal_path(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = ability.live_text_cases[-1].case
        summary = {
            "route": {"route": "robot_action"},
            "interaction_response": {
                "skills": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "metadata": {},
                    }
                ],
                "speech": [{"text": "*Blinks twice* Why did the robot laugh?"}],
            },
            "cognitive_runtime": {
                "terminal_plan": {"planner_tier": "deep"},
                "timings_ms": {"deep_planner": 10000.0},
                "metadata": {
                    "fast_planner_path": "contract_failure",
                    "deep_planner_invoked": True,
                    "stage_diagnostics": [
                        {
                            "stage": "fast_planner",
                            "failure_class": "structured_output_validation",
                        }
                    ],
                },
            },
        }

        errors = validate_live_text_result(case, summary, assertion_scope="full")

        self.assertTrue(any("terminal planner tier mismatch" in item for item in errors))
        self.assertTrue(any("Fast Planner path mismatch" in item for item in errors))
        self.assertTrue(any("Deep Planner invocation mismatch" in item for item in errors))
        self.assertTrue(any("Fast Planner contract failure" in item for item in errors))

    def test_user_outcome_scope_retains_internal_path_mismatch_as_diagnostic(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = ability.live_text_cases[0].case
        summary = {
            "route": {"route": "chat"},
            "interaction_response": {
                "skills": [
                    {
                        "request_id": "look",
                        "skill_id": "soridormi.look_at_person",
                        "args": {"duration_s": 2.0},
                        "metadata": {"source_goal_ids": ["goal-look"]},
                    },
                    {
                        "request_id": "blink",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "metadata": {"source_goal_ids": ["goal-blink"]},
                    },
                ],
                "speech": [{"id": "speech", "text": "I will look and blink."}],
            },
            "execution": {
                "results": [
                    {"request_id": "look", "status": "completed"},
                    {"request_id": "blink", "status": "completed"},
                    {"request_id": "speech", "status": "completed"},
                ]
            },
            "cognitive_runtime": {
                "terminal_plan": {"planner_tier": "deep"},
                "timings_ms": {"deep_planner": 1000.0},
                "metadata": {
                    "fast_planner_path": "contract_failure",
                    "deep_planner_invoked": True,
                },
            },
        }

        errors = validate_live_text_result(case, summary)

        self.assertEqual(errors, [])
        self.assertTrue(summary["user_outcome"]["ok"])
        self.assertTrue(summary["user_outcome"]["internal_diagnostics"])

    def test_failed_execution_receipt_cannot_satisfy_user_outcome(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = ability.live_text_cases[0].case
        summary = {
            "route": {"route": "robot_action"},
            "interaction_response": {
                "skills": [
                    {
                        "request_id": "look",
                        "skill_id": "soridormi.look_at_person",
                        "args": {"duration_s": 2.0},
                        "metadata": {"source_goal_ids": ["goal-look"]},
                    },
                    {
                        "request_id": "blink",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "metadata": {"source_goal_ids": ["goal-blink"]},
                    },
                ],
                "speech": [],
            },
            "execution": {
                "results": [
                    {"request_id": "look", "status": "completed"},
                    {"request_id": "blink", "status": "failed"},
                ]
            },
            "cognitive_runtime": {"metadata": {}},
        }

        errors = validate_live_text_result(case, summary)

        self.assertTrue(any("social_attention.blink" in item for item in errors))
        self.assertFalse(summary["user_outcome"]["ok"])

    def test_llm_truncation_fails_user_outcome_even_when_actions_complete(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = ability.live_text_cases[0].case
        summary = {
            "route": {"route": "robot_action"},
            "interaction_response": {"skills": [], "speech": [{"text": "Done."}]},
            "session_state": {
                "workflow_events": [
                    {
                        "event": "llm_output_truncated",
                        "severity": "error",
                        "message": "llm_output_truncated: done_reason=length",
                    }
                ]
            },
        }

        errors = validate_live_text_result(case, summary)

        self.assertTrue(any("LLM integrity gate failed" in item for item in errors))
        self.assertFalse(summary["user_outcome"]["llm_integrity"]["ok"])

    def test_incident_scorecard_hard_fails_goal_omission_and_stale_skill(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "composable_action_planning"
        )
        episode = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "weather_then_chinese_walk_blink_song"
        )
        case = episode.turns[1]
        summary = {
            "preview_only": True,
            "route": {"route": "robot_action"},
            "interaction_response": {
                "skills": [
                    {
                        "request_id": "walk",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0},
                        "metadata": {},
                    }
                ],
                "speech": [{"text": "我给你唱首歌。"}],
            },
            "cognitive_runtime": {
                "goal_association": {
                    "new_goals": [{"goal_id": "goal-action"}],
                },
                "fast_plan": {
                    "selected_agent_skills": [
                        {"agent_skill_id": "chromie.weather-information"}
                    ]
                },
                "terminal_plan": {
                    "goal_outcomes": [{"goal_id": "goal-action"}],
                },
                "metadata": {},
            },
        }

        errors = validate_live_text_result(case, summary)
        evaluation = summary["diagnostic_evaluation"]

        self.assertTrue(any("omitted independent" in item for item in errors))
        self.assertTrue(any("stale or unrelated" in item for item in errors))
        self.assertFalse(evaluation["passed"])
        self.assertEqual(
            evaluation["earliest_suspect_boundary"],
            "goal_association",
        )
        self.assertEqual(evaluation["metrics"]["goal_omission_rate"], 0.6667)
        self.assertTrue(evaluation["hard_gate_failures"])

    def test_incident_scorecard_caps_fatal_cognitive_runtime_failure(self) -> None:
        case = TextScenarioCase(case_id="runtime-failure", text="do it")
        summary = {
            "preview_only": True,
            "route": {"route": "robot_action"},
            "interaction_response": {
                "skills": [],
                "speech": [{"text": "I could not complete that."}],
            },
            "cognitive_runtime": {
                "status": "error",
                "goal_association": {"new_goals": []},
                "terminal_plan": {"goal_outcomes": []},
                "metadata": {
                    "failure_stage": "deep_planner",
                    "failure_class": "structured_output_validation",
                },
            },
        }

        errors = validate_live_text_result(case, summary)
        evaluation = summary["diagnostic_evaluation"]

        self.assertTrue(any("cognitive runtime" in item for item in errors))
        self.assertLessEqual(evaluation["overall_score"], 40)
        self.assertEqual(evaluation["axes"]["runtime_integrity"], 0)
        self.assertEqual(
            evaluation["earliest_suspect_boundary"],
            "cognitive_runtime:deep_planner",
        )

    def test_multi_turn_live_case_reuses_one_conversation(self) -> None:
        case = TextScenarioCase(
            case_id="episode",
            text="",
            turns=(
                TextScenarioCase(case_id="first", text="first"),
                TextScenarioCase(case_id="second", text="second"),
            ),
        )
        args = build_parser().parse_args(
            ["--mode", "live-text", "--no-write"]
        )
        summaries = [
            {
                "ok": True,
                "errors": [],
                "preview_only": True,
                "route": {"route": "chat"},
                "interaction_response": {
                    "skills": [],
                    "speech": [{"text": "ok"}],
                },
                "cognitive_runtime": {
                    "goal_association": {"new_goals": []},
                    "terminal_plan": {"goal_outcomes": []},
                    "metadata": {},
                },
            },
            {
                "ok": True,
                "errors": [],
                "preview_only": True,
                "route": {"route": "chat"},
                "interaction_response": {
                    "skills": [],
                    "speech": [{"text": "ok"}],
                },
                "cognitive_runtime": {
                    "goal_association": {"new_goals": []},
                    "terminal_plan": {"goal_outcomes": []},
                    "metadata": {},
                },
            },
        ]
        sequence = AsyncMock(return_value=summaries)

        with patch(
            "scripts.general_ability_acceptance.run_check_sequence",
            sequence,
        ):
            result = asyncio.run(
                _run_live_case(args, case, Path("/tmp/episode-evidence"))
            )

        self.assertTrue(result["ok"], result["errors"])
        namespaces = sequence.await_args.args[0]
        self.assertEqual(len(namespaces), 2)
        self.assertEqual(
            namespaces[0].conversation_id,
            namespaces[1].conversation_id,
        )
        self.assertEqual(namespaces[0].text, "first")
        self.assertEqual(namespaces[1].text, "second")
        self.assertEqual(result["diagnostic_evaluation"]["overall_score"], 100)

    def test_live_case_namespace_matches_text_checker_argument_contract(self) -> None:
        args = build_parser().parse_args(["--mode", "live-text"])
        manifest = load_manifest(DEFAULT_MANIFEST)
        case = manifest.ability_classes[0].live_text_cases[0].case

        namespace = _live_case_namespace(args, case, Path("/tmp/contract-check"))
        checker_defaults = build_text_check_parser().parse_args([])

        self.assertEqual(args.soridormi_repo, "")
        self.assertEqual(
            set(vars(checker_defaults)) - set(vars(namespace)),
            set(),
        )

    def test_live_text_defaults_allow_full_qualification_pipeline(self) -> None:
        args = build_parser().parse_args(["--mode", "live-text"])

        self.assertEqual(args.goal_driven_runtime, "apply")
        self.assertEqual(args.timeout_s, 600.0)
        self.assertEqual(args.case_timeout_s, 1200.0)
        self.assertGreater(args.case_timeout_s, args.timeout_s)

    def test_live_text_supports_explicit_legacy_runtime_opt_out(self) -> None:
        args = build_parser().parse_args(
            ["--mode", "live-text", "--goal-driven-runtime", "off"]
        )
        manifest = load_manifest(DEFAULT_MANIFEST)
        case = manifest.ability_classes[0].live_text_cases[0].case

        namespace = _live_case_namespace(args, case, Path("/tmp/legacy-case"))

        self.assertFalse(namespace.cognitive_runtime)

    def test_cli_check_mode_returns_success_for_default_manifest(self) -> None:
        with redirect_stdout(StringIO()):
            code = main(["--mode", "check", "--no-write"])

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
