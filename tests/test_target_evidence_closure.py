from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import run_target_evidence_closure as closure

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifests" / "target_evidence_closure_v1.json"


class TargetEvidenceClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def initialize(self, root: Path, *, profile: str = "source_bound_development") -> dict:
        state = {
            "schema_version": 1,
            "closure_id": self.manifest["closure_id"],
            "profile": profile,
            "source": {"revision": "revision-1", "dirty": False},
            "reviewer": "reviewer-1",
            "tracks": {},
            "qualification": {"release_qualified": False},
        }
        self.write_json(root / "closure-state.json", state)
        return state

    def approve_review(self, root: Path, track_id: str, report: Path) -> None:
        checks = {
            check: "approved"
            for check in self.manifest[f"{track_id}_review_checks"]
        }
        spec = self.manifest["tracks"][track_id]
        self.write_json(
            root / spec["review"],
            {
                "schema_version": 1,
                "closure_id": self.manifest["closure_id"],
                "track_id": track_id,
                "artifact_sha256": closure._sha256(report),
                "reviewer": "reviewer-1",
                "decision": "approved",
                "checks": checks,
            },
        )

    def write_required_reports(self, root: Path) -> None:
        self.write_json(
            root / "gateway-core" / "qualification.json",
            {
                "expected_provenance": {"chromie_revision": "revision-1"},
                "qualification": {"issue_closure_eligible": True},
            },
        )
        self.write_json(
            root / "agent-skill-weather" / "qualification.json",
            {
                "expected_provenance": {"chromie_revision": "revision-1"},
                "qualification": {"track_closure_eligible": True},
            },
        )
        social = root / "social-attention" / "qualification.json"
        self.write_json(
            social,
            {
                "qualification": {"state": "human_review_required"},
                "runs": [
                    {"run_id": "social-1", "code_revision": "revision-1"}
                ],
            },
        )
        self.approve_review(root, "social_attention", social)
        self.write_json(
            root / "lan-exposure" / "qualification.json",
            {
                "passed": True,
                "source_revision": "revision-1",
                "release_qualified": False,
            },
        )

    def args(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            manifest=MANIFEST_PATH,
            evidence_root=root,
            python="python",
        )

    def test_source_bound_profile_finalizes_without_physical_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            self.write_required_reports(root)
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ), redirect_stdout(io.StringIO()):
                result = closure.finalize(self.args(root))
            self.assertEqual(result, 0)
            report = json.loads((root / "closure-report.json").read_text())
            self.assertTrue(
                report["qualification"]["target_evidence_closure_eligible"]
            )
            self.assertFalse(report["qualification"]["release_qualified"])
            self.assertFalse(report["qualification"]["physical_support_claimed"])

    def test_physical_profile_requires_voice_and_robot_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root, profile="supervised_physical_pilot")
            self.write_required_reports(root)
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ), redirect_stdout(io.StringIO()):
                result = closure.finalize(self.args(root))
            self.assertEqual(result, 1)
            report = json.loads((root / "closure-report.json").read_text())
            self.assertFalse(
                report["qualification"]["target_evidence_closure_eligible"]
            )
            self.assertTrue(report["qualification"]["physical_support_claimed"])

    def test_review_must_match_exact_report_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.initialize(root)
            self.write_required_reports(root)
            social = root / "social-attention" / "qualification.json"
            payload = json.loads(social.read_text())
            payload["changed_after_review"] = True
            self.write_json(social, payload)
            refreshed = closure._refresh(root, self.manifest, state)
            social_status = refreshed["tracks"]["social_attention"]
            self.assertFalse(social_status["eligible"])
            self.assertTrue(
                any("fingerprint" in error for error in social_status["errors"])
            )

    def test_required_track_report_must_claim_expected_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.initialize(root)
            self.write_required_reports(root)
            self.write_json(
                root / "agent-skill-weather" / "qualification.json",
                {
                    "expected_provenance": {"chromie_revision": "revision-1"},
                    "qualification": {"track_closure_eligible": False},
                },
            )
            refreshed = closure._refresh(root, self.manifest, state)
            status = refreshed["tracks"]["agent_skill_weather"]
            self.assertFalse(status["eligible"])
            self.assertTrue(
                any("eligibility_mismatch" in error for error in status["errors"])
            )

    def test_finalize_rejects_dirty_or_moved_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            self.write_required_reports(root)
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-2", "dirty": True},
            ), redirect_stdout(io.StringIO()):
                result = closure.finalize(self.args(root))
            self.assertEqual(result, 1)
            report = json.loads((root / "closure-report.json").read_text())
            self.assertTrue(any("clean" in item for item in report["errors"]))
            self.assertTrue(any("revision" in item for item in report["errors"]))

    def test_track_report_from_another_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.initialize(root)
            self.write_required_reports(root)
            self.write_json(
                root / "agent-skill-weather" / "qualification.json",
                {
                    "expected_provenance": {"chromie_revision": "revision-2"},
                    "qualification": {"track_closure_eligible": True},
                },
            )
            refreshed = closure._refresh(root, self.manifest, state)
            status = refreshed["tracks"]["agent_skill_weather"]
            self.assertFalse(status["eligible"])
            self.assertTrue(
                any("source_revision_mismatch" in item for item in status["errors"])
            )

    def test_collection_rejects_dirty_or_moved_initialized_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            args = argparse.Namespace(
                manifest=MANIFEST_PATH,
                evidence_root=root,
                python="python",
                reviewer="reviewer-1",
                agent_url="http://127.0.0.1:8092",
                soridormi_repo=ROOT.parent / "soridormi",
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                speaker=False,
                resume=False,
                dry_run=True,
            )
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-2", "dirty": False},
            ):
                with self.assertRaisesRegex(ValueError, "initialized"):
                    closure.collect_core(args)

    def test_collect_social_covers_every_reviewed_mode_style_slice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            commands: list[list[str]] = []
            args = argparse.Namespace(
                manifest=MANIFEST_PATH,
                evidence_root=root,
                python="python",
                dataset=ROOT / "benchmarks" / "datasets" / "social_attention" / "cases.json",
                adapter="live_service_text",
                prompt_revision="prompt-1",
                provider_revision="provider-1",
                hardware_profile="rtx5090",
                mind_profile="mind-1",
                runtime_topology="cognitive-runtime-apply",
                effective_model=["fast_planner=qwen3:4b"],
                apply_lane=["chat", "robot_action"],
                sample_count=1,
                timeout_s=180.0,
                dry_run=True,
            )
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ), patch.object(
                closure,
                "_run_command",
                side_effect=lambda command, dry_run: commands.append(command) or 0,
            ):
                result = closure.collect_social(args)
            self.assertEqual(result, 0)
            e2e = [item for item in commands if "benchmarks.e2e.run" in item]
            self.assertEqual(len(e2e), 11)
            pairs = {(item[item.index("--mode") + 1], item[item.index("--style") + 1]) for item in e2e}
            self.assertIn(("on", "courteous"), pairs)
            self.assertIn(("off", "custom"), pairs)
            self.assertIn(("report_only", "reserved"), pairs)
            qualification = [
                item for item in commands if "benchmarks.social_attention" in item
            ]
            self.assertEqual(len(qualification), 1)
            self.assertEqual(qualification[0].count("--report"), 11)

    def test_current_revision_profile_requires_source_behavior_and_provider_fault_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root, profile="current_revision_qualification")
            self.write_required_reports(root)
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ):
                state = closure._refresh(root, self.manifest, closure._load_state(root, self.manifest))
            self.assertFalse(state["qualification"]["required_complete"])
            self.assertIn("source_qualification", state["tracks"])
            self.assertIn("interaction_behavior", state["tracks"])
            self.assertIn("provider_faults", state["tracks"])

    def test_interaction_behavior_track_requires_execute_full_and_clean_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root, profile="current_revision_qualification")
            report = root / "interaction-behavior" / "qualification.json"
            self.write_json(
                report,
                {
                    "ok": True,
                    "mode": "live-text",
                    "evidence_level": "C-preview",
                    "execute": False,
                    "assertion_scope": "user-outcome",
                    "goal_driven_runtime": "apply",
                    "provenance": {
                        "chromie_revision": "revision-1",
                        "chromie_dirty": False,
                    },
                },
            )
            status = closure._track_status(
                root,
                self.manifest,
                "interaction_behavior",
                expected_revision="revision-1",
            )
            self.assertFalse(status["eligible"])
            self.assertTrue(
                any(error.startswith("required_value_mismatch") for error in status["errors"])
            )

    def test_interaction_behavior_collector_runs_manifest_cases_as_execute_full(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root, profile="current_revision_qualification")
            runtime_identity = root / "runtime-identity.json"
            self.write_json(
                runtime_identity,
                {
                    "identity_sha256": "runtime-1",
                    "chromie": {"revision": "revision-1", "dirty": False},
                },
            )
            args = argparse.Namespace(
                manifest=MANIFEST_PATH,
                evidence_root=root,
                python="python",
                reviewer="reviewer-1",
                agent_url="http://127.0.0.1:8092",
                speaker=False,
                resume=False,
                dry_run=True,
                runtime_identity=runtime_identity,
                soridormi_repo="",
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                case_timeout_s=30.0,
            )
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ), patch.object(closure, "_run_command", return_value=0) as run:
                self.assertEqual(closure.collect_interaction_behavior(args), 0)
            command = run.call_args.args[0]
            self.assertIn("--execute", command)
            self.assertIn("full", command)
            self.assertIn("--grant-confirmation", command)
            for case_id in self.manifest["interaction_behavior_cases"]:
                self.assertIn(case_id, command)

    def test_current_revision_profile_finalizes_when_all_required_tracks_match_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root, profile="current_revision_qualification")
            self.write_required_reports(root)
            self.write_json(
                root / "source" / "qualification.json",
                {
                    "revision": "revision-1",
                    "source_clean": True,
                    "source_qualified": True,
                    "target_validated": False,
                    "release_qualified": False,
                },
            )
            self.write_json(
                root / "interaction-behavior" / "qualification.json",
                {
                    "ok": True,
                    "mode": "live-text",
                    "evidence_level": "C",
                    "execute": True,
                    "assertion_scope": "full",
                    "goal_driven_runtime": "apply",
                    "provenance": {
                        "chromie_revision": "revision-1",
                        "chromie_dirty": False,
                    },
                },
            )
            self.write_json(
                root / "provider-faults" / "qualification.json",
                {
                    "passed": True,
                    "evidence_source": "live",
                    "provenance": {
                        "chromie_revision": "revision-1",
                        "chromie_dirty": False,
                    },
                    "qualification": {
                        "live_provider_faults_eligible": True,
                    },
                },
            )
            with patch.object(
                closure,
                "_git_state",
                return_value={"revision": "revision-1", "dirty": False},
            ), redirect_stdout(io.StringIO()):
                result = closure.finalize(self.args(root))
            self.assertEqual(result, 0)
            report = json.loads((root / "closure-report.json").read_text())
            self.assertTrue(report["qualification"]["target_evidence_closure_eligible"])
            self.assertFalse(report["qualification"]["physical_support_claimed"])


if __name__ == "__main__":
    unittest.main()
