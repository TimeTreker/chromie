from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .planner_grounding import semantic_numeric_values
from .capabilities.validator import validate_args_for_schema
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
    materialize_goal_outcomes,
    materialize_planner_metadata,
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
    planner_goal_execution_requirements,
    planner_response_goal_ids,
    result_evidence_reentry_goal_ids,
)
from .planner_validation import (
    coordinated_action_goal_ids,
    normalize_detached_parameter_resolutions,
    normalize_missing_numeric_parameter_provenance,
    normalize_schema_default_parameter_provenance,
    parallel_plan_contract_errors,
    planner_contract_diagnostics,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
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
        FastPlannerProgressAct,
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
        FastPlannerProgressAct,
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






class _CapabilityArgumentValidationError(PlannerDTOContractError):
    def __init__(self, feedback: list[dict[str, Any]]) -> None:
        self.feedback = [dict(item) for item in feedback]
        super().__init__(
            json.dumps(
                self.feedback,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


class _AuthoritativeGroundingValidationError(ValueError):
    """Fast output contradicts or bypasses immutable Goal grounding.

    This is not evidence that the user problem is semantically difficult. Deep
    Planner must not be used as a repair service for a plan that tried to source
    executable arguments outside the authoritative Goal representation.
    """


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
            gateway_speech_act = self._gateway_speech_act(request)
            deterministic_greeting = bool(
                not needs_work
                and gateway_speech_act == "greeting"
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

    @staticmethod
    def _gateway_speech_act(request: CognitiveWorkRequest) -> str:
        """Return immutable Gateway speech-act evidence when the envelope carries it."""

        context = request.context if isinstance(request.context, dict) else {}
        envelope = context.get("user_turn_envelope")
        if not isinstance(envelope, dict):
            return ""
        attention = envelope.get("attention")
        if not isinstance(attention, dict):
            return ""
        return " ".join(
            str(attention.get("speech_act") or "").strip().split()
        ).casefold()

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
            + self._bounded(context.get("trusted_terminal_evidence") or [], 6000)
            + "\n\nAuthoritative canonical Goal JSON:\n"
            + self._bounded(canonical_goal_grounding(context), 3000)
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


    @staticmethod
    def _restore_required_capability_args_from_responsibilities(
        raw: dict[str, Any],
        *,
        responsibilities: list[CognitiveResponsibilityProposal],
        capabilities: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Restore omitted required args when GI already owns the exact value.

        The model still owns Capability selection. Once it selects a Capability,
        copying an identically named required input from every cited Responsibility
        is mechanical provenance preservation, not a new HOW decision. Conflicting,
        partial, transformed, optional, or defaulted inputs remain model-owned and
        fail through the normal contract boundary.
        """

        activities = raw.get("activities")
        if not isinstance(activities, list):
            return raw, []
        by_ref = {item.local_ref: item for item in responsibilities}
        by_capability = {
            str(item.get("capability_id") or ""): item
            for item in capabilities
            if isinstance(item, dict) and str(item.get("capability_id") or "")
        }
        normalized = copy.deepcopy(raw)
        normalized_activities = normalized.get("activities")
        if not isinstance(normalized_activities, list):
            return raw, []
        repairs: list[dict[str, Any]] = []
        for activity_index, activity in enumerate(normalized_activities):
            if not isinstance(activity, dict) or activity.get("role") != "capability":
                continue
            capability_id = str(activity.get("capability_id") or "")
            definition = by_capability.get(capability_id)
            if not isinstance(definition, dict):
                continue
            input_schema = definition.get("input_schema")
            if not isinstance(input_schema, dict):
                continue
            properties = input_schema.get("properties")
            if not isinstance(properties, dict):
                properties = {}
            required = [str(item) for item in input_schema.get("required") or []]
            source_refs = [
                str(item)
                for item in activity.get("source_responsibility_refs") or []
                if str(item) in by_ref
            ]
            if not source_refs:
                continue
            args = activity.get("args")
            if not isinstance(args, dict):
                args = {}
            else:
                args = dict(args)
            changed = False
            for parameter in required:
                if parameter in args:
                    continue
                parameter_schema = properties.get(parameter)
                if isinstance(parameter_schema, dict) and "default" in parameter_schema:
                    continue
                if not all(
                    parameter in by_ref[source_ref].bindings
                    for source_ref in source_refs
                ):
                    continue
                values = [
                    by_ref[source_ref].bindings[parameter]
                    for source_ref in source_refs
                ]
                first = values[0]
                if any(value != first for value in values[1:]):
                    continue
                args[parameter] = copy.deepcopy(first)
                changed = True
                repairs.append(
                    {
                        "activity_index": activity_index,
                        "activity_id": str(activity.get("activity_id") or ""),
                        "capability_id": capability_id,
                        "parameter": parameter,
                        "source_responsibility_refs": source_refs,
                        "recovery": "restored_required_arg_from_authoritative_responsibility",
                    }
                )
            if changed:
                activity["args"] = args
        return (normalized if repairs else raw), repairs

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
            {
                "capability_id": item.capability_id,
                "description": item.description,
                "input_schema": item.input_schema,
                "requires_confirmation": item.requires_confirmation,
                "can_run_parallel": item.can_run_parallel,
                "parallel_metadata_declared": item.parallel_metadata_declared,
                "exclusive_group": item.exclusive_group,
                "resource_claims": list(item.resource_claims),
                "effects": list(item.effects),
                "safety_class": item.safety_class,
                "side_effect_free": (item.hints or {}).get("side_effect_free") is True,
                "hints": dict(item.hints),
            }
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
                    self._restore_required_capability_args_from_responsibilities(
                        last_raw,
                        responsibilities=responsibilities,
                        capabilities=capability_payload,
                    )
                )
                if authoritative_arg_repairs:
                    logger.info(
                        "fast_planner_advance_authoritative_args_restored sid=%s repairs=%s",
                        request.sid,
                        self._bounded(authoritative_arg_repairs, 2000),
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
                self._validate_advance_output(
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
                    previous_errors = self._validation_error_json(
                        exc,
                        raw=last_raw,
                        expected_goal_ids_for_turn=responsibility_refs,
                    )
                    continue
                return self._advance_fail_safe(
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

    @staticmethod
    def _first_response_phase_decided(request: CognitiveWorkRequest) -> bool:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("fast_planner_first_response")
        if not isinstance(raw, dict):
            return False
        try:
            FastPlannerFirstResponse.model_validate(raw)
        except ValidationError:
            return False
        return True

    def _validate_advance_output(
        self,
        output: FastPlannerAdvanceModelOutput,
        *,
        request: CognitiveWorkRequest,
        responsibilities: list[CognitiveResponsibilityProposal],
        capabilities: list[dict[str, Any]],
    ) -> None:
        responsibility_refs = [item.local_ref for item in responsibilities]
        if set(output.covered_responsibility_refs) != set(responsibility_refs):
            raise PlannerDTOContractError(
                "Fast Planner must cover exactly the authoritative Responsibility refs"
            )
        by_ref = {item.local_ref: item for item in responsibilities}
        allowed = {item["capability_id"]: item for item in capabilities}
        unresolved_meaning = {
            " ".join(str(item or "").strip().split())
            for item in request.interpretation_unresolved
            if " ".join(str(item or "").strip().split())
        }
        clarification_activities = [
            item for item in output.activities if item.role == "clarification"
        ]
        capability_activities = [
            item for item in output.activities if item.role == "capability"
        ]
        complete_response_activities = [
            item for item in output.activities if item.role == "complete_response"
        ]
        numeric_args_by_ref: dict[str, set[Decimal]] = {
            ref: set() for ref in responsibility_refs
        }
        for activity in capability_activities:
            activity_numbers = semantic_numeric_values(activity.args)
            for source_ref in activity.source_responsibility_refs:
                if source_ref in numeric_args_by_ref:
                    numeric_args_by_ref[source_ref].update(activity_numbers)
        for source_ref, source in by_ref.items():
            required_numbers = semantic_numeric_values(source.bindings)
            missing_numbers = sorted(
                required_numbers - numeric_args_by_ref.get(source_ref, set())
            )
            if missing_numbers and any(
                source_ref in activity.source_responsibility_refs
                for activity in capability_activities
            ):
                raise PlannerDTOContractError(
                    "Fast Planner Capability args omitted explicit numeric "
                    f"Responsibility bindings for {source_ref}: "
                    + ",".join(str(value) for value in missing_numbers)
                )
        if output.disposition in {"execute", "respond", "clarify", "mixed"}:
            terminal_roles = {"capability", "complete_response", "clarification"}
            terminal_refs = {
                source_ref
                for activity in output.activities
                if activity.role in terminal_roles
                for source_ref in activity.source_responsibility_refs
            }
            missing_terminal_refs = set(responsibility_refs) - terminal_refs
            if missing_terminal_refs:
                raise PlannerDTOContractError(
                    "Fast Planner must supply one terminal Activity for every "
                    "authoritative Responsibility before claiming a terminal "
                    "disposition; missing="
                    + ",".join(sorted(missing_terminal_refs))
                )
        if all(item.completion_requires_fresh_evidence for item in responsibilities) and not (
            clarification_activities
            or complete_response_activities
            or any(item.role == "progress" for item in output.activities)
            or self._first_response_phase_decided(request)
        ):
            raise PlannerDTOContractError(
                "fresh-evidence Fast work requires a Communicative Main Activity"
            )
        if clarification_activities:
            expected_disposition = "mixed" if capability_activities else "clarify"
            if output.disposition != expected_disposition:
                raise PlannerDTOContractError(
                    "clarification disposition must be clarify when it is the only "
                    "terminal work, or mixed when independent Capability work proceeds"
                )
            if complete_response_activities and not capability_activities:
                raise PlannerDTOContractError(
                    "the current Fast contract cannot combine only response and "
                    "clarification outcomes without executable Work"
                )
        all_gap_ids = [
            gap.gap_id
            for activity in clarification_activities
            for gap in activity.information_gaps
        ]
        if len(all_gap_ids) != len(set(all_gap_ids)):
            raise PlannerDTOContractError(
                "Planner InformationGap IDs must be unique across the Activity Plan"
            )
        for activity in output.activities:
            unknown_refs = set(activity.source_responsibility_refs) - set(by_ref)
            if unknown_refs:
                raise PlannerDTOContractError(
                    "Fast Planner Activity references unknown Responsibilities: "
                    + ",".join(sorted(unknown_refs))
                )
            if activity.role == "complete_response" and any(
                by_ref[ref].completion_requires_fresh_evidence
                for ref in activity.source_responsibility_refs
            ):
                raise PlannerDTOContractError(
                    "Fast Planner cannot complete a fresh-evidence Responsibility "
                    "before trusted evidence"
                )
            if activity.role == "clarification":
                if output.disposition not in {"clarify", "mixed"}:
                    raise PlannerDTOContractError(
                        "a clarification Activity requires disposition=clarify or mixed"
                    )
                for gap in activity.information_gaps:
                    if gap.source_kind == "unresolved_meaning":
                        if gap.source_reference not in unresolved_meaning:
                            raise PlannerDTOContractError(
                                "semantic clarification must cite exact GI unresolved "
                                f"meaning: {gap.source_reference!r}"
                            )
                        continue
                    definition = allowed.get(gap.source_reference)
                    if definition is None:
                        raise PlannerDTOContractError(
                            "execution-input clarification must cite an available "
                            f"Capability ID: {gap.source_reference!r}"
                        )
                    input_schema = definition.get("input_schema") or {}
                    properties = input_schema.get("properties") or {}
                    required = set(input_schema.get("required") or [])
                    bound_names = {
                        str(name)
                        for ref in activity.source_responsibility_refs
                        for name in by_ref[ref].bindings
                    }
                    for parameter in gap.required_for:
                        parameter_schema = properties.get(parameter)
                        if parameter not in required or not isinstance(
                            parameter_schema, dict
                        ):
                            raise PlannerDTOContractError(
                                "execution-input clarification may name only required "
                                f"Capability inputs: {gap.source_reference}.{parameter}"
                            )
                        if "default" in parameter_schema:
                            raise PlannerDTOContractError(
                                "Planner cannot ask for an input with a Capability "
                                f"schema default: {gap.source_reference}.{parameter}"
                            )
                        if parameter in bound_names:
                            raise PlannerDTOContractError(
                                "Planner cannot ask for an already-bound input: "
                                f"{parameter}"
                            )
            if activity.role != "capability":
                continue
            definition = allowed.get(activity.capability_id)
            if definition is None:
                raise PlannerDTOContractError(
                    f"unknown or unavailable Capability {activity.capability_id!r}"
                )
            for source_ref in activity.source_responsibility_refs:
                source = by_ref[source_ref]
                if source.output_mode not in set(VOCAL_MODES) - {"speech"}:
                    continue
                if (
                    activity.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
                    or activity.args.get("mode") != source.output_mode
                ):
                    raise PlannerDTOContractError(
                        "Fast Planner must preserve a mode-specific vocal "
                        "Responsibility through the exact qualified vocal provider; "
                        f"source_ref={source_ref} expected_capability="
                        f"{VOCAL_PERFORMANCE_CAPABILITY_ID} expected_mode="
                        f"{source.output_mode} actual_capability="
                        f"{activity.capability_id} actual_mode="
                        f"{activity.args.get('mode')!r}. Ordinary speech, media, and "
                        "body Activities are not completion evidence for that mode."
                    )
            schema_errors = validate_args_for_schema(
                activity.args,
                definition.get("input_schema") or {},
            )
            if schema_errors:
                raise PlannerDTOContractError(
                    json.dumps(
                        {
                            "activity_id": activity.activity_id,
                            "capability_id": activity.capability_id,
                            "invalid_args": schema_errors[:8],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            input_schema = definition.get("input_schema") or {}
            properties = input_schema.get("properties") or {}
            required_inputs = set(input_schema.get("required") or [])
            authoritative_bindings = {
                str(name): value
                for ref in activity.source_responsibility_refs
                for name, value in by_ref[ref].bindings.items()
            }
            for parameter in sorted(required_inputs):
                parameter_schema = properties.get(parameter)
                if not isinstance(parameter_schema, dict):
                    continue
                if "default" in parameter_schema:
                    continue
                if parameter not in authoritative_bindings:
                    raise _AuthoritativeGroundingValidationError(
                        "Fast Planner cannot invent an unbound required Capability "
                        f"input before canonical Goal grounding: "
                        f"{activity.capability_id}.{parameter}"
                    )
                actual = activity.args.get(parameter)
                expected = authoritative_bindings[parameter]
                if actual != expected and str(actual).strip() != str(expected).strip():
                    raise _AuthoritativeGroundingValidationError(
                        "Fast Planner required Capability input contradicts GI "
                        f"binding: {activity.capability_id}.{parameter}"
                    )

    @staticmethod
    def _advance_fail_safe(
        request: CognitiveWorkRequest,
        *,
        responsibility_refs: list[str],
        error: Exception,
        raw_output: Any,
        committed_communicative_activities: list[Any] | None = None,
        allow_progress_salvage: bool = True,
    ) -> FastPlannerAdvance:
        inference_failure = isinstance(error, OllamaGenerationError)
        failure = (
            llm_failure_metadata(error)
            if inference_failure
            else {
                "failure_class": "fast_advance_contract_invalid",
                "failure_domain": "model_contract",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
            }
        )
        logger.warning(
            "fast_planner_advance_fail_safe sid=%s error_type=%s error=%s "
            "failure_class=%s raw_output_ref=%s",
            request.sid,
            type(error).__name__,
            error,
            failure["failure_class"],
            cognition_text_reference(raw_output),
        )
        progress_activities = (
            FastPlannerResolver._validated_fail_safe_progress(
                raw_output,
                responsibility_refs=responsibility_refs,
            )
            if allow_progress_salvage
            else []
        )
        retained_communicative_activities = list(
            committed_communicative_activities or []
        )
        retained_ids = {
            item.activity_id for item in retained_communicative_activities
        }
        for item in progress_activities:
            if item.activity_id in retained_ids:
                continue
            retained_communicative_activities.append(item)
            retained_ids.add(item.activity_id)
        return FastPlannerAdvance(
            turn_id=str(request.sid or "turn-fast-advance"),
            disposition="unavailable",
            coverage="uncertain",
            covered_responsibility_refs=responsibility_refs,
            activities=retained_communicative_activities,
            continuations=[],
            confidence=0.0,
            unresolved=[
                "Fast Planner Activity Plan unavailable; Responsibility preserved "
                "for one canonical Fast Planner revision after Goal Association."
            ],
            reason_summary=(
                "Discard the invalid Fast Planner output without executing it."
            ),
            metadata={
                "semantic_authority": "deterministic_fail_safe",
                "phase": "responsibility_activity_planning",
                "execution_authority": "none",
                "advance_status": "canonical_fast_revision_required",
                "raw_output_ref": cognition_text_reference(raw_output),
                "error_type": type(error).__name__,
                "error": str(error)[:300],
                "salvaged_progress_activity_ids": [
                    item.activity_id for item in retained_communicative_activities
                ],
                "progress_salvage_suppressed_by_first_response_decision": (
                    not allow_progress_salvage
                ),
                **failure,
            },
        )

    @staticmethod
    def _validated_fail_safe_progress(
        raw_output: Any,
        *,
        responsibility_refs: list[str],
    ) -> list[FastPlannerProgressAct]:
        """Retain independently valid, non-terminal progress from an invalid Plan.

        Progress carries no result, completion, Capability, or execution claim.  The
        invalid Plan wrapper and every terminal Activity remain discarded.  Exact
        duplicates are collapsed so one malformed model response cannot schedule
        repeated audible acknowledgements.
        """

        if not isinstance(raw_output, dict):
            return []
        allowed_refs = set(responsibility_refs)
        retained: list[FastPlannerProgressAct] = []
        seen: set[tuple[Any, ...]] = set()
        for candidate in raw_output.get("activities") or []:
            if not isinstance(candidate, dict) or candidate.get("role") != "progress":
                continue
            try:
                activity = FastPlannerProgressAct.model_validate(candidate)
            except ValidationError:
                continue
            refs = set(activity.source_responsibility_refs)
            if not refs or not refs.issubset(allowed_refs):
                continue
            key = (
                activity.progress_kind,
                activity.speech_act,
                activity.text,
                activity.timing,
                tuple(sorted(refs)),
            )
            if key in seen:
                continue
            seen.add(key)
            retained.append(activity)
        return retained

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
        plan_id = self._plan_id(request)
        context = request.context if isinstance(request.context, dict) else {}
        expected_goal_ids_for_turn = expected_goal_ids(context)
        authoritative_goals = canonical_goal_grounding(context)
        response_goal_ids = sorted(planner_response_goal_ids(authoritative_goals))
        response_only, requires_execution = planner_goal_execution_requirements(
            authoritative_goals
        )
        reentry_goal_ids = result_evidence_reentry_goal_ids(context)
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
            {
                "capability_id": item.capability_id,
                "description": item.description,
                "input_schema": item.input_schema,
                "requires_confirmation": item.requires_confirmation,
                "can_run_parallel": item.can_run_parallel,
                "parallel_metadata_declared": item.parallel_metadata_declared,
                "exclusive_group": item.exclusive_group,
                "resource_claims": list(item.resource_claims),
                "effects": list(item.effects),
                "safety_class": item.safety_class,
                "hints": dict(item.hints),
            }
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
                        self._bounded(detached_resolution_repairs, 2000),
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
                        self._bounded(provenance_repairs, 2000),
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
                        self._bounded(numeric_provenance_repairs, 2000),
                    )
                try:
                    normalized = (
                        self._normalize_multi_goal(
                            raw,
                            request=request,
                            plan_id=plan_id,
                            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        )
                        if multi_goal_contract
                        else self._normalize(
                            raw,
                            request=request,
                            plan_id=plan_id,
                            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        )
                    )
                    plan = CanonicalPlan.model_validate(normalized)
                    validated_model_output = validate_planner_model_output(
                        raw,
                        planner_tier="fast",
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    self._validate_work_reuse_selection(
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
                    raise _AuthoritativeGroundingValidationError(str(exc)) from exc
                validate_external_response_evidence_boundary(
                    validated_model_output,
                    context=request.context,
                )
                capability_errors = self._capability_argument_errors(
                    plan,
                    capability_payload,
                )
                if capability_errors:
                    raise _CapabilityArgumentValidationError(capability_errors)
            except ResourceResponsibilityRequiresCompositionError as exc:
                logger.info(
                    "fast_planner_resource_composition_required sid=%s error=%s",
                    request.sid,
                    exc,
                )
                return self._escalation(
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
                    return self._escalation(
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
                    initial_validation_errors = self._validation_error_json(
                        exc,
                        raw=raw,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    logger.warning(
                        "fast_planner_contract_repair_start sid=%s validation_errors=%s "
                        "raw_output_ref=%s raw_output=%s",
                        request.sid,
                        initial_validation_errors,
                        cognition_text_reference(initial_raw_output),
                        self._bounded(initial_raw_output, 4000),
                    )
                    continue
                logger.warning(
                    "fast_planner_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s repair_raw_output_ref=%s "
                    "initial_raw_output=%s repair_raw_output=%s",
                    request.sid,
                    cognition_text_reference(initial_raw_output),
                    cognition_text_reference(raw if contract_repair_attempted else None),
                    self._bounded(initial_raw_output, 4000)
                    if initial_raw_output is not None
                    else "",
                    self._bounded(raw, 4000)
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
                    exc, _AuthoritativeGroundingValidationError
                )
                semantic_validation_failure = (
                    isinstance(exc, ValueError)
                    and not mechanical_contract_error
                    and not authoritative_grounding_failure
                )
                return self._escalation(
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
                            if isinstance(exc, _CapabilityArgumentValidationError)
                            else []
                        ),
                        **integrity_metadata,
                    },
                )

            validated = self._validate(
                plan,
                capability_payload=capability_payload,
                request=request,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
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
                    return self._escalation(
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
                    return self._escalation(
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
                    return self._escalation(
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
                    return self._escalation(
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

    @staticmethod
    def _validation_error_json(
        exc: Exception,
        *,
        raw: Any,
        expected_goal_ids_for_turn: list[str],
    ) -> str:
        if isinstance(exc, _CapabilityArgumentValidationError):
            feedback = [dict(item) for item in exc.feedback]
        elif isinstance(exc, ValidationError):
            feedback = list(exc.errors(include_url=False))
        else:
            feedback = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
        feedback.extend(
            planner_contract_diagnostics(
                raw,
                planner_tier="fast",
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
        )
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[Any, ...]]] = set()
        for item in feedback:
            key = (
                str(item.get("msg") or item.get("message") or ""),
                tuple(item.get("loc") or []),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return bounded_json(unique, 10000)

    @staticmethod
    def _capability_argument_errors(
        plan: CanonicalPlan,
        capability_payload: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        allowed = {item["capability_id"]: item for item in capability_payload}
        errors: list[dict[str, Any]] = []
        for step in plan.steps:
            capability = allowed.get(step.capability_id)
            if capability is None:
                continue
            schema_errors = validate_args_for_schema(
                step.args,
                capability.get("input_schema") or {},
            )
            if schema_errors:
                errors.append(
                    {
                        "type": "invalid_args",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "errors": schema_errors[:8],
                    }
                )
        return errors

    @staticmethod
    def _plan_id(request: CognitiveWorkRequest) -> str:
        digest = hashlib.sha256(
            f"{request.sid or 'turn'}|fast|{request.text}".encode()
        ).hexdigest()[:20]
        return f"plan_{digest}"

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        return bounded_json(value, limit)

    @staticmethod
    def _validate_work_reuse_selection(
        output: Any,
        *,
        context: dict[str, Any] | None,
    ) -> None:
        """Validate explicit Planner reuse references without choosing reuse.

        Fast Planner owns the semantic decision by either citing a supplied
        provisional Activity ID or omitting it. This check is deliberately
        mechanical: cited IDs must exist and the selected step must preserve
        the Activity's immutable Capability, arguments, and timing. The Host
        later validates canonical Goal ownership and live runtime state.
        """

        raw_activities = (context or {}).get(
            "existing_work_activities"
        )
        activities = (
            [item for item in raw_activities if isinstance(item, dict)]
            if isinstance(raw_activities, list)
            else []
        )
        by_id = {
            str(item.get("activity_id") or "").strip(): item
            for item in activities
            if str(item.get("activity_id") or "").strip()
        }
        cited: set[str] = set()
        for step in output.steps:
            activity_id = str(step.reuse_activity_id or "").strip()
            if not activity_id:
                continue
            if activity_id in cited:
                raise PlannerDTOContractError(
                    f"reuse_activity_id is duplicated: {activity_id}"
                )
            cited.add(activity_id)
            activity = by_id.get(activity_id)
            if activity is None:
                raise PlannerDTOContractError(
                    f"reuse_activity_id was not supplied by Runtime: {activity_id}"
                )
            if step.capability_id != str(activity.get("capability_id") or ""):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes capability_id"
                )
            if step.args != dict(activity.get("args") or {}):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes immutable args"
                )
            if step.timing != str(activity.get("timing") or "sequential"):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes timing"
                )

        # The supplied reconciliation projection is one bounded snapshot.
        # Reusing any member currently requires selecting every member; extra
        # newly planned steps remain legal and execute beside the reused set.
        if cited and cited != set(by_id):
            raise PlannerDTOContractError(
                "Work reuse must select the complete supplied "
                "Activity set"
            )
        if cited and any(
            by_id[activity_id].get("origin") == "retained_runtime"
            for activity_id in cited
        ) and len(output.steps) != len(cited):
            raise PlannerDTOContractError(
                "retained Runtime Work reuse cannot add steps to the "
                "reconciliation-only Plan"
            )


    def _normalize_multi_goal(
        self,
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
        plan_id: str,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        """Add only host-owned envelope fields to a model-authored plan."""

        model_output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out = model_output.model_dump(mode="python")
        out.pop("plan_relation", None)
        out.pop("user_confirmation_required", None)
        out["goal_outcomes"] = materialize_goal_outcomes(
            model_output,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out["plan_id"] = plan_id
        out["planner_tier"] = "fast"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        metadata = materialize_planner_metadata(model_output)
        metadata.update(
            {
                "model_contract": "FastPlannerMultiGoalPlanOutput",
                "semantic_authority": "fast_planner_model",
                "model_authored_steps": True,
                "model_authored_step_ids": True,
                "model_authored_step_ownership": True,
                "model_authored_goal_outcomes": True,
                "model_authored_goal_satisfaction": True,
                "host_semantic_compilation": False,
            }
        )
        out["metadata"] = metadata
        return out

    def _normalize(
        self,
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
        plan_id: str,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        model_output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out = model_output.model_dump(mode="python")
        out.pop("plan_relation", None)
        out.pop("user_confirmation_required", None)
        out["goal_outcomes"] = materialize_goal_outcomes(
            model_output,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out["plan_id"] = plan_id
        out["planner_tier"] = "fast"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        steps = out.get("steps")
        if isinstance(steps, dict):
            steps = [steps]
        if not isinstance(steps, list):
            steps = []
        normalized_steps = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            step = dict(item)
            if not step.get("step_id"):
                step["step_id"] = f"{plan_id}:step:{index}"
            step.setdefault("timing", "sequential")
            normalized_steps.append(step)
        out["steps"] = normalized_steps
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "escalate")
        out.setdefault("confidence", 0.0)
        out.setdefault("goal_summary", request.text)
        out.setdefault("response_text", "")
        out.setdefault("escalation_reason", "")
        out.setdefault("unresolved", [])
        out.setdefault("parameter_resolutions", [])
        out.setdefault("goal_outcomes", [])
        out.setdefault("goal_satisfaction", None)
        out["metadata"] = materialize_planner_metadata(model_output)
        return out

    def _validate(
        self,
        plan: CanonicalPlan,
        *,
        capability_payload: list[dict[str, Any]],
        request: CognitiveWorkRequest,
        expected_goal_ids_for_turn: list[str],
    ) -> CanonicalPlan:
        allowed = {item["capability_id"]: item for item in capability_payload}
        contract_schema = (
            "FastPlannerMultiGoalPlanOutput"
            if len(expected_goal_ids_for_turn) > 1
            else "FastPlannerModelOutput"
        )
        counts = {
            "authoritative_goal_count": len(expected_goal_ids_for_turn),
            "goal_outcome_count": len(plan.goal_outcomes),
            "executable_step_count": len(plan.steps),
        }
        if expected_goal_ids_for_turn and set(plan.goal_ids) != set(expected_goal_ids_for_turn):
            return self._escalation(
                plan.plan_id,
                request,
                "goal_ids_do_not_match_goal_association",
                response_text=plan.response_text,
                metadata={
                    "expected_goal_ids": expected_goal_ids_for_turn,
                    "actual_goal_ids": list(plan.goal_ids),
                    **counts,
                },
            )
        _, requires_execution = planner_goal_execution_requirements(
            canonical_goal_grounding(request.context)
        )
        if result_evidence_reentry_goal_ids(request.context) == set(
            expected_goal_ids_for_turn
        ):
            requires_execution = False
        if (
            requires_execution
            and plan.disposition not in {"escalate", "clarify", "unavailable", "refused"}
            and not plan.steps
        ):
            return self._escalation(
                plan.plan_id,
                request,
                "canonical_goal_requires_executable_step",
                response_text=plan.response_text,
                metadata={
                    "proposed_disposition": plan.disposition,
                    **counts,
                },
            )
        if plan.disposition == "escalate":
            metadata = dict(plan.metadata)
            metadata.update(
                {
                    "resolver": "fast_planner",
                    "status": "escalate",
                    "authority": "advisory",
                    "path_classification": "semantic_escalation",
                    "common_capability_count": len(capability_payload),
                    "min_confidence": self.min_confidence,
                    "contract_schema": contract_schema,
                    "canonical_contract": "CanonicalPlan",
                    **counts,
                }
            )
            return plan.model_copy(update={"metadata": metadata})
        if plan.coverage != "complete" or plan.confidence < self.min_confidence:
            return self._escalation(
                plan.plan_id,
                request,
                "coverage_not_complete",
                response_text=plan.response_text,
                unresolved=plan.unresolved,
                metadata={
                    "proposed_coverage": plan.coverage,
                    "proposed_confidence": plan.confidence,
                    **counts,
                },
            )
        if plan.goal_satisfaction is None or plan.goal_satisfaction.score < 0.95:
            return self._escalation(
                plan.plan_id,
                request,
                "goal_satisfaction_not_exact",
                response_text=plan.response_text,
                unresolved=plan.unresolved,
                metadata={
                    "proposed_goal_satisfaction": (
                        plan.goal_satisfaction.model_dump(mode="json")
                        if plan.goal_satisfaction
                        else None
                    ),
                    **counts,
                },
            )
        incomplete_outcomes = [
            outcome.goal_id
            for outcome in plan.goal_outcomes
            if outcome.satisfaction is None or outcome.satisfaction.score < 0.95
        ]
        if incomplete_outcomes:
            return self._escalation(
                plan.plan_id,
                request,
                "per_goal_satisfaction_not_exact",
                response_text=plan.response_text,
                unresolved=incomplete_outcomes,
                metadata={**counts},
            )
        for step in plan.steps:
            capability = allowed.get(step.capability_id)
            if capability is None:
                return self._escalation(
                    plan.plan_id,
                    request,
                    "step_not_in_executable_common_catalog",
                    response_text=plan.response_text,
                    unresolved=[step.capability_id],
                    metadata={**counts},
                )
        parallel_errors = parallel_plan_contract_errors(
            plan,
            capability_payload,
        )
        if parallel_errors:
            return self._escalation(
                plan.plan_id,
                request,
                "parallel_execution_contract_unavailable",
                response_text=plan.response_text,
                unresolved=[str(item["type"]) for item in parallel_errors],
                metadata={
                    "parallel_contract_errors": parallel_errors,
                    "execution_allowed": False,
                    **counts,
                },
            )
        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "fast_planner",
                "status": "complete",
                "authority": "advisory",
                "common_capability_count": len(capability_payload),
                "min_confidence": self.min_confidence,
                "contract_schema": contract_schema,
                "canonical_contract": "CanonicalPlan",
                "path_classification": "terminal",
                **counts,
            }
        )
        return plan.model_copy(update={"metadata": metadata})

    def _escalation(
        self,
        plan_id: str,
        request: CognitiveWorkRequest,
        reason: str,
        *,
        response_text: str = "",
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: Exception | None = None,
        path_classification: str = "semantic_escalation",
    ) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update(
            {
                "resolver": "fast_planner",
                "status": "escalate",
                "authority": "advisory",
                "path_classification": path_classification,
            }
        )
        if error is not None:
            detail.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                    **llm_failure_metadata(error),
                }
            )
        context = request.context if isinstance(request.context, dict) else {}
        retained_progress = " ".join(str(response_text or "").strip().split())
        if retained_progress:
            detail["retained_progress_response_text"] = {
                "status": "undelivered_advisory",
                "reason": reason,
            }
        return CanonicalPlan(
            plan_id=plan_id,
            planner_tier="fast",
            disposition="escalate",
            coverage="uncertain",
            confidence=0.0,
            goal_ids=expected_goal_ids(context),
            goal_summary=request.text,
            response_text=retained_progress,
            steps=[],
            escalation_reason=reason,
            unresolved=list(unresolved or []),
            metadata=detail,
        )
