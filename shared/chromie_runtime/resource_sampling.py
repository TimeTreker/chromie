"""Low-overhead system resource observations for Runtime Trace.

The sampler intentionally uses standard-library and Linux procfs sources only.
It does not invoke network services or GPU tools from the realtime path. Missing
platform metrics are omitted rather than fabricated.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .runtime_trace import TraceModule

RESOURCE_SAMPLE_MODULE = TraceModule(
    name="chromie.runtime.resources",
    component_type="resource_sampler",
    implementation="SystemResourceSampler",
)

_VALID_MODES = {"off", "session", "periodic"}


class SystemResourceSampler:
    """Collect bounded process and host resource facts.

    ``session`` mode samples only lifecycle boundaries. ``periodic`` also allows
    the Orchestrator sweeper to sample active sessions. CPU percentage is a
    delta between sampler calls and is therefore omitted from the first sample.
    """

    def __init__(self, mode: str = "off") -> None:
        normalized = str(mode or "off").strip().lower()
        self.mode = normalized if normalized in _VALID_MODES else "off"
        self._lock = threading.Lock()
        self._last_wall: float | None = None
        self._last_cpu: float | None = None

    @classmethod
    def from_env(cls) -> "SystemResourceSampler":
        return cls(os.getenv("CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING", "off"))

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def should_sample(self, reason: str) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "periodic":
            return True
        return reason in {"session_start", "session_finish", "session_abandoned"}

    def sample(
        self,
        *,
        reason: str,
        event_loop_lag_ms: float | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.should_sample(reason):
            return {}
        now_wall = time.perf_counter()
        now_cpu = time.process_time()
        payload: dict[str, Any] = {
            "sample_reason": str(reason or "unspecified"),
            "process_cpu_time_ms": round(now_cpu * 1000.0, 3),
            "cpu_count": os.cpu_count() or 0,
        }
        with self._lock:
            if self._last_wall is not None and self._last_cpu is not None:
                wall_delta = now_wall - self._last_wall
                if wall_delta > 0:
                    payload["process_cpu_percent_one_core"] = round(
                        max(0.0, (now_cpu - self._last_cpu) / wall_delta * 100.0),
                        3,
                    )
            self._last_wall = now_wall
            self._last_cpu = now_cpu

        payload.update(_process_procfs_metrics())
        payload.update(_host_procfs_metrics())
        try:
            load1, load5, load15 = os.getloadavg()
            payload.update(
                {
                    "system_load_1m": round(load1, 4),
                    "system_load_5m": round(load5, 4),
                    "system_load_15m": round(load15, 4),
                }
            )
        except (AttributeError, OSError):
            pass
        if event_loop_lag_ms is not None:
            payload["event_loop_lag_ms"] = round(
                max(0.0, float(event_loop_lag_ms)), 3
            )
        for key, value in dict(attributes or {}).items():
            if value is not None:
                payload[str(key)] = value
        return payload


def _process_procfs_metrics() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    statm = Path("/proc/self/statm")
    try:
        values = statm.read_text(encoding="utf-8").split()
        if len(values) >= 2:
            page_size = os.sysconf("SC_PAGE_SIZE")
            payload["process_virtual_memory_bytes"] = int(values[0]) * page_size
            payload["process_rss_bytes"] = int(values[1]) * page_size
    except (OSError, ValueError, IndexError):
        pass

    status = Path("/proc/self/status")
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("Threads:"):
                payload["process_thread_count"] = int(line.split()[1])
                break
    except (OSError, ValueError, IndexError):
        pass

    fd_root = Path("/proc/self/fd")
    try:
        payload["process_open_fd_count"] = sum(1 for _ in fd_root.iterdir())
    except OSError:
        pass
    return payload


def _host_procfs_metrics() -> dict[str, Any]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            first = raw.strip().split()[0]
            values[key] = int(first) * 1024
    except (OSError, ValueError, IndexError):
        return {}
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    payload: dict[str, Any] = {}
    if total is not None:
        payload["system_memory_total_bytes"] = total
    if available is not None:
        payload["system_memory_available_bytes"] = available
    if total and available is not None:
        payload["system_memory_used_percent"] = round(
            max(0.0, min(100.0, (total - available) / total * 100.0)), 3
        )
    return payload
