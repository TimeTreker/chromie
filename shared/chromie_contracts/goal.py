from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields
from .semantic_task import InformationGap, SemanticGoal, TaskContextSnapshot


GoalRelationship = Literal[
    "continue",
    "modify",
    "clarify",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "replace",
    "merge",
    "split",
    "reference",
    "new",
]

GoalLifecycleStatus = Literal[
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


class GoalVersionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    version: int = Field(ge=1)

    @field_validator("goal_id", mode="before")
    @classmethod
    def normalize_goal_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value


class GoalAssociation(BaseModel):
    """Advisory semantic relationship between a user turn and retained goals."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    association_id: str = Field(min_length=1)
    relationship: GoalRelationship
    target_goal_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    ambiguity_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("association_id", "reason_summary", "ambiguity_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("target_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("target_goal_ids must be a list or string")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_relationship_shape(self) -> "GoalAssociation":
        if self.relationship == "new" and self.target_goal_ids:
            raise ValueError("relationship=new must not target existing goals")
        if self.relationship != "new" and not self.target_goal_ids:
            raise ValueError(f"relationship={self.relationship} requires target_goal_ids")
        if self.relationship == "merge" and len(self.target_goal_ids) < 2:
            raise ValueError("relationship=merge requires at least two target goals")
        return self


class GoalSet(BaseModel):
    """Independent semantic goals identified for one user turn."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    turn_id: str = Field(min_length=1)
    goals: list[SemanticGoal] = Field(default_factory=list)
    associations: list[GoalAssociation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_goal_ids(self) -> "GoalSet":
        ids = [goal.goal_id for goal in self.goals if goal.goal_id]
        if len(ids) != len(set(ids)):
            raise ValueError("GoalSet goal_id values must be unique")
        return self


class ActiveGoalSnapshot(BaseModel):
    """Bounded, planner-facing projection of one active semantic goal."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    goal_id: str = Field(min_length=1)
    goal_version: int = Field(default=1, ge=1)
    status: GoalLifecycleStatus = "open"
    goal: SemanticGoal
    open_information_gaps: list[InformationGap] = Field(default_factory=list)
    commitment_state: str = "none"
    last_user_update: str = ""
    updated_ms: int | None = Field(default=None, ge=0)
    source_task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("goal_id", "commitment_state", "last_user_update", "source_task_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @classmethod
    def from_task_snapshot(cls, snapshot: TaskContextSnapshot | dict[str, Any]) -> "ActiveGoalSnapshot":
        task = snapshot if isinstance(snapshot, TaskContextSnapshot) else TaskContextSnapshot.model_validate(snapshot)
        goal = task.semantic_goal.model_copy(deep=True)
        goal_id = goal.goal_id or task.task_id
        if goal.goal_id is None:
            goal.goal_id = goal_id
        goal.version = task.goal_version
        updated_ms = task.metadata.get("updated_ms") if isinstance(task.metadata, dict) else None
        try:
            normalized_updated_ms = int(updated_ms) if updated_ms is not None else None
        except (TypeError, ValueError):
            normalized_updated_ms = None
        return cls(
            goal_id=goal_id,
            goal_version=task.goal_version,
            status=task.status,
            goal=goal,
            open_information_gaps=task.open_information_gaps,
            commitment_state=task.commitment_state,
            last_user_update=task.last_user_update,
            updated_ms=normalized_updated_ms,
            source_task_id=task.task_id,
            metadata={
                "compatibility_source": "semantic_task",
                "plan_version": task.plan_version,
                **task.metadata,
            },
        )


def stable_goal_operation_id(
    *,
    turn_id: str,
    ordinal: int,
    relationship: str,
    target_goal_ids: list[str] | tuple[str, ...] = (),
) -> str:
    """Return a replay-safe identifier for one semantic goal operation proposal."""

    normalized_turn = " ".join(str(turn_id or "").strip().split())
    if not normalized_turn:
        raise ValueError("turn_id is required")
    if ordinal < 0:
        raise ValueError("ordinal must be non-negative")
    normalized_relationship = " ".join(str(relationship or "").strip().lower().split())
    if not normalized_relationship:
        raise ValueError("relationship is required")
    targets = sorted({" ".join(str(item or "").strip().split()) for item in target_goal_ids if str(item or "").strip()})
    payload = "|".join([normalized_turn, str(ordinal), normalized_relationship, *targets])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"goalop_{digest}"
