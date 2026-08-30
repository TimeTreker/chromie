#!/usr/bin/env python3
"""Qualify a vLLM OpenAI-compatible endpoint for Chromie's LLM transport needs.

This is a provider-contract probe, not a robot-behavior qualification.  It uses
no HTTP request deadline so a slow model is measured rather than misclassified
as a transport timeout.  The explicit cancellation phase still cancels one
client request to verify that a surviving concurrent stream remains usable.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class QualificationFailure(RuntimeError):
    """A required provider contract was not observed."""


@dataclass
class StreamObservation:
    label: str
    started_s: float
    first_delta_s: float | None = None
    finished_s: float | None = None
    delta_count: int = 0
    text: str = ""
    finish_reason: str | None = None
    terminal_seen: bool = False
    reasoning_seen: bool = False
    cancelled: bool = False
    error: str | None = None

    @property
    def ttft_ms(self) -> float | None:
        if self.first_delta_s is None:
            return None
        return (self.first_delta_s - self.started_s) * 1000.0

    @property
    def elapsed_ms(self) -> float | None:
        if self.finished_s is None:
            return None
        return (self.finished_s - self.started_s) * 1000.0

    def evidence(self) -> dict[str, Any]:
        value = asdict(self)
        value["ttft_ms"] = self.ttft_ms
        value["elapsed_ms"] = self.elapsed_ms
        value["response_chars"] = len(self.text)
        value["text_preview"] = self.text[:240]
        value.pop("text")
        return value


@dataclass
class GpuSample:
    observed_s: float
    memory_used_mib: int
    memory_total_mib: int
    utilization_percent: int


@dataclass
class TtsObservation:
    started_s: float
    first_audio_s: float | None = None
    finished_s: float | None = None
    audio_bytes: int = 0
    audio_sha256: str | None = None
    start_metadata: dict[str, Any] = field(default_factory=dict)
    end_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def first_audio_ms(self) -> float | None:
        if self.first_audio_s is None:
            return None
        return (self.first_audio_s - self.started_s) * 1000.0

    @property
    def elapsed_ms(self) -> float | None:
        if self.finished_s is None:
            return None
        return (self.finished_s - self.started_s) * 1000.0

    def evidence(self) -> dict[str, Any]:
        return {
            "first_audio_ms": self.first_audio_ms,
            "elapsed_ms": self.elapsed_ms,
            "audio_bytes": self.audio_bytes,
            "audio_sha256": self.audio_sha256,
            "start": self.start_metadata,
            "end": self.end_metadata,
        }


@dataclass
class Evidence:
    model: str
    base_url: str
    started_at: str
    git_revision: str | None
    git_dirty: bool | None
    phases: dict[str, Any] = field(default_factory=dict)
    gpu_samples: list[GpuSample] = field(default_factory=list)
    status: str = "running"
    error: dict[str, str] | None = None

    def payload(self) -> dict[str, Any]:
        samples = [asdict(item) for item in self.gpu_samples]
        peak = max((item.memory_used_mib for item in self.gpu_samples), default=None)
        utilization_peak = max(
            (item.utilization_percent for item in self.gpu_samples), default=None
        )
        includes_goal_interpreter = "goal_interpreter_semantics" in self.phases
        return {
            "schema_version": 1,
            "evidence_class": (
                "provider_contract_and_goal_interpreter_probe"
                if includes_goal_interpreter
                else "provider_contract_only"
            ),
            "claim_boundary": (
                "Direct vLLM transport and isolated current-checkout Goal Interpreter "
                "probe evidence only; not an Agent workflow, voice, audio playback, "
                "simulator, target, or physical robot claim."
                if includes_goal_interpreter
                else "Direct vLLM transport evidence only; not Agent semantic quality, "
                "voice, audio, simulator, target, or physical robot evidence."
            ),
            "model": self.model,
            "base_url": self.base_url,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "git_revision": self.git_revision,
            "git_dirty": self.git_dirty,
            "http_timeout": None,
            "status": self.status,
            "error": self.error,
            "phases": self.phases,
            "resources": {
                "sample_count": len(samples),
                "peak_gpu_memory_used_mib": peak,
                "peak_gpu_utilization_percent": utilization_peak,
                "samples": samples,
            },
        }


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _git_dirty() -> bool | None:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _chat_payload(
    model: str,
    prompt: str,
    *,
    stream: bool,
    max_tokens: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Follow the user instruction directly. Do not expose hidden "
                    "reasoning, analysis, or thinking."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if "qwen3" in model.casefold():
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


def _extract_stream_delta(chunk: dict[str, Any]) -> tuple[str, str | None, bool]:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", None, False
    choice = choices[0]
    if not isinstance(choice, dict):
        raise QualificationFailure("stream choice is not an object")
    delta = choice.get("delta") or {}
    if not isinstance(delta, dict):
        raise QualificationFailure("stream delta is not an object")
    reasoning = any(
        delta.get(key) not in (None, "", [], {})
        for key in ("reasoning", "reasoning_content", "thinking")
    )
    content = delta.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise QualificationFailure("stream content delta is not text")
    finish_reason = choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise QualificationFailure("stream finish_reason is not text")
    return content, finish_reason, reasoning


async def _observe_stream(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    *,
    label: str,
    first_delta_event: asyncio.Event | None = None,
) -> StreamObservation:
    observation = StreamObservation(label=label, started_s=time.perf_counter())
    try:
        async with client.stream("POST", endpoint, json=payload) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise QualificationFailure(f"HTTP {response.status_code}: {body[:600]}")
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data:"):
                    raise QualificationFailure(f"unexpected SSE line: {line[:160]}")
                encoded = line[5:].strip()
                if encoded == "[DONE]":
                    observation.terminal_seen = True
                    continue
                chunk = json.loads(encoded)
                if not isinstance(chunk, dict):
                    raise QualificationFailure("SSE data is not an object")
                content, finish_reason, reasoning = _extract_stream_delta(chunk)
                observation.reasoning_seen = observation.reasoning_seen or reasoning
                if finish_reason is not None:
                    observation.finish_reason = finish_reason
                if content:
                    if observation.first_delta_s is None:
                        observation.first_delta_s = time.perf_counter()
                        if first_delta_event is not None:
                            first_delta_event.set()
                    observation.delta_count += 1
                    observation.text += content
        observation.finished_s = time.perf_counter()
        return observation
    except asyncio.CancelledError:
        observation.cancelled = True
        observation.finished_s = time.perf_counter()
        raise
    except Exception as exc:
        observation.error = f"{type(exc).__name__}: {exc}"
        observation.finished_s = time.perf_counter()
        return observation


def _assert_complete_stream(observation: StreamObservation) -> None:
    if observation.error:
        raise QualificationFailure(f"{observation.label}: {observation.error}")
    if observation.first_delta_s is None or not observation.text:
        raise QualificationFailure(f"{observation.label}: no content delta")
    if not observation.terminal_seen:
        raise QualificationFailure(f"{observation.label}: terminal SSE marker missing")
    if observation.reasoning_seen:
        raise QualificationFailure(f"{observation.label}: reasoning channel exposed")
    if observation.finish_reason not in {"stop", "length"}:
        raise QualificationFailure(
            f"{observation.label}: unsupported finish_reason {observation.finish_reason!r}"
        )


async def _gpu_sampler(evidence: Evidence, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            output = await asyncio.to_thread(
                subprocess.check_output,
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            used, total, utilization = [
                int(part.strip()) for part in output.splitlines()[0].split(",")
            ]
            evidence.gpu_samples.append(
                GpuSample(
                    observed_s=time.perf_counter(),
                    memory_used_mib=used,
                    memory_total_mib=total,
                    utilization_percent=utilization,
                )
            )
        except Exception:
            pass
        await asyncio.sleep(0.25)


async def _observe_tts(
    url: str,
    *,
    speaker: str,
    label: str,
) -> TtsObservation:
    observation = TtsObservation(started_s=time.perf_counter())
    audio = bytearray()
    async with websockets.connect(
        url,
        max_size=50_000_000,
        open_timeout=None,
        close_timeout=None,
        ping_interval=None,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "synthesize_stream",
                    "text": (
                        "Chromie is checking that speech generation and two "
                        "cognition streams can share the GPU safely."
                    ),
                    "speaker_id": speaker,
                    "request_id": f"vllm-qualification-{label}",
                }
            )
        )
        async for message in websocket:
            if isinstance(message, bytes):
                if observation.first_audio_s is None:
                    observation.first_audio_s = time.perf_counter()
                audio.extend(message)
                continue
            data = json.loads(message)
            if not isinstance(data, dict):
                raise QualificationFailure(f"TTS {label}: control frame is not an object")
            message_type = data.get("type")
            if message_type == "start":
                observation.start_metadata = data
            elif message_type == "error":
                raise QualificationFailure(
                    f"TTS {label}: {data.get('message') or 'provider error'}"
                )
            elif message_type == "end":
                observation.end_metadata = data
                break
        else:
            raise QualificationFailure(f"TTS {label}: websocket ended without end frame")
    observation.finished_s = time.perf_counter()
    observation.audio_bytes = len(audio)
    observation.audio_sha256 = hashlib.sha256(audio).hexdigest() if audio else None
    if observation.first_audio_s is None or not audio:
        raise QualificationFailure(f"TTS {label}: no audio received")
    return observation


def _binding_value_present(
    decisions: list[dict[str, Any]],
    key: str,
    accepted_values: list[Any],
) -> bool:
    return any(
        item.get("binding_items", item.get("bindings", {})).get(key) in accepted_values
        for item in decisions
        if isinstance(item, dict)
        and isinstance(item.get("binding_items", item.get("bindings", {})), dict)
    )


def _vllm_compatible_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove only decoder hints that canonical Host validation re-enforces."""

    translated = copy.deepcopy(schema)
    removed: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if "uniqueItems" in value:
                value.pop("uniqueItems")
                removed.append(f"{path}.uniqueItems")
            for key, item in value.items():
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(translated, "$")
    return translated, removed


def _wire_coordination_satisfies(
    wire_payload: dict[str, Any], expected_kind: str, expected_ref_count: int
) -> bool:
    """Judge the model-authored relation before legacy canonical lowering."""

    return any(
        item.get("kind") == expected_kind
        and len(item.get("refs") or []) == expected_ref_count
        and len(set(item.get("refs") or [])) == expected_ref_count
        for item in wire_payload.get("coordination") or []
        if isinstance(item, dict)
    )


async def _qualify_goal_interpreter(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    model: str,
) -> dict[str, Any]:
    from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
        OllamaGoalInterpreter,
    )
    from agent.app.cognitive_core.goal_interpreter.schema import (
        GoalInterpretationRequest,
    )

    interpreter = OllamaGoalInterpreter(
        ollama_url="http://provider-adapter-not-used.invalid",
        model=model,
        # This instance only builds and validates payloads; no Ollama request is
        # made. Keep its required legacy timeout effectively unbounded so the
        # qualification has no hidden short deadline.
        timeout_ms=2_147_483_647,
        num_ctx=16384,
        num_predict=512,
    )
    cases = [
        {
            "id": "weather_exact_location",
            "text": "今晚重庆会不会下雨哦？",
            "language": "zh-CN",
            "count": 1,
            "modes": ["information"],
            "bindings": {
                "location": ["重庆"],
                "time_scope": ["今晚"],
            },
            "unresolved": False,
        },
        {
            "id": "compound_numeric_sequence",
            "text": (
                "walk ahead at 0.2 speed for 10 seconds and then nod your "
                "head twice, then turn left"
            ),
            "language": "en-US",
            "count": 3,
            "modes": ["body_action", "body_action", "body_action"],
            "bindings": {
                "speed": [0.2],
                "duration": [10, "10 seconds"],
                "count": [2],
                "direction": ["left"],
            },
            "coordination": "sequence",
            "unresolved": False,
        },
        {
            "id": "filler_blink_twice",
            "text": "嗯，那个……先眨两下眼睛吧。",
            "language": "zh-CN",
            "count": 1,
            "modes": ["body_action"],
            "bindings": {"count": [2]},
            "unresolved": False,
        },
        {
            "id": "parallel_gaze_blink",
            "text": "看着我三秒，同时眨两下眼睛。",
            "language": "zh-CN",
            "count": 2,
            "modes": ["body_action", "body_action"],
            "bindings": {"duration": [3, "三秒"], "count": [2]},
            "coordination": "parallel",
            "unresolved": False,
        },
        {
            "id": "ambiguous_bare_referent",
            "text": "你能查天信吗？",
            "language": "zh-CN",
            "count": 1,
            "modes": ["information"],
            "bindings": {"entity": ["天信"]},
            "unresolved": True,
        },
    ]
    results: list[dict[str, Any]] = []
    for case in cases:
        request = GoalInterpretationRequest(
            text=str(case["text"]),
            language=str(case["language"]),
        )
        ollama_payload = interpreter.build_interpretation_payload(request)
        provider_schema, removed_schema_keywords = _vllm_compatible_schema(ollama_payload["format"])
        options = dict(ollama_payload.get("options") or {})
        request_payload = {
            "model": model,
            "messages": ollama_payload["messages"],
            "stream": False,
            "max_tokens": int(options.get("num_predict") or 512),
            "temperature": float(options.get("temperature") or 0),
            "top_p": float(options.get("top_p") or 0.9),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "chromie_goal_interpretation",
                    "strict": True,
                    "schema": provider_schema,
                },
            },
        }
        if "qwen3" in model.casefold():
            request_payload["chat_template_kwargs"] = {"enable_thinking": False}
        started = time.perf_counter()
        response = await client.post(endpoint, json=request_payload)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        provider_data = response.json()
        choice = provider_data["choices"][0]
        message = choice["message"]
        reasoning_seen = any(
            message.get(key) not in (None, "", [], {})
            for key in ("reasoning", "reasoning_content", "thinking")
        )
        content = str(message.get("content") or "")
        result: dict[str, Any] = {
            "id": case["id"],
            "text": case["text"],
            "elapsed_ms": elapsed_ms,
            "finish_reason": choice.get("finish_reason"),
            "reasoning_seen": reasoning_seen,
            "usage": provider_data.get("usage"),
            "schema_translation": {
                "removed": removed_schema_keywords,
                "reason": "vLLM structured-output backends reject uniqueItems",
                "canonical_host_revalidation_retained": True,
            },
            "status": "fail",
        }
        try:
            wire_payload = json.loads(content)
            if not isinstance(wire_payload, dict):
                raise QualificationFailure("Goal Interpreter wire output is not an object")
            decision = interpreter._validate_interpretation_content(request, content)
            decision_payload = decision.model_dump(mode="json", exclude_none=True)
            responsibilities = decision_payload["responsibilities"]
            if reasoning_seen:
                raise QualificationFailure("reasoning channel exposed")
            if len(responsibilities) != int(case["count"]):
                raise QualificationFailure(
                    f"responsibility count {len(responsibilities)} != {case['count']}"
                )
            modes = sorted(str(item["output_mode"]) for item in responsibilities)
            if modes != sorted(str(value) for value in case["modes"]):
                raise QualificationFailure(f"output modes {modes!r} != {sorted(case['modes'])!r}")
            for key, accepted_values in case["bindings"].items():
                if not _binding_value_present(responsibilities, str(key), list(accepted_values)):
                    raise QualificationFailure(
                        f"required binding {key} absent from accepted values {accepted_values!r}"
                    )
            expected_coordination = case.get("coordination")
            if expected_coordination and not _wire_coordination_satisfies(
                wire_payload, str(expected_coordination), int(case["count"])
            ):
                raise QualificationFailure(
                    f"missing {expected_coordination} coordination over all refs"
                )
            expected_unresolved = bool(case["unresolved"])
            if bool(decision_payload.get("unresolved")) != expected_unresolved:
                raise QualificationFailure(
                    f"unresolved presence did not equal {expected_unresolved}"
                )
            result["status"] = "pass"
            result["decision"] = decision_payload
            result["wire_coordination"] = wire_payload.get("coordination") or []
        except Exception as exc:
            result["error"] = {"type": type(exc).__name__, "message": str(exc)}
            result["raw_content"] = content
        results.append(result)
    failures = [item for item in results if item["status"] != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "case_count": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "prompt_contract": "current_checkout_after_schema_alignment_fix",
        "cases": results,
    }


async def _qualify(args: argparse.Namespace, evidence: Evidence) -> None:
    endpoint = f"{args.base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=None, trust_env=False) as client:
        version_response = await client.get(
            f"{args.base_url.rstrip('/').removesuffix('/v1')}/version"
        )
        version_response.raise_for_status()
        models_response = await client.get(f"{args.base_url.rstrip('/')}/models")
        models_response.raise_for_status()
        models_payload = models_response.json()
        served_models = [
            str(item.get("id"))
            for item in models_payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
        if args.model not in served_models:
            raise QualificationFailure(
                f"requested model {args.model!r} absent from /models: {served_models}"
            )
        evidence.phases["model_identity"] = {
            "status": "pass",
            "served_models": served_models,
            "provider_version": version_response.json(),
        }

        structured_payload = _chat_payload(
            args.model,
            "Return status=ready and count=2 using the required JSON schema.",
            stream=False,
            max_tokens=128,
        )
        structured_payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "chromie_vllm_contract",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["ready"]},
                        "count": {"type": "integer", "enum": [2]},
                    },
                    "required": ["status", "count"],
                    "additionalProperties": False,
                },
            },
        }
        started = time.perf_counter()
        structured_response = await client.post(endpoint, json=structured_payload)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        structured_response.raise_for_status()
        structured_data = structured_response.json()
        choice = structured_data["choices"][0]
        message = choice["message"]
        reasoning_seen = any(
            message.get(key) not in (None, "", [], {})
            for key in ("reasoning", "reasoning_content", "thinking")
        )
        parsed = json.loads(message["content"])
        if parsed != {"status": "ready", "count": 2}:
            raise QualificationFailure(f"unexpected structured output: {parsed!r}")
        if reasoning_seen:
            raise QualificationFailure("structured response exposed reasoning")
        evidence.phases["structured_output"] = {
            "status": "pass",
            "elapsed_ms": elapsed_ms,
            "finish_reason": choice.get("finish_reason"),
            "parsed": parsed,
            "reasoning_seen": reasoning_seen,
            "usage": structured_data.get("usage"),
        }

        single = await _observe_stream(
            client,
            endpoint,
            _chat_payload(
                args.model,
                "Reply with exactly: chromie-stream-ready",
                stream=True,
                max_tokens=32,
            ),
            label="single_stream",
        )
        _assert_complete_stream(single)
        if single.text.strip() != "chromie-stream-ready":
            raise QualificationFailure(f"single_stream: unexpected output {single.text.strip()!r}")
        evidence.phases["single_stream"] = {
            "status": "pass",
            **single.evidence(),
        }

        overlap_prompt = (
            "Output the integers from 1 through 160, in order, separated only by "
            "single spaces. Do not omit any integer and do not add prose."
        )
        first_task = asyncio.create_task(
            _observe_stream(
                client,
                endpoint,
                _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                label="overlap_a",
            )
        )
        second_task = asyncio.create_task(
            _observe_stream(
                client,
                endpoint,
                _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                label="overlap_b",
            )
        )
        first, second = await asyncio.gather(first_task, second_task)
        _assert_complete_stream(first)
        _assert_complete_stream(second)
        if first.first_delta_s is None or first.finished_s is None:
            raise QualificationFailure("overlap_a: incomplete timing evidence")
        if second.first_delta_s is None or second.finished_s is None:
            raise QualificationFailure("overlap_b: incomplete timing evidence")
        overlap_proven = (
            first.first_delta_s < second.finished_s and second.first_delta_s < first.finished_s
        )
        if not overlap_proven:
            raise QualificationFailure(
                "two requests completed without observed decode-lifetime overlap"
            )
        evidence.phases["two_sequence_overlap"] = {
            "status": "pass",
            "overlap_proven": True,
            "requests": [first.evidence(), second.evidence()],
        }

        cancel_started = asyncio.Event()
        cancelled_observation: StreamObservation | None = None

        async def cancel_target() -> None:
            nonlocal cancelled_observation
            try:
                cancelled_observation = await _observe_stream(
                    client,
                    endpoint,
                    _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                    label="cancel_target",
                    first_delta_event=cancel_started,
                )
            except asyncio.CancelledError:
                raise

        cancel_task = asyncio.create_task(cancel_target())
        survivor_task = asyncio.create_task(
            _observe_stream(
                client,
                endpoint,
                _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                label="cancel_survivor",
            )
        )
        await cancel_started.wait()
        cancel_task.cancel()
        cancelled_result = await asyncio.gather(cancel_task, return_exceptions=True)
        survivor = await survivor_task
        _assert_complete_stream(survivor)
        if not isinstance(cancelled_result[0], asyncio.CancelledError):
            raise QualificationFailure("cancel target did not terminate as cancelled")
        health_after = await client.get(f"{args.base_url.rstrip('/')}/models")
        health_after.raise_for_status()
        evidence.phases["cancellation_isolation"] = {
            "status": "pass",
            "cancelled": True,
            "cancel_target": (
                cancelled_observation.evidence()
                if cancelled_observation is not None
                else {"cancelled": True, "note": "task cancelled inside stream"}
            ),
            "survivor": survivor.evidence(),
            "provider_healthy_after": True,
        }

        if args.tts_url:
            warmup_tts = await _observe_tts(
                args.tts_url,
                speaker=args.tts_speaker,
                label="warmup",
            )
            baseline_tts = await _observe_tts(
                args.tts_url,
                speaker=args.tts_speaker,
                label="baseline",
            )
            contention_tts_task = asyncio.create_task(
                _observe_tts(
                    args.tts_url,
                    speaker=args.tts_speaker,
                    label="contention",
                )
            )
            contention_a_task = asyncio.create_task(
                _observe_stream(
                    client,
                    endpoint,
                    _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                    label="tts_contention_a",
                )
            )
            contention_b_task = asyncio.create_task(
                _observe_stream(
                    client,
                    endpoint,
                    _chat_payload(args.model, overlap_prompt, stream=True, max_tokens=384),
                    label="tts_contention_b",
                )
            )
            contention_tts, contention_a, contention_b = await asyncio.gather(
                contention_tts_task,
                contention_a_task,
                contention_b_task,
            )
            _assert_complete_stream(contention_a)
            _assert_complete_stream(contention_b)
            if contention_tts.finished_s is None:
                raise QualificationFailure("TTS contention: completion timing missing")
            llm_finish_times = [
                value.finished_s
                for value in (contention_a, contention_b)
                if value.finished_s is not None
            ]
            llm_first_times = [
                value.first_delta_s
                for value in (contention_a, contention_b)
                if value.first_delta_s is not None
            ]
            overlap_proven = bool(
                llm_finish_times
                and llm_first_times
                and contention_tts.started_s < max(llm_finish_times)
                and min(llm_first_times) < contention_tts.finished_s
            )
            if not overlap_proven:
                raise QualificationFailure(
                    "TTS and vLLM requests did not have observed lifetime overlap"
                )
            first_audio_ratio = None
            if baseline_tts.first_audio_ms and contention_tts.first_audio_ms:
                first_audio_ratio = contention_tts.first_audio_ms / baseline_tts.first_audio_ms
            elapsed_ratio = None
            if baseline_tts.elapsed_ms and contention_tts.elapsed_ms:
                elapsed_ratio = contention_tts.elapsed_ms / baseline_tts.elapsed_ms
            evidence.phases["tts_gpu_coexistence"] = {
                "status": "pass",
                "overlap_proven": True,
                "discarded_warmup": warmup_tts.evidence(),
                "baseline": baseline_tts.evidence(),
                "under_two_vllm_streams": contention_tts.evidence(),
                "first_audio_slowdown_ratio": first_audio_ratio,
                "total_slowdown_ratio": elapsed_ratio,
                "vllm_requests": [
                    contention_a.evidence(),
                    contention_b.evidence(),
                ],
                "audio_was_generated_but_not_played": True,
            }

        if args.goal_interpreter_probe:
            goal_interpreter = await _qualify_goal_interpreter(
                client,
                endpoint,
                model=args.model,
            )
            evidence.phases["goal_interpreter_semantics"] = goal_interpreter
            if goal_interpreter["status"] != "pass":
                raise QualificationFailure(
                    "Goal Interpreter semantic probe failed: "
                    f"{goal_interpreter['failed']}/{goal_interpreter['case_count']} cases"
                )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tts-url")
    parser.add_argument("--tts-speaker", default="chromie_mixed")
    parser.add_argument("--goal-interpreter-probe", action="store_true")
    return parser


async def _run(args: argparse.Namespace, evidence: Evidence) -> int:
    stop_sampling = asyncio.Event()
    sampler = asyncio.create_task(_gpu_sampler(evidence, stop_sampling))
    try:
        await _qualify(args, evidence)
        evidence.status = "pass"
        return 0
    except Exception as exc:
        evidence.status = "fail"
        evidence.error = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        stop_sampling.set()
        await sampler
        _write_json(args.output, evidence.payload())


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.output = args.output.expanduser()
    evidence = Evidence(
        model=args.model,
        base_url=args.base_url.rstrip("/"),
        started_at=datetime.now(timezone.utc).isoformat(),
        git_revision=_git_revision(),
        git_dirty=_git_dirty(),
    )
    result = asyncio.run(_run(args, evidence))
    print(f"vLLM provider qualification: status={evidence.status} output={args.output}")
    if evidence.error:
        print(
            f"error={evidence.error['type']}: {evidence.error['message']}",
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
