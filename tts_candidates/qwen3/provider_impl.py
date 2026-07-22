"""Qwen3-TTS 0.6B Base candidate provider."""

from __future__ import annotations

import hashlib
import json
import os
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from candidate_provider import WorkerBackedCandidateProvider
from provider import TTSModelArtifact, TTSProviderCapabilities
from streaming_worker import StreamingProcessWorker


PROVIDER_ID = "qwen3-tts-0.6b-base"
SOFTWARE_SOURCE = "https://github.com/QwenLM/Qwen3-TTS"
DEFAULT_SOFTWARE_REVISION = "022e286b98fbec7e1e916cb940cdf532cd9f488e"
DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
DEFAULT_MODEL_REVISION = "5d83992436eae1d760afd27aff78a71d676296fc"


def required_env(name: str, default: str | None = None) -> str:
    value = str(os.getenv(name, default or "")).strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def reference_metadata() -> tuple[Path, str, str, str]:
    wav_path = Path(required_env("TTS_REFERENCE_WAV", "/evaluation/reference.wav"))
    metadata_path = Path(
        required_env("TTS_REFERENCE_METADATA", "/evaluation/reference.json")
    )
    if not wav_path.is_file() or not metadata_path.is_file():
        raise RuntimeError(
            "Shared TTS reference is missing; run scripts/prepare_tts_reference.py first"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    text = str(metadata.get("text") or "").strip()
    expected_sha = str(metadata.get("audio_sha256") or "").strip().lower()
    license_id = str(metadata.get("license_id") or "").strip()
    actual_sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    if not text or not license_id or expected_sha != actual_sha:
        raise RuntimeError("Shared TTS reference metadata or SHA-256 is invalid")
    return wav_path, text, actual_sha, license_id


def language_name(text: str, hint: str | None) -> str:
    normalized = (hint or "").lower()
    if normalized.startswith("zh"):
        return "Chinese"
    if normalized.startswith("en"):
        return "English"
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
    has_latin = any("a" <= char.lower() <= "z" for char in text)
    if has_cjk and not has_latin:
        return "Chinese"
    if has_latin and not has_cjk:
        return "English"
    return "Auto"


def float_pcm16(wav: Any) -> bytes:
    import numpy as np

    array = np.asarray(wav, dtype=np.float32).reshape(-1)
    if not array.size:
        raise RuntimeError("Qwen3-TTS returned empty audio")
    return (np.clip(array, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def worker_target(connection: Connection) -> None:
    try:
        import torch
        from huggingface_hub import snapshot_download
        from qwen_tts import Qwen3TTSModel

        model_id = required_env("QWEN3_TTS_MODEL_ID", DEFAULT_MODEL_ID)
        model_revision = required_env(
            "QWEN3_TTS_MODEL_REVISION", DEFAULT_MODEL_REVISION
        )
        wav_path, ref_text, ref_sha, _ref_license = reference_metadata()
        model_path = snapshot_download(repo_id=model_id, revision=model_revision)
        dtype_name = required_env("QWEN3_TTS_DTYPE", "bfloat16")
        dtype = getattr(torch, dtype_name)
        model = Qwen3TTSModel.from_pretrained(
            model_path,
            device_map=required_env("QWEN3_TTS_DEVICE", "cuda:0"),
            dtype=dtype,
            attn_implementation=required_env("QWEN3_TTS_ATTENTION", "sdpa"),
        )
        voice_prompt = model.create_voice_clone_prompt(
            ref_audio=str(wav_path),
            ref_text=ref_text,
            x_vector_only_mode=False,
        )
        connection.send(
            {
                "type": "ready",
                "model_id": model_id,
                "model_revision": model_revision,
                "reference_sha256": ref_sha,
                "device": str(model.device),
                "native_audio_streaming": False,
            }
        )
    except Exception as exc:
        connection.send({"type": "error", "message": f"Qwen startup failed: {exc}"})
        return

    chunk_ms = int(os.getenv("TTS_TRANSPORT_CHUNK_MS", "120"))
    while True:
        payload = connection.recv()
        if payload.get("type") == "shutdown":
            connection.send({"type": "stopped"})
            return
        if payload.get("type") != "synthesize":
            connection.send({"type": "error", "message": "unsupported worker request"})
            continue
        started = time.perf_counter()
        try:
            text = str(payload.get("text") or "")
            wavs, sample_rate = model.generate_voice_clone(
                text=text,
                language=language_name(text, payload.get("language_hint")),
                voice_clone_prompt=voice_prompt,
                non_streaming_mode=True,
            )
            pcm = float_pcm16(wavs[0])
            chunk_bytes = max(2, int(sample_rate * chunk_ms / 1000) * 2)
            for offset in range(0, len(pcm), chunk_bytes):
                connection.send(
                    {
                        "type": "audio",
                        "pcm": pcm[offset : offset + chunk_bytes],
                        "sample_rate": int(sample_rate),
                    }
                )
            connection.send(
                {
                    "type": "complete",
                    "metrics": {"generate_seconds": time.perf_counter() - started},
                    "provider_metadata": {
                        "native_audio_streaming": False,
                        "reference_sha256": ref_sha,
                    },
                }
            )
        except Exception as exc:
            connection.send({"type": "error", "message": str(exc)})


def create_provider() -> WorkerBackedCandidateProvider:
    _wav_path, _ref_text, ref_sha, ref_license = reference_metadata()
    software_revision = required_env(
        "QWEN3_TTS_SOURCE_REVISION", DEFAULT_SOFTWARE_REVISION
    )
    model_id = required_env("QWEN3_TTS_MODEL_ID", DEFAULT_MODEL_ID)
    model_revision = required_env("QWEN3_TTS_MODEL_REVISION", DEFAULT_MODEL_REVISION)
    capabilities = TTSProviderCapabilities(
        provider_id=PROVIDER_ID,
        implementation="Qwen3-TTS transformers",
        software_source=SOFTWARE_SOURCE,
        software_revision=software_revision,
        software_license_id="Apache-2.0",
        model_artifacts=(
            TTSModelArtifact(
                kind="weights",
                artifact_id=model_id,
                revision=model_revision,
                license_id="Apache-2.0",
            ),
            TTSModelArtifact(
                kind="voice_reference",
                artifact_id="chromie/evaluation/reference.wav",
                revision=f"sha256:{ref_sha}",
                license_id=ref_license,
            ),
        ),
        license_review_status="declared_unreviewed",
        languages=("zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"),
        sample_rates=(24000,),
        max_concurrency=1,
        native_text_streaming=False,
        native_audio_streaming=False,
        request_cancellation=True,
        speaker_profiles=True,
        voice_cloning=True,
    )
    worker = StreamingProcessWorker(
        worker_target,
        name="qwen3-tts-worker",
        startup_timeout_s=float(os.getenv("TTS_WORKER_STARTUP_TIMEOUT_SEC", "1200")),
        cancel_drain_timeout_s=float(
            os.getenv("TTS_CANDIDATE_CANCEL_DRAIN_TIMEOUT_SEC", "3")
        ),
    )
    return WorkerBackedCandidateProvider(
        capabilities=capabilities,
        worker=worker,
    )
