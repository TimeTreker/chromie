from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from itertools import product
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from chromie_contracts.interaction import CapabilityIdentityModel
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.interaction import CapabilityIdentityModel

try:
    from chromie_contracts.plan import (
        CanonicalPlan,
        GoalOutcomeDisposition,
        GoalSatisfactionAssessment,
        GoalSatisfactionStatus,
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlanTiming,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        GoalOutcomeDisposition,
        GoalSatisfactionAssessment,
        GoalSatisfactionStatus,
        PlanCoverage,
        PlanDisposition,
        PlanParameterResolution,
        PlanTiming,
    )

PlannerTier = Literal["fast", "deep"]
PlannerPlanRelation = Literal["exact", "safe_adjustment", "alternative"]

_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?!\w)"
)


class PlannerCoverageReview(BaseModel):
    """Model-authored audit of a coordinated action Plan's completeness."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "reject"]
    confidence: float = Field(ge=0.0, le=1.0)
    uncovered_requirements: list[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("uncovered_requirements", mode="before")
    @classmethod
    def normalize_uncovered_requirements(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("uncovered_requirements must be an array")
        return [
            text
            for item in value
            if (text := " ".join(str(item or "").strip().split()))
        ]

    @model_validator(mode="after")
    def validate_decision(self) -> "PlannerCoverageReview":
        if self.decision == "accept" and self.uncovered_requirements:
            raise ValueError("accepted coverage cannot list uncovered requirements")
        if self.decision == "reject" and not self.uncovered_requirements:
            raise ValueError("rejected coverage requires uncovered requirements")
        return self

# Response Composer owns user-facing speech in the goal-driven pipeline.  These
# runtime transport skills are valid in legacy/native InteractionResponse task
# lists, but they are not task-plan leaves: conversational goals use a
# ``respond`` outcome and model-authored ``response_text`` instead.
RESPONSE_COMPOSER_OWNED_CAPABILITY_IDS = frozenset({"chromie.speak"})
RESPONSE_COMPOSER_OWNED_SKILL_IDS = RESPONSE_COMPOSER_OWNED_CAPABILITY_IDS


def is_planner_step_capability(capability_id: str) -> bool:
    return (
        str(capability_id or "").strip()
        not in RESPONSE_COMPOSER_OWNED_CAPABILITY_IDS
    )


def is_planner_step_skill(skill_id: str) -> bool:
    """Bounded compatibility alias for pre-migration callers."""

    return is_planner_step_capability(skill_id)


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
    reason_summary: str = ""


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
                raise ValueError(
                    "execute goal outcome requires complete coverage and step_ids"
                )
            if self.response_text.strip():
                raise ValueError(
                    "execute goal outcome must not carry response_text; "
                    "Response Composer owns pre-execution speech"
                )
        elif self.disposition == "respond":
            if self.coverage != "complete" or not self.response_text.strip():
                raise ValueError(
                    "respond goal outcome requires complete coverage and response_text"
                )
            if self.step_ids:
                raise ValueError("respond goal outcome must not reference steps")
        elif self.disposition == "escalate":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError(
                    "escalate goal outcome requires partial or uncertain coverage"
                )
            if self.step_ids:
                raise ValueError("escalate goal outcome must not reference steps")
            if self.response_text.strip():
                raise ValueError(
                    "escalate goal outcome must not claim a conversational answer"
                )
            if not self.unresolved and not self.rationale.strip():
                raise ValueError(
                    "escalate goal outcome requires an unresolved need or rationale"
                )
        elif self.disposition == "clarify":
            if self.coverage not in {"partial", "uncertain"}:
                raise ValueError(
                    "clarify goal outcome requires partial or uncertain coverage"
                )
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
    escalation_reason: str = ""
    unresolved: list[str] = Field(default_factory=list)
    parameter_resolutions: list[PlanParameterResolution] = Field(default_factory=list)
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
        if normalized.get("disposition") in {"execute", "mixed"} and normalized.get(
            "response_text"
        ) is None:
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
        if (
            normalized.get("disposition") == "clarify"
            and outcome.get("disposition") == "clarify"
        ):
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
                "response transport skills are owned by Response Composer; "
                "represent conversational goals with respond outcomes and response_text: "
                + ",".join(response_transport_steps)
            )
        if self.coverage != "complete" and self.steps:
            raise ValueError("non-complete planner output must not carry executable steps")
        if self.disposition == "execute" and not self.steps:
            raise ValueError("execute planner output requires at least one step")
        if self.disposition == "mixed" and (not self.steps or not self.goal_outcomes):
            raise ValueError("mixed planner output requires steps and goal_outcomes")
        if self.disposition == "respond" and not self.response_text.strip():
            raise ValueError("respond planner output requires response_text")
        if self.disposition not in {"execute", "mixed"} and self.steps:
            raise ValueError(
                f"{self.disposition} planner output must not carry executable steps"
            )
        if self.disposition == "escalate" and not self.escalation_reason.strip():
            raise ValueError("escalate planner output requires escalation_reason")
        if self.disposition in {"execute", "respond", "mixed"}:
            if self.coverage != "complete":
                raise ValueError(
                    "execute, respond, and mixed planner output requires complete coverage"
                )
            if self.goal_satisfaction is None:
                raise ValueError(
                    "complete executable or response output requires goal_satisfaction"
                )
        if self.plan_relation in {"safe_adjustment", "alternative"}:
            if self.disposition not in {"execute", "mixed"}:
                raise ValueError(
                    "safe-adjusted and alternative plans must be executable"
                )
            if not self.user_confirmation_required:
                raise ValueError(
                    "safe-adjusted and alternative plans require user confirmation"
                )
            if not self.response_text.strip():
                raise ValueError(
                    "safe-adjusted and alternative plans require response_text "
                    "explaining the material change"
                )
        elif self.user_confirmation_required and self.disposition not in {
            "execute",
            "mixed",
        }:
            raise ValueError(
                "planner-requested confirmation is valid only for executable plans"
            )
        if self.goal_outcomes:
            outcome_dispositions = {
                item.disposition for item in self.goal_outcomes.values()
            }
            expected_disposition = (
                "mixed"
                if len(outcome_dispositions) > 1
                else next(iter(outcome_dispositions))
            )
            if self.disposition != expected_disposition:
                raise ValueError(
                    "top-level disposition must match per-goal outcome dispositions"
                )
        return self


def expected_goal_ids(context: dict[str, Any] | None) -> list[str]:
    """Return the ordered canonical goal IDs accepted by Goal Association."""

    association = (context or {}).get("goal_association_resolution")
    if not isinstance(association, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = " ".join(str(value or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)

    for item in association.get("associations") or []:
        if not isinstance(item, dict):
            continue
        for goal_id in item.get("target_goal_ids") or []:
            add(goal_id)
    for item in association.get("new_goals") or []:
        if isinstance(item, dict):
            add(item.get("goal_id"))
    return ordered


def canonical_goal_grounding(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build a compact immutable grounding block for planner prompts.

    Goal Association owns which goals exist. Planners receive only those IDs and
    their human-facing semantics; internal implementation concepts are omitted.
    """

    context = context or {}
    association = context.get("goal_association_resolution")
    active = [
        *(context.get("active_goal_snapshots") or []),
        *(context.get("recent_goal_snapshots") or []),
    ]
    active_by_id: dict[str, dict[str, Any]] = {}
    for item in active:
        if not isinstance(item, dict):
            continue
        goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        if goal_id:
            active_by_id[goal_id] = {
                "goal_id": goal_id,
                "description": goal.get("description") or item.get("last_user_update") or "",
                "source_text": goal.get("source_text") or item.get("last_user_update") or "",
                "constraints": goal.get("constraints") or {},
                "success_criteria": goal.get("success_criteria") or [],
                "object": goal.get("object") or {},
                "metadata": goal.get("metadata") or {},
            }

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(association, dict):
        for item in association.get("associations") or []:
            if not isinstance(item, dict):
                continue
            for raw_id in item.get("target_goal_ids") or []:
                goal_id = " ".join(str(raw_id or "").strip().split())
                if goal_id and goal_id not in seen:
                    seen.add(goal_id)
                    result.append(active_by_id.get(goal_id, {"goal_id": goal_id}))
        for item in association.get("new_goals") or []:
            if not isinstance(item, dict):
                continue
            goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
            if not goal_id or goal_id in seen:
                continue
            seen.add(goal_id)
            result.append(
                {
                    "goal_id": goal_id,
                    "description": item.get("description") or "",
                    "source_text": item.get("source_text") or "",
                    "constraints": item.get("constraints") or {},
                    "success_criteria": item.get("success_criteria") or [],
                    "object": item.get("object") or {},
                    "metadata": item.get("metadata") or {},
                }
            )
    return result


def planner_response_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Goal Association-authored direct-response Goal IDs.

    This reads a typed semantic judgment made at Goal Association. It does not
    classify user text or select a Capability.
    """

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        if (
            goal_id
            and isinstance(metadata, dict)
            and metadata.get("responsibility_kind") == "spoken_response"
        ):
            result.add(goal_id)
    return result


def validate_goal_responsibility_outcomes(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    """Keep planner outcomes aligned with typed Goal completion modalities."""

    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    capability_goal_ids: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        if (
            goal_id
            and isinstance(metadata, dict)
            and metadata.get("responsibility_kind") == "capability_dependent"
        ):
            capability_goal_ids.add(goal_id)
    evidence_goal_ids = {
        source_goal_id
        for item in evidence_bound_dialogue(context)
        for source_goal_id in item.get("source_goal_ids") or []
    }
    for goal_id in sorted(response_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(
                f"spoken_response goal requires an explicit outcome: {goal_id}"
            )
        if outcome.disposition != "respond":
            raise ValueError(
                "spoken_response goal must use disposition=respond and no "
                f"executable step: {goal_id}"
            )
    invalid_steps = [
        step.step_id
        for step in output.steps
        if response_goal_ids.intersection(step.source_goal_ids)
    ]
    if invalid_steps:
        raise ValueError(
            "spoken_response goals cannot own executable planner steps: "
            + ",".join(invalid_steps)
        )
    for goal_id in sorted(capability_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        responds_without_capability = (
            outcome is not None and outcome.disposition == "respond"
        ) or (
            len(authoritative_goals) == 1
            and not output.goal_outcomes
            and output.disposition == "respond"
        )
        if responds_without_capability and goal_id not in evidence_goal_ids:
            raise ValueError(
                "capability_dependent goal cannot use disposition=respond "
                "without capability or delivered evidence-bound dialogue: "
                + goal_id
            )


def coordinated_action_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Goals explicitly bound as coordinated action collections.

    Goal Association, rather than the Host, authors the ``action_list`` type or
    splits one source utterance into several independently observable Goals.
    The Host uses those structured facts only to require a bounded model
    completeness audit; it does not infer actions or select Capabilities.
    """

    goal_ids: set[str] = set()
    source_groups: dict[str, set[str]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        source_text = " ".join(str(goal.get("source_text") or "").strip().split())
        if source_text:
            source_groups.setdefault(source_text, set()).add(goal_id)
        goal_object = goal.get("object")
        if not isinstance(goal_object, dict):
            continue
        bindings = goal_object.get("bindings")
        if not isinstance(bindings, dict):
            continue
        if any(
            isinstance(binding, dict)
            and "_".join(
                str(binding.get("entity_type") or "")
                .strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            == "action_list"
            for binding in bindings.values()
        ):
            goal_ids.add(goal_id)
    for grouped_ids in source_groups.values():
        # Three or more independently observable responsibilities from one
        # model-segmented utterance cross the bounded-complexity threshold even
        # when no one Goal owns an action_list binding. Two ordinary sibling
        # Goals remain on the normal per-goal contract path.
        if len(grouped_ids) >= 3:
            goal_ids.update(grouped_ids)
    return goal_ids


def parallel_plan_contract_errors(
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate declared capability/resource evidence for parallel Plan steps.

    This validator never chooses timing. It only rejects model-authored parallel
    timing when the supplied provider catalog does not affirm that timing or
    when declared exclusive/resource claims conflict. The planner may then
    author an explicit safe adjustment, alternative, or clarification.
    """

    # One step has no peer with which to overlap. Treating its redundant
    # ``parallel`` label as a concurrency request contradicts the runtime
    # contract, which already admits a single-step batch without provider
    # parallel metadata. This is arity validation, not a Host timing choice.
    if len(plan.steps) < 2:
        return []

    by_id = {
        str(item.get("capability_id") or ""): item
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
    }
    parallel_steps = [step for step in plan.steps if step.timing == "parallel"]
    errors: list[dict[str, Any]] = []
    usable: list[tuple[Any, dict[str, Any]]] = []
    for step in parallel_steps:
        capability = by_id.get(step.capability_id)
        if capability is None:
            continue
        if (
            capability.get("parallel_metadata_declared") is not True
            or capability.get("can_run_parallel") is not True
        ):
            errors.append(
                {
                    "type": "parallel_capability_not_declared_safe",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "parallel_metadata_declared": capability.get(
                        "parallel_metadata_declared"
                    ),
                    "can_run_parallel": capability.get("can_run_parallel"),
                }
            )
            continue
        usable.append((step, capability))

    for index, (left_step, left) in enumerate(usable):
        left_group = str(left.get("exclusive_group") or "").strip()
        left_resources = {
            str(item).strip()
            for item in left.get("resource_claims") or []
            if str(item).strip()
        }
        for right_step, right in usable[index + 1 :]:
            right_group = str(right.get("exclusive_group") or "").strip()
            if left_group and left_group == right_group:
                errors.append(
                    {
                        "type": "parallel_exclusive_group_conflict",
                        "step_ids": [left_step.step_id, right_step.step_id],
                        "exclusive_group": left_group,
                    }
                )
            right_resources = {
                str(item).strip()
                for item in right.get("resource_claims") or []
                if str(item).strip()
            }
            conflicts = sorted(left_resources.intersection(right_resources))
            if conflicts:
                errors.append(
                    {
                        "type": "parallel_resource_claim_conflict",
                        "step_ids": [left_step.step_id, right_step.step_id],
                        "resource_claims": conflicts,
                    }
                )
    return errors


async def review_coordinated_action_plan_coverage(
    client: Any,
    *,
    request_text: str,
    language: str,
    authoritative_goals: list[dict[str, Any]],
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
    num_ctx: int,
) -> PlannerCoverageReview:
    """Ask the planner model to audit a structured coordinated-action Plan.

    The review can only accept or reject. It cannot add steps, choose a
    Capability, authorize execution, or rewrite the Plan. A rejection therefore
    sends Fast Planning to Deep Planning, or makes Deep Planning fail closed.
    """

    prompt = json.dumps(
        {
            "responsibility": (
                "Audit whether the proposed Plan completely represents every "
                "material responsibility in the authoritative coordinated-action "
                "Goals. Judge semantics, not words. A requested action, spoken "
                "performance, duration, ordering, or concurrency relation that can "
                "succeed or fail separately must be accounted for. Reject a Plan "
                "that claims complete or exact coverage while omitting any such "
                "responsibility. Reject a step assigned to a Goal when the supplied "
                "Capability semantics do not actually implement that Goal; a step "
                "reason cannot invent an unstated feature. Reject requested "
                "concurrency unless the Plan either uses capabilities with explicit "
                "compatible parallel declarations or records an explicit safe "
                "adjustment/alternative for user confirmation. When that adjustment "
                "contract is explicit, confirmation-bound, and explained, do not "
                "reject solely because its retained steps are sequential; the changed "
                "timing is represented for the user to approve. A Goal whose "
                "responsibility_kind is spoken_response is completed by its respond "
                "outcome response_text and requires no executable speech-transport "
                "step. Still reject a promise, acknowledgement, title, or stage "
                "direction that does not contain the requested authored response or "
                "performance itself. Do not propose or authorize replacement steps."
            ),
            "user_text": request_text,
            "language": language,
            "authoritative_goals": authoritative_goals,
            "proposed_plan": plan.model_dump(
                mode="json",
                exclude={"metadata", "selected_agent_skills"},
            ),
            "proposed_adjustment_contract": {
                "plan_relation": plan.metadata.get("plan_relation", "exact"),
                "user_confirmation_required": bool(
                    plan.metadata.get("user_confirmation_required", False)
                ),
                "response_text": plan.response_text,
            },
            "executable_capabilities": capabilities,
            "output_contract": {
                "decision": "accept or reject",
                "accept": (
                    "Only when every material responsibility is represented; "
                    "uncovered_requirements must be empty."
                ),
                "reject": (
                    "List each omitted or contradicted responsibility in "
                    "uncovered_requirements."
                ),
                "execution_authority": "none",
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    raw = await client.generate(
        prompt,
        system=(
            "You are the current Planner's bounded semantic completeness auditor. "
            "Use the authoritative Goals, proposed Plan, and supplied Capability "
            "semantics. Do not use phrase rules, invent Capabilities, revise the "
            "Plan, or authorize execution. Return only the required JSON object."
        ),
        options={
            "temperature": 0,
            "top_p": 0.8,
            "num_ctx": max(4096, int(num_ctx)),
            "num_predict": 384,
        },
        response_format=planner_coverage_review_response_schema(),
    )
    if not isinstance(raw, dict):
        raise ValueError("planner coverage review response is not a JSON object")
    return PlannerCoverageReview.model_validate(raw)


def planner_coverage_review_response_schema() -> dict[str, Any]:
    """Return a decoder-tight schema for the bounded coverage auditor."""

    schema = copy.deepcopy(PlannerCoverageReview.model_json_schema())
    schema["required"] = [
        "decision",
        "confidence",
        "uncovered_requirements",
        "reason",
    ]
    schema.setdefault("allOf", []).append(
        {
            "anyOf": [
                {
                    "properties": {
                        "decision": {"type": "string", "enum": ["accept"]},
                        "uncovered_requirements": {
                            "type": "array",
                            "maxItems": 0,
                        },
                    }
                },
                {
                    "properties": {
                        "decision": {"type": "string", "enum": ["reject"]},
                        "uncovered_requirements": {
                            "type": "array",
                            "minItems": 1,
                        },
                    }
                },
            ]
        }
    )
    return schema


def _normalized_material_value(value: Any) -> Any:
    """Normalize only representation details for exact semantic comparisons."""

    if isinstance(value, str):
        normalized = " ".join(value.strip().casefold().split())
        if _NUMERIC_LITERAL_RE.fullmatch(normalized):
            try:
                return Decimal(normalized)
            except InvalidOperation:
                pass
        return normalized
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    if isinstance(value, dict):
        return {
            str(key): _normalized_material_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_normalized_material_value(item) for item in value]
    return value


def _goal_binding_map(goal: dict[str, Any]) -> dict[str, Any]:
    goal_object = goal.get("object")
    if not isinstance(goal_object, dict):
        return {}
    raw_bindings = goal_object.get("bindings")
    if not isinstance(raw_bindings, dict):
        return {}
    bindings: dict[str, Any] = {}
    for raw_name, raw_binding in raw_bindings.items():
        name = " ".join(str(raw_name or "").strip().split())
        if not name or not isinstance(raw_binding, dict) or "value" not in raw_binding:
            continue
        bindings[name] = raw_binding.get("value")
    return bindings


def validate_goal_binding_argument_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
) -> None:
    """Keep executable arguments aligned with Goal Association bindings.

    Goal Association remains the LLM semantic authority that resolves references
    and binds entities.  This validator does not infer what ``那边`` means and it
    contains no location, weather, or phrase rules.  It only rejects a Planner
    step when an argument with the same semantic binding name contradicts the
    immutable Goal value that the step claims to satisfy.

    Verified-memory retrieval is additionally required to carry every material
    binding in ``material_args``.  This prevents a generic "latest result" lookup
    from crossing task or discourse scopes after the Goal has been resolved.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    bindings_by_goal: dict[str, dict[str, Any]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if goal_id:
            bindings_by_goal[goal_id] = _goal_binding_map(goal)

    for step in output.steps:
        claimed_goal_ids = [
            goal_id
            for goal_id in step.source_goal_ids
            if goal_id in bindings_by_goal
        ]
        if not claimed_goal_ids:
            continue

        required: dict[str, Any] = {}
        for goal_id in claimed_goal_ids:
            for name, value in bindings_by_goal[goal_id].items():
                if (
                    name in required
                    and _normalized_material_value(required[name])
                    != _normalized_material_value(value)
                ):
                    raise ValueError(
                        "one executable step cannot satisfy conflicting authoritative "
                        f"Goal bindings for {name!r}"
                    )
                required[name] = value

        for name, expected in required.items():
            if name not in step.args:
                continue
            actual = step.args[name]
            if _normalized_material_value(actual) != _normalized_material_value(
                expected
            ):
                raise ValueError(
                    "planner step argument contradicts authoritative Goal binding: "
                    f"{step.step_id}.{name}={actual!r}, expected={expected!r}"
                )

        if step.capability_id == "chromie.memory.retrieve_verified_tool_result":
            material_args = step.args.get("material_args")
            if not isinstance(material_args, dict):
                raise ValueError(
                    "verified-memory retrieval requires material_args containing "
                    "the authoritative Goal bindings"
                )
            for name, expected in required.items():
                if name not in material_args:
                    raise ValueError(
                        "verified-memory retrieval omitted authoritative Goal binding: "
                        f"{name!r}"
                    )
                actual = material_args[name]
                if _normalized_material_value(
                    actual
                ) != _normalized_material_value(expected):
                    raise ValueError(
                        "verified-memory retrieval contradicts authoritative Goal "
                        f"binding: material_args.{name}={actual!r}, "
                        f"expected={expected!r}"
                    )


def validate_external_response_evidence_boundary(
    output: PlannerModelOutput,
    *,
    context: dict[str, Any] | None,
) -> None:
    """Reject factual responses for unresolved external-read Goals.

    Active Goal snapshots may record that a trusted safe-read Capability was
    planned but has not produced completed evidence.  A planner may retry that
    read, retrieve an exact verified result, clarify, or report a limitation.
    It may not turn the unresolved execution binding into a direct factual
    response.  This validator reads typed lifecycle evidence only; it does not
    inspect user wording or choose a Capability.
    """

    context = context or {}
    snapshots = context.get("active_goal_snapshots")
    if not isinstance(snapshots, list):
        snapshots = []

    unresolved_external_goal_ids: set[str] = set()
    completed_statuses = {"completed", "done", "success", "succeeded"}
    external_safety_classes = {"safe_read", "read_only", "external_read"}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        goal_id = " ".join(str(snapshot.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        metadata = snapshot.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        binding = metadata.get("execution_binding")
        if not isinstance(binding, dict):
            continue
        outcome_status = " ".join(
            str(binding.get("execution_outcome_status") or "").strip().split()
        ).casefold()
        if outcome_status in completed_statuses:
            continue
        planned = binding.get("planned_skills")
        if not isinstance(planned, list):
            planned = []
        has_external_read = bool(binding.get("retryable_safe_read"))
        for item in planned:
            if not isinstance(item, dict):
                continue
            safety_class = " ".join(
                str(item.get("safety_class") or "").strip().split()
            ).casefold()
            if safety_class in external_safety_classes or item.get(
                "retryable_safe_read"
            ) is True:
                has_external_read = True
                break
        if has_external_read:
            unresolved_external_goal_ids.add(goal_id)

    responding_goal_ids: set[str] = set()
    if output.goal_outcomes:
        responding_goal_ids = {
            goal_id
            for goal_id, outcome in output.goal_outcomes.items()
            if outcome.disposition == "respond"
        }
    elif output.disposition == "respond":
        responding_goal_ids = set(unresolved_external_goal_ids)

    unsupported = responding_goal_ids & unresolved_external_goal_ids
    if unsupported:
        raise ValueError(
            "external_read_response_requires_completed_or_verified_evidence: "
            + ",".join(sorted(unsupported))
        )

    verified_goal_ids: set[str] = set()
    verified_index = context.get("verified_tool_memory_index")
    if isinstance(verified_index, list):
        for item in verified_index:
            if not isinstance(item, dict):
                continue
            verified_goal_ids.update(
                normalized
                for value in item.get("goal_ids") or []
                if (normalized := " ".join(str(value or "").strip().split()))
            )
    dialogue_goal_ids = {
        goal_id
        for item in evidence_bound_dialogue(context)
        for goal_id in item.get("source_goal_ids") or []
    }
    index_only_goal_ids = responding_goal_ids & verified_goal_ids - dialogue_goal_ids
    if index_only_goal_ids:
        raise ValueError(
            "external_read_response_requires_evidence_bound_dialogue_or_retrieval: "
            + ",".join(sorted(index_only_goal_ids))
        )


def evidence_bound_dialogue(
    context: dict[str, Any] | None,
    *,
    fallback_history: list[dict[str, Any]] | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Return delivered, Host-marked post-execution speech for Goal continuity."""

    context = context or {}
    history = context.get("history")
    if not isinstance(history, list):
        history = fallback_history if isinstance(fallback_history, list) else []
    out: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if (
            metadata.get("evidence_bound") is not True
            or str(metadata.get("source") or "").strip()
            != "evidence_bound_tool_result_interpretation"
        ):
            continue
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue
        out.append(
            {
                "text": text[:1200],
                "source_goal_ids": [
                    normalized
                    for value in metadata.get("source_goal_ids") or []
                    if (normalized := " ".join(str(value or "").strip().split()))
                ][:8],
                "canonical_plan_id": str(
                    metadata.get("canonical_plan_id") or ""
                )[:200],
                "source": "evidence_bound_tool_result_interpretation",
            }
        )
    return out[-max(1, int(limit)) :]


def validate_explicit_numeric_parameter_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
) -> None:
    """Verify numeric user-supplied arguments against immutable goal text.

    The planner remains the semantic authority for mapping a user value to a
    skill parameter.  This check only enforces provenance after that judgment:
    a value labelled ``user_supplied`` must agree with its executable step and
    identify an authoritative source Goal containing that value, and every
    numeric literal in an executable goal must be accounted for.  It therefore
    catches silent default substitution without introducing phrase-to-action
    or parameter-name rules.  Stable Goal IDs carry provenance; requiring the
    model to copy a second free-text citation adds no evidence and is not part
    of this contract.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    def numeric(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
            return None
        if isinstance(value, str) and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is None:
            return None
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None

    def literals(value: str) -> list[Decimal]:
        found: list[Decimal] = []
        for match in _NUMERIC_LITERAL_RE.finditer(value):
            try:
                number = Decimal(match.group(0))
            except InvalidOperation:
                continue
            if number not in found:
                found.append(number)
        return found

    def resolution_location(resolution: PlanParameterResolution) -> str:
        """Render an unambiguous typed location for model repair feedback."""

        return (
            f"step_id={resolution.step_id!r}, "
            f"parameter={resolution.parameter!r}"
        )

    goal_text: dict[str, str] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        parts: list[str] = []
        description = str(goal.get("description") or "").strip()
        if description:
            parts.append(description)
        criteria = goal.get("success_criteria")
        if isinstance(criteria, list):
            parts.extend(str(item).strip() for item in criteria if str(item).strip())
        source_text = str(goal.get("source_text") or "").strip()
        if not parts and source_text:
            parts.append(source_text)
        goal_text[goal_id] = " ".join(dict.fromkeys(parts))

    steps = {step.step_id: step for step in output.steps}
    user_numeric_resolutions: list[tuple[PlanParameterResolution, Decimal]] = []
    for resolution in output.parameter_resolutions:
        if resolution.blocking:
            continue
        step = steps.get(resolution.step_id)
        if step is None:
            raise ValueError(
                "parameter resolution references unknown executable step "
                f"({resolution_location(resolution)})"
            )
        if resolution.parameter not in step.args:
            raise ValueError(
                "parameter resolution references an argument absent from its step: "
                f"{resolution_location(resolution)}"
            )
        resolved_number = numeric(resolution.value)
        argument_number = numeric(step.args[resolution.parameter])
        if resolved_number is not None and argument_number is not None:
            if resolved_number != argument_number:
                raise ValueError(
                    "parameter resolution value must equal the executable step argument: "
                    f"{resolution_location(resolution)} has "
                    f"resolution={resolution.value!r}, step={step.args[resolution.parameter]!r}"
                )
        elif resolution.value != step.args[resolution.parameter]:
            raise ValueError(
                "parameter resolution value must equal the executable step argument: "
                f"{resolution_location(resolution)}"
            )

        if resolution.strategy != "user_supplied" or resolved_number is None:
            continue
        source_goal_ids = list(dict.fromkeys(resolution.source_goal_ids))
        if not source_goal_ids:
            raise ValueError(
                "numeric user_supplied parameter resolution requires source_goal_ids: "
                f"{resolution_location(resolution)}"
            )
        user_numeric_resolutions.append((resolution, resolved_number))

    executable_goal_ids = {
        goal_id
        for goal_id, outcome in output.goal_outcomes.items()
        if outcome.disposition == "execute"
    }
    if not executable_goal_ids:
        executable_goal_ids = {
            goal_id
            for step in output.steps
            for goal_id in step.source_goal_ids
        }
    for goal_id in executable_goal_ids:
        for literal in literals(goal_text.get(goal_id, "")):
            if not any(
                literal == value and goal_id in resolution.source_goal_ids
                for resolution, value in user_numeric_resolutions
            ):
                raise ValueError(
                    "explicit numeric goal value has no matching user_supplied "
                    f"parameter resolution: goal_id={goal_id!r}, value={literal}"
                )


def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_skill_ids: list[str],
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan`` with one
    bounded same-tier model repair. Fast Planner uses the same decoder-tight
    per-goal shape for one or many goals so the schema never instructs the model
    to omit fields that deterministic validation requires.
    """

    if planner_tier == "fast":
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=expected_goal_ids,
            allowed_skill_ids=allowed_skill_ids,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
        )
        schema["title"] = "FastPlannerModelOutput"
        return schema

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = (
        "FastPlannerModelOutput"
        if planner_tier == "fast"
        else "DeepPlannerModelOutput"
    )
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in (
        "disposition",
        "coverage",
        "confidence",
        "goal_summary",
        "response_text",
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "goal_outcomes",
        "goal_satisfaction",
        "plan_relation",
        "user_confirmation_required",
    ):
        if field_name not in required:
            required.append(field_name)

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        if response_only:
            disposition["enum"] = [
                "respond",
                "clarify",
                "unavailable",
                "refused",
            ]
        elif requires_execution:
            disposition["enum"] = (
                ["execute", "mixed", "clarify", "unavailable", "refused"]
                if response_goal_ids
                else ["execute", "clarify", "unavailable", "refused"]
            )
        else:
            disposition["enum"] = [
                "respond",
                "execute",
                "mixed",
                "clarify",
                "unavailable",
                "refused",
            ]

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_skills = list(dict.fromkeys(allowed_skill_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)

    if requires_execution:
        planner_response_text = properties.get("response_text")
        if isinstance(planner_response_text, dict):
            planner_response_text["maxLength"] = 0
            planner_response_text["description"] = (
                "Tool-route planning never speaks or predicts a tool result. "
                "Response Composer owns any tiny pre-execution acknowledgement, "
                "and verified post-execution speech is grounded in tool evidence."
            )

    # Both tiers must emit the multi-goal outcome envelope.  Deep Planner always
    # emits a complete map.  Fast Planner uses one flat decoder-compatible shape:
    # either an empty map for semantic escalation or a complete terminal map.
    if (
        len(allowed_goals) > 1
        and "goal_outcomes" not in required
    ):
        required.append("goal_outcomes")

    goal_outcomes = properties.get("goal_outcomes")
    if isinstance(goal_outcomes, dict):
        if planner_tier == "fast" and len(allowed_goals) <= 1:
            # A single-goal fast plan already has one unambiguous semantic owner
            # for the top-level response/step fields. Hiding the redundant nested
            # map avoids an Ollama decoder failure mode where it emits a partial
            # $ref object that necessarily fails PlannerModelGoalOutcome.
            goal_outcomes.clear()
            goal_outcomes.update(
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                    "maxProperties": 0,
                }
            )
        else:
            outcome_properties = {
                goal_id: {
                    "$ref": "#/$defs/PlannerModelGoalOutcome",
                    "description": (
                        "Outcome for this exact canonical goal. Decide only this "
                        "goal's disposition, coverage, response, and owned step IDs."
                    ),
                }
                for goal_id in allowed_goals
            }
            goal_outcomes.clear()
            goal_outcomes.update(
                {
                    "type": "object",
                    "properties": outcome_properties,
                    "additionalProperties": False,
                    "maxProperties": len(allowed_goals),
                }
            )
            if allowed_goals and planner_tier == "deep":
                goal_outcomes.update(
                    {
                        "required": allowed_goals,
                        "minProperties": len(allowed_goals),
                    }
                )
            elif allowed_goals and planner_tier == "fast":
                goal_outcomes["minProperties"] = 0

    outcome_schema = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
    if isinstance(outcome_schema, dict):
        # The runtime validator distinguishes an intentionally empty field from
        # one the decoder silently omitted.  Keep the decoder contract aligned
        # with that validator: every outcome must make its ownership and
        # terminal judgment explicit, even when a disposition requires an
        # empty string/list or a null satisfaction value.
        outcome_required = outcome_schema.setdefault("required", [])
        for field_name in (
            "disposition",
            "coverage",
            "response_text",
            "unresolved",
            "step_ids",
            "satisfaction",
            "rationale",
        ):
            if field_name not in outcome_required:
                outcome_required.append(field_name)
        outcome_disposition = (
            outcome_schema.get("properties", {}).get("disposition")
        )
        if isinstance(outcome_disposition, dict):
            if response_only:
                outcome_disposition["enum"] = (
                    ["respond"]
                    if planner_tier == "fast"
                    else ["respond", "clarify", "unavailable", "refused"]
                )
            elif planner_tier == "fast":
                outcome_disposition["enum"] = ["respond", "execute"]

        outcome_properties = outcome_schema.get("properties", {})
        base_branches: list[dict[str, Any]] = []
        allowed_outcomes = (
            (["respond"] if planner_tier == "fast" else ["respond", "clarify", "unavailable", "refused"])
            if response_only
            else (
                ["respond", "execute"]
                if planner_tier == "fast"
                else [
                    "respond",
                    "execute",
                    "clarify",
                    "unavailable",
                    "refused",
                ]
            )
        )
        for outcome_name in allowed_outcomes:
            branch: dict[str, Any] = {
                "properties": {"disposition": {"enum": [outcome_name]}}
            }
            branch_props = branch["properties"]
            if outcome_name == "execute":
                branch_props["coverage"] = {"enum": ["complete"]}
                branch_props["response_text"] = {"maxLength": 0}
                branch_props["step_ids"] = {"minItems": 1}
            elif outcome_name == "respond":
                branch_props["coverage"] = {"enum": ["complete"]}
                branch_props["response_text"] = {"minLength": 1}
                branch_props["step_ids"] = {"maxItems": 0}
            elif outcome_name == "clarify":
                branch_props["coverage"] = {"enum": ["partial", "uncertain"]}
                branch_props["step_ids"] = {"maxItems": 0}
            else:
                branch_props["step_ids"] = {"maxItems": 0}
            base_branches.append(branch)
        if base_branches:
            outcome_schema["oneOf"] = base_branches

    goal_list_fields = {
        "goal_ids",
        "source_goal_ids",
        "satisfied_goal_ids",
        "unmet_goal_ids",
    }

    def constrain(node: Any) -> None:
        if isinstance(node, dict):
            node_properties = node.get("properties")
            if isinstance(node_properties, dict):
                goal_id = node_properties.get("goal_id")
                if isinstance(goal_id, dict) and allowed_goals:
                    goal_id["enum"] = allowed_goals
                capability_id = node_properties.get("capability_id")
                if isinstance(capability_id, dict) and allowed_skills:
                    capability_id["enum"] = allowed_skills
                for field_name in goal_list_fields:
                    field = node_properties.get(field_name)
                    if isinstance(field, dict) and allowed_goals:
                        field["items"] = {"type": "string", "enum": allowed_goals}
                        field["uniqueItems"] = True
                        if field_name == "source_goal_ids":
                            field["minItems"] = 1
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)
    _constrain_plan_relation_confirmation(schema)

    # Ollama's structured decoder does not reliably apply nested ``required``
    # constraints through a dynamic object property that contains only a $ref.
    # Inline each Deep Planner goal outcome and its satisfaction object so the
    # decoder sees every required semantic field at the exact goal key.
    if planner_tier == "deep":
        satisfaction_schema = schema.get("$defs", {}).get(
            "PlannerGoalSatisfaction"
        )
        if isinstance(satisfaction_schema, dict):
            satisfaction_required = satisfaction_schema.setdefault(
                "required", []
            )
            for field_name in (
                "score",
                "status",
                "satisfied_goal_ids",
                "unmet_goal_ids",
                "unmet_requirements",
                "rationale",
            ):
                if field_name not in satisfaction_required:
                    satisfaction_required.append(field_name)
            top_satisfaction = properties.get("goal_satisfaction")
            if isinstance(top_satisfaction, dict):
                top_satisfaction.clear()
                top_satisfaction.update(copy.deepcopy(satisfaction_schema))
                top_satisfaction["description"] = (
                    "Required prospective adequacy judgment for the complete "
                    "Deep Planner result, including clarify/unavailable/refused."
                )

        if (
            isinstance(goal_outcomes, dict)
            and isinstance(outcome_schema, dict)
        ):
            outcome_properties = goal_outcomes.get("properties", {})
            for goal_id in allowed_goals:
                goal_property = outcome_properties.get(goal_id)
                if not isinstance(goal_property, dict):
                    continue
                specialized = copy.deepcopy(outcome_schema)
                specialized_properties = specialized.get("properties", {})
                if isinstance(satisfaction_schema, dict):
                    specialized_satisfaction = copy.deepcopy(
                        satisfaction_schema
                    )
                    satisfaction_properties = specialized_satisfaction.get(
                        "properties", {}
                    )
                    for field_name in (
                        "satisfied_goal_ids",
                        "unmet_goal_ids",
                    ):
                        field = satisfaction_properties.get(field_name)
                        if isinstance(field, dict):
                            field["items"] = {
                                "type": "string",
                                "enum": [goal_id],
                            }
                            field["uniqueItems"] = True
                            field["maxItems"] = 1
                    specialized_properties["satisfaction"] = (
                        specialized_satisfaction
                    )
                if requires_execution and goal_id not in response_goal_set:
                    disposition_field = specialized_properties.get(
                        "disposition"
                    )
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = [
                            "execute",
                            "clarify",
                            "unavailable",
                            "refused",
                        ]
                    response_text_field = specialized_properties.get(
                        "response_text"
                    )
                    if isinstance(response_text_field, dict):
                        response_text_field["maxLength"] = 0
                        response_text_field["description"] = (
                            "Planner outcomes on a tool route contain no speech "
                            "and never predict the tool result."
                        )
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {})
                                .get("disposition", {})
                                .get("enum")
                                != ["respond"]
                            )
                        ]
                if goal_id in response_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = ["respond"]
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("maxLength", None)
                        response_text_field["minLength"] = 1
                        response_text_field["description"] = (
                            "Required direct response that completes this "
                            "Goal Association-authored spoken responsibility."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict):
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {})
                                .get("disposition", {})
                                .get("enum")
                                == ["respond"]
                            )
                        ]
                goal_property.clear()
                goal_property.update(specialized)
                goal_property["description"] = (
                    "Complete model-authored Deep Planner outcome for "
                    f"authoritative goal {goal_id!r}."
                )

    if response_only:
        steps_schema = properties.get("steps")
        if isinstance(steps_schema, dict):
            steps_schema["maxItems"] = 0
            steps_schema["description"] = (
                "The source route is conversational and authorizes no "
                "executable effects; return no plan steps."
            )

    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if isinstance(step_schema, dict):
        step_required = step_schema.setdefault("required", [])
        for field_name in ("step_id", "capability_id", "args", "source_goal_ids"):
            if field_name not in step_required:
                step_required.append(field_name)
    return schema


def fast_multi_goal_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_skill_ids: list[str],
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a decoder-tight, model-authored multi-goal plan schema.

    The Fast Planner model authors the semantic plan itself: aggregate
    disposition and coverage, executable steps, exact step ownership,
    per-goal outcomes, response text, escalation judgments, and prospective
    satisfaction.  The host adds only envelope identity fields after validation.

    Every field needed by deterministic validation is required at the JSON
    decoder boundary.  Semantic escalation is represented by model-authored
    per-goal ``escalate`` outcomes rather than an empty host-interpreted map.
    This avoids phrase-to-action rules and avoids the previous gap where the
    decoder accepted an object that the planner contract necessarily rejected.
    """

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = "FastPlannerMultiGoalPlanOutput"
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in (
        "disposition",
        "coverage",
        "confidence",
        "goal_summary",
        "response_text",
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "goal_outcomes",
        "goal_satisfaction",
        "plan_relation",
        "user_confirmation_required",
    ):
        if field_name not in required:
            required.append(field_name)

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["enum"] = (
            ["respond", "clarify", "escalate"]
            if response_only
            else ["execute", "mixed", "clarify", "escalate"]
            if requires_execution and response_goal_ids
            else ["execute", "clarify", "escalate"]
            if requires_execution
            else ["respond", "execute", "mixed", "clarify", "escalate"]
        )

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_skills = list(dict.fromkeys(allowed_skill_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)

    def bound_text(
        owner: dict[str, Any],
        field_name: str,
        maximum: int,
    ) -> None:
        field = owner.get(field_name)
        if isinstance(field, dict):
            field["maxLength"] = maximum

    # Repeated prose in several semantically redundant fields previously made
    # otherwise simple plans consume most of the decoder budget.  Keep the
    # semantic judgments model-authored while bounding their representation.
    bound_text(properties, "goal_summary", 240)
    bound_text(properties, "response_text", 0 if requires_execution else 800)
    if requires_execution:
        response_text_field = properties.get("response_text")
        if isinstance(response_text_field, dict):
            response_text_field["description"] = (
                "Tool-route planning contains no user-facing speech and never "
                "predicts a tool result."
            )
    bound_text(properties, "escalation_reason", 240)
    top_unresolved = properties.get("unresolved")
    if isinstance(top_unresolved, dict):
        top_unresolved["maxItems"] = max(4, len(allowed_goals))
        if isinstance(top_unresolved.get("items"), dict):
            top_unresolved["items"]["maxLength"] = 240
    parameter_resolutions = properties.get("parameter_resolutions")
    if isinstance(parameter_resolutions, dict):
        parameter_resolutions["maxItems"] = max(4, len(allowed_goals) * 4)

    steps = properties.get("steps")
    if isinstance(steps, dict):
        # Fast multi-goal terminal scope is deliberately limited to simple
        # goals: at most one executable step per authoritative goal.  Besides
        # documenting that boundary, the decoder limit prevents a malformed
        # model response from repeating one physical step until num_predict is
        # exhausted.  A goal that needs multiple skills belongs in Deep
        # Planning through a model-authored semantic escalation.
        steps["maxItems"] = len(allowed_goals)
        steps["description"] = (
            "At most one executable step per authoritative goal. A skill's "
            "count argument represents repeated motions; never duplicate a "
            "step to implement count. Conversational respond goals have no step."
        )

    if response_only:
        response_only_steps = properties.get("steps")
        if isinstance(response_only_steps, dict):
            response_only_steps["maxItems"] = 0
            response_only_steps["description"] = (
                "The source route is conversational and authorizes no "
                "executable effects; return no plan steps."
            )

    goal_outcomes = properties.get("goal_outcomes")
    if isinstance(goal_outcomes, dict):
        goal_outcomes.clear()
        goal_outcomes.update(
            {
                "type": "object",
                "properties": {
                    goal_id: {
                        "$ref": "#/$defs/PlannerModelGoalOutcome",
                        "description": (
                            "The Fast Planner's complete semantic outcome for "
                            "this exact authoritative goal."
                        ),
                    }
                    for goal_id in allowed_goals
                },
                "required": allowed_goals,
                "additionalProperties": False,
                "minProperties": len(allowed_goals),
                "maxProperties": len(allowed_goals),
            }
        )

    # Fast multi-goal output always carries a model-authored satisfaction
    # judgment, including an unsatisfied/partial judgment when escalating.
    goal_satisfaction = properties.get("goal_satisfaction")
    if isinstance(goal_satisfaction, dict):
        goal_satisfaction.clear()
        goal_satisfaction.update({"$ref": "#/$defs/PlannerGoalSatisfaction"})

    outcome_schema = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
    if isinstance(outcome_schema, dict):
        outcome_required = outcome_schema.setdefault("required", [])
        for field_name in (
            "disposition",
            "coverage",
            "response_text",
            "unresolved",
            "step_ids",
            "satisfaction",
            "rationale",
        ):
            if field_name not in outcome_required:
                outcome_required.append(field_name)
        outcome_properties = outcome_schema.get("properties", {})
        bound_text(outcome_properties, "response_text", 800)
        bound_text(outcome_properties, "rationale", 200)
        outcome_unresolved = outcome_properties.get("unresolved")
        if isinstance(outcome_unresolved, dict):
            outcome_unresolved["maxItems"] = 4
            if isinstance(outcome_unresolved.get("items"), dict):
                outcome_unresolved["items"]["maxLength"] = 240
        outcome_disposition = outcome_properties.get("disposition")
        if isinstance(outcome_disposition, dict):
            outcome_disposition["enum"] = (
                ["respond", "clarify", "escalate"]
                if response_only
                else ["execute", "clarify", "escalate"]
                if requires_execution
                else ["respond", "execute", "clarify", "escalate"]
            )
        if response_only:
            step_ids = outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = 0
        satisfaction = outcome_properties.get("satisfaction")
        if isinstance(satisfaction, dict):
            satisfaction.clear()
            satisfaction.update({"$ref": "#/$defs/PlannerGoalSatisfaction"})

    satisfaction_schema = schema.get("$defs", {}).get("PlannerGoalSatisfaction")
    if isinstance(satisfaction_schema, dict):
        satisfaction_required = satisfaction_schema.setdefault("required", [])
        for field_name in (
            "score",
            "status",
            "satisfied_goal_ids",
            "unmet_goal_ids",
            "unmet_requirements",
            "rationale",
        ):
            if field_name not in satisfaction_required:
                satisfaction_required.append(field_name)
        satisfaction_properties = satisfaction_schema.get("properties", {})
        bound_text(satisfaction_properties, "rationale", 200)
        unmet_requirements = satisfaction_properties.get("unmet_requirements")
        if isinstance(unmet_requirements, dict):
            unmet_requirements["maxItems"] = 4
            if isinstance(unmet_requirements.get("items"), dict):
                unmet_requirements["items"]["maxLength"] = 240
            unmet_requirements["description"] = (
                "Actual planning gaps only. Pending execution, the text of a "
                "covered goal, and sibling goals are not unmet requirements. "
                "This must be empty when status is exact."
            )

    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if isinstance(step_schema, dict):
        step_required = step_schema.setdefault("required", [])
        for field_name in (
            "step_id",
            "capability_id",
            "args",
            "timing",
            "source_goal_ids",
            "reason_summary",
        ):
            if field_name not in step_required:
                step_required.append(field_name)
        step_id = step_schema.get("properties", {}).get("step_id")
        if isinstance(step_id, dict):
            step_id["minLength"] = 1
        bound_text(step_schema.get("properties", {}), "reason_summary", 160)

    resolution_schema = schema.get("$defs", {}).get("PlanParameterResolution")
    if isinstance(resolution_schema, dict):
        resolution_required = resolution_schema.setdefault("required", [])
        for field_name in (
            "step_id",
            "parameter",
            "strategy",
            "value",
            "confidence",
            "blocking",
            "rationale",
            "source_goal_ids",
        ):
            if field_name not in resolution_required:
                resolution_required.append(field_name)
        resolution_properties = resolution_schema.get("properties", {})
        bound_text(resolution_properties, "rationale", 160)
        parameter = resolution_properties.get("parameter")
        if isinstance(parameter, dict):
            parameter["description"] = (
                "Copy exactly one argument key from the referenced step's args "
                "object, such as speed_mps or duration_s. Do not prefix it "
                "with a step ID or capability ID."
            )
    goal_list_fields = {
        "goal_ids",
        "source_goal_ids",
        "satisfied_goal_ids",
        "unmet_goal_ids",
    }

    def constrain(node: Any) -> None:
        if isinstance(node, dict):
            node_properties = node.get("properties")
            if isinstance(node_properties, dict):
                capability_id = node_properties.get("capability_id")
                if isinstance(capability_id, dict) and allowed_skills:
                    capability_id["enum"] = allowed_skills
                for field_name in goal_list_fields:
                    field = node_properties.get(field_name)
                    if isinstance(field, dict) and allowed_goals:
                        field["items"] = {
                            "type": "string",
                            "enum": allowed_goals,
                        }
                        field["uniqueItems"] = True
                        if field_name == "source_goal_ids":
                            field["minItems"] = 1
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)

    def strict_satisfaction_schema(
        base: dict[str, Any],
        *,
        exact_satisfied_count: int,
    ) -> dict[str, Any]:
        """Align decoder branches with the satisfaction validator bands."""

        branches: list[dict[str, Any]] = []
        bands = (
            ("exact", 0.95, 1.0),
            ("substantial", 0.75, 0.949999),
            ("partial", 0.01, 0.749999),
            ("unsatisfied", 0.0, 0.0),
        )
        for status_value, minimum, maximum in bands:
            branch = copy.deepcopy(base)
            branch_properties = branch.setdefault("properties", {})
            status = branch_properties.setdefault("status", {})
            status.clear()
            status.update({"type": "string", "enum": [status_value]})
            score = branch_properties.setdefault("score", {})
            score["minimum"] = minimum
            score["maximum"] = maximum
            if status_value == "exact":
                for field_name in ("unmet_goal_ids", "unmet_requirements"):
                    field_schema = branch_properties.get(field_name)
                    if isinstance(field_schema, dict):
                        field_schema["maxItems"] = 0
                satisfied = branch_properties.get("satisfied_goal_ids")
                if isinstance(satisfied, dict):
                    satisfied["minItems"] = exact_satisfied_count
                    satisfied["maxItems"] = exact_satisfied_count
            branches.append(branch)
        return {
            "anyOf": branches,
            "description": (
                "Prospective plan adequacy. The selected status branch enforces "
                "its score band; exact satisfaction requires all planned goals "
                "in satisfied_goal_ids and both unmet lists empty."
            ),
        }

    if isinstance(goal_satisfaction, dict) and isinstance(satisfaction_schema, dict):
        goal_satisfaction.clear()
        goal_satisfaction.update(
            strict_satisfaction_schema(
                satisfaction_schema,
                exact_satisfied_count=len(allowed_goals),
            )
        )

    # A goal_outcomes key already identifies the one goal being judged.  The
    # generic model schema cannot express that a nested satisfaction object may
    # reference only its enclosing key, so specialize each decoder property.
    # This is contract/schema alignment, not semantic compilation: the model
    # still authors the disposition, step link, score, status, and rationale.
    # It simply cannot mislabel unrelated sibling goals as unmet inside a
    # goal-specific judgment and then fail the deterministic validator.
    if (
        isinstance(goal_outcomes, dict)
        and isinstance(outcome_schema, dict)
        and isinstance(satisfaction_schema, dict)
    ):
        outcome_properties = goal_outcomes.get("properties", {})
        for goal_id in allowed_goals:
            goal_property = outcome_properties.get(goal_id)
            if not isinstance(goal_property, dict):
                continue
            specialized_outcome = copy.deepcopy(outcome_schema)
            specialized_satisfaction = copy.deepcopy(satisfaction_schema)
            specialized_satisfaction_properties = specialized_satisfaction.get(
                "properties", {}
            )
            for field_name in ("satisfied_goal_ids", "unmet_goal_ids"):
                field_schema = specialized_satisfaction_properties.get(field_name)
                if isinstance(field_schema, dict):
                    field_schema["items"] = {"type": "string", "enum": [goal_id]}
                    field_schema["uniqueItems"] = True
                    field_schema["maxItems"] = 1
            satisfied = specialized_satisfaction_properties.get(
                "satisfied_goal_ids"
            )
            if isinstance(satisfied, dict):
                satisfied["description"] = (
                    f"Only {goal_id!r} may appear here. Include it when this "
                    "goal's proposed step or response would satisfy it."
                )
            unmet = specialized_satisfaction_properties.get("unmet_goal_ids")
            if isinstance(unmet, dict):
                unmet["description"] = (
                    f"Only {goal_id!r} may appear here, and only for an actual "
                    "planning gap. Pending execution and sibling goals do not "
                    "belong here; exact satisfaction requires an empty list."
                )
            specialized_outcome_properties = specialized_outcome.get(
                "properties", {}
            )
            if requires_execution and goal_id not in response_goal_set:
                disposition_field = specialized_outcome_properties.get(
                    "disposition"
                )
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["execute", "clarify", "escalate"]
                response_text_field = specialized_outcome_properties.get(
                    "response_text"
                )
                if isinstance(response_text_field, dict):
                    response_text_field["maxLength"] = 0
                    response_text_field["description"] = (
                        "Tool-route planner outcomes contain no speech and never "
                        "predict tool evidence."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {})
                            .get("disposition", {})
                            .get("enum")
                            != ["respond"]
                        )
                    ]
            if goal_id in response_goal_set:
                disposition_field = specialized_outcome_properties.get(
                    "disposition"
                )
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["respond"]
                response_text_field = specialized_outcome_properties.get(
                    "response_text"
                )
                if isinstance(response_text_field, dict):
                    response_text_field.pop("maxLength", None)
                    response_text_field["minLength"] = 1
                    response_text_field["description"] = (
                        "Required direct response that completes this Goal "
                        "Association-authored spoken responsibility."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {})
                            .get("disposition", {})
                            .get("enum")
                            == ["respond"]
                        )
                    ]
            specialized_outcome_properties["satisfaction"] = strict_satisfaction_schema(
                specialized_satisfaction,
                exact_satisfied_count=1,
            )
            step_ids = specialized_outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = (
                    0 if goal_id in response_goal_set else 1
                )
                step_ids["uniqueItems"] = True
                step_ids["description"] = (
                    "No executable step may be owned by this direct-response Goal."
                    if goal_id in response_goal_set
                    else "The one simple Fast Planner step owned by this goal, or an "
                    "empty list for respond/clarify/escalate."
                )
            goal_property.clear()
            goal_property.update(specialized_outcome)
            goal_property["description"] = (
                "The complete model-authored outcome for authoritative goal "
                f"{goal_id!r}. Satisfaction evaluates this goal only."
            )

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["description"] = (
            "Aggregate the already-authored goal_outcomes: execute when all "
            "outcomes execute, respond when all respond, mixed when execute and "
            "respond are both present, clarify when all clarify, and escalate when all escalate."
        )

    # Encode the aggregate invariant in the decoder grammar.  The model still
    # chooses each goal's semantic disposition; this cross-field constraint
    # only makes the redundant top-level aggregate and executable-step count
    # consistent with those model-authored choices.  Enumerating the small
    # execute/respond assignment space avoids a host-side semantic compiler.
    # Larger turns are outside the Fast terminal surface and retain the normal
    # validator/Deep Planner path rather than exploding the response schema.
    if 1 < len(allowed_goals) <= 6:
        assignment_branches: list[dict[str, Any]] = []
        assignment_choices = [
            ("respond",)
            if goal_id in response_goal_set
            else (("execute",) if requires_execution else ("execute", "respond"))
            for goal_id in allowed_goals
        ]
        assignments = list(product(*assignment_choices))
        assignments.append(tuple("clarify" for _ in allowed_goals))
        assignments.append(tuple("escalate" for _ in allowed_goals))
        for assignment in assignments:
            assignment_set = set(assignment)
            if requires_execution and assignment_set == {"respond"}:
                continue
            if assignment_set == {"execute"}:
                aggregate = "execute"
            elif assignment_set == {"respond"}:
                aggregate = "respond"
            elif assignment_set == {"clarify"}:
                aggregate = "clarify"
            elif assignment_set == {"escalate"}:
                aggregate = "escalate"
            else:
                aggregate = "mixed"
            execute_count = sum(item == "execute" for item in assignment)
            branch: dict[str, Any] = {
                "properties": {
                    "disposition": {"type": "string", "enum": [aggregate]},
                    "steps": {
                        "type": "array",
                        "minItems": execute_count,
                        "maxItems": execute_count,
                    },
                    "goal_outcomes": {
                        "type": "object",
                        "properties": {
                            goal_id: {
                                "type": "object",
                                "properties": {
                                    "disposition": {
                                        "type": "string",
                                        "enum": [goal_disposition],
                                    }
                                },
                            }
                            for goal_id, goal_disposition in zip(
                                allowed_goals, assignment, strict=True
                            )
                        },
                    },
                }
            }
            assignment_branches.append(branch)
        schema.setdefault("allOf", []).append({"anyOf": assignment_branches})

    _constrain_plan_relation_confirmation(schema)

    # The structured decoder normally emits object fields in schema order.
    # Place per-goal outcomes before steps and aggregate disposition so the
    # model authors goal meaning first; the generic cross-field grammar can
    # then bound the number of simple executable steps and aggregate it.
    preferred_property_order = (
        "goal_summary",
        "goal_outcomes",
        "steps",
        "goal_satisfaction",
        "disposition",
        "coverage",
        "confidence",
        "response_text",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "plan_relation",
        "user_confirmation_required",
    )
    schema["properties"] = {
        key: properties[key]
        for key in preferred_property_order
        if key in properties
    }
    return schema


def _constrain_plan_relation_confirmation(schema: dict[str, Any]) -> None:
    """Align material plan changes with decoder-enforced confirmation."""

    schema.setdefault("allOf", []).append(
        {
            "anyOf": [
                {
                    "properties": {
                        "plan_relation": {
                            "type": "string",
                            "enum": ["exact"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [False],
                        },
                    }
                },
                {
                    "properties": {
                        "plan_relation": {
                            "type": "string",
                            "enum": ["safe_adjustment", "alternative"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [True],
                        },
                        "response_text": {
                            "type": "string",
                            "minLength": 1,
                        },
                    }
                },
            ]
        }
    )


def planner_contract_diagnostics(
    raw: Any,
    *,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> list[dict[str, Any]]:
    """Collect independent planner-contract defects without short-circuiting.

    Pydantic intentionally validates nested values before parent model validators.
    That means one invalid nested satisfaction object can hide a missing
    ``step_ids`` or ``response_text`` defect in the same goal outcome.  The
    planners allow only one same-tier/schema repair, so repair feedback must
    expose all independently observable structural defects from the original
    model output rather than only the first validation layer that failed.

    This function is diagnostic only.  It never rewrites model-authored meaning
    or fills missing ownership/response fields.
    """

    if not isinstance(raw, dict):
        return []

    diagnostics: list[dict[str, Any]] = []

    def add(
        loc: list[str | int],
        msg: str,
        *,
        value: Any = None,
        error_type: str = "value_error",
    ) -> None:
        diagnostics.append(
            {
                "type": error_type,
                "loc": loc,
                "msg": msg,
                "input": value,
                "source": "planner_contract_diagnostics",
            }
        )

    def satisfaction_status_for_score(score: float) -> GoalSatisfactionStatus:
        if score >= 0.95:
            return "exact"
        if score >= 0.75:
            return "substantial"
        if score > 0.0:
            return "partial"
        return "unsatisfied"

    def inspect_satisfaction(value: Any, loc: list[str | int]) -> None:
        if not isinstance(value, dict):
            return
        score = value.get("score")
        status = value.get("status")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return
        if not isinstance(status, str):
            return
        if not 0.0 <= float(score) <= 1.0:
            return
        expected = satisfaction_status_for_score(float(score))
        if status != expected:
            add(
                loc,
                (
                    "goal satisfaction score is inconsistent with status; "
                    f"score={float(score):g} requires status={expected!r}"
                ),
                value=value,
            )

    steps = raw.get("steps")
    if not isinstance(steps, list):
        steps = []
    step_ids: set[str] = set()
    step_sources: dict[str, set[str]] = {}
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            continue
        step_id = " ".join(str(item.get("step_id") or "").strip().split())
        if step_id:
            step_ids.add(step_id)
            source_goal_ids = item.get("source_goal_ids")
            if isinstance(source_goal_ids, str):
                source_goal_ids = [source_goal_ids]
            if isinstance(source_goal_ids, list):
                for source_goal_id in source_goal_ids:
                    goal_id = " ".join(str(source_goal_id or "").strip().split())
                    if goal_id:
                        step_sources.setdefault(step_id, set()).add(goal_id)
        elif item.get("capability_id") or item.get("skill_id"):
            add(
                ["steps", index, "step_id"],
                "executable planner step requires step_id",
                value=item,
                error_type="missing",
            )

    disposition = raw.get("disposition")
    coverage = raw.get("coverage")
    response_text = str(raw.get("response_text") or "").strip()
    if coverage != "complete" and steps:
        add(
            ["steps"],
            "non-complete planner output must not carry executable steps",
            value=steps,
        )
    if disposition == "execute" and not steps:
        add(
            ["steps"],
            "execute planner output requires at least one step",
            value=steps,
        )
    if disposition == "mixed" and not steps:
        add(
            ["steps"],
            "mixed planner output requires steps and goal_outcomes",
            value=steps,
        )
    if disposition == "respond" and not response_text:
        add(
            ["response_text"],
            "respond planner output requires response_text",
            value=raw.get("response_text"),
        )
    if disposition not in {"execute", "mixed"} and steps:
        add(
            ["steps"],
            f"{disposition} planner output must not carry executable steps",
            value=steps,
        )
    if disposition in {"execute", "respond", "mixed"} and coverage != "complete":
        add(
            ["coverage"],
            "execute, respond, and mixed planner output requires complete coverage",
            value=coverage,
        )
    if disposition in {"execute", "respond", "mixed"} and not isinstance(
        raw.get("goal_satisfaction"), dict
    ):
        add(
            ["goal_satisfaction"],
            "complete executable or response output requires goal_satisfaction",
            value=raw.get("goal_satisfaction"),
        )
    inspect_satisfaction(raw.get("goal_satisfaction"), ["goal_satisfaction"])

    outcomes = raw.get("goal_outcomes")
    expected_goal_ids = list(dict.fromkeys(expected_goal_ids_for_turn))
    expected_goal_set = set(expected_goal_ids)
    multi_goal_fast = planner_tier == "fast" and len(expected_goal_set) > 1
    fast_escalation = planner_tier == "fast" and disposition == "escalate"

    if multi_goal_fast and "goal_outcomes" not in raw:
        add(
            ["goal_outcomes"],
            "multi-goal fast planner output requires an explicit goal_outcomes object",
            value=None,
            error_type="missing",
        )
    if fast_escalation:
        if coverage not in {"partial", "uncertain"}:
            add(
                ["coverage"],
                "fast semantic escalation requires partial or uncertain coverage",
                value=coverage,
            )
        if multi_goal_fast:
            satisfaction = raw.get("goal_satisfaction")
            if not isinstance(satisfaction, dict):
                add(
                    ["goal_satisfaction"],
                    "multi-goal fast escalation requires model-authored goal_satisfaction",
                    value=satisfaction,
                )
            elif satisfaction.get("status") == "exact":
                add(
                    ["goal_satisfaction", "status"],
                    "fast semantic escalation cannot claim exact goal satisfaction",
                    value=satisfaction.get("status"),
                )
        else:
            if isinstance(outcomes, dict) and outcomes:
                add(
                    ["goal_outcomes"],
                    "single-goal fast semantic escalation requires goal_outcomes={}",
                    value=outcomes,
                )
            if raw.get("goal_satisfaction") is not None:
                add(
                    ["goal_satisfaction"],
                    "single-goal fast semantic escalation requires goal_satisfaction=null",
                    value=raw.get("goal_satisfaction"),
                )
    if isinstance(outcomes, dict):
        outcome_goal_set = set(outcomes)
        require_complete_outcome_map = not fast_escalation or multi_goal_fast
        if require_complete_outcome_map and outcome_goal_set != expected_goal_set:
            add(
                ["goal_outcomes"],
                (
                    "goal_outcomes keys must cover exactly the authoritative Goal "
                    "Association IDs"
                ),
                value={
                    "expected": expected_goal_ids,
                    "actual": list(outcomes),
                },
            )

        outcome_dispositions: set[str] = set()
        referenced_steps: set[str] = set()
        executable_owners_by_step: dict[str, set[str]] = {}
        for goal_id, outcome in outcomes.items():
            if not isinstance(outcome, dict):
                continue
            outcome_disposition = outcome.get("disposition")
            outcome_coverage = outcome.get("coverage")
            outcome_response = str(outcome.get("response_text") or "").strip()
            outcome_step_ids = outcome.get("step_ids")
            if isinstance(outcome_step_ids, str):
                outcome_step_ids = [outcome_step_ids]
            if not isinstance(outcome_step_ids, list):
                outcome_step_ids = []
            normalized_outcome_step_ids = [
                " ".join(str(item or "").strip().split())
                for item in outcome_step_ids
                if " ".join(str(item or "").strip().split())
            ]
            outcome_dispositions.add(str(outcome_disposition or ""))
            if planner_tier == "fast" and outcome_disposition not in {
                "execute",
                "respond",
                "clarify",
                "escalate",
            }:
                add(
                    ["goal_outcomes", goal_id, "disposition"],
                    "fast goal outcomes may only execute, respond, clarify, or escalate",
                    value=outcome_disposition,
                )
            inspect_satisfaction(
                outcome.get("satisfaction"),
                ["goal_outcomes", goal_id, "satisfaction"],
            )

            if outcome_disposition == "execute":
                if outcome_coverage != "complete" or not normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id],
                        "execute goal outcome requires complete coverage and step_ids",
                        value=outcome,
                    )
                for step_id in normalized_outcome_step_ids:
                    referenced_steps.add(step_id)
                    executable_owners_by_step.setdefault(step_id, set()).add(goal_id)
            elif outcome_disposition == "respond":
                if outcome_coverage != "complete" or not outcome_response:
                    add(
                        ["goal_outcomes", goal_id],
                        "respond goal outcome requires complete coverage and response_text",
                        value=outcome,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "respond goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
            elif outcome_disposition == "escalate":
                if outcome_coverage not in {"partial", "uncertain"}:
                    add(
                        ["goal_outcomes", goal_id, "coverage"],
                        "escalate goal outcome requires partial or uncertain coverage",
                        value=outcome_coverage,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "escalate goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
                if outcome_response:
                    add(
                        ["goal_outcomes", goal_id, "response_text"],
                        "escalate goal outcome must not claim a conversational answer",
                        value=outcome_response,
                    )
                if not outcome.get("unresolved") and not str(
                    outcome.get("rationale") or ""
                ).strip():
                    add(
                        ["goal_outcomes", goal_id],
                        "escalate goal outcome requires an unresolved need or rationale",
                        value=outcome,
                    )
            elif outcome_disposition == "clarify":
                if outcome_coverage not in {"partial", "uncertain"}:
                    add(
                        ["goal_outcomes", goal_id, "coverage"],
                        "clarify goal outcome requires partial or uncertain coverage",
                        value=outcome_coverage,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "clarify goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
                unresolved = outcome.get("unresolved")
                if not outcome_response and not unresolved:
                    add(
                        ["goal_outcomes", goal_id],
                        "clarify goal outcome requires an unresolved need or response_text",
                        value=outcome,
                    )
            elif normalized_outcome_step_ids:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "unavailable and refused goal outcomes must not reference steps",
                    value=normalized_outcome_step_ids,
                )

            unknown_steps = set(normalized_outcome_step_ids) - step_ids
            if unknown_steps:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "goal outcome references unknown step IDs: "
                    + ",".join(sorted(unknown_steps)),
                    value=normalized_outcome_step_ids,
                )

        normalized_dispositions = {item for item in outcome_dispositions if item}
        if normalized_dispositions:
            expected_disposition = (
                "mixed"
                if len(normalized_dispositions) > 1
                else next(iter(normalized_dispositions))
            )
            if disposition != expected_disposition:
                add(
                    ["disposition"],
                    "top-level disposition must match per-goal outcome dispositions",
                    value={
                        "actual": disposition,
                        "expected": expected_disposition,
                        "outcome_dispositions": sorted(normalized_dispositions),
                    },
                )

        if step_ids and referenced_steps != step_ids:
            add(
                ["goal_outcomes"],
                "every executable step must belong to at least one goal outcome: "
                + ",".join(sorted(step_ids - referenced_steps)),
                value=outcomes,
            )
        for step_id, sources in step_sources.items():
            expected_sources = executable_owners_by_step.get(step_id, set())
            if expected_sources and sources != expected_sources:
                add(
                    ["steps", step_id, "source_goal_ids"],
                    (
                        f"step {step_id!r} source_goal_ids must exactly match the "
                        "executable goal outcomes that reference it"
                    ),
                    value={
                        "actual": sorted(sources),
                        "expected": sorted(expected_sources),
                    },
                )
    elif (
        len(expected_goal_set) > 1
        and disposition in {"execute", "respond", "mixed"}
    ):
        add(
            ["goal_outcomes"],
            (
                "complete multi-goal planner output requires goal_outcomes keyed by "
                "every authoritative Goal Association ID"
            ),
            value=outcomes,
        )

    if planner_tier == "deep" and disposition == "escalate":
        add(
            ["disposition"],
            "deep plans cannot return to the fast planner",
            value=disposition,
        )

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str | int, ...]]] = set()
    for item in diagnostics:
        key = (str(item.get("msg") or ""), tuple(item.get("loc") or []))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _normalize_redundant_planner_response_fields(
    raw: dict[str, Any],
    *,
    expected_goal_ids_for_turn: list[str],
) -> dict[str, Any]:
    """Normalize duplicate response fields without inventing semantics.

    Planner models occasionally place the exact response only inside the sole
    per-Goal outcome while omitting the same required top-level transport field,
    or omit outcome disposition/coverage that are already explicit at the top
    level.  The Host may copy those identical structural facts; it may not choose
    a capability, rewrite a Goal, or synthesize response content.
    """

    normalized = dict(raw)
    outcomes = normalized.get("goal_outcomes")
    if not isinstance(outcomes, dict):
        return normalized

    normalized_outcomes: dict[str, Any] = {}
    for goal_id, value in outcomes.items():
        if not isinstance(value, dict):
            normalized_outcomes[str(goal_id)] = value
            continue
        outcome = dict(value)
        response_text = str(outcome.get("response_text") or "").strip()
        step_ids = outcome.get("step_ids")
        if not outcome.get("disposition"):
            if isinstance(step_ids, list) and step_ids:
                outcome["disposition"] = "execute"
            elif response_text:
                outcome["disposition"] = "respond"
        if (
            not outcome.get("coverage")
            and normalized.get("coverage") == "complete"
            and outcome.get("disposition") in {"execute", "respond"}
        ):
            outcome["coverage"] = "complete"
        normalized_outcomes[str(goal_id)] = outcome
    normalized["goal_outcomes"] = normalized_outcomes

    if (
        normalized.get("disposition") == "respond"
        and not str(normalized.get("response_text") or "").strip()
        and len(expected_goal_ids_for_turn) == 1
    ):
        sole = normalized_outcomes.get(expected_goal_ids_for_turn[0])
        if isinstance(sole, dict):
            response_text = str(sole.get("response_text") or "").strip()
            if response_text:
                normalized["response_text"] = response_text
    return normalized


def validate_planner_model_output(
    raw: dict[str, Any],
    *,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> PlannerModelOutput:
    """Validate the semantic DTO and reject conflicting legacy goal echoes."""

    model_raw = _normalize_redundant_planner_response_fields(
        dict(raw),
        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
    )
    echoed_goal_ids = model_raw.pop("goal_ids", None)
    for field_name in ("schema_version", "plan_id", "planner_tier"):
        model_raw.pop(field_name, None)

    if echoed_goal_ids is not None:
        if isinstance(echoed_goal_ids, str):
            echoed_goal_ids = [echoed_goal_ids]
        if not isinstance(echoed_goal_ids, list):
            raise ValueError("planner goal_ids echo must be a list when present")
        normalized_echo = list(
            dict.fromkeys(
                " ".join(str(item or "").strip().split())
                for item in echoed_goal_ids
                if " ".join(str(item or "").strip().split())
            )
        )
        if expected_goal_ids_for_turn and set(normalized_echo) != set(
            expected_goal_ids_for_turn
        ):
            raise ValueError(
                "goal_ids_do_not_match_goal_association: planner echo conflicts "
                "with authoritative Goal Association IDs"
            )

    raw_steps = model_raw.get("steps")
    output = PlannerModelOutput.model_validate(model_raw)

    if isinstance(raw_steps, list):
        for index, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                continue
            missing_authority_fields = [
                field_name
                for field_name in ("step_id", "source_goal_ids")
                if field_name not in item
            ]
            if missing_authority_fields:
                raise ValueError(
                    f"planner step {index} requires explicit model-authored authority fields: "
                    + ",".join(missing_authority_fields)
                )
    allowed_dispositions = (
        {"respond", "execute", "mixed", "clarify", "escalate"}
        if planner_tier == "fast"
        else {"respond", "execute", "mixed", "clarify", "unavailable", "refused"}
    )
    if output.disposition not in allowed_dispositions:
        raise ValueError(
            f"disposition={output.disposition!r} is not valid for planner_tier={planner_tier}"
        )
    goal_outcomes_were_supplied = "goal_outcomes" in model_raw
    outcome_goal_ids = set(output.goal_outcomes)
    expected_goal_id_set = set(expected_goal_ids_for_turn)
    if planner_tier == "fast" and len(expected_goal_id_set) > 1:
        missing_envelope_fields = [
            field_name
            for field_name in ("steps", "goal_outcomes", "goal_satisfaction")
            if field_name not in model_raw
        ]
        if missing_envelope_fields:
            raise ValueError(
                "multi-goal fast planner output requires explicit fields: "
                + ",".join(missing_envelope_fields)
            )
    if (
        planner_tier == "fast"
        and len(expected_goal_id_set) > 1
        and not goal_outcomes_were_supplied
    ):
        raise ValueError(
            "multi-goal fast planner output requires an explicit goal_outcomes object"
        )
    if planner_tier == "fast" and output.disposition == "escalate":
        if output.coverage not in {"partial", "uncertain"}:
            raise ValueError(
                "fast semantic escalation requires partial or uncertain coverage"
            )
        if len(expected_goal_id_set) <= 1:
            if output.goal_outcomes:
                raise ValueError(
                    "single-goal fast semantic escalation requires goal_outcomes={}"
                )
            if output.goal_satisfaction is not None:
                raise ValueError(
                    "single-goal fast semantic escalation requires goal_satisfaction=null"
                )
    if (
        len(expected_goal_id_set) > 1
        and output.disposition in {"execute", "respond", "mixed"}
        and not output.goal_outcomes
    ):
        raise ValueError(
            "complete multi-goal planner output requires goal_outcomes keyed by "
            "every authoritative Goal Association ID"
        )
    if (
        goal_outcomes_were_supplied
        and len(expected_goal_id_set) > 1
        and outcome_goal_ids != expected_goal_id_set
    ):
        raise ValueError(
            "goal_outcomes keys must cover exactly the authoritative Goal "
            "Association IDs"
        )
    if planner_tier == "fast" and output.goal_outcomes:
        outcome_dispositions = {
            outcome.disposition for outcome in output.goal_outcomes.values()
        }
        unsupported = outcome_dispositions - {"execute", "respond", "clarify", "escalate"}
        if unsupported:
            raise ValueError(
                "fast goal outcomes may only execute, respond, clarify, or escalate: "
                + ",".join(sorted(unsupported))
            )
        if "clarify" in outcome_dispositions:
            if outcome_dispositions != {"clarify"}:
                raise ValueError(
                    "fast clarification must not mix clarify outcomes with "
                    "execute or respond outcomes"
                )
            if output.disposition != "clarify":
                raise ValueError(
                    "all-clarify goal outcomes require top-level disposition=clarify"
                )
            if output.steps:
                raise ValueError("fast clarification must not carry steps")
        elif "escalate" in outcome_dispositions:
            if outcome_dispositions != {"escalate"}:
                raise ValueError(
                    "fast semantic escalation must not mix escalate outcomes "
                    "with execute or respond outcomes"
                )
            if output.disposition != "escalate":
                raise ValueError(
                    "all-escalate goal outcomes require top-level disposition=escalate"
                )
            if output.steps:
                raise ValueError("fast semantic escalation must not carry steps")
            if output.goal_satisfaction is None:
                raise ValueError(
                    "multi-goal fast semantic escalation requires model-authored "
                    "goal_satisfaction"
                )
            if output.goal_satisfaction.status == "exact":
                raise ValueError(
                    "fast semantic escalation cannot claim exact goal satisfaction"
                )
        elif output.disposition == "escalate":
            raise ValueError(
                "multi-goal fast escalation requires one escalate outcome per goal"
            )
        if output.disposition == "mixed" and outcome_dispositions != {
            "execute",
            "respond",
        }:
            raise ValueError(
                "fast mixed output requires at least one execute and one respond goal"
            )
    for goal_id, outcome in output.goal_outcomes.items():
        if planner_tier == "fast" and len(expected_goal_id_set) > 1:
            if outcome.satisfaction is None:
                raise ValueError(
                    "multi-goal fast outcomes require model-authored satisfaction"
                )
        referenced_goal_ids = {
            *(outcome.satisfaction.satisfied_goal_ids if outcome.satisfaction else []),
            *(outcome.satisfaction.unmet_goal_ids if outcome.satisfaction else []),
        }
        foreign_goal_ids = referenced_goal_ids - {goal_id}
        if foreign_goal_ids:
            raise ValueError(
                "per-goal outcome satisfaction may reference only its enclosing "
                f"authoritative goal ID {goal_id!r}; found "
                + ",".join(sorted(foreign_goal_ids))
            )
    if planner_tier == "fast" and len(expected_goal_id_set) > 1:
        if output.goal_satisfaction is None:
            raise ValueError(
                "multi-goal fast output requires model-authored goal_satisfaction"
            )
    if output.goal_satisfaction is not None:
        referenced_goal_ids = {
            *output.goal_satisfaction.satisfied_goal_ids,
            *output.goal_satisfaction.unmet_goal_ids,
        }
        foreign_goal_ids = referenced_goal_ids - expected_goal_id_set
        if foreign_goal_ids:
            raise ValueError(
                "top-level goal satisfaction references non-authoritative goal IDs: "
                + ",".join(sorted(foreign_goal_ids))
            )
    return output


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
