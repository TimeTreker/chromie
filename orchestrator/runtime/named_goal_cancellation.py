from __future__ import annotations

import asyncio
import json
from typing import Any

from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    PendingConfirmation,
)
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from shared.chromie_contracts.control import GoalCancellationEvidence
from shared.chromie_contracts.interaction import CapabilityRequest
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
)


class ActiveGoalCancellationRequiresRuntimeDispatch(ValueError):
    def __init__(self, goal_ids: list[str]) -> None:
        self.goal_ids = tuple(sorted(goal_ids))
        super().__init__(
            "active_goal_cancellation_requires_runtime_dispatch:"
            + ",".join(self.goal_ids)
        )


class NamedGoalCancellationClosureError(ValueError):
    """A named cancellation could not be closed without an uncertain claim."""

    def __init__(
        self,
        goal_ids: set[str] | list[str] | tuple[str, ...],
        *,
        stage: str,
        detail: str,
        runtime_dispatch_attempted: bool,
        receipt_count: int = 0,
    ) -> None:
        self.goal_ids = tuple(sorted(str(item) for item in goal_ids if str(item)))
        self.stage = str(stage or "unknown")
        self.detail = str(detail or "closure failed")[:500]
        self.runtime_dispatch_attempted = bool(runtime_dispatch_attempted)
        self.receipt_count = max(0, int(receipt_count))
        super().__init__(
            "named_goal_cancellation_closure_failed:"
            f"{self.stage}:dispatch_attempted={self.runtime_dispatch_attempted}:"
            f"receipts={self.receipt_count}:{self.detail}"
        )


def cancellation_target_goal_ids(
    resolution: CognitiveRuntimeResolution,
) -> set[str]:
    association = resolution.goal_association
    if association is None:
        return set()
    return {
        goal_id
        for item in association.associations
        if item.relationship == "cancel"
        for goal_id in item.target_goal_ids
    }



def replacement_target_goal_ids(
    resolution: CognitiveRuntimeResolution,
) -> set[str]:
    association = resolution.goal_association
    if association is None:
        return set()
    return {
        goal_id
        for goal in association.new_goals
        for goal_id in goal.supersedes_goal_ids
    }

def _request_source_goal_ids(request: CapabilityRequest) -> set[str]:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    values = metadata.get("source_goal_ids") or metadata.get("covers_goal_ids")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {
        str(item).strip()
        for item in values
        if str(item).strip()
    }


def _build_confirmation_remainder(
    *,
    confirmation_dialogue: ConfirmationDialogue | None,
    target_goal_ids: set[str],
) -> tuple[PendingConfirmation | None, dict[str, Any] | None]:
    """Revoke one affected confirmation without inventing replacement wording.

    A pending confirmation is an authorization token over one immutable Planner
    response. Once a named Goal is removed, the Host may mechanically revoke that
    token, but it may not synthesize a child plan, a narrowed confirmation prompt,
    or replacement speech for preserved Goals. Those still-open Goals are left for
    Planner state re-entry after cancellation reconciliation.
    """

    dialogue = confirmation_dialogue
    pending = getattr(dialogue, "pending", None)
    if pending is None:
        return None, None
    response = pending.response
    all_goal_ids = {
        goal_id
        for request in response.capabilities
        for goal_id in _request_source_goal_ids(request)
    }
    if not target_goal_ids.intersection(all_goal_ids):
        return None, None

    cancelled_request_ids: set[str] = set()
    for request in response.capabilities:
        owners = _request_source_goal_ids(request)
        overlap = owners.intersection(target_goal_ids)
        if overlap and owners - target_goal_ids:
            raise ValueError(
                "confirmation_rebuild_shared_owner_conflict:"
                + request.request_id
            )
        if overlap:
            cancelled_request_ids.add(request.request_id)
    if not cancelled_request_ids:
        return None, None

    return None, {
        "old_confirmation_id": pending.confirmation_id,
        "cancelled_request_ids": sorted(cancelled_request_ids),
        "cancelled_goal_ids": sorted(target_goal_ids),
        "released_confirmation_goal_ids": sorted(all_goal_ids - target_goal_ids),
        "replacement": None,
        "revoked_entire_confirmation": True,
    }


def goal_cancellation_success_evidence(
    *,
    source_turn_id: str,
    metadata: dict[str, Any],
) -> GoalCancellationEvidence:
    """Project reconciled cancellation facts into bounded Planner Evidence."""

    target_goal_ids = [
        str(item).strip()
        for item in metadata.get("target_goal_ids") or []
        if str(item).strip()
    ]
    coaffected_goal_ids = [
        str(item).strip()
        for item in metadata.get("coaffected_goal_ids") or []
        if str(item).strip()
    ]
    receipts = metadata.get("cancellation_receipts")
    transition = metadata.get("confirmation_transition")
    released_confirmation_goal_ids = (
        [
            str(item).strip()
            for item in transition.get("released_confirmation_goal_ids") or []
            if str(item).strip()
        ]
        if isinstance(transition, dict)
        else []
    )
    return GoalCancellationEvidence.create(
        source_turn_id=source_turn_id,
        target_goal_ids=target_goal_ids,
        coaffected_goal_ids=coaffected_goal_ids,
        released_confirmation_goal_ids=released_confirmation_goal_ids,
        status="cancelled",
        runtime_dispatch_attempted=bool(receipts),
        goal_state_reconciled=True,
        confirmation_state_reconciled=True,
        reason_code=(
            "wider_scope_cancelled"
            if coaffected_goal_ids
            else (
                "confirmation_revoked_and_cancelled"
                if isinstance(transition, dict)
                else "cancelled"
            )
        ),
    )


def goal_cancellation_failure_evidence(
    *,
    source_turn_id: str,
    target_goal_ids: set[str] | list[str] | tuple[str, ...],
    exc: Exception,
) -> GoalCancellationEvidence:
    """Project a failed/uncertain cancellation closure without user wording."""

    normalized_goal_ids = sorted(
        {str(item).strip() for item in target_goal_ids if str(item).strip()}
    )
    if isinstance(exc, ActiveGoalCancellationRequiresRuntimeDispatch):
        normalized_goal_ids = list(exc.goal_ids) or normalized_goal_ids
        return GoalCancellationEvidence.create(
            source_turn_id=source_turn_id,
            target_goal_ids=normalized_goal_ids,
            status="not_cancelled",
            runtime_dispatch_attempted=False,
            goal_state_reconciled=False,
            confirmation_state_reconciled=False,
            reason_code="runtime_dispatch_required",
        )
    if isinstance(exc, NamedGoalCancellationClosureError):
        normalized_goal_ids = list(exc.goal_ids) or normalized_goal_ids
        return GoalCancellationEvidence.create(
            source_turn_id=source_turn_id,
            target_goal_ids=normalized_goal_ids,
            status=("uncertain" if exc.runtime_dispatch_attempted else "not_cancelled"),
            runtime_dispatch_attempted=exc.runtime_dispatch_attempted,
            goal_state_reconciled=False,
            confirmation_state_reconciled=False,
            reason_code=f"closure_{exc.stage}",
        )
    return GoalCancellationEvidence.create(
        source_turn_id=source_turn_id,
        target_goal_ids=normalized_goal_ids,
        status="uncertain",
        runtime_dispatch_attempted=False,
        goal_state_reconciled=False,
        confirmation_state_reconciled=False,
        reason_code="control_commit_failed",
    )


async def _dispatch_goal_work_stop(
    *,
    conversation_state: Any,
    interaction_runtime: Any,
    confirmation_dialogue: ConfirmationDialogue | None,
    resolution: CognitiveRuntimeResolution,
    session_id: str,
    user_text: str,
    language: str,
    target_goal_ids: set[str],
    target_responsibility_status: str,
    dispatch_reason: str,
    source: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del language
    association = resolution.goal_association
    if association is None:
        raise ValueError("Goal Work stop requires Goal Association")
    if not target_goal_ids:
        return [], {}
    bindings_fn = getattr(
        conversation_state,
        "goal_cancellation_bindings",
        None,
    )
    reconcile_fn = getattr(
        conversation_state,
        (
            "apply_goal_replacement_resolution"
            if target_responsibility_status == "superseded"
            else "apply_goal_cancellation_resolution"
        ),
        None,
    )
    if not callable(bindings_fn) or not callable(reconcile_fn):
        raise ActiveGoalCancellationRequiresRuntimeDispatch(
            sorted(target_goal_ids)
        )
    bindings = bindings_fn(sorted(target_goal_ids))
    unknown = [
        item.get("goal_id")
        for item in bindings
        if not item.get("found")
    ]
    if unknown:
        raise ValueError(
            "named_goal_cancellation_unknown_target:"
            + ",".join(sorted(str(item) for item in unknown))
        )
    revalidation_required = [
        str(item.get("goal_id") or "")
        for item in bindings
        if item.get("requires_revalidation")
    ]
    if revalidation_required:
        raise NamedGoalCancellationClosureError(
            revalidation_required,
            stage="runtime_revalidation_required",
            detail=(
                "restored Work binding cannot be cancelled or superseded until "
                "fresh provider/runtime state revalidates it"
            ),
            runtime_dispatch_attempted=False,
        )
    try:
        replacement_pending, confirmation_transition = (
            _build_confirmation_remainder(
                confirmation_dialogue=confirmation_dialogue,
                target_goal_ids=target_goal_ids,
            )
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith(
            (
                "confirmation_rebuild_shared_owner_conflict:",
                "confirmation_rebuild_shared_plan_step:",
            )
        ):
            raise NamedGoalCancellationClosureError(
                target_goal_ids,
                stage="confirmation_scope_conflict",
                detail=message,
                runtime_dispatch_attempted=False,
            ) from exc
        raise
    pending = getattr(
        confirmation_dialogue,
        "pending",
        None,
    )
    pending_id = str(getattr(pending, "confirmation_id", "") or "")
    for binding in bindings:
        if binding.get("confirmation_pending") and (
            not pending_id
            or pending_id != binding.get("confirmation_id")
            or confirmation_transition is None
        ):
            raise ValueError(
                "named_goal_confirmation_binding_unavailable:"
                + str(binding.get("goal_id") or "")
            )

    confirmation_replace = None
    if confirmation_transition is not None:
        confirmation_replace = getattr(confirmation_dialogue, "replace", None)
        if not callable(confirmation_replace):
            raise NamedGoalCancellationClosureError(
                target_goal_ids,
                stage="confirmation_replacement_unavailable",
                detail="confirmation replacement unsupported",
                runtime_dispatch_attempted=False,
            )

    grouped: dict[tuple[str, str, str], set[str]] = {}
    for binding in bindings:
        if not binding.get("requires_runtime_dispatch"):
            continue
        interaction_id = str(binding.get("interaction_id") or "").strip()
        plan_id = str(binding.get("canonical_plan_id") or "").strip()
        fingerprint = str(
            binding.get("canonical_plan_fingerprint") or ""
        ).strip()
        if not interaction_id or not plan_id or not fingerprint:
            raise ValueError(
                "named_goal_runtime_binding_incomplete:"
                + str(binding.get("goal_id") or "")
            )
        grouped.setdefault(
            (interaction_id, plan_id, fingerprint), set()
        ).add(str(binding["goal_id"]))

    cancel_scope = getattr(interaction_runtime, "cancel_scope", None)
    if grouped and not callable(cancel_scope):
        raise ActiveGoalCancellationRequiresRuntimeDispatch(
            sorted(target_goal_ids)
        )
    directives = [
        CancellationDirective(
            source_turn_id=association.turn_id,
            requested_scope="specific_goal",
            foreground_interaction_id=interaction_id,
            target_goal_ids=tuple(sorted(goal_ids)),
            expected_plan_id=plan_id,
            expected_plan_fingerprint=fingerprint,
            reason=dispatch_reason,
        )
        for (interaction_id, plan_id, fingerprint), goal_ids in grouped.items()
    ]
    raw_receipts = await asyncio.gather(
        *(cancel_scope(item) for item in directives),
        return_exceptions=True,
    )
    receipts: list[CancellationDispatchReceipt] = []
    for directive, item in zip(directives, raw_receipts, strict=True):
        if isinstance(item, BaseException):
            raise NamedGoalCancellationClosureError(
                target_goal_ids,
                stage="runtime_dispatch",
                detail=f"{type(item).__name__}:{str(item)[:240]}",
                runtime_dispatch_attempted=True,
                receipt_count=len(receipts),
            ) from item
        receipts.append(
            item
            if isinstance(item, CancellationDispatchReceipt)
            else CancellationDispatchReceipt.model_validate(item)
        )

    if confirmation_transition is not None:
        current_pending = getattr(
            confirmation_dialogue,
            "pending",
            None,
        )
        if str(getattr(current_pending, "confirmation_id", "") or "") != str(
            confirmation_transition.get("old_confirmation_id") or ""
        ):
            raise NamedGoalCancellationClosureError(
                target_goal_ids,
                stage="confirmation_changed_after_dispatch",
                detail="pending confirmation changed during cancellation dispatch",
                runtime_dispatch_attempted=bool(directives),
                receipt_count=len(receipts),
            )

    try:
        reconcile_kwargs = {
            "receipts": receipts,
            "confirmation_transition": confirmation_transition,
            "sid": session_id,
            "user_text": user_text,
            "source": source,
        }
        goal_state_results = reconcile_fn(association, **reconcile_kwargs)
    except Exception as exc:
        raise NamedGoalCancellationClosureError(
            target_goal_ids,
            stage="goal_state_reconciliation",
            detail=f"{type(exc).__name__}:{str(exc)[:300]}",
            runtime_dispatch_attempted=bool(directives),
            receipt_count=len(receipts),
        ) from exc
    rejected = [
        item
        for item in goal_state_results
        if item.get("applied") is False
        and item.get("reason") != "operation_already_applied"
    ]
    if rejected:
        raise NamedGoalCancellationClosureError(
            target_goal_ids,
            stage="goal_state_reconciliation",
            detail=(
                "named_goal_cancellation_state_commit_rejected:"
                + json.dumps(rejected, ensure_ascii=False)
            ),
            runtime_dispatch_attempted=bool(directives),
            receipt_count=len(receipts),
        )

    if confirmation_transition is not None:
        try:
            if not callable(confirmation_replace):
                raise TypeError(
                    "confirmation replacement callback is required for a pending transition"
                )
            confirmation_replace(
                expected_confirmation_id=str(
                    confirmation_transition["old_confirmation_id"]
                ),
                pending=replacement_pending,
            )
        except Exception as exc:
            raise NamedGoalCancellationClosureError(
                target_goal_ids,
                stage="confirmation_replacement",
                detail=f"{type(exc).__name__}:{str(exc)[:300]}",
                runtime_dispatch_attempted=bool(directives),
                receipt_count=len(receipts),
            ) from exc

    coaffected_goal_ids = sorted(
        {
            goal_id
            for receipt in receipts
            for goal_id in receipt.affected_goal_ids
            if goal_id not in target_goal_ids
        }
    )
    metadata = {
        "target_goal_ids": sorted(target_goal_ids),
        "coaffected_goal_ids": coaffected_goal_ids,
        "cancellation_receipts": [
            item.model_dump(mode="json", exclude_none=True)
            for item in receipts
        ],
        "confirmation_transition": confirmation_transition,
    }
    return goal_state_results, metadata


async def dispatch_named_goal_cancellation(
    *,
    conversation_state: Any,
    interaction_runtime: Any,
    confirmation_dialogue: ConfirmationDialogue | None,
    resolution: CognitiveRuntimeResolution,
    session_id: str,
    user_text: str,
    language: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return await _dispatch_goal_work_stop(
        conversation_state=conversation_state,
        interaction_runtime=interaction_runtime,
        confirmation_dialogue=confirmation_dialogue,
        resolution=resolution,
        session_id=session_id,
        user_text=user_text,
        language=language,
        target_goal_ids=cancellation_target_goal_ids(resolution),
        target_responsibility_status="cancelled",
        dispatch_reason="Core-resolved named Goal cancellation",
        source="goal_driven_named_cancellation",
    )


async def dispatch_goal_replacement(
    *,
    conversation_state: Any,
    interaction_runtime: Any,
    confirmation_dialogue: ConfirmationDialogue | None,
    resolution: CognitiveRuntimeResolution,
    session_id: str,
    user_text: str,
    language: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return await _dispatch_goal_work_stop(
        conversation_state=conversation_state,
        interaction_runtime=interaction_runtime,
        confirmation_dialogue=confirmation_dialogue,
        resolution=resolution,
        session_id=session_id,
        user_text=user_text,
        language=language,
        target_goal_ids=replacement_target_goal_ids(resolution),
        target_responsibility_status="superseded",
        dispatch_reason="Core-resolved Goal replacement Work stop",
        source="goal_driven_goal_replacement",
    )


__all__ = [
    "ActiveGoalCancellationRequiresRuntimeDispatch",
    "NamedGoalCancellationClosureError",
    "cancellation_target_goal_ids",
    "replacement_target_goal_ids",
    "goal_cancellation_success_evidence",
    "goal_cancellation_failure_evidence",
    "dispatch_named_goal_cancellation",
    "dispatch_goal_replacement",
]
