from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent.app.tool_invocation import ToolCallOutcome
from orchestrator.runtime.soridormi_scene_perception import (
    observe_soridormi_sim_scene,
    refresh_soridormi_ambient_scene_once,
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
        "scene_revision": 3,
        "scene_signature": "a" * 64,
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


class AmbientHost:
    def __init__(self, invoker: SceneInvoker) -> None:
        self.interaction_runtime = type("Runtime", (), {"soridormi_invoker": invoker})()
        self.logs: list[tuple[Any, ...]] = []

    def build_context(self, session_id):
        current = getattr(self, "_ambient_situation_projection", None)
        return {"situation": current.prompt_projection() if current is not None else None}

    def session_log(self, *args):
        self.logs.append(args)


def test_ambient_scene_refresh_updates_only_on_semantic_revision() -> None:
    invoker = SceneInvoker(scene())
    host = AmbientHost(invoker)
    assert asyncio.run(refresh_soridormi_ambient_scene_once(host)) == "updated"
    projection = host._ambient_situation_projection
    assert projection.interpretations[0].subject_ref == (
        "sim-object:soridormi_mock_milk_bottle"
    )
    assert host._ambient_scene_revision == 3

    invoker.output = {
        **scene(),
        "observation_id": "soridormi-scene-8",
        "observation_sequence": 8,
    }
    assert asyncio.run(refresh_soridormi_ambient_scene_once(host)) == "unchanged"
    assert host._ambient_situation_projection is projection

    invoker.output = {
        **scene(objects=[]),
        "observation_id": "soridormi-scene-9",
        "observation_sequence": 9,
        "scene_revision": 4,
        "scene_signature": "b" * 64,
    }
    assert asyncio.run(refresh_soridormi_ambient_scene_once(host)) == "cleared"
    assert host._ambient_situation_projection is None


def test_planning_situation_carries_goal_free_perception_forward() -> None:
    observation = asyncio.run(observe_soridormi_sim_scene(SceneInvoker(scene()), context={}))
    assert observation is not None
    planning = build_situation_projection(
        context={"situation": observation.projection.prompt_projection()},
        turn_id="turn-water",
        focus_goal_ids=["goal-water"],
        revision=4,
    )
    assert planning.focus_goal_ids == ["goal-water"]
    assert planning.interpretations[0].subject_ref == (
        "sim-object:soridormi_mock_milk_bottle"
    )
    assert planning.interpretations[0].relevance_goal_ids == []
    assert planning.source_refs[0].kind == "perception"
