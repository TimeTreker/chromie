from __future__ import annotations

"""Fast-Planner-specific deterministic qualification and fail-safe mechanics.

This is an implementation layer of the single Planner authority, not another Planner.
"""

import copy
from dataclasses import dataclass, field
from decimal import Decimal
import json
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
    from chromie_contracts.interaction import VOCAL_MODES, VOCAL_PERFORMANCE_CAPABILITY_ID
    from chromie_contracts.plan import CanonicalPlan, FastPlannerAdvanceModelOutput, FastPlannerProgressAct
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
    from shared.chromie_contracts.interaction import VOCAL_MODES, VOCAL_PERFORMANCE_CAPABILITY_ID
    from shared.chromie_contracts.plan import CanonicalPlan, FastPlannerAdvanceModelOutput, FastPlannerProgressAct

from .capabilities.validator import validate_args_for_schema
from .planner_context import first_response_phase_decided, planner_goal_execution_requirements
from .planner_grounding import semantic_numeric_values
from .planner_model_contract import PlannerDTOContractError, PlannerTier
from .planner_validation import parallel_plan_contract_errors, planner_contract_diagnostics
from .prompt_projection import bounded_json


class CapabilityArgumentValidationError(PlannerDTOContractError):
    def __init__(self, feedback: list[dict[str, Any]]) -> None:
        self.feedback = [dict(item) for item in feedback]
        super().__init__(
            json.dumps(
                self.feedback,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


class AuthoritativeGroundingValidationError(ValueError):
    """Fast output contradicts or bypasses immutable Goal grounding."""


def planner_validation_error_items(
    exc: Exception,
    *,
    raw: Any,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> list[dict[str, Any]]:
    if isinstance(exc, CapabilityArgumentValidationError):
        feedback = [dict(item) for item in exc.feedback]
    elif isinstance(exc, ValidationError):
        feedback = list(exc.errors(include_url=False))
    else:
        feedback = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
    feedback.extend(
        planner_contract_diagnostics(
            raw,
            planner_tier=planner_tier,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
    )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[Any, ...]]] = set()
    for item in feedback:
        key = (
            str(item.get("msg") or item.get("message") or ""),
            tuple(item.get("loc") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def planner_validation_error_json(
    exc: Exception,
    *,
    raw: Any,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
    limit: int = 10000,
) -> str:
    from .prompt_projection import bounded_json

    return bounded_json(
        planner_validation_error_items(
            exc,
            raw=raw,
            planner_tier=planner_tier,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        ),
        limit,
    )


@dataclass(frozen=True)
class FastPlanQualification:
    accepted: bool
    plan: CanonicalPlan
    reason: str = ""
    unresolved: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    path_classification: str = "semantic_escalation"


def qualify_fast_canonical_plan(
    plan: CanonicalPlan,
    *,
    capability_payload: list[dict[str, Any]],
    expected_goal_ids_for_turn: list[str],
    authoritative_goals: list[dict[str, Any]],
    evidence_reentry_goal_ids: set[str],
) -> FastPlanQualification:
    allowed = {item["capability_id"]: item for item in capability_payload}
    contract_schema = (
        "FastPlannerMultiGoalPlanOutput"
        if len(expected_goal_ids_for_turn) > 1
        else "FastPlannerModelOutput"
    )
    counts = {
        "authoritative_goal_count": len(expected_goal_ids_for_turn),
        "goal_outcome_count": len(plan.goal_outcomes),
        "executable_step_count": len(plan.steps),
    }

    def reject(
        reason: str,
        *,
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FastPlanQualification:
        return FastPlanQualification(
            accepted=False,
            plan=plan,
            reason=reason,
            unresolved=tuple(unresolved or []),
            metadata={**(metadata or {}), **counts},
        )

    if expected_goal_ids_for_turn and set(plan.goal_ids) != set(expected_goal_ids_for_turn):
        return reject(
            "goal_ids_do_not_match_goal_association",
            metadata={
                "expected_goal_ids": expected_goal_ids_for_turn,
                "actual_goal_ids": list(plan.goal_ids),
            },
        )
    _, requires_execution = planner_goal_execution_requirements(authoritative_goals)
    if evidence_reentry_goal_ids == set(expected_goal_ids_for_turn):
        requires_execution = False
    if (
        requires_execution
        and plan.disposition not in {"escalate", "clarify", "unavailable", "refused"}
        and not plan.steps
    ):
        return reject(
            "canonical_goal_requires_executable_step",
            metadata={"proposed_disposition": plan.disposition},
        )
    if plan.disposition == "escalate":
        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "fast_planner",
                "status": "escalate",
                "authority": "advisory",
                "path_classification": "semantic_escalation",
                "common_capability_count": len(capability_payload),
                "contract_schema": contract_schema,
                "canonical_contract": "CanonicalPlan",
                **counts,
            }
        )
        return FastPlanQualification(True, plan.model_copy(update={"metadata": metadata}))
    if plan.coverage != "complete":
        return reject(
            "coverage_not_complete",
            unresolved=list(plan.unresolved),
            metadata={
                "proposed_coverage": plan.coverage,
                "proposed_confidence": plan.confidence,
            },
        )
    if plan.goal_satisfaction is None or plan.goal_satisfaction.score < 0.95:
        return reject(
            "goal_satisfaction_not_exact",
            unresolved=list(plan.unresolved),
            metadata={
                "proposed_goal_satisfaction": (
                    plan.goal_satisfaction.model_dump(mode="json")
                    if plan.goal_satisfaction
                    else None
                )
            },
        )
    incomplete_outcomes = [
        outcome.goal_id
        for outcome in plan.goal_outcomes
        if outcome.satisfaction is None or outcome.satisfaction.score < 0.95
    ]
    if incomplete_outcomes:
        return reject(
            "per_goal_satisfaction_not_exact",
            unresolved=incomplete_outcomes,
        )
    for step in plan.steps:
        if allowed.get(step.capability_id) is None:
            return reject(
                "step_not_in_executable_common_catalog",
                unresolved=[step.capability_id],
            )
    parallel_errors = parallel_plan_contract_errors(plan, capability_payload)
    if parallel_errors:
        return reject(
            "parallel_execution_contract_unavailable",
            unresolved=[str(item["type"]) for item in parallel_errors],
            metadata={
                "parallel_contract_errors": parallel_errors,
                "execution_allowed": False,
            },
        )
    metadata = dict(plan.metadata)
    metadata.update(
        {
            "resolver": "fast_planner",
            "status": "complete",
            "authority": "advisory",
            "common_capability_count": len(capability_payload),
            "contract_schema": contract_schema,
            "canonical_contract": "CanonicalPlan",
            "path_classification": "terminal",
            **counts,
        }
    )
    return FastPlanQualification(True, plan.model_copy(update={"metadata": metadata}))


def restore_required_capability_args_from_responsibilities(
    raw: dict[str, Any],
    *,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore omitted required args when GI already owns the exact value.

    The model still owns Capability selection. Once it selects a Capability,
    copying an identically named required input from every cited Responsibility
    is mechanical provenance preservation, not a new HOW decision. Conflicting,
    partial, transformed, optional, or defaulted inputs remain model-owned and
    fail through the normal contract boundary.
    """

    activities = raw.get("activities")
    if not isinstance(activities, list):
        return raw, []
    by_ref = {item.local_ref: item for item in responsibilities}
    by_capability = {
        str(item.get("capability_id") or ""): item
        for item in capabilities
        if isinstance(item, dict) and str(item.get("capability_id") or "")
    }
    normalized = copy.deepcopy(raw)
    normalized_activities = normalized.get("activities")
    if not isinstance(normalized_activities, list):
        return raw, []
    repairs: list[dict[str, Any]] = []
    for activity_index, activity in enumerate(normalized_activities):
        if not isinstance(activity, dict) or activity.get("role") != "capability":
            continue
        capability_id = str(activity.get("capability_id") or "")
        definition = by_capability.get(capability_id)
        if not isinstance(definition, dict):
            continue
        input_schema = definition.get("input_schema")
        if not isinstance(input_schema, dict):
            continue
        properties = input_schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        required = [str(item) for item in input_schema.get("required") or []]
        source_refs = [
            str(item)
            for item in activity.get("source_responsibility_refs") or []
            if str(item) in by_ref
        ]
        if not source_refs:
            continue
        args = activity.get("args")
        if not isinstance(args, dict):
            args = {}
        else:
            args = dict(args)
        changed = False
        for parameter in required:
            if parameter in args:
                continue
            parameter_schema = properties.get(parameter)
            if isinstance(parameter_schema, dict) and "default" in parameter_schema:
                continue
            if not all(
                parameter in by_ref[source_ref].bindings
                for source_ref in source_refs
            ):
                continue
            values = [
                by_ref[source_ref].bindings[parameter]
                for source_ref in source_refs
            ]
            first = values[0]
            if any(value != first for value in values[1:]):
                continue
            args[parameter] = copy.deepcopy(first)
            changed = True
            repairs.append(
                {
                    "activity_index": activity_index,
                    "activity_id": str(activity.get("activity_id") or ""),
                    "capability_id": capability_id,
                    "parameter": parameter,
                    "source_responsibility_refs": source_refs,
                    "recovery": "restored_required_arg_from_authoritative_responsibility",
                }
            )
        if changed:
            activity["args"] = args
    return (normalized if repairs else raw), repairs


def validate_fast_advance_output(
    output: FastPlannerAdvanceModelOutput,
    *,
    request: CognitiveWorkRequest,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
) -> None:
    responsibility_refs = [item.local_ref for item in responsibilities]
    if set(output.covered_responsibility_refs) != set(responsibility_refs):
        raise PlannerDTOContractError(
            "Fast Planner must cover exactly the authoritative Responsibility refs"
        )
    by_ref = {item.local_ref: item for item in responsibilities}
    allowed = {item["capability_id"]: item for item in capabilities}
    unresolved_meaning = {
        " ".join(str(item or "").strip().split())
        for item in request.interpretation_unresolved
        if " ".join(str(item or "").strip().split())
    }
    clarification_activities = [
        item for item in output.activities if item.role == "clarification"
    ]
    capability_activities = [
        item for item in output.activities if item.role == "capability"
    ]
    complete_response_activities = [
        item for item in output.activities if item.role == "complete_response"
    ]
    numeric_args_by_ref: dict[str, set[Decimal]] = {
        ref: set() for ref in responsibility_refs
    }
    for activity in capability_activities:
        activity_numbers = semantic_numeric_values(activity.args)
        for source_ref in activity.source_responsibility_refs:
            if source_ref in numeric_args_by_ref:
                numeric_args_by_ref[source_ref].update(activity_numbers)
    for source_ref, source in by_ref.items():
        required_numbers = semantic_numeric_values(source.bindings)
        missing_numbers = sorted(
            required_numbers - numeric_args_by_ref.get(source_ref, set())
        )
        if missing_numbers and any(
            source_ref in activity.source_responsibility_refs
            for activity in capability_activities
        ):
            raise PlannerDTOContractError(
                "Fast Planner Capability args omitted explicit numeric "
                f"Responsibility bindings for {source_ref}: "
                + ",".join(str(value) for value in missing_numbers)
            )
    if output.disposition in {"execute", "respond", "clarify", "mixed"}:
        terminal_roles = {"capability", "complete_response", "clarification"}
        terminal_refs = {
            source_ref
            for activity in output.activities
            if activity.role in terminal_roles
            for source_ref in activity.source_responsibility_refs
        }
        missing_terminal_refs = set(responsibility_refs) - terminal_refs
        if missing_terminal_refs:
            raise PlannerDTOContractError(
                "Fast Planner must supply one terminal Activity for every "
                "authoritative Responsibility before claiming a terminal "
                "disposition; missing="
                + ",".join(sorted(missing_terminal_refs))
            )
    if clarification_activities:
        expected_disposition = "mixed" if capability_activities else "clarify"
        if output.disposition != expected_disposition:
            raise PlannerDTOContractError(
                "clarification disposition must be clarify when it is the only "
                "terminal work, or mixed when independent Capability work proceeds"
            )
        if complete_response_activities and not capability_activities:
            raise PlannerDTOContractError(
                "the current Fast contract cannot combine only response and "
                "clarification outcomes without executable Work"
            )
    all_gap_ids = [
        gap.gap_id
        for activity in clarification_activities
        for gap in activity.information_gaps
    ]
    if len(all_gap_ids) != len(set(all_gap_ids)):
        raise PlannerDTOContractError(
            "Planner InformationGap IDs must be unique across the Activity Plan"
        )
    for activity in output.activities:
        unknown_refs = set(activity.source_responsibility_refs) - set(by_ref)
        if unknown_refs:
            raise PlannerDTOContractError(
                "Fast Planner Activity references unknown Responsibilities: "
                + ",".join(sorted(unknown_refs))
            )
        if activity.role == "clarification":
            if output.disposition not in {"clarify", "mixed"}:
                raise PlannerDTOContractError(
                    "a clarification Activity requires disposition=clarify or mixed"
                )
            for gap in activity.information_gaps:
                if gap.source_kind == "unresolved_meaning":
                    if gap.source_reference not in unresolved_meaning:
                        raise PlannerDTOContractError(
                            "semantic clarification must cite exact GI unresolved "
                            f"meaning: {gap.source_reference!r}"
                        )
                    continue
                definition = allowed.get(gap.source_reference)
                if definition is None:
                    raise PlannerDTOContractError(
                        "execution-input clarification must cite an available "
                        f"Capability ID: {gap.source_reference!r}"
                    )
                input_schema = definition.get("input_schema") or {}
                properties = input_schema.get("properties") or {}
                required = set(input_schema.get("required") or [])
                bound_names = {
                    str(name)
                    for ref in activity.source_responsibility_refs
                    for name in by_ref[ref].bindings
                }
                for parameter in gap.required_for:
                    parameter_schema = properties.get(parameter)
                    if parameter not in required or not isinstance(
                        parameter_schema, dict
                    ):
                        raise PlannerDTOContractError(
                            "execution-input clarification may name only required "
                            f"Capability inputs: {gap.source_reference}.{parameter}"
                        )
                    if "default" in parameter_schema:
                        raise PlannerDTOContractError(
                            "Planner cannot ask for an input with a Capability "
                            f"schema default: {gap.source_reference}.{parameter}"
                        )
                    if parameter in bound_names:
                        raise PlannerDTOContractError(
                            "Planner cannot ask for an already-bound input: "
                            f"{parameter}"
                        )
        if activity.role != "capability":
            continue
        definition = allowed.get(activity.capability_id)
        if definition is None:
            raise PlannerDTOContractError(
                f"unknown or unavailable Capability {activity.capability_id!r}"
            )
        for source_ref in activity.source_responsibility_refs:
            source = by_ref[source_ref]
            if source.output_mode not in set(VOCAL_MODES) - {"speech"}:
                continue
            if (
                activity.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
                or activity.args.get("mode") != source.output_mode
            ):
                raise PlannerDTOContractError(
                    "Fast Planner must preserve a mode-specific vocal "
                    "Responsibility through the exact qualified vocal provider; "
                    f"source_ref={source_ref} expected_capability="
                    f"{VOCAL_PERFORMANCE_CAPABILITY_ID} expected_mode="
                    f"{source.output_mode} actual_capability="
                    f"{activity.capability_id} actual_mode="
                    f"{activity.args.get('mode')!r}. Ordinary speech, media, and "
                    "body Activities are not completion evidence for that mode."
                )
        schema_errors = validate_args_for_schema(
            activity.args,
            definition.get("input_schema") or {},
        )
        if schema_errors:
            raise PlannerDTOContractError(
                json.dumps(
                    {
                        "activity_id": activity.activity_id,
                        "capability_id": activity.capability_id,
                        "invalid_args": schema_errors[:8],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        input_schema = definition.get("input_schema") or {}
        properties = input_schema.get("properties") or {}
        required_inputs = set(input_schema.get("required") or [])
        authoritative_bindings = {
            str(name): value
            for ref in activity.source_responsibility_refs
            for name, value in by_ref[ref].bindings.items()
        }
        for parameter in sorted(required_inputs):
            parameter_schema = properties.get(parameter)
            if not isinstance(parameter_schema, dict):
                continue
            if "default" in parameter_schema:
                continue
            if parameter not in authoritative_bindings:
                raise AuthoritativeGroundingValidationError(
                    "Fast Planner cannot invent an unbound required Capability "
                    f"input before canonical Goal grounding: "
                    f"{activity.capability_id}.{parameter}"
                )
            actual = activity.args.get(parameter)
            expected = authoritative_bindings[parameter]
            if actual != expected and str(actual).strip() != str(expected).strip():
                raise AuthoritativeGroundingValidationError(
                    "Fast Planner required Capability input contradicts GI "
                    f"binding: {activity.capability_id}.{parameter}"
                )


def capability_argument_errors(
    plan: CanonicalPlan,
    capability_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    allowed = {item["capability_id"]: item for item in capability_payload}
    errors: list[dict[str, Any]] = []
    for step in plan.steps:
        capability = allowed.get(step.capability_id)
        if capability is None:
            continue
        schema_errors = validate_args_for_schema(
            step.args,
            capability.get("input_schema") or {},
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
    return errors


def validate_work_reuse_selection(
    output: Any,
    *,
    context: dict[str, Any] | None,
) -> None:
    """Validate explicit Planner reuse references without choosing reuse.

    Fast Planner owns the semantic decision by either citing a supplied
    provisional Activity ID or omitting it. This check is deliberately
    mechanical: cited IDs must exist and the selected step must preserve
    the Activity's immutable Capability, arguments, and timing. The Host
    later validates canonical Goal ownership and live runtime state.
    """

    raw_activities = (context or {}).get(
        "existing_work_activities"
    )
    activities = (
        [item for item in raw_activities if isinstance(item, dict)]
        if isinstance(raw_activities, list)
        else []
    )
    by_id = {
        str(item.get("activity_id") or "").strip(): item
        for item in activities
        if str(item.get("activity_id") or "").strip()
    }
    cited: set[str] = set()
    for step in output.steps:
        activity_id = str(step.reuse_activity_id or "").strip()
        if not activity_id:
            continue
        if activity_id in cited:
            raise PlannerDTOContractError(
                f"reuse_activity_id is duplicated: {activity_id}"
            )
        cited.add(activity_id)
        activity = by_id.get(activity_id)
        if activity is None:
            raise PlannerDTOContractError(
                f"reuse_activity_id was not supplied by Runtime: {activity_id}"
            )
        if step.capability_id != str(activity.get("capability_id") or ""):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes capability_id"
            )
        if step.args != dict(activity.get("args") or {}):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes immutable args"
            )
        if step.timing != str(activity.get("timing") or "sequential"):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes timing"
            )

    # The supplied reconciliation projection is one bounded snapshot.
    # Reusing any member currently requires selecting every member; extra
    # newly planned steps remain legal and execute beside the reused set.
    if cited and cited != set(by_id):
        raise PlannerDTOContractError(
            "Work reuse must select the complete supplied "
            "Activity set"
        )
    if cited and any(
        by_id[activity_id].get("origin") == "retained_runtime"
        for activity_id in cited
    ) and len(output.steps) != len(cited):
        raise PlannerDTOContractError(
            "retained Runtime Work reuse cannot add steps to the "
            "reconciliation-only Plan"
        )


def validated_fail_safe_progress(
    raw_output: Any,
    *,
    responsibility_refs: list[str],
) -> list[FastPlannerProgressAct]:
    """Retain independently valid, non-terminal progress from an invalid Plan.

    Progress carries no result, completion, Capability, or execution claim.  The
    invalid Plan wrapper and every terminal Activity remain discarded.  Exact
    duplicates are collapsed so one malformed model response cannot schedule
    repeated audible acknowledgements.
    """

    if not isinstance(raw_output, dict):
        return []
    allowed_refs = set(responsibility_refs)
    retained: list[FastPlannerProgressAct] = []
    seen: set[tuple[Any, ...]] = set()
    for candidate in raw_output.get("activities") or []:
        if not isinstance(candidate, dict) or candidate.get("role") != "progress":
            continue
        try:
            activity = FastPlannerProgressAct.model_validate(candidate)
        except ValidationError:
            continue
        refs = set(activity.source_responsibility_refs)
        if not refs or not refs.issubset(allowed_refs):
            continue
        key = (
            activity.progress_kind,
            activity.speech_act,
            activity.text,
            activity.timing,
            tuple(sorted(refs)),
        )
        if key in seen:
            continue
        seen.add(key)
        retained.append(activity)
    return retained
