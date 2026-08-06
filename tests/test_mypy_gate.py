from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_mypy.py"

spec = importlib.util.spec_from_file_location("run_mypy", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load Mypy gate")
run_mypy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_mypy)


class MypyGateTests(unittest.TestCase):
    def _fake_mypy(self, directory: Path, version: str) -> Path:
        path = directory / "mypy"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"VERSION = {version!r}\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print(f'mypy {VERSION} (compiled: yes)')\n"
            "    raise SystemExit(0)\n"
            "if '--config-file' in sys.argv:\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_scope_matches_last_verified_clean_baseline(self) -> None:
        entries = run_mypy.load_scope(ROOT / "config" / "mypy_scope.txt")
        self.assertEqual(
            entries,
            (
                "scripts/check_local_runtime_exposure.py",
                "scripts/run_ruff.py",
                "shared/chromie_contracts/errors.py",
                "shared/chromie_contracts/semantic_authority.py",
            ),
        )

    def test_scope_accepts_python_package_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scope = root / "scope.txt"
            scope.write_text("../escape.py\n", encoding="utf-8")
            with self.assertRaises(run_mypy.MypyGateError):
                run_mypy.load_scope(scope, root=root)
            package = root / "package"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "new_module.py").write_text("VALUE: int = 1\n", encoding="utf-8")
            scope.write_text("package\n", encoding="utf-8")
            self.assertEqual(
                run_mypy.load_scope(scope, root=root),
                ("package/__init__.py", "package/new_module.py"),
            )

    def test_pinned_version_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = self._fake_mypy(Path(temp_dir), "2.2.0")
            with self.assertRaisesRegex(run_mypy.MypyGateError, "version mismatch"):
                run_mypy.verify_mypy_version(str(fake))

    def test_fake_pinned_mypy_executes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = self._fake_mypy(Path(temp_dir), run_mypy.MYPY_VERSION)
            result = run_mypy.run_mypy(mypy_command=str(fake))
        self.assertEqual(result, 0)

    def test_configuration_enforces_incremental_contract_quality(self) -> None:
        text = (ROOT / "mypy.ini").read_text(encoding="utf-8")
        for setting in (
            "disallow_untyped_defs = True",
            "disallow_incomplete_defs = True",
            "no_implicit_optional = True",
            "warn_return_any = True",
            "warn_unused_ignores = True",
        ):
            self.assertIn(setting, text)
        self.assertNotIn("ignore_errors = True", text)
        self.assertNotIn("explicit_package_bases = True", text)
        self.assertNotIn("mypy_path = shared", text)
        self.assertNotIn("follow_imports = skip", text)

    def test_test_dependencies_pin_mypy(self) -> None:
        requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
        self.assertIn(f"mypy=={run_mypy.MYPY_VERSION}", requirements.splitlines())

    def test_maintained_gate_invokes_mypy_after_ruff(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        ruff_index = script.index("python scripts/run_ruff.py")
        mypy_index = script.index("python scripts/run_mypy.py")
        self.assertLess(ruff_index, mypy_index)


if __name__ == "__main__":
    unittest.main()
