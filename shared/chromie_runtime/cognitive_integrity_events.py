"""Durable capture for critical cognitive-integrity failures.

Chromie owns classification, evidence organization, atomic local persistence,
and notification of an external data-loop inbox. The data-loop system owns
merging, deduplication, bandwidth/storage governance, and cloud delivery.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .runtime_events import persist_runtime_event
from .runtime_trace import runtime_tracer

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
    conversation_id = ""
    if isinstance(runtime_context, Mapping):
        experience = runtime_context.get("experience_context")
        if isinstance(experience, Mapping):
            conversation_id = str(experience.get("conversation_id") or "")
    subtype = f"llm_{failure_class}"
    trace_snapshot = runtime_tracer.current_snapshot()
    failure_payload = {
        **dict(failure),
        "retryable": False,
        "automatic_retry_allowed": False,
        "context_reduction_allowed": False,
        "result_trusted": False,
        "new_execution_allowed": False,
    }
    payloads = {
        "failure.json": failure_payload,
        "runtime.json": {
            "stage": stage,
            "session_id": session_id or "",
            "conversation_id": conversation_id,
            "language": language,
            "route_decision": route_decision,
            "runtime_context": runtime_context,
        },
        "model_exchange.json": model_exchange,
        "user_interaction.json": {
            "user_text": user_text,
            "user_text_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
            "notification_required": True,
            "execution_prevented": True,
        },
    }
    if trace_snapshot is not None:
        payloads["trace.json"] = trace_snapshot.trace
        payloads["trace-summary.json"] = trace_snapshot.summary

    return persist_runtime_event(
        event_type=EVENT_TYPE,
        event_subtype=subtype,
        severity="critical",
        producer="chromie.cognitive_runtime",
        event_root=event_root,
        trigger_root=trigger_root,
        correlations={
            "session_id": session_id or "",
            "conversation_id": conversation_id,
            "trace_id": (
                trace_snapshot.trace.get("trace_id")
                if trace_snapshot is not None
                else ""
            ),
        },
        attributes={
            "stage": stage,
            "failure_class": failure_class,
            "failure_domain": failure.get("failure_domain"),
            "purpose": failure.get("purpose"),
            "model": failure.get("model"),
            "done_reason": failure.get("done_reason"),
            "num_ctx": failure.get("num_ctx"),
            "num_predict": failure.get("num_predict"),
            "execution_prevented": True,
            "safe_state_requested": True,
            "trace_attached": trace_snapshot is not None,
        },
        derivation={
            "episode_correlation_supported": True,
            "scenario_candidate_eligible": True,
            "scenario_auto_promotion_allowed": False,
        },
        payloads=payloads,
    )

def cognitive_integrity_user_message(*, language: str, trigger_status: str) -> str:
    zh = language.lower().startswith("zh")
    handed = trigger_status == "accepted"
    if zh:
        suffix = "现场信息已经记录并交给诊断系统" if handed else "现场信息已经记录"
        return f"啊，我好像出故障了。为了安全，我没有继续处理，也没有执行刚才的操作。{suffix}，请联系工程或售后人员帮我检查一下。"
    suffix = "The incident data was recorded and handed to the diagnostic system." if handed else "The incident data was recorded."
    return f"I seem to have developed a fault. For safety, I stopped processing and did not execute the requested operation. {suffix} Please contact engineering or support."
