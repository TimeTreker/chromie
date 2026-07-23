from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .reflex import ReflexOutcome


UserTurnChannel = Literal["voice", "text", "trusted_event"]
InputQualitySource = Literal["asr_final", "text", "trusted_event", "unknown"]
AttentionDisposition = Literal["admit", "suppress"]
ContextFreshness = Literal["current", "stale", "unknown"]
TurnAdmissionDisposition = Literal[
    "admit",
    "suppress",
    "unusable",
    "reflex_only",
    "reflex_and_admit",
]


def normalize_turn_text(value: str) -> str:
    """Apply only transport-safe whitespace normalization."""

    return " ".join((value or "").strip().split())


class OriginalTurnInput(BaseModel):
    """Immutable input evidence exactly as received by the Gateway."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(max_length=65536)


class NormalizedTurnInput(BaseModel):
    """Transport-normalized input without semantic reinterpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(max_length=65536)
    language: str = Field(default="auto", min_length=1, max_length=64)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return str(value or "auto").strip() or "auto"


class InputQualityEvidence(BaseModel):
    """Bounded evidence about whether the received input is usable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: InputQualitySource = "unknown"
    usable: bool = True
    asr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class AttentionFinding(BaseModel):
    """A bounded admission finding, never a normal intent decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: AttentionDisposition
    source: str = Field(min_length=1, max_length=120)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)

    @field_validator("source", "reason", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class ContextReference(BaseModel):
    """Source-attributed reference to a bounded immutable context snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_type: str = Field(min_length=1, max_length=120)
    reference_id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=160)
    captured_at: datetime
    freshness: ContextFreshness = "unknown"
    age_ms: int | None = Field(default=None, ge=0)

    @field_validator("context_type", "reference_id", "source", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_freshness(self) -> "ContextReference":
        if self.freshness == "current" and self.age_ms is None:
            raise ValueError("current context references require age_ms")
        return self


class UserTurnEnvelope(BaseModel):
    """Canonical, evidence-preserving input to one Cognitive Core turn.

    The contract intentionally has no ordinary intent, route, goal, capability,
    plan, authorization, execution, or response fields. Compatibility adapters
    may carry those objects alongside this envelope, but never inside it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    channel: UserTurnChannel
    received_at: datetime
    original_input: OriginalTurnInput
    normalized_input: NormalizedTurnInput
    quality: InputQualityEvidence
    reflex: ReflexOutcome
    attention: AttentionFinding
    context_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    admission: TurnAdmissionDisposition

    @field_validator("turn_id", "session_id", "conversation_id", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_gateway_invariants(self) -> "UserTurnEnvelope":
        expected_normalized = normalize_turn_text(self.original_input.text)
        if self.normalized_input.text != expected_normalized:
            raise ValueError(
                "normalized input may change whitespace only; semantic "
                "substitution is forbidden"
            )

        reference_ids = [item.reference_id for item in self.context_refs]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("context reference IDs must be unique")

        if not self.quality.usable:
            if self.admission != "unusable":
                raise ValueError("unusable input requires admission=unusable")
            if self.attention.disposition != "suppress":
                raise ValueError("unusable input must be suppressed")
        elif self.admission == "unusable":
            raise ValueError("usable input cannot use admission=unusable")

        if self.admission == "suppress":
            if self.attention.disposition != "suppress":
                raise ValueError("suppressed input requires a suppress finding")
        elif self.attention.disposition == "suppress":
            raise ValueError("a suppress finding requires admission=suppress")

        if self.reflex.action == "interrupt":
            if self.admission not in {"reflex_only", "reflex_and_admit"}:
                raise ValueError(
                    "interrupt reflexes require reflex_only or reflex_and_admit"
                )
        elif self.reflex.action == "ignore":
            if self.admission != "suppress":
                raise ValueError("ignore reflexes require admission=suppress")
        elif self.admission in {"reflex_only", "reflex_and_admit"}:
            raise ValueError(
                "reflex_only and reflex_and_admit require an interrupt reflex"
            )

        if self.admission in {"admit", "reflex_and_admit"}:
            if self.attention.disposition != "admit":
                raise ValueError("admitted input requires an admit finding")
            if not self.quality.usable:
                raise ValueError("unusable input cannot be admitted")

        return self


__all__ = [
    "AttentionDisposition",
    "AttentionFinding",
    "ContextFreshness",
    "ContextReference",
    "InputQualityEvidence",
    "InputQualitySource",
    "NormalizedTurnInput",
    "OriginalTurnInput",
    "TurnAdmissionDisposition",
    "UserTurnChannel",
    "UserTurnEnvelope",
    "normalize_turn_text",
]
