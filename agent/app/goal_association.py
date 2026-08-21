from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .clients.ollama_client import (
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .prompt_projection import bounded_json
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
    from chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        GoalEntityBinding,
        ResolvedDiscourseReference,
        stable_referent_id,
    )
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.resource import (
        AcquireAndDeliverResource,
        ResourceDescriptor,
        ResourceRecipient,
        ResourceSource,
    )
    from chromie_contracts.semantic_task import SemanticGoal
    from chromie_contracts.situation import SituationProjection
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        GoalEntityBinding,
        ResolvedDiscourseReference,
        stable_referent_id,
    )
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.resource import (
        AcquireAndDeliverResource,
        ResourceDescriptor,
        ResourceRecipient,
        ResourceSource,
    )
    from shared.chromie_contracts.semantic_task import SemanticGoal
    from shared.chromie_contracts.situation import SituationProjection

logger = logging.getLogger("chromie.agent.goal_association")

from .goal_association_contract import (
    _CoverageSourceExcerptViolation,
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
    action_collection_bindings,
    binding_semantic_contract_conflicts,
    coverage_certificate_response_schema,
    coverage_verdict,
    drop_ungrounded_resource_query_locations,
    goal_association_response_schema,
    non_verbatim_explicit_location_bindings,
    normalize_grounded_generic_location_types,
    normalize_optional_referent_updates,
    normalize_optional_resource_quantity,
    normalize_resource_binding_branches,
    resource_source_binding_contract_conflicts,
    responsibility_coverage_required,
    responsibility_output_mode_conflicts,
    restore_missing_goal_descriptions,
    source_grounded_binding_coverage_conflicts,
    validation_error_json,
)

from .goal_association_prompt import (
    build_fresh_interpretation_prompt,
    build_responsibility_coverage_prompt,
    discourse_referents,
    layered_prompt,
    layered_repair_prompt,
    repair_system_prompt,
    responsibility_coverage_system_prompt,
    semantic_review_system_prompt,
    system_prompt,
)


class GoalAssociationResolver:
    """Resolve continuity before creation without mutating runtime state."""

    TRACE_MODULE = TraceModule(
        name="agent.goal_association",
        component_type="goal_association",
        implementation="GoalAssociationResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        min_confidence: float = 0.65,
        max_active_goals: int = 8,
        num_ctx: int = 4096,
        num_predict: int = 512,
    ) -> None:
        self.ollama = ollama
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.max_active_goals = max(1, min(32, int(max_active_goals)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: CognitiveWorkRequest) -> GoalAssociationResolution:
        trace_scope = runtime_tracer.continue_from_context(request.context)
        if not trace_scope.enabled:
            return await self._resolve(request)
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    attributes={
                        "candidate_goal_count": len(self._candidate_goals(request)),
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                ) as span:
                    result = await self._resolve(request)
                    status = result.resolution_status
                    span.set_attribute("result_status", status)
                    span.set_attribute("association_count", len(result.associations))
                    span.set_attribute("new_goal_count", len(result.new_goals))
                    if status != "resolved":
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: CognitiveWorkRequest) -> GoalAssociationResolution:
        """Resolve one turn through the bounded Goal semantic transaction."""

        candidate_goals = self._candidate_goals(request)
        turn_id = self._turn_id(request)
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ) = (
            GoalAssociationModelOutput
            if candidate_goals
            else GoalSegmentationModelOutput
        )
        response_schema = goal_association_response_schema(
            output_type,
            candidate_goals,
            discourse_referents(request),
            responsibility_count=len(request.responsibilities),
            responsibility_refs=[item.local_ref for item in request.responsibilities],
            responsibility_output_modes={
                item.local_ref: item.output_mode
                for item in request.responsibilities
                if item.output_mode != "unspecified"
            },
            responsibility_fresh_evidence_refs={
                item.local_ref
                for item in request.responsibilities
                if item.completion_requires_fresh_evidence
            },
            responsibility_bindings={
                item.local_ref: {
                    str(name): value
                    for name, value in item.bindings.items()
                    if isinstance(value, str)
                }
                for item in request.responsibilities
            },
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        logical_invocations = 0
        invocation_families: list[str] = []
        initial_raw: dict[str, Any] | None = None
        accepted_raw: dict[str, Any] | None = None
        certificate_raw: dict[str, Any] | None = None
        contract_repair_attempted = False
        semantic_reconsideration_attempted = False
        optional_referent_recovery: list[dict[str, Any]] = []
        redundant_resource_binding_recovery: list[dict[str, Any]] = []
        invalid_optional_quantity_recovery: list[dict[str, Any]] = []
        ungrounded_resource_location_recovery: list[dict[str, Any]] = []
        generic_location_type_recovery: list[dict[str, Any]] = []
        missing_description_recovery: list[dict[str, Any]] = []

        async def invoke(
            prompt: Any,
            *,
            system: str,
            response_format: dict[str, Any],
            prompt_family: str,
        ) -> Any:
            nonlocal logical_invocations
            if logical_invocations >= 5:
                raise RuntimeError(
                    "goal-association logical invocation budget exhausted"
                )
            logical_invocations += 1
            invocation_families.append(prompt_family)
            return await self.ollama.generate(
                prompt,
                system=system,
                options=generation_options,
                response_format=response_format,
                prompt_family=prompt_family,
                turn_id=request.sid,
                attempt=logical_invocations,
            )

        def normalize_raw(value: Any, *, stage: str) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise OllamaGenerationError(
                    f"goal-association {stage} response is not a JSON object",
                    failure_class="structured_output_invalid",
                    failure_domain="model_contract",
                    architecture_attribution="not_evaluated",
                    retryable=True,
                )
            normalized, recovered = normalize_optional_referent_updates(
                value
            )
            optional_referent_recovery.extend(recovered)
            normalized, recovered = normalize_resource_binding_branches(
                normalized
            )
            redundant_resource_binding_recovery.extend(recovered)
            normalized, recovered = normalize_optional_resource_quantity(
                normalized
            )
            invalid_optional_quantity_recovery.extend(recovered)
            normalized, recovered = drop_ungrounded_resource_query_locations(
                normalized,
                request=request,
            )
            ungrounded_resource_location_recovery.extend(recovered)
            normalized, recovered = normalize_grounded_generic_location_types(
                normalized,
                request=request,
            )
            generic_location_type_recovery.extend(recovered)
            normalized, recovered = restore_missing_goal_descriptions(
                normalized,
                request=request,
            )
            missing_description_recovery.extend(recovered)
            return normalized

        try:
            initial_raw = normalize_raw(
                await invoke(
                    layered_prompt(
                        request,
                        candidate_goals,
                        output_type=output_type,
                    ),
                    system=system_prompt(output_type),
                    response_format=response_schema,
                    prompt_family="goal_association.primary",
                ),
                stage="primary",
            )
            try:
                resolution = await self._validate_contract_output(
                    initial_raw,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                accepted_raw = initial_raw
            except (ValidationError, ValueError) as initial_exc:
                contract_repair_attempted = True
                repaired = normalize_raw(
                    await invoke(
                        layered_repair_prompt(
                            request=request,
                            candidate_goals=candidate_goals,
                            turn_id=turn_id,
                            output_type=output_type,
                            raw=initial_raw,
                            validation_error=validation_error_json(
                                initial_exc
                            ),
                        ),
                        system=repair_system_prompt(output_type),
                        response_format=response_schema,
                        prompt_family="goal_association.contract_repair",
                    ),
                    stage="contract repair",
                )
                resolution = await self._validate_contract_output(
                    repaired,
                    request=request,
                    turn_id=turn_id,
                    output_type=output_type,
                )
                accepted_raw = repaired

            model_output = output_type.model_validate(accepted_raw)
            coverage_metadata: dict[str, Any] = {
                "attempted": False,
                "succeeded": False,
                "initial_verdict": "not_required",
                "final_verdict": "not_required",
                "reconsidered": False,
            }
            if responsibility_coverage_required(
                model_output,
                request=request,
            ):
                coverage_metadata["attempted"] = True
                certificate_raw = await invoke(
                    build_responsibility_coverage_prompt(
                        request=request,
                        raw=accepted_raw,
                    ),
                    system=responsibility_coverage_system_prompt(),
                    response_format=coverage_certificate_response_schema(
                        list(model_output.new_goals),
                        authoritative_turn=request.text,
                    ),
                    prompt_family="goal_association.responsibility_coverage",
                )
                certificate: GoalResponsibilityCoverageCertificate | None
                try:
                    certificate = self._validate_coverage_certificate(
                        certificate_raw,
                        request=request,
                        goal_count=len(model_output.new_goals),
                        candidate_goals=list(model_output.new_goals),
                    )
                except _CoverageSourceExcerptViolation:
                    # An ungrounded audit can never certify a candidate. Treat the
                    # first audit as a rejection and use the existing one-shot fresh
                    # semantic interpretation from the authoritative turn. This is
                    # not DTO repair, and the final audit still fails closed on the
                    # same provenance defect.
                    certificate = None
                    verdict = "reject"
                    problems = ["coverage_source_excerpt_not_authoritative"]
                    problems.extend(
                        "missing_source_grounded_binding=" + conflict
                        for conflict in source_grounded_binding_coverage_conflicts(
                            model_output,
                            request=request,
                        )
                    )
                    coverage_metadata["initial_certificate_contract_error"] = (
                        "source_excerpt_not_authoritative"
                    )
                else:
                    verdict, problems = coverage_verdict(
                        certificate,
                        goal_count=len(model_output.new_goals),
                    )
                coverage_metadata["initial_verdict"] = verdict
                if certificate is not None:
                    coverage_metadata["certificate"] = certificate.model_dump(
                        mode="json"
                    )
                if verdict == "reject":
                    semantic_reconsideration_attempted = True
                    coverage_metadata["reconsidered"] = True
                    clarification_required = bool(
                        certificate is not None
                        and any(
                            item.coverage == "clarification_required"
                            for item in certificate.items
                        )
                    )
                    reconsidered_raw = normalize_raw(
                        await invoke(
                            build_fresh_interpretation_prompt(
                                request=request,
                                candidate_goals=candidate_goals,
                                output_type=output_type,
                                problems=problems,
                                preserve_unresolved_meaning=clarification_required,
                            ),
                            system=semantic_review_system_prompt(
                                output_type,
                                fresh_resegmentation=True,
                            ),
                            response_format=response_schema,
                            prompt_family="goal_association.fresh_interpretation",
                        ),
                        stage="fresh interpretation",
                    )
                    # Semantic reconsideration is validated as authored. Goal Association
                    # preserves human temporal meaning and never repairs it into
                    # Planner/Capability argument vocabulary.
                    resolution = await self._validate_contract_output(
                        reconsidered_raw,
                        request=request,
                        turn_id=turn_id,
                        output_type=output_type,
                    )
                    accepted_raw = reconsidered_raw
                    reconsidered_output = output_type.model_validate(accepted_raw)
                    if responsibility_coverage_required(
                        reconsidered_output,
                        request=request,
                    ):
                        certificate_raw = await invoke(
                            build_responsibility_coverage_prompt(
                                request=request,
                                raw=accepted_raw,
                            ),
                            system=responsibility_coverage_system_prompt(),
                            response_format=coverage_certificate_response_schema(
                                list(reconsidered_output.new_goals),
                                authoritative_turn=request.text,
                            ),
                            prompt_family=(
                                "goal_association.responsibility_coverage_final"
                            ),
                        )
                        final_certificate = self._validate_coverage_certificate(
                            certificate_raw,
                            request=request,
                            goal_count=len(reconsidered_output.new_goals),
                            candidate_goals=list(reconsidered_output.new_goals),
                        )
                        final_verdict, final_problems = coverage_verdict(
                            final_certificate,
                            goal_count=len(reconsidered_output.new_goals),
                        )
                        coverage_metadata["final_verdict"] = final_verdict
                        coverage_metadata["certificate"] = (
                            final_certificate.model_dump(mode="json")
                        )
                        if final_verdict != "accept":
                            raise ValueError(
                                "fresh Goal interpretation failed final responsibility "
                                "coverage: " + "; ".join(final_problems)
                            )
                    else:
                        coverage_metadata["final_verdict"] = "clarification"
                else:
                    coverage_metadata["final_verdict"] = "accept"
                coverage_metadata["succeeded"] = True

            metadata = dict(resolution.metadata)
            metadata.update(
                {
                    "goal_semantic_transaction": {
                        "logical_invocation_count": logical_invocations,
                        "logical_invocation_budget": 5,
                        "prompt_families": invocation_families,
                        "contract_repair_attempted": contract_repair_attempted,
                        "semantic_reconsideration_attempted": (
                            semantic_reconsideration_attempted
                        ),
                        "terminal_state": "commit",
                    },
                    "responsibility_coverage": coverage_metadata,
                }
            )
            if optional_referent_recovery:
                metadata["optional_contract_recovery"] = {
                    "field": "referent_updates",
                    "strategy": "drop_invalid_unreferenced_introduce",
                    "dropped_count": len(optional_referent_recovery),
                    "entries": optional_referent_recovery,
                }
            if redundant_resource_binding_recovery:
                metadata["mechanical_contract_recovery"] = {
                    "field": "new_goals[].bindings",
                    "strategy": "normalize_inactive_resource_binding_branch",
                    "dropped_count": len(redundant_resource_binding_recovery),
                    "entries": redundant_resource_binding_recovery,
                }
            if invalid_optional_quantity_recovery:
                metadata["optional_quantity_contract_recovery"] = {
                    "field": "new_goals[].resource_responsibility.quantity",
                    "strategy": "drop_invalid_optional_scalar",
                    "dropped_count": len(invalid_optional_quantity_recovery),
                    "entries": invalid_optional_quantity_recovery,
                }
            if ungrounded_resource_location_recovery:
                metadata["source_grounding_recovery"] = {
                    "field": "new_goals[].resource_responsibility.query_scope",
                    "strategy": "drop_unentailed_location_query_fact",
                    "dropped_count": len(ungrounded_resource_location_recovery),
                    "entries": ungrounded_resource_location_recovery,
                }
            if generic_location_type_recovery:
                metadata["generic_location_type_recovery"] = {
                    "field": "new_goals[].semantic_bindings[].entity_type",
                    "strategy": "normalize_grounded_generic_location_type",
                    "changed_count": len(generic_location_type_recovery),
                    "entries": generic_location_type_recovery,
                }
            if missing_description_recovery:
                metadata["missing_description_recovery"] = {
                    "field": "new_goals[].description",
                    "strategy": "copy_exact_source_responsibility_outcome",
                    "changed_count": len(missing_description_recovery),
                    "entries": missing_description_recovery,
                }
            resolution = resolution.model_copy(update={"metadata": metadata})
            return self._validate(
                resolution,
                candidate_goals=candidate_goals,
                request=request,
            )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.exception(
                "goal_association_transaction_failed sid=%s error_type=%s "
                "error=%s logical_invocations=%d prompt_families=%s",
                request.sid,
                type(exc).__name__,
                exc,
                logical_invocations,
                ",".join(invocation_families),
            )
            metadata: dict[str, Any] = {
                "resolver": "goal_association_agent",
                "status": "model_contract_failed",
                "sid": request.sid,
                "authority": "advisory",
                **failure,
                **cognitive_integrity_metadata(
                    stage="goal_association",
                    exc=exc,
                    request=request,
                ),
                "goal_semantic_transaction": {
                    "logical_invocation_count": logical_invocations,
                    "logical_invocation_budget": 5,
                    "prompt_families": invocation_families,
                    "contract_repair_attempted": contract_repair_attempted,
                    "semantic_reconsideration_attempted": (
                        semantic_reconsideration_attempted
                    ),
                    "terminal_state": "fail_closed",
                },
                "initial_raw_output_ref": cognition_text_reference(initial_raw),
                "accepted_raw_output_ref": cognition_text_reference(accepted_raw),
                "coverage_certificate_ref": cognition_text_reference(certificate_raw),
            }
            if isinstance(exc, (ValidationError, ValueError)):
                metadata.update(
                    {
                        "failure_class": "structured_output_validation",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "not_evaluated",
                        "retryable": False,
                    }
                )
            if optional_referent_recovery:
                metadata["optional_contract_recovery"] = {
                    "field": "referent_updates",
                    "strategy": "drop_invalid_unreferenced_introduce",
                    "dropped_count": len(optional_referent_recovery),
                    "entries": optional_referent_recovery,
                }
            if redundant_resource_binding_recovery:
                metadata["mechanical_contract_recovery"] = {
                    "field": "new_goals[].bindings",
                    "strategy": "normalize_inactive_resource_binding_branch",
                    "dropped_count": len(redundant_resource_binding_recovery),
                    "entries": redundant_resource_binding_recovery,
                }
            if ungrounded_resource_location_recovery:
                metadata["source_grounding_recovery"] = {
                    "field": "new_goals[].resource_responsibility.query_scope",
                    "strategy": "drop_unentailed_location_query_fact",
                    "dropped_count": len(ungrounded_resource_location_recovery),
                    "entries": ungrounded_resource_location_recovery,
                }
            if generic_location_type_recovery:
                metadata["generic_location_type_recovery"] = {
                    "field": "new_goals[].semantic_bindings[].entity_type",
                    "strategy": "normalize_grounded_generic_location_type",
                    "changed_count": len(generic_location_type_recovery),
                    "entries": generic_location_type_recovery,
                }
            if missing_description_recovery:
                metadata["missing_description_recovery"] = {
                    "field": "new_goals[].description",
                    "strategy": "copy_exact_source_responsibility_outcome",
                    "changed_count": len(missing_description_recovery),
                    "entries": missing_description_recovery,
                }
            return GoalAssociationResolution(
                turn_id=turn_id,
                resolution_status="fail_closed",
                confidence=0.0,
                reason_summary=(
                    "Goal semantics did not reach the trusted commit boundary; "
                    "no goal operation was accepted."
                ),
                metadata=metadata,
            )


    async def _validate_contract_output(
        self,
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> GoalAssociationResolution:
        model_output = output_type.model_validate(raw)
        gaps_by_goal_id = {
            str(goal.get("goal_id") or "").strip(): {
                str(gap.get("gap_id") or "").strip()
                for gap in (goal.get("open_information_gaps") or [])
                if isinstance(gap, dict) and str(gap.get("gap_id") or "").strip()
            }
            for goal in self._candidate_goals(request)
            if str(goal.get("goal_id") or "").strip()
        }
        invalid_resolved_gaps = [
            gap_id
            for association in getattr(model_output, "associations", [])
            for gap_id in association.resolved_gap_ids
            if gap_id
            not in {
                candidate_gap
                for goal_id in association.target_goal_ids
                for candidate_gap in gaps_by_goal_id.get(goal_id, set())
            }
        ]
        if invalid_resolved_gaps:
            raise ValueError(
                "Goal Association may resolve only pending Planner gaps on its exact "
                "target Goals: "
                + ",".join(sorted(set(invalid_resolved_gaps)))
            )
        collection_bindings = action_collection_bindings(model_output)
        if collection_bindings:
            raise ValueError(
                "new Goal bindings cannot contain action collections; emit one "
                "new_goals item for every independently observable responsibility: "
                + ", ".join(collection_bindings)
            )
        output_mode_conflicts = responsibility_output_mode_conflicts(
            model_output,
            request=request,
        )
        if output_mode_conflicts:
            raise ValueError(
                "new Goal output_mode must preserve Goal Interpretation's "
                "provider-neutral completion modality: "
                + ", ".join(output_mode_conflicts)
            )
        binding_conflicts = binding_semantic_contract_conflicts(model_output)
        if binding_conflicts:
            raise ValueError(
                "binding name and entity_type cannot declare conflicting canonical "
                "parameter categories; preserve the intended parameter and correct "
                "the contradictory field: "
                + ", ".join(binding_conflicts)
            )
        resource_source_conflicts = (
            resource_source_binding_contract_conflicts(model_output)
        )
        if resource_source_conflicts:
            raise ValueError(
                "physical resource source.acquisition_bindings may describe only an "
                "actual spatial/acquisition constraint. Resource identity, "
                "requested quantity, recipient, and delivery fields are not source "
                "evidence: "
                + ", ".join(resource_source_conflicts)
            )
        location_bindings = non_verbatim_explicit_location_bindings(
            model_output,
            request=request,
        )
        if location_bindings:
            raise ValueError(
                "a location binding must preserve explicit or referent-backed "
                "provenance. For a directly named location, preserve a verbatim "
                "contiguous span from the authoritative user turn and do not "
                "translate, transliterate, or expand it. For an indirect "
                "location, copy the supplied referent_id into both the location "
                "binding and resolved_references, and copy the indirect user "
                "surface into resolved_references.surface_form: "
                + ", ".join(location_bindings)
            )
        return self._expand_model_output(
            model_output,
            request=request,
            turn_id=turn_id,
        )


    def _candidate_goals(self, request: CognitiveWorkRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        active = context.get("active_goal_snapshots")
        recent = context.get("recent_goal_snapshots")
        if not isinstance(active, list):
            active = []
        if not isinstance(recent, list):
            recent = []
        raw = [*active, *recent]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(raw):
            if len(out) >= self.max_active_goals:
                break
            if not isinstance(item, dict):
                continue
            try:
                snapshot = ActiveGoalSnapshot.model_validate(item).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                goal_id = str(snapshot.get("goal_id") or "").strip()
                if not goal_id or goal_id in seen:
                    continue
                seen.add(goal_id)
                out.append(snapshot)
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed Goal association candidate index=%s error=%s",
                    index,
                    exc,
                )
                continue
        return out


    @staticmethod
    def _turn_id(request: CognitiveWorkRequest) -> str:
        seed = f"{request.sid or 'turn'}|{request.text}"
        return f"turn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        return bounded_json(value, max_chars)


    @classmethod
    def _validate_coverage_certificate(
        cls,
        raw: Any,
        *,
        request: CognitiveWorkRequest,
        goal_count: int,
        candidate_goals: list[GoalAssociationModelGoal] | None = None,
    ) -> GoalResponsibilityCoverageCertificate:
        if not isinstance(raw, dict):
            raise OllamaGenerationError(
                "goal-association responsibility coverage is not a JSON object",
                failure_class="structured_output_invalid",
                failure_domain="model_contract",
                architecture_attribution="not_evaluated",
                retryable=True,
            )
        normalized_raw = copy.deepcopy(raw)
        normalized_items: list[Any] = []
        recoveries: list[dict[str, Any]] = []
        for field_name in ("responsibility_items", "supporting_items"):
            field_items = normalized_raw.get(field_name)
            if isinstance(field_items, list):
                unique_items: list[Any] = []
                seen_items: set[str] = set()
                for item_index, item in enumerate(field_items):
                    fingerprint = json.dumps(
                        item,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if fingerprint in seen_items:
                        recoveries.append(
                            {
                                "field": field_name,
                                "item_index": item_index,
                                "recovery": "removed_exact_duplicate",
                            }
                        )
                        continue
                    seen_items.add(fingerprint)
                    unique_items.append(item)
                normalized_raw[field_name] = unique_items
                normalized_items.extend(unique_items)
        # A coverage certificate can contradict its own role split: small models
        # sometimes repeat the same source span as both a non-independent
        # ``responsibility`` and a supporting constraint.  The non-independent
        # responsibility branch cannot own a standalone Goal by the auditor's own
        # fields, so discard only that exact conflicting duplicate.  This is DTO
        # normalization, not Host interpretation of the user's words.
        responsibility_items = normalized_raw.get("responsibility_items")
        supporting_items = normalized_raw.get("supporting_items")
        self_contradictory_support_spans: set[str] = set()
        if isinstance(responsibility_items, list) and isinstance(supporting_items, list):
            supporting_spans = {
                " ".join(str(item.get("source_excerpt") or "").strip().casefold().split())
                for item in supporting_items
                if isinstance(item, dict)
                and str(item.get("role") or "") in {"constraint", "context", "framing"}
                and str(item.get("source_excerpt") or "").strip()
            }
            retained_responsibilities: list[Any] = []
            for item_index, item in enumerate(responsibility_items):
                normalized_excerpt = (
                    " ".join(str(item.get("source_excerpt") or "").strip().casefold().split())
                    if isinstance(item, dict)
                    else ""
                )
                if (
                    isinstance(item, dict)
                    and str(item.get("role") or "") == "responsibility"
                    and item.get("independently_satisfiable") is False
                    and normalized_excerpt
                    and normalized_excerpt in supporting_spans
                ):
                    self_contradictory_support_spans.add(normalized_excerpt)
                    recoveries.append(
                        {
                            "field": "responsibility_items",
                            "item_index": item_index,
                            "recovery": "removed_nonindependent_role_duplicate",
                            "source_excerpt": item.get("source_excerpt"),
                        }
                    )
                    continue
                retained_responsibilities.append(item)
            normalized_raw["responsibility_items"] = retained_responsibilities
            normalized_items = [
                *retained_responsibilities,
                *supporting_items,
            ]

        if normalized_items:
            for item_index, item in enumerate(normalized_items):
                if not isinstance(item, dict):
                    continue
                required_goal_shape = str(
                    item.get("required_goal_shape") or "ordinary"
                )
                required_information_domain = str(
                    item.get("required_information_domain") or "none"
                )
                role = str(item.get("role") or "")
                required_output_mode = str(
                    item.get("required_output_mode") or "none"
                )
                if role != "responsibility" and item.get(
                    "independently_satisfiable"
                ) is True:
                    # The auditor already selected the non-responsibility branch.
                    # Independent satisfiability is structurally impossible there;
                    # clearing the redundant flag does not change role, ownership,
                    # coverage, or any candidate mapping judgment.
                    item["independently_satisfiable"] = False
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "cleared_supporting_independence",
                            "role": role,
                            "from": True,
                            "to": False,
                        }
                    )
                if role != "responsibility" and required_goal_shape != "ordinary":
                    # Goal shape classifies the independently owed result only. A
                    # supporting item can point at a resource Goal, but cannot own
                    # or restate that Goal's shape. This projection follows the
                    # auditor-authored role and changes no coverage judgment.
                    item["required_goal_shape"] = "ordinary"
                    item["required_information_domain"] = "none"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "cleared_supporting_goal_shape",
                            "role": role,
                            "from": required_goal_shape,
                            "to": "ordinary",
                        }
                    )
                    required_goal_shape = "ordinary"
                    required_information_domain = "none"
                if (
                    role == "responsibility"
                    and required_output_mode
                    not in {"none", "body_action", "capability_work"}
                    and required_goal_shape != "ordinary"
                ):
                    # Resource completion modes are body_action (physical) or
                    # capability_work (information). Once the independent auditor
                    # has explicitly selected any vocal/media/other completion
                    # mode, a resource shape is mechanically impossible.
                    item["required_goal_shape"] = "ordinary"
                    item["required_information_domain"] = "none"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "normalized_output_mode_goal_shape",
                            "required_output_mode": required_output_mode,
                            "from": required_goal_shape,
                            "to": "ordinary",
                        }
                    )
                    required_goal_shape = "ordinary"
                    required_information_domain = "none"
                if (
                    required_goal_shape != "information_resource"
                    and required_information_domain != "none"
                ):
                    # This domain is a redundant refinement of an information
                    # resource. Decoder-small models can populate it from a physical
                    # task's likely observational means. Clearing it for every
                    # non-information shape changes no semantic branch.
                    item["required_information_domain"] = "none"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "cleared_non_information_domain",
                            "required_goal_shape": required_goal_shape,
                            "from": required_information_domain,
                            "to": "none",
                        }
                    )
                if role != "responsibility" and required_output_mode != "none":
                    # Completion mode refines the independently satisfiable outcome,
                    # not a supporting constraint/context item. Removing it from an
                    # ineligible branch changes no candidate ownership or verdict.
                    item["required_output_mode"] = "none"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "cleared_supporting_output_mode",
                            "role": role,
                            "from": required_output_mode,
                            "to": "none",
                        }
                    )
                if (
                    role in {"context", "framing"}
                    and item.get("coverage") == "covered"
                    and item.get("candidate_goal_indices")
                ):
                    # Context/framing is acknowledged but never owns a Goal. The
                    # model already classified the role and verdict; clearing an
                    # ineligible index removes only DTO correlation noise.
                    previous_indices = list(item.get("candidate_goal_indices") or [])
                    item["candidate_goal_indices"] = []
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "recovery": "cleared_context_goal_ownership",
                            "role": role,
                            "from": previous_indices,
                            "to": [],
                        }
                    )
                coverage = str(item.get("coverage") or "")
                indices = item.get("candidate_goal_indices")
                if not isinstance(indices, list) or not indices:
                    continue
                if coverage == "missing":
                    # "missing" plus a named attempted owner is structurally
                    # contradictory. Preserve the attempted owner but keep the
                    # certificate rejecting by normalizing to representation mismatch.
                    item["coverage"] = "representation_mismatch"
                    recoveries.append(
                        {
                            "item_index": item_index,
                            "from": "missing",
                            "to": "representation_mismatch",
                            "candidate_goal_indices": list(indices),
                        }
                    )
                normalized_source_excerpt = " ".join(
                    str(item.get("source_excerpt") or "").strip().casefold().split()
                )
                if (
                    item.get("coverage") == "covered"
                    and candidate_goals is not None
                    and isinstance(indices, list)
                    and indices
                ):
                    required_goal_shape = str(
                        item.get("required_goal_shape") or "ordinary"
                    )
                    required_information_domain = str(
                        item.get("required_information_domain") or "none"
                    )
                    required_output_mode = str(
                        item.get("required_output_mode") or "none"
                    )
                    mismatch_reasons: list[str] = []
                    for goal_index in indices:
                        if not isinstance(goal_index, int) or not (
                            0 <= goal_index < len(candidate_goals)
                        ):
                            continue
                        candidate = candidate_goals[goal_index]
                        binding_types = {
                            binding.entity_type.casefold()
                            for binding in candidate.semantic_bindings
                        }
                        resource = candidate.resource_responsibility
                        shape_matches = {
                            "ordinary": (
                                item.get("role") != "responsibility"
                                or (
                                    resource is None
                                    and candidate.output_mode != "capability_work"
                                )
                            ),
                            "information_resource": (
                                resource is not None
                                and resource.kind == "information"
                            ),
                            "physical_resource": (
                                resource is not None
                                and resource.kind == "physical_object"
                            ),
                            "persistent_effect": (
                                resource is None
                                and candidate.output_mode == "capability_work"
                            ),
                        }.get(required_goal_shape, False)
                        if not shape_matches:
                            mismatch_reasons.append(
                                "required_goal_shape=" + required_goal_shape
                            )
                        if (
                            required_goal_shape == "information_resource"
                            and resource is not None
                            and resource.kind == "information"
                            and resource.information_domain
                            != required_information_domain
                        ):
                            mismatch_reasons.append(
                                "required_information_domain="
                                + required_information_domain
                            )
                        if (
                            required_output_mode != "none"
                            and candidate.output_mode != required_output_mode
                        ):
                            mismatch_reasons.append(
                                "required_output_mode=" + required_output_mode
                            )
                        binding_conflicts = (
                            source_grounded_binding_coverage_conflicts(
                                [candidate],
                                request=request,
                            )
                        )
                        mismatch_reasons.extend(
                            "missing_source_grounded_binding=" + conflict
                            for conflict in binding_conflicts
                        )
                    if mismatch_reasons:
                        item["coverage"] = "representation_mismatch"
                        recoveries.append(
                            {
                                "item_index": item_index,
                                "from": "covered",
                                "to": "representation_mismatch",
                                "candidate_goal_indices": list(indices),
                                "reasons": sorted(set(mismatch_reasons)),
                            }
                        )
        if recoveries:
            logger.warning(
                "goal_association_coverage_shape_normalized sid=%s recoveries=%s",
                request.sid,
                cls._bounded_json(recoveries, 1800),
            )
        certificate = GoalResponsibilityCoverageCertificate.model_validate(normalized_raw)
        if any(
            item.coverage == "clarification_required"
            for item in certificate.items
        ) and not request.interpretation_unresolved:
            raise ValueError(
                "clarification_required coverage needs exact GI unresolved-meaning evidence"
            )
        authoritative_turn = " ".join(request.text.strip().split()).casefold()
        for index, item in enumerate(certificate.items):
            excerpt = " ".join(item.source_excerpt.strip().split()).casefold()
            if excerpt not in authoritative_turn:
                raise _CoverageSourceExcerptViolation(
                    "coverage source_excerpt must be a verbatim current-turn span: "
                    f"items[{index}]={item.source_excerpt!r}"
                )
            invalid_indices = [
                goal_index
                for goal_index in item.candidate_goal_indices
                if goal_index < 0 or goal_index >= goal_count
            ]
            if invalid_indices:
                raise ValueError(
                    "coverage references unknown Goal candidate indices: "
                    + ",".join(str(value) for value in invalid_indices)
                )
        return certificate


    def _expand_model_output(
        self,
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
        turn_id: str,
    ) -> GoalAssociationResolution:
        candidate_goals = self._candidate_goals(request)
        responsibility_by_ref = {
            item.local_ref: item for item in request.responsibilities
        }
        active_goal_ids = {
            str(item.get("goal_id") or "").strip()
            for item in candidate_goals
            if str(item.get("goal_id") or "").strip()
        }
        existing_referents = {
            str(item.get("referent_id") or "").strip(): item
            for item in discourse_referents(request)
            if str(item.get("referent_id") or "").strip()
        }

        associations: list[GoalAssociation] = []
        model_associations = (
            model_output.associations
            if isinstance(model_output, GoalAssociationModelOutput)
            else []
        )
        for index, item in enumerate(model_associations):
            goal_update: dict[str, Any] = {}
            if item.updated_description:
                goal_update["description"] = item.updated_description
            associations.append(
                GoalAssociation(
                    association_id=stable_goal_operation_id(
                        turn_id=turn_id,
                        ordinal=index,
                        relationship=item.relationship,
                        target_goal_ids=item.target_goal_ids,
                    ),
                    relationship=item.relationship,
                    source_responsibility_refs=item.source_responsibility_refs,
                    target_goal_ids=item.target_goal_ids,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                    goal_update=goal_update,
                    resolved_gap_ids=item.resolved_gap_ids,
                )
            )

        # Host generates canonical Goal IDs first so newly introduced referents
        # can be scoped to the Goals whose bindings use them.
        generated_goal_ids: list[str] = []
        for index, item in enumerate(model_output.new_goals):
            digest = hashlib.sha256(
                f"{turn_id}|goal|{index}|{item.description}".encode("utf-8")
            ).hexdigest()[:20]
            generated_goal_ids.append(f"goal_{digest}")

        referent_updates: list[DiscourseReferentUpdate] = []
        introduced_by_value: dict[tuple[str, str], str] = {}
        for index, item in enumerate(model_output.referent_updates):
            if item.confidence < self.min_confidence:
                raise ValueError(
                    "discourse referent update is below confidence threshold"
                )
            unknown_targets = [
                referent_id
                for referent_id in item.target_referent_ids
                if referent_id not in existing_referents
            ]
            if unknown_targets:
                raise ValueError(
                    "referent update targets unknown referent IDs: "
                    + ",".join(unknown_targets)
                )
            unknown_goals = [
                goal_id
                for goal_id in item.target_goal_ids
                if goal_id not in active_goal_ids
            ]
            if unknown_goals:
                raise ValueError(
                    "referent update targets unknown active Goal IDs: "
                    + ",".join(unknown_goals)
                )

            referent: DiscourseReferent | None = None
            if item.operation in {"introduce", "correct"}:
                referent_id = stable_referent_id(
                    turn_id=turn_id,
                    ordinal=index,
                    entity_type=item.entity_type,
                    canonical_value=item.canonical_value,
                )
                matching_new_goal_ids = [
                    goal_id
                    for goal_id, goal_item in zip(
                        generated_goal_ids,
                        model_output.new_goals,
                        strict=True,
                    )
                    if any(
                        binding.entity_type.casefold()
                        == item.entity_type.casefold()
                        and binding.value.casefold()
                        == item.canonical_value.casefold()
                        for binding in goal_item.semantic_bindings
                    )
                ]
                source_goal_ids = list(
                    dict.fromkeys([*item.target_goal_ids, *matching_new_goal_ids])
                )
                scope_ids = (
                    source_goal_ids
                    if item.scope_kind == "goal"
                    else item.target_goal_ids
                    if item.scope_kind == "task"
                    else []
                )
                referent = DiscourseReferent(
                    referent_id=referent_id,
                    entity_type=item.entity_type,
                    canonical_value=item.canonical_value,
                    aliases=item.aliases,
                    scope_kind=item.scope_kind,
                    scope_ids=scope_ids,
                    status="foreground",
                    confidence=item.confidence,
                    source_turn_id=turn_id,
                    source_goal_ids=source_goal_ids,
                    supersedes_referent_ids=(
                        item.target_referent_ids
                        if item.operation == "correct"
                        else []
                    ),
                    reason_summary=item.reason_summary,
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                    },
                )
                introduced_by_value[
                    (item.entity_type.casefold(), item.canonical_value.casefold())
                ] = referent_id
            referent_updates.append(
                DiscourseReferentUpdate(
                    operation=item.operation,
                    referent=referent,
                    target_referent_ids=item.target_referent_ids,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                )
            )

        resolved_references: list[ResolvedDiscourseReference] = []
        for item in model_output.resolved_references:
            referent_id = item.referent_id or introduced_by_value.get(
                (item.entity_type.casefold(), item.resolved_value.casefold()),
                "",
            )
            if item.source in {"discourse_referent", "active_goal_binding"}:
                if referent_id not in existing_referents:
                    raise ValueError(
                        f"resolved reference uses unknown referent_id={referent_id!r}"
                    )
                expected = existing_referents[referent_id]
                if (
                    str(expected.get("entity_type") or "").casefold()
                    != item.entity_type.casefold()
                    or str(expected.get("canonical_value") or "").casefold()
                    != item.resolved_value.casefold()
                ):
                    raise ValueError(
                        "resolved reference value does not match supplied referent"
                    )
            if item.confidence < self.min_confidence:
                raise ValueError(
                    "material reference resolution is below confidence threshold"
                )
            resolved_references.append(
                ResolvedDiscourseReference(
                    surface_form=item.surface_form,
                    entity_type=item.entity_type,
                    resolved_value=item.resolved_value,
                    source=item.source,
                    referent_id=referent_id or None,
                    confidence=item.confidence,
                    reason_summary=item.reason_summary,
                )
            )

        resolved_reference_by_value = {
            (item.entity_type.casefold(), item.resolved_value.casefold()): item
            for item in resolved_references
        }
        new_goals: list[SemanticGoal] = []
        for goal_id, item in zip(
            generated_goal_ids,
            model_output.new_goals,
            strict=True,
        ):
            def normalize_binding(
                binding: GoalAssociationModelBinding,
            ) -> dict[str, Any]:
                referent_id = binding.referent_id
                if not referent_id:
                    introduced = introduced_by_value.get(
                        (binding.entity_type.casefold(), binding.value.casefold())
                    )
                    if introduced:
                        referent_id = introduced
                    else:
                        resolved = resolved_reference_by_value.get(
                            (binding.entity_type.casefold(), binding.value.casefold())
                        )
                        referent_id = (resolved.referent_id if resolved else None) or ""
                if referent_id and (
                    referent_id not in existing_referents
                    and referent_id not in introduced_by_value.values()
                ):
                    raise ValueError(
                        f"goal binding uses unknown referent_id={referent_id!r}"
                    )
                normalized = GoalEntityBinding(
                    name=binding.name,
                    entity_type=binding.entity_type,
                    value=binding.value,
                    referent_id=referent_id or None,
                    confidence=binding.confidence,
                )
                return normalized.model_dump(
                    mode="json",
                    exclude_none=True,
                )

            binding_map: dict[str, Any] = {}
            resource_responsibility = None
            if item.resource_responsibility is not None:
                resource_item = item.resource_responsibility
                recipient_referent_id = resource_item.recipient.referent_id
                if (
                    recipient_referent_id
                    and recipient_referent_id not in existing_referents
                    and recipient_referent_id not in introduced_by_value.values()
                ):
                    raise ValueError(
                        "resource recipient uses unknown referent_id="
                        f"{recipient_referent_id!r}"
                    )

                if resource_item.kind == "information":
                    attribute_bindings = {
                        binding.name: normalize_binding(binding)
                        for binding in resource_item.query_scope
                    }
                    attribute_bindings["information_domain"] = (
                        GoalEntityBinding(
                            name="information_domain",
                            entity_type="information_domain",
                            value=resource_item.information_domain,
                            confidence=1.0,
                        ).model_dump(mode="json", exclude_none=True)
                    )
                    source_bindings: dict[str, Any] = {}
                    source_description = ""
                    if resource_item.source.status == "known":
                        source_binding = GoalAssociationModelBinding(
                            name="source",
                            entity_type="information_source",
                            value=resource_item.source.source_name,
                            referent_id=resource_item.source.referent_id or "",
                            confidence=resource_item.source.confidence,
                        )
                        source_bindings["source"] = normalize_binding(source_binding)
                        source_description = resource_item.source.source_name
                    resource_responsibility = AcquireAndDeliverResource(
                        resource=ResourceDescriptor(
                            kind="information",
                            description=resource_item.description,
                            quantity=resource_item.quantity,
                            attributes=attribute_bindings,
                        ),
                        source=ResourceSource(
                            status=resource_item.source.status,
                            description=source_description,
                            bindings=source_bindings,
                        ),
                        recipient=ResourceRecipient(
                            description=resource_item.recipient.description,
                            referent_id=recipient_referent_id,
                        ),
                        delivery_mode=resource_item.delivery_mode,
                    )
                else:
                    source_bindings = {
                        binding.name: normalize_binding(binding)
                        for binding in resource_item.source.acquisition_bindings
                    }
                    resource_responsibility = AcquireAndDeliverResource(
                        resource=ResourceDescriptor(
                            kind="physical_object",
                            description=resource_item.description,
                            quantity=resource_item.quantity,
                            attributes={},
                        ),
                        source=ResourceSource(
                            status=resource_item.source.status,
                            description=resource_item.source.description,
                            bindings=source_bindings,
                        ),
                        recipient=ResourceRecipient(
                            description=resource_item.recipient.description,
                            referent_id=recipient_referent_id,
                        ),
                        delivery_mode="physical_handover",
                    )
            else:
                for binding in item.bindings:
                    normalized = normalize_binding(binding)
                    if binding.name in binding_map:
                        raise ValueError(
                            f"duplicate Goal binding name={binding.name!r}"
                        )
                    binding_map[binding.name] = normalized

            unknown_related_goal_ids = sorted(
                set(item.related_goal_ids) - active_goal_ids
            )
            if unknown_related_goal_ids:
                raise ValueError(
                    "new Goal references unknown related Goal IDs: "
                    + ", ".join(unknown_related_goal_ids)
                )
            unknown_superseded_goal_ids = sorted(
                set(item.supersedes_goal_ids) - active_goal_ids
            )
            if unknown_superseded_goal_ids:
                raise ValueError(
                    "replacement Goal references unknown superseded Goal IDs: "
                    + ", ".join(unknown_superseded_goal_ids)
                )
            if set(item.related_goal_ids).intersection(item.supersedes_goal_ids):
                raise ValueError(
                    "replacement Goal cannot also retain a superseded Goal as related context"
                )
            new_goals.append(
                SemanticGoal(
                    goal_id=goal_id,
                    source_responsibility_refs=item.source_responsibility_refs,
                    description=item.description,
                    source_text=request.original_user_text,
                    object={"bindings": binding_map} if binding_map else {},
                    constraints={},
                    success_criteria=[item.description],
                    resource_responsibility=resource_responsibility,
                    related_goal_ids=item.related_goal_ids,
                    supersedes_goal_ids=item.supersedes_goal_ids,
                    metadata={
                        "model_boundary": type(model_output).__name__,
                        "host_generated_fields": True,
                        "responsibility_kind": item.responsibility_kind,
                        "execution_lane": item.execution_lane,
                        "output_mode": item.output_mode,
                        "provider_required": item.provider_required,
                        "completion_requires_work": any(
                            responsibility_by_ref[source_ref].completion_requires_work
                            for source_ref in item.source_responsibility_refs
                            if source_ref in responsibility_by_ref
                        ),
                        "completion_requires_fresh_evidence": any(
                            responsibility_by_ref[
                                source_ref
                            ].completion_requires_fresh_evidence
                            for source_ref in item.source_responsibility_refs
                            if source_ref in responsibility_by_ref
                        ),
                        "media_operation": item.media_operation,
                        "resolved_references": [
                            reference.model_dump(mode="json", exclude_none=True)
                            for reference in resolved_references
                        ],
                    },
                )
            )


        responsibility_refs = [item.local_ref for item in request.responsibilities]
        mapped_refs = [
            ref
            for association in associations
            for ref in association.source_responsibility_refs
        ] + [
            ref
            for goal in new_goals
            for ref in goal.source_responsibility_refs
        ]
        if sorted(mapped_refs) != sorted(responsibility_refs):
            raise ValueError(
                "Goal Association must map every GI Responsibility exactly once: "
                f"expected={sorted(responsibility_refs)} actual={sorted(mapped_refs)}"
            )
        return GoalAssociationResolution(
            turn_id=turn_id,
            resolution_status="resolved",
            associations=associations,
            new_goals=new_goals,
            referent_updates=referent_updates,
            resolved_references=resolved_references,
            confidence=model_output.confidence,
            reason_summary=model_output.reason_summary,
            metadata={
                "model_contract": type(model_output).__name__,
                "host_generated_identifiers": True,
                "discourse_resolution_authority": "goal_association_llm",
            },
        )

    def _validate(
        self,
        resolution: GoalAssociationResolution,
        *,
        candidate_goals: list[dict[str, Any]],
        request: CognitiveWorkRequest,
    ) -> GoalAssociationResolution:
        candidate_ids = {
            str(item.get("goal_id") or "") for item in candidate_goals
        }
        accepted: list[GoalAssociation] = []
        rejected: list[dict[str, Any]] = []
        for association in resolution.associations:
            reason = None
            if association.confidence < self.min_confidence:
                reason = "below_confidence_threshold"
            elif any(
                goal_id not in candidate_ids
                for goal_id in association.target_goal_ids
            ):
                reason = "unknown_target_goal"
            if reason:
                rejected.append({"association_id": association.association_id, "reason": reason})
            else:
                accepted.append(association)

        new_goals = resolution.new_goals

        metadata = dict(resolution.metadata)
        metadata.update(
            {
                "resolver": "goal_association_agent",
                "status": "resolved",
                "candidate_goal_count": len(candidate_goals),
                "accepted_association_count": len(accepted),
                "new_goal_count": len(new_goals),
                "referent_update_count": len(resolution.referent_updates),
                "resolved_reference_count": len(resolution.resolved_references),
                "rejected_associations": rejected,
                "min_confidence": self.min_confidence,
                "sid": request.sid,
                "authority": "advisory",
            }
        )
        if (
            not accepted
            and not new_goals
            and not resolution.referent_updates
        ):
            return GoalAssociationResolution(
                turn_id=resolution.turn_id,
                resolution_status="fail_closed",
                confidence=0.0,
                reason_summary=(
                    "No sufficiently grounded Goal association or new Goal reached "
                    "the canonical commit boundary."
                ),
                metadata={**metadata, "status": "fail_closed"},
            )
        return resolution.model_copy(update={"associations": accepted, "new_goals": new_goals, "metadata": metadata})
