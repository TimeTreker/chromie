from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from benchmarks.contracts import ContractError
from benchmarks.runners.models import ExecutionObservation, RunProfile


class ScenarioExecutor(Protocol):
    def execute(
        self, scenario: Mapping[str, Any], profile: RunProfile
    ) -> ExecutionObservation: ...


class ReplayExecutor:
    """Replay retained observations without invoking production components."""

    def __init__(self, observations: Mapping[str, Any]) -> None:
        self._observations = dict(observations)

    @classmethod
    def from_file(cls, path: Path) -> "ReplayExecutor":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot load replay observations {path}: {exc}") from exc
        observations = payload.get("observations") if isinstance(payload, Mapping) else None
        if payload.get("schema_version") != 1 or not isinstance(observations, Mapping):
            raise ContractError("replay file must use schema_version 1 and contain observations")
        return cls(observations)

    def execute(
        self, scenario: Mapping[str, Any], profile: RunProfile
    ) -> ExecutionObservation:
        scenario_id = scenario["id"]
        payload = self._observations.get(scenario_id)
        if not isinstance(payload, Mapping):
            raise ContractError(f"replay observation missing for scenario {scenario_id!r}")
        return ExecutionObservation.from_dict(scenario_id, payload)


class CommandExecutor:
    """Invoke an explicit adapter command for a configured live model/runtime.

    The normalized scenario and run profile are written as one JSON object to
    stdin. The command must return one observation object on stdout. This keeps
    benchmark infrastructure independent of production imports and deployment
    topology.
    """

    def __init__(self, command: Sequence[str], *, timeout_s: float = 120.0) -> None:
        if not command:
            raise ContractError("live-model command must not be empty")
        if timeout_s <= 0:
            raise ContractError("command timeout must be positive")
        self._command = tuple(command)
        self._timeout_s = timeout_s

    def execute(
        self, scenario: Mapping[str, Any], profile: RunProfile
    ) -> ExecutionObservation:
        request = json.dumps(
            {"schema_version": 1, "scenario": scenario, "run": profile.to_dict()},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            completed = subprocess.run(
                self._command,
                input=request,
                text=True,
                capture_output=True,
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractError(f"benchmark adapter command failed: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ContractError(
                f"benchmark adapter exited {completed.returncode}: {detail or 'no detail'}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError(f"benchmark adapter returned invalid JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("benchmark adapter observation must be an object")
        return ExecutionObservation.from_dict(scenario["id"], payload)
