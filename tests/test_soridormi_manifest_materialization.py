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
        tools = {
            tool["name"]: tool
            for agent in payload["agents"]
            for tool in agent["tools"]
        }

        self.assertEqual(
            payload["metadata"]["upstream_repository"],
            "https://github.com/TimeTreker/soridormi.git",
        )
        self.assertRegex(str(payload["metadata"]["upstream_commit"]), r"^[0-9a-f]{40}$")
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
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.skill.execute_plan",
                "soridormi.task.get_capabilities",
                "soridormi.task.preview",
                "soridormi.task.submit",
                "soridormi.task.status",
                "soridormi.task.events",
                "soridormi.task.cancel",
                "soridormi.safety.monitor_motion",
                "soridormi.safety.emergency_stop",
                "soridormi.testing.configure_fault",
                "soridormi.testing.clear_faults",
            },
        )
        task_submit = tools["soridormi.task.submit"]
        task_status = tools["soridormi.task.status"]
        task_events = tools["soridormi.task.events"]
        task_cancel = tools["soridormi.task.cancel"]
        self.assertIn("client_task_ref", task_submit["input_schema"]["properties"])
        self.assertIn("client_task_ref", task_status["input_schema"]["properties"])
        self.assertIn("client_task_ref", task_events["input_schema"]["properties"])
        self.assertIn("client_task_ref", task_cancel["input_schema"]["properties"])
        self.assertNotIn("task_id", task_events["input_schema"].get("required", []))
        self.assertEqual(
            task_submit["output_schema"]["properties"]["idempotent_replay"]["type"],
            "boolean",
        )
        self.assertIn("deadline_at", task_submit["output_schema"]["properties"])
        self.assertIn("expired", task_submit["output_schema"]["properties"])
        self.assertIn("timeout_elapsed_s", task_submit["output_schema"]["properties"])
        self.assertEqual(
            task_events["output_schema"]["properties"]["schema_version"]["type"],
            "string",
        )
        self.assertIn("client_task_ref", task_events["output_schema"]["properties"])
        self.assertIn("poll_recommendation", task_events["output_schema"]["properties"])
        self.assertIn("deadline_at", task_events["output_schema"]["properties"])
        self.assertIn("expired", task_events["output_schema"]["properties"])


if __name__ == "__main__":
    unittest.main()
