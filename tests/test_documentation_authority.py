from __future__ import annotations

import json
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from collections.abc import Callable

from scripts import check_docs


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

    def probe(
        self, mutate: Callable[[Path, dict], None], baseline: int | None = None
    ) -> tuple[list[str], str]:
        payload = json.loads(check_docs.DOCUMENTATION_AUTHORITY.read_text(encoding="utf-8"))
        if baseline is not None:
            payload["surface_baselines"] = dict.fromkeys(
                ("core_reading_path", "markdown_files", "docs_root_markdown_files"), baseline
            )
            payload["line_baselines"] = dict.fromkeys(
                ("CHANGELOG.md", "DEVELOPMENT_CHECKPOINT.md", "docs/STATUS.md"), baseline
            )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for original in check_docs.markdown_files():
                target = root / original.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            for contract in payload["specialized_ownership"]["mechanical_contracts"]:
                target = root / contract["checker"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / contract["checker"], target)
            mutate(root, payload)
            config = root / "authority.json"
            config.write_text(json.dumps(payload), encoding="utf-8")
            errors: list[str] = []
            output = io.StringIO()
            with (
                mock.patch.object(check_docs, "ROOT", root),
                mock.patch.object(check_docs, "DOC_INDEX", root / "docs/README.md"),
                mock.patch.object(check_docs, "DOCUMENTATION_AUTHORITY", config),
                contextlib.redirect_stdout(output),
            ):
                check_docs.check_documentation_authority(errors)
                check_docs.check_document_index(errors)
        return errors, output.getvalue()

    def test_extra_blank_lines_are_reported_without_rejecting_authority(self) -> None:
        for raw_path in ("CHANGELOG.md", "DEVELOPMENT_CHECKPOINT.md", "docs/STATUS.md"):
            with self.subTest(path=raw_path):
                def pad(root: Path, payload: dict, raw_path: str = raw_path) -> None:
                    path = root / raw_path
                    path.write_text(path.read_text(encoding="utf-8") + "\n" * 300, encoding="utf-8")
                errors, output = self.probe(pad)
                self.assertEqual(errors, [])
                self.assertIn(raw_path + "=", output)
                self.assertIn("delta=+", output)
                self.assertIn("informational", output)

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

    def test_owned_document_and_reading_path_growth_are_reported(self) -> None:
        def add_owned_documents(root: Path, payload: dict) -> None:
            for name in ("probe-one.md", "probe-two.md"):
                (root / "docs" / name).write_text("# Component reference\n", encoding="utf-8")
                for entry in ("agent/README.md", "docs/README.md"):
                    path = root / entry
                    path.write_text(path.read_text(encoding="utf-8") + f"\n[Reference](../docs/{name})\n", encoding="utf-8")

        def add_core_document(root: Path, payload: dict) -> None:
            payload["core_reading_path"].append("docs/MEMORY_EXTRACTION.md")

        for mutate, metric in (
            (add_owned_documents, "markdown_files"),
            (add_core_document, "core_reading_path"),
        ):
            with self.subTest(metric=metric):
                errors, output = self.probe(mutate)
                self.assertEqual(errors, [])
                self.assertIn(metric + "=", output)
                self.assertIn("delta=+", output)
                self.assertIn("informational", output)

    def test_document_ownership_blocks_above_and_below_size_baselines(self) -> None:
        def missing_role(root: Path, payload: dict) -> None:
            payload["authorities"] = [entry for entry in payload["authorities"] if entry["role"] != "mission_architecture"]

        def missing_entrypoint(root: Path, payload: dict) -> None:
            payload["specialized_ownership"]["entrypoint_paths"].append("missing.md")

        def duplicate_core(root: Path, payload: dict) -> None:
            payload["core_reading_path"][-1] = payload["core_reading_path"][0]

        def index_only(root: Path, payload: dict) -> None:
            (root / "unowned.md").write_text("# Unowned\n", encoding="utf-8")
            path = root / "docs/README.md"
            path.write_text(path.read_text(encoding="utf-8") + "\n[Unowned](../unowned.md)\n", encoding="utf-8")

        def unindexed(root: Path, payload: dict) -> None:
            (root / "unindexed.md").write_text("# Unindexed\n", encoding="utf-8")

        for mutate, expected in (
            (missing_role, "missing roles"),
            (missing_entrypoint, "entrypoint does not exist"),
            (duplicate_core, "duplicate documents"),
            (index_only, "no current owner"),
            (unindexed, "does not index"),
        ):
            for baseline in (0, 10000):
                with self.subTest(error=expected, baseline=baseline):
                    errors, output = self.probe(mutate, baseline)
                    self.assertTrue(any(expected in error for error in errors), errors)
                    self.assertIn("informational", output)

    def test_malformed_measurement_baseline_is_not_silently_ignored(self) -> None:
        errors, _ = self.probe(lambda root, payload: None, baseline=-1)
        self.assertTrue(any("surface_baselines.markdown_files" in error for error in errors), errors)

    def test_measured_authority_document_must_remain_repository_local(self) -> None:
        def escaping_path(root: Path, payload: dict) -> None:
            payload["line_baselines"]["../outside.md"] = 0

        errors, _ = self.probe(escaping_path)
        self.assertTrue(any("measured authority document escapes repository" in error for error in errors), errors)


    def test_configuration_authority_has_unique_h2_sections(self) -> None:
        headings = [
            line.strip()
            for line in (ROOT / "docs" / "CONFIGURATION.md")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("## ")
        ]
        self.assertEqual(len(headings), len(set(headings)))

    def test_specialized_documents_have_owned_entrypoints_or_contracts(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_docs.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(
            (ROOT / "config" / "documentation_authority.json").read_text(
                encoding="utf-8"
            )
        )
        ownership = payload["specialized_ownership"]
        self.assertTrue(ownership["entrypoint_globs"])
        self.assertTrue(ownership["mechanical_contracts"])

    def test_retired_target_runner_is_not_current_authority(self) -> None:
        self.assertFalse((ROOT / "scripts" / "run_supervised_target_acceptance.sh").exists())
        for path in (ROOT / "docs" / "ACCEPTANCE.md", ROOT / "CHROMIE_RUNBOOK.md"):
            self.assertNotIn("run_supervised_target_acceptance.sh", path.read_text(encoding="utf-8"))

    def test_current_gate_summary_rejects_copied_test_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = Path(temp_dir) / "summary.md"
            summary.write_text(
                "The gate passed 1,999 primary tests.\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            with (
                mock.patch.object(check_docs, "ROOT", Path(temp_dir)),
                mock.patch.object(
                    check_docs,
                    "CURRENT_GATE_SUMMARY_FILES",
                    [summary],
                ),
            ):
                check_docs.check_current_gate_summaries(errors)
            self.assertTrue(any("hardcodes a test count" in error for error in errors))

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
