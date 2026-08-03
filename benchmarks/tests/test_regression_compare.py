from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from benchmarks.regression.compare import compare_qualification_runs


class QualificationComparisonTests(unittest.TestCase):
    def _run(
        self,
        root: Path,
        name: str,
        *,
        check_status: str = "PASS",
        mechanical: bool = True,
        semantic: str = "pass",
        latency: float = 100.0,
    ) -> Path:
        run = root / name
        (run / "e2e" / "closed").mkdir(parents=True)
        report = {
            "schema_version": 2,
            "revision": name,
            "overall_status": "passed" if check_status == "PASS" else "failed",
            "capture_mode": "auto",
            "languages": ["en", "zh"],
            "runner_version": "1.3.0",
            "checks": [
                {"phase": "source", "check": "unit", "status": check_status}
            ],
        }
        (run / "collection-report.json").write_text(json.dumps(report), encoding="utf-8")
        summary = {
            "workflow": [
                {
                    "id": "memory-recall",
                    "status": "review" if mechanical else "fail",
                    "mechanical_passed": mechanical,
                    "semantic_review_required": True,
                    "artifacts": ["cases/memory/result.json"],
                    "latency_ms": latency,
                }
            ]
        }
        (run / "e2e" / "closed" / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        (run / "reviews.json").write_text(
            json.dumps({"reviews": [{"scenario_id": "memory-recall", "verdict": semantic}]}),
            encoding="utf-8",
        )
        records = []
        for path in sorted(run.rglob("*")):
            if path.is_file() and path.name != "artifact-index.json":
                records.append(
                    {
                        "path": str(path.relative_to(run)),
                        "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        (run / "artifact-index.json").write_text(
            json.dumps({"schema_version": 1, "artifacts": records}), encoding="utf-8"
        )
        return run

    def test_detects_deterministic_semantic_and_latency_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = self._run(root, "baseline")
            candidate = self._run(
                root,
                "candidate",
                check_status="FAIL",
                mechanical=False,
                semantic="partial",
                latency=260.0,
            )
            report = compare_qualification_runs(
                baseline, candidate, max_relative_regression=0.20, absolute_latency_ms=50
            )
            self.assertEqual(report["verdict"], "regression")
            self.assertEqual(len(report["deterministic"]["regressions"]), 1)
            self.assertTrue(report["scenarios"]["regressions"])
            self.assertTrue(report["performance"]["regressions"])

    def test_accepts_archive_inputs_and_reports_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_dir = self._run(root, "baseline", check_status="FAIL", mechanical=False, semantic="fail")
            candidate_dir = self._run(root, "candidate")
            archives = []
            for directory in (baseline_dir, candidate_dir):
                archive_path = root / f"{directory.name}.tar.gz"
                with tarfile.open(archive_path, "w:gz") as archive:
                    archive.add(directory, arcname=directory.name)
                archives.append(archive_path)
            report = compare_qualification_runs(archives[0], archives[1])
            self.assertEqual(report["verdict"], "no_regression_detected")
            self.assertTrue(report["deterministic"]["improvements"])
            self.assertTrue(report["scenarios"]["improvements"])


if __name__ == "__main__":
    unittest.main()
