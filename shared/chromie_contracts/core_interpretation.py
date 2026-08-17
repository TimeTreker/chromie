from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .goal import GoalRelationship
from .interaction import reject_forbidden_low_level_fields
from .semantic_task import InformationGap
from .user_turn import normalize_turn_text


_PLANNER_OWNED_BINDING_FIELDS = frozenset({
    "capability_id",
    "tool_name",
    "provider_id",
    "execution_method",
    "executable_args",
    "args",
    "actions",
    "primary_activity",
    "activity_id",
    "work_item_id",
    "plan_step_id",
    "execution_lane",
    "realization",
    "vocal_mode",
    "coordination_id",
    "execution_item_ids",
})


def _reject_planner_owned_bindings(value: Any, *, path: str = "bindings") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key or "").strip().casefold()
            if normalized in _PLANNER_OWNED_BINDING_FIELDS:
                raise ValueError(
                    f"Planner-owned field {key!r} is forbidden in responsibility {path}"
                )
            _reject_planner_owned_bindings(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_planner_owned_bindings(item, path=f"{path}[{index}]")
    return value


class CoreInterpretationUnavailable(BaseModel):
    """Typed non-semantic outcome when Goal Interpretation is unavailable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    status: Literal["interpretation_unavailable"] = "interpretation_unavailable"
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["goal_driven_cognitive_core"] = "goal_driven_cognitive_core"
    failure_class: str = Field(min_length=1, max_length=120)
    retryable: bool = True
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("turn_id", "session_id", "failure_class", "reason", mode="before")
    @classmethod
    def normalize_unavailable_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class CognitiveResponsibilityProposal(BaseModel):
    """Context-bound WHAT understood by Goal Interpretation.

    The Responsibility remains provider-neutral and contains no Activity/Work,
    Capability, provider, execution, realization, or response wording.  It does,
    however, preserve the current turn's model-authored relationship to supplied
    Goal and InformationGap context so a short clarification answer can update the
    Responsibility it actually belongs to instead of becoming an isolated turn.
    Goal Association remains the sole canonical Goal-state commit boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    local_ref: str = Field(min_length=1, max_length=80)
    outcome: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "The provider-neutral human outcome Chromie still owes. Preserve the "
            "requested answer or judgment and proposition polarity: a question about "
            "whether P is true must not be rewritten as the assertion that P is true."
        ),
    )
    bindings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Material user-semantic facts from the authoritative turn or bounded "
            "semantic context only; never runtime/session identifiers or HOW fields."
        ),
    )
    relationship: GoalRelationship = "new"
    target_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    information_gaps: list[InformationGap] = Field(default_factory=list, max_length=8)
    resolved_gap_ids: list[str] = Field(default_factory=list, max_length=8)
    completion_requires_work: bool = Field(
        default=False,
        description="Whether Chromie still owes work before this outcome is satisfied.",
    )
    completion_requires_fresh_evidence: bool = Field(
        default=False,
        description=(
            "Whether correct completion needs evidence absent from trusted context. "
            "Reasoning from facts already supplied by the user is not fresh evidence."
        ),
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("local_ref", "outcome", mode="before")
    @classmethod
    def normalize_responsibility_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("bindings")
    @classmethod
    def reject_low_level_bindings(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_forbidden_low_level_fields(value)
        _reject_planner_owned_bindings(value)
        return value

    @field_validator("target_goal_ids", "resolved_gap_ids", mode="before")
    @classmethod
    def normalize_context_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Goal and InformationGap identity fields must be arrays")
        return list(
            dict.fromkeys(
                text
                for item in value
                if (text := normalize_turn_text(str(item or "")))
            )
        )

    @model_validator(mode="after")
    def validate_evidence_requirement(self) -> "CognitiveResponsibilityProposal":
        if self.completion_requires_fresh_evidence and not self.completion_requires_work:
            raise ValueError(
                "fresh evidence requirement implies completion_requires_work"
            )
        if self.relationship == "new" and self.target_goal_ids:
            raise ValueError("relationship=new must not target an existing Goal")
        if self.relationship != "new" and not self.target_goal_ids:
            raise ValueError(
                f"relationship={self.relationship} requires target_goal_ids"
            )
        gap_ids = [item.gap_id for item in self.information_gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Responsibility InformationGap IDs must be unique")
        overlap = set(gap_ids).intersection(self.resolved_gap_ids)
        if overlap:
            raise ValueError(
                "a Responsibility cannot introduce and resolve the same InformationGap: "
                + ",".join(sorted(overlap))
            )
        return self


class CoreInterpretationResult(BaseModel):
    """Goal Interpretation result in the current architecture.

    Goal Interpretation answers WHAT the human means in the current bounded
    Context, including whether the turn creates, continues, or modifies supplied
    Goal meaning and which pending InformationGap it answers.  Fast/Deep depth may
    change how much cognition is used, but not this authority boundary.  There is
    deliberately no compatibility RouteDecision projection and no GI-authored
    response/progress Activity, Capability choice, or Goal-state commit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["goal_interpretation"] = "goal_interpretation"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = Field(default="auto", min_length=1, max_length=64)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(min_length=1)
    unresolved: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("turn_id", "session_id", "language", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

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
            if (text := normalize_turn_text(str(item or "")))
        ]

    @model_validator(mode="after")
    def validate_responsibility_refs(self) -> "CoreInterpretationResult":
        refs = [item.local_ref for item in self.responsibilities]
        if len(refs) != len(set(refs)):
            raise ValueError("Goal Interpretation responsibility local_ref values must be unique")
        return self


class CognitiveWorkRequest(BaseModel):
    """Typed WHAT→HOW handoff used by maintained cognitive work endpoints.

    This replaces RouteDecision-shaped requests in the Goal-driven runtime.  The
    request carries Goal Interpretation responsibilities explicitly; canonical
    Goal state and later Plan/Capability state remain in their own typed contracts.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sid: str | None = None
    text: str = ""
    language: str | None = None
    responsibilities: list[CognitiveResponsibilityProposal] = Field(min_length=1)
    interpretation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    interpretation_unresolved: list[str] = Field(default_factory=list, max_length=12)
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("interpretation_unresolved", mode="before")
    @classmethod
    def normalize_interpretation_unresolved(cls, value: Any) -> list[str]:
        return CoreInterpretationResult.normalize_unresolved(value)
