from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields

PlanCoverage = Literal["complete", "partial", "uncertain"]
PlannerTier = Literal["fast", "deep"]
PlanDisposition = Literal["respond", "execute", "escalate", "clarify", "unavailable", "refused"]
PlanTiming = Literal["sequential", "parallel"]


class CanonicalPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: PlanTiming = "sequential"
    source_goal_ids: list[str] = Field(default_factory=list)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("step_id", "skill_id", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("args", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class CanonicalPlan(BaseModel):
    """Planner-neutral plan consumed by one deterministic validation path."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    plan_id: str = Field(min_length=1)
    planner_tier: PlannerTier
    disposition: PlanDisposition
    coverage: PlanCoverage
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    goal_ids: list[str] = Field(default_factory=list)
    goal_summary: str = ""
    response_text: str = ""
    steps: list[CanonicalPlanStep] = Field(default_factory=list)
    escalation_reason: str = ""
    unresolved: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("plan_id", "goal_summary", "response_text", "escalation_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_coverage_contract(self) -> "CanonicalPlan":
        if self.coverage != "complete":
            if self.disposition != "escalate":
                raise ValueError("partial or uncertain coverage must escalate")
            if self.steps:
                raise ValueError("escalating plans must not carry executable steps")
            if not self.escalation_reason:
                raise ValueError("escalating plans require escalation_reason")
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute disposition requires at least one step")
        if self.disposition == "respond" and not self.response_text:
            raise ValueError("respond disposition requires response_text")
        if self.disposition in {"execute", "respond"} and self.coverage != "complete":
            raise ValueError("respond and execute require complete coverage")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("canonical plan step_id values must be unique")
        return self
