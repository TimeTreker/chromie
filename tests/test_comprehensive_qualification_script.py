from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qualification" / "run_comprehensive_test.sh"


class ComprehensiveQualificationScriptTests(unittest.TestCase):
    def test_script_is_versioned_executable_and_shell_valid(self) -> None:
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_help_declares_hybrid_evidence_and_noninteractive_audio(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("deterministic benchmark", completed.stdout)
        self.assertIn("semantic-evidence", completed.stdout)
        self.assertIn("No operator speech is used", completed.stdout)
        self.assertIn("--collect-only", completed.stdout)
        self.assertIn("--strict-exit", completed.stdout)
        self.assertIn("--ci", completed.stdout)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--semantic-reviewers", completed.stdout)
        self.assertIn("independent model ensemble", completed.stdout)
        self.assertTrue((ROOT / "benchmarks" / "manifests" / "fault_injection_v1.json").is_file())


    def test_dry_run_accepts_repository_owned_reviewer_configuration(self) -> None:
        config = ROOT / "benchmarks" / "manifests" / "semantic_reviewers.example.json"
        completed = subprocess.run(
            [
                str(SCRIPT),
                "--repo",
                str(ROOT),
                "--semantic-reviewers",
                str(config),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(str(config), completed.stdout)
        self.assertIn(
            "Optionally run independent configured LLM judges",
            completed.stdout,
        )

    def test_dry_run_preserves_oracle_ownership_and_runs_no_hardware(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "--repo", str(ROOT), "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "Objective fixtures, contracts, and invariants remain deterministic truth",
            completed.stdout,
        )
        self.assertIn(
            "Semantic dimensions remain pending retained LLM or human adjudication",
            completed.stdout,
        )
        self.assertIn(
            "No operator voice or pronunciation judgment is required",
            completed.stdout,
        )
        self.assertNotIn("Chromie comprehensive collection complete", completed.stdout)

    def test_dry_run_reports_strict_exit_mode(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "--repo", str(ROOT), "--strict-exit", "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Strict exit:      1", completed.stdout)

    def test_script_records_machine_readable_overall_status(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"overall_status": overall_status', source)
        self.assertIn('"review_infrastructure_failed": review_infrastructure_failed', source)
        self.assertIn('[[ "$OVERALL_STATUS" != "passed" ]]', source)


if __name__ == "__main__":
    unittest.main()
