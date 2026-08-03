from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

VALID_LAYERS = frozenset({"module", "integration", "e2e", "stress", "regression"})
VALID_EVIDENCE_LEVELS = frozenset(
    {"static", "replay", "live_model", "live_service", "simulated", "physical", "unknown"}
)
VALID_ORACLE_MODES = frozenset({"deterministic", "semantic_review", "hybrid"})


class ContractError(ValueError):
    """Raised when source material cannot satisfy the common contract."""


@dataclass(frozen=True)
class OraclePolicy:
    """Declare which authority judges a scenario.

    Deterministic sources are machine-checkable contracts or fixtures. Semantic
    dimensions require reviewed model/human judgment over retained evidence.
    Hybrid scenarios use both; semantic review can never override a failed
    deterministic boundary.
    """

    mode: str
    deterministic_sources: tuple[str, ...] = ()
    semantic_dimensions: tuple[str, ...] = ()
    semantic_blocking: bool = True

    def __post_init__(self) -> None:
        if self.mode not in VALID_ORACLE_MODES:
            raise ContractError(f"unknown oracle mode: {self.mode}")
        if self.mode in {"deterministic", "hybrid"} and not self.deterministic_sources:
            raise ContractError(
                f"oracle mode {self.mode!r} requires deterministic_sources"
            )
        if self.mode in {"semantic_review", "hybrid"} and not self.semantic_dimensions:
            raise ContractError(
                f"oracle mode {self.mode!r} requires semantic_dimensions"
            )
        if self.mode == "deterministic" and self.semantic_dimensions:
            raise ContractError(
                "deterministic oracle mode cannot declare semantic_dimensions"
            )
        if self.mode == "semantic_review" and self.deterministic_sources:
            raise ContractError(
                "semantic_review oracle mode cannot declare deterministic_sources"
            )

    @classmethod
    def create(
        cls,
        *,
        mode: str,
        deterministic_sources: Any = None,
        semantic_dimensions: Any = None,
        semantic_blocking: bool = True,
    ) -> "OraclePolicy":
        if not isinstance(semantic_blocking, bool):
            raise ContractError("oracle_policy.semantic_blocking must be boolean")
        return cls(
            mode=str(mode).strip(),
            deterministic_sources=_strings(
                deterministic_sources,
                field_name="oracle_policy.deterministic_sources",
            ),
            semantic_dimensions=_strings(
                semantic_dimensions,
                field_name="oracle_policy.semantic_dimensions",
            ),
            semantic_blocking=semantic_blocking,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OraclePolicy":
        semantic_blocking = value.get("semantic_blocking", True)
        if not isinstance(semantic_blocking, bool):
            raise ContractError("oracle_policy.semantic_blocking must be boolean")
        return cls.create(
            mode=str(value.get("mode") or ""),
            deterministic_sources=value.get("deterministic_sources"),
            semantic_dimensions=value.get("semantic_dimensions"),
            semantic_blocking=semantic_blocking,
        )

    @classmethod
    def derive(
        cls,
        *,
        primary_outcomes: Sequence[str],
        forbidden_behaviors: Sequence[str],
        invariants: Sequence[str],
        review_rubric: Mapping[str, Any],
        legacy_expectations: Mapping[str, Any],
    ) -> "OraclePolicy":
        deterministic_sources: list[str] = []
        if legacy_expectations:
            deterministic_sources.append("legacy_expectations")
        if invariants:
            deterministic_sources.append("invariants")
        if forbidden_behaviors:
            deterministic_sources.append("forbidden_behaviors")

        raw_dimensions = review_rubric.get("dimensions")
        semantic_dimensions = list(
            _strings(raw_dimensions, field_name="review_rubric.dimensions")
        )
        if deterministic_sources and semantic_dimensions:
            mode = "hybrid"
        elif semantic_dimensions:
            mode = "semantic_review"
        else:
            mode = "deterministic"
            if not deterministic_sources:
                deterministic_sources.append("primary_task_observation")
        return cls(
            mode=mode,
            deterministic_sources=tuple(deterministic_sources),
            semantic_dimensions=tuple(semantic_dimensions),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "deterministic_sources": list(self.deterministic_sources),
            "semantic_dimensions": list(self.semantic_dimensions),
            "semantic_blocking": self.semantic_blocking,
        }


def _strings(value: Any, *, field_name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Sequence[Any] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        values = value
    else:
        raise ContractError(f"{field_name} must be a string or an array of strings")
    result = tuple(item.strip() for item in values if isinstance(item, str) and item.strip())
    if len(result) != len(values):
        raise ContractError(f"{field_name} contains a non-string or empty value")
    if not allow_empty and not result:
        raise ContractError(f"{field_name} must not be empty")
    return result


@dataclass(frozen=True)
class SourceReference:
    path: str
    adapter: str
    source_index: int | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ContractError("source.path must not be empty")
        if not self.adapter.strip():
            raise ContractError("source.adapter must not be empty")
        if self.source_index is not None and self.source_index < 0:
            raise ContractError("source.source_index must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "adapter": self.adapter,
            "source_index": self.source_index,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class NormalizedScenario:
    id: str
    layer: str
    datasets: tuple[str, ...]
    source: SourceReference
    inputs: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    primary_outcomes: tuple[str, ...] = ()
    acceptable_auxiliary: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    distribution_observations: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ("static",)
    review_rubric: Mapping[str, Any] = field(default_factory=dict)
    legacy_expectations: Mapping[str, Any] = field(default_factory=dict)
    oracle_policy: OraclePolicy | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ContractError("id must not be empty")
        if self.layer not in VALID_LAYERS:
            raise ContractError(f"unknown layer: {self.layer}")
        if not self.datasets:
            raise ContractError("datasets must not be empty")
        if not isinstance(self.inputs, Mapping) or not self.inputs:
            raise ContractError("inputs must be a non-empty object")
        unknown_evidence = set(self.evidence_requirements) - VALID_EVIDENCE_LEVELS
        if unknown_evidence:
            raise ContractError(f"unknown evidence requirements: {sorted(unknown_evidence)}")
        if not (self.primary_outcomes or self.invariants or self.legacy_expectations):
            raise ContractError(
                "scenario needs a primary outcome, invariant, or preserved legacy expectation"
            )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        layer: str,
        datasets: Any,
        source: SourceReference,
        inputs: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
        capabilities: Any = None,
        primary_outcomes: Any = None,
        acceptable_auxiliary: Any = None,
        forbidden_behaviors: Any = None,
        invariants: Any = None,
        distribution_observations: Any = None,
        evidence_requirements: Any = None,
        review_rubric: Mapping[str, Any] | None = None,
        legacy_expectations: Mapping[str, Any] | None = None,
        oracle_policy: OraclePolicy | Mapping[str, Any] | None = None,
    ) -> "NormalizedScenario":
        normalized_policy: OraclePolicy | None
        if oracle_policy is None:
            normalized_policy = None
        elif isinstance(oracle_policy, OraclePolicy):
            normalized_policy = oracle_policy
        elif isinstance(oracle_policy, Mapping):
            normalized_policy = OraclePolicy.from_mapping(oracle_policy)
        else:
            raise ContractError("oracle_policy must be an object or OraclePolicy")
        return cls(
            id=id.strip(),
            layer=layer,
            datasets=_strings(datasets, field_name="datasets", allow_empty=False),
            source=source,
            inputs=dict(inputs),
            context=dict(context or {}),
            capabilities=_strings(capabilities, field_name="capabilities"),
            primary_outcomes=_strings(primary_outcomes, field_name="primary_outcomes"),
            acceptable_auxiliary=_strings(
                acceptable_auxiliary, field_name="acceptable_auxiliary"
            ),
            forbidden_behaviors=_strings(forbidden_behaviors, field_name="forbidden_behaviors"),
            invariants=_strings(invariants, field_name="invariants"),
            distribution_observations=_strings(
                distribution_observations, field_name="distribution_observations"
            ),
            evidence_requirements=_strings(
                evidence_requirements or ("static",),
                field_name="evidence_requirements",
                allow_empty=False,
            ),
            review_rubric=dict(review_rubric or {}),
            legacy_expectations=dict(legacy_expectations or {}),
            oracle_policy=normalized_policy,
        )

    def to_dict(self) -> dict[str, Any]:
        policy = self.oracle_policy or OraclePolicy.derive(
            primary_outcomes=self.primary_outcomes,
            forbidden_behaviors=self.forbidden_behaviors,
            invariants=self.invariants,
            review_rubric=self.review_rubric,
            legacy_expectations=self.legacy_expectations,
        )
        return {
            "schema_version": 1,
            "id": self.id,
            "layer": self.layer,
            "datasets": list(self.datasets),
            "source": self.source.to_dict(),
            "inputs": dict(self.inputs),
            "context": dict(self.context),
            "capabilities": list(self.capabilities),
            "expectations": {
                "primary_outcomes": list(self.primary_outcomes),
                "acceptable_auxiliary": list(self.acceptable_auxiliary),
                "forbidden_behaviors": list(self.forbidden_behaviors),
                "invariants": list(self.invariants),
                "distribution_observations": list(self.distribution_observations),
            },
            "evidence_requirements": list(self.evidence_requirements),
            "review_rubric": dict(self.review_rubric),
            "legacy_expectations": dict(self.legacy_expectations),
            "oracle_policy": policy.to_dict(),
        }
