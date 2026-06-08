from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "m5_target_acceptance.sh"


class M5TargetAcceptanceTests(unittest.TestCase):
    def test_requires_explicit_supervision(self) -> None:
        result = subprocess.run(
            [str(SCRIPT)],
            cwd=ROOT,
            env={
                **os.environ,
                "M5_DRY_RUN": "1",
                "SORIDORMI_MCP_URL": "http://soridormi.example/mcp",
            },
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("SUPERVISED_ACCEPTANCE=1", result.stderr)

    def test_dry_run_records_planned_target_evidence(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            evidence = Path(temp_dir) / "evidence"
            result = subprocess.run(
                [str(SCRIPT)],
                cwd=ROOT,
                env={
                    **os.environ,
                    "SUPERVISED_ACCEPTANCE": "1",
                    "M5_DRY_RUN": "1",
                    "M5_ACCEPTANCE_ID": "test-acceptance",
                    "M5_EVIDENCE_DIR": str(evidence),
                    "SORIDORMI_MCP_URL": "http://soridormi.example/mcp",
                    "CHROMIE_ACTIVE_PROFILE": "rtx4090",
                    "CHROMIE_NVIDIA_GPU_NAME": "Test GPU",
                    "CHROMIE_NVIDIA_COMPUTE_CAP": "8.9",
                },
                check=True,
                capture_output=True,
                text=True,
            )

            summary = (evidence / "summary.env").read_text()
            self.assertIn("M5_ACCEPTANCE_STATUS=dry_run", summary)
            self.assertIn(
                "M5_ACCEPTANCE_ENDPOINT=http://soridormi.example/mcp",
                summary,
            )
            self.assertIn("M5_ACCEPTANCE_PROFILE=rtx4090", summary)
            self.assertIn("M5_ACCEPTANCE_GPU=Test\\ GPU", summary)
            self.assertIn("M5_ACCEPTANCE_RECOVERY_STATE=not_exercised", summary)
            self.assertTrue((evidence / "gpu-smoke.log").is_file())
            self.assertTrue((evidence / "runtime-preflight.json").is_file())
            self.assertTrue(
                (evidence / "runtime-preflight.stderr.log").is_file()
            )
            self.assertTrue((evidence / "runtime-cancellation.log").is_file())
            self.assertIn("--runtime-preflight", result.stdout)
            self.assertIn("--exercise-runtime-cancellation", result.stdout)
            self.assertLess(
                result.stdout.index("--runtime-preflight"),
                result.stdout.index("gpu_smoke_test.sh"),
            )

    def test_missing_endpoint_records_failed_initialization(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            evidence = Path(temp_dir) / "evidence"
            env = {
                **os.environ,
                "SUPERVISED_ACCEPTANCE": "1",
                "M5_DRY_RUN": "1",
                "M5_EVIDENCE_DIR": str(evidence),
                "SORIDORMI_MCP_URL": "",
            }
            result = subprocess.run(
                [str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            summary = (evidence / "summary.env").read_text()
            self.assertIn("M5_ACCEPTANCE_STATUS=failed", summary)
            self.assertIn("M5_ACCEPTANCE_FAILED_PHASE=initialization", summary)
            self.assertIn("M5_ACCEPTANCE_RECOVERY_STATE=not_exercised", summary)


if __name__ == "__main__":
    unittest.main()
