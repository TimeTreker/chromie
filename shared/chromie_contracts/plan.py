from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields

PlanCoverage = Literal["complete", "partial", "uncertain"]
PlannerTier = Literal["fast", "deep"]
PlanDisposition = Literal["respond", "execute", "escalate", "clarify", "unavailable", "refused"]
PlanTiming = Literal["sequential", "parallel"]
ParameterResolutionStrategy = Literal[
    "user_supplied", "schema_default", "safe_default", "observed_context",
    "trusted_service", "ask_user", "unresolvable",
]
GoalSatisfactionStatus = Literal["exact", "substantial", "partial", "unsatisfied"]


class PlanParameterResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    strategy: ParameterResolutionStrategy
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    blocking: bool = False
    rationale: str = ""
    source_ref: str = ""

    @field_validator("step_id", "parameter", "rationale", "source_ref", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_resolution(self) -> "PlanParameterResolution":
        if self.strategy in {"ask_user", "unresolvable"}:
            if not self.blocking:
                raise ValueError("ask_user and unresolvable parameter resolutions must be blocking")
            if self.value is not None:
                raise ValueError("blocking unresolved parameters must not carry a value")
        elif self.value is None:
            raise ValueError("resolved parameter strategies require a concrete value")
        return self


class GoalSatisfactionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    status: GoalSatisfactionStatus
    satisfied_goal_ids: list[str] = Field(default_factory=list)
    unmet_goal_ids: list[str] = Field(default_factory=list)
    unmet_requirements: list[str] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_status_band(self) -> "GoalSatisfactionAssessment":
        minimums = {"exact": 0.95, "substantial": 0.75, "partial": 0.01, "unsatisfied": 0.0}
        maximums = {"exact": 1.0, "substantial": 0.949999, "partial": 0.749999, "unsatisfied": 0.0}
        if self.score < minimums[self.status] or self.score > maximums[self.status]:
            raise ValueError("goal satisfaction score is inconsistent with status")
        if self.status == "exact" and (self.unmet_goal_ids or self.unmet_requirements):
            raise ValueError("exact goal satisfaction cannot report unmet goals or requirements")
        return self


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
    parameter_resolutions: list[PlanParameterResolution] = Field(default_factory=list)
    goal_satisfaction: GoalSatisfactionAssessment | None = None
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
            if self.steps:
                raise ValueError("non-complete plans must not carry executable steps")
            if self.planner_tier == "fast":
                if self.disposition != "escalate":
                    raise ValueError("partial or uncertain fast plans must escalate")
                if not self.escalation_reason:
                    raise ValueError("escalating plans require escalation_reason")
            elif self.disposition not in {"clarify", "unavailable", "refused"}:
                raise ValueError("non-complete deep plans must clarify, report unavailable, or refuse")
        if self.planner_tier == "deep" and self.disposition == "escalate":
            raise ValueError("deep plans cannot return to the fast planner")
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute disposition requires at least one step")
        if self.disposition == "respond" and not self.response_text:
            raise ValueError("respond disposition requires response_text")
        if self.disposition in {"execute", "respond"} and self.coverage != "complete":
            raise ValueError("respond and execute require complete coverage")
        resolution_keys = [(item.step_id, item.parameter) for item in self.parameter_resolutions]
        if len(resolution_keys) != len(set(resolution_keys)):
            raise ValueError("parameter resolution entries must be unique per step and parameter")
        blocking = [item for item in self.parameter_resolutions if item.blocking]
        if self.disposition == "execute" and blocking:
            raise ValueError("executable plans cannot retain blocking parameter resolutions")
        if self.coverage == "complete" and self.goal_satisfaction is not None:
            if self.goal_satisfaction.status in {"partial", "unsatisfied"}:
                raise ValueError("complete plans cannot report partial or unsatisfied goal coverage")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("canonical plan step_id values must be unique")
        return self
