from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from orchestrator.clients.tts_client import TTSClient


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
    client = TTSClient(tts_url, default_sample_rate=default_sample_rate)
    fixtures: dict[str, AudioFixture] = {}
    for index, text in enumerate(dict.fromkeys(texts), start=1):
        pcm16, sample_rate = await asyncio.wait_for(
            client.synthesize(
                text=text,
                speaker_id=speaker_id,
                request_id=f"m13-input-{uuid.uuid4().hex}",
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

    def __init__(self, sink_name: str = "chromie_m13_test") -> None:
        self.sink_name = sink_name
        self.source_name = f"{sink_name}.monitor"
        self.module_id: str | None = None

    @staticmethod
    def require_tools() -> None:
        missing = [name for name in ("pactl", "paplay") if shutil.which(name) is None]
        if missing:
            raise RuntimeError(
                "virtual-mic mode requires PulseAudio/PipeWire-Pulse tools: "
                + ", ".join(missing)
            )

    def start(self) -> None:
        self.require_tools()
        if self.module_id is not None:
            return
        completed = subprocess.run(
            [
                "pactl",
                "load-module",
                "module-null-sink",
                f"sink_name={self.sink_name}",
                "sink_properties=device.description=Chromie_M13_Test_Input",
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
        completed = subprocess.run(
            ["paplay", f"--device={self.sink_name}", str(fixture.path)],
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
        if self.module_id is None:
            return
        subprocess.run(
            ["pactl", "unload-module", self.module_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        self.module_id = None

    def __enter__(self) -> "PulseVirtualMicrophone":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
