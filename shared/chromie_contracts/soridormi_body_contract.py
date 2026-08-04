from __future__ import annotations

from typing import Any, Mapping


ABILITY_CLASS_LOCOMOTION = "locomotion_whole_body"
ABILITY_CLASS_SUBTLE_EXPRESSION = "subtle_expression"
CONTROL_COUPLING_PRIMARY = "primary_body_controller"
CONTROL_COUPLING_OVERLAY = "body_command_overlay"
CONTROL_COUPLING_INDEPENDENT = "independent_output"
CONTROL_COUPLING_STANDALONE = "standalone_body_motion"

_ALLOWED_ABILITY_CLASSES = {
    ABILITY_CLASS_LOCOMOTION,
    ABILITY_CLASS_SUBTLE_EXPRESSION,
}
_ALLOWED_CONTROL_COUPLINGS = {
    CONTROL_COUPLING_PRIMARY,
    CONTROL_COUPLING_OVERLAY,
    CONTROL_COUPLING_INDEPENDENT,
    CONTROL_COUPLING_STANDALONE,
}
_ALLOWED_BODY_LANES = {
    "subtle_expression",
    "locomotion",
    "whole_body",
    "safety",
}


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _derived_body_lane(ability_class: str, control_coupling: str) -> str | None:
    if ability_class == ABILITY_CLASS_LOCOMOTION:
        return "locomotion"
    if ability_class == ABILITY_CLASS_SUBTLE_EXPRESSION:
        return "subtle_expression"
    if control_coupling == CONTROL_COUPLING_PRIMARY:
        return "whole_body"
    return None


def normalize_soridormi_body_contract(item: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one live Soridormi skill's physical concurrency declaration.

    Soridormi's nested ``concurrency`` object remains canonical.  The flattened
    fields returned here are a bounded Chromie adapter for scheduling and
    catalog compatibility; they are never inferred from a capability name or a
    user phrase.
    """

    payload = dict(item)
    execution = _object(payload.get("execution"))
    metadata = _object(payload.get("metadata"))
    concurrency = _object(payload.get("concurrency"))
    if not concurrency:
        concurrency = _object(execution.get("concurrency"))
    if not concurrency:
        concurrency = _object(metadata.get("concurrency"))

    ability_class = str(concurrency.get("ability_class") or "").strip()
    control_coupling = str(concurrency.get("control_coupling") or "").strip()
    write_resources = _text_list(
        concurrency.get("write_resources"),
        field="concurrency.write_resources",
    )

    body_lane = str(
        payload.get("body_lane")
        or execution.get("body_lane")
        or metadata.get("body_lane")
        or _derived_body_lane(ability_class, control_coupling)
        or ""
    ).strip()
    if body_lane and body_lane not in _ALLOWED_BODY_LANES:
        raise ValueError(f"invalid Soridormi body_lane {body_lane!r}")

    if concurrency:
        if ability_class not in _ALLOWED_ABILITY_CLASSES:
            raise ValueError(
                f"invalid Soridormi concurrency.ability_class {ability_class!r}"
            )
        if control_coupling not in _ALLOWED_CONTROL_COUPLINGS:
            raise ValueError(
                "invalid Soridormi concurrency.control_coupling "
                f"{control_coupling!r}"
            )
        if not write_resources:
            raise ValueError(
                "Soridormi concurrency.write_resources must declare at least one resource"
            )

    legacy_resources = payload.get(
        "resource_claims",
        execution.get("resource_claims", []),
    )
    resource_claims = write_resources or _text_list(
        legacy_resources,
        field="resource_claims",
    )

    raw_parallel = payload.get(
        "can_run_parallel",
        execution.get("can_run_parallel"),
    )
    can_run_parallel = (
        bool(raw_parallel)
        if raw_parallel is not None
        else bool(concurrency)
    )

    exclusive_group = str(
        payload.get("exclusive_group")
        or execution.get("exclusive_group")
        or (
            "soridormi.resource." + resource_claims[0]
            if resource_claims
            else f"soridormi.body.{body_lane}"
            if body_lane
            else ""
        )
    ).strip() or None

    execution_constraints = _object(
        payload.get(
            "execution_constraints",
            execution.get("execution_constraints", {}),
        )
    )
    if concurrency:
        execution_constraints = {
            **execution_constraints,
            "ability_class": ability_class,
            "control_coupling": control_coupling,
            "parallel_safe_with": _text_list(
                concurrency.get("parallel_safe_with"),
                field="concurrency.parallel_safe_with",
            ),
            "locomotion_envelope": _object(
                concurrency.get("locomotion_envelope")
            ),
            "safety_preemption": str(
                concurrency.get("safety_preemption") or ""
            ).strip()
            or None,
        }

    return {
        "canonical_concurrency": concurrency,
        "ability_class": ability_class or None,
        "control_coupling": control_coupling or None,
        "body_lane": body_lane or None,
        "resource_claims": resource_claims,
        "can_run_parallel": can_run_parallel,
        "exclusive_group": exclusive_group,
        "execution_constraints": execution_constraints,
        "parallel_metadata_declared": bool(
            concurrency
            or raw_parallel is not None
            or exclusive_group
            or resource_claims
            or execution_constraints
        ),
        "provider_local_activity_compilation": bool(concurrency),
    }
