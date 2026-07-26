from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from benchmarks.contracts import ContractError


VALID_RUN_MODES = frozenset({"replay", "live_model"})

SOCIAL_ATTENTION_LIFECYCLE_STATES = {
    "proposal_state": frozenset({"none", "proposed", "invalid", "not_observed"}),
    "materialization_state": frozenset({"not_applicable", "accepted", "rejected", "not_observed"}),
    "provider_acceptance_state": frozenset({"not_applicable", "accepted", "rejected", "not_observed"}),
    "provider_completion_state": frozenset({"not_applicable", "completed", "failed", "not_observed"}),
    "safe_idle_state": frozenset({"not_applicable", "confirmed", "failed", "not_observed"}),
}


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
    social_attention_lifecycle: Mapping[str, Any] = field(default_factory=dict)
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
        lifecycle_value = payload.get("social_attention_lifecycle", {})
        if lifecycle_value is None:
            lifecycle_value = {}
        if not isinstance(lifecycle_value, Mapping):
            raise ContractError("social_attention_lifecycle must be an object")
        lifecycle = dict(lifecycle_value)
        unknown_lifecycle_fields = set(lifecycle) - (
            set(SOCIAL_ATTENTION_LIFECYCLE_STATES) | {"semantic_class", "detail"}
        )
        if unknown_lifecycle_fields:
            raise ContractError(
                "social_attention_lifecycle contains unknown fields: "
                + ", ".join(sorted(unknown_lifecycle_fields))
            )
        for name, allowed in SOCIAL_ATTENTION_LIFECYCLE_STATES.items():
            value = lifecycle.get(name)
            if value is not None and value not in allowed:
                raise ContractError(
                    f"social_attention_lifecycle.{name} must be one of: "
                    + ", ".join(sorted(allowed))
                )
        for name in ("semantic_class", "detail"):
            value = lifecycle.get(name)
            if value is not None and not isinstance(value, str):
                raise ContractError(
                    f"social_attention_lifecycle.{name} must be a string or null"
                )
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
            social_attention_lifecycle=lifecycle,
            raw=dict(payload),
        )
