"""Deep-Planner deterministic validation for the single Planner authority."""

from __future__ import annotations

from typing import Any

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

from .capabilities.validator import validate_args_for_schema
from .planner_validation import parallel_plan_contract_errors


def deep_plan_validation_errors(
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
    *,
    expected_goal_ids: list[str],
    authoritative_goals: list[dict[str, Any]],
    requires_execution: bool,
    min_goal_satisfaction: float,
    allows_evidence_response: bool = False,
) -> list[dict[str, Any]]:
    allowed = {item["capability_id"]: item for item in capabilities}
    errors: list[dict[str, Any]] = []
    if expected_goal_ids and set(plan.goal_ids) != set(expected_goal_ids):
        errors.append(
            {
                "type": "goal_ids_do_not_match_goal_association",
                "expected_goal_ids": expected_goal_ids,
                "actual_goal_ids": list(plan.goal_ids),
            }
        )
    if (
        requires_execution
        and not allows_evidence_response
        and plan.disposition not in {"clarify", "unavailable", "refused"}
        and not plan.steps
    ):
        errors.append(
            {
                "type": "canonical_goal_requires_executable_step",
                "disposition": plan.disposition,
            }
        )
    if plan.coverage == "complete":
        if plan.goal_satisfaction is None:
            errors.append({"type": "missing_goal_satisfaction"})
        elif (
            plan.disposition == "execute"
            or (plan.disposition == "respond" and not allows_evidence_response)
        ) and plan.goal_satisfaction.score < min_goal_satisfaction:
            errors.append(
                {
                    "type": "goal_satisfaction_below_threshold",
                    "score": plan.goal_satisfaction.score,
                    "required": min_goal_satisfaction,
                }
            )
    if plan.disposition == "mixed":
        for outcome in plan.goal_outcomes:
            if outcome.disposition not in {"execute", "respond"}:
                continue
            # The complete aggregate satisfaction object and exact keyed
            # outcome map already express prospective adequacy. Per-outcome
            # satisfaction is useful when the model supplies it, but is not
            # a second mandatory copy of the same judgment. Treat a supplied
            # low score as authoritative without failing solely on omission.
            if (
                outcome.satisfaction is not None
                and outcome.satisfaction.score < min_goal_satisfaction
            ):
                errors.append(
                    {
                        "type": "goal_outcome_satisfaction_below_threshold",
                        "goal_id": outcome.goal_id,
                        "score": outcome.satisfaction.score,
                        "required": min_goal_satisfaction,
                    }
                )
    step_ids = {step.step_id for step in plan.steps}
    for resolution in plan.parameter_resolutions:
        if resolution.step_id not in step_ids and not resolution.blocking:
            errors.append(
                {
                    "type": "parameter_resolution_unknown_step",
                    "step_id": resolution.step_id,
                    "parameter": resolution.parameter,
                }
            )
        if resolution.blocking and plan.disposition == "execute":
            errors.append(
                {
                    "type": "blocking_parameter_resolution",
                    "step_id": resolution.step_id,
                    "parameter": resolution.parameter,
                }
            )
    for step in plan.steps:
        capability = allowed.get(step.capability_id)
        if capability is None:
            errors.append(
                {
                    "type": "unknown_capability",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            )
            continue
        if not capability.get("available") or not capability.get("interaction_executable"):
            errors.append(
                {
                    "type": "capability_not_executable",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            )
            continue
        schema_errors = validate_args_for_schema(step.args, capability.get("input_schema") or {})
        if schema_errors:
            errors.append(
                {
                    "type": "invalid_args",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "errors": schema_errors[:8],
                }
            )
    errors.extend(parallel_plan_contract_errors(plan, capabilities))
    return errors
