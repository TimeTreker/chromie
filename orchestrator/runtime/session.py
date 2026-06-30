from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        "agent_start",
        "interaction_done",
        "skill_runtime_done",
        "skill_result",
        "experience_recorded",
        "episode_recorded",
        "tts_text_split",
        "tts_schedule",
        "tts_request_start",
        "tts_stream_start",
        "tts_stream_end",
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

    def create(self) -> str:
        previous = self.current_sid
        sid = str(uuid.uuid4())[:8]
        self.current_sid = sid
        self.state[sid] = {
            "t0_ms": now_ms(),
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
        }
        if previous and previous != sid:
            prev = self.state.get(previous)
            if prev and not prev.get("done_logged"):
                prev["interrupted"] = True
                self.log(previous, "session_interrupted_by_new_session: new_sid=%s", sid)
        self.log(sid, "session_start")
        return sid

    def elapsed_ms(self, sid: str | None) -> float:
        state = self.state.get(sid or "")
        return 0.0 if not state else now_ms() - float(state["t0_ms"])

    def log(self, sid: str | None, message: str, *args: Any) -> None:
        if not self.enabled:
            return
        sid = sid or "unknown"
        elapsed = self.elapsed_ms(sid)
        rendered = self._render_message(message, args)
        self._remember_workflow_event(sid, rendered)
        self.event_writer.write(
            sid=sid,
            elapsed_ms=elapsed,
            message=message,
            args=args,
        )
        if args:
            logger.info("[SID:%s +%.1fms] " + message, sid, elapsed, *args)
        else:
            logger.info("[SID:%s +%.1fms] %s", sid, elapsed, message)

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

    def _render_message(self, message: str, args: tuple[Any, ...]) -> str:
        try:
            return message % args if args else message
        except Exception:
            return f"{message} args={args!r}"

    def _remember_workflow_event(self, sid: str, rendered: str) -> None:
        if rendered.startswith("session_workflow"):
            return
        state = self.state.get(sid)
        if not state:
            return
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
            }
        )

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
