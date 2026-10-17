from __future__ import annotations

from contextlib import aclosing
import hashlib
import json
import logging
from typing import Any, AsyncGenerator

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import (
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .prompt_projection import RequiredPromptProjectionError, bounded_json
from .planner_model_contract import (
    PlannerAbilityNeed,
    PlannerDTOContractError,
    PlannerEvidenceReentryModelOutput,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
    is_planner_step_capability,
    materialize_evidence_reentry_model_output,
    materialize_planner_output,
    parse_ability_needs,
    stable_plan_id,
    take_ability_needs,
    take_activity_count,
)
from .planner_schema import (
    need_first_response_schema,
    readiness_first_response_schema,
    scoped_reporting_response_schema,
    planner_readiness_response_schema,
    work_change_response_schema,
    canonical_goal_binding_argument_response_schema,
    canonical_resource_argument_response_schema,
    canonical_plan_response_schema,
    fast_evidence_reentry_response_schema,
    fast_multi_goal_response_schema,
    fast_streaming_advance_response_schema,
    native_goal_outcome_branches,
)
from .planner_context import (
    planner_provider_vocal_goal_ids,
    provider_media_goal_ids_without_capability,
    completed_acquisition_goal_ids,
    completed_work_step_evidence,
    trusted_target_prompt_context,
    trusted_target_ref,
    realizable_with_current_target,
    cancellation_capability_facts,
    fast_capability_payload,
    fast_capability_context,
    planner_effectful_goal_ids,
    planner_goal_context,
    search_capability_library,
    situation_source_observations,
)
from .planner_validation import (
    capability_ids_acquiring_information,
    information_goal_ids_without_declared_provider,
    resource_goal_ids_without_complete_provider_contract,
    information_acquisition_goal_ids,
    normalize_common_planner_output,
    qualify_planner_capability_payload,
    fast_activity_execution_groups,
    qualify_capability_catalog_for_output_mode_values,
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
    capability_argument_errors,
    qualify_fast_canonical_plan,
    canonicalize_fast_argument_source_spans,
    collapse_redundant_idempotent_read_activities,
    drop_repeated_identical_activities,
    normalize_fast_capability_activity_purpose,
    project_responsibility_decisions,
    validate_fast_advance_output,
    validate_work_reuse_selection,
)
from .planner_fallback import materialize_planner_failure, materialize_planner_unavailable
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
from shared.chromie_contracts.user_turn import user_turn_source_tokens

from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerAdvanceModelOutput,
    FastPlannerStreamFailure,
    FastPlannerStreamFrame,
    FastPlannerStreamTerminal,
)

from .planner_prompt import (
    fast_advance_layered_prompt,
    fast_evidence_reentry_prompt,
    fast_evidence_reentry_system_prompt,
    fast_streaming_advance_system_prompt,
    fast_layered_prompt,
    fast_system_prompt,
)


logger = logging.getLogger("chromie.agent.fast_planner")




def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous member ownership before a parsed value can be exposed."""

    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PlannerDTOContractError(f"Fast Planner JSON object repeats key: {key}")
        value[key] = item
    return value


def complete_ability_needs(buffer: str) -> list[Any] | None:
    """Return the need-first prefix of a streamed Work object once its array closes."""
    key = buffer.find('"ability_needs"')
    start = buffer.find("[", key) if key >= 0 else -1
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(buffer, start)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) else None


def ability_need_metadata(needs: list[PlannerAbilityNeed], searched: list[str], loaded: tuple[str, ...]) -> dict[str, Any]:
    return {
        "ability_needs": [item.model_dump() for item in needs],
        "ability_need_search": {"unmet_needs": searched, "loaded_capability_ids": list(loaded)},
        "capability_detail_lookups": int(bool(loaded)),
    }


def parse_fast_work_document(buffer: str) -> dict[str, Any]:
    """Require one finite, unambiguous complete Work object."""
    def reject_constant(value: str) -> Any:
        raise PlannerDTOContractError(f"Fast Planner JSON contains nonfinite value: {value}")
    value = json.loads(buffer, object_pairs_hook=_unique_json_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise PlannerDTOContractError("Fast Planner Work result must be an object")
    return value


class PlannerResolver:
    """Fast planning with common contracts, need-first and one library search."""

    TRACE_MODULE = TraceModule(
        name="agent.fast_planner",
        component_type="planner",
        implementation="PlannerResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        catalog: CapabilityCatalog,
        *,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        cognitive_budget_profile: str = "interactive",
        max_capabilities: int = 24,
    ) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.cognitive_budget_profile = (
            str(cognitive_budget_profile or "interactive").strip() or "interactive"
        )
        self.max_capabilities = max(1, min(64, int(max_capabilities)))



    async def stream_advance(
        self, request: CognitiveWorkRequest,
    ) -> AsyncGenerator[FastPlannerStreamFrame, None]:
        """Validate one complete Work decision before releasing any Activity."""
        responsibilities = list(request.responsibilities)
        turn_id = str(request.sid or "turn-fast-stream")
        try:
            loaded_ids: tuple[str, ...] = ()
            first_needs: list[PlannerAbilityNeed] = []
            unmet: list[str] = []
            for invocation in range(2):
                current, catalog, entries = await fast_capability_context(self.catalog, request, loaded_ids)
                current.context["planner_target_evidence_context"] = trusted_target_prompt_context(current.context)
                target_ref = trusted_target_ref(current.context)
                output_modes = {item.output_mode for item in responsibilities}
                projected = [fast_capability_payload(item, include_side_effect_free=True)
                    for item in catalog if item.available and item.interaction_executable
                    and is_planner_step_capability(item.capability_id)
                    and realizable_with_current_target(item, target_ref)]
                capabilities = qualify_capability_catalog_for_output_mode_values(
                    projected,
                    output_modes=output_modes,
                )
                # Contracts the Planner requested through need-first search are components
                # of its HOW (for example the forecast read before a conditional action);
                # they are not filtered against the Responsibility's own output mode.
                qualified_ids = {item["capability_id"] for item in capabilities}
                capabilities += [item for item in projected if item["capability_id"] in loaded_ids
                                 and item["capability_id"] not in qualified_ids]
                if len(capabilities) > self.max_capabilities + len(loaded_ids):
                    raise PlannerDTOContractError("Common capability contracts exceed the configured context budget")
                loaded_capability_ids = [item["capability_id"] for item in capabilities]
                schema = need_first_response_schema(fast_streaming_advance_response_schema(
                    [item.local_ref for item in responsibilities], responsibilities=responsibilities,
                    capabilities=capabilities, meaning_uncertainties=list(request.meaning_uncertainties),
                    language=str(request.language or ""),
                    source_token_refs=[item["ref"] for item in user_turn_source_tokens(current.original_user_text)],
                    original_user_text=current.original_user_text,
                    situation_source_refs=list(situation_source_observations(current.context)),
                    trusted_target_ref=target_ref,
                ), loaded_capability_ids)
                prompt = fast_advance_layered_prompt(current, responsibilities=responsibilities,
                    capabilities=capabilities, response_schema=schema)
                raw_text = ""
                searched: list[str] = []
                async with aclosing(self.ollama.generate_stream(
                    prompt, system=fast_streaming_advance_system_prompt(),
                    options={"temperature": 0, "top_p": 0.9, "num_ctx": self.num_ctx,
                             "num_predict": self.num_predict},
                    response_format=schema, prompt_family="fast_planner.streaming_advance",
                    turn_id=request.sid, attempt=invocation + 1,
                )) as deltas:
                    needs_seen = invocation > 0
                    async for delta in deltas:
                        raw_text += delta
                        if len(raw_text) > 131072 or (raw_text.lstrip() and not raw_text.lstrip().startswith("{")):
                            raise PlannerDTOContractError("Fast Planner Work stream is oversized or not a JSON object")
                        if needs_seen:
                            continue
                        prefix = complete_ability_needs(raw_text)
                        if prefix is None:
                            continue
                        needs_seen = True
                        first_needs = parse_ability_needs(prefix, loaded_capability_ids=loaded_capability_ids)
                        unmet = [item.need for item in first_needs if item.unmet]
                        # Search everything the Planner did not see, including a common
                        # contract the Responsibility's output mode filtered out.
                        found = search_capability_library(
                            unmet, entries, loaded_ids=set(loaded_capability_ids)) if unmet else []
                        by_id = {item.capability_id: item for item in entries}
                        # A speech-only turn cannot author a Capability Activity, so nothing loads.
                        can_work = any(item.output_mode != "speech" for item in responsibilities)
                        searched = [key for key in found if key in by_id] if can_work else []
                        if searched:
                            # Stop reading: no Plan from this pass is used.
                            break
                if searched:
                    loaded_ids = tuple(searched)
                    continue
                from jsonschema import Draft202012Validator
                raw = parse_fast_work_document(raw_text)
                Draft202012Validator(schema).validate(raw)
                final_needs = take_ability_needs(raw, loaded_capability_ids=loaded_capability_ids)
                take_activity_count(raw)
                output = FastPlannerAdvanceModelOutput.model_validate(raw)
                output, repeated_activity_repairs = drop_repeated_identical_activities(output)
                if repeated_activity_repairs:
                    logger.info("fast_planner_repeated_activity_removed sid=%s repairs=%s",
                                request.sid, bounded_json(repeated_activity_repairs, 1000))
                authored_decisions = {ref: item.model_dump() for ref, item in output.responsibility_decisions.items()}
                output = project_responsibility_decisions(
                    output, responsibility_refs=[item.local_ref for item in responsibilities],
                    speech_refs={item.local_ref for item in responsibilities if item.output_mode == "speech"},
                )
                output = normalize_fast_capability_activity_purpose(
                    output, capabilities=capabilities
                )
                # Validate/ground every authored Activity before any representation
                # deduplication. Validation also removes exact optional schema defaults
                # that have no semantic owner. Two side-effect-free idempotent reads
                # which differ only because one redundantly restated such a provider
                # default are therefore identical *after* trusted grounding and may be
                # collapsed without changing Planner meaning.
                validate_fast_advance_output(output, request=current,
                    responsibilities=responsibilities, capabilities=capabilities)
                output, duplicate_read_repairs = collapse_redundant_idempotent_read_activities(
                    output, capabilities=capabilities
                )
                if duplicate_read_repairs:
                    logger.info(
                        "fast_planner_duplicate_idempotent_reads_collapsed sid=%s repairs=%s",
                        request.sid,
                        bounded_json(duplicate_read_repairs, 2400),
                    )
                output = canonicalize_fast_argument_source_spans(
                    output, source=current.original_user_text, responsibilities=responsibilities,
                )
                break
            else:
                raise PlannerDTOContractError("Capability search budget exhausted before a Plan")
            advance = FastPlannerAdvance(turn_id=turn_id, **output.model_dump(exclude={"responsibility_decisions"}), metadata={
                "semantic_authority": "planner_model", "phase": "responsibility_work_plan",
                "responsibility_decisions": authored_decisions,
                **({"repeated_activity_normalization": repeated_activity_repairs} if repeated_activity_repairs else {}),
                "execution_authority": "trusted_capability_runtime", "semantic_result_call_count": 1,
                **ability_need_metadata(first_needs or final_needs, unmet if loaded_ids else [], loaded_ids),
                "final_ability_needs": [item.model_dump() for item in final_needs],
                "mechanical_duplicate_activity_collapses": duplicate_read_repairs,
                # Host-derived from Planner depends_on and Capability contracts.
                "execution_groups": fast_activity_execution_groups(
                    [item for item in output.activities if item.role == "capability" and not item.deferred],
                    capabilities,
                ),
            })
            yield FastPlannerStreamTerminal(turn_id=turn_id, advance=advance)
        except Exception as exc:
            failure = (exc.metadata() if isinstance(exc, RequiredPromptProjectionError)
                else llm_failure_metadata(exc) if isinstance(exc, OllamaGenerationError)
                else {"failure_class": "fast_stream_contract_invalid", "failure_domain": "model_contract",
                      "architecture_attribution": "fast_planner", "retryable": False})
            logger.warning("fast_planner_work_fail_closed sid=%s error_type=%s error=%s", request.sid, type(exc).__name__, getattr(exc, "message", str(exc)))
            yield FastPlannerStreamFailure(turn_id=turn_id, failure_stage="before_commit",
                failure_class=str(failure["failure_class"]), failure_domain=str(failure["failure_domain"]),
                architecture_attribution=str(failure.get("architecture_attribution") or "fast_planner"),
                retryable=bool(failure.get("retryable")), error_type=type(exc).__name__, reason=str(getattr(exc, "message", str(exc)))[:500])

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

    async def _resolve(self, request: CognitiveWorkRequest, loaded_capability_ids: tuple[str, ...] = ()) -> CanonicalPlan:
        request, selected_catalog, indexed_catalog = await fast_capability_context(self.catalog, request, loaded_capability_ids)
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
        future_goal_times = dict(goal_context.future_goal_times)
        reporting_goal_ids = cancellation_reentry_goal_ids | set(future_goal_times)
        response_only = goal_context.response_only
        requires_execution = goal_context.requires_execution
        capabilities = selected_catalog
        auxiliary_catalog = await self.catalog.prompt_entries(scope="all", refresh=False)
        context["planner_cancellation_capability_facts"] = (
            cancellation_capability_facts(auxiliary_catalog)
            if cancellation_reentry_goal_ids else []
        )
        context["planner_target_evidence_context"] = trusted_target_prompt_context(context)
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
        )
        # Need-first contracts the Planner requested are composition components and are
        # not filtered against the whole Goal (the former Deep composition rule).
        qualified_ids = {item["capability_id"] for item in capability_payload}
        capability_payload += [item for item in projected_payload
                               if item["capability_id"] in set(loaded_capability_ids)
                               and item["capability_id"] not in qualified_ids]
        multi_goal_contract = len(expected_goal_ids_for_turn) > 1
        evidence_reentry = bool(
            request.planner_reentry_scope is not None
            and request.planner_reentry_scope.trigger in {
                "capability_result_reentry",
                "post_execution",
            }
            and reentry_goal_ids
        )
        # A completed acquisition may leave an explicitly unsatisfied effect in
        # the source Plan. Permit its next decision without reopening settled Work.
        deferred_goal_ids = {
            item.get("goal_id")
            for item in (context.get("canonical_plan_resolution") or {}).get("goal_outcomes", [])
            if isinstance(item, dict)
            and item.get("goal_id") in (item.get("satisfaction") or {}).get("unmet_goal_ids", [])
        }
        allow_reentry_work = requires_execution or bool(
            deferred_goal_ids & completed_acquisition_goal_ids(
                context, reentry_scope=request.planner_reentry_scope,
            )
        )
        if evidence_reentry:
            contract_schema = "FastPlannerEvidenceReentryOutput"
            response_schema = fast_evidence_reentry_response_schema(
                expected_goal_ids=expected_goal_ids_for_turn,
                evidence_refs=list(request.planner_reentry_scope.evidence_refs),
                allowed_capability_ids=[
                    item["capability_id"] for item in capability_payload
                ],
                capability_input_schemas={
                    item["capability_id"]: item["input_schema"]
                    for item in capability_payload
                },
                allow_new_work=allow_reentry_work,
                information_capability_ids=capability_ids_acquiring_information(capability_payload),
                completed_evidence_refs=[
                    str(item.get("evidence_id") or "")
                    for item in completed_work_step_evidence(
                        request.context, reentry_scope=request.planner_reentry_scope,
                    ).values()
                ],
                respond_requires_commitment=not (reporting_goal_ids & set(expected_goal_ids_for_turn)),
                held_effect_goal_ids=sorted({
                    str(goal_id)
                    for step in (context.get("canonical_plan_resolution") or {}).get("deferred_steps") or []
                    if isinstance(step, dict)
                    for goal_id in step.get("source_goal_ids") or []
                }),
            )
        else:
            contract_schema = (
                "FastPlannerMultiGoalPlanOutput"
                if multi_goal_contract
                else "FastPlannerModelOutput"
            )
            unavailable_information = information_goal_ids_without_declared_provider(
                capability_payload, authoritative_goals=authoritative_goals,
            ) - reporting_goal_ids
            unavailable_resource = resource_goal_ids_without_complete_provider_contract(
                capability_payload, authoritative_goals=authoritative_goals,
            ) - reporting_goal_ids
            if request.context.get("verified_tool_memory_index"):
                # A fresh exact memory entry may satisfy an information Goal through its
                # original provider contract; Planner and Evidence validation decide.
                unavailable_resource -= unavailable_information
                unavailable_information = set()
            loaded_ids = {item["capability_id"] for item in capability_payload}
            unavailable_vocal = (
                planner_provider_vocal_goal_ids(authoritative_goals) - reporting_goal_ids
                if VOCAL_PERFORMANCE_CAPABILITY_ID not in loaded_ids else set()
            )
            unavailable_media = provider_media_goal_ids_without_capability(
                authoritative_goals, loaded_ids,
            ) - reporting_goal_ids
            unavailable_goal_ids = sorted(
                unavailable_information | unavailable_resource | unavailable_vocal | unavailable_media
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
                    nonfulfilling_response_goal_ids=sorted(reporting_goal_ids),
                    effectful_goal_ids=list(
                        planner_effectful_goal_ids(authoritative_goals) - reporting_goal_ids
                    ),
                    confirmation_required_capability_ids=[
                        item["capability_id"]
                        for item in capability_payload
                        if item.get("requires_confirmation")
                    ],
                    unavailable_goal_ids=unavailable_goal_ids,
                    information_capability_ids=capability_ids_acquiring_information(capability_payload),
                )
                if multi_goal_contract
                else canonical_plan_response_schema(
                    expected_goal_ids=expected_goal_ids_for_turn,
                    allowed_capability_ids=[item["capability_id"] for item in capability_payload],
                    capability_input_schemas={
                        item["capability_id"]: item["input_schema"]
                        for item in capability_payload
                    },
                    response_only=response_only,
                    requires_execution=requires_execution,
                    response_goal_ids=response_goal_ids,
                    nonfulfilling_response_goal_ids=sorted(reporting_goal_ids),
                    effectful_goal_ids=list(
                        planner_effectful_goal_ids(authoritative_goals) - reporting_goal_ids
                    ),
                    confirmation_required_capability_ids=[
                        item["capability_id"]
                        for item in capability_payload
                        if item.get("requires_confirmation")
                    ],
                    unavailable_goal_ids=unavailable_goal_ids,
                    information_capability_ids=capability_ids_acquiring_information(capability_payload),
                )
            )
            response_schema = canonical_resource_argument_response_schema(
                response_schema,
                authoritative_goals=authoritative_goals,
            )
            response_schema = canonical_goal_binding_argument_response_schema(
                response_schema,
                authoritative_goals=authoritative_goals,
                capabilities=capability_payload,
            )
            response_schema = work_change_response_schema(
                response_schema, context=context
            )
            response_schema = scoped_reporting_response_schema(
                response_schema,
                goal_ids=reporting_goal_ids,
                expected_goal_ids=expected_goal_ids_for_turn,
                future_goal_times=future_goal_times,
            )
            if not reporting_goal_ids and not request.planner_reentry_scope:
                response_schema = planner_readiness_response_schema(
                    response_schema,
                    expected_goal_ids_for_turn,
                    confirmation_required_capability_ids=[
                        item["capability_id"]
                        for item in capability_payload
                        if item.get("requires_confirmation")
                    ],
                )
            response_schema = readiness_first_response_schema(need_first_response_schema(
                native_goal_outcome_branches(response_schema),
                [item["capability_id"] for item in capability_payload],
            ))
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": (
                min(self.num_predict, 1024)
                if evidence_reentry
                else self.num_predict
            ),
        }
        raw: Any = None
        need_metadata: dict[str, Any] = {}
        parameter_provenance_repairs: list[dict[str, Any]] = []
        try:
                if evidence_reentry:
                    raw = await self.ollama.generate(
                        fast_evidence_reentry_prompt(
                            request,
                            capability_payload,
                            goal_context=goal_context,
                            allow_new_work=allow_reentry_work,
                        ),
                        system=fast_evidence_reentry_system_prompt(),
                        options=options,
                        response_format=response_schema,
                        prompt_family="fast_planner.evidence_reentry",
                        turn_id=request.sid,
                        attempt=1,
                    )
                    if not isinstance(raw, dict):
                        raise ValueError(
                            "fast planner evidence re-entry response is not a JSON object"
                        )
                    from jsonschema import Draft202012Validator
                    Draft202012Validator(response_schema).validate(raw)
                    compact_reentry = PlannerEvidenceReentryModelOutput.model_validate(raw)
                    raw = materialize_evidence_reentry_model_output(
                        compact_reentry,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        allowed_evidence_refs=set(
                            request.planner_reentry_scope.evidence_refs
                        ),
                        completed_step_evidence=completed_work_step_evidence(
                            request.context,
                            reentry_scope=request.planner_reentry_scope,
                        ),
                    )
                else:
                    raw = await self.ollama.generate(
                        fast_layered_prompt(
                            request,
                            capability_payload,
                            response_schema=response_schema,
                            goal_context=goal_context,
                        ),
                        system=fast_system_prompt(),
                        options=options,
                        response_format=response_schema,
                        prompt_family="fast_planner.primary",
                        turn_id=request.sid,
                        attempt=1 + int(bool(loaded_capability_ids)),
                    )
                    if not isinstance(raw, dict):
                        raise ValueError("fast planner response is not a JSON object")
                    needs = take_ability_needs(
                        raw, loaded_capability_ids=[item["capability_id"] for item in capability_payload]
                    )
                    unmet = [item.need for item in needs if item.unmet]
                    found = search_capability_library(
                        unmet, indexed_catalog,
                        loaded_ids={item["capability_id"] for item in capability_payload},
                    ) if unmet and not loaded_capability_ids else []
                    by_id = {item.capability_id: item for item in indexed_catalog}
                    usable = [fast_capability_payload(by_id[key]) for key in found
                              if key in by_id] if found and not response_only else []
                    if usable:
                        # No Plan from this pass is used; plan once with the found contracts.
                        searched = await self._resolve(
                            request, tuple(item["capability_id"] for item in usable)
                        )
                        return searched.model_copy(update={"metadata": {
                            **searched.metadata,
                            **ability_need_metadata(needs, unmet, tuple(item["capability_id"] for item in usable)),
                            "semantic_result_call_count": 1,
                        }})
                    need_metadata = ability_need_metadata(needs, [], ())
                raw, common_repairs = normalize_common_planner_output(
                    raw,
                    authoritative_goals=authoritative_goals,
                    capability_payload=capability_payload,
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
                        fast_multi_goal_contract=multi_goal_contract,
                        completed_step_evidence=completed_work_step_evidence(
                            request.context, reentry_scope=request.planner_reentry_scope),
                        capabilities=capability_payload,
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
                    responsibilities=list(request.responsibilities),
                    authoritative_goals=authoritative_goals,
                    context=request.context,
                    reentry_scope=request.planner_reentry_scope,
                    future_goal_times=future_goal_times,
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
                        acquisition_goal_ids=information_acquisition_goal_ids(plan, capability_payload),
                    )
                except PlannerDTOContractError:
                    raise
                except ValueError as exc:
                    raise AuthoritativeGroundingValidationError(str(exc)) from exc
                try:
                    validate_explicit_numeric_parameter_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                        acquisition_goal_ids=information_acquisition_goal_ids(plan, capability_payload),
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
                # The catalog could cover the Goal by composition, but this Plan does not.
                # That is a Planner defect, not a limitation to report; no second Planner pass.
                logger.warning(
                    "fast_planner_resource_composition_incomplete sid=%s error=%s",
                    request.sid,
                    exc,
                )
                return materialize_planner_failure(
                    plan_id,
                    request,
                    "resource_responsibility_composition_incomplete",
                    unresolved=[str(exc)],
                    metadata={
                        "execution_allowed": False,
                        "resource_composition_required": True,
                    },
                    error=exc,
                )
        except Exception as exc:
                failure = (
                    exc.metadata()
                    if isinstance(exc, RequiredPromptProjectionError)
                    else llm_failure_metadata(exc)
                )
                logger.warning(
                    "fast_planner_inference_failed sid=%s attempt=%s error_type=%s error=%s "
                    "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                    request.sid,
                    failure.get("attempt_count", 1),
                    type(exc).__name__,
                    exc,
                    failure["failure_class"],
                    failure["failure_domain"],
                    failure["architecture_attribution"],
                    failure["retryable"],
                )
                if isinstance(exc, RequiredPromptProjectionError):
                    return materialize_planner_failure(
                        plan_id,
                        request,
                        "fast_planner_required_context_over_budget",
                        metadata=failure,
                    )
                if isinstance(
                    exc, ResourceResponsibilityCapabilityUnavailableError
                ):
                    return materialize_planner_unavailable(
                        plan_id,
                        request,
                        "resource_responsibility_capability_unavailable",
                        unresolved=[str(exc)],
                        metadata={
                            "execution_allowed": False,
                            "resource_contract_unavailable": True,
                        },
                    )
                logger.warning(
                    "fast_planner_contract_failure_evidence sid=%s "
                    "raw_output_ref=%s raw_output=%s",
                    request.sid,
                    cognition_text_reference(raw),
                    bounded_json(raw, 4000) if raw is not None else "",
                )
                integrity_metadata = cognitive_integrity_metadata(
                    stage="fast_planner", exc=exc, request=request
                )
                mechanical_contract_error = isinstance(
                    exc, (PlannerDTOContractError, json.JSONDecodeError, ValidationError)
                )
                authoritative_grounding_failure = isinstance(
                    exc, AuthoritativeGroundingValidationError
                )
                semantic_validation_failure = (
                    isinstance(exc, ValueError)
                    and not mechanical_contract_error
                    and not authoritative_grounding_failure
                )
                return materialize_planner_failure(
                    plan_id,
                    request,
                    (
                        "fast_planner_model_contract_failed"
                        if mechanical_contract_error
                        else "fast_planner_authoritative_grounding_failed"
                        if authoritative_grounding_failure
                        else "fast_planner_semantic_validation_failed"
                        if semantic_validation_failure
                        else "fast_planner_unavailable"
                    ),
                    error=exc,
                    # A rejected model result fails closed; no other model call
                    # repairs contradictory or ungrounded output.
                    metadata={
                        "contract_schema": contract_schema,
                        "canonical_contract": "CanonicalPlan",
                        "initial_raw_output_ref": cognition_text_reference(raw),
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

        reporting_goal_ids |= {condition.goal_id for condition in plan.time_conditions if condition.source_quote}
        qualification = qualify_fast_canonical_plan(
                plan,
                capability_payload=capability_payload,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                authoritative_goals=authoritative_goals,
                evidence_reentry_goal_ids=(
                    reentry_goal_ids | reporting_goal_ids
                ),
                nonfulfilling_response_goal_ids=reporting_goal_ids,
            )
        if not qualification.accepted:
            if qualification.path_classification == "limitation":
                return materialize_planner_unavailable(
                    plan.plan_id,
                    request,
                    qualification.reason,
                    unresolved=list(qualification.unresolved),
                    metadata=qualification.metadata,
                )
            return materialize_planner_failure(
                    plan.plan_id,
                    request,
                    qualification.reason,
                    response_text=plan.response_text,
                    unresolved=list(qualification.unresolved),
                    metadata=qualification.metadata,
                )
        validated = qualification.plan
        if parameter_provenance_repairs:
            metadata = dict(validated.metadata)
            metadata["parameter_provenance_normalization"] = {
                "strategy": "project_mechanically_derivable_provenance",
                "repairs": parameter_provenance_repairs,
                "semantic_plan_unchanged": True,
            }
            validated = validated.model_copy(update={"metadata": metadata})
        if need_metadata:
            validated = validated.model_copy(update={"metadata": {**validated.metadata, **need_metadata}})
        return validated
