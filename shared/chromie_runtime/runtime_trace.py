"""Architecture-independent Runtime Trace for Chromie.

Modules declare stable identities and emit generic spans or milestones.  The
framework owns IDs, clocks, async context propagation, bounded attributes,
trace finalization, summary derivation, and Runtime Event packaging.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

TRACE_SCHEMA_VERSION = 1
TRACE_SUMMARY_SCHEMA_VERSION = 1
TRACE_CARRIER_SCHEMA_VERSION = 1
TRACE_CARRIER_KEY = "_chromie_runtime_trace"
TRACE_FRAGMENT_KEY = "_runtime_trace_fragment"
TRACE_CHECKPOINT_SCHEMA_VERSION = 1
_TRACE_MODES = {"off": 0, "basic": 1, "debug": 2}
_TRACE_STATES = {"active", "finishing", "complete", "abandoned"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _token(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _csv_env(name: str) -> frozenset[str]:
    return frozenset(
        item.strip()
        for item in str(os.getenv(name) or "").split(",")
        if item.strip()
    )


@dataclass(frozen=True)
class TraceModule:
    """Stable, low-cardinality identity owned by one instrumented module."""

    name: str
    component_type: str
    implementation: str
    schema_version: int = 1
    version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _token(self.name, "TraceModule.name"))
        object.__setattr__(
            self,
            "component_type",
            _token(self.component_type, "TraceModule.component_type"),
        )
        object.__setattr__(
            self,
            "implementation",
            _token(self.implementation, "TraceModule.implementation"),
        )
        if int(self.schema_version) < 1:
            raise ValueError("TraceModule.schema_version must be at least 1")

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "component_type": self.component_type,
            "implementation": self.implementation,
            "schema_version": int(self.schema_version),
        }
        if self.version:
            payload["version"] = str(self.version)
        return payload


@dataclass(frozen=True)
class TraceRetentionDecision:
    emit: bool
    reason: str
    severity: str = "info"

    def as_dict(self) -> dict[str, Any]:
        return {
            "emit": self.emit,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class TracePolicy:
    mode: str = "off"
    module_allowlist: frozenset[str] = frozenset()
    debug_modules: frozenset[str] = frozenset()
    max_items: int = 1000
    max_attributes: int = 32
    max_attribute_chars: int = 512
    emit_events: bool = False
    event_sample_rate: float = 1.0
    event_min_total_ms: float = 0.0
    event_min_first_observable_ms: float = 0.0
    event_always_emit_abandoned: bool = True
    coverage: str = "partial"

    def __post_init__(self) -> None:
        mode = str(self.mode or "off").strip().lower()
        if mode not in _TRACE_MODES:
            raise ValueError(f"unsupported Runtime Trace mode: {self.mode!r}")
        object.__setattr__(self, "mode", mode)

    @classmethod
    def from_env(cls, *, mode: str | None = None) -> "TracePolicy":
        configured_mode = str(
            mode if mode is not None else os.getenv("CHROMIE_RUNTIME_TRACE_MODE", "off")
        ).strip().lower()
        if configured_mode not in _TRACE_MODES:
            configured_mode = "off"
        return cls(
            mode=configured_mode,
            module_allowlist=_csv_env("CHROMIE_RUNTIME_TRACE_MODULES"),
            debug_modules=_csv_env("CHROMIE_RUNTIME_TRACE_DEBUG_MODULES"),
            max_items=_env_int("CHROMIE_RUNTIME_TRACE_MAX_ITEMS", 1000, 16, 10000),
            max_attributes=_env_int(
                "CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTES", 32, 4, 256
            ),
            max_attribute_chars=_env_int(
                "CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTE_CHARS", 512, 64, 8192
            ),
            emit_events=_env_bool("CHROMIE_RUNTIME_TRACE_EMIT_EVENTS", False),
            event_sample_rate=_env_float(
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE", 1.0, 0.0, 1.0
            ),
            event_min_total_ms=_env_float(
                "CHROMIE_RUNTIME_TRACE_EVENT_MIN_TOTAL_MS", 0.0, 0.0, 86400000.0
            ),
            event_min_first_observable_ms=_env_float(
                "CHROMIE_RUNTIME_TRACE_EVENT_MIN_FIRST_OBSERVABLE_MS",
                0.0,
                0.0,
                86400000.0,
            ),
            event_always_emit_abandoned=_env_bool(
                "CHROMIE_RUNTIME_TRACE_EVENT_ALWAYS_EMIT_ABANDONED", True
            ),
            coverage=str(
                os.getenv("CHROMIE_RUNTIME_TRACE_COVERAGE", "partial")
            ).strip()
            or "partial",
        )

    def mode_for(self, module: TraceModule) -> str:
        if self.mode == "off":
            return "off"
        if self.module_allowlist and module.name not in self.module_allowlist:
            return "off"
        if self.mode == "debug" or module.name in self.debug_modules:
            return "debug"
        return "basic"

    def retention_decision(self, snapshot: "TraceSnapshot") -> TraceRetentionDecision:
        if not self.emit_events:
            return TraceRetentionDecision(False, "event_emission_disabled")
        state = str(snapshot.trace.get("state") or "")
        if state == "abandoned" and self.event_always_emit_abandoned:
            return TraceRetentionDecision(True, "abandoned_trace", "warning")
        first_observable = snapshot.summary.get("first_user_observable_latency_ms")
        if (
            self.event_min_first_observable_ms > 0
            and first_observable is not None
            and float(first_observable) >= self.event_min_first_observable_ms
        ):
            return TraceRetentionDecision(
                True, "first_user_observable_latency_threshold", "warning"
            )
        total = float(snapshot.summary.get("total_duration_ms") or 0.0)
        if self.event_min_total_ms > 0 and total >= self.event_min_total_ms:
            return TraceRetentionDecision(True, "total_latency_threshold", "warning")
        if self.event_sample_rate >= 1.0:
            return TraceRetentionDecision(True, "configured_full_retention")
        if self.event_sample_rate <= 0.0:
            return TraceRetentionDecision(False, "not_sampled")
        digest = hashlib.sha256(
            str(snapshot.trace.get("trace_id") or "").encode("utf-8")
        ).digest()
        fraction = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        if fraction < self.event_sample_rate:
            return TraceRetentionDecision(True, "deterministic_sample")
        return TraceRetentionDecision(False, "not_sampled")


@dataclass(frozen=True)
class TraceSnapshot:
    trace: dict[str, Any]
    summary: dict[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace.get("trace_id", ""),
            "state": self.trace.get("state", ""),
            "mode": (self.trace.get("collection") or {}).get("mode", "off"),
            "coverage": (self.trace.get("collection") or {}).get(
                "coverage", "partial"
            ),
            "item_count": self.summary.get("item_count", 0),
            "total_duration_ms": self.summary.get("total_duration_ms", 0.0),
            "first_user_observable_latency_ms": self.summary.get(
                "first_user_observable_latency_ms"
            ),
        }


class TraceCheckpointStore:
    """Atomic active-trace checkpoints for process-restart recovery."""

    def __init__(self, root: str | Path | None = None) -> None:
        raw = str(root or os.getenv("CHROMIE_RUNTIME_TRACE_CHECKPOINT_DIR") or "").strip()
        self.root = Path(raw).expanduser().resolve() if raw else None
        if self.root is not None:
            (self.root / "active").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def write(self, snapshot: TraceSnapshot) -> str:
        if self.root is None:
            return ""
        trace_id = _token(snapshot.trace.get("trace_id"), "checkpoint trace_id")
        path = self.root / "active" / f"{trace_id}.json"
        _atomic_write_json(
            path,
            {
                "schema_version": TRACE_CHECKPOINT_SCHEMA_VERSION,
                "checkpointed_at": _iso(_utc_now()),
                "trace": snapshot.trace,
                "summary": snapshot.summary,
            },
        )
        return str(path)

    def remove(self, trace_id: str) -> None:
        if self.root is None:
            return
        (self.root / "active" / f"{trace_id}.json").unlink(missing_ok=True)

    def pending(self) -> list[tuple[Path, dict[str, Any]]]:
        if self.root is None:
            return []
        pending: list[tuple[Path, dict[str, Any]]] = []
        for path in sorted((self.root / "active").glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if int(payload.get("schema_version") or 0) != TRACE_CHECKPOINT_SCHEMA_VERSION:
                    raise ValueError("unsupported checkpoint schema")
                if not isinstance(payload.get("trace"), Mapping):
                    raise ValueError("checkpoint trace is missing")
                if not isinstance(payload.get("summary"), Mapping):
                    raise ValueError("checkpoint summary is missing")
            except Exception:
                self.archive(path, category="corrupt")
                continue
            pending.append((path, payload))
        return pending

    def archive(self, path: Path, *, category: str = "recovered") -> str:
        if self.root is None or not path.exists():
            return ""
        target_root = self.root / str(category or "recovered")
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / path.name
        if target.exists():
            target = target_root / f"{path.stem}-{uuid.uuid4().hex[:8]}{path.suffix}"
        os.replace(path, target)
        return str(target)


@dataclass
class _TraceItem:
    trace_id: str
    item_id: str
    parent_item_id: str | None
    name: str
    kind: str
    module: TraceModule
    operation: str
    started_at: datetime
    started_monotonic: float
    status: str = "unset"
    finished_at: datetime | None = None
    finished_monotonic: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    error: dict[str, str] | None = None

    def as_dict(self, *, now_wall: datetime, now_monotonic: float) -> dict[str, Any]:
        finished_wall = self.finished_at
        finished_mono = self.finished_monotonic
        active = finished_wall is None or finished_mono is None
        end_mono = now_monotonic if active else finished_mono
        duration_ms = max(0.0, (end_mono - self.started_monotonic) * 1000.0)
        payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "item_id": self.item_id,
            "parent_item_id": self.parent_item_id,
            "name": self.name,
            "kind": self.kind,
            "module": self.module.as_dict(),
            "operation": self.operation,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(finished_wall) if finished_wall else None,
            "duration_ms": round(duration_ms, 3),
            "attributes": dict(self.attributes),
            "links": list(self.links),
        }
        if active:
            payload["active"] = True
        if self.error:
            payload["error"] = dict(self.error)
        return payload


class RuntimeTrace:
    def __init__(
        self,
        *,
        policy: TracePolicy,
        correlations: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
        external_parent_item_id: str | None = None,
        sampling_reason: str = "configured",
    ) -> None:
        self.policy = policy
        self.trace_id = str(trace_id or _id("trace"))
        self.state = "active"
        self.started_at = _utc_now()
        self.started_monotonic = time.perf_counter()
        self.finished_at: datetime | None = None
        self.finished_monotonic: float | None = None
        self.correlations = _safe_mapping(correlations or {}, policy)
        self.attributes = _safe_mapping(attributes or {}, policy)
        self.external_parent_item_id = external_parent_item_id or None
        self.sampling_reason = str(sampling_reason or "configured")
        self._items: list[_TraceItem | dict[str, Any]] = []
        self._item_ids: set[str] = set()
        self._last_finished_child: dict[str | None, str] = {}
        self._lock = threading.RLock()
        self._finished_snapshot: TraceSnapshot | None = None
        self.dropped_items = 0

    def update_correlations(self, values: Mapping[str, Any]) -> None:
        safe = _safe_mapping(values, self.policy)
        with self._lock:
            for key, value in safe.items():
                if value not in (None, ""):
                    self.correlations[str(key)] = value

    def start_item(
        self,
        *,
        module: TraceModule,
        operation: str,
        kind: str,
        parent_item_id: str | None,
        name: str | None,
        attributes: Mapping[str, Any] | None,
        links: Sequence[Mapping[str, Any]] | None,
    ) -> _TraceItem | None:
        if self.state != "active" or self.policy.mode_for(module) == "off":
            return None
        with self._lock:
            if len(self._items) >= self.policy.max_items:
                self.dropped_items += 1
                return None
            resolved_parent = parent_item_id or self.external_parent_item_id
            normalized_links = _safe_links(links or [])
            previous = self._last_finished_child.get(resolved_parent)
            if previous and not any(
                link.get("relationship") == "follows_from"
                and link.get("item_id") == previous
                for link in normalized_links
            ):
                normalized_links.append(
                    {"relationship": "follows_from", "item_id": previous}
                )
            item = _TraceItem(
                trace_id=self.trace_id,
                item_id=_id("item"),
                parent_item_id=resolved_parent,
                name=str(name or f"{module.name}.{operation}"),
                kind=str(kind or "operation"),
                module=module,
                operation=_token(operation, "trace operation"),
                started_at=_utc_now(),
                started_monotonic=time.perf_counter(),
                attributes=_safe_mapping(attributes or {}, self.policy),
                links=normalized_links,
            )
            self._items.append(item)
            self._item_ids.add(item.item_id)
            return item

    def finish_item(
        self,
        item: _TraceItem,
        *,
        status: str,
        error: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            if item.finished_at is not None:
                return
            item.status = str(status or "ok")
            item.error = dict(error) if error else None
            item.finished_at = _utc_now()
            item.finished_monotonic = time.perf_counter()
            self._last_finished_child[item.parent_item_id] = item.item_id

    def set_attribute(self, item: _TraceItem, key: str, value: Any) -> None:
        with self._lock:
            if len(item.attributes) >= self.policy.max_attributes and key not in item.attributes:
                return
            item.attributes[str(key)] = _safe_value(value, self.policy, depth=0)

    def merge_fragment(self, fragment: Mapping[str, Any]) -> bool:
        if str(fragment.get("trace_id") or "") != self.trace_id:
            return False
        raw_items = fragment.get("items")
        if not isinstance(raw_items, list):
            return False
        merged = False
        with self._lock:
            for raw in raw_items:
                if not isinstance(raw, Mapping):
                    continue
                item_id = str(raw.get("item_id") or "")
                if not item_id or item_id in self._item_ids:
                    continue
                if len(self._items) >= self.policy.max_items:
                    self.dropped_items += 1
                    continue
                safe = _safe_value(dict(raw), self.policy, depth=0)
                if not isinstance(safe, dict):
                    continue
                self._items.append(safe)
                self._item_ids.add(item_id)
                merged = True
        return merged

    def snapshot(self, *, state: str | None = None) -> TraceSnapshot:
        now_wall = _utc_now()
        now_mono = time.perf_counter()
        with self._lock:
            items = [
                item.as_dict(now_wall=now_wall, now_monotonic=now_mono)
                if isinstance(item, _TraceItem)
                else dict(item)
                for item in self._items
            ]
            finished_at = self.finished_at
            end_mono = self.finished_monotonic or now_mono
            duration_ms = max(0.0, (end_mono - self.started_monotonic) * 1000.0)
            resolved_state = str(state or self.state)
            trace = {
                "schema_version": TRACE_SCHEMA_VERSION,
                "trace_id": self.trace_id,
                "state": resolved_state,
                "started_at": _iso(self.started_at),
                "finished_at": _iso(finished_at) if finished_at else None,
                "duration_ms": round(duration_ms, 3),
                "correlations": dict(self.correlations),
                "attributes": dict(self.attributes),
                "collection": {
                    "mode": self.policy.mode,
                    "coverage": self.policy.coverage,
                    "sampling_reason": self.sampling_reason,
                    "dropped_items": self.dropped_items,
                },
                "items": sorted(items, key=_item_sort_key),
            }
        return TraceSnapshot(trace=trace, summary=_summarize_trace(trace))

    def finish(self, *, state: str = "complete") -> TraceSnapshot:
        resolved_state = str(state or "complete")
        if resolved_state not in _TRACE_STATES - {"active", "finishing"}:
            raise ValueError(f"invalid final Runtime Trace state: {state!r}")
        with self._lock:
            if self._finished_snapshot is not None:
                return self._finished_snapshot
            self.state = "finishing"
            self.finished_at = _utc_now()
            self.finished_monotonic = time.perf_counter()
            self.state = resolved_state
            self._finished_snapshot = self.snapshot(state=resolved_state)
            return self._finished_snapshot


_current_trace: contextvars.ContextVar[RuntimeTrace | None] = contextvars.ContextVar(
    "chromie_runtime_trace", default=None
)
_current_item_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "chromie_runtime_trace_item", default=None
)


class TraceScope:
    def __init__(self, trace: RuntimeTrace | None) -> None:
        self.trace = trace
        self._trace_token: contextvars.Token | None = None
        self._item_token: contextvars.Token | None = None
        self._snapshot: TraceSnapshot | None = None

    @property
    def enabled(self) -> bool:
        return self.trace is not None

    @property
    def policy(self) -> TracePolicy:
        return self.trace.policy if self.trace is not None else TracePolicy()

    async def __aenter__(self) -> "TraceScope":
        self.__enter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.__exit__(exc_type, exc, tb)
        return False

    def __enter__(self) -> "TraceScope":
        if self.trace is not None:
            self._trace_token = _current_trace.set(self.trace)
            self._item_token = _current_item_id.set(
                self.trace.external_parent_item_id
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._item_token is not None:
            _current_item_id.reset(self._item_token)
            self._item_token = None
        if self._trace_token is not None:
            _current_trace.reset(self._trace_token)
            self._trace_token = None
        return False

    def finish(self, *, state: str = "complete") -> TraceSnapshot | None:
        if self.trace is None:
            return None
        self._snapshot = self.trace.finish(state=state)
        return self._snapshot

    def fragment(self) -> dict[str, Any]:
        if self.trace is None:
            return {}
        snapshot = self._snapshot or self.trace.snapshot(state="active")
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": snapshot.trace["trace_id"],
            "collection": snapshot.trace.get("collection") or {},
            "correlations": snapshot.trace.get("correlations") or {},
            "items": snapshot.trace.get("items") or [],
        }


class TraceSpan:
    def __init__(
        self,
        *,
        trace: RuntimeTrace | None,
        module: TraceModule,
        operation: str,
        kind: str,
        name: str | None,
        attributes: Mapping[str, Any] | None,
        links: Sequence[Mapping[str, Any]] | None,
    ) -> None:
        self.trace = trace
        self.module = module
        self.operation = operation
        self.kind = kind
        self.name = name
        self.attributes = attributes
        self.links = links
        self.item: _TraceItem | None = None
        self._item_token: contextvars.Token | None = None
        self._explicit_status: str | None = None

    @property
    def enabled(self) -> bool:
        return self.item is not None

    async def __aenter__(self) -> "TraceSpan":
        self.__enter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self.__exit__(exc_type, exc, tb)
        return False

    def __enter__(self) -> "TraceSpan":
        if self.trace is None:
            return self
        self.item = self.trace.start_item(
            module=self.module,
            operation=self.operation,
            kind=self.kind,
            parent_item_id=_current_item_id.get(),
            name=self.name,
            attributes=self.attributes,
            links=self.links,
        )
        if self.item is not None:
            self._item_token = _current_item_id.set(self.item.item_id)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._item_token is not None:
            _current_item_id.reset(self._item_token)
            self._item_token = None
        if self.trace is None or self.item is None:
            return False
        status = self._explicit_status or "ok"
        error = None
        if exc is not None:
            status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
            error = _error_payload(exc)
        self.trace.finish_item(self.item, status=status, error=error)
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        if self.trace is not None and self.item is not None:
            self.trace.set_attribute(self.item, key, value)

    def set_status(self, status: str) -> None:
        self._explicit_status = str(status or "ok")


class RuntimeTracer:
    def start_trace(
        self,
        *,
        correlations: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
        mode: str | None = None,
        sampling_reason: str = "configured",
    ) -> TraceScope:
        policy = TracePolicy.from_env(mode=mode)
        if policy.mode == "off":
            return TraceScope(None)
        return TraceScope(
            RuntimeTrace(
                policy=policy,
                correlations=correlations,
                attributes=attributes,
                sampling_reason=sampling_reason,
            )
        )

    def activate(self, trace: RuntimeTrace | None) -> TraceScope:
        """Activate an existing trace in the current sync/async context."""

        return TraceScope(trace)

    def continue_from_context(self, context: Mapping[str, Any] | None) -> TraceScope:
        carrier = (context or {}).get(TRACE_CARRIER_KEY)
        if not isinstance(carrier, Mapping):
            return TraceScope(None)
        if int(carrier.get("schema_version") or 0) != TRACE_CARRIER_SCHEMA_VERSION:
            return TraceScope(None)
        carrier_mode = str(carrier.get("mode") or "off").lower()
        local = TracePolicy.from_env()
        if carrier_mode not in _TRACE_MODES or local.mode == "off":
            return TraceScope(None)
        effective_value = min(_TRACE_MODES[carrier_mode], _TRACE_MODES[local.mode])
        effective_mode = next(
            name for name, value in _TRACE_MODES.items() if value == effective_value
        )
        if effective_mode == "off":
            return TraceScope(None)
        policy = TracePolicy(
            mode=effective_mode,
            module_allowlist=local.module_allowlist,
            debug_modules=local.debug_modules,
            max_items=local.max_items,
            max_attributes=local.max_attributes,
            max_attribute_chars=local.max_attribute_chars,
            emit_events=False,
            event_sample_rate=0.0,
            event_min_total_ms=0.0,
            event_min_first_observable_ms=0.0,
            event_always_emit_abandoned=False,
            coverage=str(carrier.get("coverage") or local.coverage),
        )
        return TraceScope(
            RuntimeTrace(
                policy=policy,
                correlations=carrier.get("correlations")
                if isinstance(carrier.get("correlations"), Mapping)
                else {},
                trace_id=str(carrier.get("trace_id") or "") or None,
                external_parent_item_id=str(carrier.get("parent_item_id") or "")
                or None,
                sampling_reason="distributed_continuation",
            )
        )

    def span(
        self,
        *,
        module: TraceModule,
        operation: str,
        kind: str = "operation",
        name: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        links: Sequence[Mapping[str, Any]] | None = None,
    ) -> TraceSpan:
        return TraceSpan(
            trace=_current_trace.get(),
            module=module,
            operation=operation,
            kind=kind,
            name=name,
            attributes=attributes,
            links=links,
        )

    def mark(
        self,
        *,
        module: TraceModule,
        name: str,
        kind: str = "event",
        attributes: Mapping[str, Any] | None = None,
        links: Sequence[Mapping[str, Any]] | None = None,
    ) -> str | None:
        trace = _current_trace.get()
        if trace is None:
            return None
        item = trace.start_item(
            module=module,
            operation=name,
            kind=kind,
            parent_item_id=_current_item_id.get(),
            name=name,
            attributes=attributes,
            links=links,
        )
        if item is None:
            return None
        trace.finish_item(item, status="ok")
        return item.item_id

    def inject_carrier(self, context: Mapping[str, Any] | None) -> dict[str, Any]:
        payload = dict(context or {})
        trace = _current_trace.get()
        if trace is None:
            return payload
        payload[TRACE_CARRIER_KEY] = {
            "schema_version": TRACE_CARRIER_SCHEMA_VERSION,
            "trace_id": trace.trace_id,
            "parent_item_id": _current_item_id.get(),
            "mode": trace.policy.mode,
            "coverage": trace.policy.coverage,
            "correlations": dict(trace.correlations),
        }
        return payload

    def attach_fragment(
        self,
        metadata: MutableMapping[str, Any],
        scope: TraceScope,
    ) -> None:
        fragment = scope.fragment()
        if fragment:
            metadata[TRACE_FRAGMENT_KEY] = fragment

    def merge_fragment_from_metadata(
        self,
        metadata: MutableMapping[str, Any] | None,
    ) -> bool:
        if not isinstance(metadata, MutableMapping):
            return False
        fragment = metadata.pop(TRACE_FRAGMENT_KEY, None)
        trace = _current_trace.get()
        if trace is None or not isinstance(fragment, Mapping):
            return False
        return trace.merge_fragment(fragment)

    def current_snapshot(self) -> TraceSnapshot | None:
        trace = _current_trace.get()
        return trace.snapshot(state="active") if trace is not None else None

    def persist_snapshot(
        self,
        snapshot: TraceSnapshot,
        *,
        event_subtype: str,
        producer: str,
        severity: str = "info",
        retention_reason: str = "configured",
        event_root: str | Path | None = None,
        trigger_root: str | Path | None = None,
    ) -> dict[str, Any]:
        from .runtime_events import persist_runtime_event

        return persist_runtime_event(
            event_type="chromie.interaction_trace",
            event_subtype=event_subtype,
            severity=severity,
            producer=producer,
            payloads={
                "trace.json": snapshot.trace,
                "trace-summary.json": snapshot.summary,
            },
            attributes={
                "trace_state": snapshot.trace.get("state"),
                "trace_mode": (snapshot.trace.get("collection") or {}).get("mode"),
                "coverage": (snapshot.trace.get("collection") or {}).get("coverage"),
                "item_count": snapshot.summary.get("item_count"),
                "total_duration_ms": snapshot.summary.get("total_duration_ms"),
                "first_user_observable_latency_ms": snapshot.summary.get(
                    "first_user_observable_latency_ms"
                ),
                "retention_reason": retention_reason,
            },
            correlations=snapshot.trace.get("correlations") or {},
            derivation={
                "latency_analysis_supported": True,
                "critical_path_analysis_supported": True,
                "scenario_candidate_eligible": True,
                "scenario_auto_promotion_allowed": False,
            },
            event_root=event_root,
            trigger_root=trigger_root,
        )


runtime_tracer = RuntimeTracer()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
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
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary_path.unlink(missing_ok=True)


def _safe_mapping(values: Mapping[str, Any], policy: TracePolicy) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in values.items():
        if len(output) >= policy.max_attributes:
            break
        output[str(key)] = _safe_value(value, policy, depth=0)
    return output


def _safe_value(value: Any, policy: TracePolicy, *, depth: int) -> Any:
    if depth >= 5:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[: policy.max_attribute_chars]
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if len(output) >= policy.max_attributes:
                break
            output[str(key)] = _safe_value(item, policy, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            _safe_value(item, policy, depth=depth + 1)
            for item in list(value)[: policy.max_attributes]
        ]
    if hasattr(value, "model_dump"):
        return _safe_value(
            value.model_dump(mode="json", exclude_none=True), policy, depth=depth + 1
        )
    return str(value)[: policy.max_attribute_chars]


def _safe_links(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for value in list(values)[:32]:
        relationship = str(value.get("relationship") or "").strip()
        item_id = str(value.get("item_id") or "").strip()
        if relationship and item_id:
            output.append({"relationship": relationship, "item_id": item_id})
    return output


def _error_payload(exc: BaseException) -> dict[str, str]:
    classification = str(getattr(exc, "failure_class", "") or "")
    if not classification and hasattr(exc, "metadata") and callable(exc.metadata):
        try:
            metadata = exc.metadata()
        except Exception:
            metadata = {}
        if isinstance(metadata, Mapping):
            classification = str(metadata.get("failure_class") or "")
    payload = {"type": type(exc).__name__}
    if classification:
        payload["classification"] = classification
    return payload


def _item_sort_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (str(item.get("started_at") or ""), str(item.get("item_id") or ""))


def _parse_timestamp(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000.0
    except ValueError:
        return None


def _union_duration(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    total = 0.0
    start, end = sorted(intervals)[0]
    for next_start, next_end in sorted(intervals)[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += max(0.0, end - start)
            start, end = next_start, next_end
    total += max(0.0, end - start)
    return total


def _summarize_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    items = [item for item in trace.get("items") or [] if isinstance(item, Mapping)]
    intervals: dict[str, tuple[float, float]] = {}
    parents: dict[str, str | None] = {}
    children: dict[str, list[str]] = {}
    for item in items:
        item_id = str(item.get("item_id") or "")
        start = _parse_timestamp(item.get("started_at"))
        end = _parse_timestamp(item.get("finished_at"))
        if item_id and start is not None:
            if end is None:
                duration = float(item.get("duration_ms") or 0.0)
                end = start + max(0.0, duration)
            intervals[item_id] = (start, max(start, end))
            parent = str(item.get("parent_item_id") or "") or None
            parents[item_id] = parent
            if parent:
                children.setdefault(parent, []).append(item_id)

    exclusive: dict[str, float] = {}
    for item_id, (start, end) in intervals.items():
        child_intervals: list[tuple[float, float]] = []
        for child_id in children.get(item_id, []):
            child = intervals.get(child_id)
            if child is None:
                continue
            child_intervals.append((max(start, child[0]), min(end, child[1])))
        exclusive[item_id] = max(0.0, (end - start) - _union_duration(child_intervals))

    module_values: dict[str, dict[str, Any]] = {}
    largest: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("item_id") or "")
        duration = float(item.get("duration_ms") or 0.0)
        module = item.get("module") if isinstance(item.get("module"), Mapping) else {}
        module_name = str(module.get("name") or "unknown")
        aggregate = module_values.setdefault(
            module_name,
            {
                "module": dict(module),
                "item_count": 0,
                "inclusive_duration_ms": 0.0,
                "exclusive_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "error_count": 0,
            },
        )
        aggregate["item_count"] += 1
        aggregate["inclusive_duration_ms"] += duration
        aggregate["exclusive_duration_ms"] += exclusive.get(item_id, duration)
        aggregate["max_duration_ms"] = max(aggregate["max_duration_ms"], duration)
        if str(item.get("status") or "") in {"error", "timeout", "cancelled"}:
            aggregate["error_count"] += 1
        largest.append(
            {
                "item_id": item_id,
                "name": item.get("name"),
                "module": module_name,
                "kind": item.get("kind"),
                "status": item.get("status"),
                "duration_ms": round(duration, 3),
                "exclusive_duration_ms": round(exclusive.get(item_id, duration), 3),
            }
        )

    for value in module_values.values():
        for key in ("inclusive_duration_ms", "exclusive_duration_ms", "max_duration_ms"):
            value[key] = round(float(value[key]), 3)

    trace_start = _parse_timestamp(trace.get("started_at"))
    observable_starts = [
        _parse_timestamp(item.get("started_at"))
        for item in items
        if str(item.get("kind") or "") == "user_observable"
    ]
    observable_starts = [value for value in observable_starts if value is not None]
    first_observable = (
        max(0.0, min(observable_starts) - trace_start)
        if trace_start is not None and observable_starts
        else None
    )

    critical_ids, critical_duration, max_parallel = _critical_path_by_intervals(
        items, intervals, parents
    )
    collection = trace.get("collection") if isinstance(trace.get("collection"), Mapping) else {}
    return {
        "schema_version": TRACE_SUMMARY_SCHEMA_VERSION,
        "trace_id": trace.get("trace_id"),
        "status": trace.get("state"),
        "total_duration_ms": round(float(trace.get("duration_ms") or 0.0), 3),
        "item_count": len(items),
        "dropped_item_count": int(collection.get("dropped_items") or 0),
        "critical_path_item_ids": critical_ids,
        "critical_path_duration_ms": round(critical_duration, 3),
        "critical_path_method": "deepest_active_latest_finish_v1",
        "largest_items": sorted(
            largest,
            key=lambda value: (
                float(value["duration_ms"]),
                float(value["exclusive_duration_ms"]),
            ),
            reverse=True,
        )[:10],
        "module_aggregates": sorted(
            module_values.values(),
            key=lambda value: float(value["exclusive_duration_ms"]),
            reverse=True,
        ),
        "first_user_observable_latency_ms": (
            round(first_observable, 3) if first_observable is not None else None
        ),
        "max_parallel_items": max_parallel,
        "coverage": collection.get("coverage") or "partial",
    }


def _is_descendant(
    candidate: str,
    ancestor: str,
    parents: Mapping[str, str | None],
) -> bool:
    seen: set[str] = set()
    current = parents.get(candidate)
    while current and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        current = parents.get(current)
    return False


def _critical_path_by_intervals(
    items: list[Mapping[str, Any]],
    intervals: Mapping[str, tuple[float, float]],
    parents: Mapping[str, str | None],
) -> tuple[list[str], float, int]:
    if not intervals:
        return [], 0.0, 0
    item_map = {str(item.get("item_id") or ""): item for item in items}
    boundaries = sorted({point for interval in intervals.values() for point in interval})
    if len(boundaries) < 2:
        return [], 0.0, 1

    depth_cache: dict[str, int] = {}

    def depth(item_id: str) -> int:
        if item_id in depth_cache:
            return depth_cache[item_id]
        seen: set[str] = set()
        current = item_id
        value = 0
        while current and current not in seen:
            seen.add(current)
            parent = parents.get(current)
            if not parent:
                break
            value += 1
            current = parent
        depth_cache[item_id] = value
        return value

    selected: list[str] = []
    duration = 0.0
    max_parallel = 0
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        midpoint = (start + end) / 2.0
        active = [
            item_id
            for item_id, (item_start, item_end) in intervals.items()
            if item_start <= midpoint < item_end
        ]
        if not active:
            continue
        active_set = set(active)
        active_leaves = [
            item_id
            for item_id in active
            if not any(
                candidate != item_id
                and _is_descendant(candidate, item_id, parents)
                for candidate in active_set
            )
        ]
        max_parallel = max(max_parallel, len(active_leaves))
        chosen = max(
            active_leaves or active,
            key=lambda item_id: (
                depth(item_id),
                intervals[item_id][1],
                float(item_map.get(item_id, {}).get("duration_ms") or 0.0),
            ),
        )
        if not selected or selected[-1] != chosen:
            selected.append(chosen)
        duration += end - start
    return selected, duration, max_parallel
