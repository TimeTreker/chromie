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
    """Read one sim observation and project its bounded scene markers."""

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
        or len(observation_id) > 120
        or type(sequence) is not int
        or sequence < 1
        or not isinstance(objects, list)
    ):
        raise ValueError("scene observation has invalid identity or objects")
    if not objects:
        return None
    if len(objects) > 32:
        raise ValueError("mock scene observation exceeds object limit")
    source = SituationSourceRef(
        kind="perception",
        reference_id=observation_id,
        owner="soridormi.sim.scene",
    )
    interpretations: list[SituationInterpretation] = []
    seen_refs: set[str] = set()
    directions = {
        "in front of Chromie",
        "behind Chromie",
        "to Chromie's left",
        "to Chromie's right",
    }
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            raise ValueError("mock scene object is invalid")
        object_ref = item.get("object_ref")
        description = item.get("description")
        direction = item.get("relative_direction")
        distance = item.get("distance_m")
        if (
            not isinstance(object_ref, str)
            or not object_ref.startswith("soridormi_mock_")
            or len(object_ref) > 120
            or object_ref in seen_refs
            or not isinstance(description, str)
            or not description.strip()
            or len(description) > 120
            or not isinstance(direction, str)
            or direction not in directions
            or isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not math.isfinite(distance)
            or not 0 <= distance <= 60
        ):
            raise ValueError("mock scene object does not satisfy the scene marker contract")
        seen_refs.add(object_ref)
        interpretations.append(SituationInterpretation(
            interpretation_id=f"{observation_id}:object-{index}",
            subject_ref=f"sim-object:{object_ref}",
            relation="scene.simulated_object",
            value=f"{description}, {distance:g} meters {direction} (simulated)",
            epistemic_status="established",
            source_refs=[observation_id],
        ))
    return build_trusted_goal_free_situation_observation(
        context=context,
        turn_id=observation_id,
        source_id="soridormi.sim.scene",
        source_revision=sequence,
        source=source,
        interpretations=interpretations,
    )
