from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    PendingConfirmation,
)
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
)
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
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


def _request_source_goal_ids(request: SkillRequest) -> set[str]:
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
    language: str,
) -> tuple[PendingConfirmation | None, dict[str, Any] | None]:
    """Prepare, but do not install, a narrowed confirmation token.

    The original canonical plan remains immutable.  Preserved work receives
    a deterministic child plan, fresh interaction/request identities, and a
    fresh confirmation token.  A step jointly owned by cancelled and
    preserved Goals is not separable and therefore fails closed.
    """

    dialogue = confirmation_dialogue
    pending = getattr(dialogue, "pending", None)
    if pending is None:
        return None, None
    response = pending.response.model_copy(deep=True)
    all_goal_ids = {
        goal_id
        for request in response.skills
        for goal_id in _request_source_goal_ids(request)
    }
    if not target_goal_ids.intersection(all_goal_ids):
        return None, None

    cancelled_request_ids: set[str] = set()
    preserved_requests: list[SkillRequest] = []
    for request in response.skills:
        owners = _request_source_goal_ids(request)
        overlap = owners.intersection(target_goal_ids)
        if overlap and owners - target_goal_ids:
            raise ValueError(
                "confirmation_rebuild_shared_owner_conflict:"
                + request.request_id
            )
        if overlap:
            cancelled_request_ids.add(request.request_id)
        else:
            preserved_requests.append(request)
    if not cancelled_request_ids:
        return None, None

    old_plan_raw = response.metadata.get("canonical_plan")
    child_plan: CanonicalPlan | None = None
    child_fingerprint = ""
    request_id_map: dict[str, str] = {}
    preserved_goal_ids: set[str] = all_goal_ids - target_goal_ids
    if isinstance(old_plan_raw, dict):
        old_plan = CanonicalPlan.model_validate(old_plan_raw)
        parent_fingerprint = canonical_plan_fingerprint(old_plan)
        for step in old_plan.steps:
            owners = set(step.source_goal_ids)
            if owners.intersection(target_goal_ids) and owners - target_goal_ids:
                raise ValueError(
                    "confirmation_rebuild_shared_plan_step:" + step.step_id
                )
        kept_goal_ids = [
            goal_id
            for goal_id in old_plan.goal_ids
            if goal_id not in target_goal_ids
        ]
        kept_steps = [
            step.model_copy(deep=True)
            for step in old_plan.steps
            if not set(step.source_goal_ids).intersection(target_goal_ids)
        ]
        kept_step_ids = {step.step_id for step in kept_steps}
        kept_outcomes = [
            item.model_copy(deep=True)
            for item in old_plan.goal_outcomes
            if item.goal_id in kept_goal_ids
        ]
        if kept_outcomes:
            dispositions = {item.disposition for item in kept_outcomes}
            disposition = (
                "mixed" if len(dispositions) > 1 else next(iter(dispositions))
            )
        else:
            disposition = "execute" if kept_steps else "respond"
        child_seed = hashlib.sha256(
            (
                parent_fingerprint
                + "|confirmation_remainder|"
                + ",".join(sorted(target_goal_ids))
            ).encode("utf-8")
        ).hexdigest()[:20]
        child_plan = old_plan.model_copy(
            deep=True,
            update={
                "plan_id": f"plan_confirmation_remainder_{child_seed}",
                "disposition": disposition,
                "goal_ids": kept_goal_ids,
                "steps": kept_steps,
                "goal_outcomes": kept_outcomes,
                "parameter_resolutions": [
                    item.model_copy(deep=True)
                    for item in old_plan.parameter_resolutions
                    if item.step_id in kept_step_ids
                    and not set(item.source_goal_ids).intersection(
                        target_goal_ids
                    )
                ],
                "goal_satisfaction": None,
                "response_text": (
                    old_plan.response_text if disposition == "respond" else ""
                ),
                "metadata": {
                    **old_plan.metadata,
                    "plan_relation": "confirmation_remainder",
                    "parent_plan_id": old_plan.plan_id,
                    "parent_plan_fingerprint": parent_fingerprint,
                    "cancelled_goal_ids": sorted(target_goal_ids),
                },
            },
        )
        child_plan = CanonicalPlan.model_validate(
            child_plan.model_dump(mode="python")
        )
        child_fingerprint = canonical_plan_fingerprint(child_plan)
        remapped: list[SkillRequest] = []
        for request in preserved_requests:
            step_id = str(request.metadata.get("step_id") or "").strip()
            digest = hashlib.sha256(
                f"{child_fingerprint}|{step_id}|{request.request_id}".encode(
                    "utf-8"
                )
            ).hexdigest()[:20]
            new_request_id = f"cogreq_{digest}"
            request_id_map[request.request_id] = new_request_id
            remapped.append(
                request.model_copy(
                    deep=True,
                    update={
                        "request_id": new_request_id,
                        "idempotency_key": (
                            f"{child_plan.plan_id}:{step_id}:"
                            f"{child_fingerprint[:16]}"
                        ),
                        "metadata": {
                            **request.metadata,
                            "canonical_plan_id": child_plan.plan_id,
                            "canonical_plan_fingerprint": child_fingerprint,
                            "confirmation_remainder_from_request_id": (
                                request.request_id
                            ),
                        },
                    },
                )
            )
        preserved_requests = remapped

    preserved_confirmed_ids = {
        request_id_map.get(request_id, request_id)
        for request_id in pending.confirmed_request_ids
        if request_id not in cancelled_request_ids
    }
    replacement_pending: PendingConfirmation | None = None
    replacement_response: InteractionResponse | None = None
    request_ids_by_goal: dict[str, list[str]] = {}
    confirmation_request_ids_by_goal: dict[str, list[str]] = {}
    if preserved_requests and preserved_confirmed_ids:
        if child_plan is None:
            raise ValueError(
                "confirmation_rebuild_requires_canonical_plan"
            )
        preserved_speech: list[InteractionSpeech] = []
        for speech in response.speech:
            metadata = speech.metadata if isinstance(speech.metadata, dict) else {}
            covered = metadata.get("covers_goal_ids")
            if isinstance(covered, str):
                covered = [covered]
            covered_ids = {
                str(item).strip()
                for item in (covered or [])
                if str(item).strip()
            }
            if not covered_ids or covered_ids.intersection(target_goal_ids):
                continue
            digest = hashlib.sha256(
                f"{child_fingerprint}|speech|{speech.id}".encode("utf-8")
            ).hexdigest()[:16]
            preserved_speech.append(
                speech.model_copy(
                    deep=True,
                    update={
                        "id": f"speech_{digest}",
                        "metadata": {
                            **metadata,
                            "canonical_plan_id": child_plan.plan_id,
                            "canonical_plan_fingerprint": child_fingerprint,
                            "source_goal_ids": sorted(covered_ids),
                        },
                    },
                )
            )
        if not preserved_speech:
            zh = str(language or "").lower().startswith("zh")
            preserved_speech = [
                InteractionSpeech(
                    id=f"speech_confirmation_remainder_{child_fingerprint[:12]}",
                    text=(
                        "我会继续执行其余已确认的动作。"
                        if zh
                        else "I will continue with the remaining confirmed actions."
                    ),
                    timing="sequential",
                    style="brief",
                    metadata={
                        "source": "host_confirmation_remainder",
                        "phase": "pre_action",
                        "covers_goal_ids": sorted(preserved_goal_ids),
                        "source_goal_ids": sorted(preserved_goal_ids),
                        "canonical_plan_id": child_plan.plan_id,
                        "canonical_plan_fingerprint": child_fingerprint,
                        "must_not_claim_completion": True,
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                        "playback_start_required_for_effects": True,
                    },
                )
            ]
        interaction_seed = hashlib.sha256(
            f"{child_fingerprint}|{pending.confirmation_id}".encode("utf-8")
        ).hexdigest()[:16]
        replacement_response = response.model_copy(
            deep=True,
            update={
                "interaction_id": f"interaction_confirmation_remainder_{interaction_seed}",
                "speech": preserved_speech,
                "skills": preserved_requests,
                "requires_confirmation": True,
                "metadata": {
                    **response.metadata,
                    "canonical_plan": child_plan.model_dump(
                        mode="json", exclude_none=True
                    ),
                    "canonical_plan_id": child_plan.plan_id,
                    "canonical_plan_fingerprint": child_fingerprint,
                    "goal_ids": child_plan.goal_ids,
                    "confirmation_remainder": True,
                    "replaces_confirmation_id": pending.confirmation_id,
                    "cancelled_goal_ids": sorted(target_goal_ids),
                    "response_composition_superseded": True,
                },
            },
        )
        replacement_pending = dialogue.prepare(
            replacement_response,
            confirmed_request_ids=preserved_confirmed_ids,
            origin_session_id=pending.origin_session_id,
            conversation_id=pending.conversation_id,
            language=language,
            ttl_s=max(
                1.0,
                dialogue.remaining_ttl_s(pending),
            ),
        )
        for request in replacement_response.skills:
            for goal_id in _request_source_goal_ids(request):
                request_ids_by_goal.setdefault(goal_id, []).append(
                    request.request_id
                )
                if request.request_id in preserved_confirmed_ids:
                    confirmation_request_ids_by_goal.setdefault(
                        goal_id, []
                    ).append(request.request_id)

    transition = {
        "old_confirmation_id": pending.confirmation_id,
        "cancelled_request_ids": sorted(cancelled_request_ids),
        "cancelled_goal_ids": sorted(target_goal_ids),
        "replacement": (
            {
                "confirmation_id": replacement_pending.confirmation_id,
                "fingerprint": replacement_pending.fingerprint,
                "expires_at": replacement_pending.expires_at,
                "interaction_id": replacement_response.interaction_id,
                "canonical_plan_id": child_plan.plan_id,
                "canonical_plan_fingerprint": child_fingerprint,
                "request_ids_by_goal": request_ids_by_goal,
                "confirmation_request_ids_by_goal": (
                    confirmation_request_ids_by_goal
                ),
            }
            if replacement_pending is not None
            else None
        ),
    }
    return replacement_pending, transition


async def dispatch_named_goal_cancellation(
    *,
    conversation_state: Any,
    interaction_runtime: Any,
    confirmation_dialogue: ConfirmationDialogue | None,
    resolution: CognitiveRuntimeResolution,
    session_id: str,
    user_text: str,
    decision: RouteDecision,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    association = resolution.goal_association
    if association is None:
        raise ValueError("named cancellation requires Goal Association")
    target_goal_ids = cancellation_target_goal_ids(resolution)
    if not target_goal_ids:
        return [], {}
    bindings_fn = getattr(
        conversation_state,
        "goal_cancellation_bindings",
        None,
    )
    reconcile_fn = getattr(
        conversation_state,
        "apply_goal_cancellation_resolution",
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
    try:
        replacement_pending, confirmation_transition = (
            _build_confirmation_remainder(
                confirmation_dialogue=confirmation_dialogue,
                target_goal_ids=target_goal_ids,
                language=decision.language,
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
            reason="Core-resolved named Goal cancellation",
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
        goal_state_results = reconcile_fn(
            association,
            receipts=receipts,
            confirmation_transition=confirmation_transition,
            sid=session_id,
            user_text=user_text,
            route=decision.route,
            intent=decision.intent,
            source="goal_driven_named_cancellation",
        )
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
            assert callable(confirmation_replace)
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
        "replacement_confirmation_prompt": (
            replacement_pending.prompt
            if replacement_pending is not None
            else ""
        ),
    }
    return goal_state_results, metadata


__all__ = [
    "ActiveGoalCancellationRequiresRuntimeDispatch",
    "NamedGoalCancellationClosureError",
    "cancellation_target_goal_ids",
    "dispatch_named_goal_cancellation",
]
