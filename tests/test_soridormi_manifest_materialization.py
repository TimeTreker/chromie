from __future__ import annotations

import json
import unittest
from pathlib import Path

from agent.app.materialize_soridormi_manifest import (
    materialize_soridormi_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


class SoridormiManifestMaterializationTests(unittest.TestCase):
    def test_materialization_preserves_tools_and_overlays_transport(self) -> None:
        upstream = {
            "schema_version": "0.1",
            "source": "soridormi",
            "agents": [
                {
                    "agent_id": "soridormi.robot",
                    "transport": {
                        "kind": "local_cli",
                        "command": "python",
                    },
                    "tools": [
                        {
                            "name": "soridormi.robot.get_status",
                            "agent_id": "soridormi.robot",
                        }
                    ],
                }
            ],
            "dag_contract": {"source": "soridormi"},
        }

        bundle = materialize_soridormi_manifest(
            upstream,
            upstream_commit="abc123",
        )

        agent = bundle.agents[0]
        self.assertEqual(agent.transport.kind, "mcp_streamable_http")
        self.assertEqual(agent.transport.url, "${SORIDORMI_MCP_URL}")
        self.assertEqual(
            [tool.name for tool in agent.tools],
            ["soridormi.robot.get_status"],
        )
        self.assertEqual(bundle.dag_contract, {"source": "soridormi"})
        self.assertEqual(bundle.metadata["upstream_commit"], "abc123")

    def test_checked_in_manifest_records_upstream_and_all_exported_tools(self) -> None:
        payload = json.loads(
            (ROOT / "capabilities" / "soridormi.json").read_text(encoding="utf-8")
        )
        tool_names = {
            tool["name"]
            for agent in payload["agents"]
            for tool in agent["tools"]
        }

        self.assertEqual(
            payload["metadata"]["upstream_repository"],
            "https://github.com/TimeTreker/soridormi.git",
        )
        self.assertEqual(
            payload["metadata"]["upstream_commit"],
            "027b626e065a274d4d600cecbc0ab1e572a7176a",
        )
        self.assertEqual(
            tool_names,
            {
                "soridormi.robot.get_status",
                "soridormi.robot.get_mode",
                "soridormi.robot.get_battery",
                "soridormi.motion.create_plan",
                "soridormi.motion.execute_plan",
                "soridormi.motion.stop",
                "soridormi.motion.cancel",
                "soridormi.safety.monitor_motion",
                "soridormi.safety.emergency_stop",
            },
        )


if __name__ == "__main__":
    unittest.main()
