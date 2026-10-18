"""Planner re-entry after terminal Capability results and provider state.

The functions take the VoiceAssistant composition root as ``host``. Pure
binding and provenance validation stays in ``orchestrator.runtime.planner_reentry``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any


from orchestrator.runtime.cognitive_runtime import (
    CognitiveStageFailure,
)
from orchestrator.runtime.cognitive_activation import (
    activation_requested,
    resolve_cognitive_activation,
)
from orchestrator.runtime.outcome_reconciliation import planner_execution_outcome_truth
from orchestrator.runtime.situation import (
    build_provider_state_situation_observation,
    build_situation_projection,
    derive_situation_revision_opportunity,
)
from orchestrator.runtime.planner_reentry import (
    fresh_capability_state_projection,
    incremental_execution_outcome_truth,
    planner_reentry_repeats_completed_activity,
    planner_reentry_responsibilities,
    provider_state_relevance,
    terminal_evidence_relevance,
)
from orchestrator.runtime.session import (
    now_ms,
    record_session_workflow_stage,
)
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
    PlannerReentryScope,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    CapabilityResult,
)
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    SocialCommunicationNeed,
    canonical_plan_fingerprint,
    communication_need_id,
)
from shared.chromie_contracts.social_cognition import (
    SocialCognitionRequest,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    aggregate_execution_status,
    goal_completion_qualification_summary,
)
from shared.chromie_contracts.situation import CognitiveOpportunity, SituationProjection
from shared.chromie_contracts.tool_result import (
    ToolResultEvidence,
    canonical_value_sha256,
)
from orchestrator.runtime import cognitive_outcome_host


async def reenter_cognition_for_terminal_capability(
    host: Any,
    *,
    response: InteractionResponse,
    result: CapabilityResult,
    session_id: str | None,
    generation: int,
) -> None:
    """Turn one exact terminal Runtime result into an internal cognitive event.

    The result is never encoded as a user message and never decides a response
    by callback convention. Runtime owns the lifecycle fact, deterministic
    closure creates terminal Evidence, and a bounded CognitiveOpportunity
    reactivates Planner against the still-current Responsibility, Goal,
    Situation, Work, and Evidence state. Planner may answer, author genuinely
    new follow-up Work, clarify, refuse, or make no useful outward change.
    """

    try:
        evidence = cognitive_outcome_host.cognitive_turn_closure_adapter(host).build_terminal_evidence(
            response=response,
            result=result,
            session_id=session_id,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "incremental_terminal_evidence_rejected: request_id=%s "
            "error_type=%s error=%s",
            result.request_id,
            type(exc).__name__,
            exc,
        )
        return
    if evidence is None:
        return

    reason_codes = [
        value
        for value in (
            evidence.reason_code,
            f"execution_{evidence.status}",
        )
        if value
    ]
    opportunity = CognitiveOpportunity.create(
        trigger="execution_outcome",
        goal_ids=list(evidence.source_goal_ids),
        evidence_refs=[evidence.evidence_id],
        reason_codes=reason_codes[:8],
        recommended_cognition=(
            "fast" if evidence.status == "completed" else "slow"
        ),
    )
    response.metadata.setdefault(
        "incremental_cognitive_opportunities",
        [],
    ).append(opportunity.prompt_projection())
    host.session_log(
        session_id,
        "incremental_cognitive_opportunity: opportunity_id=%s request_id=%s "
        "goals=%s status=%s",
        opportunity.opportunity_id,
        evidence.request_id,
        ",".join(evidence.source_goal_ids),
        evidence.status,
    )

    relevant, relevance_reason = terminal_evidence_relevance(
        source_response=response,
        evidence=evidence,
        goal_bindings=host.conversation_state.goal_cancellation_bindings(
            evidence.source_goal_ids
        ),
    )
    if not relevant:
        host.session_log(
            session_id,
            "incremental_cognitive_reentry_suppressed: request_id=%s reason=%s",
            evidence.request_id,
            relevance_reason,
        )
        suppressed = response.metadata.setdefault(
            "suppressed_terminal_reentry",
            [],
        )
        suppressed.append(
            {
                "request_id": evidence.request_id,
                "evidence_id": evidence.evidence_id,
                "reason": relevance_reason,
            }
        )
        return
    if host._outcome_response_is_stale(
        generation=generation,
        session_id=session_id,
    ):
        # Ordinary overlap delivery is resolved by the final outcome path;
        # never interrupt a newer user turn with an early sibling result.
        host.session_log(
            session_id,
            "incremental_cognitive_reentry_deferred: request_id=%s reason=turn_overlap",
            evidence.request_id,
        )
        return
    observation = evidence.observation
    if evidence.status == "completed" and (
        observation is None
        or observation.status != "available"
        or not observation.schema_validated
    ):
        # A provider-completed event without qualified observation is not
        # admitted as successful factual Evidence. Aggregate closure retains
        # the failure/qualification details and may raise a slower opportunity.
        return

    try:
        result_response = await plan_incremental_terminal_result_response(
            host,
            source_response=response,
            evidence=evidence,
            opportunity=opportunity,
            session_id=session_id,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "incremental_planner_evidence_reentry_rejected: request_id=%s "
            "error_type=%s error=%s",
            evidence.request_id,
            type(exc).__name__,
            exc,
        )
        return
    if result_response is None:
        return

    # Planner has consumed this Evidence once a valid next-state decision exists.
    # Record semantic consumption before realization so aggregate closure cannot
    # plan from the same Evidence again merely because the new Activity is still
    # being accepted or executed asynchronously. Any later Runtime failure is a
    # new state transition with its own Evidence/CognitiveOpportunity.
    handled = response.metadata.setdefault(
        "incremental_planner_reentry_evidence_ids",
        [],
    )
    if evidence.evidence_id not in handled:
        handled.append(evidence.evidence_id)

    apply_status = await host._apply_planner_reentry_response(
        result_response,
        session_id=session_id,
    )
    if apply_status == "speech_runtime_completed":
        delivered = response.metadata.setdefault(
            "incremental_result_delivery_evidence_ids",
            [],
        )
        if evidence.evidence_id not in delivered:
            delivered.append(evidence.evidence_id)
    host.session_log(
        session_id,
        "incremental_cognitive_reentry_done: request_id=%s evidence_id=%s apply=%s",
        evidence.request_id,
        evidence.evidence_id,
        apply_status,
    )


async def plan_incremental_terminal_result_response(
    host: Any,
    *,
    source_response: InteractionResponse,
    evidence: ExecutionEvidence,
    opportunity: CognitiveOpportunity,
    session_id: str | None,
) -> InteractionResponse | None:
    observation = evidence.observation
    if evidence.status == "completed" and (
        observation is None
        or observation.status != "available"
        or not observation.schema_validated
    ):
        return None
    metadata = (
        source_response.metadata
        if isinstance(source_response.metadata, dict)
        else {}
    )
    envelope = metadata.get("user_turn_envelope")
    normalized_input = (
        envelope.get("normalized_input")
        if isinstance(envelope, dict)
        else None
    )
    user_request = (
        str(normalized_input.get("text") or "").strip()
        if isinstance(normalized_input, dict)
        else ""
    )
    if not user_request:
        return None
    language = str(
        metadata.get("language")
        or (
            normalized_input.get("language")
            if isinstance(normalized_input, dict)
            else ""
        )
        or "en-US"
    )
    evidence_data = (
        dict(observation.data)
        if observation is not None
        and observation.status == "available"
        and observation.schema_validated
        else {}
    )
    bounded_evidence = ToolResultEvidence(
        evidence_id=evidence.evidence_id,
        tool_id=evidence.capability_id,
        status=evidence.status,
        data=evidence_data,
        output_sha256=canonical_value_sha256(evidence_data),
    )
    try:
        canonical_plan = CanonicalPlan.model_validate(
            metadata.get("canonical_plan") or {}
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "incremental_evidence_reentry_rejected: request_id=%s "
            "error_type=%s error=%s",
            evidence.request_id,
            type(exc).__name__,
            exc,
        )
        return None
    goal_ids = list(evidence.source_goal_ids)
    evidence_refs = [bounded_evidence.evidence_id]
    extra_context = {
        "incremental_terminal_evidence": True,
        "terminal_request_id": evidence.request_id,
        "terminal_capability_id": evidence.capability_id,
        "terminal_status": evidence.status,
        "cognitive_opportunity": opportunity.prompt_projection(),
    }
    try:
        execution_truth = incremental_execution_outcome_truth(
            evidence=evidence,
            plan=canonical_plan,
        )
    except ValueError as exc:
        host.session_log(
            session_id,
            "incremental_evidence_reentry_rejected: request_id=%s "
            "error_type=%s error=%s",
            evidence.request_id,
            type(exc).__name__,
            exc,
        )
        return None
    return await host._planner_state_reentry_response(
        source_response=source_response,
        canonical_plan=canonical_plan,
        user_request=user_request,
        language=language,
        goal_ids=goal_ids,
        evidence_goal_ids=goal_ids,
        evidence_refs=evidence_refs,
        session_id=session_id,
        phase="capability_result_reentry",
        context_updates={
            "trusted_terminal_evidence": [bounded_evidence.model_dump(mode="json")],
            "trusted_execution_outcome": execution_truth,
            "result_evidence_refs": evidence_refs,
            "result_evidence_reentry": {
                "phase": "capability_result_reentry",
                "source_goal_ids": goal_ids,
                "evidence_refs": evidence_refs,
                "planner_authority": "planner",
            },
            **extra_context,
        },
        fast_workflow_stage="fast_planner_evidence_reentry",
        response_source="fast_planner_evidence_reentry",
        repeat_check_evidence=[bounded_evidence],
        repeat_check_context=extra_context,
    )


async def reenter_cognition_for_provider_state(
    host: Any,
    *,
    response: InteractionResponse,
    event: Any,
    provider_state: dict[str, Any],
    session_id: str | None,
) -> None:
    """Reactivate Planner for one meaningful live provider-state transition.

    Runtime state is bounded provenance, not a fabricated user turn and not
    completion Evidence.  Heartbeats/percentage churn are filtered before this
    method is called.
    """

    request = next(
        (item for item in response.capabilities if item.request_id == event.request_id),
        None,
    )
    if request is None:
        return
    goal_ids = [
        str(value).strip()
        for value in request.metadata.get("source_goal_ids") or []
        if str(value).strip()
    ]
    if not goal_ids:
        return
    relevant, relevance_reason = provider_state_relevance(
        source_response=response,
        request_id=event.request_id,
        source_goal_ids=goal_ids,
        goal_bindings=host.conversation_state.goal_cancellation_bindings(goal_ids),
    )
    if not relevant:
        host.session_log(
            session_id,
            "provider_state_reentry_suppressed: request_id=%s reason=%s",
            event.request_id,
            relevance_reason,
        )
        return
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    envelope = metadata.get("user_turn_envelope")
    normalized_input = (
        envelope.get("normalized_input") if isinstance(envelope, dict) else None
    )
    user_request = (
        str(normalized_input.get("text") or "").strip()
        if isinstance(normalized_input, dict)
        else ""
    )
    if not user_request:
        return
    try:
        canonical_plan = CanonicalPlan.model_validate(
            metadata.get("canonical_plan") or {}
        )
    except (TypeError, ValueError) as exc:
        host.session_log(
            session_id,
            "provider_state_reentry_rejected: request_id=%s error_type=%s error=%s",
            event.request_id,
            type(exc).__name__,
            exc,
        )
        return
    situation_observation = build_provider_state_situation_observation(
        context=host.build_context(session_id),
        turn_id=str(
            metadata.get("turn_id")
            or f"provider-state:{event.dispatch_id}:{event.request_id}"
        ),
        goal_ids=goal_ids,
        dispatch_id=event.dispatch_id,
        request_id=event.request_id,
        capability_id=event.capability_id,
        provider_id=event.provider_id,
        sequence=event.sequence,
        provider_state=provider_state,
    )
    opportunity = derive_situation_revision_opportunity(
        situation_observation,
    )
    if opportunity is None:
        return
    response.metadata.setdefault(
        "incremental_cognitive_opportunities", []
    ).append(opportunity.prompt_projection())
    if opportunity.recommended_cognition == "local":
        host.session_log(
            session_id,
            "provider_state_reentry_local: request_id=%s opportunity_id=%s",
            event.request_id,
            opportunity.opportunity_id,
        )
        return
    source_ref = situation_observation.source_refs[0]
    bounded_event = {
        "source_ref": source_ref,
        "sequence": event.sequence,
        "dispatch_id": event.dispatch_id,
        "request_id": event.request_id,
        "capability_id": event.capability_id,
        "provider_id": event.provider_id,
        "state": dict(provider_state),
    }
    planner_response = await host._planner_state_reentry_response(
        source_response=response,
        canonical_plan=canonical_plan,
        user_request=user_request,
        language=str(metadata.get("language") or "en-US"),
        goal_ids=goal_ids,
        evidence_goal_ids=[],
        evidence_refs=[],
        session_id=session_id,
        phase="situation_revision_reentry",
        context_updates={
            "situation": situation_observation.projection.prompt_projection(),
            "situation_revision_observation": situation_observation.model_dump(
                mode="json"
            ),
            "trusted_provider_state_event": bounded_event,
            "provider_state_reentry": {
                "source_goal_ids": goal_ids,
                "situation_source_refs": list(
                    situation_observation.source_refs
                ),
                "planner_authority": "planner",
            },
            "cognitive_opportunity": opportunity.prompt_projection(),
        },
        fast_workflow_stage="fast_planner_situation_revision_reentry",
        response_source="fast_planner_situation_revision_reentry",
    )
    if planner_response is None:
        return
    await host._apply_planner_reentry_response(
        planner_response, session_id=session_id
    )


async def revalidate_restored_goals_from_provider_state(host: Any) -> None:
    candidates = host.conversation_state.runtime_revalidation_candidates()
    if not candidates:
        return
    body_capability_ids = sorted(
        {
            capability_id
            for candidate in candidates
            for capability_id in candidate.get("capability_ids") or []
            if str(capability_id).startswith("soridormi.")
        }
    )
    if body_capability_ids:
        try:
            await asyncio.wait_for(
                host.interaction_runtime.refresh_soridormi_catalog(force=True),
                timeout=5.0,
            )
        except (TimeoutError, RuntimeError) as exc:
            host.session_log(
                None,
                "restored_goal_revalidation_deferred: reason=provider_state_unavailable error_type=%s",
                type(exc).__name__,
            )
            return

    for candidate in candidates:
        goal_id = str(candidate.get("goal_id") or "").strip()
        user_request = str(candidate.get("source_text") or "").strip()
        raw_responsibilities = candidate.get("responsibilities")
        capability_ids = [
            str(item).strip()
            for item in candidate.get("capability_ids") or []
            if str(item).strip()
        ]
        if not goal_id or not user_request or not isinstance(raw_responsibilities, list):
            continue
        if not capability_ids:
            host.session_log(
                None,
                "restored_goal_revalidation_deferred: goal_id=%s reason=no_prior_capability_binding",
                goal_id,
            )
            continue
        responsibilities: list[CognitiveResponsibilityProposal] = []
        try:
            responsibilities = [
                CognitiveResponsibilityProposal.model_validate(item)
                for item in raw_responsibilities
                if isinstance(item, dict)
            ]
        except (TypeError, ValueError) as exc:
            host.session_log(
                None,
                "restored_goal_revalidation_rejected: goal_id=%s reason=invalid_responsibility_provenance error_type=%s",
                goal_id,
                type(exc).__name__,
            )
            continue
        if not responsibilities:
            host.session_log(
                None,
                "restored_goal_revalidation_deferred: goal_id=%s reason=missing_responsibility_provenance",
                goal_id,
            )
            continue

        provider_state = fresh_capability_state_projection(
            capability_ids,
            capability_definition=host.interaction_runtime.capability_definition,
        )
        restored_marker = str(candidate.get("restored_ms") or "unknown").strip()
        source_ref = f"runtime-state:restart:{goal_id}:{restored_marker}"[:200]
        opportunity = CognitiveOpportunity.create(
            trigger="provider_state",
            goal_ids=[goal_id],
            evidence_refs=[],
            reason_codes=["restored_goal_fresh_provider_state"],
            recommended_cognition="fast",
        )
        planner_response = await host._planner_state_reentry_response(
            source_response=None,
            canonical_plan=None,
            user_request=user_request,
            language=str(candidate.get("language") or "auto"),
            goal_ids=[goal_id],
            evidence_goal_ids=[],
            evidence_refs=[],
            session_id=None,
            phase="restored_provider_state_revalidation",
            context_updates={
                "trusted_provider_state_event": {
                    "source_ref": source_ref,
                    "source": "restart_provider_revalidation",
                    "capabilities": provider_state,
                },
                "provider_state_reentry": {
                    "source_goal_ids": [goal_id],
                    "state_refs": [source_ref],
                    "planner_authority": "planner",
                    "restored_goal": True,
                },
                "cognitive_opportunity": opportunity.prompt_projection(),
            },
            fast_workflow_stage="fast_planner_restored_provider_state_reentry",
            response_source="fast_planner_restored_provider_state_reentry",
            responsibilities_override=responsibilities,
        )
        if planner_response is None:
            continue
        completed = host.conversation_state.complete_runtime_revalidation(
            [goal_id],
            source_ref=source_ref,
        )
        if goal_id not in completed:
            continue
        await host._apply_planner_reentry_response(
            planner_response,
            session_id=None,
        )


async def apply_planner_reentry_response(
    host: Any,
    response: InteractionResponse,
    *,
    session_id: str | None,
) -> str:
    """Apply a Planner delta without turning asynchronous cognition into a join.

    Speech-only deltas use the ordinary delivery path. A new safe/authorized
    Capability delta is submitted through the same detached Runtime boundary as
    foreground work, so its own terminal events can create later opportunities.
    Confirmation-requiring Work is not auto-authorized by an internal event.
    """

    if not response.capabilities:
        return await host._execute_cognitive_outcome_response(
            response,
            session_id=session_id,
            detached_delivery=True,
        )
    confirmation_ids = await host.interaction_runtime.confirmation_request_ids(response)
    if confirmation_ids:
        confirmation_session_id = str(
            session_id
            or response.metadata.get("parent_interaction_id")
            or response.interaction_id
        )
        staged = await host._stage_interaction_confirmation(
            response,
            confirmation_session_id,
            language=str(response.metadata.get("language") or "auto"),
            reset_playback=False,
        )
        if staged:
            host.session_log(
                confirmation_session_id,
                "planner_reentry_confirmation_staged: requests=%s",
                ",".join(sorted(confirmation_ids)),
            )
            return "planner_reentry_confirmation_staged"
        return "planner_reentry_confirmation_required"
    await host.interaction_runtime.runtime.record_planning_submission(
        response, lambda: host.conversation_state.record_interaction_response(session_id, response),
    )
    await host._dispatch_detached_interaction(
        response,
        session_id,
        confirmed_request_ids=None,
        reset_playback=False,
        mark_session_done=False,
    )
    return "planner_reentry_dispatched"


async def planner_state_reentry_response(
    host: Any,
    *,
    source_response: InteractionResponse | None,
    canonical_plan: CanonicalPlan | None,
    user_request: str,
    language: str,
    goal_ids: list[str],
    evidence_goal_ids: list[str],
    evidence_refs: list[str],
    session_id: str | None,
    phase: str,
    context_updates: dict[str, Any],
    fast_workflow_stage: str,
    response_source: str,
    responsibilities_override: list[CognitiveResponsibilityProposal] | None = None,
    parent_interaction_id: str | None = None,
    repeat_check_evidence: list[ToolResultEvidence] | None = None,
    repeat_check_context: dict[str, Any] | None = None,
) -> InteractionResponse | None:
    """Reactivate the same Planner from one trusted state transition.

    The Host supplies bounded facts and provenance only. It does not convert
    those facts into dialogue or a replacement Goal/Plan.
    """

    normalized_goal_ids = list(
        dict.fromkeys(
            str(item).strip() for item in goal_ids if str(item).strip()
        )
    )
    normalized_evidence_goal_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in evidence_goal_ids
            if str(item).strip()
        )
    )
    normalized_evidence_refs = list(
        dict.fromkeys(
            str(item).strip() for item in evidence_refs if str(item).strip()
        )
    )
    opportunity_projection = context_updates.get("cognitive_opportunity")
    opportunity: CognitiveOpportunity | None = None
    if isinstance(opportunity_projection, dict):
        try:
            opportunity = CognitiveOpportunity.model_validate(opportunity_projection)
        except (TypeError, ValueError):
            opportunity = None
    opportunity_ref = opportunity.opportunity_id if opportunity is not None else ""
    provided_situation: SituationProjection | None = None
    raw_situation = context_updates.get("situation")
    if isinstance(raw_situation, dict):
        try:
            provided_situation = SituationProjection.model_validate(raw_situation)
        except (TypeError, ValueError) as exc:
            host.session_log(
                session_id,
                "planner_state_reentry_rejected: reason=invalid_situation "
                "error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return None
    if opportunity is not None and opportunity.situation_digest:
        if (
            provided_situation is None
            or provided_situation.digest != opportunity.situation_digest
        ):
            host.session_log(
                session_id,
                "planner_state_reentry_rejected: "
                "reason=situation_opportunity_digest_mismatch",
            )
            return None
    if not normalized_evidence_refs and (
        opportunity is None
        or set(opportunity.goal_ids) != set(normalized_goal_ids)
    ):
        host.session_log(
            session_id,
            "planner_state_reentry_rejected: "
            "reason=missing_or_mismatched_non_evidence_opportunity",
        )
        return None
    reentry_ref = (
        normalized_evidence_refs[0]
        if normalized_evidence_refs
        else opportunity_ref
    )
    if not normalized_goal_ids or not reentry_ref:
        return None
    metadata = (
        source_response.metadata
        if source_response is not None
        and isinstance(source_response.metadata, dict)
        else {}
    )
    association = metadata.get("goal_association")
    if source_response is not None:
        if not isinstance(association, dict):
            host.session_log(
                session_id,
                "planner_state_reentry_rejected: reason=missing_goal_association",
            )
            return None
        association_goal_ids = {
            str(goal_id).strip()
            for item in association.get("associations") or []
            if isinstance(item, dict)
            for goal_id in item.get("target_goal_ids") or []
        } | {
            str(item.get("goal_id") or "").strip()
            for item in association.get("new_goals") or []
            if isinstance(item, dict)
        }
        if not set(normalized_goal_ids).issubset(association_goal_ids):
            raise ValueError(
                "Planner state re-entry Goal binding is not present in Goal Association"
            )
    responsibilities = list(responsibilities_override or [])
    if not responsibilities and source_response is not None:
        responsibilities = planner_reentry_responsibilities(
            source_response=source_response,
            goal_ids=normalized_goal_ids,
        )
    if not responsibilities:
        host.session_log(
            session_id,
            "planner_state_reentry_rejected: "
            "reason=missing_responsibility_provenance",
        )
        return None

    # Re-entry is an exact Goal subset, not the originating turn replayed with
    # a hint. Remove excluded sibling semantic material before Planner sees the
    # state so a per-result response cannot narrate another Goal's effect.
    scoped_goal_set = set(normalized_goal_ids)
    scoped_responsibility_refs = {
        item.local_ref for item in responsibilities
    }
    if isinstance(association, dict):
        scoped_new_goals: list[dict[str, Any]] = []
        for item in association.get("new_goals") or []:
            if (
                not isinstance(item, dict)
                or str(item.get("goal_id") or "").strip()
                not in scoped_goal_set
            ):
                continue
            scoped_goal = dict(item)
            # source_text can contain excluded sibling responsibilities from
            # the originating multi-Goal turn.  The scoped description,
            # bindings, and success criteria retain this Goal's exact meaning.
            scoped_goal.pop("source_text", None)
            scoped_new_goals.append(scoped_goal)
        association = {
            **association,
            "associations": [
                dict(item)
                for item in association.get("associations") or []
                if isinstance(item, dict)
                and scoped_goal_set.intersection(
                    str(value).strip()
                    for value in item.get("target_goal_ids") or []
                    if str(value).strip()
                )
            ],
            "new_goals": scoped_new_goals,
        }

    sid = str(
        session_id
        or (canonical_plan.plan_id if canonical_plan is not None else "")
        or f"restored:{normalized_goal_ids[0]}"
    )
    context = host._cognitive_core_authority_context(
        host.build_context(sid),
        session_id=sid,
        observer=False,
    )
    context.update(context_updates)
    # State re-entry deliberately uses a synthetic Work-request SID and may
    # narrow one original multi-Goal turn to a strict Goal subset.  Carrying
    # the full originating UserTurnEnvelope inside this new CognitiveWorkRequest
    # would therefore assert a false transport identity: its session/text belong
    # to the admitted source turn, not to this scoped state transition.  Keep the
    # immutable envelope on source_response and project only read-only source
    # provenance plus the scoped UMI Responsibilities below.
    context.pop("user_turn_envelope", None)
    source_envelope = metadata.get("user_turn_envelope")
    source_original_input = (
        source_envelope.get("original_input")
        if isinstance(source_envelope, dict)
        else None
    )
    source_normalized_input = (
        source_envelope.get("normalized_input")
        if isinstance(source_envelope, dict)
        else None
    )
    source_original_text = (
        source_original_input.get("text")
        if isinstance(source_original_input, dict)
        else None
    )
    source_normalized_text = (
        source_normalized_input.get("text")
        if isinstance(source_normalized_input, dict)
        else None
    )
    if (
        isinstance(source_original_text, str)
        and source_original_text
        and (
            not isinstance(source_normalized_text, str)
            or " ".join(source_original_text.strip().split())
            == " ".join(source_normalized_text.strip().split())
        )
    ):
        context["source_turn_provenance"] = {
            "schema_version": 1,
            "turn_id": str(
                source_envelope.get("turn_id")
                or metadata.get("turn_id")
                or ""
            ),
            "original_text": source_original_text,
            "original_text_sha256": hashlib.sha256(
                source_original_text.encode("utf-8")
            ).hexdigest(),
            "language": str(
                (
                    source_normalized_input.get("language")
                    if isinstance(source_normalized_input, dict)
                    else language
                )
                or language
                or "auto"
            ),
            "authority": "read_only_source_provenance",
        }
    if isinstance(association, dict):
        context["goal_association_resolution"] = association
    if canonical_plan is not None:
        plan_projection = canonical_plan.prompt_projection()
        selected_step_ids = {
            step.step_id
            for step in canonical_plan.steps
            if scoped_goal_set.intersection(step.source_goal_ids)
        }
        plan_projection.update(
            {
                "goal_ids": normalized_goal_ids,
                "response_text": "",
                "steps": [
                    item
                    for item in plan_projection.get("steps") or []
                    if isinstance(item, dict)
                    and str(item.get("step_id") or "") in selected_step_ids
                ],
                "goal_outcomes": [
                    item
                    for item in plan_projection.get("goal_outcomes") or []
                    if isinstance(item, dict)
                    and str(item.get("goal_id") or "") in scoped_goal_set
                ],
                "parameter_resolutions": [
                    item
                    for item in plan_projection.get("parameter_resolutions") or []
                    if isinstance(item, dict)
                    and str(item.get("step_id") or "") in selected_step_ids
                ],
                "time_conditions": [
                    item
                    for item in plan_projection.get("time_conditions") or []
                    if isinstance(item, dict)
                    and str(item.get("goal_id") or "") in scoped_goal_set
                ],
            }
        )
        context["canonical_plan_resolution"] = plan_projection
        planner_reentry_expectations = [
            {
                "step_id": step.step_id,
                "source_goal_ids": list(step.source_goal_ids),
                "step_purpose": step.step_purpose,
                "expected_outcome": step.expected_outcome,
            }
            for step in canonical_plan.steps
            if step.expected_outcome
            and set(step.source_goal_ids) & set(normalized_goal_ids)
        ]
        if planner_reentry_expectations:
            # Planner-authored prospective expectations are hypotheses to compare
            # with fresh trusted Evidence, never Host-created Evidence themselves.
            context["planner_reentry_expectations"] = planner_reentry_expectations
    # A state re-entry is an exact Goal-subset transaction. The full immutable
    # UserTurnEnvelope can contain excluded sibling semantics, so it remains on
    # the source response. Its exact wording is exposed separately above as
    # read-only provenance, while only authoritative scoped UMI Responsibility
    # outcomes become request.text. Canonical Goal and Plan projections retain
    # the scoped bindings and execution correlation.
    scoped_request_text = "\n".join(
        dict.fromkeys(
            item.outcome.strip()
            for item in responsibilities
            if item.outcome.strip()
        )
    )
    if isinstance(metadata.get("user_meaning_interpretation"), dict):
        source_interpretation = dict(metadata["user_meaning_interpretation"])
        source_interpretation["responsibilities"] = [
            item
            for item in source_interpretation.get("responsibilities") or []
            if isinstance(item, dict)
            and str(item.get("local_ref") or "")
            in scoped_responsibility_refs
        ]
        context["core_interpretation"] = source_interpretation
    if provided_situation is not None:
        if not set(normalized_goal_ids).issubset(
            set(provided_situation.focus_goal_ids)
        ):
            host.session_log(
                session_id,
                "planner_state_reentry_rejected: "
                "reason=situation_goal_binding_mismatch",
            )
            return None
        situation = provided_situation
    else:
        situation = build_situation_projection(
            context=context,
            turn_id=str(
                metadata.get("turn_id")
                or f"state:{reentry_ref}"
            ),
            focus_goal_ids=normalized_goal_ids,
            revision=1,
        )
    context["situation"] = situation.prompt_projection()
    interaction_ledger = getattr(
        getattr(host, "cognitive_runtime", None),
        "interaction_ledger",
        None,
    )
    if interaction_ledger is not None:
        context["interaction_context"] = interaction_ledger.context(
            sid,
            goal_ids=normalized_goal_ids,
            turn_id=str(metadata.get("turn_id") or ""),
        ).model_dump(mode="json")

    source_plan_id = canonical_plan.plan_id if canonical_plan is not None else ""
    source_plan_fingerprint = (
        canonical_plan_fingerprint(canonical_plan)
        if canonical_plan is not None
        else ""
    )
    reentry_scope = PlannerReentryScope(
        trigger=phase,
        goal_ids=normalized_goal_ids,
        evidence_refs=normalized_evidence_refs,
        opportunity_id=opportunity_ref,
        source_plan_id=source_plan_id,
        source_plan_fingerprint=source_plan_fingerprint,
    )
    request = CognitiveWorkRequest(
        sid=f"{sid}:state:{reentry_ref}"[:160],
        text=scoped_request_text,
        language=language,
        responsibilities=responsibilities,
        interpretation_confidence=1.0,
        planner_reentry_scope=reentry_scope,
        context=context,
        history=list(context.get("history") or []),
    )
    planning_runtime = host.cognitive_runtime.adapter.interaction_runtime.runtime
    planning_snapshot = await planning_runtime.planning_state_snapshot(
        normalized_goal_ids, str(metadata.get("turn_id") or request.sid),
    )
    context["existing_work_activities"] = planning_runtime.planning_work_activities(planning_snapshot)
    request = request.model_copy(deep=True, update={"context": context})

    activation_trigger = {
        "capability_result_reentry": "execution_outcome",
        "post_execution": "post_execution",
        "goal_cancellation_reentry": "goal_cancellation",
        "situation_revision_reentry": (
            "provider_state"
            if context_updates.get("trusted_provider_state_event") is not None
            else "situation_revision"
        ),
        "time_condition_reentry": "time_condition",
        "restored_provider_state_revalidation": "restored_provider_state",
    }.get(phase)
    if activation_trigger is None:
        host.session_log(
            session_id,
            "planner_state_reentry_rejected: reason=unknown_activation_trigger phase=%s",
            phase,
        )
        return None
    activation_source_refs = list(normalized_evidence_refs)
    if not activation_source_refs and opportunity is not None:
        activation_source_refs = list(opportunity.source_refs)
    activation = await resolve_cognitive_activation(
        host,
        trigger=activation_trigger,
        allowed_authorities=["planner"],
        goal_ids=normalized_goal_ids,
        responsibilities=responsibilities,
        source_refs=activation_source_refs,
        session_id=session_id,
        request_id=f"activation:{phase}:{reentry_ref}"[:200],
        state={
            "goal_association": context.get("goal_association_resolution"),
            "goal_state": context.get("active_goal_snapshots", []),
            "canonical_plan": context.get("canonical_plan_resolution"),
            "existing_work_activities": context.get("existing_work_activities", []),
            "situation": context.get("situation"),
            "trusted_state_change": dict(context_updates),
        },
    )
    if not activation_requested(activation, "planner"):
        host.session_log(
            session_id,
            "planner_state_reentry_not_requested: phase=%s ref=%s",
            phase,
            reentry_ref,
        )
        return None

    session = await host.get_http_session()
    workflow_input = {
        "source_goal_ids": normalized_goal_ids,
        "evidence_goal_ids": normalized_evidence_goal_ids,
        "evidence_refs": normalized_evidence_refs,
        "phase": phase,
    }
    async def resolve_reentry_plan(operation, workflow_stage, stage_metadata):
        started_ms = now_ms()
        result = None
        try:
            result = await operation
            failure = host.cognitive_runtime._optional_stage_failure_metadata(
                workflow_stage, result.metadata,
            )
            if host.cognitive_runtime._fast_plan_path(result) == "contract_failure":
                raise CognitiveStageFailure(
                    workflow_stage,
                    failure or host.cognitive_runtime._stage_failure_metadata(
                        workflow_stage, result.metadata,
                        default_failure_class="fast_planner_contract_failure",
                    ),
                )
            if set(result.goal_ids) != set(normalized_goal_ids):
                raise ValueError("Planner state re-entry changed the bound Goal set")
        except Exception as exc:
            record_session_workflow_stage(
                host, session_id, stage=workflow_stage,
                started_monotonic_ms=started_ms, finished_monotonic_ms=now_ms(),
                status="failed", input_payload=workflow_input, output_payload=result,
                errors=[{"error_type": type(exc).__name__, "error": str(exc)}],
                metadata={**stage_metadata, **getattr(exc, "failure_metadata", {})},
            )
            raise
        record_session_workflow_stage(
            host, session_id, stage=workflow_stage,
            started_monotonic_ms=started_ms, finished_monotonic_ms=now_ms(),
            status="resolved", input_payload=workflow_input, output_payload=result,
            errors=[], metadata=stage_metadata,
        )
        return result

    # Activation decides whether Planner should run; the one Planner owns HOW and
    # nothing re-plans its decision. Runtime never selects reasoning depth from
    # event type or a Host-authored readiness mode.
    replanned: CanonicalPlan | None = await resolve_reentry_plan(
        host.agent_client.resolve_plan(
            session, request=request,
            timeout_ms=host.cognitive_runtime_policy.planner_timeout_ms,
        ), fast_workflow_stage, {"planner_pass": "fast"},
    )

    if replanned is None:
        return None
    if (
        source_response is not None
        and repeat_check_evidence
        and planner_reentry_repeats_completed_activity(
            source_response=source_response,
            plan=replanned,
            extra_context=repeat_check_context,
            evidence=repeat_check_evidence,
        )
    ):
        raise ValueError(
            "Planner state re-entry attempted to repeat the completed terminal Activity"
        )
    runtime_errors = await host.cognitive_runtime.adapter.validation_errors(replanned)
    if runtime_errors:
        raise ValueError("Runtime rejected state re-entry Plan: " + json.dumps(runtime_errors))
    # Reviewed effects never start without a verdict: a re-entry Plan that adds a
    # value-reviewed Capability or value_review speech not yet judged in this turn
    # goes through Value Judgment, exactly as the turn's first Plan does.
    replanned = await host.cognitive_runtime.apply_value_judgment_gate(
        session, sid=sid, text=request.text, plan=replanned, work_request=request,
        goal_ids_by_responsibility=host.cognitive_runtime.goal_ids_by_responsibility_projection(association),
        turn_id=str(metadata.get("turn_id") or ""), judged_plan=canonical_plan,
    )
    if any(step.metadata.get("value_confirmation_required") for step in replanned.steps):
        replanned = host.cognitive_runtime.with_runtime_confirmation_need(replanned)
    async with planning_runtime.planning_commit_scope(planning_snapshot):
        known_ids = {item["activity_id"] for item in context["existing_work_activities"]}
        if set(replanned.cancel_activity_ids) - known_ids:
            raise ValueError("Planner cancellation names unknown Work")
        replanned, _work_status = await host.cognitive_runtime._apply_retained_work_reconciliation(
            plan=replanned, activities=context["existing_work_activities"],
            turn_id=planning_snapshot["turn_id"],
        )
        cancelled_bindings = {
            item["runtime_binding"]["interaction_id"] + "/" + item["activity_id"]
            for item in context["existing_work_activities"]
            if item["activity_id"] in replanned.cancel_activity_ids and item.get("origin") == "retained_runtime"
        }
        await planning_runtime.validate_planning_state(planning_snapshot, cancelled_bindings=cancelled_bindings)
        planning_commit = await planning_runtime.reserve_planning_submission(
            planning_snapshot, plan_id=replanned.plan_id, fingerprint=canonical_plan_fingerprint(replanned),
            prepared_activity_ids=[*replanned.cancel_activity_ids, *(step.reuse_activity_id for step in replanned.steps)],
        )
    response = await host.cognitive_runtime.resolve_plan_interaction(
        session, plan=replanned, work_request=request,
        session_id=sid,
        language=language,
        context=context, evidence_refs=normalized_evidence_refs,
    )
    response.metadata.update(
        {
            "planning_commit": planning_commit,
            "retained_work_activities": [item for item in context["existing_work_activities"]
                if item.get("origin") == "retained_runtime" and item["activity_id"] not in replanned.cancel_activity_ids],
            "planner_state_reentry": True,
            "planner_state_reentry_phase": phase,
            "planner_state_reentry_ref": reentry_ref,
            "planner_state_reentry_evidence_refs": normalized_evidence_refs,
            **(
                {"goal_association": association}
                if isinstance(association, dict)
                else {}
            ),
            **(
                {
                    "parent_interaction_id": str(
                        parent_interaction_id
                        or (source_response.interaction_id if source_response is not None else "")
                    ).strip()
                }
                if parent_interaction_id
                or source_response is not None
                else {}
            ),
        }
    )
    if isinstance(metadata.get("user_meaning_interpretation"), dict):
        response.metadata["user_meaning_interpretation"] = dict(
            metadata["user_meaning_interpretation"]
        )
    evidence_goal_set = set(normalized_evidence_goal_ids)
    for speech in response.speech:
        if speech.metadata.get("wording_owner") == "social_cognition":
            # SC's exact scope and truth stage are already validated. The
            # source Plan/Evidence remains context, not permission to widen
            # a Goal-free acknowledgement or promote it to a result claim.
            continue
        existing_source_goal_ids = {
            str(item).strip()
            for item in (
                speech.metadata.get("source_goal_ids")
                or speech.metadata.get("covers_goal_ids")
                or []
            )
            if str(item).strip()
        }
        speech.metadata.update(
            {
                "source": "planner_state_reentry",
                "phase": phase,
                **(
                    {"source_goal_ids": normalized_goal_ids}
                    if not existing_source_goal_ids
                    else {}
                ),
            }
        )
        speech_goal_ids = existing_source_goal_ids or set(normalized_goal_ids)
        if normalized_evidence_refs and (
            not speech.metadata.get("truth_stage")
            and (not evidence_goal_set or speech_goal_ids & evidence_goal_set)
        ):
            speech.metadata["truth_stage"] = "post_evidence"
        if normalized_evidence_refs and (
            not speech.metadata.get("evidence_refs")
            and (not evidence_goal_set or speech_goal_ids & evidence_goal_set)
        ):
            speech.metadata["evidence_refs"] = normalized_evidence_refs
    response.metadata.update(
        {
            "source": response_source,
            "phase": phase,
            "source_goal_ids": normalized_goal_ids,
            "evidence_refs": normalized_evidence_refs,
            "planner_reentry_plan": replanned.model_dump(
                mode="json", exclude_none=True
            ),
        }
    )
    return response


async def optional_completed_resource_social_response(
    host: Any,
    *,
    source_response: InteractionResponse,
    bundle: Any,
    plan: CanonicalPlan,
    session_id: str | None,
    language: str,
    user_request: str,
    evidence_refs: list[str],
    goal_ids: list[str],
    selected_execution_evidence: list[ExecutionEvidence],
) -> InteractionResponse | None:
    """Give SC one optional, evidence-bound handover-completion opportunity.

    Planner owns Work and Runtime owns completion truth.  A completed physical
    resource handover may still have a natural social close (for example,
    "Here you are").  Runtime exposes that trusted result as an optional
    communication Need; Social Cognition alone decides speech or silence.
    """

    completed_resource = [
        item
        for item in selected_execution_evidence
        if item.status == "completed"
        and item.capability_id == "soridormi.acquire_and_deliver_resource"
    ]
    if bundle.aggregate_status != "completed" or not completed_resource:
        return None
    if not evidence_refs or not goal_ids:
        return None

    turn_envelope = (
        source_response.metadata.get("user_turn_envelope")
        if isinstance(source_response.metadata, dict)
        else None
    )
    normalized_input = (
        turn_envelope.get("normalized_input")
        if isinstance(turn_envelope, dict)
        else None
    )
    turn_id = str(
        (turn_envelope or {}).get("turn_id")
        or source_response.metadata.get("turn_id")
        or session_id
        or "terminal-resource-delivery"
    )
    source_turn = {
        "turn_id": turn_id,
        "original_text": (
            str(normalized_input.get("text") or "").strip()
            if isinstance(normalized_input, dict)
            else user_request
        ),
    }
    interaction_ledger = getattr(host.cognitive_runtime, "interaction_ledger", None)
    interaction_context = (
        interaction_ledger.context(
            session_id, goal_ids=goal_ids, turn_id=turn_id
        ).model_dump(mode="json")
        if interaction_ledger is not None
        else {
            "events": [],
            "already_spoken": [],
            "pending_speech": [],
            "prior_delivered_speech": [],
        }
    )
    need = SocialCommunicationNeed(
        need_id=communication_need_id(plan.plan_id, "resource_delivery_completed"),
        owner="runtime",
        kind="result",
        source_goal_ids=goal_ids,
        reference_id=plan.plan_id,
        facts={
            "status": "completed",
            "result_kind": "resource_delivery_handover",
            "optional_completion_update": True,
        },
        # Built after the handover completed: the ordering is already met, and
        # this independent SC interaction transports immediate acts only (live
        # 2026-10-15: a `final` "给你。" was rejected and the handover was silent).
        delivery_phase="immediate",
        after_step_ids=[item.step_id for item in plan.steps],
    )
    request = SocialCognitionRequest(
        request_id=(
            "sc:terminal-resource:"
            + hashlib.sha256(
                f"{plan.plan_id}:{','.join(evidence_refs)}".encode("utf-8")
            ).hexdigest()[:96]
        ),
        trigger="evidence",
        source_refs=list(evidence_refs),
        language=language,
        source_turn=source_turn,
        goal_ids=list(goal_ids),
        evidence_refs=list(evidence_refs),
        communication_needs=[need],
        context={
            "interaction_context": interaction_context,
            "work_result": {
                "status": "completed",
                "result_kind": "resource_delivery_handover",
                "evidence_refs": list(evidence_refs),
            },
        },
    )
    generation = int(host.playback_delivery.playback_generation)
    resolved = await host.cognitive_runtime.resolve_social_interaction(
        await host.get_http_session(),
        request=request,
        session_id=str(session_id or "terminal-resource-delivery"),
        snapshot_is_current=lambda: not host._outcome_response_is_stale(
            generation=generation, session_id=session_id
        ),
        primary_plan=plan,
    )
    if resolved is None:
        return None
    _resolution, response = resolved
    return response


async def requested_result_evidence_social_response(
    host: Any,
    *,
    source_response: InteractionResponse,
    plan: CanonicalPlan,
    session_id: str | None,
    language: str,
    user_request: str,
    evidence: list[ToolResultEvidence],
    goal_ids: list[str],
    extra_context: dict[str, Any],
) -> InteractionResponse | None:
    """Give SC terminal Evidence for a result the person asked to be told.

    Every communication with the user goes through Social Cognition. When Activation or
    the Planner chose no next Work for terminal Evidence whose Goal carries an
    ``information`` Responsibility, SC still receives that Evidence directly
    with one Runtime result Need and decides how to communicate it (speech,
    gesture, gaze). The Planner path already invokes SC itself, so this runs
    only when that path produced nothing.
    """

    if not evidence or not goal_ids:
        return None
    result_goal_ids: list[str] = []
    responsibilities: dict[str, CognitiveResponsibilityProposal] = {}
    for goal_id in goal_ids:
        goal_responsibilities = [
            item
            for item in planner_reentry_responsibilities(
                source_response=source_response, goal_ids=[goal_id],
            )
            if item.output_mode == "information"
        ]
        if goal_responsibilities:
            result_goal_ids.append(goal_id)
            for item in goal_responsibilities:
                responsibilities.setdefault(item.local_ref, item)
    if not result_goal_ids:
        return None
    evidence_refs = [item.evidence_id for item in evidence]
    turn_envelope = (
        source_response.metadata.get("user_turn_envelope")
        if isinstance(source_response.metadata, dict)
        else None
    )
    normalized_input = (
        turn_envelope.get("normalized_input")
        if isinstance(turn_envelope, dict)
        else None
    )
    turn_id = str(
        (turn_envelope or {}).get("turn_id")
        or source_response.metadata.get("turn_id")
        or session_id
        or "terminal-requested-result"
    )
    source_turn = {
        "turn_id": turn_id,
        "original_text": (
            str(normalized_input.get("text") or "").strip()
            if isinstance(normalized_input, dict)
            else user_request
        ),
    }
    interaction_ledger = getattr(host.cognitive_runtime, "interaction_ledger", None)
    interaction_context = (
        interaction_ledger.context(
            session_id, goal_ids=result_goal_ids, turn_id=turn_id
        ).model_dump(mode="json")
        if interaction_ledger is not None
        else {
            "events": [],
            "already_spoken": [],
            "pending_speech": [],
            "prior_delivered_speech": [],
        }
    )
    status = aggregate_execution_status([item.status for item in evidence])
    need = SocialCommunicationNeed(
        need_id=communication_need_id(plan.plan_id, "requested_result_evidence"),
        owner="runtime",
        kind="result",
        source_goal_ids=result_goal_ids,
        source_responsibility_refs=list(responsibilities),
        reference_id=plan.plan_id,
        facts={
            "status": status,
            "result_kind": "requested_information",
            "required_result_update": True,
        },
        delivery_phase="immediate",
        after_step_ids=[item.step_id for item in plan.steps],
    )
    request = SocialCognitionRequest(
        request_id=(
            "sc:terminal-result:"
            + hashlib.sha256(
                f"{plan.plan_id}:{','.join(evidence_refs)}".encode("utf-8")
            ).hexdigest()[:96]
        ),
        trigger="evidence",
        source_refs=list(evidence_refs),
        language=language,
        responsibilities=list(responsibilities.values()),
        source_turn=source_turn,
        goal_ids=list(result_goal_ids),
        evidence_refs=list(evidence_refs),
        communication_needs=[need],
        context={
            "interaction_context": interaction_context,
            "trusted_terminal_evidence": [
                item.model_dump(mode="json") for item in evidence
            ],
            **{
                key: extra_context[key]
                for key in ("trusted_execution_outcome", "goal_statuses")
                if key in extra_context
            },
            "work_result": {
                "status": status,
                "result_kind": "requested_information",
                "evidence_refs": list(evidence_refs),
            },
        },
    )
    host.session_log(
        session_id,
        "terminal_evidence_social_cognition: goals=%s evidence=%s reason=no_planner_communication",
        ",".join(result_goal_ids),
        len(evidence_refs),
    )
    generation = int(host.playback_delivery.playback_generation)
    resolved = await host.cognitive_runtime.resolve_social_interaction(
        await host.get_http_session(),
        request=request,
        session_id=str(session_id or "terminal-requested-result"),
        snapshot_is_current=lambda: not host._outcome_response_is_stale(
            generation=generation, session_id=session_id
        ),
        primary_plan=plan,
    )
    if resolved is None:
        return None
    _resolution, response = resolved
    return response


async def plan_evidence_bound_capability_result_response(
    host: Any,
    *,
    source_response: InteractionResponse,
    bundle: Any,
    plan: Any,
    session_id: str | None,
) -> InteractionResponse | None:
    """Reactivate the Planner from bounded terminal Evidence.

    Complete observations stay in the immutable ExecutionOutcomeBundle. The
    Host preserves exact Goal/Plan/request binding, the Planner selects the
    still-needed Communicative Activity, and Runtime validates its evidence
    provenance before delivery.
    """

    metadata = source_response.metadata if isinstance(source_response.metadata, dict) else {}
    envelope = metadata.get("user_turn_envelope")
    normalized_input = (
        envelope.get("normalized_input")
        if isinstance(envelope, dict)
        else None
    )
    language = str(
        metadata.get("language")
        or (normalized_input.get("language") if isinstance(normalized_input, dict) else "")
        or "en-US"
    )

    delivered_incremental_evidence = {
        str(item).strip()
        for item in metadata.get(
            "incremental_result_delivery_evidence_ids",
            [],
        )
        if str(item).strip()
    }
    planner_handled_incremental_evidence = {
        str(item).strip()
        for item in metadata.get(
            "incremental_planner_reentry_evidence_ids",
            [],
        )
        if str(item).strip()
    }
    evidence: list[ToolResultEvidence] = []
    selected_execution_evidence: list[ExecutionEvidence] = []
    for item in bundle.evidence:
        if item.evidence_id in delivered_incremental_evidence:
            continue
        if item.evidence_id in planner_handled_incremental_evidence:
            continue
        if item.reason_code == "value_judgment_declined":
            # Declined by Value Judgment and already communicated; never re-planned.
            continue
        observation = item.observation
        observation_data = (
            dict(observation.data)
            if observation is not None
            and observation.status == "available"
            and observation.schema_validated
            else {}
        )
        evidence.append(
            ToolResultEvidence(
                evidence_id=item.evidence_id,
                tool_id=item.capability_id,
                status=item.status,
                data=observation_data,
                output_sha256=canonical_value_sha256(observation_data),
            )
        )
        selected_execution_evidence.append(item)
    if not evidence:
        return None

    user_request = (
        str(normalized_input.get("text") or "").strip()
        if isinstance(normalized_input, dict)
        else ""
    )
    if not user_request:
        return None
    plan_goal_ids = set(plan.executable_goal_ids())
    goal_ids = list(
        dict.fromkeys(
            goal_id
            for item in selected_execution_evidence
            for goal_id in item.source_goal_ids
            if goal_id in plan_goal_ids
        )
    )
    if not goal_ids:
        return None
    try:
        evidence_refs = [item.evidence_id for item in evidence]
        selected_evidence_ids = set(evidence_refs)
        selected_goal_ids = set(goal_ids)
        projected_bundle = bundle.model_dump(mode="json", exclude_none=True)
        projected_bundle["canonical_goal_ids"] = goal_ids
        projected_bundle["non_execution_goal_ids"] = []
        projected_bundle["evidence"] = [
            item
            for item in projected_bundle.get("evidence") or []
            if isinstance(item, dict)
            and str(item.get("evidence_id") or "") in selected_evidence_ids
        ]
        projected_bundle["goal_outcomes"] = [
            item
            for item in projected_bundle.get("goal_outcomes") or []
            if isinstance(item, dict)
            and str(item.get("goal_id") or "") in selected_goal_ids
        ]
        projected_bundle["aggregate_status"] = aggregate_execution_status(
            [item.status for item in selected_execution_evidence]
        )
        projected_truth = planner_execution_outcome_truth(bundle)
        projected_truth["aggregate_status"] = projected_bundle["aggregate_status"]
        projected_truth["goal_outcomes"] = [
            item
            for item in projected_truth.get("goal_outcomes") or []
            if str(item.get("goal_id") or "") in selected_goal_ids
        ]
        projected_truth["evidence"] = [
            item
            for item in projected_truth.get("evidence") or []
            if str(item.get("evidence_id") or "") in selected_evidence_ids
        ]
        extra_context = {
            "execution_outcome_bundle": projected_bundle,
            "trusted_execution_outcome": projected_truth,
            "aggregate_status": projected_bundle["aggregate_status"],
            "goal_statuses": [
                {
                    "goal_id": item.goal_id,
                    "status": item.status,
                    "completion_qualification": (
                        goal_completion_qualification_summary(bundle, item)
                    ),
                }
                for item in bundle.goal_outcomes
                if item.goal_id in selected_goal_ids
            ],
        }
        planner_response = await host._planner_state_reentry_response(
            source_response=source_response,
            canonical_plan=plan,
            user_request=user_request,
            language=language,
            goal_ids=goal_ids,
            evidence_goal_ids=goal_ids,
            evidence_refs=evidence_refs,
            session_id=session_id,
            phase="post_execution",
            context_updates={
                "trusted_terminal_evidence": [
                    item.model_dump(mode="json") for item in evidence
                ],
                "result_evidence_refs": evidence_refs,
                "result_evidence_reentry": {
                    "phase": "post_execution",
                    "source_goal_ids": goal_ids,
                    "evidence_refs": evidence_refs,
                    "planner_authority": "planner",
                },
                **extra_context,
            },
            fast_workflow_stage="fast_planner_evidence_reentry",
            response_source="fast_planner_evidence_reentry",
            repeat_check_evidence=evidence,
            repeat_check_context=extra_context,
        )
        if planner_response is not None:
            # resolve_plan_interaction already gave SC this exact Evidence
            # (trigger=evidence): one SC communication, never a second one.
            return planner_response
        resource_response = await optional_completed_resource_social_response(
            host,
            source_response=source_response,
            bundle=bundle,
            plan=plan,
            session_id=session_id,
            language=language,
            user_request=user_request,
            evidence_refs=evidence_refs,
            goal_ids=goal_ids,
            selected_execution_evidence=selected_execution_evidence,
        )
        if resource_response is not None:
            return resource_response
        # Activation/Planner chose no next Work. Terminal Evidence still reaches
        # SC directly, so a result the person asked for is never dropped.
        return await requested_result_evidence_social_response(
            host,
            source_response=source_response,
            plan=plan,
            session_id=session_id,
            language=language,
            user_request=user_request,
            evidence=evidence,
            goal_ids=goal_ids,
            extra_context=extra_context,
        )
    except Exception as exc:
        host.session_log(
            session_id,
            "planner_evidence_reentry_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        # Whatever failed after this Work, say so with the operational notice instead
        # of ending silently (live 2026-10-12: three failed re-entries left the person
        # with only "Got it."; owner 2026-10-15: any error gets at least one notice,
        # after a Host contract error left a completed weather read unanswered).
        stage_failure = isinstance(exc, CognitiveStageFailure)
        return host._cognitive_core_exception_safe_response(
            user_request,
            context={"user_turn_envelope": envelope},
            failure_stage=exc.stage if stage_failure else "fast_planner_evidence_reentry",
            failure_class=(
                str(exc.failure_metadata.get("failure_class") or "")
                if stage_failure else type(exc).__name__
            ),
            failure_error=str(exc),
        )
