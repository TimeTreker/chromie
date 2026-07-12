from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


_VALID_CODEC_DEVICES = {"auto", "cpu", "cuda"}


def resolve_audio_codec_device(requested: str | None, *, cuda_available: bool) -> str:
    """Resolve the OuteTTS/DAC device without silently ignoring configuration."""
    value = str(requested or "auto").strip().lower()
    if value not in _VALID_CODEC_DEVICES:
        raise ValueError(
            "TTS_AUDIO_CODEC_DEVICE must be one of auto, cpu, or cuda"
        )
    if value == "auto":
        return "cuda" if cuda_available else "cpu"
    if value == "cuda" and not cuda_available:
        raise RuntimeError(
            "TTS_AUDIO_CODEC_DEVICE=cuda was requested but torch.cuda is unavailable"
        )
    return value


def realtime_factor(generate_seconds: float, audio_seconds: float) -> float | None:
    if audio_seconds <= 0:
        return None
    return max(0.0, float(generate_seconds)) / float(audio_seconds)


def nonnegative_remainder(total: float, *parts: float) -> float:
    return max(0.0, float(total) - sum(max(0.0, float(part)) for part in parts))


@dataclass(frozen=True)
class TtsPerformanceSample:
    audio_seconds: float
    generate_seconds: float
    model_generate_seconds: float
    codec_decode_seconds: float
    pcm_conversion_seconds: float
    worker_roundtrip_seconds: float
    queue_wait_seconds: float
    total_seconds: float

    @property
    def realtime_factor(self) -> float | None:
        return realtime_factor(self.generate_seconds, self.audio_seconds)

    @property
    def model_realtime_factor(self) -> float | None:
        return realtime_factor(self.model_generate_seconds, self.audio_seconds)

    def as_dict(self) -> dict[str, float | None]:
        return {
            "audio_seconds": self.audio_seconds,
            "generate_seconds": self.generate_seconds,
            "model_generate_seconds": self.model_generate_seconds,
            "codec_decode_seconds": self.codec_decode_seconds,
            "pcm_conversion_seconds": self.pcm_conversion_seconds,
            "worker_roundtrip_seconds": self.worker_roundtrip_seconds,
            "queue_wait_seconds": self.queue_wait_seconds,
            "total_seconds": self.total_seconds,
            "realtime_factor": self.realtime_factor,
            "model_realtime_factor": self.model_realtime_factor,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TtsPerformanceSample":
        def number(name: str) -> float:
            raw = value.get(name, 0.0)
            try:
                return max(0.0, float(raw or 0.0))
            except (TypeError, ValueError):
                return 0.0

        return cls(
            audio_seconds=number("audio_seconds"),
            generate_seconds=number("generate_seconds"),
            model_generate_seconds=number("model_generate_seconds"),
            codec_decode_seconds=number("codec_decode_seconds"),
            pcm_conversion_seconds=number("pcm_conversion_seconds"),
            worker_roundtrip_seconds=number("worker_roundtrip_seconds"),
            queue_wait_seconds=number("queue_wait_seconds"),
            total_seconds=number("total_seconds"),
        )


def summarize_samples(
    samples: Iterable[TtsPerformanceSample | Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = [
        sample
        if isinstance(sample, TtsPerformanceSample)
        else TtsPerformanceSample.from_mapping(sample)
        for sample in samples
    ]
    if not normalized:
        return {"count": 0}

    def median(name: str) -> float:
        return round(
            statistics.median(float(getattr(sample, name)) for sample in normalized),
            4,
        )

    rtfs = [sample.realtime_factor for sample in normalized]
    valid_rtfs = [value for value in rtfs if value is not None]
    model_rtfs = [sample.model_realtime_factor for sample in normalized]
    valid_model_rtfs = [value for value in model_rtfs if value is not None]

    result: dict[str, Any] = {
        "count": len(normalized),
        "median_audio_seconds": median("audio_seconds"),
        "median_generate_seconds": median("generate_seconds"),
        "median_model_generate_seconds": median("model_generate_seconds"),
        "median_codec_decode_seconds": median("codec_decode_seconds"),
        "median_pcm_conversion_seconds": median("pcm_conversion_seconds"),
        "median_worker_roundtrip_seconds": median("worker_roundtrip_seconds"),
        "median_queue_wait_seconds": median("queue_wait_seconds"),
        "median_total_seconds": median("total_seconds"),
    }
    if valid_rtfs:
        result["median_realtime_factor"] = round(statistics.median(valid_rtfs), 4)
    if valid_model_rtfs:
        result["median_model_realtime_factor"] = round(
            statistics.median(valid_model_rtfs), 4
        )
    return result
