from __future__ import annotations

import copy
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from chromie_contracts.interaction import CapabilityIdentityModel
    from chromie_contracts.text import normalize_whitespace
    from chromie_contracts.plan import (
        GoalOutcomeDisposition,
        GoalSatisfactionAssessment,
        GoalSatisfactionStatus,
        AuxiliaryPlanActivity,
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlannedGoalTimeCondition,
        PlanStepPurpose,
        PlanTiming,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.interaction import CapabilityIdentityModel
    from shared.chromie_contracts.text import normalize_whitespace
    from shared.chromie_contracts.plan import (
        GoalOutcomeDisposition,
        GoalSatisfactionAssessment,
        GoalSatisfactionStatus,
        AuxiliaryPlanActivity,
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlannedGoalTimeCondition,
        PlanStepPurpose,
        PlanTiming,
    )

PlannerTier = Literal["fast", "deep"]
PlannerPlanRelation = Literal["exact", "safe_adjustment", "alternative"]

NON_PLANNER_TRANSPORT_CAPABILITY_IDS = frozenset({"chromie.speak"})
DETERMINISTIC_CONTROL_CAPABILITY_IDS = frozenset({"soridormi.stop"})

def is_planner_step_capability(capability_id: str) -> bool:
    normalized = str(capability_id or "").strip()
    return normalized not in (
        NON_PLANNER_TRANSPORT_CAPABILITY_IDS
        | DETERMINISTIC_CONTROL_CAPABILITY_IDS
    )

class PlannerModelStep(CapabilityIdentityModel):
    """Semantic plan leaf returned by a planner model.

    Step ownership and arguments are model judgments.  They intentionally have
    no host default at this boundary; otherwise a missing multi-goal ownership
    decision can silently authorize one step for every active goal.
    """

    step_id: str = ""
    args: dict[str, Any]
    timing: PlanTiming = "sequential"
    source_goal_ids: list[str] = Field(default_factory=list)
    reuse_activity_id: str = ""
    step_purpose: PlanStepPurpose = "achieve_effect"
    expected_outcome: str = Field(default="", max_length=600)
    reason_summary: str = ""

    @field_validator("step_id", "reuse_activity_id", "expected_outcome", "reason_summary", mode="before")
    @classmethod
    def normalize_step_text(cls, value: Any) -> Any:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_information_acquisition_expectation(self) -> "PlannerModelStep":
        if self.step_purpose == "acquire_information" and not self.expected_outcome:
            raise ValueError(
                "information-acquisition steps require expected_outcome"
            )
        return self

class PlannerGoalSatisfaction(GoalSatisfactionAssessment):
    """Prospective adequacy of the proposed plan, not execution progress."""

    @model_validator(mode="before")
    @classmethod
    def normalize_redundant_status(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        score = normalized.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            numeric = float(score)
            normalized["status"] = (
                "exact"
                if numeric >= 0.95
                else "substantial"
                if numeric >= 0.75
                else "partial"
                if numeric > 0.0
                else "unsatisfied"
            )
        return normalized

    score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How fully the proposed plan would satisfy the canonical goals if "
            "its steps and responses complete successfully. This is not a "
            "measurement of whether execution has already happened."
        ),
    )
    status: GoalSatisfactionStatus = Field(
        description=(
            "Prospective plan-adequacy band. Use exact with score 0.95-1.0 when "
            "the proposed plan fully covers the goals, even though execution is pending."
        )
    )
    satisfied_goal_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Canonical goals the proposed plan is designed to satisfy after "
            "successful execution or response."
        ),
    )
    unmet_goal_ids: list[str] = Field(
        default_factory=list,
        description="Canonical goals for which the proposed plan still has a planning gap.",
    )
    unmet_requirements: list[str] = Field(
        default_factory=list,
        description=(
            "Requirements not covered by the proposed plan; pending execution "
            "alone is not an unmet planning requirement."
        ),
    )

class PlannerModelGoalOutcome(BaseModel):
    """One goal-specific model judgment keyed by its host-authoritative ID.

    The enclosing JSON object supplies the goal ID as a unique key.  Keeping
    that ID out of the value prevents a decoder from emitting duplicate or
    conflicting per-goal identifiers while preserving the model's semantic
    responsibility for disposition, coverage, response text, and step links.
    """

    model_config = ConfigDict(extra="forbid")

    disposition: GoalOutcomeDisposition
    coverage: PlanCoverage
    response_text: str = ""
    unresolved: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    satisfaction: PlannerGoalSatisfaction | None = None
    rationale: str = ""

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> "PlannerModelGoalOutcome":
        if self.disposition == "execute":
            if self.coverage != "complete" or not self.step_ids:
                raise ValueError("execute goal outcome requires complete coverage and step_ids")
            if self.unresolved:
                raise ValueError("execute goal outcome must not retain unresolved work")
        elif self.disposition == "respond":
            if self.coverage != "complete" or not self.response_text.strip():
                raise ValueError(
                    "respond goal outcome requires complete coverage and response_text"
                )
            if self.step_ids:
                raise ValueError("respond goal outcome must not reference steps")
            if self.unresolved:
                raise ValueError("respond goal outcome must not retain unresolved work")
        elif self.disposition == "escalate":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError("escalate goal outcome requires partial or uncertain coverage")
            if self.step_ids:
                raise ValueError("escalate goal outcome must not reference steps")
            if self.response_text.strip():
                raise ValueError("escalate goal outcome must not claim a conversational answer")
            if not self.unresolved and not self.rationale.strip():
                raise ValueError("escalate goal outcome requires an unresolved need or rationale")
        elif self.disposition == "clarify":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError("clarify goal outcome requires partial or uncertain coverage")
            if self.step_ids:
                raise ValueError("clarify goal outcome must not reference steps")
            if not self.unresolved and not self.response_text.strip():
                raise ValueError(
                    "clarify goal outcome requires an unresolved need or response_text"
                )
        elif self.step_ids:
            raise ValueError(
                "unavailable and refused goal outcomes must not reference steps"
            )
        return self

class PlannerModelTimeCondition(BaseModel):
    """Model-facing time readiness authored by the same Planner that owns HOW."""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1, max_length=160)
    due_at_ms: int = Field(ge=1)
    reason_code: str = Field(
        default="planner_time_condition", min_length=1, max_length=120
    )

    @field_validator("goal_id", "reason_code", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return normalize_whitespace(value)


class PlannerModelOutput(BaseModel):
    """Flat model-facing planner DTO.

    Canonical envelope fields (plan ID, planner tier, schema version, and the
    authoritative top-level goal IDs) are added by the host after this DTO is
    validated.  Keeping the DTO flat is deliberate: the deployed Ollama
    structured decoder selected a top-level ``oneOf`` branch without applying
    the surrounding CanonicalPlan requirements.
    """

    model_config = ConfigDict(extra="forbid")

    disposition: PlanDisposition
    coverage: PlanCoverage
    confidence: float = Field(ge=0.0, le=1.0)
    goal_summary: str = ""
    response_text: str = ""
    steps: list[PlannerModelStep] = Field(default_factory=list)
    auxiliary_activities: list[AuxiliaryPlanActivity] = Field(
        default_factory=list,
        max_length=3,
    )
    escalation_reason: str = ""
    unresolved: list[str] = Field(default_factory=list)
    parameter_resolutions: list[PlanParameterResolution] = Field(default_factory=list)
    time_conditions: list[PlannerModelTimeCondition] = Field(
        default_factory=list, max_length=16
    )
    goal_outcomes: dict[str, PlannerModelGoalOutcome] = Field(default_factory=dict)
    goal_satisfaction: PlannerGoalSatisfaction | None = None
    plan_relation: PlannerPlanRelation = "exact"
    user_confirmation_required: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_decoder_compatibility(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = copy.deepcopy(value)
        outcomes = normalized.get("goal_outcomes")
        if (
            normalized.get("disposition") in {"execute", "mixed"}
            and normalized.get("response_text") is None
        ):
            normalized["response_text"] = ""
        if isinstance(outcomes, dict):
            for outcome_value in outcomes.values():
                if (
                    isinstance(outcome_value, dict)
                    and outcome_value.get("disposition") == "execute"
                    and outcome_value.get("response_text") is None
                ):
                    # Some structured decoders use JSON null for the semantic
                    # absence that the execute-outcome contract represents as
                    # an empty string.  This normalization carries no planning
                    # judgment; non-execute response text remains strict.
                    outcome_value["response_text"] = ""
        if not isinstance(outcomes, dict) or len(outcomes) != 1:
            return normalized
        outcome = next(iter(outcomes.values()))
        if not isinstance(outcome, dict):
            return normalized
        if normalized.get("disposition") == "clarify" and outcome.get("disposition") == "clarify":
            if not str(outcome.get("response_text") or "").strip():
                response_text = str(normalized.get("response_text") or "").strip()
                if response_text:
                    outcome["response_text"] = response_text
            if not outcome.get("unresolved"):
                unresolved = normalized.get("unresolved")
                if isinstance(unresolved, list) and unresolved:
                    outcome["unresolved"] = list(unresolved)
        return normalized

    @model_validator(mode="after")
    def validate_semantic_shape(self) -> "PlannerModelOutput":
        response_transport_steps = [
            step.capability_id
            for step in self.steps
            if not is_planner_step_capability(step.capability_id)
        ]
        if response_transport_steps:
            raise ValueError(
                "generic response transport or deterministic operational control is not an "
                "executable model-authored task-plan capability; represent conversation "
                "with respond outcomes and route stop/cancel through deterministic control: "
                + ",".join(response_transport_steps)
            )
        if self.coverage != "complete" and self.steps:
            raise ValueError("non-complete planner output must not carry executable steps")
        if self.disposition == "escalate" and self.auxiliary_activities:
            raise ValueError(
                "an escalating Planner result cannot author auxiliary Activities"
            )
        step_ids = {step.step_id for step in self.steps if step.step_id}
        primary_capability_ids = {step.capability_id for step in self.steps}
        auxiliary_ids = [
            item.auxiliary_activity_id for item in self.auxiliary_activities
        ]
        if len(auxiliary_ids) != len(set(auxiliary_ids)):
            raise ValueError("Planner auxiliary Activity IDs must be unique")
        for auxiliary in self.auxiliary_activities:
            if auxiliary.anchor_kind == "plan_step" and auxiliary.anchor_id not in step_ids:
                raise ValueError(
                    "Planner auxiliary Activity references an unknown plan step"
                )
            if auxiliary.anchor_kind == "communicative_act":
                raise ValueError(
                    "flat Planner output has no communicative-act identity; use "
                    "anchor_kind=plan_response for response_text"
                )
            if auxiliary.anchor_kind == "plan_response" and (
                auxiliary.anchor_id != "response" or not self.response_text.strip()
            ):
                raise ValueError(
                    "plan_response auxiliary Activity requires anchor_id=response "
                    "and Planner-owned response_text"
                )
            if auxiliary.capability_id in primary_capability_ids:
                raise ValueError(
                    "an auxiliary Activity cannot duplicate a primary Plan Capability"
                )
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute planner output requires at least one step")
        if self.disposition == "mixed" and (not self.steps or not self.goal_outcomes):
            raise ValueError("mixed planner output requires steps and goal_outcomes")
        if self.disposition == "respond" and not self.response_text.strip():
            raise ValueError("respond planner output requires response_text")
        if self.disposition in {"clarify", "unavailable", "refused"} and not (
            self.response_text.strip()
            or any(
                outcome.response_text.strip()
                for outcome in self.goal_outcomes.values()
            )
        ):
            raise ValueError(
                f"{self.disposition} planner output requires exact "
                "Planner-owned response_text"
            )
        if self.disposition not in {"execute", "mixed"} and self.steps:
            raise ValueError(f"{self.disposition} planner output must not carry executable steps")
        if self.disposition == "escalate" and not self.escalation_reason.strip():
            raise ValueError("escalate planner output requires escalation_reason")
        if self.disposition in {"execute", "respond", "mixed"}:
            if self.coverage != "complete":
                raise ValueError(
                    "execute, respond, and mixed planner output requires complete coverage"
                )
            if self.disposition in {"execute", "respond"} and self.unresolved:
                raise ValueError(
                    "complete execute or respond planner output must not retain "
                    "unresolved work"
                )
            if self.goal_satisfaction is None:
                raise ValueError(
                    "complete executable or response output requires goal_satisfaction"
                )
        if self.plan_relation in {"safe_adjustment", "alternative"}:
            if self.disposition not in {"execute", "mixed"}:
                raise ValueError("safe-adjusted and alternative plans must be executable")
            if not self.user_confirmation_required:
                raise ValueError("safe-adjusted and alternative plans require user confirmation")
            if not self.response_text.strip():
                raise ValueError(
                    "safe-adjusted and alternative plans require response_text "
                    "explaining the material change"
                )
        elif self.user_confirmation_required and self.disposition not in {
            "execute",
            "mixed",
        }:
            raise ValueError("planner-requested confirmation is valid only for executable plans")
        if self.time_conditions and self.disposition not in {"execute", "mixed"}:
            raise ValueError(
                "time conditions require executable Work that leaves a Goal live until future readiness"
            )
        if self.goal_outcomes:
            outcome_goal_ids = set(self.goal_outcomes)
            foreign_time_goals = {
                item.goal_id for item in self.time_conditions
            } - outcome_goal_ids
            if foreign_time_goals:
                raise ValueError(
                    "time conditions reference goals outside goal_outcomes: "
                    + ",".join(sorted(foreign_time_goals))
                )
            nonexecuting_time_goals = {
                item.goal_id
                for item in self.time_conditions
                if self.goal_outcomes[item.goal_id].disposition != "execute"
            }
            if nonexecuting_time_goals:
                raise ValueError(
                    "time conditions may only bind execute goal outcomes: "
                    + ",".join(sorted(nonexecuting_time_goals))
                )
            outcome_dispositions = {item.disposition for item in self.goal_outcomes.values()}
            expected_disposition = (
                "mixed" if len(outcome_dispositions) > 1 else next(iter(outcome_dispositions))
            )
            if self.disposition != expected_disposition:
                raise ValueError("top-level disposition must match per-goal outcome dispositions")
        return self

class PlannerDTOContractError(ValueError):
    """Planner output is mechanically malformed or internally inconsistent.

    This error is the only same-tier regeneration trigger. Semantic grounding,
    capability coverage, responsibility, evidence, and safety failures must not
    be rewritten by the same planner tier.
    """

class ResourceResponsibilityCapabilityGroundingError(ValueError):
    """A selected Capability does not satisfy a typed resource contract."""

    def __init__(
        self,
        message: str,
        *,
        goal_id: str = "",
        complete_capability_ids: list[str] | None = None,
    ) -> None:
        self.goal_id = goal_id
        self.complete_capability_ids = list(complete_capability_ids or [])
        super().__init__(message)

class ResourceResponsibilityCapabilityUnavailableError(
    ResourceResponsibilityCapabilityGroundingError
):
    """No supplied Capability set declares enough typed resource coverage."""

class ResourceResponsibilityRequiresCompositionError(
    ResourceResponsibilityCapabilityGroundingError
):
    """The Goal is coverable only by composing multiple advertised capabilities."""

def materialize_planner_metadata(output: PlannerModelOutput) -> dict[str, Any]:
    """Materialize narrow model judgments into the host canonical envelope."""

    return {
        "plan_relation": output.plan_relation,
        "user_confirmation_required": output.user_confirmation_required,
    }

def materialize_goal_outcomes(
    output: PlannerModelOutput,
    *,
    expected_goal_ids_for_turn: list[str],
) -> list[dict[str, Any]]:
    """Build canonical list outcomes from the model's unique keyed map."""

    if not output.goal_outcomes:
        return []
    ordered_ids = list(expected_goal_ids_for_turn)
    if not ordered_ids:
        ordered_ids = list(output.goal_outcomes)
    return [
        {
            "goal_id": goal_id,
            **output.goal_outcomes[goal_id].model_dump(mode="python"),
        }
        for goal_id in ordered_ids
    ]

def stable_plan_id(request: Any, planner_tier: PlannerTier) -> str:
    """Return the stable host-owned Plan ID for one Planner pass."""

    digest = hashlib.sha256(
        f"{request.sid or 'turn'}|{planner_tier}|{request.text}".encode()
    ).hexdigest()[:20]
    return f"plan_{digest}"


def materialize_planner_output(
    model_output: PlannerModelOutput,
    *,
    planner_tier: PlannerTier,
    plan_id: str,
    expected_goal_ids_for_turn: list[str],
    goal_summary_fallback: str,
    fast_multi_goal_contract: bool = False,
) -> dict[str, Any]:
    """Materialize only host-owned CanonicalPlan envelope and redundant mechanics."""

    out = model_output.model_dump(mode="python")
    out.pop("plan_relation", None)
    out.pop("user_confirmation_required", None)
    out["goal_outcomes"] = materialize_goal_outcomes(
        model_output,
        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
    )
    out["plan_id"] = plan_id
    out["planner_tier"] = planner_tier
    out["goal_ids"] = list(expected_goal_ids_for_turn)
    expected_goal_set = set(expected_goal_ids_for_turn)
    planned_time_conditions: list[dict[str, Any]] = []
    for index, condition in enumerate(model_output.time_conditions):
        if condition.goal_id not in expected_goal_set:
            raise PlannerDTOContractError(
                "time condition references a non-authoritative Goal ID: "
                + condition.goal_id
            )
        planned_time_conditions.append(
            PlannedGoalTimeCondition(
                condition_id=f"{plan_id}:time:{index}",
                goal_id=condition.goal_id,
                due_at_ms=condition.due_at_ms,
                reason_code=condition.reason_code,
            ).model_dump(mode="python")
        )
    out["time_conditions"] = planned_time_conditions

    if planner_tier == "fast" and fast_multi_goal_contract:
        metadata = materialize_planner_metadata(model_output)
        metadata.update(
            {
                "model_contract": "FastPlannerMultiGoalPlanOutput",
                "semantic_authority": "fast_planner_model",
                "model_authored_steps": True,
                "model_authored_step_ids": True,
                "model_authored_step_ownership": True,
                "model_authored_goal_outcomes": True,
                "model_authored_goal_satisfaction": True,
                "host_semantic_compilation": False,
            }
        )
        out["metadata"] = metadata
        return out

    steps = out.get("steps")
    if isinstance(steps, dict):
        steps = [steps]
    if not isinstance(steps, list):
        steps = []
    normalized_steps: list[dict[str, Any]] = []
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            continue
        step = dict(item)
        if not step.get("step_id"):
            step["step_id"] = f"{plan_id}:step:{index}"
        normalized_steps.append(step)
    if (
        planner_tier == "deep"
        and len(normalized_steps) == 1
        and normalized_steps[0].get("timing") == "parallel"
    ):
        normalized_steps[0]["timing"] = "sequential"
    out["steps"] = normalized_steps
    out.setdefault("coverage", "uncertain")
    out.setdefault("disposition", "escalate" if planner_tier == "fast" else "clarify")
    out.setdefault("confidence", 0.0)
    out.setdefault("goal_summary", goal_summary_fallback)
    out.setdefault("response_text", "")
    out.setdefault("escalation_reason", "")
    out.setdefault("unresolved", [])
    out.setdefault("parameter_resolutions", [])
    out.setdefault("time_conditions", [])
    out.setdefault("goal_outcomes", [])
    out.setdefault("goal_satisfaction", None)
    out["metadata"] = materialize_planner_metadata(model_output)
    return out
