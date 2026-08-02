from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.check_host_configuration_ownership import check

ROOT = Path(__file__).resolve().parents[1]


class HostConfigurationOwnershipTests(unittest.TestCase):
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
