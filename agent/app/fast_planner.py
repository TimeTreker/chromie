from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import (
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
    fast_first_response_response_schema,
    fast_advance_revision_response_schema,
    fast_advance_response_schema,
    fast_repair_response_schema,
)
from .planner_context import (
    fast_capability_payload,
    planner_goal_context,
)
from .planner_validation import (
    normalize_common_planner_output,
    qualify_planner_capability_payload,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from .planner_fast_validation import (
    AuthoritativeGroundingValidationError,
    CapabilityArgumentValidationError,
    FastAdvanceMechanicalSchedulingError,
    capability_argument_errors,
    planner_validation_error_json,
    qualify_fast_canonical_plan,
    restore_required_capability_args_from_responsibilities,
    validate_fast_advance_output,
    validate_work_reuse_selection,
)
from .planner_fallback import (
    materialize_fast_advance_fail_safe,
    materialize_fast_escalation,
)
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
    from chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
    )

from .planner_prompt import (
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
        num_ctx: int = 8192,
        num_predict: int = 2048,
        cognitive_budget_profile: str = "interactive",
        max_capabilities: int = 24,
        max_contract_repairs: int = 1,
    ) -> None:
        self.ollama = ollama
        # Fast Planner remains the sole semantic owner of both phases. The
        # latency-critical natural-language Activity may use a dedicated model;
        # complete Capability planning stays on ``ollama``.
        self.first_response_ollama = first_response_ollama or ollama
        self.first_response_num_ctx = max(
            2048,
            int(
                first_response_num_ctx
                if first_response_num_ctx is not None
                else min(num_ctx, 6144)
            ),
        )
        self.catalog = catalog
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.cognitive_budget_profile = (
            str(cognitive_budget_profile or "interactive").strip() or "interactive"
        )
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
        if request.interpretation_unresolved:
            # GI owns WHAT and has explicitly retained an unresolved meaning.  A
            # prospective first response would falsely imply that one meaning was
            # selected before the same Planner has authored its typed clarification.
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=None,
                metadata={
                    "semantic_authority": "fast_planner_unresolved_meaning_contract",
                    "phase": "first_communicative_activity",
                    "decision": "silence",
                    "execution_authority": "none",
                    "unresolved_meaning_count": len(request.interpretation_unresolved),
                },
            )
        response_schema = fast_first_response_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            language=str(request.language or ""),
        )
        try:
            raw = await self.first_response_ollama.generate(
                fast_first_response_prompt(
                    request,
                    responsibilities=responsibilities,
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
                    # The schema is compact, but retained qualification evidence
                    # includes a valid multi-goal first response that reached the
                    # former 128-token ceiling before Ollama closed the JSON object.
                    # Keep this below the historical 512-token repetition failure
                    # while allowing one complete bounded response.
                    "num_predict": min(
                        self.num_predict,
                        4096
                        if self.cognitive_budget_profile == "qualification"
                        else 256,
                    ),
                    "stop": [
                        "✅",
                        "\n\nNote:",
                        "\n\nExplanation:",
                        "\n\nFinal truth check:",
                        # Gemma 4 can close the schema-valid object and then loop
                        # over Markdown-fenced copies until num_predict is exhausted.
                        # Stop at the mechanical suffix while retaining the first
                        # complete JSON object; this does not salvage a truncated
                        # response or alter any semantic field.
                        "_```json",
                        "}```json",
                        "\n```json",
                        "```",
                    ],
                },
                response_format=response_schema,
                prompt_family="fast_planner.first_response",
                turn_id=request.sid,
                attempt=1,
            )
            if isinstance(raw, dict):
                raw_activity = raw.get("activity")
                if isinstance(raw_activity, dict):
                    activity_payload = dict(raw_activity)
                    if len(responsibility_refs) == 1:
                        # There is no semantic association choice in the single-
                        # Responsibility case. Keep that mechanical provenance out
                        # of the latency-critical model DTO and restore it before the
                        # authoritative Activity contract is validated.
                        activity_payload.setdefault(
                            "source_responsibility_refs", responsibility_refs
                        )
                    role = str(activity_payload.get("role") or "")
                    if not role:
                        # The latency-critical decoder omits the mechanical role
                        # discriminator. Presence of progress_kind is the semantic
                        # choice between a prospective progress act and a complete
                        # conversational response; restore the contract tag here.
                        role = (
                            "progress"
                            if activity_payload.get("progress_kind") not in (None, "")
                            else "complete_response"
                        )
                        activity_payload["role"] = role
                    activity_payload.setdefault(
                        "activity_id",
                        ("progress_" if role == "progress" else "response_")
                        + hashlib.sha256(
                            (
                                str(request.sid or "turn")
                                + "|"
                                + role
                                + "|"
                                + "|".join(responsibility_refs)
                            ).encode("utf-8")
                        ).hexdigest()[:12],
                    )
                    raw = {**raw, "activity": activity_payload}
            output = FastPlannerFirstResponseModelOutput.model_validate(raw)
            activity = output.activity
            if activity is None:
                return FastPlannerFirstResponse(
                    turn_id=str(request.sid or "turn-fast-first-response"),
                    activity=None,
                    metadata={
                        "semantic_authority": "fast_planner_model",
                        "phase": "first_communicative_activity",
                        "decision": "silence",
                        "execution_authority": "none",
                    },
                )
            refs = set(activity.source_responsibility_refs)
            if not refs or not refs.issubset(set(responsibility_refs)):
                raise PlannerDTOContractError(
                    "Fast first response must cite supplied Responsibility refs"
                )
            if activity.role == "complete_response" and any(
                item.output_mode != "speech" for item in responsibilities
            ):
                raise PlannerDTOContractError(
                    "first-response completion is valid only for conversational speech WHAT; "
                    "information and observable/stateful effects remain Planner work"
                )
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=activity,
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "first_communicative_activity",
                    "execution_authority": "host_communicative_runtime",
                    "semantic_result_call_count": 1,
                    "truth_contract": "primary_prompt_schema_and_typed_provenance",
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
        first_response_attempted = isinstance(raw_first_response, dict)
        if isinstance(raw_first_response, dict):
            try:
                first_response = FastPlannerFirstResponse.model_validate(
                    raw_first_response
                )
            except ValidationError:
                first_response = None
            if first_response is not None:
                # A fail-safe is evidence that this bounded model call did not
                # make a valid communication decision. Treating it as intentional
                # silence removes complete-response Activities from Advance and
                # can make an ordinary speech Responsibility impossible to
                # satisfy. Model-authored silence remains a real bounded
                # decision and must still suppress replacement progress chatter.
                first_response_decided = (
                    first_response.activity is not None
                    or first_response.metadata.get("semantic_authority")
                    != "deterministic_fail_safe"
                )
                if first_response.activity is not None:
                    committed_communicative_activities.append(first_response.activity)

        # A validated primary conversational response already covers an all-speech
        # WHAT. Returning here keeps unrelated body/tool choices out of a second
        # model decision; work/evidence readiness is not imported from GI.
        if (
            responsibilities
            and all(item.output_mode == "speech" for item in responsibilities)
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
            # sentence and thereby bypass its primary fail-closed decision.
            committed_communicative=bool(committed_communicative_activities),
            suppress_new_communicative=(
                first_response_decided
                and not committed_communicative_activities
            ),
            # A failed bounded response call is not a semantic silence
            # decision, so ordinary speech may still be completed here. It is
            # nevertheless an attempted prospective-speech phase and Advance
            # must not bypass its fail-closed result with substitute progress.
            suppress_new_progress=first_response_attempted,
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
                        first_response_attempted=first_response_attempted,
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
                    (
                        ValidationError,
                        FastAdvanceMechanicalSchedulingError,
                        json.JSONDecodeError,
                    ),
                ):
                    revision_source = last_raw
                    previous_errors = planner_validation_error_json(
                        exc,
                        raw=last_raw,
                        planner_tier="fast",
                        expected_goal_ids_for_turn=responsibility_refs,
                        # Advance validates an Activity DTO over GI
                        # Responsibility refs, not a CanonicalPlan over Goal IDs.
                        # Canonical-plan diagnostics here ask for unrelated
                        # steps/outcomes and corrupt the one mechanical repair.
                        include_canonical_plan_diagnostics=False,
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
        goal_context = planner_goal_context(
            context,
            reentry_scope=request.planner_reentry_scope,
        )
        expected_goal_ids_for_turn = list(goal_context.expected_goal_ids)
        authoritative_goals = list(goal_context.authoritative_goals)
        cancellation_reentry_goal_ids = set(
            goal_context.cancellation_reentry_goal_ids
        )
        reentry_goal_ids = set(goal_context.result_reentry_goal_ids)
        response_goal_ids = list(goal_context.response_goal_ids)
        response_only = goal_context.response_only
        requires_execution = goal_context.requires_execution
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
        projected_payload = [fast_capability_payload(item) for item in executable]
        retained_capability_ids = {
            str(item.get("capability_id") or "").strip()
            for item in context.get("existing_work_activities") or []
            if isinstance(item, dict)
            and str(item.get("capability_id") or "").strip()
        }
        capability_payload = qualify_planner_capability_payload(
            projected_payload,
            authoritative_goals=authoritative_goals,
            retained_capability_ids=retained_capability_ids,
        )[: self.max_capabilities]
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
            # Terminal-result plans are bounded state deltas, not full original
            # plan replays.  Their smaller output reservation keeps the complete
            # scoped prompt inside the configured context window without dropping
            # provenance or silently reducing input context.
            "num_predict": (
                min(self.num_predict, 2048)
                if reentry_goal_ids
                else self.num_predict
            ),
        }
        previous_raw: Any = None
        initial_raw_output: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False
        for attempt in range(self.max_contract_repairs + 1):
            raw: Any = None
            parameter_provenance_repairs: list[dict[str, Any]] = []
            terminal_response_repairs: list[dict[str, Any]] = []
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
                raw, common_repairs = normalize_common_planner_output(
                    raw,
                    authoritative_goals=authoritative_goals,
                    capability_payload=capability_payload,
                )
                terminal_response_repairs = common_repairs[
                    "terminal_response_goal_outcome_accounting"
                ]
                if terminal_response_repairs:
                    logger.info(
                        "fast_planner_terminal_response_accounting_normalized "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(terminal_response_repairs, 2000),
                    )
                detached_resolution_repairs = common_repairs[
                    "detached_parameter_resolutions"
                ]
                if detached_resolution_repairs:
                    logger.warning(
                        "fast_planner_detached_parameter_resolutions_removed "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(detached_resolution_repairs, 2000),
                    )
                provenance_repairs = common_repairs["schema_default_provenance"]
                if provenance_repairs:
                    logger.info(
                        "fast_planner_schema_default_provenance_normalized "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(provenance_repairs, 2000),
                    )
                parameter_provenance_repairs = common_repairs[
                    "parameter_provenance"
                ]
                if parameter_provenance_repairs:
                    logger.info(
                        "fast_planner_parameter_provenance_normalized sid=%s repairs=%s",
                        request.sid,
                        bounded_json(parameter_provenance_repairs, 2000),
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
                    validate_goal_binding_argument_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                        capabilities=capability_payload,
                    )
                except PlannerDTOContractError:
                    raise
                except ValueError as exc:
                    raise AuthoritativeGroundingValidationError(str(exc)) from exc
                try:
                    validate_explicit_numeric_parameter_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                    )
                except PlannerDTOContractError:
                    raise
                except ValueError as exc:
                    # Run after typed Capability grounding so an omitted declared
                    # realization is diagnosed as the bounded mechanical DTO defect
                    # it is. A remaining numeric mismatch is semantic and must still
                    # fail closed instead of being edited in place.
                    raise AuthoritativeGroundingValidationError(str(exc)) from exc
                try:
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
                    authoritative_goals=authoritative_goals,
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
                        or authoritative_grounding_failure
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
                            else [
                                {
                                    "type": "authoritative_grounding_mismatch",
                                    "message": str(exc)[:600],
                                }
                            ]
                            if authoritative_grounding_failure
                            else []
                        ),
                        **integrity_metadata,
                    },
                )

            qualification = qualify_fast_canonical_plan(
                plan,
                capability_payload=capability_payload,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                authoritative_goals=authoritative_goals,
                evidence_reentry_goal_ids=(
                    reentry_goal_ids | cancellation_reentry_goal_ids
                ),
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
            if parameter_provenance_repairs:
                metadata = dict(validated.metadata)
                metadata["parameter_provenance_normalization"] = {
                    "strategy": "project_mechanically_derivable_provenance",
                    "repairs": parameter_provenance_repairs,
                    "semantic_plan_unchanged": True,
                }
                validated = validated.model_copy(update={"metadata": metadata})
            if terminal_response_repairs:
                metadata = dict(validated.metadata)
                metadata["terminal_response_accounting_normalization"] = {
                    "strategy": "project_exact_per_goal_responses",
                    "repairs": terminal_response_repairs,
                    "semantic_outcomes_unchanged": True,
                }
                validated = validated.model_copy(update={"metadata": metadata})
            return validated
        raise AssertionError("unreachable")
