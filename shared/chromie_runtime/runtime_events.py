"""Versioned, durable runtime-event packages for Chromie producers.

A runtime event is an immutable local evidence package. Chromie producers own
classification and payload construction. The external data loop owns merging,
deduplication, bandwidth/storage governance, retention, and cloud delivery.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RUNTIME_EVENT_SCHEMA_VERSION = 1
RUNTIME_EVENT_TRIGGER_SCHEMA_VERSION = 1


def persist_runtime_event(
    *,
    event_type: str,
    event_subtype: str,
    severity: str,
    producer: str,
    payloads: Mapping[str, Any],
    attributes: Mapping[str, Any] | None = None,
    correlations: Mapping[str, Any] | None = None,
    derivation: Mapping[str, Any] | None = None,
    event_root: str | Path | None = None,
    trigger_root: str | Path | None = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Atomically persist one event package and optionally notify the data loop."""

    normalized_type = _required_token(event_type, "event_type")
    normalized_subtype = _required_token(event_subtype, "event_subtype")
    normalized_severity = _required_token(severity, "severity")
    normalized_producer = _required_token(producer, "producer")
    root = _configured_path(event_root, "CHROMIE_RUNTIME_EVENT_ROOT", "CHROMIE_EVENT_ROOT")
    resolved_id = event_id or _event_id()
    timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
    if root is None:
        return _result(
            event_id=resolved_id,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            severity=normalized_severity,
            capture_status="not_configured",
            trigger_status="not_attempted",
            payload_root="",
            manifest_path="",
        )

    staging = root / ".staging" / resolved_id
    ready = root / "ready" / resolved_id
    try:
        staging.mkdir(parents=True, exist_ok=False)
        ready.parent.mkdir(parents=True, exist_ok=True)
        inventory: list[dict[str, str]] = []
        for name, payload in payloads.items():
            safe_name = _payload_name(name)
            _write_json(staging / safe_name, _json_safe(payload))
            inventory.append({"path": safe_name, "content_type": "application/json"})

        safe_attributes = _json_safe(dict(attributes or {}))
        safe_correlations = _json_safe(dict(correlations or {}))
        manifest = {
            "schema_version": RUNTIME_EVENT_SCHEMA_VERSION,
            "event_id": resolved_id,
            "event_type": normalized_type,
            "event_subtype": normalized_subtype,
            "severity": normalized_severity,
            "occurred_at": timestamp,
            "producer": {"name": normalized_producer},
            "fingerprint": event_fingerprint(
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                producer=normalized_producer,
                attributes=safe_attributes,
            ),
            "correlations": safe_correlations,
            "attributes": safe_attributes,
            "derivation": _json_safe(dict(derivation or {})),
            "files": inventory,
            "capture_status": "complete",
        }
        _write_json(staging / "event.json", manifest)
        _sync_directory(staging)
        os.replace(staging, ready)
        _sync_directory(ready.parent)

        trigger_status = _notify_data_loop(
            ready=ready,
            manifest=manifest,
            trigger_root=_configured_path(
                trigger_root,
                "CHROMIE_DATA_LOOP_TRIGGER_ROOT",
            ),
        )
        return _result(
            event_id=resolved_id,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            severity=normalized_severity,
            capture_status="complete",
            trigger_status=trigger_status,
            payload_root=str(ready),
            manifest_path=str(ready / "event.json"),
        )
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        result = _result(
            event_id=resolved_id,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            severity=normalized_severity,
            capture_status="failed",
            trigger_status="not_attempted",
            payload_root=str(ready),
            manifest_path=str(ready / "event.json"),
        )
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        return result


def event_fingerprint(
    *,
    event_type: str,
    event_subtype: str,
    producer: str,
    attributes: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "event_type": event_type,
        "event_subtype": event_subtype,
        "producer": producer,
        "attributes": _json_safe(dict(attributes or {})),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _notify_data_loop(*, ready: Path, manifest: Mapping[str, Any], trigger_root: Path | None) -> str:
    if trigger_root is None:
        return "not_configured"
    event_id = str(manifest["event_id"])
    payload = {
        "schema_version": RUNTIME_EVENT_TRIGGER_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": manifest["event_type"],
        "event_subtype": manifest["event_subtype"],
        "severity": manifest["severity"],
        "occurred_at": manifest["occurred_at"],
        "producer": manifest["producer"]["name"],
        "correlations": manifest.get("correlations") or {},
        "manifest_path": str(ready / "event.json"),
        "payload_root": str(ready),
        "payload_complete": True,
    }
    _atomic_write_json(trigger_root / f"{event_id}.json", payload)
    return "accepted"


def _result(**values: Any) -> dict[str, Any]:
    return dict(values)


def _required_token(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _payload_name(value: str) -> str:
    name = str(value or "").strip()
    if not name or Path(name).name != name or not name.endswith(".json"):
        raise ValueError(f"runtime event payload name must be a JSON basename: {value!r}")
    if name == "event.json":
        raise ValueError("event.json is reserved for the runtime-event manifest")
    return name


def _event_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"evt_{stamp}_{uuid.uuid4().hex[:12]}"


def _configured_path(value: str | Path | None, *env_names: str) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        for env_name in env_names:
            raw = str(os.getenv(env_name) or "").strip()
            if raw:
                break
    return Path(raw).expanduser().resolve() if raw else None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json", exclude_none=True))
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
