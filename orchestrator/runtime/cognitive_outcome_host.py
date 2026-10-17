"""Cognitive execution closure and outcome delivery for the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host``. They close a
cognitive execution, record its outcome Evidence and deliver the resulting
response; Social Cognition authors any user-facing words.
"""

from __future__ import annotations

import asyncio
from typing import Any


from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.outcome_delivery import build_host_outcome_delivery
from orchestrator.runtime.planner_reentry import (
    execution_outcome_user_text,
)
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.interaction import (
    InteractionResponse,
)
from shared.chromie_contracts.plan import (
    CanonicalPlan,
)
from shared.chromie_contracts.reflection import ReflectionRequest
from shared.chromie_contracts.user_turn import (
    user_turn_prohibits_speech,
)


def operational_failure_notice(
    *,
    zh: bool,
    failure_stage: str | None,
    failure_class: str | None,
    failure_error: str | None,
) -> str:
    """Return a human-safe operational notice; diagnostics stay in metadata/logs."""

    stage = str(failure_stage or "").strip().casefold()
    if "user_meaning" in stage or "interpret" in stage:
        return (
            "刚才那句我没理解清楚，你能再说一次吗？"
            if zh
            else "I didn't understand that clearly. Could you say it again?"
        )
    return (
        "我这边刚才出了点问题，没能把这件事完成。"
        if zh
        else "I ran into a problem and couldn't complete that."
    )


def cognitive_core_exception_safe_response(
    host: Any,
    user_text: str,
    *,
    context: dict[str, Any] | None = None,
    failure_stage: str | None = None,
    failure_class: str | None = None,
    failure_error: str | None = None,
) -> InteractionResponse:
    """Return one non-semantic operational fallback after Core failure.

    The Host does not classify the user's request to choose different
    wording. Exact effect safety is already enforced by the absence of a
    validated Canonical Plan and Trusted Capability Runtime execution.
    """

    # Cognition is unavailable at this boundary. Keep the emergency
    # fail-closed utterance tiny and natural; detailed operational identity
    # remains in response metadata/logs rather than becoming robot speech.
    envelope = (context or {}).get("user_turn_envelope")
    zh = host._looks_zh(user_text)
    text = operational_failure_notice(
        zh=zh,
        failure_stage=failure_stage,
        failure_class=failure_class,
        failure_error=failure_error,
    )
    response = host._host_speech_response(
        text,
        style="warning",
        source="host_cognitive_core_exception_safe_fallback",
    )
    failure_metadata: dict[str, Any] = {}
    if failure_stage or failure_class or failure_error:
        failure_metadata = {
            "semantic_status": "failed",
            "semantic_failure_stage": str(failure_stage or "cognition"),
            "semantic_failure_class": str(
                failure_class or "semantic_failure"
            ),
            "semantic_failure_error": str(failure_error or ""),
        }
    return response.model_copy(
        update={
            "speech": [] if user_turn_prohibits_speech(envelope) else response.speech,
            "metadata": {
                **response.metadata,
                **({"user_turn_envelope": envelope} if isinstance(envelope, dict) else {}),
                "effect_execution": "not_authorized",
                "semantic_fallback": False,
                **failure_metadata,
            }
        }
    )


def cognitive_turn_closure_adapter(host: Any) -> CognitiveTurnClosure:
    closure = getattr(host, "cognitive_turn_closure", None)
    if closure is None:
        closure = CognitiveTurnClosure(host.interaction_runtime)
        host.cognitive_turn_closure = closure
    return closure


def record_cognitive_outcome_evidence(
    host: Any,
    bundle: Any,
    *,
    session_id: str | None,
    final_response: InteractionResponse | None,
    delivery_status: str,
    suppression_reason: str = "",
    goal_state_results: list[dict[str, Any]] | None = None,
    execution: CapabilityRuntimeResult | None = None,
) -> None:
    recorder = getattr(host, "cognitive_evidence", None)
    if recorder is None or not hasattr(recorder, "record_outcome"):
        return
    try:
        recorder.record_outcome(
            bundle,
            sid=str(session_id or bundle.turn_id),
            final_response=final_response,
            delivery_status=delivery_status,
            suppression_reason=suppression_reason,
            goal_state_results=goal_state_results,
            capability_traces=(
                execution.traces if execution is not None else ()
            ),
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "cognitive_outcome_evidence_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )


async def execute_cognitive_outcome_response(
    host: Any,
    response: InteractionResponse,
    *,
    session_id: str | None,
    detached_delivery: bool = False,
) -> str:
    try:
        delivery_session_id = session_id
        if detached_delivery and isinstance(
            response.metadata.get("deferred_outcome_delivery"), dict
        ):
            # A response intentionally held behind a newer turn is no longer
            # ordered inside its original playback session. Current-session
            # re-entry must retain its sid so TTS ordering can accept it;
            # dropping every detached delivery to sid=None makes valid
            # evidence-bound speech stale immediately.
            delivery_session_id = None
            response = response.model_copy(update={"speech": [
                speech.model_copy(update={"metadata": {
                    **speech.metadata, "origin_session_id": session_id,
                }}) for speech in response.speech
            ]})
        dispatch = await host.interaction_runtime.submit_response(
            response,
            session_id=delivery_session_id,
        )
        if isinstance(response.metadata.get("social_cognition_resolution"), dict) and response.metadata.get("authority_scope") != "goal_free_situation":
            host.cognitive_runtime.schedule_social_expression(response, session_id=delivery_session_id)
        execution = await host.interaction_runtime.wait_dispatch(dispatch)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        host.session_log(
            session_id,
            "cognitive_outcome_response_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        for speech in response.speech:
            host.conversation_state.update_pending_task_status_for_request_id(
                request_id=speech.id,
            status="failed",
        )
        return "speech_runtime_failed"

    delivered_count = await record_successfully_delivered_speech(
        host,
        response,
        execution,
        session_id=session_id,
        log_event="cognitive_outcome_history_after_delivery",
    )
    for result in execution.results:
        host.conversation_state.update_pending_task_status_for_request_id(
            request_id=result.request_id,
            status=result.status,
        )
    host.session_log(
        session_id,
        "cognitive_outcome_response_done: status=%s speech=%s results=%s",
        execution.status,
        len(response.speech),
        len(execution.results),
    )
    state = host.sessions.state.get(session_id or "")
    if state is not None:
        state["response_chars"] = state.get("response_chars", 0) + sum(
            len(item.text) for item in response.speech
        )
    if (
        execution.status == "completed"
        and delivered_count == len(response.speech)
    ):
        return "speech_runtime_completed"
    if execution.status == "completed":
        return "speech_runtime_delivery_unverified"
    return f"speech_runtime_{execution.status}"


async def record_successfully_delivered_speech(
    host: Any,
    response: InteractionResponse,
    execution: CapabilityRuntimeResult,
    *,
    session_id: str | None,
    log_event: str,
) -> int:
    """Expose only speech the runtime proves was delivered.

    Confirmation prompts are operational turns: recording them before the
    speech provider succeeds would let unheard text influence later model
    context and confirmation resolution.
    """

    results_by_request = {
        result.request_id: result for result in execution.results
    }
    delivered_speech = []
    for speech in response.speech:
        result = results_by_request.get(speech.id)
        if result is None or result.capability_id != "chromie.speak" or result.status != "completed":
            continue
        if not isinstance(result.output, dict):
            continue
        if await host.playback_delivery.wait_for_speech_completion(session_id, result.output):
            delivered_speech.append(speech)
    if not delivered_speech:
        host.session_log(
            session_id,
            "%s: delivered_speech=0 runtime_status=%s",
            log_event,
            execution.status,
        )
        return 0
    if any(speech.metadata.get("wording_owner") == "social_cognition" for speech in delivered_speech):
        await host.interaction_runtime.record_social_delivery(response, execution, session_id=session_id)
    delivered_response = response.model_copy(
        deep=True,
        update={
            "speech": delivered_speech,
            "capabilities": [],
            "requires_confirmation": False,
        },
    )
    try:
        # This delivery helper is also used by bounded non-turn cognition.
        # Retain only speech the Runtime proves was delivered; never reinterpret
        # that communicative delta as replacement executable Work.
        host.conversation_state.record_interaction_response(
            session_id,
            delivered_response,
            bind_planned_execution=False,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "%s_failed: error_type=%s error=%s",
            log_event,
            type(exc).__name__,
            exc,
        )
        return 0
    host.session_log(
        session_id,
        "%s: delivered_speech=%s runtime_status=%s",
        log_event,
        len(delivered_speech),
        execution.status,
    )
    return len(delivered_speech)


def schedule_outcome_reflection(
    host: Any, *, response: InteractionResponse, plan: CanonicalPlan, bundle: Any,
    opportunities: list[Any], session_id: str | None, generation: int,
) -> None:
    """Learn from recorded outcomes under the existing detached-task lifecycle.

    Optional learning has one in-flight slot and one bounded deadline. It
    cannot hold foreground result planning or request another review of it.
    """
    reflection_call = getattr(getattr(host, "agent_client", None), "resolve_reflection", None)
    if not opportunities or not callable(reflection_call):
        return
    tasks = getattr(host, "active_cognitive_runtime_tasks", None)
    if not isinstance(tasks, dict):
        tasks = {}
        host.active_cognitive_runtime_tasks = tasks
    if any(not task.done() and task.get_name().startswith("outcome-reflection:") for task in tasks):
        host.session_log(session_id, "selective_reflection_skipped: reason=background_slot_busy")
        return
    try:
        mind = host.mind.context()
        reflection_context = {
            "mind": {key: mind[key] for key in (
                "owner_approved", "profile_id", "version", "worldview", "household_values", "core_principles"
            ) if key in mind},
            "active_goal_snapshots": host.conversation_state.active_goal_snapshots(),
            "recent_goal_snapshots": host.conversation_state.recent_goal_snapshots(),
            "execution_outcome_bundle": bundle.model_dump(mode="json", exclude_none=True),
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
        }
        for source, target in (("goal_association", "goal_association_resolution"), ("situation", "situation")):
            projection = response.metadata.get(source)
            if isinstance(projection, dict):
                reflection_context[target] = dict(projection)
        requests = [ReflectionRequest(
            sid=session_id, text=execution_outcome_user_text(response, plan),
            language=str(response.metadata.get("language") or "en-US"),
            opportunity=opportunity,
            context={**reflection_context, "cognitive_opportunity": opportunity.prompt_projection()},
            history=host.conversation_state.get_history(),
        ) for opportunity in opportunities]
    except Exception as exc:
        host.session_log(session_id, "selective_reflection_context_rejected: error=%s", exc)
        return

    async def learn_forward() -> None:
        timeout_ms = host.cognitive_runtime_policy.deliberative_timeout_ms
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                session = await host.get_http_session()
                for request in requests:
                    result = await reflection_call(session, request=request, timeout_ms=timeout_ms)
                    if generation != host.playback_delivery.playback_generation:
                        host.session_log(session_id, "selective_reflection_suppressed: reason=stale_generation")
                        return
                    state_results = host.conversation_state.apply_reflection_resolution(result, sid=session_id)
                    response.metadata.setdefault("reflection_resolutions", []).append(result.prompt_projection())
                    response.metadata.setdefault("reflection_state_results", []).extend(state_results)
                    # Only the state owner's bounded Memory proposals can affect
                    # future cognition. Advisory actions never bypass handled-
                    # Evidence suppression or trigger a second Planner result.
                    host.session_log(session_id, "selective_reflection_recorded: opportunity=%s", request.opportunity.opportunity_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            host.session_log(session_id, "selective_reflection_unavailable: error_type=%s error=%s", type(exc).__name__, exc)

    task = asyncio.create_task(learn_forward(), name=f"outcome-reflection:{response.interaction_id}")
    tasks[task] = response.interaction_id
    task.add_done_callback(host._cognitive_runtime_task_done)


async def close_cognitive_execution(
    host: Any,
    *,
    response: InteractionResponse,
    execution: CapabilityRuntimeResult,
    session_id: str | None,
    generation: int,
    provider_status: dict[str, Any] | None,
    suppress_final_reason: str | None = None,
) -> str:
    closure = cognitive_turn_closure_adapter(host)
    interaction_ledger = getattr(
        getattr(host, "interaction_runtime", None),
        "interaction_ledger",
        None,
    )
    try:
        plan = closure.canonical_plan(response)
    except Exception as exc:
        plan = None
        host.session_log(
            session_id,
            "cognitive_outcome_plan_rejected: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        response.metadata["execution_outcome_error"] = (
            f"plan_rejected:{type(exc).__name__}"
        )
    if plan is None:
        return "not_applicable"

    try:
        bundle = closure.build(
            response=response,
            execution=execution,
            session_id=session_id,
            provider_status=provider_status,
        )
        if bundle is None:  # pragma: no cover - guarded by plan above
            raise ValueError("effectful cognitive turn produced no outcome")
    except Exception as exc:
        host.session_log(
            session_id,
            "cognitive_outcome_reconciliation_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        response.metadata["execution_outcome_error"] = (
            f"reconciliation_failed:{type(exc).__name__}"
        )
        # No trusted outcome bundle exists at this boundary. Preserve the
        # diagnostic fact and fail closed; Host cannot infer result meaning or
        # manufacture a post-execution utterance without trusted Evidence.
        return "reconciliation_failed"

    response.metadata["execution_outcome_bundle"] = bundle.model_dump(
        mode="json"
    )
    if interaction_ledger is not None:
        try:
            interaction_ledger.record_execution_outcome(
                bundle,
                session_id=str(session_id or bundle.turn_id),
            )
        except Exception as exc:
            response.metadata["interaction_ledger_error"] = (
                type(exc).__name__
            )
            host.session_log(
                session_id,
                "interaction_ledger_outcome_append_failed: "
                "error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
    goal_state_results: list[dict[str, Any]] = []
    responsibility_results: list[dict[str, Any]] = []
    try:
        goal_state_results = (
            host.conversation_state.record_execution_outcome_bundle(
                bundle,
                sid=session_id,
            )
        )
        responsibility_results = (
            host.conversation_state.reconcile_execution_outcome_responsibilities(
                bundle,
                sid=session_id,
            )
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "cognitive_outcome_goal_state_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        response.metadata["execution_outcome_goal_state_error"] = (
            type(exc).__name__
        )
        # Evidence is retained, but Goal/Responsibility state did not commit.
        # Do not let Host turn that implementation failure into result meaning.
        record_cognitive_outcome_evidence(
            host,
            bundle,
            session_id=session_id,
            final_response=None,
            delivery_status="goal_state_commit_failed",
            suppression_reason="goal_state_commit_failed",
            execution=execution,
        )
        return "goal_state_commit_failed"

    response.metadata["execution_outcome_goal_state_results"] = (
        goal_state_results
    )
    response.metadata["responsibility_reconciliation_results"] = (
        responsibility_results
    )
    cognitive_opportunities = (
        host.conversation_state.derive_execution_cognitive_opportunities(
            bundle
        )
    )
    response.metadata["cognitive_opportunities"] = [
        item.prompt_projection() for item in cognitive_opportunities
    ]
    if cognitive_opportunities:
        host.session_log(
            session_id,
            "cognitive_opportunity_raised: count=%s goals=%s modes=%s",
            len(cognitive_opportunities),
            ",".join(
                goal_id
                for item in cognitive_opportunities
                for goal_id in item.goal_ids
            ),
            ",".join(
                item.recommended_cognition
                for item in cognitive_opportunities
            ),
        )
    slow_opportunities = [
        item
        for item in cognitive_opportunities
        if item.recommended_cognition == "slow"
    ]

    host.session_log(
        session_id,
        "cognitive_outcome_reconciled: outcome_id=%s aggregate=%s goals=%s evidence=%s",
        bundle.outcome_id,
        bundle.aggregate_status,
        len(bundle.goal_outcomes),
        len(bundle.evidence),
    )

    stale_outcome = host._outcome_response_is_stale(
        generation=generation,
        session_id=session_id,
    )
    current_session_id = host.session_id
    outcome_delivery = build_host_outcome_delivery(host)
    defer_for_ordinary_overlap = (
        stale_outcome
        and outcome_delivery.is_ordinary_overlap(
            origin_session_id=session_id,
            current_session_id=current_session_id,
            generation_changed=(generation != host.playback_delivery.playback_generation),
            execution_status=str(execution.status),
            aggregate_status=str(bundle.aggregate_status),
        )
    )
    if stale_outcome and not defer_for_ordinary_overlap:
        host.session_log(
            session_id,
            "cognitive_outcome_response_suppressed: reason=stale_turn",
        )
        record_cognitive_outcome_evidence(
            host,
            bundle,
            session_id=session_id,
            final_response=None,
            delivery_status="suppressed",
            suppression_reason="stale_turn",
            goal_state_results=goal_state_results,
            execution=execution,
        )
        return "suppressed_stale"
    if defer_for_ordinary_overlap:
        host.session_log(
            session_id,
            "cognitive_outcome_response_deferred: reason=ordinary_overlap current_sid=%s",
            current_session_id,
        )
    if suppress_final_reason is not None:
        record_cognitive_outcome_evidence(
            host,
            bundle,
            session_id=session_id,
            final_response=None,
            delivery_status="suppressed",
            suppression_reason=suppress_final_reason,
            goal_state_results=goal_state_results,
            execution=execution,
        )
        return f"suppressed_{suppress_final_reason}"
    delivered_incremental_evidence = {
        str(item).strip()
        for item in response.metadata.get(
            "incremental_result_delivery_evidence_ids",
            [],
        )
        if str(item).strip()
    }
    planner_handled_incremental_evidence = {
        str(item).strip()
        for item in response.metadata.get(
            "incremental_planner_reentry_evidence_ids",
            [],
        )
        if str(item).strip()
    }
    terminal_evidence_ids = {item.evidence_id for item in bundle.evidence}
    completed_evidence_ids = {
        item.evidence_id
        for item in bundle.evidence
        if item.status == "completed"
    }
    if (
        bundle.aggregate_status == "completed"
        and completed_evidence_ids
        and completed_evidence_ids.issubset(delivered_incremental_evidence)
    ):
        host.session_log(
            session_id,
            "cognitive_outcome_response_suppressed: "
            "reason=incremental_result_already_delivered evidence=%s",
            len(completed_evidence_ids),
        )
        record_cognitive_outcome_evidence(
            host,
            bundle,
            session_id=session_id,
            final_response=None,
            delivery_status="incremental_result_delivery_completed",
            suppression_reason="incremental_result_already_delivered",
            goal_state_results=goal_state_results,
            execution=execution,
        )
        return "incremental_result_delivery_completed"
    if (
        terminal_evidence_ids
        and terminal_evidence_ids.issubset(
            planner_handled_incremental_evidence
        )
    ):
        host.session_log(
            session_id,
            "cognitive_outcome_response_suppressed: "
            "reason=incremental_planner_reentry_already_handled evidence=%s",
            len(terminal_evidence_ids),
        )
        record_cognitive_outcome_evidence(
            host,
            bundle,
            session_id=session_id,
            final_response=None,
            delivery_status="incremental_planner_reentry_handled",
            suppression_reason="incremental_planner_reentry_already_handled",
            goal_state_results=goal_state_results,
            execution=execution,
        )
        return "incremental_planner_reentry_handled"

    final_response = None
    try:
        final_response = await host._plan_evidence_bound_capability_result_response(
            source_response=response,
            bundle=bundle,
            plan=plan,
            session_id=session_id,
        )
        schedule_outcome_reflection(
            host,
            response=response, plan=plan, bundle=bundle, opportunities=slow_opportunities,
            session_id=session_id, generation=generation,
        )

        if final_response is None:
            host.session_log(
                session_id,
                "planner_evidence_reentry_response_unavailable: "
                "aggregate=%s evidence=%s action=retain_evidence_no_speech",
                bundle.aggregate_status,
                len(bundle.evidence),
            )
            record_cognitive_outcome_evidence(
                host,
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="planner_reentry_unavailable",
                suppression_reason="planner_reentry_unavailable",
                goal_state_results=goal_state_results,
                execution=execution,
            )
            return "planner_reentry_unavailable"
    except Exception as exc:
        host.session_log(
            session_id,
            "cognitive_outcome_response_rejected: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        if final_response is None:
            # An error after Work is never silent (owner, 2026-10-15): the person
            # hears the operational notice; the error stays in its metadata.
            envelope = response.metadata.get("user_turn_envelope") if isinstance(response.metadata, dict) else None
            normalized_input = envelope.get("normalized_input") if isinstance(envelope, dict) else None
            final_response = host._cognitive_core_exception_safe_response(
                str(normalized_input.get("text") or "") if isinstance(normalized_input, dict) else "",
                context={"user_turn_envelope": envelope},
                failure_stage="cognitive_outcome_response",
                failure_class=type(exc).__name__,
                failure_error=str(exc),
            )

    if defer_for_ordinary_overlap:
        goal_ids = tuple(
            str(item.goal_id)
            for item in bundle.goal_outcomes
            if str(item.goal_id or "").strip()
        )
        window = await outcome_delivery.wait_for_window(
            origin_session_id=str(session_id),
            source_goal_ids=goal_ids,
            timeout_s=max(
                5.0,
                min(
                    120.0,
                    float(
                        getattr(
                            getattr(
                                getattr(host, "host_settings", None),
                                "session",
                                None,
                            ),
                            "idle_timeout_ms",
                            120000.0,
                        )
                    )
                    / 1000.0,
                ),
            ),
        )
        if window.status != "ready":
            suppression_reason = (
                "goal_invalidated_before_deferred_delivery"
                if window.status == "goal_invalidated"
                else "ordinary_overlap_delivery_timeout"
            )
            host.session_log(
                session_id,
                "cognitive_outcome_response_suppressed: reason=%s waited_for=%s",
                suppression_reason,
                ",".join(window.waited_for_session_ids),
            )
            record_cognitive_outcome_evidence(
                host,
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="suppressed",
                suppression_reason=suppression_reason,
                goal_state_results=goal_state_results,
                execution=execution,
            )
            return f"suppressed_{window.status}"
        final_response.metadata["deferred_outcome_delivery"] = {
            "reason": "ordinary_overlap",
            "origin_session_id": session_id,
            "waited_for_session_ids": list(window.waited_for_session_ids),
            "source_goal_ids": list(goal_ids),
        }
        host.session_log(
            session_id,
            "cognitive_outcome_response_delivery_ready: reason=ordinary_overlap waited_for=%s",
            ",".join(window.waited_for_session_ids),
        )

    delivery_status = await host._apply_planner_reentry_response(
        final_response,
        session_id=session_id,
    )
    response.metadata["post_execution_response"] = final_response.model_dump(
        mode="json"
    )
    record_cognitive_outcome_evidence(
        host,
        bundle,
        session_id=session_id,
        final_response=final_response,
        delivery_status=delivery_status,
        goal_state_results=goal_state_results,
        execution=execution,
    )
    return delivery_status
