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
    assert [item.value for item in observation.projection.interpretations] == [
        "bottle of milk", "50 meters in front of Chromie (simulated)",
        "user", "1.5 meters to Chromie's right (simulated)",
    ]
    assert observation.projection.interpretations[3].source_refs == ["soridormi-scene-7"]


@pytest.mark.parametrize("marked", [[], ["user"], ["user", "grandma"]])
def test_the_trusted_person_target_is_the_speaker_soridormi_marks(marked: list[str]) -> None:
    """Live 2026-10-28: since the legacy runtime's removal nothing produced trusted target
    evidence, so 293 of 297 Social Cognition calls read it as unavailable and a look or
    gesture could not aim at the person. Who is speaking is Soridormi's perception (owner
    decision 2026-10-28): its mark becomes the one target, an unmarked person never does,
    and two marked people are no single target."""
    from shared.chromie_contracts.situation import trusted_target_evidence

    people = [{"object_ref": f"soridormi_mock_{name}", "description": name, "relative_direction": "to Chromie's right",
               "distance_m": 1.5, **({"current_speaker": True} if name in marked else {})}
              for name in ("user", "grandma")]
    observation = asyncio.run(observe_soridormi_sim_scene(SceneInvoker(scene(objects=people)), context={}))
    assert observation is not None
    evidence = trusted_target_evidence({"situation": observation.projection.prompt_projection()})
    if len(marked) == 1:
        assert evidence == {"available": True, "source": "live_perception", "target": {
            "target_ref": "requester", "evidence_refs": ["soridormi-scene-7:object-0:speaker"]}}
    else:
        assert evidence == {"available": False}
    with pytest.raises(ValueError, match="scene marker contract"):
        asyncio.run(observe_soridormi_sim_scene(SceneInvoker(scene(objects=[{**people[0], "current_speaker": "yes"}])),
                                                context={}))


def test_object_value_names_only_what_it_is() -> None:
    """Live 2026-10-21 (multi_thirsty_yes_en): the fused value "bottle of milk, 9.899 meters
    to Chromie's left (simulated)" was copied whole into resource.description, and Soridormi
    reported the resource not observed. Its position is a separate aspect of the same subject."""
    observation = asyncio.run(observe_soridormi_sim_scene(SceneInvoker(scene()), context={}))
    assert observation is not None
    what, where = observation.projection.interpretations
    assert (what.relation, what.value) == ("scene.simulated_object", "bottle of milk")
    assert (where.relation, where.value) == (
        "scene.simulated_position", "50 meters in front of Chromie (simulated)")
    assert where.subject_ref == what.subject_ref == "sim-object:soridormi_mock_milk_bottle"
    assert where.interpretation_id == what.interpretation_id + ":position"


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
    assert [item.value for item in observation.projection.interpretations] == [
        "bottle of water", "3 meters to Chromie's left (simulated)",
    ]
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


def test_each_scene_revision_replaces_the_one_before() -> None:
    """Live 2026-10-21: every ambient refresh inherited the earlier scene revisions, so
    the interpretation bound kept only stale objects and, once 16 sources had piled up,
    the new revision was dropped ("source refs must be present in projection") and
    Chromie's perception stopped updating."""
    invoker = SceneInvoker(scene())
    host = AmbientHost(invoker)
    directions = ["in front of Chromie", "to Chromie's left", "behind Chromie", "to Chromie's right"]
    for revision in range(1, 21):
        objects = [{"object_ref": f"soridormi_mock_{name}", "description": name.replace("_", " "),
                    "relative_direction": directions[(revision + index) % 4], "distance_m": 1.0 + index}
                   for index, name in enumerate(("milk_bottle", "water_bottle", "user_torso"))]
        invoker.output = {**scene(objects=objects), "observation_id": f"soridormi-scene-{revision}",
                          "observation_sequence": revision, "scene_revision": revision,
                          "scene_signature": f"{revision:064x}"}
        assert asyncio.run(refresh_soridormi_ambient_scene_once(host)) == "updated"
        projection = host._ambient_situation_projection
        assert [source.reference_id for source in projection.source_refs] == [f"soridormi-scene-{revision}"]
        assert [item.value for item in projection.interpretations
                if item.relation == "scene.simulated_position"] == [
            f"{1.0 + index:g} meters {directions[(revision + index) % 4]} (simulated)" for index in range(3)]


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
                      "interpretation_count": 2}
    assert host._ambient_situation_projection.interpretations[0].value == "bottle of milk"
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
