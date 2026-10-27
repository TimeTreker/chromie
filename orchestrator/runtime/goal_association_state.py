"""Goal Association and semantic Task operations for ConversationStateManager.

The functions take the ``ConversationStateManager`` as ``state`` and commit a
validated Goal Association, Planner information gaps or semantic Task
operations as one state transaction.
"""

from __future__ import annotations

import copy
import logging
from collections import deque
from typing import Any, Callable

from pydantic import ValidationError

from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
    stable_goal_operation_id,
)
from shared.chromie_contracts.plan import PlannerInformationGap
from shared.chromie_contracts.semantic_task import (
    SemanticGoal,
    apply_goal_meaning_update,
    SemanticTaskOperation,
)

from orchestrator.runtime.conversation_state import _now_ms

logger = logging.getLogger("chromie.orchestrator.conversation_state")


def semantic_operations_from_metadata(
    metadata: dict[str, Any] | None,
) -> list[SemanticTaskOperation]:
    if not isinstance(metadata, dict):
        return []
    raw = (
        metadata.get("semantic_task_operations")
        or metadata.get("task_operations")
        or metadata.get("semantic_task_operation")
    )
    if raw is None:
        return []
    if isinstance(raw, dict):
        if isinstance(raw.get("operations"), list):
            raw = raw["operations"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    operations: list[SemanticTaskOperation] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            operations.append(SemanticTaskOperation.model_validate(item))
        except ValidationError as exc:
            logger.warning(
                "Ignoring malformed semantic task operation from turn metadata error=%s",
                exc,
            )
            continue
    return operations


def context_has_operation_id(
    context: dict[str, Any],
    operation_id: str,
) -> bool:
    history = context.get("operation_history")
    if not isinstance(history, list):
        return False
    return any(
        isinstance(item, dict)
        and str(item.get("operation_id") or "") == operation_id
        for item in history
    )


def context_by_operation_id(
    state: Any,
    operation_id: str,
) -> dict[str, Any] | None:
    if not operation_id:
        return None
    for context in reversed(state._task_contexts):
        if context_has_operation_id(context, operation_id):
            return context
    return None


def new_semantic_task_context(
    state: Any,
    *,
    sid: str | None,
    operation: SemanticTaskOperation,
    user_text: str,
    source: str | None,
) -> dict[str, Any]:
    if operation.goal is None:
        raise ValueError(
            "create semantic operation requires a goal before state mutation"
        )
    now = _now_ms()
    task_id = state._new_task_id()
    goal = operation.goal.model_copy(
        update={
            "goal_id": operation.goal.goal_id or task_id,
            "version": 1,
            "source_text": operation.goal.source_text or user_text,
        }
    )
    status = operation.status_update or (
        "waiting_for_user"
        if any(gap.blocking and gap.preferred_resolution == "ask_user" for gap in operation.information_gaps)
        else "planning"
    )
    commitment = operation.commitment_state or (
        "waiting_for_user" if status == "waiting_for_user" else "evaluating"
    )
    context = {
        "task_id": task_id,
        "conversation_id": state.conversation_id,
        "status": status,
        "task_relation": "new_task",
        "task_type": str((operation.metadata or {}).get("task_type") or "conversation"),
        "goal": state._compact_text(goal.description, limit=220),
        "semantic_goal": goal.model_dump(mode="json", exclude_none=True),
        "goal_version": 1,
        "plan_version": 0,
        "plan_status": "not_planned",
        "commitment_state": commitment,
        "important_claims": [],
        "entities": [],
        "constraints": dict(goal.constraints),
        "pending_questions": [gap.description for gap in operation.information_gaps if gap.blocking],
        "open_information_gaps": [
            gap.model_dump(mode="json", exclude_none=True)
            for gap in operation.information_gaps
            if not gap.resolved
        ],
        "operation_history": [
            {
                "operation_id": operation.operation_id,
                "operation": operation.operation,
                "goal_version": 1,
                "ts_ms": now,
                "reason_summary": operation.reason_summary,
            }
        ],
        "last_meaningful_user_turn": state._compact_text(user_text, limit=220),
        "last_assistant_response": None,
        "related_sids": [sid] if sid else [],
        "created_ms": now,
        "updated_ms": now,
        "persistence_policy": str((operation.metadata or {}).get("persistence_policy") or "persist_if_unfinished"),
        "confirmation": None,
        "evidence_summary": {},
        "metadata": {
            "source": source,
            "semantic_operation_id": operation.operation_id,
            "semantic_operation_confidence": operation.confidence,
            "semantic_relationship": operation.relationship,
        },
    }
    state._task_contexts.append(context)
    return context


def merge_semantic_goal(
    goal: SemanticGoal,
    operation: SemanticTaskOperation,
    *,
    user_text: str,
) -> SemanticGoal:
    update = dict(operation.goal_update or {})
    if "base_goal_fingerprint" in update:
        revised = apply_goal_meaning_update(goal, update)
        if goal.responsibility_status == "satisfied":
            revised = revised.model_copy(update={"responsibility_status": "open"})
        return revised
    if operation.goal is not None:
        replacement = operation.goal
        update = {
            "description": replacement.description,
            "source_text": replacement.source_text,
            "beneficiary": replacement.beneficiary,
            "object": replacement.object,
            "constraints": replacement.constraints,
            "success_criteria": replacement.success_criteria,
            "metadata": replacement.metadata,
            **update,
        }

    constraints = dict(goal.constraints)
    replacement_constraints = update.get("constraints")
    if isinstance(replacement_constraints, dict):
        constraints = dict(replacement_constraints)
    constraint_updates = update.get("constraint_updates")
    if isinstance(constraint_updates, dict):
        constraints.update(constraint_updates)
    removals = update.get("constraint_removals")
    if isinstance(removals, list):
        for key in removals:
            constraints.pop(str(key), None)

    object_value = dict(goal.object)
    replacement_object = update.get("object")
    if isinstance(replacement_object, dict):
        object_value = replacement_object
    object_updates = update.get("object_updates")
    if isinstance(object_updates, dict):
        object_value.update(object_updates)

    criteria = update.get("success_criteria", goal.success_criteria)
    metadata = dict(goal.metadata)
    update_metadata = update.get("metadata")
    if isinstance(update_metadata, dict):
        metadata.update(update_metadata)

    version = goal.version + 1
    responsibility_status = (
        "open"
        if goal.responsibility_status == "satisfied"
        and operation.operation in {"modify", "clarification_answer", "correct"}
        else goal.responsibility_status
    )
    return SemanticGoal.model_validate({
        **goal.model_dump(mode="json"),
        "goal_id": goal.goal_id,
        "version": version,
        "responsibility_status": responsibility_status,
        "description": str(update.get("description") or goal.description),
        "source_text": str(update.get("source_text") or goal.source_text),
        "beneficiary": str(update["beneficiary"]) if update.get("beneficiary") is not None else goal.beneficiary,
        "object": object_value,
        "constraints": constraints,
        "success_criteria": criteria,
        "metadata": metadata,
    })


def apply_semantic_operation_to_context(
    state: Any,
    context: dict[str, Any],
    operation: SemanticTaskOperation,
    *,
    sid: str | None,
    user_text: str,
    source: str | None,
) -> dict[str, Any]:
    now = _now_ms()
    previous_work_status = str(context.get("status") or "open")
    previous_commitment_state = str(context.get("commitment_state") or "none")
    previous_plan_status = str(context.get("plan_status") or "not_planned")
    result: dict[str, Any] = {
        "operation_id": operation.operation_id,
        "operation": operation.operation,
        "task_id": context.get("task_id"),
        "applied": False,
    }
    if context_has_operation_id(context, operation.operation_id):
        result.update(
            {
                "replayed": True,
                "reason": "operation_already_applied",
                "goal_version": int(context.get("goal_version") or 1),
                "plan_version": int(context.get("plan_version") or 0),
                "status": context.get("status"),
            }
        )
        return result

    responsibility_status = state._goal_responsibility_status(context)
    if (
        responsibility_status in {"cancelled", "refused", "superseded"}
        and operation.operation not in {"query_status"}
    ):
        result["reason"] = (
            f"responsibility_status_{responsibility_status}_is_not_modifiable"
        )
        return result
    if (
        responsibility_status == "satisfied"
        and operation.operation
        not in {"query_status", "modify", "clarification_answer", "correct"}
    ):
        result["reason"] = "satisfied_responsibility_requires_correction_to_reopen"
        return result

    if operation.operation in {"cancel", "reject"}:
        context["status"] = "cancelled" if operation.operation == "cancel" else "refused"
        context["commitment_state"] = "cancelled" if operation.operation == "cancel" else "failed"
        state._set_goal_responsibility_status(
            context,
            "cancelled" if operation.operation == "cancel" else "refused",
            source=f"semantic_operation:{operation.operation}",
        )
    elif operation.operation == "pause":
        context["status"] = "paused"
    elif operation.operation == "resume":
        context["status"] = operation.status_update or "planning"
        context["commitment_state"] = operation.commitment_state or "evaluating"
    elif operation.operation == "confirm":
        context["status"] = operation.status_update or "committed"
        context["commitment_state"] = operation.commitment_state or "accepted"
    elif operation.operation == "query_status":
        pass
    else:
        goal = state._semantic_goal_from_context(context)
        try:
            revised = merge_semantic_goal(goal, operation, user_text=user_text)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Goal meaning update rejected task_id=%s reason=%s", context.get("task_id"), exc)
            result.update(reason="invalid_goal_meaning_update", detail=str(exc))
            return result
        history = context.setdefault("goal_revision_history", [])
        history.append({"operation_id": operation.operation_id,
                        "prior_goal": goal.model_dump(mode="json"),
                        "source_update": copy.deepcopy(operation.goal_update)})
        context["semantic_goal"] = revised.model_dump(mode="json", exclude_none=True)
        if revised.responsibility_status == "open":
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            context["metadata"] = {**metadata, "responsibility_status": "open"}
        context["goal"] = state._compact_text(revised.description, limit=220)
        context["goal_version"] = revised.version
        context["constraints"] = dict(revised.constraints)

        raw_gaps = context.get("open_information_gaps")
        existing_gaps: list[dict[str, Any]] = [
            dict(item) for item in raw_gaps if isinstance(item, dict)
        ] if isinstance(raw_gaps, list) else []
        resolved = set(operation.resolved_gap_ids)
        existing_gaps = [
            item for item in existing_gaps
            if str(item.get("gap_id") or "") not in resolved
        ]
        by_id = {
            str(item.get("gap_id") or ""): item
            for item in existing_gaps
            if str(item.get("gap_id") or "")
        }
        for gap in operation.information_gaps:
            if gap.resolved:
                by_id.pop(gap.gap_id, None)
            else:
                by_id[gap.gap_id] = gap.model_dump(mode="json", exclude_none=True)
        context["open_information_gaps"] = list(by_id.values())
        context["pending_questions"] = [
            str(item.get("description") or "")
            for item in context["open_information_gaps"]
            if item.get("blocking") is not False and str(item.get("description") or "")
        ][:4]

        old_plan_version = max(0, int(context.get("plan_version") or 0))
        blocking_user_gap = any(
            bool(item.get("blocking", True))
            and str(item.get("preferred_resolution") or "") == "ask_user"
            for item in context["open_information_gaps"]
        )
        blocking_context_gap = any(
            bool(item.get("blocking", True))
            and str(item.get("preferred_resolution") or "")
            in {"observe_environment", "query_trusted_service"}
            for item in context["open_information_gaps"]
        )
        preserve_work_state = (
            old_plan_version > 0
            or previous_work_status
            in {
                "awaiting_confirmation",
                "committed",
                "scheduled",
                "running",
                "paused",
                "recoverable",
            }
        )
        if preserve_work_state:
            context["status"] = previous_work_status
            context["commitment_state"] = previous_commitment_state
            context["plan_status"] = previous_plan_status
        else:
            context["status"] = operation.status_update or (
                "waiting_for_user"
                if blocking_user_gap
                else "needs_context"
                if blocking_context_gap
                else "planning"
            )
            context["commitment_state"] = operation.commitment_state or (
                "waiting_for_user"
                if context["status"] == "waiting_for_user"
                else "evaluating"
            )

    context["task_relation"] = {
        "modify": "modify_task",
        "clarification_answer": "clarify_task",
        "correct": "modify_task",
        "cancel": "close_task",
        "reject": "close_task",
    }.get(operation.operation, context.get("task_relation") or "continue_task")
    context["updated_ms"] = now
    context["last_meaningful_user_turn"] = state._compact_text(user_text, limit=220)
    if sid:
        related = context.get("related_sids")
        if not isinstance(related, list):
            related = []
        if sid not in related:
            related.append(sid)
        context["related_sids"] = related[-12:]
    history = context.get("operation_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "operation_id": operation.operation_id,
            "operation": operation.operation,
            "goal_version": int(context.get("goal_version") or 1),
            "plan_version": int(context.get("plan_version") or 0),
            "ts_ms": now,
            "reason_summary": operation.reason_summary,
        }
    )
    context["operation_history"] = history[-24:]
    metadata = context.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    context["metadata"] = {
        **metadata,
        "source": source,
        "semantic_operation_id": operation.operation_id,
        "semantic_operation_confidence": operation.confidence,
        "semantic_relationship": operation.relationship,
    }
    result.update(
        {
            "applied": True,
            "goal_version": int(context.get("goal_version") or 1),
            "plan_version": int(context.get("plan_version") or 0),
            "status": context.get("status"),
        }
    )
    return result


def commit_semantic_state_transaction(
    state: Any,
    mutate: Callable[[], list[dict[str, Any]]],
    *,
    rollback_reason: str = "atomic_semantic_transaction_rolled_back",
    persistence_failure_reason: str = "atomic_semantic_persistence_failed",
) -> list[dict[str, Any]]:
    """Commit one semantic-state mutation as an in-memory/durable transaction.

    This is the only rollback and durable-commit boundary for atomic Goal
    Association and semantic-operation batches. Callers mutate only in memory;
    this primitive snapshots state, rejects the whole batch on any
    non-idempotent failure, persists once, and restores the snapshot on
    rejection, persistence failure, or exception.
    """

    task_context_snapshot = copy.deepcopy(list(state._task_contexts))
    pending_task_snapshot = copy.deepcopy(list(state._pending_tasks))
    discourse_referent_snapshot = copy.deepcopy(list(state._discourse_referents))
    discourse_focus_snapshot = list(state._discourse_focus)
    activity_snapshot = state.last_activity_ms
    store_error_snapshot = state.last_task_store_error

    def restore_snapshot(*, store_error: str | None = store_error_snapshot) -> None:
        state._task_contexts = deque(
            task_context_snapshot, maxlen=max(1, state.max_pending_tasks)
        )
        state._pending_tasks = deque(
            pending_task_snapshot, maxlen=max(1, state.max_pending_tasks)
        )
        state._discourse_referents = deque(
            discourse_referent_snapshot,
            maxlen=state.max_discourse_referents,
        )
        state._discourse_focus = deque(
            discourse_focus_snapshot,
            maxlen=state.max_discourse_focus,
        )
        state.last_activity_ms = activity_snapshot
        state.last_task_store_error = store_error

    try:
        results = mutate()
        rejected = [
            item
            for item in results
            if item.get("applied") is False
            and item.get("reason") != "operation_already_applied"
        ]
        if rejected:
            restore_snapshot()
            for item in results:
                if item.get("applied") is True:
                    item["applied"] = False
                    item["reason"] = rollback_reason
                    item["rolled_back"] = True
            return results

        changed = any(item.get("applied") is True for item in results)
        if changed:
            state.last_activity_ms = _now_ms()
        if changed and state.task_store_enabled and not state.persist_task_contexts():
            persistence_error = (
                state.last_task_store_error or "task context persistence failed"
            )
            restore_snapshot(store_error=persistence_error)
            for item in results:
                if item.get("applied") is True:
                    item["applied"] = False
                    item["reason"] = persistence_failure_reason
                    item["rolled_back"] = True
                    item["persistence_error"] = persistence_error
        return results
    except Exception:
        restore_snapshot()
        raise


def apply_goal_association_resolution(
    state: Any,
    resolution: GoalAssociationResolution | dict[str, Any],
    *,
    sid: str | None,
    user_text: str,
    source: str = "goal_association",
    atomic: bool = False,
) -> list[dict[str, Any]]:
    """Apply Goal Association through the shared semantic-state boundary."""

    if not state.enabled:
        return []

    def mutate() -> list[dict[str, Any]]:
        return apply_goal_association_resolution_in_memory(
            state,
            resolution,
            sid=sid,
            user_text=user_text,
            source=source,
        )

    if atomic:
        return state._commit_semantic_state_transaction(
            mutate,
            rollback_reason="atomic_goal_transaction_rolled_back",
            persistence_failure_reason="atomic_goal_persistence_failed",
        )

    results = mutate()
    if any(item.get("applied") is True for item in results):
        state._persist_task_contexts_if_enabled()
    return results


def apply_planner_information_gaps(
    state: Any,
    gaps_by_goal_id: dict[str, list[PlannerInformationGap | dict[str, Any]]],
    *,
    turn_id: str,
    sid: str | None,
    user_text: str,
    source: str = "fast_planner_information_gap",
) -> list[dict[str, Any]]:
    """Attach Planner-owned blocking needs without revising Goal meaning.

    Goal Association has already committed semantic identity. This atomic
    host adapter only joins Planner Responsibility provenance to those exact
    Goal IDs and exposes the pending question to the next turn's Context.
    """

    if not state.enabled or not gaps_by_goal_id:
        return []
    normalized: dict[str, list[PlannerInformationGap]] = {}
    for raw_goal_id, raw_gaps in gaps_by_goal_id.items():
        goal_id = " ".join(str(raw_goal_id or "").strip().split())
        if not goal_id:
            raise ValueError("Planner InformationGap requires a canonical Goal ID")
        gaps = [
            item
            if isinstance(item, PlannerInformationGap)
            else PlannerInformationGap.model_validate(item)
            for item in raw_gaps
        ]
        gap_ids = [item.gap_id for item in gaps]
        if not gaps or len(gap_ids) != len(set(gap_ids)):
            raise ValueError(
                f"Planner InformationGaps for {goal_id!r} must be non-empty and unique"
            )
        normalized[goal_id] = gaps

    def mutate() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        now = _now_ms()
        for ordinal, (goal_id, gaps) in enumerate(normalized.items()):
            operation_id = stable_goal_operation_id(
                turn_id=turn_id,
                ordinal=ordinal,
                relationship="planner_information_gap",
                target_goal_ids=[goal_id, *[item.gap_id for item in gaps]],
            )
            context = state._task_context_by_goal_id(goal_id)
            if context is None:
                results.append(
                    {
                        "operation_id": operation_id,
                        "operation": "planner_information_gap",
                        "goal_id": goal_id,
                        "applied": False,
                        "reason": "unknown_target_goal",
                    }
                )
                continue
            if context_has_operation_id(context, operation_id):
                results.append(
                    {
                        "operation_id": operation_id,
                        "operation": "planner_information_gap",
                        "goal_id": goal_id,
                        "task_id": context.get("task_id"),
                        "applied": False,
                        "replayed": True,
                        "reason": "operation_already_applied",
                    }
                )
                continue

            raw_existing = context.get("open_information_gaps")
            by_id = {
                str(item.get("gap_id") or ""): dict(item)
                for item in raw_existing
                if isinstance(item, dict) and str(item.get("gap_id") or "")
            } if isinstance(raw_existing, list) else {}
            for gap in gaps:
                by_id[gap.gap_id] = gap.model_dump(mode="json", exclude_none=True)
            context["open_information_gaps"] = list(by_id.values())
            context["pending_questions"] = [
                str(item.get("description") or "")
                for item in context["open_information_gaps"]
                if item.get("blocking") is not False
                and str(item.get("description") or "")
            ][:4]
            context["status"] = "waiting_for_user"
            context["commitment_state"] = "waiting_for_user"
            context["task_relation"] = "clarify_task"
            context["updated_ms"] = now
            context["last_meaningful_user_turn"] = state._compact_text(
                user_text,
                limit=220,
            )
            if sid:
                related = context.get("related_sids")
                if not isinstance(related, list):
                    related = []
                if sid not in related:
                    related.append(sid)
                context["related_sids"] = related[-12:]
            history = context.get("operation_history")
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "operation_id": operation_id,
                    "operation": "planner_information_gap",
                    "goal_version": int(context.get("goal_version") or 1),
                    "ts_ms": now,
                    "reason_summary": "The Planner selected user clarification.",
                }
            )
            context["operation_history"] = history[-24:]
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            context["metadata"] = {
                **metadata,
                "source": source,
                "planner_information_gap_owner": "fast_planner",
                "planner_information_gap_turn_id": turn_id,
            }
            results.append(
                {
                    "operation_id": operation_id,
                    "operation": "planner_information_gap",
                    "goal_id": goal_id,
                    "task_id": context.get("task_id"),
                    "gap_ids": [item.gap_id for item in gaps],
                    "applied": True,
                    "goal_version": int(context.get("goal_version") or 1),
                    "status": context.get("status"),
                }
            )
        return results

    return state._commit_semantic_state_transaction(
        mutate,
        rollback_reason="atomic_planner_gap_transaction_rolled_back",
        persistence_failure_reason="atomic_planner_gap_persistence_failed",
    )


def apply_goal_association_resolution_in_memory(
    state: Any,
    resolution: GoalAssociationResolution | dict[str, Any],
    *,
    sid: str | None,
    user_text: str,
    source: str = "goal_association",
) -> list[dict[str, Any]]:
    """Apply a validated goal-continuity result through semantic-task state.

    Semantic interpretation remains model-owned. This adapter only maps
    supported structured relationships into replay-safe state operations and
    records continuity markers for non-mutating references. Merge and split
    remain advisory until a dedicated multi-goal state transaction exists.
    """

    if not state.enabled:
        return []
    resolved = (
        resolution
        if isinstance(resolution, GoalAssociationResolution)
        else GoalAssociationResolution.model_validate(resolution)
    )
    candidates = {
        item["goal_id"]: item
        for item in state.goal_association_candidate_snapshots(
            limit=state.max_pending_tasks
        )
        if isinstance(item, dict) and item.get("goal_id")
    }
    operations: list[SemanticTaskOperation] = []
    results: list[dict[str, Any]] = []
    results.extend(state._apply_discourse_resolution_in_memory(resolved))

    for ordinal, goal in enumerate(resolved.new_goals):
        operation_id = stable_goal_operation_id(
            turn_id=resolved.turn_id,
            ordinal=len(resolved.associations) + ordinal,
            relationship="new",
        )
        operations.append(
            SemanticTaskOperation(
                operation_id=operation_id,
                operation="create",
                confidence=resolved.confidence,
                relationship="new",
                goal=goal,
                reason_summary=resolved.reason_summary,
                metadata={
                    "goal_association_turn_id": resolved.turn_id,
                    "goal_association_authority": "applied_after_validation",
                },
            )
        )

    relationship_map = {
        "modify": "modify",
        "clarify": "clarification_answer",
        "confirm": "confirm",
        "reject": "reject",
        "cancel": "cancel",
        "pause": "pause",
        "resume": "resume",
    }
    for association in resolved.associations:
        target_task_ids = [
            str(candidates[goal_id].get("source_task_id") or goal_id)
            for goal_id in association.target_goal_ids
            if goal_id in candidates
        ]
        if len(target_task_ids) != len(association.target_goal_ids):
            results.append(
                {
                    "association_id": association.association_id,
                    "relationship": association.relationship,
                    "applied": False,
                    "reason": "unknown_target_goal",
                }
            )
            continue
        if association.relationship in {"merge", "split"}:
            results.append(
                {
                    "association_id": association.association_id,
                    "relationship": association.relationship,
                    "applied": False,
                    "reason": "multi_goal_transaction_not_implemented",
                }
            )
            continue
        # A continuation or reference that answers the Goal's open input gap closes it like a
        # clarification answer (live 2026-10-27: "我在上海上班。" continued, then referenced, the umbrella
        # Goal with its location gap resolved; the gap stayed open and the Goal-bound Planner asked again).
        answers_gap = association.relationship in {"continue", "reference"} and bool(association.resolved_gap_ids)
        if association.relationship in {"continue", "reference"} and not answers_gap:
            for task_id in target_task_ids:
                context = state._task_context_by_id(task_id)
                if context is None:
                    continue
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                context["metadata"] = {
                    **metadata,
                    "goal_association_id": association.association_id,
                    "goal_relationship": association.relationship,
                    "goal_association_confidence": association.confidence,
                    "goal_association_reason": association.reason_summary,
                }
                context["last_meaningful_user_turn"] = state._compact_text(
                    user_text, limit=220
                )
                context["updated_ms"] = _now_ms()
                if sid:
                    related = context.get("related_sids")
                    if not isinstance(related, list):
                        related = []
                    if sid not in related:
                        related.append(sid)
                    context["related_sids"] = related[-12:]
                results.append(
                    {
                        "association_id": association.association_id,
                        "relationship": association.relationship,
                        "task_id": task_id,
                        "applied": True,
                        "state_change": "continuity_marker",
                    }
                )
            continue

        operation_name = "clarification_answer" if answers_gap else relationship_map.get(association.relationship)
        if operation_name is None:
            results.append(
                {
                    "association_id": association.association_id,
                    "relationship": association.relationship,
                    "applied": False,
                    "reason": "unsupported_relationship",
                }
            )
            continue
        if operation_name in {
            "modify",
            "clarification_answer",
        } and not (association.goal_update or association.resolved_gap_ids):
            results.append(
                {
                    "association_id": association.association_id,
                    "relationship": association.relationship,
                    "applied": False,
                    "reason": "semantic_delta_required",
                }
            )
            continue
        updates = association.goal_update.get("by_goal_id", {})
        invalid_source = False
        if isinstance(updates, dict):
            for payload in updates.values():
                if not isinstance(payload, dict) or "base_goal_fingerprint" not in payload:
                    invalid_source = True
                    break
                sources = payload.get("source_responsibilities")
                if (payload.get("source_turn_id") != resolved.turn_id
                        or not isinstance(sources, list) or not sources
                        or any(not isinstance(item, dict)
                               or item.get("local_ref") not in association.source_responsibility_refs
                               for item in sources)):
                    invalid_source = True
                    break
        if association.goal_update and (
            set(association.goal_update) != {"by_goal_id"}
            or not isinstance(updates, dict)
            or set(updates) - set(association.target_goal_ids)
            or not updates or invalid_source
        ):
            results.append({"association_id": association.association_id,
                            "applied": False, "reason": "source_bound_goal_update_required"})
            continue
        for goal_id, task_id in zip(association.target_goal_ids, target_task_ids, strict=True):
            operations.append(
                SemanticTaskOperation(
                    operation_id=(association.association_id if len(target_task_ids) == 1
                                  else f"{association.association_id}:{goal_id}"),
                    operation=operation_name,
                    target_task_ids=[task_id],
                    confidence=association.confidence,
                    relationship=association.relationship,
                    goal_update=updates.get(goal_id, {}),
                    resolved_gap_ids=association.resolved_gap_ids,
                    reason_summary=association.reason_summary,
                    metadata={
                        "goal_association_turn_id": resolved.turn_id,
                        "goal_association_authority": "applied_after_validation",
                    },
                )
            )

    if operations:
        results.extend(
            state.apply_semantic_task_operations(
                operations,
                sid=sid,
                user_text=user_text,
                        source=source,
                persist=False,
            )
        )
    return results


def apply_semantic_task_operations(
    state: Any,
    operations: list[SemanticTaskOperation] | list[dict[str, Any]],
    *,
    sid: str | None,
    user_text: str,
    source: str | None = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    if not state.enabled:
        return []
    validated: list[SemanticTaskOperation] = []
    for index, item in enumerate(operations):
        if isinstance(item, SemanticTaskOperation):
            validated.append(item)
            continue
        try:
            validated.append(SemanticTaskOperation.model_validate(item))
        except (ValidationError, TypeError) as exc:
            raise ValueError(
                f"invalid semantic operation at index {index}: {exc}"
            ) from exc
    results: list[dict[str, Any]] = []
    for operation in validated:
        if operation.operation == "create":
            existing = context_by_operation_id(state, operation.operation_id)
            if existing is not None:
                results.append(
                    {
                        "operation_id": operation.operation_id,
                        "operation": operation.operation,
                        "task_id": existing.get("task_id"),
                        "applied": False,
                        "replayed": True,
                        "reason": "operation_already_applied",
                        "goal_version": int(existing.get("goal_version") or 1),
                        "plan_version": int(existing.get("plan_version") or 0),
                        "status": existing.get("status"),
                    }
                )
                continue
            context = new_semantic_task_context(
                state,
                sid=sid,
                operation=operation,
                user_text=user_text,
                        source=source,
            )
            results.append(
                {
                    "operation_id": operation.operation_id,
                    "operation": operation.operation,
                    "task_id": context["task_id"],
                    "applied": True,
                    "goal_version": context["goal_version"],
                    "plan_version": context["plan_version"],
                    "status": context["status"],
                }
            )
            continue
        for task_id in operation.target_task_ids:
            context = state._task_context_by_id(task_id)
            if context is None:
                results.append(
                    {
                        "operation_id": operation.operation_id,
                        "operation": operation.operation,
                        "task_id": task_id,
                        "applied": False,
                        "reason": "unknown_task_id",
                    }
                )
                continue
            results.append(
                apply_semantic_operation_to_context(
                    state,
                    context,
                    operation,
                    sid=sid,
                    user_text=user_text,
                                    source=source,
                )
            )
    if results:
        if persist:
            state._persist_task_contexts_if_enabled()
        state.last_activity_ms = _now_ms()
    return results


def apply_semantic_task_operations_atomically(
    state: Any,
    operations: list[SemanticTaskOperation] | list[dict[str, Any]],
    *,
    sid: str | None,
    user_text: str,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Apply a semantic-operation batch as one in-memory/durable transaction.

    The full batch is validated before mutation. Any state-level rejection
    rolls back all earlier operations, and durable state is written only once
    after the complete batch succeeds. Existing idempotent replays remain
    accepted.
    """
    if not state.enabled:
        return []

    validated: list[SemanticTaskOperation] = []
    for index, item in enumerate(operations):
        try:
            validated.append(
                item
                if isinstance(item, SemanticTaskOperation)
                else SemanticTaskOperation.model_validate(item)
            )
        except Exception as exc:
            raise ValueError(
                f"invalid semantic operation at batch index {index}: {exc}"
            ) from exc

    return state._commit_semantic_state_transaction(
        lambda: state.apply_semantic_task_operations(
            validated,
            sid=sid,
            user_text=user_text,
            source=source,
            persist=False,
        )
    )
