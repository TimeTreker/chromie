from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

logger = logging.getLogger(__name__)


def now_ms() -> float:
    return time.perf_counter() * 1000.0


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
        "asr_final",
        "context_snapshot",
        "router_start",
        "router_done",
        "fast_first_response_schedule",
        "fast_first_response_scheduled",
        "fast_first_response_skipped",
        "fast_first_audio_hedge_started",
        "fast_first_audio_schedule",
        "fast_first_audio_suppressed",
        "playback_cancel_before_start",
        "playback_skip_cancelled",
        "agent_start",
        "interaction_done",
        "cognitive_interaction_ready",
        "cognitive_skill_proposed",
        "skill_runtime_done",
        "skill_result",
        "soridormi_post_status",
        "soridormi_post_status_failed",
        "experience_recorded",
        "episode_recorded",
        "tts_text_split",
        "tts_schedule",
        "tts_request_start",
        "tts_stream_start",
        "tts_stream_end",
        "tts_server_metrics",
        "tts_stream_failed",
        "tts_playback_start_waiter_resolved",
        "playback_start",
        "playback_end",
        "session_done",
    )

    def __init__(
        self,
        enabled: bool = True,
        *,
        event_log_path: str | os.PathLike[str] | None = None,
    ):
        self.enabled = enabled
        self.current_sid: str | None = None
        self.state: dict[str, dict[str, Any]] = {}
        self.event_writer = SessionEventWriter(event_log_path)
        self.resource_sampler = SystemResourceSampler.from_env()
        self.checkpoint_store = TraceCheckpointStore()
        self.recovered_runtime_traces = self._recover_abandoned_runtime_traces()

    def create(self) -> str:
        previous = self.current_sid
        sid = str(uuid.uuid4())[:8]
        self.current_sid = sid
        self.state[sid] = {
            "t0_ms": now_ms(),
            "last_activity_ms": now_ms(),
            "scheduled_tts": 0,
            "queued_tts": 0,
            "played_tts": 0,
            "failed_tts": 0,
            "skipped_tts": 0,
            "llm_done": False,
            "done_logged": False,
            "response_chars": 0,
            "interrupted": False,
            "workflow_events": [],
            "runtime_trace": self._create_runtime_trace(sid),
            "runtime_trace_event": {},
        }
        if previous and previous != sid:
            prev = self.state.get(previous)
            if prev and not prev.get("done_logged"):
                prev["interrupted"] = True
                self.log(previous, "session_interrupted_by_new_session: new_sid=%s", sid)
                self._finalize_runtime_trace(previous, state="abandoned")
        self.log(sid, "session_start")
        self.trace_mark(sid, "session_started", kind="session", attributes={"sid": sid})
        self.sample_resources(sid, reason="session_start")
        self._checkpoint_runtime_trace(sid)
        return sid

    def _create_runtime_trace(self, sid: str) -> RuntimeTrace | None:
        policy = TracePolicy.from_env()
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
        trace = session.get("runtime_trace")
        if not isinstance(trace, RuntimeTrace) or session.get("runtime_trace_finalized"):
            return
        trace.update_correlations(values)
        self._checkpoint_runtime_trace(str(sid or ""))

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
        with self.trace_context(sid):
            item_id = runtime_tracer.mark(
                module=RESOURCE_SAMPLE_MODULE,
                name="runtime_resource_sample",
                kind="resource_sample",
                attributes=payload,
            )
        self._checkpoint_runtime_trace(str(sid or ""))
        return item_id

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
        trace = session.get("runtime_trace")
        if not isinstance(trace, RuntimeTrace):
            return
        self.sample_resources(
            sid,
            reason="session_abandoned" if state == "abandoned" else "session_finish",
        )
        session["runtime_trace_finalized"] = True
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

        if event_name == "skill_result":
            status = self._field_value(rendered, "status").casefold()
            if status and status not in {"completed", "ok", "success"}:
                if status in {"cancelled", "canceled", "skipped", "ignored"}:
                    return logging.WARNING
                return logging.ERROR

        if event_name == "skill_runtime_done":
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

        if event_name == "router_done":
            route = self._field_value(rendered, "route").casefold()
            intent = self._field_value(rendered, "intent").casefold()
            if route == "robot_action" and intent == "capability:chromie.speak":
                return logging.WARNING

        if event_name == "tts_schedule" and self._looks_like_failure_speech(rendered):
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
    def _looks_like_failure_speech(rendered: str) -> bool:
        lowered = rendered.casefold()
        return any(
            phrase in lowered
            for phrase in (
                "i cannot perform that action",
                "i can't perform that action",
                "cannot perform that action",
                "can't perform that action",
                "no executable action was produced",
                "will not pretend i did it",
                "i am not able to perform",
            )
        )

    @staticmethod
    def _colorize_for_cli(line: str, level: int) -> str:
        return colorize_for_cli(line, level, env_var="ORCH_CLI_COLOR")

    def _compact_workflow_message(self, rendered: str, *, limit: int = 320) -> str:
        text = " ".join(rendered.split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

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
