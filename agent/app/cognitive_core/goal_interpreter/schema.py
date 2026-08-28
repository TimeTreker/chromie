from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal


def _normalized_scalar_texts(value: Any) -> set[str]:
    if isinstance(value, str):
        normalized = " ".join(value.strip().casefold().split())
        return {normalized} if normalized else set()
    if isinstance(value, dict):
        return {
            text
            for item in value.values()
            for text in _normalized_scalar_texts(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            text
            for item in value
            for text in _normalized_scalar_texts(item)
        }
    return set()


class GoalInterpretationRequest(BaseModel):
    """Internal request for already-admitted Goal Interpretation.

    Cognitive Gateway owns admission/reflex handling before this request exists.
    Goal Interpretation receives only the immutable human turn plus bounded semantic
    context and owns only WHAT the human means.
    """

    model_config = ConfigDict(extra="forbid")

    sid: str | None = None
    text: str = Field(min_length=0, description="Already-admitted normalized user text")
    language: str | None = Field(default=None, description="Optional BCP-47 language hint")
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join((value or "").strip().split())


class GoalInterpretationDecision(BaseModel):
    """Canonical model-facing Goal Interpretation contract: WHAT only.

    Fast/Deep depth may change how much cognition is used, but never this authority.
    No route/intent label, response Activity, Work, Capability, provider, execution
    contract, or canonical lifecycle identity belongs here.
    """

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(
        min_length=1,
        description=(
            "Complete set of independently satisfiable outcomes: one item per "
            "requested observable effect, including separate concurrent embodied and "
            "authored-vocal effects. Coordination never merges effects."
        ),
    )
    unresolved: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("unresolved", mode="before")
    @classmethod
    def normalize_unresolved(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("unresolved must be an array")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @model_validator(mode="after")
    def validate_local_refs(self) -> "GoalInterpretationDecision":
        refs = [item.local_ref for item in self.responsibilities]
        if len(refs) != len(set(refs)):
            raise ValueError("responsibility local_ref values must be unique")
        bound_values = {
            value
            for item in self.responsibilities
            for value in _normalized_scalar_texts(item.bindings)
        }
        repeated_bound_values = sorted(
            text
            for text in self.unresolved
            if " ".join(text.strip().casefold().split()) in bound_values
        )
        if repeated_bound_values:
            raise ValueError(
                "already-bound semantic values are not unresolved: "
                + ",".join(repeated_bound_values)
            )
        return self
