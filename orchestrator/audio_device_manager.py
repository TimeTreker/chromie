from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _sounddevice() -> Any:
    import sounddevice as sd

    return sd


def _parse_device(value: str | None) -> int | str | None:
    if value is None or value == "" or value.lower() in {"none", "default", "auto"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


class AudioDeviceManager:
    """Small host-side audio device resolver.

    Keep this on host. It avoids putting microphone/speaker/PipeWire/ALSA setup
    inside Docker.
    """

    def __init__(self):
        self.input_device = _parse_device(os.getenv("ORCH_INPUT_DEVICE"))
        self.output_device = _parse_device(os.getenv("ORCH_OUTPUT_DEVICE"))

    def _query(self, device: int | str | None, kind: str) -> dict[str, Any]:
        sd = _sounddevice()
        try:
            info = sd.query_devices(device=device, kind=kind)
        except Exception as exc:
            logger.warning("Could not query %s audio device %r: %s; using defaults", kind, device, exc)
            info = sd.query_devices(kind=kind)
        return dict(info)

    def get_input_params(self) -> dict[str, Any]:
        info = self._query(self.input_device, "input")
        rate = int(float(os.getenv("ORCH_INPUT_RATE") or info.get("default_samplerate") or 48000))
        channels = int(os.getenv("ORCH_INPUT_CHANNELS", "1"))
        block_ms = int(os.getenv("ORCH_INPUT_BLOCK_MS", "30"))
        blocksize = int(os.getenv("ORCH_INPUT_BLOCKSIZE", "0"))
        if blocksize <= 0:
            blocksize = max(1, int(rate * block_ms / 1000))
        return {
            "name": info.get("name", "default input"),
            "device": self.input_device,
            "rate": rate,
            "channels": channels,
            "blocksize": blocksize,
            "block_ms": block_ms,
            "latency": os.getenv("ORCH_INPUT_LATENCY", "low"),
        }

    def get_output_params(self) -> dict[str, Any]:
        info = self._query(self.output_device, "output")
        rate = int(float(os.getenv("ORCH_OUTPUT_RATE") or info.get("default_samplerate") or 48000))
        channels = int(os.getenv("ORCH_OUTPUT_CHANNELS", "2"))
        block_ms = int(os.getenv("ORCH_OUTPUT_BLOCK_MS", "30"))
        blocksize = int(os.getenv("ORCH_OUTPUT_BLOCKSIZE", "0"))
        if blocksize <= 0:
            blocksize = 0
        return {
            "name": info.get("name", "default output"),
            "device": self.output_device,
            "rate": rate,
            "channels": channels,
            "blocksize": blocksize,
            "block_ms": block_ms,
            "latency": os.getenv("ORCH_OUTPUT_LATENCY", "low"),
        }

    def close(self) -> None:
        return None
