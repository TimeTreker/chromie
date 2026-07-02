from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .interaction import reject_forbidden_low_level_fields


ProposalState = Literal[
    "advisory",
    "committed",
    "running",
    "completed",
    "failed",
    "refused",
    "timed_out",
    "cancelled",
    "not_committed",
    "rejected",
    "superseded",
]


class TaskProposalPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "unknown"
    reason_code: str = "unknown"
    world_feasibility: str = "unknown_until_runtime"


class TaskProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(default="unknown", min_length=1)
    proposal_kind: str = Field(default="task", min_length=1)
    task_type: str = Field(default="unknown", min_length=1)
    state: ProposalState
    reason: str = ""
    effectful: bool = False
    priority: str = "normal"
    sequence: int = Field(default=0, ge=0)
    skill_id: str | None = None
    request_id: str | None = None
    speech_id: str | None = None
    committed_by: str | None = None
    superseded_by: str | None = None
    preflight: TaskProposalPreflight | None = None
    timing: str | None = None
    requires_confirmation: bool | None = None
    text_chars: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "id",
        "source",
        "proposal_kind",
        "task_type",
        "reason",
        "priority",
        "skill_id",
        "request_id",
        "speech_id",
        "committed_by",
        "superseded_by",
        "timing",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class TaskProposalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_count: int = Field(default=0, ge=0)
    states: dict[str, int] = Field(default_factory=dict)
    sources: dict[str, int] = Field(default_factory=dict)
    preflight_statuses: dict[str, int] = Field(default_factory=dict)
    effectful_proposal_count: int = Field(default=0, ge=0)
    committed_effectful_count: int = Field(default=0, ge=0)
    not_committed_effectful_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)

    @field_validator("states", "sources", "preflight_statuses")
    @classmethod
    def reject_negative_counts(cls, value: dict[str, int]) -> dict[str, int]:
        for key, item in value.items():
            if item < 0:
                raise ValueError(f"negative count for {key!r}")
        return value


class TaskProposalLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    strategy: str = Field(min_length=1)
    summary: TaskProposalSummary
    proposals: list[TaskProposal] = Field(default_factory=list)

    @field_validator("strategy", mode="before")
    @classmethod
    def normalize_strategy(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value
