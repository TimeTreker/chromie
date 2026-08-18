from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from itertools import product
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

try:
    from chromie_contracts.interaction import (
        CapabilityIdentityModel,
        MEDIA_CAPABILITY_IDS,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.interaction import (
        CapabilityIdentityModel,
        MEDIA_CAPABILITY_IDS,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )

try:
    from chromie_contracts.goal import GoalAssociationResolution
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.goal import GoalAssociationResolution

try:
    from chromie_contracts.situation import SituationProjection
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.situation import SituationProjection

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

try:
    from chromie_contracts.resource import (
        AcquireAndDeliverResource,
        resource_semantic_bindings,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.resource import (
        AcquireAndDeliverResource,
        resource_semantic_bindings,
    )

try:
    from chromie_contracts.tool_result import ToolResultEvidence
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.tool_result import ToolResultEvidence

PlannerTier = Literal["fast", "deep"]
PlannerPlanRelation = Literal["exact", "safe_adjustment", "alternative"]

EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT = (
    "Treat an explicit numeric value in authoritative Goal text or a typed "
    "Goal binding as a "
    "user-supplied candidate for the matching catalog argument. When "
    "the value and units are unambiguous and the value is within the "
    "catalog schema, copy it exactly; never silently replace it with "
    "a schema default or describe it only in prose. Select a capability "
    "whose argument schema can represent the supplied value. Catalog "
    "defaults are only for parameters the user did not supply. If the "
    "units, argument mapping, or validity are uncertain, clarify or "
    "escalate according to the planner tier instead of claiming exact "
    "coverage. A material adjustment must use a non-exact plan_relation, "
    "require confirmation, and explain the change. For each numeric "
    "literal in an executable authoritative Goal's text or typed bindings, "
    "include a user_supplied "
    "parameter_resolution tied to the owned step and goal. The parameter "
    "field must be the exact bare key in that step's args object, never a "
    "step- or capability-qualified name. Its value must equal the step "
    "argument and its source_goal_ids must identify the authoritative Goal "
    "containing that same number. A typed binding is the model-owned canonical "
    "provenance for a quantity stated in words by the user. Use those stable "
    "Goal IDs as provenance. Never borrow a numeric literal or typed binding from "
    "a sibling Goal to fill another step. When an optional catalog argument was not "
    "supplied by the owning Goal, omit that argument and its resolution so the "
    "provider applies its declared default, or copy the exact catalog default with "
    "strategy=schema_default and no source_goal_ids. Never label a catalog default "
    "as user_supplied. "
    "do not copy, paraphrase, or annotate Goal text into another field. "
)

_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_LIST_ENTITY_TYPES = frozenset({"list", "action_list"})
_INFORMATION_TEMPORAL_ENTITY_TYPES = frozenset(
    {
        "day_part",
        "date",
        "date_range",
        "time",
        "time_frame",
        "time_period",
        "temporal_period",
        "temporal_scope",
    }
)
_LIST_LITERAL_SEPARATOR_RE = re.compile(r"[,，;；、]")


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
        return [text for item in value if (text := " ".join(str(item or "").strip().split()))]

    @model_validator(mode="after")
    def validate_decision(self) -> "PlannerCoverageReview":
        if self.decision == "accept" and self.uncovered_requirements:
            raise ValueError("accepted coverage cannot list uncovered requirements")
        if self.decision == "reject" and not self.uncovered_requirements:
            raise ValueError("rejected coverage requires uncovered requirements")
        return self


class PlannerCommunicationGoalResponse(BaseModel):
    """One model-reviewed conversational response for an authoritative Goal."""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    response_text: str = Field(min_length=1, max_length=2400)

    @field_validator("goal_id", "response_text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value


class PlannerCommunicationReview(BaseModel):
    """Bounded model review of a retained-evidence conversational follow-up."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "revise"]
    confidence: float = Field(ge=0.0, le=1.0)
    response_text: str = Field(min_length=1, max_length=2400)
    goal_responses: list[PlannerCommunicationGoalResponse] = Field(
        min_length=1,
        max_length=16,
    )
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("response_text", "reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_goal_responses(self) -> "PlannerCommunicationReview":
        goal_ids = [item.goal_id for item in self.goal_responses]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("communication review goal responses must be unique")
        return self


# Generic response transport is not a task-plan leaf. These runtime transport
# capabilities remain valid in legacy/native InteractionResponse task lists, but
# Fast/Deep planners express conversational intent through ``response_text`` or
# a ``respond`` outcome. Executable outcomes may also carry prospective
# ``response_text``; that speech never authorizes or proves the effect.
NON_PLANNER_TRANSPORT_CAPABILITY_IDS = frozenset({"chromie.speak"})


def is_planner_step_capability(capability_id: str) -> bool:
    return str(capability_id or "").strip() not in NON_PLANNER_TRANSPORT_CAPABILITY_IDS




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
            raise ValueError("unavailable and refused goal outcomes must not reference steps")
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
                "generic response transport is not an executable task-plan capability; "
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
        if self.goal_outcomes:
            outcome_dispositions = {item.disposition for item in self.goal_outcomes.values()}
            expected_disposition = (
                "mixed" if len(outcome_dispositions) > 1 else next(iter(outcome_dispositions))
            )
            if self.disposition != expected_disposition:
                raise ValueError("top-level disposition must match per-goal outcome dispositions")
        return self


def goal_association_prompt_projection(
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the closed Goal Association projection permitted in prompts.

    The maintained runtime supplies a validated ``GoalAssociationResolution``.
    Tests and compatibility callers may provide an older partial dictionary, so
    the dictionary path uses the same explicit allowlist without inventing
    missing fields or accepting diagnostic metadata.
    """

    raw = (context or {}).get("goal_association_resolution")
    if raw is None:
        return {}
    if isinstance(raw, GoalAssociationResolution):
        return raw.prompt_projection()
    if not isinstance(raw, dict):
        raise ValueError("goal_association_resolution must be an object")

    top_level_keys = (
        "schema_version",
        "turn_id",
        "confidence",
        "reason_summary",
    )
    association_keys = (
        "schema_version",
        "association_id",
        "relationship",
        "target_goal_ids",
        "confidence",
        "reason_summary",
        "ambiguity_summary",
        "goal_update",
        "resolved_gap_ids",
        "requires_replan",
    )
    goal_keys = (
        "schema_version",
        "goal_id",
        "version",
        "description",
        "source_text",
        "beneficiary",
        "object",
        "constraints",
        "success_criteria",
        "resource_responsibility",
    )
    projection = {key: copy.deepcopy(raw[key]) for key in top_level_keys if key in raw}
    projection["associations"] = [
        {key: copy.deepcopy(item[key]) for key in association_keys if key in item}
        for item in raw.get("associations") or []
        if isinstance(item, dict)
    ]
    goals: list[dict[str, Any]] = []
    for item in raw.get("new_goals") or []:
        if not isinstance(item, dict):
            continue
        goal = {key: copy.deepcopy(item[key]) for key in goal_keys if key in item}
        metadata = item.get("metadata")
        projected_metadata = (
            {
                key: copy.deepcopy(metadata[key])
                for key in (
                    "responsibility_kind",
                    "execution_lane",
                    "output_mode",
                    "provider_required",
                )
                if key in metadata
            }
            if isinstance(metadata, dict)
            else {}
        )
        if projected_metadata:
            goal["metadata"] = projected_metadata
        goals.append(goal)
    projection["new_goals"] = goals
    referent_keys = (
        "schema_version",
        "referent_id",
        "entity_type",
        "canonical_value",
        "aliases",
        "scope_kind",
        "scope_ids",
        "status",
        "confidence",
        "source_turn_id",
        "source_goal_ids",
        "supersedes_referent_ids",
        "reason_summary",
    )
    update_keys = (
        "operation",
        "target_referent_ids",
        "confidence",
        "reason_summary",
    )
    referent_updates: list[dict[str, Any]] = []
    for item in raw.get("referent_updates") or []:
        if not isinstance(item, dict):
            continue
        update = {key: copy.deepcopy(item[key]) for key in update_keys if key in item}
        referent = item.get("referent")
        if isinstance(referent, dict):
            update["referent"] = {
                key: copy.deepcopy(referent[key]) for key in referent_keys if key in referent
            }
        referent_updates.append(update)
    projection["referent_updates"] = referent_updates
    resolved_reference_keys = (
        "surface_form",
        "entity_type",
        "resolved_value",
        "source",
        "referent_id",
        "confidence",
        "reason_summary",
    )
    projection["resolved_references"] = [
        {key: copy.deepcopy(item[key]) for key in resolved_reference_keys if key in item}
        for item in raw.get("resolved_references") or []
        if isinstance(item, dict)
    ]
    serialized = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(serialized) > 65_536:
        raise ValueError("Goal Association prompt projection exceeds 65536 UTF-8 bytes")
    return projection


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
                **(
                    {
                        "resource_responsibility": goal[
                            "resource_responsibility"
                        ]
                    }
                    if isinstance(goal.get("resource_responsibility"), dict)
                    and goal["resource_responsibility"]
                    else {}
                ),
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
                    **(
                        {
                            "resource_responsibility": item[
                                "resource_responsibility"
                            ]
                        }
                        if isinstance(item.get("resource_responsibility"), dict)
                        and item["resource_responsibility"]
                        else {}
                    ),
                    "metadata": item.get("metadata") or {},
                }
            )
    return result


def _goal_execution_metadata(goal: dict[str, Any]) -> tuple[str, str, bool]:
    metadata = goal.get("metadata")
    if not isinstance(metadata, dict):
        return "", "", False
    return (
        str(metadata.get("responsibility_kind") or "").strip(),
        str(metadata.get("output_mode") or "").strip(),
        bool(metadata.get("provider_required")),
    )


def planner_response_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return direct Vocal Goals completed by ordinary authored speech.

    Mode-specific vocal performance is deliberately excluded.  It remains in
    the Vocal lane but requires exact provider evidence and cannot be closed
    by a generic ``respond`` outcome.
    """

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        if (
            goal_id
            and responsibility_kind == "vocal_output"
            and output_mode in {"", "speech"}
            and not provider_required
        ):
            result.add(goal_id)
    return result


def planner_effectful_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Goals that require provider evidence or an explicit terminal block.

    Goal Association already owns these typed responsibility declarations.  The
    validator does not infer an effect from user wording or select a Capability;
    it only prevents a planner from declaring such a Goal satisfied through an
    ordinary response while emitting no executable work.
    """

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        if not goal_id or not isinstance(metadata, dict):
            continue
        responsibility_kind = str(
            metadata.get("responsibility_kind") or ""
        ).strip()
        if (
            responsibility_kind in {"executable_action", "capability_dependent"}
            or bool(metadata.get("provider_required"))
        ):
            result.add(goal_id)
    return result


def planner_goal_execution_requirements(
    authoritative_goals: list[dict[str, Any]],
) -> tuple[bool, bool]:
    """Derive Planner execution shape only from canonical Goal semantics.

    Goal Interpretation is provider-neutral WHAT evidence and must
    never grant or suppress executable capability access. Goal Association owns the
    typed completion contract; planners may tighten their decoder surface from that
    canonical truth only.

    Returns ``(response_only, requires_execution)``. ``requires_execution`` is the
    decoder-tightening flag for canonical ``capability_dependent`` work (the semantic
    successor to the old tool route). Other provider-backed Activity/Vocal Goals retain
    the normal mixed-response schema and are still enforced by Goal outcome validation.
    """

    goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
    }
    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    capability_work_goal_ids = {
        goal_id
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and (goal_id := " ".join(str(goal.get("goal_id") or "").strip().split()))
        and isinstance(goal.get("metadata"), dict)
        and str(goal["metadata"].get("responsibility_kind") or "").strip()
        == "capability_dependent"
    }
    response_only = bool(goal_ids) and goal_ids.issubset(response_goal_ids)
    requires_execution = bool(capability_work_goal_ids)
    return response_only, requires_execution


def planner_provider_vocal_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return Vocal Goals that require mode-specific provider evidence."""

    result: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        if (
            goal_id
            and responsibility_kind == "vocal_output"
            and output_mode not in {"", "speech"}
            and provider_required
        ):
            result.add(goal_id)
    return result


def planner_provider_media_goal_operations(
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, str]:
    """Return exact media lifecycle operations owned by Activity Goals."""

    result: dict[str, str] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility_kind, output_mode, provider_required = _goal_execution_metadata(goal)
        metadata = goal.get("metadata")
        operation = (
            str(metadata.get("media_operation") or "").strip() if isinstance(metadata, dict) else ""
        )
        if (
            goal_id
            and responsibility_kind == "executable_action"
            and output_mode == "media_playback"
            and provider_required
        ):
            if operation not in MEDIA_CAPABILITY_IDS:
                raise ValueError(f"media_playback Goal requires exact media_operation: {goal_id}")
            result[goal_id] = operation
    return result


def result_evidence_reentry_goal_ids(
    context: dict[str, Any] | None,
) -> set[str]:
    """Return Goals bound to Host-admitted terminal tool Evidence.

    This boundary validates the immutable evidence DTO and its correlation refs;
    it never interprets result content or decides response wording.  It gives the
    same Planner that requested the work permission to answer the exact Goals
    after Trusted Capability Runtime has returned their evidence.
    """

    if not isinstance(context, dict):
        return set()
    reentry = context.get("result_evidence_reentry")
    raw_evidence = context.get("trusted_terminal_evidence")
    if not isinstance(reentry, dict) or not isinstance(raw_evidence, list):
        return set()
    try:
        evidence = [ToolResultEvidence.model_validate(item) for item in raw_evidence]
    except (ValidationError, ValueError, TypeError):
        return set()
    if not evidence:
        return set()
    evidence_ids = {item.evidence_id for item in evidence}
    referenced_ids = {
        normalized
        for value in reentry.get("evidence_refs") or []
        if (normalized := " ".join(str(value or "").strip().split()))
    }
    if referenced_ids and not referenced_ids.issubset(evidence_ids):
        return set()
    return {
        normalized
        for value in reentry.get("source_goal_ids") or []
        if (normalized := " ".join(str(value or "").strip().split()))
    }


def validate_goal_responsibility_outcomes(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    """Keep planner outcomes aligned with typed Goal completion contracts."""

    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    provider_vocal_goal_ids = planner_provider_vocal_goal_ids(authoritative_goals)
    provider_media_goal_operations = planner_provider_media_goal_operations(authoritative_goals)
    speaking_goal_ids = response_goal_ids | provider_vocal_goal_ids
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
    evidence_goal_ids.update(result_evidence_reentry_goal_ids(context))
    valid_vocal_step_ids: set[str] = set()
    valid_media_step_ids: set[str] = set()
    for goal_id in sorted(response_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(f"vocal_output goal requires an explicit outcome: {goal_id}")
        if outcome.disposition != "respond":
            raise ValueError(
                "vocal_output goal must use disposition=respond and no "
                f"executable step: {goal_id}"
            )
    for goal_id in sorted(provider_vocal_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(
                f"provider-required vocal goal requires an explicit outcome: {goal_id}"
            )
        if outcome.disposition == "respond":
            raise ValueError(
                "provider-required vocal goal cannot be completed by response_text, "
                "ordinary TTS, media playback, or a body step: "
                f"{goal_id}"
            )
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if outcome.disposition == "execute":
            expected_mode = next(
                (
                    _goal_execution_metadata(goal)[1]
                    for goal in authoritative_goals
                    if str(goal.get("goal_id") or "").strip() == goal_id
                ),
                "",
            )
            if len(owned_steps) != 1:
                raise ValueError(
                    "provider-required vocal execute outcome requires exactly one "
                    f"owned {VOCAL_PERFORMANCE_CAPABILITY_ID} step: {goal_id}"
                )
            step = owned_steps[0]
            if step.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID:
                raise ValueError(
                    "provider-required vocal goal requires exact capability_id "
                    f"{VOCAL_PERFORMANCE_CAPABILITY_ID}: {goal_id}"
                )
            if str(step.args.get("mode") or "").strip() != expected_mode:
                raise ValueError(
                    "vocal capability mode must exactly match authoritative Goal "
                    f"output_mode={expected_mode!r}: {goal_id}"
                )
            if not str(step.args.get("text") or "").strip():
                raise ValueError(
                    f"vocal capability request requires authored text/content: {goal_id}"
                )
            valid_vocal_step_ids.add(step.step_id)
        elif owned_steps:
            raise ValueError(
                f"non-executing provider-required vocal outcome cannot own plan steps: {goal_id}"
            )
    for goal_id, operation in sorted(provider_media_goal_operations.items()):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(
                f"provider-required media Goal requires an explicit outcome: {goal_id}"
            )
        if outcome.disposition == "respond":
            raise ValueError(
                "media playback Goal cannot be completed by response text, ordinary "
                f"TTS, or vocal performance: {goal_id}"
            )
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if outcome.disposition == "execute":
            expected_capability = MEDIA_CAPABILITY_IDS[operation]
            if len(owned_steps) != 1:
                raise ValueError(
                    "provider-required media execute outcome requires exactly one "
                    f"owned {expected_capability} step: {goal_id}"
                )
            step = owned_steps[0]
            if step.capability_id != expected_capability:
                raise ValueError(
                    "provider-required media Goal requires exact capability_id "
                    f"{expected_capability}: {goal_id}"
                )
            valid_media_step_ids.add(step.step_id)
        elif owned_steps:
            raise ValueError(
                f"non-executing provider-required media outcome cannot own plan steps: {goal_id}"
            )
    invalid_steps = [
        step.step_id
        for step in output.steps
        if speaking_goal_ids.intersection(step.source_goal_ids)
        and step.step_id not in valid_vocal_step_ids
    ]
    if invalid_steps:
        raise ValueError(
            "Vocal goals can own only an exact qualified vocal Capability step: "
            + ",".join(invalid_steps)
        )
    invalid_media_steps = [
        step.step_id
        for step in output.steps
        if set(provider_media_goal_operations).intersection(step.source_goal_ids)
        and step.step_id not in valid_media_step_ids
    ]
    if invalid_media_steps:
        raise ValueError(
            "Media playback Goals can own only their exact chromie.media.* "
            "Capability step: " + ",".join(invalid_media_steps)
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
                "without capability or delivered evidence-bound dialogue: " + goal_id
            )
    # Keep this broad invariant last so narrower responsibility contracts retain
    # their more actionable diagnostics.  It contains every remaining typed
    # effectful Goal without inferring effect from user wording.
    terminal_block_dispositions = {
        "clarify",
        "escalate",
        "unavailable",
        "refused",
    }
    for goal_id in sorted(planner_effectful_goal_ids(authoritative_goals)):
        outcome = output.goal_outcomes.get(goal_id)
        disposition = outcome.disposition if outcome is not None else output.disposition
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if disposition == "execute" and owned_steps:
            continue
        if disposition in terminal_block_dispositions:
            continue
        if disposition == "respond" and goal_id in evidence_goal_ids:
            continue
        raise ValueError(
            "unresolved effectful goal requires an executable step or explicit "
            "clarify/escalate/unavailable/refused evidence: " + goal_id
        )


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


def validate_resource_responsibility_capability_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    capabilities: list[dict[str, Any]],
) -> None:
    """Validate resource Goals against the current plan-level capability boundary.

    Goal Association owns the provider-neutral responsibility. The Planner owns
    selection and composition across the *advertised* catalog. Providers own any
    decomposition hidden inside one selected capability. This validator makes no
    semantic choices; it mechanically verifies that selected capability contracts
    form an ordered resource-state chain and that their combined promises cover
    the already-authored Goal.

    ``resource_contract.plan_requires`` and ``plan_provides`` are public
    composition facts. ``completion_requires`` remains provider-result evidence
    for the exact capability. Legacy one-step full providers that predate
    ``plan_provides`` remain accepted when their existing scope/contract already
    declares the complete delivery responsibility.
    """

    capability_by_id = {
        " ".join(str(item.get("capability_id") or "").strip().split()): item
        for item in capabilities
        if isinstance(item, dict)
        and " ".join(str(item.get("capability_id") or "").strip().split())
    }

    def normalized_values(value: Any) -> set[str]:
        values = value if isinstance(value, list) else []
        return {
            " ".join(str(item or "").strip().split())
            for item in values
            if " ".join(str(item or "").strip().split())
        }

    def capability_contract(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        hints = candidate.get("hints")
        metadata = candidate.get("metadata")
        hints = hints if isinstance(hints, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        scope = hints.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = metadata.get("semantic_scope")
        contract = hints.get("resource_contract")
        if not isinstance(contract, dict) or not contract:
            contract = metadata.get("resource_contract")
        return (scope if isinstance(scope, dict) else {}, contract if isinstance(contract, dict) else {})

    def contract_projection(
        candidate: dict[str, Any],
        *,
        expected_type: str,
        expected_kind: str,
        expected_delivery: str,
        allow_legacy_full: bool,
    ) -> tuple[list[str], set[str], set[str], set[str], str]:
        scope, contract = capability_contract(candidate)
        errors: list[str] = []
        if not contract:
            errors.append("missing resource_contract")
        if scope.get("responsibility_type") != expected_type:
            errors.append(
                "semantic_scope.responsibility_type does not match "
                f"{expected_type!r}"
            )
        kinds = normalized_values(scope.get("resource_kinds"))
        if expected_kind not in kinds:
            errors.append(
                "semantic_scope.resource_kinds does not include "
                f"{expected_kind!r}"
            )
        raw_delivery_modes = scope.get("delivery_modes")
        delivery_modes = {
            " ".join(str(value or "").strip().split())
            for value in (
                raw_delivery_modes
                if isinstance(raw_delivery_modes, list)
                else [scope.get("delivery")]
            )
            if " ".join(str(value or "").strip().split())
        }
        requires = normalized_values(contract.get("plan_requires"))
        provides = normalized_values(contract.get("plan_provides"))
        completion_requires = normalized_values(contract.get("completion_requires"))
        if not provides and completion_requires:
            # Existing complete providers already express the states their own
            # successful result must prove. Those states are also valid public
            # plan coverage when no explicit plan_provides exists.
            provides = set(completion_requires)
        final_delivery_owner = " ".join(
            str(contract.get("final_delivery_owner") or "").strip().split()
        )
        if (
            not provides
            and allow_legacy_full
            and contract
            and expected_delivery in delivery_modes
        ):
            # Backward compatibility for one-step providers from before the
            # composition contract existed. Do not apply this inference to a
            # multi-step plan because it would make every partial step look full.
            provides = {"resource_acquired"}
            if expected_kind == "physical_object":
                provides.add("resource_delivered")
        if "resource_delivered" in provides and expected_delivery not in delivery_modes:
            errors.append(
                "capability providing resource_delivered must declare "
                f"delivery mode {expected_delivery!r}"
            )
        if (
            final_delivery_owner == "chromie_response_layer"
            and expected_delivery not in delivery_modes
        ):
            errors.append(
                "response-layer delivery capability must declare "
                f"delivery mode {expected_delivery!r}"
            )
        if not provides and final_delivery_owner != "chromie_response_layer":
            errors.append("resource_contract.plan_provides is empty")
        return errors, requires, provides, delivery_modes, final_delivery_owner

    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility = goal.get("resource_responsibility")
        if not goal_id or not isinstance(responsibility, dict) or not responsibility:
            continue

        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if not owned_steps:
            continue

        resource = responsibility.get("resource")
        resource = resource if isinstance(resource, dict) else {}
        responsibility_args = {
            name: responsibility.get(name)
            for name in ("resource", "source", "recipient")
            if isinstance(responsibility.get(name), dict)
        }
        expected_type = " ".join(
            str(responsibility.get("responsibility_type") or "").strip().split()
        )
        expected_kind = " ".join(str(resource.get("kind") or "").strip().split())
        expected_delivery = " ".join(
            str(responsibility.get("delivery_mode") or "").strip().split()
        )
        required_terminal_states = {"resource_acquired"}
        if expected_kind == "physical_object":
            required_terminal_states.add("resource_delivered")

        def catalog_coverage(
            initial_state: set[str],
        ) -> tuple[set[str], bool, list[str], list[str]]:
            """Return reachable resource state from currently advertised contracts."""

            reachable = set(initial_state)
            response_delivery = False
            projections: list[tuple[str, set[str], set[str], str]] = []
            complete_capability_ids: list[str] = []
            for capability_id, candidate in capability_by_id.items():
                errors, requires, provides, _modes, final_delivery_owner = (
                    contract_projection(
                        candidate,
                        expected_type=expected_type,
                        expected_kind=expected_kind,
                        expected_delivery=expected_delivery,
                        allow_legacy_full=True,
                    )
                )
                if errors:
                    continue
                projections.append(
                    (capability_id, requires, provides, final_delivery_owner)
                )
                individually_complete = (
                    not requires
                    and required_terminal_states <= provides
                    and (
                        expected_kind == "physical_object"
                        or "resource_delivered" in provides
                        or final_delivery_owner == "chromie_response_layer"
                    )
                )
                if individually_complete:
                    complete_capability_ids.append(capability_id)

            used: list[str] = []
            remaining = list(projections)
            while remaining:
                progressed = False
                next_remaining: list[tuple[str, set[str], set[str], str]] = []
                for capability_id, requires, provides, final_delivery_owner in remaining:
                    if not requires <= reachable:
                        next_remaining.append(
                            (capability_id, requires, provides, final_delivery_owner)
                        )
                        continue
                    reachable.update(provides)
                    response_delivery = response_delivery or (
                        final_delivery_owner == "chromie_response_layer"
                    )
                    used.append(capability_id)
                    progressed = True
                if not progressed:
                    break
                remaining = next_remaining
            return (
                reachable,
                response_delivery,
                sorted(set(used)),
                sorted(set(complete_capability_ids)),
            )

        def coverage_complete(state: set[str], response_delivery: bool) -> bool:
            if not required_terminal_states <= state:
                return False
            if expected_kind == "physical_object":
                return True
            return "resource_delivered" in state or response_delivery

        resource_state: set[str] = set()
        response_layer_delivery = False
        selected_ids: list[str] = []

        for step in owned_steps:
            capability = capability_by_id.get(step.capability_id)
            if capability is None:
                raise ValueError(
                    "resource responsibility step uses a Capability absent from the "
                    f"authoritative catalog: goal_id={goal_id}, "
                    f"capability_id={step.capability_id}"
                )
            errors, requires, provides, _delivery_modes, final_delivery_owner = (
                contract_projection(
                    capability,
                    expected_type=expected_type,
                    expected_kind=expected_kind,
                    expected_delivery=expected_delivery,
                    allow_legacy_full=len(owned_steps) == 1,
                )
            )
            if errors:
                reachable, response_delivery, composition_ids, complete_ids = (
                    catalog_coverage(set())
                )
                message = (
                    "resource responsibility Capability contract mismatch: "
                    f"goal_id={goal_id}, capability_id={step.capability_id}: "
                    + "; ".join(errors)
                )
                if complete_ids:
                    raise ResourceResponsibilityCapabilityGroundingError(
                        message
                        + "; complete_capability_ids="
                        + ",".join(complete_ids),
                        goal_id=goal_id,
                        complete_capability_ids=complete_ids,
                    )
                if coverage_complete(reachable, response_delivery):
                    raise ResourceResponsibilityRequiresCompositionError(
                        message
                        + "; composable_capability_ids="
                        + ",".join(composition_ids)
                    )
                raise ResourceResponsibilityCapabilityUnavailableError(
                    message
                    + "; no supplied Capability set declares the required contract"
                )
            for argument_name, expected_value in responsibility_args.items():
                if argument_name not in step.args:
                    continue
                if not _material_values_equal(
                    step.args[argument_name],
                    expected_value,
                    list_compatible=False,
                ):
                    raise ResourceResponsibilityCapabilityGroundingError(
                        "resource responsibility step argument contradicts the "
                        "canonical Goal responsibility: "
                        f"goal_id={goal_id}, capability_id={step.capability_id}, "
                        f"argument={argument_name!r}",
                        goal_id=goal_id,
                        complete_capability_ids=(
                            [step.capability_id]
                            if len(owned_steps) == 1
                            and not requires
                            and required_terminal_states <= provides
                            and (
                                expected_kind == "physical_object"
                                or "resource_delivered" in provides
                                or final_delivery_owner
                                == "chromie_response_layer"
                            )
                            else []
                        ),
                    )
            missing_preconditions = sorted(requires - resource_state)
            if missing_preconditions:
                raise ResourceResponsibilityCapabilityGroundingError(
                    "resource responsibility capability chain has unsatisfied "
                    f"plan_requires for goal_id={goal_id}, "
                    f"capability_id={step.capability_id}: "
                    + ",".join(missing_preconditions)
                )
            if requires and step.timing == "parallel":
                raise ResourceResponsibilityCapabilityGroundingError(
                    "resource responsibility capability with plan_requires must be "
                    f"sequential: goal_id={goal_id}, capability_id={step.capability_id}"
                )
            resource_state.update(provides)
            response_layer_delivery = response_layer_delivery or (
                final_delivery_owner == "chromie_response_layer"
            )
            selected_ids.append(step.capability_id)

        missing_terminal_states = sorted(required_terminal_states - resource_state)
        delivery_missing = (
            expected_kind != "physical_object"
            and "resource_delivered" not in resource_state
            and not response_layer_delivery
        )
        if not missing_terminal_states and not delivery_missing:
            continue

        reachable, response_delivery, composition_ids, complete_ids = catalog_coverage(
            resource_state
        )

        details = [*missing_terminal_states]
        if delivery_missing:
            details.append("user_delivery")
        message = (
            "resource responsibility plan does not cover the complete Goal: "
            f"goal_id={goal_id}, selected_capability_ids={','.join(selected_ids)}, "
            f"missing={','.join(details)}"
        )
        if complete_ids:
            raise ResourceResponsibilityCapabilityGroundingError(
                message
                + "; complete_capability_ids="
                + ",".join(complete_ids),
                goal_id=goal_id,
                complete_capability_ids=complete_ids,
            )
        if coverage_complete(reachable, response_delivery):
            additional_ids = [
                capability_id
                for capability_id in composition_ids
                if capability_id not in selected_ids
            ]
            raise ResourceResponsibilityRequiresCompositionError(
                message
                + "; additional_capability_ids="
                + ",".join(additional_ids)
            )
        raise ResourceResponsibilityCapabilityUnavailableError(
            message + "; no supplied Capability set declares the missing resource coverage"
        )


def canonical_resource_argument_response_schema(
    base_schema: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Make one canonical resource Goal's provider projection read-only.

    Capability selection and step ownership remain model-authored. When the turn
    has exactly one canonical resource Goal, any selected Capability branch that
    accepts complete resource/source/recipient objects receives those objects as
    decoder constants instead of a second writable semantic copy.
    """

    resource_goals = [
        goal
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and isinstance(goal.get("resource_responsibility"), dict)
    ]
    if len(resource_goals) != 1 or len(authoritative_goals) != 1:
        return base_schema
    responsibility = resource_goals[0]["resource_responsibility"]
    exact_arguments = {
        name: copy.deepcopy(responsibility[name])
        for name in ("resource", "source", "recipient")
        if isinstance(responsibility.get(name), dict)
    }
    if not exact_arguments:
        return base_schema

    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    branches = step_schema.get("oneOf") if isinstance(step_schema, dict) else None
    if not isinstance(branches, list):
        return base_schema

    constrained = False
    for branch in branches:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        args = properties.get("args") if isinstance(properties, dict) else None
        argument_properties = args.get("properties") if isinstance(args, dict) else None
        if not isinstance(argument_properties, dict):
            continue
        required = args.setdefault("required", [])
        for name, value in exact_arguments.items():
            if name not in argument_properties:
                continue
            argument_properties[name] = {"const": value}
            if isinstance(required, list) and name not in required:
                required.append(name)
            constrained = True
    if not constrained:
        return base_schema

    parameter_resolutions = schema.get("properties", {}).get(
        "parameter_resolutions"
    )
    if isinstance(parameter_resolutions, dict):
        parameter_resolutions["maxItems"] = 0
        parameter_resolutions["description"] = (
            "Canonical resource/source/recipient arguments are deterministic "
            "read-only projections and require no Planner-authored resolutions."
        )
    return schema


def resource_grounding_repair_response_schema(
    base_schema: dict[str, Any],
    *,
    error: ResourceResponsibilityCapabilityGroundingError | None,
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Constrain repair to validator-proven complete resource work.

    The semantic choice comes from the model-authored resource Goal and catalog
    contracts already evaluated by the grounding validator. This projection only
    prevents a bounded repair from selecting the same incomplete Capability again
    or rewriting canonical nested resource arguments.
    """

    if error is None or not error.complete_capability_ids:
        return base_schema
    goals = [goal for goal in authoritative_goals if isinstance(goal, dict)]
    goal = next(
        (
            item
            for item in goals
            if " ".join(str(item.get("goal_id") or "").strip().split())
            == error.goal_id
        ),
        None,
    )
    if goal is None:
        return base_schema
    goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
    responsibility = goal.get("resource_responsibility")
    if (
        not goal_id
        or goal_id != error.goal_id
        or not isinstance(responsibility, dict)
    ):
        return base_schema
    exact_arguments = {
        name: copy.deepcopy(responsibility[name])
        for name in ("resource", "source", "recipient")
        if isinstance(responsibility.get(name), dict)
    }
    if not exact_arguments:
        return base_schema

    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if not isinstance(step_schema, dict):
        return base_schema
    branches = step_schema.get("oneOf")
    if not isinstance(branches, list):
        return base_schema
    complete_ids = set(error.complete_capability_ids)
    retained: list[dict[str, Any]] = []
    complete_branches: list[dict[str, Any]] = []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        properties = branch.get("properties")
        if not isinstance(properties, dict):
            continue
        capability = properties.get("capability_id")
        identifiers = capability.get("enum") if isinstance(capability, dict) else None
        is_complete_capability = (
            isinstance(identifiers, list)
            and len(identifiers) == 1
            and identifiers[0] in complete_ids
        )
        if (
            not isinstance(identifiers, list)
            or len(identifiers) != 1
        ):
            continue
        if len(goals) == 1 and not is_complete_capability:
            continue
        args = properties.get("args")
        argument_properties = (
            args.get("properties") if isinstance(args, dict) else None
        )
        if not isinstance(argument_properties, dict):
            continue
        if is_complete_capability:
            required = args.setdefault("required", [])
            for name, value in exact_arguments.items():
                if name not in argument_properties:
                    continue
                argument_properties[name] = {"const": value}
                if isinstance(required, list) and name not in required:
                    required.append(name)
            complete_branches.append(branch)
        retained.append(branch)
    if not retained or not complete_branches:
        return base_schema
    step_schema["oneOf"] = retained
    capability_property = step_schema.get("properties", {}).get("capability_id")
    if isinstance(capability_property, dict):
        capability_property["enum"] = sorted(
            {
                branch["properties"]["capability_id"]["enum"][0]
                for branch in retained
            }
        )
    steps = schema.get("properties", {}).get("steps")
    if isinstance(steps, dict):
        steps["minItems"] = 1
        if len(goals) == 1:
            steps["maxItems"] = 1
        else:
            steps["contains"] = {
                "type": "object",
                "properties": {
                    "capability_id": {
                        "type": "string",
                        "enum": sorted(complete_ids),
                    },
                    "source_goal_ids": {
                        "type": "array",
                        "contains": {"const": error.goal_id},
                        "minContains": 1,
                    },
                },
                "required": ["capability_id", "source_goal_ids"],
            }
            steps["minContains"] = 1
    parameter_resolutions = schema.get("properties", {}).get(
        "parameter_resolutions"
    )
    if isinstance(parameter_resolutions, dict) and len(goals) == 1:
        parameter_resolutions["maxItems"] = 0
    return schema


def coordinated_action_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return model-authored provider Goals requiring semantic coverage audit.

    Goal Association, rather than the Host, declares ``responsibility_kind`` and
    authors any ``action_list`` binding or sibling Goal split. The Host uses only
    those typed facts to require an independent model completeness audit; it does
    not infer actions, parse user wording, or select Capabilities. Auditing every
    executable-action and capability-dependent Goal prevents a generic movement
    step from being accepted as object handling and prevents a domain-specific
    read Capability from being broadened into unrelated external retrieval.
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
        metadata = goal.get("metadata")
        if isinstance(metadata, dict) and str(
            metadata.get("responsibility_kind") or ""
        ).strip() in {"executable_action", "capability_dependent"}:
            goal_ids.add(goal_id)
        resource_responsibility = goal.get("resource_responsibility")
        if isinstance(resource_responsibility, dict) and resource_responsibility:
            goal_ids.add(goal_id)
        goal_object = goal.get("object")
        if not isinstance(goal_object, dict):
            continue
        bindings = goal_object.get("bindings")
        if not isinstance(bindings, dict):
            continue
        if any(
            isinstance(binding, dict)
            and "_".join(
                str(binding.get("entity_type") or "").strip().casefold().replace("-", "_").split()
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
                    "parallel_step_count": len(parallel_steps),
                    "parallel_metadata_declared": capability.get("parallel_metadata_declared"),
                    "can_run_parallel": capability.get("can_run_parallel"),
                }
            )
            continue
        usable.append((step, capability))

    for index, (left_step, left) in enumerate(usable):
        left_group = str(left.get("exclusive_group") or "").strip()
        left_resources = {
            str(item).strip() for item in left.get("resource_claims") or [] if str(item).strip()
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


def retained_evidence_response_review_required(
    context: dict[str, Any] | None,
    plan: CanonicalPlan,
) -> bool:
    """Identify typed retained-Goal responses that need semantic turn review.

    Goal Association, not Host wording rules, decides whether the latest turn
    continues or otherwise refers to an existing Goal. The review is required
    only when trusted delivered evidence is also available and the terminal
    Plan proposes a conversational response with no executable effects.
    """

    if plan.disposition != "respond" or plan.steps:
        return False
    responding_goal_ids = {
        item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"
    } or set(plan.goal_ids)
    if not responding_goal_ids or not evidence_bound_dialogue(context):
        return False
    association = goal_association_prompt_projection(context)
    return any(
        isinstance(item, dict)
        and str(item.get("relationship") or "").strip() != "new"
        and responding_goal_ids.intersection(
            str(goal_id).strip()
            for goal_id in item.get("target_goal_ids") or []
            if str(goal_id).strip()
        )
        for item in association.get("associations") or []
    )


async def review_retained_evidence_response(
    client: Any,
    *,
    request_text: str,
    language: str,
    association: dict[str, Any],
    authoritative_goals: list[dict[str, Any]],
    delivered_evidence: list[dict[str, Any]],
    plan: CanonicalPlan,
    num_ctx: int,
    turn_id: str,
) -> PlannerCommunicationReview:
    """Ask the planner model to accept or revise follow-up communication.

    This review can change only model-authored response text. It cannot create
    Goals, choose Capabilities, add steps, authorize execution, or reinterpret
    provider evidence. An accepted response must be returned byte-for-byte so
    the Host cannot silently treat an unrequested rewrite as acceptance.
    """

    response_goal_ids = [
        item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"
    ] or list(plan.goal_ids)
    proposed_goal_responses = {
        item.goal_id: item.response_text
        for item in plan.goal_outcomes
        if item.disposition == "respond"
    }
    if not proposed_goal_responses and len(response_goal_ids) == 1:
        proposed_goal_responses[response_goal_ids[0]] = plan.response_text
    prompt = json.dumps(
        {
            "responsibility": (
                "Review whether the proposed response answers the latest user turn's "
                "communicative act directly while using retained delivered evidence only "
                "as support. Judge meaning across languages rather than matching phrases. "
                "First determine whether the latest turn is a reaction, feeling, "
                "acknowledgement, evaluation, practical decision, recommendation request, "
                "or yes/no question about the retained result. A practical decision, "
                "recommendation, or yes/no follow-up must state that answer in its first "
                "sentence and may then include at most one short supporting clause. It "
                "must not begin by replaying prior evidence, and must omit previously "
                "delivered measurements or conditions that do not change the decision. "
                "Other follow-ups must likewise answer the latest act instead of replacing "
                "it with the old task answer. Preserve the requested language and every "
                "retained fact that is actually used; never invent, infer, strengthen, or "
                "contradict an external fact. Choose accept only when the proposed text "
                "already satisfies this contract. Otherwise choose revise and author the "
                "smallest natural correction."
            ),
            "latest_user_turn": request_text,
            "language": language,
            "goal_association": association,
            "authoritative_goals": authoritative_goals,
            "delivered_evidence_bound_dialogue": delivered_evidence,
            "proposed_response_text": plan.response_text,
            "proposed_goal_responses": proposed_goal_responses,
            "output_contract": {
                "decision": "accept or revise",
                "accept": (
                    "Return proposed_response_text and every proposed_goal_response "
                    "exactly unchanged."
                ),
                "revise": (
                    "Return one corrected aggregate response_text and exactly one "
                    "corrected response for every supplied response Goal ID."
                ),
                "response_goal_ids": response_goal_ids,
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
            "You are the current Planner's bounded conversational-contract reviewer. "
            "Review the latest communicative act against the model-authored Goal "
            "Association and trusted delivered evidence. Do not use phrase rules, add "
            "facts, create actions, or authorize execution. Return only the required "
            "JSON object."
        ),
        options={
            "temperature": 0,
            "top_p": 0.8,
            "num_ctx": max(4096, int(num_ctx)),
            "num_predict": 512,
        },
        response_format=planner_communication_review_response_schema(response_goal_ids),
        prompt_family="fast_planner.communication_review",
        turn_id=turn_id,
        attempt=1,
    )
    if not isinstance(raw, dict):
        raise ValueError("planner communication review response is not a JSON object")
    review = PlannerCommunicationReview.model_validate(raw)
    reviewed_by_goal = {item.goal_id: item.response_text for item in review.goal_responses}
    if set(reviewed_by_goal) != set(response_goal_ids):
        raise ValueError(
            "communication review responses must cover exactly the response Goal IDs"
        )
    if review.decision == "accept" and (
        review.response_text != plan.response_text
        or reviewed_by_goal != proposed_goal_responses
    ):
        raise ValueError("accepted communication review must preserve proposed text exactly")
    return review


def planner_communication_review_response_schema(
    response_goal_ids: list[str],
) -> dict[str, Any]:
    """Return a decoder-tight schema for bounded response communication review."""

    schema = copy.deepcopy(PlannerCommunicationReview.model_json_schema())
    schema["required"] = [
        "decision",
        "confidence",
        "response_text",
        "goal_responses",
        "reason",
    ]
    goal_responses = schema.get("properties", {}).get("goal_responses")
    if isinstance(goal_responses, dict):
        goal_responses["minItems"] = len(response_goal_ids)
        goal_responses["maxItems"] = len(response_goal_ids)
    goal_response = schema.get("$defs", {}).get("PlannerCommunicationGoalResponse")
    if isinstance(goal_response, dict):
        goal_response["required"] = ["goal_id", "response_text"]
        goal_response_properties = goal_response.get("properties", {})
        goal_id = goal_response_properties.get("goal_id")
        if isinstance(goal_id, dict):
            # llama.cpp's deployed JSON-grammar parser rejects the combination
            # of nested string-length constraints used by this DTO. Pydantic
            # still enforces every length immediately after decoding.
            goal_id.pop("minLength", None)
            goal_id.pop("maxLength", None)
            goal_id["enum"] = list(response_goal_ids)
        goal_response_text = goal_response_properties.get("response_text")
        if isinstance(goal_response_text, dict):
            goal_response_text.pop("minLength", None)
            goal_response_text.pop("maxLength", None)
    for field_name in ("response_text", "reason"):
        field = schema.get("properties", {}).get(field_name)
        if isinstance(field, dict):
            field.pop("minLength", None)
            field.pop("maxLength", None)
    return schema


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
                "material responsibility in the authoritative Goals. Judge semantics "
                "using ordinary world knowledge together with the supplied Capability "
                "contracts; do not match phrases or treat capability names as answers. "
                "A Plan may claim exact coverage only when every material Goal "
                "requirement is entailed by the declared semantics and arguments of "
                "its selected Capabilities, or by trusted evidence explicitly supplied "
                "to this review. Do not broaden a Capability from its name, rationale, "
                "identity/personality context, shared argument names, or superficial "
                "similarity. Do not infer undeclared effects, guarantees, resources, "
                "state transitions, or completion of another responsibility. Preserve "
                "authoritative typed bindings, requested ordering/concurrency, output "
                "modes, and resource responsibilities. Capability parallel-safety is "
                "permission to honor requested concurrency, never evidence that "
                "concurrency was requested. A response_text may communicate a new "
                "prospective acknowledgement, limitation, clarification, or other "
                "conversational delta, but it never substitutes for an effectful or "
                "provider-backed responsibility and never proves execution. A direct "
                "vocal_output Goal is completed by its respond outcome rather than "
                "a response-transport task step. Unavailable or refused outcomes may "
                "represent an unmet Goal only when satisfaction remains non-exact and "
                "the wording does not promise the unavailable work. For a material "
                "adjustment or alternative, require the explicit confirmation-bound "
                "plan relation. Reject any exact Plan that omits or contradicts one of "
                "these semantic responsibilities. Do not propose or authorize "
                "replacement steps."
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
                    "List each omitted or contradicted responsibility in uncovered_requirements."
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


def _normalized_entity_type(value: Any) -> str:
    """Normalize a model-authored binding type without inferring semantics."""

    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())


def _list_literal_items(value: str) -> list[str]:
    """Project one typed list literal into its representation-level items."""

    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return []
    return [
        item
        for part in _LIST_LITERAL_SEPARATOR_RE.split(normalized)
        if (item := " ".join(part.strip().split()))
    ]


def _material_values_equal(
    left: Any,
    right: Any,
    *,
    list_compatible: bool = False,
) -> bool:
    """Compare material values while tolerating only declared shape aliases.

    Goal Association may serialize a binding whose ``entity_type`` is ``list``
    as a delimiter-separated string, while a Capability schema correctly
    requires the executable argument to be a JSON array. That is a wire-shape
    difference, not a semantic contradiction. No arbitrary prose is split:
    list compatibility is enabled only by the typed binding or by an already
    structured list on the other side of a parameter-resolution comparison.
    """

    if isinstance(left, dict) and isinstance(right, dict):
        left_by_key = {str(key): value for key, value in left.items()}
        right_by_key = {str(key): value for key, value in right.items()}
        if left_by_key.keys() != right_by_key.keys():
            return False
        return all(
            _material_values_equal(
                left_by_key[key],
                right_by_key[key],
                list_compatible=(
                    isinstance(left_by_key[key], list) or isinstance(right_by_key[key], list)
                ),
            )
            for key in left_by_key
        )

    if list_compatible:
        if isinstance(left, str):
            left = _list_literal_items(left)
        if isinstance(right, str):
            right = _list_literal_items(right)
    elif (
        isinstance(left, (int, float, Decimal))
        and not isinstance(left, bool)
        and isinstance(right, str)
        and _NUMERIC_LITERAL_RE.fullmatch(right.strip()) is not None
    ) or (
        isinstance(right, (int, float, Decimal))
        and not isinstance(right, bool)
        and isinstance(left, str)
        and _NUMERIC_LITERAL_RE.fullmatch(left.strip()) is not None
    ):
        try:
            return Decimal(str(left).strip()) == Decimal(str(right).strip())
        except InvalidOperation:
            return False
    return _normalized_material_value(left) == _normalized_material_value(right)


def _goal_binding_map(goal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return one transient typed binding view from the canonical Goal authority.

    Non-resource Goals own ``object.bindings``. Resource Goals own only
    ``resource_responsibility``; their flat view is computed on demand and is never
    persisted back into the Goal.
    """

    raw_resource = goal.get("resource_responsibility")
    if isinstance(raw_resource, dict):
        responsibility = AcquireAndDeliverResource.model_validate(raw_resource)
        raw_bindings = resource_semantic_bindings(responsibility)
    else:
        goal_object = goal.get("object")
        if not isinstance(goal_object, dict):
            return {}
        raw_bindings = goal_object.get("bindings")
        if not isinstance(raw_bindings, dict):
            return {}
    bindings: dict[str, dict[str, Any]] = {}
    for raw_name, raw_binding in raw_bindings.items():
        name = " ".join(str(raw_name or "").strip().split())
        if not name or not isinstance(raw_binding, dict) or "value" not in raw_binding:
            continue
        bindings[name] = {
            "entity_type": _normalized_entity_type(raw_binding.get("entity_type")),
            "value": raw_binding.get("value"),
        }
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

    bindings_by_goal: dict[str, dict[str, dict[str, Any]]] = {}
    information_goal_ids: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if goal_id:
            bindings_by_goal[goal_id] = _goal_binding_map(goal)
            responsibility = goal.get("resource_responsibility")
            resource = (
                responsibility.get("resource")
                if isinstance(responsibility, dict)
                else None
            )
            if isinstance(resource, dict) and resource.get("kind") == "information":
                information_goal_ids.add(goal_id)

    def nested_values(value: Any) -> list[Any]:
        if isinstance(value, dict):
            return [item for child in value.values() for item in nested_values(child)]
        if isinstance(value, list):
            return [item for child in value for item in nested_values(child)]
        return [value]

    for step in output.steps:
        claimed_goal_ids = [
            goal_id for goal_id in step.source_goal_ids if goal_id in bindings_by_goal
        ]
        if not claimed_goal_ids:
            continue

        required: dict[str, dict[str, Any]] = {}
        for goal_id in claimed_goal_ids:
            for name, binding in bindings_by_goal[goal_id].items():
                if name in required and not _material_values_equal(
                    required[name]["value"],
                    binding["value"],
                    list_compatible=(
                        required[name]["entity_type"] in _LIST_ENTITY_TYPES
                        or binding["entity_type"] in _LIST_ENTITY_TYPES
                    ),
                ):
                    raise ValueError(
                        "one executable step cannot satisfy conflicting authoritative "
                        f"Goal bindings for {name!r}"
                    )
                required[name] = binding

        for name, binding in required.items():
            if name not in step.args:
                continue
            actual = step.args[name]
            expected = binding["value"]
            if not _material_values_equal(
                actual,
                expected,
                list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
            ):
                raise ValueError(
                    "planner step argument contradicts authoritative Goal binding: "
                    f"{step.step_id}.{name}={actual!r}, expected={expected!r}"
                )

        argument_values = nested_values(step.args)
        for goal_id in claimed_goal_ids:
            if goal_id not in information_goal_ids:
                continue
            for name, binding in bindings_by_goal[goal_id].items():
                if binding["entity_type"] not in _INFORMATION_TEMPORAL_ENTITY_TYPES:
                    continue
                expected = binding["value"]
                if any(
                    _material_values_equal(actual, expected, list_compatible=False)
                    for actual in argument_values
                ):
                    continue
                raise PlannerDTOContractError(
                    "information capability step omits authoritative temporal scope: "
                    f"goal_id={goal_id!r}, binding={name!r}, value={expected!r}"
                )

        if step.capability_id == "chromie.memory.retrieve_verified_tool_result":
            material_args = step.args.get("material_args")
            if not isinstance(material_args, dict):
                raise ValueError(
                    "verified-memory retrieval requires material_args containing "
                    "the authoritative Goal bindings"
                )
            for name, binding in required.items():
                if name not in material_args:
                    raise ValueError(
                        f"verified-memory retrieval omitted authoritative Goal binding: {name!r}"
                    )
                actual = material_args[name]
                expected = binding["value"]
                if not _material_values_equal(
                    actual,
                    expected,
                    list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                ):
                    raise ValueError(
                        "verified-memory retrieval contradicts authoritative Goal "
                        f"binding: material_args.{name}={actual!r}, "
                        f"expected={expected!r}"
                    )


def validate_user_supplied_parameter_provenance(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
) -> None:
    """Require non-numeric ``user_supplied`` values to exist in typed Goals.

    A Planner may map a Goal binding to a differently named Capability argument,
    but it cannot manufacture a material string/entity value and label it as user
    supplied. Numeric provenance retains its older dedicated validator because it
    also accounts for explicit numeric literals during the binding migration.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    bindings_by_goal: dict[str, dict[str, dict[str, Any]]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if goal_id:
            bindings_by_goal[goal_id] = _goal_binding_map(goal)

    for resolution in output.parameter_resolutions:
        if resolution.strategy != "user_supplied":
            continue
        value = resolution.value
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float, Decimal))
        ) or (
            isinstance(value, str)
            and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is not None
        ):
            # The dedicated numeric provenance validator also supports legacy
            # Goals whose numeric binding migration is still in progress.
            continue

        source_goal_ids = [
            goal_id
            for goal_id in resolution.source_goal_ids
            if goal_id in bindings_by_goal
        ]
        if not source_goal_ids:
            raise ValueError(
                "non-numeric user_supplied parameter resolution requires "
                f"authoritative source_goal_ids: {resolution.step_id}."
                f"{resolution.parameter}"
            )

        cited_bindings: dict[str, list[dict[str, Any]]] = {}
        for goal_id in source_goal_ids:
            for name, binding in bindings_by_goal[goal_id].items():
                cited_bindings.setdefault(name, []).append(binding)

        if isinstance(value, dict) and resolution.parameter == "material_args":
            unmatched = []
            for name, actual in value.items():
                candidates = cited_bindings.get(str(name), [])
                if not candidates or not any(
                    _material_values_equal(
                        actual,
                        binding["value"],
                        list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                    )
                    for binding in candidates
                ):
                    unmatched.append(str(name))
            if not unmatched:
                continue
        else:
            preferred = cited_bindings.get(resolution.parameter, [])
            candidates = preferred or [
                binding
                for bindings in cited_bindings.values()
                for binding in bindings
            ]
            if any(
                _material_values_equal(
                    value,
                    binding["value"],
                    list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                )
                for binding in candidates
            ):
                continue

        raise ValueError(
            "user_supplied parameter resolution is not present in authoritative "
            f"typed Goal bindings: {resolution.step_id}."
            f"{resolution.parameter}={value!r}"
        )



def situation_prompt_projection(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return only a validated bounded Situation projection for model prompts."""

    current = context if isinstance(context, dict) else {}
    raw = current.get("situation")
    if not isinstance(raw, dict):
        return {}
    try:
        return SituationProjection.model_validate(raw).prompt_projection()
    except ValidationError:
        return {}


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
        planned = binding.get("planned_capabilities")
        if not isinstance(planned, list):
            planned = []
        has_external_read = bool(binding.get("retryable_safe_read"))
        for item in planned:
            if not isinstance(item, dict):
                continue
            safety_class = " ".join(str(item.get("safety_class") or "").strip().split()).casefold()
            if safety_class in external_safety_classes or item.get("retryable_safe_read") is True:
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
    unsupported -= result_evidence_reentry_goal_ids(context)
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
                "canonical_plan_id": str(metadata.get("canonical_plan_id") or "")[:200],
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

        return f"step_id={resolution.step_id!r}, parameter={resolution.parameter!r}"

    def numerically_equal(left: Decimal, right: Decimal) -> bool:
        """Ignore only representation-scale floating-point roundoff."""

        scale = max(abs(left), abs(right), Decimal(1))
        return abs(left - right) <= Decimal("1e-12") * scale

    goal_text: dict[str, str] = {}
    resource_arguments_by_goal: dict[str, dict[str, Any]] = {}
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
        bindings = _goal_binding_map(goal)
        parts.extend(
            str(binding.get("value")).strip()
            for binding in bindings.values()
            if binding.get("value") is not None
            and str(binding.get("value")).strip()
        )
        responsibility = goal.get("resource_responsibility")
        if isinstance(responsibility, dict):
            resource_arguments_by_goal[goal_id] = {
                name: responsibility.get(name)
                for name in ("resource", "source", "recipient")
                if isinstance(responsibility.get(name), dict)
            }
        goal_text[goal_id] = " ".join(dict.fromkeys(parts))

    steps = {step.step_id: step for step in output.steps}
    structured_numeric_grounding: dict[str, set[Decimal]] = {}

    def nested_numbers(value: Any) -> set[Decimal]:
        if isinstance(value, dict):
            return {
                number
                for item in value.values()
                for number in nested_numbers(item)
            }
        if isinstance(value, list):
            return {
                number
                for item in value
                for number in nested_numbers(item)
            }
        if isinstance(value, str):
            return set(literals(value))
        number = numeric(value)
        return {number} if number is not None else set()

    for step in output.steps:
        for goal_id in step.source_goal_ids:
            expected_arguments = resource_arguments_by_goal.get(goal_id, {})
            for parameter, expected in expected_arguments.items():
                actual = step.args.get(parameter)
                if actual is None or not _material_values_equal(
                    actual,
                    expected,
                    list_compatible=False,
                ):
                    continue
                structured_numeric_grounding.setdefault(goal_id, set()).update(
                    nested_numbers(actual)
                )
    user_numeric_resolutions: list[tuple[PlanParameterResolution, Decimal]] = []
    unsupported_user_numeric_resolutions: list[
        tuple[PlanParameterResolution, Decimal, list[str]]
    ] = []
    for resolution in output.parameter_resolutions:
        if resolution.blocking:
            continue
        step = steps.get(resolution.step_id)
        if step is None:
            raise PlannerDTOContractError(
                "parameter resolution references unknown executable step "
                f"({resolution_location(resolution)})"
            )
        if resolution.parameter not in step.args:
            raise PlannerDTOContractError(
                "parameter resolution references an argument absent from its step: "
                f"{resolution_location(resolution)}"
            )
        resolved_number = numeric(resolution.value)
        argument_number = numeric(step.args[resolution.parameter])
        if resolved_number is not None and argument_number is not None:
            if not numerically_equal(resolved_number, argument_number):
                raise PlannerDTOContractError(
                    "parameter resolution value must equal the executable step argument: "
                    f"{resolution_location(resolution)} has "
                    f"resolution={resolution.value!r}, step={step.args[resolution.parameter]!r}"
                )
        elif not _material_values_equal(
            resolution.value,
            step.args[resolution.parameter],
            list_compatible=(
                isinstance(resolution.value, list)
                or isinstance(step.args[resolution.parameter], list)
            ),
        ):
            raise PlannerDTOContractError(
                "parameter resolution value must equal the executable step argument: "
                f"{resolution_location(resolution)}"
            )

        if resolution.strategy != "user_supplied" or resolved_number is None:
            continue
        source_goal_ids = list(dict.fromkeys(resolution.source_goal_ids))
        if not source_goal_ids:
            raise PlannerDTOContractError(
                "numeric user_supplied parameter resolution requires source_goal_ids: "
                f"{resolution_location(resolution)}"
            )
        unsupported_goal_ids = [
            goal_id
            for goal_id in source_goal_ids
            if resolved_number not in literals(goal_text.get(goal_id, ""))
        ]
        if unsupported_goal_ids:
            unsupported_user_numeric_resolutions.append(
                (resolution, resolved_number, unsupported_goal_ids)
            )
        user_numeric_resolutions.append((resolution, resolved_number))

    executable_goal_ids = {
        goal_id
        for goal_id, outcome in output.goal_outcomes.items()
        if outcome.disposition == "execute"
    }
    if not executable_goal_ids:
        executable_goal_ids = {goal_id for step in output.steps for goal_id in step.source_goal_ids}
    missing_numeric_grounding: list[tuple[str, Decimal]] = []
    for goal_id in sorted(executable_goal_ids):
        for literal in literals(goal_text.get(goal_id, "")):
            if not any(
                literal == value and goal_id in resolution.source_goal_ids
                for resolution, value in user_numeric_resolutions
            ) and literal not in structured_numeric_grounding.get(goal_id, set()):
                missing_numeric_grounding.append((goal_id, literal))
    if missing_numeric_grounding:
        missing = "; ".join(
            f"goal_id={goal_id!r}, value={literal}"
            for goal_id, literal in missing_numeric_grounding
        )
        raise ValueError(
            "explicit numeric goal value has no matching user_supplied "
            f"parameter resolution: {missing}"
        )
    if unsupported_user_numeric_resolutions:
        unsupported = "; ".join(
            f"{resolution_location(resolution)}, value={value}, "
            f"source_goal_ids={goal_ids!r}"
            for resolution, value, goal_ids in unsupported_user_numeric_resolutions
        )
        raise ValueError(
            "numeric user_supplied parameter resolution is not present in "
            f"its authoritative source Goal: {unsupported}"
        )


def normalize_schema_default_parameter_provenance(
    raw: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
    capability_payload: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Correct a mechanically provable schema-default provenance label.

    The planner still owns capability, argument, and Goal/step selection. This
    adapter changes only ``user_supplied`` provenance when the numeric value is
    absent from every cited Goal and exactly equals the selected capability's
    declared default for the same argument. It never changes an argument value
    or repairs values without authoritative catalog-default evidence.
    """

    def numeric(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(
            value,
            (int, float, Decimal, str),
        ):
            return None
        if (
            isinstance(value, str)
            and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is None
        ):
            return None
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None

    goal_numbers: dict[str, set[Decimal]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        values: set[Decimal] = set()
        for text in [
            goal.get("description"),
            *(goal.get("success_criteria") or []),
        ]:
            for match in _NUMERIC_LITERAL_RE.finditer(str(text or "")):
                parsed = numeric(match.group(0))
                if parsed is not None:
                    values.add(parsed)
        for binding in _goal_binding_map(goal).values():
            parsed = numeric(binding.get("value"))
            if parsed is not None:
                values.add(parsed)
        goal_numbers[goal_id] = values

    schemas = {
        str(item.get("capability_id") or "").strip(): item.get("input_schema") or {}
        for item in capability_payload
        if isinstance(item, dict)
    }
    normalized = copy.deepcopy(raw)
    steps = {
        str(item.get("step_id") or "").strip(): item
        for item in normalized.get("steps") or []
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    repairs: list[dict[str, Any]] = []
    for resolution in normalized.get("parameter_resolutions") or []:
        if not isinstance(resolution, dict):
            continue
        if str(resolution.get("strategy") or "") != "user_supplied":
            continue
        resolved_number = numeric(resolution.get("value"))
        if resolved_number is None:
            continue
        source_goal_ids = [
            " ".join(str(value or "").strip().split())
            for value in resolution.get("source_goal_ids") or []
        ]
        if any(
            resolved_number in goal_numbers.get(goal_id, set())
            for goal_id in source_goal_ids
        ):
            continue
        step_id = str(resolution.get("step_id") or "").strip()
        parameter = str(resolution.get("parameter") or "").strip()
        step = steps.get(step_id)
        if not isinstance(step, dict):
            continue
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        argument_number = numeric(args.get(parameter))
        capability_id = str(step.get("capability_id") or "").strip()
        parameter_schema = (
            schemas.get(capability_id, {}).get("properties", {}).get(parameter, {})
        )
        schema_default = (
            parameter_schema.get("default")
            if isinstance(parameter_schema, dict)
            else None
        )
        default_number = numeric(schema_default)
        if (
            argument_number is None
            or default_number is None
            or resolved_number != argument_number
            or resolved_number != default_number
        ):
            continue
        resolution["strategy"] = "schema_default"
        resolution["source_goal_ids"] = []
        repairs.append(
            {
                "step_id": step_id,
                "capability_id": capability_id,
                "parameter": parameter,
                "value": resolution.get("value"),
                "from_strategy": "user_supplied",
                "to_strategy": "schema_default",
                "reason": "exact_declared_catalog_default_absent_from_cited_goals",
            }
        )
    return normalized, repairs


def normalize_detached_parameter_resolutions(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove only non-blocking resolution records with no step argument.

    A ``PlanParameterResolution`` is provenance for one exact executable argument;
    it does not own the argument or any Goal meaning.  When a model attaches a
    non-blocking resolution to a parameter absent from the referenced step while
    the exact resolved value is already carried by another top-level argument, that
    record cannot ground additional execution meaning and is mechanically detached.
    Dropping it does not rewrite the selected Capability, step arguments, Goal
    ownership, timing, or disposition.  All remaining authoritative binding and
    numeric-grounding checks still run, so a missing or differently nested material
    argument continues through the normal repair/fail-closed path.

    Blocking resolutions are deliberately retained because they describe an
    unresolved parameter that may not yet exist in executable ``args``.
    """

    normalized = copy.deepcopy(raw)
    steps = {
        str(item.get("step_id") or "").strip(): item
        for item in normalized.get("steps") or []
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    resolutions = normalized.get("parameter_resolutions")
    if not isinstance(resolutions, list):
        return normalized, []

    retained: list[Any] = []
    repairs: list[dict[str, Any]] = []
    for resolution in resolutions:
        if not isinstance(resolution, dict) or resolution.get("blocking") is True:
            retained.append(resolution)
            continue
        step_id = str(resolution.get("step_id") or "").strip()
        parameter = str(resolution.get("parameter") or "").strip()
        step = steps.get(step_id)
        args = step.get("args") if isinstance(step, dict) else None
        if (
            not step_id
            or not parameter
            or not isinstance(args, dict)
            or parameter in args
        ):
            retained.append(resolution)
            continue
        equivalent_arguments = sorted(
            str(name)
            for name, value in args.items()
            if _material_values_equal(
                resolution.get("value"),
                value,
                list_compatible=(
                    isinstance(resolution.get("value"), list)
                    or isinstance(value, list)
                ),
            )
        )
        if not equivalent_arguments:
            retained.append(resolution)
            continue
        repairs.append(
            {
                "normalization": "detached_parameter_resolution_removed",
                "step_id": step_id,
                "parameter": parameter,
                "step_argument_keys": sorted(str(key) for key in args),
                "equivalent_step_argument_keys": equivalent_arguments,
            }
        )

    normalized["parameter_resolutions"] = retained
    return normalized, repairs


def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    provider_required_vocal_goal_ids: list[str] | None = None,
    provider_required_media_goal_operations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan``. A planner
    may regenerate once only when this DTO is mechanically malformed; semantic
    rejection is not a same-tier repair trigger. Fast Planner uses the same decoder-tight
    per-goal shape for one or many goals so the schema never instructs the model
    to omit fields that deterministic validation requires.
    """

    if planner_tier == "fast":
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=expected_goal_ids,
            allowed_capability_ids=allowed_capability_ids,
            capability_input_schemas=capability_input_schemas,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
        )
        schema["title"] = "FastPlannerModelOutput"
        return schema

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = (
        "FastPlannerModelOutput" if planner_tier == "fast" else "DeepPlannerModelOutput"
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

    planner_response_text = properties.get("response_text")
    if isinstance(planner_response_text, dict) and requires_execution:
        planner_response_text["description"] = (
            "Optional prospective conversational delta for executable work. Use "
            "Interaction Context to avoid repeating already delivered or pending "
            "speech. This field never satisfies the effectful Goal and never proves "
            "execution or an external result."
        )

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)
    provider_vocal_goal_set = set(provider_required_vocal_goal_ids or []).intersection(
        allowed_goals
    )
    provider_media_goal_operations = {
        goal_id: operation
        for goal_id, operation in (provider_required_media_goal_operations or {}).items()
        if goal_id in allowed_goals and operation in MEDIA_CAPABILITY_IDS
    }
    vocal_capability_available = VOCAL_PERFORMANCE_CAPABILITY_ID in allowed_capabilities

    if requires_execution and not response_goal_set:
        planner_response_text = properties.get("response_text")
        if isinstance(planner_response_text, dict):
            planner_response_text["maxLength"] = 0
            planner_response_text["description"] = (
                "Execution-only planning does not author speech; communication is "
                "owned by the response layer."
            )

    # Both tiers must emit the multi-goal outcome envelope.  Deep Planner always
    # emits a complete map.  Fast Planner uses one flat decoder-compatible shape:
    # either an empty map for semantic escalation or a complete terminal map.
    if len(allowed_goals) > 1 and "goal_outcomes" not in required:
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
        outcome_disposition = outcome_schema.get("properties", {}).get("disposition")
        if isinstance(outcome_disposition, dict):
            if response_only:
                outcome_disposition["enum"] = (
                    ["respond"]
                    if planner_tier == "fast"
                    else ["respond", "clarify", "unavailable", "refused"]
                )
            elif planner_tier == "fast":
                outcome_disposition["enum"] = ["respond", "execute"]
            else:
                outcome_disposition["enum"] = [
                    "respond",
                    "execute",
                    "clarify",
                    "unavailable",
                    "refused",
                ]

        outcome_properties = outcome_schema.get("properties", {})
        base_branches: list[dict[str, Any]] = []
        allowed_outcomes = (
            (
                ["respond"]
                if planner_tier == "fast"
                else ["respond", "clarify", "unavailable", "refused"]
            )
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
            branch: dict[str, Any] = {"properties": {"disposition": {"enum": [outcome_name]}}}
            branch_props = branch["properties"]
            if outcome_name == "execute":
                branch_props["coverage"] = {"enum": ["complete"]}
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
        if base_branches and planner_tier == "fast":
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
                if isinstance(capability_id, dict) and allowed_capabilities:
                    capability_id["enum"] = allowed_capabilities
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
            top_satisfaction = properties.get("goal_satisfaction")
            if isinstance(top_satisfaction, dict):
                top_satisfaction.clear()
                top_satisfaction.update(copy.deepcopy(satisfaction_schema))
                top_satisfaction["description"] = (
                    "Required prospective adequacy judgment for the complete "
                    "Deep Planner result, including clarify/unavailable/refused."
                )

        if isinstance(goal_outcomes, dict) and isinstance(outcome_schema, dict):
            outcome_properties = goal_outcomes.get("properties", {})
            for goal_id in allowed_goals:
                goal_property = outcome_properties.get(goal_id)
                if not isinstance(goal_property, dict):
                    continue
                specialized = copy.deepcopy(outcome_schema)
                specialized_properties = specialized.get("properties", {})
                if isinstance(satisfaction_schema, dict):
                    specialized_satisfaction = copy.deepcopy(satisfaction_schema)
                    satisfaction_properties = specialized_satisfaction.get("properties", {})
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
                    specialized_properties["satisfaction"] = specialized_satisfaction
                if requires_execution and goal_id not in response_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = [
                            "execute",
                            "clarify",
                            "unavailable",
                            "refused",
                        ]
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field["maxLength"] = 0
                        response_text_field["description"] = (
                            "Execution Goals do not author speech; communication is "
                            "owned by the response layer."
                        )
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
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
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                == ["respond"]
                            )
                        ]
                if goal_id in provider_vocal_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = (
                            [
                                "execute",
                                "clarify",
                                "unavailable",
                                "refused",
                            ]
                            if vocal_capability_available
                            else [
                                "clarify",
                                "unavailable",
                                "refused",
                            ]
                        )
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("minLength", None)
                        response_text_field["maxLength"] = 800
                        response_text_field["description"] = (
                            "Optional conversational delta; it never substitutes for "
                            "the provider-required vocal performance."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict) and not vocal_capability_available:
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                != ["respond"]
                            )
                            and (
                                vocal_capability_available
                                or (
                                    branch.get("properties", {}).get("disposition", {}).get("enum")
                                    != ["execute"]
                                )
                            )
                        ]
                if goal_id in provider_media_goal_operations:
                    exact_media_capability = MEDIA_CAPABILITY_IDS[
                        provider_media_goal_operations[goal_id]
                    ]
                    media_capability_available = exact_media_capability in allowed_capabilities
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = (
                            ["execute", "clarify", "unavailable", "refused"]
                            if media_capability_available
                            else ["clarify", "unavailable", "refused"]
                        )
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("minLength", None)
                        response_text_field["maxLength"] = 800
                        response_text_field["description"] = (
                            "Optional conversational delta; it never substitutes for "
                            "the provider-required media operation."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict) and not media_capability_available:
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                != ["respond"]
                            )
                            and (
                                media_capability_available
                                or (
                                    branch.get("properties", {}).get("disposition", {}).get("enum")
                                    != ["execute"]
                                )
                            )
                        ]
                goal_property.clear()
                goal_property.update(specialized)
                goal_property["description"] = (
                    "Complete model-authored Deep Planner outcome for "
                    f"authoritative goal {goal_id!r}."
                )

    if planner_tier == "deep":
        max_deep_steps = max(4, len(allowed_goals) * 4)
        steps_schema = properties.get("steps")
        if isinstance(steps_schema, dict):
            steps_schema["maxItems"] = max_deep_steps
            steps_schema["description"] = (
                "A bounded compositional plan with at most four executable "
                "steps per authoritative Goal. Repeated motions belong in a "
                "capability count argument; never duplicate a step."
            )
        parameter_resolution_schema = properties.get("parameter_resolutions")
        if isinstance(parameter_resolution_schema, dict):
            parameter_resolution_schema["maxItems"] = max_deep_steps * 2
        unresolved_schema = properties.get("unresolved")
        if isinstance(unresolved_schema, dict):
            unresolved_schema["maxItems"] = max(4, len(allowed_goals) * 2)

        def bound_deep_text(
            owner: dict[str, Any], field_name: str, maximum: int
        ) -> None:
            field = owner.get(field_name)
            if isinstance(field, dict):
                current = field.get("maxLength")
                field["maxLength"] = (
                    min(int(current), maximum)
                    if isinstance(current, int)
                    else maximum
                )

        bound_deep_text(properties, "goal_summary", 240)
        bound_deep_text(properties, "response_text", 800)
        bound_deep_text(properties, "escalation_reason", 240)
        step_model = schema.get("$defs", {}).get("PlannerModelStep")
        if isinstance(step_model, dict):
            bound_deep_text(step_model.get("properties", {}), "reason_summary", 240)
        resolution_model = schema.get("$defs", {}).get("PlanParameterResolution")
        if isinstance(resolution_model, dict):
            bound_deep_text(resolution_model.get("properties", {}), "rationale", 240)
        satisfaction_model = schema.get("$defs", {}).get("PlannerGoalSatisfaction")
        if isinstance(satisfaction_model, dict):
            bound_deep_text(satisfaction_model.get("properties", {}), "rationale", 320)
        outcome_model = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
        if isinstance(outcome_model, dict):
            bound_deep_text(outcome_model.get("properties", {}), "rationale", 320)

        def bound_deep_prose(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
                    bound_deep_text(node_properties, "reason_summary", 240)
                    bound_deep_text(node_properties, "rationale", 320)
                for nested in node.values():
                    bound_deep_prose(nested)
            elif isinstance(node, list):
                for nested in node:
                    bound_deep_prose(nested)

        bound_deep_prose(schema)

    if response_only:
        steps_schema = properties.get("steps")
        if isinstance(steps_schema, dict):
            steps_schema["maxItems"] = 0
            steps_schema["description"] = (
                "The canonical Goals are provider-free direct speech responsibilities; "
                "return no executable plan steps."
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
        _constrain_planner_step_args(
            step_schema,
            allowed_capabilities=allowed_capabilities,
            capability_input_schemas=capability_input_schemas,
        )
    _constrain_terminal_unresolved(schema)
    return schema


def fast_multi_goal_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
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
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
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
    bound_text(
        properties,
        "response_text",
        0 if requires_execution and not response_goal_set else 800,
    )
    if requires_execution:
        response_text_field = properties.get("response_text")
        if isinstance(response_text_field, dict):
            response_text_field["description"] = (
                "Planner speech is empty for execution-only work; a separate "
                "response owner handles communication. Mixed plans may carry only "
                "the direct-response Goal delta."
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
        # exhausted.  A goal that needs multiple capabilities belongs in Deep
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
                "The canonical Goals are provider-free direct speech responsibilities; "
                "return no executable plan steps."
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
        bound_text(
            outcome_properties,
            "response_text",
            0 if requires_execution and not response_goal_set else 800,
        )
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
                if isinstance(capability_id, dict) and allowed_capabilities:
                    capability_id["enum"] = allowed_capabilities
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
    if isinstance(step_schema, dict):
        _constrain_planner_step_args(
            step_schema,
            allowed_capabilities=allowed_capabilities,
            capability_input_schemas=capability_input_schemas,
        )

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
            specialized_satisfaction_properties = specialized_satisfaction.get("properties", {})
            for field_name in ("satisfied_goal_ids", "unmet_goal_ids"):
                field_schema = specialized_satisfaction_properties.get(field_name)
                if isinstance(field_schema, dict):
                    field_schema["items"] = {"type": "string", "enum": [goal_id]}
                    field_schema["uniqueItems"] = True
                    field_schema["maxItems"] = 1
            satisfied = specialized_satisfaction_properties.get("satisfied_goal_ids")
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
            specialized_outcome_properties = specialized_outcome.get("properties", {})
            if requires_execution and goal_id not in response_goal_set:
                disposition_field = specialized_outcome_properties.get("disposition")
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["execute", "clarify", "escalate"]
                response_text_field = specialized_outcome_properties.get("response_text")
                if isinstance(response_text_field, dict):
                    response_text_field["maxLength"] = 0
                    response_text_field["description"] = (
                        "Execution Goals do not author speech; communication is "
                        "owned by the response layer."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            != ["respond"]
                        )
                    ]
            if goal_id in response_goal_set:
                disposition_field = specialized_outcome_properties.get("disposition")
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["respond"]
                response_text_field = specialized_outcome_properties.get("response_text")
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
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            == ["respond"]
                        )
                    ]
            specialized_outcome_properties["satisfaction"] = strict_satisfaction_schema(
                specialized_satisfaction,
                exact_satisfied_count=1,
            )
            step_ids = specialized_outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = 0 if goal_id in response_goal_set else 1
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
        key: properties[key] for key in preferred_property_order if key in properties
    }
    _constrain_terminal_unresolved(schema)
    return schema


def _constrain_planner_step_args(
    step_schema: dict[str, Any],
    *,
    allowed_capabilities: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None,
) -> None:
    """Bind each model-selected capability to its exact provider arg schema."""

    if not capability_input_schemas:
        return
    base_properties = step_schema.get("properties")
    if not isinstance(base_properties, dict):
        return
    required = [
        str(item) for item in step_schema.get("required", []) if str(item).strip()
    ]
    branches: list[dict[str, Any]] = []
    for capability_id in allowed_capabilities:
        input_schema = capability_input_schemas.get(capability_id)
        if not isinstance(input_schema, dict):
            continue
        properties = copy.deepcopy(base_properties)
        properties["capability_id"] = {
            "type": "string",
            "enum": [capability_id],
        }
        properties["args"] = copy.deepcopy(input_schema)
        branches.append(
            {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }
        )
    if branches:
        step_schema["oneOf"] = branches


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


def _constrain_terminal_unresolved(schema: dict[str, Any]) -> None:
    """Align decoder branches with terminal unresolved-work validators."""

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if (
                isinstance(properties, dict)
                and isinstance(properties.get("disposition"), dict)
                and isinstance(properties.get("unresolved"), dict)
            ):
                node.setdefault("allOf", []).append(
                    {
                        "if": {
                            "properties": {
                                "disposition": {"enum": ["execute", "respond"]}
                            },
                            "required": ["disposition"],
                        },
                        "then": {
                            "properties": {"unresolved": {"maxItems": 0}},
                            "required": ["unresolved"],
                        },
                    }
                )
            for value in list(node.values()):
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)


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
    planners allow only one mechanical DTO regeneration, so validation feedback must
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
        elif item.get("capability_id"):
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
                ("goal_outcomes keys must cover exactly the authoritative Goal Association IDs"),
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
            allowed_outcome_dispositions = (
                {"execute", "respond", "clarify", "escalate"}
                if planner_tier == "fast"
                else {
                    "execute",
                    "respond",
                    "clarify",
                    "unavailable",
                    "refused",
                }
            )
            if outcome_disposition not in allowed_outcome_dispositions:
                add(
                    ["goal_outcomes", goal_id, "disposition"],
                    f"{planner_tier} goal outcome requires one legal explicit disposition",
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
                if (
                    not outcome.get("unresolved")
                    and not str(outcome.get("rationale") or "").strip()
                ):
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
            elif outcome_disposition in {"unavailable", "refused"} and normalized_outcome_step_ids:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "unavailable and refused goal outcomes must not reference steps",
                    value=normalized_outcome_step_ids,
                )

            unknown_steps = set(normalized_outcome_step_ids) - step_ids
            if unknown_steps:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "goal outcome references unknown step IDs: " + ",".join(sorted(unknown_steps)),
                    value=normalized_outcome_step_ids,
                )

        normalized_dispositions = {item for item in outcome_dispositions if item}
        if normalized_dispositions:
            expected_disposition = (
                "mixed" if len(normalized_dispositions) > 1 else next(iter(normalized_dispositions))
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
    elif len(expected_goal_set) > 1 and disposition in {"execute", "respond", "mixed"}:
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
    """Normalize transport redundancy without inventing planning semantics.

    ``steps[].source_goal_ids`` is the model's semantic ownership judgment.
    ``goal_outcomes.*.step_ids`` and the top-level disposition repeat that same
    judgment as cross-reference and aggregate transport fields. Models regularly
    produce stale or nonexistent step references even when capability choice,
    arguments, and source ownership are otherwise coherent. Rebuild only those
    redundant fields from the model-authored step ownership; never choose a
    capability, add a step, or assign an unowned Goal. An execute outcome with no
    owned step therefore remains invalid and must be repaired by the model.
    """

    normalized = copy.deepcopy(raw)
    outcomes = normalized.get("goal_outcomes")
    if not isinstance(outcomes, dict):
        return normalized

    expected = list(dict.fromkeys(expected_goal_ids_for_turn))
    expected_set = set(expected)
    owned_step_ids: dict[str, list[str]] = {goal_id: [] for goal_id in expected}
    steps = normalized.get("steps")
    ownership_is_usable = isinstance(steps, list)
    seen_step_ids: set[str] = set()
    if ownership_is_usable:
        for item in steps:
            if not isinstance(item, dict):
                ownership_is_usable = False
                break
            step_id = " ".join(str(item.get("step_id") or "").strip().split())
            source_goal_ids = item.get("source_goal_ids")
            if not step_id or step_id in seen_step_ids or not isinstance(source_goal_ids, list):
                ownership_is_usable = False
                break
            seen_step_ids.add(step_id)
            for raw_goal_id in source_goal_ids:
                goal_id = " ".join(str(raw_goal_id or "").strip().split())
                if goal_id in expected_set and step_id not in owned_step_ids[goal_id]:
                    owned_step_ids[goal_id].append(step_id)

    normalized_outcomes: dict[str, Any] = {}
    for raw_goal_id, value in outcomes.items():
        goal_id = str(raw_goal_id)
        if not isinstance(value, dict):
            normalized_outcomes[goal_id] = value
            continue
        outcome = copy.deepcopy(value)
        response_text = str(outcome.get("response_text") or "").strip()
        owned = owned_step_ids.get(goal_id, []) if ownership_is_usable else []
        if not outcome.get("disposition"):
            if owned:
                outcome["disposition"] = "execute"
            elif response_text:
                outcome["disposition"] = "respond"
        if (
            not outcome.get("coverage")
            and normalized.get("coverage") == "complete"
            and outcome.get("disposition") in {"execute", "respond"}
        ):
            outcome["coverage"] = "complete"
        if ownership_is_usable and outcome.get("disposition") == "execute":
            outcome["step_ids"] = list(owned)
        elif outcome.get("disposition") == "respond":
            outcome["step_ids"] = []
        normalized_outcomes[goal_id] = outcome
    normalized["goal_outcomes"] = normalized_outcomes

    if set(normalized_outcomes) == expected_set and expected_set:
        dispositions = {
            str(item.get("disposition") or "")
            for item in normalized_outcomes.values()
            if isinstance(item, dict)
        }
        if "" not in dispositions:
            aggregate = (
                "mixed"
                if dispositions == {"execute", "respond"}
                else next(iter(dispositions))
                if len(dispositions) == 1
                else ""
            )
            if aggregate:
                normalized["disposition"] = aggregate

    if (
        normalized.get("disposition") == "respond"
        and not str(normalized.get("response_text") or "").strip()
        and len(expected) == 1
    ):
        sole = normalized_outcomes.get(expected[0])
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
        if expected_goal_ids_for_turn and set(normalized_echo) != set(expected_goal_ids_for_turn):
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
    if planner_tier == "fast" and len(expected_goal_id_set) > 1 and not goal_outcomes_were_supplied:
        raise ValueError("multi-goal fast planner output requires an explicit goal_outcomes object")
    if planner_tier == "fast" and output.disposition == "escalate":
        if output.coverage not in {"partial", "uncertain"}:
            raise ValueError("fast semantic escalation requires partial or uncertain coverage")
        if len(expected_goal_id_set) <= 1:
            if output.goal_outcomes:
                raise ValueError("single-goal fast semantic escalation requires goal_outcomes={}")
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
            "goal_outcomes keys must cover exactly the authoritative Goal Association IDs"
        )
    if planner_tier == "fast" and output.goal_outcomes:
        outcome_dispositions = {outcome.disposition for outcome in output.goal_outcomes.values()}
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
                raise ValueError("all-clarify goal outcomes require top-level disposition=clarify")
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
                    "multi-goal fast semantic escalation requires model-authored goal_satisfaction"
                )
            if output.goal_satisfaction.status == "exact":
                raise ValueError("fast semantic escalation cannot claim exact goal satisfaction")
        elif output.disposition == "escalate":
            raise ValueError("multi-goal fast escalation requires one escalate outcome per goal")
        if output.disposition == "mixed" and outcome_dispositions != {
            "execute",
            "respond",
        }:
            raise ValueError("fast mixed output requires at least one execute and one respond goal")
    for goal_id, outcome in output.goal_outcomes.items():
        if planner_tier == "fast" and len(expected_goal_id_set) > 1:
            if outcome.satisfaction is None:
                raise ValueError("multi-goal fast outcomes require model-authored satisfaction")
        referenced_goal_ids = {
            *(outcome.satisfaction.satisfied_goal_ids if outcome.satisfaction else []),
            *(outcome.satisfaction.unmet_goal_ids if outcome.satisfaction else []),
        }
        foreign_goal_ids = referenced_goal_ids - {goal_id}
        if foreign_goal_ids:
            raise ValueError(
                "per-goal outcome satisfaction may reference only its enclosing "
                f"authoritative goal ID {goal_id!r}; found " + ",".join(sorted(foreign_goal_ids))
            )
    if planner_tier == "fast" and len(expected_goal_id_set) > 1:
        if output.goal_satisfaction is None:
            raise ValueError("multi-goal fast output requires model-authored goal_satisfaction")
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
