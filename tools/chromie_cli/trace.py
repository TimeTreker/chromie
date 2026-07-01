"""Trace artifact viewer for the Chromie developer CLI."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .output import CommandResult, ExitCode


IDENTIFIER_KEYS = {
    "session": {"sid", "session_id", "origin_session_id", "session_ids"},
    "interaction": {"interaction_id", "active_interaction_ids"},
    "graph": {"graph_id", "active_graph_ids"},
    "trace": {"trace_id"},
}
TRACE_JSON_FILENAMES = {
    "route.json",
    "interaction_response.json",
    "execution.json",
    "trace.json",
    "summary.json",
}
TRACE_CONTENT_KEYS = {
    "sid",
    "session_id",
    "session_ids",
    "interaction_id",
    "graph_id",
    "trace_id",
    "outcome_summary",
    "node_results",
    "events",
    "traces",
    "route",
    "intent",
    "results",
    "skills",
    "debug_summary",
}


def trace_view(
    root: Path,
    *,
    trace_root: Path | None = None,
    source_file: Path | None = None,
    session: str | None = None,
    interaction: str | None = None,
    graph: str | None = None,
    trace: str | None = None,
    limit: int = 20,
) -> CommandResult:
    root = root.resolve()
    warnings: list[str] = []
    filters = {
        "session": _clean_filter(session),
        "interaction": _clean_filter(interaction),
        "graph": _clean_filter(graph),
        "trace": _clean_filter(trace),
    }
    active_filters = {name: value for name, value in filters.items() if value}

    if source_file is not None:
        source_file = _resolve_under_root(root, source_file)
        if not source_file.is_file():
            return CommandResult(
                status="failure",
                message=f"Trace source file does not exist: {source_file}",
                details={
                    "schema_version": 1,
                    "source_file": str(source_file),
                    "filters": filters,
                    "warnings": [f"missing trace source file: {source_file}"],
                },
                exit_code=ExitCode.FAILURE,
            )
        scan_root = source_file.parent
        paths = [source_file]
        source = "file"
    else:
        scan_root = _resolve_under_root(
            root,
            trace_root or Path(".chromie") / "acceptance",
        )
        source = "scan"
        if not scan_root.exists():
            return _no_trace_result(
                trace_root=scan_root,
                source=source,
                filters=filters,
                limit=limit,
                warnings=[f"trace root does not exist: {scan_root}"],
            )
        paths = _discover_trace_paths(scan_root)

    artifacts = [
        artifact
        for path in paths
        for artifact in [
            _read_artifact(
                path,
                scan_root=scan_root,
                filters=active_filters,
                limit=limit,
                warnings=warnings,
                force=source_file is not None,
            )
        ]
        if artifact is not None
    ]
    matched_records = sum(int(item.get("matched_records", 0)) for item in artifacts)
    details = {
        "schema_version": 1,
        "source": source,
        "trace_root": str(scan_root),
        "filters": filters,
        "limits": {"records_per_artifact": limit},
        "artifacts_scanned": len(paths),
        "artifacts_matched": len(artifacts),
        "matched_records": matched_records,
        "warnings": warnings,
        "artifacts": artifacts,
        "claim_note": (
            "Trace view reads retained local artifacts only. It does not create "
            "target validation, live service evidence, or release readiness."
        ),
    }
    if artifacts:
        return CommandResult(
            status="ok",
            message=(
                f"Trace view matched {matched_records} record(s) across "
                f"{len(artifacts)} artifact(s)."
            ),
            details=details,
            exit_code=ExitCode.OK,
        )
    if paths:
        message = "Trace artifacts were found, but none matched the requested filters."
    else:
        message = "Trace view found no retained trace artifacts."
    return CommandResult(
        status="warning",
        message=message,
        details=details,
        exit_code=ExitCode.WARNING,
    )


def _no_trace_result(
    *,
    trace_root: Path,
    source: str,
    filters: dict[str, str | None],
    limit: int,
    warnings: list[str],
) -> CommandResult:
    return CommandResult(
        status="warning",
        message="Trace view found no retained trace artifacts.",
        details={
            "schema_version": 1,
            "source": source,
            "trace_root": str(trace_root),
            "filters": filters,
            "limits": {"records_per_artifact": limit},
            "artifacts_scanned": 0,
            "artifacts_matched": 0,
            "matched_records": 0,
            "warnings": warnings,
            "artifacts": [],
            "claim_note": (
                "Trace view reads retained local artifacts only. It does not "
                "create target validation, live service evidence, or release "
                "readiness."
            ),
        },
        exit_code=ExitCode.WARNING,
    )


def _resolve_under_root(root: Path, path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _discover_trace_paths(trace_root: Path) -> list[Path]:
    jsonl = sorted(path for path in trace_root.rglob("*.jsonl") if path.is_file())
    json_paths = sorted(path for path in trace_root.rglob("*.json") if path.is_file())
    return [*jsonl, *json_paths]


def _read_artifact(
    path: Path,
    *,
    scan_root: Path,
    filters: dict[str, str],
    limit: int,
    warnings: list[str],
    force: bool,
) -> dict[str, Any] | None:
    if path.suffix == ".jsonl":
        return _read_jsonl_artifact(
            path,
            scan_root=scan_root,
            filters=filters,
            limit=limit,
            warnings=warnings,
            force=force,
        )
    if path.suffix == ".json":
        return _read_json_artifact(
            path,
            scan_root=scan_root,
            filters=filters,
            limit=limit,
            warnings=warnings,
            force=force,
        )
    return None


def _read_jsonl_artifact(
    path: Path,
    *,
    scan_root: Path,
    filters: dict[str, str],
    limit: int,
    warnings: list[str],
    force: bool,
) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    parse_errors = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        warnings.append(f"{path}: could not read JSONL artifact: {exc}")
        return None
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors += 1
            warnings.append(f"{path}:{line_number}: invalid JSONL record: {exc.msg}")
            continue
        if isinstance(loaded, dict):
            records.append(loaded)
        else:
            parse_errors += 1
            warnings.append(f"{path}:{line_number}: JSONL record is not an object")

    if not force and not records:
        return None
    matched = _filter_records(records, filters)
    if filters and not matched:
        return None
    sample = matched[:limit]
    identifiers = _collect_identifiers(records)
    artifact = {
        "path": str(path),
        "relative_path": _relative(path, scan_root),
        "kind": _jsonl_kind(records),
        "record_count": len(records),
        "matched_records": len(matched),
        "parse_errors": parse_errors,
        "identifiers": identifiers,
        "records": [_summarize_event_record(record) for record in sample],
        "event_timeline": _summarize_event_timeline(matched, limit=limit),
    }
    workflow_graphs = [
        _summarize_workflow_graph(record.get("graph"), limit=limit)
        for record in matched
        if record.get("event") == "session_workflow_graph"
        and isinstance(record.get("graph"), dict)
    ]
    if workflow_graphs:
        artifact["workflow_graphs"] = workflow_graphs[:limit]
        artifact["workflow_graph_count"] = len(workflow_graphs)
    return artifact


def _read_json_artifact(
    path: Path,
    *,
    scan_root: Path,
    filters: dict[str, str],
    limit: int,
    warnings: list[str],
    force: bool,
) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append(f"{path}: invalid JSON: {exc.msg}")
        return None
    except OSError as exc:
        warnings.append(f"{path}: could not read JSON artifact: {exc}")
        return None

    if not force and not _looks_like_trace_json(path, loaded):
        return None
    if filters and not _matches_filters(loaded, filters):
        return None
    identifiers = _collect_identifiers(loaded)
    summary = _summarize_json_payload(loaded, limit=limit)
    return {
        "path": str(path),
        "relative_path": _relative(path, scan_root),
        "kind": _json_kind(path, loaded),
        "record_count": 1,
        "matched_records": 1,
        "parse_errors": 0,
        "identifiers": identifiers,
        "summary": summary,
    }


def _filter_records(
    records: Iterable[dict[str, Any]],
    filters: dict[str, str],
) -> list[dict[str, Any]]:
    if not filters:
        return list(records)
    return [record for record in records if _matches_filters(record, filters)]


def _matches_filters(value: Any, filters: dict[str, str]) -> bool:
    return all(
        _contains_identifier(value, IDENTIFIER_KEYS[name], expected)
        for name, expected in filters.items()
    )


def _contains_identifier(value: Any, keys: set[str], expected: str) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys and _value_contains(nested, expected):
                return True
            if _contains_identifier(nested, keys, expected):
                return True
    elif isinstance(value, list):
        return any(_contains_identifier(item, keys, expected) for item in value)
    return False


def _value_contains(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, (int, float, bool)):
        return str(value) == expected
    if isinstance(value, list):
        return any(_value_contains(item, expected) for item in value)
    if isinstance(value, dict):
        return any(_value_contains(item, expected) for item in value.values())
    return False


def _collect_identifiers(value: Any) -> dict[str, list[str]]:
    collected: dict[str, set[str]] = {name: set() for name in IDENTIFIER_KEYS}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                for name, keys in IDENTIFIER_KEYS.items():
                    if key in keys:
                        collected[name].update(_scalar_values(nested))
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return {
        name: sorted(values)
        for name, values in collected.items()
        if values
    }


def _scalar_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (int, float, bool)):
        return {str(value)}
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            values.update(_scalar_values(item))
        return values
    return set()


def _looks_like_trace_json(path: Path, value: Any) -> bool:
    if path.name in TRACE_JSON_FILENAMES:
        return True
    if not isinstance(value, dict):
        return False
    return bool(TRACE_CONTENT_KEYS.intersection(value.keys()))


def _jsonl_kind(records: list[dict[str, Any]]) -> str:
    if any({"sid", "event", "message"}.issubset(record.keys()) for record in records):
        return "session_events_jsonl"
    return "jsonl_events"


def _json_kind(path: Path, value: Any) -> str:
    if isinstance(value, dict):
        if "graph_id" in value and ("node_results" in value or "outcome_summary" in value):
            return "task_graph_trace"
        if "interaction_id" in value and "traces" in value and "results" in value:
            return "skill_runtime_execution"
        if "interaction_id" in value and "skills" in value:
            return "interaction_response"
        if "route" in value and "intent" in value:
            return "route_decision"
        if path.name == "summary.json":
            return "acceptance_summary"
    return "json_trace_artifact"


def _summarize_json_payload(value: Any, *, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    summary: dict[str, Any] = {
        "top_level_keys": sorted(str(key) for key in value.keys())[:40],
    }
    for key in (
        "ok",
        "status",
        "intent",
        "confidence",
        "sid",
        "session_id",
        "interaction_id",
        "graph_id",
        "trace_id",
        "outcome_summary",
        "summary",
        "text",
    ):
        if key in value:
            summary[key] = _shorten(value[key])
    route = value.get("route")
    if isinstance(route, dict):
        summary["route"] = _summarize_route_decision(route, limit=limit)
    elif "route" in value:
        summary["route"] = _shorten(value["route"])
    interaction_response = value.get("interaction_response")
    if isinstance(interaction_response, dict):
        summary["interaction_response"] = _summarize_interaction_response(
            interaction_response,
            limit=limit,
        )
    for key in ("session_state", "status_before", "status_after", "checks"):
        nested = value.get(key)
        if isinstance(nested, dict):
            summary[key] = _summarize_scalar_mapping(nested, limit=limit)
    if isinstance(value.get("errors"), list):
        summary["errors"] = [_shorten(item) for item in value["errors"][:limit]]
        summary["error_count"] = len(value["errors"])
    if isinstance(value.get("skills"), list):
        summary["skill_ids"] = [
            str(item.get("skill_id") or item.get("id") or "")
            for item in value["skills"][:limit]
            if isinstance(item, dict)
        ]
        summary["skill_count"] = len(value["skills"])
    if isinstance(value.get("results"), list):
        summary["results"] = [
            _summarize_result(item)
            for item in value["results"][:limit]
            if isinstance(item, dict)
        ]
        summary["result_count"] = len(value["results"])
    if isinstance(value.get("traces"), list):
        summary["traces"] = [
            _summarize_skill_trace(item)
            for item in value["traces"][:limit]
            if isinstance(item, dict)
        ]
        summary["trace_count"] = len(value["traces"])
    if isinstance(value.get("node_results"), list):
        summary["node_results"] = [
            _summarize_node_result(item)
            for item in value["node_results"][:limit]
            if isinstance(item, dict)
        ]
        summary["node_result_count"] = len(value["node_results"])
    if isinstance(value.get("events"), list):
        summary["events"] = [
            _summarize_execution_event(item)
            for item in value["events"][:limit]
            if isinstance(item, dict)
        ]
        summary["event_count"] = len(value["events"])
    nested_execution = value.get("execution")
    if isinstance(nested_execution, dict):
        summary["execution"] = _summarize_json_payload(nested_execution, limit=limit)
    return summary


def _summarize_route_decision(route: dict[str, Any], *, limit: int) -> dict[str, Any]:
    summary = {
        key: _shorten(route[key])
        for key in (
            "route",
            "intent",
            "confidence",
            "source",
            "language",
            "priority",
            "reason",
        )
        if key in route
    }
    agents = route.get("agents")
    if isinstance(agents, list):
        summary["agents"] = [str(agent) for agent in agents[:limit]]
        summary["agent_count"] = len(agents)
    actions = route.get("actions")
    if isinstance(actions, list):
        summary["actions"] = [
            _summarize_route_action(item)
            for item in actions[:limit]
            if isinstance(item, dict)
        ]
        summary["action_count"] = len(actions)
    candidates = route.get("candidate_capabilities")
    if isinstance(candidates, list):
        summary["candidate_capability_ids"] = [
            str(item.get("capability_id") or item.get("id") or "")
            for item in candidates[:limit]
            if isinstance(item, dict)
        ]
        summary["candidate_count"] = len(candidates)
    metadata = route.get("metadata")
    if isinstance(metadata, dict):
        route_merge = metadata.get("route_merge")
        if isinstance(route_merge, dict):
            summary["route_merge"] = _summarize_scalar_mapping(route_merge, limit=limit)
        task_list = metadata.get("task_list")
        if isinstance(task_list, list):
            summary["task_types"] = [
                str(item.get("task_type") or "")
                for item in task_list[:limit]
                if isinstance(item, dict)
            ]
            summary["task_count"] = len(task_list)
    return summary


def _summarize_route_action(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _shorten(item[key])
        for key in (
            "capability_id",
            "skill_id",
            "sequence",
            "timing",
            "requires_confirmation",
        )
        if key in item
    }


def _summarize_interaction_response(
    response: dict[str, Any],
    *,
    limit: int,
) -> dict[str, Any]:
    summary = {
        key: _shorten(response[key])
        for key in (
            "interaction_id",
            "status",
            "reason",
            "requires_confirmation",
        )
        if key in response
    }
    speech = response.get("speech")
    if isinstance(speech, list):
        summary["speech"] = [
            _summarize_speech_item(item)
            for item in speech[:limit]
            if isinstance(item, dict)
        ]
        summary["speech_count"] = len(speech)
    skills = response.get("skills")
    if isinstance(skills, list):
        summary["skill_ids"] = [
            str(item.get("skill_id") or item.get("id") or "")
            for item in skills[:limit]
            if isinstance(item, dict)
        ]
        summary["skill_count"] = len(skills)
    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        summary["metadata_keys"] = sorted(str(key) for key in metadata.keys())[:limit]
    return summary


def _summarize_speech_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _shorten(item[key])
        for key in ("id", "text", "style", "timing", "priority")
        if key in item
    }


def _summarize_scalar_mapping(value: dict[str, Any], *, limit: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in sorted(value.keys())[:limit]:
        nested = value[key]
        if isinstance(nested, (str, int, float, bool)) or nested is None:
            summary[str(key)] = _shorten(nested)
        elif isinstance(nested, list):
            summary[str(key)] = [_shorten(item) for item in nested[:limit]]
            summary[f"{key}_count"] = len(nested)
        elif isinstance(nested, dict):
            summary[str(key)] = {
                "keys": sorted(str(item_key) for item_key in nested.keys())[:limit],
            }
    summary["key_count"] = len(value)
    return summary


def _summarize_event_record(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "timestamp_utc",
        "timestamp",
        "sid",
        "session_id",
        "elapsed_ms",
        "event",
        "message",
        "interaction_id",
        "graph_id",
        "trace_id",
        "status",
        "route",
        "intent",
    )
    summary = {
        key: _shorten(record[key])
        for key in keys
        if key in record
    }
    if record.get("event") == "session_workflow_graph" and isinstance(
        record.get("graph"),
        dict,
    ):
        summary["workflow_graph"] = _summarize_workflow_graph(record["graph"], limit=5)
    return summary


def _summarize_event_timeline(
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> dict[str, Any]:
    if not records:
        return {"record_count": 0}
    event_names = [
        str(record.get("event") or record.get("type") or "")
        for record in records
        if record.get("event") is not None or record.get("type") is not None
    ]
    status_names = [
        str(record.get("status"))
        for record in records
        if record.get("status") is not None
    ]
    elapsed_values = [
        float(record["elapsed_ms"])
        for record in records
        if isinstance(record.get("elapsed_ms"), (int, float))
    ]
    summary: dict[str, Any] = {
        "record_count": len(records),
        "events": event_names[:limit],
        "event_counts": _top_counts(event_names, limit=limit),
    }
    if status_names:
        summary["status_counts"] = _top_counts(status_names, limit=limit)
    if elapsed_values:
        first_elapsed = elapsed_values[0]
        last_elapsed = elapsed_values[-1]
        summary["first_elapsed_ms"] = _shorten(first_elapsed)
        summary["last_elapsed_ms"] = _shorten(last_elapsed)
        summary["duration_ms"] = _shorten(max(0.0, last_elapsed - first_elapsed))
    markers = {
        "fallback": _records_have_marker(records, "fallback"),
        "cancellation": _records_have_marker(records, "cancellation"),
        "stop": _records_have_marker(records, "stop"),
        "emergency": _records_have_marker(records, "emergency"),
        "timeout": _records_have_marker(records, "timeout"),
        "error": _records_have_marker(records, "error"),
    }
    active_markers = {
        name: present
        for name, present in markers.items()
        if present
    }
    if active_markers:
        summary["markers"] = active_markers
    return summary


def _records_have_marker(records: list[dict[str, Any]], marker: str) -> bool:
    return any(_record_has_marker(record, marker) for record in records)


def _record_has_marker(record: dict[str, Any], marker: str) -> bool:
    status = str(record.get("status") or "").lower()
    text = (
        str(record.get("event") or "")
        + "\n"
        + status
        + "\n"
        + str(record.get("message") or "")
    ).lower()
    if marker == "fallback":
        return "fallback" in text
    if marker == "cancellation":
        return status in {"cancelled", "canceled"} or re.search(
            r"\bcancel(?:led|ed|lation)?\b",
            text,
        ) is not None
    if marker == "stop":
        return (
            re.search(r"\bstop(?:_current_output|_now|_polling)?\b", text)
            is not None
        )
    if marker == "emergency":
        return "emergency" in text
    if marker == "timeout":
        return status in {"timeout", "timed_out"} or re.search(
            r"\btimeout\b|\btimed out\b|\btimed_out\b",
            text,
        ) is not None
    if marker == "error":
        return status in {"failed", "failure", "error"} or re.search(
            r"\b(?:error|failed|failure)\b"
            r"|\berrors=[1-9]\d*\b"
            r"|\bfailed_[a-z_]+=[1-9]\d*\b",
            text,
        ) is not None
    return False


def _top_counts(values: list[str], *, limit: int) -> dict[str, int]:
    return dict(Counter(value for value in values if value).most_common(limit))


def _summarize_workflow_graph(value: Any, *, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nodes = value.get("nodes") if isinstance(value.get("nodes"), list) else []
    edges = value.get("edges") if isinstance(value.get("edges"), list) else []
    summary: dict[str, Any] = {
        "schema_version": value.get("schema_version"),
        "sid": value.get("sid"),
        "total_ms": value.get("total_ms"),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    if nodes:
        summary["events"] = [
            str(node.get("event") or "")
            for node in nodes[:limit]
            if isinstance(node, dict)
        ]
        slow_nodes = sorted(
            (
                node
                for node in nodes
                if isinstance(node, dict)
                and isinstance(node.get("delta_from_previous_ms"), (int, float))
            ),
            key=lambda node: float(node.get("delta_from_previous_ms") or 0.0),
            reverse=True,
        )[:limit]
        summary["slowest_nodes"] = [
            {
                "event": str(node.get("event") or ""),
                "delta_from_previous_ms": _shorten(node.get("delta_from_previous_ms")),
                "elapsed_ms": _shorten(node.get("elapsed_ms")),
            }
            for node in slow_nodes
        ]
    return summary


def _summarize_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _shorten(item[key])
        for key in (
            "request_id",
            "skill_id",
            "provider_id",
            "status",
            "reason_code",
            "message",
            "trace_id",
        )
        if key in item
    }


def _summarize_skill_trace(item: dict[str, Any]) -> dict[str, Any]:
    summary = {
        key: _shorten(item[key])
        for key in (
            "trace_id",
            "interaction_id",
            "request_id",
            "skill_id",
            "provider_id",
            "status",
        )
        if key in item
    }
    events = item.get("events")
    if isinstance(events, list):
        summary["events"] = [
            _summarize_execution_event(event)
            for event in events[:10]
            if isinstance(event, dict)
        ]
        summary["event_count"] = len(events)
    return summary


def _summarize_node_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _shorten(item[key])
        for key in (
            "node_id",
            "tool",
            "status",
            "error",
            "attempts",
            "blocked_by",
        )
        if key in item
    }


def _summarize_execution_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _shorten(item[key])
        for key in ("timestamp", "type", "node_id", "tool", "message", "status")
        if key in item
    }


def _shorten(value: Any, *, max_chars: int = 240) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[: max_chars - 3] + "..."
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
