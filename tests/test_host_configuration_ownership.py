from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_host_configuration_ownership import check

ROOT = Path(__file__).resolve().parents[1]


class HostConfigurationOwnershipTests(unittest.TestCase):
    def test_check_excludes_virtual_environments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "orchestrator" / "runtime" / "host_settings.py"
            settings.parent.mkdir(parents=True)
            settings.write_text('os.getenv("OWNED_SETTING")\n', encoding="utf-8")
            (root / "orchestrator" / "orchestrator.py").write_text(
                "def run():\n    return None\n",
                encoding="utf-8",
            )
            ignored = root / "orchestrator" / ".venv" / "lib" / "dependency.py"
            ignored.parent.mkdir(parents=True)
            ignored.write_text(
                'os.getenv("DEPENDENCY_SETTING")\n',
                encoding="utf-8",
            )

            self.assertEqual(check(root), [])

    def test_every_direct_orchestrator_environment_read_is_typed(self) -> None:
        self.assertEqual(check(ROOT), [])

    def test_maintained_gate_runs_host_configuration_check(self) -> None:
        script = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
        self.assertIn("python scripts/check_host_configuration_ownership.py", script)

    def test_cli_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_host_configuration_ownership.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Host configuration ownership passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
