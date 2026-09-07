from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .situation import SituationEpistemicStatus, SituationSourceRef

SocialPresenceState = Literal["present", "entered", "left"]
SocialIdentityStatus = Literal["resolved", "candidate", "unknown"]


class TrustedPersonPresence(BaseModel):
    """One source-owned person/presence observation.

    This is perception truth only. It does not imply relationship, permission,
    social relevance, or a recommended response.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str = Field(min_length=1, max_length=200)
    presence: SocialPresenceState
    identity_status: SocialIdentityStatus = "unknown"
    identity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    epistemic_status: SituationEpistemicStatus = "provisional"
    source_refs: list[str] = Field(min_length=1, max_length=8)

    @field_validator("subject_ref", mode="before")
    @classmethod
    def normalize_subject(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("source_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("source_refs must be an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out


class TrustedSocialPerceptionObservation(BaseModel):
    """Source-neutral trusted person/presence/audience ingress.

    A concrete camera/principal/presence adapter owns sensing and identity resolution
    before constructing this object. Runtime only validates provenance and projects it
    into Situation; it never infers who somebody is or how Chromie should react.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=160)
    source_revision: int = Field(ge=1)
    source_refs: list[SituationSourceRef] = Field(min_length=1, max_length=16)
    people: list[TrustedPersonPresence] = Field(min_length=1, max_length=16)
    audience_refs: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("observation_id", "source_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("audience_refs", mode="before")
    @classmethod
    def normalize_audience(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("audience_refs must be an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_provenance(self) -> "TrustedSocialPerceptionObservation":
        refs = {item.reference_id for item in self.source_refs}
        if any(item.kind != "perception" for item in self.source_refs):
            raise ValueError("trusted social perception source refs must be perception refs")
        if any(item.owner != self.source_id for item in self.source_refs):
            raise ValueError("trusted social perception source owner must match source_id")
        for person in self.people:
            if not set(person.source_refs).issubset(refs):
                raise ValueError("person presence source refs must exist in observation")
        present = {item.subject_ref for item in self.people if item.presence != "left"}
        external_audience = {item for item in self.audience_refs if item != "self:chromie"}
        if not external_audience.issubset(present):
            raise ValueError("audience refs must be present observed subjects or self:chromie")
        return self

class TrustedSocialFeedbackSignal(BaseModel):
    """One source-owned social/interaction signal after Chromie's observable activity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str = Field(min_length=1, max_length=200)
    relation: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=240)
    epistemic_status: SituationEpistemicStatus = "provisional"
    source_refs: list[str] = Field(min_length=1, max_length=8)

    @field_validator("subject_ref", "relation", "value", mode="before")
    @classmethod
    def normalize_signal_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("source_refs", mode="before")
    @classmethod
    def normalize_signal_refs(cls, value: Any) -> list[str]:
        return TrustedPersonPresence.normalize_refs(value)


class TrustedSocialFeedbackObservation(BaseModel):
    """Trusted source feedback tied to one or more actually observable Chromie activities.

    The source reports signals only; it does not classify them as approval, anger,
    rejection, or a recommended conversational response unless that meaning is itself
    source-owned evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=160)
    source_revision: int = Field(ge=1)
    source_refs: list[SituationSourceRef] = Field(min_length=1, max_length=16)
    reacts_to_activity_ids: list[str] = Field(min_length=1, max_length=8)
    signals: list[TrustedSocialFeedbackSignal] = Field(min_length=1, max_length=16)
    audience_refs: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("observation_id", "source_id", mode="before")
    @classmethod
    def normalize_feedback_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("reacts_to_activity_ids", "audience_refs", mode="before")
    @classmethod
    def normalize_feedback_lists(cls, value: Any) -> list[str]:
        return TrustedSocialPerceptionObservation.normalize_audience(value)

    @model_validator(mode="after")
    def validate_feedback_provenance(self) -> "TrustedSocialFeedbackObservation":
        refs = {item.reference_id for item in self.source_refs}
        if any(item.owner != self.source_id for item in self.source_refs):
            raise ValueError("social feedback source owner must match source_id")
        for signal in self.signals:
            if not set(signal.source_refs).issubset(refs):
                raise ValueError("social feedback signal refs must exist in observation")
        return self
