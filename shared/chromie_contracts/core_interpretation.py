from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .goal import GoalRelationship
from .interaction import reject_forbidden_low_level_fields
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

    @field_validator("turn_id", "session_id", "failure_class", mode="before")
    @classmethod
    def normalize_unavailable_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_bounded_reason(cls, value: str) -> str:
        # A nested validation report can be large. Keep the public failure DTO
        # bounded so the intended HTTP 503 path cannot become an unrelated 500.
        return normalize_turn_text(str(value or ""))[:500]


class CognitiveResponsibilityProposal(BaseModel):
    """Context-bound WHAT understood by Goal Interpretation.

    The Responsibility remains provider-neutral and contains no Activity/Work,
    Capability, provider, execution, realization, or response wording.  It does,
    however, preserve the current turn's model-authored relationship to supplied
    Goal context so a short clarification answer can update the Responsibility it
    actually belongs to instead of becoming an isolated turn. Planning
    InformationGaps, their blocking state, and their resolution strategy belong to
    Planner. Goal Association remains the sole canonical Goal-state commit boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    local_ref: str = Field(min_length=1, max_length=80)
    outcome: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Exactly one independently satisfiable provider-neutral human outcome "
            "Chromie still owes. Never combine two requested positive effects merely "
            "because the user coordinates them with while, simultaneously, at the "
            "same time, a conjunction, or an equivalent construction; each effect "
            "that can be independently accepted or rejected requires its own sibling "
            "Responsibility. Preserve the "
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
    output_mode: Literal[
        "unspecified",
        "speech",
        "styled_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
        "body_action",
        "media_playback",
        "capability_work",
        "other",
    ] = Field(
        default="unspecified",
        description=(
            "Provider-neutral completion category for this one outcome, not its "
            "eventual response transport. Fresh external information is "
            "capability_work even when a later grounded answer will be spoken; "
            "speech is an immediate ordinary answer authored without fresh "
            "acquisition or downstream work. This "
            "preserves WHAT kind of effect is owed without selecting a Capability, "
            "provider, Activity, executable argument, or wording."
        ),
    )
    relationship: GoalRelationship = "new"
    target_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    completion_requires_work: bool = Field(
        default=False,
        description=(
            "Whether satisfying the outcome requires downstream work beyond the "
            "immediate ordinary conversational response that Fast Planner can author "
            "from supplied context. Use false for a greeting, empathy, social reply, "
            "or direct contextual answer; use true for body/media/vocal-performance "
            "effects, Capability work, fresh evidence, or other work that remains "
            "after an immediate response."
        ),
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

    @field_validator("target_goal_ids", mode="before")
    @classmethod
    def normalize_context_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Goal identity fields must be arrays")
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
        if self.output_mode == "speech" and self.completion_requires_work:
            raise ValueError(
                "output_mode=speech is an immediate contextual answer and cannot "
                "require downstream work"
            )
        if self.completion_requires_fresh_evidence and self.output_mode in {
            "styled_speech",
            "recitation",
            "singing",
            "humming",
            "nonverbal_vocalization",
            "body_action",
            "media_playback",
        }:
            raise ValueError(
                f"output_mode={self.output_mode} is the requested observable effect, "
                "not a fresh-information Responsibility"
            )
        if self.relationship == "new" and self.target_goal_ids:
            raise ValueError("relationship=new must not target an existing Goal")
        if self.relationship != "new" and not self.target_goal_ids:
            raise ValueError(
                f"relationship={self.relationship} requires target_goal_ids"
            )
        if self.output_mode not in {"unspecified", "speech", "other"} and not (
            self.completion_requires_work
        ):
            raise ValueError(
                f"output_mode={self.output_mode} requires completion_requires_work"
            )
        return self


class CoreInterpretationResult(BaseModel):
    """Goal Interpretation result in the current architecture.

    Goal Interpretation answers WHAT the human means in the current bounded
    Context, including whether the turn creates, continues, or modifies supplied
    Goal meaning. Pending clarification is semantic context, but GI neither owns nor
    resolves its Planner-created InformationGap. Fast/Deep depth may change how much
    cognition is used, but not this authority boundary. There is
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
    responsibilities: list[CognitiveResponsibilityProposal] = Field(
        min_length=1,
        description=(
            "Complete set of independently satisfiable human outcomes. Emit one item "
            "per requested observable effect, including separate concurrent embodied "
            "and authored-vocal effects; coordination is a relation, not permission "
            "to collapse two effects into one item."
        ),
    )
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
