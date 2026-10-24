"""Planning metadata, time conditions and restart revalidation for ConversationStateManager.

The functions take the ``ConversationStateManager`` as ``state``. They record a
Plan's metadata and time conditions on its Goals, report due conditions and
restart-revalidation candidates, and record each interaction response.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from shared.chromie_contracts.situation import CognitiveOpportunity, GoalTimeCondition
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.semantic_task import InformationGap
from orchestrator.runtime import goal_outcome_state

from orchestrator.runtime.conversation_state import _now_ms

logger = logging.getLogger("chromie.orchestrator.conversation_state")


def record_planning_metadata(
    state: Any,
    metadata: dict[str, Any],
    *,
    confirmation_authorized: bool = False,
) -> None:
    planning_result = str(metadata.get("planning_result") or "").strip()
    if not planning_result:
        return
    task_id = str(metadata.get("task_id") or "").strip()
    context = state._task_context_by_id(task_id) if task_id else state._current_task_context()
    if context is None:
        return
    if metadata.get("retained_work_reconciliation_only") is True:
        current_metadata = context.get("metadata")
        if not isinstance(current_metadata, dict):
            current_metadata = {}
        context["metadata"] = {
            **current_metadata,
            "last_retained_work_reconciliation_plan_id": str(
                metadata.get("canonical_plan_id") or ""
            ),
            "last_retained_work_reconciliation_ms": _now_ms(),
        }
        state._persist_task_contexts_if_enabled()
        return
    try:
        proposed_goal_version = int(metadata.get("goal_version") or context.get("goal_version") or 1)
    except (TypeError, ValueError):
        proposed_goal_version = 1
    current_goal_version = max(1, int(context.get("goal_version") or 1))
    if proposed_goal_version != current_goal_version:
        meta = context.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        context["metadata"] = {
            **meta,
            "stale_planning_result_rejected": {
                "planning_result": planning_result,
                "proposed_goal_version": proposed_goal_version,
                "current_goal_version": current_goal_version,
                "ts_ms": _now_ms(),
            },
        }
        return

    raw_gaps = metadata.get("information_gaps")
    gaps: list[dict[str, Any]] = []
    if isinstance(raw_gaps, list):
        for item in raw_gaps:
            if not isinstance(item, dict):
                continue
            try:
                gap = InformationGap.model_validate(item)
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed planning information gap task_id=%s error=%s",
                    context.get("task_id"),
                    exc,
                )
                continue
            if not gap.resolved:
                gaps.append(gap.model_dump(mode="json", exclude_none=True))

    if planning_result == "needs_clarification":
        context["status"] = "waiting_for_user"
        context["commitment_state"] = "waiting_for_user"
        context["plan_status"] = "blocked_on_user"
        context["open_information_gaps"] = gaps
        context["pending_questions"] = [
            str(item.get("description") or "")
            for item in gaps
            if item.get("blocking") is not False
        ][:4]
    elif planning_result == "needs_context":
        context["status"] = "needs_context"
        context["commitment_state"] = "evaluating"
        context["plan_status"] = "blocked_on_context"
        context["open_information_gaps"] = gaps
    elif planning_result in {"unavailable", "refused"}:
        context["status"] = "refused"
        context["commitment_state"] = "failed"
        context["plan_status"] = planning_result
        context["open_information_gaps"] = gaps
    elif planning_result in {
        "direct_capability",
        "composed_plan",
        "safe_adjustment",
        "alternative_plan",
        "mixed_plan",
    }:
        context["plan_version"] = max(0, int(context.get("plan_version") or 0)) + 1
        context["plan_status"] = "proposed"
        requires_confirmation = bool(
            not confirmation_authorized
            and (
                metadata.get("semantic_plan_confirmation_required")
                or metadata.get("confirmation_prompt")
                or planning_result == "alternative_plan"
            )
        )
        context["status"] = (
            "awaiting_confirmation" if requires_confirmation else "planning"
        )
        context["commitment_state"] = (
            "waiting_for_user" if requires_confirmation else "evaluating"
        )
        context["open_information_gaps"] = []
        confirmation_prompt = " ".join(
            str(metadata.get("confirmation_prompt") or "").strip().split()
        )
        context["pending_questions"] = (
            [confirmation_prompt] if confirmation_prompt else []
        )
        planned_capabilities = metadata.get("planned_capabilities")
        if isinstance(planned_capabilities, list):
            context["plan_summary"] = {
                "result": planning_result,
                "capabilities": [item for item in planned_capabilities if isinstance(item, dict)][:12],
            }
        if requires_confirmation:
            context["confirmation"] = {
                "status": "pending",
                "goal_version": current_goal_version,
                "plan_version": context["plan_version"],
                "prompt": confirmation_prompt,
            }
    else:
        return

    context["updated_ms"] = _now_ms()
    meta = context.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    context["metadata"] = {
        **meta,
        "last_planning_result": planning_result,
        "last_planning_goal_version": current_goal_version,
    }
    state._persist_task_contexts_if_enabled()


def planner_reentry_responsibilities(
    state: Any,
    *,
    result_metadata: dict[str, Any] | None,
    goal_id: str,
) -> list[dict[str, Any]]:
    """Retain exact UMI provenance for later state-driven Planner re-entry.

    This is not a second Responsibility authority. The canonical Goal remains
    the owed outcome; these immutable source records let a later trusted Runtime,
    Situation, or time transition reactivate the same Planner without fabricating
    a new UserTurn or reconstructing WHAT from Goal prose. Restart revalidation is
    one consumer of the same bounded provenance.
    """

    if not isinstance(result_metadata, dict):
        return []
    interpretation = result_metadata.get("user_meaning_interpretation")
    if not isinstance(interpretation, dict):
        return []
    raw_responsibilities = interpretation.get("responsibilities")
    if not isinstance(raw_responsibilities, list):
        return []
    context = state._task_context_by_goal_id(goal_id)
    if context is None:
        return []
    semantic_goal = context.get("semantic_goal")
    if not isinstance(semantic_goal, dict):
        return []
    source_refs = {
        str(item).strip()
        for item in semantic_goal.get("source_responsibility_refs") or []
        if str(item).strip()
    }
    if not source_refs:
        return []
    retained: list[dict[str, Any]] = []
    for item in raw_responsibilities:
        if not isinstance(item, dict):
            continue
        if str(item.get("local_ref") or "").strip() not in source_refs:
            continue
        retained.append(state._json_safe(item))
    return retained


def record_planner_time_conditions(
    state: Any,
    result_metadata: dict[str, Any],
) -> int:
    """Bind Planner-authored time semantics to current Goal provenance.

    The canonical Plan carries only Planner-owned Goal/time semantics.  This
    owner adds current Plan identity and original UMI Responsibility refs at
    persistence time; it never derives time from Goal prose.
    """

    raw_plan = result_metadata.get("canonical_plan")
    if not isinstance(raw_plan, dict):
        return 0
    try:
        plan = CanonicalPlan.model_validate(raw_plan)
    except ValidationError:
        return 0
    if not plan.time_conditions:
        return 0

    canonical_fingerprint = str(
        result_metadata.get("canonical_plan_fingerprint") or ""
    ).strip()
    language = state._compact_text(
        str(result_metadata.get("language") or "auto"), limit=64
    )
    for goal_id in plan.goal_ids:
        context = state._task_context_by_goal_id(goal_id)
        if context is None or state._goal_responsibility_status(context) != "open":
            continue
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        responsibilities = planner_reentry_responsibilities(
            state,
            result_metadata=result_metadata,
            goal_id=goal_id,
        )
        context["metadata"] = {
            **metadata,
            "canonical_plan_id": plan.plan_id,
            **(
                {"canonical_plan_fingerprint": canonical_fingerprint}
                if canonical_fingerprint
                else {}
            ),
            **(
                {
                    "planner_reentry_responsibilities": responsibilities,
                    "planner_reentry_language": language,
                }
                if responsibilities
                else {}
            ),
        }
        context["updated_ms"] = _now_ms()

    accepted = 0
    for planned in plan.time_conditions:
        context = state._task_context_by_goal_id(planned.goal_id)
        if context is None or state._goal_responsibility_status(context) != "open":
            continue
        goal = state._semantic_goal_from_context(context)
        condition = GoalTimeCondition(
            condition_id=planned.condition_id,
            goal_id=planned.goal_id,
            due_at_ms=planned.due_at_ms,
            source_plan_id=plan.plan_id,
            source_responsibility_refs=list(goal.source_responsibility_refs),
            reason_code=planned.reason_code,
        )
        if state.register_goal_time_condition(condition):
            accepted += 1
    if accepted:
        state._persist_task_contexts_if_enabled()
    return accepted


def register_goal_time_condition(
    state: Any,
    condition: GoalTimeCondition | dict[str, Any],
) -> bool:
    """Persist one structured Planner-authored wake condition on an open Goal.

    Host never parses a Goal sentence into time semantics. The caller must supply
    a typed condition already bound to the current canonical Plan and original
    Responsibility refs. Revisions supersede stale conditions mechanically.
    """

    validated = (
        condition
        if isinstance(condition, GoalTimeCondition)
        else GoalTimeCondition.model_validate(condition)
    )
    context = state._task_context_by_goal_id(validated.goal_id)
    if context is None or state._goal_responsibility_status(context) != "open":
        return False
    metadata = context.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if str(metadata.get("canonical_plan_id") or "").strip() != validated.source_plan_id:
        return False
    goal = state._semantic_goal_from_context(context)
    source_refs = {str(item).strip() for item in goal.source_responsibility_refs}
    if not set(validated.source_responsibility_refs).issubset(source_refs):
        return False
    existing = metadata.get("time_conditions")
    if not isinstance(existing, list):
        existing = []
    payload = validated.model_dump(mode="json")
    retained = [
        item
        for item in existing
        if isinstance(item, dict)
        and str(item.get("condition_id") or "") != validated.condition_id
    ]
    retained.append(payload)
    context["metadata"] = {**metadata, "time_conditions": retained[-16:]}
    context["updated_ms"] = _now_ms()
    state._persist_task_contexts_if_enabled()
    return True


def due_time_condition_opportunities(
    state: Any,
    *,
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Atomically consume due structured conditions and emit Planner readiness.

    Conditions are discarded when their Goal/Plan binding is no longer current.
    A returned item carries source provenance plus an ephemeral
    ``CognitiveOpportunity``; it does not choose an Activity or response.
    """

    now = int(_now_ms() if now_ms is None else now_ms)
    due: list[dict[str, Any]] = []
    changed = False
    for context in state._active_task_contexts():
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            continue
        raw_conditions = metadata.get("time_conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            continue
        goal = state._semantic_goal_from_context(context)
        current_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
        keep: list[dict[str, Any]] = []
        for raw in raw_conditions:
            try:
                condition = GoalTimeCondition.model_validate(raw)
            except (TypeError, ValueError):
                changed = True
                continue
            if (
                condition.goal_id != goal.goal_id
                or condition.source_plan_id != current_plan_id
                or state._goal_responsibility_status(context) != "open"
            ):
                changed = True
                continue
            if condition.due_at_ms > now:
                keep.append(condition.model_dump(mode="json"))
                continue
            changed = True
            opportunity = CognitiveOpportunity.create(
                trigger="time_condition",
                goal_ids=[condition.goal_id],
                reason_codes=[condition.reason_code],
                recommended_cognition="fast",
            )
            due.append(
                {
                    "condition": condition.model_dump(mode="json"),
                    "opportunity": opportunity.prompt_projection(),
                    "source_text": str(
                        goal.source_text
                        or context.get("last_meaningful_user_turn")
                        or ""
                    ).strip(),
                    "language": str(
                        metadata.get("planner_reentry_language") or "auto"
                    ).strip()
                    or "auto",
                    "responsibilities": [
                        state._json_safe(item)
                        for item in (
                            metadata.get("planner_reentry_responsibilities") or []
                        )
                        if isinstance(item, dict)
                    ],
                }
            )
        if len(keep) != len(raw_conditions):
            context["metadata"] = {**metadata, "time_conditions": keep}
            context["updated_ms"] = _now_ms()
    if changed:
        state._persist_task_contexts_if_enabled()
    return due


def next_time_condition_due_ms(state: Any) -> int | None:
    """Return the nearest durable due time without interpreting Goal text."""

    nearest: int | None = None
    for context in state._active_task_contexts():
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            continue
        current_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
        for raw in metadata.get("time_conditions") or []:
            try:
                condition = GoalTimeCondition.model_validate(raw)
            except (TypeError, ValueError):
                continue
            if condition.source_plan_id != current_plan_id:
                continue
            nearest = (
                condition.due_at_ms
                if nearest is None
                else min(nearest, condition.due_at_ms)
            )
    return nearest


def runtime_revalidation_candidates(state: Any) -> list[dict[str, Any]]:
    """Return bounded open Goals whose pre-restart Runtime binding is stale."""

    candidates: list[dict[str, Any]] = []
    for context in state._active_task_contexts():
        metadata = context.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("runtime_revalidation_required") is not True:
            continue
        semantic_goal = context.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            continue
        goal_id = str(semantic_goal.get("goal_id") or context.get("task_id") or "").strip()
        if not goal_id:
            continue
        planned_capabilities = metadata.get("planned_capabilities")
        if not isinstance(planned_capabilities, list):
            planned_capabilities = []
        capability_ids = list(
            dict.fromkeys(
                str(item.get("capability_id") or "").strip()
                for item in planned_capabilities
                if isinstance(item, dict)
                and str(item.get("capability_id") or "").strip()
            )
        )
        responsibilities = metadata.get("planner_reentry_responsibilities")
        if not isinstance(responsibilities, list):
            responsibilities = []
        candidates.append(
            {
                "goal_id": goal_id,
                "task_id": str(context.get("task_id") or ""),
                "source_text": str(semantic_goal.get("source_text") or context.get("last_meaningful_user_turn") or "").strip(),
                "language": str(metadata.get("planner_reentry_language") or "auto").strip() or "auto",
                "capability_ids": capability_ids,
                "responsibilities": [
                    state._json_safe(item)
                    for item in responsibilities
                    if isinstance(item, dict)
                ],
                "restored_ms": metadata.get("restored_ms"),
            }
        )
    return candidates


def goal_reentry_provenance(
    state: Any,
    goal_ids: list[str] | tuple[str, ...] | set[str],
) -> list[dict[str, Any]]:
    """Return retained Planner re-entry provenance for still-open Goals.

    Used when a trusted state transition (such as a shared stop that halted a
    sibling's Work) must re-enter the Planner for a Goal whose originating
    turn response is no longer at hand. Terminal or unknown Goals are omitted.
    """

    provenance: list[dict[str, Any]] = []
    wanted = {str(item).strip() for item in goal_ids if str(item).strip()}
    for context in state._active_task_contexts():
        semantic_goal = context.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            continue
        goal_id = str(semantic_goal.get("goal_id") or context.get("task_id") or "").strip()
        if goal_id not in wanted:
            continue
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        responsibilities = metadata.get("planner_reentry_responsibilities")
        provenance.append(
            {
                "goal_id": goal_id,
                "source_text": str(semantic_goal.get("source_text") or context.get("last_meaningful_user_turn") or "").strip(),
                "language": str(metadata.get("planner_reentry_language") or "auto").strip() or "auto",
                "responsibilities": [
                    state._json_safe(item)
                    for item in (responsibilities if isinstance(responsibilities, list) else [])
                    if isinstance(item, dict)
                ],
            }
        )
    return provenance


def complete_runtime_revalidation(
    state: Any,
    goal_ids: list[str],
    *,
    source_ref: str,
) -> list[str]:
    """Invalidate stale pre-restart Work only after fresh provider truth.

    Provider/catalog state is authoritative for its Runtime domain but is not
    execution/world Evidence. Retain the source reference without promoting it
    into the Evidence namespace.
    """

    completed: list[str] = []
    now = _now_ms()
    for goal_id in dict.fromkeys(str(item).strip() for item in goal_ids if str(item).strip()):
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            continue
        metadata = context.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("runtime_revalidation_required") is not True:
            continue
        previous_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
        previous_fingerprint = str(metadata.get("canonical_plan_fingerprint") or "").strip()
        previous_capabilities = metadata.get("planned_capabilities")
        updated = dict(metadata)
        updated.pop("runtime_revalidation_required", None)
        for key in (
            "canonical_plan_id",
            "canonical_plan_fingerprint",
            "request_ids",
            "remaining_request_ids",
            "request_statuses",
            "planned_capabilities",
            "confirmation_id",
            "confirmation_request_ids",
            "confirmation_pending",
        ):
            updated.pop(key, None)
        if previous_plan_id:
            updated["recovery_previous_canonical_plan_id"] = previous_plan_id
        if previous_fingerprint:
            updated["recovery_previous_canonical_plan_fingerprint"] = previous_fingerprint
        if isinstance(previous_capabilities, list) and previous_capabilities:
            updated["recovery_previous_planned_capabilities"] = state._json_safe(previous_capabilities)
        updated["runtime_revalidation_source_ref"] = str(source_ref or "").strip()
        updated["runtime_revalidated_ms"] = now
        context["metadata"] = updated
        if str(context.get("plan_status") or "") == "revalidation_required":
            context["plan_status"] = "revalidated"
        if str(context.get("status") or "") == "recoverable":
            context["status"] = "planning"
            context["commitment_state"] = "evaluating"
        context["updated_ms"] = now
        completed.append(goal_id)
    if completed:
        state._persist_task_contexts_if_enabled()
        state.last_activity_ms = now
    return completed


def record_interaction_response(
    state: Any,
    sid: str | None,
    result: Any,
    *,
    confirmed_request_ids: set[str] | None = None,
    bind_planned_execution: bool = True,
) -> None:
    """Record assistant speech and, when dispatched, planned execution bindings.

    Preview and other planning-only callers retain the assistant turn and
    canonical Goal/plan metadata, but must not turn an undispatched request
    into authoritative Runtime Work.  Runtime-backed callers keep the
    default and reconcile the resulting bindings from execution receipts.
    """
    if not state.enabled:
        return

    if hasattr(result, "model_dump"):
        data = result.model_dump(mode="json")
    elif isinstance(result, dict):
        data = result
    else:
        data = {}

    result_metadata = data.get("metadata")
    interaction_id = str(data.get("interaction_id") or "").strip()
    turn_id = ""
    canonical_plan_id = ""
    canonical_plan_fingerprint = ""
    goal_outcomes: dict[str, dict[str, Any]] = {}
    planner_reentry_language = "auto"
    if isinstance(result_metadata, dict):
        planner_reentry_language = str(result_metadata.get("language") or "auto")
        state._record_tool_evidence(result_metadata)
        turn_id = str(result_metadata.get("turn_id") or "").strip()
        canonical_plan_id = str(
            result_metadata.get("canonical_plan_id") or ""
        ).strip()
        canonical_plan_fingerprint = str(
            result_metadata.get("canonical_plan_fingerprint") or ""
        ).strip()
        record_planning_metadata(
            state,
            result_metadata,
            confirmation_authorized=bool(confirmed_request_ids),
        )
        record_planner_time_conditions(state, result_metadata)
        goal_outcomes = goal_outcome_state.canonical_goal_outcomes(result_metadata)
        goal_outcome_state.record_nonexecuting_goal_outcomes(state, goal_outcomes)
        if isinstance(result_metadata.get("planning_commit"), dict):
            for goal_id in result_metadata.get("goal_ids") or []:
                goal_context = state._task_context_by_goal_id(str(goal_id))
                if goal_context is not None:
                    goal_context.setdefault("metadata", {})["retained_work_activities"] = [
                        state._json_safe(item) for item in result_metadata.get("retained_work_activities", [])
                        if goal_id in item.get("source_goal_ids", [])
                    ]

    speech_parts: list[str] = []
    for key in ("speak_immediate", "speak_after", "speech"):
        for item in data.get(key, []) or []:
            item_metadata = (
                item.get("metadata")
                if isinstance(item, dict)
                else getattr(item, "metadata", None)
            )
            if isinstance(item_metadata, dict) and item_metadata.get("wording_owner") == "social_cognition":
                # SC utterances enter dialogue only through the playback-qualified
                # recorder. This call may merely bind a proposed response to Work.
                continue
            if (
                isinstance(item_metadata, dict)
                and item_metadata.get("reuse_current_turn_speech") is True
            ):
                # The Fast Communicative Activity was recorded when its
                # playback completed. This response only reuses that exact
                # event as an execution barrier; it is not a second turn.
                continue
            text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            text = state._compact_text(text)
            if text:
                speech_parts.append(text)
    if speech_parts:
        assistant_turn_metadata: dict[str, Any] = {"source": "agent_result"}
        if isinstance(result_metadata, dict):
            result_source = str(result_metadata.get("source") or "").strip()
            if (
                result_source == "evidence_bound_tool_result_interpretation"
                and result_metadata.get("full_tool_result_retained") is True
            ):
                assistant_turn_metadata = {
                    "source": result_source,
                    "evidence_bound": True,
                    "phase": "post_execution",
                    "source_goal_ids": state._string_list(
                        result_metadata.get("source_goal_ids")
                    ),
                    "canonical_plan_id": canonical_plan_id,
                }
        state.record_assistant_turn(
            sid,
            " ".join(speech_parts),
            metadata=assistant_turn_metadata,
        )

    # A conversational Goal is not complete merely because Response
    # Composer produced text. Bind it to the concrete chromie.speak request
    # IDs generated from InteractionSpeech so only Capability Runtime evidence
    # can make that Goal terminal. Clarification speech is intentionally not
    # bound: its Goal must remain active while waiting for the user.
    if bind_planned_execution:
        speech_items = [
            item for item in (data.get("speech") or []) if isinstance(item, dict)
        ]
        for goal_id, outcome in goal_outcomes.items():
            if str(outcome.get("disposition") or "").strip().lower() != "respond":
                continue
            scoped_speech: list[dict[str, Any]] = []
            for item in speech_items:
                item_metadata = item.get("metadata")
                if not isinstance(item_metadata, dict):
                    continue
                if item_metadata.get("wording_owner") == "social_cognition" and goal_id not in state._string_list(
                    item_metadata.get("communication_completion_goal_ids")
                ):
                    # Relevant progress is not fulfillment of an answer. SC's
                    # exact need coverage selects the eligible communication
                    # Goals; actual Runtime delivery still completes them.
                    continue
                covered_goal_ids = state._string_list(
                    item_metadata.get("covers_goal_ids")
                )
                if goal_id in covered_goal_ids:
                    scoped_speech.append(item)
            request_ids = [
                str(item.get("id"))
                for item in scoped_speech
                if str(item.get("id") or "").strip()
            ]
            if not request_ids:
                continue
            goal_outcome_state.record_goal_pending_execution(
                state,
                sid=sid,
                goal_id=goal_id,
                status="scheduled",
                summary="chromie.speak",
                request_ids=request_ids,
                planning_result="respond",
                planned_capabilities=[
                    {
                        "capability_id": "chromie.speak",
                        "request_id": request_id,
                        "source_goal_ids": [goal_id],
                    }
                    for request_id in request_ids
                ],
                confirmation_pending=False,
                interaction_id=interaction_id,
                turn_id=turn_id,
                canonical_plan_id=canonical_plan_id,
                canonical_plan_fingerprint=canonical_plan_fingerprint,
                planner_reentry_responsibilities=(
                    planner_reentry_responsibilities(
                        state,
                        result_metadata=result_metadata,
                        goal_id=goal_id,
                    )
                ),
                planner_reentry_language=planner_reentry_language,
                planned_satisfaction=outcome.get("satisfaction"),
            )

    actions = data.get("actions", []) or data.get("capabilities", []) or []
    primary_actions: list[dict[str, Any]] = []
    for action in actions:
        if isinstance(action, dict):
            item = dict(action)
        else:
            item = {
                "request_id": getattr(action, "request_id", None),
                "capability_id": getattr(action, "capability_id", None) or getattr(action, "capability_id", None),
                "type": getattr(action, "type", None),
                "target": getattr(action, "target", None),
                "metadata": dict(getattr(action, "metadata", {}) or {}),
            }
        action_metadata = item.get("metadata")
        if not isinstance(action_metadata, dict):
            action_metadata = {}
        if action_metadata.get("auxiliary_plan_activity"):
            continue
        item["metadata"] = action_metadata
        primary_actions.append(item)

    if primary_actions and bind_planned_execution:
        planning_result = (
            str(result_metadata.get("planning_result") or "").strip()
            if isinstance(result_metadata, dict)
            else ""
        )
        confirmation_pending = bool(
            not confirmed_request_ids
            and isinstance(result_metadata, dict)
            and (
                result_metadata.get("semantic_plan_confirmation_required")
                or result_metadata.get("confirmation_prompt")
                or planning_result == "alternative_plan"
            )
        )
        pending_status = "awaiting_confirmation" if confirmation_pending else "scheduled"
        by_goal: dict[str, list[dict[str, Any]]] = {}
        unscoped: list[dict[str, Any]] = []
        for item in primary_actions:
            action_metadata = item.get("metadata") or {}
            goal_ids = state._string_list(action_metadata.get("source_goal_ids"))
            if not goal_ids:
                unscoped.append(item)
                continue
            for goal_id in goal_ids:
                by_goal.setdefault(goal_id, []).append(item)

        for goal_id, goal_actions in by_goal.items():
            request_ids = [
                str(item.get("request_id"))
                for item in goal_actions
                if item.get("request_id")
            ]
            summaries = [
                str(item.get("capability_id") or item.get("type") or item.get("target") or "action")
                for item in goal_actions[:3]
            ]
            planned_capabilities = [
                {
                    "capability_id": item.get("capability_id"),
                    "request_id": item.get("request_id"),
                    "args": state._json_safe(
                        item.get("args") if isinstance(item.get("args"), dict) else {}
                    ),
                    "timing": str(item.get("timing") or "sequential"),
                    "source_goal_ids": state._string_list(
                        (item.get("metadata") or {}).get("source_goal_ids")
                    ),
                    "safety_class": str(
                        (item.get("metadata") or {}).get("safety_class") or ""
                    ),
                    "retryable_safe_read": (
                        (item.get("metadata") or {}).get("retryable_safe_read")
                        is True
                    ),
                }
                for item in goal_actions
            ]
            goal_outcome_state.record_goal_pending_execution(
                state,
                sid=sid,
                goal_id=goal_id,
                status=pending_status,
                summary=", ".join(summaries),
                request_ids=request_ids,
                planning_result=planning_result,
                planned_capabilities=planned_capabilities,
                confirmation_pending=confirmation_pending,
                interaction_id=interaction_id,
                turn_id=turn_id,
                canonical_plan_id=canonical_plan_id,
                canonical_plan_fingerprint=canonical_plan_fingerprint,
                planner_reentry_responsibilities=(
                    planner_reentry_responsibilities(
                        state,
                        result_metadata=result_metadata,
                        goal_id=goal_id,
                    )
                ),
                planner_reentry_language=planner_reentry_language,
            )

        if unscoped:
            request_ids = [
                str(item.get("request_id"))
                for item in unscoped
                if item.get("request_id")
            ]
            action_summaries = [
                str(item.get("capability_id") or item.get("type") or item.get("target") or "action")
                for item in unscoped[:3]
            ]
            state.record_pending_task(
                sid=sid,
                task_type="robot_action",
                status=pending_status,
                summary=", ".join(action_summaries),
                metadata={
                    "action_count": len(unscoped),
                    "request_ids": request_ids,
                    "remaining_request_ids": list(request_ids),
                    "planning_result": planning_result,
                    "confirmation_pending": confirmation_pending,
                },
            )

    # Native InteractionResponse keeps Memory mutations in metadata so the
    # shared wire contract remains narrow. Historical top-level
    # ``memory_updates`` is intentionally not a compatibility input.
    metadata = data.get("metadata")
    record_memory_updates(
        state, sid, metadata.get("memory_updates", []) or [] if isinstance(metadata, dict) else [],
    )


def record_memory_updates(state: Any, sid: str | None, memory_updates: list[Any]) -> None:
    """Apply the Memory mutations an InteractionResponse carries in its metadata.

    Social Cognition's own Memory decision is also applied when its words are delivered,
    not only when its response ends the turn (live 2026-10-24: a preference agreed at
    ingress was lost because the turn's Planner response was the one recorded). One
    Memory ID per entry makes a second application idempotent.
    """
    if not state.enabled:
        return
    for update in memory_updates:
        if not isinstance(update, dict):
            continue
        update_type = str(update.get("type") or "")
        if update_type in {"extracted_memory", "memory_entry", "memory"}:
            state._store_explicit_memory_entries(
                state._memory_extractor.extract_explicit_entries(
                    update.get("value"),
                    sid=sid,
                )
            )
            continue
        if update_type == "durable_memory_forget":
            value = update.get("value")
            key = str(update.get("key") or "").strip()
            if (
                key
                and state._authorized_durable_mutation(
                    value, operation="forget"
                )
                and str(value.get("key") or "").strip() == key
            ):
                state.forget_durable_memory(key=key)
            continue
        if update_type == "durable_memory_clear":
            if state._authorized_durable_mutation(
                update.get("value"), operation="clear_profile"
            ):
                state.clear_durable_memory()
            continue
        if update_type not in {"pending_task", "task_status", "active_task"}:
            continue
        value = update.get("value")
        if isinstance(value, dict):
            state.record_pending_task(
                sid=sid,
                task_type=str(value.get("type") or update.get("key") or "task"),
                status=str(value.get("status") or "pending"),
                summary=str(value.get("summary") or value.get("description") or value.get("type") or "task"),
                metadata=value,
            )
