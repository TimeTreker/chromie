"""Detached interaction dispatch and terminal consumers for the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host``. Capability
lifetime stays detached from the foreground interaction call stack.
"""

from __future__ import annotations

import asyncio
from typing import Any


from orchestrator.runtime.observability_recording import (
    record_execution_experience_safely,
)
from orchestrator.runtime.planner_reentry import (
    meaningful_provider_state,
    terminal_result_waits_for_batch_closure,
)
from orchestrator.runtime.session import (
    now_ms,
    record_session_workflow_stage,
    summarize_provider_start_evidence,
)
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.interaction import (
    InteractionResponse,
)
from shared.chromie_contracts.user_turn import (
    user_turn_prohibits_speech,
)
from orchestrator.runtime import cognitive_outcome_host
from orchestrator.runtime import planner_reentry_host


def launch_interaction(
    host: Any,
    response: InteractionResponse,
    session_id: str | None,
    *,
    confirmed_request_ids: set[str] | None = None,
    reset_playback: bool = True,
    mark_session_done: bool = True,
) -> None:
    """Launch every InteractionResponse through the non-blocking dispatch boundary."""

    if user_turn_prohibits_speech(response.metadata.get("user_turn_envelope")):
        response = response.model_copy(update={"speech": []})

    task = asyncio.create_task(
        host._dispatch_detached_interaction(
            response,
            session_id,
            confirmed_request_ids=confirmed_request_ids,
            reset_playback=reset_playback,
            mark_session_done=mark_session_done,
        )
    )
    active_tasks = getattr(host, "active_interaction_tasks", None)
    if not isinstance(active_tasks, dict):
        active_tasks = {}
        host.active_interaction_tasks = active_tasks
    active_tasks[task] = response.interaction_id
    host.active_interaction_task = task
    host.active_interaction_id = response.interaction_id
    task.add_done_callback(host._interaction_task_done)


def uses_detached_cognitive_capability_runtime(
    response: InteractionResponse,
) -> bool:
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    return bool(
        metadata.get("cognitive_runtime_apply") is True
        and isinstance(metadata.get("canonical_plan"), dict)
        and response.capabilities
    )


async def dispatch_detached_interaction(
    host: Any,
    response: InteractionResponse,
    session_id: str | None,
    *,
    confirmed_request_ids: set[str] | None,
    reset_playback: bool,
    mark_session_done: bool,
) -> Any:
    """Submit trusted provider work and end the foreground Python task.

    Terminal work is consumed by a separate result task. The Capability
    Runtime, not this foreground call stack, keeps request ownership alive.
    """

    if reset_playback:
        await host.reset_playback_ordering()
    generation = int(host.playback_delivery.playback_generation)
    started_ms = now_ms()
    try:
        dispatch = await host.interaction_runtime.submit_response(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
    except Exception as exc:
        record_session_workflow_stage(
            host,
            session_id,
            stage="trusted_capability_runtime_dispatch",
            started_monotonic_ms=started_ms,
            finished_monotonic_ms=now_ms(),
            status="failed",
            input_payload={"interaction_response": response},
            output_payload=None,
            errors=[{"error_type": type(exc).__name__, "error": str(exc)}],
            metadata=summarize_provider_start_evidence(response),
        )
        raise

    if isinstance(response.metadata.get("social_cognition_resolution"), dict):
        host.cognitive_runtime.schedule_social_expression(response, session_id=session_id)
    receipt = dispatch.receipt
    record_session_workflow_stage(
        host,
        session_id,
        stage="trusted_capability_runtime_dispatch",
        started_monotonic_ms=started_ms,
        finished_monotonic_ms=now_ms(),
        status="accepted" if receipt is not None else "terminal_before_dispatch",
        input_payload={"interaction_response": dispatch.source_response},
        output_payload=(
            receipt
            if receipt is not None
            else dispatch.immediate_execution
        ),
        errors=[],
        metadata=summarize_provider_start_evidence(dispatch.source_response),
    )
    host.session_log(
        session_id,
        "capability_runtime_detached: interaction_id=%s dispatch_id=%s requests=%s",
        dispatch.source_response.interaction_id,
        receipt.dispatch_id if receipt is not None else "none",
        len(receipt.request_ids) if receipt is not None else 0,
    )

    result_consumer = (
        host._consume_detached_cognitive_dispatch
        if uses_detached_cognitive_capability_runtime(response)
        else host._consume_detached_non_cognitive_dispatch
    )

    async def consume_and_finalize_session() -> CapabilityRuntimeResult:
        try:
            return await result_consumer(
                dispatch,
                session_id=session_id,
                generation=generation,
                confirmed_request_ids=confirmed_request_ids,
            )
        finally:
            # A dispatch receipt transfers provider ownership but does not prove
            # that response speech was even scheduled.  Closing the session at
            # receipt time lets the next voice turn invalidate that still-pending
            # speech as stale.  Finalize only after Runtime has consumed the
            # detached response (including its playback-start barrier).
            if mark_session_done:
                state = host.sessions.state.get(session_id or "")
                if state is not None:
                    state["llm_done"] = True
                    state["response_chars"] = state.get(
                        "response_chars", 0
                    ) + sum(
                        len(item.text)
                        for item in dispatch.runtime_response.speech
                    )
                host.maybe_session_done(session_id)

    result_task = asyncio.create_task(
        consume_and_finalize_session(),
        name=(
            "capability-result-reentry:"
            f"{dispatch.source_response.interaction_id}:"
            f"{receipt.dispatch_id if receipt is not None else 'immediate'}"
        ),
    )
    host.sessions.track_capability_dispatch(session_id, result_task)
    result_tasks = getattr(host, "active_cognitive_runtime_tasks", None)
    if not isinstance(result_tasks, dict):
        result_tasks = {}
        host.active_cognitive_runtime_tasks = result_tasks
    result_tasks[result_task] = dispatch.source_response.interaction_id
    result_task.add_done_callback(host._cognitive_runtime_task_done)

    return receipt


async def consume_detached_non_cognitive_dispatch(
    host: Any,
    dispatch: Any,
    *,
    session_id: str | None,
    generation: int,
    confirmed_request_ids: set[str] | None,
) -> CapabilityRuntimeResult:
    """Consume a non-cognitive dispatch without reopening the foreground turn."""

    execution = await host.interaction_runtime.wait_dispatch(dispatch)
    response = dispatch.source_response
    for result in execution.results:
        host.conversation_state.update_pending_task_status_for_request_id(
            request_id=result.request_id, status=result.status
        )
    if response.metadata.get("history_after_successful_delivery") is True:
        await cognitive_outcome_host.record_successfully_delivered_speech(host,
            response, execution, session_id=session_id,
            log_event="interaction_history_after_delivery",
        )
    record_execution_experience_safely(
        prepare_response=host._prepared_interaction_response_for_record,
        record_experience=host._record_experience,
        session_log=host.session_log,
        response=response, execution=execution, session_id=session_id,
        confirmed_request_ids=confirmed_request_ids,
    )
    return execution


async def consume_detached_cognitive_dispatch(
    host: Any,
    dispatch: Any,
    *,
    session_id: str | None,
    generation: int,
    confirmed_request_ids: set[str] | None,
) -> CapabilityRuntimeResult:
    """Consume Runtime events after the originating foreground task ended."""

    response = dispatch.source_response
    receipt = dispatch.receipt
    started_ms = now_ms()
    source_capability_request_ids = {
        request.request_id for request in response.capabilities
    }
    runtime_capability_request_ids = {
        request.request_id
        for request in dispatch.runtime_response.capabilities
    }
    terminal_capability_ids: set[str] = set()

    preexecuted_capability_results = [
        result
        for result in dispatch.preexecuted_results
        if result.request_id in source_capability_request_ids
    ]
    for result in preexecuted_capability_results:
        terminal_capability_ids.add(result.request_id)
        if runtime_capability_request_ids and not terminal_result_waits_for_batch_closure(
            source_capability_count=len(source_capability_request_ids),
            status=result.status,
        ):
            await host._reenter_cognition_for_terminal_capability(
                response=response,
                result=result,
                session_id=session_id,
                generation=generation,
            )
        elif runtime_capability_request_ids:
            host.session_log(
                session_id,
                "incremental_cognitive_reentry_deferred: request_id=%s "
                "reason=batch_closure",
                result.request_id,
            )

    if receipt is not None:
        cursor = receipt.event_cursor
        runtime_terminal_ids: set[str] = set()
        provider_state_signatures: dict[str, dict[str, Any]] = {}
        while len(runtime_terminal_ids) < len(runtime_capability_request_ids):
            event = await host.interaction_runtime.runtime.wait_runtime_event(
                cursor,
                dispatch_id=receipt.dispatch_id,
            )
            cursor = event.sequence
            if event.request_id not in runtime_capability_request_ids:
                continue
            if event.type == "progress" and not event.terminal:
                projected_state = meaningful_provider_state(event.progress)
                if projected_state and provider_state_signatures.get(
                    event.request_id
                ) != projected_state:
                    provider_state_signatures[event.request_id] = dict(
                        projected_state
                    )
                    await planner_reentry_host.reenter_cognition_for_provider_state(host,
                        response=response,
                        event=event,
                        provider_state=projected_state,
                        session_id=session_id,
                    )
                continue
            if (
                not event.terminal
                or event.result is None
                or event.request_id in runtime_terminal_ids
            ):
                continue
            runtime_terminal_ids.add(event.request_id)
            terminal_capability_ids.add(event.request_id)
            host.session_log(
                session_id,
                "capability_terminal_reentry_event: dispatch_id=%s request_id=%s "
                "capability_id=%s status=%s remaining=%s",
                receipt.dispatch_id,
                event.request_id,
                event.capability_id,
                event.type,
                max(
                    0,
                    len(source_capability_request_ids)
                    - len(terminal_capability_ids),
                ),
            )
            if terminal_result_waits_for_batch_closure(
                source_capability_count=len(source_capability_request_ids),
                status=event.result.status,
            ):
                host.session_log(
                    session_id,
                    "incremental_cognitive_reentry_deferred: request_id=%s "
                    "reason=batch_closure",
                    event.request_id,
                )
            else:
                await host._reenter_cognition_for_terminal_capability(
                    response=response,
                    result=event.result,
                    session_id=session_id,
                    generation=generation,
                )

    try:
        execution = await host.interaction_runtime.wait_dispatch(
            dispatch
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        host.session_log(
            session_id,
            "detached_capability_completion_failed: interaction_id=%s "
            "error_type=%s error=%s",
            response.interaction_id,
            type(exc).__name__,
            exc,
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
        )

    record_session_workflow_stage(
        host,
        session_id,
        stage="trusted_capability_runtime_completion",
        started_monotonic_ms=started_ms,
        finished_monotonic_ms=now_ms(),
        status=execution.status,
        input_payload={
            "interaction_id": response.interaction_id,
            "dispatch_id": receipt.dispatch_id if receipt is not None else "",
        },
        output_payload=execution,
        errors=[
            {
                "request_id": result.request_id,
                "capability_id": result.capability_id,
                "status": result.status,
                "reason_code": result.reason_code,
                "message": result.message,
            }
            for result in execution.results
            if result.status not in {"completed", "success"}
        ],
        metadata=summarize_provider_start_evidence(response, execution),
    )
    host.session_log(
        session_id,
        "detached_capability_runtime_done: interaction_id=%s status=%s "
        "results=%s runtime_ms=%.1f",
        response.interaction_id,
        execution.status,
        len(execution.results),
        now_ms() - started_ms,
    )
    for result in execution.results:
        host.conversation_state.update_pending_task_status_for_request_id(
            request_id=result.request_id,
            status=result.status,
        )

    has_soridormi_request = any(
        request.capability_id.startswith("soridormi.")
        for request in response.capabilities
    )
    provider_status = (
        await host._record_soridormi_post_status(session_id)
        if has_soridormi_request
        else None
    )
    completed_request_ids = {
        result.request_id for result in execution.results
    }
    if execution.status != "completed":
        for request in response.capabilities:
            if request.request_id in completed_request_ids:
                continue
            host.conversation_state.update_pending_task_status_for_request_id(
                request_id=request.request_id,
                status="not_run",
            )
    closure_status = await host._close_cognitive_execution(
        response=response,
        execution=execution,
        session_id=session_id,
        generation=generation,
        provider_status=provider_status,
    )
    response.metadata["cognitive_turn_closure_status"] = closure_status
    record_execution_experience_safely(
        prepare_response=host._prepared_interaction_response_for_record,
        record_experience=host._record_experience,
        session_log=host.session_log,
        response=response,
        execution=execution,
        session_id=session_id,
        confirmed_request_ids=confirmed_request_ids,
    )
    return execution


async def record_soridormi_post_status(
    host: Any,
    session_id: str | None,
) -> dict[str, Any] | None:
    invoker = getattr(host.interaction_runtime, "soridormi_invoker", None)
    if invoker is None:
        host.session_log(
            session_id,
            "soridormi_post_status_failed: reason=provider_unavailable",
        )
        return None
    try:
        outcome = await asyncio.wait_for(
            invoker.invoke("soridormi.robot.get_status", {}),
            timeout=5.0,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "soridormi_post_status_failed: reason=%s",
            type(exc).__name__,
        )
        return None
    if outcome.status != "success":
        host.session_log(
            session_id,
            "soridormi_post_status_failed: reason=%s",
            outcome.error or outcome.status,
        )
        return None
    status = outcome.output if isinstance(outcome.output, dict) else {}
    host.session_log(
        session_id,
        "soridormi_post_status: mode=%s backend=%s safe_idle=%s "
        "active_task_present=%s emergency_stop=%s fallen=%s",
        status.get("mode"),
        status.get("backend"),
        status.get("safe_idle"),
        status.get("active_task") is not None,
        status.get("emergency_stop"),
        status.get("fallen"),
    )
    return status
