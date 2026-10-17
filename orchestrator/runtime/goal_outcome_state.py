"""Confirmation scope, pending execution and execution outcomes for ConversationStateManager.

The functions take the ``ConversationStateManager`` as ``state``. They record
confirmation scope and pending Work, reconcile execution outcome Evidence and
Reflection with Goal state and derive follow-up cognitive opportunities.
"""

from __future__ import annotations

import copy
from typing import Any

from orchestrator.runtime.memory import MemoryEntry

from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    execution_outcome_fingerprint,
    goal_completion_qualification_summary,
)
from shared.chromie_contracts.situation import CognitiveOpportunity
from shared.chromie_contracts.reflection import ReflectionResolution

from orchestrator.runtime.conversation_state import _DONE_TASK_STATUSES, _now_ms


def canonical_goal_outcomes(
    metadata: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return goal-keyed outcomes from a trusted canonical-plan envelope."""

    if not isinstance(metadata, dict):
        return {}
    if metadata.get("transient_responsibility") is True:
        return {}
    plan = metadata.get("canonical_plan")
    if not isinstance(plan, dict):
        if (
            metadata.get("planning_result") == "direct_response"
            and metadata.get("planless_direct_response") is True
        ):
            goal_ids = metadata.get("goal_ids")
            if isinstance(goal_ids, str):
                goal_ids = [goal_ids]
            if isinstance(goal_ids, list):
                return {
                    goal_id: {"goal_id": goal_id, "disposition": "respond"}
                    for value in goal_ids
                    if (goal_id := " ".join(str(value or "").strip().split()))
                }
        return {}
    raw_outcomes = plan.get("goal_outcomes")
    outcomes: dict[str, dict[str, Any]] = {}
    if isinstance(raw_outcomes, dict):
        iterable = []
        for goal_id, value in raw_outcomes.items():
            if isinstance(value, dict):
                iterable.append({"goal_id": goal_id, **value})
    elif isinstance(raw_outcomes, list):
        iterable = [item for item in raw_outcomes if isinstance(item, dict)]
    else:
        iterable = []
    for item in iterable:
        goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
        disposition = str(item.get("disposition") or "").strip().lower()
        if goal_id and disposition:
            outcomes[goal_id] = dict(item)
    # A Value Judgment that withheld a Goal's answer is that Goal's speech outcome:
    # decline ends it refused, ask leaves it waiting for the person (choice A).
    verdict = (plan.get("metadata") or {}).get("value_judgment") if isinstance(plan.get("metadata"), dict) else None
    if isinstance(verdict, dict) and verdict.get("decision") in {"ask", "decline"}:
        withheld_disposition = "clarify" if verdict["decision"] == "ask" else "value_declined"
        for goal_id in verdict.get("withheld_answer_goal_ids") or []:
            if goal_id in outcomes and outcomes[goal_id].get("disposition") == "respond":
                outcomes[goal_id] = {**outcomes[goal_id], "disposition": withheld_disposition,
                                     "value_withheld": True}

    # Single-disposition plans may omit per-goal outcomes. Preserve their
    # exact structured disposition without inferring anything from speech.
    if not outcomes:
        disposition = str(plan.get("disposition") or "").strip().lower()
        goal_ids = plan.get("goal_ids")
        if isinstance(goal_ids, str):
            goal_ids = [goal_ids]
        if disposition and isinstance(goal_ids, list):
            for value in goal_ids:
                goal_id = " ".join(str(value or "").strip().split())
                if goal_id:
                    outcomes[goal_id] = {
                        "goal_id": goal_id,
                        "disposition": disposition,
                    }
    return outcomes


def commitment_state_for_status(status: str) -> str:
    return {
        "awaiting_confirmation": "waiting_for_user",
        "scheduled": "accepted",
        "running": "executing",
        "done": "completed",
        "failed": "failed",
        "refused": "failed",
        "timed_out": "failed",
        "cancelled": "cancelled",
    }.get(status, "evaluating")


def record_nonexecuting_goal_outcomes(
    state: Any,
    outcomes: dict[str, dict[str, Any]],
) -> None:
    """Apply deterministic non-execution lifecycle outcomes per goal.

    A clarification remains active and waits for the user.  Refusal and
    unavailability are terminal planning outcomes.  Respond outcomes are
    deliberately left for speech-request evidence, while execute outcomes
    are left for their goal-scoped CapabilityRequest evidence.
    """

    changed = False
    now = _now_ms()
    for goal_id, outcome in outcomes.items():
        disposition = str(outcome.get("disposition") or "").strip().lower()
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            continue
        item_changed = False
        if disposition == "clarify":
            context["status"] = "waiting_for_user"
            context["commitment_state"] = "waiting_for_user"
            context["plan_status"] = "blocked_on_user"
            unresolved = outcome.get("unresolved")
            if isinstance(unresolved, str):
                unresolved = [unresolved]
            if isinstance(unresolved, list):
                context["pending_questions"] = [
                    state._compact_text(str(item), limit=220)
                    for item in unresolved
                    if str(item).strip()
                ][:4]
            item_changed = True
        elif disposition in {"unavailable", "refused", "value_declined"}:
            # value_declined: Chromie's Value Judgment withheld this Goal's answer. Like a
            # limitation it ends the Goal without a pre-dispatch responsibility change.
            context["status"] = "refused"
            context["commitment_state"] = "failed"
            context["plan_status"] = disposition
            if disposition == "refused":
                state._set_goal_responsibility_status(
                    context,
                    "refused",
                    source="canonical_plan_refusal",
                )
            item_changed = True
        if item_changed:
            context["updated_ms"] = now
            changed = True
    if changed:
        state._persist_task_contexts_if_enabled()


def record_goal_pending_execution(
    state: Any,
    *,
    sid: str | None,
    goal_id: str,
    status: str,
    summary: str,
    request_ids: list[str],
    planning_result: str,
    planned_capabilities: list[dict[str, Any]],
    confirmation_pending: bool,
    interaction_id: str = "",
    turn_id: str = "",
    canonical_plan_id: str = "",
    canonical_plan_fingerprint: str = "",
    planner_reentry_responsibilities: list[dict[str, Any]] | None = None,
    planner_reentry_language: str = "",
    planned_satisfaction: dict[str, Any] | None = None,
) -> None:
    """Track execution lifecycle for one semantic goal only.

    Multi-goal plans must not attach every provider request to whichever goal
    happens to be last in the deque. Auxiliary social-attention requests are
    intentionally omitted by the caller.
    """

    if not state.enabled or not goal_id or not request_ids:
        return
    timestamp_ms = _now_ms()
    metadata = {
        "goal_id": goal_id,
        "request_ids": list(request_ids),
        "remaining_request_ids": list(request_ids),
        "request_statuses": {},
        "planning_result": planning_result,
        "planned_satisfaction": planned_satisfaction,
        "confirmation_pending": confirmation_pending,
        "planned_capabilities": [dict(item) for item in planned_capabilities],
        "interaction_id": str(interaction_id or "").strip(),
        "turn_id": str(turn_id or "").strip(),
        "canonical_plan_id": str(canonical_plan_id or "").strip(),
        "canonical_plan_fingerprint": str(
            canonical_plan_fingerprint or ""
        ).strip(),
        **(
            {
                "planner_reentry_responsibilities": [
                    state._json_safe(item)
                    for item in planner_reentry_responsibilities
                    if isinstance(item, dict)
                ],
                "planner_reentry_language": state._compact_text(
                    planner_reentry_language or "auto", limit=64
                ),
            }
            if planner_reentry_responsibilities
            else {}
        ),
    }
    state._pending_tasks.append(
        {
            "sid": sid,
            "type": "goal_execution",
            "status": status,
            "summary": state._compact_text(summary or goal_id),
            "ts_ms": timestamp_ms,
            "updated_ms": timestamp_ms,
            "conversation_id": state.conversation_id,
            "metadata": metadata,
        }
    )
    context = state._task_context_by_goal_id(goal_id)
    if context is not None:
        context["status"] = status
        context["commitment_state"] = commitment_state_for_status(status)
        context["updated_ms"] = timestamp_ms
        current_metadata = context.get("metadata")
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        retained = list(current_metadata.get("retained_work_activities") or [])
        retained_ids = [item["activity_id"] for item in retained]
        context["metadata"] = {
            **current_metadata, **metadata,
            "request_ids": list(dict.fromkeys([*retained_ids, *request_ids])),
            "remaining_request_ids": list(dict.fromkeys([*retained_ids, *request_ids])),
            "request_statuses": {key: value for key, value in current_metadata.get("request_statuses", {}).items() if key in retained_ids},
            "planned_capabilities": [*[{**item, "request_id": item["activity_id"]} for item in retained], *metadata["planned_capabilities"]],
        }
        state._persist_task_contexts_if_enabled()
    state.last_activity_ms = timestamp_ms


def record_confirmation_scope(
    state: Any,
    *,
    sid: str | None,
    confirmation_id: str,
    interaction_id: str,
    fingerprint: str,
    expires_at: float,
    response: Any,
    confirmed_request_ids: set[str],
) -> list[str]:
    """Bind a staged confirmation to every semantic goal it covers.

    A confirmation is a user-decision boundary, not runtime execution
    evidence.  Its request IDs are therefore retained for auditability but
    are deliberately stored in ``goal_confirmation`` records instead of
    ``goal_execution`` records.  Only the post-approval Agent result may
    schedule those requests.
    """

    if not state.enabled or state.max_pending_tasks <= 0:
        return []
    if hasattr(response, "model_dump"):
        data = response.model_dump(mode="json")
    elif isinstance(response, dict):
        data = response
    else:
        data = {}

    confirmed = {
        str(request_id).strip()
        for request_id in confirmed_request_ids
        if str(request_id).strip()
    }
    by_goal: dict[str, list[dict[str, str]]] = {}
    scoped_request_ids: set[str] = set()
    for raw_request in data.get("capabilities", []) or data.get("actions", []) or []:
        if isinstance(raw_request, dict):
            request = raw_request
        else:
            request = {
                "request_id": getattr(raw_request, "request_id", None),
                "capability_id": getattr(raw_request, "capability_id", None),
                "metadata": getattr(raw_request, "metadata", None),
            }
        request_id = str(request.get("request_id") or "").strip()
        if not request_id or request_id not in confirmed:
            continue
        metadata = request.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        capability_id = str(
            request.get("capability_id")
            or request.get("type")
            or request.get("target")
            or "action"
        ).strip()
        for goal_id in state._string_list(metadata.get("source_goal_ids")):
            by_goal.setdefault(goal_id, []).append(
                {"request_id": request_id, "capability_id": capability_id}
            )
            scoped_request_ids.add(request_id)

    timestamp_ms = _now_ms()
    goal_ids: list[str] = []
    for goal_id, requests in by_goal.items():
        request_ids = list(
            dict.fromkeys(item["request_id"] for item in requests)
        )
        summary = ", ".join(
            dict.fromkeys(item["capability_id"] for item in requests)
        )
        metadata = {
            "confirmation_id": confirmation_id,
            "interaction_id": interaction_id,
            "fingerprint": fingerprint,
            "expires_at": expires_at,
            "goal_id": goal_id,
            "request_ids": request_ids,
            "confirmation_request_ids": request_ids,
        }
        state._pending_tasks.append(
            {
                "sid": sid,
                "type": "goal_confirmation",
                "status": "awaiting_confirmation",
                "summary": state._compact_text(summary or goal_id),
                "ts_ms": timestamp_ms,
                "updated_ms": timestamp_ms,
                "conversation_id": state.conversation_id,
                "metadata": metadata,
            }
        )
        goal_ids.append(goal_id)
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            continue
        context["status"] = "awaiting_confirmation"
        context["commitment_state"] = "waiting_for_user"
        context["plan_status"] = "awaiting_confirmation"
        context["confirmation"] = {
            "status": "pending",
            "confirmation_id": confirmation_id,
            "fingerprint": fingerprint,
            "expires_at": expires_at,
            "request_ids": request_ids,
        }
        context["updated_ms"] = timestamp_ms
        current_metadata = context.get("metadata")
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        context["metadata"] = {
            **current_metadata,
            "confirmation_id": confirmation_id,
            "confirmation_request_ids": request_ids,
        }

    # Keep request-bound evidence even for legacy/unscoped requests, but do
    # not mutate whichever task context happens to be current.
    unscoped_request_ids = sorted(confirmed - scoped_request_ids)
    if unscoped_request_ids:
        state._pending_tasks.append(
            {
                "sid": sid,
                "type": "confirmation",
                "status": "awaiting_confirmation",
                "summary": "confirmation",
                "ts_ms": timestamp_ms,
                "updated_ms": timestamp_ms,
                "conversation_id": state.conversation_id,
                "metadata": {
                    "confirmation_id": confirmation_id,
                    "interaction_id": interaction_id,
                    "fingerprint": fingerprint,
                    "expires_at": expires_at,
                    "request_ids": unscoped_request_ids,
                    "confirmation_request_ids": unscoped_request_ids,
                },
            }
        )

    if goal_ids:
        state._persist_task_contexts_if_enabled()
    state.last_activity_ms = timestamp_ms
    return goal_ids


def resolve_confirmation_scope(
    state: Any,
    *,
    confirmation_id: str,
    decision: str,
) -> bool:
    """Resolve all pending records and goals bound to one confirmation."""

    if not state.enabled or not confirmation_id:
        return False
    normalized_decision = str(decision or "").strip().lower()
    final_status = {
        "approved": "done",
        "denied": "cancelled",
        "ambiguous": "refused",
        "expired": "timed_out",
        "operational_interrupt": "cancelled",
    }.get(normalized_decision, "cancelled")
    matched = False
    changed_context = False
    timestamp_ms = _now_ms()
    for task in state._pending_tasks:
        metadata = task.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if metadata.get("confirmation_id") != confirmation_id:
            continue
        matched = True
        task["status"] = final_status
        task["updated_ms"] = timestamp_ms
        goal_id = str(metadata.get("goal_id") or "").strip()
        if not goal_id:
            continue
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            continue
        if normalized_decision == "approved":
            # Approval commits the plan but does not claim that Skill
            # Runtime has scheduled it. record_interaction_response performs that
            # transition immediately before the authorized launch.
            context["status"] = "planning"
            context["commitment_state"] = "accepted"
            context["plan_status"] = "confirmed"
        else:
            context["status"] = final_status
            context["commitment_state"] = commitment_state_for_status(
                final_status
            )
            context["plan_status"] = final_status
        confirmation = context.get("confirmation")
        if not isinstance(confirmation, dict):
            confirmation = {}
        context["confirmation"] = {
            **confirmation,
            "status": normalized_decision or final_status,
            "resolved_ms": timestamp_ms,
        }
        context["updated_ms"] = timestamp_ms
        changed_context = True

    if changed_context:
        state._persist_task_contexts_if_enabled()
    if matched:
        state.last_activity_ms = timestamp_ms
    return matched


def record_pending_task(
    state: Any,
    *,
    sid: str | None,
    task_type: str,
    status: str = "pending",
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not state.enabled or state.max_pending_tasks <= 0:
        return
    task_type = (task_type or "unknown").strip() or "unknown"
    timestamp_ms = _now_ms()
    state._pending_tasks.append(
        {
            "sid": sid,
            "type": task_type,
            "status": status or "pending",
            "summary": state._compact_text(summary or task_type),
            "ts_ms": timestamp_ms,
            "updated_ms": timestamp_ms,
            "conversation_id": state.conversation_id,
            "metadata": metadata or {},
        }
    )
    current_task = state._current_task_context()
    if current_task is not None:
        current_task["status"] = status or "pending"
        current_task["updated_ms"] = timestamp_ms
        meta = current_task.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        current_task["metadata"] = {
            **meta,
            "pending_task_type": task_type,
            **(metadata or {}),
        }
        state._persist_task_contexts_if_enabled()
    state.last_activity_ms = _now_ms()


def update_pending_task_status(
    state: Any,
    *,
    metadata_key: str,
    metadata_value: Any,
    status: str,
) -> bool:
    if not state.enabled:
        return False
    for task in reversed(state._pending_tasks):
        metadata = task.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if metadata.get(metadata_key) != metadata_value:
            continue
        task["status"] = status
        task["updated_ms"] = _now_ms()
        current_task = state._current_task_context()
        if current_task is not None:
            current_task["status"] = status
            current_task["updated_ms"] = task["updated_ms"]
            state._persist_task_contexts_if_enabled()
        state.last_activity_ms = _now_ms()
        return True
    return False


def update_pending_task_status_for_request_id(
    state: Any,
    *,
    request_id: str | None,
    status: str,
) -> bool:
    if not state.enabled or not request_id:
        return False
    normalized_status = str(status or "done").lower()
    final_status = {
        "completed": "done",
        "success": "done",
        "ok": "done",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "expired": "timed_out",
        "timed_out": "timed_out",
        "refused": "refused",
        "failed": "failed",
        "error": "failed",
        "partial": "failed",
        "not_run": "failed",
    }.get(normalized_status, normalized_status)
    matched = False
    for task in list(state._pending_tasks):
        if task.get("type") in {"confirmation", "goal_confirmation"}:
            # A confirmation record is decision evidence only. Runtime
            # results belong to the execution record created after
            # approval, even though both retain the same request IDs.
            continue
        metadata = task.get("metadata")
        if not isinstance(metadata, dict):
            continue
        request_ids = metadata.get("request_ids")
        if isinstance(request_ids, str):
            request_ids = [request_ids]
        if not isinstance(request_ids, list) or request_id not in request_ids:
            continue
        matched = True
        statuses = metadata.setdefault("request_statuses", {})
        if not isinstance(statuses, dict):
            statuses = {}
            metadata["request_statuses"] = statuses
        statuses[request_id] = final_status
        remaining = metadata.get("remaining_request_ids")
        if isinstance(remaining, str):
            remaining = [remaining]
        if not isinstance(remaining, list):
            remaining = list(request_ids)
        remaining = [item for item in remaining if item != request_id]
        metadata["remaining_request_ids"] = remaining
        if remaining:
            task_status = "running"
        else:
            values = list(statuses.values())
            if "failed" in values:
                task_status = "failed"
            elif "refused" in values:
                task_status = "refused"
            elif "cancelled" in values:
                task_status = "cancelled"
            elif "timed_out" in values:
                task_status = "timed_out"
            else:
                task_status = "done"
        task["status"] = task_status
        task["updated_ms"] = _now_ms()

        goal_id = str(metadata.get("goal_id") or "").strip()
        contexts: list[dict[str, Any]] = []
        if goal_id:
            context = state._task_context_by_goal_id(goal_id)
            if context is not None:
                contexts.append(context)
        else:
            for context in state._task_contexts:
                context_metadata = context.get("metadata")
                if not isinstance(context_metadata, dict):
                    continue
                context_request_ids = context_metadata.get("request_ids")
                if isinstance(context_request_ids, str):
                    context_request_ids = [context_request_ids]
                if isinstance(context_request_ids, list) and request_id in context_request_ids:
                    contexts.append(context)
        for context in contexts:
            context_metadata = context.get("metadata") or {}
            if context_metadata.get("retained_work_activities"):
                owned_ids = set(context_metadata.get("request_ids") or [])
                if request_id not in owned_ids:
                    continue
                statuses = {**context_metadata.get("request_statuses", {}), request_id: final_status}
                remaining = [item for item in context_metadata.get("remaining_request_ids", []) if item != request_id]
                if remaining:
                    task_status = "running"
                else:
                    failures = [item for item in ("failed", "refused", "cancelled", "timed_out") if item in statuses.values()]
                    task_status = failures[0] if failures else "done"
            context["status"] = task_status
            context["commitment_state"] = (
                commitment_state_for_status(task_status)
            )
            if task_status in _DONE_TASK_STATUSES:
                context["plan_status"] = task_status
            context["updated_ms"] = task["updated_ms"]
            context_metadata = context.get("metadata")
            if not isinstance(context_metadata, dict):
                context_metadata = {}
            context["metadata"] = {
                **context_metadata,
                "request_statuses": dict(statuses),
                "remaining_request_ids": list(remaining),
            }
            planned_capabilities = context["metadata"].get("planned_capabilities")
            speaking_only = bool(planned_capabilities) and all(
                isinstance(item, dict)
                and str(item.get("capability_id") or "") == "chromie.speak"
                for item in planned_capabilities
            ) if isinstance(planned_capabilities, list) else False
            planned_satisfaction = context["metadata"].get("planned_satisfaction") or {}
            if (
                task_status == "done" and speaking_only
                and not planned_satisfaction.get("unmet_requirements")
                and goal_id not in (planned_satisfaction.get("unmet_goal_ids") or [])
                and state._goal_responsibility_status(context) not in {"cancelled", "refused", "superseded"}
            ):
                state._set_goal_responsibility_status(
                    context,
                    "satisfied",
                    source="speaking_delivery_reconciliation",
                    evidence_refs=[request_id],
                )

        state._memory_store.add_many(
            state._memory_extractor.extract_task_outcome(
                sid=str(task.get("sid") or ""),
                summary=str(task.get("summary") or task.get("type") or "task"),
                status=str(task_status),
                trusted=True,
            )
        )
    if matched:
        state._persist_task_contexts_if_enabled()
        state.last_activity_ms = _now_ms()
    return matched


def record_execution_outcome_bundle(
    state: Any,
    bundle: ExecutionOutcomeBundle,
    *,
    sid: str | None,
) -> list[dict[str, Any]]:
    """Atomically attach exact execution evidence to bound Work records.

    ExecutionOutcome is immutable historical truth about what execution did.
    This method updates Work/runtime projections and evidence only; it never
    decides whether the semantic Responsibility is satisfied.
    """

    if not state.enabled:
        return []
    validated = ExecutionOutcomeBundle.model_validate(bundle)
    fingerprint = execution_outcome_fingerprint(validated)
    normalized_sid = str(sid or "").strip()
    evidence_request_ids_by_goal: dict[str, set[str]] = {}
    for evidence in validated.evidence:
        for goal_id in evidence.source_goal_ids:
            evidence_request_ids_by_goal.setdefault(goal_id, set()).add(
                evidence.request_id
            )

    expected_binding = {
        "interaction_id": validated.interaction_id,
        "turn_id": validated.turn_id,
        "canonical_plan_id": validated.canonical_plan_id,
        "canonical_plan_fingerprint": (
            validated.canonical_plan_fingerprint
        ),
    }
    bound_records: dict[
        str,
        tuple[dict[str, Any], list[dict[str, Any]]],
    ] = {}
    for outcome in validated.goal_outcomes:
        context = state._task_context_by_goal_id(outcome.goal_id)
        if context is None:
            raise ValueError(
                "execution outcome references a goal with no committed "
                f"task context: {outcome.goal_id}"
            )
        context_metadata = context.get("metadata")
        if not isinstance(context_metadata, dict):
            raise ValueError(
                "execution outcome goal has no committed plan binding: "
                f"{outcome.goal_id}"
            )
        current_binding = all(str(context_metadata.get(key) or "").strip() == expected for key, expected in expected_binding.items())
        retained_binding = any(
            item.get("activity_id") in evidence_request_ids_by_goal.get(outcome.goal_id, set())
            and all(str((item.get("runtime_binding") or {}).get(key) or "") == expected_binding[key]
                    for key in ("interaction_id", "canonical_plan_id", "canonical_plan_fingerprint"))
            for item in context_metadata.get("retained_work_activities", [])
        )
        if not current_binding and not retained_binding:
            raise ValueError("execution outcome is stale or does not match the current or explicitly retained goal binding: " + outcome.goal_id)

        expected_request_ids = evidence_request_ids_by_goal.get(
            outcome.goal_id,
            set(),
        )
        matches: list[dict[str, Any]] = []
        for task in state._pending_tasks:
            task_metadata = task.get("metadata")
            if (
                task.get("type") != "goal_execution"
                or not isinstance(task_metadata, dict)
                or str(task_metadata.get("goal_id") or "").strip()
                != outcome.goal_id
            ):
                continue
            if normalized_sid and str(task.get("sid") or "").strip() != normalized_sid:
                continue
            if any(
                str(task_metadata.get(key) or "").strip() != expected
                for key, expected in expected_binding.items()
            ):
                continue
            request_ids = task_metadata.get("request_ids")
            if isinstance(request_ids, str):
                request_ids = [request_ids]
            if not isinstance(request_ids, list):
                continue
            if {
                str(item).strip()
                for item in request_ids
                if str(item).strip()
            } != expected_request_ids:
                continue
            matches.append(task)
        if len(matches) != 1:
            raise ValueError(
                "execution outcome requires exactly one matching committed "
                f"goal execution record: {outcome.goal_id}"
            )
        bound_records[outcome.goal_id] = (context, matches)

    pending_backup = copy.deepcopy(state._pending_tasks)
    contexts_backup = copy.deepcopy(state._task_contexts)
    timestamp_ms = _now_ms()
    status_projection = {
        "completed": "done",
        "partial": "failed",
        "failed": "failed",
        "refused": "refused",
        "timed_out": "timed_out",
        "cancelled": "cancelled",
        "not_run": "failed",
    }
    evidence_by_id = {
        item.evidence_id: item for item in validated.evidence
    }
    results: list[dict[str, Any]] = []
    try:
        for outcome in validated.goal_outcomes:
            context, matching_tasks = bound_records[outcome.goal_id]
            prior_context = copy.deepcopy(context)
            is_retained_outcome = any(str((context.get("metadata") or {}).get(key) or "") != expected for key, expected in expected_binding.items())
            referenced_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in outcome.evidence_ids
                if evidence_id in evidence_by_id
            ]
            retryable_safe_read = bool(referenced_evidence) and all(
                item.metadata.get("retryable_safe_read") is True
                for item in referenced_evidence
            )
            qualification = completion_qualification_summary(
                validated, outcome
            )
            completion_unqualified = bool(
                outcome.status == "completed"
                and qualification["required"]
                and not qualification["established"]
            )
            execution_task_status = status_projection[outcome.status]
            lifecycle_status = (
                "recoverable"
                if completion_unqualified
                or (
                    retryable_safe_read
                    and outcome.status
                    in {"failed", "timed_out", "cancelled", "not_run"}
                )
                else "planning"
                if outcome.status == "completed"
                and outcome.requires_planner_continuation
                else execution_task_status
            )
            evidence_summary = context.get("evidence_summary")
            if not isinstance(evidence_summary, dict):
                evidence_summary = {}
            evidence_summary["execution_outcome"] = {
                "outcome_id": validated.outcome_id,
                "outcome_fingerprint": fingerprint,
                "turn_id": validated.turn_id,
                "interaction_id": validated.interaction_id,
                "canonical_plan_id": validated.canonical_plan_id,
                "canonical_plan_fingerprint": (
                    validated.canonical_plan_fingerprint
                ),
                "goal_id": outcome.goal_id,
                "status": outcome.status,
                "step_ids": list(outcome.step_ids),
                "evidence_ids": list(outcome.evidence_ids),
                "completed_step_ids": list(outcome.completed_step_ids),
                "unresolved_step_ids": list(outcome.unresolved_step_ids),
                "acquisition_step_ids": list(outcome.acquisition_step_ids),
                "planned_satisfaction": (
                    outcome.planned_satisfaction.model_dump(mode="json")
                    if outcome.planned_satisfaction else None
                ),
                "requires_planner_continuation": outcome.requires_planner_continuation,
                "reason_codes": list(outcome.reason_codes),
                "completion_qualification_required": qualification["required"],
                "completion_qualification_established": qualification["established"],
                "completion_qualifications": qualification["qualifications"],
            }
            context["evidence_summary"] = evidence_summary
            context["status"] = lifecycle_status
            context["commitment_state"] = (
                commitment_state_for_status(lifecycle_status)
            )
            context["plan_status"] = lifecycle_status
            context["updated_ms"] = timestamp_ms
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            context["metadata"] = {
                **metadata,
                "execution_outcome_id": validated.outcome_id,
                "execution_outcome_fingerprint": fingerprint,
                "execution_outcome_status": outcome.status,
                "execution_evidence_ids": list(outcome.evidence_ids),
                "retryable_safe_read": retryable_safe_read,
                "completion_qualification_required": qualification["required"],
                "completion_qualification_established": qualification["established"],
            }

            matched_pending = 0
            for task in matching_tasks:
                task_metadata = task.get("metadata")
                if not isinstance(task_metadata, dict):
                    raise RuntimeError(
                        "pending task metadata must be an object during outcome reconciliation"
                    )
                # The exact execution task is terminal even when the broader Goal
                # remains open for post-acquisition cognition/delivery.
                task["status"] = execution_task_status
                task["updated_ms"] = timestamp_ms
                task["metadata"] = {
                    **task_metadata,
                    "execution_outcome_id": validated.outcome_id,
                    "execution_outcome_fingerprint": fingerprint,
                    "execution_outcome_status": outcome.status,
                    "execution_evidence_ids": list(outcome.evidence_ids),
                    "retryable_safe_read": retryable_safe_read,
                    "completion_qualification_required": qualification["required"],
                    "completion_qualification_established": qualification["established"],
                }
                matched_pending += 1

            if is_retained_outcome:
                retained_summary = context["evidence_summary"]["execution_outcome"]
                context.clear()
                context.update(prior_context)
                summary = context.setdefault("evidence_summary", {})
                history = [item for item in summary.get("retained_execution_outcomes", []) if item.get("outcome_id") != validated.outcome_id]
                summary["retained_execution_outcomes"] = [*history, retained_summary][-8:]
            if context.get("metadata", {}).get("retained_work_activities"):
                # Per-request Evidence is already exact-bound above. Reconcile
                # every preserved/current request without replacing Goal meaning.
                for item in referenced_evidence:
                    state.update_pending_task_status_for_request_id(request_id=item.request_id, status=item.status)
                remaining = context.get("metadata", {}).get("remaining_request_ids", [])
                if remaining:
                    context["status"] = "running"
                    context["commitment_state"] = commitment_state_for_status("running")
                    context["plan_status"] = "running"

            results.append(
                {
                    "goal_id": outcome.goal_id,
                    "status": outcome.status,
                    "work_status": lifecycle_status,
                    "outcome_id": validated.outcome_id,
                    "applied": True,
                    "completion_qualification_required": qualification["required"],
                    "completion_qualification_established": qualification["established"],
                    "pending_records_updated": matched_pending,
                }
            )
        state._persist_task_contexts_if_enabled()
    except Exception:
        state._pending_tasks = pending_backup
        state._task_contexts = contexts_backup
        raise
    state._record_execution_outcome_tool_evidence(validated)
    state.last_activity_ms = timestamp_ms
    return results


def completion_qualification_summary(
    bundle: ExecutionOutcomeBundle,
    outcome: Any,
) -> dict[str, Any]:
    return goal_completion_qualification_summary(bundle, outcome)


def reconcile_communicative_goal_completion(
    state: Any,
    sid: str | None,
    goal_ids: list[str],
    *,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Close Goals only from model-authorized communication actually delivered.

    Fast Planner can complete a no-Work speech Goal before GA has canonical IDs;
    SC can complete a Planner-established answer need only after playback.  For
    information Goals, delivery alone is insufficient: the delivered act must
    cite exact trusted execution Evidence already recorded on that Goal.  This
    boundary performs lifecycle reconciliation only; Planner/SC own semantic
    eligibility and wording, while Runtime/Evidence own factual truth.
    """

    if not state.enabled:
        return []
    evidence = dict(metadata or {})
    source = " ".join(str(evidence.get("source") or "").strip().split())
    fast_delivery = source == "fast_planner_communicative_completion"
    social_delivery = source == "social_cognition_communicative_completion"
    if not (fast_delivery or social_delivery):
        return []
    if (
        fast_delivery
        and str(evidence.get("delivery_role") or "") != "complete_response"
    ):
        return []
    normalized_sid = " ".join(str(sid or "").strip().split())
    delivery_id = " ".join(
        str(
            evidence.get("speech_event_id")
            or evidence.get("fast_activity_id")
            or evidence.get("interaction_id")
            or ""
        ).strip().split()
    )
    evidence_ref = (
        f"communicative_delivery:{delivery_id}"
        if delivery_id
        else "communicative_delivery:delivered"
    )
    delivered_evidence_refs = {
        " ".join(str(value or "").strip().split())
        for value in evidence.get("evidence_refs") or []
        if str(value or "").strip()
    }
    results: list[dict[str, Any]] = []
    changed = False
    now = _now_ms()
    for raw_goal_id in goal_ids:
        goal_id = " ".join(str(raw_goal_id or "").strip().split())
        if not goal_id:
            continue
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            results.append(
                {
                    "goal_id": goal_id,
                    "changed": False,
                    "reason": "unknown_goal",
                }
            )
            continue
        if normalized_sid:
            related_sids = {
                " ".join(str(item or "").strip().split())
                for item in context.get("related_sids") or []
                if str(item or "").strip()
            }
            if related_sids and normalized_sid not in related_sids:
                results.append(
                    {
                        "goal_id": goal_id,
                        "changed": False,
                        "reason": "delivery_turn_does_not_match_goal",
                    }
                )
                continue
        goal = state._semantic_goal_from_context(context)
        goal_metadata = goal.metadata if isinstance(goal.metadata, dict) else {}
        output_mode = str(goal_metadata.get("output_mode") or "").strip()
        if output_mode == "information":
            if not social_delivery:
                results.append(
                    {
                        "goal_id": goal_id,
                        "changed": False,
                        "reason": "goal_requires_evidence_bound_social_delivery",
                    }
                )
                continue
            evidence_summary = context.get("evidence_summary")
            execution_outcome = (
                evidence_summary.get("execution_outcome")
                if isinstance(evidence_summary, dict)
                else None
            )
            execution_evidence_refs = {
                " ".join(str(value or "").strip().split())
                for value in (
                    execution_outcome.get("evidence_ids")
                    if isinstance(execution_outcome, dict)
                    else []
                ) or []
                if str(value or "").strip()
            }
            if (
                not isinstance(execution_outcome, dict)
                or str(execution_outcome.get("status") or "").strip()
                != "completed"
                or not delivered_evidence_refs.intersection(
                    execution_evidence_refs
                )
            ):
                results.append(
                    {
                        "goal_id": goal_id,
                        "changed": False,
                        "reason": "information_delivery_lacks_committed_execution_evidence",
                    }
                )
                continue
        elif output_mode != "speech":
            results.append(
                {
                    "goal_id": goal_id,
                    "changed": False,
                    "reason": "goal_requires_nontrivial_completion_evidence",
                }
            )
            continue
        previous = state._goal_responsibility_status(context)
        if previous != "open":
            results.append(
                {
                    "goal_id": goal_id,
                    "previous_status": previous,
                    "responsibility_status": previous,
                    "changed": False,
                    "reason": "responsibility_already_terminal",
                }
            )
            continue

        state._set_goal_responsibility_status(
            context,
            "satisfied",
            source=source,
            evidence_refs=[evidence_ref],
        )
        context["status"] = "done"
        context["commitment_state"] = "completed"
        context["plan_status"] = "done"
        context["updated_ms"] = now
        evidence_summary = context.get("evidence_summary")
        if not isinstance(evidence_summary, dict):
            evidence_summary = {}
        evidence_summary["communicative_completion"] = {
            **evidence,
            "evidence_ref": evidence_ref,
            "goal_id": goal_id,
        }
        context["evidence_summary"] = evidence_summary
        changed = True
        results.append(
            {
                "goal_id": goal_id,
                "previous_status": previous,
                "responsibility_status": "satisfied",
                "work_status": "done",
                "changed": True,
                "evidence_ref": evidence_ref,
            }
        )

    if changed:
        state._persist_task_contexts_if_enabled()
        state.last_activity_ms = now
    return results


def reconcile_execution_outcome_responsibilities(
    state: Any,
    bundle: ExecutionOutcomeBundle,
    *,
    sid: str | None,
) -> list[dict[str, Any]]:
    """Reconcile current Responsibility truth from trusted execution evidence.

    A completed execution is evidence, not Goal truth by itself. This explicit
    boundary performs the current satisfaction judgment after the immutable
    outcome has already been recorded. Non-completed Work leaves the Goal open
    so later evidence, replanning, or provider changes may still advance it.
    """

    if not state.enabled:
        return []
    validated = ExecutionOutcomeBundle.model_validate(bundle)
    results: list[dict[str, Any]] = []
    changed = False
    for outcome in validated.goal_outcomes:
        context = state._task_context_by_goal_id(outcome.goal_id)
        if context is None:
            raise ValueError(
                "responsibility reconciliation references unknown Goal: "
                f"{outcome.goal_id}"
            )
        evidence_summary = context.get("evidence_summary")
        if not isinstance(evidence_summary, dict):
            raise ValueError(
                "responsibility reconciliation requires recorded execution evidence"
            )
        recorded = evidence_summary.get("execution_outcome")
        if (
            not isinstance(recorded, dict)
            or recorded.get("outcome_id") != validated.outcome_id
            or recorded.get("outcome_fingerprint") != execution_outcome_fingerprint(validated)
        ):
            raise ValueError(
                "responsibility reconciliation requires the exact recorded outcome"
            )

        previous = state._goal_responsibility_status(context)
        if previous in {"cancelled", "refused", "superseded"}:
            results.append({
                "goal_id": outcome.goal_id,
                "previous_status": previous,
                "responsibility_status": previous,
                "changed": False,
                "reason": "semantic_terminal_state_preserved",
            })
            continue

        qualification = completion_qualification_summary(
            validated, outcome
        )
        completion_established = bool(
            outcome.status == "completed"
            and not outcome.requires_planner_continuation
            and (
                not qualification["required"]
                or qualification["established"]
            )
        )
        current = "satisfied" if completion_established else "open"
        if current != previous:
            state._set_goal_responsibility_status(
                context,
                current,
                source="execution_outcome_reconciliation",
                evidence_refs=[validated.outcome_id, *outcome.evidence_ids],
            )
            context["updated_ms"] = _now_ms()
            changed = True
        results.append({
            "goal_id": outcome.goal_id,
            "previous_status": previous,
            "responsibility_status": current,
            "changed": current != previous,
            "execution_status": outcome.status,
            "requires_planner_continuation": outcome.requires_planner_continuation,
            "completion_qualification_required": qualification["required"],
            "completion_qualification_established": qualification["established"],
            "completion_qualifications": qualification["qualifications"],
        })

    if changed:
        state._persist_task_contexts_if_enabled()
        state.last_activity_ms = _now_ms()
    return results


def apply_reflection_resolution(
    state: Any,
    resolution: ReflectionResolution | dict[str, Any],
    *,
    sid: str | None,
) -> list[dict[str, Any]]:
    """Apply bounded future adaptation without rewriting Goal history.

    Responsibility-control actions are valid only while the Responsibility
    remains open. Evidence-bound ``experience``/``calibration`` proposals may
    also learn from terminal history because learning forward does not reopen
    or mutate that history. Online proposals remain non-durable advisory
    Memory; shared/systemic adaptation stays outside this path.
    """

    if not state.enabled:
        return []
    reflected = (
        resolution
        if isinstance(resolution, ReflectionResolution)
        else ReflectionResolution.model_validate(resolution)
    )
    results: list[dict[str, Any]] = []
    memory_entries: list[MemoryEntry] = []
    now = _now_ms()
    responsibility_actions = {"replan", "clarify", "correct_user"}

    for goal_id in reflected.goal_ids:
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            raise ValueError(f"reflection references unknown Goal: {goal_id}")

        evidence_summary = context.get("evidence_summary")
        recorded = (
            evidence_summary.get("execution_outcome")
            if isinstance(evidence_summary, dict)
            else None
        )
        if not isinstance(recorded, dict):
            raise ValueError("reflection requires recorded execution evidence")
        recorded_outcome_id = str(recorded.get("outcome_id") or "").strip()
        allowed_refs = {recorded_outcome_id}
        allowed_refs.update(
            str(item).strip()
            for item in recorded.get("evidence_ids") or []
            if str(item).strip()
        )
        if reflected.actions and (
            not recorded_outcome_id
            or recorded_outcome_id not in reflected.evidence_refs
        ):
            raise ValueError(
                "reflection actions require the recorded execution outcome reference"
            )
        unknown_refs = set(reflected.evidence_refs) - allowed_refs
        if unknown_refs:
            raise ValueError(
                "reflection references evidence outside the recorded outcome: "
                + ",".join(sorted(unknown_refs))
            )

        responsibility_status = state._goal_responsibility_status(context)
        responsibility_open = responsibility_status == "open"
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        history = metadata.get("reflection_history")
        if not isinstance(history, list):
            history = []
        current_reasons = set(reflected.reason_codes)
        repeated_pattern = any(
            current_reasons.intersection(
                str(item).strip()
                for item in previous.get("reason_codes") or []
                if str(item).strip()
            )
            for previous in history
            if isinstance(previous, dict)
        )

        advisory_actions: list[str] = []
        rejected_actions: list[str] = []
        for action in reflected.actions:
            if action in responsibility_actions:
                if not responsibility_open:
                    rejected_actions.append(action)
                    continue
                advisory_actions.append(action)

        planner_advisory: dict[str, Any] | None = None
        if advisory_actions:
            planner_advisory = {
                "opportunity_id": reflected.opportunity_id,
                "goal_id": goal_id,
                "actions": advisory_actions,
                "correction_text": (
                    reflected.correction_text
                    if "correct_user" in advisory_actions
                    else ""
                ),
                "reason_codes": list(reflected.reason_codes),
                "reason_summary": reflected.reason_summary,
                "evidence_refs": list(reflected.evidence_refs),
                "authority": "planner_advisory_only",
            }

        applied_actions: list[str] = []
        promoted = 0
        if "propose_memory" in reflected.actions:
            for candidate in reflected.memory_candidates:
                memory_entries.append(
                    MemoryEntry(
                        scope=candidate.scope,
                        kind=candidate.kind,
                        text=candidate.text,
                        confidence=candidate.confidence,
                        source_sids=[sid] if sid else [],
                        source_turn_ids=[str(recorded.get("turn_id") or "")]
                        if str(recorded.get("turn_id") or "").strip()
                        else [],
                        expires_ms=(
                            now + state.reflection_memory_max_ttl_sec * 1000.0
                        ),
                        persistence_policy="ephemeral",
                    )
                )
                promoted += 1
            if promoted:
                applied_actions.append("propose_memory")

        history.append({
            "opportunity_id": reflected.opportunity_id,
            "actions": list(reflected.actions),
            "planner_advisory_actions": advisory_actions,
            "applied_actions": applied_actions,
            "rejected_actions": rejected_actions,
            "reason_codes": list(reflected.reason_codes),
            "evidence_refs": list(reflected.evidence_refs),
            "memory_candidates": len(reflected.memory_candidates),
            "memory_promoted": promoted,
            "responsibility_status": responsibility_status,
            "terminal_history_learning": bool(
                not responsibility_open and promoted
            ),
            "ts_ms": now,
        })
        context["metadata"] = {
            **metadata,
            "reflection_history": history[-12:],
        }
        if advisory_actions or applied_actions or responsibility_open:
            context["updated_ms"] = now

        result: dict[str, Any] = {
            "goal_id": goal_id,
            "applied": bool(applied_actions),
            "actions": list(reflected.actions),
            "planner_advisory_actions": advisory_actions,
            "applied_actions": applied_actions,
            "rejected_actions": rejected_actions,
            "memory_promoted": promoted,
            "repeated_pattern": repeated_pattern,
            "responsibility_status": responsibility_status,
            "future_adaptation": bool(applied_actions),
            "terminal_history_learning": bool(
                not responsibility_open and promoted
            ),
        }
        if planner_advisory is not None:
            result["planner_advisory"] = planner_advisory
        if rejected_actions and not applied_actions:
            result["reason"] = "reflection_terminal_responsibility_action_rejected"
        results.append(result)

    if memory_entries:
        state._memory_store.add_many(memory_entries)
    if results:
        state._persist_task_contexts_if_enabled()
        state.last_activity_ms = now
    return results


def derive_execution_cognitive_opportunities(
    state: Any,
    bundle: ExecutionOutcomeBundle,
    *,
    situation_digest: str = "",
) -> list[CognitiveOpportunity]:
    """Derive ephemeral cognition opportunities from trusted outcome evidence.

    The result is intentionally not persisted. An opportunity is merely a
    bounded signal that current authoritative state changed enough that
    another cognitive act may be useful. The referenced Goal and Evidence
    remain authoritative in their existing owners.
    """

    if not state.enabled:
        return []
    validated = ExecutionOutcomeBundle.model_validate(bundle)
    opportunities: list[CognitiveOpportunity] = []
    for outcome in validated.goal_outcomes:
        qualification = completion_qualification_summary(
            validated, outcome
        )
        if outcome.status == "completed" and (
            not qualification["required"]
            or qualification["established"]
        ):
            continue
        context = state._task_context_by_goal_id(outcome.goal_id)
        if context is None:
            continue
        if state._goal_responsibility_status(context) != "open":
            continue
        evidence_summary = context.get("evidence_summary")
        if not isinstance(evidence_summary, dict):
            continue
        recorded = evidence_summary.get("execution_outcome")
        if (
            not isinstance(recorded, dict)
            or recorded.get("outcome_id") != validated.outcome_id
        ):
            continue
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        retryable_safe_read = metadata.get("retryable_safe_read") is True
        mode = "fast" if retryable_safe_read else "slow"
        qualification_reason_codes = [
            str(reason)
            for row in qualification["qualifications"]
            for reason in row.get("reason_codes", [])
            if str(reason).strip()
        ]
        reason_codes = (
            list(outcome.reason_codes)
            or qualification_reason_codes
            or [
                (
                    "completion_evidence_insufficient"
                    if outcome.status == "completed"
                    else f"execution_{outcome.status}"
                )
            ]
        )
        opportunities.append(
            CognitiveOpportunity.create(
                trigger="execution_outcome",
                goal_ids=[outcome.goal_id],
                evidence_refs=[validated.outcome_id, *outcome.evidence_ids],
                reason_codes=reason_codes,
                recommended_cognition=mode,
                situation_digest=situation_digest,
            )
        )
    return opportunities
