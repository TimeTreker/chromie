from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import CapabilityIdentityModel, reject_forbidden_low_level_fields

SocialAttentionMode = Literal["off", "report_only", "on"]
_LEGACY_SIMULATOR_ONLY_MODE = "sim" + "_only"


def normalize_social_attention_mode(
    value: Any,
    *,
    default: SocialAttentionMode = "on",
) -> SocialAttentionMode:
    """Normalize deployment input without widening the public policy contract.

    The previous simulator-scoped value migrates to ``on`` because embodiment
    selection is owned by Soridormi/provider, not Chromie's social policy.
    Unknown explicit values fail closed to ``off``.
    """

    normalized_default = (
        default if default in {"off", "report_only", "on"} else "on"
    )
    raw = str(value or "").strip().lower()
    if not raw:
        return normalized_default
    if raw == _LEGACY_SIMULATOR_ONLY_MODE:
        return "on"
    if raw in {"off", "report_only", "on"}:
        return cast(SocialAttentionMode, raw)
    return "off"


SocialAttentionEvent = Literal[
    "primary_activity_ready",
    "primary_activity_started",
]
SocialAttentionActivityKind = Literal[
    "speech",
    "body_action",
    "vocal_performance",
    "media_playback",
    "mixed",
]
SocialAttentionActivityPhase = Literal["ready", "started"]


class SocialAttentionActivityAnchor(BaseModel):
    """A real human-observable primary Activity that Social Attention may decorate.

    This anchor is deliberately downstream of cognition. Goal interpretation, Goal
    Association, planning, evidence arrival, and other internal milestones are not
    Activities and therefore cannot be used as Social Attention anchors.
    """

    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=200)
    kind: SocialAttentionActivityKind
    phase: SocialAttentionActivityPhase
    summary: str = Field(default="", max_length=500)
    goal_ids: list[str] = Field(default_factory=list, max_length=24)
    capability_ids: list[str] = Field(default_factory=list, max_length=24)

    @field_validator("activity_id", "summary", mode="before")
    @classmethod
    def normalize_activity_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("goal_ids", "capability_ids")
    @classmethod
    def normalize_activity_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                normalized.append(text)
        return normalized


class SocialAttentionRequest(BaseModel):
    """One Activity-scoped projection for optional background Social Attention.

    The request must carry a real primary human-observable Activity. Social Attention
    may decorate that Activity but never creates a Goal, selects primary work, changes
    completion semantics, or fires merely because an internal cognitive milestone
    occurred.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    session_id: str = Field(min_length=1, max_length=160)
    turn_id: str = Field(min_length=1, max_length=160)
    event: SocialAttentionEvent
    primary_activity: SocialAttentionActivityAnchor
    text: str = ""
    language: str = Field(default="auto", min_length=1, max_length=64)
    intent: str = Field(default="unknown", min_length=1, max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)

    @field_validator("session_id", "turn_id", "text", "language", "intent", mode="before")
    @classmethod
    def normalize_request_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_activity_phase(self) -> "SocialAttentionRequest":
        expected = (
            "primary_activity_ready"
            if self.primary_activity.phase == "ready"
            else "primary_activity_started"
        )
        if self.event != expected:
            raise ValueError(
                "Social Attention event must describe the supplied primary Activity phase"
            )
        return self


SocialAttentionDecision = Literal["none", "express"]
SocialAttentionTargetSource = Literal[
    "live_perception",
    "conversation_context",
    "none",
]
SocialAttentionSkillTiming = Literal["parallel"]
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


class SocialAttentionTarget(BaseModel):
    """Evidence-backed target for social-attention decoration."""

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


class SocialAttentionBehavior(CapabilityIdentityModel):
    """One optional decorative body expression selected from the live catalog."""

    args: dict[str, Any] = Field(default_factory=dict)
    timing: SocialAttentionSkillTiming = "parallel"
    social_function: str | None = None
    reason: str | None = None

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
    """Advisory model-authored Social Attention decoration plan.

    Social Attention is background cognition that may add small, non-disruptive
    body expressions around an anchored interaction. It does not author or alter
    response text, create a Goal, own completion, or become an execution lane.
    Explicit user-requested actions remain authoritative CanonicalPlan goals and
    cannot be replaced by this optional decoration plan.
    """

    model_config = ConfigDict(extra="forbid")

    behavior_domain: Literal["social_attention"] = "social_attention"
    interaction_role: SocialAttentionInteractionRole = "auxiliary_expression"
    purpose: SocialAttentionPurpose = "neutral_presence"
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
            raise ValueError("decision=none must not contain decorative body behaviors")
        if self.decision == "express" and not self.behaviors:
            raise ValueError("decision=express requires at least one decorative body behavior")
        return self
