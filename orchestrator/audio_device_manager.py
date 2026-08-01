from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator
from typing import Any


_PIPEWIRE_DEFAULT_DIRECTIONS = {
    "default.audio.source": "input",
    "default.configured.audio.source": "input",
    "default.audio.sink": "output",
    "default.configured.audio.sink": "output",
}
_PIPEWIRE_KEY_RE = re.compile(r"\bkey:'([^']+)'")
_PIPEWIRE_VALUE_RE = re.compile(r"\bvalue:'(.*?)'(?:\s+type:|$)")


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


def _system_default_device(sd: Any, kind: str) -> int | str:
    """Return sounddevice's current OS-selected device for one direction."""

    pair = sd.default.device
    if isinstance(pair, (int, str)):
        selected = pair
    else:
        try:
            selected = pair[0 if kind == "input" else 1]
        except (IndexError, KeyError, TypeError):
            selected = pair
    if selected is None or selected == -1:
        raise RuntimeError(f"No system-default {kind} audio device is available")
    return selected


class AudioDeviceManager:
    """Small host-side audio device resolver.

    Keep this on host. It avoids putting microphone/speaker/PipeWire/ALSA setup
    inside Docker.
    """

    def __init__(self):
        self.input_device = _parse_device(os.getenv("ORCH_INPUT_DEVICE"))
        self.output_device = _parse_device(os.getenv("ORCH_OUTPUT_DEVICE"))

    def follows_system_default(self, kind: str) -> bool:
        if kind == "input":
            return self.input_device is None
        if kind == "output":
            return self.output_device is None
        raise ValueError(f"Unknown audio direction: {kind!r}")

    @staticmethod
    def device_params_changed(
        current: dict[str, Any],
        candidate: dict[str, Any],
    ) -> bool:
        """Compare the stream-relevant identity of two resolved devices."""

        keys = (
            "device",
            "name",
            "rate",
            "channels",
            "blocksize",
            "latency",
        )
        return any(current.get(key) != candidate.get(key) for key in keys)

    @staticmethod
    def parse_pipewire_default_update(
        line: str,
    ) -> tuple[str, str, str | None] | None:
        """Parse one read-only ``pw-metadata`` default-device update."""

        key_match = _PIPEWIRE_KEY_RE.search(line)
        if key_match is None:
            return None
        key = key_match.group(1)
        kind = _PIPEWIRE_DEFAULT_DIRECTIONS.get(key)
        if kind is None:
            return None
        value_match = _PIPEWIRE_VALUE_RE.search(line)
        value = value_match.group(1) if value_match is not None else None
        return kind, key, value

    async def watch_system_default_changes(self) -> AsyncIterator[str]:
        """Yield input/output when PipeWire reports an OS-default change.

        PortAudio default polling remains the portable fallback. PipeWire
        metadata is also observed because its stable ``default`` PortAudio
        device can conceal a USB/Bluetooth node change behind the same index.
        This command is read-only and never changes a route or device setting.
        """

        try:
            process = await asyncio.create_subprocess_exec(
                "pw-metadata",
                "-m",
                "-n",
                "default",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError):
            return
        stdout = process.stdout
        if stdout is None:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            return

        observed: dict[str, str | None] = {}
        try:
            # ``pw-metadata --monitor`` emits the current state first. Consume
            # that initial burst so startup does not look like a device change.
            while True:
                try:
                    raw_line = await asyncio.wait_for(
                        stdout.readline(),
                        timeout=0.25,
                    )
                except asyncio.TimeoutError:
                    break
                if not raw_line:
                    return
                parsed = self.parse_pipewire_default_update(
                    raw_line.decode("utf-8", errors="replace")
                )
                if parsed is not None:
                    _, key, value = parsed
                    observed[key] = value

            while True:
                raw_line = await stdout.readline()
                if not raw_line:
                    return
                parsed = self.parse_pipewire_default_update(
                    raw_line.decode("utf-8", errors="replace")
                )
                if parsed is None:
                    continue
                kind, key, value = parsed
                previous = observed.get(key)
                observed[key] = value
                if previous != value:
                    yield kind
        finally:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()

    def _resolve(
        self,
        device: int | str | None,
        kind: str,
    ) -> tuple[int | str, dict[str, Any], str]:
        sd = _sounddevice()
        explicit = device is not None
        selected = device if explicit else _system_default_device(sd, kind)
        try:
            info = dict(sd.query_devices(device=selected, kind=kind))
        except Exception as exc:
            authority = "configured" if explicit else "system-default"
            raise RuntimeError(
                f"The {authority} {kind} audio device {selected!r} is unavailable: {exc}"
            ) from exc
        return selected, info, "configured" if explicit else "system_default"

    @staticmethod
    def _validate(
        sd: Any,
        *,
        device: int | str,
        info: dict[str, Any],
        kind: str,
        rate: int,
        channels: int,
    ) -> None:
        channel_key = f"max_{kind}_channels"
        try:
            available_channels = int(info.get(channel_key) or 0)
        except (TypeError, ValueError):
            available_channels = 0
        if channels <= 0 or available_channels < channels:
            raise RuntimeError(
                f"Selected {kind} audio device {device!r} provides "
                f"{available_channels} channel(s), but {channels} are required"
            )
        checker = (
            sd.check_input_settings
            if kind == "input"
            else sd.check_output_settings
        )
        dtype = "float32" if kind == "input" else "int16"
        try:
            checker(
                device=device,
                channels=channels,
                dtype=dtype,
                samplerate=rate,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Selected {kind} audio device {device!r} rejected "
                f"{channels} channel(s) at {rate} Hz: {exc}"
            ) from exc

    def get_input_params(self) -> dict[str, Any]:
        sd = _sounddevice()
        device, info, selection_source = self._resolve(self.input_device, "input")
        rate = int(float(os.getenv("ORCH_INPUT_RATE") or info.get("default_samplerate") or 48000))
        channels = int(os.getenv("ORCH_INPUT_CHANNELS", "1"))
        self._validate(
            sd,
            device=device,
            info=info,
            kind="input",
            rate=rate,
            channels=channels,
        )
        block_ms = int(os.getenv("ORCH_INPUT_BLOCK_MS", "30"))
        blocksize = int(os.getenv("ORCH_INPUT_BLOCKSIZE", "0"))
        if blocksize <= 0:
            blocksize = max(1, int(rate * block_ms / 1000))
        return {
            "name": info.get("name", "default input"),
            "device": device,
            "selection_source": selection_source,
            "rate": rate,
            "channels": channels,
            "blocksize": blocksize,
            "block_ms": block_ms,
            "latency": os.getenv("ORCH_INPUT_LATENCY", "low"),
        }

    def get_output_params(self) -> dict[str, Any]:
        sd = _sounddevice()
        device, info, selection_source = self._resolve(self.output_device, "output")
        rate = int(float(os.getenv("ORCH_OUTPUT_RATE") or info.get("default_samplerate") or 48000))
        channels = int(os.getenv("ORCH_OUTPUT_CHANNELS", "2"))
        self._validate(
            sd,
            device=device,
            info=info,
            kind="output",
            rate=rate,
            channels=channels,
        )
        block_ms = int(os.getenv("ORCH_OUTPUT_BLOCK_MS", "30"))
        blocksize = int(os.getenv("ORCH_OUTPUT_BLOCKSIZE", "0"))
        if blocksize <= 0:
            blocksize = 0
        return {
            "name": info.get("name", "default output"),
            "device": device,
            "selection_source": selection_source,
            "rate": rate,
            "channels": channels,
            "blocksize": blocksize,
            "block_ms": block_ms,
            "latency": os.getenv("ORCH_OUTPUT_LATENCY", "low"),
        }

    def close(self) -> None:
        return None
