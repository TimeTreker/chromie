from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.general_ability_acceptance import (
    DEFAULT_MANIFEST,
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
        self.assertEqual(validate_manifest(manifest), [])
        self.assertGreaterEqual(len(level_a_keys(manifest.ability_classes)), 20)
        live_ids = live_case_ids(manifest.ability_classes)
        self.assertIn("wal_forward_typo_walk", live_ids)
        self.assertIn("multi_goal_look_then_blink", live_ids)

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
                                "root_cause_boundaries": ["Router/intent"],
                                "level_a_scenarios": [
                                    {
                                        "key": "router/polite_stop",
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
        self.assertEqual(summary["ability_classes"][0]["cases"][0]["key"], "router/polite_stop")


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
        self.assertEqual(summary["case_count"], 8)
        self.assertEqual(summary["passed"], 8)

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
        self.assertEqual(
            namespace.expect_skill,
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

        errors = validate_live_text_result(case, summary)

        self.assertTrue(any("terminal planner tier mismatch" in item for item in errors))
        self.assertTrue(any("Fast Planner path mismatch" in item for item in errors))
        self.assertTrue(any("Deep Planner invocation mismatch" in item for item in errors))
        self.assertTrue(any("Fast Planner contract failure" in item for item in errors))
        self.assertTrue(any("stage direction" in item for item in errors))

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
