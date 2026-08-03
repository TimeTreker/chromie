#!/usr/bin/env python3
"""Run bilingual closed-loop TTS/ASR and full workflow playback qualification.

The maintained path is deliberately human-voice independent:

* transport: source text -> Chromie TTS -> PCM/WAV -> Chromie ASR;
* workflow: injected user text -> Gateway/Core/Agent/tools -> TTS -> real host
  playback capture -> ASR verification.

Chinese and English use the same evidence contract. ASR is used as an automated
observer of generated/playback audio, not as a test of an operator's accent.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import uuid
import wave
from typing import Any, Iterable, Sequence

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.clients.asr_client import ASRClient  # noqa: E402
from orchestrator.clients.tts_client import TTSClient  # noqa: E402
from scripts.acceptance_audio import (  # noqa: E402
    AudioFixture,
    HostSpeakerPlayer,
    write_pcm16_wav,
)
from scripts.evaluate_asr_accuracy import (  # noqa: E402
    char_tokens,
    error_rate,
    normalize_text,
    word_tokens,
)
from benchmarks.review.bundle import build_review_bundle  # noqa: E402

DEFAULT_MANIFEST = ROOT / "benchmarks" / "manifests" / "closed_loop_e2e_v1.json"
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "acceptance" / "closed-loop-e2e"


@dataclass(frozen=True)
class ClosedLoopCase:
    case_id: str
    language: str
    text: str
    speaker_id: str
    max_error_rate: float
    turns: tuple[str, ...] = ()
    expected_any: tuple[str, ...] = ()
    expected_all: tuple[str, ...] = ()
    oracle_mode: str = "deterministic"
    deterministic_sources: tuple[str, ...] = ("audio_transport",)
    primary_outcomes: tuple[str, ...] = ()
    semantic_dimensions: tuple[str, ...] = ()
    review_rubric: dict[str, Any] | None = None

    def user_turns(self) -> tuple[str, ...]:
        return self.turns or (self.text,)


@dataclass(frozen=True)
class AudioData:
    pcm16: bytes
    sample_rate: int
    channels: int = 1


class CaptureBackend(AbstractContextManager["CaptureBackend"]):
    name = "unknown"

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "CaptureBackend":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class PulseMonitorCapture(CaptureBackend):
    """Record the actual default output stream through its monitor source."""

    name = "monitor"

    def __init__(self, path: Path, *, sample_rate: int = 16000) -> None:
        super().__init__(path)
        self.sample_rate = sample_rate
        self.process: subprocess.Popen[bytes] | None = None
        self.source_name = self.discover_source()

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("pactl") and shutil.which("parec"))

    @staticmethod
    def discover_source() -> str:
        if not PulseMonitorCapture.available():
            raise RuntimeError("monitor capture requires pactl and parec")
        sink = subprocess.check_output(
            ["pactl", "get-default-sink"], text=True
        ).strip()
        if not sink:
            raise RuntimeError("pactl returned no default sink")
        source = f"{sink}.monitor"
        sources = subprocess.check_output(
            ["pactl", "list", "short", "sources"], text=True
        )
        if source not in sources:
            raise RuntimeError(f"default sink monitor {source!r} was not found")
        return source

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [
                "parec",
                f"--device={self.source_name}",
                "--file-format=wav",
                f"--rate={self.sample_rate}",
                "--channels=1",
                str(self.path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.25)
        if self.process.poll() is not None:
            stderr = (self.process.stderr.read() if self.process.stderr else b"").decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(f"parec failed to start: {stderr.strip()}")

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None


class PhysicalMicrophoneCapture(CaptureBackend):
    """Record speaker output through the configured physical microphone."""

    name = "acoustic"

    def __init__(
        self,
        path: Path,
        *,
        sample_rate: int = 48000,
        device: int | str | None = None,
    ) -> None:
        super().__init__(path)
        self.sample_rate = sample_rate
        self.device = device
        self._frames: list[np.ndarray] = []
        self._stream: Any = None

    @staticmethod
    def available() -> bool:
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            return False
        return True

    def start(self) -> None:
        import sounddevice as sd

        self._frames = []

        def callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
            del frames, time_info
            if status:
                print(f"[closed-loop][audio] {status}", file=sys.stderr)
            self._frames.append(np.array(indata[:, 0], copy=True))

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=callback,
        )
        self._stream.start()
        time.sleep(0.25)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        samples = (
            np.concatenate(self._frames)
            if self._frames
            else np.zeros(0, dtype=np.float32)
        )
        pcm = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
        write_pcm16_wav(
            self.path,
            pcm16=pcm.tobytes(),
            sample_rate=self.sample_rate,
            channels=1,
        )


def utc_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def install_python_log_capture(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(threadName)s %(message)s"
        )
    )
    logging.getLogger().addHandler(handler)
    return handler


def collect_command(
    output: Path,
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        rendered = completed.stdout
        if completed.stderr:
            rendered += "\n--- stderr ---\n" + completed.stderr
        output.write_text(rendered, encoding="utf-8")
        return {
            "command": list(command),
            "returncode": completed.returncode,
            "artifact": str(output),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        output.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return {
            "command": list(command),
            "returncode": None,
            "error": f"{type(exc).__name__}: {exc}",
            "artifact": str(output),
        }


def copy_redacted_env(source: Path, target: Path) -> None:
    sensitive_fragments = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PASSWD",
        "API_KEY",
        "CREDENTIAL",
        "PRIVATE_KEY",
    )
    rendered: list[str] = []
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line or raw_line.lstrip().startswith("#"):
            rendered.append(raw_line)
            continue
        key, value = raw_line.split("=", 1)
        if any(fragment in key.upper() for fragment in sensitive_fragments):
            value = "<redacted>"
        rendered.append(f"{key}={value}")
    target.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def collect_run_diagnostics(output_dir: Path) -> list[dict[str, Any]]:
    diagnostics_dir = output_dir / "diagnostics"
    commands = [
        ("git-status.txt", ["git", "status", "--short"]),
        ("git-revision.txt", ["git", "rev-parse", "HEAD"]),
        (
            "docker-compose-ps.txt",
            ["docker", "compose", "--env-file", ".env.runtime", "ps"],
        ),
        (
            "docker-compose-logs.txt",
            [
                "docker",
                "compose",
                "--env-file",
                ".env.runtime",
                "logs",
                "--no-color",
                "--timestamps",
            ],
        ),
        ("nvidia-smi.txt", ["nvidia-smi"]),
    ]
    records = [
        collect_command(diagnostics_dir / name, command)
        for name, command in commands
    ]
    for candidate in (
        ROOT / ".chromie" / "runtime_profile.json",
        ROOT / ".env.runtime",
    ):
        if candidate.exists():
            target = diagnostics_dir / candidate.name
            if candidate.name.startswith(".env"):
                copy_redacted_env(candidate, target)
            else:
                shutil.copy2(candidate, target)
            records.append(
                {
                    "command": None,
                    "returncode": 0,
                    "artifact": str(target),
                    "source": str(candidate),
                }
            )
    return records


def parse_cases(payload: dict[str, Any], key: str) -> list[ClosedLoopCase]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise ValueError(f"manifest field {key!r} must be an array")
    cases: list[ClosedLoopCase] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"manifest {key} item must be an object")
        oracle = row.get("oracle_policy") or {}
        if not isinstance(oracle, dict):
            raise ValueError(f"manifest {key} oracle_policy must be an object")
        mode = str(oracle.get("mode") or "deterministic")
        deterministic_sources = tuple(
            str(v) for v in oracle.get("deterministic_sources", ["audio_transport"])
        )
        semantic_dimensions = tuple(
            str(v) for v in oracle.get("semantic_dimensions", [])
        )
        if mode not in {"deterministic", "semantic_review", "hybrid"}:
            raise ValueError(f"manifest {key} has unknown oracle mode {mode!r}")
        if mode in {"deterministic", "hybrid"} and not deterministic_sources:
            raise ValueError(f"manifest {key} {mode} oracle needs deterministic_sources")
        if mode in {"semantic_review", "hybrid"} and not semantic_dimensions:
            raise ValueError(f"manifest {key} {mode} oracle needs semantic_dimensions")
        raw_turns = row.get("turns")
        turns = tuple(
            str(value).strip()
            for value in raw_turns
            if str(value).strip()
        ) if isinstance(raw_turns, list) else ()
        text = str(row.get("text") or (turns[0] if turns else "")).strip()
        if not text:
            raise ValueError(f"manifest {key} item {row.get('id')!r} needs text or turns")
        cases.append(
            ClosedLoopCase(
                case_id=str(row["id"]),
                language=str(row["language"]),
                text=text,
                speaker_id=str(row.get("speaker_id") or "default"),
                turns=turns,
                max_error_rate=float(row.get("max_error_rate", 0.35)),
                expected_any=tuple(str(v) for v in row.get("expected_any", [])),
                expected_all=tuple(str(v) for v in row.get("expected_all", [])),
                oracle_mode=mode,
                deterministic_sources=deterministic_sources,
                primary_outcomes=tuple(str(v) for v in row.get("primary_outcomes", [])),
                semantic_dimensions=semantic_dimensions,
                review_rubric=(
                    dict(row.get("review_rubric") or {})
                    if isinstance(row.get("review_rubric") or {}, dict)
                    else None
                ),
            )
        )
    return cases


def read_wav(path: Path) -> AudioData:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if sample_width != 2:
        raise ValueError(f"{path}: expected PCM16 WAV, got {sample_width * 8}-bit")
    return AudioData(frames, sample_rate, channels)


def mono_pcm(audio: AudioData) -> np.ndarray:
    samples = np.frombuffer(audio.pcm16, dtype="<i2").astype(np.float64)
    if audio.channels > 1:
        samples = samples.reshape(-1, audio.channels).mean(axis=1)
    return samples


def resample_pcm16(audio: AudioData, target_rate: int = 16000) -> bytes:
    samples = mono_pcm(audio)
    if audio.sample_rate != target_rate and samples.size:
        divisor = math.gcd(audio.sample_rate, target_rate)
        samples = signal.resample_poly(
            samples,
            target_rate // divisor,
            audio.sample_rate // divisor,
        )
    return np.clip(np.rint(samples), -32768, 32767).astype("<i2").tobytes()


def trim_silence(audio: AudioData, *, target_rate: int = 16000) -> AudioData:
    pcm = resample_pcm16(audio, target_rate)
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    if samples.size == 0:
        return AudioData(b"", target_rate, 1)
    frame = max(1, int(target_rate * 0.02))
    rms = np.array(
        [
            np.sqrt(np.mean(samples[index : index + frame] ** 2))
            for index in range(0, samples.size, frame)
        ]
    )
    noise = float(np.percentile(rms, 20)) if rms.size else 0.0
    threshold = max(120.0, noise * 3.0)
    active = np.flatnonzero(rms >= threshold)
    if active.size == 0:
        return AudioData(pcm, target_rate, 1)
    pad_frames = int(0.25 / 0.02)
    first = max(0, int(active[0]) - pad_frames) * frame
    last = min(len(rms), int(active[-1]) + pad_frames + 1) * frame
    trimmed = samples[first:last]
    return AudioData(
        np.clip(np.rint(trimmed), -32768, 32767).astype("<i2").tobytes(),
        target_rate,
        1,
    )


def primary_error(language: str, reference: str, hypothesis: str) -> tuple[str, float]:
    normalized_language = language.casefold()
    if normalized_language.startswith("zh"):
        return "cer", error_rate(char_tokens(reference), char_tokens(hypothesis))
    return "wer", error_rate(word_tokens(reference), word_tokens(hypothesis))


def transcript_metrics(language: str, reference: str, hypothesis: str) -> dict[str, Any]:
    metric, value = primary_error(language, reference, hypothesis)
    return {
        "metric": metric,
        "error_rate": round(value, 6),
        "wer": round(error_rate(word_tokens(reference), word_tokens(hypothesis)), 6),
        "cer": round(error_rate(char_tokens(reference), char_tokens(hypothesis)), 6),
        "reference_normalized": normalize_text(reference),
        "hypothesis_normalized": normalize_text(hypothesis),
    }


async def transcribe_audio(asr_url: str, audio: AudioData, *, timeout_s: float) -> str:
    client = ASRClient(asr_url, timeout_ms=int(timeout_s * 1000))
    try:
        response = await client.transcribe(resample_pcm16(audio, 16000), timeout_s)
    finally:
        await client.close()
    return str(response.get("text") or "").strip()


async def synthesize_case(tts_url: str, case: ClosedLoopCase, *, timeout_s: float) -> AudioData:
    client = TTSClient(tts_url, default_sample_rate=24000)
    pcm, rate = await asyncio.wait_for(
        client.synthesize(
            text=case.text,
            speaker_id=case.speaker_id,
            request_id=f"closed-loop-{case.case_id}-{uuid.uuid4().hex[:10]}",
        ),
        timeout=timeout_s,
    )
    return AudioData(pcm, rate, 1)


def choose_capture_backend(
    name: str,
    path: Path,
    *,
    input_device: int | str | None,
) -> CaptureBackend:
    if name == "monitor":
        return PulseMonitorCapture(path)
    if name == "acoustic":
        if not PhysicalMicrophoneCapture.available():
            raise RuntimeError("acoustic capture requires sounddevice")
        return PhysicalMicrophoneCapture(path, device=input_device)
    if name != "auto":
        raise ValueError(f"unknown capture backend {name!r}")
    if PulseMonitorCapture.available():
        return PulseMonitorCapture(path)
    if PhysicalMicrophoneCapture.available():
        return PhysicalMicrophoneCapture(path, device=input_device)
    raise RuntimeError("no playback capture backend is available")


def expected_term_result(case: ClosedLoopCase, text: str) -> dict[str, Any]:
    """Evaluate explicit phrase contracts only for deterministic cases.

    Semantic workflow cases must use the retained semantic review bundle instead
    of phrase matching.
    """

    if case.oracle_mode != "deterministic":
        return {
            "expected_any": [],
            "expected_all": [],
            "any_ok": True,
            "all_ok": True,
            "passed": True,
            "applied": False,
        }
    normalized = normalize_text(text)
    any_ok = not case.expected_any or any(
        normalize_text(term) in normalized for term in case.expected_any
    )
    all_ok = all(normalize_text(term) in normalized for term in case.expected_all)
    return {
        "expected_any": list(case.expected_any),
        "expected_all": list(case.expected_all),
        "any_ok": any_ok,
        "all_ok": all_ok,
        "passed": any_ok and all_ok,
        "applied": True,
    }


async def run_transport_case(
    case: ClosedLoopCase,
    *,
    output_dir: Path,
    tts_url: str,
    asr_url: str,
    capture_backend: str,
    input_device: int | str | None,
    timeout_s: float,
    playback_gain: float,
) -> dict[str, Any]:
    case_dir = output_dir / "transport" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    synthesized = await synthesize_case(tts_url, case, timeout_s=timeout_s)
    source_wav = case_dir / "tts.wav"
    write_pcm16_wav(
        source_wav,
        pcm16=synthesized.pcm16,
        sample_rate=synthesized.sample_rate,
        channels=1,
    )
    digital_hypothesis = await transcribe_audio(asr_url, synthesized, timeout_s=timeout_s)
    digital_metrics = transcript_metrics(case.language, case.text, digital_hypothesis)
    digital_passed = bool(digital_hypothesis) and (
        digital_metrics["error_rate"] <= case.max_error_rate
    )

    captured_wav = case_dir / "playback-capture.wav"
    capture = choose_capture_backend(
        capture_backend,
        captured_wav,
        input_device=input_device,
    )
    fixture = AudioFixture(
        text=case.text,
        pcm16=synthesized.pcm16,
        sample_rate=synthesized.sample_rate,
        channels=1,
        path=source_wav,
    )
    with capture:
        HostSpeakerPlayer(playback_gain=playback_gain).play(
            fixture,
            timeout_s=timeout_s,
        )
        time.sleep(0.75)
    captured = trim_silence(read_wav(captured_wav))
    trimmed_wav = case_dir / "playback-capture-trimmed.wav"
    write_pcm16_wav(
        trimmed_wav,
        pcm16=captured.pcm16,
        sample_rate=captured.sample_rate,
        channels=1,
    )
    playback_hypothesis = await transcribe_audio(asr_url, captured, timeout_s=timeout_s)
    playback_metrics = transcript_metrics(case.language, case.text, playback_hypothesis)
    playback_passed = bool(playback_hypothesis) and (
        playback_metrics["error_rate"] <= case.max_error_rate
    )
    return {
        "id": case.case_id,
        "language": case.language,
        "source_text": case.text,
        "speaker_id": case.speaker_id,
        "oracle_policy": {
            "mode": case.oracle_mode,
            "deterministic_sources": list(case.deterministic_sources),
            "semantic_dimensions": list(case.semantic_dimensions),
            "semantic_blocking": True,
        },
        "capture_backend": capture.name,
        "source_wav": str(source_wav),
        "captured_wav": str(captured_wav),
        "trimmed_wav": str(trimmed_wav),
        "digital": {
            "hypothesis": digital_hypothesis,
            "metrics": digital_metrics,
            "passed": digital_passed,
        },
        "playback": {
            "hypothesis": playback_hypothesis,
            "metrics": playback_metrics,
            "passed": playback_passed,
        },
        "mechanical_passed": digital_passed and playback_passed,
        "semantic_review_required": False,
        "status": "pass" if digital_passed and playback_passed else "fail",
        "passed": digital_passed and playback_passed,
    }


async def wait_for_session_done(assistant: Any, sid: str, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = assistant.sessions.state.get(sid) or {}
        if state.get("done_logged"):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"session {sid} did not finish within {timeout_s:.1f}s")


def configure_workflow_environment(args: argparse.Namespace, case_dir: Path) -> None:
    from orchestrator.orchestrator import load_runtime_environment

    load_runtime_environment()
    os.environ["AGENT_URL"] = args.agent_url
    os.environ["ASR_URL"] = args.asr_url
    os.environ["TTS_URL"] = args.tts_url
    os.environ["ORCH_ENABLE_AGENT"] = "1"
    os.environ["ORCH_ENABLE_INTERACTION_RESPONSE"] = "1"
    os.environ["ORCH_ENABLE_SORIDORMI_SKILLS"] = "0"
    os.environ["ORCH_AUDIO_INPUT_MODE"] = "stdin"
    os.environ["ORCH_AUDIO_OUTPUT_MODE"] = "device"
    os.environ["ORCH_DISCARD_PLAYBACK_REALTIME"] = "0"
    os.environ["ORCH_EVENT_LOG_PATH"] = str(case_dir / "session-events.jsonl")
    os.environ["ORCH_COGNITIVE_RUNTIME_MODE"] = "apply"
    os.environ["ORCH_COGNITIVE_APPLY_LANES"] = "chat,tool"
    os.environ["ORCH_COGNITIVE_FALLBACK_POLICY"] = "fail_closed"
    os.environ["ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED"] = "0"
    os.environ["ORCH_ENABLE_TASK_CONTEXT_STORE"] = "0"
    os.environ["ORCH_RUNTIME_READY_GREETING_ENABLED"] = "0"
    os.environ["ORCH_CONVERSATION_ID"] = f"closed-loop-{case_dir.name}"
    os.environ["RECORDINGS_DIR"] = str(case_dir / "recordings")


async def run_workflow_case(
    case: ClosedLoopCase,
    *,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    from orchestrator.orchestrator import VoiceAssistant

    case_dir = output_dir / "workflow" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    configure_workflow_environment(args, case_dir)
    captured_wav = case_dir / "playback-capture.wav"
    capture = choose_capture_backend(
        args.capture,
        captured_wav,
        input_device=args.input_device,
    )
    assistant = VoiceAssistant()
    error = ""
    turn_records: list[dict[str, Any]] = []
    delivered_events: list[dict[str, Any]] = []
    delivered_text = ""
    hypothesis = ""
    metrics = transcript_metrics(case.language, "", "")
    semantic = expected_term_result(case, "")
    audio_passed = False
    mechanical_passed = False
    semantic_review_required = case.oracle_mode in {"semantic_review", "hybrid"}
    status = "fail"
    trimmed_wav = case_dir / "playback-capture-trimmed.wav"
    try:
        with capture:
            for index, user_text in enumerate(case.user_turns(), start=1):
                sid = assistant.create_session()
                await assistant.handle_routed_text(user_text, sid, channel="text")
                await wait_for_session_done(
                    assistant,
                    sid,
                    timeout_s=args.workflow_timeout,
                )
                await asyncio.sleep(0.25)
                turn_events = assistant._delivered_turn_speech_events(sid)
                turn_text = " ".join(
                    str(event.get("text") or "").strip()
                    for event in turn_events
                    if str(event.get("text") or "").strip()
                ).strip()
                delivered_events.extend(turn_events)
                turn_records.append(
                    {
                        "turn_index": index,
                        "session_id": sid,
                        "user_text": user_text,
                        "delivered_text": turn_text,
                        "delivered_speech_events": turn_events,
                    }
                )
            await asyncio.sleep(0.75)
        delivered_text = " ".join(
            row["delivered_text"] for row in turn_records if row["delivered_text"]
        ).strip()
        captured = trim_silence(read_wav(captured_wav))
        write_pcm16_wav(
            trimmed_wav,
            pcm16=captured.pcm16,
            sample_rate=captured.sample_rate,
            channels=1,
        )
        hypothesis = await transcribe_audio(
            args.asr_url,
            captured,
            timeout_s=args.timeout,
        )
        metrics = transcript_metrics(case.language, delivered_text, hypothesis)
        audio_passed = bool(delivered_text and hypothesis) and (
            metrics["error_rate"] <= case.max_error_rate
        )
        semantic = expected_term_result(case, delivered_text)
        event_ids = [
            str(event.get("event_id") or "")
            for event in delivered_events
            if str(event.get("event_id") or "")
        ]
        unique_delivery = len(event_ids) == len(set(event_ids))
        all_turns_finished = len(turn_records) == len(case.user_turns())
        mechanical_passed = (
            audio_passed
            and semantic["passed"]
            and unique_delivery
            and all_turns_finished
        )
        status = (
            "fail"
            if not mechanical_passed
            else "review"
            if semantic_review_required
            else "pass"
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        delivered_text = " ".join(
            row["delivered_text"] for row in turn_records if row["delivered_text"]
        ).strip()
        metrics = transcript_metrics(case.language, delivered_text, "")
        semantic = expected_term_result(case, delivered_text)
    finally:
        await assistant.cleanup()
    result = {
        "id": case.case_id,
        "language": case.language,
        "user_text": case.text,
        "user_turns": list(case.user_turns()),
        "turns": turn_records,
        "capture_backend": capture.name,
        "delivered_speech_events": delivered_events,
        "delivered_text": delivered_text,
        "captured_transcript": hypothesis,
        "metrics": metrics,
        "semantic_expectations": semantic,
        "oracle_policy": {
            "mode": case.oracle_mode,
            "deterministic_sources": list(case.deterministic_sources),
            "semantic_dimensions": list(case.semantic_dimensions),
            "semantic_blocking": True,
        },
        "primary_outcomes": list(case.primary_outcomes),
        "review_rubric": dict(case.review_rubric or {}),
        "semantic_review_required": semantic_review_required,
        "semantic_review_status": (
            "pending" if semantic_review_required and status != "fail" else "not_required"
        ),
        "audio_passed": audio_passed,
        "all_turns_finished": len(turn_records) == len(case.user_turns()),
        "unique_delivery": len(
            {
                str(event.get("event_id") or "")
                for event in delivered_events
                if str(event.get("event_id") or "")
            }
        ) == len(
            [
                event
                for event in delivered_events
                if str(event.get("event_id") or "")
            ]
        ),
        "mechanical_passed": mechanical_passed,
        "captured_wav": str(captured_wav),
        "trimmed_wav": str(trimmed_wav),
        "artifacts": [
            str(case_dir / "session-events.jsonl"),
            str(captured_wav),
            str(trimmed_wav),
            str(case_dir / "result.json"),
        ],
        "error": error or None,
        "status": status,
        "passed": status == "pass",
    }
    write_json(case_dir / "result.json", result)
    return result


def closed_loop_review_bundle(
    workflow_cases: Sequence[ClosedLoopCase],
    workflow_results: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    cases_by_id = {case.case_id: case for case in workflow_cases}
    normalized_cases: list[dict[str, Any]] = []
    suite_results: list[dict[str, Any]] = []
    for result in workflow_results:
        case = cases_by_id[str(result["id"])]
        normalized_cases.append(
            {
                "schema_version": 1,
                "id": case.case_id,
                "layer": "e2e",
                "datasets": ["closed_loop_audio", "bilingual_and_asr_noise"],
                "source": {
                    "path": "benchmarks/manifests/closed_loop_e2e_v1.json",
                    "adapter": "closed_loop_e2e_v1",
                    "source_index": None,
                    "source_id": case.case_id,
                },
                "inputs": {
                    "user_text": case.text,
                    "turns": list(case.user_turns()),
                    "language": case.language,
                },
                "context": {},
                "capabilities": [],
                "expectations": {
                    "primary_outcomes": list(case.primary_outcomes),
                    "acceptable_auxiliary": [],
                    "forbidden_behaviors": [],
                    "invariants": [
                        "generated speech is delivered through playback",
                        "captured playback substantially matches delivered speech",
                    ],
                    "distribution_observations": [],
                },
                "evidence_requirements": ["live_service"],
                "review_rubric": dict(case.review_rubric or {}),
                "legacy_expectations": {},
                "oracle_policy": {
                    "mode": case.oracle_mode,
                    "deterministic_sources": list(case.deterministic_sources),
                    "semantic_dimensions": list(case.semantic_dimensions),
                    "semantic_blocking": True,
                },
            }
        )
        invariant_results = [
            {
                "name": "generated speech is delivered through playback",
                "passed": bool(result.get("delivered_text")),
                "detail": None if result.get("delivered_text") else "no delivered speech",
            },
            {
                "name": "captured playback substantially matches delivered speech",
                "passed": bool(result.get("audio_passed")),
                "detail": (
                    None
                    if result.get("audio_passed")
                    else f"audio metric={result.get('metrics')}"
                ),
            },
        ]
        deterministic_failed = not bool(result.get("mechanical_passed"))
        semantic_required = bool(result.get("semantic_review_required"))
        suite_results.append(
            {
                "schema_version": 1,
                "scenario_id": case.case_id,
                "status": str(result.get("status") or "fail"),
                "run": {
                    "mode": "live_model",
                    "evidence_level": "live_service",
                    "model": None,
                    "prompt_revision": None,
                    "metadata": {"transport": "closed_loop_playback_asr"},
                },
                "observations": {
                    "primary_task_passed": None if semantic_required else not deterministic_failed,
                    "primary_outcome": result.get("delivered_text"),
                    "auxiliary_behavior": None,
                    "behaviors": [],
                    "latency_ms": None,
                    "social_attention_lifecycle": {},
                    "evidence": [
                        {
                            "turns": result.get("turns"),
                            "delivered_speech_events": result.get(
                                "delivered_speech_events"
                            ),
                            "captured_transcript": result.get("captured_transcript"),
                            "audio_metrics": result.get("metrics"),
                            "error": result.get("error"),
                        }
                    ],
                },
                "evaluation": {
                    "semantic_review_required": semantic_required,
                    "forbidden_behavior_hits": [],
                    "oracle_policy": result.get("oracle_policy"),
                    "deterministic_status": (
                        "fail" if deterministic_failed else "pass"
                    ),
                    "semantic_review_status": (
                        "pending" if semantic_required else "not_required"
                    ),
                },
                "invariant_results": invariant_results,
                "artifacts": list(result.get("artifacts") or []),
            }
        )
    report = {
        "schema_version": 1,
        "run": {
            "mode": "live_model",
            "evidence_level": "live_service",
            "model": None,
            "prompt_revision": None,
            "metadata": {"transport": "closed_loop_playback_asr"},
        },
        "summary": {
            "total": len(suite_results),
            "pass": sum(item["status"] == "pass" for item in suite_results),
            "fail": sum(item["status"] == "fail" for item in suite_results),
            "review": sum(item["status"] == "review" for item in suite_results),
            "error": 0,
        },
        "results": suite_results,
        "errors": [],
    }
    return build_review_bundle(
        {"schema_version": 1, "cases": normalized_cases},
        report,
    )


def filter_language(cases: Iterable[ClosedLoopCase], languages: set[str]) -> list[ClosedLoopCase]:
    if not languages:
        return list(cases)
    return [
        case
        for case in cases
        if case.language.casefold().split("-", 1)[0] in languages
    ]


def parse_device(value: str | None) -> int | str | None:
    if value is None or value.strip().casefold() in {"", "default", "auto"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def start_services() -> None:
    subprocess.run([str(ROOT / "scripts" / "start_services.sh")], cwd=ROOT, check=True)


def stop_services() -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            ".env.runtime",
            "down",
        ],
        cwd=ROOT,
        check=False,
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(args.manifest)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported closed-loop manifest schema")
    languages = {
        item.strip().casefold()
        for item in args.languages.split(",")
        if item.strip()
    }
    transport_cases = filter_language(
        parse_cases(manifest, "transport_cases"), languages
    )
    workflow_cases = filter_language(parse_cases(manifest, "workflow_cases"), languages)
    output_dir = (args.output_dir or DEFAULT_OUTPUT_ROOT / utc_id()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_handler = install_python_log_capture(output_dir / "logs" / "python-runtime.log")
    input_device = parse_device(args.input_device)

    transport_results: list[dict[str, Any]] = []
    workflow_results: list[dict[str, Any]] = []
    if not args.workflow_only:
        for case in transport_cases:
            transport_results.append(
                await run_transport_case(
                    case,
                    output_dir=output_dir,
                    tts_url=args.tts_url,
                    asr_url=args.asr_url,
                    capture_backend=args.capture,
                    input_device=input_device,
                    timeout_s=args.timeout,
                    playback_gain=args.playback_gain,
                )
            )
    if not args.transport_only:
        args.input_device = input_device
        for case in workflow_cases:
            workflow_results.append(
                await run_workflow_case(case, output_dir=output_dir, args=args)
            )

    review_bundle = closed_loop_review_bundle(workflow_cases, workflow_results)
    write_json(output_dir / "semantic-review-bundle.json", review_bundle)
    diagnostics = (
        collect_run_diagnostics(output_dir) if args.collect_diagnostics else []
    )
    mechanical_passed = all(
        bool(row.get("passed")) for row in transport_results
    ) and all(bool(row.get("mechanical_passed")) for row in workflow_results)
    semantic_review_pending = any(
        bool(row.get("semantic_review_required")) and row.get("status") != "fail"
        for row in workflow_results
    )
    status = (
        "fail"
        if not mechanical_passed
        else "review"
        if semantic_review_pending
        else "pass"
    )
    payload = {
        "schema_version": 2,
        "qualification_id": manifest.get("qualification_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "languages": sorted(languages),
        "capture_requested": args.capture,
        "transport": transport_results,
        "workflow": workflow_results,
        "mechanical_passed": mechanical_passed,
        "semantic_review_pending": semantic_review_pending,
        "status": status,
        "passed": status == "pass",
        "collection_succeeded": mechanical_passed,
        "human_voice_required": False,
        "operator_pronunciation_graded": False,
        "semantic_truth_source": "external_llm_or_human_review",
        "deterministic_truth_source": "declared_fixtures_contracts_and_invariants",
        "semantic_review_bundle": str(output_dir / "semantic-review-bundle.json"),
        "diagnostics": diagnostics,
        "claim": (
            "Automated generated-speech closed-loop evidence. It validates bilingual "
            "TTS/ASR transport and captured workflow playback. Mechanical boundaries "
            "are evaluated deterministically; semantic workflow quality remains pending "
            "external LLM or human review. It does not claim human speech-recognition "
            "accuracy."
        ),
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "summary.json", payload)
    if args.archive:
        archive_path = args.archive.resolve()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(output_dir, arcname=output_dir.name)
        payload["archive"] = str(archive_path)
        write_json(output_dir / "summary.json", payload)
    logging.getLogger().removeHandler(log_handler)
    log_handler.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--languages", default="zh,en")
    parser.add_argument("--tts-url", default=os.getenv("TTS_URL", "ws://127.0.0.1:5000"))
    parser.add_argument("--asr-url", default=os.getenv("ASR_URL", "ws://127.0.0.1:9001"))
    parser.add_argument(
        "--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092")
    )
    parser.add_argument(
        "--capture",
        choices=("auto", "monitor", "acoustic"),
        default="auto",
        help="Capture actual output through the default sink monitor or physical mic.",
    )
    parser.add_argument("--input-device")
    parser.add_argument("--playback-gain", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--workflow-timeout", type=float, default=300.0)
    parser.add_argument("--transport-only", action="store_true")
    parser.add_argument("--workflow-only", action="store_true")
    parser.add_argument(
        "--collect-diagnostics",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Collect Git, Docker, runtime-profile, and GPU diagnostics.",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="Optional .tar.gz path containing the complete evidence directory.",
    )
    parser.add_argument("--start-services", action="store_true")
    parser.add_argument("--stop-services", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.transport_only and args.workflow_only:
        raise SystemExit("--transport-only and --workflow-only are mutually exclusive")
    if args.start_services:
        start_services()
    try:
        payload = asyncio.run(run(args))
    finally:
        if args.stop_services:
            stop_services()
    # Semantic review pending is a successful collection state, not a failed
    # mechanical qualification. External review decides the final verdict.
    return 0 if payload["collection_succeeded"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
