#!/usr/bin/env python3
"""Install and validate the local reference voice used by cloned-voice TTS backends."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

DEFAULT_REFERENCE_DIR = Path(".chromie/private/tts-voice")
REFERENCE_WAV = "reference.wav"
REFERENCE_METADATA = "reference.json"


def _normalized_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _wav_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_wav(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"reference WAV is missing: {path}")
    payload = path.read_bytes()
    if len(payload) <= 44:
        raise ValueError("reference WAV is empty or too short")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValueError("reference audio must be a RIFF/WAVE file")


def validate_reference_dir(reference_dir: Path) -> dict[str, Any]:
    root = reference_dir.expanduser().resolve()
    wav_path = root / REFERENCE_WAV
    metadata_path = root / REFERENCE_METADATA
    _validate_wav(wav_path)
    if not metadata_path.is_file():
        raise ValueError(f"reference metadata is missing: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("reference metadata is not valid UTF-8 JSON") from exc
    if not isinstance(metadata, dict):
        raise ValueError("reference metadata must be a JSON object")
    transcript = _normalized_text(metadata.get("text", ""))
    license_id = _normalized_text(metadata.get("license_id", ""))
    expected_sha = str(metadata.get("audio_sha256") or "").strip().lower()
    actual_sha = _wav_sha256(wav_path)
    if not transcript:
        raise ValueError("reference metadata text is required")
    if not license_id:
        raise ValueError("reference metadata license_id is required")
    if expected_sha != actual_sha:
        raise ValueError("reference metadata audio_sha256 does not match reference.wav")
    return {
        **metadata,
        "text": transcript,
        "license_id": license_id,
        "audio_sha256": actual_sha,
        "reference_dir": str(root),
        "wav_path": str(wav_path),
        "metadata_path": str(metadata_path),
    }


def install_reference(
    *,
    source_wav: Path,
    transcript: str,
    license_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    source = source_wav.expanduser().resolve()
    _validate_wav(source)
    normalized_transcript = _normalized_text(transcript)
    normalized_license = _normalized_text(license_id)
    if not normalized_transcript:
        raise ValueError("transcript is required")
    if not normalized_license:
        raise ValueError("license_id is required")

    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target_wav = root / REFERENCE_WAV
    temporary_wav = root / f".{REFERENCE_WAV}.tmp"
    shutil.copyfile(source, temporary_wav)
    temporary_wav.replace(target_wav)
    metadata = {
        "schema_version": 1,
        "purpose": "chromie-default-cloned-voice-reference",
        "text": normalized_transcript,
        "audio_file": REFERENCE_WAV,
        "audio_sha256": _wav_sha256(target_wav),
        "license_id": normalized_license,
        "source_file": source.name,
        "operator_supplied": True,
    }
    temporary_metadata = root / f".{REFERENCE_METADATA}.tmp"
    temporary_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_metadata.replace(root / REFERENCE_METADATA)
    return validate_reference_dir(root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate an installed reference")
    validate.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR)

    install = subparsers.add_parser("install", help="Install an authorized WAV reference")
    install.add_argument("--source-wav", type=Path, required=True)
    install.add_argument("--transcript", required=True)
    install.add_argument("--license-id", required=True)
    install.add_argument("--output-dir", type=Path, default=DEFAULT_REFERENCE_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate":
            result = validate_reference_dir(args.reference_dir)
        else:
            result = install_reference(
                source_wav=args.source_wav,
                transcript=args.transcript,
                license_id=args.license_id,
                output_dir=args.output_dir,
            )
    except ValueError as exc:
        raise SystemExit(f"[tts-reference][error] {exc}") from exc
    print(
        "[tts-reference] valid "
        f"dir={result['reference_dir']} sha256={result['audio_sha256']} "
        f"license_id={result['license_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
