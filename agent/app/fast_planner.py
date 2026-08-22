from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .prompt_projection import bounded_json
from .planner_model_contract import (
    PlannerDTOContractError,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
    is_planner_step_capability,
    materialize_planner_output,
    stable_plan_id,
)
from .planner_schema import (
    canonical_goal_binding_argument_response_schema,
    canonical_resource_argument_response_schema,
    canonical_plan_response_schema,
    fast_multi_goal_response_schema,
    fast_truth_certificate_response_schema,
    fast_first_response_response_schema,
    fast_advance_revision_response_schema,
    fast_advance_response_schema,
    fast_repair_response_schema,
)
from .planner_context import (
    canonical_goal_grounding,
    expected_goal_ids,
    fast_capability_payload,
    gateway_speech_act,
    goal_cancellation_evidence_reentry_goal_ids,
    planner_goal_execution_requirements,
    planner_response_goal_ids,
    result_evidence_reentry_goal_ids,
)
from .planner_validation import (
    AuthoritativeGroundingValidationError,
    CapabilityArgumentValidationError,
    capability_argument_errors,
    coordinated_action_goal_ids,
    normalize_detached_parameter_resolutions,
    normalize_missing_numeric_parameter_provenance,
    normalize_schema_default_parameter_provenance,
    planner_validation_error_json,
    qualify_fast_canonical_plan,
    restore_required_capability_args_from_responsibilities,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_fast_advance_output,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
    validate_work_reuse_selection,
)
from .planner_fallback import (
    materialize_fast_advance_fail_safe,
    materialize_fast_escalation,
)
from .planner_audit import review_coordinated_action_plan_coverage
try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.llm_diagnostics import cognition_text_reference
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from chromie_contracts.interaction import (
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
        FastPlannerFirstResponseTruthCertificate,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.interaction import (
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
        FastPlannerFirstResponseTruthCertificate,
    )

from .planner_prompt import (
    fast_first_response_truth_system_prompt,
    fast_first_response_truth_prompt,
    fast_first_response_system_prompt,
    fast_first_response_prompt,
    fast_advance_layered_prompt,
    fast_advance_system_prompt,
    fast_layered_prompt,
    fast_system_prompt,
    fast_repair_system_prompt,
)


logger = logging.getLogger("chromie.agent.fast_planner")










class FastPlannerResolver:
    """Low-latency semantic planner over the executable common catalog only."""

    TRACE_MODULE = TraceModule(
        name="agent.fast_planner",
        component_type="planner",
        implementation="FastPlannerResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        catalog: CapabilityCatalog,
        *,
        first_response_ollama: OllamaClient | None = None,
        first_response_num_ctx: int | None = None,
        truth_ollama: OllamaClient | None = None,
        truth_num_ctx: int | None = None,
        min_confidence: float = 0.8,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        max_capabilities: int = 24,
        max_contract_repairs: int = 1,
    ) -> None:
        self.ollama = ollama
        # Fast Planner remains the sole semantic owner of both phases.  The
        # Separately qualified clients may specialize the latency-critical
        # natural-language Activity and its bounded accept/reject qualification;
        # complete Capability planning stays on ``ollama``. When configured roles
        # share a model, main reuses the exact client so bounded calls do not force
        # an avoidable runner reload.
        self.first_response_ollama = first_response_ollama or ollama
        self.first_response_num_ctx = max(
            2048,
            int(
                first_response_num_ctx
                if first_response_num_ctx is not None
                else min(num_ctx, 6144)
            ),
        )
        self.truth_ollama = truth_ollama or ollama
        self.truth_num_ctx = max(
            2048,
            int(
                truth_num_ctx
                if truth_num_ctx is not None
                else (
                    num_ctx
                    if self.truth_ollama is self.ollama
                    else self.first_response_num_ctx
                    if self.truth_ollama is self.first_response_ollama
                    else min(num_ctx, 6144)
                )
            ),
        )
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.max_capabilities = max(1, min(64, int(max_capabilities)))
        self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))

    async def resolve_first_response(
        self, request: CognitiveWorkRequest
    ) -> FastPlannerFirstResponse:
        """Author the earliest useful speech while Fast HOW planning continues.

        This is deliberately a latency phase of Fast Planner. It neither selects a
        Capability nor resolves an execution-input gap, and it never creates a
        second response-authoring owner.
        """

        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(
                item.model_dump(mode="json")
            )
            for item in request.responsibilities
        ]
        responsibility_refs = [item.local_ref for item in responsibilities]
        needs_work = any(
            item.completion_requires_work
            or item.completion_requires_fresh_evidence
            for item in responsibilities
        )
        needs_fresh_evidence = any(
            item.completion_requires_fresh_evidence
            for item in responsibilities
        )
        requested_output_modes = {
            item.output_mode for item in responsibilities
        }
        effect_output_modes = {
            "body_action",
            "media_playback",
            "styled_speech",
            "recitation",
            "singing",
            "humming",
            "nonverbal_vocalization",
        }
        required_progress_kind = (
            "check_information"
            if needs_fresh_evidence
            else (
                "perform_action"
                if requested_output_modes
                and requested_output_modes.issubset(effect_output_modes)
                else None
            )
        )
        response_schema = fast_first_response_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            needs_work=needs_work,
            needs_fresh_evidence=needs_fresh_evidence,
            required_progress_kind=required_progress_kind,
            language=str(request.language or ""),
        )
        try:
            raw = await self.first_response_ollama.generate(
                fast_first_response_prompt(
                    request,
                    responsibilities=responsibilities,
                    needs_work=needs_work,
                ),
                system=fast_first_response_system_prompt(),
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    # The bootstrap topology chooses this context explicitly:
                    # reuse the Fast runner when models match, otherwise keep the
                    # latency-critical response phase bounded rather than inheriting
                    # a deliberate role's context window.
                    "num_ctx": self.first_response_num_ctx,
                    "num_predict": min(self.num_predict, 192),
                },
                response_format=response_schema,
                prompt_family="fast_planner.first_response",
                turn_id=request.sid,
                attempt=1,
            )
            if needs_work and isinstance(raw, dict):
                raw_activity = raw.get("activity")
                if isinstance(raw_activity, dict):
                    activity_payload = dict(raw_activity)
                    if len(responsibility_refs) == 1:
                        # There is no semantic association choice in the single-
                        # Responsibility case.  Keep that mechanical provenance out
                        # of the latency-critical model DTO and restore it before the
                        # authoritative Activity contract is validated.
                        activity_payload.setdefault(
                            "source_responsibility_refs", responsibility_refs
                        )
                    activity_payload.setdefault("role", "progress")
                    activity_payload.setdefault(
                        "activity_id",
                        "progress_"
                        + hashlib.sha256(
                            (
                                str(request.sid or "turn")
                                + "|"
                                + "|".join(responsibility_refs)
                            ).encode("utf-8")
                        ).hexdigest()[:12],
                    )
                    raw = {**raw, "activity": activity_payload}
            output = FastPlannerFirstResponseModelOutput.model_validate(raw)
            activity = output.activity
            refs = set(activity.source_responsibility_refs)
            if not refs or not refs.issubset(set(responsibility_refs)):
                raise PlannerDTOContractError(
                    "Fast first response must cite supplied Responsibility refs"
                )
            if needs_work and activity.role != "progress":
                raise PlannerDTOContractError(
                    "unfinished work requires a prospective progress response"
                )
            if not needs_work and activity.role != "complete_response":
                raise PlannerDTOContractError(
                    "immediate conversational work requires a complete response"
                )
            speech_act = gateway_speech_act(request)
            deterministic_greeting = bool(
                not needs_work
                and speech_act == "greeting"
                and activity.role == "complete_response"
                and activity.truth_stage == "context_grounded"
                and not activity.evidence_refs
            )
            if deterministic_greeting:
                # Gateway has already classified this admitted turn as a greeting,
                # and GI says the single communicative outcome requires neither
                # Work nor fresh Evidence. A second LLM cannot add authoritative
                # truth here; it only lengthens the human-facing critical path.
                # Keep the same immutable Activity acceptance surface, but let
                # trusted contract evidence close the qualification locally.
                truth_certificate = FastPlannerFirstResponseTruthCertificate(
                    decision="accept"
                )
                qualification_metadata = {
                    "truth_qualification_owner": "trusted_gateway_greeting_contract",
                    "truth_qualification_call_count": 0,
                    "truth_qualification": truth_certificate.model_dump(
                        mode="json",
                        exclude_none=True,
                        exclude_defaults=True,
                    ),
                }
            else:
                truth_certificate = await self._qualify_first_response_truth(
                    request,
                    activity=activity,
                    responsibilities=responsibilities,
                )
                qualification_metadata = {
                    "truth_qualification_owner": "fast_planner",
                    "truth_qualification_call_count": 1,
                    "truth_qualification": truth_certificate.model_dump(
                        mode="json",
                        exclude_none=True,
                        exclude_defaults=True,
                    ),
                }
            if truth_certificate.decision != "accept":
                logger.warning(
                    "fast_planner_first_response_truth_rejected sid=%s activity_id=%s",
                    request.sid,
                    activity.activity_id,
                )
                return FastPlannerFirstResponse(
                    turn_id=str(request.sid or "turn-fast-first-response"),
                    activity=None,
                    metadata={
                        "semantic_authority": "fast_planner_truth_rejection",
                        "phase": "first_communicative_activity",
                        "execution_authority": "none",
                        **qualification_metadata,
                    },
                )
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=activity,
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "first_communicative_activity",
                    "execution_authority": "host_communicative_runtime",
                    **qualification_metadata,
                },
            )
        except Exception as exc:
            failure = (
                llm_failure_metadata(exc)
                if isinstance(exc, OllamaGenerationError)
                else {
                    "failure_class": "fast_first_response_contract_invalid",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "not_evaluated",
                    "retryable": True,
                }
            )
            logger.warning(
                "fast_planner_first_response_fail_safe sid=%s error_type=%s "
                "error=%s failure_class=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
            )
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=None,
                metadata={
                    "semantic_authority": "deterministic_fail_safe",
                    "phase": "first_communicative_activity",
                    "execution_authority": "none",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    **failure,
                },
            )


    async def _qualify_first_response_truth(
        self,
        request: CognitiveWorkRequest,
        *,
        activity: Any,
        responsibilities: list[CognitiveResponsibilityProposal],
    ) -> FastPlannerFirstResponseTruthCertificate:
        """Accept or reject immutable wording without authoring a replacement.

        This is Fast Planner's LLM Epistemic Qualification for responses whose
        truth cannot be closed by an immutable Gateway/GI contract. A failure,
        malformed certificate, or uncertain acceptance is
        terminal for the first-response Activity and is never repaired.
        """

        schema = fast_truth_certificate_response_schema()
        context = request.context if isinstance(request.context, dict) else {}
        raw = await self.truth_ollama.generate(
            fast_first_response_truth_prompt(
                request,
                activity=activity,
                responsibilities=responsibilities,
                trusted_evidence=context.get("trusted_terminal_evidence") or [],
            ),
            system=fast_first_response_truth_system_prompt(),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.truth_num_ctx,
                "num_predict": min(self.num_predict, 128),
            },
            response_format=schema,
            prompt_family="fast_planner.first_response.truth_check",
            turn_id=request.sid,
            attempt=1,
        )
        certificate = FastPlannerFirstResponseTruthCertificate.model_validate(raw)
        return certificate

    async def _qualify_evidence_response_truth(
        self,
        request: CognitiveWorkRequest,
        *,
        plan: CanonicalPlan,
    ) -> FastPlannerFirstResponseTruthCertificate:
        """Accept or reject immutable post-Evidence wording without repairing it."""

        schema = fast_truth_certificate_response_schema()
        context = request.context if isinstance(request.context, dict) else {}
        contract = (
            "Fast Planner post-Evidence Epistemic Qualification contract: inspect every "
            "candidate response string against only the admitted trusted terminal "
            "Evidence and authoritative Goal scope. Return decision=accept only when "
            "every material claim preserves the Evidence values, scope, and epistemic "
            "strength. Preserve uncertainty and qualification exactly: probabilistic, "
            "forecast, estimated, bounded, partial, conditional, or otherwise qualified "
            "Evidence must remain qualified. Reject wording that strengthens probability, "
            "confidence, causal implication, temporal scope, or certainty beyond the "
            "admitted Evidence. Reject unsupported duration, "
            "severity, advice, reassurance, or facts from another period. Do not "
            "rewrite the response, choose a Capability, or add an explanation. "
            "Classify whether the response has an unsupported material claim or a "
            "semantic-perspective contradiction, then return only decision=accept "
            "when neither is present. Otherwise return decision=reject."
        )
        candidate = {
            "response_text": plan.response_text,
            "goal_outcome_response_texts": [
                {
                    "goal_id": outcome.goal_id,
                    "response_text": outcome.response_text,
                }
                for outcome in plan.goal_outcomes
                if getattr(outcome, "response_text", "")
            ],
        }
        rendered = (
            contract
            + "\n\nImmutable candidate response JSON:\n"
            + json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n\nAdmitted trusted terminal Evidence JSON:\n"
            + bounded_json(context.get("trusted_terminal_evidence") or [], 6000)
            + "\n\nAuthoritative canonical Goal JSON:\n"
            + bounded_json(canonical_goal_grounding(context), 3000)
            + "\n\nCurrent user turn (scope only):\n"
            + str(request.original_user_text or "")[:700]
        )
        raw = await self.truth_ollama.generate(
            LayeredPrompt.promote(rendered, operating_contract=(contract,)),
            system=(
                "You are the same Fast Planner's bounded post-Evidence Epistemic "
                "Qualification, not a response author. Accept or reject the immutable "
                "candidate. Never repair, replace, or expand it."
            ),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.truth_num_ctx,
                "num_predict": min(self.num_predict, 64),
            },
            response_format=schema,
            prompt_family="fast_planner.evidence_response.truth_check",
            turn_id=request.sid,
            attempt=1,
        )
        return FastPlannerFirstResponseTruthCertificate.model_validate(raw)



    async def resolve_advance(self, request: CognitiveWorkRequest) -> FastPlannerAdvance:
        """Produce Fast Planner's first Activity Plan from GI Responsibilities."""

        context = request.context if isinstance(request.context, dict) else {}
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(item.model_dump(mode="json"))
            for item in request.responsibilities
        ]
        committed_communicative_activities: list[Any] = []
        first_response_decided = False
        raw_first_response = context.get("fast_planner_first_response")
        if isinstance(raw_first_response, dict):
            try:
                first_response = FastPlannerFirstResponse.model_validate(
                    raw_first_response
                )
            except ValidationError:
                first_response = None
            if first_response is not None:
                first_response_decided = True
                if first_response.activity is not None:
                    committed_communicative_activities.append(first_response.activity)

        # A fully qualified immediate conversational response already covers a
        # Responsibility that GI says needs no downstream work.  Returning here
        # keeps unrelated body/tool choices out of a second model decision; before
        # this boundary, greetings and human feelings could acquire decorative
        # stand/stop Activities despite requesting no physical effect.
        if (
            responsibilities
            and all(
                not item.completion_requires_work
                and not item.completion_requires_fresh_evidence
                for item in responsibilities
            )
            and len(committed_communicative_activities) == 1
            and committed_communicative_activities[0].role == "complete_response"
        ):
            return FastPlannerAdvance(
                turn_id=str(request.sid or "turn-fast-advance"),
                disposition="respond",
                coverage="complete",
                covered_responsibility_refs=[
                    item.local_ref for item in responsibilities
                ],
                activities=committed_communicative_activities,
                continuations=[],
                confidence=min(item.confidence for item in responsibilities),
                unresolved=[],
                reason_summary="Immediate conversational response is complete.",
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "responsibility_activity_planning",
                    "execution_authority": "host_communicative_runtime",
                    "immediate_conversation_terminal": True,
                },
            )

        responsibility_refs = [item.local_ref for item in responsibilities]
        capabilities = await self.catalog.prompt_entries(scope="common", refresh=False)
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_capability(item.capability_id)
        ]
        capability_payload = [
            fast_capability_payload(item, include_side_effect_free=True)
            for item in executable[: self.max_capabilities]
        ]
        response_schema = fast_advance_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            capabilities=capability_payload,
            interpretation_unresolved=list(request.interpretation_unresolved),
            # A null first-response result is still a terminal decision for that
            # bounded speech phase.  Advance must not author a substitute progress
            # sentence and thereby bypass its one truth qualification.
            committed_communicative=first_response_decided,
            suppress_new_communicative=(
                first_response_decided
                and not committed_communicative_activities
            ),
        )
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": min(self.num_predict, 2048),
        }
        previous_errors = ""
        last_raw: Any = None
        revision_source: Any = None
        for attempt in range(self.max_contract_repairs + 1):
            try:
                active_response_schema = (
                    fast_advance_revision_response_schema(
                        response_schema,
                        revision_source,
                        committed_communicative=first_response_decided,
                        capabilities=capability_payload,
                        responsibilities=responsibilities,
                    )
                    if attempt
                    else response_schema
                )
                last_raw = await self.ollama.generate(
                    fast_advance_layered_prompt(
                        request,
                        responsibilities=responsibilities,
                        capabilities=capability_payload,
                        committed_communicative_activities=(
                            committed_communicative_activities
                        ),
                        first_response_decided=first_response_decided,
                        validation_errors=previous_errors,
                    ),
                    system=fast_advance_system_prompt(),
                    options=options,
                    response_format=active_response_schema,
                    prompt_family=(
                        "fast_planner.advance.revision"
                        if attempt
                        else "fast_planner.advance"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(last_raw, dict):
                    raise PlannerDTOContractError(
                        "Fast Planner advance response is not a JSON object"
                    )
                last_raw, authoritative_arg_repairs = (
                    restore_required_capability_args_from_responsibilities(
                        last_raw,
                        responsibilities=responsibilities,
                        capabilities=capability_payload,
                    )
                )
                if authoritative_arg_repairs:
                    logger.info(
                        "fast_planner_advance_authoritative_args_restored sid=%s repairs=%s",
                        request.sid,
                        bounded_json(authoritative_arg_repairs, 2000),
                    )
                output = FastPlannerAdvanceModelOutput.model_validate(last_raw)
                if first_response_decided and any(
                    activity.role == "progress" for activity in output.activities
                ):
                    raise PlannerDTOContractError(
                        "Fast Planner advance cannot replace a completed first-response "
                        "accept/reject decision with another progress Activity"
                    )
                combined_output = output.model_copy(
                    update={
                        "activities": [
                            *committed_communicative_activities,
                            *output.activities,
                        ]
                    }
                )
                validate_fast_advance_output(
                    combined_output,
                    request=request,
                    responsibilities=responsibilities,
                    capabilities=capability_payload,
                )
                return FastPlannerAdvance(
                    turn_id=str(request.sid or "turn-fast-advance"),
                    disposition=combined_output.disposition,
                    coverage=combined_output.coverage,
                    covered_responsibility_refs=(
                        combined_output.covered_responsibility_refs
                    ),
                    activities=combined_output.activities,
                    continuations=combined_output.continuations,
                    confidence=combined_output.confidence,
                    unresolved=combined_output.unresolved,
                    reason_summary=combined_output.reason_summary,
                    metadata={
                        "semantic_authority": "fast_planner_model",
                        "phase": "responsibility_activity_planning",
                        "execution_authority": "trusted_capability_runtime",
                        "contract_revision_attempted": bool(attempt),
                        **(
                            {"authoritative_arg_repairs": authoritative_arg_repairs}
                            if authoritative_arg_repairs
                            else {}
                        ),
                    },
                )
            except Exception as exc:
                if attempt < self.max_contract_repairs and isinstance(
                    exc,
                    (ValidationError, json.JSONDecodeError),
                ):
                    revision_source = last_raw
                    previous_errors = planner_validation_error_json(
                        exc,
                        raw=last_raw,
                        planner_tier="fast",
                        expected_goal_ids_for_turn=responsibility_refs,
                    )
                    continue
                return materialize_fast_advance_fail_safe(
                    request,
                    responsibility_refs=responsibility_refs,
                    error=exc,
                    raw_output=last_raw,
                    committed_communicative_activities=(
                        committed_communicative_activities
                    ),
                    allow_progress_salvage=not first_response_decided,
                )
        raise AssertionError("unreachable")





    async def resolve(self, request: CognitiveWorkRequest) -> CanonicalPlan:
        trace_scope = runtime_tracer.continue_from_context(request.context)
        if not trace_scope.enabled:
            return await self._resolve(request)
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    attributes={
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                        "max_capabilities": self.max_capabilities,
                    },
                ) as span:
                    result = await self._resolve(request)
                    span.set_attribute("disposition", result.disposition)
                    span.set_attribute("coverage", result.coverage)
                    span.set_attribute("step_count", len(result.steps))
                    span.set_attribute("goal_count", len(result.goal_ids))
                    path = str(result.metadata.get("path_classification") or "")
                    if path:
                        span.set_attribute("path_classification", path)
                    if result.metadata.get("failure_class"):
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: CognitiveWorkRequest) -> CanonicalPlan:
        plan_id = stable_plan_id(request, "fast")
        context = request.context if isinstance(request.context, dict) else {}
        expected_goal_ids_for_turn = expected_goal_ids(context)
        authoritative_goals = canonical_goal_grounding(context)
        cancellation_reentry_goal_ids = (
            goal_cancellation_evidence_reentry_goal_ids(context)
        )
        response_goal_ids = sorted(
            planner_response_goal_ids(authoritative_goals)
            | cancellation_reentry_goal_ids
        )
        response_only, requires_execution = planner_goal_execution_requirements(
            authoritative_goals
        )
        reentry_goal_ids = result_evidence_reentry_goal_ids(context)
        if cancellation_reentry_goal_ids:
            capability_goal_ids = {
                str(goal.get("goal_id") or "").strip()
                for goal in authoritative_goals
                if isinstance(goal, dict)
                and isinstance(goal.get("metadata"), dict)
                and str(goal["metadata"].get("responsibility_kind") or "").strip()
                == "capability_dependent"
            }
            requires_execution = bool(
                capability_goal_ids - cancellation_reentry_goal_ids
            )
            if cancellation_reentry_goal_ids == set(expected_goal_ids_for_turn):
                response_only = True
        if reentry_goal_ids == set(expected_goal_ids_for_turn):
            # Terminal Evidence satisfies the just-completed provider prerequisite,
            # but it does not force a response-only callback.  Planner must see the
            # executable catalog so the new trusted state can legitimately yield a
            # response, genuinely new follow-up Work, clarification/waiting, or no
            # new Activity.  The just-completed Activity is rejected separately by
            # the Host re-entry boundary rather than hidden by this schema.
            response_only = False
            requires_execution = False
            response_goal_ids = list(expected_goal_ids_for_turn)
        capabilities = await self.catalog.prompt_entries(scope="common", refresh=False)
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_capability(item.capability_id)
        ]
        if response_only:
            executable = []
        capability_payload = [
            fast_capability_payload(item)
            for item in executable[: self.max_capabilities]
        ]
        multi_goal_contract = len(expected_goal_ids_for_turn) > 1
        contract_schema = (
            "FastPlannerMultiGoalPlanOutput" if multi_goal_contract else "FastPlannerModelOutput"
        )
        response_schema = (
            fast_multi_goal_response_schema(
                expected_goal_ids=expected_goal_ids_for_turn,
                allowed_capability_ids=[item["capability_id"] for item in capability_payload],
                capability_input_schemas={
                    item["capability_id"]: item["input_schema"]
                    for item in capability_payload
                },
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
            )
            if multi_goal_contract
            else canonical_plan_response_schema(
                planner_tier="fast",
                expected_goal_ids=expected_goal_ids_for_turn,
                allowed_capability_ids=[item["capability_id"] for item in capability_payload],
                capability_input_schemas={
                    item["capability_id"]: item["input_schema"]
                    for item in capability_payload
                },
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
            )
        )
        response_schema = canonical_resource_argument_response_schema(
            response_schema,
            authoritative_goals=authoritative_goals,
        )
        response_schema = canonical_goal_binding_argument_response_schema(
            response_schema,
            authoritative_goals=authoritative_goals,
        )
        if reentry_goal_ids:
            evidence_wording_description = (
                "Exact natural answer grounded only in trusted terminal Evidence for "
                "the requested Goal scope. Preserve epistemic strength: a probability "
                "below 100% remains a possibility/probability, never certainty. Do not "
                "add unsupported duration, severity, reassurance, advice, or measurements "
                "from another current/day/period scope."
            )
            top_response = response_schema.get("properties", {}).get(
                "response_text"
            )
            if isinstance(top_response, dict):
                top_response["description"] = evidence_wording_description
                top_response["maxLength"] = 240
            for definition in response_schema.get("$defs", {}).values():
                if not isinstance(definition, dict):
                    continue
                outcome_response = definition.get("properties", {}).get(
                    "response_text"
                )
                if isinstance(outcome_response, dict):
                    outcome_response["description"] = evidence_wording_description
                    outcome_response["maxLength"] = 240
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        previous_raw: Any = None
        initial_raw_output: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False
        for attempt in range(self.max_contract_repairs + 1):
            raw: Any = None
            numeric_provenance_repairs: list[dict[str, Any]] = []
            try:
                active_response_schema = (
                    fast_repair_response_schema(
                        response_schema,
                        initial_raw_output,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    if contract_repair_attempted
                    else response_schema
                )
                raw = await self.ollama.generate(
                    fast_layered_prompt(
                        request,
                        capability_payload,
                        response_schema=response_schema,
                        previous_raw=previous_raw,
                        validation_errors=initial_validation_errors,
                    ),
                    system=(
                        fast_repair_system_prompt()
                        if contract_repair_attempted
                        else fast_system_prompt()
                    ),
                    options=options,
                    response_format=active_response_schema,
                    prompt_family=(
                        "fast_planner.repair"
                        if contract_repair_attempted
                        else "fast_planner.primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ValueError("fast planner response is not a JSON object")
                raw, detached_resolution_repairs = (
                    normalize_detached_parameter_resolutions(raw)
                )
                if detached_resolution_repairs:
                    logger.warning(
                        "fast_planner_detached_parameter_resolutions_removed "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(detached_resolution_repairs, 2000),
                    )
                raw, provenance_repairs = (
                    normalize_schema_default_parameter_provenance(
                        raw,
                        authoritative_goals=canonical_goal_grounding(
                            request.context
                        ),
                        capability_payload=capability_payload,
                    )
                )
                if provenance_repairs:
                    logger.info(
                        "fast_planner_schema_default_provenance_normalized "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(provenance_repairs, 2000),
                    )
                raw, numeric_provenance_repairs = (
                    normalize_missing_numeric_parameter_provenance(
                        raw,
                        authoritative_goals=canonical_goal_grounding(
                            request.context
                        ),
                    )
                )
                if numeric_provenance_repairs:
                    logger.info(
                        "fast_planner_numeric_provenance_normalized sid=%s repairs=%s",
                        request.sid,
                        bounded_json(numeric_provenance_repairs, 2000),
                    )
                try:
                    validated_model_output = validate_planner_model_output(
                        raw,
                        planner_tier="fast",
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    normalized = materialize_planner_output(
                        validated_model_output,
                        planner_tier="fast",
                        plan_id=plan_id,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        goal_summary_fallback=request.text,
                        fast_multi_goal_contract=multi_goal_contract,
                    )
                    plan = CanonicalPlan.model_validate(normalized)
                    validate_work_reuse_selection(
                        validated_model_output,
                        context=request.context,
                    )
                except (ValidationError, ValueError) as exc:
                    raise PlannerDTOContractError(str(exc)) from exc

                authoritative_goals = canonical_goal_grounding(request.context)
                validate_goal_responsibility_outcomes(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                    context=request.context,
                )
                validate_resource_responsibility_capability_grounding(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                    capabilities=capability_payload,
                )
                try:
                    validate_explicit_numeric_parameter_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                    )
                except ValueError as exc:
                    # A missing or internally inconsistent provenance record is
                    # a mechanically malformed Planner DTO. One same-stage repair
                    # may add or correct that record without changing Goal meaning,
                    # Capability selection, or executable arguments.
                    raise PlannerDTOContractError(str(exc)) from exc
                try:
                    validate_goal_binding_argument_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                        capabilities=capability_payload,
                    )
                    validate_user_supplied_parameter_provenance(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                    )
                except PlannerDTOContractError:
                    raise
                except ValueError as exc:
                    raise AuthoritativeGroundingValidationError(str(exc)) from exc
                validate_external_response_evidence_boundary(
                    validated_model_output,
                    context=request.context,
                )
                capability_errors = capability_argument_errors(
                    plan,
                    capability_payload,
                )
                if capability_errors:
                    raise CapabilityArgumentValidationError(capability_errors)
            except ResourceResponsibilityRequiresCompositionError as exc:
                logger.info(
                    "fast_planner_resource_composition_required sid=%s error=%s",
                    request.sid,
                    exc,
                )
                return materialize_fast_escalation(
                    plan_id,
                    request,
                    "resource_responsibility_composition_required",
                    unresolved=[str(exc)],
                    path_classification="semantic_escalation",
                    metadata={
                        "execution_allowed": False,
                        "resource_composition_required": True,
                    },
                )
            except Exception as exc:
                failure = llm_failure_metadata(exc)
                logger.warning(
                    "fast_planner_inference_failed sid=%s attempt=%s error_type=%s error=%s "
                    "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                    request.sid,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                    failure["failure_class"],
                    failure["failure_domain"],
                    failure["architecture_attribution"],
                    failure["retryable"],
                )
                if isinstance(
                    exc, ResourceResponsibilityCapabilityUnavailableError
                ):
                    return materialize_fast_escalation(
                        plan_id,
                        request,
                        "resource_responsibility_capability_unavailable",
                        unresolved=[str(exc)],
                        path_classification="semantic_escalation",
                        metadata={
                            "execution_allowed": False,
                            "resource_contract_unavailable": True,
                        },
                    )
                if attempt < self.max_contract_repairs and isinstance(
                    exc, (PlannerDTOContractError, json.JSONDecodeError)
                ):
                    contract_repair_attempted = True
                    initial_raw_output = raw
                    # Regenerate from authoritative grounding instead of asking
                    # the model to edit invalid JSON in place.  In live runs,
                    # copy-editing caused validator text to be embedded inside
                    # rationale strings while required fields stayed missing.
                    previous_raw = None
                    initial_validation_errors = planner_validation_error_json(
                        exc,
                        raw=raw,
                        planner_tier="fast",
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    logger.warning(
                        "fast_planner_contract_repair_start sid=%s validation_errors=%s "
                        "raw_output_ref=%s raw_output=%s",
                        request.sid,
                        initial_validation_errors,
                        cognition_text_reference(initial_raw_output),
                        bounded_json(initial_raw_output, 4000),
                    )
                    continue
                logger.warning(
                    "fast_planner_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s repair_raw_output_ref=%s "
                    "initial_raw_output=%s repair_raw_output=%s",
                    request.sid,
                    cognition_text_reference(initial_raw_output),
                    cognition_text_reference(raw if contract_repair_attempted else None),
                    bounded_json(initial_raw_output, 4000)
                    if initial_raw_output is not None
                    else "",
                    bounded_json(raw, 4000)
                    if contract_repair_attempted and raw is not None
                    else "",
                )
                integrity_metadata = cognitive_integrity_metadata(
                    stage="fast_planner", exc=exc, request=request
                )
                mechanical_contract_error = isinstance(
                    exc, (PlannerDTOContractError, json.JSONDecodeError)
                )
                authoritative_grounding_failure = isinstance(
                    exc, AuthoritativeGroundingValidationError
                )
                semantic_validation_failure = (
                    isinstance(exc, ValueError)
                    and not mechanical_contract_error
                    and not authoritative_grounding_failure
                )
                return materialize_fast_escalation(
                    plan_id,
                    request,
                    (
                        "fast_planner_model_contract_failed"
                        if contract_repair_attempted or mechanical_contract_error
                        else "fast_planner_authoritative_grounding_failed"
                        if authoritative_grounding_failure
                        else "fast_planner_semantic_validation_failed"
                        if semantic_validation_failure
                        else "fast_planner_unavailable"
                    ),
                    error=exc,
                    path_classification=(
                        "semantic_escalation"
                        if semantic_validation_failure
                        else "contract_failure"
                    ),
                    metadata={
                        "contract_schema": contract_schema,
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output_ref": cognition_text_reference(initial_raw_output),
                        "repair_raw_output_ref": cognition_text_reference(
                            raw if contract_repair_attempted else None
                        ),
                        "validation_feedback": (
                            exc.feedback
                            if isinstance(exc, CapabilityArgumentValidationError)
                            else []
                        ),
                        **integrity_metadata,
                    },
                )

            qualification = qualify_fast_canonical_plan(
                plan,
                capability_payload=capability_payload,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                authoritative_goals=canonical_goal_grounding(request.context),
                evidence_reentry_goal_ids=(
                    result_evidence_reentry_goal_ids(request.context)
                    | goal_cancellation_evidence_reentry_goal_ids(request.context)
                ),
                min_confidence=self.min_confidence,
            )
            if not qualification.accepted:
                return materialize_fast_escalation(
                    plan.plan_id,
                    request,
                    qualification.reason,
                    response_text=plan.response_text,
                    unresolved=list(qualification.unresolved),
                    metadata=qualification.metadata,
                    path_classification=qualification.path_classification,
                )
            validated = qualification.plan
            if (
                reentry_goal_ids
                and validated.disposition == "respond"
                and validated.response_text
            ):
                try:
                    evidence_truth = await self._qualify_evidence_response_truth(
                        request,
                        plan=validated,
                    )
                except Exception as exc:
                    logger.warning(
                        "fast_planner_evidence_response_truth_unavailable "
                        "sid=%s error_type=%s error=%s",
                        request.sid,
                        type(exc).__name__,
                        exc,
                    )
                    return materialize_fast_escalation(
                        plan_id,
                        request,
                        "fast_planner_evidence_response_truth_unavailable",
                        error=exc,
                        unresolved=[
                            "Post-Evidence wording could not be truth-qualified."
                        ],
                        path_classification="semantic_escalation",
                    )
                qualification = evidence_truth.model_dump(
                    mode="json", exclude_none=True, exclude_defaults=True
                )
                if evidence_truth.decision != "accept":
                    logger.warning(
                        "fast_planner_evidence_response_truth_rejected sid=%s",
                        request.sid,
                    )
                    return materialize_fast_escalation(
                        plan_id,
                        request,
                        "fast_planner_evidence_response_truth_rejected",
                        unresolved=[
                            "Post-Evidence wording must preserve probability below "
                            "100% as uncertainty rather than certainty."
                        ],
                        path_classification="semantic_escalation",
                        metadata={
                            "evidence_response_truth_qualification": qualification,
                            "execution_allowed": False,
                        },
                    )
                metadata = dict(validated.metadata)
                metadata["evidence_response_truth_qualification"] = qualification
                validated = validated.model_copy(update={"metadata": metadata})
            coordinated_goal_ids = coordinated_action_goal_ids(
                canonical_goal_grounding(request.context)
            )
            if (
                coordinated_goal_ids.intersection(validated.goal_ids)
                and validated.disposition in {"execute", "mixed"}
                and validated.steps
            ):
                try:
                    coverage_review = await review_coordinated_action_plan_coverage(
                        self.ollama,
                        request_text=request.text,
                        language=str(request.language or "und"),
                        authoritative_goals=canonical_goal_grounding(request.context),
                        plan=validated,
                        capabilities=capability_payload,
                        num_ctx=self.num_ctx,
                    )
                except Exception as exc:
                    logger.warning(
                        "fast_planner_coverage_review_unavailable sid=%s error_type=%s error=%s",
                        request.sid,
                        type(exc).__name__,
                        exc,
                    )
                    return materialize_fast_escalation(
                        plan_id,
                        request,
                        "coordinated_action_coverage_review_unavailable",
                        error=exc,
                        path_classification="coverage_review_failure",
                        metadata={
                            "coordinated_goal_ids": sorted(coordinated_goal_ids),
                            "execution_allowed": False,
                        },
                    )
                if coverage_review.decision != "accept":
                    logger.warning(
                        "fast_planner_coverage_review_rejected sid=%s uncovered=%s reason=%s",
                        request.sid,
                        coverage_review.uncovered_requirements,
                        coverage_review.reason,
                    )
                    return materialize_fast_escalation(
                        plan_id,
                        request,
                        "coordinated_action_coverage_incomplete",
                        unresolved=coverage_review.uncovered_requirements,
                        path_classification="semantic_escalation",
                        metadata={
                            "coordinated_goal_ids": sorted(coordinated_goal_ids),
                            "coverage_review": coverage_review.model_dump(mode="json"),
                            "execution_allowed": False,
                        },
                    )
                metadata = dict(validated.metadata)
                metadata["coverage_review"] = {
                    "status": "accepted",
                    "confidence": coverage_review.confidence,
                    "reason": coverage_review.reason,
                    "execution_authority": "none",
                }
                validated = validated.model_copy(update={"metadata": metadata})
            if contract_repair_attempted:
                metadata = dict(validated.metadata)
                metadata.update(
                    {
                        "contract_schema": contract_schema,
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": True,
                        "contract_repair_succeeded": True,
                        "contract_repair": {
                            "attempted": True,
                            "succeeded": True,
                            "strategy": "schema_constrained_model_revision",
                            "attempt_count": 1,
                        },
                    }
                )
                validated = validated.model_copy(update={"metadata": metadata})
                logger.info("fast_planner_contract_repair_done sid=%s status=success", request.sid)
            if numeric_provenance_repairs:
                metadata = dict(validated.metadata)
                metadata["numeric_provenance_normalization"] = {
                    "strategy": "copy_exact_owned_step_argument",
                    "repairs": numeric_provenance_repairs,
                    "semantic_plan_unchanged": True,
                }
                validated = validated.model_copy(update={"metadata": metadata})
            return validated
        raise AssertionError("unreachable")
