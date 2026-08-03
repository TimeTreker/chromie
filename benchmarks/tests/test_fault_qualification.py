from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from benchmarks.faults.runner import run_fault_manifest, run_repeated_command


class FaultQualificationTests(unittest.TestCase):
    def test_default_fault_manifest_exercises_real_ollama_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "faults.json"
            report = run_fault_manifest(
                Path("benchmarks/manifests/fault_injection_v1.json"),
                output=output,
                repeat=1,
            )
            self.assertEqual(report["summary"]["consistent_fail"], 0)
            self.assertEqual(report["summary"]["intermittent"], 0)
            self.assertTrue(output.is_file())

    def test_repeat_runner_classifies_consistent_and_intermittent_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            passed = run_repeated_command(
                [sys.executable, "-c", "print('ok')"],
                count=3,
                output_dir=root / "pass",
                timeout_s=5,
            )
            self.assertEqual(passed["status"], "consistent_pass")

            counter = root / "counter"
            code = (
                "from pathlib import Path; import sys; "
                f"p=Path({str(counter)!r}); n=int(p.read_text()) if p.exists() else 0; "
                "p.write_text(str(n+1)); sys.exit(n % 2)"
            )
            intermittent = run_repeated_command(
                [sys.executable, "-c", code],
                count=3,
                output_dir=root / "intermittent",
                timeout_s=5,
            )
            self.assertEqual(intermittent["status"], "intermittent")
            payload = json.loads((root / "intermittent" / "repeat-report.json").read_text())
            self.assertEqual(len(payload["attempts"]), 3)


if __name__ == "__main__":
    unittest.main()
