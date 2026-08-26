from __future__ import annotations

from typing import Any, Literal

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


class _GoalInterpretationCoverageItemBase(BaseModel):
    """Shared source-grounded fields in the GI atomic-Responsibility audit.

    The coverage model owns the semantic classification.  Trusted code only
    checks exact source provenance, candidate references, one-owner cardinality,
    and output-mode agreement; it never discovers effects from user wording.
    """

    model_config = ConfigDict(extra="forbid")

    source_excerpt: str = Field(min_length=1, max_length=500)
    coverage: Literal[
        "covered",
        "missing",
        "clarification_required",
        "representation_mismatch",
    ]
    responsibility_refs: list[str] = Field(max_length=8)

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def normalize_source_excerpt(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("responsibility_refs must be an array")
        return list(
            dict.fromkeys(
                text
                for item in value
                if (text := " ".join(str(item or "").strip().split()))
            )
        )

    @model_validator(mode="after")
    def validate_missing_coverage(self) -> "_GoalInterpretationCoverageItemBase":
        if self.coverage == "missing" and self.responsibility_refs:
            raise ValueError("missing coverage must not cite a Responsibility")
        return self


class GoalInterpretationResponsibilityCoverageItem(
    _GoalInterpretationCoverageItemBase
):
    """One independently audited positive outcome and its candidate owner."""

    role: Literal["responsibility"]
    audit_ref: str = Field(
        default="",
        max_length=24,
        description=(
            "Turn-local audit item identity used only to type relations among "
            "source outcomes; never a Goal or candidate Responsibility identity."
        ),
    )
    independently_satisfiable: Literal[True]
    required_output_mode: Literal[
        "speech",
        "styled_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
        "body_action",
        "media_playback",
        "information",
        "stateful_effect",
    ] = Field(
        description=(
            "Exact provider-neutral WHAT mode for this positive outcome. "
            "Singing or a song is singing; ordinary conversational wording is "
            "speech; locomotion, gaze, blink, gesture, and posture are body_action."
        )
    )


class GoalInterpretationSupportingCoverageItem(
    _GoalInterpretationCoverageItemBase
):
    """A non-outcome source fragment that cannot own a Responsibility mode."""

    role: Literal["constraint", "context", "framing"]
    independently_satisfiable: Literal[False]
    required_output_mode: Literal["none"] = Field(
        description=(
            "Always none: constraints, context, and framing do not inherit an "
            "outcome's output mode."
        )
    )
    relation_kind: Literal["none", "ordered", "parallel"] = Field(
        default="none",
        description=(
            "Typed meaning of a coordination constraint. ordered lists candidate "
            "Responsibility refs in source order; parallel lists the complete set "
            "of outcomes requested concurrently. Other modifiers use none."
        ),
    )
    related_audit_refs: list[str] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Exact audit_ref values of the positive source outcomes this constraint "
            "modifies. Ordered relations preserve source order; parallel relations "
            "list concurrent membership; ordinary modifiers cite their exact owner."
        ),
    )

    @field_validator("related_audit_refs", mode="before")
    @classmethod
    def normalize_related_audit_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("related_audit_refs must be an array")
        return list(
            dict.fromkeys(
                text
                for item in value
                if (text := " ".join(str(item or "").strip().split()))
            )
        )

    @model_validator(mode="after")
    def validate_supporting_shape(
        self,
    ) -> "GoalInterpretationSupportingCoverageItem":
        if self.role in {"context", "framing"}:
            if (
                self.coverage != "covered"
                or self.responsibility_refs
                or self.relation_kind != "none"
                or self.related_audit_refs
            ):
                raise ValueError(
                    "context and framing are acknowledged without Responsibility ownership"
                )
        if self.relation_kind != "none" and self.role != "constraint":
            raise ValueError("typed coordination relations must be constraints")
        return self


class GoalInterpretationCoverageCertificate(BaseModel):
    """Ephemeral, independent proof over one GI Responsibility candidate set."""

    model_config = ConfigDict(extra="forbid")

    responsibility_items: list[GoalInterpretationResponsibilityCoverageItem] = Field(
        min_length=1,
        max_length=12,
        description="Positive outcome items only; every item has role=responsibility.",
    )
    supporting_items: list[GoalInterpretationSupportingCoverageItem] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Constraint, context, and framing items only; required_output_mode is none."
        ),
    )
    reason_summary: str = Field(min_length=1, max_length=1200)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason_summary(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())
