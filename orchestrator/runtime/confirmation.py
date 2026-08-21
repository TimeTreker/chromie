from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse

ConfirmationDecision = Literal[
    "approved",
    "denied",
    "ambiguous",
    "expired",
    "operational_interrupt",
    "no_pending",
    "not_confirmation",
]
ConfirmationReplyMeaning = Literal["confirm", "reject", "ambiguous"]


@dataclass(frozen=True)
class PendingConfirmation:
    confirmation_id: str
    response: InteractionResponse
    confirmed_request_ids: frozenset[str]
    fingerprint: str
    prompt: str
    created_at: float
    expires_at: float
    origin_session_id: str | None
    conversation_id: str | None


@dataclass(frozen=True)
class ConfirmationResolution:
    decision: ConfirmationDecision
    confirmation_id: str | None = None
    response: InteractionResponse | None = None
    confirmed_request_ids: frozenset[str] = frozenset()
    fingerprint: str | None = None
    message: str = ""


class ConfirmationDialogue:
    """Single-use, request-bound spoken confirmation state."""

    def __init__(
        self,
        *,
        ttl_s: float = 20.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ttl_s = min(300.0, max(1.0, float(ttl_s)))
        self._clock = clock
        self._pending: PendingConfirmation | None = None

    @property
    def pending(self) -> PendingConfirmation | None:
        return self._pending

    def remaining_ttl_s(
        self,
        pending: PendingConfirmation | None = None,
    ) -> float:
        """Return the bounded remaining lifetime using this dialogue's clock."""

        candidate = pending or self._pending
        if candidate is None:
            return 0.0
        return max(0.0, float(candidate.expires_at) - float(self._clock()))

    def prepare(
        self,
        response: InteractionResponse,
        *,
        confirmed_request_ids: set[str],
        origin_session_id: str | None,
        conversation_id: str | None,
        language: str | None = None,
        prompt_override: str | None = None,
        ttl_s: float | None = None,
    ) -> PendingConfirmation:
        request_ids = frozenset(confirmed_request_ids)
        known_ids = {request.request_id for request in response.capabilities}
        if not request_ids:
            raise ValueError("confirmation must bind at least one skill request")
        if not request_ids.issubset(known_ids):
            unknown = sorted(request_ids - known_ids)
            raise ValueError(f"confirmation references unknown request IDs: {unknown}")

        stored = response.model_copy(deep=True)
        now = self._clock()
        effective_ttl_s = self.ttl_s if ttl_s is None else min(300.0, max(1.0, float(ttl_s)))
        prompt = (prompt_override or "").strip() or _confirmation_prompt(
            stored,
            request_ids,
            language=language,
        )
        pending = PendingConfirmation(
            confirmation_id=f"confirm_{uuid4().hex[:12]}",
            response=stored,
            confirmed_request_ids=request_ids,
            fingerprint=_request_fingerprint(stored, request_ids),
            prompt=prompt,
            created_at=now,
            expires_at=now + effective_ttl_s,
            origin_session_id=origin_session_id,
            conversation_id=conversation_id,
        )
        return pending

    def begin(
        self,
        response: InteractionResponse,
        *,
        confirmed_request_ids: set[str],
        origin_session_id: str | None,
        conversation_id: str | None,
        language: str | None = None,
        prompt_override: str | None = None,
        ttl_s: float | None = None,
    ) -> PendingConfirmation:
        pending = self.prepare(
            response,
            confirmed_request_ids=confirmed_request_ids,
            origin_session_id=origin_session_id,
            conversation_id=conversation_id,
            language=language,
            prompt_override=prompt_override,
            ttl_s=ttl_s,
        )
        self._pending = pending
        return pending

    def replace(
        self,
        *,
        expected_confirmation_id: str,
        pending: PendingConfirmation | None,
    ) -> PendingConfirmation | None:
        current = self._pending
        if current is None or current.confirmation_id != expected_confirmation_id:
            raise ValueError(
                "pending confirmation changed before replacement"
            )
        self._pending = pending
        return current

    def cancel(self) -> PendingConfirmation | None:
        pending = self._pending
        self._pending = None
        return pending

    def resolve(
        self,
        meaning: ConfirmationReplyMeaning,
        *,
        expected_confirmation_id: str | None = None,
    ) -> ConfirmationResolution:
        """Apply a typed semantic decision to the exact pending request.

        Language understanding is owned by Goal Association. This class owns
        only token lifetime, request identity, single use, and fail-closed
        authorization.
        """

        pending = self._pending
        if pending is None:
            return ConfirmationResolution(decision="not_confirmation")
        if (
            expected_confirmation_id is not None
            and pending.confirmation_id != expected_confirmation_id
        ):
            return ConfirmationResolution(decision="not_confirmation")

        self._pending = None
        if pending.expires_at <= self._clock():
            return self._resolution(
                pending,
                "expired",
                "That confirmation expired, so I will not perform the action.",
            )
        if _request_fingerprint(
            pending.response,
            pending.confirmed_request_ids,
        ) != pending.fingerprint:
            return self._resolution(
                pending,
                "ambiguous",
                "The requested action changed, so I will not perform it.",
            )
        if meaning == "confirm":
            return self._resolution(
                pending,
                "approved",
                "Confirmed.",
                include_request=True,
            )
        if meaning == "reject":
            return self._resolution(
                pending,
                "denied",
                "Okay, I will not perform that action.",
            )
        return self._resolution(
            pending,
            "ambiguous",
            "I did not get a clear yes or no, so I will not perform the action.",
        )

    @staticmethod
    def _resolution(
        pending: PendingConfirmation,
        decision: ConfirmationDecision,
        message: str,
        *,
        include_request: bool = False,
    ) -> ConfirmationResolution:
        return ConfirmationResolution(
            decision=decision,
            confirmation_id=pending.confirmation_id,
            response=(
                pending.response.model_copy(deep=True)
                if include_request
                else None
            ),
            confirmed_request_ids=(
                pending.confirmed_request_ids if include_request else frozenset()
            ),
            fingerprint=pending.fingerprint,
            message=message,
        )


def pending_confirmation_goal_ids(
    pending: PendingConfirmation,
) -> set[str]:
    """Return the exact Goals owned by the confirmation-bound requests."""

    goal_ids: set[str] = set()
    for request in pending.response.capabilities:
        if request.request_id not in pending.confirmed_request_ids:
            continue
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        raw_goal_ids = metadata.get("source_goal_ids")
        if isinstance(raw_goal_ids, str):
            raw_goal_ids = [raw_goal_ids]
        if not isinstance(raw_goal_ids, list):
            continue
        goal_ids.update(
            str(goal_id).strip()
            for goal_id in raw_goal_ids
            if str(goal_id).strip()
        )
    return goal_ids


def confirmation_meaning_from_goal_association(
    association: GoalAssociationResolution,
    *,
    pending_goal_ids: set[str],
) -> ConfirmationReplyMeaning:
    """Validate model-owned confirmation meaning against the exact scope."""

    if (
        not pending_goal_ids
        or association.new_goals
        or not association.associations
    ):
        return "ambiguous"
    relationships = {item.relationship for item in association.associations}
    targeted_goal_ids = {
        goal_id
        for item in association.associations
        for goal_id in item.target_goal_ids
    }
    if targeted_goal_ids != pending_goal_ids:
        return "ambiguous"
    if relationships == {"confirm"}:
        return "confirm"
    if relationships == {"reject"}:
        return "reject"
    return "ambiguous"


def revoke_pending_confirmation_for_reflex(
    dialogue: Any,
    *,
    cancellation_scope: str,
    interaction_registry: Any,
) -> PendingConfirmation | None:
    """Revoke an exact pending confirmation token when a fixed reflex requires it.

    This is mechanical token/scope policy only. It does not interpret the user,
    decide whether confirmation is semantically required, or mutate Goal meaning.
    """

    if cancellation_scope in {"output_only", "media_output"}:
        return None
    if cancellation_scope == "embodied_motion":
        pending = getattr(dialogue, "pending", None)
        if pending is None:
            return None
        confirmed = set(getattr(pending, "confirmed_request_ids", ()) or ())
        response = getattr(pending, "response", None)
        requests = getattr(response, "capabilities", ()) or ()
        has_motion = False
        seen_confirmed_request_ids: set[str] = set()
        unknown_confirmed_request = False
        for request in requests:
            if request.request_id not in confirmed:
                continue
            seen_confirmed_request_ids.add(request.request_id)
            try:
                definition = interaction_registry.get(request.capability_id)
            except (AttributeError, ValueError):
                unknown_confirmed_request = True
                continue
            if "embodied_motion" in definition.cancellation_domains:
                has_motion = True
                break
        if confirmed - seen_confirmed_request_ids:
            unknown_confirmed_request = True
        if not has_motion and not unknown_confirmed_request:
            return None
    cancel = getattr(dialogue, "cancel", None)
    return cancel() if callable(cancel) else None


def revoked_confirmation_evidence_for_reflex(
    pending: PendingConfirmation | None,
    *,
    cancellation_scope: str,
    interaction_registry: Any,
) -> dict[str, Any]:
    """Describe a revoked token without inventing Goal or execution truth."""

    if pending is None:
        return {}
    confirmation_id = str(getattr(pending, "confirmation_id", "") or "")
    fingerprint = str(getattr(pending, "fingerprint", "") or "")
    confirmed_request_ids = sorted(
        str(item) for item in (getattr(pending, "confirmed_request_ids", ()) or ())
    )
    motion_request_ids: set[str] = set()
    unknown_request_ids: set[str] = set()
    response = getattr(pending, "response", None)
    request_by_id = {
        str(request.request_id): request
        for request in (getattr(response, "capabilities", ()) or ())
    }
    for request_id in confirmed_request_ids:
        request = request_by_id.get(request_id)
        if request is None:
            unknown_request_ids.add(request_id)
            continue
        try:
            definition = interaction_registry.get(request.capability_id)
        except (AttributeError, ValueError):
            unknown_request_ids.add(request_id)
            continue
        if "embodied_motion" in definition.cancellation_domains:
            motion_request_ids.add(request_id)
    confirmation_scope_widened = bool(
        cancellation_scope == "embodied_motion"
        and (
            set(confirmed_request_ids) - motion_request_ids
            or unknown_request_ids
        )
    )
    return {
        "confirmation_id": confirmation_id,
        "fingerprint": fingerprint,
        "cancellation_scope": cancellation_scope,
        "confirmed_request_ids": confirmed_request_ids,
        "motion_request_ids": sorted(motion_request_ids),
        "unknown_request_ids": sorted(unknown_request_ids),
        "confirmation_scope_widened": confirmation_scope_widened,
        "widening_reason": (
            "shared_confirmation_token_revoked_conservatively"
            if confirmation_scope_widened
            else ""
        ),
    }


def reconcile_revoked_confirmation_for_reflex(
    pending: PendingConfirmation | None,
    *,
    conversation_state: Any,
    session_id: str,
    cancellation_scope: str,
    interaction_registry: Any,
    session_log: Callable[..., None],
) -> dict[str, Any]:
    """Synchronize a revoked token into Conversation State as fail-safe bookkeeping."""

    evidence = revoked_confirmation_evidence_for_reflex(
        pending,
        cancellation_scope=cancellation_scope,
        interaction_registry=interaction_registry,
    )
    confirmation_id = str(evidence.get("confirmation_id") or "")
    if not confirmation_id:
        return evidence
    resolved = False
    resolve_confirmation_scope = getattr(
        conversation_state,
        "resolve_confirmation_scope",
        None,
    )
    if callable(resolve_confirmation_scope):
        resolved = bool(
            resolve_confirmation_scope(
                confirmation_id=confirmation_id,
                decision="operational_interrupt",
            )
        )
    if not resolved:
        update_pending_task_status = getattr(
            conversation_state,
            "update_pending_task_status",
            None,
        )
        if callable(update_pending_task_status):
            update_pending_task_status(
                metadata_key="confirmation_id",
                metadata_value=confirmation_id,
                status="cancelled",
            )

    session_log(
        session_id,
        "cognitive_gateway_confirmation_cancelled: "
        "confirmation_id=%s fingerprint=%s scope=%s widened=%s",
        confirmation_id or "<unknown>",
        str(evidence.get("fingerprint") or "<unknown>"),
        cancellation_scope,
        bool(evidence.get("confirmation_scope_widened")),
    )
    return evidence

def _request_fingerprint(
    response: InteractionResponse,
    request_ids: frozenset[str],
) -> str:
    payload = {
        "interaction_id": response.interaction_id,
        "requests": [
            request.model_dump(mode="json")
            for request in response.capabilities
            if request.request_id in request_ids
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _confirmation_prompt(
    response: InteractionResponse,
    request_ids: frozenset[str],
    *,
    language: str | None,
) -> str:
    del response, request_ids
    if (language or "").lower().startswith("zh"):
        return "要我做刚才说的动作吗？你说“好”，我就开始啦！"
    return "Would you like me to do that? Say “yes” and I’ll get started!"
