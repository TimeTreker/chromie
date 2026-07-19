"""Durable capture for critical cognitive-integrity failures.

Chromie owns classification, evidence organization, atomic local persistence,
and notification of an external data-loop inbox. The data-loop system owns
merging, deduplication, bandwidth/storage governance, and cloud delivery.
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

EVENT_TYPE = "chromie.cognitive_integrity_failure"
TRUNCATION_FAILURES = frozenset({"output_truncated", "prompt_truncated"})


def capture_cognitive_integrity_exception(*, stage: str, exc: Exception, request: Any) -> dict[str, Any]:
    failure = exc.metadata() if hasattr(exc, "metadata") and callable(exc.metadata) else {}
    if failure.get("failure_class") not in TRUNCATION_FAILURES:
        return {}
    evidence = (
        exc.incident_evidence()
        if hasattr(exc, "incident_evidence") and callable(exc.incident_evidence)
        else {}
    )
    route = getattr(request, "route_decision", None)
    if hasattr(route, "model_dump"):
        route = route.model_dump(mode="json", exclude_none=True)
    return capture_cognitive_integrity_event(
        stage=stage,
        failure=failure,
        session_id=getattr(request, "sid", None),
        user_text=str(getattr(request, "text", "") or ""),
        language=str(getattr(request, "language", "") or ""),
        route_decision=route or {},
        runtime_context=getattr(request, "context", {}) or {},
        model_exchange=evidence,
    )


def cognitive_integrity_metadata(*, stage: str, exc: Exception, request: Any) -> dict[str, Any]:
    incident = capture_cognitive_integrity_exception(stage=stage, exc=exc, request=request)
    if not incident:
        return {}
    return {
        "incident": incident,
        "user_notification_required": True,
        "user_notification": cognitive_integrity_user_message(
            language=str(getattr(request, "language", "") or ""),
            trigger_status=str(incident.get("trigger_status") or ""),
        ),
        "execution_prevented": True,
    }


def capture_cognitive_integrity_event(
    *,
    stage: str,
    failure: Mapping[str, Any],
    session_id: str | None,
    user_text: str,
    language: str,
    route_decision: Any,
    runtime_context: Any,
    model_exchange: Any,
    event_root: str | Path | None = None,
    trigger_root: str | Path | None = None,
) -> dict[str, Any]:
    failure_class = str(failure.get("failure_class") or "")
    if failure_class not in TRUNCATION_FAILURES:
        return {}
    root = _path(event_root, "CHROMIE_EVENT_ROOT")
    subtype = f"llm_{failure_class}"
    if root is None:
        return _result("", subtype, "not_configured", "not_attempted", "", "")

    event_id = _event_id()
    staging = root / ".staging" / event_id
    ready = root / "ready" / event_id
    occurred_at = datetime.now(timezone.utc).isoformat()
    try:
        staging.mkdir(parents=True, exist_ok=False)
        ready.parent.mkdir(parents=True, exist_ok=True)
        conversation_id = ""
        if isinstance(runtime_context, Mapping):
            experience = runtime_context.get("experience_context")
            if isinstance(experience, Mapping):
                conversation_id = str(experience.get("conversation_id") or "")

        files = {
            "failure.json": {
                **_safe(dict(failure)),
                "retryable": False,
                "automatic_retry_allowed": False,
                "context_reduction_allowed": False,
                "result_trusted": False,
                "new_execution_allowed": False,
            },
            "runtime.json": {
                "stage": stage,
                "session_id": session_id or "",
                "conversation_id": conversation_id,
                "language": language,
                "route_decision": _safe(route_decision),
                "runtime_context": _safe(runtime_context),
            },
            "model_exchange.json": _safe(model_exchange),
            "user_interaction.json": {
                "user_text": user_text,
                "user_text_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
                "notification_required": True,
                "execution_prevented": True,
            },
        }
        for name, payload in files.items():
            _write_json(staging / name, payload)

        manifest = {
            "schema_version": 1,
            "event_id": event_id,
            "event_type": EVENT_TYPE,
            "event_subtype": subtype,
            "severity": "critical",
            "occurred_at": occurred_at,
            "producer": {"name": "chromie"},
            "stage": stage,
            "session_id": session_id or "",
            "conversation_id": conversation_id,
            "fingerprint": _fingerprint(stage, failure),
            "integrity_policy": {
                "result_trusted": False,
                "automatic_retry_allowed": False,
                "context_reduction_allowed": False,
                "new_execution_allowed": False,
                "operator_attention_required": True,
            },
            "execution": {"execution_prevented": True, "safe_state_requested": True},
            "derivation": {
                "episode_correlation_supported": True,
                "scenario_candidate_eligible": True,
                "scenario_auto_promotion_allowed": False,
            },
            "files": [{"path": name, "content_type": "application/json"} for name in files],
            "capture_status": "complete",
        }
        _write_json(staging / "event.json", manifest)
        _sync_dir(staging)
        os.replace(staging, ready)
        _sync_dir(ready.parent)
        trigger_status = _trigger(
            ready=ready,
            event_id=event_id,
            subtype=subtype,
            occurred_at=occurred_at,
            trigger_root=_path(trigger_root, "CHROMIE_DATA_LOOP_TRIGGER_ROOT"),
        )
        return _result(event_id, subtype, "complete", trigger_status, str(ready), str(ready / "event.json"))
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        result = _result(event_id, subtype, "failed", "not_attempted", str(ready), str(ready / "event.json"))
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        return result


def cognitive_integrity_user_message(*, language: str, trigger_status: str) -> str:
    zh = language.lower().startswith("zh")
    handed = trigger_status == "accepted"
    if zh:
        suffix = "现场信息已经记录并交给诊断系统" if handed else "现场信息已经记录"
        return f"啊，我好像出故障了。为了安全，我没有继续处理，也没有执行刚才的操作。{suffix}，请联系工程或售后人员帮我检查一下。"
    suffix = "The incident data was recorded and handed to the diagnostic system." if handed else "The incident data was recorded."
    return f"I seem to have developed a fault. For safety, I stopped processing and did not execute the requested operation. {suffix} Please contact engineering or support."


def _trigger(*, ready: Path, event_id: str, subtype: str, occurred_at: str, trigger_root: Path | None) -> str:
    if trigger_root is None:
        return "not_configured"
    payload = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": EVENT_TYPE,
        "event_subtype": subtype,
        "severity": "critical",
        "occurred_at": occurred_at,
        "producer": "chromie",
        "manifest_path": str(ready / "event.json"),
        "payload_root": str(ready),
        "payload_complete": True,
    }
    _atomic_json(trigger_root / f"{event_id}.json", payload)
    return "accepted"


def _result(event_id: str, subtype: str, capture: str, trigger: str, root: str, manifest: str) -> dict[str, Any]:
    return {"event_id": event_id, "event_type": EVENT_TYPE, "event_subtype": subtype, "severity": "critical", "capture_status": capture, "trigger_status": trigger, "payload_root": root, "manifest_path": manifest}


def _event_id() -> str:
    return f"evt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:12]}"


def _fingerprint(stage: str, failure: Mapping[str, Any]) -> str:
    keys = ("failure_class", "failure_domain", "purpose", "model", "done_reason", "num_ctx", "num_predict")
    payload = {"stage": stage, **{key: failure.get(key) for key in keys}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _path(value: str | Path | None, env: str) -> Path | None:
    raw = str(value or os.getenv(env) or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        return _safe(value.model_dump(mode="json", exclude_none=True))
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _sync_dir(path.parent)
    finally:
        tmp_path.unlink(missing_ok=True)


def _sync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
