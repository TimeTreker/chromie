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
    async def test_adapter_behavior_scenario_files(self) -> None:
        scenarios = load_scenarios(suites={"adapter"})

        report = await run_scenarios(scenarios)

        self.assertTrue(report["ok"], _format_failures(report))
        self.assertEqual(report["case_count"], 4)

    async def test_router_behavior_scenario_files(self) -> None:
        scenarios = load_scenarios(suites={"router"})

        report = await run_scenarios(scenarios)

        self.assertTrue(report["ok"], _format_failures(report))
        self.assertEqual(report["case_count"], 17)

    async def test_interaction_behavior_scenario_files(self) -> None:
        scenarios = load_scenarios(suites={"interaction"})

        report = await run_scenarios(scenarios)

        self.assertTrue(report["ok"], _format_failures(report))
        self.assertEqual(report["case_count"], 16)

    async def test_dialogue_behavior_scenario_files(self) -> None:
        scenarios = load_scenarios(suites={"dialogue"})

        report = await run_scenarios(scenarios)

        self.assertTrue(report["ok"], _format_failures(report))
        self.assertEqual(report["case_count"], 316)


if __name__ == "__main__":
    unittest.main()
