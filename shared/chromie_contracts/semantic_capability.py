from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def normalize_semantic_capability_facade(
    value: Any,
    *,
    capability_id: str,
    provider_input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a provider-declared semantic facade for one Capability.

    The facade changes only the Core-facing argument vocabulary. Provider-local
    encodings remain below the trusted adapter boundary and are materialized by
    :func:`realize_semantic_capability_args` immediately before provider use.
    """

    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Capability {capability_id!r} semantic_facade must be an object")

    semantic_schema = value.get("input_schema")
    if not isinstance(semantic_schema, Mapping):
        raise ValueError(
            f"Capability {capability_id!r} semantic_facade requires input_schema"
        )
    semantic_schema = dict(semantic_schema)
    if semantic_schema.get("type") != "object":
        raise ValueError(
            f"Capability {capability_id!r} semantic_facade input_schema must be an object schema"
        )
    if semantic_schema.get("additionalProperties") is not False:
        raise ValueError(
            f"Capability {capability_id!r} semantic_facade input_schema must be closed"
        )
    semantic_properties = semantic_schema.get("properties")
    if not isinstance(semantic_properties, Mapping):
        raise ValueError(
            f"Capability {capability_id!r} semantic_facade input_schema requires properties"
        )
    provider_properties = provider_input_schema.get("properties")
    if not isinstance(provider_properties, Mapping):
        provider_properties = {}

    raw_realizations = value.get("provider_realizations", {})
    if not isinstance(raw_realizations, Mapping):
        raise ValueError(
            f"Capability {capability_id!r} semantic_facade provider_realizations must be an object"
        )

    normalized_realizations: dict[str, dict[str, Any]] = {}
    for raw_provider_arg, raw_contract in raw_realizations.items():
        provider_arg = str(raw_provider_arg).strip()
        if not provider_arg or provider_arg not in provider_properties:
            raise ValueError(
                f"Capability {capability_id!r} semantic facade names unknown provider argument {provider_arg!r}"
            )
        if not isinstance(raw_contract, Mapping):
            raise ValueError(
                f"Capability {capability_id!r} realization for {provider_arg!r} must be an object"
            )
        contract = dict(raw_contract)
        kind = str(contract.get("kind") or "").strip()
        if kind != "signed_magnitude":
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} has unsupported kind {kind!r}"
            )
        direction_argument = str(contract.get("direction_argument") or "").strip()
        raw_magnitude_argument = contract.get("magnitude_argument")
        magnitude_argument = (
            str(raw_magnitude_argument).strip()
            if raw_magnitude_argument not in (None, "")
            else ""
        )
        if direction_argument not in semantic_properties:
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} names unknown direction argument"
            )
        if magnitude_argument and magnitude_argument not in semantic_properties:
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} names unknown magnitude argument"
            )
        positive_direction = str(contract.get("positive_direction") or "").strip()
        negative_direction = str(contract.get("negative_direction") or "").strip()
        if not positive_direction or not negative_direction or positive_direction == negative_direction:
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} requires distinct positive/negative directions"
            )
        direction_schema = semantic_properties[direction_argument]
        direction_enum = direction_schema.get("enum") if isinstance(direction_schema, Mapping) else None
        if not isinstance(direction_enum, list) or positive_direction not in direction_enum or negative_direction not in direction_enum:
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} directions must be declared by the semantic enum"
            )
        default_magnitude = contract.get("default_magnitude")
        if magnitude_argument:
            if default_magnitude is not None and (
                isinstance(default_magnitude, bool)
                or not isinstance(default_magnitude, (int, float))
                or float(default_magnitude) <= 0
            ):
                raise ValueError(
                    f"Capability {capability_id!r} realization {provider_arg!r} has invalid default_magnitude"
                )
        elif (
            isinstance(default_magnitude, bool)
            or not isinstance(default_magnitude, (int, float))
            or float(default_magnitude) <= 0
        ):
            raise ValueError(
                f"Capability {capability_id!r} realization {provider_arg!r} requires positive default_magnitude"
            )
        normalized_realizations[provider_arg] = {
            "kind": kind,
            "direction_argument": direction_argument,
            "magnitude_argument": magnitude_argument or None,
            "positive_direction": positive_direction,
            "negative_direction": negative_direction,
            "default_magnitude": float(default_magnitude) if default_magnitude is not None else None,
        }

    provider_required = {
        str(item)
        for item in (provider_input_schema.get("required") or [])
        if str(item).strip()
    }
    semantic_names = {str(name) for name in semantic_properties}
    directly_supplied = provider_required & semantic_names
    unrealized_required = provider_required - directly_supplied - set(normalized_realizations)
    if unrealized_required:
        raise ValueError(
            f"Capability {capability_id!r} semantic facade cannot realize required provider arguments {sorted(unrealized_required)}"
        )

    return {
        "input_schema": semantic_schema,
        "provider_realizations": normalized_realizations,
    }


def realize_semantic_capability_args(
    args: Mapping[str, Any],
    *,
    facade: Mapping[str, Any] | None,
    provider_input_schema: Mapping[str, Any],
    capability_id: str = "runtime",
) -> dict[str, Any]:
    """Materialize provider-local arguments from trusted semantic Capability args."""

    if not facade:
        return dict(args)
    normalized = normalize_semantic_capability_facade(
        facade,
        capability_id=capability_id,
        provider_input_schema=provider_input_schema,
    )
    semantic_schema = normalized["input_schema"]
    semantic_properties = semantic_schema.get("properties") or {}
    unknown = set(args) - set(semantic_properties)
    if unknown:
        raise ValueError(f"semantic Capability args contain unknown fields {sorted(unknown)}")

    provider_properties = provider_input_schema.get("properties") or {}
    generated_targets = set(normalized["provider_realizations"])
    provider_args: dict[str, Any] = {
        name: value
        for name, value in args.items()
        if name in provider_properties and name not in generated_targets
    }

    for provider_arg, contract in normalized["provider_realizations"].items():
        direction = args.get(contract["direction_argument"])
        if direction not in {contract["positive_direction"], contract["negative_direction"]}:
            raise ValueError(
                f"semantic direction {direction!r} cannot realize provider argument {provider_arg!r}"
            )
        magnitude_argument = contract.get("magnitude_argument")
        magnitude = args.get(magnitude_argument) if magnitude_argument else None
        if magnitude is None:
            magnitude = contract.get("default_magnitude")
        if isinstance(magnitude, bool) or not isinstance(magnitude, (int, float)) or float(magnitude) <= 0:
            raise ValueError(
                f"semantic magnitude cannot realize provider argument {provider_arg!r}"
            )
        signed = float(magnitude)
        if direction == contract["negative_direction"]:
            signed = -signed
        provider_args[provider_arg] = signed

    missing = [
        str(name)
        for name in (provider_input_schema.get("required") or [])
        if str(name) not in provider_args
    ]
    if missing:
        raise ValueError(f"semantic facade did not realize required provider arguments {missing}")
    return provider_args
