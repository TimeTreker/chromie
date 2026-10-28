"""Reflex cancellation applied by the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host``. They apply
a deterministic reflex CancellationDirective to playback, input turns, Goals and
the Capability Runtime, and reconcile its dispatch receipt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any


from orchestrator.runtime.confirmation import (
    reconcile_revoked_confirmation_for_reflex,
    revoked_confirmation_evidence_for_reflex,
)
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.long_running_social_skill import social_skill_of
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    ReflexOutcome,
)

logger = logging.getLogger("chromie-orchestrator")


def reconcile_reflex_cancellation_receipt(
    host: Any,
    receipt: CancellationDispatchReceipt,
    pending: Any | None,
    session_id: str,
    *,
    user_text: str,
    cancellation_scope: str,
) -> dict[str, Any]:
    """Commit a broad fixed-reflex receipt and confirmation as one state update."""

    confirmation_evidence = revoked_confirmation_evidence_for_reflex(
        pending,
        cancellation_scope=cancellation_scope,
        interaction_registry=getattr(
            getattr(host, "interaction_runtime", None),
            "registry",
            None,
        ),
    )
    apply_receipt = getattr(
        getattr(host, "conversation_state", None),
        "apply_reflex_cancellation_receipt",
        None,
    )
    if not callable(apply_receipt):
        cancelled_confirmation = reconcile_revoked_confirmation_for_reflex(
            pending,
            conversation_state=getattr(host, "conversation_state", None),
            session_id=session_id,
            cancellation_scope=cancellation_scope,
            interaction_registry=getattr(
                getattr(host, "interaction_runtime", None),
                "registry",
                None,
            ),
            session_log=host.session_log,
        )
        return {
            "status": "compatibility_fallback",
            "goal_state_results": [],
            "cancelled_confirmation": cancelled_confirmation,
        }
    try:
        results = apply_receipt(
            receipt,
            revoked_confirmation=confirmation_evidence,
            sid=session_id,
            user_text=user_text,
            source="cognitive_gateway_fixed_reflex",
        )
    except Exception as exc:
        cancelled_confirmation = reconcile_revoked_confirmation_for_reflex(
            pending,
            conversation_state=getattr(host, "conversation_state", None),
            session_id=session_id,
            cancellation_scope=cancellation_scope,
            interaction_registry=getattr(
                getattr(host, "interaction_runtime", None),
                "registry",
                None,
            ),
            session_log=host.session_log,
        )
        host.session_log(
            session_id,
            "cognitive_gateway_reflex_goal_reconciliation_failed: "
            "scope=%s error=%s:%s",
            cancellation_scope,
            type(exc).__name__,
            str(exc)[:300],
        )
        return {
            "status": "uncertain",
            "goal_state_results": [],
            "cancelled_confirmation": cancelled_confirmation,
            "error": f"{type(exc).__name__}:{str(exc)[:300]}",
        }
    rejected = [
        item
        for item in results
        if item.get("applied") is False
        and item.get("reason") != "operation_already_applied"
    ]
    if rejected:
        cancelled_confirmation = reconcile_revoked_confirmation_for_reflex(
            pending,
            conversation_state=getattr(host, "conversation_state", None),
            session_id=session_id,
            cancellation_scope=cancellation_scope,
            interaction_registry=getattr(
                getattr(host, "interaction_runtime", None),
                "registry",
                None,
            ),
            session_log=host.session_log,
        )
        return {
            "status": "uncertain",
            "goal_state_results": results,
            "cancelled_confirmation": cancelled_confirmation,
            "error": "atomic_reflex_cancellation_state_commit_rejected",
        }
    if confirmation_evidence:
        host.session_log(
            session_id,
            "cognitive_gateway_confirmation_cancelled: "
            "confirmation_id=%s fingerprint=%s scope=%s widened=%s",
            str(confirmation_evidence.get("confirmation_id") or "<unknown>"),
            str(confirmation_evidence.get("fingerprint") or "<unknown>"),
            cancellation_scope,
            bool(confirmation_evidence.get("confirmation_scope_widened")),
        )
    return {
        "status": "reconciled",
        "goal_state_results": results,
        "cancelled_confirmation": confirmation_evidence,
    }


async def apply_reflex_cancellation(
    host: Any,
    outcome: ReflexOutcome,
    *,
    source_turn_id: str,
) -> CancellationDispatchReceipt:
    """Apply one closed reflex scope without semantic goal guessing."""

    scope = outcome.cancellation_scope
    if scope == "none":
        raise ValueError("reflex cancellation requires a concrete scope")
    if scope == "specific_goal":
        raise ValueError(
            "specific_goal cancellation requires the Core's exact "
            "committed plan binding and cannot originate from ReflexOutcome"
        )
    # Every deterministic stop, cancel, emergency or silence ends the long-running social
    # skill (Social Attention contract); Social Cognition may start it again on a later turn.
    social_skill = social_skill_of(getattr(host, "interaction_runtime", None))
    if social_skill is not None:
        social_skill.schedule_stop(f"reflex:{scope}")
    if scope in {"current_interaction", "global_emergency"}:
        input_session_runtime_for(host)._cancel_active_routed_turns(
            excluding=asyncio.current_task(),
            cancel_all=(scope == "global_emergency"),
            reason=f"protective_reflex:{scope}",
        )
    active_interaction_id = ""
    active_tasks = getattr(host, "active_interaction_tasks", None)
    active_host_interactions: list[
        tuple[asyncio.Task, str]
    ] = []
    if isinstance(active_tasks, dict):
        active_host_interactions = [
            (task, str(interaction_id).strip())
            for task, interaction_id in active_tasks.items()
            if not task.done() and str(interaction_id).strip()
        ]
        if active_host_interactions:
            active_interaction_id = active_host_interactions[-1][1]
    if not active_interaction_id:
        active_task = getattr(
            host,
            "active_interaction_task",
            None,
        )
        legacy_interaction_id = str(
            getattr(host, "active_interaction_id", None) or ""
        ).strip()
        if active_task is None or not active_task.done():
            active_interaction_id = legacy_interaction_id
        if (
            active_task is not None
            and not active_task.done()
            and legacy_interaction_id
            and all(
                item[0] is not active_task
                for item in active_host_interactions
            )
        ):
            active_host_interactions.append(
                (active_task, legacy_interaction_id)
            )
    runtime_open_interaction_ids: list[str] = []
    runtime = getattr(
        getattr(host, "interaction_runtime", None),
        "runtime",
        None,
    )
    observe_execution = getattr(runtime, "execution_observation", None)
    if callable(observe_execution):
        try:
            observation = await observe_execution()
            runtime_open_interaction_ids = [
                str(item).strip()
                for item in observation.open_interaction_ids
                if str(item).strip()
            ]
        except Exception as exc:
            logger.warning(
                "Runtime execution observation failed during cancellation: %s",
                exc,
            )
    if not active_interaction_id and runtime_open_interaction_ids:
        # Detached capability work intentionally outlives the foreground
        # interaction task. Runtime ownership is therefore the authoritative
        # fallback for current-interaction cancellation scope.
        active_interaction_id = runtime_open_interaction_ids[-1]
    if scope == "global_emergency":
        host_scope_interaction_ids = tuple(
            sorted(
                {
                    interaction_id
                    for _, interaction_id in active_host_interactions
                }.union(runtime_open_interaction_ids)
            )
        )
    elif (
        scope in {"output_only", "current_interaction"}
        and active_interaction_id
    ):
        host_scope_interaction_ids = (active_interaction_id,)
    else:
        host_scope_interaction_ids = ()
    receipt = CancellationDispatchReceipt(
        source_turn_id=source_turn_id,
        requested_scope=scope,
        effective_scope=scope,
    )
    dispatch_failures: list[str] = []
    emergency_evidence: dict[str, Any] = {}
    phase_operations: list[tuple[str, Any]] = []

    # Safety dispatches lead the first phase. Output teardown can wait on a
    # device write lock; it must never serialize motion cancellation or an
    # emergency stop behind that audio cleanup.
    if scope == "global_emergency":
        emergency_stop = getattr(
            host.interaction_runtime,
            "emergency_stop",
            None,
        )
        if callable(emergency_stop):
            phase_operations.append(
                (
                    "emergency_stop",
                    emergency_stop(reason=outcome.reason),
                )
            )
        else:
            emergency_evidence = {
                "status": "unavailable",
                "reason": "emergency_stop_dispatch_unsupported",
            }
            dispatch_failures.append(
                "emergency_stop:dispatch_unsupported"
            )

    runtime_dispatch_required = not (
        scope in {"output_only", "current_interaction"}
        and not active_interaction_id
    )
    runtime_operation_kind = ""
    if runtime_dispatch_required:
        directive = CancellationDirective(
            source_turn_id=source_turn_id,
            requested_scope=scope,
            foreground_interaction_id=(
                active_interaction_id
                if scope
                in {
                    "output_only",
                    "current_interaction",
                    "specific_goal",
                }
                else None
            ),
            target_goal_ids=outcome.target_goal_ids,
            reason=outcome.reason,
        )
        cancel_scope = getattr(
            host.interaction_runtime,
            "cancel_scope",
            None,
        )
        if callable(cancel_scope):
            runtime_operation_kind = "runtime_scope"
            phase_operations.append(
                (
                    runtime_operation_kind,
                    cancel_scope(directive),
                )
            )
        else:
            dispatch_failures.append(
                "capability_runtime:scoped_dispatch_unsupported"
            )

    if scope in {
        "output_only",
        "current_interaction",
        "global_emergency",
    }:
        try:
            host._invalidate_output_state(
                cancel_cognitive_work=False,
            )
            host._schedule_output_abort(
                new_session_id=source_turn_id,
                log_event=False,
            )
        except Exception as exc:
            dispatch_failures.append(
                "output_invalidation:"
                f"{type(exc).__name__}:{str(exc)[:300]}"
            )

    phase_results = await asyncio.gather(
        *(operation for _, operation in phase_operations),
        return_exceptions=True,
    )
    for (operation_kind, _), result in zip(
        phase_operations,
        phase_results,
        strict=True,
    ):
        if operation_kind == "runtime_scope":
            if isinstance(result, BaseException):
                dispatch_failures.append(
                    "capability_runtime:"
                    f"{type(result).__name__}:{str(result)[:300]}"
                )
            elif isinstance(result, CancellationDispatchReceipt):
                receipt = result
            else:
                dispatch_failures.append(
                    "capability_runtime:invalid_dispatch_receipt"
                )
        elif operation_kind == "emergency_stop":
            if isinstance(result, BaseException):
                emergency_evidence = {
                    "status": "failed",
                    "reason": (
                        f"{type(result).__name__}:{str(result)[:300]}"
                    ),
                }
                dispatch_failures.append(
                    "emergency_stop:"
                    f"{type(result).__name__}:{str(result)[:300]}"
                )
            elif isinstance(result, dict):
                emergency_evidence = result
            else:
                emergency_evidence = {
                    "status": "failed",
                    "reason": "invalid_emergency_stop_evidence",
                }
                dispatch_failures.append(
                    "emergency_stop:invalid_evidence"
                )
    receipt = receipt.model_copy(
        update={
            "interaction_ids": tuple(
                sorted(
                    {
                        *receipt.interaction_ids,
                        *host_scope_interaction_ids,
                    }
                )
            ),
            "host_interaction_ids": tuple(
                sorted(
                    {
                        *receipt.host_interaction_ids,
                        *host_scope_interaction_ids,
                    }
                )
            ),
            "dispatch_failures": tuple(
                dict.fromkeys(
                    [
                        *receipt.dispatch_failures,
                        *dispatch_failures,
                    ]
                )
            ),
            "emergency_stop_evidence": (
                emergency_evidence
                if scope == "global_emergency"
                else receipt.emergency_stop_evidence
            ),
            "output_invalidation_requested": (
                receipt.output_invalidation_requested
                or scope
                in {
                    "output_only",
                    "current_interaction",
                    "global_emergency",
                }
            ),
        }
    )

    # A provider task may have been inside the speech scheduler while
    # runtime cancellation ran. Invalidate once more so no late synthesis
    # can re-enter playback. Device teardown remains detached: a blocked
    # audio driver must not keep this protective reflex active or delay a
    # later emergency reflex.
    if scope in {
        "output_only",
        "current_interaction",
        "global_emergency",
    }:
        try:
            host._invalidate_output_state(
                cancel_cognitive_work=False,
            )
        except Exception as exc:
            receipt = receipt.model_copy(
                update={
                    "dispatch_failures": tuple(
                        dict.fromkeys(
                            [
                                *receipt.dispatch_failures,
                                "output_reinvalidation:"
                                f"{type(exc).__name__}:"
                                f"{str(exc)[:300]}",
                            ]
                        )
                    )
                }
            )

    host_task_cancel_requested: list[str] = []
    host_cancel_candidates: list[tuple[asyncio.Task, str]] = []
    if scope == "global_emergency":
        # Global emergency is also a host-workflow boundary. If the
        # runtime dispatch fails before it can install durable rules, no
        # older preflight interaction may survive and start work later.
        host_cancel_candidates = list(active_host_interactions)
    elif (
        scope == "current_interaction"
        and not receipt.selected_request_bindings
    ):
        host_cancel_candidates = [
            (task, interaction_id)
            for task, interaction_id in active_host_interactions
            if interaction_id == active_interaction_id
        ]
    current_task = asyncio.current_task()
    for task, interaction_id in host_cancel_candidates:
        if (
            task is not None
            and task is not current_task
            and not task.done()
        ):
            task.cancel()
            if interaction_id:
                host_task_cancel_requested.append(
                    interaction_id
                )
    if host_task_cancel_requested:
        receipt = receipt.model_copy(
            update={
                "host_task_cancel_requested_interaction_ids": tuple(
                    sorted(
                        {
                            *receipt.host_task_cancel_requested_interaction_ids,
                            *host_task_cancel_requested,
                        }
                    )
                )
            }
        )

    host.session_log(
        source_turn_id,
        "cognitive_gateway_cancellation_dispatched: "
        "requested_scope=%s effective_scope=%s interactions=%s "
        "selected=%s active=%s queued=%s non_interruptible=%s "
        "provider_failures=%s dispatch_failures=%s",
        receipt.requested_scope,
        receipt.effective_scope,
        ",".join(receipt.interaction_ids) or "none",
        len(receipt.selected_request_bindings),
        len(receipt.active_request_bindings),
        len(receipt.queued_request_bindings),
        len(receipt.non_interruptible_request_bindings),
        len(receipt.provider_cancel_failure_evidence),
        len(receipt.dispatch_failures),
    )
    emergency_status = str(
        receipt.emergency_stop_evidence.get("status") or ""
    )
    if scope == "global_emergency" and emergency_status != "success":
        host.session_log(
            source_turn_id,
            "cognitive_gateway_emergency_stop_unconfirmed: status=%s "
            "evidence=%s",
            emergency_status or "missing",
            json.dumps(
                receipt.emergency_stop_evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    return receipt
