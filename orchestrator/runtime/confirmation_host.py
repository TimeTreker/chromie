"""Pending-confirmation staging and reply handling for the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host``. Reply
meaning comes from Goal Association; confirmation token bookkeeping stays in
``orchestrator.runtime.confirmation``.
"""

from __future__ import annotations

from typing import Any


from orchestrator.runtime.confirmation import (
    ConfirmationReplyMeaning,
    PendingConfirmation,
    confirmation_meaning_from_goal_association,
    pending_confirmation_goal_ids,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
)
from shared.chromie_contracts.user_turn import (
    UserTurnEnvelope,
)


async def stage_interaction_confirmation(
    host: Any,
    response: InteractionResponse,
    session_id: str,
    *,
    language: str | None,
    reset_playback: bool = True,
) -> bool:
    confirmation_request_ids = (
        await host.interaction_runtime.confirmation_request_ids(response)
    )
    if not confirmation_request_ids:
        return False

    confirmation_prompt = str(
        (response.metadata or {}).get("confirmation_prompt") or ""
    ).strip()
    pending = host.confirmation_dialogue.begin(
        response,
        confirmed_request_ids=confirmation_request_ids,
        origin_session_id=session_id,
        conversation_id=host.conversation_state.conversation_id,
        prompt_override=confirmation_prompt or None,
    )
    host.session_log(
        session_id,
        "confirmation_requested: confirmation_id=%s interaction_id=%s "
        "request_ids=%s fingerprint=%s expires_at=%.3f",
        pending.confirmation_id,
        response.interaction_id,
        ",".join(sorted(pending.confirmed_request_ids)),
        pending.fingerprint,
        pending.expires_at,
    )
    prompt_response = host._host_speech_response(
        pending.prompt,
        style="confirm",
    )
    prompt_response = prompt_response.model_copy(
        deep=True,
        update={
            "metadata": {
                **prompt_response.metadata,
                **({"user_turn_envelope": response.metadata["user_turn_envelope"]}
                   if isinstance(response.metadata.get("user_turn_envelope"), dict) else {}),
                "history_after_successful_delivery": True,
                "confirmation_id": pending.confirmation_id,
            }
        },
    )
    record_confirmation_scope = getattr(
        host.conversation_state,
        "record_confirmation_scope",
        None,
    )
    if callable(record_confirmation_scope):
        record_confirmation_scope(
            sid=session_id,
            confirmation_id=pending.confirmation_id,
            interaction_id=response.interaction_id,
            fingerprint=pending.fingerprint,
            expires_at=pending.expires_at,
            response=response,
            confirmed_request_ids=set(pending.confirmed_request_ids),
        )
    else:  # pragma: no cover - compatibility with lightweight test doubles
        host.conversation_state.record_pending_task(
            sid=session_id,
            task_type="confirmation",
            status="awaiting_confirmation",
            summary=", ".join(
                request.capability_id
                for request in response.capabilities
                if request.request_id in pending.confirmed_request_ids
            ),
            metadata={
                "confirmation_id": pending.confirmation_id,
                "interaction_id": response.interaction_id,
                "fingerprint": pending.fingerprint,
                "expires_at": pending.expires_at,
            },
        )
    host._launch_interaction(
        prompt_response,
        session_id,
        reset_playback=reset_playback,
    )
    return True


async def handle_confirmation_reply(
    host: Any,
    user_text: str,
    session_id: str,
    *,
    turn_envelope: UserTurnEnvelope | None = None,
) -> bool:
    pending = host.confirmation_dialogue.pending
    if pending is None:
        return False
    meaning = await host._resolve_pending_confirmation_meaning(
        user_text,
        session_id=session_id,
        pending=pending,
    )
    resolution = host.confirmation_dialogue.resolve(
        meaning,
        expected_confirmation_id=pending.confirmation_id,
    )
    if resolution.decision == "not_confirmation":
        return False

    host.conversation_state.record_user_turn(
        session_id,
        user_text,
        metadata=host._metadata_with_turn_envelope(
            {
                "confirmation_id": resolution.confirmation_id,
                "fingerprint": resolution.fingerprint,
            },
            turn_envelope,
        ),
    )
    host.session_log(
        session_id,
        "confirmation_reply: confirmation_id=%s decision=%s fingerprint=%s",
        resolution.confirmation_id,
        resolution.decision,
        resolution.fingerprint,
    )
    if resolution.confirmation_id:
        resolve_confirmation_scope = getattr(
            host.conversation_state,
            "resolve_confirmation_scope",
            None,
        )
        handled = bool(
            callable(resolve_confirmation_scope)
            and resolve_confirmation_scope(
                confirmation_id=resolution.confirmation_id,
                decision=resolution.decision,
            )
        )
        if not handled:
            pending_status = {
                "approved": "done",
                "expired": "expired",
            }.get(resolution.decision, "cancelled")
            host.conversation_state.update_pending_task_status(
                metadata_key="confirmation_id",
                metadata_value=resolution.confirmation_id,
                status=pending_status,
            )

    if resolution.decision == "approved":
        if resolution.response is None:
            raise RuntimeError(
                "approved confirmation resolution is missing its bound response"
            )
        host.session_log(
            session_id,
            "confirmation_authorized: confirmation_id=%s interaction_id=%s "
            "request_ids=%s fingerprint=%s",
            resolution.confirmation_id,
            resolution.response.interaction_id,
            ",".join(sorted(resolution.confirmed_request_ids)),
            resolution.fingerprint,
        )
        host.conversation_state.record_interaction_response(
            session_id,
            resolution.response,
            confirmed_request_ids=set(resolution.confirmed_request_ids),
        )
        host._launch_interaction(
            resolution.response,
            session_id,
            confirmed_request_ids=set(resolution.confirmed_request_ids),
        )
        return True

    host.session_log(
        session_id,
        "confirmation_rejected: confirmation_id=%s reason=%s fingerprint=%s",
        resolution.confirmation_id,
        resolution.decision,
        resolution.fingerprint,
    )
    # Confirmation state is deterministic authorization truth, not a speech
    # author.  A rejected/expired/ambiguous token therefore closes fail-safe
    # without inventing Host dialogue.  A later Planner opportunity may choose
    # a communicative Activity from the updated Goal/Situation state.
    sessions = getattr(host, "sessions", None)
    state_map = getattr(sessions, "state", None)
    if isinstance(state_map, dict):
        state = state_map.get(session_id)
        if isinstance(state, dict):
            state["llm_done"] = True
    maybe_session_done = getattr(host, "maybe_session_done", None)
    if sessions is not None and callable(maybe_session_done):
        maybe_session_done(session_id)
    return True


async def resolve_pending_confirmation_meaning(
    host: Any,
    user_text: str,
    *,
    session_id: str,
    pending: PendingConfirmation,
) -> ConfirmationReplyMeaning:
    """Ask Goal Association for meaning; never infer it from user phrases."""

    pending_goal_ids = pending_confirmation_goal_ids(pending)
    if not pending_goal_ids:
        host.session_log(
            session_id,
            "confirmation_semantics_failed_closed: confirmation_id=%s reason=missing_goal_scope",
            pending.confirmation_id,
        )
        return "ambiguous"
    context = host.build_context(session_id)
    context = {
        **context,
        "pending_confirmation_scope": {
            "confirmation_id": pending.confirmation_id,
            "goal_ids": sorted(pending_goal_ids),
        },
    }
    request = CognitiveWorkRequest(
        sid=session_id,
        text=user_text,
        language="zh-CN" if host._looks_zh(user_text) else "en-US",
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref="pending_confirmation_reply",
                outcome=user_text,
                confidence=1.0,
            )
        ],
        interpretation_confidence=1.0,
        context=context,
        history=list(context.get("history", [])),
    )
    try:
        session = await host.get_http_session()
        association = await host.agent_client.resolve_goal_association(
            session,
            request=request,
            timeout_ms=host.goal_association_timeout_ms,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "confirmation_semantics_failed_closed: confirmation_id=%s reason=%s error=%s",
            pending.confirmation_id,
            type(exc).__name__,
            str(exc)[:300],
        )
        return "ambiguous"
    meaning = confirmation_meaning_from_goal_association(
        association,
        pending_goal_ids=pending_goal_ids,
    )
    host.session_log(
        session_id,
        "confirmation_semantics_resolved: confirmation_id=%s meaning=%s relationships=%s targets=%s",
        pending.confirmation_id,
        meaning,
        ",".join(item.relationship for item in association.associations) or "none",
        ",".join(
            sorted(
                goal_id
                for item in association.associations
                for goal_id in item.target_goal_ids
            )
        )
        or "none",
    )
    return meaning
