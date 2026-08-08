"""Versioned, durable runtime-event packages for Chromie producers.

A runtime event is an immutable local evidence package. Chromie producers own
classification and payload construction. The external data loop owns merging,
deduplication, bandwidth/storage governance, retention, and cloud delivery.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .settings import RuntimePolicySettings

RUNTIME_EVENT_SCHEMA_VERSION = 1
RUNTIME_EVENT_TRIGGER_SCHEMA_VERSION = 1

logger = logging.getLogger("chromie.runtime.runtime_events")


@dataclass(frozen=True)
class RuntimeEventArtifact:
    """One immutable non-JSON artifact supplied by an evidence provider."""

    source: bytes | Path
    content_type: str = "application/octet-stream"


def persist_runtime_event(
    *,
    event_type: str,
    event_subtype: str,
    severity: str,
    producer: str,
    payloads: Mapping[str, Any],
    artifacts: Mapping[str, RuntimeEventArtifact] | None = None,
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
    settings = RuntimePolicySettings.from_env()
    root = settings.configured_path(
        event_root, "runtime_event_root", "legacy_event_root"
    )
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
    existing = _existing_event_result(
        ready=ready,
        event_id=resolved_id,
        event_type=normalized_type,
        event_subtype=normalized_subtype,
        producer=normalized_producer,
        trigger_root=settings.configured_path(
            trigger_root,
            "data_loop_trigger_root",
        ),
    )
    if existing is not None:
        return existing
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=False)
        ready.parent.mkdir(parents=True, exist_ok=True)
        inventory: list[dict[str, Any]] = []
        for name, payload in payloads.items():
            safe_name = _payload_name(name)
            target = staging / safe_name
            _write_json(target, _json_safe(payload))
            inventory.append(
                _artifact_inventory(
                    target,
                    path=safe_name,
                    content_type="application/json",
                )
            )
        for name, artifact in (artifacts or {}).items():
            safe_name = _artifact_name(name)
            target = staging / safe_name
            _write_artifact(target, artifact)
            inventory.append(
                _artifact_inventory(
                    target,
                    path=safe_name,
                    content_type=artifact.content_type,
                )
            )

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
        result = _result(
            event_id=resolved_id,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            severity=normalized_severity,
            capture_status="complete",
            trigger_status="not_attempted",
            payload_root=str(ready),
            manifest_path=str(ready / "event.json"),
        )
        try:
            result["trigger_status"] = _notify_data_loop(
                ready=ready,
                manifest=manifest,
                trigger_root=settings.configured_path(
                    trigger_root,
                    "data_loop_trigger_root",
                ),
            )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            # The immutable evidence is already committed. A notification or
            # downstream evaluator outage must not relabel it as uncaptured.
            result["trigger_status"] = "failed"
            result["trigger_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.warning(
                "Runtime Event trigger notification failed event_id=%s "
                "error_type=%s error=%s",
                resolved_id,
                type(exc).__name__,
                exc,
            )
        return result
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


def _artifact_name(value: str) -> str:
    name = str(value or "").strip()
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError(f"runtime event artifact name must be a basename: {value!r}")
    if name == "event.json":
        raise ValueError("event.json is reserved for the runtime-event manifest")
    return name


def _event_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"evt_{stamp}_{uuid.uuid4().hex[:12]}"



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


def _write_artifact(path: Path, artifact: RuntimeEventArtifact) -> None:
    source = artifact.source
    if isinstance(source, Path):
        if not source.is_file():
            raise ValueError(f"runtime event artifact source is not a file: {source}")
        try:
            os.link(source, path)
        except OSError:
            shutil.copyfile(source, path)
    elif isinstance(source, bytes):
        with path.open("xb") as handle:
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        raise TypeError("RuntimeEventArtifact.source must be bytes or Path")


def _artifact_inventory(
    file_path: Path,
    *,
    path: str,
    content_type: str,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    sha256 = digest.hexdigest()
    return {
        "artifact_id": f"artifact_sha256_{sha256}",
        "path": path,
        "content_type": str(content_type or "application/octet-stream"),
        "size_bytes": size,
        "sha256": sha256,
    }


def _existing_event_result(
    *,
    ready: Path,
    event_id: str,
    event_type: str,
    event_subtype: str,
    producer: str,
    trigger_root: Path | None,
) -> dict[str, Any] | None:
    manifest_path = ready / "event.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("event_id") != event_id
            or manifest.get("event_type") != event_type
            or manifest.get("event_subtype") != event_subtype
            or (manifest.get("producer") or {}).get("name") != producer
        ):
            raise ValueError("existing runtime event identity does not match retry")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _result(
            event_id=event_id,
            event_type=event_type,
            event_subtype=event_subtype,
            severity="error",
            capture_status="failed",
            trigger_status="not_attempted",
            payload_root=str(ready),
            manifest_path=str(manifest_path),
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
        )
    result = _result(
        event_id=event_id,
        event_type=event_type,
        event_subtype=event_subtype,
        severity=str(manifest.get("severity") or "info"),
        capture_status="complete",
        trigger_status="not_attempted",
        payload_root=str(ready),
        manifest_path=str(manifest_path),
        idempotent_reuse=True,
    )
    try:
        result["trigger_status"] = _notify_data_loop(
            ready=ready,
            manifest=manifest,
            trigger_root=trigger_root,
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result["trigger_status"] = "failed"
        result["trigger_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        logger.warning(
            "Runtime Event retry notification failed event_id=%s "
            "error_type=%s error=%s",
            event_id,
            type(exc).__name__,
            exc,
        )
    return result


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
