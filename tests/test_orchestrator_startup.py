from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from orchestrator.orchestrator import VoiceAssistant, load_runtime_environment

ROOT = Path(__file__).resolve().parents[1]


class OrchestratorEnvironmentBootstrapTests(unittest.TestCase):
    def test_import_does_not_load_generated_runtime_environment(self) -> None:
        code = (
            "from unittest import mock\n"
            "with mock.patch('dotenv.load_dotenv') as loader:\n"
            "    import orchestrator.orchestrator\n"
            "    if loader.call_count:\n"
            "        raise SystemExit(f'load_dotenv called {loader.call_count} times')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_explicit_bootstrap_loads_owned_environment_files(self) -> None:
        project_root = Path("/project")
        orchestrator_dir = project_root / "orchestrator"
        with mock.patch("orchestrator.orchestrator.load_dotenv") as loader:
            load_runtime_environment(
                project_root=project_root,
                orchestrator_dir=orchestrator_dir,
            )

        self.assertEqual(
            loader.call_args_list,
            [
                mock.call(project_root / ".env.runtime"),
                mock.call(orchestrator_dir / ".env.local"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
