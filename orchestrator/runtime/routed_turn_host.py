"""Routed-turn intake for the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host`` and run one
admitted text or speech turn through the Cognitive Gateway and Core dispatch.
"""

from __future__ import annotations

import json
import logging
from typing import Any


from orchestrator.runtime.confirmation import (
    reconcile_revoked_confirmation_for_reflex,
    revoke_pending_confirmation_for_reflex,
)
from orchestrator.runtime.observability_recording import (
    record_cognitive_gateway_evidence,
)
from orchestrator.runtime.session import (
    now_ms,
    record_session_workflow_stage,
)
from orchestrator.runtime import cognitive_pipeline_host

logger = logging.getLogger("chromie-orchestrator")


def safe_immediate_route_speech(text: str | None) -> str | None:
    """Apply only transport-safe checks to source-authored immediate speech.

    Semantic wording is owned by the Planner's Communicative Activity. Typed
    Planner provenance carries the mechanical claim boundary; the Host does not add a
    second semantic LLM or infer meaning from phrases, keywords, or punctuation.
    """

    cleaned = " ".join((text or "").strip().split())
    if not cleaned or len(cleaned) > 120:
        return None
    lowered = cleaned.casefold()
    if any(marker in lowered for marker in (
        "soridormi.",
        "chromie.",
    )):
        return None
    if any(ord(char) < 32 and char not in {"\t", "\n", "\r"} for char in cleaned):
        return None
    return cleaned


async def handle_routed_text(
    host: Any,
    user_text: str,
    session_id: str,
    *,
    channel: str = "voice",
) -> None:
    gateway = host._cognitive_gateway_adapter()
    turn_capture = gateway.capture(
        user_text,
        session_id=session_id,
        conversation_id=cognitive_pipeline_host.current_conversation_id(host, session_id),
        channel=channel,
    )
    reflex_outcome = turn_capture.reflex_candidate
    residual_semantic_input = bool(
        reflex_outcome.action == "interrupt"
        and reflex_outcome.cancellation_scope == "output_only"
        and reflex_outcome.metadata.get("residual_semantic_input") is True
    )
    boundary = None
    if reflex_outcome.action == "interrupt":
        host.session_log(
            session_id,
            "cognitive_gateway_reflex_detected: action=%s trigger=%s scope=%s confidence=%.2f",
            reflex_outcome.action,
            reflex_outcome.trigger,
            reflex_outcome.cancellation_scope,
            reflex_outcome.confidence,
        )
        revoked_confirmation = revoke_pending_confirmation_for_reflex(
            getattr(host, "confirmation_dialogue", None),
            cancellation_scope=reflex_outcome.cancellation_scope,
            interaction_registry=getattr(
                getattr(host, "interaction_runtime", None),
                "registry",
                None,
            ),
        )
        # The approval token is revoked synchronously before the first
        # await, so slow trusted-provider cancellation cannot leave an old
        # action approvable. Persistence and goal-state reconciliation run
        # only after interruption has begun, so they cannot delay stopping.
        try:
            cancellation_receipt = await host._apply_reflex_cancellation(
                reflex_outcome,
                source_turn_id=session_id,
            )
        except BaseException:
            # The approval token was already revoked synchronously. If the
            # operational dispatch itself cannot return a receipt, retain
            # that revocation through the compatibility state path before
            # propagating the failure.
            reconcile_revoked_confirmation_for_reflex(
                revoked_confirmation,
                conversation_state=getattr(host, "conversation_state", None),
                session_id=session_id,
                cancellation_scope=reflex_outcome.cancellation_scope,
                interaction_registry=getattr(
                    getattr(host, "interaction_runtime", None),
                    "registry",
                    None,
                ),
                session_log=host.session_log,
            )
            raise
        cancellation_reconciliation = (
            host._reconcile_reflex_cancellation_receipt(
                cancellation_receipt,
                revoked_confirmation,
                session_id,
                user_text=user_text,
                cancellation_scope=reflex_outcome.cancellation_scope,
                )
        )
        cancelled_confirmation = dict(
            cancellation_reconciliation.get(
                "cancelled_confirmation"
            )
            or {}
        )
        reflex_metadata = dict(reflex_outcome.metadata)
        if cancelled_confirmation:
            reflex_metadata["cancelled_confirmation"] = (
                cancelled_confirmation
            )
        reflex_metadata["cancellation_goal_reconciliation"] = (
            cancellation_reconciliation
        )
        reflex_outcome = reflex_outcome.model_copy(
            update={"metadata": reflex_metadata}
        )
        turn_capture = gateway.with_reflex_outcome(
            turn_capture,
            reflex_outcome,
        )
        if residual_semantic_input:
            # Cancel first, then evaluate idle expiry before this receipt
            # updates last_activity_ms. Active work keeps its existing
            # conversation through the usual boundary owner.
            boundary = host.conversation_state.prepare_for_user_text(
                user_text, session_id
            )
            turn_capture = gateway.with_conversation_id(
                turn_capture, boundary.get("conversation_id")
            )
        turn_envelope = gateway.for_reflex(turn_capture)
        record_cognitive_gateway_evidence(
            getattr(host, "cognitive_evidence", None),
            turn_envelope,
            user_text=user_text,
            session_log=host.session_log,
        )
        host.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=host._metadata_with_turn_envelope(
                {
                    "source": "cognitive_gateway_reflex",
                    "confidence": reflex_outcome.confidence,
                    "reflex_outcome": reflex_outcome.model_dump(mode="json"),
                    "cancellation_dispatch_receipt": (
                        cancellation_receipt.model_dump(mode="json")
                    ),
                    "cancellation_goal_reconciliation": (
                        cancellation_reconciliation
                    ),
                },
                turn_envelope,
            ),
        )
        host.session_log(
            session_id,
            "cognitive_gateway_reflex_applied: action=%s trigger=%s user_meaning_interpretation_bypassed=%s",
            reflex_outcome.action,
            reflex_outcome.trigger,
            not residual_semantic_input,
        )
        if not residual_semantic_input:
            state = host.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            host.maybe_session_done(session_id)
            return

    if reflex_outcome.action == "ignore":
        turn_envelope = gateway.for_suppression(turn_capture)
        record_cognitive_gateway_evidence(
            getattr(host, "cognitive_evidence", None),
            turn_envelope,
            user_text=user_text,
            session_log=host.session_log,
        )
        host.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=host._metadata_with_turn_envelope(
                {
                    "source": "cognitive_gateway_reflex",
                    "confidence": reflex_outcome.confidence,
                    "reflex_outcome": reflex_outcome.model_dump(mode="json"),
                },
                turn_envelope,
            ),
        )
        host.session_log(
            session_id,
            "cognitive_gateway_reflex_applied: action=%s trigger=%s user_meaning_interpretation_bypassed=True",
            reflex_outcome.action,
            reflex_outcome.trigger,
        )
        state = host.sessions.state.get(session_id)
        if state is not None:
            state["llm_done"] = True
        host.maybe_session_done(session_id)
        return

    if boundary is None:
        boundary = host.conversation_state.prepare_for_user_text(user_text, session_id)
    turn_capture = gateway.with_conversation_id(
        turn_capture,
        boundary.get("conversation_id"),
    )
    if boundary.get("started_new"):
        host.session_log(
            session_id,
            "conversation_boundary: started_new=True conversation_id=%s reason=%s",
            boundary.get("conversation_id"),
            boundary.get("reason"),
        )

    session = await host.get_http_session()
    context = host.build_context(session_id)
    if residual_semantic_input:
        # The protective receipt is retained before admission. It is this
        # turn's evidence, not a previously accepted dialogue turn.
        context["history"] = [
            item for item in context.get("history", [])
            if not (item.get("role") == "user" and item.get("sid") == session_id)
        ]
    interaction_ledger = getattr(
        getattr(host, "cognitive_runtime", None),
        "interaction_ledger",
        None,
    )
    if interaction_ledger is not None:
        context["interaction_context"] = interaction_ledger.context(
            str(session_id or ""),
            turn_id=turn_capture.turn_id,
        ).model_dump(mode="json")
    turn_capture = gateway.with_conversation_id(
        turn_capture,
        context.get("conversation_id"),
    )
    host.sessions.update_trace_correlations(
        session_id,
        conversation_id=context.get("conversation_id"),
    )
    host.session_log(
        session_id,
        "context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s engagement=%s",
        context.get("conversation_id"),
        len(context.get("history", [])),
        len(context.get("active_pending_tasks", [])),
        json.dumps(
            context.get("interaction_engagement", {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    host._log_goal_list(
        session_id,
        phase="before_turn",
        active_goals=context.get("active_goal_snapshots") or [],
        recent_terminal_goals=context.get("recent_goal_snapshots") or [],
    )
    context_snapshot = gateway.assemble_context(turn_capture, context)
    if residual_semantic_input:
        # The protective control has already run. Preserve its envelope and
        # admit the unchanged whole utterance to the one semantic authority.
        turn_envelope = gateway.for_reflex(turn_capture, context=context)
        record_cognitive_gateway_evidence(
            getattr(host, "cognitive_evidence", None),
            turn_envelope,
            user_text=user_text,
            context_snapshot=context_snapshot,
            session_log=host.session_log,
        )
    else:
        attention_request = gateway.attention_request(
            turn_capture,
            context_snapshot,
        )
        attention_started_ms = now_ms()
        attention_errors: list[dict[str, str]] = []
        try:
            review_attention = host.agent_client.review_attention
            attention_review = await review_attention(
                session,
                request=attention_request,
            )
        except Exception as exc:
            attention_errors.append(
                {"error_type": type(exc).__name__, "error": str(exc)}
            )
            logger.warning(
                "Cognitive Gateway attention review failed open: %s",
                exc,
            )
            attention_review = gateway.attention_fail_open(
                attention_request,
                reason=f"attention review unavailable: {type(exc).__name__}",
            )
        record_session_workflow_stage(
            host,
            session_id,
            stage="cognitive_gateway_attention",
            started_monotonic_ms=attention_started_ms,
            finished_monotonic_ms=now_ms(),
            status=("failed_open" if attention_errors else "accepted"),
            input_payload={
                "user_turn": turn_capture,
                "context_snapshot": context_snapshot,
            },
            output_payload=attention_review,
            errors=attention_errors,
        )
        turn_envelope = gateway.admit_attention(
            turn_capture,
            context_snapshot,
            attention_review,
        )
        record_cognitive_gateway_evidence(
            getattr(host, "cognitive_evidence", None),
            turn_envelope,
            user_text=user_text,
            context_snapshot=context_snapshot,
            attention_review=attention_review,
            session_log=host.session_log,
        )
        host.session_log(
            session_id,
            "cognitive_gateway_attention_done: disposition=%s speech_act=%s confidence=%.2f source=%s",
            attention_review.disposition,
            attention_review.speech_act,
            attention_review.confidence,
            attention_review.source,
        )
        if turn_envelope.admission == "suppress":
            host.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=host._metadata_with_turn_envelope(
                    {
                        "source": attention_review.source,
                        "confidence": attention_review.confidence,
                        "speech_act": attention_review.speech_act,
                        "reason": attention_review.reason,
                    },
                    turn_envelope,
                ),
            )
            state = host.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            host.maybe_session_done(session_id)
            return

        # A pending confirmation is resolved only by input the Gateway has
        # admitted. Noise/filler ignored by the reflex and room speech that
        # Attention Review suppressed returned above, so neither can reach
        # the model call that approves or denies a pending action.
        if await host._handle_confirmation_reply(
            user_text,
            session_id,
            turn_envelope=turn_envelope,
        ):
            return

    context["user_turn_envelope"] = turn_envelope.model_dump(mode="json")

    # Admission is already trusted dialogue evidence even though Goal
    # Association has not run yet. Publish only the user utterance here so a
    # concurrent follow-up can resolve ellipsis/reference against it. Canonical
    # Goal and Task state remains model-owned and is committed later.
    host.conversation_state.record_accepted_user_turn(
        session_id,
        user_text,
        metadata=host._metadata_with_turn_envelope(
            {
                "source": "cognitive_gateway_admitted_dialogue",
                "admission": turn_envelope.admission,
            },
            turn_envelope,
        ),
    )
    core_start_ms = now_ms()
    host.session_log(
        session_id,
        "cognitive_core_start: text_chars=%s text=%r admission=%s",
        len(user_text),
        user_text,
        turn_envelope.admission,
    )
    try:
        core_interpretation = await host.agent_client.interpret_turn(
            session,
            turn_envelope=turn_envelope,
            context_snapshot=context_snapshot,
        )
        core_interpretation_latency_ms = now_ms() - core_start_ms
        host.session_log(
            session_id,
            "cognitive_core_done: core_ms=%.1f responsibilities=%s confidence=%.2f unresolved=%s authority=%s",
            core_interpretation_latency_ms,
            len(core_interpretation.responsibilities),
            core_interpretation.confidence,
            len(core_interpretation.meaning_uncertainties),
            core_interpretation.authority,
        )
        record_session_workflow_stage(
            host,
            session_id,
            stage="user_meaning_interpretation",
            started_monotonic_ms=core_start_ms,
            finished_monotonic_ms=now_ms(),
            status="accepted",
            input_payload={
                "user_turn_envelope": turn_envelope,
                "context_snapshot": context_snapshot,
            },
            output_payload={
                "core_interpretation": core_interpretation,
            },
            errors=[],
        )
    except Exception as exc:
        record_session_workflow_stage(
            host,
            session_id,
            stage="user_meaning_interpretation",
            started_monotonic_ms=core_start_ms,
            finished_monotonic_ms=now_ms(),
            status="failed",
            input_payload={
                "user_turn_envelope": turn_envelope,
                "context_snapshot": context_snapshot,
            },
            output_payload=None,
            errors=[
                {"error_type": type(exc).__name__, "error": str(exc)}
            ],
        )
        host.session_log(session_id, "cognitive_core_exception: core_ms=%.1f error=%s", now_ms() - core_start_ms, exc)
        logger.warning("Cognitive Core interpretation failed; falling back safely: %s", exc)
        safe_response = host._cognitive_core_exception_safe_response(
            user_text,
            context=context,
            failure_stage="user_meaning_interpretation",
            failure_class=type(exc).__name__,
            failure_error=str(exc),
        )
        host.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=host._metadata_with_turn_envelope(
                {
                    "source": "cognitive_core_exception",
                    "error": str(exc),
                    "semantic_status": "failed",
                    "semantic_failure_stage": "user_meaning_interpretation",
                    "semantic_failure_class": type(exc).__name__,
                    "canonical_goal_committed": False,
                },
                turn_envelope,
            ),
        )
        host.session_log(
            session_id,
            "cognitive_core_exception_safe_fallback: embodied=%s text=%r",
            bool(safe_response.metadata.get("embodied_request")),
            user_text,
        )
        record_session_workflow_stage(
            host,
            session_id,
            stage="fallback_speech",
            started_monotonic_ms=now_ms(),
            finished_monotonic_ms=now_ms(),
            status="selected",
            input_payload={
                "failure_stage": "user_meaning_interpretation",
                "user_text": user_text,
            },
            output_payload=safe_response,
            errors=[
                {"error_type": type(exc).__name__, "error": str(exc)}
            ],
        )
        host.conversation_state.record_interaction_response(session_id, safe_response)
        host._launch_interaction(safe_response, session_id)
        return

    handled = await host._try_apply_cognitive_runtime(
        session,
        user_text=user_text,
        session_id=session_id,
        context=context,
        core_interpretation=core_interpretation,
        core_interpretation_latency_ms=core_interpretation_latency_ms,
        turn_envelope=turn_envelope,
    )
    if handled:
        return

    # The maintained architecture has no compatibility fallback. Once Goal
    # Interpretation has produced Responsibility evidence, execution may only
    # continue through the goal-driven Cognitive Runtime. A disabled or
    # unavailable runtime therefore fails closed instead of reconstructing a
    # retired route/intent projection or entering a second semantic pipeline.
    safe_response = host._cognitive_core_exception_safe_response(
        user_text,
        context=context,
        failure_stage="cognitive_runtime_entry",
        failure_class="runtime_unavailable",
    )
    host.conversation_state.record_user_turn(
        session_id,
        user_text,
        metadata=host._metadata_with_turn_envelope(
            {
                "source": "goal_driven_cognitive_runtime",
                "semantic_status": "failed",
                "semantic_failure_stage": "cognitive_runtime_entry",
                "semantic_failure_class": "runtime_unavailable",
                "canonical_goal_committed": False,
                "user_meaning_interpretation": core_interpretation.model_dump(mode="json"),
            },
            turn_envelope,
        ),
    )
    host.conversation_state.record_interaction_response(session_id, safe_response)
    host._launch_interaction(safe_response, session_id)
    return
