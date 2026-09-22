from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scripts.general_ability_acceptance import (
    DEFAULT_LEVEL_A_SCENARIO_ROOT,
    DEFAULT_LIVE_SCENARIO_ROOT,
    LiveCaseRef,
    TextScenarioCase,
    _exclusive_orchestrator_lock,
    _social_response_timing_evidence,
    _run_live_case,
    _runtime_provenance,
    _speech_text,
    _write_reviewer_packet,
    build_parser,
    level_a_keys,
    live_case_ids,
    load_scenario_library,
    main,
    library_summary,
    run_level_a,
    run_live_text,
    _live_case_namespace,
    select_ability_classes,
    validate_live_text_result,
    validate_library,
)
from scripts.interaction_text_mujoco_check import build_parser as build_text_check_parser


@pytest.mark.parametrize("blink_start,passes", [("03", True), ("05", False)])
def test_simultaneous_scenario_requires_execution_overlap(blink_start, passes):
    library = load_scenario_library()
    case = next(ref.case for ability in library.ability_classes for ref in ability.live_text_cases
                if ref.case.case_id == "look_while_blinking_twice")
    capabilities = [
        {"request_id": "gaze", "capability_id": "soridormi.look_at_person", "capability_version": "1", "args": {"duration_s": 3}},
        {"request_id": "blink", "capability_id": "soridormi.blink_eyes", "capability_version": "1", "args": {"count": 2}},
    ]
    results = [
        {**capabilities[0], "status": "completed", "started_at": "2026-09-22T14:15:02Z", "finished_at": "2026-09-22T14:15:05Z"},
        {**capabilities[1], "status": "completed", "started_at": f"2026-09-22T14:15:{blink_start}Z", "finished_at": "2026-09-22T14:15:06Z"},
    ]
    errors = validate_live_text_result(case, {
        "interaction_response": {"capabilities": capabilities, "speech": []},
        "execution": {"results": results}, "preview_only": False,
    })
    assert not errors if passes else any("execution overlap" in error for error in errors)


@pytest.mark.parametrize("status", [None, "open", "abandoned", "satisfied"])
def test_spoken_answer_does_not_hide_unfinished_created_goal(status):
    case = TextScenarioCase(case_id="answer_completion", text="Answer the question.",
                            expect_created_goals_satisfied=True)
    summary = {
        "interaction_response": {"speech": [], "capabilities": []},
        "preview_only": False,
        "cognitive_runtime": {"goal_association": {"new_goals": [{"goal_id": "goal:answer"}]}},
        "session_state": {"scheduled_tts": 1, "played_tts": 1, "queued_tts": 0,
                          "workflow_events": [{"event": "tts_schedule", "message": "order=1 text='The answer.'"},
                                              {"event": "playback_end", "message": "order=1"}]},
    }
    if status is not None:
        summary["final_goal_snapshots"] = [
            {"goal": {"goal_id": "goal:answer", "responsibility_status": status}},
            {"goal": {"goal_id": "unrelated", "responsibility_status": "open"}},
        ]
    errors = validate_live_text_result(case, summary)
    assert (errors == []) == (status == "satisfied"), errors
    if status != "satisfied":
        assert any("Goal" in error for error in errors)


@pytest.mark.parametrize("stage", ["must_pass", "core"])
@pytest.mark.parametrize("failure", [
    {"turn_id": "scenario-turn", "sid": "cbe8a87b", "cognitive_runtime": {"status": "error", "metadata": {
        "failure_domain": "model_contract", "failure_class": "fast_stream_contract_invalid",
        "failure_stage": "fast_planner_stream", "turn_id": "cbe8a87b",
    }}},
    {"cognitive_runtime": {"status": "failed", "metadata": {"failure_domain": "service"}}},
    {"session_state": {"workflow_events": [{"event": "llm_output_truncated"}]}},
    {"cognitive_runtime": {"status": "applied"}, "session_state": {
        "cognitive_workflow_stages": [{"stage": "fast_planner_evidence_reentry", "status": "failed"}]}},
    {"cognitive_runtime": {"status": "applied"}, "session_state": {
        "cognitive_workflow_stages": [{"stage": "planner_deep_pass_evidence_reentry", "status": "failed"}]}},
    {"status_before": {"safe_idle": False}},
    {"status_after": {"safe_idle": False}},
    {"harness_failure": {"failure_domain": "preflight", "failure_class": "preflight_rejected"},
     "sid": None, "cognitive_runtime": None, "execution": None, "status_after": None},
    {"diagnostic_evaluation": {"metrics": {"goal_omission_rate": 0.5}}},
    {"diagnostic_evaluation": {"metrics": {"provenance_attachment_rejected": True}}},
    {"turns": [{"turn_id": "first", "cognitive_runtime": {
        "status": "error", "metadata": {"failure_domain": "model_contract"},
    }}]},
    TimeoutError("case deadline"),
    ConnectionError("service unavailable"),
])
def test_live_cohort_stops_before_next_case_on_integrity_failure(stage, failure):
    args = build_parser().parse_args(["--mode", "live-text", "--stage", stage, "--no-write"])
    # Even a superficially passing summary cannot override retained hard evidence.
    result = {"ok": True, "errors": [], **copy.deepcopy(failure)} if isinstance(failure, dict) else failure
    runner = AsyncMock(side_effect=[result] if isinstance(result, Exception) else None,
                       return_value=result)
    with patch("scripts.general_ability_acceptance._run_live_case", runner):
        report = asyncio.run(run_live_text(args))
    assert runner.await_count == 1
    assert report["ok"] is False
    assert report["qualification_complete"] is False
    assert report["cohort_complete"] is False
    assert report["case_count"] == 1
    assert report["skipped_case_count"] == report["planned_case_count"] - 1
    assert report["integrity_stop"]["case_id"] == report["cases"][0]["case_id"]
    assert report["stage_results"][0]["status"] == "incomplete"
    assert len({item["case_id"] for item in report["skipped_cases"]}) == report["skipped_case_count"]
    if isinstance(failure, dict) and failure.get("harness_failure"):
        assert report["integrity_stop"]["failure_domain"] == "preflight"
        assert report["integrity_stop"]["failure_class"] == "preflight_rejected"
    if isinstance(failure, dict) and failure.get("sid") == "cbe8a87b":
        assert report["integrity_stop"]["turn_id"] == "cbe8a87b"
        assert report["integrity_stop"]["scenario_turn_id"] == "scenario-turn"
        assert report["integrity_stop"]["sid"] == "cbe8a87b"


@pytest.mark.parametrize("failure", [
    {"ok": False, "errors": ["wrong requested effect"]},
    {"ok": True, "errors": [], "cognitive_runtime": {"status": "error", "metadata": {
        "failure_domain": "model_contract", "failure_class": "fast_stream_contract_invalid",
    }}},
    {"ok": True, "errors": [], "status_after": {"safe_idle": False}},
    TimeoutError("case deadline"),
    ConnectionError("service unavailable"),
])
def test_live_keep_going_attempts_all_cases_without_erasing_failure(failure):
    args = build_parser().parse_args(["--mode", "live-text", "--keep-going", "--no-write"])
    runner = AsyncMock(side_effect=[copy.deepcopy(failure)] + [
        {"ok": True, "errors": []} for _ in range(100)
    ])
    with patch("scripts.general_ability_acceptance._run_live_case", runner):
        report = asyncio.run(run_live_text(args))
    assert runner.await_count == report["planned_case_count"]
    assert report["case_count"] == report["planned_case_count"]
    assert report["case_attempt_coverage_percent"] == 100.0
    assert report["failed"] == 1
    assert report["passed"] == report["planned_case_count"] - 1
    assert report["pass_rate_percent"] == round(100 * report["passed"] / report["planned_case_count"], 2)
    assert report["ok"] is False
    assert report["qualification_complete"] is False
    assert report["cases"][0]["ok"] is False
    assert report["skipped_cases"] == []
    assert report["integrity_stop"] is None
    assert report["stopped_after_stage"] is None
    if isinstance(failure, Exception) or failure.get("ok"):
        assert len(report["integrity_failures"]) == 1
        assert report["cases"][0]["integrity_failure"] == report["integrity_failures"][0]


def test_live_keep_going_does_not_enable_unsupervised_physical_testing():
    args = build_parser().parse_args([
        "--mode", "live-text", "--keep-going", "--allow-non-sim", "--no-write",
    ])
    with patch("scripts.general_ability_acceptance._run_live_case", AsyncMock()) as runner:
        with pytest.raises(ValueError, match="simulator"):
            asyncio.run(run_live_text(args))
    runner.assert_not_awaited()


def test_live_cohort_retains_stop_and_unrun_coverage_in_reviewer_packet(tmp_path):
    identity = tmp_path / "identity.json"
    identity.write_text(json.dumps({"identity_sha256": "fixture-only"}))
    args = build_parser().parse_args([
        "--mode", "live-text", "--execute", "--runtime-identity", str(identity),
        "--evidence-dir", str(tmp_path / "evidence"),
    ])
    runner = AsyncMock(return_value={"ok": True, "errors": [], "status_after": None})
    with patch("scripts.general_ability_acceptance._run_live_case", runner):
        report = asyncio.run(run_live_text(args))
    assert runner.await_count == 1
    assert report["integrity_stop"]["failure_domain"] == "safe_idle"
    for path in (tmp_path / "evidence" / "summary.json", tmp_path / "evidence" / "reviewer-packet" / "summary.json"):
        retained = json.loads(path.read_text())
        assert retained["cohort_complete"] is False
        assert retained["planned_case_count"] == report["planned_case_count"]
        assert retained["skipped_cases"] == report["skipped_cases"]
        assert retained["integrity_stop"] == report["integrity_stop"]


@pytest.mark.parametrize("execute", [False, True])
def test_live_cohort_finishes_all_selected_cases_without_integrity_failure(execute):
    args = build_parser().parse_args(["--mode", "live-text", "--no-write"])
    args.execute = execute
    safe = {"safe_idle": True, "active_task": None, "fallen": False, "emergency_stop": False}
    runner = AsyncMock(side_effect=lambda *args: {
        "ok": True, "errors": [], "status_before": safe,
        "status_after": safe if execute else None,
    })
    with patch("scripts.general_ability_acceptance._run_live_case", runner):
        report = asyncio.run(run_live_text(args))
    assert runner.await_count == report["planned_case_count"]
    assert report["cohort_complete"] is True
    assert report["ok"] is True
    assert report["integrity_stop"] is None
    assert report["skipped_cases"] == []
    assert report["qualification_complete"] is False  # Semantic review is still pending.


class GeneralAbilityAcceptanceTests(unittest.TestCase):
    def test_speech_text_includes_completed_detached_result_delivery(self) -> None:
        summary = {
            "interaction_response": {"speech": []},
            "user_outcome": {
                "observations": [
                    {
                        "type": "speech.output",
                        "status": "completed",
                        "text": "I looked at you, then blinked twice.",
                    },
                    {
                        "type": "speech.output",
                        "status": "failed",
                        "text": "This was never delivered.",
                    },
                ]
            },
        }

        self.assertEqual(
            _speech_text(summary),
            "I looked at you, then blinked twice.",
        )

    def test_runtime_provenance_is_revision_bound_for_target_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime-identity.json"
            path.write_text(
                json.dumps(
                    {
                        "identity_sha256": "identity-digest",
                        "chromie": {
                            "revision": "revision-1",
                            "dirty": False,
                            "source_tree_sha256": "tree-digest",
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                _runtime_provenance(path),
                {
                    "chromie_revision": "revision-1",
                    "chromie_dirty": False,
                    "source_tree_sha256": "tree-digest",
                    "runtime_identity_sha256": "identity-digest",
                },
            )

    def test_live_runner_refuses_a_second_orchestrator_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "orchestrator.lock"
            with patch.dict(
                os.environ,
                {"ORCH_LOCK_FILE": str(lock_path)},
            ):
                with _exclusive_orchestrator_lock():
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "another Orchestrator is running",
                    ):
                        with _exclusive_orchestrator_lock():
                            self.fail("nested Host lock unexpectedly succeeded")

    def test_default_library_discovers_self_describing_scenarios(self) -> None:
        manifest = load_scenario_library()
        self.assertEqual(manifest.live_root, DEFAULT_LIVE_SCENARIO_ROOT.resolve())

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
        self.assertIn("human_like_cognitive_continuity", ability_ids)
        self.assertIn("planner_goal_semantic_quality", ability_ids)
        self.assertIn("workdag_multi_goal_revision_integrity", ability_ids)
        self.assertIn("continuous_cognition_recovery", ability_ids)
        self.assertEqual(validate_library(manifest), [])
        self.assertGreaterEqual(len(level_a_keys(manifest.ability_classes)), 20)
        live_ids = live_case_ids(manifest.ability_classes)
        self.assertIn("wal_forward_typo_walk", live_ids)
        self.assertIn("multi_goal_look_then_blink", live_ids)
        self.assertIn("weather_then_chinese_walk_blink_song", live_ids)
        self.assertIn("beijing_rain_evidence_bound_result", live_ids)
        self.assertIn("qualification_human_continuity_continue_walk", live_ids)
        self.assertIn("qualification_planner_weather_evidence", live_ids)
        self.assertIn("qualification_workdag_walk_blink_once", live_ids)
        self.assertIn("qualification_continuous_weather_reentry", live_ids)
        self.assertIn("standalone_greeting_one_natural_reply", live_ids)
        self.assertIn("weather_rain_followup_after_completed_lookup", live_ids)
        self.assertFalse(
            (DEFAULT_LEVEL_A_SCENARIO_ROOT / "general_ability_acceptance.json").exists()
        )
        self.assertEqual(
            [(stage.stage_id, len(stage.scenario_paths)) for stage in manifest.stages],
            [("must_pass", 52), ("core", 15), ("challenge", 8)],
        )
        self.assertEqual(len(live_ids), 75)
        self.assertEqual(
            len({ref.source_path for ability in manifest.ability_classes for ref in ability.live_text_cases}),
            75,
        )
        generated = [
            ref
            for ability in manifest.ability_classes
            for ref in ability.live_text_cases
            if ref.provenance.get("batch_id") == "common_must_pass_2026_08_28"
        ]
        self.assertEqual(len(generated), 25)
        self.assertTrue(
            all(
                ref.provenance
                == {
                    "origin": "codex_generated_common_scene",
                    "batch_id": "common_must_pass_2026_08_28",
                    "derived_from_existing_scenario": False,
                }
                for ref in generated
            )
        )
        for ability in manifest.ability_classes:
            for ref in ability.live_text_cases:
                self.assertIsNotNone(ref.source_path)
                source = json.loads(ref.source_path.read_text(encoding="utf-8"))
                serialized = json.dumps(source)
                self.assertNotIn("expected_speech_any", serialized)
                self.assertNotIn("expected_speech_all", serialized)
                self.assertNotIn("forbidden_speech_any", serialized)
                self.assertNotIn("ability_class", source)
                self.assertEqual(
                    source["general_ability"]["memberships"][0]["id"],
                    ability.ability_id,
                )
                self.assertEqual(source["oracle_policy"]["mode"], "hybrid")
                self.assertTrue(source["review_rubric"]["primary_outcomes"])
            for ref in ability.level_a_scenarios:
                self.assertIsNotNone(ref.source_path)
                source = json.loads(ref.source_path.read_text(encoding="utf-8"))
                membership_ids = {
                    item["id"]
                    for item in source["general_ability"]["memberships"]
                }
                self.assertIn(ability.ability_id, membership_ids)

    def test_library_rejects_first_turn_previous_speech_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_root = root / "live"
            level_a_root = root / "level-a"
            case_path = live_root / "must_pass" / "continuity" / "invalid_first_turn_history.json"
            case_path.parent.mkdir(parents=True)
            case_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "chromie_general_ability_live_text",
                        "id": "invalid_first_turn_history",
                        "stage": "must_pass",
                        "difficulty": "easy",
                        "general_ability": {
                            "memberships": [
                                {
                                    "id": "continuity",
                                    "title": "Continuity",
                                    "general_rule": "Preserve dialogue history.",
                                    "rationale": "Preserve actual dialogue history.",
                                    "root_cause_boundaries": ["dialogue_state"],
                                }
                            ]
                        },
                        "oracle_policy": {
                            "mode": "hybrid",
                            "deterministic_sources": ["runtime_contracts"],
                            "semantic_dimensions": ["dialogue_continuity"],
                            "semantic_blocking": True,
                        },
                        "review_rubric": {
                            "dimensions": ["dialogue_continuity"],
                            "primary_outcomes": ["Preserve actual dialogue history."],
                        },
                        "turns": [
                            {
                                "id": "first",
                                "text": "What did you say?",
                                "forbid_repeat_of_previous_speech": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest = load_scenario_library(live_root, level_a_root)
            errors = validate_library(manifest, validate_level_a_sources=False)
        self.assertTrue(any("previous-speech comparison" in item for item in errors))

    def test_live_validation_requires_structured_pending_work_speech(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="今天北京下雨了没有？",
            require_speech=False,
            require_social_communicative_act=True,
            expected_social_communicative_functions=("acknowledge",),
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "preview_only": True,
            "cognitive_runtime": {},
        }

        missing = validate_live_text_result(case, _social_test_summary(summary))
        self.assertTrue(any("omitted" in item for item in missing))

        summary["cognitive_runtime"]["fast_advance"] = {
            "activities": [
                {
                    "activity_id": "a1",
                    "role": "progress",
                    "speech_act": "acknowledge_and_check",
                    "progress_kind": "check_information",
                    "source_responsibility_refs": ["r1"],
                }
            ]
        }
        self.assertEqual(validate_live_text_result(case, _social_test_summary(summary)), [])

    def test_live_validation_accepts_current_progress_communicative_act(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="哎，今天上午重庆会不会下雨？",
            require_speech=False,
            require_social_communicative_act=True,
            expected_social_communicative_functions=("acknowledge",),
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "preview_only": False,
            "cognitive_runtime": {
                "fast_advance": {
                    "activities": [
                        {
                            "activity_id": "a1",
                            "role": "progress",
                            "speech_act": "acknowledge_and_check",
                            "progress_kind": "check_information",
                            "source_responsibility_refs": ["r1"],
                        }
                    ]
                },
                "metadata": {
                    "fast_communicative_realization_status": "planner_owned"
                },
            },
        }

        self.assertEqual(validate_live_text_result(case, _social_test_summary(summary)), [])

    def test_live_validation_gates_fast_commit_and_goal_evidence_reentry(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="哎，今天上午重庆会不会下雨？",
            require_speech=False,
            require_fast_planner_evidence_reentry=True,
            require_work_held_until_canonical_validation=True,
            require_canonical_work_reconciliation=True,
            max_warm_sc_decision_ms=2000,
            max_warm_sc_to_playback_start_ms=3000,
        )
        summary = {
            "preview_only": False,
            "speaker": False,
            "timings_ms": {"user_meaning_interpretation_ms": 400.0},
            "interaction_response": {"speech": [], "capabilities": []},
            "cognitive_runtime": {
                "timings_ms": {"fast_planner_commit": 600.0},
                "metadata": {
                    "fast_capability_activity_status": (
                        "deferred_until_canonical_validation"
                    ),
                    "work_reconciliation_required": True,
                },
            },
            "session_state": {
                "cognitive_workflow_stages": [
                    {
                        "stage": "social_cognition",
                        "status": "accepted",
                        "output": {"semantic_owner": "social_cognition", "disposition": "communicate", "activities": [{"text": "Hello."}]},
                        "started_elapsed_ms": 500.0,
                        "duration_ms": 600.0,
                        "finished_elapsed_ms": 1100.0,
                    },
                    {
                        "stage": "fast_planner_evidence_reentry",
                        "status": "resolved",
                    },
                ],
                "workflow_events": [
                    {"event": "session_start", "elapsed_ms": 0.0},
                    {
                        "event": "text_check_user_meaning_interpretation_done",
                        "elapsed_ms": 500.0,
                    },
                    {"event": "tts_schedule", "elapsed_ms": 1102.0},
                    {
                        "event": "tts_first_provider_pcm",
                        "elapsed_ms": 3390.0,
                    },
                    {"event": "playback_start", "elapsed_ms": 3400.0},
                ],
            },
        }

        self.assertEqual(validate_live_text_result(case, summary), [])
        evidence = summary["social_response_timing_evidence"]
        self.assertEqual(
            evidence["derived"]["sc_decision_ms"],
            600.0,
        )
        self.assertEqual(
            evidence["derived"]["sc_to_playback_start_ms"],
            2300.0,
        )
        self.assertEqual(
            evidence["derived"]["user_meaning_interpretation_plus_sc_duration_ms"],
            1000.0,
        )
        self.assertFalse(evidence["claim_limits"]["audible_speaker_proven"])

        premature_summary = json.loads(json.dumps(summary))
        premature_summary["cognitive_runtime"]["metadata"][
            "fast_capability_activity_status"
        ] = "completed_before_canonical_dispatch:completed"
        errors = validate_live_text_result(case, premature_summary)
        self.assertTrue(
            any("crossed the complete Work validation boundary" in item for item in errors),
            errors,
        )

        unreconciled_summary = json.loads(json.dumps(summary))
        unreconciled_summary["cognitive_runtime"]["metadata"][
            "work_reconciliation_required"
        ] = False
        errors = validate_live_text_result(case, unreconciled_summary)
        self.assertTrue(
            any("Work reconciliation did not run" in item for item in errors),
            errors,
        )

        slow_summary = json.loads(json.dumps(summary))
        slow_summary["session_state"]["workflow_events"][-1]["elapsed_ms"] = 4500.0
        errors = validate_live_text_result(case, slow_summary)
        self.assertTrue(
            any("commitment to first playback" in item for item in errors),
            errors,
        )

    def test_fast_timing_evidence_keeps_absolute_and_duration_axes_separate(self) -> None:
        summary = {
            "speaker": False,
            "timings_ms": {"user_meaning_interpretation_ms": 826.2},
            "session_state": {
                "cognitive_workflow_stages": [
                    {
                        "stage": "social_cognition",
                        "status": "accepted",
                        "output": {"semantic_owner": "social_cognition", "disposition": "communicate", "activities": [{"text": "Hello."}]},
                        "started_elapsed_ms": 1300.879,
                        "duration_ms": 1062.218,
                        "finished_elapsed_ms": 2363.097,
                    }
                ],
                "workflow_events": [
                    {"event": "session_start", "elapsed_ms": 0.266},
                    {
                        "event": "text_check_user_meaning_interpretation_done",
                        "elapsed_ms": 1299.678,
                    },
                    {"event": "tts_schedule", "elapsed_ms": 2366.437},
                    {
                        "event": "tts_first_provider_pcm",
                        "elapsed_ms": 4857.717,
                    },
                    {"event": "playback_start", "elapsed_ms": 4859.329},
                ],
            },
        }

        evidence = _social_response_timing_evidence(summary)

        self.assertEqual(
            evidence["derived"]["sc_decision_ms"],
            1062.218,
        )
        self.assertEqual(
            evidence["derived"]["sc_to_playback_start_ms"],
            2496.232,
        )
        self.assertEqual(
            evidence["derived"]["session_start_to_sc_ms"],
            2362.831,
        )
        self.assertEqual(
            evidence["derived"]["user_meaning_interpretation_plus_sc_duration_ms"],
            1888.418,
        )
        self.assertFalse(
            evidence["claim_limits"]["duration_sum_is_absolute_anchor"]
        )

    def test_reviewer_packet_binds_source_runtime_profile_and_raw_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "evidence"
            runtime_identity_path = Path(temp_dir) / "runtime-identity.json"
            runtime_identity_path.write_text(
                json.dumps(
                    {
                        "identity_sha256": "i" * 64,
                        "chromie": {
                            "revision": "a" * 40,
                            "dirty": False,
                            "source_tree_sha256": "s" * 64,
                        },
                        "runtime_profile": {
                            "active_profile": "rtx5090",
                            "active_validation_profile": "target",
                            "fingerprint": "f" * 64,
                            "sha256": "p" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            timing = {
                "schema_version": 1,
                "clock": "session_relative_monotonic_elapsed_ms",
                "raw": {
                    "social_cognition_started_elapsed_ms": 100.0,
                    "social_cognition_finished_elapsed_ms": 900.0,
                    "first_playback_start_elapsed_ms": 2500.0,
                },
                "derived": {
                    "sc_decision_ms": 800.0,
                    "sc_to_playback_start_ms": 1600.0,
                },
            }
            metadata = _write_reviewer_packet(
                root=root,
                runtime_identity_path=runtime_identity_path,
                run_summary={
                    "ok": True,
                    "mode": "live-text",
                    "evidence_level": "C",
                    "claim_scope": "injected text only",
                    "execute": True,
                    "speaker": False,
                    "assertion_scope": "full",
                    "goal_driven_runtime": "apply",
                    "passed": 1,
                    "failed": 0,
                    "cases": [
                        {
                            "case_id": "weather",
                            "ability_class": "truthful_embodied_speech",
                            "ok": True,
                            "errors": [],
                            "social_response_timing_evidence": timing,
                        }
                    ],
                },
            )

            packet = root / "reviewer-packet"
            summary = json.loads((packet / "summary.json").read_text())
            timeline = json.loads((packet / "timeline.json").read_text())
            manifest = json.loads((packet / "manifest.json").read_text())
            self.assertEqual(summary["input_channel"], "injected_text")
            self.assertFalse(summary["speaker"])
            self.assertEqual(
                summary["source_identity"]["source_tree_sha256"],
                "s" * 64,
            )
            self.assertEqual(
                timeline["cases"][0]["raw"][
                    "social_cognition_finished_elapsed_ms"
                ],
                900.0,
            )
            self.assertEqual(manifest["source_revision"], "a" * 40)
            self.assertTrue((packet / "collection-report.json").is_file())
            self.assertTrue((packet / "SHA256SUMS").is_file())
            self.assertEqual(metadata["file_count"], 6)

    def test_live_validation_can_forbid_pre_effect_communicative_act(self) -> None:
        case = TextScenarioCase(
            case_id="weather",
            text="今天北京下雨了没有？",
            require_speech=False,
            forbid_social_communicative_act=True,
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "preview_only": True,
            "cognitive_runtime": {
                "fast_advance": {
                    "activities": [
                        {
                            "role": "progress",
                            "speech_act": "acknowledge_and_check",
                        }
                    ]
                }
            },
        }

        errors = validate_live_text_result(case, _social_test_summary(summary))
        self.assertTrue(any("forbidden pre-effect" in item for item in errors))

        summary["cognitive_runtime"]["fast_advance"] = {"activities": []}
        self.assertEqual(validate_live_text_result(case, _social_test_summary(summary)), [])

    def test_live_validation_can_require_complete_silence(self) -> None:
        case = TextScenarioCase(
            case_id="silent_motion",
            text="别说话，过来。",
            require_speech=False,
            expect_no_speech=True,
            forbid_social_communicative_act=True,
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "session_state": {
                "scheduled_tts": 1,
                "played_tts": 1,
                "queued_tts": 0,
            },
            "preview_only": False,
            "cognitive_runtime": {},
        }

        errors = validate_live_text_result(case, summary)
        self.assertTrue(any("required silence" in item for item in errors))

        summary["session_state"] = {
            "scheduled_tts": 0,
            "played_tts": 0,
            "queued_tts": 0,
        }
        self.assertEqual(validate_live_text_result(case, summary), [])

    def test_live_validation_can_require_executed_safe_idle(self) -> None:
        case = TextScenarioCase(
            case_id="stop_active_motion",
            text="停下！",
            require_speech=False,
            expect_no_speech=True,
            require_safe_idle=True,
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "preview_only": False,
            "status_after": {
                "safe_idle": False,
                "active_task": "walk-1",
                "emergency_stop": False,
                "fallen": False,
            },
            "cognitive_runtime": {},
        }

        errors = validate_live_text_result(case, summary)
        self.assertTrue(any("safe-idle final state" in item for item in errors))

        summary["status_after"] = {
            "safe_idle": True,
            "active_task": None,
            "emergency_stop": False,
            "fallen": False,
        }
        self.assertEqual(validate_live_text_result(case, summary), [])

        summary["preview_only"] = True
        errors = validate_live_text_result(case, summary)
        self.assertTrue(any("preview output is insufficient" in item for item in errors))

    def test_manifest_rejects_contradictory_fast_communicative_act_policy(self) -> None:
        manifest = load_scenario_library()
        ability = manifest.ability_classes[0]
        contradictory = TextScenarioCase(
            case_id="contradictory",
            text="Check something.",
            require_social_communicative_act=True,
            forbid_social_communicative_act=True,
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

        errors = validate_library(patched_manifest, validate_level_a_sources=False)
        self.assertTrue(any("both required and forbidden" in item for item in errors))

    def test_live_validation_counts_played_fast_complete_response_as_speech(self) -> None:
        case = TextScenarioCase(
            case_id="fast_complete_response",
            text="I am tired.",
            expected_speech_any=("rest",),
            expect_no_capabilities=True,
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "cognitive_runtime": {
                "metadata": {
                    "retired_frame_fixture": {
                        "activity": {
                            "role": "complete_response",
                            "text": "You sound tired; get some rest.",
                        }
                    }
                }
            },
            "session_state": {
                "scheduled_tts": 1,
                "played_tts": 1,
                "queued_tts": 0,
            },
        }

        summary["session_state"]["workflow_events"] = [{"event": "tts_schedule", "message": "order=1 text='You sound tired; get some rest.'"}, {"event": "playback_end", "message": "order=1"}]
        self.assertEqual(validate_live_text_result(case, summary), [])

    def test_live_validation_counts_played_fast_progress_as_speech(self) -> None:
        case = TextScenarioCase(
            case_id="fast_progress",
            text="刚才那个事情继续。",
            expected_speech_any=("往前走",),
        )
        summary = {
            "interaction_response": {"speech": [], "capabilities": []},
            "cognitive_runtime": {
                "metadata": {
                    "retired_frame_fixture": {
                        "activity": {
                            "role": "progress",
                            "text": "好，我接着往前走。",
                        }
                    }
                }
            },
            "session_state": {
                "scheduled_tts": 1,
                "played_tts": 1,
                "queued_tts": 1,
            },
        }

        summary["session_state"]["workflow_events"] = [{"event": "tts_schedule", "message": "order=1 text='好，我接着往前走。'"}, {"event": "playback_end", "message": "order=1"}]
        self.assertEqual(validate_live_text_result(case, summary), [])
        summary["session_state"]["played_tts"] = 0
        summary["session_state"]["workflow_events"] = []
        errors = validate_live_text_result(case, summary)
        self.assertTrue(any("speech missing" in item for item in errors))

    def test_previous_speech_repeat_requires_delivered_assistant_utterance(self) -> None:
        from scripts.general_ability_acceptance import _previous_speech_repeat_error

        previous = {
            "interaction_response": {"speech": []},
            "cognitive_runtime": {
                "metadata": {
                    "retired_frame_fixture": {
                        "activity": {
                            "role": "complete_response",
                            "text": "你好！有什么想聊的吗？",
                        }
                    }
                }
            },
        }
        correct = {
            "interaction_response": {
                "speech": [{"text": "我刚才说：你好！有什么想聊的吗？"}]
            }
        }
        wrong_speaker = {
            "interaction_response": {
                "speech": [{"text": "我刚才说：你好，Chromie。"}]
            }
        }

        previous["user_outcome"] = {"observations": [{"type": "speech.output", "status": "completed", "text": "你好！有什么想聊的吗？"}]}
        self.assertEqual(_previous_speech_repeat_error(previous, correct), "")
        self.assertIn(
            "did not repeat",
            _previous_speech_repeat_error(previous, wrong_speaker),
        )

    def test_manifest_rejects_contradictory_silence_policy(self) -> None:
        manifest = load_scenario_library()
        ability = manifest.ability_classes[0]
        contradictory = TextScenarioCase(
            case_id="contradictory_silence",
            text="Come here silently.",
            require_speech=True,
            expect_no_speech=True,
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

        errors = validate_library(patched_manifest, validate_level_a_sources=False)
        self.assertTrue(any("speech cannot be both required and forbidden" in item for item in errors))

    def test_retained_voice_incident_is_a_two_turn_live_episode(self) -> None:
        manifest = load_scenario_library()
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
        self.assertEqual(
            case.turns[0].expected_capabilities,
            ("chromie.weather.lookup",),
        )
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

    def test_library_summary_labels_scope_and_counts(self) -> None:
        manifest = load_scenario_library()

        summary = library_summary(manifest)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["mode"], "check")
        self.assertGreater(summary["ability_class_count"], 0)
        self.assertGreater(summary["level_a_case_count"], 0)
        self.assertGreater(summary["live_text_case_count"], 0)

    def test_select_ability_classes_rejects_unknown_id(self) -> None:
        manifest = load_scenario_library()

        selected = select_ability_classes(manifest, ["deterministic_safety_controls"])

        self.assertEqual([item.ability_id for item in selected], ["deterministic_safety_controls"])
        with self.assertRaisesRegex(ValueError, "unknown ability class"):
            select_ability_classes(manifest, ["missing"])

    def test_live_stage_gate_finishes_must_pass_before_blocking_later_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            level_a_root = root / "level-a"
            stage_cases = {
                "must_pass": ["must_one", "must_two"],
                "core": ["core_one"],
                "challenge": ["challenge_one"],
            }
            for stage_id, case_ids in stage_cases.items():
                for case_id in case_ids:
                    path = live_root / stage_id / "intent" / f"{case_id}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "kind": "chromie_general_ability_live_text",
                                "id": case_id,
                                "stage": stage_id,
                                "difficulty": "easy" if stage_id == "must_pass" else "medium",
                                "general_ability": {
                                    "memberships": [
                                        {
                                            "id": "intent",
                                            "title": "Intent",
                                            "general_rule": "Understand the selected test turns.",
                                            "rationale": "Understand this selected test turn.",
                                            "root_cause_boundaries": ["user_meaning_interpretation"],
                                        }
                                    ]
                                },
                                "text": case_id,
                                "expect_no_capabilities": True,
                                "oracle_policy": {
                                    "mode": "hybrid",
                                    "deterministic_sources": ["runtime_contracts"],
                                    "semantic_dimensions": ["intent_understanding"],
                                    "semantic_blocking": True,
                                },
                                "review_rubric": {
                                    "dimensions": ["intent_understanding"],
                                    "primary_outcomes": ["Understand the selected test turn."],
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
            args = build_parser().parse_args(
                [
                    "--mode",
                    "live-text",
                    "--scenario-root",
                    str(live_root),
                    "--level-a-scenario-root",
                    str(level_a_root),
                    "--no-write",
                ]
            )

            failing_runner = AsyncMock(
                side_effect=[
                    {"ok": False, "errors": ["hard failure"]},
                    {"ok": True, "errors": []},
                ]
            )
            with patch(
                "scripts.general_ability_acceptance._run_live_case",
                failing_runner,
            ):
                failed = asyncio.run(run_live_text(args))

            self.assertEqual(failing_runner.await_count, 2)
            self.assertEqual(
                [call.args[1].case_id for call in failing_runner.await_args_list],
                ["must_one", "must_two"],
            )
            self.assertEqual(failed["stopped_after_stage"], "must_pass")
            self.assertEqual(failed["skipped_case_count"], 2)
            self.assertEqual(
                [item["status"] for item in failed["stage_results"]],
                ["hard_fail", "skipped", "skipped"],
            )

            passing_runner = AsyncMock(
                side_effect=[{"ok": True, "errors": []} for _ in range(4)]
            )
            with patch(
                "scripts.general_ability_acceptance._run_live_case",
                passing_runner,
            ):
                passed = asyncio.run(run_live_text(args))

            self.assertEqual(passing_runner.await_count, 4)
            self.assertIsNone(passed["stopped_after_stage"])
            self.assertEqual(passed["skipped_case_count"], 0)
            self.assertEqual(
                [item["status"] for item in passed["stage_results"]],
                ["hard_pass", "hard_pass", "hard_pass"],
            )

    def test_level_a_runner_discovers_selected_case_membership(self) -> None:
        args = build_parser().parse_args(
            [
                "--mode",
                "level-a",
                "--ability-class",
                "deterministic_safety_controls",
                "--only-case",
                "cognitive_turn_loop/active_stop_cancel_retains_outcome",
                "--no-write",
            ]
        )

        summary = run_level_a(args)

        self.assertTrue(summary["ok"], summary["errors"])
        self.assertEqual(summary["evidence_level"], "A")
        self.assertIn("deterministic file-backed evidence", summary["claim_scope"])
        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(
            summary["ability_classes"][0]["id"],
            "deterministic_safety_controls",
        )
        self.assertEqual(
            summary["ability_classes"][0]["cases"][0]["key"],
            "cognitive_turn_loop/active_stop_cancel_retains_outcome",
        )


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
        manifest = load_scenario_library()
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "multi_goal_look_then_blink"
        )
        args = build_parser().parse_args(
            [
                "--mode",
                "live-text",
                "--goal-driven-runtime",
                "apply",
                "--soridormi-repo",
                "/tmp/soridormi-checkout",
                "--no-write",
            ]
        )

        namespace = _live_case_namespace(args, case, Path("/tmp/multi-goal"))

        self.assertTrue(namespace.cognitive_runtime)
        self.assertEqual(namespace.soridormi_repo, "/tmp/soridormi-checkout")
        self.assertEqual(
            namespace.conversation_id,
            "ga-live-multi_goal_look_then_blink",
        )
        self.assertEqual(
            namespace.trusted_target_context["target_ref"],
            "current_speaker",
        )
        self.assertEqual(
            namespace.trusted_target_context["source"],
            "live_perception",
        )
        self.assertEqual(args.assertion_scope, "user-outcome")
        self.assertEqual(namespace.expect_capability, [])
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
            full_namespace.expect_capability,
            ["soridormi.look_at_person", "soridormi.blink_eyes"],
        )
        self.assertEqual(case.expected_terminal_planner_tier, "fast")
        self.assertEqual(case.expected_fast_planner_path, "terminal")
        self.assertFalse(case.expect_deep_planner_invoked)
        self.assertTrue(case.expect_no_fast_contract_failure)

    def test_live_validation_enforces_fast_terminal_path(self) -> None:
        manifest = load_scenario_library()
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "multi_goal_blink_and_joke"
        )
        summary = {
            "interaction_response": {
                "capabilities": [
                    {
                        "capability_id": "soridormi.blink_eyes",
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
        manifest = load_scenario_library()
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "multi_goal_look_then_blink"
        )
        summary = {
            "interaction_response": {
                "capabilities": [
                    {
                        "request_id": "look",
                        "capability_id": "soridormi.look_at_person",
                        "args": {"duration_s": 2.0},
                        "metadata": {"source_goal_ids": ["goal-look"]},
                    },
                    {
                        "request_id": "blink",
                        "capability_id": "soridormi.blink_eyes",
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
        manifest = load_scenario_library()
        ability = next(
            item for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "multi_goal_look_then_blink"
        )
        summary = {
            "interaction_response": {
                "capabilities": [
                    {
                        "request_id": "look",
                        "capability_id": "soridormi.look_at_person",
                        "args": {"duration_s": 2.0},
                        "metadata": {"source_goal_ids": ["goal-look"]},
                    },
                    {
                        "request_id": "blink",
                        "capability_id": "soridormi.blink_eyes",
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
        manifest = load_scenario_library()
        ability = next(
            item
            for item in manifest.ability_classes
            if item.ability_id == "multi_goal_daily_life"
        )
        case = next(
            ref.case
            for ref in ability.live_text_cases
            if ref.case.case_id == "multi_goal_look_then_blink"
        )
        summary = {
            "interaction_response": {"capabilities": [], "speech": [{"text": "Done."}]},
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
        manifest = load_scenario_library()
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
            "interaction_response": {
                "capabilities": [
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
            "interaction_response": {
                "capabilities": [],
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
                "interaction_response": {
                    "capabilities": [],
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
                "interaction_response": {
                    "capabilities": [],
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
        self.assertTrue(result["cohort_complete"])
        with patch(
            "scripts.general_ability_acceptance.run_check_sequence",
            AsyncMock(return_value=summaries[:1]),
        ):
            incomplete = asyncio.run(_run_live_case(args, case, Path("/tmp/episode-evidence")))
        self.assertFalse(incomplete["cohort_complete"])
        self.assertFalse(incomplete["ok"])
        self.assertIn("not run", incomplete["turns"][1]["errors"][0])

    def test_live_case_namespace_matches_text_checker_argument_contract(self) -> None:
        args = build_parser().parse_args(["--mode", "live-text"])
        manifest = load_scenario_library()
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

        self.assertFalse(hasattr(args, "ability_manifest"))
        self.assertEqual(args.scenario_root, DEFAULT_LIVE_SCENARIO_ROOT)
        self.assertEqual(args.goal_driven_runtime, "apply")
        self.assertEqual(args.timeout_s, 600.0)
        self.assertEqual(args.case_timeout_s, 1200.0)
        self.assertGreater(args.case_timeout_s, args.timeout_s)

    def test_live_text_supports_explicit_legacy_runtime_opt_out(self) -> None:
        args = build_parser().parse_args(
            ["--mode", "live-text", "--goal-driven-runtime", "off"]
        )
        manifest = load_scenario_library()
        case = manifest.ability_classes[0].live_text_cases[0].case

        namespace = _live_case_namespace(args, case, Path("/tmp/legacy-case"))

        self.assertFalse(namespace.cognitive_runtime)

    def test_cli_check_mode_returns_success_for_default_manifest(self) -> None:
        with redirect_stdout(StringIO()):
            code = main(["--mode", "check", "--no-write"])

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()


def _social_test_summary(summary):
    """Author the new role fixture separately from the retained Work scenario."""
    cognitive = summary.get("cognitive_runtime", {})
    metadata = cognitive.get("metadata", {})
    old = cognitive.get("fast_advance", {}).get("activities", [])
    result = {"semantic_owner": "social_cognition", "request_id": "sc-test",
              "disposition": "communicate", "activities": [
        {"activity_id": act.get("activity_id", "act"), "function": "acknowledge",
         "text": act.get("text", "I will check."), "truth_stage": "context_grounded"}
        for act in old]}
    if old:
        summary.setdefault("interaction_response", {}).setdefault("metadata", {})["social_cognition_resolution"] = result
    else:
        summary.get("interaction_response", {}).get("metadata", {}).pop("social_cognition_resolution", None)
    return summary


def test_silent_or_missing_sc_output_cannot_satisfy_spoken_latency_target():
    from scripts.general_ability_acceptance import _social_response_timing_evidence
    for output in (None, {"semantic_owner": "social_cognition", "disposition": "silence", "activities": []}):
        summary = {"session_state": {"cognitive_workflow_stages": [{
            "stage": "social_cognition", "status": "accepted", "output": output,
            "started_elapsed_ms": 100, "finished_elapsed_ms": 200, "duration_ms": 100,
        }]}}
        assert _social_response_timing_evidence(summary)["derived"]["sc_decision_ms"] is None


def test_redacted_sc_reentry_retains_verifiable_communication_structure(tmp_path):
    from orchestrator.runtime.session import SessionTracker, now_ms
    from scripts.general_ability_acceptance import _social_activities

    tracker = SessionTracker(workflow_report_root=tmp_path, workflow_report_include_text=False)
    sid = tracker.create()
    tracker.record_cognitive_stage(
        sid, stage="social_cognition", status="accepted",
        started_monotonic_ms=now_ms(), finished_monotonic_ms=now_ms(),
        output_payload={
            "semantic_owner": "social_cognition", "request_id": "sc-result-reentry",
            "disposition": "communicate", "activities": [{
                "activity_id": "result-act", "function": "inform",
                "delivery_phase": "final", "truth_stage": "result_grounded",
                "text": "Private result for a private person.",
            }],
        },
    )
    summary = {"interaction_response": {"speech": []}, "session_state": tracker.state[sid]}
    acts = _social_activities(summary)
    assert len(acts) == 1
    assert acts[0]["function"] == "inform"
    assert acts[0]["text"]["redacted"] is True
    assert "Private result" not in json.dumps(summary)
