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
        try:
            with self._lock:
                with self.path.open("a", encoding="utf-8") as handle:
                    json.dump(record, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
        except Exception as exc:  # evidence capture must not break runtime
            logger.warning("Could not append session event evidence: %s", exc)


class SessionTracker:
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
