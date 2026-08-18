from __future__ import annotations

import unittest

from orchestrator.runtime.agent_tool_provider import local_agent_tool_definitions


class AgentToolCapabilityDefinitionTests(unittest.TestCase):
    def test_weather_preserves_explicit_parallel_declaration_for_pre_ga_execution(
        self,
    ) -> None:
        definitions = {
            item.capability_id: item for item in local_agent_tool_definitions()
        }

        weather = definitions["chromie.weather.lookup"]

        self.assertTrue(weather.can_run_parallel)
        self.assertTrue(weather.metadata["side_effect_free"])
        self.assertTrue(weather.metadata["parallel_metadata_declared"])


if __name__ == "__main__":
    unittest.main()
