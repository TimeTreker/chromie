from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .agent_skill import PlanAgentSkillProvenance
from .interaction import CapabilityIdentityModel, reject_forbidden_low_level_fields

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
GoalOutcomeDisposition = Literal[
    "respond",
    "execute",
    "escalate",
    "clarify",
    "unavailable",
    "refused",
]
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
FastPlannerContinuation = Literal["goal_association", "deep_planner"]
FastVocalActivityRole = Literal["complete_response", "progress", "clarification"]
FastProgressKind = Literal[
    "acknowledge_work",
    "check_information",
    "perform_action",
    "think",
]


class _FastPlannerVocalActivityBase(BaseModel):
    """Common identity/provenance for one Fast-Planner-authored vocal Activity."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=160)
    speech_act: str = Field(default="inform", min_length=1, max_length=120)
    source_responsibility_refs: list[str] = Field(min_length=1)

    @field_validator("activity_id", "speech_act", mode="before")
    @classmethod
    def normalize_vocal_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("source_responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class FastPlannerCompleteResponseActivity(_FastPlannerVocalActivityBase):
    """A conversational answer that can fully complete its Responsibility now."""

    role: Literal["complete_response"] = "complete_response"
    response_text: str = Field(min_length=1, max_length=600)

    @field_validator("response_text", mode="before")
    @classmethod
    def normalize_response_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value


class FastPlannerClarificationActivity(_FastPlannerVocalActivityBase):
    """A user-facing question when WHAT lacks a material binding."""

    role: Literal["clarification"] = "clarification"
    response_text: str = Field(min_length=1, max_length=600)

    @field_validator("response_text", mode="before")
    @classmethod
    def normalize_response_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value


class FastPlannerProgressActivity(_FastPlannerVocalActivityBase):
    """Pre-evidence progress semantics with no model-authored factual wording.

    A progress Activity is deliberately not free text.  Before trusted Evidence
    exists, allowing arbitrary response text lets a model hide an unsupported
    result claim behind ``role=progress``.  The Planner therefore selects only a
    bounded progress act; trusted runtime renders that act without inventing a
    result.
    """

    role: Literal["progress"] = "progress"
    progress_kind: FastProgressKind


FastPlannerVocalActivity = Annotated[
    Union[
        FastPlannerCompleteResponseActivity,
        FastPlannerProgressActivity,
        FastPlannerClarificationActivity,
    ],
    Field(discriminator="role"),
]

# Fresh-evidence Responsibilities cannot be completed before new Evidence exists.
# Encode that known truth in the decoder contract itself so Goal Progress
# Communication can still choose progress/clarification without offering an
# impossible complete_response branch and discarding useful communication after
# inference.
# When WHAT is already confident, fresh Evidence means the only honest immediate
# act is bounded progress. A separate clarifiable contract is used only when Goal
# Interpretation explicitly carries material uncertainty at low confidence.
FastPlannerFreshEvidenceVocalActivity = FastPlannerProgressActivity

FastPlannerFreshEvidenceClarifiableVocalActivity = Annotated[
    Union[
        FastPlannerProgressActivity,
        FastPlannerClarificationActivity,
    ],
    Field(discriminator="role"),
]


def render_fast_planner_vocal_activity(
    activity: FastPlannerVocalActivity,
    *,
    language: str,
) -> str:
    """Render only the bounded speech semantics already authorized by Fast Planner."""

    if activity.role != "progress":
        return activity.response_text
    zh = str(language or "").strip().casefold().startswith("zh")
    if zh:
        return {
            "acknowledge_work": "好，我先想想。",
            "check_information": "我先看看能不能查到。",
            "perform_action": "我先看看能不能做到。",
            "think": "我想一想。",
        }[activity.progress_kind]
    return {
        "acknowledge_work": "Okay, let me think about that.",
        "check_information": "Let me see what I can check.",
        "perform_action": "Let me see what I can do.",
        "think": "Let me think about it.",
    }[activity.progress_kind]


class FastPlannerAdvance(BaseModel):
    """Fast Planner's pre-Goal advancement decision over Responsibility evidence.

    Fast Goal Interpretation owns WHAT the user appears to want.  This contract is
    the first planner-owned decision about HOW to advance that meaning.  It may
    author one immediately-ready conversational Activity and may request Goal
    Association and/or Deep Planner continuation.  It cannot mutate canonical Goal
    state or authorize effects.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    turn_id: str = Field(min_length=1, max_length=160)
    planner_tier: Literal["fast"] = "fast"
    covered_responsibility_refs: list[str] = Field(default_factory=list)
    immediate_vocal_activity: FastPlannerVocalActivity | None = None
    continuations: list[FastPlannerContinuation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "reason_summary", mode="before")
    @classmethod
    def normalize_advance_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("covered_responsibility_refs", "continuations", "unresolved", mode="before")
    @classmethod
    def normalize_advance_lists(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("metadata")
    @classmethod
    def reject_advance_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_advance_contract(self) -> "FastPlannerAdvance":
        if "deep_planner" in self.continuations and "goal_association" not in self.continuations:
            raise ValueError(
                "Deep Planner continuation requires Goal Association so deeper planning "
                "receives canonical Goal state"
            )
        if not self.continuations and self.immediate_vocal_activity is None:
            raise ValueError(
                "a terminal Fast Planner advance requires an immediate conversational Activity"
            )
        if self.immediate_vocal_activity is not None:
            unknown = set(self.immediate_vocal_activity.source_responsibility_refs) - set(
                self.covered_responsibility_refs
            )
            if unknown:
                raise ValueError(
                    "immediate vocal Activity references uncovered Responsibility refs: "
                    + ",".join(sorted(unknown))
                )
        return self


class FastPlannerAdvanceModelOutput(BaseModel):
    """Schema-constrained model payload before host-owned turn identity is attached.

    Every decision field is required even when its value is empty or null.  The
    model must explicitly state coverage and continuation rather than relying on
    host-side defaults that can turn an omitted decision into a false terminal
    advance.
    """

    model_config = ConfigDict(extra="forbid")

    covered_responsibility_refs: list[str]
    immediate_vocal_activity: FastPlannerVocalActivity | None
    continuations: list[FastPlannerContinuation]
    confidence: float = Field(ge=0.0, le=1.0)
    unresolved: list[str]
    reason_summary: str

    @field_validator("covered_responsibility_refs", "continuations", "unresolved", mode="before")
    @classmethod
    def normalize_output_lists(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_output_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value


class FastPlannerFreshEvidenceAdvanceModelOutput(FastPlannerAdvanceModelOutput):
    """Decoder contract for confident WHAT that still needs fresh Evidence.

    No factual result can be complete yet, and confident WHAT does not need a
    clarification question. The only immediate user-facing semantic delta is
    bounded progress (or silence).
    """

    immediate_vocal_activity: FastPlannerFreshEvidenceVocalActivity | None


class FastPlannerFreshEvidenceClarifiableAdvanceModelOutput(FastPlannerAdvanceModelOutput):
    """Fresh-evidence decoder contract when WHAT is materially uncertain."""

    immediate_vocal_activity: FastPlannerFreshEvidenceClarifiableVocalActivity | None


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
    parameter: str = Field(
        min_length=1,
        description=(
            "Exact argument key from the referenced plan step's args object. "
            "Do not prefix it with a step ID or capability ID."
        ),
    )
    strategy: ParameterResolutionStrategy
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    blocking: bool = False
    rationale: str = ""
    source_goal_ids: list[str] = Field(default_factory=list)

    @field_validator("step_id", "parameter", "rationale", mode="before")
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


class CanonicalPlanStep(CapabilityIdentityModel):
    """One canonical executable Capability step in a Plan."""

    step_id: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: PlanTiming = "sequential"
    source_goal_ids: list[str] = Field(default_factory=list)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("step_id", "reason_summary", mode="before")
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
    unresolved: list[str] = Field(default_factory=list, max_length=0)
    step_ids: list[str] = Field(min_length=1)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class RespondGoalPlanOutcome(_GoalPlanOutcomeBase):
    disposition: Literal["respond"]
    coverage: Literal["complete"]
    unresolved: list[str] = Field(default_factory=list, max_length=0)
    step_ids: list[str] = Field(default_factory=list, max_length=0)
    response_text: str = Field(min_length=1)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)


class EscalateGoalPlanOutcome(_GoalPlanOutcomeBase):
    """Fast-tier decision that delegates one goal to Deep Planner.

    This is a planner judgment, not an execution result.  It keeps semantic
    escalation attached to the exact authoritative goal instead of forcing the
    host to invent or discard per-goal meaning while converting model output
    into a CanonicalPlan.
    """

    disposition: Literal["escalate"]
    coverage: Literal["partial", "uncertain"]
    step_ids: list[str] = Field(default_factory=list, max_length=0)

    @field_validator("step_ids", mode="before")
    @classmethod
    def normalize_step_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @model_validator(mode="after")
    def validate_escalation(self) -> "EscalateGoalPlanOutcome":
        if self.response_text:
            raise ValueError(
                "escalate goal outcomes must not claim a user-facing answer"
            )
        if not self.unresolved and not self.rationale:
            raise ValueError(
                "escalate goal outcomes require an unresolved need or rationale"
            )
        return self


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
        EscalateGoalPlanOutcome,
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
    selected_agent_skills: list[PlanAgentSkillProvenance] = Field(default_factory=list)
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

    def prompt_projection(self) -> dict[str, Any]:
        """Return the closed semantic Plan projection permitted in prompts.

        Runtime and diagnostic metadata remain on the authoritative Plan object.
        Downstream model stages receive typed semantic fields plus the two
        material plan-policy values they must preserve.
        """

        payload = self.model_dump(
            mode="json",
            exclude={"metadata", "steps", "goal_outcomes"},
            exclude_none=True,
        )
        payload["steps"] = [
            item.model_dump(mode="json", exclude={"metadata"}, exclude_none=True)
            for item in self.steps
        ]
        payload["goal_outcomes"] = [
            item.model_dump(mode="json", exclude={"metadata"}, exclude_none=True)
            for item in self.goal_outcomes
        ]
        allowed_metadata: dict[str, Any] = {}
        relation = self.metadata.get("plan_relation")
        if relation in {"exact", "safe_adjustment", "alternative"}:
            allowed_metadata["plan_relation"] = relation
        confirmation = self.metadata.get("user_confirmation_required")
        if isinstance(confirmation, bool):
            allowed_metadata["user_confirmation_required"] = confirmation
        path_classification = self.metadata.get("path_classification")
        if path_classification in {
            "terminal",
            "semantic_escalation",
            "contract_failure",
            "coverage_review_failure",
        }:
            allowed_metadata["path_classification"] = path_classification
        if allowed_metadata:
            payload["metadata"] = allowed_metadata
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(serialized) > 65_536:
            raise ValueError("Canonical Plan prompt projection exceeds 65536 UTF-8 bytes")
        return payload

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

    def agent_skill_provenance_for_goals(
        self,
        goal_ids: list[str] | tuple[str, ...] | set[str],
    ) -> list[PlanAgentSkillProvenance]:
        """Narrow inherited method provenance to an exact derived Goal subset."""

        allowed = {str(item).strip() for item in goal_ids if str(item).strip()}
        narrowed: list[PlanAgentSkillProvenance] = []
        for item in self.selected_agent_skills:
            relevant = tuple(
                goal_id for goal_id in item.relevant_goal_ids if goal_id in allowed
            )
            if not relevant:
                continue
            narrowed.append(item.model_copy(update={"relevant_goal_ids": relevant}))
        return narrowed

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
        if self.disposition == "mixed" and not self.steps:
            raise ValueError("mixed disposition requires at least one executable step")
        if self.disposition == "respond" and not self.response_text:
            raise ValueError("respond disposition requires response_text")
        if self.disposition not in {"execute", "mixed"} and self.steps:
            raise ValueError(
                f"{self.disposition} disposition must not carry executable steps"
            )
        if self.disposition in {"execute", "respond", "mixed"} and self.coverage != "complete":
            raise ValueError("respond, execute, and mixed plans require complete accounting coverage")
        if self.disposition in {"execute", "respond"} and self.unresolved:
            raise ValueError(
                "complete execute or respond plans must not retain unresolved "
                "planning work"
            )
        resolution_keys = [(item.step_id, item.parameter) for item in self.parameter_resolutions]
        if len(resolution_keys) != len(set(resolution_keys)):
            raise ValueError("parameter resolution entries must be unique per step and parameter")
        blocking = [item for item in self.parameter_resolutions if item.blocking]
        if self.disposition == "execute" and blocking:
            raise ValueError("executable plans cannot retain blocking parameter resolutions")

        goal_id_set = set(self.goal_ids)
        provenance_keys = [
            (item.agent_skill_id, item.selected_by_agent_role)
            for item in self.selected_agent_skills
        ]
        if len(provenance_keys) != len(set(provenance_keys)):
            raise ValueError(
                "Canonical Plan Agent Skill provenance must be unique per Skill and planner role"
            )
        allowed_roles = (
            {"fast_planner"}
            if self.planner_tier == "fast"
            else {"fast_planner", "deep_planner"}
        )
        for item in self.selected_agent_skills:
            if item.selected_by_agent_role not in allowed_roles:
                raise ValueError(
                    "Canonical Plan Agent Skill provenance is inconsistent with planner_tier"
                )
            unknown_provenance_goals = set(item.relevant_goal_ids) - goal_id_set
            if unknown_provenance_goals:
                raise ValueError(
                    "Plan Agent Skill provenance references unknown goal IDs: "
                    + ",".join(sorted(unknown_provenance_goals))
                )
        if self.goal_satisfaction is not None:
            if (
                self.coverage == "complete"
                and self.disposition != "mixed"
                and self.goal_satisfaction.status in {"partial", "unsatisfied"}
            ):
                raise ValueError("complete non-mixed plans cannot report partial or unsatisfied goal coverage")
            satisfaction_goal_ids = {
                *self.goal_satisfaction.satisfied_goal_ids,
                *self.goal_satisfaction.unmet_goal_ids,
            }
            unknown_satisfaction_goals = satisfaction_goal_ids - goal_id_set
            if unknown_satisfaction_goals:
                raise ValueError(
                    "goal satisfaction references unknown goal IDs: "
                    + ",".join(sorted(unknown_satisfaction_goals))
                )

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("canonical plan step_id values must be unique")
        step_id_set = set(step_ids)
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
            if self.planner_tier == "deep" and "escalate" in outcome_dispositions:
                raise ValueError("deep plans cannot contain escalate goal outcomes")

            referenced_steps: set[str] = set()
            executable_owners_by_step: dict[str, set[str]] = {}
            for outcome in self.goal_outcomes:
                if outcome.satisfaction is not None:
                    outcome_satisfaction_goal_ids = {
                        *outcome.satisfaction.satisfied_goal_ids,
                        *outcome.satisfaction.unmet_goal_ids,
                    }
                    foreign_satisfaction_goals = outcome_satisfaction_goal_ids - {
                        outcome.goal_id
                    }
                    if foreign_satisfaction_goals:
                        raise ValueError(
                            "per-goal outcome satisfaction may reference only its "
                            f"own goal ID {outcome.goal_id!r}: "
                            + ",".join(sorted(foreign_satisfaction_goals))
                        )
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
        elif len(goal_id_set) > 1 and self.disposition in {"execute", "respond"}:
            raise ValueError(
                "complete multi-goal execute or respond plans require per-goal outcomes"
            )

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
            if self.planner_tier == "fast":
                unsupported = dispositions - {"execute", "respond"}
                if unsupported:
                    raise ValueError(
                        "fast mixed plans may contain only execute and respond outcomes: "
                        + ",".join(sorted(unsupported))
                    )
        return self
