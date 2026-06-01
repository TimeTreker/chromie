from __future__ import annotations

from typing import Any

from .models import NodeResult

REF_KEY = "$ref"


def iter_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        if set(value.keys()) == {REF_KEY} and isinstance(value[REF_KEY], str):
            refs.append(value[REF_KEY])
        else:
            for child in value.values():
                refs.extend(iter_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(iter_refs(child))
    return refs


def ref_node_id(ref: str) -> str | None:
    parts = ref.split(".")
    if len(parts) < 3 or parts[1] != "output":
        return None
    return parts[0]


def resolve_ref(ref: str, results: dict[str, NodeResult]) -> Any:
    node_id = ref_node_id(ref)
    if not node_id or node_id not in results:
        raise KeyError(f"unresolved ref: {ref}")
    value: Any = results[node_id].output
    for part in ref.split(".")[2:]:
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"unresolved ref field: {ref}")
        value = value[part]
    return value


def resolve_refs(value: Any, results: dict[str, NodeResult]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {REF_KEY} and isinstance(value[REF_KEY], str):
            return resolve_ref(value[REF_KEY], results)
        return {key: resolve_refs(child, results) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_refs(child, results) for child in value]
    return value
