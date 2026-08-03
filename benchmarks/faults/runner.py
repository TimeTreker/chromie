from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping, Sequence

from agent.app.clients.ollama_client import (
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from benchmarks.contracts import ContractError
from benchmarks.faults.server import FaultHttpServer


@dataclass(frozen=True)
class RepeatAttempt:
    index: int
    returncode: int | None
    timed_out: bool
    duration_ms: float
    stdout_path: str
    stderr_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
        }


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load fault manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError("fault manifest must be a JSON object")
    return payload


async def _ollama_request(base_url: str, *, timeout_ms: int, response_format: str) -> dict[str, Any]:
    client = OllamaClient(
        base_url=base_url,
        model="fault-probe",
        timeout_ms=timeout_ms,
        purpose="fault_injection_qualification",
    )
    started = time.perf_counter()
    try:
        value = await client.generate(
            "Return a tiny test response.",
            response_format=response_format,  # type: ignore[arg-type]
        )
        return {
            "status": "success",
            "value": value,
            "duration_ms": (time.perf_counter() - started) * 1000.0,
        }
    except OllamaGenerationError as exc:
        return {
            "status": "failure",
            "error_type": type(exc).__name__,
            "failure_class": exc.failure_class,
            "retryable": exc.retryable,
            "detail": str(exc),
            "duration_ms": (time.perf_counter() - started) * 1000.0,
        }
    except Exception as exc:
        metadata = llm_failure_metadata(exc)
        return {
            "status": "failure",
            "error_type": type(exc).__name__,
            "failure_class": metadata["failure_class"],
            "retryable": metadata["retryable"],
            "detail": str(exc),
            "duration_ms": (time.perf_counter() - started) * 1000.0,
        }


def _matches_expected(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for key, value in expected.items():
        if actual.get(key) != value:
            errors.append(f"{key}: expected {value!r}, got {actual.get(key)!r}")
    return not errors, errors


def run_fault_manifest(manifest_path: Path, *, output: Path, repeat: int = 1) -> dict[str, Any]:
    if repeat < 1:
        raise ContractError("repeat must be at least one")
    manifest = _load(manifest_path)
    cases = manifest.get("cases")
    if manifest.get("schema_version") != 1 or not isinstance(cases, list):
        raise ContractError("fault manifest must use schema_version 1 and contain cases")
    results: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ContractError("fault case must be an object")
        case_id = str(case.get("id") or "").strip()
        responses = case.get("responses")
        expected = case.get("expected")
        if not case_id or not isinstance(responses, list) or not isinstance(expected, list):
            raise ContractError("fault case requires id, responses, and expected arrays")
        if len(expected) != int(case.get("request_count") or len(expected)):
            raise ContractError(f"fault case {case_id}: expected count mismatch")
        trials: list[dict[str, Any]] = []
        for trial_index in range(1, repeat + 1):
            with FaultHttpServer(responses) as server:
                observations = [
                    asyncio.run(
                        _ollama_request(
                            server.base_url,
                            timeout_ms=int(case.get("timeout_ms") or 250),
                            response_format=str(case.get("response_format") or "text"),
                        )
                    )
                    for _ in range(len(expected))
                ]
                checks = [
                    _matches_expected(observation, expectation)
                    for observation, expectation in zip(observations, expected)
                ]
                trial_passed = all(item[0] for item in checks)
                trials.append(
                    {
                        "trial": trial_index,
                        "passed": trial_passed,
                        "observations": observations,
                        "errors": [error for _, errors in checks for error in errors],
                        "requests": list(server.state.requests),
                    }
                )
        pass_count = sum(bool(item["passed"]) for item in trials)
        status = "consistent_pass" if pass_count == repeat else "consistent_fail" if pass_count == 0 else "intermittent"
        results.append(
            {
                "id": case_id,
                "description": case.get("description"),
                "status": status,
                "passed": status == "consistent_pass",
                "trials": trials,
            }
        )
    report = {
        "schema_version": 1,
        "kind": "chromie_fault_injection_report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "repeat": repeat,
        "results": results,
        "summary": {
            "total": len(results),
            "consistent_pass": sum(item["status"] == "consistent_pass" for item in results),
            "consistent_fail": sum(item["status"] == "consistent_fail" for item in results),
            "intermittent": sum(item["status"] == "intermittent" for item in results),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def run_repeated_command(
    command: Sequence[str],
    *,
    count: int,
    output_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    if not command:
        raise ContractError("repeat command must not be empty")
    if count < 1:
        raise ContractError("count must be at least one")
    if timeout_s <= 0:
        raise ContractError("timeout must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[RepeatAttempt] = []
    for index in range(1, count + 1):
        stdout_path = output_dir / f"attempt-{index:03d}.stdout.log"
        stderr_path = output_dir / f"attempt-{index:03d}.stderr.log"
        started = time.perf_counter()
        returncode: int | None = None
        timed_out = False
        try:
            completed = subprocess.run(
                list(command),
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            returncode = completed.returncode
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_path.write_text(str(exc.stdout or ""), encoding="utf-8")
            stderr_path.write_text(str(exc.stderr or ""), encoding="utf-8")
        except OSError as exc:
            stderr_path.write_text(str(exc), encoding="utf-8")
        attempts.append(
            RepeatAttempt(
                index=index,
                returncode=returncode,
                timed_out=timed_out,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
            )
        )
    codes = [attempt.returncode for attempt in attempts if not attempt.timed_out]
    pass_count = sum(code == 0 for code in codes)
    timeout_count = sum(attempt.timed_out for attempt in attempts)
    if timeout_count == count:
        status = "infrastructure_timeout"
    elif pass_count == count:
        status = "consistent_pass"
    elif pass_count == 0 and timeout_count == 0:
        status = "consistent_fail"
    else:
        status = "intermittent"
    report = {
        "schema_version": 1,
        "kind": "chromie_repeated_command_report",
        "command": list(command),
        "count": count,
        "timeout_s": timeout_s,
        "status": status,
        "attempts": [attempt.to_dict() for attempt in attempts],
        "summary": {
            "pass": pass_count,
            "fail": sum(code not in (None, 0) for code in codes),
            "timeout": timeout_count,
        },
    }
    (output_dir / "repeat-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
