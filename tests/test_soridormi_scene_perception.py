from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent.app.capabilities.loader import build_configured_registry
from agent.app.tool_invocation import McpStreamableHttpInvoker, ToolCallOutcome
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


def test_scene_observation_uses_checked_in_registry_and_transport(monkeypatch) -> None:
    monkeypatch.setenv("SORIDORMI_MCP_URL", "http://scene-provider:8000/mcp")
    calls = []

    async def transport(url, tool, args, timeout_s):
        calls.append((url, tool, args, timeout_s))
        return {"structuredContent": scene()}

    manifest = Path(__file__).resolve().parents[1] / "capabilities" / "soridormi.json"
    configured = build_configured_registry([str(manifest)])
    invoker = McpStreamableHttpInvoker(configured.registry, call=transport)
    observation = asyncio.run(observe_soridormi_sim_scene(invoker, context={}))

    assert observation is not None
    assert observation.source_refs == ["soridormi-scene-7"]
    assert calls == [(
        "http://scene-provider:8000/mcp", "soridormi.robot.observe_scene", {}, 2.0,
    )]
    tool = configured.registry.get_tool("soridormi.robot.observe_scene")
    assert tool.safety_class == "safe_read"
    assert tool.availability.modes == ["sim"]
    assert tool.execution.side_effect_free


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


class _TextHost:
    """The Host surface the text harness and ambient poll actually touch."""

    def __init__(self, invoker: SceneInvoker) -> None:
        from types import SimpleNamespace

        self.enable_soridormi_capabilities = True
        self.interaction_runtime = SimpleNamespace(soridormi_invoker=invoker)
        self.active_cognitive_runtime_tasks: dict[asyncio.Task, str] = {}
        self.started = 0

    def build_context(self, sid):
        return {}

    def _cognitive_runtime_task_done(self, task) -> None:
        self.active_cognitive_runtime_tasks.pop(task, None)

    def start_soridormi_ambient_perception(self):
        from orchestrator.orchestrator import VoiceAssistant

        self.started += 1
        return VoiceAssistant.start_soridormi_ambient_perception(self)


def test_text_check_primes_and_keeps_live_ambient_perception() -> None:
    # Live text runs on 2026-10-08 planned water with `situation: {}` because only
    # the voice main loop started the ambient poll.
    from scripts.interaction_text_mujoco_check import _prepare_ambient_perception

    async def exercise():
        host = _TextHost(SceneInvoker(scene()))
        record = await _prepare_ambient_perception(host)
        first = host._ambient_perception_task
        await _prepare_ambient_perception(host)  # a later turn on the same Host
        assert host._ambient_perception_task is first
        assert host.active_cognitive_runtime_tasks == {first: "soridormi-ambient-perception"}
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        return host, record

    host, record = asyncio.run(exercise())
    assert record == {"enabled": True, "primed": "updated", "scene_revision": 3,
                      "interpretation_count": 1}
    assert host._ambient_situation_projection.interpretations[0].value == (
        "bottle of milk, 50 meters in front of Chromie (simulated)"
    )
    assert host.started == 2


def test_text_check_records_unavailable_perception_without_blocking() -> None:
    from scripts.interaction_text_mujoco_check import _prepare_ambient_perception

    class Failing(SceneInvoker):
        async def invoke(self, tool_name, args, *, context=None):
            return ToolCallOutcome.failed("scene provider offline")

    async def exercise():
        host = _TextHost(Failing(scene()))
        record = await _prepare_ambient_perception(host)
        host._ambient_perception_task.cancel()
        await asyncio.gather(host._ambient_perception_task, return_exceptions=True)
        return record

    record = asyncio.run(exercise())
    assert record["enabled"] is True
    assert record["primed"].startswith("unavailable:RuntimeError")
    assert record["interpretation_count"] == 0
