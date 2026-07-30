from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Mapping

try:
    from .backends import ASRBackendConfig, validate_asr_mode
except ImportError:  # pragma: no cover - script execution compatibility
    from backends import ASRBackendConfig, validate_asr_mode


DEFAULT_SENSEVOICE_MODEL_ID = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_SENSEVOICE_MODEL_REVISION = f"asr-models/{DEFAULT_SENSEVOICE_MODEL_ID}"
DEFAULT_SENSEVOICE_MODEL_PATH = (
    "/root/.cache/huggingface/sherpa-onnx/"
    f"{DEFAULT_SENSEVOICE_MODEL_ID}"
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _text(values: Mapping[str, str], name: str, default: str) -> str:
    return values.get(name, default).strip()


def _optional_text(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def _bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} must be one of {sorted(_TRUE_VALUES | _FALSE_VALUES)}, got {raw!r}"
    )


def _int(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = values.get(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")
    return value


def _float(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = values.get(name)
    try:
        value = default if raw is None or not raw.strip() else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class ASRServiceSettings:
    host: str
    port: int
    log_level: str
    mode: str
    model_name: str
    model_revision: str | None
    device: str
    sample_rate: int
    language: str | None
    sherpa_model_type: str
    sherpa_provider: str | None
    sherpa_num_threads: int
    sherpa_language: str
    sherpa_use_itn: bool
    sherpa_debug: bool
    sherpa_model_file: str | None
    sherpa_tokens_file: str | None
    max_concurrent_transcriptions: int
    startup_warmup_enabled: bool
    startup_warmup_audio_seconds: float

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "ASRServiceSettings":
        # Copy once so later process-environment mutation cannot produce a
        # partially reconfigured running service.
        values = dict(os.environ if environ is None else environ)
        language = _optional_text(values, "ASR_LANGUAGE")
        mode = validate_asr_mode(_text(values, "ASR_MODE", "final"))
        return cls(
            host=_text(values, "ASR_HOST", "0.0.0.0"),
            port=_int(values, "ASR_PORT", 9001, minimum=1, maximum=65535),
            log_level=_text(values, "LOG_LEVEL", "INFO").upper(),
            mode=mode,
            model_name=_text(values, "ASR_MODEL", DEFAULT_SENSEVOICE_MODEL_PATH),
            model_revision=(
                _optional_text(values, "ASR_MODEL_REVISION")
                or DEFAULT_SENSEVOICE_MODEL_REVISION
            ),
            device=_text(values, "ASR_DEVICE", "cuda"),
            sample_rate=_int(
                values,
                "ASR_SAMPLE_RATE",
                16000,
                minimum=8000,
                maximum=192000,
            ),
            language=language,
            sherpa_model_type=_text(values, "SHERPA_ONNX_MODEL_TYPE", "sense_voice"),
            sherpa_provider=_optional_text(values, "SHERPA_ONNX_PROVIDER"),
            sherpa_num_threads=_int(
                values,
                "SHERPA_ONNX_NUM_THREADS",
                2,
                minimum=1,
                maximum=256,
            ),
            sherpa_language=(
                _optional_text(values, "SHERPA_ONNX_LANGUAGE")
                or language
                or "auto"
            ),
            sherpa_use_itn=_bool(values, "SHERPA_ONNX_USE_ITN", True),
            sherpa_debug=_bool(values, "SHERPA_ONNX_DEBUG", False),
            sherpa_model_file=_optional_text(values, "SHERPA_ONNX_MODEL_FILE"),
            sherpa_tokens_file=_optional_text(values, "SHERPA_ONNX_TOKENS_FILE"),
            max_concurrent_transcriptions=_int(
                values,
                "ASR_MAX_CONCURRENT_TRANSCRIPTIONS",
                1,
                minimum=1,
                maximum=64,
            ),
            startup_warmup_enabled=_bool(
                values,
                "ASR_STARTUP_WARMUP_ENABLED",
                True,
            ),
            startup_warmup_audio_seconds=_float(
                values,
                "ASR_STARTUP_WARMUP_AUDIO_SECONDS",
                1.0,
                minimum=0.01,
                maximum=30.0,
            ),
        )

    def backend_config(self) -> ASRBackendConfig:
        return ASRBackendConfig(
            mode=self.mode,
            model_name=self.model_name,
            model_revision=self.model_revision,
            device=self.device,
            sample_rate=self.sample_rate,
            sherpa_model_type=self.sherpa_model_type,
            sherpa_provider=self.sherpa_provider,
            sherpa_num_threads=self.sherpa_num_threads,
            sherpa_language=self.sherpa_language,
            sherpa_use_itn=self.sherpa_use_itn,
            sherpa_debug=self.sherpa_debug,
            sherpa_model_file=self.sherpa_model_file,
            sherpa_tokens_file=self.sherpa_tokens_file,
        )

    def safe_diagnostics(self) -> dict[str, object]:
        values = asdict(self)
        # Local model paths are operational details but not credentials. Keep
        # explicit override file paths out of diagnostics because installations
        # may encode private directory names in them.
        values.pop("sherpa_model_file", None)
        values.pop("sherpa_tokens_file", None)
        return values
