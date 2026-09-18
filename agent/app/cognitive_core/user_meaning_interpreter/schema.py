from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty
    from chromie_contracts.user_turn import UserTurnEnvelope
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty
    from shared.chromie_contracts.user_turn import UserTurnEnvelope


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


class UserMeaningInterpretationRequest(BaseModel):
    """Internal request for already-admitted User Meaning Interpretation.

    Cognitive Gateway owns admission/reflex handling before this request exists.
    User Meaning Interpretation receives only the immutable human turn plus bounded semantic
    context and owns only WHAT the human means.
    """

    model_config = ConfigDict(extra="forbid")

    sid: str | None = None
    text: str = Field(min_length=0, description="Already-admitted normalized user text")
    language: str | None = Field(default=None, description="Optional BCP-47 language hint")
    turn_envelope: UserTurnEnvelope | None = Field(
        default=None,
        description=(
            "The immutable admitted UserTurnEnvelope referenced by User Meaning Interpretation. "
            "It is transport/source evidence, never another semantic author."
        ),
    )
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join((value or "").strip().split())

    @model_validator(mode="after")
    def validate_turn_envelope_reference(self) -> "UserMeaningInterpretationRequest":
        envelope = self.turn_envelope
        if envelope is None:
            return self
        if envelope.admission not in {"admit", "reflex_and_admit"}:
            raise ValueError("User Meaning Interpretation requires an admitted UserTurnEnvelope")
        if envelope.normalized_input.text != self.text:
            raise ValueError("User Meaning Interpretation text does not match UserTurnEnvelope")
        if self.sid is not None and str(self.sid).strip() and self.sid != envelope.session_id:
            raise ValueError("User Meaning Interpretation session does not match UserTurnEnvelope")
        if (
            self.language is not None
            and str(self.language).strip()
            and self.language != envelope.normalized_input.language
        ):
            raise ValueError("User Meaning Interpretation language does not match UserTurnEnvelope")
        return self


class UserMeaningInterpretationDecision(BaseModel):
    """Canonical model-facing User Meaning Interpretation contract: WHAT only.

    Fast/Deep depth may change how much cognition is used, but never this authority.
    No route/intent label, response Activity, Work, Capability, provider, execution
    contract, or canonical lifecycle identity belongs here.
    """

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0, strict=True)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(
        min_length=1, max_length=12,
        description="Complete natural-language intentions, preserving all details and relations.",
    )
    meaning_uncertainties: list[UserMeaningUncertainty] = Field(
        default_factory=list, max_length=12,
        description=(
            "Genuine semantic uncertainty remaining after bounded conversation, "
            "situation, activated-memory and continuity context have been used. "
            "These are not clarification instructions."
        ),
    )

    @model_validator(mode="after")
    def validate_local_refs(self) -> "UserMeaningInterpretationDecision":
        refs = [item.local_ref for item in self.responsibilities]
        if len(refs) != len(set(refs)):
            raise ValueError("responsibility local_ref values must be unique")
        bound_values = {
            value
            for item in self.responsibilities
            for value in _normalized_scalar_texts(item.bindings)
        }
        uncertainty_refs = [item.local_ref for item in self.meaning_uncertainties]
        if len(uncertainty_refs) != len(set(uncertainty_refs)):
            raise ValueError("meaning uncertainty local_ref values must be unique")
        known_refs = set(refs)
        scope_by_ref = {
            item.local_ref: item.continuity_scope for item in self.responsibilities
        }
        repeated_bound_values: list[str] = []
        for uncertainty in self.meaning_uncertainties:
            unknown_refs = set(uncertainty.responsibility_refs) - known_refs
            if unknown_refs:
                raise ValueError(
                    "meaning uncertainty references unknown Responsibilities: "
                    + ",".join(sorted(unknown_refs))
                )
            scopes = {scope_by_ref[ref] for ref in uncertainty.responsibility_refs}
            if len(scopes) != 1:
                raise ValueError(
                    "one meaning uncertainty cannot span turn-local and goal-scoped "
                    "Responsibilities; UMI must keep those semantic uncertainties separate"
                )
            normalized = " ".join(uncertainty.description.strip().casefold().split())
            if normalized in bound_values:
                repeated_bound_values.append(uncertainty.description)
        if repeated_bound_values:
            raise ValueError(
                "already-bound semantic values are not uncertain: "
                + ",".join(sorted(repeated_bound_values))
            )
        return self
