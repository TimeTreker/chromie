from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core_interpretation import CognitiveResponsibilityProposal
from .text import normalize_whitespace


CognitiveActivationAuthority = Literal["planner", "social_cognition"]
CognitiveActivationTrigger = Literal[
    "execution_outcome",
    "post_execution",
    "provider_state",
    "restored_provider_state",
    "time_condition",
    "goal_cancellation",
    "situation_revision",
]


class CognitiveActivationContext(BaseModel):
    """Bounded trusted state asking whether existing cognition should run now.

    The Host authors only provenance and the list of authorities that are structurally
    legal for this ingress.  The model decides whether any of those existing cognitive
    owners are useful now.  This contract cannot author Goal meaning, Work, wording,
    Capability selection, execution, or completion truth.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    trigger: CognitiveActivationTrigger
    allowed_authorities: list[CognitiveActivationAuthority] = Field(
        min_length=1, max_length=2
    )
    goal_ids: list[str] = Field(default_factory=list, max_length=8)
    responsibility_refs: list[str] = Field(default_factory=list, max_length=12)
    source_refs: list[str] = Field(default_factory=list, max_length=24)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(
        default_factory=list, max_length=12
    )
    state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", mode="before")
    @classmethod
    def normalize_request_id(cls, value: Any) -> str:
        return normalize_whitespace(str(value or ""))

    @field_validator(
        "allowed_authorities",
        "goal_ids",
        "responsibility_refs",
        "source_refs",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("cognitive activation identity fields must be arrays")
        result: list[str] = []
        for item in value:
            text = normalize_whitespace(str(item or ""))
            if text and text not in result:
                result.append(text)
        return result

    @model_validator(mode="after")
    def validate_scope(self) -> "CognitiveActivationContext":
        if len(self.allowed_authorities) != len(set(self.allowed_authorities)):
            raise ValueError("cognitive activation authorities must be unique")
        known_refs = {item.local_ref for item in self.responsibilities}
        if self.responsibility_refs and not set(self.responsibility_refs).issubset(
            known_refs
        ):
            raise ValueError(
                "cognitive activation responsibility_refs must name supplied Responsibilities"
            )
        if self.trigger == "situation_revision" and not self.goal_ids and not self.source_refs:
            raise ValueError("Goal-free Situation activation requires trusted source_refs")
        if self.trigger != "situation_revision" and not (
            self.goal_ids or self.source_refs
        ):
            raise ValueError(
                "internal cognitive activation requires Goal or source provenance"
            )
        return self


class CognitiveActivationSelection(BaseModel):
    """One model-authored request to wake an already-defined cognitive owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority: CognitiveActivationAuthority
    goal_ids: list[str] = Field(default_factory=list, max_length=8)
    responsibility_refs: list[str] = Field(default_factory=list, max_length=12)
    source_refs: list[str] = Field(default_factory=list, max_length=24)
    reason_summary: str = Field(default="", max_length=320)

    @field_validator("goal_ids", "responsibility_refs", "source_refs", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return CognitiveActivationContext.normalize_lists(value)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return normalize_whitespace(str(value or ""))


class CognitiveActivationDecision(BaseModel):
    """Model decision over which existing cognitive owners should run now."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cognitive_requests: list[CognitiveActivationSelection] = Field(
        default_factory=list, max_length=2
    )
    confidence: float = Field(ge=0.0, le=1.0, strict=True)
    reason_summary: str = Field(default="", max_length=320)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return normalize_whitespace(str(value or ""))

    def validate_request(
        self, request: CognitiveActivationContext
    ) -> "CognitiveActivationDecision":
        authorities = [item.authority for item in self.cognitive_requests]
        if len(authorities) != len(set(authorities)):
            raise ValueError("activation may request each cognitive authority at most once")
        allowed = set(request.allowed_authorities)
        known_goals = set(request.goal_ids)
        known_responsibilities = set(request.responsibility_refs)
        known_sources = set(request.source_refs)
        for item in self.cognitive_requests:
            if item.authority not in allowed:
                raise ValueError(
                    f"activation requested unavailable authority: {item.authority}"
                )
            if not set(item.goal_ids).issubset(known_goals):
                raise ValueError("activation widened Goal scope")
            if not set(item.responsibility_refs).issubset(known_responsibilities):
                raise ValueError("activation widened Responsibility scope")
            if not set(item.source_refs).issubset(known_sources):
                raise ValueError("activation widened source scope")
            if request.goal_ids and set(item.goal_ids) != known_goals:
                raise ValueError("Goal-bound activation must preserve exact Goal scope")
            if request.responsibility_refs and set(item.responsibility_refs) != known_responsibilities:
                raise ValueError(
                    "activation must preserve exact Responsibility scope"
                )
            if request.source_refs and not item.source_refs:
                raise ValueError("activation request must retain source provenance")
        return self
