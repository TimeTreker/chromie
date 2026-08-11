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

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(default=1, ge=1)
    lane: str = Field(default="unknown", min_length=1, max_length=120)
    intent: str = Field(default="unknown", min_length=1, max_length=240)
    focus_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    discourse_focus_ids: list[str] = Field(default_factory=list, max_length=8)
    unresolved_conditions: list[SituationConditionRef] = Field(
        default_factory=list,
        max_length=12,
    )
    progress_candidate_ids: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[SituationEvidenceRef] = Field(default_factory=list, max_length=8)
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("turn_id", "lane", "intent", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "focus_goal_ids",
        "discourse_focus_ids",
        "progress_candidate_ids",
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
