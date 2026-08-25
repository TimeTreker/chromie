from __future__ import annotations

import copy
import json
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
    deep_safety_revision_response_schema,
    deep_contract_revision_response_schema,
)
from .planner_context import (
    deep_capability_payload,
    planner_goal_context,
    planner_provider_media_goal_operations,
    planner_provider_vocal_goal_ids,
)
from .planner_validation import (
    coordinated_action_goal_ids,
    explicit_numeric_goal_values,
    information_goal_ids_without_declared_provider,
    normalize_common_planner_output,
    qualify_planner_capability_payload,
    requires_safety_revision,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from .planner_deep_validation import (
    deep_plan_validation_errors,
    deep_validation_error_items,
    detached_numeric_provenance_obligations,
    initial_safety_feedback,
    merge_planner_feedback,
    normalize_mixed_goal_outcome_accounting,
    safety_revision_contract_errors,
    validate_mechanical_numeric_revision_preserved,
)
from .planner_fallback import (
    materialize_deep_clarify,
    materialize_deep_unavailable,
)
from .planner_audit import review_coordinated_action_plan_coverage

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

from .planner_prompt import (
    deep_layered_prompt,
    deep_system_prompt,
    deep_revision_system_prompt,
)


logger = logging.getLogger("chromie.agent.deep_planner")


class DeepPlannerResolver:
    """Terminal full-catalog semantic planner with one bounded mechanical DTO regeneration."""

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
        max_contract_repairs: int = 1,
        min_goal_satisfaction: float = 0.75,
    ) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(256, int(num_predict))
        self.max_capabilities = max(1, min(256, int(max_capabilities)))
        self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))
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
                        "max_contract_repairs": self.max_contract_repairs,
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
        qualified_payload = qualify_planner_capability_payload(
            full_payload,
            authoritative_goals=authoritative_goals,
        )
        payload = qualified_payload[: self.max_capabilities]
        omitted_domain_capability_ids = sorted(
            {
                str(item.get("capability_id") or "")
                for item in full_payload
            }
            - {
                str(item.get("capability_id") or "")
                for item in qualified_payload
            }
        )
        if omitted_domain_capability_ids:
            logger.info(
                "deep_planner_semantic_catalog_qualified sid=%s omitted=%s",
                request.sid,
                omitted_domain_capability_ids,
            )
        unavailable_information_goal_ids = information_goal_ids_without_declared_provider(
            payload,
            authoritative_goals=authoritative_goals,
        )
        if context.get("verified_tool_memory_index"):
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
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=list(goal_context.response_goal_ids),
            provider_vocal_goal_ids=sorted(
                planner_provider_vocal_goal_ids(authoritative_goals)
            ),
            provider_media_goal_operations=(
                planner_provider_media_goal_operations(authoritative_goals)
            ),
            unavailable_information_goal_ids=sorted(
                unavailable_information_goal_ids
            ),
            single_step_goal_ids=single_step_goal_ids,
            required_numeric_goal_values=explicit_numeric_goal_values(
                authoritative_goals
            ),
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
        persistent_safety_feedback = initial_safety_feedback(
            request.context if isinstance(request.context, dict) else {}
        )
        feedback: list[dict[str, Any]] = list(persistent_safety_feedback)
        previous_raw: Any = None
        initial_raw_output: Any = None
        mechanical_numeric_baseline: dict[str, Any] | None = None
        contract_repair_attempted = False
        initial_validation_errors = ""
        for attempt in range(self.max_contract_repairs + 1):
            raw: Any = None
            mixed_accounting_repairs: list[dict[str, Any]] = []
            parameter_provenance_repairs: list[dict[str, Any]] = []
            try:
                active_response_schema = deep_contract_revision_response_schema(
                    response_schema,
                    feedback=feedback,
                    semantic_baseline=mechanical_numeric_baseline,
                )
                if requires_safety_revision(feedback):
                    active_response_schema = deep_safety_revision_response_schema(
                        active_response_schema,
                        feedback=feedback,
                    )
                raw = await self.ollama.generate(
                    deep_layered_prompt(
                        request,
                        payload,
                        feedback=feedback,
                        response_schema=active_response_schema,
                        previous_raw=previous_raw,
                        expected_goal_ids=expected_goal_ids_for_turn,
                    ),
                    system=(deep_revision_system_prompt() if feedback else deep_system_prompt()),
                    options=generation_options,
                    response_format=active_response_schema,
                    prompt_family=("deep_planner.revision" if feedback else "deep_planner.primary"),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise PlannerDTOContractError("deep planner response is not a JSON object")
                if mechanical_numeric_baseline is not None:
                    validate_mechanical_numeric_revision_preserved(
                        raw,
                        baseline=mechanical_numeric_baseline,
                    )
                raw, common_repairs = normalize_common_planner_output(
                    raw,
                    authoritative_goals=authoritative_goals,
                    capability_payload=payload,
                )
                detached_resolution_repairs = common_repairs[
                    "detached_parameter_resolutions"
                ]
                if detached_resolution_repairs:
                    logger.warning(
                        "deep_planner_detached_parameter_resolutions_removed "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(detached_resolution_repairs, 2000),
                    )
                provenance_repairs = common_repairs["schema_default_provenance"]
                if provenance_repairs:
                    logger.info(
                        "deep_planner_schema_default_provenance_normalized "
                        "sid=%s repairs=%s",
                        request.sid,
                        bounded_json(provenance_repairs, 2000),
                    )
                parameter_provenance_repairs = common_repairs[
                    "parameter_provenance"
                ]
                if parameter_provenance_repairs:
                    logger.info(
                        "deep_planner_parameter_provenance_normalized sid=%s repairs=%s",
                        request.sid,
                        bounded_json(parameter_provenance_repairs, 2000),
                    )
                raw, mixed_accounting_repairs = (
                    normalize_mixed_goal_outcome_accounting(
                        raw,
                        expected_goal_ids=expected_goal_ids_for_turn,
                    )
                )
                if mixed_accounting_repairs:
                    logger.info(
                        "deep_planner_mixed_accounting_normalized sid=%s repairs=%s",
                        request.sid,
                        bounded_json(mixed_accounting_repairs, 2000),
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
                            goal_summary_fallback=request.text,
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
                validate_explicit_numeric_parameter_grounding(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                )
                validate_goal_binding_argument_grounding(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                    capabilities=payload,
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
                    "deep_planner_inference_failed sid=%s attempt=%s error_type=%s error=%s "
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
                    return materialize_deep_unavailable(
                        plan_id,
                        request,
                        "resource_responsibility_capability_unavailable",
                        unresolved=[str(exc)],
                        attempts=attempt + 1,
                        metadata={
                            "execution_allowed": False,
                            "resource_contract_unavailable": True,
                        },
                        max_contract_repairs=self.max_contract_repairs,
                    )
                mechanical_contract_error = isinstance(
                    exc, (PlannerDTOContractError, json.JSONDecodeError)
                )
                numeric_obligations = detached_numeric_provenance_obligations(
                    raw,
                    authoritative_goals=authoritative_goals,
                    error=exc,
                )
                if numeric_obligations:
                    # The model has already made the semantic mapping by placing
                    # the exact Goal number in one owned step argument. A missing
                    # duplicate provenance row is a mechanically incomplete DTO,
                    # eligible for the one bounded same-tier regeneration.
                    mechanical_contract_error = True
                if attempt < self.max_contract_repairs and mechanical_contract_error:
                    contract_repair_attempted = True
                    initial_raw_output = raw
                    mechanical_numeric_baseline = (
                        copy.deepcopy(raw)
                        if numeric_obligations and isinstance(raw, dict)
                        else None
                    )
                    # Contract repair is a fresh schema-constrained regeneration,
                    # not an in-place JSON edit.  Supplying the invalid object as
                    # copy text encouraged deployed models to splice validator
                    # fragments into rationale strings instead of rebuilding the
                    # missing fields.
                    previous_raw = None
                    validation_feedback = deep_validation_error_items(
                        exc,
                        raw=raw,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        capability_payload=payload,
                        authoritative_goals=authoritative_goals,
                    )
                    initial_validation_errors = bounded_json(
                        validation_feedback, 12000
                    )
                    logger.warning(
                        "deep_planner_contract_repair_start sid=%s attempt=%s "
                        "validation_errors=%s raw_output_ref=%s raw_output=%s",
                        request.sid,
                        attempt + 1,
                        initial_validation_errors,
                        cognition_text_reference(initial_raw_output),
                        bounded_json(initial_raw_output, 5000),
                    )
                    feedback = merge_planner_feedback(
                        persistent_safety_feedback,
                        feedback,
                        validation_feedback,
                    )
                    continue
                logger.warning(
                    "deep_planner_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s repair_raw_output_ref=%s "
                    "initial_raw_output=%s repair_raw_output=%s",
                    request.sid,
                    cognition_text_reference(initial_raw_output),
                    cognition_text_reference(raw if contract_repair_attempted else None),
                    bounded_json(initial_raw_output, 5000)
                    if initial_raw_output is not None
                    else "",
                    bounded_json(raw, 5000)
                    if contract_repair_attempted and raw is not None
                    else "",
                )
                integrity_metadata = cognitive_integrity_metadata(
                    stage="deep_planner", exc=exc, request=request
                )
                return materialize_deep_clarify(
                    plan_id,
                    request,
                    "deep_planner_model_contract_failed"
                    if contract_repair_attempted or mechanical_contract_error
                    else "deep_planner_semantic_validation_failed",
                    error=exc,
                    attempts=attempt + 1,
                    metadata={
                        "contract_schema": "DeepPlannerModelOutput",
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output_ref": cognition_text_reference(initial_raw_output),
                        "repair_raw_output_ref": cognition_text_reference(
                            raw if contract_repair_attempted else None
                        ),
                        **integrity_metadata,
                    },
                    max_contract_repairs=self.max_contract_repairs,
                )
            errors = deep_plan_validation_errors(
                plan,
                payload,
                expected_goal_ids=expected_goal_ids_for_turn,
                authoritative_goals=authoritative_goals,
                requires_execution=requires_execution,
                min_goal_satisfaction=self.min_goal_satisfaction,
            )
            errors = [
                *safety_revision_contract_errors(plan, feedback),
                *errors,
            ]
            if not errors:
                coverage_review_metadata: dict[str, Any] = {}
                coordinated_goal_ids = coordinated_action_goal_ids(
                    authoritative_goals
                )
                if (
                    coordinated_goal_ids.intersection(plan.goal_ids)
                    and plan.disposition in {"execute", "mixed"}
                    and plan.steps
                ):
                    try:
                        coverage_review = await review_coordinated_action_plan_coverage(
                            self.ollama,
                            request_text=request.text,
                            language=str(request.language or "und"),
                            authoritative_goals=authoritative_goals,
                            plan=plan,
                            capabilities=payload,
                            num_ctx=self.num_ctx,
                        )
                    except Exception as exc:
                        logger.warning(
                            "deep_planner_coverage_review_unavailable sid=%s "
                            "error_type=%s error=%s",
                            request.sid,
                            type(exc).__name__,
                            exc,
                        )
                        return materialize_deep_clarify(
                            plan_id,
                            request,
                            "coordinated_action_coverage_review_unavailable",
                            unresolved=["coordinated_action_coverage"],
                            error=exc,
                            attempts=attempt + 1,
                            metadata={
                                "coordinated_goal_ids": sorted(coordinated_goal_ids),
                                "execution_allowed": False,
                            },
                            max_contract_repairs=self.max_contract_repairs,
                        )
                    if coverage_review.decision != "accept":
                        review_error = {
                            "type": "coordinated_action_coverage_incomplete",
                            "uncovered_requirements": list(coverage_review.uncovered_requirements),
                            "reason": coverage_review.reason,
                            "confidence": coverage_review.confidence,
                        }
                        logger.warning(
                            "deep_planner_coverage_review_rejected sid=%s "
                            "attempt=%s uncovered=%s reason=%s",
                            request.sid,
                            attempt + 1,
                            coverage_review.uncovered_requirements,
                            coverage_review.reason,
                        )
                        return materialize_deep_clarify(
                            plan_id,
                            request,
                            "coordinated_action_coverage_incomplete",
                            unresolved=coverage_review.uncovered_requirements,
                            metadata={
                                "validation_feedback": [review_error],
                                "coordinated_goal_ids": sorted(coordinated_goal_ids),
                                "execution_allowed": False,
                            },
                            attempts=attempt + 1,
                            max_contract_repairs=self.max_contract_repairs,
                        )
                    coverage_review_metadata["coverage_review"] = {
                        "status": "accepted",
                        "confidence": coverage_review.confidence,
                        "reason": coverage_review.reason,
                        "execution_authority": "none",
                    }
                metadata = dict(plan.metadata)
                metadata.update(
                    {
                        "resolver": "deep_planner",
                        "status": "complete" if plan.coverage == "complete" else plan.disposition,
                        "authority": "advisory",
                        "attempt_count": attempt + 1,
                        "full_capability_count": len(payload),
                        "max_contract_repairs": self.max_contract_repairs,
                        "min_goal_satisfaction": self.min_goal_satisfaction,
                        "contract_schema": "DeepPlannerModelOutput",
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": contract_repair_attempted,
                    }
                )
                metadata.update(coverage_review_metadata)
                if parameter_provenance_repairs:
                    metadata["parameter_provenance_normalization"] = {
                        "strategy": "project_mechanically_derivable_provenance",
                        "repairs": parameter_provenance_repairs,
                        "semantic_plan_unchanged": True,
                    }
                if mixed_accounting_repairs:
                    metadata["mixed_goal_accounting_recovery"] = {
                        "strategy": (
                            "preserve_per_goal_outcomes_and_remove_unowned_steps"
                        ),
                        "repairs": mixed_accounting_repairs,
                        "semantic_outcomes_unchanged": True,
                    }
                if contract_repair_attempted:
                    metadata["contract_repair"] = {
                        "attempted": True,
                        "succeeded": True,
                        "strategy": "schema_constrained_model_revision",
                        "attempt_count": 1,
                    }
                    logger.info(
                        "deep_planner_contract_repair_done sid=%s status=success",
                        request.sid,
                    )
                return plan.model_copy(update={"metadata": metadata})
            mechanical_error_types = {
                "invalid_args",
                "parameter_resolution_unknown_step",
                "missing_goal_satisfaction",
            }
            if (
                attempt < self.max_contract_repairs
                and errors
                and all(str(item.get("type") or "") in mechanical_error_types for item in errors)
            ):
                contract_repair_attempted = True
                initial_raw_output = raw
                initial_validation_errors = bounded_json(errors, 12000)
                feedback = merge_planner_feedback(
                    persistent_safety_feedback,
                    errors,
                )
                previous_raw = None
                logger.warning(
                    "deep_planner_contract_repair_start sid=%s attempt=%s validation_errors=%s",
                    request.sid,
                    attempt + 1,
                    initial_validation_errors,
                )
                continue
            return materialize_deep_clarify(
                plan_id,
                request,
                "deep_planner_semantic_validation_rejected",
                unresolved=[
                    item.get("step_id") or item.get("capability_id") or item["type"] for item in errors
                ],
                metadata={
                    "validation_feedback": errors,
                    "contract_schema": "DeepPlannerModelOutput",
                    "canonical_contract": "CanonicalPlan",
                    "initial_raw_output_ref": cognition_text_reference(initial_raw_output),
                    "repair_raw_output_ref": cognition_text_reference(
                        raw if contract_repair_attempted else None
                    ),
                },
                attempts=attempt + 1,
                max_contract_repairs=self.max_contract_repairs,
            )
        raise AssertionError("unreachable")
