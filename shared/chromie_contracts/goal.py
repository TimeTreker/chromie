from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields
from .semantic_task import InformationGap, ResponsibilityStatus, SemanticGoal, TaskContextSnapshot
from .discourse import DiscourseReferentUpdate, ResolvedDiscourseReference


GoalRelationship = Literal[
    "continue",
    "modify",
    "clarify",
    "confirm",
    "reject",
    "cancel",
    "pause",
    "resume",
    "merge",
    "split",
    "reference",
    "new",
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
    goal_update: dict[str, Any] = Field(default_factory=dict)
    resolved_gap_ids: list[str] = Field(default_factory=list)
    requires_replan: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("association_id", "reason_summary", "ambiguity_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("target_goal_ids", "resolved_gap_ids", mode="before")
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

    @field_validator("goal_update", "metadata")
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
    responsibility_status: ResponsibilityStatus = "open"
    work_status: str = "open"
    goal: SemanticGoal
    open_information_gaps: list[InformationGap] = Field(default_factory=list)
    last_user_update: str = ""
    updated_ms: int | None = Field(default=None, ge=0)
    source_task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("goal_id", "work_status", "last_user_update", "source_task_id", mode="before")
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
            responsibility_status=goal.responsibility_status,
            work_status=task.status,
            goal=goal,
            open_information_gaps=task.open_information_gaps,
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


class GoalProgressBinding(BaseModel):
    """Goal Association binding from one Core progress candidate to canonical Goals."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    goal_ids: list[str] = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator("candidate_id", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("goal_ids must be a list")
        return list(dict.fromkeys(
            normalized
            for item in value
            if (normalized := " ".join(str(item or "").strip().split()))
        ))


class GoalAssociationResolution(BaseModel):
    """Advisory result for continuity-before-creation on one user turn."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    turn_id: str = Field(min_length=1)
    associations: list[GoalAssociation] = Field(default_factory=list)
    new_goals: list[SemanticGoal] = Field(default_factory=list)
    referent_updates: list[DiscourseReferentUpdate] = Field(default_factory=list)
    resolved_references: list[ResolvedDiscourseReference] = Field(default_factory=list)
    progress_bindings: list[GoalProgressBinding] = Field(default_factory=list)
    clarification: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "clarification", "reason_summary", mode="before")
    @classmethod
    def normalize_resolution_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("metadata")
    @classmethod
    def reject_resolution_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "GoalAssociationResolution":
        existing_targets = {
            goal_id
            for association in self.associations
            if association.relationship != "new"
            for goal_id in association.target_goal_ids
        }
        new_ids = [goal.goal_id for goal in self.new_goals if goal.goal_id]
        if len(new_ids) != len(set(new_ids)):
            raise ValueError("new_goals goal_id values must be unique")
        if existing_targets.intersection(new_ids):
            raise ValueError("new_goals must not reuse target existing goal IDs")
        new_id_set = set(new_ids)
        superseded_ids = {
            goal_id
            for goal in self.new_goals
            for goal_id in goal.supersedes_goal_ids
        }
        if superseded_ids.intersection(new_id_set):
            raise ValueError("new Goals may supersede only retained prior Goal IDs")
        if superseded_ids.intersection(existing_targets):
            raise ValueError(
                "a retained Goal cannot be both associated and superseded in one resolution"
            )
        binding_ids = [item.candidate_id for item in self.progress_bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("progress_bindings candidate_id values must be unique")
        canonical_ids = existing_targets | set(new_ids)
        for binding in self.progress_bindings:
            unknown = set(binding.goal_ids) - canonical_ids
            if unknown:
                raise ValueError(
                    "progress binding references non-canonical Goal IDs: "
                    + ", ".join(sorted(unknown))
                )
        if self.clarification and (
            self.new_goals
            or self.associations
            or self.referent_updates
            or self.resolved_references
            or self.progress_bindings
        ):
            raise ValueError(
                "clarification result must not also propose goal or discourse changes"
            )
        if (
            not self.clarification
            and not self.new_goals
            and not self.associations
            and not self.referent_updates
        ):
            raise ValueError(
                "resolution must contain associations, new_goals, referent_updates, or clarification"
            )
        return self

    def prompt_projection(self) -> dict[str, Any]:
        """Return the closed semantic projection permitted in later prompts.

        Diagnostic metadata is deliberately excluded at every nested level.
        New Goal metadata keeps only the typed responsibility classification
        consumed by planner contracts. The final byte ceiling is a fail-closed
        guard against accidental prompt-state growth, not a semantic compactor.
        """

        associations = [
            item.model_dump(mode="json", exclude={"metadata"}, exclude_none=True)
            for item in self.associations
        ]
        new_goals: list[dict[str, Any]] = []
        for goal in self.new_goals:
            payload = goal.model_dump(
                mode="json",
                exclude={"metadata"},
                exclude_none=True,
            )
            metadata = goal.metadata or {}
            projected_metadata = {
                key: metadata[key]
                for key in (
                    "responsibility_kind",
                    "execution_lane",
                    "output_mode",
                    "provider_required",
                    "media_operation",
                )
                if key in metadata
            }
            if projected_metadata:
                payload["metadata"] = projected_metadata
            new_goals.append(payload)
        referent_updates: list[dict[str, Any]] = []
        for update in self.referent_updates:
            payload = update.model_dump(
                mode="json",
                exclude={"referent"},
                exclude_none=True,
            )
            if update.referent is not None:
                payload["referent"] = update.referent.model_dump(
                    mode="json",
                    exclude={"metadata"},
                    exclude_none=True,
                )
            referent_updates.append(payload)
        projection = {
            "schema_version": self.schema_version,
            "turn_id": self.turn_id,
            "associations": associations,
            "new_goals": new_goals,
            "referent_updates": referent_updates,
            "resolved_references": [
                item.model_dump(mode="json", exclude_none=True)
                for item in self.resolved_references
            ],
            "progress_bindings": [
                item.model_dump(mode="json", exclude_none=True)
                for item in self.progress_bindings
            ],
            "clarification": self.clarification,
            "confidence": self.confidence,
            "reason_summary": self.reason_summary,
        }
        serialized = json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(serialized) > 65_536:
            raise ValueError(
                "Goal Association prompt projection exceeds 65536 UTF-8 bytes"
            )
        return projection
