from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent.app.tool_invocation import ToolCallOutcome
from orchestrator.runtime.soridormi_scene_perception import (
    observe_soridormi_sim_scene,
    physical_resource_goals_need_scene_refresh,
    refresh_planner_soridormi_sim_scene,
)
from orchestrator.runtime.situation import build_situation_projection


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
    invoker = SceneInvoker(scene(objects=[
        scene()["objects"][0],
        {
            "object_ref": "soridormi_mock_user_torso",
            "description": "user",
            "relative_direction": "to Chromie's right",
            "distance_m": 1.5,
        },
    ]))
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
    assert observation.projection.interpretations[1].value == (
        "user, 1.5 meters to Chromie's right (simulated)"
    )
    assert observation.projection.interpretations[1].source_refs == ["soridormi-scene-7"]


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
    with pytest.raises(ValueError, match="scene marker contract"):
        asyncio.run(observe_soridormi_sim_scene(
            SceneInvoker(scene(objects=[{**scene()["objects"][0], "distance_m": 500.0}])),
            context={},
        ))


def test_scene_object_can_describe_another_simulated_resource() -> None:
    observation = asyncio.run(observe_soridormi_sim_scene(
        SceneInvoker(scene(objects=[{
            "object_ref": "soridormi_mock_water_bottle",
            "description": "bottle of water",
            "relative_direction": "to Chromie's left",
            "distance_m": 3.0,
        }])),
        context={"recent_dialogue": ["I am thirsty"]},
    ))
    assert observation is not None
    assert observation.projection.interpretations[0].value == (
        "bottle of water, 3 meters to Chromie's left (simulated)"
    )
    assert observation.projection.interpretations[0].source_refs == ["soridormi-scene-7"]

def test_physical_resource_planner_refresh_returns_trusted_scene_projection() -> None:
    goals = [{
        "goal_id": "goal-water",
        "resource_responsibility": {
            "resource": {"kind": "physical_object", "description": "a bottle of water"},
        },
    }]
    assert physical_resource_goals_need_scene_refresh(goals)
    invoker = SceneInvoker(scene(objects=[{
        "object_ref": "soridormi_mock_water_bottle",
        "description": "bottle of water",
        "relative_direction": "to Chromie's left",
        "distance_m": 3.0,
    }]))
    projection = asyncio.run(refresh_planner_soridormi_sim_scene(
        invoker, context={}, authoritative_goals=goals,
    ))
    assert projection is not None
    assert projection["source_refs"][0]["reference_id"] == "soridormi-scene-7"
    assert projection["interpretations"][0]["subject_ref"] == (
        "sim-object:soridormi_mock_water_bottle"
    )


def test_rebuilt_planner_situation_preserves_fresh_trusted_perception() -> None:
    observation = asyncio.run(observe_soridormi_sim_scene(
        SceneInvoker(scene()), context={}
    ))
    assert observation is not None
    rebuilt = build_situation_projection(
        context={"situation": observation.projection.prompt_projection()},
        turn_id="turn-water",
        focus_goal_ids=["goal-water"],
        revision=observation.projection.revision + 1,
    )
    assert rebuilt.focus_goal_ids == ["goal-water"]
    assert rebuilt.source_refs == observation.projection.source_refs
    assert rebuilt.interpretations == observation.projection.interpretations

