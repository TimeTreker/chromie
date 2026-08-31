from __future__ import annotations

import hashlib
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


class ResponsibilitySourceEvidence(BaseModel):
    """Primary-result citation into the authoritative admitted turn.

    Goal Interpretation owns the semantic choice of the cited span. Trusted code
    resolves the two closed token references back to the immutable turn and checks
    only provenance, order, and non-overlap; it never retypes or resegments WHAT.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_start_token_ref: str = Field(min_length=1, max_length=24)
    source_end_token_ref: str = Field(min_length=1, max_length=24)

    @field_validator("source_start_token_ref", "source_end_token_ref", mode="before")
    @classmethod
    def normalize_source_token_ref(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))


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
            "whether P is true must not be rewritten as the assertion that P is true. "
            "For conversational speech, describe the communicative obligation or "
            "proposition to convey; never write the exact words Chromie will say. "
            "Planner alone authors the utterance."
        ),
    )
    bindings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Material user-semantic facts from the authoritative turn or bounded "
            "semantic context only; never runtime/session identifiers or HOW fields. "
            "Preserve an explicitly measured value and its unit together as one exact "
            "source/context surface; execution-unit normalization belongs downstream. "
            "Cross-Responsibility order uses before/after with exact sibling local_ref "
            "values; requested concurrency uses parallel_with with exact sibling "
            "local_ref values."
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
        "information",
        "stateful_effect",
        "other",
    ] = Field(
        default="unspecified",
        description=(
            "Goal Interpretation's provider-neutral WHAT category for this one human "
            "outcome. Goal Association preserves the accepted value and must not "
            "re-author it. information "
            "means the person wants Chromie to determine or provide information; "
            "stateful_effect means the person wants a durable or future state change "
            "outside embodiment. Physical locomotion, posture, gaze, gesture, manipulation, "
            "carrying, and handover are body_action even when they change location or "
            "another lasting physical state. "
            "These categories do not say whether work, fresh evidence, a Capability, "
            "provider, Activity, executable argument, or later speech is required. "
            "Requested physical-object acquisition/carrying/handover remains "
            "body_action because the human-level outcome is an embodied effect."
        ),
    )
    relationship: GoalRelationship = "new"
    target_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_evidence: ResponsibilitySourceEvidence | None = Field(
        default=None,
        description=(
            "Primary Goal-Interpretation evidence citing the exact inclusive token "
            "span in the authoritative admitted turn that grounds this one "
            "Responsibility. The live GI contract requires it; the optional model "
            "default preserves construction of bounded downstream/test projections "
            "that do not themselves author GI meaning."
        ),
    )

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
    def validate_goal_relationship(self) -> "CognitiveResponsibilityProposal":
        if self.relationship == "new" and self.target_goal_ids:
            raise ValueError("relationship=new must not target an existing Goal")
        if self.relationship != "new" and not self.target_goal_ids:
            raise ValueError(
                f"relationship={self.relationship} requires target_goal_ids"
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


class PlannerReentryScope(BaseModel):
    """Immutable state-transition scope for one same-Planner re-entry.

    This is readiness/provenance, not another semantic owner.  It prevents a
    full conversation Goal projection from silently widening the exact Goal set
    affected by terminal Evidence, cancellation, Situation, time, or provider
    revalidation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    trigger: Literal[
        "capability_result_reentry",
        "post_execution",
        "goal_cancellation_reentry",
        "situation_revision_reentry",
        "time_condition_reentry",
        "restored_provider_state_revalidation",
    ]
    goal_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    opportunity_id: str = Field(default="", max_length=200)
    source_plan_id: str = Field(default="", max_length=200)
    source_plan_fingerprint: str = Field(default="", max_length=128)

    @field_validator(
        "goal_ids",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def normalize_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Planner re-entry identity fields must be arrays")
        return tuple(
            dict.fromkeys(
                text
                for item in value
                if (text := normalize_turn_text(str(item or "")))
            )
        )

    @field_validator(
        "opportunity_id",
        "source_plan_id",
        "source_plan_fingerprint",
        mode="before",
    )
    @classmethod
    def normalize_scalar_ids(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))

    @model_validator(mode="after")
    def validate_trigger_evidence(self) -> "PlannerReentryScope":
        evidence_triggers = {
            "capability_result_reentry",
            "post_execution",
            "goal_cancellation_reentry",
        }
        if self.trigger in evidence_triggers and not self.evidence_refs:
            raise ValueError(
                f"Planner re-entry trigger={self.trigger} requires evidence_refs"
            )
        if self.trigger not in evidence_triggers and not self.opportunity_id:
            raise ValueError(
                f"Planner re-entry trigger={self.trigger} requires opportunity_id"
            )
        if bool(self.source_plan_id) != bool(self.source_plan_fingerprint):
            raise ValueError(
                "source_plan_id and source_plan_fingerprint must be supplied together"
            )
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
    planner_reentry_scope: PlannerReentryScope | None = None
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

    @property
    def source_turn_provenance(self) -> dict[str, Any]:
        """Project immutable source wording without granting semantic authority.

        ``text`` is transport-normalized so model-facing work can compare turns
        deterministically.  Semantic owners must still be able to inspect the
        exact admitted source wording; the UserTurnEnvelope already owns that
        immutable evidence, so this is a computed prompt projection rather than
        another persisted copy.  A scoped Planner re-entry may supply the same
        projection without replaying the whole UserTurnEnvelope as a fresh turn.
        """

        context = self.context if isinstance(self.context, dict) else {}
        projected = context.get("source_turn_provenance")
        if isinstance(projected, dict):
            original = projected.get("original_text")
            digest = str(projected.get("original_text_sha256") or "").strip()
            if (
                projected.get("authority") == "read_only_source_provenance"
                and isinstance(original, str)
                and original
                and digest
                == hashlib.sha256(original.encode("utf-8")).hexdigest()
            ):
                return {
                    "schema_version": 1,
                    "turn_id": str(projected.get("turn_id") or ""),
                    "original_text": original,
                    "original_text_sha256": digest,
                    "language": str(
                        projected.get("language") or self.language or "auto"
                    ),
                    "authority": "read_only_source_provenance",
                }
        envelope = context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            original = envelope.get("original_input")
            if isinstance(original, dict):
                value = original.get("text")
                if (
                    isinstance(value, str)
                    and value
                    and normalize_turn_text(value) == self.text
                ):
                    normalized = envelope.get("normalized_input")
                    language = (
                        normalized.get("language")
                        if isinstance(normalized, dict)
                        else self.language
                    )
                    return {
                        "schema_version": 1,
                        "turn_id": str(envelope.get("turn_id") or ""),
                        "original_text": value,
                        "original_text_sha256": hashlib.sha256(
                            value.encode("utf-8")
                        ).hexdigest(),
                        "language": str(language or self.language or "auto"),
                        "authority": "read_only_source_provenance",
                    }
        value = self.text
        return {
            "schema_version": 1,
            "turn_id": "",
            "original_text": value,
            "original_text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "language": str(self.language or "auto"),
            "authority": "normalized_transport_fallback",
        }

    @property
    def original_user_text(self) -> str:
        """Return exact source wording from the validated provenance projection."""

        return str(self.source_turn_provenance.get("original_text") or self.text)
