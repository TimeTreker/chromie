from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from benchmarks.contracts import ContractError


VALID_RUN_MODES = frozenset({"replay", "live_model"})


@dataclass(frozen=True)
class RunProfile:
    mode: str
    evidence_level: str
    model: str | None = None
    prompt_revision: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in VALID_RUN_MODES:
            raise ContractError(f"unsupported benchmark run mode: {self.mode}")
        if not self.evidence_level.strip():
            raise ContractError("run evidence_level must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "evidence_level": self.evidence_level,
            "model": self.model,
            "prompt_revision": self.prompt_revision,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class InvariantObservation:
    name: str
    passed: bool
    detail: str | None = None

    @classmethod
    def from_value(cls, name: str, value: Any) -> "InvariantObservation":
        if isinstance(value, bool):
            return cls(name=name, passed=value)
        if isinstance(value, Mapping):
            passed = value.get("passed")
            if not isinstance(passed, bool):
                raise ContractError(f"invariant {name!r} must declare boolean passed")
            detail = value.get("detail")
            if detail is not None and not isinstance(detail, str):
                raise ContractError(f"invariant {name!r} detail must be a string or null")
            return cls(name=name, passed=passed, detail=detail)
        raise ContractError(f"invariant {name!r} must be a boolean or object")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class ExecutionObservation:
    scenario_id: str
    primary_task_passed: bool | None = None
    primary_outcome: Any = None
    auxiliary_behavior: Any = None
    behaviors: tuple[str, ...] = ()
    evidence: tuple[Any, ...] = ()
    invariant_results: tuple[InvariantObservation, ...] = ()
    latency_ms: float | None = None
    artifacts: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, scenario_id: str, payload: Mapping[str, Any]) -> "ExecutionObservation":
        observed_id = payload.get("scenario_id", scenario_id)
        if observed_id != scenario_id:
            raise ContractError(
                f"executor returned scenario_id {observed_id!r} for {scenario_id!r}"
            )
        primary_task_passed = payload.get("primary_task_passed")
        if primary_task_passed is not None and not isinstance(primary_task_passed, bool):
            raise ContractError("primary_task_passed must be boolean or null")
        behaviors_value = payload.get("behaviors", [])
        if not isinstance(behaviors_value, list) or not all(
            isinstance(item, str) and item for item in behaviors_value
        ):
            raise ContractError("behaviors must be an array of non-empty strings")
        invariant_value = payload.get("invariant_results", {})
        if not isinstance(invariant_value, Mapping):
            raise ContractError("invariant_results must be an object keyed by invariant name")
        invariants = tuple(
            InvariantObservation.from_value(name, value)
            for name, value in sorted(invariant_value.items())
        )
        latency = payload.get("latency_ms")
        if latency is not None and (not isinstance(latency, (int, float)) or latency < 0):
            raise ContractError("latency_ms must be a non-negative number or null")
        evidence = payload.get("evidence", [])
        artifacts = payload.get("artifacts", [])
        if not isinstance(evidence, list):
            raise ContractError("evidence must be an array")
        if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
            raise ContractError("artifacts must be an array of strings")
        return cls(
            scenario_id=scenario_id,
            primary_task_passed=primary_task_passed,
            primary_outcome=payload.get("primary_outcome"),
            auxiliary_behavior=payload.get("auxiliary_behavior"),
            behaviors=tuple(behaviors_value),
            evidence=tuple(evidence),
            invariant_results=invariants,
            latency_ms=float(latency) if latency is not None else None,
            artifacts=tuple(artifacts),
            raw=dict(payload),
        )
