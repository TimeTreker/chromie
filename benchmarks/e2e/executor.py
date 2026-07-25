from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.runners.models import ExecutionObservation

from .evidence import EvidenceItem, load_partial_evidence, merge_evidence, parse_evidence
from .profiles import EvidenceProfile, EvidenceProfileError


@dataclass(frozen=True)
class E2EExecutionRecord:
    scenario_id: str
    correlation_id: str
    execution_state: str
    observation: ExecutionObservation | None
    evidence: tuple[EvidenceItem, ...]
    timing: Mapping[str, Any]
    execution_claims: tuple[str, ...]
    artifacts: tuple[str, ...]
    error: str | None = None
    partial_evidence_retained: bool = False


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:180]


def _response_record(
    *,
    scenario_id: str,
    correlation_id: str,
    payload: Mapping[str, Any],
    partial: tuple[EvidenceItem, ...],
    artifacts: tuple[str, ...],
) -> E2EExecutionRecord:
    if payload.get("schema_version") != 1:
        raise EvidenceProfileError("E2E adapter response must use schema_version 1")
    observed_id = payload.get("scenario_id", scenario_id)
    if observed_id != scenario_id:
        raise EvidenceProfileError(
            f"E2E adapter returned scenario_id {observed_id!r} for {scenario_id!r}"
        )
    observed_correlation = payload.get("correlation_id", correlation_id)
    if observed_correlation != correlation_id:
        raise EvidenceProfileError(
            f"E2E adapter returned correlation_id {observed_correlation!r} for {correlation_id!r}"
        )
    state = payload.get("execution_state", "completed")
    if state not in {"completed", "failed", "partial"}:
        raise EvidenceProfileError(f"invalid E2E execution_state: {state!r}")
    raw_observation = payload.get("observation")
    if not isinstance(raw_observation, Mapping):
        raise EvidenceProfileError("E2E adapter response must contain an observation object")
    response_evidence = parse_evidence(payload.get("evidence", []))
    observation_evidence = parse_evidence(raw_observation.get("evidence", []))
    evidence = merge_evidence(partial, response_evidence, observation_evidence)
    observation_payload = dict(raw_observation)
    observation_payload["scenario_id"] = scenario_id
    observation_payload["evidence"] = [item.to_dict() for item in evidence]
    observation_payload.setdefault("artifacts", list(artifacts))
    observation = ExecutionObservation.from_dict(scenario_id, observation_payload)
    timing = payload.get("timing", {})
    claims = payload.get("execution_claims", [])
    if not isinstance(timing, Mapping):
        raise EvidenceProfileError("E2E adapter timing must be an object")
    if not isinstance(claims, list) or not all(isinstance(item, str) for item in claims):
        raise EvidenceProfileError("E2E adapter execution_claims must be an array of strings")
    response_artifacts = payload.get("artifacts", [])
    if not isinstance(response_artifacts, list) or not all(
        isinstance(item, str) for item in response_artifacts
    ):
        raise EvidenceProfileError("E2E adapter artifacts must be an array of strings")
    all_artifacts = tuple(dict.fromkeys((*artifacts, *response_artifacts, *observation.artifacts)))
    return E2EExecutionRecord(
        scenario_id=scenario_id,
        correlation_id=correlation_id,
        execution_state=state,
        observation=observation,
        evidence=evidence,
        timing=dict(timing),
        execution_claims=tuple(claims),
        artifacts=all_artifacts,
        partial_evidence_retained=bool(partial),
    )


class ReplayE2EExecutor:
    def __init__(self, observations: Mapping[str, Any]) -> None:
        self._observations = dict(observations)

    @classmethod
    def from_file(cls, path: Path) -> "ReplayE2EExecutor":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceProfileError(f"cannot load E2E replay file {path}: {exc}") from exc
        observations = payload.get("observations") if isinstance(payload, Mapping) else None
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise EvidenceProfileError("E2E replay file must use schema_version 1")
        if not isinstance(observations, Mapping):
            raise EvidenceProfileError("E2E replay file must contain observations")
        return cls(observations)

    def execute(
        self,
        scenario: Mapping[str, Any],
        run: Mapping[str, Any],
        profile: EvidenceProfile,
    ) -> E2EExecutionRecord:
        scenario_id = str(scenario["id"])
        correlation_id = str(run["correlation_id"])
        payload = self._observations.get(scenario_id)
        if not isinstance(payload, Mapping):
            return E2EExecutionRecord(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                execution_state="adapter_error",
                observation=None,
                evidence=(),
                timing={},
                execution_claims=(),
                artifacts=(),
                error=f"replay observation missing for scenario {scenario_id!r}",
            )
        try:
            return _response_record(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                payload=payload,
                partial=(),
                artifacts=(),
            )
        except EvidenceProfileError as exc:
            return E2EExecutionRecord(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                execution_state="adapter_error",
                observation=None,
                evidence=(),
                timing={},
                execution_claims=(),
                artifacts=(),
                error=str(exc),
            )


class CommandE2EExecutor:
    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_s: float,
        artifact_root: Path,
    ) -> None:
        if not command:
            raise EvidenceProfileError("E2E adapter command must not be empty")
        if timeout_s <= 0:
            raise EvidenceProfileError("E2E adapter timeout must be positive")
        self._command = tuple(command)
        self._timeout_s = timeout_s
        self._artifact_root = artifact_root

    def execute(
        self,
        scenario: Mapping[str, Any],
        run: Mapping[str, Any],
        profile: EvidenceProfile,
    ) -> E2EExecutionRecord:
        scenario_id = str(scenario["id"])
        correlation_id = str(run["correlation_id"])
        scenario_dir = self._artifact_root / _safe_name(scenario_id)
        scenario_dir.mkdir(parents=True, exist_ok=True)
        partial_path = scenario_dir / "partial_evidence.jsonl"
        stdout_path = scenario_dir / "adapter_stdout.json"
        stderr_path = scenario_dir / "adapter_stderr.txt"
        request = {
            "schema_version": 1,
            "scenario": scenario,
            "run": dict(run),
            "evidence_profile": profile.to_dict(),
            "artifact_dir": str(scenario_dir.resolve()),
            "partial_evidence_path": str(partial_path.resolve()),
        }
        rendered = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        completed: subprocess.CompletedProcess[str] | None = None
        error: str | None = None
        state = "adapter_error"
        try:
            completed = subprocess.run(
                self._command,
                input=rendered,
                text=True,
                capture_output=True,
                timeout=self._timeout_s,
                check=False,
            )
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            if completed.returncode != 0:
                error = (
                    f"E2E adapter exited {completed.returncode}: "
                    f"{completed.stderr.strip() or completed.stdout.strip() or 'no detail'}"
                )
            else:
                try:
                    response = json.loads(completed.stdout)
                except json.JSONDecodeError as exc:
                    error = f"E2E adapter returned invalid JSON: {exc}"
                else:
                    if not isinstance(response, Mapping):
                        error = "E2E adapter response must be an object"
                    else:
                        partial = load_partial_evidence(partial_path)
                        return _response_record(
                            scenario_id=scenario_id,
                            correlation_id=correlation_id,
                            payload=response,
                            partial=partial,
                            artifacts=(
                                str(stdout_path),
                                str(stderr_path),
                                str(partial_path),
                            ),
                        )
        except subprocess.TimeoutExpired as exc:
            state = "timeout"
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            error = f"E2E adapter timed out after {self._timeout_s:.3f}s"
        except OSError as exc:
            error = f"E2E adapter command failed: {exc}"

        try:
            partial = load_partial_evidence(partial_path)
        except EvidenceProfileError as exc:
            partial = ()
            error = f"{error or 'E2E adapter failed'}; partial evidence error: {exc}"
        return E2EExecutionRecord(
            scenario_id=scenario_id,
            correlation_id=correlation_id,
            execution_state=state,
            observation=None,
            evidence=partial,
            timing={},
            execution_claims=(),
            artifacts=(str(stdout_path), str(stderr_path), str(partial_path)),
            error=error,
            partial_evidence_retained=bool(partial),
        )
