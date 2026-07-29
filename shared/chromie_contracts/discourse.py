from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields


DiscourseScopeKind = Literal["conversation", "task", "goal"]
DiscourseReferentStatus = Literal["foreground", "background", "retired"]
DiscourseReferentOperation = Literal[
    "introduce",
    "correct",
    "focus",
    "background",
    "retire",
]
DiscourseReferenceSource = Literal[
    "discourse_referent",
    "active_goal_binding",
]


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def stable_referent_id(
    *,
    turn_id: str,
    ordinal: int,
    entity_type: str,
    canonical_value: str,
) -> str:
    normalized_turn = _normalized_text(turn_id)
    normalized_type = _normalized_text(entity_type).casefold()
    normalized_value = _normalized_text(canonical_value).casefold()
    if not normalized_turn or not normalized_type or not normalized_value:
        raise ValueError("turn_id, entity_type, and canonical_value are required")
    if ordinal < 0:
        raise ValueError("ordinal must be non-negative")
    digest = hashlib.sha256(
        f"{normalized_turn}|{ordinal}|{normalized_type}|{normalized_value}".encode(
            "utf-8"
        )
    ).hexdigest()[:20]
    return f"ref_{digest}"


class GoalEntityBinding(BaseModel):
    """One model-authored semantic parameter bound before planning begins."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    value: str = Field(min_length=1)
    referent_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("name", "entity_type", "value", "referent_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return _normalized_text(value)
        return value


class ResolvedDiscourseReference(BaseModel):
    """Explicit LLM resolution of a surface reference such as ``那边``."""

    model_config = ConfigDict(extra="forbid")

    surface_form: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    resolved_value: str = Field(min_length=1)
    source: DiscourseReferenceSource
    referent_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator(
        "surface_form",
        "entity_type",
        "resolved_value",
        "referent_id",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return _normalized_text(value)
        return value

class DiscourseReferent(BaseModel):
    """One scoped entity retained in short-term conversational focus state."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    referent_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    canonical_value: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    scope_kind: DiscourseScopeKind = "conversation"
    scope_ids: list[str] = Field(default_factory=list)
    status: DiscourseReferentStatus = "background"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_turn_id: str = Field(min_length=1)
    source_goal_ids: list[str] = Field(default_factory=list)
    supersedes_referent_ids: list[str] = Field(default_factory=list)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "referent_id",
        "entity_type",
        "canonical_value",
        "source_turn_id",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _normalized_text(value)
        return value

    @field_validator(
        "aliases",
        "scope_ids",
        "source_goal_ids",
        "supersedes_referent_ids",
        mode="before",
    )
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected a list or string")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = _normalized_text(item)
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
        return out

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class DiscourseReferentUpdate(BaseModel):
    """Validated semantic mutation proposed by Goal Association."""

    model_config = ConfigDict(extra="forbid")

    operation: DiscourseReferentOperation
    referent: DiscourseReferent | None = None
    target_referent_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_summary: str = ""

    @field_validator("target_referent_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("target_referent_ids must be a list")
        return [text for item in value if (text := _normalized_text(item))]

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _normalized_text(value)
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "DiscourseReferentUpdate":
        if self.operation in {"introduce", "correct"} and self.referent is None:
            raise ValueError(f"operation={self.operation} requires referent")
        if self.operation in {"focus", "background", "retire"} and not self.target_referent_ids:
            raise ValueError(f"operation={self.operation} requires target_referent_ids")
        if self.operation == "correct" and not self.target_referent_ids:
            raise ValueError("operation=correct requires superseded target_referent_ids")
        return self


__all__ = [
    "DiscourseReferenceSource",
    "DiscourseReferent",
    "DiscourseReferentOperation",
    "DiscourseReferentStatus",
    "DiscourseReferentUpdate",
    "DiscourseScopeKind",
    "GoalEntityBinding",
    "ResolvedDiscourseReference",
    "stable_referent_id",
]
