"""Framework-neutral contracts for Chromie text-to-speech providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import asdict, dataclass, field
import re
from typing import Any


TTS_PROVIDER_CONTRACT_VERSION = 1


def _immutable_revision(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(
        re.fullmatch(r"[0-9a-f]{7,64}", normalized)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", normalized)
    )


def _immutable_software_revision(value: str) -> bool:
    normalized = value.strip().lower()
    return _immutable_revision(normalized) or bool(
        re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][a-z0-9.-]+)?", normalized)
    )


@dataclass(frozen=True)
class TTSModelArtifact:
    kind: str
    artifact_id: str
    revision: str
    license_id: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.artifact_id.strip():
            raise ValueError("model artifact kind and artifact_id are required")
        if not _immutable_revision(self.revision):
            raise ValueError(
                "model artifact revision must be an immutable commit or sha256 digest"
            )
        if not self.license_id.strip():
            raise ValueError("model artifact license_id is required")


@dataclass(frozen=True)
class TTSProviderCapabilities:
    """Declared behavior and provenance for one provider implementation.

    ``native_*_streaming`` describes the model/runtime itself. A provider may
    still implement the common streaming iterator by yielding a completed
    buffer in transport-sized chunks.
    """

    provider_id: str
    implementation: str
    software_source: str
    software_revision: str
    software_license_id: str
    model_artifacts: tuple[TTSModelArtifact, ...]
    license_review_status: str
    languages: tuple[str, ...]
    sample_rates: tuple[int, ...]
    max_concurrency: int
    native_text_streaming: bool
    native_audio_streaming: bool
    request_cancellation: bool
    speaker_profiles: bool
    voice_cloning: bool
    contract_version: int = TTS_PROVIDER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if not self.implementation.strip():
            raise ValueError("implementation must be non-empty")
        if not self.software_source.strip():
            raise ValueError("software_source is required")
        if not _immutable_software_revision(self.software_revision):
            raise ValueError(
                "software_revision must be an immutable commit, sha256 digest, "
                "or semantic version"
            )
        if not self.software_license_id.strip():
            raise ValueError("software_license_id is required")
        if not self.model_artifacts:
            raise ValueError("at least one immutable model artifact is required")
        if not self.license_review_status.strip():
            raise ValueError("license_review_status is required")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if not self.sample_rates or any(rate < 8000 for rate in self.sample_rates):
            raise ValueError("sample_rates must contain valid PCM rates")
        if not self.languages or any(not value.strip() for value in self.languages):
            raise ValueError("languages must contain non-empty language identifiers")

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["languages"] = list(self.languages)
        payload["sample_rates"] = list(self.sample_rates)
        payload["model_artifacts"] = [asdict(item) for item in self.model_artifacts]
        return payload


@dataclass(frozen=True)
class TTSSynthesisRequest:
    request_id: str
    text: str
    speaker_id: str = "default"
    language_hint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must be non-empty")
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        if not self.speaker_id.strip():
            raise ValueError("speaker_id must be non-empty")


@dataclass(frozen=True)
class TTSAudioChunk:
    pcm: bytes
    sample_rate: int
    channels: int = 1
    sample_format: str = "pcm_s16le"

    def __post_init__(self) -> None:
        if not self.pcm:
            raise ValueError("audio chunk must contain PCM bytes")
        if self.sample_rate < 8000:
            raise ValueError("audio chunk sample_rate must be >= 8000")
        if self.channels != 1:
            raise ValueError("Chromie's current playback contract requires mono PCM")
        if self.sample_format != "pcm_s16le":
            raise ValueError("Chromie's current playback contract requires pcm_s16le")


@dataclass(frozen=True)
class TTSSynthesisCompleted:
    metrics: Mapping[str, Any] = field(default_factory=dict)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)


TTSStreamEvent = TTSAudioChunk | TTSSynthesisCompleted


class TTSProvider(ABC):
    """Lifecycle, synthesis, cancellation, and observability contract.

    Cancellation is expressed by cancelling or closing the consumer of
    ``synthesize_stream``. Implementations that declare
    ``request_cancellation=True`` must stop or isolate the associated native
    work and must not leak later audio into another request.
    """

    @property
    @abstractmethod
    def capabilities(self) -> TTSProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def synthesize_stream(
        self,
        request: TTSSynthesisRequest,
    ) -> AsyncIterator[TTSStreamEvent]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def list_speakers(self) -> list[str]:
        raise NotImplementedError

    async def create_speaker(
        self,
        *,
        speaker_id: str,
        wav_path: str,
        make_default: bool,
        transcript: str | None = None,
    ) -> Mapping[str, Any]:
        raise NotImplementedError(
            f"provider {self.capabilities.provider_id} does not create speaker profiles"
        )


class TTSProviderRegistry:
    """Small explicit registry; providers are never selected by import side effects."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], TTSProvider]] = {}

    def register(self, provider_id: str, factory: Callable[[], TTSProvider]) -> None:
        key = provider_id.strip().lower()
        if not key:
            raise ValueError("provider_id must be non-empty")
        if key in self._factories:
            raise ValueError(f"TTS provider already registered: {key}")
        self._factories[key] = factory

    def create(self, provider_id: str) -> TTSProvider:
        key = provider_id.strip().lower()
        try:
            provider = self._factories[key]()
        except KeyError as exc:
            available = ", ".join(sorted(self._factories)) or "none"
            raise RuntimeError(
                f"Unknown TTS_PROVIDER={provider_id!r}; registered providers: {available}"
            ) from exc
        if provider.capabilities.provider_id != key:
            raise RuntimeError(
                "TTS provider registry key does not match declared provider_id: "
                f"{key!r} != {provider.capabilities.provider_id!r}"
            )
        return provider

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
