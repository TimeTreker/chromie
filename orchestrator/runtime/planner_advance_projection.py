"""Projection of a Planner advance onto Goal Association's canonical Goals.

Pure functions that bind the Planner's first Activity Plan to the canonical
Goals, reuse safe Capability work it already started and validate retained
Work changes. They hold no runtime state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
)
from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
)
from shared.chromie_contracts.plan import (
    argument_source_span,
    communication_need_id,
    SocialCommunicationNeed,
    CanonicalPlan,
    CanonicalPlanStep,
    PlanParameterResolution,
    ClarifyGoalPlanOutcome,
    ExecuteGoalPlanOutcome,
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerSituationArgumentSource,
    GoalSatisfactionAssessment,
    PlannerInformationGap,
    RespondGoalPlanOutcome,
    UnavailableGoalPlanOutcome,
)
from shared.chromie_contracts.user_turn import (
    resolve_user_turn_source_span,
)



def association_goal_ids(association: GoalAssociationResolution) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = " ".join(str(value or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)

    for item in association.associations:
        for goal_id in item.target_goal_ids:
            add(goal_id)
    for goal in association.new_goals:
        add(goal.goal_id)
    return ordered


def goal_ids_by_responsibility(
    association: GoalAssociationResolution,
) -> dict[str, list[str]]:
    """Resolve the GA-owned Goal identity for every UMI Responsibility.

    The Planner is allowed to plan before Goal Association finishes, so its
    Activities carry UMI-local Responsibility references.  This is the single
    deterministic join from those references to GA's canonical Goal IDs.
    It never guesses a missing mapping.
    """

    mapped: dict[str, list[str]] = {}

    def bind(responsibility_ref: str, goal_ids: list[str]) -> None:
        ref = " ".join(str(responsibility_ref or "").strip().split())
        normalized = [
            goal_id
            for value in goal_ids
            if (goal_id := " ".join(str(value or "").strip().split()))
        ]
        if not ref or not normalized:
            return
        current = mapped.setdefault(ref, [])
        for goal_id in normalized:
            if goal_id not in current:
                current.append(goal_id)

    for item in association.associations:
        for responsibility_ref in item.source_responsibility_refs:
            bind(responsibility_ref, item.target_goal_ids)
    for goal in association.new_goals:
        if not goal.goal_id:
            continue
        for responsibility_ref in goal.source_responsibility_refs:
            bind(responsibility_ref, [goal.goal_id])
    return mapped


def planner_gaps_by_goal_id(
    *,
    advance: FastPlannerAdvance,
    association: GoalAssociationResolution,
) -> dict[str, list[PlannerInformationGap]]:
    """Join Planner gap ownership to GA Goal identity without interpreting it."""

    refs_to_goals = goal_ids_by_responsibility(association)
    by_goal: dict[str, list[PlannerInformationGap]] = {}
    seen_by_goal: dict[str, set[str]] = {}
    for activity in advance.activities:
        if activity.role != "clarification":
            continue
        target_goal_ids = [
            goal_id
            for ref in activity.source_responsibility_refs
            for goal_id in refs_to_goals.get(ref, [])
        ]
        for goal_id in target_goal_ids:
            seen = seen_by_goal.setdefault(goal_id, set())
            target = by_goal.setdefault(goal_id, [])
            for gap in activity.information_gaps:
                if gap.gap_id in seen:
                    continue
                seen.add(gap.gap_id)
                target.append(gap)
    return by_goal


def canonical_plan_from_fast_advance(
    *,
    advance: FastPlannerAdvance,
    association: GoalAssociationResolution,
    user_text: str,
    retained_goals: list[dict[str, Any]] | None = None,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
) -> CanonicalPlan:
    """Bind the Planner's first Activity Plan to GA's canonical Goals."""

    refs_to_goals = goal_ids_by_responsibility(association)
    missing_refs = sorted(
        set(advance.covered_responsibility_refs) - set(refs_to_goals)
    )
    if missing_refs:
        raise ValueError(
            "Goal Association omitted Planner Responsibility mappings: "
            + ",".join(missing_refs)
        )

    goal_ids = association_goal_ids(association)
    has_argument_sources = any(
        isinstance(activity, FastPlannerCapabilityActivity) and activity.argument_sources
        for activity in advance.activities
    )
    if retained_goals is not None and has_argument_sources:
        consistent_retained_ids: set[str] = set()
        for snapshot in retained_goals:
            if not isinstance(snapshot, dict):
                continue
            snapshot_id = str(snapshot.get("goal_id") or "").strip()
            for key in ("goal", "semantic_goal"):
                goal_payload = snapshot.get(key)
                if (
                    snapshot_id
                    and isinstance(goal_payload, dict)
                    and str(goal_payload.get("goal_id") or "").strip() == snapshot_id
                ):
                    consistent_retained_ids.add(snapshot_id)
                    break
        new_goal_ids = {goal.goal_id for goal in association.new_goals}
        missing_retained = sorted(set(goal_ids) - new_goal_ids - consistent_retained_ids)
        if missing_retained:
            raise ValueError(
                "Fast argument source has no exact canonical Goal owner: inconsistent retained Goal snapshot: "
                + ",".join(missing_retained)
            )
    activities_by_goal: dict[str, list[Any]] = {
        goal_id: [] for goal_id in goal_ids
    }
    steps: list[CanonicalPlanStep] = []
    deferred_steps: list[CanonicalPlanStep] = []
    # Start-together groups come from the Fast Host (Planner depends_on + Capability
    # contracts). Without them Runtime serializes in list order; it never infers overlap.
    capability_ids = [
        item.activity_id for item in advance.activities
        if isinstance(item, FastPlannerCapabilityActivity) and not item.deferred
    ]
    raw_groups = advance.metadata.get("execution_groups")
    execution_groups = (
        [[str(item) for item in group] for group in raw_groups]
        if isinstance(raw_groups, list)
        and sorted(str(item) for group in raw_groups for item in group) == sorted(capability_ids)
        else [[activity_id] for activity_id in capability_ids]
    )
    group_of = {
        activity_id: index for index, group in enumerate(execution_groups) for activity_id in group
    }
    for activity in advance.activities:
        activity_goal_ids: list[str] = []
        for responsibility_ref in activity.source_responsibility_refs:
            for goal_id in refs_to_goals[responsibility_ref]:
                if goal_id not in activity_goal_ids:
                    activity_goal_ids.append(goal_id)
        for goal_id in activity_goal_ids:
            activities_by_goal[goal_id].append(activity)
        if isinstance(activity, FastPlannerCapabilityActivity) and activity.deferred:
            # Held for the evidence re-entry (owner choice B): never an executable step.
            deferred_steps.append(CanonicalPlanStep(
                step_id=activity.activity_id, capability_id=activity.capability_id,
                args=dict(activity.args), step_purpose="achieve_effect",
                source_goal_ids=activity_goal_ids, reason_summary=activity.reason_summary,
                metadata={
                    "fast_activity_id": activity.activity_id,
                    "source_responsibility_refs": list(activity.source_responsibility_refs),
                    "depends_on": list(activity.depends_on),
                    "deferred": True,
                },
            ))
        elif isinstance(activity, FastPlannerCapabilityActivity):
            steps.append(
                CanonicalPlanStep(
                    step_id=activity.activity_id,
                    capability_id=activity.capability_id,
                    args=dict(activity.args),
                    timing=(
                        "parallel"
                        if len(execution_groups[group_of[activity.activity_id]]) > 1
                        else "sequential"
                    ),
                    step_purpose=activity.step_purpose,
                    expected_outcome=activity.expected_outcome,
                    source_goal_ids=activity_goal_ids,
                    reason_summary=activity.reason_summary,
                    metadata={
                        "fast_activity_id": activity.activity_id,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "task_list_revision": 1,
                        "depends_on": list(activity.depends_on),
                        "execution_group": group_of[activity.activity_id],
                    },
                )
            )
    # Contiguous steps per group, groups in dependency-wave order.
    steps.sort(key=lambda step: group_of[step.step_id])

    outcomes_by_ref = {item.local_ref: item.outcome for item in responsibilities or []}
    def argument_source_text(span: Any, owner_refs: list[str]) -> str:
        ref = getattr(span, "source_responsibility_ref", None)
        if ref is None:
            return user_text
        if ref not in outcomes_by_ref or ref not in owner_refs:
            raise ValueError("Fast argument source has no exact accepted Responsibility owner")
        return outcomes_by_ref[ref]

    parameter_resolutions = [
        PlanParameterResolution(
            step_id=activity.activity_id, parameter=parameter,
            strategy="observed_context", value=activity.args[parameter],
            rationale=f"situation_interpretation_ref={span.situation_interpretation_ref}",
            confidence=advance.confidence,
            source_goal_ids=list(dict.fromkeys(
                goal_id for ref in activity.source_responsibility_refs
                for goal_id in refs_to_goals[ref]
            )),
        )
        if isinstance(span, FastPlannerSituationArgumentSource) else
        PlanParameterResolution(
            step_id=activity.activity_id, parameter=parameter,
            strategy="semantic_realization", value=activity.args[parameter],
            source_quote=resolve_user_turn_source_span(
                argument_source_text(span, activity.source_responsibility_refs), argument_source_span(span),
            ),
            confidence=advance.confidence,
            source_goal_ids=list(dict.fromkeys(
                goal_id for ref in (
                    [span.source_responsibility_ref]
                    if getattr(span, "source_responsibility_ref", None) is not None
                    else activity.source_responsibility_refs
                )
                for goal_id in refs_to_goals[ref]
            )),
        )
        for activity in advance.activities if isinstance(activity, FastPlannerCapabilityActivity)
        for parameter, span in activity.argument_sources.items()
    ]
    if any(not item.source_goal_ids for item in parameter_resolutions):
        raise ValueError("Fast argument source has no canonical Goal owner")

    outcomes: list[Any] = []
    unresolved = list(advance.unresolved)
    plan_seed = json.dumps(advance.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    plan_id = "fast_activity_plan_" + hashlib.sha256(plan_seed.encode()).hexdigest()[:20]
    needs: list[SocialCommunicationNeed] = []
    capability_indexes = [index for index, item in enumerate(advance.activities) if item.role == "capability"]
    for index, activity in enumerate(advance.activities):
        # An unavailable Goal's result need is bound from its outcome below.
        if activity.role in {"capability", "unavailable"}:
            continue
        activity_goal_ids = list(dict.fromkeys(goal_id for ref in activity.source_responsibility_refs
                                               for goal_id in refs_to_goals[ref]))
        # This preserves the validated ordered Work obligation. SC supplies
        # words later without moving that obligation across task Activities.
        # The Planner activity_id names Work and already lives in need_id and
        # step order; under SC's own act-identity key it invited SC to author
        # delivered words again as a "new" act.
        phase = ("final" if capability_indexes and index > max(capability_indexes)
                 else "immediate" if capability_indexes and index > min(capability_indexes)
                 else "pre_action" if capability_indexes else "immediate") if activity.timing == "sequential" else "immediate"
        needs.append(SocialCommunicationNeed(
            need_id=communication_need_id(plan_id, activity.activity_id), owner="planner",
            kind="input" if activity.role == "clarification" else "answer",
            source_goal_ids=activity_goal_ids, source_responsibility_refs=list(activity.source_responsibility_refs),
            reference_id=plan_id, delivery_phase=phase,
            facts=activity.model_dump(mode="json", exclude={"activity_id"}),
            before_step_ids=[item.activity_id for item in advance.activities[index+1:] if item.role == "capability"] if activity.timing == "sequential" else [],
            after_step_ids=[item.activity_id for item in advance.activities[:index] if item.role == "capability"] if activity.timing == "sequential" else [],
        ))
    for goal_id in goal_ids:
        goal_activities = activities_by_goal.get(goal_id, [])
        goal_steps = [
            step.step_id for step in steps if goal_id in step.source_goal_ids
        ]
        clarifications = [
            activity
            for activity in goal_activities
            if activity.role == "clarification"
        ]
        responses = [
            activity
            for activity in goal_activities
            if activity.role == "complete_response"
        ]
        limitations = [
            activity
            for activity in goal_activities
            if activity.role == "unavailable"
        ]
        if goal_steps:
            acquisition_steps = [
                step.step_id for step in steps
                if goal_id in step.source_goal_ids
                and step.step_purpose == "acquire_information"
            ]
            if acquisition_steps:
                # The Planner's typed deferred requirement names what the re-entry
                # still owes (for example a conditional action); otherwise the answer.
                deferred = list(dict.fromkeys(
                    activity.deferred_requirement for activity in goal_activities
                    if isinstance(activity, FastPlannerCapabilityActivity)
                    and activity.deferred_requirement
                ))
                satisfaction = GoalSatisfactionAssessment(
                    score=min(0.5, advance.confidence),
                    status="partial",
                    satisfied_goal_ids=[],
                    unmet_goal_ids=[goal_id],
                    unmet_requirements=deferred or [
                        "Interpret the acquired Evidence and complete the remaining "
                        "user-facing information obligation."
                    ],
                    rationale=(
                        "The Planner supplied information-acquisition Work; acquisition "
                        "alone is not terminal Responsibility fulfillment."
                    ),
                )
            else:
                satisfaction = GoalSatisfactionAssessment(
                    score=max(0.95, advance.confidence),
                    status="exact",
                    satisfied_goal_ids=[goal_id],
                    rationale="The Planner supplied executable Activities for this Goal.",
                )
            outcomes.append(
                ExecuteGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="execute",
                    coverage="complete",
                    step_ids=goal_steps,
                    satisfaction=satisfaction,
                    rationale=(
                        "Runtime acquisition Evidence and subsequent cognition remain required."
                        if acquisition_steps
                        else "Runtime execution and Evidence remain required."
                    ),
                )
            )
        elif clarifications:
            outcomes.append(
                ClarifyGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="clarify",
                    coverage="uncertain",
                    unresolved=(unresolved or ["user_clarification_required"]),
                    rationale=(
                        "A source-proven Planner InformationGap blocks this Goal's Work."
                    ),
                )
            )
        elif responses:
            satisfaction = GoalSatisfactionAssessment(
                score=max(0.95, advance.confidence),
                status="exact",
                satisfied_goal_ids=[goal_id],
                rationale="The Planner established an ordinary answer obligation.",
            )
            outcomes.append(
                RespondGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="respond",
                    coverage="complete",
                    satisfaction=satisfaction,
                    rationale="No Capability Evidence is required for this Goal.",
                )
            )
        elif limitations:
            outcomes.append(
                UnavailableGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="unavailable",
                    coverage="uncertain",
                    unresolved=list(dict.fromkeys(
                        item for activity in limitations for item in activity.missing
                    )),
                    rationale="The Planner found no currently available way to satisfy this Goal.",
                )
            )
        elif advance.disposition == "unavailable":
            outcomes.append(
                UnavailableGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="unavailable",
                    coverage=advance.coverage,
                    unresolved=unresolved,
                    rationale=(
                        advance.reason_summary
                        or "The Planner found no currently available way to satisfy this Goal."
                    ),
                )
            )
        else:
            raise ValueError(
                f"The Planner supplied no terminal Activity for Goal {goal_id!r}"
            )

    for outcome in outcomes:
        if outcome.disposition in {"unavailable", "refused"}:
            needs.append(SocialCommunicationNeed(
                need_id=communication_need_id(plan_id, outcome.goal_id),
                owner="planner", kind="result", reference_id=plan_id,
                source_goal_ids=[outcome.goal_id],
                source_responsibility_refs=[
                    ref for ref, ids in refs_to_goals.items() if outcome.goal_id in ids
                ],
                facts=outcome.model_dump(mode="json", exclude_none=True),
            ))
    dispositions = {item.disposition for item in outcomes}
    disposition = (
        next(iter(dispositions)) if len(dispositions) == 1 else "mixed"
    )
    top_coverage = (
        advance.coverage
        if disposition in {"clarify", "unavailable", "refused"}
        else "complete"
    )
    plan_seed = json.dumps(
        advance.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    global_satisfaction = None
    if dispositions.issubset({"execute", "respond"}):
        acquisition_goal_ids = {
            goal_id
            for step in steps if step.step_purpose == "acquire_information"
            for goal_id in step.source_goal_ids
        }
        if acquisition_goal_ids:
            global_satisfaction = GoalSatisfactionAssessment(
                score=min(0.5, advance.confidence),
                status="partial",
                satisfied_goal_ids=[
                    goal_id for goal_id in goal_ids
                    if goal_id not in acquisition_goal_ids
                ],
                unmet_goal_ids=[
                    goal_id for goal_id in goal_ids
                    if goal_id in acquisition_goal_ids
                ],
                unmet_requirements=[
                    "Information-acquisition Work must re-enter Planner with trusted "
                    "Evidence before the information Responsibility can be completed."
                ],
                rationale=(
                    "The current Plan completes acquisition Work but retains the "
                    "remaining information-delivery obligation."
                ),
            )
        else:
            global_satisfaction = GoalSatisfactionAssessment(
                score=max(0.95, advance.confidence),
                status="exact",
                satisfied_goal_ids=goal_ids,
                rationale="Every canonical Goal has a complete Planner outcome.",
            )
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="fast",
        disposition=disposition,
        coverage=top_coverage,
        confidence=advance.confidence,
        goal_ids=goal_ids,
        goal_summary=user_text,
        communication_needs=needs,
        parameter_resolutions=parameter_resolutions,
        steps=steps,
        deferred_steps=deferred_steps,
        unresolved=(
            unresolved
            if disposition in {"clarify", "mixed", "unavailable", "refused"}
            else []
        ),
        goal_outcomes=outcomes,
        goal_satisfaction=global_satisfaction,
        metadata={
            "resolver": "fast_planner_advance",
            "path_classification": "terminal",
            "plan_relation": "exact",
            "task_list_revision": 1,
            "goal_grouped_task_list": True,
            "goal_ids_by_responsibility": refs_to_goals,
        },
    )


def canonical_plan_reusing_fast_capability_execution(
    *,
    execution: Any,
    plan: CanonicalPlan,
    association: GoalAssociationResolution,
) -> CanonicalPlan | None:
    """Prove exact plan-level reuse without making a semantic judgment.

    The Planner owns whether the canonical Goal still needs the provisional
    Work by explicitly citing stable Activity IDs. The Host may reuse
    already-started safe Work when a selected Activity's exact identity matches.
    Omitted Activities continue unchanged; cancellation must be explicit.
    Extra newly planned steps are allowed.
    """

    activities = list(getattr(execution, "activities", []) or [])
    if (
        plan.disposition not in {"execute", "mixed"}
        or not activities
    ):
        return None
    refs_to_goals = goal_ids_by_responsibility(association)
    updated_steps = list(plan.steps)
    matched_step_indexes: set[int] = set()
    for activity in activities:
        activity_goal_ids = list(
            dict.fromkeys(
                goal_id
                for responsibility_ref in activity.source_responsibility_refs
                for goal_id in refs_to_goals.get(responsibility_ref, [])
            )
        )
        if not activity_goal_ids:
            return None
        candidates = [
            index
            for index, step in enumerate(plan.steps)
            if index not in matched_step_indexes
            and step.reuse_activity_id == activity.activity_id
            and step.capability_id == activity.capability_id
            and step.args == activity.args
            and len(step.source_goal_ids) == len(activity_goal_ids)
            and set(step.source_goal_ids) == set(activity_goal_ids)
        ]
        if not candidates and activity.activity_id not in {step.reuse_activity_id for step in plan.steps}:
            continue
        if len(candidates) != 1:
            raise ValueError("Planner reuse changes provisional Work identity")
        index = candidates[0]
        matched_step_indexes.add(index)
        step = plan.steps[index]
        updated_steps[index] = step.model_copy(
            deep=True,
            update={
                "metadata": {
                    **step.metadata,
                    "fast_activity_id": activity.activity_id,
                    "source_responsibility_refs": list(
                        activity.source_responsibility_refs
                    ),
                    "task_list_revision": int(
                        plan.metadata.get("task_list_revision") or 1
                    ),
                }
            },
        )
    return plan.model_copy(deep=True, update={"steps": updated_steps})


def retained_existing_work_activities(
    *,
    context: dict[str, Any],
    goal_ids: set[str],
) -> list[dict[str, Any]]:
    """Project still-owned retained Work for Planner comparison.

    Conversation State supplies the trusted bounded task snapshot. This
    projection adds no semantic judgment: it includes only request IDs still
    listed as remaining for the canonical Goals in scope.
    """

    by_activity_id: dict[str, dict[str, Any]] = {}
    snapshots = context.get("active_task_snapshots")
    if not isinstance(snapshots, list):
        return []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        semantic_goal = snapshot.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            continue
        goal_id = str(semantic_goal.get("goal_id") or "").strip()
        if not goal_id or goal_id not in goal_ids:
            continue
        metadata = snapshot.get("metadata")
        binding = (
            metadata.get("execution_binding")
            if isinstance(metadata, dict)
            else None
        )
        if not isinstance(binding, dict):
            continue
        remaining = {
            str(item).strip()
            for item in binding.get("remaining_request_ids") or []
            if str(item).strip()
        }
        if not remaining:
            continue
        interaction_id = str(binding.get("interaction_id") or "").strip()
        plan_id = str(binding.get("canonical_plan_id") or "").strip()
        fingerprint = str(
            binding.get("canonical_plan_fingerprint") or ""
        ).strip()
        if not interaction_id or not plan_id or not fingerprint:
            continue
        for item in binding.get("planned_capabilities") or []:
            if not isinstance(item, dict):
                continue
            request_id = str(item.get("request_id") or "").strip()
            capability_id = str(item.get("capability_id") or "").strip()
            if request_id not in remaining or not capability_id:
                continue
            existing = by_activity_id.get(request_id)
            source_goal_ids = list(
                dict.fromkeys(
                    [
                        *(
                            existing.get("source_goal_ids", [])
                            if existing is not None
                            else []
                        ),
                        *(
                            item.get("source_goal_ids")
                            if isinstance(item.get("source_goal_ids"), list)
                            else []
                        ),
                        goal_id,
                    ]
                )
            )
            activity = {
                "activity_id": request_id,
                "origin": "retained_runtime",
                "capability_id": capability_id,
                "args": dict(item.get("args") or {}),
                "timing": str(item.get("timing") or "sequential"),
                "source_goal_ids": source_goal_ids,
                "runtime_binding": {
                    "interaction_id": interaction_id,
                    "canonical_plan_id": plan_id,
                    "canonical_plan_fingerprint": fingerprint,
                },
                "state": str(
                    (binding.get("request_statuses") or {}).get(request_id)
                    or snapshot.get("status")
                    or "scheduled"
                ),
            }
            if existing is not None and any(
                existing.get(key) != activity.get(key)
                for key in ("capability_id", "args", "timing", "runtime_binding")
            ):
                raise ValueError(
                    "retained Work identity conflicts across Goal snapshots: "
                    + request_id
                )
            by_activity_id[request_id] = activity
    return list(by_activity_id.values())


def validate_work_change_selection(plan: CanonicalPlan, activities: list[dict[str, Any]]) -> None:
    by_id = {str(item.get("activity_id") or ""): item for item in activities}
    if len(by_id) != len(activities):
        raise ValueError("ambiguous existing Work identity")
    if set(plan.cancel_activity_ids) - set(by_id):
        raise ValueError("Planner cancellation names unknown Work")
    for step in plan.steps:
        if not step.reuse_activity_id:
            continue
        activity = by_id.get(step.reuse_activity_id)
        if activity is None:
            raise ValueError("Planner reuse names unknown Work")
        # Identity is what the Work does; its timing is derived scheduling.
        if any(getattr(step, key) != activity.get(key) for key in ("capability_id", "args")):
            raise ValueError("Planner reuse changes immutable Work identity")
        if set(step.source_goal_ids) != set(activity.get("source_goal_ids") or []):
            raise ValueError("Planner reuse changes shared Work Goal ownership")
    for activity_id in plan.cancel_activity_ids:
        if not set(by_id[activity_id].get("source_goal_ids") or []).issubset(plan.goal_ids):
            raise ValueError("Planner cancellation exceeds shared Work Goal ownership")
