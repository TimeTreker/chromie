"""Typed policy configuration for shared runtime observability utilities."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    return str(values.get(name, default) or "").strip()


def _boolean(values: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(str(values.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _floating(
    values: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(str(values.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _csv(values: Mapping[str, str], name: str) -> frozenset[str]:
    return frozenset(
        item.strip() for item in str(values.get(name) or "").split(",") if item.strip()
    )


@dataclass(frozen=True)
class RuntimePolicySettings:
    trace_mode: str = "off"
    trace_modules: frozenset[str] = frozenset()
    trace_debug_modules: frozenset[str] = frozenset()
    trace_max_items: int = 1000
    trace_max_attributes: int = 32
    trace_max_attribute_chars: int = 512
    trace_emit_events: bool = False
    trace_event_sample_rate: float = 1.0
    trace_event_min_total_ms: float = 0.0
    trace_event_min_first_observable_ms: float = 0.0
    trace_event_always_emit_abandoned: bool = True
    trace_coverage: str = "partial"
    trace_checkpoint_dir: str = ""
    resource_sampling_mode: str = "off"
    accelerator_sampling_mode: str = "off"
    accelerator_provider: str = "auto"
    accelerator_timeout_ms: int = 1000
    accelerator_min_interval_s: float = 5.0
    runtime_event_root: str = ""
    data_loop_trigger_root: str = ""
    environment: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "RuntimePolicySettings":
        source = dict(os.environ if values is None else values)
        mode = _text(source, "CHROMIE_RUNTIME_TRACE_MODE", "off").lower()
        if mode not in {"off", "basic", "debug"}:
            mode = "off"
        resource_mode = _text(
            source, "CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING", "off"
        ).lower()
        if resource_mode not in {"off", "session", "periodic"}:
            resource_mode = "off"
        accelerator_mode = _text(
            source, "CHROMIE_RUNTIME_TRACE_ACCELERATOR_SAMPLING", "off"
        ).lower()
        if accelerator_mode not in {"off", "session", "periodic"}:
            accelerator_mode = "off"
        provider = _text(
            source, "CHROMIE_RUNTIME_TRACE_ACCELERATOR_PROVIDER", "auto"
        ).lower()
        if provider not in {"auto", "off", "nvidia_smi"}:
            provider = "auto"
        return cls(
            trace_mode=mode,
            trace_modules=_csv(source, "CHROMIE_RUNTIME_TRACE_MODULES"),
            trace_debug_modules=_csv(source, "CHROMIE_RUNTIME_TRACE_DEBUG_MODULES"),
            trace_max_items=_integer(
                source, "CHROMIE_RUNTIME_TRACE_MAX_ITEMS", 1000, 16, 10000
            ),
            trace_max_attributes=_integer(
                source, "CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTES", 32, 4, 256
            ),
            trace_max_attribute_chars=_integer(
                source,
                "CHROMIE_RUNTIME_TRACE_MAX_ATTRIBUTE_CHARS",
                512,
                64,
                8192,
            ),
            trace_emit_events=_boolean(
                source, "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS", False
            ),
            trace_event_sample_rate=_floating(
                source,
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE",
                1.0,
                0.0,
                1.0,
            ),
            trace_event_min_total_ms=_floating(
                source,
                "CHROMIE_RUNTIME_TRACE_EVENT_MIN_TOTAL_MS",
                0.0,
                0.0,
                86400000.0,
            ),
            trace_event_min_first_observable_ms=_floating(
                source,
                "CHROMIE_RUNTIME_TRACE_EVENT_MIN_FIRST_OBSERVABLE_MS",
                0.0,
                0.0,
                86400000.0,
            ),
            trace_event_always_emit_abandoned=_boolean(
                source,
                "CHROMIE_RUNTIME_TRACE_EVENT_ALWAYS_EMIT_ABANDONED",
                True,
            ),
            trace_coverage=_text(
                source, "CHROMIE_RUNTIME_TRACE_COVERAGE", "partial"
            )
            or "partial",
            trace_checkpoint_dir=_text(
                source, "CHROMIE_RUNTIME_TRACE_CHECKPOINT_DIR"
            ),
            resource_sampling_mode=resource_mode,
            accelerator_sampling_mode=accelerator_mode,
            accelerator_provider=provider,
            accelerator_timeout_ms=_integer(
                source,
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_TIMEOUT_MS",
                1000,
                50,
                30000,
            ),
            accelerator_min_interval_s=_floating(
                source,
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_MIN_INTERVAL_S",
                5.0,
                0.0,
                3600.0,
            ),
            runtime_event_root=_text(source, "CHROMIE_RUNTIME_EVENT_ROOT"),
            data_loop_trigger_root=_text(source, "CHROMIE_DATA_LOOP_TRIGGER_ROOT"),
            environment=source,
        )

    def configured_path(
        self, value: str | Path | None, *setting_names: str
    ) -> Path | None:
        raw = str(value or "").strip()
        if not raw:
            for name in setting_names:
                raw = str(getattr(self, name) or "").strip()
                if raw:
                    break
        return Path(raw).expanduser().resolve() if raw else None

    def color_value(self, name: str, fallback_name: str | None = None) -> str | None:
        value = self.environment.get(name)
        if value is None and fallback_name:
            value = self.environment.get(fallback_name)
        return value
