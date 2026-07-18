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
SocialAttentionInteractionRole = Literal["auxiliary_expression"]
SocialAttentionPurpose = Literal[
    "acknowledge",
    "listening",
    "engagement",
    "empathy",
    "turn_taking",
    "deference",
    "neutral_presence",
    "other",
]
SocialAttentionSpeechMode = Literal["none", "adapt"]
SocialAttentionSpeechStyle = Literal[
    "neutral",
    "brief",
    "warm",
    "calm",
    "encouraging",
    "empathetic",
    "playful",
]
SocialAttentionSpeechPacing = Literal["normal", "slower", "faster"]


class SocialAttentionTarget(BaseModel):
    """Evidence-backed target for social-attention expression."""

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


class SocialAttentionSpeechExpression(BaseModel):
    """Model-authored language-expression guidance coordinated with ResponsePlan.

    This object does not contain a second response or override task semantics.
    The Response Composer authors the actual ResponsePlan text and uses this
    guidance to choose tone and pacing for the current scene.
    """

    model_config = ConfigDict(extra="forbid")

    mode: SocialAttentionSpeechMode = "none"
    style: SocialAttentionSpeechStyle = "neutral"
    pacing: SocialAttentionSpeechPacing = "normal"
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None

    @model_validator(mode="after")
    def validate_mode(self) -> "SocialAttentionSpeechExpression":
        if self.mode == "none" and (
            self.style != "neutral" or self.pacing != "normal" or self.reason
        ):
            raise ValueError(
                "speech_expression mode=none must use neutral style, normal pacing, and no reason"
            )
        return self


class SocialAttentionBehavior(BaseModel):
    """One model-authored body expression selected from the live catalog."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: SocialAttentionSkillTiming = "parallel"
    social_function: str | None = None
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

    @field_validator("social_function", "reason")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None


class SocialAttentionPlan(BaseModel):
    """Advisory model-authored social-attention expression plan.

    Social attention is a high-level behavior domain, not a fixed skill. The
    model may adapt language expression, select one or more context-appropriate
    body behaviors from the supplied catalog, select both, or choose stillness.
    This contract is only for auxiliary expression; explicit user-requested
    actions remain authoritative CanonicalPlan goals and cannot be replaced by
    this optional plan.
    """

    model_config = ConfigDict(extra="forbid")

    behavior_domain: Literal["social_attention"] = "social_attention"
    interaction_role: SocialAttentionInteractionRole = "auxiliary_expression"
    purpose: SocialAttentionPurpose = "neutral_presence"
    decision: SocialAttentionDecision = "none"
    target: SocialAttentionTarget = Field(default_factory=SocialAttentionTarget)
    speech_expression: SocialAttentionSpeechExpression = Field(
        default_factory=SocialAttentionSpeechExpression
    )
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
        has_speech_expression = self.speech_expression.mode == "adapt"
        if self.decision == "none" and (self.behaviors or has_speech_expression):
            raise ValueError(
                "decision=none must not contain body behaviors or adapted speech expression"
            )
        if self.decision == "express" and not (self.behaviors or has_speech_expression):
            raise ValueError(
                "decision=express requires at least one body behavior or adapted speech expression"
            )
        return self
