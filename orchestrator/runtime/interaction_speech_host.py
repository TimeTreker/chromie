"""Interaction speech scheduling and cancellation for the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host`` and are
bound as the Capability Runtime speech scheduler and cancel scheduler.
"""

from __future__ import annotations

from typing import Any


from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
)


async def cancel_interaction_speech(
    host: Any,
    request: CapabilityRequest,
    scheduled: dict[str, Any],
) -> None:
    """Cancel one goal-bound speech request at the shared output boundary.

    Pending chunks are invalidated by exact generation/order.  Once any
    chunk may have started, Chromie's playback resource is global, so the
    only truthful cancellation is a shared output abort.  Capability Runtime
    marks that provider as global-domain and records every coaffected Goal.
    """

    metadata = request.args.get("metadata")
    session_id = (
        metadata.get("session_id")
        if isinstance(metadata, dict)
        else None
    )
    cancelled_orders = host._cancel_scheduled_playback_before_start(
        scheduled,
        session_id=session_id,
        reason="named_goal_speech_cancelled",
    )
    raw_orders = scheduled.get("orders")
    if not isinstance(raw_orders, list):
        raw_orders = [scheduled.get("order")]
    expected_orders = {
        int(item)
        for item in raw_orders
        if isinstance(item, int)
        or (isinstance(item, str) and item.isdigit())
    }
    needs_global_abort = bool(
        not scheduled
        or scheduled.get("scheduled") is not True
        or scheduled.get("playback_started") is True
        or expected_orders - set(cancelled_orders)
    )
    if needs_global_abort:
        host._invalidate_output_state(cancel_cognitive_work=False)
        await playback_transport_for(host).abort_output_stream()
    host.session_log(
        session_id,
        "interaction_speech_cancelled: request_id=%s pending_orders=%s "
        "global_abort=%s",
        request.request_id,
        ",".join(str(item) for item in sorted(cancelled_orders)),
        needs_global_abort,
    )


async def schedule_interaction_speech(
    host: Any,
    args: dict[str, Any],
) -> dict[str, Any]:
    metadata = args.get("metadata")
    session_id = (
        metadata.get("session_id")
        if isinstance(metadata, dict)
        else None
    )
    origin_session_id = metadata.get("origin_session_id") if isinstance(metadata, dict) else None
    voice_release_required = bool(
        isinstance(metadata, dict)
        and metadata.get("wait_for_voice_release") is True
    )

    async def wait_for_voice_release(
        generation: int,
        orders: list[int],
        playback_started: bool,
    ) -> bool:
        if not voice_release_required or not playback_started or not orders:
            return False
        raw_timeout_ms = (
            metadata.get("voice_release_timeout_ms", 30000)
            if isinstance(metadata, dict)
            else 30000
        )
        try:
            timeout_ms = max(1000, int(raw_timeout_ms))
        except (TypeError, ValueError):
            timeout_ms = 30000
        return await host.playback_delivery.wait_for_playback_release(
            generation=generation,
            order=orders[-1],
            session_id=session_id,
            timeout_s=timeout_ms / 1000.0,
        )

    if (
        isinstance(metadata, dict)
        and metadata.get("reuse_current_turn_speech") is True
    ):
        raw_generation = metadata.get("reused_speech_generation")
        raw_orders = metadata.get("reused_speech_orders")
        event_id = str(metadata.get("reused_speech_event_id") or "").strip()
        try:
            generation = int(raw_generation)
        except (TypeError, ValueError):
            return {
                "scheduled": False,
                "reason": "reused_speech_missing_generation",
                "reused": True,
            }
        orders = [
            int(item)
            for item in (raw_orders if isinstance(raw_orders, list) else [])
            if isinstance(item, int)
        ]
        if not orders:
            return {
                "scheduled": False,
                "reason": "reused_speech_missing_orders",
                "reused": True,
            }

        def current_status() -> str:
            events = host.playback_delivery.turn_speech_events.get(
                str(origin_session_id or session_id or ""),
                [],
            )
            for item in reversed(events):
                if event_id and str(item.get("event_id") or "") != event_id:
                    continue
                raw_event_generation = item.get("generation")
                try:
                    event_generation = int(raw_event_generation)
                except (TypeError, ValueError):
                    event_generation = -1
                if event_generation != generation:
                    continue
                item_orders = item.get("orders")
                if not isinstance(item_orders, list) or orders[0] not in item_orders:
                    continue
                if host.normalize_tts_candidate(str(args.get("text") or "")) != item.get("text"):
                    raise ValueError("Communicative Activity wording cannot change under one identity")
                return str(item.get("status") or "")
            return ""

        status = current_status()
        from orchestrator.runtime.scheduler import current_execution_start

        execution_start = current_execution_start.get()
        if execution_start is not None:
            if status in {"playback_started", "playback_completed"}:
                await execution_start.group.ready_after_observed_start(
                    execution_start.member
                )
            elif status == "scheduled":
                key = host.playback_start_key(
                    generation,
                    orders[0],
                    session_id,
                )
                host.playback_delivery.execution_starts[key] = execution_start
                status_after_binding = current_status()
                if status_after_binding in {
                    "playback_started",
                    "playback_completed",
                }:
                    host.playback_delivery.execution_starts.pop(key, None)
                    await execution_start.group.ready_after_observed_start(
                        execution_start.member
                    )
                    status = status_after_binding
        playback_started = status in {
            "playback_started",
            "playback_completed",
        }
        playback_barrier = (
            metadata.get("wait_for_playback_start") is True
            or voice_release_required
        )
        if playback_barrier and not playback_started:
            default_playback_timeout_ms = int(
                getattr(
                    getattr(
                        getattr(host, "host_settings", None),
                        "playback",
                        None,
                    ),
                    "playback_start_timeout_ms",
                    20000,
                )
            )
            try:
                timeout_ms = int(
                    metadata.get(
                        "playback_start_timeout_ms",
                        default_playback_timeout_ms,
                    )
                )
            except (TypeError, ValueError):
                timeout_ms = default_playback_timeout_ms
            playback_started = await host.wait_for_playback_start(
                generation=generation,
                order=orders[0],
                session_id=session_id,
                timeout_s=max(0.001, timeout_ms / 1000.0),
            )
            playback_started = playback_started or current_status() in {
                "playback_started",
                "playback_completed",
            }
            if not playback_started:
                status_after_wait = current_status()
                reused_request = {
                    "scheduled": True,
                    "generation": generation,
                    "order": orders[0],
                    "orders": orders,
                }
                if status_after_wait == "scheduled":
                    host._cancel_scheduled_playback_before_start(
                        reused_request,
                        session_id=session_id,
                        reason="reused_speech_delivery_not_observed",
                    )
                    status_after_wait = current_status()
                if status_after_wait in {
                    "playback_started",
                    "playback_completed",
                }:
                    playback_started = True
                elif status_after_wait in {"not_delivered", ""}:
                    fallback_metadata = dict(metadata)
                    fallback_metadata["reuse_current_turn_speech"] = False
                    fallback_metadata.pop("reused_speech_generation", None)
                    fallback_metadata.pop("reused_speech_orders", None)
                    fallback_metadata.pop("reused_speech_status", None)
                    fallback_metadata.pop("reused_speech_event_id", None)
                    fallback_metadata[
                        "fallback_for_undelivered_speech_event_id"
                    ] = event_id
                    fallback_args = dict(args)
                    fallback_args["metadata"] = fallback_metadata
                    fallback = await host._schedule_interaction_speech(
                        fallback_args
                    )
                    fallback["reused"] = False
                    fallback[
                        "fallback_for_undelivered_speech_event_id"
                    ] = event_id
                    return fallback
        return {
            "scheduled": True,
            "reused": True,
            "speech_event_id": event_id or None,
            "generation": generation,
            "order": orders[0],
            "orders": orders,
            "chunks": len(orders),
            "playback_started": playback_started,
            "voice_release_required": voice_release_required,
            "voice_released": await wait_for_voice_release(
                generation, orders, playback_started
            ),
            "status": current_status() or status or "scheduled",
        }

    # Semantic idempotency is keyed by exact Planner Communicative Activity
    # identity, not by transport generation/order and not by wording similarity.
    # If the same Activity is materialized twice during reconciliation or a
    # retry, reuse the already-scheduled/delivered audio rather than creating
    # a second user-facing act.
    semantic_activity_ids: list[str] = []
    if isinstance(metadata, dict):
        raw_activity_ids = metadata.get("communicative_activity_ids")
        if isinstance(raw_activity_ids, str):
            raw_activity_ids = [raw_activity_ids]
        if isinstance(raw_activity_ids, list):
            semantic_activity_ids.extend(
                str(item).strip()
                for item in raw_activity_ids
                if str(item).strip()
            )
        fast_activity_id = str(metadata.get("fast_activity_id") or "").strip()
        if fast_activity_id and fast_activity_id not in semantic_activity_ids:
            semantic_activity_ids.append(fast_activity_id)
    reuse_args = None
    async with host.playback_delivery.speech_submission_lock:
        if semantic_activity_ids:
            existing_event = host.playback_delivery.find_turn_speech_event_for_activities(
                session_id=origin_session_id or session_id,
                turn_id=(
                    str(metadata.get("turn_id") or session_id or "")
                    if isinstance(metadata, dict)
                    else str(session_id or "")
                ),
                communicative_activity_ids=semantic_activity_ids,
                reusable_statuses={"scheduled", "playback_started", "playback_completed", "playback_interrupted", "not_delivered"},
            )
            if existing_event is not None:
                if host.normalize_tts_candidate(str(args.get("text") or "")) != existing_event.get("text"):
                    raise ValueError("Communicative Activity wording cannot change under one identity")
                if existing_event.get("status") == "not_delivered":
                    existing_event = None
            if existing_event is not None:
                existing_orders = existing_event.get("orders")
                if isinstance(existing_orders, list) and existing_orders:
                    reuse_metadata = dict(metadata or {})
                    reuse_metadata.update(
                        {
                            "reuse_current_turn_speech": True,
                            "reused_speech_event_id": existing_event.get("event_id"),
                            "reused_speech_generation": existing_event.get("generation"),
                            "reused_speech_orders": list(existing_orders),
                            "reused_speech_status": existing_event.get("status"),
                            "semantic_idempotent_reuse": True,
                        }
                    )
                    reuse_args = dict(args)
                    reuse_args["metadata"] = reuse_metadata
        if reuse_args is None:
            text = str(args.get("text") or "")
            scheduled = await host.schedule_tts_text(text, session_id)
            if scheduled.get("scheduled") is True:
                raw_orders = scheduled.get("orders")
                if not isinstance(raw_orders, list):
                    raw_orders = [scheduled.get("order")]
                orders = [
                    int(item)
                    for item in raw_orders
                    if isinstance(item, int)
                    or (isinstance(item, str) and item.isdigit())
                ]
                speech_event = host._register_turn_speech_event(
                    session_id=session_id,
                    origin_session_id=origin_session_id,
                    generation=int(scheduled.get("generation") or 0),
                    orders=orders,
                    text=text,
                    stage=(
                        str(metadata.get("phase") or "interaction_speech")
                        if isinstance(metadata, dict)
                        else "interaction_speech"
                    ),
                    purpose=(
                        str(
                            metadata.get("speech_act")
                            or metadata.get("delivery_role")
                            or "response"
                        )
                        if isinstance(metadata, dict)
                        else "response"
                    ),
                    commitment=(
                        str(metadata.get("commitment_state") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    fast_activity_id=(
                        str(metadata.get("fast_activity_id") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    communicative_activity_ids=(
                        list(metadata.get("communicative_activity_ids") or [])
                        if isinstance(metadata, dict)
                        and isinstance(metadata.get("communicative_activity_ids"), list)
                        else []
                    ),
                    addressed_need_ids=(
                        metadata.get("addressed_need_ids") if isinstance(metadata, dict) else None
                    ),
                    source_responsibility_refs=(
                        metadata.get("source_responsibility_refs") if isinstance(metadata, dict) else None
                    ),
                    wording_owner=(
                        str(metadata.get("wording_owner") or "") if isinstance(metadata, dict) else ""
                    ),
                    turn_id=(
                        str(metadata.get("turn_id") or session_id or "")
                        if isinstance(metadata, dict)
                        else str(session_id or "")
                    ),
                    source_goal_ids=(
                        list(metadata.get("source_goal_ids") or [])
                        if isinstance(metadata, dict)
                        and isinstance(metadata.get("source_goal_ids"), list)
                        else []
                    ),
                    canonical_plan_id=(
                        str(metadata.get("canonical_plan_id") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    canonical_plan_fingerprint=(
                        str(metadata.get("canonical_plan_fingerprint") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    goal_association_fingerprint=(
                        str(metadata.get("goal_association_fingerprint") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    delivery_role=(
                        str(metadata.get("delivery_role") or "response")
                        if isinstance(metadata, dict)
                        else "response"
                    ),
                    claims=(
                        list(metadata.get("claims") or [])
                        if isinstance(metadata, dict)
                        and isinstance(metadata.get("claims"), list)
                        else []
                    ),
                    must_not_claim_completion=(
                        metadata.get("must_not_claim_completion")
                        if isinstance(metadata, dict)
                        and isinstance(metadata.get("must_not_claim_completion"), bool)
                        else None
                    ),
                    cognitive_opportunity_id=(
                        str(metadata.get("cognitive_opportunity_id") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    situation_signature=(
                        str(metadata.get("situation_signature") or "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    subject_refs=(
                        list(metadata.get("subject_refs") or [])
                        if isinstance(metadata, dict)
                        and isinstance(metadata.get("subject_refs"), list)
                        else []
                    ),
                )
                if speech_event is not None:
                    scheduled["speech_event_id"] = speech_event["event_id"]
    if reuse_args is not None:
        return await host._schedule_interaction_speech(reuse_args)
    if (
        isinstance(metadata, dict)
        and (
            metadata.get("wait_for_playback_start") is True
            or voice_release_required
        )
        and scheduled.get("scheduled") is True
    ):
        default_playback_timeout_ms = int(
            getattr(
                getattr(
                    getattr(host, "host_settings", None),
                    "playback",
                    None,
                ),
                "playback_start_timeout_ms",
                20000,
            )
        )
        raw_timeout_ms = metadata.get(
            "playback_start_timeout_ms",
            default_playback_timeout_ms,
        )
        try:
            timeout_ms = int(raw_timeout_ms)
        except (TypeError, ValueError):
            timeout_ms = default_playback_timeout_ms
        playback_started = await host.wait_for_playback_start(
            generation=int(scheduled["generation"]),
            order=int(scheduled["order"]),
            session_id=session_id,
            timeout_s=max(0.001, timeout_ms / 1000.0),
        )
        scheduled["playback_started"] = playback_started
        if not playback_started:
            scheduled["cancelled_orders"] = host._cancel_scheduled_playback_before_start(
                scheduled,
                session_id=session_id,
                reason="required_playback_start_not_observed",
            )
    if voice_release_required and scheduled.get("scheduled") is True:
        raw_orders = scheduled.get("orders")
        if not isinstance(raw_orders, list):
            raw_orders = [scheduled.get("order")]
        orders = [int(item) for item in raw_orders if isinstance(item, int)]
        playback_started = bool(scheduled.get("playback_started"))
        scheduled["voice_release_required"] = True
        scheduled["voice_released"] = await wait_for_voice_release(
            int(scheduled.get("generation") or 0),
            orders,
            playback_started,
        )
    return scheduled
