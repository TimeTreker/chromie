"""Goal cancellation and replacement state transitions for ConversationStateManager.

The functions take the ``ConversationStateManager`` as ``state`` and apply a
resolved named-Goal cancellation, a Goal replacement or a reflex cancellation
receipt to Goal and Task state under its lock.
"""

from __future__ import annotations

from typing import Any

from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.reflex import CancellationDispatchReceipt
from orchestrator.runtime import goal_association_state
from orchestrator.runtime import goal_outcome_state

from orchestrator.runtime.conversation_state import _DONE_TASK_STATUSES, _now_ms


def goal_cancellation_bindings(
    state: Any,
    goal_ids: list[str] | tuple[str, ...] | set[str],
) -> list[dict[str, Any]]:
    """Return trusted host-only runtime bindings for named Goal cancellation.

    This projection is intentionally not part of ``active_goal_snapshots``:
    model-facing continuity context does not need interaction/request
    identities.  The Core selects semantic Goal IDs; the trusted host then
    resolves those IDs to exact committed runtime and confirmation state.
    """

    bindings: list[dict[str, Any]] = []
    for raw_goal_id in goal_ids:
        goal_id = " ".join(str(raw_goal_id or "").strip().split())
        if not goal_id:
            continue
        context = state._task_context_by_goal_id(goal_id)
        if context is None:
            bindings.append(
                {
                    "goal_id": goal_id,
                    "found": False,
                    "reason": "unknown_target_goal",
                }
            )
            continue
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        confirmation = context.get("confirmation")
        if not isinstance(confirmation, dict):
            confirmation = {}
        remaining = state._string_list(metadata.get("remaining_request_ids"))
        confirmation_request_ids = state._string_list(
            confirmation.get("request_ids")
            or metadata.get("confirmation_request_ids")
        )
        planned_request_ids = [
            str(item.get("request_id") or "").strip()
            for item in (metadata.get("planned_capabilities") or [])
            if isinstance(item, dict) and str(item.get("request_id") or "").strip()
        ]
        bound_request_ids = sorted(
            {
                *planned_request_ids,
                *remaining,
                *confirmation_request_ids,
                *state._string_list(metadata.get("request_ids")),
            }
        )
        status = str(context.get("status") or "open").strip().lower()
        interaction_id = str(metadata.get("interaction_id") or "").strip()
        plan_id = str(metadata.get("canonical_plan_id") or "").strip()
        plan_fingerprint = str(
            metadata.get("canonical_plan_fingerprint") or ""
        ).strip()
        confirmation_id = str(
            confirmation.get("confirmation_id")
            or metadata.get("confirmation_id")
            or ""
        ).strip()
        confirmation_pending = bool(
            confirmation_id
            and str(confirmation.get("status") or "pending").strip().lower()
            == "pending"
        )
        runtime_revalidation_required = bool(
            metadata.get("runtime_revalidation_required") is True
        )
        runtime_status = status in {
            "committed",
            "scheduled",
            "running",
            "paused",
            "recoverable",
        }
        retained_groups: dict[tuple[str, str, str], list[str]] = {}
        for item in metadata.get("retained_work_activities", []):
            if item.get("activity_id") not in remaining:
                continue
            identity = item.get("runtime_binding") or {}
            key = tuple(str(identity.get(field) or "") for field in ("interaction_id", "canonical_plan_id", "canonical_plan_fingerprint"))
            retained_groups.setdefault(key, []).append(item["activity_id"])
        retained_ids = {request_id for ids in retained_groups.values() for request_id in ids}
        work_bindings = [
            {"interaction_id": key[0], "canonical_plan_id": key[1], "canonical_plan_fingerprint": key[2], "remaining_request_ids": ids}
            for key, ids in retained_groups.items()
        ]
        current_remaining = [request_id for request_id in remaining if request_id not in retained_ids]
        if current_remaining or not work_bindings:
            work_bindings.append({"interaction_id": interaction_id, "canonical_plan_id": plan_id,
                "canonical_plan_fingerprint": plan_fingerprint, "remaining_request_ids": current_remaining})
        bindings.append(
            {
                "goal_id": goal_id,
                "runtime_bindings": work_bindings,
                "task_id": str(context.get("task_id") or ""),
                "found": True,
                "status": status,
                "responsibility_status": state._goal_responsibility_status(context),
                "plan_version": max(0, int(context.get("plan_version") or 0)),
                "request_ids": bound_request_ids,
                "remaining_request_ids": remaining,
                "interaction_id": interaction_id,
                "canonical_plan_id": plan_id,
                "canonical_plan_fingerprint": plan_fingerprint,
                "confirmation_id": confirmation_id,
                "confirmation_pending": confirmation_pending,
                "confirmation_request_ids": confirmation_request_ids,
                "requires_revalidation": runtime_revalidation_required,
                "revalidation_reason": (
                    "restored_runtime_binding_requires_fresh_provider_state"
                    if runtime_revalidation_required
                    else ""
                ),
                "requires_runtime_dispatch": bool(
                    not runtime_revalidation_required
                    and (
                        runtime_status
                        or (remaining and not confirmation_pending)
                    )
                ),
            }
        )
    return bindings


def receipt_failure_reasons(
    receipt: CancellationDispatchReceipt,
) -> list[str]:
    reasons: list[str] = []
    if receipt.requested_scope != "specific_goal":
        reasons.append("receipt_scope_not_specific_goal")
    if receipt.stale_binding_request_bindings:
        reasons.append("stale_runtime_binding")
    if receipt.shared_owner_conflict_request_bindings:
        reasons.append("shared_owner_conflict")
    if receipt.non_interruptible_request_bindings:
        reasons.append("non_interruptible_request")
    if receipt.provider_cancel_failure_evidence:
        reasons.append("provider_cancel_failure")
    if receipt.dispatch_failures:
        reasons.append("cancellation_dispatch_failure")
    return reasons


def apply_goal_cancellation_resolution(
    state: Any,
    resolution: GoalAssociationResolution | dict[str, Any],
    *,
    receipts: list[CancellationDispatchReceipt | dict[str, Any]],
    confirmation_transition: dict[str, Any] | None,
    sid: str | None,
    user_text: str,
    source: str = "goal_cancellation_reconciliation",
    target_goal_ids_override: set[str] | list[str] | tuple[str, ...] | None = None,
    target_responsibility_status: str = "cancelled",
) -> list[dict[str, Any]]:
    """Atomically reconcile trusted cancellation evidence into Goal state.

    Runtime/provider cancellation cannot be rolled back, but Goal state must
    never be mutated from a model proposal alone.  This transaction first
    validates exact interaction/plan/request bindings for every execution-
    bound Goal, then applies semantic cancellation, collateral widening, and
    confirmation-token replacement in one in-memory/durable commit.
    """

    resolved = (
        resolution
        if isinstance(resolution, GoalAssociationResolution)
        else GoalAssociationResolution.model_validate(resolution)
    )
    target_goal_ids = (
        {str(goal_id).strip() for goal_id in target_goal_ids_override if str(goal_id).strip()}
        if target_goal_ids_override is not None
        else {
            goal_id
            for association in resolved.associations
            if association.relationship == "cancel"
            for goal_id in association.target_goal_ids
        }
    )
    if target_responsibility_status not in {"cancelled", "superseded"}:
        raise ValueError("unsupported target responsibility transition")
    if not target_goal_ids:
        return state.apply_goal_association_resolution(
            resolved,
            sid=sid,
            user_text=user_text,
            source=source,
            atomic=True,
        )

    validated_receipts = [
        item
        if isinstance(item, CancellationDispatchReceipt)
        else CancellationDispatchReceipt.model_validate(item)
        for item in receipts
    ]
    transition = dict(confirmation_transition or {})
    cancelled_confirmation_ids = {
        str(item).strip()
        for item in transition.get("cancelled_request_ids", [])
        if str(item).strip()
    }
    bindings = {
        item["goal_id"]: item
        for item in state.goal_cancellation_bindings(target_goal_ids)
    }
    validation_errors: list[str] = []
    receipt_by_goal: dict[str, CancellationDispatchReceipt] = {}
    for goal_id in sorted(target_goal_ids):
        binding = bindings.get(goal_id) or {"found": False}
        if not binding.get("found"):
            validation_errors.append(f"{goal_id}:unknown_target_goal")
            continue
        if not binding.get("requires_runtime_dispatch"):
            continue
        for work_binding in binding.get("runtime_bindings") or [binding]:
            matching = [
                receipt
                for receipt in validated_receipts
                if goal_id in receipt.target_goal_ids
                and receipt.expected_plan_id
                == work_binding.get("canonical_plan_id")
                and receipt.expected_plan_fingerprint
                == work_binding.get("canonical_plan_fingerprint")
                and work_binding.get("interaction_id") in receipt.interaction_ids
            ]
            if len(matching) != 1:
                validation_errors.append(
                    f"{goal_id}:exact_cancellation_receipt_missing"
                )
                continue
            receipt = matching[0]
            failures = receipt_failure_reasons(receipt)
            if failures:
                validation_errors.extend(
                    f"{goal_id}:{reason}" for reason in failures
                )
                continue
            required_request_ids = set(
                work_binding.get("remaining_request_ids") or ()
            ) - cancelled_confirmation_ids
            selected_request_ids = {
                item.request_id
                for item in receipt.selected_request_bindings
                if item.interaction_id == work_binding.get("interaction_id")
            }
            missing = sorted(required_request_ids - selected_request_ids)
            if missing:
                validation_errors.append(
                    f"{goal_id}:unselected_runtime_requests:{','.join(missing)}"
                )
                continue
            receipt_by_goal[goal_id] = receipt

    if validation_errors:
        raise ValueError(
            "goal_cancellation_reconciliation_rejected:"
            + ";".join(validation_errors)
        )

    coaffected_goal_ids = {
        goal_id
        for receipt in validated_receipts
        for goal_id in receipt.affected_goal_ids
        if goal_id not in target_goal_ids
    }
    replacement = transition.get("replacement")
    if replacement is not None and not isinstance(replacement, dict):
        raise ValueError("confirmation replacement must be a dictionary")

    def mutate() -> list[dict[str, Any]]:
        results = goal_association_state.apply_goal_association_resolution_in_memory(
            state,
            resolved,
            sid=sid,
            user_text=user_text,
            source=source,
        )
        rejected = [
            item
            for item in results
            if item.get("applied") is False
            and item.get("reason") != "operation_already_applied"
        ]
        if rejected:
            return results

        timestamp_ms = _now_ms()
        receipt_payloads = [
            item.model_dump(mode="json", exclude_none=True)
            for item in validated_receipts
        ]
        for goal_id in sorted(target_goal_ids | coaffected_goal_ids):
            context = state._task_context_by_goal_id(goal_id)
            if context is None:
                results.append(
                    {
                        "goal_id": goal_id,
                        "applied": True,
                        "state_change": "unmatched_coaffected_goal_recorded",
                    }
                )
                continue
            previous_status = str(
                context.get("status") or "open"
            ).lower()
            if goal_id in target_goal_ids:
                context["status"] = "cancelled"
                context["commitment_state"] = "cancelled"
                context["plan_status"] = (
                    "work_stopped_for_replacement"
                    if target_responsibility_status == "superseded"
                    else "cancelled"
                )
                if target_responsibility_status == "superseded":
                    replacement_goal_ids = [
                        str(goal.goal_id or "")
                        for goal in resolved.new_goals
                        if goal_id in goal.supersedes_goal_ids and goal.goal_id
                    ]
                    state._set_goal_responsibility_status(
                        context,
                        "superseded",
                        source=source,
                    )
                    metadata = context.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                    context["metadata"] = {
                        **metadata,
                        "superseded_by_goal_ids": replacement_goal_ids,
                    }
            elif goal_id in coaffected_goal_ids:
                if state._goal_responsibility_status(context) == "open":
                    context["status"] = "recoverable"
                    context["commitment_state"] = "evaluating"
                    context["plan_status"] = "interrupted_by_widened_scope"
            confirmation = context.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            if goal_id in target_goal_ids:
                context["confirmation"] = {
                    **confirmation,
                    "status": "cancelled",
                    "resolved_ms": timestamp_ms,
                }
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            context["metadata"] = {
                **metadata,
                "remaining_request_ids": (
                    []
                    if goal_id in target_goal_ids
                    else metadata.get("remaining_request_ids", [])
                ),
                "cancellation_source_turn_id": resolved.turn_id,
                "cancellation_receipts": receipt_payloads,
                "cancellation_targeted": goal_id in target_goal_ids,
                "cancellation_scope_widened": goal_id in coaffected_goal_ids,
            }
            context["updated_ms"] = timestamp_ms
            if goal_id in coaffected_goal_ids:
                results.append(
                    {
                        "goal_id": goal_id,
                        "operation": "runtime_scope_widened_cancel",
                        "applied": True,
                        "status": str(context.get("status") or previous_status),
                        "state_change": (
                            "work_interrupted_responsibility_open"
                            if state._goal_responsibility_status(context) == "open"
                            else "responsibility_terminal_work_recorded"
                        ),
                    }
                )

        selected_request_bindings = {
            (item.interaction_id, item.request_id)
            for receipt in validated_receipts
            for item in receipt.selected_request_bindings
        }
        for task in state._pending_tasks:
            if task.get("type") != "goal_execution":
                continue
            task_metadata = task.get("metadata")
            if not isinstance(task_metadata, dict):
                continue
            task_goal_id = str(task_metadata.get("goal_id") or "").strip()
            if task_goal_id in target_goal_ids:
                task["status"] = "cancelled"
                task["updated_ms"] = timestamp_ms
                task["metadata"] = {
                    **task_metadata,
                    "remaining_request_ids": [],
                    "work_stop_source_turn_id": resolved.turn_id,
                }
            elif task_goal_id in coaffected_goal_ids:
                remaining = state._string_list(
                    task_metadata.get("remaining_request_ids")
                    or task_metadata.get("request_ids")
                )
                task_interaction_id = str(
                    task_metadata.get("interaction_id") or ""
                ).strip()
                remaining = [
                    request_id
                    for request_id in remaining
                    if (task_interaction_id, request_id)
                    not in selected_request_bindings
                ]
                task["status"] = "recoverable"
                task["updated_ms"] = timestamp_ms
                task["metadata"] = {
                    **task_metadata,
                    "remaining_request_ids": remaining,
                    "work_stop_scope_widened": True,
                }

        old_confirmation_id = str(
            transition.get("old_confirmation_id") or ""
        ).strip()
        released_confirmation_goal_ids = {
            str(item).strip()
            for item in transition.get("released_confirmation_goal_ids") or []
            if str(item).strip()
        }
        if old_confirmation_id:
            new_confirmation_id = str(
                (replacement or {}).get("confirmation_id") or ""
            ).strip()
            new_fingerprint = str(
                (replacement or {}).get("fingerprint") or ""
            ).strip()
            new_expires_at = (replacement or {}).get("expires_at")
            preserved_by_goal = (
                (replacement or {}).get("request_ids_by_goal") or {}
            )
            confirmed_by_goal = (
                (replacement or {}).get(
                    "confirmation_request_ids_by_goal"
                )
                or {}
            )
            replacement_interaction_id = str(
                (replacement or {}).get("interaction_id") or ""
            ).strip()
            replacement_plan_id = str(
                (replacement or {}).get("canonical_plan_id") or ""
            ).strip()
            replacement_plan_fingerprint = str(
                (replacement or {}).get(
                    "canonical_plan_fingerprint"
                )
                or ""
            ).strip()
            for task in state._pending_tasks:
                metadata = task.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                if metadata.get("confirmation_id") != old_confirmation_id:
                    continue
                goal_id = str(metadata.get("goal_id") or "").strip()
                if goal_id in target_goal_ids:
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    continue
                request_ids = confirmed_by_goal.get(goal_id)
                if new_confirmation_id and isinstance(request_ids, list):
                    task["metadata"] = {
                        **metadata,
                        "confirmation_id": new_confirmation_id,
                        "fingerprint": new_fingerprint,
                        "expires_at": new_expires_at,
                        "request_ids": list(request_ids),
                        "confirmation_request_ids": list(request_ids),
                        "replaces_confirmation_id": old_confirmation_id,
                    }
                    task["status"] = "awaiting_confirmation"
                    task["updated_ms"] = timestamp_ms
                else:
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    if goal_id in released_confirmation_goal_ids:
                        context = state._task_context_by_goal_id(goal_id)
                        if context is not None and state._goal_responsibility_status(context) == "open":
                            context["status"] = "planning"
                            context["commitment_state"] = "evaluating"
                            context["plan_status"] = "confirmation_revoked_requires_replan"
                            confirmation = context.get("confirmation")
                            if not isinstance(confirmation, dict):
                                confirmation = {}
                            context["confirmation"] = {
                                **confirmation,
                                "status": "revoked",
                                "resolved_ms": timestamp_ms,
                            }
                            context_metadata = context.get("metadata")
                            if not isinstance(context_metadata, dict):
                                context_metadata = {}
                            context["metadata"] = {
                                **context_metadata,
                                "confirmation_id": "",
                                "confirmation_request_ids": [],
                                "remaining_request_ids": [],
                                "confirmation_revoked_by_goal_cancellation": True,
                            }
                            context["updated_ms"] = timestamp_ms

            for task in state._pending_tasks:
                if task.get("type") != "goal_execution":
                    continue
                metadata = task.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                goal_id = str(metadata.get("goal_id") or "").strip()
                if not goal_id:
                    continue
                if goal_id in target_goal_ids:
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **metadata,
                        "remaining_request_ids": [],
                        "cancellation_source_turn_id": resolved.turn_id,
                    }
                    continue
                request_ids = preserved_by_goal.get(goal_id)
                if goal_id in released_confirmation_goal_ids and not new_confirmation_id:
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **metadata,
                        "remaining_request_ids": [],
                        "confirmation_revoked_by_goal_cancellation": True,
                    }
                elif new_confirmation_id and isinstance(request_ids, list):
                    task["status"] = "awaiting_confirmation"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **metadata,
                        "request_ids": list(request_ids),
                        "remaining_request_ids": list(request_ids),
                        "interaction_id": replacement_interaction_id,
                        "canonical_plan_id": replacement_plan_id,
                        "canonical_plan_fingerprint": (
                            replacement_plan_fingerprint
                        ),
                        "confirmation_pending": True,
                        "confirmation_id": new_confirmation_id,
                        "replaces_confirmation_id": old_confirmation_id,
                    }

            if new_confirmation_id:
                for goal_id, request_ids in preserved_by_goal.items():
                    context = state._task_context_by_goal_id(str(goal_id))
                    if context is None or str(goal_id) in target_goal_ids:
                        continue
                    context["status"] = "awaiting_confirmation"
                    context["commitment_state"] = "waiting_for_user"
                    context["plan_status"] = "awaiting_confirmation"
                    context["confirmation"] = {
                        "status": "pending",
                        "confirmation_id": new_confirmation_id,
                        "fingerprint": new_fingerprint,
                        "expires_at": new_expires_at,
                        "request_ids": list(
                            confirmed_by_goal.get(goal_id, [])
                        ),
                        "replaces_confirmation_id": old_confirmation_id,
                    }
                    metadata = context.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                    context["metadata"] = {
                        **metadata,
                        "confirmation_id": new_confirmation_id,
                        "confirmation_request_ids": list(
                            confirmed_by_goal.get(goal_id, [])
                        ),
                        "request_ids": list(request_ids),
                        "remaining_request_ids": list(request_ids),
                        "interaction_id": replacement_interaction_id,
                        "canonical_plan_id": replacement_plan_id,
                        "canonical_plan_fingerprint": (
                            replacement_plan_fingerprint
                        ),
                    }
                    context["updated_ms"] = timestamp_ms

        results.append(
            {
                "operation": "cancellation_receipt_reconciliation",
                "applied": True,
                "target_goal_ids": sorted(target_goal_ids),
                "coaffected_goal_ids": sorted(coaffected_goal_ids),
                "receipt_count": len(validated_receipts),
                "confirmation_rebuilt": bool(replacement),
            }
        )
        return results

    return state._commit_semantic_state_transaction(
        mutate,
        rollback_reason="atomic_cancellation_transaction_rolled_back",
        persistence_failure_reason="atomic_cancellation_persistence_failed",
    )


def apply_goal_replacement_resolution(
    state: Any,
    resolution: GoalAssociationResolution | dict[str, Any],
    *,
    receipts: list[CancellationDispatchReceipt | dict[str, Any]],
    confirmation_transition: dict[str, Any] | None,
    sid: str | None,
    user_text: str,
    source: str = "goal_replacement_reconciliation",
) -> list[dict[str, Any]]:
    resolved = (
        resolution
        if isinstance(resolution, GoalAssociationResolution)
        else GoalAssociationResolution.model_validate(resolution)
    )
    target_goal_ids = {
        goal_id
        for goal in resolved.new_goals
        for goal_id in goal.supersedes_goal_ids
    }
    if not target_goal_ids:
        return state.apply_goal_association_resolution(
            resolved,
            sid=sid,
            user_text=user_text,
            source=source,
            atomic=True,
        )
    return state.apply_goal_cancellation_resolution(
        resolved,
        receipts=receipts,
        confirmation_transition=confirmation_transition,
        sid=sid,
        user_text=user_text,
        source=source,
        target_goal_ids_override=target_goal_ids,
        target_responsibility_status="superseded",
    )


def apply_reflex_cancellation_receipt(
    state: Any,
    receipt: CancellationDispatchReceipt | dict[str, Any],
    *,
    revoked_confirmation: dict[str, Any] | None,
    sid: str | None,
    user_text: str,
    source: str = "reflex_cancellation_reconciliation",
) -> list[dict[str, Any]]:
    """Atomically reconcile a fixed-reflex dispatch into canonical Goal state.

    A broad stop is selected by deterministic operational policy, not by the
    semantic Core.  The receipt therefore owns request/interaction scope,
    while the host's committed Goal records own request-to-Goal binding.
    This transaction updates only Goals for which those two evidence sets
    intersect.  Request-level provider failures, non-interruptible work,
    host-only preflight cancellation, and stale/unselected work remain
    explicitly recoverable/uncertain rather than being rewritten as a
    successful cancellation.
    """

    if not state.enabled:
        return []
    validated = (
        receipt
        if isinstance(receipt, CancellationDispatchReceipt)
        else CancellationDispatchReceipt.model_validate(receipt)
    )
    if validated.requested_scope in {"none", "specific_goal"}:
        raise ValueError(
            "fixed reflex reconciliation requires a broad cancellation scope"
        )
    confirmation_evidence = dict(revoked_confirmation or {})
    confirmation_id = str(
        confirmation_evidence.get("confirmation_id") or ""
    ).strip()

    def binding_keys(values: Any) -> set[tuple[str, str]]:
        return {
            (str(item.interaction_id), str(item.request_id))
            for item in values
        }

    selected_keys = binding_keys(validated.selected_request_bindings)
    non_interruptible_keys = binding_keys(
        validated.non_interruptible_request_bindings
    )
    provider_failure_keys = {
        (str(item.interaction_id), str(item.request_id))
        for item in validated.provider_cancel_failure_evidence
    }
    failed_keys = non_interruptible_keys | provider_failure_keys
    affected_goal_ids = set(validated.affected_goal_ids)
    receipt_interactions = {
        *validated.interaction_ids,
        *validated.host_interaction_ids,
    }
    host_cancel_interactions = set(
        validated.host_task_cancel_requested_interaction_ids
    )
    runtime_dispatch_uncertain = any(
        str(item).startswith("capability_runtime:")
        for item in validated.dispatch_failures
    )
    output_dispatch_uncertain = any(
        str(item).startswith(
            ("output_invalidation:", "output_reinvalidation:")
        )
        for item in validated.dispatch_failures
    )
    emergency = dict(validated.emergency_stop_evidence or {})
    emergency_output = emergency.get("output")
    if not isinstance(emergency_output, dict):
        emergency_output = {}
    safe_idle_verified = bool(
        emergency.get("postcondition_confirmed") is True
        or (
            emergency.get("status") == "success"
            and all(
                emergency_output.get(key) is True
                for key in ("stopped", "emergency", "safe_idle")
            )
        )
    )
    receipt_payload = validated.model_dump(mode="json", exclude_none=True)

    def goal_id_for(context: dict[str, Any]) -> str:
        goal = state._semantic_goal_from_context(context)
        return str(goal.goal_id or "").strip()

    def context_request_skills(
        metadata: dict[str, Any],
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        planned = metadata.get("planned_capabilities")
        if not isinstance(planned, list):
            return result
        for item in planned:
            if not isinstance(item, dict):
                continue
            request_id = str(item.get("request_id") or "").strip()
            capability_id = str(item.get("capability_id") or "").strip()
            if request_id:
                result[request_id] = capability_id
        return result

    candidate_contexts: list[dict[str, Any]] = []
    for context in state._task_contexts:
        goal_id = goal_id_for(context)
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        interaction_id = str(metadata.get("interaction_id") or "").strip()
        confirmation = context.get("confirmation")
        if not isinstance(confirmation, dict):
            confirmation = {}
        bound_confirmation_id = str(
            confirmation.get("confirmation_id")
            or metadata.get("confirmation_id")
            or ""
        ).strip()
        if (
            goal_id in affected_goal_ids
            or (interaction_id and interaction_id in receipt_interactions)
            or (
                confirmation_id
                and bound_confirmation_id == confirmation_id
            )
        ):
            candidate_contexts.append(context)

    def mutate() -> list[dict[str, Any]]:
        timestamp_ms = _now_ms()
        results: list[dict[str, Any]] = []
        summaries: dict[str, dict[str, Any]] = {}

        for context in candidate_contexts:
            goal_id = goal_id_for(context)
            if not goal_id:
                continue
            previous_status = str(context.get("status") or "open").lower()
            if previous_status in _DONE_TASK_STATUSES:
                results.append(
                    {
                        "goal_id": goal_id,
                        "applied": True,
                        "state_change": "terminal_state_unchanged",
                        "status": previous_status,
                    }
                )
                continue

            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            interaction_id = str(metadata.get("interaction_id") or "").strip()
            remaining = set(
                state._string_list(
                    metadata.get("remaining_request_ids")
                    or metadata.get("request_ids")
                )
            )
            request_statuses = metadata.get("request_statuses")
            if not isinstance(request_statuses, dict):
                request_statuses = {}
            request_statuses = {
                str(key): str(value)
                for key, value in request_statuses.items()
            }
            skills_by_request = context_request_skills(metadata)

            confirmation = context.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            bound_confirmation_id = str(
                confirmation.get("confirmation_id")
                or metadata.get("confirmation_id")
                or ""
            ).strip()
            confirmation_cancelled = bool(
                confirmation_id
                and bound_confirmation_id == confirmation_id
            )

            selected_for_goal = {
                request_id
                for bound_interaction, request_id in selected_keys
                if (
                    not interaction_id
                    or bound_interaction == interaction_id
                )
                and (not remaining or request_id in remaining)
            }
            failed_for_goal = {
                request_id
                for bound_interaction, request_id in failed_keys
                if (
                    not interaction_id
                    or bound_interaction == interaction_id
                )
                and (not remaining or request_id in remaining)
            }

            known_cancelled = selected_for_goal - failed_for_goal
            uncertain = set(failed_for_goal)
            uncertainty_reasons: list[str] = []

            if runtime_dispatch_uncertain and (
                interaction_id in receipt_interactions
                or goal_id in affected_goal_ids
            ):
                uncertain.update(remaining or selected_for_goal)
                uncertainty_reasons.append("runtime_dispatch_failure")
            if (
                interaction_id in host_cancel_interactions
                and not selected_for_goal
            ):
                uncertain.update(remaining)
                uncertainty_reasons.append(
                    "host_workflow_cancel_requested_unknown_start"
                )
            if validated.requested_scope in {
                "current_interaction",
                "global_emergency",
            }:
                unselected = remaining - selected_for_goal
                if unselected and not confirmation_cancelled:
                    uncertain.update(unselected)
                    uncertainty_reasons.append(
                        "broad_scope_request_not_in_runtime_receipt"
                    )
            if output_dispatch_uncertain:
                speech_requests = {
                    request_id
                    for request_id, capability_id in skills_by_request.items()
                    if capability_id == "chromie.speak"
                }
                affected_speech = speech_requests.intersection(
                    remaining or speech_requests
                )
                if affected_speech and validated.effective_scope in {
                    "output_only",
                    "current_interaction",
                    "global_emergency",
                }:
                    uncertain.update(affected_speech)
                    known_cancelled.difference_update(affected_speech)
                    uncertainty_reasons.append(
                        "output_invalidation_failure"
                    )

            # A request cannot be both proven cancelled and uncertain.
            # Broad dispatch failures may retroactively make an otherwise
            # selected request unknown, so uncertainty always dominates.
            known_cancelled.difference_update(uncertain)

            if confirmation_cancelled:
                confirmation_request_ids = set(
                    state._string_list(
                        confirmation.get("request_ids")
                        or metadata.get("confirmation_request_ids")
                    )
                )
                known_cancelled.update(confirmation_request_ids)
                remaining_after = set()
                new_status = "cancelled"
                plan_status = "cancelled_by_operational_interrupt"
                state_change = "confirmation_cancelled"
            else:
                remaining_after = remaining - known_cancelled
                if uncertain:
                    remaining_after.update(uncertain)
                    new_status = "recoverable"
                    plan_status = "cancellation_uncertain"
                    state_change = "cancellation_uncertain"
                elif known_cancelled and remaining and not remaining_after:
                    new_status = "cancelled"
                    plan_status = "cancelled"
                    state_change = "cancelled"
                elif known_cancelled:
                    new_status = "recoverable"
                    plan_status = "partially_cancelled"
                    state_change = "partially_cancelled"
                elif validated.effective_scope == "output_only":
                    # Pre-action/progress speech may cover an embodied Goal
                    # without belonging to that Goal's committed execution
                    # request set. Stopping that shared output must not
                    # rewrite the embodied Goal as cancelled or uncertain.
                    context["metadata"] = {
                        **metadata,
                        "reflex_cancellation_source_turn_id": (
                            validated.source_turn_id
                        ),
                        "reflex_cancellation_scope": (
                            validated.requested_scope
                        ),
                        "reflex_cancellation_effective_scope": (
                            validated.effective_scope
                        ),
                        "reflex_cancellation_receipt": receipt_payload,
                        "output_cancellation_recorded": True,
                    }
                    context["updated_ms"] = timestamp_ms
                    results.append(
                        {
                            "goal_id": goal_id,
                            "applied": True,
                            "state_change": (
                                "output_cancelled_goal_execution_unchanged"
                            ),
                            "status": previous_status,
                        }
                    )
                    continue
                elif (
                    interaction_id in host_cancel_interactions
                    or goal_id in affected_goal_ids
                ):
                    new_status = "recoverable"
                    plan_status = "cancellation_uncertain"
                    state_change = "cancellation_uncertain"
                    uncertainty_reasons.append(
                        "cancellation_receipt_has_no_bound_request"
                    )
                else:
                    results.append(
                        {
                            "goal_id": goal_id,
                            "applied": True,
                            "state_change": "no_goal_owned_work_selected",
                            "status": previous_status,
                        }
                    )
                    continue

            for request_id in known_cancelled:
                request_statuses[request_id] = "cancelled"
            for request_id in uncertain:
                request_statuses[request_id] = "cancellation_uncertain"

            context["status"] = new_status
            context["commitment_state"] = (
                goal_outcome_state.commitment_state_for_status(new_status)
            )
            context["plan_status"] = plan_status
            if confirmation_cancelled:
                context["confirmation"] = {
                    **confirmation,
                    "status": "operational_interrupt",
                    "resolved_ms": timestamp_ms,
                }
            context["metadata"] = {
                **metadata,
                "remaining_request_ids": sorted(remaining_after),
                "request_statuses": request_statuses,
                "reflex_cancellation_source_turn_id": (
                    validated.source_turn_id
                ),
                "reflex_cancellation_scope": validated.requested_scope,
                "reflex_cancellation_effective_scope": (
                    validated.effective_scope
                ),
                "reflex_cancelled_request_ids": sorted(known_cancelled),
                "reflex_uncertain_request_ids": sorted(uncertain),
                "reflex_cancellation_uncertainty_reasons": list(
                    dict.fromkeys(uncertainty_reasons)
                ),
                "reflex_cancellation_receipt": receipt_payload,
                "emergency_stop_status": str(
                    emergency.get("status") or ""
                ),
                "safe_idle_verified": safe_idle_verified,
            }
            context["updated_ms"] = timestamp_ms
            summaries[goal_id] = {
                "status": new_status,
                "state_change": state_change,
                "known_cancelled": sorted(known_cancelled),
                "uncertain": sorted(uncertain),
                "remaining": sorted(remaining_after),
            }
            results.append(
                {
                    "goal_id": goal_id,
                    "applied": True,
                    "status": new_status,
                    "state_change": state_change,
                    "cancelled_request_ids": sorted(known_cancelled),
                    "uncertain_request_ids": sorted(uncertain),
                    "remaining_request_ids": sorted(remaining_after),
                }
            )

        for task in state._pending_tasks:
            task_metadata = task.get("metadata")
            if not isinstance(task_metadata, dict):
                continue
            task_goal_id = str(task_metadata.get("goal_id") or "").strip()
            summary = summaries.get(task_goal_id)
            if summary is not None:
                task["status"] = summary["status"]
                task["updated_ms"] = timestamp_ms
                statuses = task_metadata.get("request_statuses")
                if not isinstance(statuses, dict):
                    statuses = {}
                statuses = {str(key): str(value) for key, value in statuses.items()}
                for request_id in summary["known_cancelled"]:
                    statuses[request_id] = "cancelled"
                for request_id in summary["uncertain"]:
                    statuses[request_id] = "cancellation_uncertain"
                task["metadata"] = {
                    **task_metadata,
                    "remaining_request_ids": list(summary["remaining"]),
                    "request_statuses": statuses,
                    "reflex_cancellation_source_turn_id": (
                        validated.source_turn_id
                    ),
                    "reflex_cancellation_scope": validated.requested_scope,
                    "reflex_cancellation_receipt": receipt_payload,
                }
                continue
            if (
                confirmation_id
                and task_metadata.get("confirmation_id") == confirmation_id
            ):
                task["status"] = "cancelled"
                task["updated_ms"] = timestamp_ms
                task["metadata"] = {
                    **task_metadata,
                    "reflex_cancellation_source_turn_id": (
                        validated.source_turn_id
                    ),
                    "reflex_cancellation_scope": validated.requested_scope,
                }

        results.append(
            {
                "operation": "fixed_reflex_receipt_reconciliation",
                "applied": True,
                "requested_scope": validated.requested_scope,
                "effective_scope": validated.effective_scope,
                "affected_goal_ids": sorted(summaries),
                "safe_idle_verified": safe_idle_verified,
                "confirmation_cancelled": bool(confirmation_id),
            }
        )
        return results

    return state._commit_semantic_state_transaction(
        mutate,
        rollback_reason="atomic_reflex_cancellation_transaction_rolled_back",
        persistence_failure_reason=(
            "atomic_reflex_cancellation_persistence_failed"
        ),
    )
