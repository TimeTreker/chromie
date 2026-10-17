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
        approved, findings = ownership.load_ownership(
            ROOT / "config" / "test_source_ownership.json",
            root=ROOT,
        )
        self.assertEqual(findings, [])
        self.assertEqual(
            set(ownership.discover_python_source_readers(ROOT)),
            set(approved),
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

    def test_detector_finds_indirect_python_source_reads(self) -> None:
        sources = {
            "getsource": "import inspect\ndef test_x():\n    inspect.getsource(test_x)\n",
            "helper": (
                "from pathlib import Path\n"
                "def _text(path):\n    return Path(path).read_text()\n"
                "def test_x():\n    _text('agent/app/runtime.py')\n"
            ),
            "glob_loop": (
                "from pathlib import Path\n"
                "def test_x():\n"
                "    for path in sorted(Path('agent').rglob('*.py')):\n"
                "        path.read_text()\n"
            ),
            "named_path": (
                "from pathlib import Path\n"
                "SOURCE = Path('orchestrator') / 'runtime.py'\n"
                "def test_x():\n    SOURCE.read_text()\n"
            ),
            "module_file": (
                "from pathlib import Path\nimport json\n"
                "def test_x():\n    Path(json.__file__).read_text()\n"
            ),
        }
        for form, source in sources.items():
            with self.subTest(form=form), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "tests").mkdir()
                (root / "tests" / "test_probe.py").write_text(source, encoding="utf-8")
                self.assertIn(
                    "tests/test_probe.py", ownership.discover_python_source_readers(root)
                )

    def test_detector_ignores_non_source_reads(self) -> None:
        source = (
            "from pathlib import Path\nimport importlib.util\n"
            "SCRIPT = Path('scripts') / 'tool.py'\n"
            "spec = importlib.util.spec_from_file_location('tool', SCRIPT)\n"
            "def test_x(tmp_path):\n"
            "    names = [p.name for p in Path('shared').rglob('*.py')]\n"
            "    Path('docs/README.md').read_text()\n"
            "    (tmp_path / 'probe.json').read_text()\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "tests").mkdir()
            (root / "tests" / "test_probe.py").write_text(source, encoding="utf-8")
            self.assertEqual(ownership.discover_python_source_readers(root), {})

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
