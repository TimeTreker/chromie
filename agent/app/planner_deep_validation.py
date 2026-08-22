from __future__ import annotations

"""Deep-Planner-specific deterministic repair, safety, and diagnostic mechanics.

This is an implementation layer of the single Planner authority, not another Planner.
"""

import copy
import json
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

from .capabilities.validator import validate_args_for_schema
from .planner_context import planner_goal_execution_requirements
from .planner_model_contract import PlannerDTOContractError
from .planner_validation import (
    explicit_numeric_goal_values,
    parallel_plan_contract_errors,
    planner_contract_diagnostics,
    requires_safety_revision,
    requires_sequential_safety_revision,
)


def merge_planner_feedback(
    *groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            key = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def initial_safety_feedback(
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Carry upstream deterministic safety findings into Deep attempt one."""

    candidates: list[dict[str, Any]] = []
    fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution")
    if isinstance(fast_plan, dict):
        metadata = fast_plan.get("metadata")
        if isinstance(metadata, dict):
            parallel_errors = metadata.get("parallel_contract_errors")
            # A lone step labeled parallel has no overlap relation to
            # revise.  Carry this finding only when Fast actually proposed
            # a multi-step concurrency plan; otherwise Deep may safely
            # regenerate the single step as sequential.
            if (
                isinstance(parallel_errors, list)
                and int(metadata.get("executable_step_count") or 0) > 1
            ):
                candidates.extend(item for item in parallel_errors if isinstance(item, dict))
    runtime_feedback = context.get("runtime_validator_feedback")
    if isinstance(runtime_feedback, list):
        candidates.extend(item for item in runtime_feedback if isinstance(item, dict))
    return [
        dict(item)
        for item in merge_planner_feedback(candidates)
        if requires_safety_revision([item])
    ]


def normalize_mixed_goal_outcome_accounting(
    raw: dict[str, Any],
    *,
    expected_goal_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize only redundant aggregate fields in an explicit mixed plan.

    Per-Goal outcomes are the semantic authority. When they cover every
    canonical Goal, contain at least two terminal dispositions, and explicitly
    leave some Goals non-executing, top-level ``coverage`` means accounting
    coverage and is therefore mechanically ``complete``. A step that no execute
    outcome references is contradictory DTO residue and cannot be executed; it
    is removed without changing any Goal outcome or inventing replacement work.
    """

    normalized = copy.deepcopy(raw)
    outcomes = normalized.get("goal_outcomes")
    expected = set(expected_goal_ids)
    if not isinstance(outcomes, dict) or set(outcomes) != expected or not expected:
        return normalized, []
    dispositions = {
        str(item.get("disposition") or "").strip()
        for item in outcomes.values()
        if isinstance(item, dict)
    }
    if len(dispositions) < 2 or not dispositions.issubset(
        {"execute", "respond", "clarify", "unavailable", "refused"}
    ):
        return normalized, []
    repairs: list[dict[str, Any]] = []
    if normalized.get("disposition") != "mixed":
        repairs.append(
            {
                "path": "disposition",
                "from": normalized.get("disposition"),
                "to": "mixed",
                "basis": "explicit per-Goal terminal dispositions differ",
            }
        )
        normalized["disposition"] = "mixed"
    if normalized.get("coverage") != "complete":
        repairs.append(
            {
                "path": "coverage",
                "from": normalized.get("coverage"),
                "to": "complete",
                "basis": "every canonical Goal has an explicit terminal outcome",
            }
        )
        normalized["coverage"] = "complete"

    for goal_id, outcome in outcomes.items():
        if not isinstance(outcome, dict):
            continue
        satisfaction = outcome.get("satisfaction")
        if not isinstance(satisfaction, dict) or satisfaction.get("status") != "exact":
            continue
        satisfied = {
            str(item).strip()
            for item in satisfaction.get("satisfied_goal_ids") or []
            if str(item).strip()
        }
        unmet = list(satisfaction.get("unmet_goal_ids") or [])
        retained_unmet = [
            item for item in unmet if str(item).strip() not in satisfied
        ]
        if retained_unmet != unmet:
            repairs.append(
                {
                    "path": f"goal_outcomes.{goal_id}.satisfaction.unmet_goal_ids",
                    "from": unmet,
                    "to": retained_unmet,
                    "basis": "the same Goal cannot be both satisfied and unmet",
                }
            )
            satisfaction["unmet_goal_ids"] = retained_unmet
        unmet_requirements = list(
            satisfaction.get("unmet_requirements") or []
        )
        if unmet_requirements:
            repairs.append(
                {
                    "path": (
                        f"goal_outcomes.{goal_id}.satisfaction."
                        "unmet_requirements"
                    ),
                    "from": unmet_requirements,
                    "to": [],
                    "basis": (
                        "status=exact is the explicit prospective adequacy "
                        "judgment and cannot also carry unmet requirements"
                    ),
                }
            )
            satisfaction["unmet_requirements"] = []

    per_goal_satisfaction = [
        outcome.get("satisfaction")
        for outcome in outcomes.values()
        if isinstance(outcome, dict)
        and isinstance(outcome.get("satisfaction"), dict)
    ]
    aggregate_satisfaction = normalized.get("goal_satisfaction")
    if (
        len(per_goal_satisfaction) == len(expected)
        and isinstance(aggregate_satisfaction, dict)
    ):
        scores = [item.get("score") for item in per_goal_satisfaction]
        if all(
            isinstance(score, (int, float)) and not isinstance(score, bool)
            for score in scores
        ):
            aggregate_score = sum(float(score) for score in scores) / len(scores)
            aggregate_satisfied = list(
                dict.fromkeys(
                    str(goal_id).strip()
                    for item in per_goal_satisfaction
                    for goal_id in item.get("satisfied_goal_ids") or []
                    if str(goal_id).strip()
                )
            )
            aggregate_unmet = list(
                dict.fromkeys(
                    str(goal_id).strip()
                    for item in per_goal_satisfaction
                    for goal_id in item.get("unmet_goal_ids") or []
                    if str(goal_id).strip()
                )
            )
            aggregate_requirements = list(
                dict.fromkeys(
                    " ".join(str(requirement or "").strip().split())
                    for item in per_goal_satisfaction
                    for requirement in item.get("unmet_requirements") or []
                    if " ".join(str(requirement or "").strip().split())
                )
            )
            aggregate_status = (
                "exact"
                if aggregate_score >= 0.95 and not aggregate_unmet and not aggregate_requirements
                else "substantial"
                if aggregate_score >= 0.75
                else "partial"
                if aggregate_score > 0.0
                else "unsatisfied"
            )
            aggregate_projection = {
                "score": aggregate_score,
                "status": aggregate_status,
                "satisfied_goal_ids": aggregate_satisfied,
                "unmet_goal_ids": aggregate_unmet,
                "unmet_requirements": aggregate_requirements,
            }
            changed_fields = {
                field_name: {
                    "from": aggregate_satisfaction.get(field_name),
                    "to": value,
                }
                for field_name, value in aggregate_projection.items()
                if aggregate_satisfaction.get(field_name) != value
            }
            if changed_fields:
                repairs.append(
                    {
                        "path": "goal_satisfaction",
                        "fields": changed_fields,
                        "basis": "deterministic aggregate of explicit per-Goal judgments",
                    }
                )
                aggregate_satisfaction.update(aggregate_projection)

    referenced_execute_steps = {
        str(step_id).strip()
        for outcome in outcomes.values()
        if isinstance(outcome, dict)
        and outcome.get("disposition") == "execute"
        for step_id in outcome.get("step_ids") or []
        if str(step_id).strip()
    }
    execute_owners_by_step: dict[str, list[str]] = {}
    for goal_id, outcome in outcomes.items():
        if not isinstance(outcome, dict) or outcome.get("disposition") != "execute":
            continue
        for step_id in outcome.get("step_ids") or []:
            normalized_step_id = str(step_id).strip()
            if normalized_step_id:
                execute_owners_by_step.setdefault(normalized_step_id, []).append(
                    str(goal_id)
                )
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return normalized, repairs
    retained: list[Any] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            retained.append(step)
            continue
        step_id = str(step.get("step_id") or "").strip()
        if not step_id or step_id in referenced_execute_steps:
            expected_owners = execute_owners_by_step.get(step_id, [])
            actual_owners = list(step.get("source_goal_ids") or [])
            if step_id and expected_owners and actual_owners != expected_owners:
                repaired_step = dict(step)
                repaired_step["source_goal_ids"] = expected_owners
                repairs.append(
                    {
                        "path": f"steps[{index}].source_goal_ids",
                        "step_id": step_id,
                        "from": actual_owners,
                        "to": expected_owners,
                        "basis": "execute outcomes are the per-Goal ownership authority",
                    }
                )
                retained.append(repaired_step)
                continue
            retained.append(step)
            continue
        repairs.append(
            {
                "path": f"steps[{index}]",
                "step_id": step_id,
                "reason": "not_referenced_by_any_execute_outcome",
            }
        )
    normalized["steps"] = retained
    return normalized, repairs


def validate_mechanical_numeric_revision_preserved(
    candidate: dict[str, Any],
    *,
    baseline: dict[str, Any],
) -> None:
    """Reject any semantic rewrite during a provenance-only DTO repair."""

    changed = sorted(
        field_name
        for field_name in set(candidate).union(baseline)
        if field_name != "parameter_resolutions"
        and candidate.get(field_name) != baseline.get(field_name)
    )
    if changed:
        raise PlannerDTOContractError(
            "mechanical numeric provenance repair changed semantic plan fields: "
            + ",".join(changed)
        )


def safety_revision_contract_errors(
    plan: CanonicalPlan,
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enforce the decoder's safety-revision grammar at runtime too."""

    if not requires_safety_revision(feedback):
        return []
    if plan.disposition in {"clarify", "unavailable", "refused"}:
        return (
            []
            if not plan.steps
            else [
                {
                    "type": "safety_revision_contract_not_satisfied",
                    "reason": "non-executable safety revision retained plan steps",
                }
            ]
        )
    relation = str(plan.metadata.get("plan_relation") or "exact")
    confirmation = plan.metadata.get("user_confirmation_required") is True
    retained_parallel_steps = [step.step_id for step in plan.steps if step.timing == "parallel"]
    if requires_sequential_safety_revision(feedback) and retained_parallel_steps:
        return [
            {
                "type": "safety_revision_contract_not_satisfied",
                "plan_relation": relation,
                "parallel_step_ids": retained_parallel_steps,
                "reason": (
                    "concurrency was rejected, so a safe revision cannot "
                    "retain parallel step timing"
                ),
            }
        ]
    if (
        plan.disposition in {"execute", "mixed"}
        and relation in {"safe_adjustment", "alternative"}
        and confirmation
        and bool(plan.response_text.strip())
    ):
        return []
    return [
        {
            "type": "safety_revision_contract_not_satisfied",
            "disposition": plan.disposition,
            "plan_relation": relation,
            "user_confirmation_required": confirmation,
            "response_text_present": bool(plan.response_text.strip()),
            "reason": (
                "after concurrency safety rejection, execution requires an "
                "explicit safe_adjustment or alternative, explanatory "
                "response_text, and user confirmation"
            ),
        }
    ]


def detached_numeric_provenance_obligations(
    raw: Any,
    *,
    authoritative_goals: list[dict[str, Any]],
    error: Exception,
) -> list[dict[str, Any]]:
    """Identify only unambiguous missing duplicate numeric provenance rows."""

    if (
        "explicit numeric goal value has no matching user_supplied "
        "parameter resolution" not in str(error)
        or not isinstance(raw, dict)
    ):
        return []
    numeric_by_goal = explicit_numeric_goal_values(authoritative_goals)
    outcomes = raw.get("goal_outcomes")
    steps = raw.get("steps")
    resolutions = raw.get("parameter_resolutions")
    if not isinstance(steps, list):
        return []
    outcomes = outcomes if isinstance(outcomes, dict) else {}
    resolutions = resolutions if isinstance(resolutions, list) else []
    step_owned_goal_ids = {
        str(goal_id)
        for step in steps
        if isinstance(step, dict)
        for goal_id in step.get("source_goal_ids") or []
        if str(goal_id).strip()
    }

    def numeric(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            return float(str(value).strip())
        except ValueError:
            return None

    obligations: list[dict[str, Any]] = []
    for goal_id, values in numeric_by_goal.items():
        outcome = outcomes.get(goal_id)
        if isinstance(outcome, dict):
            if outcome.get("disposition") != "execute":
                continue
        elif goal_id not in step_owned_goal_ids:
            continue
        for value in values:
            candidates: list[tuple[str, str]] = []
            for step in steps:
                if not isinstance(step, dict) or goal_id not in (
                    step.get("source_goal_ids") or []
                ):
                    continue
                step_id = " ".join(str(step.get("step_id") or "").strip().split())
                args = step.get("args")
                if not step_id or not isinstance(args, dict):
                    continue
                for parameter, argument in args.items():
                    argument_number = numeric(argument)
                    if argument_number is None:
                        continue
                    scale = max(abs(float(value)), abs(argument_number), 1.0)
                    if abs(float(value) - argument_number) <= 1e-12 * scale:
                        candidates.append((step_id, str(parameter)))
            if len(candidates) != 1:
                return []
            step_id, parameter = candidates[0]
            already_present = any(
                isinstance(resolution, dict)
                and str(resolution.get("strategy") or "") == "user_supplied"
                and str(resolution.get("step_id") or "").strip() == step_id
                and str(resolution.get("parameter") or "").strip() == parameter
                and resolution.get("source_goal_ids") == [goal_id]
                and numeric(resolution.get("value")) is not None
                and abs(
                    float(value)
                    - float(numeric(resolution.get("value")) or 0.0)
                )
                <= 1e-12 * max(abs(float(value)), 1.0)
                for resolution in resolutions
            )
            if already_present:
                continue
            obligations.append(
                {
                    "step_id": step_id,
                    "parameter": parameter,
                    "value": value,
                    "source_goal_ids": [goal_id],
                }
            )
    return obligations


def deep_validation_error_items(
    exc: Exception,
    *,
    raw: Any,
    expected_goal_ids_for_turn: list[str],
    capability_payload: list[dict[str, Any]] | None = None,
    authoritative_goals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(exc, ValidationError):
        feedback = list(exc.errors(include_url=False))
    else:
        feedback = [
            {
                "type": "canonical_plan_contract_validation_failure",
                "error_type": type(exc).__name__,
                "message": str(exc)[:1000],
            }
        ]
    feedback.extend(
        planner_contract_diagnostics(
            raw,
            planner_tier="deep",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
    )
    if isinstance(raw, dict):
        schemas = {
            str(item.get("capability_id") or ""): item.get("input_schema") or {}
            for item in list(capability_payload or [])
        }
        steps = {
            str(item.get("step_id") or ""): item
            for item in raw.get("steps") or []
            if isinstance(item, dict) and str(item.get("step_id") or "").strip()
        }
        for resolution in raw.get("parameter_resolutions") or []:
            if not isinstance(resolution, dict):
                continue
            step_id = str(resolution.get("step_id") or "").strip()
            parameter = str(resolution.get("parameter") or "").strip()
            step = steps.get(step_id)
            if not parameter or not isinstance(step, dict):
                continue
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            if parameter in args:
                continue
            capability_id = str(step.get("capability_id") or "").strip()
            feedback.append(
                {
                    "type": "parameter_resolution_argument_mismatch",
                    "step_id": step_id,
                    "capability_id": capability_id,
                    "parameter": parameter,
                    "resolution_value": resolution.get("value"),
                    "resolution_strategy": resolution.get("strategy"),
                    "source_goal_ids": list(resolution.get("source_goal_ids") or []),
                    "actual_arg_keys": sorted(args),
                    "capability_input_schema": schemas.get(capability_id, {}),
                    "corrective_contract": (
                        "A nonblocking parameter_resolution must name an argument "
                        "present in the referenced step args with the same value. "
                        "If the value came from an authoritative Goal, use strategy "
                        "user_supplied. Regenerate a schema-valid consistent step "
                        "and resolution or return a non-executable clarification; "
                        "do not describe an absent argument only in prose."
                    ),
                }
            )
        if "no matching user_supplied parameter resolution" in str(exc):
            for resolution in raw.get("parameter_resolutions") or []:
                if not isinstance(resolution, dict):
                    continue
                if str(resolution.get("strategy") or "") == "user_supplied":
                    continue
                value = resolution.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                step_id = str(resolution.get("step_id") or "").strip()
                step = steps.get(step_id)
                if not isinstance(step, dict):
                    continue
                feedback.append(
                    {
                        "type": "explicit_numeric_resolution_strategy_mismatch",
                        "step_id": step_id,
                        "capability_id": str(
                            step.get("capability_id") or ""
                        ).strip(),
                        "parameter": str(
                            resolution.get("parameter") or ""
                        ).strip(),
                        "resolution_value": value,
                        "actual_strategy": resolution.get("strategy"),
                        "source_goal_ids": list(
                            resolution.get("source_goal_ids") or []
                        ),
                        "corrective_contract": (
                            "A numeric value copied from an authoritative Goal "
                            "must use strategy user_supplied, equal the referenced "
                            "step argument, and cite that Goal in source_goal_ids."
                        ),
                    }
                )
        if "numeric user_supplied parameter resolution is not present" in str(exc):
            for resolution in raw.get("parameter_resolutions") or []:
                if not isinstance(resolution, dict):
                    continue
                if str(resolution.get("strategy") or "") != "user_supplied":
                    continue
                step_id = str(resolution.get("step_id") or "").strip()
                step = steps.get(step_id)
                if not isinstance(step, dict):
                    continue
                capability_id = str(step.get("capability_id") or "").strip()
                parameter = str(resolution.get("parameter") or "").strip()
                parameter_schema = (
                    schemas.get(capability_id, {})
                    .get("properties", {})
                    .get(parameter, {})
                )
                feedback.append(
                    {
                        "type": "unsupported_user_supplied_provenance",
                        "step_id": step_id,
                        "capability_id": capability_id,
                        "parameter": parameter,
                        "resolution_value": resolution.get("value"),
                        "source_goal_ids": list(
                            resolution.get("source_goal_ids") or []
                        ),
                        "catalog_parameter_schema": parameter_schema,
                        "corrective_contract": (
                            "This value is absent from every cited owning Goal. "
                            "Never borrow a sibling Goal's quantity. If the owning "
                            "Goal omitted this optional parameter, omit the argument "
                            "and resolution, or use the exact catalog default with "
                            "strategy schema_default and no source_goal_ids."
                        ),
                    }
                )
        for obligation in detached_numeric_provenance_obligations(
            raw,
            authoritative_goals=list(authoritative_goals or []),
            error=exc,
        ):
            feedback.append(
                {
                    "type": "missing_user_supplied_parameter_resolution",
                    **obligation,
                    "corrective_contract": (
                        "The semantic mapping already exists in exactly one owned "
                        "step argument. Preserve the plan meaning and add one "
                        "nonblocking parameter_resolution with this exact step_id, "
                        "parameter, numeric value, strategy=user_supplied, and sole "
                        "source Goal. Do not add, remove, or substitute work."
                    ),
                }
            )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[Any, ...]]] = set()
    for item in feedback:
        message = str(item.get("msg") or item.get("message") or "")
        location = tuple(item.get("loc") or [])
        key = (
            message
            or json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
            location,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def deep_plan_validation_errors(
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
    *,
    expected_goal_ids: list[str],
    authoritative_goals: list[dict[str, Any]],
    min_confidence: float,
    min_goal_satisfaction: float,
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
    _, requires_execution = planner_goal_execution_requirements(
        authoritative_goals
    )
    if (
        requires_execution
        and plan.disposition not in {"clarify", "unavailable", "refused"}
        and not plan.steps
    ):
        errors.append(
            {
                "type": "canonical_goal_requires_executable_step",
                "disposition": plan.disposition,
            }
        )
    if plan.coverage == "complete" and plan.confidence < min_confidence:
        errors.append(
            {
                "type": "confidence_below_threshold",
                "confidence": plan.confidence,
                "required": min_confidence,
            }
        )
    if plan.coverage == "complete":
        if plan.goal_satisfaction is None:
            errors.append({"type": "missing_goal_satisfaction"})
        elif (
            plan.disposition != "mixed"
            and plan.goal_satisfaction.score < min_goal_satisfaction
        ):
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
        schema_errors = validate_args_for_schema(
            step.args, capability.get("input_schema") or {}
        )
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
