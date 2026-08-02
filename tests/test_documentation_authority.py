from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationAuthorityTests(unittest.TestCase):
    def test_authority_registry_has_unique_required_roles(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "documentation_authority.json").read_text(
                encoding="utf-8"
            )
        )
        entries = payload["authorities"]
        roles = [entry["role"] for entry in entries]
        paths = [entry["path"] for entry in entries]

        self.assertEqual(len(roles), len(set(roles)))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertIn("implementation_and_evidence_status", roles)
        self.assertIn("target_evidence_closure", roles)
        self.assertIn("resume_point", roles)
        self.assertIn("delivery_order", roles)
        for raw_path in paths:
            self.assertTrue((ROOT / raw_path).is_file(), raw_path)

    def test_live_owner_documents_are_concise(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "documentation_authority.json").read_text(
                encoding="utf-8"
            )
        )
        for raw_path, limit in payload["concise_line_limits"].items():
            line_count = len(
                (ROOT / raw_path).read_text(encoding="utf-8").splitlines()
            )
            self.assertLessEqual(line_count, int(limit), raw_path)

    def test_historical_archives_are_removed_from_current_tree(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "documentation_authority.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["historical_archives"], [])
        for raw_path in (
            "CHANGELOG_ARCHIVE_2026-07-30.md",
            "DEVELOPMENT_CHECKPOINT_ARCHIVE_2026-07-30.md",
            "docs/STATUS_ARCHIVE_2026-07-30.md",
        ):
            self.assertFalse((ROOT / raw_path).exists(), raw_path)

    def test_core_reading_path_and_surface_ratchets_are_bounded(self) -> None:
        payload = json.loads(
            (ROOT / "config" / "documentation_authority.json").read_text(
                encoding="utf-8"
            )
        )
        core = payload["core_reading_path"]
        ratchets = payload["surface_ratchets"]
        self.assertLessEqual(len(core), ratchets["max_core_reading_path"])
        self.assertEqual(len(core), len(set(core)))
        self.assertLessEqual(
            len(list(ROOT.rglob("*.md"))),
            ratchets["max_markdown_files"],
        )
        self.assertLessEqual(
            len(list((ROOT / "docs").glob("*.md"))),
            ratchets["max_docs_root_markdown_files"],
        )


    def test_retired_target_runner_is_not_current_authority(self) -> None:
        self.assertFalse((ROOT / "scripts" / "run_supervised_target_acceptance.sh").exists())
        for path in (ROOT / "docs" / "ACCEPTANCE.md", ROOT / "CHROMIE_RUNBOOK.md"):
            self.assertNotIn("run_supervised_target_acceptance.sh", path.read_text(encoding="utf-8"))

    def test_canonical_documentation_gate_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_docs.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("documentation authority", completed.stdout)


if __name__ == "__main__":
    unittest.main()
