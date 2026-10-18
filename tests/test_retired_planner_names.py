"""The docs checker keeps the retired tiered planner names out of prose and comments."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_docs


def _run(root: Path) -> list[str]:
    errors: list[str] = []
    with mock.patch.object(check_docs, "ROOT", root):
        check_docs.check_retired_planner_names(errors)
    return errors


class RetiredPlannerNameGuardTest(unittest.TestCase):
    def test_repository_has_no_retired_planner_names(self) -> None:
        errors: list[str] = []
        check_docs.check_retired_planner_names(errors)
        self.assertEqual(errors, [])

    def test_markdown_prose_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs").mkdir()
            (root / "docs" / "note.md").write_text(
                "The " + "Fast " + "Planner answers first.\n", encoding="utf-8"
            )
            errors = _run(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("docs/note.md:1", errors[0])

    def test_python_comment_and_docstring_are_rejected_but_string_literals_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "comment.py").write_text(
                "x = 1  # the " + "deep " + "planner escalation\n", encoding="utf-8"
            )
            (root / "docstring.py").write_text(
                'def f():\n    """Ask the ' + "Fast " + 'Planner."""\n    return 1\n',
                encoding="utf-8",
            )
            (root / "wire.py").write_text(
                'ROLE = "' + "Fast " + 'Planner Agent"\n', encoding="utf-8"
            )
            errors = _run(root)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("comment.py:1" in item for item in errors))
        self.assertTrue(any("docstring.py:2" in item for item in errors))

    def test_history_and_recorded_corpora_are_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            name = "Deep " + "Planner"
            (root / "CHANGELOG.md").write_text(f"- Added the {name}.\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "STATUS.md").write_text(
                f"The {name} was retired on 2026-10-11.\n", encoding="utf-8"
            )
            for folder in ("benchmarks/integration", "benchmarks/datasets", "agent/prompts"):
                (root / folder).mkdir(parents=True)
            (root / "benchmarks" / "integration" / "README.md").write_text(name, encoding="utf-8")
            (root / "benchmarks" / "datasets" / "corpus.py").write_text(f"# {name}\n", encoding="utf-8")
            (root / "agent" / "prompts" / "system.txt").write_text(name, encoding="utf-8")
            errors = _run(root)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
