#!/usr/bin/env python3
"""Generate one locally owned reference voice for candidate TTS comparison."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmark_tts import request_health, synthesize_case


DEFAULT_TEXT = (
    "你好，我是 Chromie，很高兴认识你。"
    "Today is a good day to learn something new together."
)


def build_metadata(
    *,
    text: str,
    wav_path: Path,
    health: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    wav_bytes = wav_path.read_bytes()
    if len(wav_bytes) <= 44 or int(result.get("audio_bytes") or 0) <= 0:
        raise RuntimeError("reference synthesis did not produce non-empty WAV audio")
    provider = health.get("provider")
    if not isinstance(provider, dict):
        raise RuntimeError("reference source did not expose TTSProvider metadata")
    return {
        "schema_version": 1,
        "purpose": "tts-provider-ab-shared-zero-shot-reference",
        "text": text,
        "audio_file": wav_path.name,
        "audio_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        "pcm_sha256": result.get("audio_sha256"),
        "audio_bytes": result.get("audio_bytes"),
        "observed_audio_seconds": result.get("observed_audio_seconds"),
        "source_provider": provider,
        "license_id": "Chromie-generated-evaluation-only",
        "production_voice_approved": False,
    }


async def run(args: argparse.Namespace) -> tuple[Path, Path]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = args.output_dir / "reference.wav"
    metadata_path = args.output_dir / "reference.json"
    health = await request_health(args.url)
    result = await synthesize_case(
        url=args.url,
        speaker_id=args.speaker,
        case_name="shared_voice_reference",
        text=args.text,
        timeout_s=args.timeout,
        audio_output=wav_path,
    )
    metadata = build_metadata(
        text=args.text,
        wav_path=wav_path,
        health=health,
        result=result,
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return wav_path, metadata_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:5000")
    parser.add_argument("--speaker", default="default")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".chromie/evidence/tts-provider-ab/reference"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.text.strip() or args.timeout <= 0:
        raise SystemExit("--text must be non-empty and --timeout must be > 0")
    wav_path, metadata_path = asyncio.run(run(args))
    print(f"Wrote shared reference WAV: {wav_path}")
    print(f"Wrote shared reference metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
