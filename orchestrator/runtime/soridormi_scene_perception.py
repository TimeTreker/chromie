"""Admit Soridormi scene reads into Chromie Situation without ambient thinking.

Soridormi owns sensor/provider reads. Chromie owns Situation and cognition. This
module validates the provider observation, projects bounded scene markers into
Situation, and supports a mechanical ambient poll loop. A poll by itself never
invokes UMI, GA, Planner, Social Cognition, or Memory extraction.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from agent.app.tool_invocation import AsyncToolInvoker
from shared.chromie_contracts.situation import (
    SituationInterpretation,
    SituationRevisionObservation,
    SituationSourceRef,
)

from .situation import build_trusted_goal_free_situation_observation


AMBIENT_SCENE_POLL_INTERVAL_S = 0.5


def _validated_sim_scene_observation(
    payload: dict[str, Any],
    *,
    context: dict[str, Any],
) -> tuple[SituationRevisionObservation | None, str, int]:
    if (
        payload.get("mode") != "sim"
        or payload.get("source_kind") != "mujoco_scene_marker"
        or payload.get("mocked_simulation") is not True
    ):
        raise ValueError("scene observation lacks simulation source provenance")
    observation_id = payload.get("observation_id")
    sequence = payload.get("observation_sequence")
    scene_revision = payload.get("scene_revision")
    scene_signature = payload.get("scene_signature")
    objects = payload.get("objects")
    if (
        not isinstance(observation_id, str)
        or not observation_id.strip()
        or len(observation_id) > 120
        or type(sequence) is not int
        or sequence < 1
        or type(scene_revision) is not int
        or scene_revision < 1
        or not isinstance(scene_signature, str)
        or len(scene_signature) != 64
        or any(ch not in "0123456789abcdef" for ch in scene_signature)
        or not isinstance(objects, list)
    ):
        raise ValueError("scene observation has invalid identity, revision, or objects")
    if len(objects) > 32:
        raise ValueError("mock scene observation exceeds object limit")
    if not objects:
        return None, scene_signature, scene_revision

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
    observation = build_trusted_goal_free_situation_observation(
        context=context,
        turn_id=observation_id,
        source_id="soridormi.sim.scene",
        source_revision=scene_revision,
        source=source,
        interpretations=interpretations,
    )
    return observation, scene_signature, scene_revision


async def _read_soridormi_sim_scene(
    invoker: AsyncToolInvoker,
    *,
    context: dict[str, Any],
) -> tuple[SituationRevisionObservation | None, str, int]:
    outcome = await invoker.invoke("soridormi.robot.observe_scene", {})
    if outcome.status != "success":
        raise RuntimeError(outcome.error or "Soridormi scene observation failed")
    payload = outcome.output
    if not isinstance(payload, dict):
        raise ValueError("scene observation payload must be an object")
    return _validated_sim_scene_observation(payload, context=context)


async def observe_soridormi_sim_scene(
    invoker: AsyncToolInvoker,
    *,
    context: dict[str, Any],
) -> SituationRevisionObservation | None:
    """Read one explicit sim observation and project its bounded scene markers."""

    observation, _, _ = await _read_soridormi_sim_scene(invoker, context=context)
    return observation


async def refresh_soridormi_ambient_scene_once(host: Any) -> str:
    """Refresh Chromie's ambient Situation once without invoking cognition."""

    invoker = getattr(getattr(host, "interaction_runtime", None), "soridormi_invoker", None)
    if invoker is None:
        return "provider_unavailable"
    observation, signature, revision = await _read_soridormi_sim_scene(
        invoker,
        context=host.build_context(None),
    )
    previous_signature = getattr(host, "_ambient_scene_signature", None)
    if signature == previous_signature:
        return "unchanged"

    host._ambient_scene_signature = signature
    host._ambient_scene_revision = revision
    host._ambient_situation_projection = (
        observation.projection if observation is not None else None
    )
    if hasattr(host, "session_log"):
        host.session_log(
            None,
            "ambient_scene_revision: revision=%s objects=%s",
            revision,
            len(observation.projection.interpretations) if observation is not None else 0,
        )
    return "updated" if observation is not None else "cleared"


async def run_soridormi_ambient_perception_loop(
    host: Any,
    *,
    poll_interval_s: float = AMBIENT_SCENE_POLL_INTERVAL_S,
) -> None:
    """Mechanically maintain current Situation from Soridormi safe reads.

    This is not an ambient thinking loop. Polls never invoke UMI, GA, Planner,
    Social Cognition, or Memory extraction. They only replace current trusted
    perception when Soridormi reports a new semantic scene revision.
    """

    interval = max(0.1, float(poll_interval_s))
    unavailable_logged = False
    while True:
        try:
            await refresh_soridormi_ambient_scene_once(host)
            unavailable_logged = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not unavailable_logged and hasattr(host, "session_log"):
                host.session_log(
                    None,
                    "ambient_scene_perception_unavailable: error_type=%s error=%s",
                    type(exc).__name__,
                    str(exc)[:240],
                )
            unavailable_logged = True
        await asyncio.sleep(interval)
