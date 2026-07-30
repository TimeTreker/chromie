from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_ruff.py"

spec = importlib.util.spec_from_file_location("run_ruff", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load Ruff gate")
run_ruff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_ruff)


class RuffGateTests(unittest.TestCase):
    def _fake_ruff(self, directory: Path, version: str) -> Path:
        path = directory / "ruff"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"VERSION = {version!r}\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print(f'ruff {VERSION}')\n"
            "    raise SystemExit(0)\n"
            "if sys.argv[1:2] == ['check']:\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_scope_is_sorted_unique_and_existing(self) -> None:
        entries = run_ruff.load_scope(ROOT / "config" / "ruff_scope.txt")
        self.assertEqual(entries, tuple(sorted(set(entries))))
        self.assertGreaterEqual(len(entries), 4)

    def test_scope_rejects_missing_and_escaping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scope = root / "scope.txt"
            scope.write_text("../escape.py\n", encoding="utf-8")
            with self.assertRaises(run_ruff.RuffGateError):
                run_ruff.load_scope(scope, root=root)
            scope.write_text("missing.py\n", encoding="utf-8")
            with self.assertRaises(run_ruff.RuffGateError):
                run_ruff.load_scope(scope, root=root)

    def test_pinned_version_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = self._fake_ruff(Path(temp_dir), "0.15.0")
            with self.assertRaisesRegex(run_ruff.RuffGateError, "version mismatch"):
                run_ruff.verify_ruff_version(str(fake))

    def test_fake_pinned_ruff_executes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = self._fake_ruff(Path(temp_dir), run_ruff.RUFF_VERSION)
            result = run_ruff.run_ruff(ruff_command=str(fake))
        self.assertEqual(result, 0)

    def test_configuration_selects_only_reviewed_defect_families(self) -> None:
        text = (ROOT / "ruff.toml").read_text(encoding="utf-8")
        self.assertIn('select = ["E4", "E7", "E9", "F", "B", "ASYNC"]', text)
        self.assertIn("preview = false", text)
        self.assertNotIn('select = ["ALL"]', text)
        self.assertNotIn("extend-select", text)

    def test_test_dependencies_pin_ruff(self) -> None:
        requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
        self.assertIn(f"ruff=={run_ruff.RUFF_VERSION}", requirements.splitlines())

    def test_maintained_gate_invokes_ruff(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/run_ruff.py", script)


if __name__ == "__main__":
    unittest.main()
