"""Typed startup configuration for the TTS service boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


class TTSConfigurationError(RuntimeError):
    """Raised when a TTS startup value cannot satisfy its typed contract."""


def _raw(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name)
    return default if value is None or value == "" else str(value)


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    return _raw(values, name, default).strip()


def _integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    raw = _raw(values, name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise TTSConfigurationError(f"{name} must be an integer; got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise TTSConfigurationError(
            f"{name} must be >= {minimum}; got {value}"
        )
    return value


def _floating(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = _raw(values, name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise TTSConfigurationError(f"{name} must be a number; got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise TTSConfigurationError(f"{name} must be >= {minimum}; got {value}")
    if maximum is not None and value > maximum:
        raise TTSConfigurationError(f"{name} must be <= {maximum}; got {value}")
    return value


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    normalized = str(raw).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise TTSConfigurationError(
        f"{name} must be a boolean (0/1, false/true, no/yes, off/on); got {raw!r}"
    )


@dataclass(frozen=True)
class TTSServiceSettings:
    log_level: str
    timezone: str
    host: str
    port: int
    provider: str
    model_size: str
    quantization: str
    sample_rate: int
    chunk_ms: int
    n_gpu_layers: int
    context_size: int
    requested_max_length: int
    min_generation_length: int
    n_batch: int
    threads: int
    temperature: float
    repetition_penalty: float
    max_concurrent_synthesis: int
    worker_count: int
    min_text_chars: int
    max_text_chars: int
    generation_retries: int
    reset_llama_state: bool
    detailed_timing: bool
    metrics_window: int
    audio_codec_device: str
    speaker_dir: Path
    speaker_alignment_device: str
    speaker_transcript_min_similarity: float
    worker_startup_timeout_s: float
    tokenizer_repo: str
    tokenizer_revision: str
    gguf_repo: str
    gguf_revision: str

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "TTSServiceSettings":
        values = dict(os.environ if environ is None else environ)
        min_text_chars = _integer(values, "TTS_MIN_TEXT_CHARS", 4, minimum=1)
        context_size = _integer(values, "TTS_CONTEXT_SIZE", 4096, minimum=512)
        alignment_device = _text(
            values, "TTS_SPEAKER_ALIGNMENT_DEVICE", "cpu"
        ).casefold()
        if alignment_device not in {"cpu", "cuda"}:
            raise TTSConfigurationError(
                "TTS_SPEAKER_ALIGNMENT_DEVICE must be cpu or cuda; "
                f"got {alignment_device!r}"
            )
        provider = _text(values, "TTS_PROVIDER", "oute").casefold()
        if not provider:
            raise TTSConfigurationError("TTS_PROVIDER must not be empty")
        port = _integer(values, "TTS_PORT", 5000, minimum=1)
        if port > 65535:
            raise TTSConfigurationError(f"TTS_PORT must be <= 65535; got {port}")
        return cls(
            log_level=_text(values, "LOG_LEVEL", "INFO").upper(),
            timezone=_text(values, "TZ", "unset"),
            host=_text(values, "TTS_HOST", "0.0.0.0"),
            port=port,
            provider=provider,
            model_size=_text(values, "TTS_MODEL_SIZE", "0.6B"),
            quantization=_text(values, "TTS_QUANTIZATION", "FP16"),
            sample_rate=_integer(values, "TTS_SAMPLE_RATE", 44100, minimum=8000),
            chunk_ms=_integer(values, "TTS_CHUNK_MS", 120, minimum=20),
            n_gpu_layers=_integer(values, "TTS_N_GPU_LAYERS", -1),
            context_size=context_size,
            requested_max_length=_integer(
                values, "TTS_MAX_LENGTH", context_size, minimum=1
            ),
            min_generation_length=_integer(
                values, "MIN_TTS_GENERATION_LENGTH", 1024, minimum=128
            ),
            n_batch=_integer(values, "TTS_N_BATCH", 256, minimum=1),
            threads=_integer(values, "TTS_THREADS", 4, minimum=1),
            temperature=_floating(values, "TTS_TEMPERATURE", 0.4, minimum=0.0),
            repetition_penalty=_floating(
                values, "TTS_REPETITION_PENALTY", 1.1, minimum=0.0
            ),
            max_concurrent_synthesis=_integer(
                values, "TTS_MAX_CONCURRENT_SYNTHESIS", 1, minimum=1
            ),
            worker_count=_integer(values, "TTS_WORKER_COUNT", 1, minimum=1),
            min_text_chars=min_text_chars,
            max_text_chars=_integer(
                values,
                "TTS_MAX_TEXT_CHARS",
                220,
                minimum=min_text_chars,
            ),
            generation_retries=_integer(
                values, "TTS_GENERATION_RETRIES", 1, minimum=1
            ),
            reset_llama_state=_boolean(
                values, "TTS_RESET_LLAMA_STATE", True
            ),
            detailed_timing=_boolean(values, "TTS_DETAILED_TIMING", True),
            metrics_window=_integer(values, "TTS_METRICS_WINDOW", 20, minimum=1),
            audio_codec_device=_text(values, "TTS_AUDIO_CODEC_DEVICE", "auto"),
            speaker_dir=Path(_text(values, "SPEAKER_DIR", "/app/speakers")),
            speaker_alignment_device=alignment_device,
            speaker_transcript_min_similarity=_floating(
                values,
                "TTS_SPEAKER_TRANSCRIPT_MIN_SIMILARITY",
                0.75,
                minimum=0.0,
                maximum=1.0,
            ),
            worker_startup_timeout_s=_floating(
                values,
                "TTS_WORKER_STARTUP_TIMEOUT_SEC",
                600.0,
                minimum=1.0,
            ),
            tokenizer_repo=_text(values, "TTS_TOKENIZER_REPO"),
            tokenizer_revision=_text(values, "TTS_TOKENIZER_REVISION"),
            gguf_repo=_text(values, "TTS_GGUF_REPO"),
            gguf_revision=_text(values, "TTS_GGUF_REVISION"),
        )

    def required_model_sources(self) -> tuple[str, str, str, str]:
        values = (
            ("TTS_TOKENIZER_REPO", self.tokenizer_repo),
            ("TTS_TOKENIZER_REVISION", self.tokenizer_revision),
            ("TTS_GGUF_REPO", self.gguf_repo),
            ("TTS_GGUF_REVISION", self.gguf_revision),
        )
        missing = [name for name, value in values if not value]
        if missing:
            raise TTSConfigurationError(
                ", ".join(missing)
                + " required so OuteTTS does not resolve a mutable model revision"
            )
        return (
            self.tokenizer_repo,
            self.tokenizer_revision,
            self.gguf_repo,
            self.gguf_revision,
        )
