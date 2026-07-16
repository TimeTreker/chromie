from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields

PlanCoverage = Literal["complete", "partial", "uncertain"]
PlannerTier = Literal["fast", "deep"]
PlanDisposition = Literal[
    "respond",
    "execute",
    "mixed",
    "escalate",
    "clarify",
    "unavailable",
    "refused",
]
GoalOutcomeDisposition = Literal["respond", "execute", "clarify", "unavailable", "refused"]
PlanTiming = Literal["sequential", "parallel"]
ParameterResolutionStrategy = Literal[
    "user_supplied",
    "schema_default",
    "safe_default",
    "observed_context",
    "trusted_service",
    "ask_user",
    "unresolvable",
]
GoalSatisfactionStatus = Literal["exact", "substantial", "partial", "unsatisfied"]


def _normalize_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list or string")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


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
    source_goal_ids: list[str] = Field(default_factory=list)

    @field_validator("step_id", "parameter", "rationale", "source_ref", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("source_goal_ids", mode="before")
    @classmethod
    def normalize_source_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

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

    @field_validator("satisfied_goal_ids", "unmet_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

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

    @field_validator("source_goal_ids", mode="before")
    @classmethod
    def normalize_source_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("args", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class _GoalPlanOutcomeBase(BaseModel):
    """Shared fields for one per-goal terminal planning outcome."""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    coverage: PlanCoverage
    response_text: str = ""
    unresolved: list[str] = Field(default_factory=list)
    satisfaction: GoalSatisfactionAssessment | None = None
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("goal_id", "response_text", "rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("unresolved", mode="before")
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class ExecuteGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["execute"]
    coverage: Literal["complete"]
    step_ids: list[str] = Field(min_length=1)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class RespondGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["respond"]
    coverage: Literal["complete"]
    step_ids: list[str] = Field(default_factory=list, max_length=0)
    response_text: str = Field(min_length=1)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class ClarifyGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["clarify"]
    coverage: Literal["partial", "uncertain"]
    step_ids: list[str] = Field(default_factory=list, max_length=0)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @model_validator(mode="after")
    def validate_clarification(self) -> "ClarifyGoalPlanOutcome":
        if not self.unresolved and not self.response_text:
            raise ValueError(
                "clarify goal outcomes require an unresolved need or response_text"
            )
        return self


class UnavailableGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["unavailable"]
    step_ids: list[str] = Field(default_factory=list, max_length=0)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class RefusedGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["refused"]
    step_ids: list[str] = Field(default_factory=list, max_length=0)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


GoalPlanOutcome = Annotated[
    Union[
        ExecuteGoalPlanOutcome,
        RespondGoalPlanOutcome,
        ClarifyGoalPlanOutcome,
        UnavailableGoalPlanOutcome,
        RefusedGoalPlanOutcome,
    ],
    Field(discriminator="disposition"),
]


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
    goal_outcomes: list[GoalPlanOutcome] = Field(default_factory=list)
    goal_satisfaction: GoalSatisfactionAssessment | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("plan_id", "goal_summary", "response_text", "escalation_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("goal_ids", "unresolved", mode="before")
    @classmethod
    def normalize_text_list(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    def outcome_for_goal(self, goal_id: str) -> GoalPlanOutcome | None:
        return next((item for item in self.goal_outcomes if item.goal_id == goal_id), None)

    def executable_goal_ids(self) -> list[str]:
        if self.goal_outcomes:
            return [item.goal_id for item in self.goal_outcomes if item.disposition == "execute"]
        return list(self.goal_ids) if self.disposition == "execute" else []

    def waiting_goal_ids(self) -> list[str]:
        if self.goal_outcomes:
            return [item.goal_id for item in self.goal_outcomes if item.disposition == "clarify"]
        return list(self.goal_ids) if self.disposition == "clarify" else []

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
        if self.planner_tier == "fast" and self.disposition == "mixed":
            raise ValueError("mixed multi-goal outcomes require deep planning")
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute disposition requires at least one step")
        if self.disposition == "mixed" and not self.steps:
            raise ValueError("mixed disposition requires at least one executable step")
        if self.disposition == "respond" and not self.response_text:
            raise ValueError("respond disposition requires response_text")
        if self.disposition in {"execute", "respond", "mixed"} and self.coverage != "complete":
            raise ValueError("respond, execute, and mixed plans require complete accounting coverage")

        resolution_keys = [(item.step_id, item.parameter) for item in self.parameter_resolutions]
        if len(resolution_keys) != len(set(resolution_keys)):
            raise ValueError("parameter resolution entries must be unique per step and parameter")
        blocking = [item for item in self.parameter_resolutions if item.blocking]
        if self.disposition == "execute" and blocking:
            raise ValueError("executable plans cannot retain blocking parameter resolutions")

        if self.coverage == "complete" and self.goal_satisfaction is not None:
            if self.disposition != "mixed" and self.goal_satisfaction.status in {"partial", "unsatisfied"}:
                raise ValueError("complete non-mixed plans cannot report partial or unsatisfied goal coverage")

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("canonical plan step_id values must be unique")
        step_id_set = set(step_ids)
        goal_id_set = set(self.goal_ids)

        if self.steps and not goal_id_set:
            raise ValueError("executable steps require at least one canonical plan goal_id")
        for step in self.steps:
            source_goal_ids = set(step.source_goal_ids)
            if not source_goal_ids:
                raise ValueError(
                    f"executable step {step.step_id!r} requires source_goal_ids"
                )
            unknown = source_goal_ids - goal_id_set
            if unknown:
                raise ValueError("plan step references unknown goal IDs: " + ",".join(sorted(unknown)))
        for resolution in self.parameter_resolutions:
            unknown = set(resolution.source_goal_ids) - goal_id_set
            if unknown:
                raise ValueError(
                    "parameter resolution references unknown goal IDs: " + ",".join(sorted(unknown))
                )

        outcome_by_goal: dict[str, GoalPlanOutcome] = {}
        if self.goal_outcomes:
            outcome_ids = [item.goal_id for item in self.goal_outcomes]
            if len(outcome_ids) != len(set(outcome_ids)):
                raise ValueError("goal outcome IDs must be unique")
            if set(outcome_ids) != goal_id_set:
                raise ValueError("goal outcomes must cover exactly the canonical plan goal_ids")
            outcome_by_goal = {item.goal_id: item for item in self.goal_outcomes}

            outcome_dispositions = {item.disposition for item in self.goal_outcomes}
            expected_disposition = (
                "mixed" if len(outcome_dispositions) > 1 else next(iter(outcome_dispositions))
            )
            if self.disposition != expected_disposition:
                raise ValueError(
                    "top-level disposition must match the per-goal outcome dispositions"
                )

            referenced_steps: set[str] = set()
            executable_owners_by_step: dict[str, set[str]] = {}
            for outcome in self.goal_outcomes:
                unknown_steps = set(outcome.step_ids) - step_id_set
                if unknown_steps:
                    raise ValueError(
                        "goal outcome references unknown step IDs: " + ",".join(sorted(unknown_steps))
                    )
                referenced_steps.update(outcome.step_ids)
                if outcome.disposition == "execute":
                    for step_id in outcome.step_ids:
                        executable_owners_by_step.setdefault(step_id, set()).add(outcome.goal_id)
            if referenced_steps != step_id_set:
                missing = sorted(step_id_set - referenced_steps)
                raise ValueError(
                    "every executable step must belong to at least one goal outcome: "
                    + ",".join(missing)
                )
            for step in self.steps:
                expected_owners = executable_owners_by_step.get(step.step_id, set())
                if set(step.source_goal_ids) != expected_owners:
                    raise ValueError(
                        f"step {step.step_id!r} source_goal_ids must exactly match "
                        "the executable goal outcomes that reference it"
                    )
        elif self.disposition == "mixed":
            raise ValueError("mixed plans require per-goal outcomes")

        for resolution in blocking:
            if not resolution.source_goal_ids:
                raise ValueError("blocking parameter resolutions require source_goal_ids")
            if outcome_by_goal:
                invalid_goals = sorted(
                    goal_id
                    for goal_id in resolution.source_goal_ids
                    if outcome_by_goal[goal_id].disposition != "clarify"
                )
                if invalid_goals:
                    raise ValueError(
                        "blocking parameter resolutions may only target clarify goal outcomes: "
                        + ",".join(invalid_goals)
                    )

        if self.disposition == "mixed":
            dispositions = {item.disposition for item in self.goal_outcomes}
            if "execute" not in dispositions:
                raise ValueError("mixed plans require at least one executable goal outcome")
        return self
