from __future__ import annotations

import unittest

from scripts.behavior_scenarios import load_scenarios, run_scenarios_sync


class AgentInteractionAdapterScenarioTests(unittest.TestCase):
    def test_adapter_behavior_scenarios_from_json(self) -> None:
        scenarios = load_scenarios(suites={"adapter"})

        report = run_scenarios_sync(scenarios)

        self.assertTrue(report["ok"], report["cases"])
        self.assertEqual(report["case_count"], 4)


if __name__ == "__main__":
    unittest.main()
