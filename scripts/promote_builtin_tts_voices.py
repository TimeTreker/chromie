#!/usr/bin/env python3
"""Promote the local AI-generated Chromie voices into Git-controlled assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))

from voice_catalog import (  # noqa: E402
    DEFAULT_SPEAKER_ID,
    REFERENCE_METADATA,
    REFERENCE_WAV,
    SUPPORTED_SPEAKER_IDS,
    VOICE_MANIFEST,
    validate_voice_catalog,
)

DEFAULT_SOURCE_DIR = Path(".chromie/private/tts-voice")
DEFAULT_OUTPUT_DIR = Path("assets/tts/voices")
SOURCE_CANDIDATES = {
    "chromie_zh": ("chromie_zh.wav", "chromie_cn.wav"),
    "chromie_en": ("chromie_en.wav",),
    "chromie_mixed": ("chromie_mixed.wav",),
}
LANGUAGES = {
    "chromie_zh": ["zh"],
    "chromie_en": ["en"],
    "chromie_mixed": ["zh", "en", "mixed"],
}


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_source(source_dir: Path, speaker_id: str) -> Path:
    for name in SOURCE_CANDIDATES[speaker_id]:
        candidate = source_dir / name
        if candidate.is_file():
            return candidate
    names = ", ".join(SOURCE_CANDIDATES[speaker_id])
    raise ValueError(f"missing {speaker_id} WAV; expected one of: {names}")


def _extract_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("text", "transcript", "prompt_text", "reference_text"):
            value = _normalized_text(payload.get(key))
            if value:
                return value
        for key in ("metadata", "reference", "speaker"):
            value = _extract_text(payload.get(key))
            if value:
                return value
    return ""


def _sidecar_transcript(source_dir: Path, source_wav: Path, speaker_id: str) -> str:
    candidates = [
        source_dir / f"{speaker_id}.txt",
        source_wav.with_suffix(".txt"),
        source_dir / f"{speaker_id}.json",
        source_wav.with_suffix(".json"),
    ]
    if speaker_id == "chromie_mixed":
        reference_wav = source_dir / "reference.wav"
        reference_json = source_dir / "reference.json"
        if reference_wav.is_file() and reference_json.is_file():
            if _sha256(reference_wav) == _sha256(source_wav):
                candidates.append(reference_json)
    for path in candidates:
        if not path.is_file():
            continue
        if path.suffix == ".txt":
            text = _normalized_text(path.read_text(encoding="utf-8"))
        else:
            try:
                text = _extract_text(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        if text:
            return text
    return ""


def promote(
    *,
    source_dir: Path,
    output_dir: Path,
    transcripts: dict[str, str],
) -> dict[str, Any]:
    source_root = source_dir.expanduser().resolve()
    output_root = output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, tuple[Path, str]] = {}
    for speaker_id in SUPPORTED_SPEAKER_IDS:
        source_wav = _find_source(source_root, speaker_id)
        transcript = _normalized_text(transcripts.get(speaker_id)) or _sidecar_transcript(
            source_root, source_wav, speaker_id
        )
        if not transcript:
            raise ValueError(
                f"missing exact transcript for {speaker_id}; provide --{speaker_id.removeprefix('chromie_')}-transcript "
                f"or add {speaker_id}.txt beside the WAV"
            )
        resolved[speaker_id] = (source_wav, transcript)

    for speaker_id, (source_wav, transcript) in resolved.items():
        profile_root = output_root / speaker_id
        profile_root.mkdir(parents=True, exist_ok=True)
        target_wav = profile_root / REFERENCE_WAV
        temporary_wav = profile_root / f".{REFERENCE_WAV}.tmp"
        shutil.copyfile(source_wav, temporary_wav)
        temporary_wav.replace(target_wav)
        metadata = {
            "schema_version": 1,
            "speaker_id": speaker_id,
            "purpose": "chromie-built-in-cosyvoice-reference",
            "source": "ai_generated",
            "contributor": "project_owner",
            "redistribution_permitted": True,
            "operator_supplied": False,
            "text": transcript,
            "audio_file": REFERENCE_WAV,
            "audio_sha256": _sha256(target_wav),
            "license_id": "project-ai-generated-voice",
            "languages": LANGUAGES[speaker_id],
            "source_file": source_wav.name,
        }
        (profile_root / REFERENCE_METADATA).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "schema_version": 1,
        "purpose": "chromie-built-in-voice-catalog",
        "default_speaker_id": DEFAULT_SPEAKER_ID,
        "speakers": list(SUPPORTED_SPEAKER_IDS),
        "language_routes": {
            "zh": "chromie_zh",
            "en": "chromie_en",
            "mixed": "chromie_mixed",
        },
    }
    (output_root / VOICE_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    catalog = validate_voice_catalog(output_root)
    return {
        "voice_root": str(catalog.root),
        "default_speaker_id": catalog.default_speaker_id,
        "speaker_ids": list(catalog.speaker_ids()),
        "catalog_revision": catalog.revision,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--zh-transcript", default="")
    parser.add_argument("--en-transcript", default="")
    parser.add_argument("--mixed-transcript", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = promote(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            transcripts={
                "chromie_zh": args.zh_transcript,
                "chromie_en": args.en_transcript,
                "chromie_mixed": args.mixed_transcript,
            },
        )
    except ValueError as exc:
        raise SystemExit(f"[tts-voices][error] {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print("[tts-voices] Run 'git add assets/tts/voices' to commit the built-in voices.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
