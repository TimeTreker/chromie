from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

try:
    from chromie_contracts.resource import AcquireAndDeliverResource, resource_semantic_bindings
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.resource import AcquireAndDeliverResource, resource_semantic_bindings

_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_LIST_LITERAL_SEPARATOR_RE = re.compile(r"[,，;；、]")

def _normalized_material_value(value: Any) -> Any:
    """Normalize only representation details for exact semantic comparisons."""

    if isinstance(value, str):
        normalized = " ".join(value.strip().casefold().split())
        if _NUMERIC_LITERAL_RE.fullmatch(normalized):
            try:
                return Decimal(normalized)
            except InvalidOperation:
                pass
        return normalized
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    if isinstance(value, dict):
        return {
            str(key): _normalized_material_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_normalized_material_value(item) for item in value]
    return value

def _normalized_entity_type(value: Any) -> str:
    """Normalize a model-authored binding type without inferring semantics."""

    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())

def _list_literal_items(value: str) -> list[str]:
    """Project one typed list literal into its representation-level items."""

    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return []
    return [
        item
        for part in _LIST_LITERAL_SEPARATOR_RE.split(normalized)
        if (item := " ".join(part.strip().split()))
    ]

def _material_values_equal(
    left: Any,
    right: Any,
    *,
    list_compatible: bool = False,
) -> bool:
    """Compare material values while tolerating only declared shape aliases.

    Goal Association may serialize a binding whose ``entity_type`` is ``list``
    as a delimiter-separated string, while a Capability schema correctly
    requires the executable argument to be a JSON array. That is a wire-shape
    difference, not a semantic contradiction. No arbitrary prose is split:
    list compatibility is enabled only by the typed binding or by an already
    structured list on the other side of a parameter-resolution comparison.
    """

    if isinstance(left, dict) and isinstance(right, dict):
        left_by_key = {str(key): value for key, value in left.items()}
        right_by_key = {str(key): value for key, value in right.items()}
        if left_by_key.keys() != right_by_key.keys():
            return False
        return all(
            _material_values_equal(
                left_by_key[key],
                right_by_key[key],
                list_compatible=(
                    isinstance(left_by_key[key], list) or isinstance(right_by_key[key], list)
                ),
            )
            for key in left_by_key
        )

    if list_compatible:
        if isinstance(left, str):
            left = _list_literal_items(left)
        if isinstance(right, str):
            right = _list_literal_items(right)
    elif (
        isinstance(left, (int, float, Decimal))
        and not isinstance(left, bool)
        and isinstance(right, str)
        and _NUMERIC_LITERAL_RE.fullmatch(right.strip()) is not None
    ) or (
        isinstance(right, (int, float, Decimal))
        and not isinstance(right, bool)
        and isinstance(left, str)
        and _NUMERIC_LITERAL_RE.fullmatch(left.strip()) is not None
    ):
        try:
            return Decimal(str(left).strip()) == Decimal(str(right).strip())
        except InvalidOperation:
            return False
    return _normalized_material_value(left) == _normalized_material_value(right)

def _goal_binding_map(goal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return one transient typed binding view from the canonical Goal authority.

    Non-resource Goals own ``object.bindings``. Resource Goals own only
    ``resource_responsibility``; their flat view is computed on demand and is never
    persisted back into the Goal.
    """

    raw_resource = goal.get("resource_responsibility")
    if isinstance(raw_resource, dict):
        responsibility = AcquireAndDeliverResource.model_validate(raw_resource)
        raw_bindings = resource_semantic_bindings(responsibility)
    else:
        goal_object = goal.get("object")
        if not isinstance(goal_object, dict):
            return {}
        raw_bindings = goal_object.get("bindings")
        if not isinstance(raw_bindings, dict):
            return {}
    bindings: dict[str, dict[str, Any]] = {}
    for raw_name, raw_binding in raw_bindings.items():
        name = " ".join(str(raw_name or "").strip().split())
        if not name or not isinstance(raw_binding, dict) or "value" not in raw_binding:
            continue
        bindings[name] = {
            "entity_type": _normalized_entity_type(raw_binding.get("entity_type")),
            "value": raw_binding.get("value"),
        }
    return bindings

def _argument_realization_contract(
    capability: dict[str, Any],
    entity_type: str,
) -> dict[str, Any] | None:
    """Return a Capability-owned semantic-to-argument realization contract.

    Goal Association owns human semantic scope.  A selected Capability may declare
    how Planner is allowed to realize one semantic entity type into provider-local
    arguments.  The Host validates only that the declared boundary and provenance
    are respected; it never interprets the user's natural-language scope itself.
    """

    hints = capability.get("hints")
    if not isinstance(hints, dict):
        return None
    contracts = hints.get("argument_realization")
    if not isinstance(contracts, dict):
        return None
    normalized = _normalized_entity_type(entity_type)
    for contract in contracts.values():
        if not isinstance(contract, dict):
            continue
        if _normalized_entity_type(contract.get("source_entity_type")) == normalized:
            return contract
    return None

def _argument_schema_accepts_canonical_binding(
    argument_schema: dict[str, Any],
    value: Any,
) -> bool:
    """Return whether a binding can be copied without semantic conversion."""

    if "const" in argument_schema:
        return argument_schema["const"] == value
    enum = argument_schema.get("enum")
    if isinstance(enum, list):
        return value in enum
    value_type = argument_schema.get("type")
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type in {"integer", "number"}:
        numeric_values = semantic_numeric_values(value)
        if len(numeric_values) != 1:
            return False
        numeric_value = next(iter(numeric_values))
        if value_type == "integer" and numeric_value != numeric_value.to_integral_value():
            return False
        minimum = argument_schema.get("minimum")
        maximum = argument_schema.get("maximum")
        if minimum is not None and numeric_value < Decimal(str(minimum)):
            return False
        if maximum is not None and numeric_value > Decimal(str(maximum)):
            return False
        return True
    return False

_SINGLE_SEMANTIC_NUMBER = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?)\s*[^\d]*$"
)


def semantic_numeric_values(value: Any) -> set[Decimal]:
    """Collect exact user-semantic quantities without mining prose or IDs."""

    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float, Decimal)):
        try:
            return {Decimal(str(value))}
        except InvalidOperation:
            return set()
    if isinstance(value, str):
        match = _SINGLE_SEMANTIC_NUMBER.fullmatch(value)
        if match is None:
            return set()
        try:
            return {Decimal(match.group(1))}
        except InvalidOperation:
            return set()
    if isinstance(value, dict):
        return {
            number
            for key, item in value.items()
            if str(key).strip().casefold()
            not in {"confidence", "schema_version", "version", "referent_id"}
            for number in semantic_numeric_values(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            number
            for item in value
            for number in semantic_numeric_values(item)
        }
    return set()
