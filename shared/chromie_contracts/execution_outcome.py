from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import normalize_whitespace

from .interaction import CapabilityIdentityModel, reject_forbidden_low_level_fields


ExecutionEvidenceStatus = Literal[
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "refused",
    "not_run",
]
GoalExecutionStatus = Literal[
    "completed",
    "partial",
    "failed",
    "cancelled",
    "timed_out",
    "refused",
    "not_run",
]
ExecutionAggregateStatus = GoalExecutionStatus
ModelObservationStatus = Literal[
    "available",
    "schema_unavailable",
    "schema_invalid",
    "too_large",
    "sensitive",
]
ClaimQualificationStatus = Literal[
    "established",
    "insufficient",
    "stale",
    "contradicted",
    "unknown",
]
ClaimCoverageStatus = Literal[
    "not_required",
    "complete",
    "partial",
    "unknown",
]
EvidenceRequirementSource = Literal[
    "execution_observation",
    "provider_postcondition",
]
JsonScalar: TypeAlias = str | int | float | bool | None


class EvidenceRequirement(BaseModel):
    """One declarative observation requirement for a factual claim.

    A requirement always requires one schema-valid, available observation of
    the selected source. Optional exact scalar assertions can further constrain
    that observation. It is not a rule engine and it cannot select work,
    capabilities, or cognitive depth. ``field_assertions`` uses dotted paths
    only to address already schema-validated observation data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: EvidenceRequirementSource
    condition: str = ""
    field_assertions: dict[str, JsonScalar] = Field(default_factory=dict)
    trust_domain: str = ""
    max_age_ms: int | None = Field(default=None, ge=0)

    @field_validator("condition", "trust_domain", mode="before")
    @classmethod
    def normalize_requirement_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("field_assertions", mode="before")
    @classmethod
    def normalize_assertions(cls, value: Any) -> dict[str, JsonScalar]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("field_assertions must be an object")
        normalized: dict[str, JsonScalar] = {}
        for raw_path, expected in value.items():
            path = ".".join(
                part.strip()
                for part in str(raw_path or "").split(".")
                if part.strip()
            )
            if not path:
                raise ValueError("field_assertions paths must not be empty")
            if isinstance(expected, (dict, list, tuple, set)):
                raise ValueError(
                    "field_assertions values must be exact JSON scalars"
                )
            normalized[path] = expected
        return normalized

    @model_validator(mode="after")
    def validate_requirement_shape(self) -> "EvidenceRequirement":
        if self.source == "execution_observation" and self.condition:
            raise ValueError(
                "execution_observation requirements must not name a postcondition"
            )
        if self.source == "provider_postcondition" and not self.condition:
            raise ValueError(
                "provider_postcondition requirements require condition"
            )
        return self


class EvidenceRequirementGroup(BaseModel):
    """One sufficient conjunction; policy groups are alternatives."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirements: list[EvidenceRequirement] = Field(min_length=1, max_length=16)
    minimum_independent_trust_domains: int = Field(default=1, ge=1, le=16)

    @model_validator(mode="after")
    def validate_trust_domain_bound(self) -> "EvidenceRequirementGroup":
        if self.minimum_independent_trust_domains > len(self.requirements):
            raise ValueError(
                "minimum_independent_trust_domains cannot exceed requirement count"
            )
        return self


class ClaimQualificationPolicy(BaseModel):
    """Owner-reviewed evidence sufficiency policy for one factual claim.

    Every requirement inside one group must hold. Multiple groups are accepted
    alternatives. The policy is declarative and runtime-checkable; providers may
    advertise observations, but changing provider output cannot silently change
    this owner-reviewed sufficiency rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=200)
    requirement_groups: list[EvidenceRequirementGroup] = Field(
        min_length=1,
        max_length=8,
    )
    requires_complete_coverage: bool = False

    @field_validator("claim", mode="before")
    @classmethod
    def normalize_claim(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


def claim_qualification_policy_sha256(
    policy: ClaimQualificationPolicy | dict[str, Any],
) -> str:
    validated = (
        policy
        if isinstance(policy, ClaimQualificationPolicy)
        else ClaimQualificationPolicy.model_validate(policy)
    )
    payload = json.dumps(
        validated.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ClaimQualification(BaseModel):
    """Immutable result of mechanically checking evidence against a policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=200)
    status: ClaimQualificationStatus
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    reason_codes: list[str] = Field(default_factory=list, max_length=16)
    trust_domains: list[str] = Field(default_factory=list, max_length=16)
    coverage: ClaimCoverageStatus = "not_required"
    satisfied_group_index: int | None = Field(default=None, ge=0)
    evaluated_at: datetime

    @field_validator("claim", mode="before")
    @classmethod
    def normalize_qualification_claim(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "evidence_ids",
        "reason_codes",
        "trust_domains",
        mode="before",
    )
    @classmethod
    def normalize_qualification_lists(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("evaluated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_established_shape(self) -> "ClaimQualification":
        if self.status == "established" and self.satisfied_group_index is None:
            raise ValueError(
                "established qualification requires satisfied_group_index"
            )
        if self.status != "established" and self.satisfied_group_index is not None:
            raise ValueError(
                "non-established qualification cannot name a satisfied group"
            )
        return self


def _normalize_identifier(value: Any) -> Any:
    return normalize_whitespace(value)


def _normalize_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list or string")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def aggregate_execution_status(
    statuses: list[ExecutionEvidenceStatus | GoalExecutionStatus],
) -> GoalExecutionStatus:
    """Aggregate terminal states without inventing partial completion.

    ``partial`` is evidence-bearing: at least one child completed (or was
    itself partial) while other work remains unresolved. Heterogeneous
    uncompleted states are conservatively aggregated as ``failed`` while their
    exact per-goal or per-step statuses remain available in the bundle.
    """

    if not statuses:
        return "not_run"
    unique = set(statuses)
    if len(unique) == 1:
        return statuses[0]
    if "completed" in unique or "partial" in unique:
        return "partial"
    return "failed"


class ModelObservation(BaseModel):
    """Bounded provider output that is safe to expose to a model stage.

    Raw provider output is not part of this contract. A non-available
    observation retains only its digest, byte size, and bounded validation
    diagnostics so invalid, oversized, schema-less, or sensitive output cannot
    become response evidence accidentally.
    """

    model_config = ConfigDict(extra="forbid")

    status: ModelObservationStatus
    data: dict[str, Any] = Field(default_factory=dict)
    schema_validated: bool = False
    output_sha256: str = Field(min_length=64, max_length=64)
    output_size_bytes: int = Field(ge=0)
    validation_errors: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("data")
    @classmethod
    def reject_low_level_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @field_validator("validation_errors", mode="before")
    @classmethod
    def normalize_validation_errors(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("validation_errors must be a list or string")
        return [
            text[:300]
            for item in value[:8]
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @model_validator(mode="after")
    def validate_exposure_boundary(self) -> "ModelObservation":
        if self.status == "available":
            if not self.schema_validated:
                raise ValueError(
                    "available model observation must be schema validated"
                )
        elif self.data:
            raise ValueError(
                "non-available model observation must not expose output data"
            )
        return self


class ExecutionEvidence(CapabilityIdentityModel):
    """One exact planned-step/request correlation and its terminal evidence."""

    schema_version: int = Field(default=1, ge=1)
    evidence_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    source_goal_ids: list[str] = Field(min_length=1)
    status: ExecutionEvidenceStatus
    reported_status: str = ""
    provider_id: str | None = None
    trust_domain: str = ""
    observation: ModelObservation | None = None
    completion_qualification: ClaimQualification | None = None
    reason_code: str | None = None
    message: str = ""
    trace_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    missing_result: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "evidence_id",
        "request_id",
        "step_id",
        "reported_status",
        "provider_id",
        "trust_domain",
        "reason_code",
        "message",
        "trace_id",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return _normalize_identifier(value)

    @field_validator("source_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_missing_result(self) -> "ExecutionEvidence":
        if self.missing_result and self.status != "not_run":
            raise ValueError("missing result evidence must have status=not_run")
        if self.status == "completed" and self.missing_result:
            raise ValueError("missing result evidence cannot report completion")
        if (
            self.status == "completed"
            and self.observation is not None
            and self.observation.status == "schema_invalid"
        ):
            raise ValueError(
                "completed execution evidence cannot rely on an untrusted "
                "or schema-invalid provider observation"
            )
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class GoalExecutionOutcome(BaseModel):
    """Deterministic execution status for one executable canonical goal."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    goal_id: str = Field(min_length=1)
    status: GoalExecutionStatus
    step_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    unresolved_step_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("goal_id", mode="before")
    @classmethod
    def normalize_goal_id(cls, value: Any) -> Any:
        return _normalize_identifier(value)

    @field_validator(
        "step_ids",
        "evidence_ids",
        "completed_step_ids",
        "unresolved_step_ids",
        "reason_codes",
        mode="before",
    )
    @classmethod
    def normalize_text_lists(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_step_partition(self) -> "GoalExecutionOutcome":
        steps = set(self.step_ids)
        completed = set(self.completed_step_ids)
        unresolved = set(self.unresolved_step_ids)
        if not completed.issubset(steps) or not unresolved.issubset(steps):
            raise ValueError(
                "completed and unresolved step IDs must belong to step_ids"
            )
        if completed.intersection(unresolved):
            raise ValueError(
                "completed and unresolved step IDs must not overlap"
            )
        if completed.union(unresolved) != steps:
            raise ValueError(
                "completed and unresolved step IDs must partition step_ids"
            )
        if self.status == "completed" and completed != steps:
            raise ValueError(
                "completed goal outcome requires every step to be completed"
            )
        if self.status == "partial" and (
            not completed or not unresolved
        ):
            raise ValueError(
                "partial goal outcome requires completed and unresolved steps"
            )
        if self.status != "partial" and completed and unresolved:
            raise ValueError(
                "mixed completed and unresolved steps require status=partial"
            )
        if self.status == "not_run" and completed:
            raise ValueError(
                "not_run goal outcome cannot contain completed steps"
            )
        return self


class ProviderPostconditionEvidence(BaseModel):
    """Provider observation retained separately from requested-step evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    evidence_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    trust_domain: str = ""
    condition: str = Field(min_length=1)
    observation: ModelObservation
    source_goal_ids: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "evidence_id",
        "provider_id",
        "trust_domain",
        "condition",
        "trace_id",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return _normalize_identifier(value)

    @field_validator("source_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class ExecutionOutcomeBundle(BaseModel):
    """Immutable deterministic execution outcome for post-execution cognition."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    outcome_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    canonical_plan_id: str = Field(min_length=1)
    canonical_plan_fingerprint: str = Field(min_length=16)
    canonical_goal_ids: list[str] = Field(min_length=1)
    non_execution_goal_ids: list[str] = Field(default_factory=list)
    aggregate_status: ExecutionAggregateStatus
    evidence: list[ExecutionEvidence] = Field(default_factory=list)
    goal_outcomes: list[GoalExecutionOutcome] = Field(default_factory=list)
    provider_postconditions: list[ProviderPostconditionEvidence] = Field(
        default_factory=list
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "outcome_id",
        "turn_id",
        "interaction_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return _normalize_identifier(value)

    @field_validator(
        "canonical_goal_ids",
        "non_execution_goal_ids",
        mode="before",
    )
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_correlations(self) -> "ExecutionOutcomeBundle":
        canonical_goals = set(self.canonical_goal_ids)
        non_execution_goals = set(self.non_execution_goal_ids)
        if not non_execution_goals.issubset(canonical_goals):
            raise ValueError(
                "non_execution_goal_ids must belong to canonical_goal_ids"
            )

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("execution evidence IDs must be unique")
        request_ids = [item.request_id for item in self.evidence]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError(
                "execution evidence request IDs must be unique"
            )
        step_ids = [item.step_id for item in self.evidence]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError(
                "execution evidence step IDs must be unique"
            )

        outcomes_by_goal = {
            item.goal_id: item for item in self.goal_outcomes
        }
        if len(outcomes_by_goal) != len(self.goal_outcomes):
            raise ValueError("goal execution outcome IDs must be unique")
        executable_goals = canonical_goals - non_execution_goals
        if set(outcomes_by_goal) != executable_goals:
            missing = sorted(executable_goals - set(outcomes_by_goal))
            extra = sorted(set(outcomes_by_goal) - executable_goals)
            raise ValueError(
                "goal execution outcomes must cover exactly executable "
                f"canonical goals; missing={missing}, extra={extra}"
            )

        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        for evidence in self.evidence:
            unknown = set(evidence.source_goal_ids) - executable_goals
            if unknown:
                raise ValueError(
                    "execution evidence references non-executable or unknown "
                    "goal IDs: "
                    + ",".join(sorted(unknown))
                )
        for goal_id, outcome in outcomes_by_goal.items():
            unknown_evidence = set(outcome.evidence_ids) - set(evidence_by_id)
            if unknown_evidence:
                raise ValueError(
                    "goal execution outcome references unknown evidence IDs: "
                    + ",".join(sorted(unknown_evidence))
                )
            foreign = [
                evidence_id
                for evidence_id in outcome.evidence_ids
                if goal_id not in evidence_by_id[evidence_id].source_goal_ids
            ]
            if foreign:
                raise ValueError(
                    "goal execution outcome references evidence owned by "
                    "another goal: "
                    + ",".join(sorted(foreign))
                )
            evidence_steps = {
                evidence_by_id[evidence_id].step_id
                for evidence_id in outcome.evidence_ids
            }
            if evidence_steps != set(outcome.step_ids):
                raise ValueError(
                    "goal execution outcome evidence must cover exactly its "
                    "step_ids"
                )
            goal_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in outcome.evidence_ids
            ]
            expected_goal_status = aggregate_execution_status(
                [item.status for item in goal_evidence]
            )
            if outcome.status != expected_goal_status:
                raise ValueError(
                    "goal execution outcome status must be derived from its "
                    "execution evidence"
                )
            expected_completed_steps = {
                item.step_id
                for item in goal_evidence
                if item.status == "completed"
            }
            if set(outcome.completed_step_ids) != expected_completed_steps:
                raise ValueError(
                    "completed_step_ids must match completed execution "
                    "evidence"
                )

        evidence_owners: dict[str, set[str]] = {
            evidence_id: set() for evidence_id in evidence_by_id
        }
        for goal_id, outcome in outcomes_by_goal.items():
            for evidence_id in outcome.evidence_ids:
                evidence_owners[evidence_id].add(goal_id)
        orphan_evidence = sorted(
            evidence_id
            for evidence_id, owner_ids in evidence_owners.items()
            if not owner_ids
        )
        if orphan_evidence:
            raise ValueError(
                "execution evidence must be referenced by a goal outcome: "
                + ",".join(orphan_evidence)
            )
        for evidence_id, owner_ids in evidence_owners.items():
            declared_owner_ids = set(
                evidence_by_id[evidence_id].source_goal_ids
            )
            if owner_ids != declared_owner_ids:
                raise ValueError(
                    "execution evidence source_goal_ids must exactly match "
                    "the goal outcomes that reference it"
                )

        expected_aggregate = aggregate_execution_status(
            [item.status for item in self.goal_outcomes]
        )
        if self.aggregate_status != expected_aggregate:
            raise ValueError(
                "aggregate_status must be derived from goal_outcomes"
            )

        postcondition_ids = [
            item.evidence_id for item in self.provider_postconditions
        ]
        if len(postcondition_ids) != len(set(postcondition_ids)):
            raise ValueError(
                "provider postcondition evidence IDs must be unique"
            )
        if set(postcondition_ids).intersection(evidence_ids):
            raise ValueError(
                "provider postcondition and execution evidence IDs must not "
                "overlap"
            )
        for item in self.provider_postconditions:
            unknown = set(item.source_goal_ids) - canonical_goals
            if unknown:
                raise ValueError(
                    "provider postcondition references unknown goal IDs: "
                    + ",".join(sorted(unknown))
                )
        return self


def goal_completion_qualification_summary(
    bundle: ExecutionOutcomeBundle,
    outcome: GoalExecutionOutcome,
) -> dict[str, Any]:
    """Project request-level completion qualification for one canonical Goal.

    Execution status remains an immutable fact about what the provider/runtime
    reported. This projection answers the separate question of whether every
    maintained completion claim required for that Goal is established. It adds
    no semantic judgment: the result is derived only from exact evidence IDs,
    their committed qualification requirement, and immutable qualification
    records.
    """

    evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
    referenced = [
        evidence_by_id[evidence_id]
        for evidence_id in outcome.evidence_ids
        if evidence_id in evidence_by_id
    ]
    required = [
        item
        for item in referenced
        if item.metadata.get("completion_qualification_required") is True
    ]
    rows: list[dict[str, Any]] = []
    for item in required:
        qualification = item.completion_qualification
        rows.append(
            {
                "evidence_id": item.evidence_id,
                "status": (
                    qualification.status
                    if qualification is not None
                    else "unknown"
                ),
                "claim": (
                    qualification.claim if qualification is not None else ""
                ),
                "reason_codes": (
                    list(qualification.reason_codes)
                    if qualification is not None
                    else [
                        str(
                            item.metadata.get(
                                "completion_evidence_gate_reason"
                            )
                            or "completion_qualification_missing"
                        )
                    ]
                ),
            }
        )
    return {
        "required": bool(required),
        "established": bool(required)
        and all(
            item.completion_qualification is not None
            and item.completion_qualification.status == "established"
            for item in required
        ),
        "qualifications": rows,
    }


def execution_outcome_fingerprint(bundle: ExecutionOutcomeBundle) -> str:
    payload = json.dumps(
        bundle.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
