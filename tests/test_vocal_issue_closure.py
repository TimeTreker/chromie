from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.evidence_identity import canonical_json_sha256
from scripts.vocal_issue_closure import (
    _build_live_command,
    _failure_summary,
    build_parser,
    validate_closure_summary,
    validate_runtime_identity,
)


REVISION = "a" * 40
SORIDORMI_REVISION = "b" * 40
WALK = "soridormi.walk_velocity"
BLINK = "soridormi.blink_eyes"


def passing_summary() -> dict:
    return {
        "ok": True,
        "errors": [],
        "route": {"route": "robot_action"},
        "provenance": {
            "chromie": {"revision": REVISION, "dirty": False},
            "runtime_identity": {"complete": True, "identity_sha256": "c" * 64},
            "soridormi": {
                "endpoint_revision": SORIDORMI_REVISION,
                "checkout_revision": SORIDORMI_REVISION,
                "checkout_dirty": False,
            },
        },
        "status_before": {
            "mode": "sim",
            "safe_idle": True,
            "active_task": None,
            "emergency_stop": False,
            "fallen": False,
        },
        "status_after": {
            "mode": "sim",
            "safe_idle": True,
            "active_task": None,
            "emergency_stop": False,
            "fallen": False,
        },
        "cognitive_runtime": {
            "status": "applied",
            "goal_association": {
                "new_goals": [
                    {
                        "goal_id": "goal-walk",
                        "description": "往前走15秒",
                        "metadata": {
                            "responsibility_kind": "executable_action",
                            "execution_lane": "activity",
                            "output_mode": "body_action",
                            "provider_required": True,
                        },
                    },
                    {
                        "goal_id": "goal-sing",
                        "description": "边走边唱歌",
                        "resource_responsibility": None,
                        "metadata": {
                            "responsibility_kind": "spoken_response",
                            "execution_lane": "speaking",
                            "output_mode": "singing",
                            "provider_required": True,
                        },
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "同时眨眼睛",
                        "metadata": {
                            "responsibility_kind": "executable_action",
                            "execution_lane": "activity",
                            "output_mode": "body_action",
                            "provider_required": True,
                        },
                    },
                ]
            },
            "terminal_plan": {
                "disposition": "mixed",
                "steps": [
                    {
                        "step_id": "step-walk",
                        "capability_id": WALK,
                        "args": {"duration_s": 15.0, "vx_mps": 0.1},
                        "timing": "parallel",
                        "source_goal_ids": ["goal-walk"],
                    },
                    {
                        "step_id": "step-blink",
                        "capability_id": BLINK,
                        "args": {"count": 2},
                        "timing": "parallel",
                        "source_goal_ids": ["goal-blink"],
                    },
                ],
                "goal_outcomes": [
                    {
                        "goal_id": "goal-walk",
                        "disposition": "execute",
                        "step_ids": ["step-walk"],
                    },
                    {
                        "goal_id": "goal-sing",
                        "disposition": "unavailable",
                        "step_ids": [],
                        "unresolved": ["no singing-capable provider"],
                    },
                    {
                        "goal_id": "goal-blink",
                        "disposition": "execute",
                        "step_ids": ["step-blink"],
                    },
                ],
            },
        },
        "interaction_response": {
            "skills": [
                {
                    "capability_id": WALK,
                    "timing": "parallel",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "capability_id": BLINK,
                    "timing": "parallel",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ]
        },
        "execution": {
            "status": "completed",
            "results": [
                {
                    "capability_id": WALK,
                    "status": "completed",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "capability_id": BLINK,
                    "status": "completed",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
        },
    }


class VocalIssueClosureTests(unittest.TestCase):
    def validate(self, summary: dict) -> list[str]:
        errors, _ = validate_closure_summary(
            summary,
            expected_chromie_revision=REVISION,
            expected_walk_capability=WALK,
            expected_blink_capability=BLINK,
        )
        return errors

    def test_passing_summary_closes_exact_scope(self) -> None:
        errors, report = validate_closure_summary(
            passing_summary(),
            expected_chromie_revision=REVISION,
            expected_walk_capability=WALK,
            expected_blink_capability=BLINK,
        )
        self.assertEqual(errors, [])
        self.assertEqual(report["singing_goal_id"], "goal-sing")
        self.assertEqual(
            report["executed_capabilities"],
            [BLINK, WALK],
        )
        self.assertTrue(report["safe_idle_after"])

    def test_generic_respond_cannot_close_singing(self) -> None:
        summary = passing_summary()
        singing = summary["cognitive_runtime"]["terminal_plan"]["goal_outcomes"][1]
        singing["disposition"] = "respond"
        singing["response_text"] = "我唱给你听。"

        errors = self.validate(summary)

        self.assertTrue(
            any("honestly unavailable/refused" in item for item in errors),
            errors,
        )

    def test_singing_goal_cannot_own_activity_request_or_result(self) -> None:
        summary = passing_summary()
        summary["interaction_response"]["skills"][0]["metadata"][
            "source_goal_ids"
        ] = ["goal-sing"]
        summary["execution"]["results"][0]["metadata"]["source_goal_ids"] = [
            "goal-sing"
        ]

        errors = self.validate(summary)

        self.assertTrue(any("incorrectly reached" in item for item in errors), errors)
        self.assertTrue(
            any("ordinary capability execution" in item for item in errors),
            errors,
        )

    def test_body_execution_and_safe_idle_are_required(self) -> None:
        summary = passing_summary()
        summary["execution"]["results"] = []
        summary["status_after"]["safe_idle"] = False

        errors = self.validate(summary)

        self.assertTrue(any("missing body results" in item for item in errors), errors)
        self.assertTrue(any("after safe_idle" in item for item in errors), errors)

    def test_source_binding_must_match_live_endpoint(self) -> None:
        summary = passing_summary()
        summary["provenance"]["soridormi"]["endpoint_revision"] = "d" * 40

        errors = self.validate(summary)

        self.assertTrue(
            any("endpoint/checkout revision mismatch" in item for item in errors),
            errors,
        )

    def test_parallel_timing_and_duration_are_required(self) -> None:
        summary = passing_summary()
        summary["cognitive_runtime"]["terminal_plan"]["steps"][0][
            "timing"
        ] = "sequential"
        summary["cognitive_runtime"]["terminal_plan"]["steps"][0]["args"][
            "duration_s"
        ] = 5.0

        errors = self.validate(summary)

        self.assertTrue(any("timing=parallel" in item for item in errors), errors)
        self.assertTrue(any("walk duration" in item for item in errors), errors)

    def test_runtime_identity_reference_must_match_captured_identity(self) -> None:
        summary = passing_summary()

        errors, _ = validate_closure_summary(
            summary,
            expected_chromie_revision=REVISION,
            expected_walk_capability=WALK,
            expected_blink_capability=BLINK,
            expected_runtime_identity_sha256="d" * 64,
        )

        self.assertTrue(any("runtime identity mismatch" in item for item in errors), errors)

    def test_expected_body_result_requires_goal_ownership(self) -> None:
        summary = passing_summary()
        summary["execution"]["results"][0]["metadata"] = {}

        errors = self.validate(summary)

        self.assertTrue(any("result ownership" in item for item in errors), errors)

    def test_runtime_identity_binds_clean_current_revision(self) -> None:
        payload = {
            "schema_version": 1,
            "chromie": {"revision": REVISION, "dirty": False},
            "runtime_profile": {"fingerprint": "profile"},
            "deployment": {"complete": True},
            "capability_manifests": [{"path": "capabilities/soridormi.json"}],
            "qualification": {
                "source_clean": True,
                "deployment_complete": True,
            },
        }
        payload["identity_sha256"] = canonical_json_sha256(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "identity.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            errors, loaded = validate_runtime_identity(
                path,
                expected_chromie_revision=REVISION,
            )

        self.assertEqual(errors, [])
        self.assertEqual(loaded["identity_sha256"], payload["identity_sha256"])

    def test_runtime_identity_rejects_wrong_revision_and_incomplete_deployment(self) -> None:
        payload = {
            "schema_version": 1,
            "chromie": {"revision": "d" * 40, "dirty": False},
            "runtime_profile": {"fingerprint": "profile"},
            "deployment": {"complete": False},
            "capability_manifests": [{"path": "capabilities/soridormi.json"}],
            "qualification": {
                "source_clean": True,
                "deployment_complete": False,
            },
        }
        payload["identity_sha256"] = canonical_json_sha256(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "identity.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            errors, _ = validate_runtime_identity(
                path,
                expected_chromie_revision=REVISION,
            )

        self.assertTrue(any("revision mismatch" in item for item in errors), errors)
        self.assertTrue(any("deployment is incomplete" in item for item in errors), errors)

    def test_failure_summary_never_claims_closure(self) -> None:
        report = {
            "chromie_revision": REVISION,
            "canonical_gate": {"status": "failed"},
            "runtime_identity": {"status": "passed"},
            "live_run": {"status": "failed"},
            "validation": {"status": "failed", "errors": ["broken"]},
        }

        rendered = _failure_summary(report)

        self.assertIn("Do not close", rendered)
        self.assertIn("broken", rendered)

    def test_live_command_matches_maintained_runner_contract(self) -> None:
        from scripts.interaction_text_mujoco_check import build_parser as build_live_parser

        command = _build_live_command(
            agent_url="http://127.0.0.1:8092",
            soridormi_mcp_url="http://127.0.0.1:8000/mcp",
            manifest=Path("capabilities/soridormi.json"),
            soridormi_repo=Path("../soridormi"),
            live_dir=Path("/tmp/live"),
            runtime_identity_path=Path("/tmp/runtime-identity.json"),
            conversation_id="vocal-issue-1-test",
            timeout_s=1200.0,
            skill_timeout_s=180.0,
            speaker=False,
        )

        self.assertEqual(command.count("--skill-timeout-s"), 1)
        parsed = build_live_parser().parse_args(command[2:])
        self.assertEqual(parsed.text, "你好，你往前走个15秒，然后边走边唱歌，同时眨眼睛。")
        self.assertEqual(parsed.expect_route, "robot_action")
        self.assertTrue(parsed.cognitive_runtime)
        self.assertTrue(parsed.grant_confirmation)
        self.assertFalse(parsed.speaker)
        self.assertEqual(parsed.skill_timeout_s, 180.0)

    def test_close_issue_is_explicit_opt_in(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--soridormi-repo", "../soridormi"])
        self.assertFalse(args.close_issue)
        opted_in = parser.parse_args(
            ["--soridormi-repo", "../soridormi", "--close-issue"]
        )
        self.assertTrue(opted_in.close_issue)

    def test_missing_typed_goal_is_rejected(self) -> None:
        summary = passing_summary()
        broken = copy.deepcopy(summary)
        broken["cognitive_runtime"]["goal_association"]["new_goals"][1][
            "metadata"
        ]["output_mode"] = "speech"

        errors = self.validate(broken)

        self.assertTrue(any("typed singing Goal" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
