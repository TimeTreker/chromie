from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Protocol


_SHERPA_SPECIAL_TOKEN_RE = re.compile(r"<\|[^>]*\|>")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?，。！？])")


class FinalASRBackend(Protocol):
    name: str
    mode: str
    model_name: str
    model_revision: str | None

    def transcribe_final(self, audio: Any, **kwargs: Any) -> tuple[str, Any]:
        """Return one final transcript for a complete utterance."""


@dataclass(frozen=True)
class ASRBackendConfig:
    mode: str
    model_name: str
    model_revision: str | None
    device: str
    sample_rate: int = 16000
    sherpa_model_type: str = "sense_voice"
    sherpa_provider: str | None = None
    sherpa_num_threads: int = 1
    sherpa_language: str | None = None
    sherpa_use_itn: bool = True
    sherpa_debug: bool = False
    sherpa_model_file: str | None = None
    sherpa_tokens_file: str | None = None


def validate_asr_mode(mode: str | None) -> str:
    normalized = (mode or "final").strip().lower()
    if normalized != "final":
        raise ValueError(
            f"ASR_MODE={mode!r} is not implemented yet. The current ASR "
            "WebSocket contract accepts complete utterances and returns one "
            "final transcript."
        )
    return normalized


def _as_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def _resolve_sherpa_sense_voice_files(config: ASRBackendConfig) -> tuple[Path, Path]:
    model_path = _as_path(config.sherpa_model_file)
    tokens_path = _as_path(config.sherpa_tokens_file)

    if model_path is None:
        model_root = Path(config.model_name).expanduser()
        if model_root.suffix == ".onnx":
            model_path = model_root
            tokens_path = tokens_path or model_root.parent / "tokens.txt"
        else:
            candidates = (model_root / "model.int8.onnx", model_root / "model.onnx")
            model_path = next((path for path in candidates if path.is_file()), candidates[0])
            tokens_path = tokens_path or model_root / "tokens.txt"

    if tokens_path is None:
        tokens_path = model_path.parent / "tokens.txt"

    missing = [str(path) for path in (model_path, tokens_path) if not path.is_file()]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            "SenseVoice ASR requires local model files. "
            f"Missing: {joined}. Set ASR_MODEL to a model directory or set "
            "SHERPA_ONNX_MODEL_FILE and SHERPA_ONNX_TOKENS_FILE explicitly."
        )
    return model_path, tokens_path


def _sherpa_provider(config: ASRBackendConfig) -> str:
    if config.sherpa_provider:
        return config.sherpa_provider.strip().lower()
    device = (config.device or "").strip().lower()
    if device.startswith("cuda") or device == "gpu":
        return "cuda"
    return "cpu"


def _sherpa_language(config: ASRBackendConfig) -> str:
    language = (config.sherpa_language or "").strip().lower()
    return language or "auto"


def _stringify_sherpa_result(result: Any) -> str:
    text = getattr(result, "text", None)
    if text not in (None, ""):
        return str(text)
    return str(result)


def _clean_sherpa_text(value: str) -> str:
    cleaned = _SHERPA_SPECIAL_TOKEN_RE.sub(" ", value)
    cleaned = " ".join(cleaned.split())
    return _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", cleaned).strip()


def _extract_sherpa_result_text(result: Any) -> str:
    raw = _stringify_sherpa_result(result).strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _clean_sherpa_text(raw)
    if isinstance(payload, dict):
        return _clean_sherpa_text(str(payload.get("text", "")))
    return _clean_sherpa_text(raw)


class SenseVoiceFinalBackend:
    name = "sherpa_onnx"
    mode = "final"

    def __init__(
        self,
        config: ASRBackendConfig,
        *,
        recognizer_factory: Any | None = None,
    ) -> None:
        validate_asr_mode(config.mode)
        model_type = (config.sherpa_model_type or "sense_voice").strip().lower()
        if model_type not in {"sense_voice", "sensevoice"}:
            raise ValueError(
                "Chromie ASR currently supports only "
                f"SHERPA_ONNX_MODEL_TYPE=sense_voice, not {config.sherpa_model_type!r}."
            )

        model_path, tokens_path = _resolve_sherpa_sense_voice_files(config)

        if recognizer_factory is None:
            try:
                import sherpa_onnx
            except ImportError as exc:
                raise RuntimeError(
                    "SenseVoice ASR requires the sherpa-onnx Python package "
                    "installed in the ASR service image."
                ) from exc

            recognizer_factory = sherpa_onnx.OfflineRecognizer

        self.model_name = config.model_name
        self.model_revision = config.model_revision
        self.model_type = "sense_voice"
        self.provider = _sherpa_provider(config)
        self.sample_rate = config.sample_rate
        self._recognizer = recognizer_factory.from_sense_voice(
            model=str(model_path),
            tokens=str(tokens_path),
            num_threads=max(1, config.sherpa_num_threads),
            sample_rate=config.sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
            debug=config.sherpa_debug,
            provider=self.provider,
            language=_sherpa_language(config),
            use_itn=config.sherpa_use_itn,
        )

    def transcribe_final(self, audio: Any, **kwargs: Any) -> tuple[str, Any]:
        stream = self._recognizer.create_stream()
        stream.accept_waveform(self.sample_rate, audio)
        self._recognizer.decode_stream(stream)
        text = _extract_sherpa_result_text(stream.result)
        return text, {
            "backend": self.name,
            "model_type": self.model_type,
            "provider": self.provider,
            "raw_result": _stringify_sherpa_result(stream.result),
        }


def create_final_asr_backend(
    config: ASRBackendConfig,
    *,
    sherpa_onnx_factory: Any | None = None,
) -> FinalASRBackend:
    """Create Chromie's single supported final-utterance SenseVoice backend."""
    return SenseVoiceFinalBackend(
        config,
        recognizer_factory=sherpa_onnx_factory,
    )
