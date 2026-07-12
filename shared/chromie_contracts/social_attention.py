from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields

SocialAttentionDecision = Literal["none", "express"]
SocialAttentionTargetSource = Literal[
    "live_perception",
    "conversation_context",
    "installation_calibration",
    "none",
]
SocialAttentionSkillTiming = Literal["parallel", "sequential"]


class SocialAttentionTarget(BaseModel):
    """Evidence-backed target for optional social attention behavior."""

    model_config = ConfigDict(extra="forbid")

    target_ref: str = "none"
    source: SocialAttentionTargetSource = "none"
    relative_direction: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_ref")
    @classmethod
    def normalize_target_ref(cls, value: str) -> str:
        return " ".join((value or "none").strip().split()) or "none"

    @field_validator("relative_direction")
    @classmethod
    def normalize_relative_direction(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SocialAttentionBehavior(BaseModel):
    """One optional named-skill behavior coordinated with spoken interaction."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: SocialAttentionSkillTiming = "parallel"
    reason: str | None = None

    @field_validator("skill_id")
    @classmethod
    def normalize_skill_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("skill_id must not be empty")
        return normalized

    @field_validator("args")
    @classmethod
    def reject_low_level_args(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None


class SocialAttentionPlan(BaseModel):
    """Advisory model-authored plan for subtle nonverbal attention behavior."""

    model_config = ConfigDict(extra="forbid")

    decision: SocialAttentionDecision = "none"
    target: SocialAttentionTarget = Field(default_factory=SocialAttentionTarget)
    behaviors: list[SocialAttentionBehavior] = Field(default_factory=list, max_length=3)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> "SocialAttentionPlan":
        if self.decision == "none" and self.behaviors:
            raise ValueError("decision=none must not contain behaviors")
        if self.decision == "express" and not self.behaviors:
            raise ValueError("decision=express requires at least one behavior")
        return self
