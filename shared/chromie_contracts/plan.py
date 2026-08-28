from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Union, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import normalize_whitespace
from .agent_skill import PlanAgentSkillProvenance
from .interaction import CapabilityIdentityModel, reject_forbidden_low_level_fields
from .semantic_task import (
    InformationGap,
    InformationGapResolutionSource,
    InformationGapSourceKind,
)

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
PlanStepPurpose = Literal["achieve_effect", "acquire_information"]
ParameterResolutionStrategy = Literal[
    "user_supplied",
    "schema_default",
    "safe_default",
    "observed_context",
    "trusted_service",
    "semantic_realization",
    "ask_user",
    "unresolvable",
]
GoalSatisfactionStatus = Literal["exact", "substantial", "partial", "unsatisfied"]
FastPlannerContinuation = Literal["deep_planner"]
FastCommunicativeActRole = Literal[
    "complete_response",
    "progress",
    "clarification",
]
FastProgressKind = Literal[
    "acknowledge_work",
    "check_information",
    "perform_action",
    "think",
]
FastProgressSpeechAct = Literal[
    "acknowledge",
    "acknowledge_and_check",
    "thinking",
]
FastCompleteResponseSpeechAct = Literal[
    "acknowledge",
    "answer",
    "apologize",
    "explain",
    "farewell",
    "greeting",
    "inform",
    "respond",
    "support",
    "thank",
]
FastClarificationSpeechAct = Literal["ask_clarification"]
PlannerInformationGapSource = InformationGapSourceKind
PlannerInformationSource = InformationGapResolutionSource
FastCommunicativeSpeechAct = Union[
    FastCompleteResponseSpeechAct,
    FastProgressSpeechAct,
    FastClarificationSpeechAct,
]
CommunicativeTruthStage = Literal[
    "context_grounded",
    "pre_evidence",
    "post_evidence",
]

_FAST_PROGRESS_SPEECH_ACT_BY_KIND: dict[
    FastProgressKind, FastProgressSpeechAct
] = {
    "acknowledge_work": "acknowledge",
    "check_information": "acknowledge_and_check",
    "perform_action": "acknowledge",
    "think": "thinking",
}


class _FastPlannerCommunicativeActBase(BaseModel):
    """Planner-owned communicative Main Activity, including exact wording.

    Planner owns both the semantic function and the natural words. The Host may
    validate provenance, truth stage, evidence binding, safety, and delivery,
    but it does not rewrite the sentence. Vocal runtime owns acoustic delivery.
    """

    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=600)
    timing: PlanTiming = "parallel"
    speech_act: str = Field(default="inform", min_length=1, max_length=120)
    source_responsibility_refs: list[str] = Field(min_length=1)
    truth_stage: CommunicativeTruthStage
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("activity_id", "text", "speech_act", mode="before")
    @classmethod
    def normalize_communicative_act_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("source_responsibility_refs", "evidence_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @model_validator(mode="after")
    def validate_truth_provenance(self) -> "_FastPlannerCommunicativeActBase":
        if self.truth_stage == "pre_evidence" and self.evidence_refs:
            raise ValueError("pre-evidence communication must not reference Evidence")
        if self.truth_stage == "post_evidence" and not self.evidence_refs:
            raise ValueError("post-evidence communication requires Evidence refs")
        return self


class FastPlannerCompleteResponseAct(_FastPlannerCommunicativeActBase):
    """An answer act that can fully complete its Responsibility once realized."""

    role: Literal["complete_response"]
    speech_act: FastCompleteResponseSpeechAct = "respond"
    truth_stage: Literal["context_grounded", "post_evidence"] = "context_grounded"


class PlannerInformationGap(InformationGap):
    """One Fast-Planner-owned input need with exact source provenance."""

    model_config = ConfigDict(extra="forbid")

    owner: Literal["fast_planner"] = "fast_planner"
    source_kind: PlannerInformationGapSource
    source_reference: str = Field(min_length=1, max_length=500)
    resolution_sources_considered: list[PlannerInformationSource] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("source_reference", mode="before")
    @classmethod
    def normalize_source_reference(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_planner_gap(self) -> "PlannerInformationGap":
        if not self.blocking or self.resolved:
            raise ValueError(
                "clarification InformationGap must be blocking and unresolved"
            )
        if self.preferred_resolution != "ask_user":
            raise ValueError(
                "clarification InformationGap must select preferred_resolution=ask_user"
            )
        if not self.required_for:
            raise ValueError(
                "Planner InformationGap must name at least one required input"
            )
        if "authoritative_context" not in self.resolution_sources_considered:
            raise ValueError(
                "Planner clarification must first consider authoritative context"
            )
        if self.source_kind == "execution_input" and (
            "capability_schema" not in self.resolution_sources_considered
        ):
            raise ValueError(
                "execution-input clarification must inspect the Capability schema"
            )
        return self


class FastPlannerClarificationAct(_FastPlannerCommunicativeActBase):
    """A Planner-selected question carrying its owned input-need records."""

    role: Literal["clarification"]
    speech_act: FastClarificationSpeechAct = "ask_clarification"
    truth_stage: Literal["context_grounded"] = "context_grounded"
    evidence_refs: list[str] = Field(default_factory=list, max_length=0)
    information_gaps: list[PlannerInformationGap] = Field(min_length=1, max_length=8)

    @field_validator("information_gaps", mode="after")
    @classmethod
    def unique_information_gap_ids(
        cls,
        value: list[PlannerInformationGap],
    ) -> list[PlannerInformationGap]:
        ids = [item.gap_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Planner InformationGap IDs must be unique")
        return value


class FastPlannerProgressAct(_FastPlannerCommunicativeActBase):
    """Planner-authored prospective communication before fresh Evidence exists."""

    role: Literal["progress"]
    truth_stage: Literal["pre_evidence"] = "pre_evidence"
    evidence_refs: list[str] = Field(default_factory=list, max_length=0)
    progress_kind: FastProgressKind
    speech_act: str = Field(
        default="acknowledge",
        json_schema_extra={
            "enum": ["acknowledge", "acknowledge_and_check", "thinking"]
        },
    )

    @model_validator(mode="before")
    @classmethod
    def bind_progress_kind_to_safe_speech_act(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        progress_kind = normalized.get("progress_kind")
        expected = _FAST_PROGRESS_SPEECH_ACT_BY_KIND.get(
            cast(FastProgressKind, progress_kind)
        )
        if expected is None:
            return normalized
        supplied = normalized.get("speech_act")
        if supplied not in (None, "") and supplied != expected:
            raise ValueError(
                "Fast Planner progress speech_act must match progress_kind"
            )
        normalized["speech_act"] = expected
        return normalized


class FastPlannerCapabilityActivity(CapabilityIdentityModel):
    """One Fast-Planner-authored executable Activity over Responsibility evidence."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["capability"]
    activity_id: str = Field(min_length=1, max_length=160)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: PlanTiming = "sequential"
    source_responsibility_refs: list[str] = Field(min_length=1)
    reason_summary: str = ""

    @field_validator("activity_id", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("source_responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("args")
    @classmethod
    def reject_low_level_args(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class PlannedCommunicativeAct(BaseModel):
    """Goal-bound exact communication selected and worded by Planner."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=2400)
    role: FastCommunicativeActRole
    timing: PlanTiming = "parallel"
    speech_act: FastCommunicativeSpeechAct
    source_goal_ids: list[str] = Field(min_length=1)
    source_responsibility_refs: list[str] = Field(default_factory=list)
    truth_stage: CommunicativeTruthStage = "context_grounded"
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)
    information_gaps: list[PlannerInformationGap] = Field(default_factory=list, max_length=8)
    progress_kind: FastProgressKind | None = None

    @field_validator("activity_id", "text", "speech_act", mode="before")
    @classmethod
    def normalize_act_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator(
        "source_goal_ids",
        "source_responsibility_refs",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def normalize_act_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @model_validator(mode="after")
    def validate_role_fields(self) -> "PlannedCommunicativeAct":
        if self.truth_stage == "pre_evidence" and self.evidence_refs:
            raise ValueError("pre-evidence communication must not reference Evidence")
        if self.truth_stage == "post_evidence" and not self.evidence_refs:
            raise ValueError("post-evidence communication requires Evidence refs")
        if self.role == "progress" and self.truth_stage != "pre_evidence":
            raise ValueError("progress Communicative Acts must be pre-evidence")
        if self.role == "clarification" and self.truth_stage != "context_grounded":
            raise ValueError("clarification Communicative Acts must be context-grounded")
        if self.role == "complete_response" and self.speech_act not in {
            "acknowledge",
            "answer",
            "apologize",
            "explain",
            "farewell",
            "greeting",
            "inform",
            "respond",
            "support",
            "thank",
        }:
            raise ValueError(
                "complete-response Communicative Act requires a complete-response function"
            )
        if self.role == "clarification" and self.speech_act != "ask_clarification":
            raise ValueError(
                "clarification Communicative Act requires ask_clarification"
            )
        if self.role == "progress" and self.speech_act not in {
            "acknowledge",
            "acknowledge_and_check",
            "thinking",
        }:
            raise ValueError("progress Communicative Act requires a progress function")
        if self.role == "progress" and self.progress_kind is None:
            raise ValueError("progress Communicative Act requires progress_kind")
        if self.role != "progress" and self.progress_kind is not None:
            raise ValueError("only progress Communicative Acts carry progress_kind")
        if self.role == "clarification" and not self.information_gaps:
            raise ValueError(
                "clarification Communicative Act requires Planner InformationGaps"
            )
        if self.role != "clarification" and self.information_gaps:
            raise ValueError(
                "only clarification Communicative Acts carry Planner InformationGaps"
            )
        return self


FastPlannerCommunicativeAct = Annotated[
    Union[
        FastPlannerCompleteResponseAct,
        FastPlannerProgressAct,
        FastPlannerClarificationAct,
    ],
    Field(discriminator="role"),
]

FastPlannerImmediateCommunicativeAct = Annotated[
    Union[
        FastPlannerCompleteResponseAct,
        FastPlannerProgressAct,
    ],
    Field(discriminator="role"),
]


class FastPlannerFirstResponseModelOutput(BaseModel):
    """Minimal model payload for Fast Planner's first-response latency phase.

    ``activity=None`` is a first-class Planner decision: if no still-needed
    user-facing semantic delta exists yet, silence is correct.
    """

    model_config = ConfigDict(extra="forbid")

    activity: FastPlannerImmediateCommunicativeAct | None = None


class FastPlannerFirstResponse(BaseModel):
    """Fast Planner's earliest independently realizable communicative decision.

    This is a latency phase of Fast Planner, not a response-composition owner.
    It carries the exact immutable wording that Runtime may start while the same
    Planner continues Capability/clarification planning and Goal Association
    independently commits canonical Goal state.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    turn_id: str = Field(min_length=1, max_length=160)
    planner_tier: Literal["fast"] = "fast"
    activity: FastPlannerImmediateCommunicativeAct | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", mode="before")
    @classmethod
    def normalize_turn_id(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("metadata")
    @classmethod
    def reject_first_response_low_level_metadata(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

FastPlannerActivity = Annotated[
    Union[
        FastPlannerCompleteResponseAct,
        FastPlannerProgressAct,
        FastPlannerClarificationAct,
        FastPlannerCapabilityActivity,
    ],
    Field(discriminator="role"),
]

# Fresh-evidence Responsibilities cannot be completed before new Evidence exists.
# Encode that known truth in the decoder contract itself so Goal Progress
# Communication can still choose progress/clarification without offering an
# impossible complete_response branch and discarding useful communication after
# inference.
# When WHAT is already confident, fresh Evidence forbids a complete response. The
# remaining honest branches include progress, applicable Capability work, or a
# Planner-owned clarification for a real unresolved execution input.
FastPlannerFreshEvidenceCommunicativeAct = FastPlannerProgressAct

FastPlannerFreshEvidenceClarifiableCommunicativeAct = Annotated[
    Union[
        FastPlannerProgressAct,
        FastPlannerClarificationAct,
    ],
    Field(discriminator="role"),
]


def fast_planner_activity_request_id(turn_id: str, activity_id: str) -> str:
    """Return the stable Runtime request identity for one Fast Activity."""

    digest = hashlib.sha256(
        f"{turn_id}|{activity_id}".encode("utf-8")
    ).hexdigest()[:20]
    return f"fastreq_{digest}"


class FastPlannerAdvance(BaseModel):
    """Fast Planner's first Activity Plan over Goal Interpretation evidence.

    Goal Interpretation owns contextual WHAT. This contract is the first
    planner-owned HOW decision and may contain speaking and Capability Activities
    with the same sequential/parallel relation. Goal Association runs independently
    from the same GI result; it is not a Planner continuation. Runtime safety,
    confirmation, and authorization still decide whether an Activity may start.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    turn_id: str = Field(min_length=1, max_length=160)
    planner_tier: Literal["fast"] = "fast"
    disposition: PlanDisposition
    coverage: PlanCoverage
    covered_responsibility_refs: list[str] = Field(default_factory=list)
    activities: list[FastPlannerActivity] = Field(default_factory=list, max_length=24)
    continuations: list[FastPlannerContinuation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "reason_summary", mode="before")
    @classmethod
    def normalize_advance_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

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
        if self.disposition == "escalate" and "deep_planner" not in self.continuations:
            raise ValueError("Fast Planner escalation requires Deep Planner continuation")
        if "deep_planner" in self.continuations and self.disposition != "escalate":
            raise ValueError("Deep Planner continuation requires disposition=escalate")
        if self.disposition in {"execute", "mixed"} and not any(
            item.role == "capability" for item in self.activities
        ):
            raise ValueError("executable Fast Planner disposition requires a Capability Activity")
        if self.disposition == "respond" and not any(
            item.role == "complete_response" for item in self.activities
        ):
            raise ValueError("respond disposition requires a complete-response Activity")
        if self.disposition == "clarify" and not any(
            item.role == "clarification" for item in self.activities
        ):
            raise ValueError("clarify disposition requires a clarification Activity")
        if self.disposition == "escalate" and any(
            item.role == "capability" for item in self.activities
        ):
            raise ValueError("escalating Fast Planner output must not carry Capability Activities")
        if self.coverage != "complete" and self.disposition not in {
            "clarify",
            "escalate",
            "unavailable",
            "refused",
        }:
            raise ValueError(
                "non-complete Fast Planner output must clarify, escalate, report "
                "unavailable, or refuse"
            )
        activity_ids = [item.activity_id for item in self.activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("Fast Planner Activity IDs must be unique")
        for activity in self.activities:
            unknown = set(activity.source_responsibility_refs) - set(
                self.covered_responsibility_refs
            )
            if unknown:
                raise ValueError(
                    "Fast Planner Activity references uncovered Responsibility refs: "
                    + ",".join(sorted(unknown))
                )
        activity_roles_by_ref: dict[str, set[str]] = {}
        for activity in self.activities:
            for responsibility_ref in activity.source_responsibility_refs:
                activity_roles_by_ref.setdefault(responsibility_ref, set()).add(
                    activity.role
                )
        for responsibility_ref, roles in activity_roles_by_ref.items():
            terminal_roles = roles.intersection(
                {"capability", "complete_response", "clarification"}
            )
            if len(terminal_roles) > 1:
                raise ValueError(
                    "one Responsibility cannot have conflicting terminal Fast "
                    f"Planner Activities: {responsibility_ref}={sorted(terminal_roles)}"
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

    disposition: PlanDisposition
    coverage: PlanCoverage
    covered_responsibility_refs: list[str]
    activities: list[FastPlannerActivity]
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
        return normalize_whitespace(value)


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
        return normalize_whitespace(value)

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
        return normalize_whitespace(value)

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


class PlannedGoalTimeCondition(BaseModel):
    """Planner-authored semantic wake condition before Host provenance binding.

    Planner owns *when* an existing Goal should become cognitively ready again.
    Host adds the canonical Plan ID and original Responsibility provenance only
    when persisting the condition; it never parses free-form Goal text into time
    semantics.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str = Field(min_length=1, max_length=200)
    goal_id: str = Field(min_length=1, max_length=160)
    due_at_ms: int = Field(ge=1)
    reason_code: str = Field(
        default="planner_time_condition", min_length=1, max_length=120
    )

    @field_validator("condition_id", "goal_id", "reason_code", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)


class CanonicalPlanStep(CapabilityIdentityModel):
    """One canonical executable Capability step in a Plan."""

    step_id: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    timing: PlanTiming = "sequential"
    source_goal_ids: list[str] = Field(default_factory=list)
    reuse_activity_id: str = ""
    step_purpose: PlanStepPurpose = "achieve_effect"
    expected_outcome: str = Field(default="", max_length=600)
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "step_id", "reuse_activity_id", "expected_outcome", "reason_summary", mode="before"
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @field_validator("source_goal_ids", mode="before")
    @classmethod
    def normalize_source_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("args", "metadata")
    @classmethod
    def reject_low_level_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_step_expectation(self) -> "CanonicalPlanStep":
        if self.step_purpose == "acquire_information" and not self.expected_outcome:
            raise ValueError(
                "information-acquisition steps require an expected_outcome describing "
                "the observation needed for progress"
            )
        return self


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
        return normalize_whitespace(value)

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
    response_text: str = ""

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
    communicative_acts: list[PlannedCommunicativeAct] = Field(
        default_factory=list,
        max_length=24,
    )
    steps: list[CanonicalPlanStep] = Field(default_factory=list)
    escalation_reason: str = ""
    unresolved: list[str] = Field(default_factory=list)
    parameter_resolutions: list[PlanParameterResolution] = Field(default_factory=list)
    time_conditions: list[PlannedGoalTimeCondition] = Field(
        default_factory=list, max_length=16
    )
    goal_outcomes: list[GoalPlanOutcome] = Field(default_factory=list)
    goal_satisfaction: GoalSatisfactionAssessment | None = None
    selected_agent_skills: list[PlanAgentSkillProvenance] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("plan_id", "goal_summary", "response_text", "escalation_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

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
                if self.disposition not in {"escalate", "clarify"}:
                    raise ValueError(
                        "partial or uncertain fast plans must clarify or escalate"
                    )
                if self.disposition == "escalate" and not self.escalation_reason:
                    raise ValueError("escalating plans require escalation_reason")
            elif self.disposition not in {"clarify", "unavailable", "refused"}:
                raise ValueError("non-complete deep plans must clarify, report unavailable, or refuse")
        if self.planner_tier == "deep" and self.disposition == "escalate":
            raise ValueError("deep plans cannot return to the fast planner")
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute disposition requires at least one step")
        if self.disposition == "mixed" and not self.steps:
            raise ValueError("mixed disposition requires at least one executable step")
        if self.disposition == "respond" and not (
            self.response_text
            or any(item.role == "complete_response" for item in self.communicative_acts)
        ):
            raise ValueError(
                "respond disposition requires response_text or a complete-response "
                "Communicative Act"
            )
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
        condition_ids = [item.condition_id for item in self.time_conditions]
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("time condition IDs must be unique")
        unknown_time_goals = {
            item.goal_id for item in self.time_conditions
        } - goal_id_set
        if unknown_time_goals:
            raise ValueError(
                "time conditions reference unknown Goal IDs: "
                + ",".join(sorted(unknown_time_goals))
            )
        if self.time_conditions and self.disposition not in {"execute", "mixed"}:
            raise ValueError(
                "time conditions require executable Work with future Goal readiness"
            )
        communicative_act_ids = [
            item.activity_id for item in self.communicative_acts
        ]
        if len(communicative_act_ids) != len(set(communicative_act_ids)):
            raise ValueError("Canonical Plan Communicative Act IDs must be unique")
        for act in self.communicative_acts:
            unknown_act_goals = set(act.source_goal_ids) - goal_id_set
            if unknown_act_goals:
                raise ValueError(
                    "Communicative Act references unknown Goal IDs: "
                    + ",".join(sorted(unknown_act_goals))
                )
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

            for outcome in self.goal_outcomes:
                if outcome.disposition == "respond" and not (
                    outcome.response_text
                    or any(
                        act.role == "complete_response"
                        and outcome.goal_id in act.source_goal_ids
                        for act in self.communicative_acts
                    )
                ):
                    raise ValueError(
                        "respond goal outcome requires response_text or a matching "
                        "Communicative Act"
                    )

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
            nonexecuting_time_goals = {
                item.goal_id
                for item in self.time_conditions
                if outcome_by_goal[item.goal_id].disposition != "execute"
            }
            if nonexecuting_time_goals:
                raise ValueError(
                    "time conditions may only bind execute goal outcomes: "
                    + ",".join(sorted(nonexecuting_time_goals))
                )

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
                unsupported = dispositions - {"execute", "respond", "clarify"}
                if unsupported:
                    raise ValueError(
                        "fast mixed plans may contain only execute, respond, and "
                        "clarify outcomes: "
                        + ",".join(sorted(unsupported))
                    )
        return self


def canonical_plan_fingerprint(plan: CanonicalPlan) -> str:
    """Stable fingerprint of the immutable CanonicalPlan prompt projection."""

    payload = json.dumps(
        plan.prompt_projection(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
