from __future__ import annotations

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
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlannedGoalTimeCondition,
        SocialCommunicationNeed,
        communication_need_id,
        PlanStepPurpose,
        PlanTiming,
        validate_acquisition_stage_isolation,
        validate_goal_satisfaction_conservation,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.interaction import CapabilityIdentityModel
    from shared.chromie_contracts.text import normalize_whitespace
    from shared.chromie_contracts.plan import (
        GoalOutcomeDisposition,
        GoalSatisfactionAssessment,
        GoalSatisfactionStatus,
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlannedGoalTimeCondition,
        SocialCommunicationNeed,
        communication_need_id,
        PlanStepPurpose,
        PlanTiming,
        validate_acquisition_stage_isolation,
        validate_goal_satisfaction_conservation,
    )

PlannerTier = Literal["fast", "deep"]
PlannerPlanRelation = Literal["exact", "safe_adjustment", "alternative"]

NON_PLANNER_TRANSPORT_CAPABILITY_IDS = frozenset({"chromie.speak"})
DETERMINISTIC_CONTROL_CAPABILITY_IDS = frozenset({"soridormi.stop"})
PLANNER_LIBRARY_INTROSPECTION_SUFFIXES = (".get_capabilities", ".skill.list")
# Provider-native plan compilation/execution is a realization detail beneath an
# already selected semantic Capability. The trusted adapter may call these tools;
# Planner must not choose or detail-lookup them as user Work.
PLANNER_PROVIDER_REALIZATION_SUFFIXES = (
    ".skill.create_plan",
    ".skill.execute_plan",
    ".activity.compile",
    ".activity.execute",
    ".activity.status",
    ".motion.create_plan",
    ".motion.execute_plan",
)

def is_planner_step_capability(capability_id: str) -> bool:
    normalized = str(capability_id or "").strip()
    if normalized in (
        NON_PLANNER_TRANSPORT_CAPABILITY_IDS
        | DETERMINISTIC_CONTROL_CAPABILITY_IDS
    ):
        return False
    # Fast Planner already receives a current provider-neutral Capability index
    # and has one bounded exact-detail lookup. Executing a provider's own catalog
    # introspection or realization pipeline adds a redundant model round trip and
    # creates no user Work.
    return not normalized.endswith(
        PLANNER_LIBRARY_INTROSPECTION_SUFFIXES
        + PLANNER_PROVIDER_REALIZATION_SUFFIXES
    )

class PlannerModelStep(CapabilityIdentityModel):
    """Semantic plan leaf returned by a planner model.

    Step ownership and arguments are model judgments.  They intentionally have
    no host default at this boundary; otherwise a missing multi-goal ownership
    decision can silently authorize one step for every active goal.
    """

    step_id: str = Field(min_length=1, max_length=160)
    args: dict[str, Any]
    timing: PlanTiming
    source_goal_ids: list[str] = Field(min_length=1)
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

    score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How fully the proposed plan would satisfy the canonical goals if "
            "its steps and responses complete successfully. This is not a "
            "measurement of whether execution has already happened. A complete current "
            "acquisition stage may have partial whole-Goal adequacy; retain deferred "
            "requirements in both per-Goal and aggregate satisfaction."
        ),
    )
    status: GoalSatisfactionStatus = Field(
        description=(
            "Prospective Goal-fulfillment band, not confidence or refusal quality. "
            "Inclusive score ranges: unsatisfied=0; partial=0.01-0.749999; "
            "substantial=0.75-0.949999; exact=0.95-1.0. Pending execution "
            "alone does not reduce adequacy; unresolved Goals remain unmet."
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
    responsibility for Work disposition, coverage, input needs, and step links.
    """

    model_config = ConfigDict(extra="forbid")

    disposition: GoalOutcomeDisposition
    coverage: PlanCoverage
    unresolved: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    satisfaction: PlannerGoalSatisfaction | None = None
    rationale: str = ""
    precedes_step_ids: list[str] = Field(default_factory=list, max_length=64, description="This communication must finish BEFORE each listed Work step starts.")
    follows_step_ids: list[str] = Field(default_factory=list, max_length=64, description="This communication waits until AFTER each listed Work step finishes.")

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> "PlannerModelGoalOutcome":
        if self.disposition in {"execute", "escalate"} and (self.precedes_step_ids or self.follows_step_ids):
            raise ValueError("only communication outcomes may order a communication need")
        if self.disposition == "execute":
            if self.coverage != "complete" or not self.step_ids:
                raise ValueError("execute goal outcome requires complete coverage and step_ids")
            if self.unresolved:
                raise ValueError("execute goal outcome must not retain unresolved work")
        elif self.disposition == "respond":
            if self.coverage != "complete":
                raise ValueError("respond goal outcome requires complete coverage")
            if self.step_ids:
                raise ValueError("respond goal outcome must not reference steps")
            if self.unresolved:
                raise ValueError("respond goal outcome must not retain unresolved work")
        elif self.disposition == "escalate":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError("escalate goal outcome requires partial or uncertain coverage")
            if self.step_ids:
                raise ValueError("escalate goal outcome must not reference steps")
            if not self.unresolved and not self.rationale.strip():
                raise ValueError("escalate goal outcome requires an unresolved need or rationale")
        elif self.disposition == "clarify":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError("clarify goal outcome requires partial or uncertain coverage")
            if self.step_ids:
                raise ValueError("clarify goal outcome must not reference steps")
            if not self.unresolved:
                raise ValueError("clarify goal outcome requires an unresolved input need")
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
    source_quote: str = Field(default="", max_length=500, description="Exact owned Goal time phrase; required for newly interpreted future readiness.")
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
    steps: list[PlannerModelStep] = Field(default_factory=list)
    cancel_activity_ids: list[str] = Field(default_factory=list, max_length=32)
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
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute planner output requires at least one step")
        if self.disposition == "mixed":
            if not self.goal_outcomes:
                raise ValueError("mixed planner output requires goal_outcomes")
            if not self.steps:
                dispositions = {item.disposition for item in self.goal_outcomes.values()}
                if not (
                    "respond" in dispositions
                    and dispositions.intersection({"clarify", "unavailable", "refused"})
                    and dispositions <= {"respond", "clarify", "unavailable", "refused"}
                ):
                    raise ValueError("mixed output without steps requires response and limitation outcomes")
                if self.user_confirmation_required or self.plan_relation != "exact":
                    raise ValueError("mixed output without steps cannot authorize or schedule Work")
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
        elif self.user_confirmation_required and self.disposition not in {
            "execute",
            "mixed",
        }:
            raise ValueError("planner-requested confirmation is valid only for executable plans")
        if self.time_conditions and self.disposition not in {"execute", "mixed", "respond"}:
            raise ValueError(
                "time conditions require live Work or an unmet future Goal acknowledgement"
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
                if self.goal_outcomes[item.goal_id].disposition not in {"execute", "respond"}
            }
            if nonexecuting_time_goals:
                raise ValueError(
                    "time conditions may only bind execute or waiting respond goal outcomes: "
                    + ",".join(sorted(nonexecuting_time_goals))
                )
            outcome_dispositions = {item.disposition for item in self.goal_outcomes.values()}
            expected_disposition = (
                "mixed" if len(outcome_dispositions) > 1 else next(iter(outcome_dispositions))
            )
            if self.disposition != expected_disposition:
                raise ValueError("top-level disposition must match per-goal outcome dispositions")
            validate_acquisition_stage_isolation(
                [(step.source_goal_ids, step.step_purpose) for step in self.steps]
            )
            validate_goal_satisfaction_conservation(
                [(goal_id, item.disposition, item.satisfaction) for goal_id, item in self.goal_outcomes.items()],
                self.goal_satisfaction,
            )
        return self



class PlannerEvidenceReentryGoalDecision(BaseModel):
    """One post-execution decision over an already-owned canonical Goal.

    This is intentionally not a CanonicalPlan/PlannerModelGoalOutcome shape. Re-entry
    answers one narrow question: given fresh trusted Evidence, what should the same
    Planner do next for this Goal? Host later lifts the decision into the canonical
    Planner DTO and re-runs the ordinary trusted validators.
    """

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1, max_length=160)
    next_action: GoalOutcomeDisposition
    satisfaction_status: GoalSatisfactionStatus
    satisfaction_score: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)
    unresolved_needs: list[str] = Field(default_factory=list, max_length=16)
    unmet_requirements: list[str] = Field(default_factory=list, max_length=16)
    rationale: str = Field(default="", max_length=600)

    @field_validator(
        "goal_id", "evidence_refs", "unresolved_needs", "unmet_requirements",
        mode="before",
    )
    @classmethod
    def normalize_reentry_ids_and_lists(cls, value: Any, info: Any) -> Any:
        if info.field_name == "goal_id":
            return normalize_whitespace(value)
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError(f"{info.field_name} must be an array")
        return list(dict.fromkeys(
            text for item in value if (text := normalize_whitespace(str(item or "")))
        ))

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_reentry_rationale(cls, value: Any) -> str:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_reentry_goal_decision(self) -> "PlannerEvidenceReentryGoalDecision":
        band = PlannerGoalSatisfaction(
            score=self.satisfaction_score,
            status=self.satisfaction_status,
            satisfied_goal_ids=[],
            unmet_goal_ids=[],
            unmet_requirements=[],
        )
        del band
        if self.next_action == "respond" and not self.evidence_refs:
            raise ValueError("post-execution respond requires trusted Evidence refs")
        if self.next_action in {"respond", "execute"} and self.unresolved_needs:
            raise ValueError("complete re-entry action cannot retain unresolved needs")
        if self.next_action in {"clarify", "escalate"} and not (
            self.unresolved_needs or self.unmet_requirements or self.rationale
        ):
            raise ValueError(
                "clarify/escalate re-entry requires a concrete unresolved need or rationale"
            )
        if self.next_action in {"clarify", "unavailable", "refused", "escalate"}:
            if self.satisfaction_status == "exact":
                raise ValueError("noncompletion re-entry action cannot claim exact satisfaction")
        return self


class PlannerEvidenceReentryModelOutput(BaseModel):
    """Minimal model-facing contract for trusted post-execution Evidence re-entry.

    It deliberately avoids the names/shapes of both ``CanonicalPlan`` and
    ``PlannerModelOutput`` (notably ``goal_outcomes`` and ``steps``). That prevents
    historical Runtime/Plan evidence from acting as an accidental output template.
    """

    model_config = ConfigDict(extra="forbid")

    goal_decisions: list[PlannerEvidenceReentryGoalDecision] = Field(min_length=1, max_length=16)
    new_work: list[PlannerModelStep] = Field(default_factory=list, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    plan_relation: PlannerPlanRelation
    user_confirmation_required: bool
    escalation_reason: str = Field(default="", max_length=600)

    @field_validator("escalation_reason", mode="before")
    @classmethod
    def normalize_reentry_escalation(cls, value: Any) -> str:
        return normalize_whitespace(value)

    @model_validator(mode="after")
    def validate_reentry_shape(self) -> "PlannerEvidenceReentryModelOutput":
        goal_ids = [item.goal_id for item in self.goal_decisions]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("re-entry goal_decisions must contain unique Goal IDs")
        executing = {item.goal_id for item in self.goal_decisions if item.next_action == "execute"}
        authored = {goal_id for step in self.new_work for goal_id in step.source_goal_ids}
        if executing != authored:
            raise ValueError(
                "re-entry new_work ownership must exactly match execute Goal decisions"
            )
        if any(item.next_action != "execute" for item in self.goal_decisions) and authored - executing:
            raise ValueError("non-execute re-entry Goal cannot own new Work")
        if any(item.next_action == "escalate" for item in self.goal_decisions):
            if self.new_work:
                raise ValueError("escalating re-entry cannot also author new Work")
            if not self.escalation_reason:
                raise ValueError("escalating re-entry requires escalation_reason")
        elif self.escalation_reason:
            raise ValueError("escalation_reason is valid only when a Goal escalates")
        if self.plan_relation in {"safe_adjustment", "alternative"}:
            if not self.user_confirmation_required:
                raise ValueError("adjusted/alternative re-entry requires user confirmation")
            if not executing:
                raise ValueError("adjusted/alternative re-entry requires executable Work")
        elif self.user_confirmation_required and not executing:
            raise ValueError("re-entry confirmation is valid only for executable Work")
        return self

class PlannerDTOContractError(ValueError):
    """Planner output is mechanically malformed or internally inconsistent."""

    def metadata(self) -> dict[str, Any]:
        return {
            "failure_class": "structured_output_validation",
            "failure_domain": "model_contract",
            "architecture_attribution": "not_evaluated",
            "retryable": False,
        }

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
            **output.goal_outcomes[goal_id].model_dump(mode="python", exclude={"precedes_step_ids", "follows_step_ids"}),
        }
        for goal_id in ordered_ids
    ]



def materialize_evidence_reentry_model_output(
    output: PlannerEvidenceReentryModelOutput,
    *,
    expected_goal_ids_for_turn: list[str],
    allowed_evidence_refs: set[str],
    completed_step_evidence: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Lift the compact post-execution decision into the ordinary Planner DTO.

    This is deterministic representation materialization, not semantic repair. The model
    still owns each Goal's next action, satisfaction band/score, unresolved needs, new
    Work, and plan relation. Host owns the redundant aggregate/envelope fields required by
    the maintained ``PlannerModelOutput`` contract.
    """

    expected = list(dict.fromkeys(expected_goal_ids_for_turn))
    decisions = {item.goal_id: item for item in output.goal_decisions}
    if set(decisions) != set(expected):
        raise PlannerDTOContractError(
            "evidence re-entry must decide every scoped Goal exactly once: "
            f"expected={sorted(expected)} actual={sorted(decisions)}"
        )
    allowed_evidence = {str(item).strip() for item in allowed_evidence_refs if str(item).strip()}
    for decision in output.goal_decisions:
        unknown = set(decision.evidence_refs) - allowed_evidence
        if unknown:
            raise PlannerDTOContractError(
                "evidence re-entry decision cites Evidence outside typed scope: "
                + ",".join(sorted(unknown))
            )

    steps_by_goal: dict[str, list[str]] = {goal_id: [] for goal_id in expected}
    for step in output.new_work:
        for goal_id in step.source_goal_ids:
            if goal_id not in steps_by_goal:
                raise PlannerDTOContractError(
                    f"evidence re-entry new Work references out-of-scope Goal: {goal_id}"
                )
            steps_by_goal[goal_id].append(step.step_id)

    proved_steps = completed_step_evidence or {}
    outcomes: dict[str, dict[str, Any]] = {}
    per_goal_satisfaction: list[PlannerGoalSatisfaction] = []
    for goal_id in expected:
        decision = decisions[goal_id]
        completion_action = decision.next_action in {"respond", "execute"}
        unmet_goal_ids = (
            []
            if completion_action and decision.satisfaction_status in {"exact", "substantial"}
            else [goal_id]
        )
        satisfied_goal_ids = (
            [goal_id]
            if completion_action and not unmet_goal_ids
            else []
        )
        satisfaction = PlannerGoalSatisfaction(
            score=decision.satisfaction_score,
            status=decision.satisfaction_status,
            satisfied_goal_ids=satisfied_goal_ids,
            unmet_goal_ids=unmet_goal_ids,
            unmet_requirements=decision.unmet_requirements,
            rationale=decision.rationale,
        )
        per_goal_satisfaction.append(satisfaction)
        follows: list[str] = []
        if decision.next_action == "respond":
            cited = set(decision.evidence_refs)
            follows = [
                step_id
                for step_id, evidence in proved_steps.items()
                if goal_id in set(evidence.get("source_goal_ids") or [])
                and str(evidence.get("evidence_id") or "") in cited
            ]
            proved_refs = {str(proved_steps[step_id].get("evidence_id") or "") for step_id in follows}
            if cited - proved_refs:
                raise PlannerDTOContractError(
                    "evidence re-entry response lacks verified completed Work for its Goal: "
                    + goal_id
                )
        coverage: PlanCoverage = (
            "complete"
            if completion_action
            else "partial"
            if decision.unresolved_needs or decision.unmet_requirements
            else "uncertain"
        )
        outcomes[goal_id] = {
            "disposition": decision.next_action,
            "coverage": coverage,
            "unresolved": list(decision.unresolved_needs),
            "step_ids": list(steps_by_goal[goal_id]),
            "satisfaction": satisfaction.model_dump(mode="python"),
            "rationale": decision.rationale,
            "precedes_step_ids": [],
            "follows_step_ids": follows,
        }

    statuses = {item.next_action for item in output.goal_decisions}
    disposition: PlanDisposition = (
        next(iter(statuses)) if len(statuses) == 1 else "mixed"
    )
    aggregate_score = min(item.score for item in per_goal_satisfaction)
    worst_status = min(
        (item.status for item in per_goal_satisfaction),
        key={"unsatisfied": 0, "partial": 1, "substantial": 2, "exact": 3}.get,
    )
    aggregate_satisfied = list(dict.fromkeys(
        goal_id for item in per_goal_satisfaction for goal_id in item.satisfied_goal_ids
    ))
    aggregate_unmet = list(dict.fromkeys(
        goal_id for item in per_goal_satisfaction for goal_id in item.unmet_goal_ids
    ))
    aggregate_requirements = list(dict.fromkeys(
        requirement
        for item in per_goal_satisfaction
        for requirement in item.unmet_requirements
    ))
    aggregate = PlannerGoalSatisfaction(
        score=aggregate_score,
        status=worst_status,
        satisfied_goal_ids=aggregate_satisfied,
        unmet_goal_ids=aggregate_unmet,
        unmet_requirements=aggregate_requirements,
        rationale="; ".join(
            item.rationale for item in output.goal_decisions if item.rationale
        )[:1200],
    )
    coverage: PlanCoverage = (
        "complete"
        if all(item.next_action in {"respond", "execute"} for item in output.goal_decisions)
        else "partial"
        if aggregate_unmet or aggregate_requirements
        else "uncertain"
    )
    unresolved = list(dict.fromkeys(
        need for item in output.goal_decisions for need in item.unresolved_needs
    ))
    return {
        "disposition": disposition,
        "coverage": coverage,
        "confidence": output.confidence,
        "goal_summary": "",
        "steps": [item.model_dump(mode="python") for item in output.new_work],
        "cancel_activity_ids": [],
        "escalation_reason": output.escalation_reason,
        "unresolved": unresolved,
        "parameter_resolutions": [],
        "time_conditions": [],
        "goal_outcomes": outcomes,
        "goal_satisfaction": aggregate.model_dump(mode="python"),
        "plan_relation": output.plan_relation,
        "user_confirmation_required": output.user_confirmation_required,
    }

def stable_plan_id(request: Any, planner_tier: PlannerTier) -> str:
    """Return the stable host-owned Plan ID for one Planner pass."""

    task_id = request.planning_task_id
    scope = request.planner_reentry_scope
    if not task_id and scope is not None:
        task_id = scope.opportunity_id or "|".join(scope.evidence_refs)
    identity = f"{request.sid or 'turn'}|{planner_tier}|{request.text}"
    if task_id:
        identity += "|" + task_id
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    return f"plan_{digest}"


def materialize_planner_output(
    model_output: PlannerModelOutput,
    *,
    planner_tier: PlannerTier,
    plan_id: str,
    expected_goal_ids_for_turn: list[str],
    fast_multi_goal_contract: bool = False,
    completed_step_evidence: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Materialize only the Host-owned CanonicalPlan envelope."""

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
    # The validated disposition establishes WHAT must be communicated, not words.
    # SC owns fulfillment; an answer need is prospective until actual delivery.
    needs = []
    current_step_ids = {step.step_id for step in model_output.steps}
    proved_steps = completed_step_evidence or {}
    for goal_id, outcome in model_output.goal_outcomes.items():
        kind = {"respond": "answer", "clarify": "input", "unavailable": "result", "refused": "result"}.get(outcome.disposition)
        if kind is not None:
            facts = outcome.model_dump(mode="json", exclude_none=True)
            completed = {key: proved_steps[key] for key in outcome.follows_step_ids
                         if key not in current_step_ids and key in proved_steps}
            if completed:
                # Keep the model's original relation in facts. Only the already
                # fulfilled scheduling edge disappears; no Work is replayed and
                # no BEFORE edge or unproved reference is rewritten.
                facts["completed_work_dependencies"] = list(completed.values())
            needs.append(SocialCommunicationNeed(
                need_id=communication_need_id(plan_id, goal_id), owner="planner", kind=kind,
                reference_id=plan_id, source_goal_ids=[goal_id],
                facts=facts,
                before_step_ids=list(outcome.precedes_step_ids),
                after_step_ids=[key for key in outcome.follows_step_ids if key not in completed],
            ).model_dump(mode="python"))
    if model_output.user_confirmation_required:
        executing = [goal_id for goal_id, outcome in model_output.goal_outcomes.items() if outcome.disposition == "execute"]
        needs.append(SocialCommunicationNeed(
            need_id=communication_need_id(plan_id, "confirmation"), owner="planner", kind="confirmation",
            reference_id=plan_id, source_goal_ids=executing, delivery_phase="pre_action",
            facts={"plan_relation": model_output.plan_relation, "user_confirmation_required": True},
        ).model_dump(mode="python"))
    out["communication_needs"] = needs
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
                source_quote=condition.source_quote,
                reason_code=condition.reason_code,
            ).model_dump(mode="python")
        )
    out["time_conditions"] = planned_time_conditions

    metadata = materialize_planner_metadata(model_output)
    if planner_tier == "fast" and fast_multi_goal_contract:
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
