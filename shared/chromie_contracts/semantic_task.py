from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields


TaskOperationName = Literal[
    "create",
    "modify",
    "clarification_answer",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "query_status",
    "correct",
    "replace",
]

TaskLifecycleStatus = Literal[
    "open",
    "planning",
    "needs_context",
    "waiting_for_user",
    "awaiting_confirmation",
    "committed",
    "scheduled",
    "running",
    "paused",
    "recoverable",
    "done",
    "failed",
    "refused",
    "timed_out",
    "cancelled",
    "superseded",
]

CommitmentState = Literal[
    "none",
    "heard",
    "evaluating",
    "accepted",
    "waiting_for_user",
    "executing",
    "completed",
    "failed",
    "cancelled",
]

InformationResolution = Literal[
    "ask_user",
    "observe_environment",
    "query_trusted_service",
    "use_owner_approved_preference",
    "use_safe_default",
    "unresolvable",
]

PlanningResultKind = Literal[
    "direct_skill",
    "composed_plan",
    "needs_context",
    "needs_clarification",
    "needs_confirmation",
    "unavailable",
    "refused",
]


class SemanticGoal(BaseModel):
    """Open semantic outcome retained independently from a concrete skill plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    goal_id: str | None = None
    version: int = Field(default=1, ge=1)
    description: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    beneficiary: str | None = None
    object: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "goal_id",
        "description",
        "source_text",
        "beneficiary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("success_criteria", mode="before")
    @classmethod
    def normalize_criteria(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("success_criteria must be a list or string")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
        return out

    @field_validator("object", "constraints", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class InformationGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    blocking: bool = True
    required_for: list[str] = Field(default_factory=list)
    preferred_resolution: InformationResolution
    candidate_values: list[Any] = Field(default_factory=list)
    resolved: bool = False
    resolution_value: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("gap_id", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("required_for", mode="before")
    @classmethod
    def normalize_required_for(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("required_for must be a list or string")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class ResponseStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    speech_act: str = Field(default="inform", min_length=1)
    commitment_state: CommitmentState = "none"
    must_not_claim_completion: bool = True
    covers_task_ids: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", "speech_act", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("covers_task_ids", "claims", mode="before")
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected a list or string")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_completion_contract(self) -> "ResponseStage":
        terminal = {"completed", "failed", "cancelled"}
        if self.must_not_claim_completion and self.commitment_state in terminal:
            raise ValueError(
                "terminal commitment_state requires must_not_claim_completion=false"
            )
        if self.must_not_claim_completion and any(
            claim.strip().casefold() in terminal for claim in self.claims
        ):
            raise ValueError(
                "terminal claims require must_not_claim_completion=false"
            )
        return self


class ResponsePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    immediate: ResponseStage | None = None
    pre_action: ResponseStage | None = None
    progress: list[ResponseStage] = Field(default_factory=list)
    final: ResponseStage | None = None


class SemanticTaskOperation(BaseModel):
    """Advisory semantic change proposed by a model for deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    operation_id: str = Field(min_length=1)
    operation: TaskOperationName
    target_task_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relationship: str = ""
    goal: SemanticGoal | None = None
    goal_update: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    resolved_gap_ids: list[str] = Field(default_factory=list)
    status_update: TaskLifecycleStatus | None = None
    commitment_state: CommitmentState | None = None
    requires_replan: bool = False
    response_plan: ResponsePlan | None = None
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "operation_id",
        "relationship",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("target_task_ids", "resolved_gap_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("task and gap IDs must be a list or string")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @field_validator("goal_update", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "SemanticTaskOperation":
        if self.operation == "create" and self.goal is None:
            raise ValueError("operation=create requires goal")
        if self.operation != "create" and not self.target_task_ids:
            raise ValueError(f"operation={self.operation} requires target_task_ids")
        if self.operation in {"modify", "clarification_answer", "correct", "replace"}:
            if (
                not self.goal_update
                and self.goal is None
                and not self.information_gaps
                and not self.resolved_gap_ids
                and self.status_update is None
            ):
                raise ValueError(
                    f"operation={self.operation} requires a goal update, gap update, or status update"
                )
        return self


class SemanticTaskOperationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    operations: list[SemanticTaskOperation] = Field(default_factory=list)
    response_plan: ResponsePlan | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class TaskContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    task_id: str = Field(min_length=1)
    status: TaskLifecycleStatus = "open"
    semantic_goal: SemanticGoal
    goal_version: int = Field(default=1, ge=1)
    plan_version: int = Field(default=0, ge=0)
    open_information_gaps: list[InformationGap] = Field(default_factory=list)
    confirmation: dict[str, Any] | None = None
    commitment_state: CommitmentState = "none"
    last_user_update: str = ""
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "last_user_update", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("confirmation", "evidence_summary", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return reject_forbidden_low_level_fields(value)


class PlanningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    task_id: str = Field(min_length=1)
    goal_version: int = Field(ge=1)
    result: PlanningResultKind
    plan: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    unavailable_reason: str | None = None
    response_plan: ResponsePlan | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "unavailable_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("plan", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)
