"""Validated multi-speaker voice catalog for cloned-voice TTS providers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

VOICE_MANIFEST = "manifest.json"
REFERENCE_WAV = "reference.wav"
REFERENCE_METADATA = "reference.json"
DEFAULT_SPEAKER_ID = "chromie_mixed"
SUPPORTED_SPEAKER_IDS = ("chromie_zh", "chromie_en", "chromie_mixed")


@dataclass(frozen=True)
class VoiceProfile:
    speaker_id: str
    wav_path: Path
    metadata_path: Path
    text: str
    audio_sha256: str
    license_id: str
    languages: tuple[str, ...]


@dataclass(frozen=True)
class VoiceCatalog:
    root: Path
    default_speaker_id: str
    language_routes: Mapping[str, str]
    profiles: Mapping[str, VoiceProfile]
    revision: str

    def speaker_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.profiles))


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_wav(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"voice WAV is missing: {path}")
    payload = path.read_bytes()
    if len(payload) <= 44:
        raise ValueError(f"voice WAV is empty or too short: {path}")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValueError(f"voice audio must be a RIFF/WAVE file: {path}")


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def validate_voice_profile(root: Path, speaker_id: str) -> VoiceProfile:
    if not re.fullmatch(r"[a-z0-9_]+", speaker_id):
        raise ValueError(f"invalid speaker_id: {speaker_id!r}")
    profile_root = root / speaker_id
    wav_path = profile_root / REFERENCE_WAV
    metadata_path = profile_root / REFERENCE_METADATA
    _validate_wav(wav_path)
    metadata = _read_json(metadata_path, label=f"voice metadata for {speaker_id}")
    metadata_speaker = _normalized_text(metadata.get("speaker_id"))
    if metadata_speaker and metadata_speaker != speaker_id:
        raise ValueError(
            f"voice metadata speaker_id mismatch: {metadata_speaker!r} != {speaker_id!r}"
        )
    text = _normalized_text(metadata.get("text") or metadata.get("transcript"))
    license_id = _normalized_text(metadata.get("license_id"))
    expected_sha = str(metadata.get("audio_sha256") or "").strip().lower()
    actual_sha = _sha256(wav_path)
    raw_languages = metadata.get("languages") or []
    if isinstance(raw_languages, str):
        raw_languages = [raw_languages]
    languages = tuple(
        value for value in (_normalized_text(item).lower() for item in raw_languages) if value
    )
    if not text:
        raise ValueError(f"voice metadata text is required for {speaker_id}")
    if not license_id:
        raise ValueError(f"voice metadata license_id is required for {speaker_id}")
    if expected_sha != actual_sha:
        raise ValueError(
            f"voice metadata audio_sha256 does not match {speaker_id}/{REFERENCE_WAV}"
        )
    if not languages:
        raise ValueError(f"voice metadata languages are required for {speaker_id}")
    return VoiceProfile(
        speaker_id=speaker_id,
        wav_path=wav_path,
        metadata_path=metadata_path,
        text=text,
        audio_sha256=actual_sha,
        license_id=license_id,
        languages=languages,
    )


def validate_voice_catalog(root: Path) -> VoiceCatalog:
    catalog_root = root.expanduser().resolve()
    manifest_path = catalog_root / VOICE_MANIFEST
    manifest = _read_json(manifest_path, label="voice catalog manifest")
    default_speaker_id = _normalized_text(
        manifest.get("default_speaker_id") or DEFAULT_SPEAKER_ID
    )
    raw_speakers = manifest.get("speakers")
    if not isinstance(raw_speakers, list) or not raw_speakers:
        raise ValueError("voice catalog manifest speakers must be a non-empty list")
    speaker_ids = tuple(_normalized_text(item) for item in raw_speakers)
    if any(not item for item in speaker_ids) or len(set(speaker_ids)) != len(speaker_ids):
        raise ValueError("voice catalog manifest speaker IDs must be unique and non-empty")
    profiles = {
        speaker_id: validate_voice_profile(catalog_root, speaker_id)
        for speaker_id in speaker_ids
    }
    if default_speaker_id not in profiles:
        raise ValueError("voice catalog default speaker is not present")
    raw_routes = manifest.get("language_routes") or {}
    if not isinstance(raw_routes, dict):
        raise ValueError("voice catalog language_routes must be an object")
    routes: dict[str, str] = {}
    for raw_language, raw_speaker in raw_routes.items():
        language = _normalized_text(raw_language).lower()
        speaker = _normalized_text(raw_speaker)
        if not language or speaker not in profiles:
            raise ValueError("voice catalog language route is invalid")
        routes[language] = speaker
    canonical = {
        "schema_version": int(manifest.get("schema_version") or 1),
        "default_speaker_id": default_speaker_id,
        "language_routes": dict(sorted(routes.items())),
        "profiles": {
            speaker_id: {
                "audio_sha256": profile.audio_sha256,
                "text": profile.text,
                "license_id": profile.license_id,
                "languages": list(profile.languages),
            }
            for speaker_id, profile in sorted(profiles.items())
        },
    }
    revision = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return VoiceCatalog(
        root=catalog_root,
        default_speaker_id=default_speaker_id,
        language_routes=routes,
        profiles=profiles,
        revision=revision,
    )


def _language_key(language_hint: str | None, text: str) -> str:
    hint = _normalized_text(language_hint).lower().replace("_", "-")
    if hint.startswith("zh"):
        return "zh"
    if hint.startswith("en"):
        return "en"
    has_han = bool(re.search(r"[\u3400-\u9fff]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_han and has_latin:
        return "mixed"
    if has_han:
        return "zh"
    if has_latin:
        return "en"
    return "mixed"


def resolve_voice_profile(
    catalog: VoiceCatalog,
    *,
    requested_speaker_id: str,
    language_hint: str | None,
    text: str,
) -> VoiceProfile:
    requested = _normalized_text(requested_speaker_id) or "default"
    if requested != "default":
        try:
            return catalog.profiles[requested]
        except KeyError as exc:
            raise ValueError(f"unknown speaker_id: {requested}") from exc
    language_key = _language_key(language_hint, text)
    routed = catalog.language_routes.get(language_key, catalog.default_speaker_id)
    return catalog.profiles[routed]
