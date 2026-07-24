"""Fun-CosyVoice3 0.5B provider with source-controlled Chromie voices."""

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
from voice_catalog import VoiceCatalog, VoiceProfile, resolve_voice_profile, validate_voice_catalog


PROVIDER_ID = "fun-cosyvoice3-0.5b"
SOFTWARE_SOURCE = "https://github.com/FunAudioLLM/CosyVoice"
DEFAULT_SOFTWARE_REVISION = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
DEFAULT_MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
DEFAULT_MODEL_REVISION = "29e01c4e8d000f4bcd70751be16fa94bf3d85a18"


def required_env(name: str, default: str | None = None) -> str:
    value = str(os.getenv(name, default or "")).strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def reference_metadata() -> tuple[Path, str, str, str]:
    """Load the legacy single-reference contract used by isolated A/B runs."""

    wav_path = Path(required_env("TTS_REFERENCE_WAV", "/evaluation/reference.wav"))
    metadata_path = Path(
        required_env("TTS_REFERENCE_METADATA", "/evaluation/reference.json")
    )
    if not wav_path.is_file() or not metadata_path.is_file():
        raise RuntimeError(
            "TTS reference is missing; install it with scripts/tts_reference.py"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    text = str(metadata.get("text") or "").strip()
    expected_sha = str(metadata.get("audio_sha256") or "").strip().lower()
    license_id = str(metadata.get("license_id") or "").strip()
    actual_sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    if not text or not license_id or expected_sha != actual_sha:
        raise RuntimeError("Shared TTS reference metadata or SHA-256 is invalid")
    return wav_path, text, actual_sha, license_id


class _RuntimeVoices:
    def __init__(
        self,
        *,
        catalog: VoiceCatalog | None,
        profiles: dict[str, VoiceProfile],
        default_speaker_id: str,
        revision: str,
    ) -> None:
        self.catalog = catalog
        self.profiles = profiles
        self.default_speaker_id = default_speaker_id
        self.revision = revision

    def resolve(self, *, speaker_id: str, language_hint: str | None, text: str) -> VoiceProfile:
        if self.catalog is not None:
            return resolve_voice_profile(
                self.catalog,
                requested_speaker_id=speaker_id,
                language_hint=language_hint,
                text=text,
            )
        requested = str(speaker_id or "default").strip() or "default"
        if requested != "default":
            raise ValueError(f"unknown speaker_id: {requested}")
        return self.profiles[self.default_speaker_id]


def runtime_voices() -> _RuntimeVoices:
    voice_root = str(os.getenv("TTS_VOICE_ROOT") or "").strip()
    if voice_root:
        try:
            catalog = validate_voice_catalog(Path(voice_root))
        except ValueError as exc:
            raise RuntimeError(f"invalid TTS voice catalog: {exc}") from exc
        configured_default = str(
            os.getenv("TTS_DEFAULT_SPEAKER") or catalog.default_speaker_id
        ).strip()
        if configured_default not in catalog.profiles:
            raise RuntimeError(
                f"TTS_DEFAULT_SPEAKER is not in the voice catalog: {configured_default}"
            )
        if configured_default != catalog.default_speaker_id:
            catalog = VoiceCatalog(
                root=catalog.root,
                default_speaker_id=configured_default,
                language_routes=catalog.language_routes,
                profiles=catalog.profiles,
                revision=catalog.revision,
            )
        return _RuntimeVoices(
            catalog=catalog,
            profiles=dict(catalog.profiles),
            default_speaker_id=configured_default,
            revision=catalog.revision,
        )

    wav_path, text, audio_sha, license_id = reference_metadata()
    profile = VoiceProfile(
        speaker_id="default",
        wav_path=wav_path,
        metadata_path=Path(required_env("TTS_REFERENCE_METADATA", "/evaluation/reference.json")),
        text=text,
        audio_sha256=audio_sha,
        license_id=license_id,
        languages=("zh", "en", "mixed"),
    )
    return _RuntimeVoices(
        catalog=None,
        profiles={"default": profile},
        default_speaker_id="default",
        revision=audio_sha,
    )


def tensor_pcm16(tensor: Any) -> bytes:
    import numpy as np

    array = tensor.detach().cpu().numpy().astype(np.float32).reshape(-1)
    if not array.size:
        raise RuntimeError("CosyVoice returned empty audio")
    return (np.clip(array, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def worker_target(connection: Connection) -> None:
    try:
        from cosyvoice.cli.cosyvoice import AutoModel
        from huggingface_hub import snapshot_download

        model_id = required_env("COSYVOICE3_MODEL_ID", DEFAULT_MODEL_ID)
        model_revision = required_env(
            "COSYVOICE3_MODEL_REVISION", DEFAULT_MODEL_REVISION
        )
        voices = runtime_voices()
        model_path = snapshot_download(repo_id=model_id, revision=model_revision)
        model = AutoModel(
            model_dir=model_path,
            fp16=required_env("COSYVOICE3_FP16", "1") == "1",
        )
        sample_rate = int(model.sample_rate)
        prompt_prefix = required_env(
            "COSYVOICE3_PROMPT_PREFIX", "You are a helpful assistant."
        )
        connection.send(
            {
                "type": "ready",
                "model_id": model_id,
                "model_revision": model_revision,
                "voice_catalog_revision": voices.revision,
                "default_speaker_id": voices.default_speaker_id,
                "speaker_ids": sorted(voices.profiles),
                "sample_rate": sample_rate,
                "native_audio_streaming": True,
            }
        )
    except Exception as exc:
        connection.send(
            {"type": "error", "message": f"CosyVoice startup failed: {exc}"}
        )
        return

    while True:
        payload = connection.recv()
        if payload.get("type") == "shutdown":
            connection.send({"type": "stopped"})
            return
        if payload.get("type") != "synthesize":
            connection.send({"type": "error", "message": "unsupported worker request"})
            continue
        started = time.perf_counter()
        first_audio_at: float | None = None
        try:
            text = str(payload.get("text") or "")
            profile = voices.resolve(
                speaker_id=str(payload.get("speaker_id") or "default"),
                language_hint=(
                    str(payload.get("language_hint"))
                    if payload.get("language_hint") is not None
                    else None
                ),
                text=text,
            )
            prompt_text = prompt_prefix + "<|endofprompt|>" + profile.text
            for output in model.inference_zero_shot(
                text,
                prompt_text,
                str(profile.wav_path),
                stream=True,
            ):
                pcm = tensor_pcm16(output["tts_speech"])
                if first_audio_at is None:
                    first_audio_at = time.perf_counter()
                connection.send(
                    {"type": "audio", "pcm": pcm, "sample_rate": sample_rate}
                )
            completed = time.perf_counter()
            connection.send(
                {
                    "type": "complete",
                    "metrics": {
                        "generate_seconds": completed - started,
                        "native_first_audio_seconds": (
                            first_audio_at - started if first_audio_at is not None else None
                        ),
                    },
                    "provider_metadata": {
                        "native_audio_streaming": True,
                        "voice_catalog_revision": voices.revision,
                        "speaker_id": profile.speaker_id,
                        "reference_sha256": profile.audio_sha256,
                    },
                }
            )
        except Exception as exc:
            connection.send({"type": "error", "message": str(exc)})


def create_provider() -> WorkerBackedCandidateProvider:
    voices = runtime_voices()
    software_revision = required_env(
        "COSYVOICE3_SOURCE_REVISION", DEFAULT_SOFTWARE_REVISION
    )
    model_id = required_env("COSYVOICE3_MODEL_ID", DEFAULT_MODEL_ID)
    model_revision = required_env(
        "COSYVOICE3_MODEL_REVISION", DEFAULT_MODEL_REVISION
    )
    voice_artifacts = tuple(
        TTSModelArtifact(
            kind="voice_reference",
            artifact_id=f"chromie/voices/{profile.speaker_id}/reference.wav",
            revision=f"sha256:{profile.audio_sha256}",
            license_id=profile.license_id,
        )
        for profile in sorted(voices.profiles.values(), key=lambda item: item.speaker_id)
    )
    capabilities = TTSProviderCapabilities(
        provider_id=PROVIDER_ID,
        implementation="Fun-CosyVoice3 transformers/ONNX",
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
            *voice_artifacts,
        ),
        license_review_status="declared_project_assets",
        languages=("zh", "en", "fr", "es", "ja", "ko", "it", "ru", "de"),
        sample_rates=(24000,),
        max_concurrency=1,
        native_text_streaming=True,
        native_audio_streaming=True,
        request_cancellation=True,
        speaker_profiles=True,
        voice_cloning=True,
    )
    worker = StreamingProcessWorker(
        worker_target,
        name="cosyvoice3-worker",
        startup_timeout_s=float(os.getenv("TTS_WORKER_STARTUP_TIMEOUT_SEC", "1200")),
        cancel_drain_timeout_s=float(
            os.getenv("TTS_CANDIDATE_CANCEL_DRAIN_TIMEOUT_SEC", "3")
        ),
    )
    speakers = ["default", *sorted(voices.profiles)]
    return WorkerBackedCandidateProvider(
        capabilities=capabilities,
        worker=worker,
        speakers=speakers,
    )
