#!/usr/bin/env python3
"""Measure Chromie TTS latency and stage timings without audio playback."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Any

import websockets


DEFAULT_CASES = [
    ("short_en", "Hello from Chromie."),
    ("short_zh", "你好，我在这里。"),
    ("weather_zh", "北京今天有雷雨，气温二十五到三十一度，降雨概率很高。"),
]


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


async def request_health(url: str) -> dict[str, Any]:
    async with websockets.connect(url, max_size=20_000_000, open_timeout=15) as ws:
        await ws.send(json.dumps({"type": "health"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        if not isinstance(raw, str):
            raise RuntimeError("TTS health returned binary data")
        data = json.loads(raw)
        if data.get("type") != "pong":
            raise RuntimeError(f"Unexpected TTS health response: {data}")
        return data


async def synthesize_case(
    *,
    url: str,
    speaker_id: str,
    case_name: str,
    text: str,
    timeout_s: float,
    audio_output: Path | None = None,
) -> dict[str, Any]:
    request_id = f"benchmark-{case_name}-{uuid.uuid4().hex[:10]}"
    started = time.perf_counter()
    first_binary_at: float | None = None
    audio = bytearray()
    start_metadata: dict[str, Any] = {}
    end_metadata: dict[str, Any] = {}

    async with websockets.connect(
        url,
        max_size=50_000_000,
        open_timeout=15,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "synthesize_stream",
                    "text": text,
                    "speaker_id": speaker_id,
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        )
        async with asyncio.timeout(timeout_s):
            async for message in ws:
                now = time.perf_counter()
                if isinstance(message, bytes):
                    if first_binary_at is None:
                        first_binary_at = now
                    audio.extend(message)
                    continue
                data = json.loads(message)
                message_type = data.get("type")
                if message_type == "start":
                    start_metadata = data
                elif message_type == "error":
                    raise RuntimeError(data.get("message") or "TTS benchmark failed")
                elif message_type == "end":
                    end_metadata = data
                    break
            else:
                raise RuntimeError("TTS websocket closed before end message")

    completed = time.perf_counter()
    sample_rate = int(start_metadata.get("sample_rate") or 44100)
    audio_bytes = len(audio)
    observed_audio_seconds = audio_bytes / (sample_rate * 2) if audio_bytes else 0.0
    audio_path: str | None = None
    if audio_output is not None and audio:
        audio_output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio_output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio)
        audio_path = str(audio_output)
    return {
        "case": case_name,
        "text": text,
        "text_chars": len(text),
        "request_id": request_id,
        "audio_bytes": audio_bytes,
        "audio_sha256": hashlib.sha256(audio).hexdigest() if audio else None,
        "audio_path": audio_path,
        "observed_audio_seconds": round(observed_audio_seconds, 4),
        "observed_first_binary_seconds": round(
            (first_binary_at - started) if first_binary_at is not None else 0.0,
            4,
        ),
        "observed_total_seconds": round(completed - started, 4),
        "start": start_metadata,
        "end": end_metadata,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"count": 0}

    def median_from(path: tuple[str, ...]) -> float:
        values: list[float] = []
        for result in results:
            value: Any = result
            for key in path:
                value = value.get(key, {}) if isinstance(value, dict) else 0.0
            values.append(_number(value))
        return round(statistics.median(values), 4)

    generation_limit_reached_count = sum(
        1
        for result in results
        if bool((result.get("end") or {}).get("generation_limit_reached", False))
    )
    return {
        "count": len(results),
        "generation_limit_reached_count": generation_limit_reached_count,
        "median_first_binary_seconds": median_from(("observed_first_binary_seconds",)),
        "median_total_seconds": median_from(("observed_total_seconds",)),
        "median_audio_seconds": median_from(("end", "audio_seconds")),
        "median_generate_seconds": median_from(("end", "generate_seconds")),
        "median_model_generate_seconds": median_from(
            ("end", "model_generate_seconds")
        ),
        "median_codec_decode_seconds": median_from(
            ("end", "codec_decode_seconds")
        ),
        "median_pcm_conversion_seconds": median_from(
            ("end", "pcm_conversion_seconds")
        ),
        "median_realtime_factor": median_from(("end", "realtime_factor")),
    }


def print_results(payload: dict[str, Any]) -> None:
    health = payload["health"]
    workers = health.get("workers") or []
    worker_codec = workers[0].get("audio_codec") if workers else None
    effective_codec = (
        worker_codec.get("effective")
        if isinstance(worker_codec, dict)
        else health.get("audio_codec_device")
    )
    print(
        "TTS profile: "
        f"quantization={health.get('quantization')} "
        f"context={health.get('context_size')} "
        f"batch={health.get('n_batch')} "
        f"codec={effective_codec}"
    )
    print(
        "case                 chars  first_audio  generate  model  codec  audio  rtf  limit"
    )
    for result in payload["results"]:
        end = result["end"]
        print(
            f"{result['case']:<20} "
            f"{result['text_chars']:>5} "
            f"{result['observed_first_binary_seconds']:>11.3f} "
            f"{_number(end.get('generate_seconds')):>9.3f} "
            f"{_number(end.get('model_generate_seconds')):>6.3f} "
            f"{_number(end.get('codec_decode_seconds')):>6.3f} "
            f"{_number(end.get('audio_seconds')):>6.3f} "
            f"{_number(end.get('realtime_factor')):>5.3f} "
            f"{'yes' if end.get('generation_limit_reached') else 'no':>6}"
        )
    summary = payload["summary"]
    print(
        "median: "
        f"first_audio={summary.get('median_first_binary_seconds', 0):.3f}s "
        f"generate={summary.get('median_generate_seconds', 0):.3f}s "
        f"audio={summary.get('median_audio_seconds', 0):.3f}s "
        f"rtf={summary.get('median_realtime_factor', 0):.3f} "
        f"generation_limit_reached={summary.get('generation_limit_reached_count', 0)}"
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    health = await request_health(args.url)
    cases = list(DEFAULT_CASES)
    for index, text in enumerate(args.text or []):
        cases.append((f"custom_{index + 1}", text))

    for _ in range(args.warmup):
        await synthesize_case(
            url=args.url,
            speaker_id=args.speaker,
            case_name="warmup",
            text=cases[0][1],
            timeout_s=args.timeout,
        )

    results: list[dict[str, Any]] = []
    for repeat in range(args.repeat):
        for name, text in cases:
            case_name = name if args.repeat == 1 else f"{name}_{repeat + 1}"
            results.append(
                await synthesize_case(
                    url=args.url,
                    speaker_id=args.speaker,
                    case_name=case_name,
                    text=text,
                    timeout_s=args.timeout,
                )
            )
    return {
        "schema_version": 1,
        "url": args.url,
        "speaker": args.speaker,
        "health": health,
        "results": results,
        "summary": summarize(results),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("TTS_URL", "ws://127.0.0.1:5000"),
    )
    parser.add_argument(
        "--speaker",
        default=os.getenv("TTS_SPEAKER_ID", "default"),
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--text", action="append", help="additional benchmark text")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--max-median-rtf",
        type=float,
        help="exit non-zero when median generation/audio RTF exceeds this value",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repeat < 1 or args.warmup < 0:
        raise SystemExit("--repeat must be >= 1 and --warmup must be >= 0")
    payload = asyncio.run(run(args))
    print_results(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote benchmark JSON: {args.output}")
    generation_limit_reached_count = int(
        payload["summary"].get("generation_limit_reached_count") or 0
    )
    if generation_limit_reached_count:
        print(
            "FAIL: TTS generation reached max_length in "
            f"{generation_limit_reached_count} benchmark case(s); audio may be truncated",
            file=sys.stderr,
        )
        return 3

    threshold = args.max_median_rtf
    median_rtf = _number(payload["summary"].get("median_realtime_factor"))
    if threshold is not None and median_rtf > threshold:
        print(
            f"FAIL: median realtime factor {median_rtf:.3f} exceeds {threshold:.3f}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
