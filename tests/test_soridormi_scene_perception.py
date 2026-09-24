from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent.app.tool_invocation import ToolCallOutcome
from orchestrator.runtime.soridormi_scene_perception import observe_soridormi_sim_scene


class SceneInvoker:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def invoke(self, tool_name: str, args: dict[str, Any], *, context=None):
        self.calls.append((tool_name, args))
        return ToolCallOutcome.success(self.output)


def scene(*, objects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "observation_id": "soridormi-scene-7",
        "observation_sequence": 7,
        "mode": "sim",
        "source_kind": "mujoco_scene_marker",
        "mocked_simulation": True,
        "robot_time_s": 2.5,
        "objects": objects if objects is not None else [{
            "object_ref": "soridormi_mock_milk_bottle",
            "description": "bottle of milk",
            "relative_direction": "in front of Chromie",
            "distance_m": 50.0,
        }],
    }


def test_simulator_observation_reaches_chromie_with_source_ref() -> None:
    invoker = SceneInvoker(scene())
    observation = asyncio.run(observe_soridormi_sim_scene(
        invoker, context={}
    ))
    assert invoker.calls == [("soridormi.robot.observe_scene", {})]
    assert observation is not None
    assert observation.goal_ids == []
    assert observation.source_refs == ["soridormi-scene-7"]
    assert observation.projection.interpretations[0].value == (
        "bottle of milk, 50 meters in front of Chromie (simulated)"
    )


def test_user_report_cannot_substitute_for_scene_observation() -> None:
    empty = asyncio.run(observe_soridormi_sim_scene(
        SceneInvoker(scene(objects=[])),
        context={"recent_dialogue": ["There is a bottle of milk 50 meters ahead"]},
    ))
    assert empty is None
    with pytest.raises(ValueError, match="simulation source provenance"):
        asyncio.run(observe_soridormi_sim_scene(
            SceneInvoker({**scene(), "source_kind": "user_report"}),
            context={},
        ))
    with pytest.raises(ValueError, match="bottle contract"):
        asyncio.run(observe_soridormi_sim_scene(
            SceneInvoker(scene(objects=[{**scene()["objects"][0], "distance_m": 500.0}])),
            context={},
        ))
