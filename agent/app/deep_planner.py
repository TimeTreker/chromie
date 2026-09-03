from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import OllamaClient, llm_failure_metadata

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
from .prompt_projection import bounded_json
from .planner_model_contract import (
    PlannerDTOContractError,
    ResourceResponsibilityCapabilityUnavailableError,
    is_planner_step_capability,
    materialize_planner_output,
    stable_plan_id,
)
from .planner_schema import (
    canonical_goal_binding_argument_response_schema,
    canonical_resource_argument_response_schema,
    deep_plan_response_schema,
)
from .planner_context import (
    auxiliary_social_capability_payloads,
    auxiliary_social_prompt_context,
    deep_capability_payload,
    planner_goal_context,
    planner_provider_media_goal_operations,
    planner_provider_vocal_goal_ids,
)
from .planner_validation import (
    explicit_numeric_goal_values,
    information_goal_ids_without_declared_provider,
    normalize_common_planner_output,
    qualify_planner_capability_payload,
    resource_goal_ids_without_complete_provider_contract,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from .planner_deep_validation import deep_plan_validation_errors
from .planner_fallback import (
    materialize_deep_clarify,
    materialize_deep_unavailable,
)

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

from .planner_prompt import (
    deep_layered_prompt,
    deep_system_prompt,
)


logger = logging.getLogger("chromie.agent.deep_planner")


class DeepPlannerResolver:
    """Terminal full-catalog semantic planner with one primary model invocation."""

    TRACE_MODULE = TraceModule(
        name="agent.deep_planner",
        component_type="planner",
        implementation="DeepPlannerResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        catalog: CapabilityCatalog,
        *,
        num_ctx: int = 8192,
        num_predict: int = 1024,
        max_capabilities: int = 96,
        min_goal_satisfaction: float = 0.75,
    ) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(256, int(num_predict))
        self.max_capabilities = max(1, min(256, int(max_capabilities)))
        self.min_goal_satisfaction = max(0.0, min(1.0, float(min_goal_satisfaction)))

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
                    if result.metadata.get("failure_class"):
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: CognitiveWorkRequest) -> CanonicalPlan:
        plan_id = stable_plan_id(request, "deep")
        context = request.context if isinstance(request.context, dict) else {}
        goal_context = planner_goal_context(
            context,
            reentry_scope=request.planner_reentry_scope,
        )
        expected_goal_ids_for_turn = list(goal_context.expected_goal_ids)
        authoritative_goals = list(goal_context.authoritative_goals)
        response_only = goal_context.response_only
        requires_execution = goal_context.requires_execution
        capabilities = await self.catalog.prompt_entries(scope="all", refresh=False)
        auxiliary_social_capabilities = auxiliary_social_capability_payloads(capabilities)
        context["planner_auxiliary_social_context"] = auxiliary_social_prompt_context(
            context,
            auxiliary_social_capabilities,
        )
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_capability(item.capability_id)
        ]
        if response_only:
            executable = []
        full_payload = [deep_capability_payload(item) for item in executable]
        # Deep is the composition pass. It must see the complete available
        # catalog (within its explicit size bound); filtering each Capability
        # against the whole Goal would erase components needed for multi-step
        # or Evidence-reentry plans before the model can compose them.
        payload = full_payload[: self.max_capabilities]
        omitted_domain_capability_ids = sorted(
            {str(item.get("capability_id") or "") for item in full_payload}
            - {str(item.get("capability_id") or "") for item in payload}
        )
        if omitted_domain_capability_ids:
            logger.info(
                "deep_planner_catalog_size_bounded sid=%s omitted=%s",
                request.sid,
                omitted_domain_capability_ids,
            )
        unavailable_information_goal_ids = information_goal_ids_without_declared_provider(
            payload,
            authoritative_goals=authoritative_goals,
        )
        unavailable_resource_goal_ids = resource_goal_ids_without_complete_provider_contract(
            payload,
            authoritative_goals=authoritative_goals,
        )
        if context.get("verified_tool_memory_index"):
            unavailable_resource_goal_ids -= set(unavailable_information_goal_ids)
            # A fresh exact memory entry may satisfy a typed information Goal via
            # its original provider contract; the Planner and evidence validator
            # retain authority over that match.
            unavailable_information_goal_ids.clear()
        single_step_goal_ids = [
            str(goal.get("goal_id") or "").strip()
            for goal in authoritative_goals
            if isinstance(goal, dict)
            and str(goal.get("goal_id") or "").strip()
            and not goal.get("resource_responsibility")
            and isinstance(goal.get("metadata"), dict)
            and str(goal["metadata"].get("output_mode") or "").strip()
            in {"body_action", "media_playback", "stateful_effect"}
        ]
        response_schema = deep_plan_response_schema(
            expected_goal_ids_for_turn,
            allowed_capability_ids=[item["capability_id"] for item in payload],
            capability_input_schemas={
                item["capability_id"]: item["input_schema"] for item in payload
            },
            auxiliary_social_capabilities=auxiliary_social_capabilities,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=list(goal_context.response_goal_ids),
            provider_vocal_goal_ids=sorted(planner_provider_vocal_goal_ids(authoritative_goals)),
            provider_media_goal_operations=(
                planner_provider_media_goal_operations(authoritative_goals)
            ),
            unavailable_information_goal_ids=sorted(unavailable_information_goal_ids),
            unavailable_resource_goal_ids=sorted(unavailable_resource_goal_ids),
            single_step_goal_ids=single_step_goal_ids,
            required_numeric_goal_values=explicit_numeric_goal_values(authoritative_goals),
            confirmation_required_capability_ids=[
                item["capability_id"] for item in payload if item.get("requires_confirmation")
            ],
            nonparallel_capability_ids=[
                item["capability_id"] for item in payload if item.get("can_run_parallel") is False
            ],
        )
        response_schema = canonical_resource_argument_response_schema(
            response_schema,
            authoritative_goals=authoritative_goals,
        )
        response_schema = canonical_goal_binding_argument_response_schema(
            response_schema,
            authoritative_goals=authoritative_goals,
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        raw: Any = None
        parameter_provenance_repairs: list[dict[str, Any]] = []
        try:
            raw = await self.ollama.generate(
                deep_layered_prompt(
                    request,
                    payload,
                    response_schema=response_schema,
                    expected_goal_ids=expected_goal_ids_for_turn,
                    minimum_goal_satisfaction=self.min_goal_satisfaction,
                ),
                system=deep_system_prompt(),
                options=generation_options,
                response_format=response_schema,
                prompt_family="deep_planner.primary",
                turn_id=request.sid,
                attempt=1,
            )
            if not isinstance(raw, dict):
                raise PlannerDTOContractError("deep planner response is not a JSON object")
            raw, common_repairs = normalize_common_planner_output(
                raw,
                authoritative_goals=authoritative_goals,
                capability_payload=payload,
            )
            detached_resolution_repairs = common_repairs["detached_parameter_resolutions"]
            if detached_resolution_repairs:
                logger.warning(
                    "deep_planner_detached_parameter_resolutions_removed sid=%s repairs=%s",
                    request.sid,
                    bounded_json(detached_resolution_repairs, 2000),
                )
            provenance_repairs = common_repairs["schema_default_provenance"]
            if provenance_repairs:
                logger.info(
                    "deep_planner_schema_default_provenance_normalized sid=%s repairs=%s",
                    request.sid,
                    bounded_json(provenance_repairs, 2000),
                )
            parameter_provenance_repairs = common_repairs["parameter_provenance"]
            if parameter_provenance_repairs:
                logger.info(
                    "deep_planner_parameter_provenance_normalized sid=%s repairs=%s",
                    request.sid,
                    bounded_json(parameter_provenance_repairs, 2000),
                )
            try:
                validated_model_output = validate_planner_model_output(
                    raw,
                    planner_tier="deep",
                    expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                )
                plan = CanonicalPlan.model_validate(
                    materialize_planner_output(
                        validated_model_output,
                        planner_tier="deep",
                        plan_id=plan_id,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                )
            except (ValidationError, ValueError) as exc:
                if isinstance(exc, PlannerDTOContractError):
                    raise
                raise PlannerDTOContractError(str(exc)) from exc

            validate_goal_responsibility_outcomes(
                validated_model_output,
                authoritative_goals=authoritative_goals,
                context=request.context,
            )
            validate_resource_responsibility_capability_grounding(
                validated_model_output,
                authoritative_goals=authoritative_goals,
                capabilities=payload,
            )
            validate_goal_binding_argument_grounding(
                validated_model_output,
                authoritative_goals=authoritative_goals,
                capabilities=payload,
            )
            validate_explicit_numeric_parameter_grounding(
                validated_model_output,
                authoritative_goals=authoritative_goals,
            )
            validate_user_supplied_parameter_provenance(
                validated_model_output,
                authoritative_goals=authoritative_goals,
            )
            validate_external_response_evidence_boundary(
                validated_model_output,
                context=request.context,
                authoritative_goals=authoritative_goals,
            )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.warning(
                "deep_planner_inference_failed sid=%s attempt=1 error_type=%s error=%s "
                "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
            )
            if isinstance(exc, ResourceResponsibilityCapabilityUnavailableError):
                return materialize_deep_unavailable(
                    plan_id,
                    request,
                    "resource_responsibility_capability_unavailable",
                    unresolved=[str(exc)],
                    attempts=1,
                    metadata={
                        "execution_allowed": False,
                        "resource_contract_unavailable": True,
                    },
                )
            logger.warning(
                "deep_planner_contract_failure_evidence sid=%s raw_output_ref=%s raw_output=%s",
                request.sid,
                cognition_text_reference(raw),
                bounded_json(raw, 5000) if raw is not None else "",
            )
            integrity_metadata = cognitive_integrity_metadata(
                stage="deep_planner", exc=exc, request=request
            )
            return materialize_deep_clarify(
                plan_id,
                request,
                (
                    "deep_planner_model_contract_failed"
                    if isinstance(exc, PlannerDTOContractError)
                    else "deep_planner_semantic_validation_failed"
                ),
                error=exc,
                attempts=1,
                metadata={
                    "contract_schema": "DeepPlannerModelOutput",
                    "canonical_contract": "CanonicalPlan",
                    "raw_output_ref": cognition_text_reference(raw),
                    **integrity_metadata,
                },
            )

        errors = deep_plan_validation_errors(
            plan,
            payload,
            expected_goal_ids=expected_goal_ids_for_turn,
            authoritative_goals=authoritative_goals,
            requires_execution=requires_execution,
            min_goal_satisfaction=self.min_goal_satisfaction,
            allows_evidence_response=bool(
                context.get("result_evidence_reentry") or context.get("goal_cancellation_reentry")
            ),
        )
        if errors:
            return materialize_deep_clarify(
                plan_id,
                request,
                "deep_planner_semantic_validation_rejected",
                unresolved=[
                    item.get("step_id") or item.get("capability_id") or item["type"]
                    for item in errors
                ],
                metadata={
                    "validation_feedback": errors,
                    "contract_schema": "DeepPlannerModelOutput",
                    "canonical_contract": "CanonicalPlan",
                    "raw_output_ref": cognition_text_reference(raw),
                },
                attempts=1,
            )

        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "deep_planner",
                "status": ("complete" if plan.coverage == "complete" else plan.disposition),
                "authority": "advisory",
                "attempt_count": 1,
                "full_capability_count": len(payload),
                "min_goal_satisfaction": self.min_goal_satisfaction,
                "contract_schema": "DeepPlannerModelOutput",
                "canonical_contract": "CanonicalPlan",
            }
        )
        if parameter_provenance_repairs:
            metadata["parameter_provenance_normalization"] = {
                "strategy": "project_mechanically_derivable_provenance",
                "repairs": parameter_provenance_repairs,
                "semantic_plan_unchanged": True,
            }
        return plan.model_copy(update={"metadata": metadata})
