#!/usr/bin/env python3
"""Compare final ASR backend accuracy on a manifest of reference audio."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for import_path in (ROOT, ROOT / "asr"):
    value = str(import_path)
    if value not in sys.path:
        sys.path.insert(0, value)

SAMPLE_RATE = 16000
SENSEVOICE_MODEL_ID = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_SENSEVOICE_ROOT = (
    "/root/.cache/huggingface/sherpa-onnx/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)
SPECIAL_TOKEN_RE = re.compile(r"<\|[^>]*\|>")


@dataclass(frozen=True)
class EvalSample:
    sample_id: str
    audio_path: Path
    text: str
    language: str | None = None


def edit_distance(left: list[str], right: list[str]) -> int:
    rows = len(left) + 1
    cols = len(right) + 1
    previous = list(range(cols))
    for row in range(1, rows):
        current = [row] + [0] * (cols - 1)
        for col in range(1, cols):
            cost = 0 if left[row - 1] == right[col - 1] else 1
            current[col] = min(
                previous[col] + 1,
                current[col - 1] + 1,
                previous[col - 1] + cost,
            )
        previous = current
    return previous[-1]


def normalize_text(value: str) -> str:
    value = SPECIAL_TOKEN_RE.sub(" ", value).lower()
    chars: list[str] = []
    for char in value:
        if unicodedata.category(char).startswith("P"):
            chars.append(" ")
        else:
            chars.append(char)
    return " ".join("".join(chars).split())


def word_tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    if " " in normalized:
        return normalized.split()
    return list(normalized)


def char_tokens(value: str) -> list[str]:
    return list(normalize_text(value).replace(" ", ""))


def error_rate(reference: list[str], hypothesis: list[str]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def _resolve_manifest_audio(manifest: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (manifest.parent / path).resolve()


def read_manifest(path: Path) -> list[EvalSample]:
    samples: list[EvalSample] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        payload = json.loads(line)
        try:
            sample_id = str(payload["id"])
            audio = str(payload["audio"])
            text = str(payload["text"])
        except KeyError as exc:
            raise ValueError(f"{path}:{line_number} is missing {exc.args[0]!r}") from exc
        language = payload.get("language")
        samples.append(
            EvalSample(
                sample_id=sample_id,
                audio_path=_resolve_manifest_audio(path, audio),
                text=text,
                language=str(language) if language else None,
            )
        )
    if not samples:
        raise ValueError(f"{path} contains no ASR evaluation samples")
    return samples


def sensevoice_smoke_samples(audio_root: Path) -> list[EvalSample]:
    return [
        EvalSample(
            sample_id="sensevoice_en",
            audio_path=audio_root / "test_wavs" / "en.wav",
            text="The tribal chieftain called for the boy and presented him with 50 pieces of gold.",
            language="en",
        ),
        EvalSample(
            sample_id="sensevoice_zh",
            audio_path=audio_root / "test_wavs" / "zh.wav",
            text="开放时间早上9点至下午5点。",
            language="zh",
        ),
    ]


def load_audio(path: Path, sample_rate: int) -> tuple[Any, float]:
    import soundfile as sf

    audio, actual_rate = sf.read(path, dtype="float32")
    if actual_rate != sample_rate:
        raise ValueError(f"{path} sample rate {actual_rate}, expected {sample_rate}")
    if getattr(audio, "ndim", 1) > 1:
        audio = audio[:, 0]
    return audio, len(audio) / sample_rate


def create_backend(args: argparse.Namespace, backend_name: str) -> Any:
    try:
        from asr.backends import ASRBackendConfig, create_final_asr_backend
    except ImportError:
        from backends import ASRBackendConfig, create_final_asr_backend

    if backend_name == "sherpa_onnx":
        sherpa_model = args.sherpa_model or args.audio_root
        return create_final_asr_backend(
            ASRBackendConfig(
                backend="sherpa_onnx",
                mode="final",
                model_name=str(sherpa_model),
                model_revision=args.sherpa_revision,
                device=args.sherpa_device,
                compute_type=args.sherpa_compute_type,
                sample_rate=args.sample_rate,
                sherpa_model_type=args.sherpa_model_type,
                sherpa_provider=args.sherpa_provider,
                sherpa_num_threads=args.sherpa_num_threads,
                sherpa_language=args.sherpa_language,
                sherpa_use_itn=args.sherpa_use_itn,
                sherpa_debug=args.sherpa_debug,
            )
        )

    if backend_name == "faster_whisper":
        return create_final_asr_backend(
            ASRBackendConfig(
                backend="faster_whisper",
                mode="final",
                model_name=args.faster_whisper_model,
                model_revision=args.faster_whisper_revision,
                device=args.faster_whisper_device,
                compute_type=args.faster_whisper_compute_type,
                sample_rate=args.sample_rate,
            )
        )

    raise ValueError(f"Unsupported evaluator backend: {backend_name}")


def transcribe_sample(
    backend: Any,
    backend_name: str,
    sample: EvalSample,
    audio: Any,
    args: argparse.Namespace,
) -> str:
    if backend_name != "faster_whisper":
        text, _ = backend.transcribe_final(audio)
        return text

    language = sample.language
    if args.faster_whisper_language != "sample":
        language = None if args.faster_whisper_language == "auto" else args.faster_whisper_language
    text, _ = backend.transcribe_final(
        audio,
        language=language,
        beam_size=args.faster_whisper_beam_size,
        vad_filter=args.faster_whisper_vad_filter,
        condition_on_previous_text=False,
        temperature=0.0,
    )
    return text


def evaluate_backend(
    args: argparse.Namespace,
    backend_name: str,
    samples: list[EvalSample],
) -> dict[str, Any]:
    started = time.perf_counter()
    backend = create_backend(args, backend_name)
    load_s = time.perf_counter() - started

    word_edits = 0
    word_count = 0
    char_edits = 0
    char_count = 0
    audio_s = 0.0
    decode_s = 0.0
    rows: list[dict[str, Any]] = []

    for sample in samples:
        audio, duration = load_audio(sample.audio_path, args.sample_rate)
        started = time.perf_counter()
        hypothesis = transcribe_sample(backend, backend_name, sample, audio, args)
        sample_decode_s = time.perf_counter() - started

        ref_words = word_tokens(sample.text)
        hyp_words = word_tokens(hypothesis)
        ref_chars = char_tokens(sample.text)
        hyp_chars = char_tokens(hypothesis)
        sample_word_edits = edit_distance(ref_words, hyp_words)
        sample_char_edits = edit_distance(ref_chars, hyp_chars)

        word_edits += sample_word_edits
        word_count += len(ref_words)
        char_edits += sample_char_edits
        char_count += len(ref_chars)
        audio_s += duration
        decode_s += sample_decode_s
        rows.append(
            {
                "id": sample.sample_id,
                "audio": str(sample.audio_path),
                "language": sample.language,
                "reference": sample.text,
                "hypothesis": hypothesis,
                "wer": error_rate(ref_words, hyp_words),
                "cer": error_rate(ref_chars, hyp_chars),
                "duration_s": duration,
                "decode_s": sample_decode_s,
                "rtf": sample_decode_s / duration if duration else None,
            }
        )

    return {
        "backend": backend_name,
        "load_s": load_s,
        "samples_count": len(samples),
        "wer": word_edits / word_count if word_count else 0.0,
        "cer": char_edits / char_count if char_count else 0.0,
        "audio_s": audio_s,
        "decode_s": decode_s,
        "rtf": decode_s / audio_s if audio_s else None,
        "samples": rows,
    }


def print_table(results: list[dict[str, Any]]) -> None:
    print("backend           samples  WER     CER     RTF     decode_s  load_s")
    for result in results:
        print(
            f"{result['backend']:<17} "
            f"{result['samples_count']:>7} "
            f"{result['wer']:.4f}  "
            f"{result['cer']:.4f}  "
            f"{result['rtf']:.4f}  "
            f"{result['decode_s']:.3f}     "
            f"{result['load_s']:.3f}"
        )
    print()
    for result in results:
        print(f"[{result['backend']}]")
        for sample in result["samples"]:
            print(
                f"- {sample['id']}: WER={sample['wer']:.4f} "
                f"CER={sample['cer']:.4f} RTF={sample['rtf']:.4f} "
                f"text={sample['hypothesis']!r}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="JSONL samples with id, audio, text, and optional language fields.",
    )
    parser.add_argument(
        "--sample-set",
        choices=("sensevoice-smoke",),
        default="sensevoice-smoke",
        help="Built-in sample set to use when --manifest is omitted.",
    )
    parser.add_argument("--audio-root", type=Path, default=Path(DEFAULT_SENSEVOICE_ROOT))
    parser.add_argument(
        "--backend",
        action="append",
        choices=("faster_whisper", "sherpa_onnx"),
        help="Backend to evaluate. Repeat to set order. Defaults to both.",
    )
    parser.add_argument("--sample-rate", type=int, default=SAMPLE_RATE)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--fail-wer-above", type=float)
    parser.add_argument("--fail-cer-above", type=float)

    parser.add_argument("--faster-whisper-model", default="Systran/faster-whisper-small")
    parser.add_argument(
        "--faster-whisper-revision",
        default="536b0662742c02347bc0e980a01041f333bce120",
    )
    parser.add_argument("--faster-whisper-device", default="cpu")
    parser.add_argument("--faster-whisper-compute-type", default="int8")
    parser.add_argument("--faster-whisper-language", default="auto")
    parser.add_argument("--faster-whisper-beam-size", type=int, default=1)
    parser.add_argument("--faster-whisper-vad-filter", action="store_true")

    parser.add_argument("--sherpa-model", type=Path)
    parser.add_argument("--sherpa-revision", default=SENSEVOICE_MODEL_ID)
    parser.add_argument("--sherpa-device", default="cpu")
    parser.add_argument("--sherpa-compute-type", default="int8")
    parser.add_argument("--sherpa-model-type", default="sense_voice")
    parser.add_argument("--sherpa-provider", default="cpu")
    parser.add_argument("--sherpa-num-threads", type=int, default=1)
    parser.add_argument("--sherpa-language", default="auto")
    parser.add_argument("--sherpa-use-itn", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sherpa-debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = read_manifest(args.manifest) if args.manifest else sensevoice_smoke_samples(args.audio_root)
    backends = args.backend or ["sherpa_onnx", "faster_whisper"]
    results = [evaluate_backend(args, backend, samples) for backend in backends]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_table(results)

    failed = False
    for result in results:
        if args.fail_wer_above is not None and result["wer"] > args.fail_wer_above:
            print(
                f"{result['backend']} WER {result['wer']:.4f} exceeds "
                f"{args.fail_wer_above:.4f}",
                file=sys.stderr,
            )
            failed = True
        if args.fail_cer_above is not None and result["cer"] > args.fail_cer_above:
            print(
                f"{result['backend']} CER {result['cer']:.4f} exceeds "
                f"{args.fail_cer_above:.4f}",
                file=sys.stderr,
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
