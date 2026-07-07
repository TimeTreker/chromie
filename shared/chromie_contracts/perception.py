from __future__ import annotations

from typing import Any

LIVE_PERCEPTION_CONTRACT_VERSION = "live_perception_dependency_v1"
_DEFAULT_DEPENDENCY = "runtime_observation"
_DEPENDENCY_ALIASES = {
    "find": "locate_object",
    "find_object": "locate_object",
    "locate": "locate_object",
    "locate_target": "locate_object",
    "object_location": "locate_object",
    "scan": "inspect_scene",
    "search": "locate_object",
    "see": "inspect_scene",
}


def normalize_perception_dependency(value: Any) -> str:
    text = "_".join(str(value or "").strip().lower().replace("-", "_").split())
    if not text:
        return _DEFAULT_DEPENDENCY
    return _DEPENDENCY_ALIASES.get(text, text)


def live_perception_dependency_from_metadata(
    *sources: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a machine-readable live-perception dependency if requested.

    The contract intentionally contains semantic dependency information only.
    It must not carry coordinates, poses, joint targets, or other physical-world
    facts invented by Chromie. Soridormi owns real-time perception, pose
    estimation, and closed-loop execution.
    """

    requires = False
    dependency: Any = None
    reason: Any = None
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("requires_live_perception") is True:
            requires = True
        if source.get("perception_dependency") is not None:
            dependency = source.get("perception_dependency")
            requires = True
        if source.get("live_perception_dependency") is not None:
            dependency = source.get("live_perception_dependency")
            requires = True
        if source.get("perception_reason") is not None:
            reason = source.get("perception_reason")
    if not requires:
        return None
    payload: dict[str, Any] = {
        "requires_live_perception": True,
        "perception_dependency": normalize_perception_dependency(dependency),
        "contract_version": LIVE_PERCEPTION_CONTRACT_VERSION,
        "physical_state_source": "soridormi_runtime",
        "chromie_must_not_provide_physical_coordinates": True,
        "soridormi_owns_pose_estimation": True,
        "allowed_chromie_inputs": [
            "semantic_target",
            "user_goal",
            "preference_constraints",
        ],
        "expected_soridormi_feedback": [
            "observation_summary",
            "target_found_confidence",
            "failure_code",
            "recommended_next_actions",
        ],
    }
    if reason is not None:
        payload["reason"] = str(reason)[:240]
    return payload
