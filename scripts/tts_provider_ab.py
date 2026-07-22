#!/usr/bin/env python3
"""Run one comparable multilingual and runtime matrix against TTS providers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_tts import request_health, synthesize_case  # noqa: E402


REQUIRED_KINDS = {
    "chinese",
    "english",
    "mixed",
    "interruption",
    "long_dialogue",
    "concurrency",
}


def load_matrix(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("TTS A/B matrix schema_version must be 1")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("TTS A/B matrix must contain cases")
    ids: set[str] = set()
    kinds: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every TTS A/B case must be an object")
        case_id = str(case.get("id") or "").strip()
        kind = str(case.get("kind") or "").strip()
        if not case_id or case_id in ids:
            raise ValueError(f"invalid or duplicate TTS A/B case id: {case_id!r}")
        if kind not in REQUIRED_KINDS:
            raise ValueError(f"unsupported TTS A/B case kind: {kind!r}")
        ids.add(case_id)
        kinds.add(kind)
        if kind == "long_dialogue":
            turns = case.get("turns")
            if not isinstance(turns, list) or len(turns) < 4:
                raise ValueError("long_dialogue must contain at least four turns")
            if not all(isinstance(turn, str) and turn.strip() for turn in turns):
                raise ValueError("long_dialogue turns must be non-empty strings")
        elif kind == "concurrency":
            texts = case.get("texts")
            if not isinstance(texts, list) or len(texts) < 2:
                raise ValueError("concurrency must contain at least two texts")
            if not all(isinstance(text, str) and text.strip() for text in texts):
                raise ValueError("concurrency texts must be non-empty strings")
        else:
            if not isinstance(case.get("text"), str) or not case["text"].strip():
                raise ValueError(f"{kind} case must contain text")
        if kind == "interruption" and not str(case.get("recovery_text") or "").strip():
            raise ValueError("interruption case must contain recovery_text")
    missing = REQUIRED_KINDS - kinds
    if missing:
        raise ValueError(
            "TTS A/B matrix is missing required kinds: " + ", ".join(sorted(missing))
        )
    return payload


def parse_provider_specs(values: list[str]) -> dict[str, str]:
    providers: dict[str, str] = {}
    for value in values:
        name, separator, url = value.partition("=")
        name = name.strip()
        url = url.strip()
        if not separator or not name or not url:
            raise ValueError("--provider must use NAME=ws://host:port")
        if name in providers:
            raise ValueError(f"duplicate provider label: {name}")
        providers[name] = url
    return providers


def validate_health(label: str, health: dict[str, Any]) -> dict[str, Any]:
    provider = health.get("provider")
    if health.get("provider_contract_version") != 1 or not isinstance(provider, dict):
        raise RuntimeError(
            f"{label} does not expose Chromie TTSProvider contract version 1"
        )
    required = {
        "provider_id",
        "implementation",
        "software_license_id",
        "model_artifacts",
        "license_review_status",
        "languages",
        "sample_rates",
        "max_concurrency",
        "native_text_streaming",
        "native_audio_streaming",
        "request_cancellation",
    }
    missing = sorted(required - set(provider))
    if missing:
        raise RuntimeError(
            f"{label} provider declaration is missing: {', '.join(missing)}"
        )
    artifacts = provider.get("model_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimeError(f"{label} provider has no immutable model artifacts")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not all(
            str(artifact.get(field) or "").strip()
            for field in ("kind", "artifact_id", "revision", "license_id")
        ):
            raise RuntimeError(
                f"{label} provider has an incomplete model artifact declaration"
            )
        revision = str(artifact["revision"]).strip().lower()
        if not (
            re.fullmatch(r"[0-9a-f]{7,64}", revision)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", revision)
        ):
            raise RuntimeError(
                f"{label} provider model artifact revision is mutable: {revision!r}"
            )
    return provider


def _median(results: list[dict[str, Any]], key: str) -> float | None:
    values = [float(result.get(key) or 0.0) for result in results if key in result]
    return round(statistics.median(values), 4) if values else None


async def run_interrupt_case(
    *,
    label: str,
    url: str,
    speaker: str,
    case: dict[str, Any],
    timeout_s: float,
    audio_dir: Path,
) -> dict[str, Any]:
    import websockets

    request_id = f"ab-interrupt-{label}-{uuid.uuid4().hex[:10]}"
    started = time.perf_counter()
    start_metadata: dict[str, Any] = {}
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
                    "text": case["text"],
                    "speaker_id": speaker,
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
        )
        async with asyncio.timeout(timeout_s):
            while True:
                message = await ws.recv()
                if isinstance(message, bytes):
                    raise RuntimeError(
                        "provider emitted audio before the required start metadata"
                    )
                data = json.loads(message)
                if data.get("type") == "error":
                    raise RuntimeError(data.get("message") or "interrupt setup failed")
                if data.get("type") == "start":
                    start_metadata = data
                    break
    closed_at = time.perf_counter()
    recovery = await synthesize_case(
        url=url,
        speaker_id=speaker,
        case_name=f"{case['id']}_recovery",
        text=case["recovery_text"],
        timeout_s=timeout_s,
        audio_output=audio_dir / f"{case['id']}_recovery.wav",
    )
    return {
        "case": case["id"],
        "kind": "interruption",
        "request_id": request_id,
        "start": start_metadata,
        "connection_closed_seconds": round(closed_at - started, 4),
        "recovery": recovery,
        "passed": recovery.get("audio_bytes", 0) > 0,
    }


async def run_provider(
    *,
    label: str,
    url: str,
    speaker: str,
    matrix: dict[str, Any],
    warmup: int,
    timeout_s: float,
    output_dir: Path,
) -> dict[str, Any]:
    health = await request_health(url)
    declaration = validate_health(label, health)
    audio_dir = output_dir / "audio" / label
    first_text = next(
        case["text"] for case in matrix["cases"] if case["kind"] == "chinese"
    )
    for index in range(warmup):
        await synthesize_case(
            url=url,
            speaker_id=speaker,
            case_name=f"warmup_{index + 1}",
            text=first_text,
            timeout_s=timeout_s,
        )

    case_results: list[dict[str, Any]] = []
    synthesis_results: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        case_id = case["id"]
        kind = case["kind"]
        if kind in {"chinese", "english", "mixed"}:
            result = await synthesize_case(
                url=url,
                speaker_id=speaker,
                case_name=case_id,
                text=case["text"],
                timeout_s=timeout_s,
                audio_output=audio_dir / f"{case_id}.wav",
            )
            result["kind"] = kind
            result["passed"] = result.get("audio_bytes", 0) > 0
            case_results.append(result)
            synthesis_results.append(result)
        elif kind == "long_dialogue":
            turns: list[dict[str, Any]] = []
            dialogue_started = time.perf_counter()
            for index, text in enumerate(case["turns"], start=1):
                result = await synthesize_case(
                    url=url,
                    speaker_id=speaker,
                    case_name=f"{case_id}_turn_{index}",
                    text=text,
                    timeout_s=timeout_s,
                    audio_output=audio_dir / f"{case_id}_turn_{index}.wav",
                )
                turns.append(result)
                synthesis_results.append(result)
            case_results.append(
                {
                    "case": case_id,
                    "kind": kind,
                    "turns": turns,
                    "wall_seconds": round(time.perf_counter() - dialogue_started, 4),
                    "passed": all(item.get("audio_bytes", 0) > 0 for item in turns),
                }
            )
        elif kind == "concurrency":
            concurrent_started = time.perf_counter()
            results = await asyncio.gather(
                *(
                    synthesize_case(
                        url=url,
                        speaker_id=speaker,
                        case_name=f"{case_id}_{index}",
                        text=text,
                        timeout_s=timeout_s,
                        audio_output=audio_dir / f"{case_id}_{index}.wav",
                    )
                    for index, text in enumerate(case["texts"], start=1)
                )
            )
            synthesis_results.extend(results)
            case_results.append(
                {
                    "case": case_id,
                    "kind": kind,
                    "requests": results,
                    "wall_seconds": round(time.perf_counter() - concurrent_started, 4),
                    "passed": all(item.get("audio_bytes", 0) > 0 for item in results),
                }
            )
        elif kind == "interruption":
            case_results.append(
                await run_interrupt_case(
                    label=label,
                    url=url,
                    speaker=speaker,
                    case=case,
                    timeout_s=timeout_s,
                    audio_dir=audio_dir,
                )
            )

    return {
        "label": label,
        "url": url,
        "speaker": speaker,
        "provider": declaration,
        "health": health,
        "cases": case_results,
        "summary": {
            "case_count": len(case_results),
            "passed_count": sum(bool(item.get("passed")) for item in case_results),
            "all_cases_passed": all(bool(item.get("passed")) for item in case_results),
            "median_first_binary_seconds": _median(
                synthesis_results, "observed_first_binary_seconds"
            ),
            "median_total_seconds": _median(
                synthesis_results, "observed_total_seconds"
            ),
            "median_realtime_factor": _median(
                [dict(item.get("end") or {}) for item in synthesis_results],
                "realtime_factor",
            ),
        },
    }


def listening_review_template(
    matrix: dict[str, Any],
    provider_results: list[dict[str, Any]],
) -> dict[str, Any]:
    audio_case_ids: list[str] = []
    for case in matrix["cases"]:
        if case["kind"] == "long_dialogue":
            audio_case_ids.extend(
                f"{case['id']}_turn_{index}"
                for index in range(1, len(case["turns"]) + 1)
            )
        elif case["kind"] == "concurrency":
            audio_case_ids.extend(
                f"{case['id']}_{index}"
                for index in range(1, len(case["texts"]) + 1)
            )
        elif case["kind"] == "interruption":
            audio_case_ids.append(f"{case['id']}_recovery")
        else:
            audio_case_ids.append(case["id"])
    return {
        "schema_version": 1,
        "status": "operator_review_required",
        "scale": "1=unacceptable, 5=excellent",
        "dimensions": matrix.get("listening_dimensions", []),
        "reviews": [
            {
                "provider": result["label"],
                "case": case_id,
                "ratings": {
                    dimension: None
                    for dimension in matrix.get("listening_dimensions", [])
                },
                "notes": "",
            }
            for result in provider_results
            for case_id in audio_case_ids
        ],
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    matrix = load_matrix(args.matrix)
    providers = parse_provider_specs(args.provider)
    if len(providers) < 2:
        raise ValueError("A/B evaluation requires at least two --provider entries")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for label, url in providers.items():
        results.append(
            await run_provider(
                label=label,
                url=url,
                speaker=args.speaker,
                matrix=matrix,
                warmup=args.warmup,
                timeout_s=args.timeout,
                output_dir=args.output_dir,
            )
        )
    return {
        "schema_version": 1,
        "matrix": str(args.matrix),
        "provider_count": len(results),
        "providers": results,
        "automated_matrix_passed": all(
            bool(result["summary"]["all_cases_passed"]) for result in results
        ),
        "selection_ready": False,
        "selection_blockers": [
            "complete listening-review.json",
            "review provider and model licenses for the intended deployment",
            "repeat on the claimed target hardware with other GPU workloads active",
            "approve environment-specific latency and quality thresholds",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("scenarios/tts_provider_ab.json"),
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        metavar="NAME=URL",
        help="provider label and Chromie TTSProvider WebSocket endpoint; repeat twice",
    )
    parser.add_argument(
        "--speaker",
        default=os.getenv("TTS_SPEAKER_ID", "default"),
    )
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".chromie/evidence/tts-provider-ab"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the matrix without contacting providers",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matrix = load_matrix(args.matrix)
    if args.check:
        print(
            f"TTS provider A/B matrix valid: {len(matrix['cases'])} cases, "
            f"kinds={','.join(sorted(REQUIRED_KINDS))}"
        )
        return 0
    if args.warmup < 0 or args.timeout <= 0:
        raise SystemExit("--warmup must be >= 0 and --timeout must be > 0")
    payload = asyncio.run(run(args))
    result_path = args.output_dir / "result.json"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_path = args.output_dir / "listening-review.json"
    review_path.write_text(
        json.dumps(
            listening_review_template(matrix, payload["providers"]),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for provider in payload["providers"]:
        summary = provider["summary"]
        print(
            f"{provider['label']}: {summary['passed_count']}/{summary['case_count']} "
            f"first_audio={summary['median_first_binary_seconds']}s "
            f"rtf={summary['median_realtime_factor']}"
        )
    print(f"Wrote A/B result: {result_path}")
    print(f"Listening review required: {review_path}")
    return 0 if payload["automated_matrix_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
