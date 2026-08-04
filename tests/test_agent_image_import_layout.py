from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentImageImportLayoutTests(unittest.TestCase):
    def test_agent_catalog_imports_with_image_pythonpath(self) -> None:
        """Exercise the same top-level packages copied by agent/Dockerfile."""

        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            (
                str(ROOT / "agent"),
                str(ROOT / "shared"),
            )
        )
        script = "\n".join(
            (
                "from app.capabilities.catalog import CapabilityCatalog",
                "from chromie_contracts.soridormi_body_contract import (",
                "    normalize_soridormi_body_contract,",
                ")",
                "assert CapabilityCatalog.__name__ == 'CapabilityCatalog'",
                "assert callable(normalize_soridormi_body_contract)",
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=directory,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg=(
                "Agent import failed under the production image PYTHONPATH.\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            ),
        )

    def test_agent_dockerfile_contains_packaged_import_smoke_check(self) -> None:
        dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "COPY shared/chromie_contracts ./chromie_contracts",
            dockerfile,
        )
        self.assertIn(
            "from app.capabilities.catalog import CapabilityCatalog",
            dockerfile,
        )
        self.assertIn(
            "from chromie_contracts.soridormi_body_contract import",
            dockerfile,
        )


if __name__ == "__main__":
    unittest.main()
