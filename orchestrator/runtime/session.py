from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_runtime.log_colors import colorize_for_cli
from shared.chromie_runtime.resource_sampling import (
    RESOURCE_SAMPLE_MODULE,
    SystemResourceSampler,
)
from shared.chromie_runtime.runtime_events import persist_runtime_event
from shared.chromie_runtime.runtime_trace import (
    RuntimeTrace,
    TraceCheckpointStore,
    TraceModule,
    TracePolicy,
    TraceScope,
    runtime_tracer,
)

from .interaction_session_evidence import (
    InteractionSessionCapturePolicySnapshot,
    InteractionSessionEvidenceCollector,
)

logger = logging.getLogger(__name__)


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def summarize_provider_start_evidence(
    response: InteractionResponse,
    execution: Any | None = None,
) -> dict[str, int | bool]:
    """Separate requested-Work dispatch from ordinary speech delivery."""

    requested_ids = {
        request.request_id
        for request in response.capabilities
        if request.capability_id != "chromie.speak"
    }
    speech_ids = {speech.id for speech in response.speech} | {
        request.request_id
        for request in response.capabilities
        if request.capability_id == "chromie.speak"
    }
    started = [
        trace
        for trace in list(getattr(execution, "traces", ()) or ())
        if any(event.type == "started" for event in trace.events)
    ]
    return {
        "requested_work_request_count": len(requested_ids),
        "speech_delivery_request_count": len(speech_ids),
        "requested_work_provider_start_observed": any(
            trace.request_id in requested_ids for trace in started
        ),
        "speech_delivery_provider_start_observed": any(
            trace.request_id in speech_ids or trace.capability_id == "chromie.speak"
            for trace in started
        ),
        "any_provider_start_observed": bool(started),
    }


def record_session_workflow_stage(
    host: Any,
    session_id: str | None,
    **stage: Any,
) -> None:
    """Retain optional workflow evidence without changing runtime behavior."""

    sessions = getattr(host, "sessions", None)
    recorder = getattr(sessions, "record_cognitive_stage", None)
    if not callable(recorder):
        return
    try:
        recorder(session_id, **stage)
    except Exception as exc:
        logger.warning(
            "Could not retain session workflow stage %s: %s",
            stage.get("stage", "unknown"),
            exc,
        )


class SessionEventWriter:
    """Append session events as JSON Lines for acceptance evidence.

    The writer is intentionally dependency-free and best-effort: evidence
    capture must never crash the realtime voice loop. The path is supplied by
    ``ORCH_EVENT_LOG_PATH`` or directly in tests/embedding code.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        raw = str(path or os.getenv("ORCH_EVENT_LOG_PATH", "")).strip()
        self.path = Path(raw).expanduser().resolve() if raw else None
        self._lock = threading.Lock()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        sid: str,
        elapsed_ms: float,
        message: str,
        args: tuple[Any, ...],
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.path is None:
            return
        try:
            rendered = message % args if args else message
        except Exception:
            rendered = f"{message} args={args!r}"
        event_name = rendered.split(":", 1)[0].strip() or "session_event"
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "elapsed_ms": round(float(elapsed_ms), 3),
            "event": event_name,
            "message": rendered,
        }
        if extra:
            record.update(extra)
        try:
            with self._lock:
                with self.path.open("a", encoding="utf-8") as handle:
                    json.dump(record, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
        except Exception as exc:  # evidence capture must not break runtime
            logger.warning("Could not append session event evidence: %s", exc)


class SessionTracker:
    TRACE_MODULE = TraceModule(
        name="orchestrator.session",
        component_type="session",
        implementation="SessionTracker",
    )

    _WORKFLOW_EVENT_PREFIXES = (
        "session_start",
        "session_interrupted_by_new_session",
        "vad_valid_end",
        "asr_send_start",
        "asr_send_done",
        "asr_final",
        "asr_error",
        "asr_exception",
        "context_snapshot",
        "cognitive_gateway_attention_done",
        "cognitive_core_start",
        "cognitive_core_done",
        "cognitive_core_exception",
        "goal_interpretation_start",
        "goal_interpretation_done",
        "fast_first_response_schedule",
        "fast_first_response_scheduled",
        "fast_first_response_skipped",
        "fast_first_audio_hedge_started",
        "fast_first_audio_schedule",
        "fast_first_audio_suppressed",
        "playback_cancel_before_start",
        "playback_skip_cancelled",
        "routed_turn_cancellation_requested",
        "turn_cancelled",
        "agent_start",
        "interaction_done",
        "cognitive_interaction_ready",
        "cognitive_capability_proposed",
        "capability_runtime_done",
        "capability_result",
        "soridormi_post_status",
        "soridormi_post_status_failed",
        "experience_recorded",
        "episode_recorded",
        "tts_text_split",
        "tts_schedule",
        "tts_request_start",
        "tts_stream_start",
        "tts_first_provider_pcm",
        "tts_stream_end",
        "tts_server_metrics",
        "tts_stream_failed",
        "tts_playback_start_waiter_resolved",
        "playback_start",
        "playback_end",
        "playback_stream_incomplete",
        "session_idle_timeout",
        "session_done",
    )

    def __init__(
        self,
        enabled: bool = True,
        *,
        event_log_path: str | os.PathLike[str] | None = None,
        workflow_report_root: str | os.PathLike[str] | None = None,
        workflow_report_include_text: bool = False,
        resource_sampling_mode: str | None = None,
        interaction_session_capture: InteractionSessionEvidenceCollector | None = None,
    ):
        self.enabled = enabled
        self.current_sid: str | None = None
        self.state: dict[str, dict[str, Any]] = {}
        self.event_writer = SessionEventWriter(event_log_path)
        self.workflow_report_root = (
            Path(workflow_report_root).expanduser().resolve()
            if workflow_report_root
            else None
        )
        self.workflow_report_include_text = bool(workflow_report_include_text)
        self._workflow_report_lock = threading.Lock()
        self.resource_sampler = (
            SystemResourceSampler(resource_sampling_mode)
            if resource_sampling_mode is not None
            else SystemResourceSampler.from_env()
        )
        self.external_resource_snapshot_providers: list[
            tuple[TraceModule, str, Callable[..., dict[str, Any]]]
        ] = []
        self.interaction_session_capture = interaction_session_capture
        self.checkpoint_store = TraceCheckpointStore()
        self.recovered_runtime_traces = self._recover_abandoned_runtime_traces()

    def create(self) -> str:
        previous = self.current_sid
        sid = str(uuid.uuid4())[:8]
        self.current_sid = sid
        capture_policy = (
            self.interaction_session_capture.begin_session(sid)
            if self.interaction_session_capture is not None
            else None
        )
        self.state[sid] = {
            "t0_ms": now_ms(),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "last_activity_ms": now_ms(),
            "scheduled_tts": 0,
            "queued_tts": 0,
            "played_tts": 0,
            "failed_tts": 0,
            "skipped_tts": 0,
            "llm_done": False,
            "done_logged": False,
            "flow_summary_logged": False,
            "response_chars": 0,
            "interrupted": False,
            "workflow_events": [],
            "cognitive_workflow_stages": [],
            "correlations": {"session_id": sid},
            "runtime_trace": self._create_runtime_trace(sid, capture_policy),
            "runtime_trace_event": {},
            "interaction_session_capture_policy": (
                capture_policy.model_dump(mode="json", exclude_none=True)
                if capture_policy is not None
                else {}
            ),
        }
        if previous and previous != sid:
            prev = self.state.get(previous)
            if prev and not prev.get("done_logged"):
                prev["interrupted"] = True
                self.log(previous, "session_interrupted_by_new_session: new_sid=%s", sid)
                self._log_session_flow_summary(previous, termination_state="abandoned")
                self._finalize_runtime_trace(previous, state="abandoned")
        self.log(sid, "session_start")
        self.trace_mark(sid, "session_started", kind="session", attributes={"sid": sid})
        self.sample_resources(sid, reason="session_start")
        self._record_external_resource_snapshots(sid, reason="session_start")
        self._checkpoint_runtime_trace(sid)
        return sid

    def _create_runtime_trace(
        self,
        sid: str,
        capture_policy: InteractionSessionCapturePolicySnapshot | None = None,
    ) -> RuntimeTrace | None:
        policy = TracePolicy.from_env()
        if (
            policy.mode == "off"
            and capture_policy is not None
            and capture_policy.enabled
            and capture_policy.evidence.runtime_trace
        ):
            policy = TracePolicy.from_env(mode="basic")
        if policy.mode == "off":
            return None
        return RuntimeTrace(
            policy=policy,
            correlations={"session_id": sid},
            attributes={"trace_scope": "voice_session"},
            sampling_reason="session_lifecycle",
        )

    def trace_context(self, sid: str | None) -> TraceScope:
        state = self.state.get(sid or "") or {}
        trace = state.get("runtime_trace")
        return runtime_tracer.activate(trace if isinstance(trace, RuntimeTrace) else None)

    def update_trace_correlations(self, sid: str | None, **values: Any) -> None:
        session = self.state.get(sid or "") or {}
        correlations = session.setdefault("correlations", {})
        if isinstance(correlations, dict):
            correlations.update(
                {
                    str(key): value
                    for key, value in values.items()
                    if value not in (None, "")
                }
            )
        trace = session.get("runtime_trace")
        if not isinstance(trace, RuntimeTrace) or session.get("runtime_trace_finalized"):
            return
        trace.update_correlations(values)
        self._checkpoint_runtime_trace(str(sid or ""))

    def capture_input_audio(
        self,
        sid: str | None,
        audio: bytes,
        *,
        sample_rate_hz: int,
        channels: int,
    ) -> dict[str, Any] | None:
        if self.interaction_session_capture is None or not sid:
            return None
        return self.interaction_session_capture.capture_input_audio(
            sid,
            audio,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
        )

    def attach_episode_evidence(
        self,
        sid: str | None,
        episode: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.interaction_session_capture is None or not sid:
            return None
        return self.interaction_session_capture.attach_episode_evidence(
            sid,
            episode,
        )

    def interaction_session_capture_reference(
        self,
        sid: str | None,
    ) -> dict[str, Any] | None:
        if self.interaction_session_capture is None or not sid:
            return None
        return self.interaction_session_capture.session_reference(sid)

    def sample_resources(
        self,
        sid: str | None,
        *,
        reason: str,
        event_loop_lag_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str | None:
        payload = self.resource_sampler.sample(
            reason=reason,
            event_loop_lag_ms=event_loop_lag_ms,
            attributes=attributes,
        )
        if not payload:
            return None
        return self.record_resource_sample(
            sid,
            module=RESOURCE_SAMPLE_MODULE,
            name="runtime_resource_sample",
            attributes=payload,
        )

    def register_resource_snapshot_provider(
        self,
        *,
        module: TraceModule,
        name: str,
        provider: Callable[..., dict[str, Any]],
    ) -> None:
        """Register a non-blocking cached resource snapshot provider.

        Providers are invoked synchronously only for their latest cached value;
        they must not perform I/O, subprocess work, or network access here.
        """

        self.external_resource_snapshot_providers.append((module, str(name), provider))

    def record_resource_sample(
        self,
        sid: str | None,
        *,
        module: TraceModule,
        name: str,
        attributes: dict[str, Any],
    ) -> str | None:
        if not attributes:
            return None
        with self.trace_context(sid):
            item_id = runtime_tracer.mark(
                module=module,
                name=name,
                kind="resource_sample",
                attributes=attributes,
            )
        self._checkpoint_runtime_trace(str(sid or ""))
        return item_id

    def record_active_resource_sample(
        self,
        *,
        module: TraceModule,
        name: str,
        attributes: dict[str, Any],
    ) -> list[str]:
        recorded: list[str] = []
        for sid, session in list(self.state.items()):
            if session.get("runtime_trace_finalized"):
                continue
            if self.record_resource_sample(
                sid,
                module=module,
                name=name,
                attributes=attributes,
            ):
                recorded.append(sid)
        return recorded

    def _record_external_resource_snapshots(self, sid: str, *, reason: str) -> None:
        for module, name, provider in self.external_resource_snapshot_providers:
            try:
                payload = provider(reason=reason)
            except Exception as exc:
                logger.debug(
                    "Cached resource snapshot provider failed: module=%s error=%s",
                    module.name,
                    type(exc).__name__,
                )
                continue
            if payload:
                self.record_resource_sample(
                    sid,
                    module=module,
                    name=name,
                    attributes=payload,
                )

    def sample_active_resources(
        self,
        *,
        event_loop_lag_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> list[str]:
        sampled: list[str] = []
        for sid, session in list(self.state.items()):
            if session.get("runtime_trace_finalized"):
                continue
            if self.sample_resources(
                sid,
                reason="periodic",
                event_loop_lag_ms=event_loop_lag_ms,
                attributes=attributes,
            ):
                sampled.append(sid)
        return sampled

    def trace_mark(
        self,
        sid: str | None,
        name: str,
        *,
        kind: str = "event",
        attributes: dict[str, Any] | None = None,
    ) -> str | None:
        with self.trace_context(sid):
            item_id = runtime_tracer.mark(
                module=self.TRACE_MODULE,
                name=name,
                kind=kind,
                attributes=attributes,
            )
        self._checkpoint_runtime_trace(str(sid or ""))
        return item_id

    def _checkpoint_runtime_trace(self, sid: str) -> str:
        session = self.state.get(sid) or {}
        trace = session.get("runtime_trace")
        if (
            not self.checkpoint_store.enabled
            or not isinstance(trace, RuntimeTrace)
            or session.get("runtime_trace_finalized")
        ):
            return ""
        path = self.checkpoint_store.write(trace.snapshot(state="active"))
        if path:
            session["runtime_trace_checkpoint"] = path
        return path

    def checkpoint_active_traces(self) -> list[str]:
        checkpointed: list[str] = []
        for sid in list(self.state):
            if self._checkpoint_runtime_trace(sid):
                checkpointed.append(sid)
        return checkpointed

    def _recover_abandoned_runtime_traces(self) -> list[dict[str, Any]]:
        recovered: list[dict[str, Any]] = []
        if not self.checkpoint_store.enabled:
            return recovered
        policy = TracePolicy.from_env()
        recovered_at = datetime.now(timezone.utc).isoformat()
        for path, payload in self.checkpoint_store.pending():
            trace = dict(payload.get("trace") or {})
            summary = dict(payload.get("summary") or {})
            checkpointed_at = str(payload.get("checkpointed_at") or recovered_at)
            trace["state"] = "abandoned"
            trace["finished_at"] = checkpointed_at
            trace_attributes = dict(trace.get("attributes") or {})
            trace_attributes.update(
                {
                    "recovery_reason": "process_restart",
                    "recovered_from_checkpoint": True,
                    "recovery_detected_at": recovered_at,
                }
            )
            trace["attributes"] = trace_attributes
            collection = dict(trace.get("collection") or {})
            collection["checkpoint_recovered"] = True
            trace["collection"] = collection
            summary["status"] = "abandoned"
            result: dict[str, Any] = {
                "trace_id": trace.get("trace_id"),
                "checkpoint_path": str(path),
                "event": {},
            }
            if policy.emit_events:
                result["event"] = persist_runtime_event(
                    event_type="chromie.interaction_trace",
                    event_subtype="voice_session_restart_recovery",
                    severity="warning",
                    producer="chromie.orchestrator.session",
                    payloads={
                        "trace.json": trace,
                        "trace-summary.json": summary,
                    },
                    attributes={
                        "trace_state": "abandoned",
                        "retention_reason": "process_restart_recovery",
                        "checkpointed_at": checkpointed_at,
                    },
                    correlations=trace.get("correlations") or {},
                    derivation={
                        "latency_analysis_supported": True,
                        "scenario_candidate_eligible": True,
                        "scenario_auto_promotion_allowed": False,
                    },
                )
            result["archive_path"] = self.checkpoint_store.archive(path)
            recovered.append(result)
        return recovered

    def _finalize_runtime_trace(self, sid: str, *, state: str) -> None:
        session = self.state.get(sid)
        if not session or session.get("runtime_trace_finalized"):
            return
        self._finalize_workflow_report(
            sid,
            termination_state=("abandoned" if state == "abandoned" else "complete"),
        )
        # Lifecycle finalization is required even when runtime tracing is off.
        # Previously a session without a RuntimeTrace stayed perpetually
        # unfinished and the idle sweeper logged the same timeout every cycle.
        session["runtime_trace_finalized"] = True
        trace = session.get("runtime_trace")
        snapshot = None
        if not isinstance(trace, RuntimeTrace):
            session["runtime_trace_snapshot"] = None
        else:
            self.sample_resources(
                sid,
                reason=(
                    "session_abandoned" if state == "abandoned" else "session_finish"
                ),
            )
            self._record_external_resource_snapshots(
                sid,
                reason=(
                    "session_abandoned" if state == "abandoned" else "session_finish"
                ),
            )
            snapshot = trace.finish(state=state)
            session["runtime_trace_snapshot"] = snapshot
            retention = trace.policy.retention_decision(snapshot)
            session["runtime_trace_retention"] = retention.as_dict()
            if retention.emit:
                session["runtime_trace_event"] = runtime_tracer.persist_snapshot(
                    snapshot,
                    event_subtype="voice_session",
                    producer="chromie.orchestrator",
                    severity=retention.severity,
                    retention_reason=retention.reason,
                )
            self.checkpoint_store.remove(trace.trace_id)
        if self.interaction_session_capture is not None:
            capture_event = self.interaction_session_capture.seal_session(
                sid,
                termination_state=(
                    "abandoned" if state == "abandoned" else "complete"
                ),
                trace_snapshot=snapshot,
            )
            if capture_event.get("capture_status") != "not_requested":
                session["interaction_session_capture_event"] = capture_event

    def elapsed_ms(self, sid: str | None) -> float:
        state = self.state.get(sid or "")
        return 0.0 if not state else now_ms() - float(state["t0_ms"])

    def log(self, sid: str | None, message: str, *args: Any) -> None:
        sid = sid or "unknown"
        state = self.state.get(sid)
        if state is not None:
            state["last_activity_ms"] = now_ms()
        if not self.enabled:
            return
        elapsed = self.elapsed_ms(sid)
        rendered = self._render_message(message, args)
        level = self._event_log_level(rendered)
        severity = logging.getLevelName(level).lower()
        self._remember_workflow_event(sid, rendered, severity=severity)
        self.event_writer.write(
            sid=sid,
            elapsed_ms=elapsed,
            message=message,
            args=args,
            extra={"severity": severity},
        )
        line = self._colorize_for_cli(f"[SID:{sid} +{elapsed:.1f}ms] {rendered}", level)
        logger.log(level, "%s", line)

    def maybe_done(self, sid: str | None) -> None:
        if not sid:
            return
        s = self.state.get(sid)
        if not s or s.get("done_logged") or s.get("interrupted"):
            return
        scheduled = int(s.get("scheduled_tts", 0))
        played = int(s.get("played_tts", 0))
        failed = int(s.get("failed_tts", 0))
        skipped = int(s.get("skipped_tts", 0))
        if s.get("llm_done") and scheduled == played + failed + skipped:
            s["done_logged"] = True
            self.log(
                sid,
                "session_done: scheduled_tts=%s queued_tts=%s played_tts=%s failed_tts=%s skipped_tts=%s response_chars=%s total_ms=%.1f",
                scheduled,
                s.get("queued_tts", 0),
                played,
                failed,
                skipped,
                s.get("response_chars", 0),
                self.elapsed_ms(sid),
            )
            self._log_session_flow_summary(sid, termination_state="complete")
            workflow = self._workflow_summary(sid)
            if workflow:
                self.event_writer.write(
                    sid=sid,
                    elapsed_ms=self.elapsed_ms(sid),
                    message="session_workflow: %s",
                    args=(workflow,),
                )
            graph = self._workflow_graph(sid)
            if graph:
                self._emit_workflow_graph(sid, graph)
                summary = self._workflow_timing_summary(graph)
                if summary:
                    self.log(sid, "session_workflow_summary: %s", summary)
            self._finalize_workflow_report(sid, termination_state="complete")
            self.trace_mark(
                sid,
                "session_finished",
                kind="session",
                attributes={
                    "scheduled_tts": scheduled,
                    "played_tts": played,
                    "failed_tts": failed,
                    "skipped_tts": skipped,
                    "response_chars": int(s.get("response_chars", 0)),
                },
            )
            self._finalize_runtime_trace(sid, state="complete")

    def finalize_active_sessions(self, *, reason: str) -> list[str]:
        finalized: list[str] = []
        for sid, session in list(self.state.items()):
            if session.get("runtime_trace_finalized"):
                continue
            session["interrupted"] = True
            self.trace_mark(
                sid,
                "session_abandoned",
                kind="session",
                attributes={"reason": str(reason or "shutdown")},
            )
            self._log_session_flow_summary(sid, termination_state="abandoned")
            self._finalize_runtime_trace(sid, state="abandoned")
            finalized.append(sid)
        return finalized

    def finalize_idle_sessions(
        self,
        *,
        idle_timeout_ms: float,
        now_ms_value: float | None = None,
    ) -> list[str]:
        """Finalize unfinished sessions whose activity has exceeded the idle limit."""

        current = now_ms() if now_ms_value is None else float(now_ms_value)
        finalized: list[str] = []
        for sid, session in list(self.state.items()):
            if session.get("done_logged") or session.get("runtime_trace_finalized"):
                continue
            last_activity = float(session.get("last_activity_ms", session.get("t0_ms", current)))
            if current - last_activity < float(idle_timeout_ms):
                continue
            session["interrupted"] = True
            self.log(
                sid,
                "session_idle_timeout: idle_ms=%.1f timeout_ms=%.1f",
                current - last_activity,
                idle_timeout_ms,
            )
            self.trace_mark(
                sid,
                "session_idle_timeout",
                kind="session",
                attributes={
                    "idle_ms": round(current - last_activity, 3),
                    "timeout_ms": round(float(idle_timeout_ms), 3),
                },
            )
            self._log_session_flow_summary(sid, termination_state="abandoned")
            self._finalize_runtime_trace(sid, state="abandoned")
            finalized.append(sid)
        return finalized

    def _render_message(self, message: str, args: tuple[Any, ...]) -> str:
        try:
            return message % args if args else message
        except Exception:
            return f"{message} args={args!r}"

    def _remember_workflow_event(self, sid: str, rendered: str, *, severity: str) -> None:
        if rendered.startswith("session_workflow"):
            return
        state = self.state.get(sid)
        if not state:
            return
        state["last_activity_ms"] = now_ms()
        event_name = rendered.split(":", 1)[0].strip()
        if event_name not in self._WORKFLOW_EVENT_PREFIXES:
            return
        workflow_events = state.setdefault("workflow_events", [])
        if not isinstance(workflow_events, list):
            workflow_events = []
            state["workflow_events"] = workflow_events
        workflow_events.append(
            {
                "event": event_name,
                "elapsed_ms": round(self.elapsed_ms(sid), 3),
                "message": self._compact_workflow_message(rendered),
                "severity": severity,
            }
        )

    def _event_log_level(self, rendered: str) -> int:
        event_name = rendered.split(":", 1)[0].strip()
        lowered = rendered.casefold()

        if event_name in {"tts_stream_failed", "llm_prompt_truncated", "llm_output_truncated"}:
            return logging.ERROR
        if any(
            token in lowered
            for token in (
                "exception",
                "traceback",
                " error=",
                " error_type=",
                "done_reason=length",
                "finish_reason=length",
                "num_predict_exhausted",
                "prompt_eval_count_reached_num_ctx",
            )
        ):
            return logging.ERROR
        if any(token in event_name for token in ("failed", "failure", "error")):
            return logging.ERROR
        if event_name in {"llm_prompt_context_pressure", "llm_output_budget_pressure"}:
            return logging.WARNING

        if event_name == "capability_result":
            status = self._field_value(rendered, "status").casefold()
            if status and status not in {"completed", "ok", "success"}:
                if status in {"cancelled", "canceled", "skipped", "ignored"}:
                    return logging.WARNING
                return logging.ERROR

        if event_name == "capability_runtime_done":
            status = self._field_value(rendered, "status").casefold()
            if status and status not in {"completed", "ok", "success"}:
                if status in {"cancelled", "canceled", "interrupted"}:
                    return logging.WARNING
                return logging.ERROR

        if event_name == "session_done":
            if self._int_field_value(rendered, "failed_tts") > 0:
                return logging.ERROR
            if self._int_field_value(rendered, "skipped_tts") > 0:
                return logging.WARNING
            if (
                self._int_field_value(rendered, "scheduled_tts") == 0
                and self._int_field_value(rendered, "response_chars") == 0
            ):
                return logging.WARNING

        if event_name == "tts_playback_start_waiter_resolved" and self._field_value(rendered, "started").casefold() == "false":
            return logging.WARNING

        if event_name == "goal_interpretation_done":
            route = self._field_value(rendered, "route").casefold()
            intent = self._field_value(rendered, "intent").casefold()
            if route == "robot_action" and intent == "capability:chromie.speak":
                return logging.WARNING

        if any(token in lowered for token in ("status=blocked", "status=rejected", "status=timeout")):
            return logging.WARNING
        return logging.INFO

    @staticmethod
    def _field_value(rendered: str, key: str) -> str:
        match = re.search(rf"(?:^|\s){re.escape(key)}=([^\s]+)", rendered)
        if not match:
            return ""
        return match.group(1).strip().strip("'\"")

    @classmethod
    def _int_field_value(cls, rendered: str, key: str) -> int:
        try:
            return int(float(cls._field_value(rendered, key)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _colorize_for_cli(line: str, level: int) -> str:
        return colorize_for_cli(line, level, env_var="ORCH_CLI_COLOR")

    def _compact_workflow_message(self, rendered: str, *, limit: int = 320) -> str:
        text = " ".join(rendered.split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _flow_duration_text(duration_ms: float) -> str:
        duration_ms = max(0.0, float(duration_ms))
        return (
            f"{duration_ms:.1f}ms"
            if duration_ms < 1000.0
            else f"{duration_ms / 1000.0:.2f}s"
        )

    def _session_flow_summary(self, sid: str, *, termination_state: str) -> str:
        """Render one CLI line from already-retained typed Session evidence."""

        state = self.state.get(sid)
        if not state:
            return ""
        events = state.get("workflow_events") or []
        parts = (
            ["vad[accepted]"]
            if isinstance(events, list)
            and any(
                isinstance(item, dict) and item.get("event") == "vad_valid_end"
                for item in events
            )
            else []
        )
        slowest_name = ""
        slowest_ms = 0.0
        stages = state.get("cognitive_workflow_stages") or []
        if isinstance(stages, list):
            for item in sorted(
                (row for row in stages if isinstance(row, dict)),
                key=lambda row: float(row.get("started_elapsed_ms") or 0.0),
            ):
                name = str(item.get("stage") or "stage").strip().replace(" ", "_")
                status = str(item.get("status") or "unknown").strip().replace(" ", "_")
                attempt = max(1, int(item.get("attempt") or 1))
                if attempt > 1:
                    name = f"{name}#{attempt}"
                duration_ms = float(item.get("duration_ms") or 0.0)
                errors = item.get("errors")
                error_suffix = (
                    f",errors={len(errors)}"
                    if isinstance(errors, list) and errors
                    else ""
                )
                parts.append(
                    f"{name}[{status},{self._flow_duration_text(duration_ms)}{error_suffix}]"
                )
                if duration_ms > slowest_ms:
                    slowest_name = name
                    slowest_ms = duration_ms

        scheduled = int(state.get("scheduled_tts", 0))
        played = int(state.get("played_tts", 0))
        failed = int(state.get("failed_tts", 0))
        skipped = int(state.get("skipped_tts", 0))
        if scheduled or played or failed or skipped:
            parts.append(
                f"tts_playback[played={played}/{scheduled},failed={failed},skipped={skipped}]"
            )
        if not parts:
            return ""
        suffix = (
            f" | state={termination_state} "
            f"total={self._flow_duration_text(self.elapsed_ms(sid))}"
        )
        if slowest_name:
            suffix += f" slowest={slowest_name}:{self._flow_duration_text(slowest_ms)}"
        return " -> ".join(parts) + suffix

    def _log_session_flow_summary(
        self,
        sid: str,
        *,
        termination_state: str,
    ) -> None:
        state = self.state.get(sid)
        if not state or state.get("flow_summary_logged"):
            return
        summary = self._session_flow_summary(sid, termination_state=termination_state)
        if summary:
            state["flow_summary_logged"] = True
            self.log(sid, "session_flow: %s", summary)

    def _workflow_summary(self, sid: str) -> str:
        state = self.state.get(sid)
        if not state:
            return ""
        workflow_events = state.get("workflow_events") or []
        if not isinstance(workflow_events, list):
            return ""
        messages: list[str] = []
        for item in workflow_events:
            if isinstance(item, dict):
                messages.append(str(item.get("message") or ""))
            elif item:
                messages.append(str(item))
        return " -> ".join(item for item in messages if item)

    def _workflow_graph(self, sid: str) -> dict[str, Any]:
        state = self.state.get(sid)
        if not state:
            return {}
        workflow_events = state.get("workflow_events") or []
        if not isinstance(workflow_events, list):
            return {}
        nodes: list[dict[str, Any]] = []
        for index, item in enumerate(workflow_events):
            if not isinstance(item, dict):
                continue
            elapsed_ms = float(item.get("elapsed_ms") or 0.0)
            previous_elapsed = float(nodes[-1]["elapsed_ms"]) if nodes else elapsed_ms
            nodes.append(
                {
                    "id": f"n{index}",
                    "index": index,
                    "event": str(item.get("event") or "session_event"),
                    "elapsed_ms": round(elapsed_ms, 3),
                    "delta_from_previous_ms": round(max(0.0, elapsed_ms - previous_elapsed), 3),
                    "message": str(item.get("message") or ""),
                    "severity": str(item.get("severity") or "info"),
                }
            )
        edges = [
            {
                "from": nodes[index - 1]["id"],
                "to": nodes[index]["id"],
                "delta_ms": round(
                    max(0.0, float(nodes[index]["elapsed_ms"]) - float(nodes[index - 1]["elapsed_ms"])),
                    3,
                ),
            }
            for index in range(1, len(nodes))
        ]
        return {
            "schema_version": 1,
            "sid": sid,
            "total_ms": round(self.elapsed_ms(sid), 3),
            "nodes": nodes,
            "edges": edges,
        }

    def _emit_workflow_graph(self, sid: str, graph: dict[str, Any]) -> None:
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
        total_ms = float(graph.get("total_ms") or self.elapsed_ms(sid))
        self.event_writer.write(
            sid=sid,
            elapsed_ms=self.elapsed_ms(sid),
            message="session_workflow_graph: nodes=%s edges=%s total_ms=%.1f",
            args=(len(nodes), len(edges), total_ms),
            extra={"graph": graph},
        )

    def _workflow_timing_summary(self, graph: dict[str, Any]) -> str:
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        if not nodes:
            return ""
        total_ms = float(graph.get("total_ms") or 0.0)
        slow_nodes = sorted(
            (
                node
                for node in nodes
                if isinstance(node, dict)
                and float(node.get("delta_from_previous_ms") or 0.0) > 0.0
            ),
            key=lambda node: float(node.get("delta_from_previous_ms") or 0.0),
            reverse=True,
        )[:5]
        slowest = ", ".join(
            f"{node.get('event')}+{float(node.get('delta_from_previous_ms') or 0.0):.1f}ms"
            for node in slow_nodes
        )
        return (
            f"nodes={len(nodes)} edges={max(0, len(nodes) - 1)} "
            f"total_ms={total_ms:.1f} slowest={slowest or 'none'}"
        )

    def record_cognitive_stage(
        self,
        sid: str | None,
        *,
        stage: str,
        started_monotonic_ms: float,
        finished_monotonic_ms: float,
        status: str,
        input_payload: Any = None,
        output_payload: Any = None,
        errors: list[Any] | None = None,
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Retain one observed cognitive boundary without affecting execution.

        The caller supplies already-owned DTOs and monotonic timestamps. The
        Session owner only serializes evidence; it never infers meaning,
        changes a plan, or authorizes a Capability.
        """

        if not sid:
            return
        session = self.state.get(sid)
        if not session or session.get("workflow_report_finalized"):
            return
        t0_ms = float(session.get("t0_ms") or started_monotonic_ms)
        started_elapsed_ms = max(0.0, float(started_monotonic_ms) - t0_ms)
        finished_elapsed_ms = max(
            started_elapsed_ms,
            float(finished_monotonic_ms) - t0_ms,
        )
        record = {
            "stage": " ".join(str(stage or "cognitive_stage").strip().split()),
            "attempt": max(1, int(attempt)),
            "status": " ".join(str(status or "unknown").strip().split()),
            "started_elapsed_ms": round(started_elapsed_ms, 3),
            "finished_elapsed_ms": round(finished_elapsed_ms, 3),
            "duration_ms": round(finished_elapsed_ms - started_elapsed_ms, 3),
            "input": self._workflow_evidence_value(input_payload),
            "output": self._workflow_evidence_value(output_payload),
            "errors": self._workflow_evidence_value(list(errors or [])),
            "metadata": self._workflow_evidence_value(dict(metadata or {})),
        }
        stages = session.setdefault("cognitive_workflow_stages", [])
        if not isinstance(stages, list):
            stages = []
            session["cognitive_workflow_stages"] = stages
        stages.append(record)
        session["last_activity_ms"] = now_ms()

    def _workflow_evidence_value(
        self,
        value: Any,
        *,
        key: str = "",
        depth: int = 0,
    ) -> Any:
        if hasattr(value, "model_dump"):
            try:
                value = value.model_dump(mode="json", exclude_none=True)
            except (AttributeError, TypeError, ValueError):
                value = str(value)
        normalized_key = key.casefold()
        safe_string_keys = {
            "authority",
            "capability_id",
            "classification",
            "disposition",
            "error_type",
            "event",
            "execution_lane",
            "failure_stage",
            "interaction_id",
            "intent",
            "operation",
            "output_mode",
            "provider_id",
            "reason_code",
            "request_id",
            "result_type",
            "route",
            "session_id",
            "severity",
            "sid",
            "capability_id",
            "stage",
            "status",
            "termination_state",
            "trace_id",
            "turn_id",
            "type",
        }
        string_key_is_structural = (
            normalized_key in safe_string_keys
            or normalized_key.endswith("_id")
            or normalized_key.endswith("_ids")
            or normalized_key.endswith("_version")
            or normalized_key.endswith("_sha256")
            or normalized_key.endswith("_at_utc")
        )
        if (
            not self.workflow_report_include_text
            and (
                normalized_key
                in {
                    "text",
                    "user_text",
                    "source_text",
                    "description",
                    "response_text",
                    "clarification",
                    "speech",
                    "message",
                }
                or (isinstance(value, str) and not string_key_is_structural)
            )
            and value not in (None, "", [], {})
        ):
            serialized = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            )
            return {
                "redacted": True,
                "chars": len(serialized),
                "sha256_16": hashlib.sha256(
                    serialized.encode("utf-8", errors="replace")
                ).hexdigest()[:16],
            }
        if depth >= 10:
            return "<depth-limit>"
        if isinstance(value, dict):
            return {
                str(item_key): self._workflow_evidence_value(
                    item_value,
                    key=str(item_key),
                    depth=depth + 1,
                )
                for item_key, item_value in list(value.items())[:160]
            }
        if isinstance(value, (list, tuple, set)):
            return [
                self._workflow_evidence_value(item, key=key, depth=depth + 1)
                for item in list(value)[:160]
            ]
        if isinstance(value, str):
            return value if len(value) <= 12000 else value[:11997].rstrip() + "..."
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)

    def _workflow_report(self, sid: str, *, termination_state: str) -> dict[str, Any]:
        session = self.state.get(sid) or {}
        graph = self._workflow_graph(sid)
        stages = session.get("cognitive_workflow_stages")
        if not isinstance(stages, list):
            stages = []
        retained_stages = [
            dict(item) for item in stages if isinstance(item, dict)
        ]
        trusted_runtime_stages = [
            item
            for item in retained_stages
            if item.get("stage") == "trusted_capability_runtime"
        ]
        dispatch_blocked = any(
            item.get("stage") == "canonical_plan_rejection"
            and isinstance(item.get("metadata"), dict)
            and item["metadata"].get("dispatch_allowed") is False
            for item in retained_stages
        )
        requested_work_provider_start_observed = any(
            isinstance(item.get("metadata"), dict)
            and item["metadata"].get("requested_work_provider_start_observed") is True
            for item in trusted_runtime_stages
        )
        speech_delivery_provider_start_observed = any(
            isinstance(item.get("metadata"), dict)
            and item["metadata"].get("speech_delivery_provider_start_observed") is True
            for item in trusted_runtime_stages
        )
        any_provider_start_observed = any(
            isinstance(item.get("metadata"), dict)
            and item["metadata"].get("any_provider_start_observed") is True
            for item in trusted_runtime_stages
        )
        return {
            "schema_version": 2,
            "sid": sid,
            "termination_state": termination_state,
            "started_at_utc": str(session.get("started_at_utc") or ""),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_ms": round(self.elapsed_ms(sid), 3),
            "correlations": self._workflow_evidence_value(
                dict(session.get("correlations") or {})
            ),
            "privacy": {
                "raw_text_included": self.workflow_report_include_text,
                "classification": "private_runtime_evidence",
                "safe_to_publish_without_review": False,
            },
            "cognitive_stages": retained_stages,
            "runtime_timeline": self._workflow_evidence_value(
                list(graph.get("nodes") or [])
            ),
            "outcome": {
                "scheduled_tts": int(session.get("scheduled_tts", 0)),
                "queued_tts": int(session.get("queued_tts", 0)),
                "played_tts": int(session.get("played_tts", 0)),
                "failed_tts": int(session.get("failed_tts", 0)),
                "skipped_tts": int(session.get("skipped_tts", 0)),
                "response_chars": int(session.get("response_chars", 0)),
                "interrupted": bool(session.get("interrupted", False)),
                "trusted_runtime_observed": bool(trusted_runtime_stages),
                "requested_work_provider_start_observed": (
                    requested_work_provider_start_observed
                ),
                "speech_delivery_provider_start_observed": (
                    speech_delivery_provider_start_observed
                ),
                "any_provider_start_observed": any_provider_start_observed,
                "dispatch_blocked_before_requested_provider": (
                    dispatch_blocked and not requested_work_provider_start_observed
                ),
            },
        }

    @staticmethod
    def _workflow_stage_label(stage: str) -> str:
        return " ".join(part.capitalize() for part in str(stage).split("_"))

    def _render_workflow_report_markdown(self, report: dict[str, Any]) -> str:
        stages = report.get("cognitive_stages")
        if not isinstance(stages, list):
            stages = []
        runtime = report.get("runtime_timeline")
        if not isinstance(runtime, list):
            runtime = []
        flow_items: list[tuple[float, str, str]] = []
        for item in stages:
            if not isinstance(item, dict):
                continue
            flow_items.append(
                (
                    float(item.get("started_elapsed_ms") or 0.0),
                    self._workflow_stage_label(str(item.get("stage") or "stage")),
                    str(item.get("status") or "unknown"),
                )
            )
        visible_runtime_events = {
            "asr_final",
            "cognitive_capability_proposed",
            "capability_runtime_done",
            "capability_result",
            "tts_schedule",
            "playback_start",
            "playback_end",
            "session_done",
        }
        for item in runtime:
            if not isinstance(item, dict):
                continue
            event = str(item.get("event") or "")
            if event not in visible_runtime_events:
                continue
            flow_items.append(
                (
                    float(item.get("elapsed_ms") or 0.0),
                    self._workflow_stage_label(event),
                    str(item.get("severity") or "info"),
                )
            )
        flow_items.sort(key=lambda item: item[0])
        flow_lines: list[str] = []
        for index, (elapsed_ms, label, status) in enumerate(flow_items):
            if index:
                flow_lines.extend(["          │", "          ▼"])
            flow_lines.append(f"{label} [{status}] +{elapsed_ms:.1f} ms")

        lines = [
            "# Chromie interaction-session workflow",
            "",
            f"- SID: `{report.get('sid')}`",
            f"- State: `{report.get('termination_state')}`",
            f"- Started: `{report.get('started_at_utc')}`",
            f"- Finished: `{report.get('finished_at_utc')}`",
            f"- Total: `{float(report.get('total_ms') or 0.0):.1f} ms`",
            f"- Correlations: `{json.dumps(report.get('correlations') or {}, ensure_ascii=False, sort_keys=True)}`",
            "- Privacy: private runtime evidence; review before sharing.",
            "",
            "## Flow",
            "",
            "```text",
            *(flow_lines or ["No retained workflow stages."]),
            "```",
            "",
            "## Outcome",
            "",
            "```json",
            json.dumps(
                report.get("outcome") or {},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Cognitive stages",
            "",
        ]
        for item in stages:
            if not isinstance(item, dict):
                continue
            label = self._workflow_stage_label(str(item.get("stage") or "stage"))
            lines.extend(
                [
                    f"### {label} — attempt {item.get('attempt', 1)}",
                    "",
                    (
                        f"Timeline: `+{float(item.get('started_elapsed_ms') or 0.0):.1f} ms` "
                        f"→ `+{float(item.get('finished_elapsed_ms') or 0.0):.1f} ms` "
                        f"(`{float(item.get('duration_ms') or 0.0):.1f} ms`), "
                        f"status `{item.get('status')}`."
                    ),
                    "",
                    "Input:",
                    "",
                    "```json",
                    json.dumps(
                        item.get("input"),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                    "```",
                    "",
                    "Output:",
                    "",
                    "```json",
                    json.dumps(
                        item.get("output"),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                    "```",
                ]
            )
            errors = item.get("errors")
            if errors:
                lines.extend(
                    [
                        "",
                        "Errors:",
                        "",
                        "```json",
                        json.dumps(
                            errors,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        ),
                        "```",
                    ]
                )
            lines.append("")

        lines.extend(["## Runtime timeline", ""])
        for item in runtime:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            rendered_message = (
                message
                if isinstance(message, str)
                else json.dumps(message, ensure_ascii=False, sort_keys=True)
            )
            lines.append(
                f"- `+{float(item.get('elapsed_ms') or 0.0):.1f} ms` "
                f"**{item.get('event')}** [{item.get('severity')}]: "
                f"{rendered_message}"
            )
        lines.append("")
        return "\n".join(lines)

    def _finalize_workflow_report(
        self,
        sid: str,
        *,
        termination_state: str,
    ) -> dict[str, Any]:
        session = self.state.get(sid)
        if not session:
            return {}
        existing = session.get("workflow_report")
        if session.get("workflow_report_finalized") and isinstance(existing, dict):
            return existing
        report = self._workflow_report(sid, termination_state=termination_state)
        markdown = self._render_workflow_report_markdown(report)
        paths: dict[str, str] = {}
        if self.workflow_report_root is not None:
            try:
                self.workflow_report_root.mkdir(parents=True, exist_ok=True)
                started = re.sub(
                    r"[^0-9A-Za-z]+",
                    "",
                    str(report.get("started_at_utc") or "session"),
                )[:20]
                stem = f"{started or 'session'}-{sid}"
                json_path = self.workflow_report_root / f"{stem}.json"
                markdown_path = self.workflow_report_root / f"{stem}.md"
                with self._workflow_report_lock:
                    json_temp = json_path.with_suffix(".json.tmp")
                    markdown_temp = markdown_path.with_suffix(".md.tmp")
                    json_temp.write_text(
                        json.dumps(
                            report,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    markdown_temp.write_text(markdown, encoding="utf-8")
                    os.replace(json_temp, json_path)
                    os.replace(markdown_temp, markdown_path)
                paths = {"json": str(json_path), "markdown": str(markdown_path)}
            except Exception as exc:  # evidence capture must not break runtime
                logger.warning("Could not write session workflow report: %s", exc)
        report["paths"] = paths
        session["workflow_report"] = report
        session["workflow_report_markdown"] = markdown
        session["workflow_report_paths"] = paths
        session["workflow_report_finalized"] = True
        conversation_paths = self._write_conversation_workflow_report(sid)
        if conversation_paths:
            session["conversation_workflow_report_paths"] = conversation_paths
        self.event_writer.write(
            sid=sid,
            elapsed_ms=self.elapsed_ms(sid),
            message="session_workflow_report: state=%s stages=%s runtime_events=%s",
            args=(
                termination_state,
                len(report["cognitive_stages"]),
                len(report["runtime_timeline"]),
            ),
            extra={"report": report, "report_paths": paths},
        )
        return report

    def _write_conversation_workflow_report(self, sid: str) -> dict[str, str]:
        """Refresh the multi-turn view for the SID's existing conversation.

        The conversation ID already belongs to ConversationState and only
        correlates finalized per-SID facts here. This rollup never decides when
        a conversation starts, ends, or changes meaning.
        """

        if self.workflow_report_root is None:
            return {}
        session = self.state.get(sid) or {}
        correlations = session.get("correlations")
        if not isinstance(correlations, dict):
            return {}
        conversation_id = str(correlations.get("conversation_id") or "").strip()
        if not conversation_id:
            return {}
        session_reports: list[dict[str, Any]] = []
        for candidate in self.state.values():
            candidate_correlations = candidate.get("correlations")
            candidate_report = candidate.get("workflow_report")
            if (
                isinstance(candidate_correlations, dict)
                and candidate_correlations.get("conversation_id") == conversation_id
                and isinstance(candidate_report, dict)
                and candidate.get("workflow_report_finalized")
            ):
                session_reports.append(
                    {
                        key: value
                        for key, value in candidate_report.items()
                        if key != "paths"
                    }
                )
        session_reports.sort(
            key=lambda item: (
                str(item.get("started_at_utc") or ""),
                str(item.get("sid") or ""),
            )
        )
        if not session_reports:
            return {}
        rollup = {
            "schema_version": 1,
            "conversation_id": conversation_id,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_count": len(session_reports),
            "sessions": session_reports,
            "privacy": {
                "raw_text_included": self.workflow_report_include_text,
                "classification": "private_runtime_evidence",
                "safe_to_publish_without_review": False,
            },
        }
        markdown_lines = [
            "# Chromie interactive-session workflow",
            "",
            f"- Conversation: `{conversation_id}`",
            f"- Updated: `{rollup['updated_at_utc']}`",
            f"- Interaction SIDs: `{len(session_reports)}`",
            "- Privacy: private runtime evidence; review before sharing.",
            "",
        ]
        for index, item in enumerate(session_reports, start=1):
            markdown_lines.extend(
                [
                    f"## Turn {index} — SID `{item.get('sid')}`",
                    "",
                    self._render_workflow_report_markdown(item),
                    "",
                ]
            )
        safe_conversation_id = re.sub(
            r"[^0-9A-Za-z_.-]+",
            "-",
            conversation_id,
        ).strip("-._")[:80]
        conversation_digest = hashlib.sha256(
            conversation_id.encode("utf-8", errors="replace")
        ).hexdigest()[:10]
        safe_conversation_id = (
            f"{safe_conversation_id}-{conversation_digest}"
            if safe_conversation_id
            else conversation_digest
        )
        json_path = (
            self.workflow_report_root
            / f"conversation-{safe_conversation_id}.json"
        )
        markdown_path = (
            self.workflow_report_root
            / f"conversation-{safe_conversation_id}.md"
        )
        try:
            self.workflow_report_root.mkdir(parents=True, exist_ok=True)
            with self._workflow_report_lock:
                json_temp = json_path.with_suffix(".json.tmp")
                markdown_temp = markdown_path.with_suffix(".md.tmp")
                json_temp.write_text(
                    json.dumps(
                        rollup,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                markdown_temp.write_text(
                    "\n".join(markdown_lines),
                    encoding="utf-8",
                )
                os.replace(json_temp, json_path)
                os.replace(markdown_temp, markdown_path)
        except Exception as exc:  # evidence capture must not break runtime
            logger.warning("Could not write conversation workflow report: %s", exc)
            return {}
        return {"json": str(json_path), "markdown": str(markdown_path)}
