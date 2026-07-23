from __future__ import annotations

import unittest

from scripts.behavior_scenarios import load_scenarios, run_scenarios


def _format_failures(report: dict[str, object]) -> str:
    chunks: list[str] = []
    for case in report.get("cases", []):
        if isinstance(case, dict) and not case.get("ok"):
            chunks.append(f"{case.get('key')}: {case.get('errors')}")
    return "\n".join(chunks)


class BehaviorTruthSuiteTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_behavior_scenario_suites(self) -> None:
        expected_counts = {
            "adapter": 4,
            "router": 24,
            "router_dialogue": 2,
            "interaction": 21,
            "dialogue": 319,
        }

        for suite, expected_count in expected_counts.items():
            with self.subTest(suite=suite):
                scenarios = load_scenarios(suites={suite})
                report = await run_scenarios(scenarios)

                self.assertTrue(report["ok"], _format_failures(report))
                self.assertEqual(report["case_count"], expected_count)


if __name__ == "__main__":
    unittest.main()
