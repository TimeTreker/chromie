from __future__ import annotations

import asyncio
import array
import contextlib
import json
import shutil
import subprocess
import sys
import threading
import time
import tempfile
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class AudioFixture:
    text: str
    pcm16: bytes
    sample_rate: int
    channels: int
    path: Path


def write_pcm16_wav(
    path: Path,
    *,
    pcm16: bytes,
    sample_rate: int,
    channels: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm16)


def _safe_fixture_name(index: int, text: str) -> str:
    words = ["".join(ch for ch in word.casefold() if ch.isalnum()) for word in text.split()]
    slug = "-".join(item for item in words if item)[:48] or "utterance"
    return f"{index:02d}-{slug}.wav"


async def _generate_fixtures_async(
    *,
    texts: Iterable[str],
    output_dir: Path,
    tts_url: str,
    speaker_id: str,
    default_sample_rate: int,
    timeout_s: float,
) -> dict[str, AudioFixture]:
    from orchestrator.clients.tts_client import TTSClient

    client = TTSClient(tts_url, default_sample_rate=default_sample_rate)
    fixtures: dict[str, AudioFixture] = {}
    for index, text in enumerate(dict.fromkeys(texts), start=1):
        pcm16, sample_rate = await asyncio.wait_for(
            client.synthesize(
                text=text,
                speaker_id=speaker_id,
                request_id=f"voice-input-{uuid.uuid4().hex}",
            ),
            timeout=timeout_s,
        )
        if not pcm16:
            raise RuntimeError(f"TTS generated no audio for acceptance prompt: {text!r}")
        path = output_dir / _safe_fixture_name(index, text)
        write_pcm16_wav(
            path,
            pcm16=pcm16,
            sample_rate=sample_rate,
            channels=1,
        )
        fixtures[text] = AudioFixture(
            text=text,
            pcm16=pcm16,
            sample_rate=sample_rate,
            channels=1,
            path=path,
        )
    return fixtures


def generate_tts_fixtures(
    *,
    texts: Iterable[str],
    output_dir: Path,
    tts_url: str,
    speaker_id: str,
    default_sample_rate: int = 44100,
    timeout_s: float = 180.0,
) -> dict[str, AudioFixture]:
    return asyncio.run(
        _generate_fixtures_async(
            texts=texts,
            output_dir=output_dir,
            tts_url=tts_url,
            speaker_id=speaker_id,
            default_sample_rate=default_sample_rate,
            timeout_s=timeout_s,
        )
    )


def _parse_sounddevice_device(value: str | None) -> int | str | None:
    if value is None or value == "" or value.lower() in {"none", "default", "auto"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


HOST_AUDIO_PLAYERS = ("pw-play", "paplay", "aplay")


def _scale_pcm16(pcm16: bytes, gain: float) -> bytes:
    if gain == 1.0:
        return pcm16
    samples = array.array("h")
    samples.frombytes(pcm16)
    if sys.byteorder != "little":
        samples.byteswap()
    for index, sample in enumerate(samples):
        scaled = int(round(sample * gain))
        samples[index] = max(-32768, min(32767, scaled))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


@contextlib.contextmanager
def _fixture_path_for_playback(fixture: AudioFixture, playback_gain: float):
    if playback_gain == 1.0:
        yield fixture.path
        return
    with tempfile.TemporaryDirectory(prefix="chromie-acoustic-") as temp_dir:
        path = Path(temp_dir) / fixture.path.name
        write_pcm16_wav(
            path,
            pcm16=_scale_pcm16(fixture.pcm16, playback_gain),
            sample_rate=fixture.sample_rate,
            channels=fixture.channels,
        )
        yield path


class HostSpeakerPlayer:
    """Play generated fixtures through a host audio output."""

    def __init__(
        self,
        *,
        device: str | None = None,
        channels: int = 2,
        playback_gain: float = 1.0,
        player: str = "auto",
        target: str | None = None,
    ) -> None:
        self.device = _parse_sounddevice_device(device)
        self.channels = max(1, channels)
        self.playback_gain = max(0.0, playback_gain)
        self.player = player
        self.target = target or None

    @staticmethod
    def available_backend() -> str | None:
        for name in HOST_AUDIO_PLAYERS:
            if shutil.which(name):
                return name
        return None

    def play(self, fixture: AudioFixture, *, timeout_s: float = 60.0) -> None:
        errors: list[str] = []
        if self.player == "auto" or self.player in HOST_AUDIO_PLAYERS:
            played, backend_errors = self._play_with_host_tool(
                fixture,
                timeout_s=timeout_s,
            )
            if played:
                return
            errors.extend(backend_errors)
            if self.player != "auto":
                raise RuntimeError("; ".join(errors))

        if self.player in {"auto", "sounddevice"}:
            try:
                self._play_with_sounddevice(fixture, timeout_s=timeout_s)
                return
            except Exception as exc:
                errors.append(str(exc))

        if not errors:
            errors.append(f"Unknown acoustic playback backend: {self.player!r}")
        raise RuntimeError(
            f"Failed to play {fixture.path} through host audio: "
            + "; ".join(errors)
        )

    def _play_with_host_tool(
        self,
        fixture: AudioFixture,
        *,
        timeout_s: float,
    ) -> tuple[bool, list[str]]:
        names = HOST_AUDIO_PLAYERS if self.player == "auto" else (self.player,)
        candidates = [
            (name, executable)
            for name in names
            if (executable := shutil.which(name)) is not None
        ]
        if not candidates:
            return False, [f"No host audio player found for {', '.join(names)}"]

        errors: list[str] = []
        with _fixture_path_for_playback(fixture, self.playback_gain) as path:
            for name, executable in candidates:
                command = [executable]
                if name == "pw-play":
                    if self.target:
                        command.extend(["--target", self.target])
                    command.append(str(path))
                elif name == "paplay":
                    if self.target:
                        command.append(f"--device={self.target}")
                    command.append(str(path))
                else:
                    command.append(str(path))
                try:
                    completed = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                    )
                except subprocess.TimeoutExpired:
                    errors.append(f"{name} timed out after {timeout_s:.1f}s")
                    continue
                if completed.returncode == 0:
                    return True, []
                detail = (completed.stderr or completed.stdout or "").strip()
                errors.append(
                    f"{name} exited {completed.returncode}"
                    + (f": {detail}" if detail else "")
                )
        return False, errors

    def _play_with_sounddevice(
        self,
        fixture: AudioFixture,
        *,
        timeout_s: float,
    ) -> None:
        import numpy as np
        import sounddevice as sd

        samples = np.frombuffer(fixture.pcm16, dtype=np.int16).astype(np.float32)
        if fixture.channels > 1:
            samples = samples.reshape(-1, fixture.channels).mean(axis=1)
        samples = samples / 32768.0
        if self.playback_gain != 1.0:
            samples = np.clip(samples * self.playback_gain, -1.0, 1.0)
        if self.channels > 1:
            samples = np.column_stack([samples] * self.channels)

        error: list[BaseException] = []

        def run() -> None:
            try:
                sd.play(
                    samples,
                    samplerate=fixture.sample_rate,
                    device=self.device,
                    blocking=True,
                )
            except BaseException as exc:  # pragma: no cover - defensive handoff
                error.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            sd.stop()
            raise TimeoutError(
                f"Timed out playing {fixture.path} through sounddevice output "
                f"{self.device!r}"
            )
        if error:
            raise RuntimeError(
                f"Failed to play {fixture.path} through sounddevice output "
                f"{self.device!r}: {error[0]}"
            )


class PulseVirtualMicrophone:
    """Temporary PulseAudio/PipeWire-Pulse null sink and monitor source."""

    def __init__(self, sink_name: str = "chromie_voice_test") -> None:
        self.sink_name = sink_name
        self.source_name = f"{sink_name}.monitor"
        self.module_id: str | None = None
        self.node_id: int | None = None
        self.backend: str | None = None

    @staticmethod
    def available_backend() -> str | None:
        if all(shutil.which(name) for name in ("pactl", "paplay")):
            return "pulse"
        if all(shutil.which(name) for name in ("pw-cli", "pw-cat", "pw-dump")):
            return "pipewire"
        return None

    @classmethod
    def require_tools(cls) -> str:
        backend = cls.available_backend()
        if backend is None:
            raise RuntimeError(
                "virtual-mic mode requires pactl/paplay or pw-cli/pw-cat/pw-dump"
            )
        return backend

    def start(self) -> None:
        if self.module_id is not None or self.node_id is not None:
            return
        self.backend = self.require_tools()
        if self.backend == "pipewire":
            self._start_pipewire()
            return
        completed = subprocess.run(
            [
                "pactl",
                "load-module",
                "module-null-sink",
                f"sink_name={self.sink_name}",
                "sink_properties=device.description=Chromie_Voice_Test_Input",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Failed to create the virtual microphone sink with pactl: "
                + completed.stdout.strip()
            )
        self.module_id = completed.stdout.strip()
        if not self.module_id:
            raise RuntimeError("pactl did not return a module ID for the virtual sink")

    def play(self, fixture: AudioFixture, *, timeout_s: float = 60.0) -> None:
        if self.backend == "pipewire":
            command = [
                "pw-cat",
                "--playback",
                "--target",
                self.sink_name,
                str(fixture.path),
            ]
        else:
            command = ["paplay", f"--device={self.sink_name}", str(fixture.path)]
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Failed to play {fixture.path} into {self.sink_name}: "
                + completed.stdout.strip()
            )

    def stop(self) -> None:
        if self.node_id is not None:
            subprocess.run(
                ["pw-cli", "destroy", str(self.node_id)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            self.node_id = None
            self.backend = None
            return
        if self.module_id is None:
            return
        subprocess.run(
            ["pactl", "unload-module", self.module_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        self.module_id = None
        self.backend = None

    def _start_pipewire(self) -> None:
        completed = subprocess.run(
            [
                "pw-cli",
                "create-node",
                "adapter",
                (
                    "{ factory.name=support.null-audio-sink "
                    f"node.name={self.sink_name} "
                    "node.description=\"Chromie Voice Test Input\" "
                    "media.class=Audio/Sink object.linger=true "
                    "audio.position=[ FL FR ] }"
                ),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Failed to create the virtual microphone sink with pw-cli: "
                + completed.stdout.strip()
            )
        for _ in range(50):
            self.node_id = self._pipewire_node_id()
            if self.node_id is not None:
                return
            time.sleep(0.1)
        raise RuntimeError(
            f"PipeWire created no visible node named {self.sink_name!r}"
        )

    def _pipewire_node_id(self) -> int | None:
        completed = subprocess.run(
            ["pw-dump"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            return None
        try:
            objects = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        for item in objects:
            info = item.get("info") if isinstance(item, dict) else None
            props = info.get("props") if isinstance(info, dict) else None
            if isinstance(props, dict) and props.get("node.name") == self.sink_name:
                return int(item["id"])
        return None

    def __enter__(self) -> "PulseVirtualMicrophone":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
