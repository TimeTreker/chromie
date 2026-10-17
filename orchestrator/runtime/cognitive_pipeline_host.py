"""Cognitive Gateway/Core pipeline steps run against the VoiceAssistant host.

The functions take the VoiceAssistant composition root as ``host``. They run
the goal-driven runtime for an admitted turn, apply its Goal state and named
Goal cancellation, and keep no semantic authority of their own.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from orchestrator.runtime.confirmation import (
    pending_confirmation_goal_ids,
)
from orchestrator.runtime.named_goal_cancellation import (
    ActiveGoalCancellationRequiresRuntimeDispatch,
    cancellation_target_goal_ids,
    replacement_target_goal_ids,
    dispatch_named_goal_cancellation,
    goal_cancellation_failure_evidence,
    goal_cancellation_success_evidence,
    dispatch_goal_replacement,
)
from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimeResolution,
)
from orchestrator.runtime.observability_recording import (
    record_cognitive_runtime_evidence,
)
from orchestrator.runtime.session import (
    now_ms,
    record_session_workflow_stage,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CoreInterpretationResult,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import (
    CanonicalPlan,
)
from shared.chromie_contracts.situation import CognitiveOpportunity
from shared.chromie_contracts.control import GoalCancellationEvidence
from shared.chromie_contracts.user_turn import (
    UserTurnEnvelope,
)

logger = logging.getLogger("chromie-orchestrator")


def current_conversation_id(host: Any, session_id: str) -> str:
    conversation_id = str(
        getattr(getattr(host, "conversation_state", None), "conversation_id", "")
        or ""
    ).strip()
    return conversation_id or session_id


async def run_cognitive_runtime_pipeline(
    host: Any,
    session: aiohttp.ClientSession,
    *,
    user_text: str,
    session_id: str,
    context: dict[str, Any],
    core_interpretation: CoreInterpretationResult,
    record_evidence: bool = True,
    turn_envelope: UserTurnEnvelope | None = None,
) -> CognitiveRuntimeResolution:
    started_ms = now_ms()
    if turn_envelope is None:
        resolution = CognitiveRuntimeResolution(
            mode=host.cognitive_runtime_mode,
            status="error",
            timings_ms={"total": round(now_ms() - started_ms, 1)},
            fallback_reason="missing_admitted_user_turn_envelope",
            metadata={
                "failure_stage": "cognitive_gateway_admission",
                "failure_class": "missing_user_turn_envelope",
                "failure_domain": "contract",
                "architecture_attribution": "cognitive_gateway",
                "retryable": False,
            },
        )
        if record_evidence:
            record_cognitive_runtime_evidence(
                getattr(host, "cognitive_evidence", None),
                resolution,
                session_id=session_id,
                user_text=user_text,
                session_log=host.session_log,
            )
        host.session_log(
            session_id,
            "cognitive_runtime_rejected: reason=missing_admitted_user_turn_envelope",
        )
        return resolution
    authority_context = host._cognitive_core_authority_context(
        context,
        session_id=session_id,
        observer=host.cognitive_runtime_mode != "apply",
    )
    resolved_text = user_text
    resolved_session_id = session_id
    resolved_language = core_interpretation.language or (
        "zh-CN" if host._looks_zh(user_text) else "en-US"
    )
    resolved_history = authority_context.get("history", [])
    if turn_envelope is not None:
        projection = host._cognitive_gateway_adapter().project_for_core(
            turn_envelope,
            current_text=user_text,
            current_session_id=session_id,
            context=authority_context,
        )
        resolved_text = projection.text
        resolved_session_id = projection.sid
        resolved_language = projection.language
        authority_context = projection.context
        resolved_history = projection.history
    try:
        resolution = await asyncio.wait_for(
            host.cognitive_runtime.resolve(
                session,
                text=resolved_text,
                sid=resolved_session_id,
                core_interpretation=core_interpretation,
                context=authority_context,
                history=resolved_history,
                language=resolved_language,
                turn_envelope=turn_envelope,
            ),
            timeout=host.cognitive_runtime_timeout_ms / 1000.0,
        )
    except Exception as exc:
        status = "error"
        is_timeout = isinstance(exc, (asyncio.TimeoutError, TimeoutError))
        resolution = CognitiveRuntimeResolution(
            mode=host.cognitive_runtime_mode,
            status=status,
            turn_envelope=turn_envelope,
            timings_ms={"total": round(now_ms() - started_ms, 1)},
            fallback_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
            metadata={
                "foreground_deadline_ms": host.cognitive_runtime_timeout_ms,
                "failure_stage": "cognitive_runtime_foreground",
                "failure_class": (
                    "foreground_deadline_exceeded"
                    if is_timeout
                    else type(exc).__name__
                ),
                "failure_domain": (
                    "interaction_deadline" if is_timeout else "cognitive_runtime"
                ),
                "architecture_attribution": "not_evaluated",
                "retryable": is_timeout,
            },
        )
    if turn_envelope is not None and resolution.turn_envelope is None:
        resolution = resolution.model_copy(
            update={"turn_envelope": turn_envelope}
        )

    trace_reference = resolution.metadata.get("runtime_trace")
    if isinstance(trace_reference, dict):
        host.sessions.update_trace_correlations(
            session_id,
            cognitive_trace_id=trace_reference.get("trace_id"),
        )

    if record_evidence:
        record_cognitive_runtime_evidence(
            getattr(host, "cognitive_evidence", None),
            resolution, session_id=session_id, user_text=user_text,
            session_log=host.session_log,
        )

    terminal = resolution.terminal_plan
    failure_stage = str(resolution.metadata.get("failure_stage") or "none")
    failure_class = str(resolution.metadata.get("failure_class") or "none")
    attribution = str(
        resolution.metadata.get("architecture_attribution") or "not_evaluated"
    )
    host.session_log(
        session_id,
        "cognitive_runtime_done: mode=%s status=%s total_ms=%.1f "
        "planner=%s disposition=%s steps=%s failure_stage=%s failure_class=%s "
        "architecture_attribution=%s fallback=%s",
        resolution.mode,
        resolution.status,
        float(resolution.timings_ms.get("total", now_ms() - started_ms)),
        terminal.planner_tier if terminal is not None else "none",
        terminal.disposition if terminal is not None else "none",
        len(terminal.steps) if terminal is not None else 0,
        failure_stage,
        failure_class,
        attribution,
        resolution.fallback_reason or "none",
    )
    return resolution


def goal_cancellation_operational_fail_safe(
    host: Any,
    user_text: str,
    *,
    evidence: GoalCancellationEvidence,
) -> InteractionResponse:
    """Return one conservative warning only when Planner re-entry is unavailable.

    This is an operational safety fallback, not ordinary cancellation dialogue:
    it makes no claim that cancellation succeeded or failed and exposes no
    internal closure stage. The normal path is Planner-authored from Evidence.
    """

    text = (
        "刚才那个停止我没确认好，先别当作已经停了。"
        if host._looks_zh(user_text)
        else "I couldn't verify that stop, so don't assume it stopped."
    )
    response = host._host_speech_response(
        text,
        style="warning",
        source="host_goal_cancellation_operational_fail_safe",
    )
    return response.model_copy(
        deep=True,
        update={
            "metadata": {
                **response.metadata,
                "operational_fail_safe": True,
                "goal_cancellation_evidence": evidence.model_dump(
                    mode="json"
                ),
            }
        },
    )


async def dispatch_resolution_goal_cancellation(
    host: Any,
    resolution: CognitiveRuntimeResolution,
    *,
    session_id: str,
    user_text: str,
    language: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bridge the Core's semantic target to trusted cancellation closure."""

    return await dispatch_named_goal_cancellation(
        conversation_state=host.conversation_state,
        interaction_runtime=host.interaction_runtime,
        confirmation_dialogue=getattr(host, "confirmation_dialogue", None),
        resolution=resolution,
        session_id=session_id,
        user_text=user_text,
        language=language,
    )


async def reenter_coaffected_goals_after_cancellation(
    host: Any,
    evidence: GoalCancellationEvidence,
    *,
    session_id: str | None,
    excluded_goal_ids: set[str],
) -> dict[str, str]:
    """Re-enter the Planner for still-open siblings a shared stop halted.

    Provider-widened cancellation can stop a sibling Goal's Work while its
    responsibility stays open. The same trusted cancellation Evidence wakes
    the Planner for each such Goal from its retained provenance, so the
    Planner (never the Host) decides whether to resume, re-plan, or report.
    """

    sibling_goal_ids = [
        goal_id
        for goal_id in evidence.coaffected_goal_ids
        if goal_id not in excluded_goal_ids
    ]
    if not sibling_goal_ids:
        return {}
    statuses: dict[str, str] = {}
    for item in host.conversation_state.goal_reentry_provenance(sibling_goal_ids):
        goal_id = str(item.get("goal_id") or "")
        source_text = str(item.get("source_text") or "").strip()
        try:
            responsibilities = [
                CognitiveResponsibilityProposal.model_validate(raw)
                for raw in item.get("responsibilities") or []
            ]
        except (TypeError, ValueError):
            responsibilities = []
        if not responsibilities or not source_text:
            statuses[goal_id] = "missing_responsibility_provenance"
            continue
        opportunity = CognitiveOpportunity.create(
            trigger="execution_outcome",
            goal_ids=[goal_id],
            evidence_refs=[evidence.evidence_id],
            reason_codes=[evidence.reason_code],
            recommended_cognition="fast",
        )
        planner_response = await host._planner_state_reentry_response(
            source_response=None,
            canonical_plan=None,
            user_request=source_text,
            language=str(item.get("language") or "auto"),
            goal_ids=[goal_id],
            evidence_goal_ids=[goal_id],
            evidence_refs=[evidence.evidence_id],
            session_id=session_id,
            phase="goal_cancellation_reentry",
            context_updates={
                "trusted_goal_cancellation_evidence": [
                    evidence.model_dump(mode="json")
                ],
                "goal_cancellation_reentry": {
                    "phase": "goal_cancellation_reentry",
                    "source_goal_ids": list(evidence.target_goal_ids),
                    "evidence_refs": [evidence.evidence_id],
                    "planner_authority": "planner",
                },
                "cognitive_opportunity": opportunity.prompt_projection(),
            },
            fast_workflow_stage="fast_planner_goal_cancellation_reentry",
            response_source="fast_planner_goal_cancellation_reentry",
            responsibilities_override=responsibilities,
        )
        if planner_response is None:
            statuses[goal_id] = "no_change"
            continue
        statuses[goal_id] = await host._apply_planner_reentry_response(
            planner_response, session_id=session_id
        )
    return statuses


def launch_coaffected_goal_reentry(
    host: Any,
    evidence: GoalCancellationEvidence,
    *,
    session_id: str | None,
    excluded_goal_ids: set[str],
) -> None:
    if not set(evidence.coaffected_goal_ids) - excluded_goal_ids:
        return
    task = asyncio.create_task(
        reenter_coaffected_goals_after_cancellation(host,
            evidence,
            session_id=session_id,
            excluded_goal_ids=excluded_goal_ids,
        ),
        name=f"coaffected-goal-reentry:{evidence.evidence_id}",
    )
    result_tasks = getattr(host, "active_cognitive_runtime_tasks", None)
    if not isinstance(result_tasks, dict):
        result_tasks = {}
        host.active_cognitive_runtime_tasks = result_tasks
    result_tasks[task] = evidence.evidence_id
    task.add_done_callback(host._cognitive_runtime_task_done)


def apply_cognitive_goal_state(
    host: Any,
    resolution: CognitiveRuntimeResolution,
    *,
    session_id: str,
    user_text: str,
) -> list[dict[str, Any]]:
    association = resolution.goal_association
    if association is None:
        return []
    replacement_goal_ids = {
        goal_id
        for goal in association.new_goals
        for goal_id in goal.supersedes_goal_ids
    }
    if replacement_goal_ids:
        raise ActiveGoalCancellationRequiresRuntimeDispatch(
            sorted(replacement_goal_ids)
        )
    cancel_goal_ids = {
        goal_id
        for item in association.associations
        if item.relationship == "cancel"
        for goal_id in item.target_goal_ids
    }
    if cancel_goal_ids:
        snapshots = host.conversation_state.active_goal_snapshots(
            limit=host.conversation_state.max_pending_tasks
        )
        runtime_bound: list[str] = []
        for snapshot in snapshots:
            goal_id = str(snapshot.get("goal_id") or "").strip()
            if goal_id not in cancel_goal_ids:
                continue
            status = str(snapshot.get("status") or "").strip()
            metadata = snapshot.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            remaining = metadata.get("remaining_request_ids")
            if isinstance(remaining, str):
                remaining = [remaining]
            has_remaining = bool(
                isinstance(remaining, list)
                and any(str(item).strip() for item in remaining)
            )
            exact_binding = all(
                str(metadata.get(key) or "").strip()
                for key in (
                    "interaction_id",
                    "canonical_plan_id",
                    "canonical_plan_fingerprint",
                )
            )
            if (
                status
                in {
                    "awaiting_confirmation",
                    "committed",
                    "scheduled",
                    "running",
                    "paused",
                }
                or has_remaining
                or exact_binding
            ):
                runtime_bound.append(goal_id)
        if runtime_bound:
            raise ActiveGoalCancellationRequiresRuntimeDispatch(
                runtime_bound
            )
    results = host.conversation_state.apply_goal_association_resolution(
        association,
        sid=session_id,
        user_text=user_text,
        source="goal_driven_cognitive_runtime",
        atomic=True,
    )
    rejected = [
        item
        for item in results
        if item.get("applied") is False
        and item.get("reason") != "operation_already_applied"
    ]
    if rejected:
        raise ValueError(
            "goal-state commit rejected: "
            + json.dumps(rejected, ensure_ascii=False)
        )
    return results


def commit_goal_association_state(
    host: Any,
    association: GoalAssociationResolution,
    *,
    sid: str | None,
    user_text: str,
    source: str,
) -> list[dict[str, Any]]:
    """Commit the validated Goal Association DTO without semantic reinterpretation."""

    results = host.conversation_state.apply_goal_association_resolution(
        association,
        sid=sid,
        user_text=user_text,
        source=source,
        atomic=True,
    )
    applied = [item for item in results if item.get("applied") is True]
    if applied:
        created = [item for item in applied if item.get("operation") == "create"]
        try:
            snapshot = host.conversation_state.snapshot()
            active_goals = host.conversation_state.active_goal_snapshots(
                limit=host.conversation_state.max_pending_tasks
            )
            recent_goals = snapshot.get("recent_goal_snapshots")
            if not isinstance(recent_goals, list):
                recent_goals = []
            host._log_goal_list(
                sid,
                phase="after_association",
                active_goals=active_goals,
                recent_terminal_goals=recent_goals,
                applied_operations=applied,
            )
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            # Observability must never turn committed Goal state into a failed turn.
            logger.warning(
                "goal_list_after_association_log_failed: applied=%s error_type=%s error=%s",
                len(applied),
                type(exc).__name__,
                exc,
            )
    return results


def commit_planner_information_gaps(
    host: Any,
    gaps_by_goal_id: dict[str, list[Any]],
    *,
    turn_id: str,
    sid: str | None,
    user_text: str,
    source: str,
) -> list[dict[str, Any]]:
    """Persist Fast-Planner gaps after deterministic Goal identity binding."""

    return host.conversation_state.apply_planner_information_gaps(
        gaps_by_goal_id,
        turn_id=turn_id,
        sid=sid,
        user_text=user_text,
        source=source,
    )


async def try_apply_cognitive_runtime(
    host: Any,
    session: aiohttp.ClientSession,
    *,
    user_text: str,
    session_id: str,
    context: dict[str, Any],
    core_interpretation: CoreInterpretationResult,
    core_interpretation_latency_ms: float,
    turn_envelope: UserTurnEnvelope | None = None,
) -> bool:
    if (
        host.cognitive_runtime_mode != "apply"
        or not host.enable_agent
        or not host.enable_interaction_response
    ):
        return False

    # Maintained apply mode fans UMI out to independent SC and task planning.
    # User Meaning Interpretation contributes Responsibility evidence only.
    fast_first_hedge = None
    runtime_context = dict(context)
    host.session_log(
        session_id,
        "goal_progress_communication_owner=social_cognition work_owner=planner umi_speech_bypassed=true",
    )
    resolution = await host._run_cognitive_runtime_pipeline(
        session,
        user_text=user_text,
        session_id=session_id,
        context=runtime_context,
        core_interpretation=core_interpretation,
        record_evidence=False,
        turn_envelope=turn_envelope,
    )
    if turn_envelope is not None and resolution.turn_envelope is None:
        resolution = resolution.model_copy(
            update={"turn_envelope": turn_envelope}
        )
    planner_speech_events = [
        event
        for event in host.playback_delivery.turn_speech_events.get(
            str(session_id or ""), []
        )
        if isinstance(event, dict)
        and str(event.get("status") or "")
        in {"scheduled", "playback_started", "playback_completed"}
        and (
            event.get("fast_activity_id")
            or event.get("communicative_activity_ids")
        )
    ]
    fast_planner_vocal_scheduled = bool(
        (
            resolution.fast_advance is not None
            and resolution.metadata.get("fast_vocal_activity_ids")
        )
        or planner_speech_events
    )
    summary = host._cognitive_resolution_summary(resolution)
    if resolution.status != "applied" or resolution.interaction_response is None:
        sessions = getattr(host, "sessions", None)
        if sessions is not None and session_id in sessions.state:
            sessions.state[session_id]["semantic_status"] = "failed"
        fallback_started_ms = now_ms()
        fast_first_scheduled = fast_planner_vocal_scheduled
        delivered_social = (
            resolution.interaction_response is not None
            and resolution.interaction_response.metadata.get("presentation_already_dispatched") is True
        )
        safe_response = resolution.interaction_response if delivered_social else host._cognitive_core_exception_safe_response(
            user_text,
            context=context,
            failure_stage=str(
                resolution.metadata.get("failure_stage")
                or "cognitive_runtime"
            ),
            failure_class=str(
                resolution.metadata.get("failure_class")
                or resolution.fallback_reason
                or resolution.status
            ),
            failure_error=str(resolution.fallback_reason or ""),
        )
        # Preserve the exact independently delivered SC response. A Work
        # failure remains failed evidence; it does not authorize a second
        # greeting or a generic Host apology over that completed act.
        if not delivered_social:
            record_session_workflow_stage(
                host,
                session_id,
                stage="fallback_speech",
                started_monotonic_ms=fallback_started_ms,
                finished_monotonic_ms=now_ms(),
                status="selected" if safe_response.speech else "silent",
                input_payload={
                    "cognitive_runtime_status": resolution.status,
                    "failure_stage": resolution.metadata.get("failure_stage"),
                    "fallback_reason": resolution.fallback_reason,
                    "user_text": user_text,
                    "early_communication_already_scheduled": fast_first_scheduled,
                },
                output_payload=safe_response,
                errors=list(resolution.metadata.get("stage_diagnostics") or []),
            )
        host.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=host._metadata_with_turn_envelope(
                {
                    "source": "goal_driven_cognitive_runtime",
                    "semantic_task_resolution_authoritative": True,
                    "cognitive_runtime_resolution": summary,
                    "semantic_status": "failed",
                    "semantic_failure_stage": str(
                        resolution.metadata.get("failure_stage")
                        or "cognitive_runtime"
                    ),
                    "semantic_failure_class": str(
                        resolution.metadata.get("failure_class")
                        or resolution.fallback_reason
                        or resolution.status
                    ),
                    "canonical_goal_committed": (
                        resolution.metadata.get("goal_state_commit_stage")
                        == "goal_association"
                    ),
                },
                turn_envelope,
            ),
        )
        host.conversation_state.record_interaction_response(session_id, safe_response)
        record_cognitive_runtime_evidence(
            getattr(host, "cognitive_evidence", None),
            resolution, session_id=session_id, user_text=user_text,
            session_log=host.session_log,
        )
        if delivered_social:
            host._finish_delivered_social_session(session_id, safe_response)
            return True
        host._launch_interaction(
            safe_response,
            session_id,
            reset_playback=not (
                fast_first_scheduled
                or resolution.metadata.get("social_cognition_started")
            ),
        )
        return True

    response = resolution.interaction_response.model_copy(deep=True)
    planner_source_plan = resolution.terminal_plan
    cancellation_goal_ids = cancellation_target_goal_ids(resolution)
    replacement_goal_ids = replacement_target_goal_ids(resolution)
    cancellation_reentry_source_response = response
    cancellation_reentry_source_plan: CanonicalPlan | None = None
    pending_confirmation = getattr(
        getattr(host, "confirmation_dialogue", None), "pending", None
    )
    if (
        cancellation_goal_ids
        and pending_confirmation is not None
        and cancellation_goal_ids.intersection(
            pending_confirmation_goal_ids(pending_confirmation)
        )
    ):
        cancellation_reentry_source_response = (
            pending_confirmation.response.model_copy(deep=True)
        )
        raw_pending_plan = cancellation_reentry_source_response.metadata.get(
            "canonical_plan"
        )
        if isinstance(raw_pending_plan, dict):
            try:
                cancellation_reentry_source_plan = CanonicalPlan.model_validate(
                    raw_pending_plan
                )
            except (TypeError, ValueError):
                cancellation_reentry_source_plan = None
    try:
        response_metadata = host._metadata_with_turn_envelope(
            {
                **response.metadata,
                "language": core_interpretation.language,
                "cognitive_runtime_resolution": summary,
                "user_meaning_interpretation": core_interpretation.model_dump(mode="json"),
                "experience_context": {
                    "user_text": user_text,
                    "user_meaning_interpretation_confidence": core_interpretation.confidence,
                    "user_meaning_uncertainties": [
                        item.model_dump(mode="json")
                        for item in core_interpretation.meaning_uncertainties
                    ],
                    "user_meaning_interpretation_latency_ms": core_interpretation_latency_ms,
                    "cognitive_runtime_latency_ms": float(
                        resolution.timings_ms.get("total", 0.0)
                    ),
                },
            },
            turn_envelope,
        )
        response = response.model_copy(
            deep=True,
            update={
                "metadata": response_metadata,
            },
        )
        if planner_source_plan is None:
            raw_plan = response.metadata.get("canonical_plan")
            if isinstance(raw_plan, dict):
                planner_source_plan = CanonicalPlan.model_validate(raw_plan)
        if replacement_goal_ids:
            goal_state_results, replacement_metadata = (
                await dispatch_goal_replacement(
                    conversation_state=host.conversation_state,
                    interaction_runtime=host.interaction_runtime,
                    confirmation_dialogue=getattr(host, "confirmation_dialogue", None),
                    resolution=resolution,
                    session_id=session_id,
                    user_text=user_text,
                    language=core_interpretation.language,
                )
            )
            host.interaction_runtime.runtime.refresh_planning_submission_after_goal_commit(response)
            response = host.interaction_runtime.prepare_response(
                response, session_id=session_id
            )
            response.metadata = {
                **response.metadata,
                "goal_state_results": goal_state_results,
                "goal_replacement": replacement_metadata,
            }
            resolution.goal_state_results = goal_state_results
            resolution.metadata = {
                **resolution.metadata,
                "host_commit_status": "goal_replacement_work_stopped_and_committed",
                "goal_replacement": replacement_metadata,
            }
        elif cancellation_goal_ids:
            goal_state_results, cancellation_metadata = (
                await dispatch_resolution_goal_cancellation(host,
                    resolution,
                    session_id=session_id,
                    user_text=user_text,
                    language=core_interpretation.language,
                )
            )
            association = resolution.goal_association
            if association is None:
                raise ValueError(
                    "named cancellation requires Goal Association provenance"
                )
            cancellation_evidence = goal_cancellation_success_evidence(
                source_turn_id=association.turn_id,
                metadata=cancellation_metadata,
            )
            cancellation_metadata = {
                **cancellation_metadata,
                "evidence": cancellation_evidence.model_dump(mode="json"),
            }
            planner_response: InteractionResponse | None = None
            released_goal_ids = list(
                cancellation_evidence.released_confirmation_goal_ids
            )
            reentry_source_response = response
            reentry_source_plan = planner_source_plan
            reentry_goal_ids = list(cancellation_evidence.target_goal_ids)
            if released_goal_ids and cancellation_reentry_source_plan is not None:
                reentry_source_response = cancellation_reentry_source_response
                reentry_source_plan = cancellation_reentry_source_plan
                reentry_goal_ids = list(
                    dict.fromkeys(
                        [
                            *cancellation_evidence.target_goal_ids,
                            *released_goal_ids,
                        ]
                    )
                )
            if reentry_source_plan is not None:
                planner_response = (
                    await host._planner_state_reentry_response(
                        source_response=reentry_source_response,
                        canonical_plan=reentry_source_plan,
                        user_request=user_text,
                        language=core_interpretation.language,
                        goal_ids=reentry_goal_ids,
                        evidence_goal_ids=list(cancellation_evidence.target_goal_ids),
                        evidence_refs=[cancellation_evidence.evidence_id],
                        session_id=session_id,
                        phase="goal_cancellation_reentry",
                        context_updates={
                            "trusted_goal_cancellation_evidence": [
                                cancellation_evidence.model_dump(mode="json")
                            ],
                            "goal_cancellation_reentry": {
                                "phase": "goal_cancellation_reentry",
                                "source_goal_ids": list(
                                    cancellation_evidence.target_goal_ids
                                ),
                                "evidence_refs": [cancellation_evidence.evidence_id],
                                "planner_authority": "planner",
                            },
                        },
                        fast_workflow_stage=(
                            "fast_planner_goal_cancellation_reentry"
                        ),
                        response_source=(
                            "fast_planner_goal_cancellation_reentry"
                        ),
                    )
                )
            if planner_response is None:
                # Control state is already reconciled. Never resurrect the old
                # prospective Planner wording or invent Host completion speech.
                response = response.model_copy(
                    deep=True,
                    update={
                        "speech": [],
                        "capabilities": [],
                        "requires_confirmation": False,
                    },
                )
            else:
                response = planner_response
            response = response.model_copy(
                deep=True,
                update={
                    "metadata": host._metadata_with_turn_envelope(
                        {
                            **response.metadata,
                            "cognitive_runtime_apply": True,
                            "goal_state_results": goal_state_results,
                            "named_goal_cancellation": cancellation_metadata,
                            "cognitive_runtime_resolution": summary,
                        },
                        turn_envelope,
                    )
                },
            )
            response = host.interaction_runtime.prepare_response(
                response, session_id=session_id
            )
            resolution.interaction_response = response
            resolution.goal_state_results = goal_state_results
            resolution.metadata = {
                **resolution.metadata,
                "host_commit_status": (
                    "named_goal_cancellation_dispatched_and_reconciled"
                ),
                "named_goal_cancellation": cancellation_metadata,
                "goal_cancellation_evidence_id": cancellation_evidence.evidence_id,
            }
            launch_coaffected_goal_reentry(host,
                cancellation_evidence,
                session_id=session_id,
                excluded_goal_ids=set(reentry_goal_ids),
            )
        else:
            response = host.interaction_runtime.prepare_response(
                response, session_id=session_id
            )
            if (
                str(
                    resolution.metadata.get("goal_state_commit_stage")
                    or ""
                )
                == "goal_association"
            ):
                goal_state_results = list(resolution.goal_state_results)
            else:
                goal_state_results = host._apply_cognitive_goal_state(
                    resolution,
                    session_id=session_id,
                    user_text=user_text,
                )
            response.metadata = {
                **response.metadata,
                "goal_state_results": goal_state_results,
            }
            resolution.goal_state_results = goal_state_results
            resolution.metadata = {
                **resolution.metadata,
                "host_commit_status": "prepared_and_goal_state_committed",
            }
    except Exception as exc:
        cancellation_failure_evidence: GoalCancellationEvidence | None = None
        if cancellation_goal_ids:
            association = resolution.goal_association
            source_turn_id = (
                association.turn_id
                if association is not None
                else str(session_id or "named_goal_cancellation")
            )
            cancellation_failure_evidence = goal_cancellation_failure_evidence(
                source_turn_id=source_turn_id,
                target_goal_ids=cancellation_goal_ids,
                exc=exc,
            )
        host.session_log(
            session_id,
            "cognitive_runtime_commit_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        fast_first_scheduled = fast_planner_vocal_scheduled
        resolution = resolution.model_copy(
            deep=True,
            update={
                "status": "error",
                "fallback_reason": f"host_commit_failed:{type(exc).__name__}:{str(exc)[:300]}",
                "interaction_response": None,
                "metadata": {
                    **resolution.metadata,
                    "host_commit_status": "rejected",
                },
            },
        )
        summary = host._cognitive_resolution_summary(resolution)
        safe_response: InteractionResponse
        if cancellation_failure_evidence is not None:
            planner_failure_response: InteractionResponse | None = None
            try:
                if planner_source_plan is not None:
                    planner_failure_response = (
                        await host._planner_state_reentry_response(
                            source_response=response,
                            canonical_plan=planner_source_plan,
                            user_request=user_text,
                            language=core_interpretation.language,
                            goal_ids=list(
                                cancellation_failure_evidence.target_goal_ids
                            ),
                            evidence_goal_ids=list(
                                cancellation_failure_evidence.target_goal_ids
                            ),
                            evidence_refs=[
                                cancellation_failure_evidence.evidence_id
                            ],
                            session_id=session_id,
                            phase="goal_cancellation_reentry",
                            context_updates={
                                "trusted_goal_cancellation_evidence": [
                                    cancellation_failure_evidence.model_dump(
                                        mode="json"
                                    )
                                ],
                                "goal_cancellation_reentry": {
                                    "phase": "goal_cancellation_reentry",
                                    "source_goal_ids": list(
                                        cancellation_failure_evidence.target_goal_ids
                                    ),
                                    "evidence_refs": [
                                        cancellation_failure_evidence.evidence_id
                                    ],
                                    "planner_authority": "planner",
                                },
                            },
                            fast_workflow_stage=(
                                "fast_planner_goal_cancellation_reentry"
                            ),
                            response_source=(
                                "fast_planner_goal_cancellation_reentry"
                            ),
                        )
                    )
            except Exception as reentry_exc:
                host.session_log(
                    session_id,
                    "goal_cancellation_planner_reentry_failed: "
                    "error_type=%s error=%s",
                    type(reentry_exc).__name__,
                    reentry_exc,
                )
            safe_response = (
                planner_failure_response
                or goal_cancellation_operational_fail_safe(host,
                    user_text,
                    evidence=cancellation_failure_evidence,
                )
            )
            safe_response = safe_response.model_copy(
                deep=True,
                update={
                    "metadata": host._metadata_with_turn_envelope(
                        {
                            **safe_response.metadata,
                            "goal_cancellation_evidence": (
                                cancellation_failure_evidence.model_dump(
                                    mode="json"
                                )
                            ),
                        },
                        turn_envelope,
                    )
                },
            )
        else:
            safe_response = host._cognitive_core_exception_safe_response(
                user_text,
                context=context,
                failure_stage="host_commit",
                failure_class=type(exc).__name__,
                failure_error=str(exc),
            )
        record_session_workflow_stage(
            host,
            session_id,
            stage="fallback_speech",
            started_monotonic_ms=now_ms(),
            finished_monotonic_ms=now_ms(),
            status="selected",
            input_payload={
                "failure_stage": "host_commit",
                "fallback_reason": resolution.fallback_reason,
                "user_text": user_text,
            },
            output_payload=safe_response,
            errors=[
                {"error_type": type(exc).__name__, "error": str(exc)}
            ],
        )
        host.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=host._metadata_with_turn_envelope(
                {
                    "source": "goal_driven_cognitive_runtime",
                    "semantic_task_resolution_authoritative": True,
                    "cognitive_runtime_resolution": summary,
                },
                turn_envelope,
            ),
        )
        host.conversation_state.record_interaction_response(session_id, safe_response)
        record_cognitive_runtime_evidence(
            getattr(host, "cognitive_evidence", None),
            resolution, session_id=session_id, user_text=user_text,
            session_log=host.session_log,
        )
        host._launch_interaction(
            safe_response, session_id, reset_playback=not fast_first_scheduled
        )
        return True

    host.conversation_state.record_user_turn(
        session_id,
        user_text,
        metadata=host._metadata_with_turn_envelope(
            {
                "source": "goal_driven_cognitive_runtime",
                "confidence": core_interpretation.confidence,
                "semantic_task_resolution_authoritative": True,
                "cognitive_runtime_resolution": summary,
                **(
                    {
                        "semantic_status": "terminal_without_canonical_goal",
                        "canonical_goal_committed": False,
                    }
                    if resolution.metadata.get("terminal_user_meaning_interpretation") is True
                    else {}
                ),
            },
            turn_envelope,
        ),
    )
    record_cognitive_runtime_evidence(
        getattr(host, "cognitive_evidence", None),
        resolution, session_id=session_id, user_text=user_text,
        session_log=host.session_log,
    )
    host.session_log(
        session_id,
        "cognitive_interaction_ready: speech=%s capabilities=%s requires_confirmation=%s",
        len(response.speech),
        len(response.capabilities),
        response.requires_confirmation,
    )
    for request in response.capabilities:
        host.session_log(
            session_id,
            "cognitive_capability_proposed: request_id=%s capability_id=%s timing=%s "
            "requires_confirmation=%s args=%s",
            request.request_id,
            request.capability_id,
            request.timing,
            request.requires_confirmation,
            json.dumps(request.args, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    fast_first_scheduled = fast_planner_vocal_scheduled
    if response.metadata.get("presentation_already_dispatched") is True:
        # SC may have delivered a social-only interaction while GA completed
        # its continuity check. Preserve that exact response in conversation
        # history, but never schedule the already-dispatched presentation twice.
        host.conversation_state.record_interaction_response(
            session_id, response
        )
        host._finish_delivered_social_session(session_id, response)
        return True
    if await host._stage_interaction_confirmation(
        response,
        session_id,
        language=core_interpretation.language,
        reset_playback=not fast_first_scheduled,
    ):
        return True
    await host.interaction_runtime.runtime.record_planning_submission(
        response, lambda: host.conversation_state.record_interaction_response(session_id, response),
    )
    host._launch_interaction(
        response, session_id, reset_playback=not (fast_first_scheduled or resolution.metadata.get("social_cognition_started"))
    )
    return True
