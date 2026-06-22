from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
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
