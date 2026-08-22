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
    if len(parts) < 2:
        return None
    if parts[1] in {"error", "status"} and len(parts) == 2:
        return parts[0]
    if parts[1] == "output" and len(parts) >= 2:
        return parts[0]
    return None


def resolve_ref(ref: str, results: dict[str, NodeResult]) -> Any:
    node_id = ref_node_id(ref)
    if not node_id or node_id not in results:
        raise KeyError(f"unresolved ref: {ref}")
    parts = ref.split(".")
    if parts[1] == "error":
        value: Any = results[node_id].error or ""
        return value
    if parts[1] == "status":
        value = results[node_id].status
        return value
    if parts[1] != "output":
        raise KeyError(f"unresolved ref: {ref}")
    value = results[node_id].output
    for part in parts[2:]:
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
