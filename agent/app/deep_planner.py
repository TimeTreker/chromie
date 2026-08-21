from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .capabilities.validator import validate_args_for_schema
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
from .planner_contract import (
    PlannerDTOContractError,
    ResourceResponsibilityCapabilityUnavailableError,
    canonical_goal_binding_argument_response_schema,
    canonical_resource_argument_response_schema,
    canonical_goal_grounding,
    canonical_plan_response_schema,
    coordinated_action_goal_ids,
    expected_goal_ids,
    explicit_numeric_goal_values,
    information_goal_ids_without_declared_provider,
    is_planner_step_capability,
    materialize_goal_outcomes,
    materialize_planner_metadata,
    normalize_detached_parameter_resolutions,
    normalize_missing_numeric_parameter_provenance,
    normalize_schema_default_parameter_provenance,
    parallel_plan_contract_errors,
    planner_goal_execution_requirements,
    planner_provider_media_goal_operations,
    planner_provider_vocal_goal_ids,
    planner_response_goal_ids,
    planner_contract_diagnostics,
    qualify_capability_catalog_for_information_domains,
    qualify_capability_catalog_for_output_modes,
    review_coordinated_action_plan_coverage,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)

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
        min_confidence: float = 0.65,
        num_ctx: int = 8192,
        num_predict: int = 1024,
        max_capabilities: int = 96,
        max_contract_repairs: int = 1,
        min_goal_satisfaction: float = 0.75,
    ) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
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
        plan_id = self._plan_id(request)
        context = request.context if isinstance(request.context, dict) else {}
        expected_goal_ids_for_turn = expected_goal_ids(context)
        authoritative_goals = canonical_goal_grounding(context)
        response_only, requires_execution = planner_goal_execution_requirements(
            authoritative_goals
        )
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
        full_payload = [self._capability_payload(item) for item in executable]
        output_mode_qualified_payload = qualify_capability_catalog_for_output_modes(
            full_payload,
            authoritative_goals=authoritative_goals,
        )
        qualified_payload = qualify_capability_catalog_for_information_domains(
            output_mode_qualified_payload,
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
                "deep_planner_information_domain_catalog_qualified sid=%s omitted=%s",
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
            and str(goal["metadata"].get("responsibility_kind") or "").strip()
            in {"executable_action", "capability_dependent"}
        ]
        response_schema = self._response_schema(
            expected_goal_ids_for_turn,
            allowed_capability_ids=[item["capability_id"] for item in payload],
            capability_input_schemas={
                item["capability_id"]: item["input_schema"] for item in payload
            },
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=sorted(planner_response_goal_ids(authoritative_goals)),
            provider_required_vocal_goal_ids=sorted(
                planner_provider_vocal_goal_ids(authoritative_goals)
            ),
            provider_required_media_goal_operations=(
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
        persistent_safety_feedback = self._initial_safety_feedback(
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
            numeric_provenance_repairs: list[dict[str, Any]] = []
            try:
                active_response_schema = self._contract_revision_response_schema(
                    response_schema,
                    feedback=feedback,
                    semantic_baseline=mechanical_numeric_baseline,
                )
                if self._requires_safety_revision(feedback):
                    active_response_schema = self._safety_revision_response_schema(
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
                    self._validate_mechanical_numeric_revision_preserved(
                        raw,
                        baseline=mechanical_numeric_baseline,
                    )
                raw, detached_resolution_repairs = (
                    normalize_detached_parameter_resolutions(raw)
                )
                if detached_resolution_repairs:
                    logger.warning(
                        "deep_planner_detached_parameter_resolutions_removed "
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
                        capability_payload=payload,
                    )
                )
                if provenance_repairs:
                    logger.info(
                        "deep_planner_schema_default_provenance_normalized "
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
                        "deep_planner_numeric_provenance_normalized sid=%s repairs=%s",
                        request.sid,
                        self._bounded(numeric_provenance_repairs, 2000),
                    )
                raw, mixed_accounting_repairs = (
                    self._normalize_mixed_goal_outcome_accounting(
                        raw,
                        expected_goal_ids=expected_goal_ids_for_turn,
                    )
                )
                if mixed_accounting_repairs:
                    logger.info(
                        "deep_planner_mixed_accounting_normalized sid=%s repairs=%s",
                        request.sid,
                        self._bounded(mixed_accounting_repairs, 2000),
                    )
                try:
                    self._validate_parallel_timing_preservation(
                        raw,
                        context=request.context,
                    )
                    plan = CanonicalPlan.model_validate(
                        self._normalize(
                            raw,
                            request=request,
                            plan_id=plan_id,
                            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                            capability_payload=payload,
                        )
                    )
                    validated_model_output = validate_planner_model_output(
                        raw,
                        planner_tier="deep",
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                except (ValidationError, ValueError) as exc:
                    if isinstance(exc, PlannerDTOContractError):
                        raise
                    raise PlannerDTOContractError(str(exc)) from exc

                validate_goal_responsibility_outcomes(
                    validated_model_output,
                    authoritative_goals=canonical_goal_grounding(request.context),
                    context=request.context,
                )
                validate_resource_responsibility_capability_grounding(
                    validated_model_output,
                    authoritative_goals=canonical_goal_grounding(request.context),
                    capabilities=payload,
                )
                validate_explicit_numeric_parameter_grounding(
                    validated_model_output,
                    authoritative_goals=canonical_goal_grounding(request.context),
                )
                validate_goal_binding_argument_grounding(
                    validated_model_output,
                    authoritative_goals=canonical_goal_grounding(request.context),
                    capabilities=payload,
                )
                validate_user_supplied_parameter_provenance(
                    validated_model_output,
                    authoritative_goals=canonical_goal_grounding(request.context),
                )
                validate_external_response_evidence_boundary(
                    validated_model_output,
                    context=request.context,
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
                    return self._unavailable(
                        plan_id,
                        request,
                        "resource_responsibility_capability_unavailable",
                        unresolved=[str(exc)],
                        attempts=attempt + 1,
                        metadata={
                            "execution_allowed": False,
                            "resource_contract_unavailable": True,
                        },
                    )
                mechanical_contract_error = isinstance(
                    exc, (PlannerDTOContractError, json.JSONDecodeError)
                )
                numeric_obligations = self._detached_numeric_provenance_obligations(
                    raw,
                    authoritative_goals=canonical_goal_grounding(request.context),
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
                    validation_feedback = self._validation_error_items(
                        exc,
                        raw=raw,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                        capability_payload=payload,
                        authoritative_goals=canonical_goal_grounding(
                            request.context
                        ),
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
                        self._bounded(initial_raw_output, 5000),
                    )
                    feedback = self._merge_feedback(
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
                    self._bounded(initial_raw_output, 5000)
                    if initial_raw_output is not None
                    else "",
                    self._bounded(raw, 5000)
                    if contract_repair_attempted and raw is not None
                    else "",
                )
                integrity_metadata = cognitive_integrity_metadata(
                    stage="deep_planner", exc=exc, request=request
                )
                return self._clarify(
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
                )
            errors = self._validation_errors(
                plan,
                payload,
                expected_goal_ids=expected_goal_ids_for_turn,
                request=request,
            )
            errors = [
                *self._safety_revision_contract_errors(plan, feedback),
                *errors,
            ]
            if not errors:
                coverage_review_metadata: dict[str, Any] = {}
                coordinated_goal_ids = coordinated_action_goal_ids(
                    canonical_goal_grounding(request.context)
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
                            authoritative_goals=canonical_goal_grounding(request.context),
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
                        return self._clarify(
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
                        return self._clarify(
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
                if numeric_provenance_repairs:
                    metadata["numeric_provenance_normalization"] = {
                        "strategy": "copy_exact_owned_step_argument",
                        "repairs": numeric_provenance_repairs,
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
                feedback = self._merge_feedback(
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
            return self._clarify(
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
            )
        raise AssertionError("unreachable")


    @staticmethod
    def _validation_error_items(
        exc: Exception,
        *,
        raw: Any,
        expected_goal_ids_for_turn: list[str],
        capability_payload: list[dict[str, Any]] | None = None,
        authoritative_goals: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(exc, ValidationError):
            feedback = list(exc.errors(include_url=False))
        else:
            feedback = [
                {
                    "type": "canonical_plan_contract_validation_failure",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
            ]
        feedback.extend(
            planner_contract_diagnostics(
                raw,
                planner_tier="deep",
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
        )
        if isinstance(raw, dict):
            schemas = {
                str(item.get("capability_id") or ""): item.get("input_schema") or {}
                for item in list(capability_payload or [])
            }
            steps = {
                str(item.get("step_id") or ""): item
                for item in raw.get("steps") or []
                if isinstance(item, dict) and str(item.get("step_id") or "").strip()
            }
            for resolution in raw.get("parameter_resolutions") or []:
                if not isinstance(resolution, dict):
                    continue
                step_id = str(resolution.get("step_id") or "").strip()
                parameter = str(resolution.get("parameter") or "").strip()
                step = steps.get(step_id)
                if not parameter or not isinstance(step, dict):
                    continue
                args = step.get("args") if isinstance(step.get("args"), dict) else {}
                if parameter in args:
                    continue
                capability_id = str(step.get("capability_id") or "").strip()
                feedback.append(
                    {
                        "type": "parameter_resolution_argument_mismatch",
                        "step_id": step_id,
                        "capability_id": capability_id,
                        "parameter": parameter,
                        "resolution_value": resolution.get("value"),
                        "resolution_strategy": resolution.get("strategy"),
                        "source_goal_ids": list(resolution.get("source_goal_ids") or []),
                        "actual_arg_keys": sorted(args),
                        "capability_input_schema": schemas.get(capability_id, {}),
                        "corrective_contract": (
                            "A nonblocking parameter_resolution must name an argument "
                            "present in the referenced step args with the same value. "
                            "If the value came from an authoritative Goal, use strategy "
                            "user_supplied. Regenerate a schema-valid consistent step "
                            "and resolution or return a non-executable clarification; "
                            "do not describe an absent argument only in prose."
                        ),
                    }
                )
            if "no matching user_supplied parameter resolution" in str(exc):
                for resolution in raw.get("parameter_resolutions") or []:
                    if not isinstance(resolution, dict):
                        continue
                    if str(resolution.get("strategy") or "") == "user_supplied":
                        continue
                    value = resolution.get("value")
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    step_id = str(resolution.get("step_id") or "").strip()
                    step = steps.get(step_id)
                    if not isinstance(step, dict):
                        continue
                    feedback.append(
                        {
                            "type": "explicit_numeric_resolution_strategy_mismatch",
                            "step_id": step_id,
                            "capability_id": str(
                                step.get("capability_id") or ""
                            ).strip(),
                            "parameter": str(
                                resolution.get("parameter") or ""
                            ).strip(),
                            "resolution_value": value,
                            "actual_strategy": resolution.get("strategy"),
                            "source_goal_ids": list(
                                resolution.get("source_goal_ids") or []
                            ),
                            "corrective_contract": (
                                "A numeric value copied from an authoritative Goal "
                                "must use strategy user_supplied, equal the referenced "
                                "step argument, and cite that Goal in source_goal_ids."
                            ),
                        }
                    )
            if "numeric user_supplied parameter resolution is not present" in str(exc):
                for resolution in raw.get("parameter_resolutions") or []:
                    if not isinstance(resolution, dict):
                        continue
                    if str(resolution.get("strategy") or "") != "user_supplied":
                        continue
                    step_id = str(resolution.get("step_id") or "").strip()
                    step = steps.get(step_id)
                    if not isinstance(step, dict):
                        continue
                    capability_id = str(step.get("capability_id") or "").strip()
                    parameter = str(resolution.get("parameter") or "").strip()
                    parameter_schema = (
                        schemas.get(capability_id, {})
                        .get("properties", {})
                        .get(parameter, {})
                    )
                    feedback.append(
                        {
                            "type": "unsupported_user_supplied_provenance",
                            "step_id": step_id,
                            "capability_id": capability_id,
                            "parameter": parameter,
                            "resolution_value": resolution.get("value"),
                            "source_goal_ids": list(
                                resolution.get("source_goal_ids") or []
                            ),
                            "catalog_parameter_schema": parameter_schema,
                            "corrective_contract": (
                                "This value is absent from every cited owning Goal. "
                                "Never borrow a sibling Goal's quantity. If the owning "
                                "Goal omitted this optional parameter, omit the argument "
                                "and resolution, or use the exact catalog default with "
                                "strategy schema_default and no source_goal_ids."
                            ),
                        }
                    )
            for obligation in DeepPlannerResolver._detached_numeric_provenance_obligations(
                raw,
                authoritative_goals=list(authoritative_goals or []),
                error=exc,
            ):
                feedback.append(
                    {
                        "type": "missing_user_supplied_parameter_resolution",
                        **obligation,
                        "corrective_contract": (
                            "The semantic mapping already exists in exactly one owned "
                            "step argument. Preserve the plan meaning and add one "
                            "nonblocking parameter_resolution with this exact step_id, "
                            "parameter, numeric value, strategy=user_supplied, and sole "
                            "source Goal. Do not add, remove, or substitute work."
                        ),
                    }
                )
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[Any, ...]]] = set()
        for item in feedback:
            message = str(item.get("msg") or item.get("message") or "")
            location = tuple(item.get("loc") or [])
            key = (
                message
                or json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
                location,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _detached_numeric_provenance_obligations(
        raw: Any,
        *,
        authoritative_goals: list[dict[str, Any]],
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Identify only unambiguous missing duplicate numeric provenance rows."""

        if (
            "explicit numeric goal value has no matching user_supplied "
            "parameter resolution" not in str(error)
            or not isinstance(raw, dict)
        ):
            return []
        numeric_by_goal = explicit_numeric_goal_values(authoritative_goals)
        outcomes = raw.get("goal_outcomes")
        steps = raw.get("steps")
        resolutions = raw.get("parameter_resolutions")
        if not isinstance(steps, list):
            return []
        outcomes = outcomes if isinstance(outcomes, dict) else {}
        resolutions = resolutions if isinstance(resolutions, list) else []
        step_owned_goal_ids = {
            str(goal_id)
            for step in steps
            if isinstance(step, dict)
            for goal_id in step.get("source_goal_ids") or []
            if str(goal_id).strip()
        }

        def numeric(value: Any) -> float | None:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                return None
            try:
                return float(str(value).strip())
            except ValueError:
                return None

        obligations: list[dict[str, Any]] = []
        for goal_id, values in numeric_by_goal.items():
            outcome = outcomes.get(goal_id)
            if isinstance(outcome, dict):
                if outcome.get("disposition") != "execute":
                    continue
            elif goal_id not in step_owned_goal_ids:
                continue
            for value in values:
                candidates: list[tuple[str, str]] = []
                for step in steps:
                    if not isinstance(step, dict) or goal_id not in (
                        step.get("source_goal_ids") or []
                    ):
                        continue
                    step_id = " ".join(str(step.get("step_id") or "").strip().split())
                    args = step.get("args")
                    if not step_id or not isinstance(args, dict):
                        continue
                    for parameter, argument in args.items():
                        argument_number = numeric(argument)
                        if argument_number is None:
                            continue
                        scale = max(abs(float(value)), abs(argument_number), 1.0)
                        if abs(float(value) - argument_number) <= 1e-12 * scale:
                            candidates.append((step_id, str(parameter)))
                if len(candidates) != 1:
                    return []
                step_id, parameter = candidates[0]
                already_present = any(
                    isinstance(resolution, dict)
                    and str(resolution.get("strategy") or "") == "user_supplied"
                    and str(resolution.get("step_id") or "").strip() == step_id
                    and str(resolution.get("parameter") or "").strip() == parameter
                    and resolution.get("source_goal_ids") == [goal_id]
                    and numeric(resolution.get("value")) is not None
                    and abs(
                        float(value)
                        - float(numeric(resolution.get("value")) or 0.0)
                    )
                    <= 1e-12 * max(abs(float(value)), 1.0)
                    for resolution in resolutions
                )
                if already_present:
                    continue
                obligations.append(
                    {
                        "step_id": step_id,
                        "parameter": parameter,
                        "value": value,
                        "source_goal_ids": [goal_id],
                    }
                )
        return obligations

    @staticmethod
    def _validation_error_json(
        exc: Exception,
        *,
        raw: Any,
        expected_goal_ids_for_turn: list[str],
    ) -> str:
        """Compatibility helper for focused callers outside the resolve loop."""

        return bounded_json(
            DeepPlannerResolver._validation_error_items(
                exc,
                raw=raw,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            ),
            12000,
        )

    @staticmethod
    def _capability_payload(item: Any) -> dict[str, Any]:
        return {
            "capability_id": item.capability_id,
            "description": item.description,
            "input_schema": item.input_schema,
            "available": item.available,
            "interaction_executable": item.interaction_executable,
            "requires_confirmation": item.requires_confirmation,
            "effects": item.effects,
            "safety_class": item.safety_class,
            "can_run_parallel": item.can_run_parallel,
            "parallel_metadata_declared": item.parallel_metadata_declared,
            "exclusive_group": item.exclusive_group,
            "resource_claims": item.resource_claims,
            "execution_constraints": item.execution_constraints,
            "hints": dict(item.hints),
        }

    @staticmethod
    def _plan_id(request: CognitiveWorkRequest) -> str:
        digest = hashlib.sha256(
            f"{request.sid or 'turn'}|deep|{request.text}".encode()
        ).hexdigest()[:20]
        return f"plan_{digest}"

    @classmethod
    def _response_schema(
        cls,
        expected_goal_ids: list[str],
        *,
        allowed_capability_ids: list[str] | None = None,
        capability_input_schemas: dict[str, dict[str, Any]] | None = None,
        response_only: bool = False,
        requires_execution: bool = False,
        response_goal_ids: list[str] | None = None,
        provider_required_vocal_goal_ids: list[str] | None = None,
        provider_required_media_goal_operations: dict[str, str] | None = None,
        unavailable_information_goal_ids: list[str] | None = None,
        single_step_goal_ids: list[str] | None = None,
        required_numeric_goal_values: dict[str, list[int | float]] | None = None,
    ) -> dict[str, Any]:
        return canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=expected_goal_ids,
            allowed_capability_ids=list(allowed_capability_ids or []),
            capability_input_schemas=capability_input_schemas,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
            provider_required_vocal_goal_ids=(provider_required_vocal_goal_ids),
            provider_required_media_goal_operations=(provider_required_media_goal_operations),
            unavailable_information_goal_ids=unavailable_information_goal_ids,
            single_step_goal_ids=single_step_goal_ids,
            required_numeric_goal_values=required_numeric_goal_values,
        )

    @staticmethod
    def _requires_safety_revision(feedback: list[dict[str, Any]]) -> bool:
        safety_types = {
            "parallel_capability_not_declared_safe",
            "parallel_exclusive_group_conflict",
            "parallel_resource_claim_conflict",
            "safety_revision_contract_not_satisfied",
        }
        return any(
            isinstance(item, dict)
            and item.get("type") in safety_types
            and not (
                item.get("type") == "parallel_capability_not_declared_safe"
                and item.get("parallel_step_count") == 1
            )
            for item in feedback
        )

    @staticmethod
    def _requires_sequential_safety_revision(
        feedback: list[dict[str, Any]],
    ) -> bool:
        concurrency_types = {
            "parallel_capability_not_declared_safe",
            "parallel_exclusive_group_conflict",
            "parallel_resource_claim_conflict",
        }
        return any(
            isinstance(item, dict)
            and item.get("type") in concurrency_types
            and not (
                item.get("type") == "parallel_capability_not_declared_safe"
                and item.get("parallel_step_count") == 1
            )
            for item in feedback
        )

    @classmethod
    def _initial_safety_feedback(
        cls,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Carry upstream deterministic safety findings into Deep attempt one."""

        candidates: list[dict[str, Any]] = []
        fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution")
        if isinstance(fast_plan, dict):
            metadata = fast_plan.get("metadata")
            if isinstance(metadata, dict):
                parallel_errors = metadata.get("parallel_contract_errors")
                # A lone step labeled parallel has no overlap relation to
                # revise.  Carry this finding only when Fast actually proposed
                # a multi-step concurrency plan; otherwise Deep may safely
                # regenerate the single step as sequential.
                if (
                    isinstance(parallel_errors, list)
                    and int(metadata.get("executable_step_count") or 0) > 1
                ):
                    candidates.extend(item for item in parallel_errors if isinstance(item, dict))
        runtime_feedback = context.get("runtime_validator_feedback")
        if isinstance(runtime_feedback, list):
            candidates.extend(item for item in runtime_feedback if isinstance(item, dict))
        return [
            dict(item)
            for item in cls._merge_feedback(candidates)
            if cls._requires_safety_revision([item])
        ]

    @staticmethod
    def _merge_feedback(
        *groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for group in groups:
            for item in group:
                if not isinstance(item, dict):
                    continue
                key = json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    @staticmethod
    def _normalize_mixed_goal_outcome_accounting(
        raw: dict[str, Any],
        *,
        expected_goal_ids: list[str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Normalize only redundant aggregate fields in an explicit mixed plan.

        Per-Goal outcomes are the semantic authority. When they cover every
        canonical Goal, contain at least two terminal dispositions, and explicitly
        leave some Goals non-executing, top-level ``coverage`` means accounting
        coverage and is therefore mechanically ``complete``. A step that no execute
        outcome references is contradictory DTO residue and cannot be executed; it
        is removed without changing any Goal outcome or inventing replacement work.
        """

        normalized = copy.deepcopy(raw)
        outcomes = normalized.get("goal_outcomes")
        expected = set(expected_goal_ids)
        if not isinstance(outcomes, dict) or set(outcomes) != expected or not expected:
            return normalized, []
        dispositions = {
            str(item.get("disposition") or "").strip()
            for item in outcomes.values()
            if isinstance(item, dict)
        }
        if len(dispositions) < 2 or not dispositions.issubset(
            {"execute", "respond", "clarify", "unavailable", "refused"}
        ):
            return normalized, []
        repairs: list[dict[str, Any]] = []
        if normalized.get("disposition") != "mixed":
            repairs.append(
                {
                    "path": "disposition",
                    "from": normalized.get("disposition"),
                    "to": "mixed",
                    "basis": "explicit per-Goal terminal dispositions differ",
                }
            )
            normalized["disposition"] = "mixed"
        if normalized.get("coverage") != "complete":
            repairs.append(
                {
                    "path": "coverage",
                    "from": normalized.get("coverage"),
                    "to": "complete",
                    "basis": "every canonical Goal has an explicit terminal outcome",
                }
            )
            normalized["coverage"] = "complete"

        for goal_id, outcome in outcomes.items():
            if not isinstance(outcome, dict):
                continue
            satisfaction = outcome.get("satisfaction")
            if not isinstance(satisfaction, dict) or satisfaction.get("status") != "exact":
                continue
            satisfied = {
                str(item).strip()
                for item in satisfaction.get("satisfied_goal_ids") or []
                if str(item).strip()
            }
            unmet = list(satisfaction.get("unmet_goal_ids") or [])
            retained_unmet = [
                item for item in unmet if str(item).strip() not in satisfied
            ]
            if retained_unmet != unmet:
                repairs.append(
                    {
                        "path": f"goal_outcomes.{goal_id}.satisfaction.unmet_goal_ids",
                        "from": unmet,
                        "to": retained_unmet,
                        "basis": "the same Goal cannot be both satisfied and unmet",
                    }
                )
                satisfaction["unmet_goal_ids"] = retained_unmet
            unmet_requirements = list(
                satisfaction.get("unmet_requirements") or []
            )
            if unmet_requirements:
                repairs.append(
                    {
                        "path": (
                            f"goal_outcomes.{goal_id}.satisfaction."
                            "unmet_requirements"
                        ),
                        "from": unmet_requirements,
                        "to": [],
                        "basis": (
                            "status=exact is the explicit prospective adequacy "
                            "judgment and cannot also carry unmet requirements"
                        ),
                    }
                )
                satisfaction["unmet_requirements"] = []

        per_goal_satisfaction = [
            outcome.get("satisfaction")
            for outcome in outcomes.values()
            if isinstance(outcome, dict)
            and isinstance(outcome.get("satisfaction"), dict)
        ]
        aggregate_satisfaction = normalized.get("goal_satisfaction")
        if (
            len(per_goal_satisfaction) == len(expected)
            and isinstance(aggregate_satisfaction, dict)
        ):
            scores = [item.get("score") for item in per_goal_satisfaction]
            if all(
                isinstance(score, (int, float)) and not isinstance(score, bool)
                for score in scores
            ):
                aggregate_score = sum(float(score) for score in scores) / len(scores)
                aggregate_satisfied = list(
                    dict.fromkeys(
                        str(goal_id).strip()
                        for item in per_goal_satisfaction
                        for goal_id in item.get("satisfied_goal_ids") or []
                        if str(goal_id).strip()
                    )
                )
                aggregate_unmet = list(
                    dict.fromkeys(
                        str(goal_id).strip()
                        for item in per_goal_satisfaction
                        for goal_id in item.get("unmet_goal_ids") or []
                        if str(goal_id).strip()
                    )
                )
                aggregate_requirements = list(
                    dict.fromkeys(
                        " ".join(str(requirement or "").strip().split())
                        for item in per_goal_satisfaction
                        for requirement in item.get("unmet_requirements") or []
                        if " ".join(str(requirement or "").strip().split())
                    )
                )
                aggregate_status = (
                    "exact"
                    if aggregate_score >= 0.95 and not aggregate_unmet and not aggregate_requirements
                    else "substantial"
                    if aggregate_score >= 0.75
                    else "partial"
                    if aggregate_score > 0.0
                    else "unsatisfied"
                )
                aggregate_projection = {
                    "score": aggregate_score,
                    "status": aggregate_status,
                    "satisfied_goal_ids": aggregate_satisfied,
                    "unmet_goal_ids": aggregate_unmet,
                    "unmet_requirements": aggregate_requirements,
                }
                changed_fields = {
                    field_name: {
                        "from": aggregate_satisfaction.get(field_name),
                        "to": value,
                    }
                    for field_name, value in aggregate_projection.items()
                    if aggregate_satisfaction.get(field_name) != value
                }
                if changed_fields:
                    repairs.append(
                        {
                            "path": "goal_satisfaction",
                            "fields": changed_fields,
                            "basis": "deterministic aggregate of explicit per-Goal judgments",
                        }
                    )
                    aggregate_satisfaction.update(aggregate_projection)

        referenced_execute_steps = {
            str(step_id).strip()
            for outcome in outcomes.values()
            if isinstance(outcome, dict)
            and outcome.get("disposition") == "execute"
            for step_id in outcome.get("step_ids") or []
            if str(step_id).strip()
        }
        execute_owners_by_step: dict[str, list[str]] = {}
        for goal_id, outcome in outcomes.items():
            if not isinstance(outcome, dict) or outcome.get("disposition") != "execute":
                continue
            for step_id in outcome.get("step_ids") or []:
                normalized_step_id = str(step_id).strip()
                if normalized_step_id:
                    execute_owners_by_step.setdefault(normalized_step_id, []).append(
                        str(goal_id)
                    )
        steps = normalized.get("steps")
        if not isinstance(steps, list):
            return normalized, repairs
        retained: list[Any] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                retained.append(step)
                continue
            step_id = str(step.get("step_id") or "").strip()
            if not step_id or step_id in referenced_execute_steps:
                expected_owners = execute_owners_by_step.get(step_id, [])
                actual_owners = list(step.get("source_goal_ids") or [])
                if step_id and expected_owners and actual_owners != expected_owners:
                    repaired_step = dict(step)
                    repaired_step["source_goal_ids"] = expected_owners
                    repairs.append(
                        {
                            "path": f"steps[{index}].source_goal_ids",
                            "step_id": step_id,
                            "from": actual_owners,
                            "to": expected_owners,
                            "basis": "execute outcomes are the per-Goal ownership authority",
                        }
                    )
                    retained.append(repaired_step)
                    continue
                retained.append(step)
                continue
            repairs.append(
                {
                    "path": f"steps[{index}]",
                    "step_id": step_id,
                    "reason": "not_referenced_by_any_execute_outcome",
                }
            )
        normalized["steps"] = retained
        return normalized, repairs

    @classmethod
    def _safety_revision_response_schema(
        cls,
        base_schema: dict[str, Any],
        *,
        feedback: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Forbid exact execution after deterministic concurrency rejection."""

        schema = copy.deepcopy(base_schema)
        response_text = schema.get("properties", {}).get("response_text")
        if isinstance(response_text, dict):
            response_text.pop("maxLength", None)
        if cls._requires_sequential_safety_revision(list(feedback or [])):
            # The deployed structured decoder does not reliably enforce a
            # nested step constraint added only through a top-level allOf.
            # Specialize the referenced step DTO itself so a concurrency
            # rejection cannot be relabeled as a safe adjustment while the
            # rejected parallel timing remains unchanged.  This conservative
            # revision may still clarify or propose a confirmation-bound
            # sequential alternative; it cannot authorize overlap.
            step_schema = schema.get("$defs", {}).get("PlannerModelStep")
            if isinstance(step_schema, dict):
                timing = step_schema.get("properties", {}).get("timing")
                if isinstance(timing, dict):
                    timing["enum"] = ["sequential"]
                    timing["default"] = "sequential"
                    timing["description"] = (
                        "Concurrency was rejected by deterministic provider/resource "
                        "validation; retained executable steps must be sequential."
                    )
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "properties": {
                            "disposition": {
                                "type": "string",
                                "enum": ["execute", "mixed"],
                            },
                            "plan_relation": {
                                "type": "string",
                                "enum": ["safe_adjustment", "alternative"],
                            },
                            "user_confirmation_required": {
                                "type": "boolean",
                                "enum": [True],
                            },
                            "response_text": {
                                "type": "string",
                                "minLength": 1,
                            },
                        }
                    },
                    {
                        "properties": {
                            "disposition": {
                                "type": "string",
                                "enum": ["clarify", "unavailable", "refused"],
                            },
                            "steps": {
                                "type": "array",
                                "maxItems": 0,
                            },
                            "plan_relation": {
                                "type": "string",
                                "enum": ["exact"],
                            },
                            "user_confirmation_required": {
                                "type": "boolean",
                                "enum": [False],
                            },
                        }
                    },
                ]
            }
        )
        return schema

    @staticmethod
    def _contract_revision_response_schema(
        base_schema: dict[str, Any],
        *,
        feedback: list[dict[str, Any]] | None = None,
        semantic_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Tighten rejected pairs without allowing a mechanical repair to replan."""

        mismatches = [
            item
            for item in list(feedback or [])
            if isinstance(item, dict)
            and item.get("type") == "parameter_resolution_argument_mismatch"
            and str(item.get("capability_id") or "").strip()
            and str(item.get("parameter") or "").strip()
        ]
        missing_numeric = [
            item
            for item in list(feedback or [])
            if isinstance(item, dict)
            and item.get("type")
            == "missing_user_supplied_parameter_resolution"
            and str(item.get("step_id") or "").strip()
            and str(item.get("parameter") or "").strip()
            and list(item.get("source_goal_ids") or [])
        ]
        if not mismatches and not missing_numeric:
            return base_schema
        schema = copy.deepcopy(base_schema)
        branches = (
            schema.get("$defs", {})
            .get("PlannerModelStep", {})
            .get("oneOf", [])
        )
        if not isinstance(branches, list):
            return schema
        for mismatch in mismatches:
            capability_id = str(mismatch["capability_id"]).strip()
            parameter = str(mismatch["parameter"]).strip()
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                properties = branch.get("properties")
                if not isinstance(properties, dict):
                    continue
                capability_property = properties.get("capability_id")
                if not isinstance(capability_property, dict) or capability_property.get(
                    "enum"
                ) != [capability_id]:
                    continue
                args = properties.get("args")
                if not isinstance(args, dict) or parameter not in (
                    args.get("properties") or {}
                ):
                    continue
                required = args.setdefault("required", [])
                if parameter not in required:
                    required.append(parameter)
        if missing_numeric:
            if isinstance(semantic_baseline, dict):
                properties = schema.get("properties")
                if isinstance(properties, dict):
                    for field_name, field_value in semantic_baseline.items():
                        if field_name == "parameter_resolutions":
                            continue
                        properties[field_name] = {
                            "const": copy.deepcopy(field_value)
                        }
            resolution_array = schema.get("properties", {}).get(
                "parameter_resolutions"
            )
            resolution_model = schema.get("$defs", {}).get(
                "PlanParameterResolution"
            )
            if isinstance(resolution_array, dict) and isinstance(
                resolution_model, dict
            ):
                resolution_branches: list[dict[str, Any]] = []
                for obligation in missing_numeric:
                    branch = copy.deepcopy(resolution_model)
                    branch_properties = branch.setdefault("properties", {})
                    branch_properties["step_id"] = {
                        "const": str(obligation["step_id"])
                    }
                    branch_properties["parameter"] = {
                        "const": str(obligation["parameter"])
                    }
                    branch_properties["strategy"] = {"const": "user_supplied"}
                    branch_properties["value"] = {"const": obligation["value"]}
                    branch_properties["blocking"] = {"const": False}
                    branch_properties["source_goal_ids"] = {
                        "const": list(obligation["source_goal_ids"])
                    }
                    required = branch.setdefault("required", [])
                    for field_name in (
                        "step_id",
                        "parameter",
                        "strategy",
                        "value",
                        "confidence",
                        "blocking",
                        "rationale",
                        "source_goal_ids",
                    ):
                        if field_name not in required:
                            required.append(field_name)
                    resolution_branches.append(branch)
                resolution_array["items"] = (
                    resolution_branches[0]
                    if len(resolution_branches) == 1
                    else {"oneOf": resolution_branches}
                )
                resolution_array["minItems"] = len(resolution_branches)
        return schema

    @staticmethod
    def _validate_mechanical_numeric_revision_preserved(
        candidate: dict[str, Any],
        *,
        baseline: dict[str, Any],
    ) -> None:
        """Reject any semantic rewrite during a provenance-only DTO repair."""

        changed = sorted(
            field_name
            for field_name in set(candidate).union(baseline)
            if field_name != "parameter_resolutions"
            and candidate.get(field_name) != baseline.get(field_name)
        )
        if changed:
            raise PlannerDTOContractError(
                "mechanical numeric provenance repair changed semantic plan fields: "
                + ",".join(changed)
            )

    @classmethod
    def _safety_revision_contract_errors(
        cls,
        plan: CanonicalPlan,
        feedback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Enforce the decoder's safety-revision grammar at runtime too."""

        if not cls._requires_safety_revision(feedback):
            return []
        if plan.disposition in {"clarify", "unavailable", "refused"}:
            return (
                []
                if not plan.steps
                else [
                    {
                        "type": "safety_revision_contract_not_satisfied",
                        "reason": "non-executable safety revision retained plan steps",
                    }
                ]
            )
        relation = str(plan.metadata.get("plan_relation") or "exact")
        confirmation = plan.metadata.get("user_confirmation_required") is True
        retained_parallel_steps = [step.step_id for step in plan.steps if step.timing == "parallel"]
        if cls._requires_sequential_safety_revision(feedback) and retained_parallel_steps:
            return [
                {
                    "type": "safety_revision_contract_not_satisfied",
                    "plan_relation": relation,
                    "parallel_step_ids": retained_parallel_steps,
                    "reason": (
                        "concurrency was rejected, so a safe revision cannot "
                        "retain parallel step timing"
                    ),
                }
            ]
        if (
            plan.disposition in {"execute", "mixed"}
            and relation in {"safe_adjustment", "alternative"}
            and confirmation
            and bool(plan.response_text.strip())
        ):
            return []
        return [
            {
                "type": "safety_revision_contract_not_satisfied",
                "disposition": plan.disposition,
                "plan_relation": relation,
                "user_confirmation_required": confirmation,
                "response_text_present": bool(plan.response_text.strip()),
                "reason": (
                    "after concurrency safety rejection, execution requires an "
                    "explicit safe_adjustment or alternative, explanatory "
                    "response_text, and user confirmation"
                ),
            }
        ]

    @staticmethod
    def _validate_parallel_timing_preservation(
        raw: dict[str, Any],
        *,
        context: dict[str, Any] | None,
    ) -> None:
        """Reject an omitted Deep Planner ordering/concurrency decision.

        Every Deep step must author its timing explicitly.  The Host must not
        turn an omitted semantic decision into sequential execution through the
        DTO's compatibility default, including when Fast Planner failed before
        producing a usable advisory plan.  When Fast did retain a parallel plan,
        the later checks also ensure that Deep does not omit timing only for the
        corresponding replacement steps.
        """

        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list):
            return
        missing = [
            index
            for index, item in enumerate(raw_steps)
            if isinstance(item, dict) and "timing" not in item
        ]
        # A single executable step has no inter-step overlap relation, so its
        # compatibility default cannot silently serialize another action.  The
        # decoder still requires an explicit value for all new model output;
        # retain bounded acceptance here only for older/test providers that
        # return one otherwise valid singleton step.
        if missing and len(raw_steps) > 1:
            raise ValueError(
                "deep planner omitted timing for executable step(s) "
                f"{missing}; explicitly author sequential or parallel timing"
            )
        if not isinstance(context, dict):
            return
        advisory = context.get("fast_plan_resolution") or context.get("fast_planner_resolution")
        if not isinstance(advisory, dict):
            return
        fast_steps = advisory.get("steps")
        if not isinstance(fast_steps, list) or not isinstance(raw_steps, list):
            return
        parallel_fast = [
            item
            for item in fast_steps
            if isinstance(item, dict) and str(item.get("timing") or "").strip() == "parallel"
        ]
        if len(parallel_fast) < 2:
            return
        expected_capabilities = sorted(
            str(item.get("capability_id") or "").strip()
            for item in parallel_fast
            if str(item.get("capability_id") or "").strip()
        )
        actual_capabilities = sorted(
            str(item.get("capability_id") or "").strip()
            for item in raw_steps
            if isinstance(item, dict)
            and str(item.get("capability_id") or "").strip()
        )
        if expected_capabilities != actual_capabilities:
            return
        # Missing timing was rejected above.  Keep the Fast-plan comparison so
        # this boundary remains the owner for future exact replacement checks.

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        return bounded_json(value, limit)


    def _normalize(
        self,
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
        plan_id: str,
        expected_goal_ids_for_turn: list[str],
        capability_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        model_output = validate_planner_model_output(
            raw,
            planner_tier="deep",
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
        out["planner_tier"] = "deep"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        steps = out.get("steps")
        if isinstance(steps, dict):
            steps = [steps]
        if not isinstance(steps, list):
            steps = []
        normalized = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            step = dict(item)
            if not step.get("step_id"):
                step["step_id"] = f"{plan_id}:step:{index}"
            normalized.append(step)
        # A singleton step has no inter-step concurrency relation. Canonicalize
        # a model-authored ``parallel`` label to ``sequential`` mechanically
        # instead of spending another semantic model call to repair a meaningless
        # scheduling annotation. Multi-step concurrency remains model-owned and
        # is validated against provider safety below.
        if len(normalized) == 1 and normalized[0].get("timing") == "parallel":
            normalized[0]["timing"] = "sequential"
        out["steps"] = normalized
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "clarify")
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

    def _validation_errors(
        self,
        plan: CanonicalPlan,
        capabilities: list[dict[str, Any]],
        *,
        expected_goal_ids: list[str],
        request: CognitiveWorkRequest,
    ) -> list[dict[str, Any]]:
        allowed = {item["capability_id"]: item for item in capabilities}
        errors: list[dict[str, Any]] = []
        if expected_goal_ids and set(plan.goal_ids) != set(expected_goal_ids):
            errors.append(
                {
                    "type": "goal_ids_do_not_match_goal_association",
                    "expected_goal_ids": expected_goal_ids,
                    "actual_goal_ids": list(plan.goal_ids),
                }
            )
        _, requires_execution = planner_goal_execution_requirements(
            canonical_goal_grounding(request.context)
        )
        if (
            requires_execution
            and plan.disposition not in {"clarify", "unavailable", "refused"}
            and not plan.steps
        ):
            errors.append(
                {
                    "type": "canonical_goal_requires_executable_step",
                    "disposition": plan.disposition,
                }
            )
        if plan.coverage == "complete" and plan.confidence < self.min_confidence:
            errors.append(
                {
                    "type": "confidence_below_threshold",
                    "confidence": plan.confidence,
                    "required": self.min_confidence,
                }
            )
        if plan.coverage == "complete":
            if plan.goal_satisfaction is None:
                errors.append({"type": "missing_goal_satisfaction"})
            elif (
                plan.disposition != "mixed"
                and plan.goal_satisfaction.score < self.min_goal_satisfaction
            ):
                errors.append(
                    {
                        "type": "goal_satisfaction_below_threshold",
                        "score": plan.goal_satisfaction.score,
                        "required": self.min_goal_satisfaction,
                    }
                )
        if plan.disposition == "mixed":
            for outcome in plan.goal_outcomes:
                if outcome.disposition not in {"execute", "respond"}:
                    continue
                # The complete aggregate satisfaction object and exact keyed
                # outcome map already express prospective adequacy. Per-outcome
                # satisfaction is useful when the model supplies it, but is not
                # a second mandatory copy of the same judgment. Treat a supplied
                # low score as authoritative without failing solely on omission.
                if (
                    outcome.satisfaction is not None
                    and outcome.satisfaction.score < self.min_goal_satisfaction
                ):
                    errors.append(
                        {
                            "type": "goal_outcome_satisfaction_below_threshold",
                            "goal_id": outcome.goal_id,
                            "score": outcome.satisfaction.score,
                            "required": self.min_goal_satisfaction,
                        }
                    )
        step_ids = {step.step_id for step in plan.steps}
        for resolution in plan.parameter_resolutions:
            if resolution.step_id not in step_ids and not resolution.blocking:
                errors.append(
                    {
                        "type": "parameter_resolution_unknown_step",
                        "step_id": resolution.step_id,
                        "parameter": resolution.parameter,
                    }
                )
            if resolution.blocking and plan.disposition == "execute":
                errors.append(
                    {
                        "type": "blocking_parameter_resolution",
                        "step_id": resolution.step_id,
                        "parameter": resolution.parameter,
                    }
                )
        for step in plan.steps:
            capability = allowed.get(step.capability_id)
            if capability is None:
                errors.append(
                    {
                        "type": "unknown_capability",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                    }
                )
                continue
            if not capability.get("available") or not capability.get("interaction_executable"):
                errors.append(
                    {
                        "type": "capability_not_executable",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                    }
                )
                continue
            schema_errors = validate_args_for_schema(
                step.args, capability.get("input_schema") or {}
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
        errors.extend(parallel_plan_contract_errors(plan, capabilities))
        return errors

    def _unavailable(
        self,
        plan_id: str,
        request: CognitiveWorkRequest,
        reason: str,
        *,
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: Exception | None = None,
        attempts: int = 1,
    ) -> CanonicalPlan:
        """Return a terminal capability limitation without asking a fake question.

        Missing provider ability is not user-semantic ambiguity. Additional user
        detail cannot create an absent Capability, so Deep Planning reports the
        limitation and authors only honest conversational next steps.
        """

        detail = dict(metadata or {})
        detail.update(
            {
                "resolver": "deep_planner",
                "status": "unavailable",
                "authority": "advisory",
                "attempt_count": attempts,
                "max_contract_repairs": self.max_contract_repairs,
                "reason": reason,
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
        return CanonicalPlan(
            plan_id=plan_id,
            planner_tier="deep",
            disposition="unavailable",
            coverage="uncertain",
            confidence=0.0,
            goal_summary=request.text,
            goal_ids=expected_goal_ids(context),
            response_text="",
            steps=[],
            unresolved=list(unresolved or []),
            metadata=detail,
        )

    def _clarify(
        self,
        plan_id: str,
        request: CognitiveWorkRequest,
        reason: str,
        *,
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: Exception | None = None,
        attempts: int = 1,
    ) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update(
            {
                "resolver": "deep_planner",
                "status": "clarify",
                "authority": "advisory",
                "attempt_count": attempts,
                "max_contract_repairs": self.max_contract_repairs,
                "reason": reason,
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
        return CanonicalPlan(
            plan_id=plan_id,
            planner_tier="deep",
            disposition="clarify",
            coverage="uncertain",
            confidence=0.0,
            goal_summary=request.text,
            goal_ids=expected_goal_ids(context),
            response_text="",
            steps=[],
            unresolved=list(unresolved or []),
            metadata=detail,
        )
