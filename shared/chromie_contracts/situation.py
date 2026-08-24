from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SituationEvidenceKind = Literal[
    "tool_evidence",
    "execution_evidence",
    "interaction_evidence",
    "other_evidence",
]


class SituationConditionRef(BaseModel):
    """Reference to one unresolved condition owned by an existing Goal/context artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_id: str = Field(min_length=1, max_length=160)
    condition_id: str = Field(min_length=1, max_length=200)
    resolution: str = Field(default="unknown", min_length=1, max_length=120)

    @field_validator("goal_id", "condition_id", "resolution", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class SituationEvidenceRef(BaseModel):
    """Reference to retained evidence; Situation never copies the evidence payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SituationEvidenceKind = "other_evidence"
    reference_id: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=160)

    @field_validator("reference_id", "owner", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class SituationProjection(BaseModel):
    """Bounded, revisable, reconstructable live cognitive interpretation index.

    Situation does not own the referenced Goal, Evidence, Memory, provider, or
    runtime facts.  It only records which already-owned meanings are currently
    relevant to this turn so multiple cognitive roles can reason from one bounded
    interpretation instead of independently rebuilding different working sets.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    turn_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(default=1, ge=1)
    focus_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    discourse_focus_ids: list[str] = Field(default_factory=list, max_length=8)
    unresolved_conditions: list[SituationConditionRef] = Field(
        default_factory=list,
        max_length=12,
    )
    evidence_refs: list[SituationEvidenceRef] = Field(default_factory=list, max_length=8)
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("turn_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "focus_goal_ids",
        "discourse_focus_ids",
        mode="before",
    )
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Situation ID fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @staticmethod
    def calculate_digest(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"digest"})

    @model_validator(mode="after")
    def validate_digest(self) -> "SituationProjection":
        expected = self.calculate_digest(self.semantic_payload())
        if self.digest != expected:
            raise ValueError("Situation digest does not match projection content")
        return self

    @classmethod
    def create(cls, **kwargs: Any) -> "SituationProjection":
        payload = cls.model_construct(digest="0" * 64, **kwargs).model_dump(
            mode="json",
            exclude={"digest"},
        )
        return cls(digest=cls.calculate_digest(payload), **kwargs)

    def prompt_projection(self) -> dict[str, Any]:
        """Return the complete bounded projection; referenced evidence stays external."""

        return self.model_dump(mode="json")


class SituationRevisionObservation(BaseModel):
    """Trusted external Situation delta admitted for continuous cognition.

    The observation names its independently trusted source and references retained
    Evidence; it does not become Goal/Evidence truth itself.  Runtime may derive a
    CognitiveOpportunity only when the supplied projection actually changed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=160)
    source_revision: int = Field(ge=1)
    goal_ids: list[str] = Field(min_length=1, max_length=8)
    evidence_refs: list[str] = Field(min_length=1, max_length=16)
    projection: SituationProjection

    @field_validator("observation_id", "source_id", mode="before")
    @classmethod
    def normalize_observation_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("goal_ids", "evidence_refs", mode="before")
    @classmethod
    def normalize_observation_lists(cls, value: Any) -> list[str]:

        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_projection_binding(self) -> "SituationRevisionObservation":
        if self.source_revision != self.projection.revision:
            raise ValueError("source_revision must match Situation projection revision")
        projection_goals = set(self.projection.focus_goal_ids)
        if not set(self.goal_ids).issubset(projection_goals):
            raise ValueError("Situation observation Goal IDs must be in projection focus")
        return self


class GoalTimeCondition(BaseModel):
    """Durable Planner-authored wake condition for one existing Goal.

    The condition is structured provenance, never a deadline parsed by Host from
    free-form Goal text. ConversationState owns persistence/consumption while the
    same Planner owns what to do when the condition becomes due.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    condition_id: str = Field(min_length=1, max_length=200)
    goal_id: str = Field(min_length=1, max_length=160)
    due_at_ms: int = Field(ge=1)
    source_plan_id: str = Field(min_length=1, max_length=200)
    source_responsibility_refs: list[str] = Field(min_length=1, max_length=8)
    reason_code: str = Field(default="planner_time_condition", min_length=1, max_length=120)

    @field_validator("condition_id", "goal_id", "source_plan_id", "reason_code", mode="before")
    @classmethod
    def normalize_condition_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("source_responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:

        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

CognitiveOpportunityTrigger = Literal[
    "execution_outcome",
    "situation_revision",
    "time_condition",
    "provider_state",
]
CognitiveOpportunityMode = Literal["local", "fast", "slow"]


class CognitiveOpportunity(BaseModel):
    """Ephemeral readiness signal derived from a meaningful trusted state transition.

    This is not durable Mind state and is never an authority over the referenced
    Goal, Evidence, or next Activity. It carries exact Goal/Evidence provenance only
    long enough to decide whether no cognition, local handling, Planner fast-pass
    cognition, or slower/deeper cognition is useful. A Runtime callback never becomes
    a response/action decision merely by creating this object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    opportunity_id: str = Field(min_length=1, max_length=200)
    trigger: CognitiveOpportunityTrigger
    goal_ids: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    recommended_cognition: CognitiveOpportunityMode = "slow"
    situation_digest: str = Field(default="", max_length=64)

    @field_validator(
        "opportunity_id",
        "situation_digest",
        mode="before",
    )
    @classmethod
    def normalize_opportunity_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("goal_ids", "evidence_refs", "reason_codes", mode="before")
    @classmethod
    def normalize_opportunity_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("CognitiveOpportunity list fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @classmethod
    def create(
        cls,
        *,
        trigger: CognitiveOpportunityTrigger,
        goal_ids: list[str],
        evidence_refs: list[str] | None = None,
        reason_codes: list[str] | None = None,
        recommended_cognition: CognitiveOpportunityMode = "slow",
        situation_digest: str = "",
    ) -> "CognitiveOpportunity":
        payload = {
            "trigger": trigger,
            "goal_ids": goal_ids,
            "evidence_refs": list(evidence_refs or []),
            "reason_codes": list(reason_codes or []),
            "recommended_cognition": recommended_cognition,
            "situation_digest": situation_digest,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return cls(
            opportunity_id=(
                f"cognitive_opportunity_{hashlib.sha256(encoded).hexdigest()[:20]}"
            ),
            trigger=trigger,
            goal_ids=goal_ids,
            evidence_refs=list(evidence_refs or []),
            reason_codes=list(reason_codes or []),
            recommended_cognition=recommended_cognition,
            situation_digest=situation_digest,
        )

    def prompt_projection(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
