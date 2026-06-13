from __future__ import annotations

import unittest

from scripts.provider_fault_matrix import (
    MATRIX_VERSION,
    SCENARIOS,
    parse_scenario_ids,
    run_matrix,
)


class ProviderFaultMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_matrix_matches_all_expected_terminal_states(self) -> None:
        payload = await run_matrix()

        self.assertEqual(payload["matrix_version"], MATRIX_VERSION)
        self.assertEqual(payload["scenario_count"], len(SCENARIOS))
        self.assertTrue(payload["passed"])
        self.assertTrue(all(item["passed"] for item in payload["results"]))

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


if __name__ == "__main__":
    unittest.main()
