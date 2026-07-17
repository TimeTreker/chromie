from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

# Response Composer owns user-facing speech in the goal-driven pipeline.  These
# runtime transport skills are valid in legacy/native InteractionResponse task
# lists, but they are not task-plan leaves: conversational goals use a
# ``respond`` outcome and model-authored ``response_text`` instead.
RESPONSE_COMPOSER_OWNED_SKILL_IDS = frozenset({"chromie.speak"})


def is_planner_step_skill(skill_id: str) -> bool:
    return str(skill_id or "").strip() not in RESPONSE_COMPOSER_OWNED_SKILL_IDS


class PlannerModelStep(BaseModel):
    """Semantic plan leaf returned by a planner model.

    Step ownership and arguments are model judgments.  They intentionally have
    no host default at this boundary; otherwise a missing multi-goal ownership
    decision can silently authorize one step for every active goal.
    """

    model_config = ConfigDict(extra="forbid")

    step_id: str = ""
    skill_id: str = Field(min_length=1)
    args: dict[str, Any]
    timing: PlanTiming = "sequential"
    source_goal_ids: list[str] = Field(default_factory=list)
    reason_summary: str = ""


class PlannerGoalSatisfaction(GoalSatisfactionAssessment):
    """Prospective adequacy of the proposed plan, not execution progress."""

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
        elif self.disposition == "respond":
            if self.coverage != "complete" or not self.response_text.strip():
                raise ValueError(
                    "respond goal outcome requires complete coverage and response_text"
                )
            if self.step_ids:
                raise ValueError("respond goal outcome must not reference steps")
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

    @model_validator(mode="after")
    def validate_semantic_shape(self) -> "PlannerModelOutput":
        response_transport_steps = [
            step.skill_id
            for step in self.steps
            if not is_planner_step_skill(step.skill_id)
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
    active = context.get("active_goal_snapshots") or []
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
                }
            )
    return result


def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_skill_ids: list[str],
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan`` with one
    bounded same-tier model repair.
    """

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = (
        "FastPlannerModelOutput"
        if planner_tier == "fast"
        else "DeepPlannerModelOutput"
    )
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in ("disposition", "coverage", "confidence", "steps", "goal_satisfaction"):
        if field_name not in required:
            required.append(field_name)

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["enum"] = (
            ["respond", "execute", "escalate"]
            if planner_tier == "fast"
            else [
                "respond",
                "execute",
                "mixed",
                "clarify",
                "unavailable",
                "refused",
            ]
        )

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_skills = list(dict.fromkeys(allowed_skill_ids))

    goal_outcomes = properties.get("goal_outcomes")
    if isinstance(goal_outcomes, dict):
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
        if allowed_goals:
            goal_outcomes.update(
                {
                    "required": allowed_goals,
                    "minProperties": len(allowed_goals),
                }
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
                goal_id = node_properties.get("goal_id")
                if isinstance(goal_id, dict) and allowed_goals:
                    goal_id["enum"] = allowed_goals
                skill_id = node_properties.get("skill_id")
                if isinstance(skill_id, dict) and allowed_skills:
                    skill_id["enum"] = allowed_skills
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
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if isinstance(step_schema, dict):
        step_required = step_schema.setdefault("required", [])
        for field_name in ("step_id", "skill_id", "args", "source_goal_ids"):
            if field_name not in step_required:
                step_required.append(field_name)
    return schema


def validate_planner_model_output(
    raw: dict[str, Any],
    *,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> PlannerModelOutput:
    """Validate the semantic DTO and reject conflicting legacy goal echoes."""

    model_raw = dict(raw)
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
    if isinstance(raw_steps, list) and len(expected_goal_ids_for_turn) == 1:
        sole_goal_id = expected_goal_ids_for_turn[0]
        normalized_steps: list[Any] = []
        for item in raw_steps:
            if isinstance(item, dict) and not item.get("source_goal_ids"):
                item = {**item, "source_goal_ids": [sole_goal_id]}
            normalized_steps.append(item)
        model_raw["steps"] = normalized_steps

    output = PlannerModelOutput.model_validate(model_raw)
    allowed_dispositions = (
        {"respond", "execute", "escalate"}
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
    if (
        len(expected_goal_id_set) > 1
        and output.disposition in {"execute", "respond", "mixed"}
        and not output.goal_outcomes
    ):
        raise ValueError(
            "complete multi-goal planner output requires goal_outcomes keyed by "
            "every authoritative Goal Association ID"
        )
    if goal_outcomes_were_supplied and outcome_goal_ids != expected_goal_id_set:
        raise ValueError(
            "goal_outcomes keys must cover exactly the authoritative Goal "
            "Association IDs"
        )
    for goal_id, outcome in output.goal_outcomes.items():
        if outcome.satisfaction is None:
            continue
        referenced_goal_ids = {
            *outcome.satisfaction.satisfied_goal_ids,
            *outcome.satisfaction.unmet_goal_ids,
        }
        foreign_goal_ids = referenced_goal_ids - {goal_id}
        if foreign_goal_ids:
            raise ValueError(
                "per-goal outcome satisfaction may reference only its enclosing "
                f"authoritative goal ID {goal_id!r}; found "
                + ",".join(sorted(foreign_goal_ids))
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
