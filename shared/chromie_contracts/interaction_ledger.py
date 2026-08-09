from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields


InteractionEventOwner = Literal[
    "cognitive_runtime",
    "playback_delivery",
    "trusted_capability_runtime",
    "execution_closure",
]
InteractionEventLane = Literal[
    "cognition",
    "speaking",
    "activity",
    "social_attention",
]
InteractionEventType = Literal[
    "goal_associated",
    "plan_resolved",
    "speech_scheduled",
    "speech_playback_started",
    "speech_not_delivered",
    "speaking_action_committed",
    "speaking_action_completed",
    "speaking_action_partial",
    "speaking_action_failed",
    "speaking_action_cancelled",
    "speaking_action_timed_out",
    "speaking_action_refused",
    "speaking_action_not_run",
    "activity_committed",
    "activity_completed",
    "activity_partial",
    "activity_failed",
    "activity_cancelled",
    "activity_timed_out",
    "activity_refused",
    "activity_not_run",
    "social_action_committed",
    "social_action_completed",
    "social_action_failed",
    "social_action_cancelled",
    "social_action_timed_out",
    "social_action_refused",
    "social_action_not_run",
]


def _normalize_text(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("expected a string or list of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


class InteractionLedgerEvent(BaseModel):
    """One immutable, owner-authored fact about Chromie's current interaction.

    The event transports an existing owner's observation into later cognition.
    It never upgrades a proposal, scheduled utterance, or provider postcondition
    into execution completion evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    event_id: str = Field(min_length=1, max_length=160)
    sequence: int = Field(ge=1)
    session_id: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(default="", max_length=200)
    interaction_id: str = Field(default="", max_length=200)
    owner: InteractionEventOwner
    lane: InteractionEventLane
    event_type: InteractionEventType
    state: str = Field(min_length=1, max_length=80)
    goal_ids: list[str] = Field(default_factory=list, max_length=16)
    canonical_plan_id: str = Field(default="", max_length=200)
    canonical_plan_fingerprint: str = Field(default="", max_length=160)
    subject_id: str = Field(min_length=1, max_length=240)
    capability_id: str = Field(default="", max_length=200)
    speech_act: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=1200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "event_id",
        "session_id",
        "turn_id",
        "interaction_id",
        "state",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        "subject_id",
        "capability_id",
        "speech_act",
        "text",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return _normalize_text(value)

    @field_validator("goal_ids", "evidence_refs", mode="before")
    @classmethod
    def normalize_text_lists(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_owner_boundary(self) -> "InteractionLedgerEvent":
        if self.event_type.startswith("speech_"):
            if self.owner != "playback_delivery" or self.lane != "speaking":
                raise ValueError(
                    "speech events must be owned by playback_delivery in the "
                    "speaking lane"
                )
        elif self.event_type.startswith("speaking_action_"):
            expected_owner = (
                "trusted_capability_runtime"
                if self.event_type == "speaking_action_committed"
                else "execution_closure"
            )
            if self.owner != expected_owner or self.lane != "speaking":
                raise ValueError(
                    "provider-backed speaking events must retain their trusted "
                    "runtime owner"
                )
        elif self.event_type.startswith("activity_"):
            expected_owner = (
                "trusted_capability_runtime"
                if self.event_type == "activity_committed"
                else "execution_closure"
            )
            if self.owner != expected_owner or self.lane != "activity":
                raise ValueError(
                    "activity events must retain their trusted runtime owner"
                )
        elif self.event_type.startswith("social_action_"):
            if (
                self.owner != "trusted_capability_runtime"
                or self.lane != "social_attention"
            ):
                raise ValueError(
                    "social action events must be owned by the trusted "
                    "capability runtime"
                )
        elif (
            self.owner != "cognitive_runtime"
            or self.lane != "cognition"
        ):
            raise ValueError(
                "goal and plan events must be owned by cognitive_runtime"
            )

        terminal_activity = (
            self.event_type.startswith("activity_")
            and self.event_type != "activity_committed"
        ) or (
            self.event_type.startswith("speaking_action_")
            and self.event_type != "speaking_action_committed"
        )
        if terminal_activity and not self.evidence_refs:
            raise ValueError(
                "terminal activity events require trusted execution evidence"
            )
        if self.canonical_plan_fingerprint and not self.canonical_plan_id:
            raise ValueError(
                "canonical plan fingerprint requires canonical_plan_id"
            )
        return self


class InteractionContextProjection(BaseModel):
    """Bounded Goal-scoped projection supplied to later model stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    session_id: str = Field(min_length=1)
    goal_ids: list[str] = Field(default_factory=list)
    event_count: int = Field(default=0, ge=0)
    events: list[dict[str, Any]] = Field(default_factory=list)
    already_spoken: list[dict[str, Any]] = Field(default_factory=list)
    pending_speech: list[dict[str, Any]] = Field(default_factory=list)
    activity: list[dict[str, Any]] = Field(default_factory=list)
    social_actions: list[dict[str, Any]] = Field(default_factory=list)
    goal_history: list[dict[str, Any]] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_text_list(value)

    @field_validator(
        "events",
        "already_spoken",
        "pending_speech",
        "activity",
        "social_actions",
        "goal_history",
        "unresolved",
    )
    @classmethod
    def reject_low_level_projection(
        cls,
        value: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [reject_forbidden_low_level_fields(dict(item)) for item in value]


__all__ = [
    "InteractionContextProjection",
    "InteractionEventLane",
    "InteractionEventOwner",
    "InteractionEventType",
    "InteractionLedgerEvent",
]
