from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO

MAGIC = b"CAUD"
HEADER = struct.Struct("!4sIII")
MAX_AUDIO_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class InjectedAudioPacket:
    sample_rate: int
    channels: int
    pcm16: bytes


def encode_audio_packet(*, pcm16: bytes, sample_rate: int, channels: int = 1) -> bytes:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be greater than zero")
    if channels <= 0:
        raise ValueError("channels must be greater than zero")
    if len(pcm16) % (2 * channels) != 0:
        raise ValueError("PCM16 payload is not aligned to the declared channel count")
    if len(pcm16) > MAX_AUDIO_BYTES:
        raise ValueError(f"PCM16 payload exceeds {MAX_AUDIO_BYTES} bytes")
    return HEADER.pack(MAGIC, sample_rate, channels, len(pcm16)) + pcm16


def _read_exact(stream: BinaryIO, size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if not chunks:
                return None
            raise EOFError(f"audio injection stream closed with {remaining} bytes missing")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_audio_packet(stream: BinaryIO) -> InjectedAudioPacket | None:
    header = _read_exact(stream, HEADER.size)
    if header is None:
        return None
    magic, sample_rate, channels, payload_size = HEADER.unpack(header)
    if magic != MAGIC:
        raise ValueError(f"invalid audio injection magic: {magic!r}")
    if sample_rate <= 0:
        raise ValueError("injected sample_rate must be greater than zero")
    if channels <= 0:
        raise ValueError("injected channels must be greater than zero")
    if payload_size > MAX_AUDIO_BYTES:
        raise ValueError(f"injected payload exceeds {MAX_AUDIO_BYTES} bytes")
    if payload_size % (2 * channels) != 0:
        raise ValueError("injected PCM16 payload is not channel aligned")
    payload = _read_exact(stream, payload_size)
    if payload is None:
        raise EOFError("audio injection stream closed before PCM16 payload")
    return InjectedAudioPacket(
        sample_rate=sample_rate,
        channels=channels,
        pcm16=payload,
    )
