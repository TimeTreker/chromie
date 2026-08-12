from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReflectionAction = Literal[
    "replan",
    "clarify",
    "correct_user",
    "propose_memory",
]
ReflectionMemoryKind = Literal["experience", "calibration"]
ReflectionMemoryScope = Literal["task", "session"]


class ReflectionMemoryCandidate(BaseModel):
    """Bounded non-durable memory proposal from selective Reflection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: ReflectionMemoryScope = "task"
    kind: ReflectionMemoryKind = "experience"
    text: str = Field(min_length=1, max_length=260)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class ReflectionResolution(BaseModel):
    """Ephemeral result of selective slow cognition over trusted evidence.

    Reflection may propose future repair. It never rewrites Evidence,
    ExecutionOutcome, delivered speech, Stable Mind, or effect authority.
    Goal/evidence references are supplied by trusted runtime, not chosen by the
    model-facing Reflection output.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    opportunity_id: str = Field(min_length=1, max_length=200)
    goal_ids: list[str] = Field(min_length=1, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    actions: list[ReflectionAction] = Field(default_factory=list, max_length=4)
    correction_text: str = Field(default="", max_length=600)
    memory_candidates: list[ReflectionMemoryCandidate] = Field(
        default_factory=list,
        max_length=4,
    )
    reason_summary: str = Field(default="", max_length=600)

    @field_validator("opportunity_id", "correction_text", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("goal_ids", "evidence_refs", "reason_codes", "actions", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Reflection list fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_actions(self) -> "ReflectionResolution":
        if self.correction_text and "correct_user" not in self.actions:
            raise ValueError("correction_text requires correct_user action")
        if "correct_user" in self.actions and not self.correction_text:
            raise ValueError("correct_user action requires correction_text")
        if self.memory_candidates and "propose_memory" not in self.actions:
            raise ValueError("memory_candidates require propose_memory action")
        if "propose_memory" in self.actions and not self.memory_candidates:
            raise ValueError("propose_memory action requires memory_candidates")
        return self

    def prompt_projection(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
