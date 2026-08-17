from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
)
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.validator import GraphValidator


ROOT = Path(__file__).resolve().parents[1]
DECLARED_SORIDORMI_TASK_TYPES = {
    "move_forward",
    "move_velocity",
    "turn_to_heading",
    "approach_target",
    "navigate_to_location",
    "look_at_target",
    "perform_gesture",
    "skill_sequence",
    "speak_while_moving",
    "stop_now",
    "recover_safe_idle",
    "deliver_object",
}


class LiveSkillInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None):
        del arguments, context
        if tool_name != "soridormi.skill.list":
            raise AssertionError(tool_name)

        class Outcome:
            status = "success"
            error = None
            output = {
                "mode": "sim",
                "skills": [
                    {
                        "skill_id": "walk_velocity",
                        "description": "Walk forward or backward for an explicitly bounded duration.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "vx_mps": {"type": "number"},
                                "duration_s": {"type": "number"},
                            },
                            "required": ["vx_mps", "duration_s"],
                        },
                        "available": True,
                        "effects": ["physical_motion"],
                        "safety_class": "physical_motion",
                        "requires_confirmation": True,
                    }
                ],
            }

        return Outcome()


def _registry():
    external = CapabilityBundle(
        source="weather-test",
        agents=[
            AgentManifest(
                agent_id="weather",
                tools=[
                    ToolCapability(
                        name="weather.current",
                        agent_id="weather",
                        description="Read current weather.",
                        input_schema={
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                            "required": ["location"],
                        },
                        effects=["read_only"],
                        safety_class="safe_read",
                    )
                ],
            )
        ],
    )
    return build_chromie_registry([external])


def _soridormi_task_registry() -> CapabilityRegistry:
    return build_chromie_registry(
        [
            CapabilityBundle(
                source="soridormi-task-planning-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List concrete bounded Soridormi named capabilities.",
                                safety_class="safe_read",
                                effects=["read_only"],
                            )
                        ],
                    ),
                    AgentManifest(
                        agent_id="soridormi.task",
                        tags=["soridormi", "task", "embodied-goal"],
                        tools=[
                            ToolCapability(
                                name="soridormi.task.get_capabilities",
                                agent_id="soridormi.task",
                                description=(
                                    "Inspect Soridormi embodied task readiness, blocked "
                                    "subsystems, navigation, approach, inspection, and delivery support."
                                ),
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                            ToolCapability(
                                name="soridormi.task.preview",
                                agent_id="soridormi.task",
                                description=(
                                    "Preview a structured embodied task goal such as navigation, "
                                    "approach, inspection, recovery, or deliver object without motion."
                                ),
                                safety_class="planning_only",
                                effects=["planning_only", "embodied_task_request", "no_motion_contract"],
                            ),
                            ToolCapability(
                                name="soridormi.task.submit",
                                agent_id="soridormi.task",
                                description=(
                                    "Submit a structured embodied goal for navigation, approach, "
                                    "inspection, recovery, or object delivery such as bringing water."
                                ),
                                safety_class="planning_only",
                                effects=["planning_only", "embodied_task_request", "no_motion_contract"],
                            ),
                            ToolCapability(
                                name="soridormi.task.events",
                                agent_id="soridormi.task",
                                description="Monitor terminal events for a submitted Soridormi task.",
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                        ],
                    ),
                ],
            )
        ]
    )


def _checked_in_soridormi_registry() -> CapabilityRegistry:
    return build_chromie_registry(
        [CapabilityBundle.load_file(ROOT / "capabilities" / "soridormi.json")]
    )


def _declared_soridormi_task_types() -> list[str]:
    payload = json.loads((ROOT / "capabilities" / "soridormi.json").read_text(encoding="utf-8"))
    for agent in payload["agents"]:
        for tool in agent["tools"]:
            if tool["name"] == "soridormi.task.submit":
                return list(tool["input_schema"]["properties"]["task_type"]["enum"])
    raise AssertionError("soridormi.task.submit not found in checked-in manifest")


def _task_args(task_type: str) -> dict[str, Any]:
    parameters_by_type = {
        "move_forward": {"distance_m": 0.3, "speed": "slow"},
        "move_velocity": {"vx_mps": 0.1, "duration_s": 1.0},
        "turn_to_heading": {"heading_rad": 0.5},
        "approach_target": {"target": "speaker", "speed": "slow"},
        "navigate_to_location": {"target": "kitchen"},
        "look_at_target": {"target": "speaker"},
        "perform_gesture": {"gesture": "nod_yes"},
        "skill_sequence": {"skills": [{"skill_id": "nod_yes", "args": {}}]},
        "speak_while_moving": {"text": "I am moving carefully.", "vx_mps": 0.05},
        "stop_now": {"reason": "user_requested_stop"},
        "recover_safe_idle": {"reason": "operator_request"},
        "deliver_object": {"object": "water", "source": "kitchen", "target": "user"},
    }
    return {
        "task_type": task_type,
        "summary": f"Route declared Soridormi task type {task_type}.",
        "parameters": parameters_by_type[task_type],
    }



class TaskGraphPlanningTests(unittest.IsolatedAsyncioTestCase):
    def test_checked_in_soridormi_manifest_declares_expected_task_types(self) -> None:
        self.assertEqual(
            set(_declared_soridormi_task_types()),
            DECLARED_SORIDORMI_TASK_TYPES,
        )

    def test_undeclared_soridormi_task_type_is_rejected_by_graph_validator(self) -> None:
        graph = TaskGraph.model_validate(
            {
                "graph_id": "raw-body",
                "summary": "Invalid raw body request.",
                "created_by": "llm",
                "nodes": [
                    {
                        "id": "submit",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "args": {
                            "task_type": "raw_joint_action",
                            "parameters": {"action_14d": [0.0] * 14},
                        },
                    }
                ],
            }
        )

        report = GraphValidator(_checked_in_soridormi_registry()).validate(graph)

        self.assertFalse(report.valid)
        self.assertTrue(
            any("args.task_type must be one of" in error for error in report.errors),
            report.errors,
        )



if __name__ == "__main__":
    unittest.main()
