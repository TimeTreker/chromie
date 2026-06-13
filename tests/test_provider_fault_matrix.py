from __future__ import annotations

import unittest

from scripts.provider_fault_matrix import (
    MATRIX_VERSION,
    MatrixThresholds,
    SCENARIOS,
    is_safe_idle,
    parse_scenario_ids,
    run_matrix,
    threshold_violations,
)


class ProviderFaultMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_matrix_matches_all_expected_terminal_states(self) -> None:
        payload = await run_matrix()

        self.assertEqual(payload["matrix_version"], MATRIX_VERSION)
        self.assertEqual(payload["scenario_count"], len(SCENARIOS))
        self.assertTrue(payload["passed"])
        self.assertTrue(all(item["passed"] for item in payload["results"]))
        self.assertEqual(payload["summary"]["passed_count"], len(SCENARIOS))
        self.assertEqual(payload["summary"]["failed_count"], 0)
        self.assertEqual(payload["summary"]["safe_idle_count"], len(SCENARIOS))
        self.assertEqual(payload["summary"]["status_counts"]["cancelled"], 1)
        self.assertIn("timeout", payload["summary"]["reason_counts"])
        self.assertGreater(payload["summary"]["max_elapsed_ms"], 0)

    async def test_selected_matrix_is_stable_and_ordered(self) -> None:
        payload = await run_matrix(
            ["monitor_refused", "execute_disconnect", "operator_cancel"]
        )

        self.assertEqual(
            [item["scenario_id"] for item in payload["results"]],
            ["monitor_refused", "execute_disconnect", "operator_cancel"],
        )
        self.assertEqual(
            [item["actual_status"] for item in payload["results"]],
            ["failed", "failed", "cancelled"],
        )

    def test_parser_rejects_unknown_scenarios(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fault scenario"):
            parse_scenario_ids("success,not-a-scenario")

    def test_threshold_violation_is_reported_deterministically(self) -> None:
        scenario = next(
            item for item in SCENARIOS if item.scenario_id == "operator_cancel"
        )
        violations = threshold_violations(
            scenario,
            elapsed_ms=20,
            terminal_latency_ms=11,
            thresholds=MatrixThresholds(
                max_scenario_ms=100,
                max_timeout_terminal_ms=100,
                max_cancel_terminal_ms=10,
            ),
        )

        self.assertEqual(
            violations,
            ("cancel terminal latency 11.000ms exceeds 10.000ms",),
        )

    def test_thresholds_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            MatrixThresholds(max_scenario_ms=0)

    def test_safe_idle_requires_no_active_task_and_clear_emergency_stop(self) -> None:
        self.assertTrue(
            is_safe_idle({"active_task": None, "emergency_stop": False})
        )
        self.assertFalse(
            is_safe_idle({"active_task": "plan-1", "emergency_stop": False})
        )
        self.assertFalse(
            is_safe_idle({"active_task": None, "emergency_stop": True})
        )


if __name__ == "__main__":
    unittest.main()
