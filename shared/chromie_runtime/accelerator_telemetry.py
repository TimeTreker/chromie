"""Non-blocking accelerator telemetry for Runtime Trace.

The realtime event loop never invokes accelerator tools directly. Collection is
performed in a worker thread behind a bounded timeout and cached so session
finalization can attach the last truthful observation without blocking.
"""
from __future__ import annotations

import asyncio
import csv
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .runtime_trace import TraceModule

ACCELERATOR_SAMPLE_MODULE = TraceModule(
    name="chromie.runtime.accelerator",
    component_type="resource_sampler",
    implementation="AcceleratorTelemetrySampler",
)

_VALID_MODES = {"off", "session", "periodic"}
_VALID_PROVIDERS = {"auto", "nvidia_smi", "off"}
_NVIDIA_FIELDS = (
    "index",
    "uuid",
    "name",
    "utilization.gpu",
    "utilization.memory",
    "memory.total",
    "memory.used",
    "memory.free",
    "temperature.gpu",
    "power.draw",
)


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


def _optional_number(value: Any, *, integer: bool = False) -> int | float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {
        "n/a",
        "na",
        "not supported",
        "[not supported]",
        "[n/a]",
    }:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    return int(numeric) if integer else round(numeric, 3)


def parse_nvidia_smi_csv(text: str) -> list[dict[str, Any]]:
    """Parse the stable no-units CSV requested by the NVIDIA provider."""

    devices: list[dict[str, Any]] = []
    reader = csv.reader(line for line in str(text or "").splitlines() if line.strip())
    for row in reader:
        if len(row) != len(_NVIDIA_FIELDS):
            continue
        raw = {key: value.strip() for key, value in zip(_NVIDIA_FIELDS, row)}
        total_mib = _optional_number(raw["memory.total"])
        used_mib = _optional_number(raw["memory.used"])
        free_mib = _optional_number(raw["memory.free"])
        device: dict[str, Any] = {
            "index": _optional_number(raw["index"], integer=True),
            "uuid": raw["uuid"],
            "name": raw["name"],
            "gpu_utilization_percent": _optional_number(raw["utilization.gpu"]),
            "memory_utilization_percent": _optional_number(
                raw["utilization.memory"]
            ),
            "memory_total_bytes": (
                int(float(total_mib) * 1024 * 1024) if total_mib is not None else None
            ),
            "memory_used_bytes": (
                int(float(used_mib) * 1024 * 1024) if used_mib is not None else None
            ),
            "memory_free_bytes": (
                int(float(free_mib) * 1024 * 1024) if free_mib is not None else None
            ),
            "temperature_c": _optional_number(raw["temperature.gpu"]),
            "power_w": _optional_number(raw["power.draw"]),
        }
        device = {key: value for key, value in device.items() if value is not None}
        if device.get("uuid") or device.get("name"):
            devices.append(device)
    return devices


def _nvidia_smi_collect(timeout_s: float) -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {
            "available": False,
            "provider": "nvidia_smi",
            "provider_status": "executable_not_found",
        }
    command = [
        executable,
        f"--query-gpu={','.join(_NVIDIA_FIELDS)}",
        "--format=csv,noheader,nounits",
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.05, timeout_s),
            env={**os.environ, "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "provider": "nvidia_smi",
            "provider_status": "timeout",
            "collection_duration_ms": round(
                (time.perf_counter() - started) * 1000.0, 3
            ),
        }
    except OSError as exc:
        return {
            "available": False,
            "provider": "nvidia_smi",
            "provider_status": type(exc).__name__,
            "collection_duration_ms": round(
                (time.perf_counter() - started) * 1000.0, 3
            ),
        }
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    if completed.returncode != 0:
        return {
            "available": False,
            "provider": "nvidia_smi",
            "provider_status": f"exit_{completed.returncode}",
            "collection_duration_ms": duration_ms,
        }
    devices = parse_nvidia_smi_csv(completed.stdout)
    if not devices:
        return {
            "available": False,
            "provider": "nvidia_smi",
            "provider_status": "no_devices",
            "collection_duration_ms": duration_ms,
        }
    return {
        "available": True,
        "provider": "nvidia_smi",
        "provider_status": "ok",
        "collection_duration_ms": duration_ms,
        "devices": devices,
        **_accelerator_aggregates(devices),
    }


def _accelerator_aggregates(devices: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def values(name: str) -> list[float]:
        output: list[float] = []
        for device in devices:
            value = device.get(name)
            if isinstance(value, (int, float)):
                output.append(float(value))
        return output

    payload: dict[str, Any] = {"accelerator_device_count": len(devices)}
    gpu = values("gpu_utilization_percent")
    memory = values("memory_utilization_percent")
    temperature = values("temperature_c")
    power = values("power_w")
    used = values("memory_used_bytes")
    total = values("memory_total_bytes")
    if gpu:
        payload["accelerator_gpu_utilization_max_percent"] = round(max(gpu), 3)
        payload["accelerator_gpu_utilization_mean_percent"] = round(
            sum(gpu) / len(gpu), 3
        )
    if memory:
        payload["accelerator_memory_utilization_max_percent"] = round(
            max(memory), 3
        )
    if temperature:
        payload["accelerator_temperature_max_c"] = round(max(temperature), 3)
    if power:
        payload["accelerator_power_total_w"] = round(sum(power), 3)
    if used:
        payload["accelerator_memory_used_total_bytes"] = int(sum(used))
    if total:
        payload["accelerator_memory_total_bytes"] = int(sum(total))
        if used and sum(total) > 0:
            payload["accelerator_memory_used_percent"] = round(
                sum(used) / sum(total) * 100.0, 3
            )
    return payload


@dataclass(frozen=True)
class AcceleratorTelemetryConfig:
    mode: str = "off"
    provider: str = "auto"
    timeout_ms: int = 1000
    min_interval_s: float = 5.0

    @classmethod
    def from_env(cls) -> "AcceleratorTelemetryConfig":
        mode = str(
            os.getenv("CHROMIE_RUNTIME_TRACE_ACCELERATOR_SAMPLING", "off")
        ).strip().lower()
        provider = str(
            os.getenv("CHROMIE_RUNTIME_TRACE_ACCELERATOR_PROVIDER", "auto")
        ).strip().lower()
        return cls(
            mode=mode if mode in _VALID_MODES else "off",
            provider=provider if provider in _VALID_PROVIDERS else "auto",
            timeout_ms=_env_int(
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_TIMEOUT_MS", 1000, 50, 30000
            ),
            min_interval_s=_env_float(
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_MIN_INTERVAL_S",
                5.0,
                0.0,
                3600.0,
            ),
        )


class AcceleratorTelemetrySampler:
    """Asynchronously collect and cache accelerator telemetry."""

    def __init__(
        self,
        config: AcceleratorTelemetryConfig | None = None,
        *,
        collector: Callable[[float], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or AcceleratorTelemetryConfig.from_env()
        self._collector = collector or _nvidia_smi_collect
        self._lock = asyncio.Lock()
        self._cache_lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._latest_monotonic: float | None = None

    @classmethod
    def from_env(cls) -> "AcceleratorTelemetrySampler":
        return cls(AcceleratorTelemetryConfig.from_env())

    @property
    def enabled(self) -> bool:
        return self.config.mode != "off" and self.config.provider != "off"

    def should_sample(self, reason: str) -> bool:
        if not self.enabled:
            return False
        if self.config.mode == "periodic":
            return True
        return reason in {"session_start", "session_finish", "session_abandoned"}

    async def _collect(self, timeout_s: float) -> dict[str, Any]:
        """Run the blocking provider without owning the loop's default executor.

        A timed-out ``asyncio.to_thread`` call keeps its worker alive, and
        ``asyncio.run`` waits for default-executor workers during shutdown. A
        stuck telemetry utility could therefore delay Orchestrator shutdown for
        minutes even though sampling itself had already timed out. The provider
        has its own subprocess timeout; an owned daemon thread adds a final
        lifecycle boundary without making shutdown depend on that provider.
        """

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        def complete(
            payload: dict[str, Any] | None,
            error: BaseException | None,
        ) -> None:
            if future.done():
                return
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(dict(payload or {}))

        def collect() -> None:
            payload: dict[str, Any] | None = None
            error: BaseException | None = None
            try:
                payload = self._collector(timeout_s)
            except BaseException as exc:  # propagated and normalized by sample()
                error = exc
            try:
                loop.call_soon_threadsafe(complete, payload, error)
            except RuntimeError:
                # The bounded caller already returned and its loop has closed.
                return

        threading.Thread(
            target=collect,
            name="chromie-accelerator-telemetry",
            daemon=True,
        ).start()
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout_s + 0.25)

    async def sample(self, *, reason: str, force: bool = False) -> dict[str, Any]:
        if not self.should_sample(reason):
            return {}
        async with self._lock:
            now = time.monotonic()
            with self._cache_lock:
                latest_time = self._latest_monotonic
            if (
                not force
                and latest_time is not None
                and now - latest_time < self.config.min_interval_s
            ):
                return self.cached_sample(reason=reason)
            timeout_s = self.config.timeout_ms / 1000.0
            try:
                payload = await self._collect(timeout_s)
            except TimeoutError:
                payload = {
                    "available": False,
                    "provider": self.config.provider,
                    "provider_status": "worker_timeout",
                }
            except Exception as exc:
                payload = {
                    "available": False,
                    "provider": self.config.provider,
                    "provider_status": type(exc).__name__,
                }
            normalized = dict(payload or {})
            normalized["sample_reason"] = str(reason or "unspecified")
            normalized["sample_cached"] = False
            normalized.setdefault(
                "provider",
                "nvidia_smi" if self.config.provider == "auto" else self.config.provider,
            )
            with self._cache_lock:
                self._latest = normalized
                self._latest_monotonic = time.monotonic()
            return dict(normalized)

    def cached_sample(self, *, reason: str) -> dict[str, Any]:
        with self._cache_lock:
            payload = dict(self._latest)
            sampled_at = self._latest_monotonic
        if not payload or sampled_at is None:
            return {}
        payload["sample_reason"] = str(reason or "unspecified")
        payload["sample_cached"] = True
        payload["sample_age_ms"] = round(
            max(0.0, (time.monotonic() - sampled_at) * 1000.0), 3
        )
        return payload
