"""Resolve immutable OuteTTS model snapshots for llama.cpp inference."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from huggingface_hub import snapshot_download


TOKENIZER_ALLOW_PATTERNS = [
    "*.json",
    "*.model",
    "*.tiktoken",
    "*.txt",
]

GGUF_FILENAMES = {
    "FP16": "OuteTTS-1.0-0.6B-FP16.gguf",
    "Q8_0": "OuteTTS-1.0-0.6B-Q8_0.gguf",
    "Q6_K": "OuteTTS-1.0-0.6B-Q6_K.gguf",
    "Q5_K_M": "OuteTTS-1.0-0.6B-Q5_K_M.gguf",
    "Q4_K_M": "OuteTTS-1.0-0.6B-Q4_K_M.gguf",
}


@dataclass(frozen=True)
class ResolvedModelSources:
    tokenizer_repo: str
    tokenizer_revision: str
    tokenizer_path: str
    gguf_repo: str
    gguf_revision: str
    gguf_filename: str
    model_path: str

    def metadata(self) -> dict[str, str]:
        return asdict(self)


def required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is required so OuteTTS does not resolve a mutable model revision"
        )
    return value


def gguf_filename(model_size: str, quantization: str) -> str:
    if model_size != "0.6B":
        raise RuntimeError(
            "Only the release-locked OuteTTS 0.6B model is currently supported; "
            "update release/model-lock.json before enabling another size"
        )
    try:
        return GGUF_FILENAMES[quantization.upper()]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported pinned GGUF quantization: {quantization}") from exc


def resolve_model_sources(
    model_size: str,
    quantization: str,
    *,
    downloader=snapshot_download,
) -> ResolvedModelSources:
    tokenizer_repo = required_env("TTS_TOKENIZER_REPO")
    tokenizer_revision = required_env("TTS_TOKENIZER_REVISION")
    gguf_repo = required_env("TTS_GGUF_REPO")
    gguf_revision = required_env("TTS_GGUF_REVISION")
    filename = gguf_filename(model_size, quantization)

    tokenizer_path = Path(
        downloader(
            repo_id=tokenizer_repo,
            revision=tokenizer_revision,
            allow_patterns=TOKENIZER_ALLOW_PATTERNS,
        )
    )
    gguf_snapshot = Path(
        downloader(
            repo_id=gguf_repo,
            revision=gguf_revision,
            allow_patterns=[filename],
        )
    )
    model_path = gguf_snapshot / filename
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Pinned OuteTTS GGUF was not found after snapshot download: {model_path}"
        )

    return ResolvedModelSources(
        tokenizer_repo=tokenizer_repo,
        tokenizer_revision=tokenizer_revision,
        tokenizer_path=str(tokenizer_path),
        gguf_repo=gguf_repo,
        gguf_revision=gguf_revision,
        gguf_filename=filename,
        model_path=str(model_path),
    )


def apply_model_sources(config, sources: ResolvedModelSources):
    """Override OuteTTS auto-config paths with immutable local snapshots."""
    config.tokenizer_path = str(Path(sources.tokenizer_path).resolve())
    config.model_path = str(Path(sources.model_path).resolve())
    return config
