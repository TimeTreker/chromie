from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.chromie_runtime.latency_evidence import (
    build_latency_report,
    evaluate_latency_gate,
)


def _write_trace(
    root: Path,
    name: str,
    *,
    total_ms: float,
    observable_ms: float,
    ollama_ms: float,
    gpu_percent: float,
) -> None:
    package = root / "ready" / name
    package.mkdir(parents=True)
    trace = {
        "schema_version": 1,
        "trace_id": f"trace_{name}",
        "state": "complete",
        "coverage": "partial",
        "correlations": {"session_id": name},
        "items": [
            {
                "trace_id": f"trace_{name}",
                "item_id": f"item_model_{name}",
                "parent_item_id": None,
                "name": "generate",
                "operation": "generate",
                "kind": "model_call",
                "module": {
                    "name": "agent.ollama",
                    "component_type": "model_client",
                    "implementation": "OllamaClient",
                    "schema_version": 1,
                },
                "started_at": "2026-07-21T00:00:00+00:00",
                "finished_at": "2026-07-21T00:00:01+00:00",
                "duration_ms": ollama_ms,
                "status": "ok",
                "attributes": {},
                "links": [],
            },
            {
                "trace_id": f"trace_{name}",
                "item_id": f"item_gpu_{name}",
                "parent_item_id": None,
                "name": "accelerator_resource_sample",
                "operation": None,
                "kind": "resource_sample",
                "module": {
                    "name": "chromie.runtime.accelerator",
                    "component_type": "resource_sampler",
                    "implementation": "AcceleratorTelemetrySampler",
                    "schema_version": 1,
                },
                "started_at": "2026-07-21T00:00:00+00:00",
                "finished_at": "2026-07-21T00:00:00+00:00",
                "duration_ms": 0.0,
                "status": "ok",
                "attributes": {
                    "accelerator_gpu_utilization_max_percent": gpu_percent,
                },
                "links": [],
            },
        ],
    }
    summary = {
        "schema_version": 1,
        "status": "complete",
        "total_duration_ms": total_ms,
        "first_user_observable_latency_ms": observable_ms,
        "item_count": 2,
        "module_aggregates": [
            {
                "module": {
                    "name": "agent.ollama",
                    "component_type": "model_client",
                    "implementation": "OllamaClient",
                    "schema_version": 1,
                },
                "item_count": 1,
                "inclusive_duration_ms": ollama_ms,
                "exclusive_duration_ms": ollama_ms,
                "max_duration_ms": ollama_ms,
                "error_count": 0,
            }
        ],
    }
    event = {
        "event_id": f"evt_{name}",
        "event_type": "chromie.interaction_trace",
        "event_subtype": "voice_session",
        "occurred_at": "2026-07-21T00:00:00+00:00",
    }
    for filename, payload in (
        ("trace.json", trace),
        ("trace-summary.json", summary),
        ("event.json", event),
    ):
        (package / filename).write_text(json.dumps(payload), encoding="utf-8")


class RuntimeTraceLatencyTests(unittest.TestCase):
    def test_report_builds_latency_module_and_resource_distributions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "events"
            _write_trace(
                root,
                "one",
                total_ms=1000,
                observable_ms=500,
                ollama_ms=700,
                gpu_percent=40,
            )
            _write_trace(
                root,
                "two",
                total_ms=2000,
                observable_ms=900,
                ollama_ms=1200,
                gpu_percent=80,
            )

            report = build_latency_report(
                sources=[root],
                evidence_class="simulator",
                environment="rtx5090-mujoco",
                label="baseline",
                chromie_revision="abc",
                chromie_dirty=False,
            )

        self.assertEqual(report["source"]["included_trace_count"], 2)
        self.assertEqual(report["metrics"]["total_duration_ms"]["p50"], 1500.0)
        self.assertEqual(
            report["module_metrics"]["agent.ollama"]["inclusive_duration_ms"]["max"],
            1200.0,
        )
        self.assertEqual(
            report["resource_metrics"][
                "chromie.runtime.accelerator.accelerator_gpu_utilization_max_percent"
            ]["p50"],
            60.0,
        )

    def test_gate_passes_and_fails_from_retained_reports(self) -> None:
        baseline = {
            "report_type": "chromie.runtime_trace_latency_report",
            "label": "baseline",
            "evidence_class": "target",
            "environment": "robot-a",
            "provenance": {"chromie_revision": "base", "chromie_dirty": False},
            "source": {"included_trace_count": 20, "digest_sha256": "a"},
            "metrics": {"total_duration_ms": {"count": 20, "p95": 1000.0}},
            "module_metrics": {},
            "resource_metrics": {},
        }
        candidate = {
            **baseline,
            "label": "candidate",
            "provenance": {"chromie_revision": "next", "chromie_dirty": False},
            "source": {"included_trace_count": 20, "digest_sha256": "b"},
            "metrics": {"total_duration_ms": {"count": 20, "p95": 1080.0}},
        }
        policy = {
            "schema_version": 1,
            "enabled": True,
            "minimum_baseline_samples": 20,
            "minimum_candidate_samples": 20,
            "required_evidence_class": "target",
            "require_same_environment": True,
            "require_clean_revision": True,
            "gates": [
                {
                    "scope": "metrics",
                    "metric": "total_duration_ms",
                    "statistic": "p95",
                    "minimum_metric_samples": 20,
                    "max_regression_percent": 10.0,
                    "max_regression_ms": 150.0,
                }
            ],
        }

        passed = evaluate_latency_gate(
            baseline=baseline,
            candidate=candidate,
            policy=policy,
        )
        candidate["metrics"]["total_duration_ms"]["p95"] = 1300.0
        failed = evaluate_latency_gate(
            baseline=baseline,
            candidate=candidate,
            policy=policy,
        )

        self.assertEqual(passed["status"], "pass")
        self.assertEqual(failed["status"], "fail")
        self.assertIn("max_regression_percent", failed["gates"][0]["violations"])
        self.assertIn("max_regression_ms", failed["gates"][0]["violations"])

    def test_gate_refuses_unqualified_or_disabled_evidence(self) -> None:
        report = {
            "report_type": "chromie.runtime_trace_latency_report",
            "evidence_class": "automated",
            "environment": "unit",
            "provenance": {"chromie_dirty": True},
            "source": {"included_trace_count": 1},
            "metrics": {},
            "module_metrics": {},
            "resource_metrics": {},
        }
        result = evaluate_latency_gate(
            baseline=report,
            candidate=report,
            policy={"schema_version": 1, "enabled": False},
        )
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
