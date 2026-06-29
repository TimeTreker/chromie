from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


SUPPORTED_FINAL_BACKENDS = ("faster_whisper",)
PLANNED_FINAL_BACKENDS = ("sherpa_onnx",)


class FinalASRBackend(Protocol):
    name: str
    model_name: str
    model_revision: str | None

    def transcribe_final(self, audio: Any, **kwargs: Any) -> tuple[str, Any]:
        """Return one final transcript for a complete utterance."""


@dataclass(frozen=True)
class ASRBackendConfig:
    backend: str
    mode: str
    model_name: str
    model_revision: str | None
    device: str
    compute_type: str


def canonical_backend_name(value: str | None) -> str:
    name = (value or "faster_whisper").strip().lower().replace("-", "_")
    return name or "faster_whisper"


def validate_asr_mode(mode: str | None) -> str:
    normalized = (mode or "final").strip().lower()
    if normalized != "final":
        raise ValueError(
            f"ASR_MODE={mode!r} is not implemented yet. The current ASR "
            "WebSocket contract accepts complete utterances and returns one "
            "final transcript."
        )
    return normalized


class FasterWhisperFinalBackend:
    name = "faster_whisper"

    def __init__(
        self,
        config: ASRBackendConfig,
        *,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        if model_factory is None:
            from faster_whisper import WhisperModel

            model_factory = WhisperModel

        self.model_name = config.model_name
        self.model_revision = config.model_revision
        self.device = config.device
        self.compute_type = config.compute_type
        self._model = model_factory(
            config.model_name,
            device=config.device,
            compute_type=config.compute_type,
            revision=config.model_revision,
        )

    def transcribe_final(self, audio: Any, **kwargs: Any) -> tuple[str, Any]:
        segments, info = self._model.transcribe(audio, **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info


def create_final_asr_backend(
    config: ASRBackendConfig,
    *,
    faster_whisper_factory: Callable[..., Any] | None = None,
) -> FinalASRBackend:
    backend = canonical_backend_name(config.backend)
    mode = validate_asr_mode(config.mode)
    normalized_config = ASRBackendConfig(
        backend=backend,
        mode=mode,
        model_name=config.model_name,
        model_revision=config.model_revision,
        device=config.device,
        compute_type=config.compute_type,
    )
    if backend == "faster_whisper":
        return FasterWhisperFinalBackend(
            normalized_config,
            model_factory=faster_whisper_factory,
        )
    if backend in PLANNED_FINAL_BACKENDS:
        raise ValueError(
            f"ASR_BACKEND={config.backend!r} is planned but not implemented in "
            "this revision. Keep ASR_BACKEND=faster_whisper until the "
            "sherpa-onnx backend has dependency, model-lock, benchmark, and "
            "acceptance evidence."
        )
    supported = ", ".join(SUPPORTED_FINAL_BACKENDS)
    planned = ", ".join(PLANNED_FINAL_BACKENDS)
    raise ValueError(
        f"Unsupported ASR_BACKEND={config.backend!r}; supported final "
        f"backends: {supported}; planned backends: {planned}."
    )
