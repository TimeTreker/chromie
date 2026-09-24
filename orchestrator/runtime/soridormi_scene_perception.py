"""Admit Soridormi's simulation scene observation with its original provenance.

This is an explicit read boundary. A user utterance cannot seed the observation,
and a mock scene marker never becomes physical camera or hardware evidence.
"""

from __future__ import annotations

import math
from typing import Any

from agent.app.tool_invocation import AsyncToolInvoker
from shared.chromie_contracts.situation import (
    SituationInterpretation,
    SituationRevisionObservation,
    SituationSourceRef,
)

from .situation import build_trusted_goal_free_situation_observation


async def observe_soridormi_sim_scene(
    invoker: AsyncToolInvoker,
    *,
    context: dict[str, Any],
) -> SituationRevisionObservation | None:
    """Read one sim observation and project only a verified bottle marker."""

    outcome = await invoker.invoke("soridormi.robot.observe_scene", {})
    if outcome.status != "success":
        raise RuntimeError(outcome.error or "Soridormi scene observation failed")
    payload = outcome.output
    if (
        payload.get("mode") != "sim"
        or payload.get("source_kind") != "mujoco_scene_marker"
        or payload.get("mocked_simulation") is not True
    ):
        raise ValueError("scene observation lacks simulation source provenance")
    observation_id = payload.get("observation_id")
    sequence = payload.get("observation_sequence")
    objects = payload.get("objects")
    if (
        not isinstance(observation_id, str)
        or not observation_id.strip()
        or type(sequence) is not int
        or sequence < 1
        or not isinstance(objects, list)
    ):
        raise ValueError("scene observation has invalid identity or objects")
    if not objects:
        return None
    if len(objects) != 1 or not isinstance(objects[0], dict):
        raise ValueError("mock scene observation has unexpected object set")
    item = objects[0]
    distance = item.get("distance_m")
    if (
        item.get("object_ref") != "soridormi_mock_milk_bottle"
        or item.get("description") != "bottle of milk"
        or item.get("relative_direction") != "in front of Chromie"
        or isinstance(distance, bool)
        or not isinstance(distance, (int, float))
        or not math.isfinite(distance)
        or not 0 <= distance <= 60
    ):
        raise ValueError("mock scene object does not satisfy the bottle contract")
    source = SituationSourceRef(
        kind="perception",
        reference_id=observation_id,
        owner="soridormi.sim.scene",
    )
    interpretation = SituationInterpretation(
        interpretation_id=f"{observation_id}:milk-bottle"[:200],
        subject_ref="sim-object:soridormi_mock_milk_bottle",
        relation="scene.simulated_object",
        value=f"bottle of milk, {distance:g} meters in front of Chromie (simulated)",
        epistemic_status="established",
        source_refs=[observation_id],
    )
    return build_trusted_goal_free_situation_observation(
        context=context,
        turn_id=observation_id,
        source_id="soridormi.sim.scene",
        source_revision=sequence,
        source=source,
        interpretations=[interpretation],
    )
