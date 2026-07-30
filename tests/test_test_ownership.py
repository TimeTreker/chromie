from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_test_ownership.py"

spec = importlib.util.spec_from_file_location("check_test_ownership", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load test ownership checker")
ownership = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ownership
spec.loader.exec_module(ownership)


class TestOwnershipTests(unittest.TestCase):
    def _write_config(self, root: Path, entries: list[dict[str, str]]) -> Path:
        path = root / "config" / "test_source_ownership.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": "1.0", "python_source_readers": entries}),
            encoding="utf-8",
        )
        return path

    def test_current_repository_has_only_reviewed_python_source_readers(self) -> None:
        self.assertEqual(ownership.audit_test_ownership(ROOT), [])
        self.assertEqual(
            set(ownership.discover_python_source_readers(ROOT)),
            {"tests/test_runtime_configuration.py"},
        )

    def test_unclassified_behavior_source_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_behavior.py").write_text(
                "from pathlib import Path\n"
                "def test_bad():\n"
                "    Path('runtime.py').read_text()\n",
                encoding="utf-8",
            )
            config = self._write_config(root, [])
            findings = ownership.audit_test_ownership(root, config_path=config)
        self.assertEqual(len(findings), 1)
        self.assertIn("may not inspect Python implementation text", findings[0].message)

    def test_reviewed_artifact_contract_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_artifact.py").write_text(
                "from pathlib import Path\n"
                "def test_script_contract():\n"
                "    Path('generated.py').read_text()\n",
                encoding="utf-8",
            )
            config = self._write_config(
                root,
                [
                    {
                        "test_path": "tests/test_artifact.py",
                        "category": "generated_artifact_contract",
                        "reason": "The generated Python file is itself the committed deployment artifact under test.",
                    }
                ],
            )
            findings = ownership.audit_test_ownership(root, config_path=config)
        self.assertEqual(findings, [])

    def test_stale_ownership_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "tests").mkdir()
            config = self._write_config(
                root,
                [
                    {
                        "test_path": "tests/test_old.py",
                        "category": "architecture_policy",
                        "reason": "This exact architecture source contract was previously reviewed and approved.",
                    }
                ],
            )
            findings = ownership.audit_test_ownership(root, config_path=config)
        self.assertEqual(len(findings), 1)
        self.assertIn("stale", findings[0].message)

    def test_weak_or_unsafe_registry_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "tests").mkdir()
            config = self._write_config(
                root,
                [
                    {
                        "test_path": "../escape.py",
                        "category": "behavior",
                        "reason": "short",
                    }
                ],
            )
            approved, findings = ownership.load_ownership(config, root=root)
        self.assertEqual(approved, {})
        self.assertEqual(len(findings), 1)

    def test_maintained_gate_runs_test_ownership_checker(self) -> None:
        text = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/check_test_ownership.py", text)


if __name__ == "__main__":
    unittest.main()
