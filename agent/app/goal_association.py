from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import copy
import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import ValidationError

from .clients.ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    owner_approved_identity_context,
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
    _EXECUTION_CONTRACT_PROMPT,
    _GOAL_SEGMENTATION_IDENTITY_CONTRACT,
    GoalAssociationModelAssociation,
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelInformationResourceResponsibility,
    GoalAssociationModelOutput,
    GoalAssociationModelPhysicalResourceResponsibility,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
    _validate_model_resource_quantity,
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
        response_schema = self._response_schema(
            output_type,
            candidate_goals,
            self._discourse_referents(request),
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
            normalized, recovered = self._drop_invalid_optional_referent_introductions(
                value
            )
            optional_referent_recovery.extend(recovered)
            normalized, recovered = self._drop_inactive_resource_bindings(
                normalized
            )
            redundant_resource_binding_recovery.extend(recovered)
            normalized, recovered = self._drop_invalid_optional_resource_quantities(
                normalized
            )
            invalid_optional_quantity_recovery.extend(recovered)
            normalized, recovered = self._drop_ungrounded_resource_query_locations(
                normalized,
                request=request,
            )
            ungrounded_resource_location_recovery.extend(recovered)
            normalized, recovered = self._normalize_grounded_generic_location_types(
                normalized,
                request=request,
            )
            generic_location_type_recovery.extend(recovered)
            normalized, recovered = self._restore_missing_goal_descriptions(
                normalized,
                request=request,
            )
            missing_description_recovery.extend(recovered)
            return normalized

        try:
            initial_raw = normalize_raw(
                await invoke(
                    self._layered_prompt(
                        request,
                        candidate_goals,
                        output_type=output_type,
                    ),
                    system=self._system_prompt(output_type),
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
                        self._layered_repair_prompt(
                            request=request,
                            candidate_goals=candidate_goals,
                            turn_id=turn_id,
                            output_type=output_type,
                            raw=initial_raw,
                            validation_error=self._validation_error_json(
                                initial_exc
                            ),
                        ),
                        system=self._repair_system_prompt(output_type),
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
            if self._responsibility_coverage_required(
                model_output,
                request=request,
            ):
                coverage_metadata["attempted"] = True
                certificate_raw = await invoke(
                    self._build_responsibility_coverage_prompt(
                        request=request,
                        raw=accepted_raw,
                    ),
                    system=self._responsibility_coverage_system_prompt(),
                    response_format=self._coverage_certificate_response_schema(
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
                        for conflict in self._source_grounded_binding_coverage_conflicts(
                            model_output,
                            request=request,
                        )
                    )
                    coverage_metadata["initial_certificate_contract_error"] = (
                        "source_excerpt_not_authoritative"
                    )
                else:
                    verdict, problems = self._coverage_verdict(
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
                            self._build_fresh_interpretation_prompt(
                                request=request,
                                candidate_goals=candidate_goals,
                                output_type=output_type,
                                problems=problems,
                                preserve_unresolved_meaning=clarification_required,
                            ),
                            system=self._semantic_review_system_prompt(
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
                    if self._responsibility_coverage_required(
                        reconsidered_output,
                        request=request,
                    ):
                        certificate_raw = await invoke(
                            self._build_responsibility_coverage_prompt(
                                request=request,
                                raw=accepted_raw,
                            ),
                            system=self._responsibility_coverage_system_prompt(),
                            response_format=self._coverage_certificate_response_schema(
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
                        final_verdict, final_problems = self._coverage_verdict(
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


    @staticmethod
    def _drop_invalid_optional_referent_introductions(
        raw: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Drop only semantically unusable optional referent-index updates.

        Referent focus changes, retirements, and introductions with actual entity
        content remain contract-authoritative and still fail closed. A correction
        without any supplied target referent cannot update the discourse index; the
        canonical Goal association and coverage audit remain responsible for the
        actual correction meaning.
        A model-added ``introduce`` item with neither an entity type nor canonical
        value cannot ground any Goal binding and must not discard otherwise valid
        Goals.
        """

        normalized = copy.deepcopy(raw)
        updates = normalized.get("referent_updates")
        if not isinstance(updates, list):
            return normalized, []
        kept: list[Any] = []
        dropped: list[dict[str, Any]] = []
        for index, item in enumerate(updates):
            if not isinstance(item, dict):
                kept.append(item)
                continue
            operation = str(item.get("operation") or "").strip()
            entity_type = str(item.get("entity_type") or "").strip()
            canonical_value = str(item.get("canonical_value") or "").strip()
            target_referent_ids = item.get("target_referent_ids") or []
            target_goal_ids = item.get("target_goal_ids") or []
            if (
                operation == "introduce"
                and not entity_type
                and not canonical_value
                and not target_referent_ids
                and not target_goal_ids
            ):
                dropped.append(
                    {
                        "path": f"referent_updates[{index}]",
                        "operation": "introduce",
                        "reason": "missing_entity_type_and_canonical_value",
                    }
                )
                continue
            if operation == "correct" and not target_referent_ids:
                dropped.append(
                    {
                        "path": f"referent_updates[{index}]",
                        "operation": "correct",
                        "reason": "missing_target_referent_ids",
                    }
                )
                continue
            kept.append(item)
        normalized["referent_updates"] = kept
        return normalized, dropped

    @staticmethod
    def _drop_inactive_resource_bindings(
        raw: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Normalize model content from a resource Goal's inactive binding branch.

        Resource Goals have one semantic owner: ``resource_responsibility``. Some
        structured-output models nevertheless populate the mutually exclusive top-
        level ``bindings`` branch. Move nonduplicate model-authored bindings into the
        discriminated resource owner before clearing the inactive branch. This is
        mechanical DTO normalization: no value is inferred or rewritten, and the
        independent source-grounded coverage certificate still decides whether each
        migrated fact belongs to the Responsibility.
        """

        normalized = copy.deepcopy(raw)
        goals = normalized.get("new_goals")
        if not isinstance(goals, list):
            return normalized, []

        dropped: list[dict[str, Any]] = []
        for index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            top_level = goal.get("bindings")
            if not isinstance(top_level, list):
                top_level = []
            resource = goal.get("resource_responsibility")
            if not isinstance(resource, dict):
                continue
            kind = str(resource.get("kind") or "").strip()
            if kind not in {"information", "physical_object"}:
                continue
            if kind == "information":
                target = resource.get("query_scope")
            else:
                source = resource.get("source")
                target = (
                    source.get("acquisition_bindings")
                    if isinstance(source, dict)
                    else None
                )
            physical_source_unknown = bool(
                kind == "physical_object"
                and isinstance(resource.get("source"), dict)
                and resource["source"].get("status") != "known"
            )
            has_inactive_physical_grounding = bool(
                physical_source_unknown
                and isinstance(target, list)
                and target
            )
            if physical_source_unknown and (top_level or has_inactive_physical_grounding):
                # `status` is the discriminant: unknown/provider-resolved sources
                # cannot own acquisition grounding. Clear model content from that
                # inactive branch so the independent semantic coverage audit can
                # decide whether the entire resource wrapper was justified. Never
                # flip unknown to known or reinterpret body-motion parameters as an
                # object-acquisition location.
                source = resource["source"]
                existing = source.pop("acquisition_bindings", [])
                goal["bindings"] = []
                dropped.append(
                    {
                        "path": f"new_goals[{index}].bindings",
                        "resource_kind": kind,
                        "binding_count": len(top_level),
                        "migrated_count": 0,
                        "inactive_acquisition_binding_count": (
                            len(existing) if isinstance(existing, list) else 0
                        ),
                        "reason": "unknown_physical_source_has_no_grounding_branch",
                    }
                )
                continue
            if not top_level:
                continue
            if not isinstance(target, list):
                target = []
                if kind == "information":
                    resource["query_scope"] = target
                elif isinstance(resource.get("source"), dict):
                    resource["source"]["acquisition_bindings"] = target
            fingerprints = {
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for item in target
            }
            migrated_count = 0
            for binding in top_level:
                fingerprint = json.dumps(
                    binding,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if fingerprint in fingerprints:
                    continue
                target.append(copy.deepcopy(binding))
                fingerprints.add(fingerprint)
                migrated_count += 1
            goal["bindings"] = []
            dropped.append(
                {
                    "path": f"new_goals[{index}].bindings",
                    "resource_kind": kind,
                    "binding_count": len(top_level),
                    "migrated_count": migrated_count,
                    "reason": "normalized_into_active_resource_binding_branch",
                }
            )
        return normalized, dropped

    @staticmethod
    def _drop_invalid_optional_resource_quantities(
        raw: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Drop only malformed optional quantity scalars before validation.

        No replacement quantity is inferred. Responsibility coverage still proves
        conservation of any source-grounded quantity, so removing decoder noise
        cannot silently erase a quantity the human actually supplied.
        """

        normalized = copy.deepcopy(raw)
        goals = normalized.get("new_goals")
        if not isinstance(goals, list):
            return normalized, []
        dropped: list[dict[str, Any]] = []
        for index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            resource = goal.get("resource_responsibility")
            if not isinstance(resource, dict) or "quantity" not in resource:
                continue
            value = resource.get("quantity")
            if value is None or value == "":
                continue
            try:
                if not isinstance(value, str):
                    raise ValueError("quantity is not a string")
                _validate_model_resource_quantity(value.strip())
            except (TypeError, ValueError):
                resource.pop("quantity", None)
                dropped.append(
                    {
                        "path": (
                            f"new_goals[{index}].resource_responsibility.quantity"
                        ),
                        "reason": "invalid_optional_quantity_scalar",
                        "input_type": type(value).__name__,
                    }
                )
        return normalized, dropped

    @staticmethod
    def _restore_missing_goal_descriptions(
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Restore a mechanically omitted description from its exact source outcome.

        The source Responsibility remains the semantic authority.  Recovery is
        permitted only when the candidate names exactly one admitted local_ref and
        its description is absent or blank; no wording is generated or inferred.
        Responsibility/output-mode conservation and the independent coverage audit
        still validate the resulting Goal.
        """

        normalized = copy.deepcopy(raw)
        outcomes = {
            item.local_ref: item.outcome
            for item in request.responsibilities
            if item.local_ref and item.outcome
        }
        recovered: list[dict[str, Any]] = []
        goals = normalized.get("new_goals")
        if not isinstance(goals, list):
            return normalized, recovered
        for index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            if str(goal.get("description") or "").strip():
                continue
            source_refs = goal.get("source_responsibility_refs")
            if not isinstance(source_refs, list) or len(source_refs) != 1:
                continue
            source_ref = str(source_refs[0] or "").strip()
            outcome = outcomes.get(source_ref)
            if not outcome:
                continue
            goal["description"] = outcome
            recovered.append(
                {
                    "path": f"new_goals[{index}].description",
                    "source_responsibility_ref": source_ref,
                    "semantic_value_unchanged": True,
                }
            )
        return normalized, recovered

    @staticmethod
    def _drop_ungrounded_resource_query_locations(
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Drop an invented optional query location without choosing a replacement.

        This restores Responsibility conservation before validation.  Coverage
        remains responsible for rejecting the Goal when location was actually
        material, so the normalization cannot silently satisfy missing meaning.
        """

        normalized = copy.deepcopy(raw)
        authoritative_turn = " ".join(request.text.strip().split()).casefold()
        grounded_values = {
            " ".join(str(value).strip().split()).casefold()
            for responsibility in request.responsibilities
            for value in responsibility.bindings.values()
            if str(value).strip()
        }
        resolved_values = {
            " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
            for item in normalized.get("resolved_references") or []
            if isinstance(item, dict)
            and str(item.get("resolved_value") or "").strip()
        }
        location_types = {
            "address",
            "city",
            "country",
            "county",
            "location",
            "place",
            "region",
        }
        dropped: list[dict[str, Any]] = []
        goals = normalized.get("new_goals")
        if not isinstance(goals, list):
            return normalized, dropped
        for goal_index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            resource = goal.get("resource_responsibility")
            if not isinstance(resource, dict) or resource.get("kind") != "information":
                continue
            query_scope = resource.get("query_scope")
            if not isinstance(query_scope, list):
                continue
            kept: list[Any] = []
            for binding_index, binding in enumerate(query_scope):
                if not isinstance(binding, dict):
                    kept.append(binding)
                    continue
                name = "_".join(
                    str(binding.get("name") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                entity_type = "_".join(
                    str(binding.get("entity_type") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                value = " ".join(
                    str(binding.get("value") or "").strip().split()
                ).casefold()
                is_location = name == "location" or entity_type in location_types
                grounded = bool(
                    value
                    and (
                        value in authoritative_turn
                        or value in grounded_values
                        or value in resolved_values
                    )
                )
                if (
                    not is_location
                    or str(binding.get("referent_id") or "").strip()
                    or grounded
                ):
                    kept.append(binding)
                    continue
                dropped.append(
                    {
                        "path": (
                            f"new_goals[{goal_index}].resource_responsibility."
                            f"query_scope[{binding_index}]"
                        ),
                        "name": str(binding.get("name") or ""),
                        "entity_type": str(binding.get("entity_type") or ""),
                        "value": str(binding.get("value") or ""),
                        "reason": "not_entailed_by_turn_responsibility_or_referent",
                    }
                )
            resource["query_scope"] = kept
        return normalized, dropped

    @staticmethod
    def _normalize_grounded_generic_location_types(
        raw: dict[str, Any],
        *,
        request: CognitiveWorkRequest,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Canonicalize only a source-grounded location with a generic DTO type.

        The model already owns the semantic field name and exact value. This adapter
        changes neither; it replaces only the mechanically non-semantic ``string``/
        ``text``/``entity`` type label after the value is proven by the authoritative
        turn, GI bindings, or an admitted resolved reference.
        """

        normalized = copy.deepcopy(raw)
        authoritative_turn = " ".join(request.text.strip().split()).casefold()
        grounded_values = {
            " ".join(str(value).strip().split()).casefold()
            for responsibility in request.responsibilities
            for value in responsibility.bindings.values()
            if str(value).strip()
        }
        grounded_values.update(
            " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
            for item in normalized.get("resolved_references") or []
            if isinstance(item, dict)
            and str(item.get("resolved_value") or "").strip()
        )
        generic_types = {"entity", "string", "text"}
        repaired: list[dict[str, Any]] = []
        goals = normalized.get("new_goals")
        if not isinstance(goals, list):
            return normalized, repaired
        for goal_index, goal in enumerate(goals):
            if not isinstance(goal, dict):
                continue
            surfaces: list[tuple[str, Any]] = [("bindings", goal.get("bindings"))]
            resource = goal.get("resource_responsibility")
            if isinstance(resource, dict):
                if resource.get("kind") == "information":
                    surfaces.append(("resource.query_scope", resource.get("query_scope")))
                source = resource.get("source")
                if isinstance(source, dict):
                    surfaces.append(
                        (
                            "resource.source.acquisition_bindings",
                            source.get("acquisition_bindings"),
                        )
                    )
            for surface_name, bindings in surfaces:
                if not isinstance(bindings, list):
                    continue
                for binding_index, binding in enumerate(bindings):
                    if not isinstance(binding, dict):
                        continue
                    name = "_".join(
                        str(binding.get("name") or "")
                        .strip()
                        .casefold()
                        .replace("-", "_")
                        .split()
                    )
                    entity_type = "_".join(
                        str(binding.get("entity_type") or "")
                        .strip()
                        .casefold()
                        .replace("-", "_")
                        .split()
                    )
                    value = " ".join(
                        str(binding.get("value") or "").strip().split()
                    ).casefold()
                    if (
                        name != "location"
                        or entity_type not in generic_types
                        or not value
                        or (
                            value not in authoritative_turn
                            and value not in grounded_values
                        )
                    ):
                        continue
                    binding["entity_type"] = "place"
                    repaired.append(
                        {
                            "path": (
                                f"new_goals[{goal_index}].{surface_name}"
                                f"[{binding_index}].entity_type"
                            ),
                            "from": entity_type,
                            "to": "place",
                            "value_unchanged": True,
                        }
                    )
        return normalized, repaired

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
        collection_bindings = self._action_collection_bindings(model_output)
        if collection_bindings:
            raise ValueError(
                "new Goal bindings cannot contain action collections; emit one "
                "new_goals item for every independently observable responsibility: "
                + ", ".join(collection_bindings)
            )
        output_mode_conflicts = self._responsibility_output_mode_conflicts(
            model_output,
            request=request,
        )
        if output_mode_conflicts:
            raise ValueError(
                "new Goal output_mode must preserve Goal Interpretation's "
                "provider-neutral completion modality: "
                + ", ".join(output_mode_conflicts)
            )
        binding_conflicts = self._binding_semantic_contract_conflicts(model_output)
        if binding_conflicts:
            raise ValueError(
                "binding name and entity_type cannot declare conflicting canonical "
                "parameter categories; preserve the intended parameter and correct "
                "the contradictory field: "
                + ", ".join(binding_conflicts)
            )
        resource_source_conflicts = (
            self._resource_source_binding_contract_conflicts(model_output)
        )
        if resource_source_conflicts:
            raise ValueError(
                "physical resource source.acquisition_bindings may describe only an "
                "actual spatial/acquisition constraint. Resource identity, "
                "requested quantity, recipient, and delivery fields are not source "
                "evidence: "
                + ", ".join(resource_source_conflicts)
            )
        location_bindings = self._non_verbatim_explicit_location_bindings(
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

    @staticmethod
    def _action_collection_bindings(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    ) -> list[str]:
        rejected: list[str] = []
        for goal_index, goal in enumerate(model_output.new_goals):
            for binding in goal.semantic_bindings:
                entity_type = "_".join(
                    binding.entity_type.strip().casefold().replace("-", "_").split()
                )
                if "action" in entity_type and (
                    "list" in entity_type
                    or "set" in entity_type
                    or "group" in entity_type
                    or "collection" in entity_type
                ):
                    rejected.append(
                        f"new_goals[{goal_index}].bindings[{binding.name}]="
                        f"{binding.entity_type}"
                    )
        return rejected

    @staticmethod
    def _responsibility_output_mode_conflicts(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
    ) -> list[str]:
        expected = {
            item.local_ref: item.output_mode
            for item in request.responsibilities
            if item.output_mode != "unspecified"
        }
        conflicts: list[str] = []
        for goal_index, goal in enumerate(model_output.new_goals):
            for source_ref in goal.source_responsibility_refs:
                required = expected.get(source_ref)
                if required is None or goal.output_mode == required:
                    continue
                conflicts.append(
                    f"new_goals[{goal_index}] source_ref={source_ref} "
                    f"expected={required} actual={goal.output_mode}"
                )
        return conflicts

    @staticmethod
    def _binding_semantic_contract_conflicts(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    ) -> list[str]:
        """Reject contradictions between model-authored canonical binding fields.

        This does not infer a parameter from user wording. It only prevents a DTO
        from calling the same binding a different or non-canonical parameter kind,
        such as ``name=distance`` with ``entity_type=quantity`` or the generic
        ``measurement`` label. The decoder already exposes this exact invariant;
        runtime validation keeps it fail-closed when a provider ignores the clause.
        """

        categories = {
            "distance": {"distance"},
            "direction": {"direction"},
            "quantity": {
                "amount",
                "count",
                "item_count",
                "quantity",
                "quantity_binding",
                "resource_count",
                "resource_quantity",
            },
        }
        category_by_token = {
            token: category
            for category, tokens in categories.items()
            for token in tokens
        }
        conflicts: list[str] = []
        for goal_index, goal in enumerate(model_output.new_goals):
            for binding_index, binding in enumerate(goal.semantic_bindings):
                name = "_".join(
                    binding.name.strip().casefold().replace("-", "_").split()
                )
                entity_type = "_".join(
                    binding.entity_type.strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                name_category = category_by_token.get(name)
                type_category = category_by_token.get(entity_type)
                if name_category is not None and type_category != name_category:
                    conflicts.append(
                        f"new_goals[{goal_index}].bindings[{binding_index}]="
                        f"{binding.name}/{binding.entity_type}"
                    )
        return conflicts

    @staticmethod
    def _resource_source_binding_contract_conflicts(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    ) -> list[str]:
        """Report invalid model-declared links from a resource to source evidence.

        This is a typed integrity check over fields the model already authored. It
        does not infer a source, binding, parameter, or value from user wording.
        It prevents the resource's identity, requested amount, recipient, or delivery
        mode from being relabelled as the place/source from which that resource should
        be acquired. A focused model revision remains responsible for semantic repair.
        """

        non_source_names = {
            "amount",
            "count",
            "delivery_mode",
            "delivery_recipient",
            "desired_item",
            "item",
            "item_count",
            "object",
            "quantity",
            "recipient",
            "resource",
            "resource_count",
            "resource_description",
            "resource_identity",
            "resource_kind",
            "resource_quantity",
            "target_item",
        }
        identity_or_quantity_types = {
            "amount",
            "count",
            "item",
            "object",
            "physical_object",
            "quantity",
            "resource",
            "resource_identity",
            "resource_kind",
        }
        explicit_source_names = {
            "direction",
            "distance",
            "location",
            "origin",
            "path",
            "place",
            "provider",
            "route",
            "source",
            "source_location",
            "source_provider",
            "spatial_offset",
        }
        spatial_source_types = {
            "direction",
            "distance",
            "location",
            "place",
            "relative_location",
            "route",
        }

        conflicts: list[str] = []
        for goal_index, goal in enumerate(model_output.new_goals):
            resource = goal.resource_responsibility
            if resource is None:
                continue
            if resource.kind != "physical_object":
                continue
            for binding in resource.source.acquisition_bindings:
                source_name = binding.name
                normalized_name = "_".join(
                    binding.name.strip().casefold().replace("-", "_").split()
                )
                normalized_type = "_".join(
                    binding.entity_type.strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                if (
                    normalized_name in non_source_names
                    or normalized_name not in explicit_source_names
                    or normalized_type not in spatial_source_types
                    or (
                        normalized_type in identity_or_quantity_types
                        and normalized_name not in explicit_source_names
                    )
                ):
                    conflicts.append(
                        f"new_goals[{goal_index}].resource_responsibility."
                        f"source.acquisition_bindings[{source_name}]="
                        f"non_source_semantics({binding.name}/{binding.entity_type})"
                    )
        return conflicts

    @staticmethod
    def _source_grounded_binding_coverage_conflicts(
        model_output: (
            GoalAssociationModelOutput
            | GoalSegmentationModelOutput
            | list[GoalAssociationModelGoal]
        ),
        *,
        request: CognitiveWorkRequest,
    ) -> list[str]:
        """Conserve direct GI material values on their one typed Goal surface.

        Goal Interpretation already owns whether a value is material WHAT. This
        check does not infer a parameter kind from the utterance; it follows the
        model-authored source_responsibility_refs and verifies that directly
        source-grounded values did not disappear. The Goal description is the
        authoritative owner of the action/effect itself, while bindings own its
        material parameters; an exact source action retained in that description
        therefore does not need a redundant ``action`` binding.
        Context-normalized values absent from the literal turn remain governed by
        their dedicated temporal/referent contracts.
        """

        authoritative_turn = " ".join(request.text.strip().casefold().split())
        expected_by_ref: dict[str, set[tuple[str, str]]] = {}

        def scalar_values(value: Any) -> set[str]:
            if isinstance(value, str):
                normalized = " ".join(value.strip().casefold().split())
                return {normalized} if normalized else set()
            if isinstance(value, dict):
                return {
                    item
                    for nested in value.values()
                    for item in scalar_values(nested)
                }
            if isinstance(value, (list, tuple)):
                return {
                    item
                    for nested in value
                    for item in scalar_values(nested)
                }
            return set()

        for responsibility in request.responsibilities:
            expected_by_ref[responsibility.local_ref] = {
                (
                    "_".join(str(name).strip().casefold().replace("-", "_").split()),
                    value,
                )
                for name, raw_value in responsibility.bindings.items()
                for value in scalar_values(raw_value)
                if value in authoritative_turn
            }

        conflicts: list[str] = []
        goals = model_output if isinstance(model_output, list) else model_output.new_goals
        for goal_index, goal in enumerate(goals):
            expected_pairs = {
                pair
                for source_ref in goal.source_responsibility_refs
                for pair in expected_by_ref.get(source_ref, set())
            }
            if not expected_pairs:
                continue
            resource = goal.resource_responsibility
            canonicalized_binding_names: set[str] = set()
            if resource is None:
                actual = {
                    " ".join(binding.value.strip().casefold().split())
                    for binding in goal.semantic_bindings
                }
                canonicalized_binding_names = {
                    "_".join(
                        binding.name.strip().casefold().replace("-", "_").split()
                    )
                    for binding in goal.semantic_bindings
                    if binding.entity_type.casefold() == "speed"
                }
                normalized_description = " ".join(
                    goal.description.strip().casefold().split()
                )
                actual.update(
                    value
                    for name, value in expected_pairs
                    if name in {"action", "activity", "effect", "outcome"}
                    and value in normalized_description
                )
            elif resource.kind == "information":
                actual = {
                    " ".join(binding.value.strip().casefold().split())
                    for binding in resource.query_scope
                }
                actual.update(
                    scalar_values(resource.quantity)
                )
                actual.update(scalar_values(resource.recipient.description))
                if resource.source.status == "known":
                    actual.update(scalar_values(resource.source.source_name))
            else:
                actual = {
                    " ".join(binding.value.strip().casefold().split())
                    for binding in resource.source.acquisition_bindings
                }
                normalized_description = " ".join(
                    goal.description.strip().casefold().split()
                )
                normalized_resource_description = " ".join(
                    resource.description.strip().casefold().split()
                )
                actual.update(
                    value
                    for name, value in expected_pairs
                    if name in {"action", "activity", "effect", "outcome"}
                    and value in normalized_description
                )
                actual.update(
                    value
                    for name, value in expected_pairs
                    if name
                    in {
                        "desired_item",
                        "item",
                        "object",
                        "resource",
                        "resource_identity",
                        "target_item",
                    }
                    and value in normalized_resource_description
                )
                actual.update(
                    value
                    for name, value in expected_pairs
                    if name in {"amount", "count", "quantity", "resource_quantity"}
                    and value in scalar_values(resource.quantity)
                )
                actual.update(
                    value
                    for name, value in expected_pairs
                    if name in {"recipient", "delivery_recipient"}
                    and value in scalar_values(resource.recipient.description)
                )
            for _, missing in sorted(
                pair
                for pair in expected_pairs
                if pair[1] not in actual
                and pair[0] not in canonicalized_binding_names
            ):
                conflicts.append(
                    f"new_goals[{goal_index}] source_refs="
                    f"{','.join(goal.source_responsibility_refs)} missing={missing!r}"
                )
        return conflicts

    @staticmethod
    def _non_verbatim_explicit_location_bindings(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
    ) -> list[str]:
        """Reject ungrounded rewrites of directly named locations.

        Indirect references keep their resolved canonical value and provenance.
        A new location without referent provenance, however, came from the current
        explicit user turn and must remain source-grounded user language after
        whitespace normalization.  This prevents a model translation or
        transliteration from silently changing which real place a provider sees.
        """

        authoritative_turn = " ".join(request.text.strip().split()).casefold()
        resolved_values = {
            (item.entity_type.casefold(), item.resolved_value.casefold())
            for item in model_output.resolved_references
        }
        rejected: list[str] = []
        canonical_location_types = {
            "address",
            "city",
            "country",
            "county",
            "location",
            "place",
            "relative_location",
            "region",
        }
        for goal_index, goal in enumerate(model_output.new_goals):
            for binding in goal.semantic_bindings:
                name = "_".join(
                    binding.name.strip().casefold().replace("-", "_").split()
                )
                entity_type = "_".join(
                    binding.entity_type.strip().casefold().replace("-", "_").split()
                )
                if name != "location" and entity_type not in {
                    "address",
                    "city",
                    "country",
                    "county",
                    "location",
                    "place",
                    "region",
                }:
                    continue
                if name == "location" and entity_type not in canonical_location_types:
                    rejected.append(
                        f"new_goals[{goal_index}].bindings[{binding.name}]="
                        f"non_location_semantics({binding.entity_type!r})"
                    )
                    continue
                if binding.referent_id or (
                    binding.entity_type.casefold(),
                    binding.value.casefold(),
                ) in resolved_values:
                    continue
                value = " ".join(binding.value.strip().split()).casefold()
                if value not in authoritative_turn:
                    rejected.append(
                        f"new_goals[{goal_index}].bindings[{binding.name}]="
                        f"{binding.value!r}"
                    )
        return rejected


    @staticmethod
    def _validation_error_json(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            payload: Any = exc.errors(include_url=False)
        else:
            payload = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
        return bounded_json(payload, 6000)


    @staticmethod
    def _response_schema(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        candidate_goals: list[dict[str, Any]],
        discourse_referents: list[dict[str, Any]],
        *,
        responsibility_count: int | None = None,
        responsibility_refs: list[str] | None = None,
        responsibility_output_modes: dict[str, str] | None = None,
        responsibility_fresh_evidence_refs: set[str] | None = None,
        responsibility_bindings: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        schema = copy.deepcopy(output_type.model_json_schema())
        active_ids = [
            " ".join(str(item.get("goal_id") or "").strip().split())
            for item in candidate_goals
            if " ".join(str(item.get("goal_id") or "").strip().split())
        ]
        referent_ids = [
            " ".join(str(item.get("referent_id") or "").strip().split())
            for item in discourse_referents
            if " ".join(str(item.get("referent_id") or "").strip().split())
        ]
        gap_ids = [
            " ".join(str(gap.get("gap_id") or "").strip().split())
            for goal in candidate_goals
            for gap in (goal.get("open_information_gaps") or [])
            if isinstance(gap, dict)
            and " ".join(str(gap.get("gap_id") or "").strip().split())
        ]
        responsibility_refs = list(responsibility_refs or [])
        responsibility_output_modes = dict(responsibility_output_modes or {})
        responsibility_fresh_evidence_refs = set(
            responsibility_fresh_evidence_refs or set()
        )
        responsibility_bindings = {
            str(source_ref): dict(bindings)
            for source_ref, bindings in (responsibility_bindings or {}).items()
        }
        properties = schema.get("properties", {})
        new_goals = properties.get("new_goals")
        if isinstance(new_goals, dict):
            new_goals["maxItems"] = (
                8
                if responsibility_count is None
                else min(8, max(0, int(responsibility_count)))
            )
        if not referent_ids:
            resolved_references = properties.get("resolved_references")
            if isinstance(resolved_references, dict):
                resolved_references["maxItems"] = 0

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
                    source_refs = node_properties.get("source_responsibility_refs")
                    if isinstance(source_refs, dict):
                        required_fields = list(node.get("required") or [])
                        if "source_responsibility_refs" not in required_fields:
                            required_fields.append("source_responsibility_refs")
                        node["required"] = required_fields
                        source_refs["items"] = {
                            "type": "string",
                            "enum": responsibility_refs,
                        }
                        source_refs["uniqueItems"] = True
                        if responsibility_refs:
                            source_refs["minItems"] = 1
                        if "relationship" in node_properties:
                            # Association confidence is model evidence used by the
                            # fail-closed commit threshold. A DTO default of 0.0 is
                            # not evidence and must never silently discard an
                            # otherwise correct continuity decision.
                            required_fields = list(node.get("required") or [])
                            for field in ("target_goal_ids", "confidence"):
                                if field not in required_fields:
                                    required_fields.append(field)
                            node["required"] = required_fields
                    related_field = node_properties.get("related_goal_ids")
                    if isinstance(related_field, dict):
                        items = related_field.get("items")
                        if isinstance(items, dict):
                            if active_ids:
                                items["type"] = "string"
                                items["enum"] = active_ids
                            else:
                                related_field["maxItems"] = 0
                    target_ids = node_properties.get("target_goal_ids")
                    if isinstance(target_ids, dict):
                        target_ids["items"] = {
                            "type": "string",
                            "enum": active_ids,
                        }
                        target_ids["uniqueItems"] = True
                        if "relationship" in node_properties and active_ids:
                            # Every association addresses retained Goal state.
                            # An empty array can never satisfy the DTO, so expose
                            # that mechanical fact to the structured decoder.
                            target_ids["minItems"] = 1
                    target_referents = node_properties.get("target_referent_ids")
                    if isinstance(target_referents, dict):
                        target_referents["items"] = {
                            "type": "string",
                            "enum": referent_ids,
                        }
                        target_referents["uniqueItems"] = True
                    resolved_gaps = node_properties.get("resolved_gap_ids")
                    if isinstance(resolved_gaps, dict):
                        if gap_ids:
                            resolved_gaps["items"] = {
                                "type": "string",
                                "enum": gap_ids,
                            }
                            resolved_gaps["uniqueItems"] = True
                        else:
                            resolved_gaps["maxItems"] = 0
                    referent_id = node_properties.get("referent_id")
                    if isinstance(referent_id, dict):
                        referent_id["type"] = "string"
                        referent_id["enum"] = ["", *referent_ids]
                if node.get("type") == "object":
                    node["additionalProperties"] = False
                for value in node.values():
                    constrain(value)
            elif isinstance(node, list):
                for value in node:
                    constrain(value)

        constrain(schema)
        goal_schema = schema.get("$defs", {}).get("GoalAssociationModelGoal")
        if isinstance(goal_schema, dict) and responsibility_refs:
            # Every writable Goal-semantic surface must be explicit in the
            # constrained model output. Defaults on these fields are Python DTO
            # conveniences, not permission for the model to drop GI-grounded
            # bindings or silently avoid deciding the resource branch.
            goal_required = list(
                dict.fromkeys(
                    [
                        *(goal_schema.get("required") or []),
                        "source_responsibility_refs",
                        "description",
                        "output_mode",
                        "bindings",
                        "resource_responsibility",
                    ]
                )
            )
            goal_schema["required"] = goal_required
            source_refs_schema = goal_schema.get("properties", {}).get(
                "source_responsibility_refs"
            )
            if isinstance(source_refs_schema, dict):
                source_refs_schema["minItems"] = 1
                source_refs_schema["maxItems"] = 1
            goal_properties = goal_schema.get("properties")
            branch_goal_properties = (
                copy.deepcopy(goal_properties)
                if isinstance(goal_properties, dict)
                else {}
            )

            def branch_properties(
                source_ref: str,
                *,
                resource_variant: Literal[
                    "ordinary", "physical_object", "information", "unbounded"
                ],
            ) -> dict[str, Any]:
                """Return the complete, output-mode-compatible Goal surface.

                ``resource_responsibility`` is required so the decoder must make
                the resource decision explicitly, but Pydantic's default schema
                lists the object union before ``null``.  Ollama's constrained
                decoder consequently biased ordinary effects toward fabricated
                resources.  Keep semantic selection model-owned while removing
                impossible resource kinds and putting the ordinary ``null`` branch
                first.  ``body_action`` remains free to select a real physical
                acquisition, and ``capability_work`` remains free to select a real
                information responsibility.
                """

                properties = copy.deepcopy(branch_goal_properties)
                output_mode = responsibility_output_modes.get(source_ref)
                if resource_variant == "ordinary":
                    properties["resource_responsibility"] = {"type": "null"}
                    expected_bindings = [
                        (" ".join(str(name).strip().split()), str(value))
                        for name, value in responsibility_bindings.get(
                            source_ref, {}
                        ).items()
                        if " ".join(str(name).strip().split())
                        and "_".join(
                            str(name)
                            .strip()
                            .casefold()
                            .replace("-", "_")
                            .split()
                        )
                        not in {"action", "activity", "effect", "outcome"}
                    ]
                    if expected_bindings:
                        bindings_schema = copy.deepcopy(
                            properties.get("bindings") or {}
                        )
                        bindings_schema["minItems"] = len(expected_bindings)
                        bindings_schema["maxItems"] = len(expected_bindings)
                        binding_item_template = copy.deepcopy(
                            schema.get("$defs", {}).get(
                                "GoalAssociationModelBinding"
                            )
                            or {}
                        )
                        binding_branches: list[dict[str, Any]] = []
                        for name, value in expected_bindings:
                            binding_branch = copy.deepcopy(binding_item_template)
                            binding_properties = binding_branch.setdefault(
                                "properties", {}
                            )
                            binding_properties["name"] = {"const": name}
                            binding_properties["value"] = {"const": value}
                            binding_branch["required"] = list(
                                dict.fromkeys(
                                    [
                                        *(binding_branch.get("required") or []),
                                        "name",
                                        "value",
                                        "entity_type",
                                        "confidence",
                                    ]
                                )
                            )
                            binding_branches.append(binding_branch)
                        bindings_schema["items"] = {"oneOf": binding_branches}
                        bindings_schema["allOf"] = [
                            {
                                "contains": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"const": name},
                                        "value": {"const": value},
                                    },
                                    "required": ["name", "value"],
                                },
                                "minContains": 1,
                            }
                            for name, value in expected_bindings
                        ]
                        properties["bindings"] = bindings_schema
                elif resource_variant == "physical_object":
                    properties["resource_responsibility"] = {
                        "$ref": (
                            "#/$defs/"
                            "GoalAssociationModelPhysicalResourceResponsibility"
                        )
                    }
                    properties["bindings"] = {
                        **copy.deepcopy(properties.get("bindings") or {}),
                        "maxItems": 0,
                    }
                elif resource_variant == "information":
                    properties["resource_responsibility"] = {
                        "$ref": (
                            "#/$defs/"
                            "GoalAssociationModelInformationResourceResponsibility"
                        )
                    }
                    properties["bindings"] = {
                        **copy.deepcopy(properties.get("bindings") or {}),
                        "maxItems": 0,
                    }

                properties["source_responsibility_refs"] = {
                    "const": [source_ref]
                }
                if output_mode is not None:
                    properties["output_mode"] = {"const": output_mode}
                return properties

            def resource_variants(source_ref: str) -> list[str]:
                output_mode = responsibility_output_modes.get(source_ref)
                if source_ref in responsibility_fresh_evidence_refs:
                    # GI already authored the fresh-evidence semantic fact. At the
                    # trusted Goal boundary that fact has exactly one canonical
                    # representation: information resource work. Keeping the
                    # ordinary branch would silently downgrade evidence acquisition
                    # to conversational speech.
                    return ["information"]
                if output_mode == "body_action":
                    return ["ordinary", "physical_object"]
                if output_mode == "capability_work":
                    return ["ordinary", "information"]
                if output_mode is not None:
                    return ["ordinary"]
                return ["unbounded"]

            goal_schema["oneOf"] = []
            for source_ref in responsibility_refs:
                for resource_variant in resource_variants(source_ref):
                    goal_schema["oneOf"].append(
                        {
                            # Ollama's constrained decoder treats the selected
                            # oneOf object branch as the active production surface.
                            # Repeat the complete writable Goal surface here, not
                            # only the discriminants, so branch-local required
                            # fields can actually be generated. Resource-capable
                            # modes use complete cross-product branches so an
                            # ordinary Goal cannot also populate a resource object.
                            "properties": branch_properties(
                                source_ref,
                                resource_variant=resource_variant,
                            ),
                            # Some constrained decoders treat a nested oneOf branch
                            # as the active object production surface rather than
                            # combining its required list with the parent object.
                            "required": list(
                                dict.fromkeys(
                                    [
                                        *goal_required,
                                        "source_responsibility_refs",
                                        *(
                                            ["output_mode"]
                                            if source_ref
                                            in responsibility_output_modes
                                            else []
                                        ),
                                    ]
                                )
                            ),
                        }
                    )
        properties = schema.setdefault("properties", {})
        required = list(schema.get("required") or [])
        if output_type is GoalSegmentationModelOutput:
            properties["decision"] = {
                "type": "string",
                "enum": ["create_goals"],
            }
            ordered_required = [
                "decision",
                "new_goals",
                "referent_updates",
                "resolved_references",
                "confidence",
                "reason_summary",
            ]
        else:
            properties["decision"] = {
                "type": "string",
                "enum": ["associate", "create_goals"],
            }
            ordered_required = [
                "decision",
                "associations",
                "new_goals",
                "referent_updates",
                "resolved_references",
                "confidence",
                "reason_summary",
            ]
        if responsibility_refs:
            def contains_source_ref(source_ref: str) -> dict[str, Any]:
                return {
                    "contains": {
                        "type": "object",
                        "properties": {
                            "source_responsibility_refs": {
                                "type": "array",
                                "contains": {"const": source_ref},
                                "minContains": 1,
                                "maxContains": 1,
                            }
                        },
                        "required": ["source_responsibility_refs"],
                    },
                    "minContains": 1,
                    "maxContains": 1,
                }

            new_goal_conservation = {
                "minItems": len(responsibility_refs),
                "maxItems": len(responsibility_refs),
                "allOf": [
                    contains_source_ref(source_ref)
                    for source_ref in responsibility_refs
                ],
            }
            if output_type is GoalSegmentationModelOutput:
                # With no retained Goal candidate, every GI Responsibility must
                # become exactly one new Goal. Encode the already-enforced Host
                # invariant in the decoder so contract repair cannot emit r1,r1
                # for an r1,r2 turn. This is identity conservation, not semantic
                # reassociation.
                properties["new_goals"].update(new_goal_conservation)
            else:
                # Goal Association owns the branch choice. Once it chooses
                # create_goals, associations are inactive and every Responsibility
                # necessarily belongs to the new-goal branch. Conversely, an
                # association branch must conserve each supplied ref exactly once.
                schema.setdefault("allOf", []).append(
                    {
                        "if": {
                            "properties": {"decision": {"const": "create_goals"}},
                            "required": ["decision"],
                        },
                        "then": {
                            "properties": {
                                "associations": {"maxItems": 0},
                                "new_goals": new_goal_conservation,
                            }
                        },
                        "else": {
                            "properties": {
                                "new_goals": {"maxItems": 0},
                                "associations": {
                                    "minItems": 1,
                                    "allOf": [
                                        contains_source_ref(source_ref)
                                        for source_ref in responsibility_refs
                                    ],
                                },
                            }
                        },
                    }
                )

        schema["required"] = list(dict.fromkeys([*ordered_required, *required]))
        schema.pop("oneOf", None)
        schema.pop("anyOf", None)
        return GoalAssociationResolver._resource_semantic_contract_response_schema(
            GoalAssociationResolver._binding_semantic_contract_response_schema(
                schema
            )
        )

    @staticmethod
    def _binding_semantic_contract_response_schema(
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Expose the existing canonical binding invariant to constrained decoding."""

        schema = copy.deepcopy(response_schema)
        binding_schema = schema.get("$defs", {}).get(
            "GoalAssociationModelBinding"
        )
        if not isinstance(binding_schema, dict):
            return schema
        categories = {
            "distance": ["distance"],
            "direction": ["direction"],
            "quantity": [
                "amount",
                "count",
                "item_count",
                "quantity",
                "quantity_binding",
                "resource_count",
                "resource_quantity",
            ],
        }
        clauses = binding_schema.setdefault("allOf", [])
        for names in categories.values():
            clauses.append(
                {
                    "if": {
                        "properties": {"name": {"enum": names}},
                        "required": ["name"],
                    },
                    "then": {
                        "properties": {"entity_type": {"enum": names}},
                        "required": ["entity_type"],
                    },
                }
            )
        clauses.append(
            {
                "if": {
                    "properties": {"entity_type": {"const": "speed"}},
                    "required": ["entity_type"],
                },
                "then": {
                    "properties": {
                        "value": {
                            "anyOf": [
                                {"enum": ["slow", "normal", "quick"]},
                                {"pattern": r".*[0-9].*"},
                            ]
                        }
                    },
                    "required": ["value"],
                },
            }
        )
        return schema

    @staticmethod
    def _resource_semantic_contract_response_schema(
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Expose single-owner resource kinds and completion modes to decoding."""

        schema = copy.deepcopy(response_schema)
        definitions = schema.get("$defs", {})
        goal_schema = definitions.get("GoalAssociationModelGoal")
        if isinstance(goal_schema, dict):
            clauses = goal_schema.setdefault("allOf", [])
            for resource_kind, output_mode in (
                ("physical_object", "body_action"),
                ("information", "capability_work"),
            ):
                clauses.append(
                    {
                        "if": {
                            "properties": {
                                "resource_responsibility": {
                                    "type": "object",
                                    "properties": {"kind": {"enum": [resource_kind]}},
                                    "required": ["kind"],
                                }
                            },
                            "required": ["resource_responsibility"],
                        },
                        "then": {
                            "properties": {"output_mode": {"enum": [output_mode]}},
                            "required": ["output_mode"],
                        },
                    }
                )

        physical_source = definitions.get("GoalAssociationModelPhysicalSource")
        if isinstance(physical_source, dict):
            physical_source.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {"status": {"enum": ["known"]}},
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {"acquisition_bindings": {"minItems": 1}}
                    },
                }
            )

        information_source = definitions.get("GoalAssociationModelInformationSource")
        if isinstance(information_source, dict):
            information_source.setdefault("allOf", []).extend(
                [
                    {
                        "if": {
                            "properties": {"status": {"enum": ["known"]}},
                            "required": ["status"],
                        },
                        "then": {
                            "properties": {"source_name": {"minLength": 1}}
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "status": {"enum": ["unknown", "provider_resolved"]}
                            },
                            "required": ["status"],
                        },
                        "then": {
                            "properties": {"source_name": {"maxLength": 0}}
                        },
                    },
                ]
            )
        return schema

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

    def _discourse_referents(self, request: CognitiveWorkRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("discourse_referents")
        if not isinstance(raw, list):
            raw = []
        out: list[dict[str, Any]] = []
        for index, item in enumerate(raw[:24]):
            if not isinstance(item, dict):
                continue
            try:
                out.append(
                    DiscourseReferent.model_validate(item).model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                )
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed discourse referent index=%s error=%s",
                    index,
                    exc,
                )
                continue
        return out

    @staticmethod
    def _situation_projection(request: CognitiveWorkRequest) -> dict[str, Any]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("situation")
        if not isinstance(raw, dict):
            return {}
        try:
            return SituationProjection.model_validate(raw).prompt_projection()
        except ValidationError as exc:
            logger.debug("Ignoring malformed Situation projection error=%s", exc)
            return {}

    @staticmethod
    def _turn_id(request: CognitiveWorkRequest) -> str:
        seed = f"{request.sid or 'turn'}|{request.text}"
        return f"turn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        return bounded_json(value, max_chars)

    def _build_segmentation_prompt(
        self,
        request: CognitiveWorkRequest,
    ) -> str:
        """Render the complete no-candidate Goal contract without continuity prose.

        The former shared prompt repeated association, planning, resource, and
        coverage rules even when no Goal existed to associate.  Besides making the
        semantic boundary harder to review, that forced qualified small models into
        a much larger context allocation.  This prompt keeps the same authorities
        and failure semantics while stating each no-candidate rule once.
        """

        context = request.context if isinstance(request.context, dict) else {}
        identity_json = self._goal_segmentation_identity_json(context)
        identity_contract = (
            _GOAL_SEGMENTATION_IDENTITY_CONTRACT
            if identity_json != "null"
            else ""
        )
        responsibilities_json = self._bounded_json(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in request.responsibilities
            ],
            4200,
        )
        return (
            "There are no active or retained recent Goals. Association is impossible; "
            "create new Goals only. Goal Association receives provider-neutral "
            "Responsibility evidence, not a route, Capability, plan, or response draft. "
            "The authoritative user turn and the supplied GI Responsibilities are the "
            "only sources of owed human outcomes. Fast Planner Activity is HOW authored "
            "concurrently and must never become, justify, or be copied into a Goal. "
            "Responsibility conservation is strict: create exactly one Goal for each "
            "independently satisfiable Responsibility, copy its local_ref into "
            "source_responsibility_refs, and neither merge independent effects nor add "
            "acknowledgement, progress, delivery, personality, or implementation Goals. "
            "A manner, prohibition, timing, or social-presentation modifier stays on the "
            "outcome it constrains. A greeting attached to substantive work is framing; "
            "a standalone social act is one speech Goal. One lookup and the requested "
            "judgment of that same evidence are one Goal. Acquisition, carrying, return, "
            "and handoff are stages of one requested physical delivery, not sibling Goals.\n\n"
            "Copy a supplied Responsibility output_mode exactly; it is the only "
            "model-authored execution discriminator. Preserve every supplied material "
            "binding verbatim, including counts, durations, speeds, directions, targets, "
            "severity, thresholds, negation, comparison, and scope. For a non-resource "
            "Goal, put these in top-level typed bindings; the action itself may remain in "
            "description. Do not claim completion or choose a Capability. "
            f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
            "Use resource_responsibility only when obtaining and making a resource "
            "available to a recipient is the human outcome. A physical_object is a "
            "distinct concrete object independent of Chromie's body and requires "
            "acquisition plus physical_handover. Locomotion, gaze, blinking, gesture, "
            "turning, posture, and other self-motion are non-resource body_action Goals; "
            "never describe Chromie's body, position, displacement, or motion as an "
            "object to acquire or hand over. A physical resource keeps top-level bindings "
            "empty; its identity/quantity belong to description/quantity and its supplied "
            "location, distance, direction, and route belong separately in "
            "source.acquisition_bindings. Supplied spatial grounding requires "
            "source.status=known; source.status=unknown is allowed only when none was "
            "supplied.\n\n"
            "An information resource uses output_mode=capability_work and one exact "
            "information_domain: local_clock, weather_forecast, "
            "external_grounded_information, direct_environment_perception, or "
            "private_runtime_information. Its query_scope is the sole owner of location, "
            "time, aspects, comparisons, and thresholds: a resolved place is a "
            "query_scope binding named location, with time and requested result aspects "
            "as separate bindings. Current nearby people/objects/events require "
            "direct_environment_perception, not weather. A public source uses "
            "source.status=provider_resolved; source.status=unknown preserves an "
            "unavailable local/private/runtime source; source.status=known is only for an "
            "explicitly named source. Never invent location, timezone, source, provider, "
            "device, coordinates, or another query fact. Preserve source-grounded "
            "temporal wording as human semantic scope in query_scope. A compound natural "
            "expression stays intact instead of being decomposed into Capability date, period, "
            "or clock-range arguments. A duration remains duration. Never narrow broader "
            "temporal scope.\n\n"
            "Resolve a pronoun, demonstrative, ellipsis, correction, or task mention only "
            "from explicit current meaning, a supplied scoped discourse referent, a "
            "candidate binding, or accepted dialogue, in that order. There are no "
            "candidate Goals in this request. If evidence does not select one meaning, "
            "keep the narrowest source-grounded provisional Goal and do not invent the "
            "referent; Fast Planner owns any clarification. resolved_references may copy "
            "only a supplied referent_id. Ordinary explicit mentions are bindings, not "
            "resolved references. referent_updates require supplied provenance; never "
            "invent IDs. Tool results and runtime diagnostics are not semantic authority.\n\n"
            f"{identity_contract}"
            "The Host owns IDs, versions, lifecycle, source text, persistence, plans, and "
            "canonical construction. Emit none of those fields. Return only the exact "
            "GoalSegmentationModelOutput JSON Schema: decision=create_goals, new_goals, "
            "referent_updates, resolved_references, confidence, and compact reason_summary. "
            "Goal Association never executes, commits, asks a question, creates a planning "
            "InformationGap, or pretends work is complete.\n\n"
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
            + "Responsibility evidence JSON:\n"
            f"{responsibilities_json}\n\n"
            "GI unresolved-meaning evidence JSON:\n"
            f"{self._bounded_json(request.interpretation_unresolved, 1600)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 3000)}\n\n"
            "Recent accepted conversation JSON (reference evidence only):\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-6:], 2600)}\n\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
        )

    @staticmethod
    def _goal_segmentation_identity_json(context: dict[str, Any]) -> str:
        """Project identity facts Goal semantics can own, excluding voice style."""

        source = owner_approved_identity_context(context)
        identity = source.get("identity")
        if not isinstance(identity, dict):
            return "null"
        compact_identity = {
            key: identity[key]
            for key in (
                "entity_id",
                "name",
                "kind",
                "gender",
                "pronouns",
                "age_description",
                "family_role",
                "family_context_boundary",
            )
            if key in identity and identity[key] not in (None, "", [], {})
        }
        payload: dict[str, Any] = {
            "owner_approved": True,
            "identity": compact_identity,
        }
        self_model = source.get("self_model")
        if isinstance(self_model, dict):
            compact_self_model = {
                key: self_model[key]
                for key in (
                    "perceiving_entity_id",
                    "acting_entity_id",
                    "body_owner_entity_id",
                )
                if key in self_model and self_model[key] not in (None, "")
            }
            if compact_self_model:
                payload["self_model"] = compact_self_model
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _association_goal_projection(
        candidate_goals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep only semantic continuity evidence owned by Goal Association."""

        projected: list[dict[str, Any]] = []
        for snapshot in candidate_goals:
            if not isinstance(snapshot, dict):
                continue
            goal = snapshot.get("goal")
            goal = goal if isinstance(goal, dict) else {}
            metadata = goal.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            item = {
                "goal_id": snapshot.get("goal_id") or goal.get("goal_id"),
                "responsibility_status": (
                    snapshot.get("responsibility_status")
                    or goal.get("responsibility_status")
                ),
                "work_status": snapshot.get("work_status"),
                "description": goal.get("description"),
                "source_text": goal.get("source_text"),
                "bindings": (goal.get("object") or {}).get("bindings", {}),
                "output_mode": metadata.get("output_mode"),
                "completion_requires_work": metadata.get(
                    "completion_requires_work"
                ),
                "completion_requires_fresh_evidence": metadata.get(
                    "completion_requires_fresh_evidence"
                ),
                "open_information_gaps": snapshot.get(
                    "open_information_gaps", []
                ),
                "last_user_update": snapshot.get("last_user_update"),
            }
            projected.append(
                {
                    key: value
                    for key, value in item.items()
                    if value not in (None, "", [], {})
                }
            )
        return projected

    @staticmethod
    def _association_dialogue_projection(history: Any) -> list[dict[str, Any]]:
        """Remove runtime envelopes while retaining accepted dialogue meaning."""

        if not isinstance(history, list):
            return []
        projected: list[dict[str, Any]] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            text = " ".join(str(item.get("text") or "").strip().split())
            if role not in {"user", "assistant"} or not text:
                continue
            compact: dict[str, Any] = {"role": role, "text": text[:320]}
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                semantic_status = str(
                    metadata.get("semantic_status") or ""
                ).strip()
                if semantic_status:
                    compact["semantic_status"] = semantic_status
            projected.append(compact)
        return projected

    def _build_association_prompt(
        self,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
    ) -> str:
        """Render existing-Goal continuity without unrelated planning prose."""

        context = request.context if isinstance(request.context, dict) else {}
        identity_json = self._goal_segmentation_identity_json(context)
        identity_section = (
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
        )
        identity_contract = (
            _GOAL_SEGMENTATION_IDENTITY_CONTRACT
            if identity_json != "null"
            else ""
        )
        responsibilities = [
            item.model_dump(mode="json", exclude_none=True)
            for item in request.responsibilities
        ]
        history = context.get("history") or request.history or []
        return (
            "Resolve canonical Goal continuity from the authoritative user turn, GI "
            "Responsibilities, bounded candidate Goals, scoped referents, and accepted "
            "dialogue. This boundary owns Goal association/creation only: never choose "
            "a Capability, Plan, execution method, response wording, clarification "
            "policy, or completion claim. The Host owns IDs, versions, persistence, "
            "lifecycle mechanics, and canonical construction.\n\n"
            "Map every GI local_ref exactly once to either one association or one new "
            "Goal; never merge independent effects or add progress, acknowledgement, "
            "delivery, personality, or implementation Goals. Verify GI relationship "
            "and target_goal_ids against the supplied candidates rather than recency or "
            "lexical overlap. For unchanged unfinished/recoverable work use continue. "
            "Use resume only for paused work. Use reference for retrieval, restatement, "
            "explanation, comparison, or another answer from retained Goal meaning "
            "without lifecycle change. A new reaction, feeling, evaluation, practical "
            "decision, or independently satisfiable conversation is a new speech Goal. "
            "Use clarify only when this turn supplies missing Goal meaning; confirm and "
            "reject apply only to a pending proposal. Copy relationship exactly from "
            "continue, modify, clarify, confirm, reject, cancel, pause, resume, merge, "
            "split, or reference. Target only supplied Goal IDs.\n\n"
            "An association preserves the existing Goal's description, typed bindings, "
            "output_mode, and completion contract. It cannot rewrite a material entity "
            "or parameter. If current meaning changes one, create one complete replacement "
            "Goal and put the old ID in supersedes_goal_ids. If current meaning is "
            "independent, create a new Goal without reopening the old one. A recent "
            "terminal Goal may be referenced but not reopened. Preserve unresolved human "
            "meaning in the narrowest provisional Goal; Fast Planner alone decides any "
            "question.\n\n"
            "For a new Goal, copy the GI output_mode and every material binding exactly. "
            "Use resource_responsibility only when the owed outcome is to acquire and "
            "make a resource available. A physical_object is a concrete object independent "
            "of Chromie's body and uses physical_handover; locomotion, gaze, blinking, "
            "gesture, and posture are non-resource body_action. An information resource "
            "uses capability_work and keeps location, time, aspects, comparisons, and "
            "thresholds in query_scope. Never invent a source, location, provider, device, "
            "timezone, or execution fact. Directly named entities preserve the exact "
            "current-turn surface. resolved_references and referent_updates may copy only "
            "supplied referent IDs.\n\n"
            "Return only the exact GoalAssociationModelOutput JSON: decision, "
            "associations, new_goals, referent_updates, resolved_references, confidence, "
            "and compact reason_summary. Use decision=associate for continuity and "
            "decision=create_goals for independent or replacement work.\n\n"
            f"{identity_section}"
            f"{identity_contract}"
            f"{_EXECUTION_CONTRACT_PROMPT}\n\n"
            "Candidate Goal semantic evidence JSON:\n"
            f"{self._bounded_json(self._association_goal_projection(candidate_goals), 2600)}\n\n"
            "GI Responsibility evidence JSON:\n"
            f"{self._bounded_json(responsibilities, 2600)}\n\n"
            "GI unresolved-meaning evidence JSON:\n"
            f"{self._bounded_json(request.interpretation_unresolved, 800)}\n\n"
            "Goal interaction evidence JSON:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 900)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 1400)}\n\n"
            "Accepted dialogue JSON:\n"
            f"{self._bounded_json(self._association_dialogue_projection(history), 1400)}\n\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
            "FINAL CANDIDATE GOAL IDS JSON:\n"
            f"{self._bounded_json([item.get('goal_id') for item in candidate_goals], 900)}"
        )

    def _build_prompt(
        self,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        *,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        if output_type is GoalSegmentationModelOutput:
            return self._build_segmentation_prompt(request)
        return self._build_association_prompt(request, candidate_goals)

        # The remaining source below is retained temporarily while the compact
        # existing-Goal prompt is validated against the canonical behavior suite.
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        if output_type is GoalSegmentationModelOutput:
            state_instructions = (
                "There are no active or retained recent Goals, so no existing-goal relationship is possible and the contract intentionally has no associations field. "
                "Segment the authoritative user turn into independent new Goals. When GI preserves unresolved material meaning, create the narrowest source-grounded provisional Goal without inventing the missing referent or scope; Fast Planner owns any clarification decision. "
            )
            output_instructions = (
                "Return only JSON with decision, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
                "Use decision=create_goals and preserve each source-grounded Responsibility, including a provisional Goal whose exact referent or scope remains unresolved. Do not author a question or decide input-resolution policy. "
                "The decoder enforces the exact GoalSegmentationModelOutput JSON Schema. "
            )
        else:
            state_instructions = (
                "Resolve continuity before creation using semantic reasoning. "
                "For continuity with an existing goal, emit an associations item with source_responsibility_refs, relationship, target_goal_ids, confidence, reason_summary, the applicable updated_description, and resolved_gap_ids fields. Goal Association owns canonical Goal continuity only: do not decide whether Work must be reused, replaced, cancelled, or replanned; Fast Planner owns that judgment from the committed Goal and actual Work state. "
                "relationship must be copied exactly from [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"merge\",\"split\",\"reference\"]. "
                "Use continue only when the current turn advances unchanged unfinished active or recoverable work. Use reference when the current turn asks to retrieve, restate, explain, compare, verify, or otherwise answer from a retained Goal without changing its meaning or lifecycle. Do not use continue or reference merely because the topic overlaps with a previous Goal. When the latest turn is a social reaction, acknowledgement, personal feeling, practical decision, conversational evaluation, empathy-seeking comment, or another independently satisfiable communicative act, create a fresh vocal_output Goal that captures that latest intent; prior delivered information remains context for that answer. Use modify only when the same Responsibility is being refined and include updated_description or resolved_gap_ids. When the user abandons that Responsibility for a genuinely different outcome, return decision=create_goals with a new Goal whose supersedes_goal_ids names the old Goal; never mutate the old Goal through an association. The association relationship clarify means the current user turn supplies missing information for a Goal and must include updated_description or resolved_gap_ids; it never means that the user is asking Chromie for more explanation. When GI preserves unresolved material meaning, create or associate the narrowest source-grounded provisional Goal without inventing that meaning; Fast Planner alone decides whether and how to ask. "
                "Use confirm only when the current turn approves a pending proposal for the targeted Goal, and use reject only when it declines that proposal. "
                "Associations may target only IDs from the bounded candidate-goal list. A recent terminal Goal may be referenced without reopening or changing its terminal lifecycle state. "
                "An association cannot rewrite an existing Goal's typed material bindings. When your semantic judgment is that the current user meaning changes a material entity or parameter, preserve the old Goal and return decision=create_goals with a complete replacement Goal and authoritative bindings. "
            )
            output_instructions = (
                "Return only JSON with decision, associations, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
                "Use decision=associate for continuity or decision=create_goals for independent work, including provisional source-grounded Goals with unresolved meaning retained outside this DTO for Planner. New Goals may copy related_goal_ids from the bounded active Goal list when that relationship helps later reasoning; this contextual relationship does not itself reopen or add the retained Goal to the current responsibility. "
                "The decoder enforces the exact GoalAssociationModelOutput JSON Schema. "
            )
        return (
            state_instructions
            + "Goal Association receives provider-neutral Responsibility evidence, not a route or intent classification. "
            "Each Responsibility also carries GI's context-grounded Goal relationship and target_goal_ids. Verify those proposals against the complete candidate Goal list and authoritative turn; preserve a correct answer to a pending Planner clarification as a Goal update instead of interpreting its short surface as a new Goal. Goal Association remains the sole canonical commit authority and may resolve a supplied pending gap only through its canonical association update. "
            "No compatibility label may force a clarification branch or attach the turn to an existing Goal. "
            "Create or associate a Goal for every source-grounded human Responsibility even when GI reports bounded unresolved meaning or Fast Planner later finds a missing execution input. That provisional Goal persists while Fast Planner asks the user. Goal Association never selects or words a clarification Activity and never creates a planning InformationGap. "
            + "The model-facing contract is deliberately small. "
            "The host owns all IDs, versions, source text, constraints, metadata, persistence fields, and canonical object construction. "
            "Never emit id, goal_id, association_id, turn_id, schema_version, source_text, constraints, object, metadata, success_criteria, capabilities, or plans. Referent IDs may only be copied from the supplied discourse context; new referent IDs are Host-generated.\n\n"
            "Create one new goal for each independently satisfiable user responsibility. Copy every owning GI local_ref into that Goal's source_responsibility_refs; every GI Responsibility ref must map to exactly one association or new Goal. The authoritative user turn plus Responsibility evidence are the only sources of human Responsibility here; Fast Planner Activity is HOW authored concurrently and must never become, justify, or be copied into a sibling Goal. Responsibility conservation is strict: never create an extra Goal for acknowledgement, progress, response delivery, personality, or any other outcome that is absent from the authoritative Responsibility evidence. Emit exactly one new_goals item containing source_responsibility_refs, description, typed bindings, and an optional provider-neutral resource_responsibility for each responsibility. "
            "Every new Goal must declare one exact output_mode that describes the semantic work completing the human outcome. output_mode is the only model-authored execution discriminator. Responsibility kind, execution lane, and provider requirement are Host-derived projections and are not fields in the model schema. Media playback may also declare its exact media_operation; non-media Goals may omit media_operation and the Host supplies none. "
            "When Responsibility evidence includes output_mode, copy that exact value "
            "to its one Goal. Goal Interpretation owns this provider-neutral completion "
            "modality; Goal Association must not reinterpret, weaken, or relabel it. "
            "Use output_mode=speech for an ordinary authored conversational response, including a greeting, empathy, reassurance, restatement, explanation from supplied context, or acknowledgement of a person's feeling. The need to think or formulate words never makes ordinary conversation capability_work. A person's report of their own state never becomes body_action or capability_work unless the authoritative Responsibility separately asks Chromie to change the world. Preserve speaker, experiencer, actor, and addressee ownership exactly. "
            f"{_EXECUTION_CONTRACT_PROMPT} "
            "The eventual spoken delivery of a capability result is part of that same capability_dependent Goal, never an additional vocal_output Goal. Persona, tone, wording, and answer delivery are not independent Goals. "
            "A requested manner, mood, persona, or social presentation attached to a substantive action or other effect is a constraint on how that effect should be expressed, not a second Goal. Keep it in the substantive Goal description. It becomes a separate vocal Goal only when the user independently asks to hear positive authored content or a vocal performance that remains satisfiable without the substantive effect. "
            "A standalone social interaction such as a greeting, thanks, reassurance request, casual check-in, reaction, personal feeling, evaluation, or practical decision is itself one satisfiable conversational Goal: respond naturally to that current social act. This remains true when the act is grounded in information delivered by a previous Goal. Prior evidence may support the answer, but it does not replace the latest communicative responsibility. Do not treat it as an empty turn or fold it into an already completed task merely because the topic is related. "
            "A new question about what Chromie previously said is a fresh speech Goal whose owed outcome is for Chromie to repeat or summarize the most recent accepted assistant/Chromie dialogue utterance. It references that utterance as content but does not continue, resume, or modify the old Goal merely because the old response supplies the answer. Never reverse this into asking the user to repeat, and never substitute the user's earlier utterance or current question for Chromie's delivered words. "
            "A greeting or politeness preamble attached to a substantive request is conversational framing, not a separate Goal unless the user independently asks for a social response. Owner-approved identity and personality shape expression only; never create a Goal merely to mention age, identity, warmth, curiosity, or another style trait. "
            "Information acquisition and a requested interpretation of that same evidence are one Goal when one result can satisfy both. Multiple requested aspects derived from one information result remain one information responsibility when the same result satisfies them. Do not split evidence acquisition, requested result aspects, or interpretation of that result into separate Goals. "
            "A physical action and a conversational answer or spoken performance are independent goals when the answer or performance is genuinely requested. Separate independently requested outcomes that can be accepted or rejected on their own. However, acquisition and delivery stages that together constitute one human responsibility are one Goal: navigating/searching, locating, grasping or retrieving, carrying, returning, and handing over are provider-owned stages of one physical resource delivery; external search, evidence retrieval, evaluation, and spoken explanation are stages of one information resource delivery. Do not split those implementation stages into separate Goals unless the user independently requests one stage as its own outcome. A simple acknowledgement, confirmation, willingness statement, or progress prelude for capability work is not a separate vocal_output Goal; it is prospective conversational output attached to the existing responsibility and every cognitive stage must use Interaction Context to avoid repeating an already fulfilled act. Before returning, verify that every independently satisfiable user responsibility appears in exactly one new_goals item: no merged unrelated outcomes and no duplicated responsibility across Goals. "
            "For a responsibility whose human-level outcome is to obtain something and make it available to a recipient, include exactly one nested resource_responsibility. It is the sole writable resource authority and is discriminated by top-level kind. A physical_object resource means a distinct concrete object that exists independently of Chromie's body motion and whose acquisition plus handover completes the human outcome. It is never a generic wrapper for embodied work: locomotion, body motion, gaze, blinking, waving, turning, posture, and gestures are non-resource body_action Goals, keep resource_responsibility absent, and preserve their material semantic parameters in top-level bindings. For kind=information, use output_mode=capability_work, classify the provider-neutral information_domain from the evidence actually needed (local_clock, weather_forecast, external_grounded_information, direct_environment_perception, or private_runtime_information), and write every requested query fact—location, time, requested aspect, comparison, threshold, or other answer-shaping scope—exactly once in query_scope. Current nearby person/object/event presence is direct_environment_perception, never weather merely because both concern outside. Its source object is intentionally narrow: source.status=provider_resolved delegates public/external source selection; source.status=unknown preserves an unavailable local/private/runtime source; source.status=known is only for a user- or discourse-named information source and then source_name is required. Never copy query_scope facts into source. For kind=physical_object, use output_mode=body_action and delivery_mode=physical_handover; identity and quantity live at resource_responsibility.description/quantity, while source.acquisition_bindings is the only writable location/distance/direction/route surface. When the user or a resolved discourse referent supplies any spatial acquisition fact, source.status must be known and acquisition_bindings must preserve every supplied distance, direction, location, or route separately. source.status=unknown is valid only when no acquisition grounding was supplied. Preserve explicit distance and direction separately; source.description is summary only and any numeric fact in it must also exist in acquisition_bindings. Resource Goals keep top-level bindings empty. No flat compatibility copy is created. resource_responsibility must never name or imply a Capability, provider implementation, website, search engine, coordinates, grasp pose, execution mode, or plan. Human-readable descriptions never override typed fields. "
            "Also preserve semantic qualifiers such as temporal scope, comparison period, and requested answer shape. Keep source-grounded temporal wording as human semantic scope rather than translating it into provider date/day-part parameters. One compound source expression may remain one temporal_scope binding; separately stated independent scopes remain separate semantic constraints. Never silently narrow broader, historical, comparative, or otherwise scoped meaning. If the intended scope is materially ambiguous, preserve it in a provisional Goal without choosing a narrower interpretation. "
            "Resolve references, pronouns, demonstratives, ellipsis, and task mentions before planning. Authority order is: explicit current user meaning; foreground scoped discourse referents; candidate Goal bindings; recent dialogue. First identify every material indirect referring expression, then require a unique value from that authority order before writing a resolved binding or supplied referent. Imperative grammar and a plausible generic noun such as device, object, person, task, or setting are never reference evidence. If two or more contextual candidates remain plausible, or none is supplied, preserve the unresolved reference in the provisional Goal description without selecting a candidate; Fast Planner owns the narrow clarification decision. Phrases such as ‘the last task I told you’ may semantically associate with an active, recoverable, or retained recent terminal Goal, but the model must decide that relationship from the supplied Goal state and dialogue—not from a Host phrase table. Tool-result memory is not reference-resolution authority and must never decide what an unresolved expression refers to. "
            "When the user introduces or explicitly corrects a salient entity, emit referent_updates only when the required discourse-index provenance is available. Use operation=correct with non-empty target_referent_ids copied from supplied discourse context when a new value supersedes an earlier referent; never emit an unscoped correction when no target referent ID was supplied. The canonical Goal association and typed bindings still preserve a correction even when no discourse-index update can be authored. The old referent remains available in its own task scope but becomes background. Use operation=introduce for a new salient entity, and focus/background/retire only for supplied referent IDs. "
            "Use resolved_references only for indirect references whose denotation is uniquely selected from a supplied discourse referent or active Goal binding, such as pronouns, demonstratives, ellipsis, aliases, corrections, or task mentions. Do not emit resolved_references for an ordinary explicit entity mention such as a directly named place; represent that meaning in the new Goal bindings and, when it is salient for future dialogue, in referent_updates. Every resolved_references item must copy a supplied referent_id and include explicit confidence. If resolution is materially ambiguous, omit the invented binding/reference and preserve a provisional Goal instead. "
            "Each non-resource Goal must include top-level typed bindings for material entities and parameters already resolved here, including explicit counts, durations, speeds, directions, and targets. For a qualitative speed, use the provider-neutral canonical value slow, normal, or quick; retain more specific severity or intensity as a separate binding rather than hiding it in an inflected speed phrase. Preserve an explicit quantitative speed with its value and units. The action/effect itself belongs in the Goal description; it does not need a duplicate action binding when that exact source value is already retained there. A resource Goal keeps top-level bindings empty and owns every material resource fact only in resource_responsibility. For information, query_scope is the one query-fact surface. Preserve each resolved answer-shaping fact there exactly once as its own typed binding, including spatial, temporal, comparison, threshold, or requested-result scope when supplied. For physical acquisition, use the canonical name and entity_type distance/distance for distance and direction/direction for direction. A relative spatial place may use location/relative_location; generic labels such as measurement or string are not canonical substitutes for a known typed fact. Preserve every explicit severity, intensity, magnitude, threshold, subtype, negation, or comparison qualifier that changes satisfactory completion. Never generalize a narrower request. Downstream planners read the canonical resource directly; no persisted flat projection exists. "
            "For a location named directly in the final authoritative user turn, copy the complete location value verbatim as one contiguous span in the user's language. Never translate, transliterate, shorten, or expand a directly named location. A directly supplied location is a resolved semantic binding, not a claim that provider canonicalization has already succeeded. Do not ask the user for administrative granularity merely because multiple real-world places might share that value; create the fully bound Goal and let the downstream Capability resolve the exact value or report provider ambiguity. When the user's intended location is genuinely underdetermined in the dialogue, preserve that unresolved scope in the provisional Goal and leave clarification selection to Fast Planner. Only an indirect reference resolved from a supplied referent may use the referent's canonical value instead. For an indirect location, copy the supplied referent_id into both the location binding and resolved_references, and copy the indirect user surface into resolved_references.surface_form. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Do not split implementation steps into goals. Do not create goals for implementation mechanics, safety checks, status lookups, capability calls, or other internal work.\n\n"
            "Goal Association must not author a clarification question, input-source policy, or planning InformationGap. Put only compact Goal-state rationale in reason_summary.\n\n"
            + output_instructions
            + "Each new_goals object contains description, output_mode, optional media_operation, bindings, optional resource_responsibility, related_goal_ids only when retained Goals remain relevant context, and supersedes_goal_ids only when the old Responsibility is genuinely abandoned and replaced by this new independently owed outcome. bindings is an array of typed semantic parameters with name, entity_type, value, optional copied referent_id, and confidence. Use [] when no material binding exists. resource_responsibility is provider-neutral and must follow the contract above. A vocal Goal must never carry resource_responsibility merely because rendering needs a provider. Every referent_updates item and every resolved_references item must include explicit confidence; never rely on an omitted-field default.\n\n"
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{personality_json}\n\n"
            + "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 6500)}\n\n"
            "Responsibility evidence JSON (Core-authored provider-neutral semantic handoff from Goal Interpretation. These are not canonical Goals. Preserve the WHAT and material bindings; use the authoritative user turn, discourse, retained Goal state, and Situation only to associate continuity or identify a real representation mismatch, never to silently rewrite the Responsibility. Goal Association alone decides create/continue/modify/supersede canonical Goal state. Never infer a Capability, provider, execution method, executable argument, or response wording here):\n"
            f"{self._bounded_json([item.model_dump(mode='json', exclude_none=True) for item in request.responsibilities], 4200)}\n\n"
            "Bounded active task/progress snapshots JSON:\n"
            f"{self._bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON (append-only facts about what Chromie already associated, planned, said, committed, completed, or failed; owner and event_type preserve evidence strength). Use it to identify the still-needed Goal/continuity delta. Generated or scheduled speech is not heard speech, and planned or committed work is not completed work. Do not reopen, repeat, or recreate an already fulfilled responsibility unless the current turn explicitly repeats it or new failure, correction, changed state, evidence, or clarification requires a new delta:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON (most recent/foreground last):\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Recent conversation is accepted dialogue evidence for ellipsis, pronouns, corrections, and other follow-up meaning. Bounded Goal and Task state is stronger evidence of already-validated semantic continuity when it exists. A newer accepted turn whose metadata says semantic_status=failed or terminal_without_canonical_goal remains valid recent conversational evidence even though it has no canonical Goal; do not skip it solely because an older Goal is canonical. If an earlier admitted turn has not yet produced canonical Goal state, dialogue may still resolve the current reference, but never invent a Goal ID or pretend uncommitted work is canonical.\n\n"
            "Tool-result contents are intentionally absent at this boundary. Resolve references and Goal bindings from user semantics, scoped referents, candidate Goals, and dialogue only. A later Planner may explicitly retrieve an exact verified memory record after bindings are fixed. "
            "For an open safe-read Goal whose bound Work is scheduled, running, or recoverable, associate a semantic follow-up with that exact Goal when appropriate; do not answer from another task's result. "
            "Do not reason from prior routing labels, planner states, validation failures, fallback states, or other runtime diagnostics; they are not user-semantic evidence.\n\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
            f"FINAL CANDIDATE GOAL IDS JSON:\n{self._bounded_json([item.get('goal_id') for item in candidate_goals], 1600)}"
        )

    def _build_repair_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        validation_error: str,
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        if output_type is GoalSegmentationModelOutput:
            contract_name = "Goal Segmentation"
            revision_action = "Re-evaluate the independent goal segmentation"
            state_instructions = (
                "There are no active or retained recent Goals. Existing-goal associations are structurally invalid and must not appear. "
                "Re-segment every independently satisfiable responsibility into new_goals. Preserve unresolved human-level meaning in the narrowest provisional Goal without inventing it; Fast Planner owns any question. "
                "A standalone social interaction is one conversational Goal and must not be returned as an empty goal list. A greeting attached to substantive work is framing, not a second Goal. Identity and personality shape wording only and never create a Goal. A lookup plus an interpretation derived from the same result is one Goal. "
            )
            output_instructions = (
                "The exact GoalSegmentationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only decision, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
            )
        else:
            contract_name = "Goal Association"
            revision_action = "Re-evaluate the semantic associations"
            state_instructions = (
                "Re-evaluate continuity against only the supplied bounded candidate Goal IDs. "
                "The final authoritative user turn owns the current communicative responsibility. A completed task may supply context, but a reaction, feeling, evaluation, acknowledgement, or practical decision about that context is normally a fresh vocal_output Goal rather than continuation or reference. Existing Goal bindings are provenance-stable and cannot be changed by an association. If current user meaning changes a material binding, use decision=create_goals with one fully bound replacement Goal rather than a description-only association. "
            )
            output_instructions = (
                "The exact GoalAssociationModelOutput JSON Schema is enforced by the Ollama decoder out-of-band. "
                "Return only decision, associations, new_goals, referent_updates, resolved_references, confidence, and reason_summary. "
            )
        return (
            f"The previous minimal {contract_name} semantic DTO failed its exact contract. {revision_action} and "
            "return one corrected JSON object. Preserve valid semantic judgments, but revise every field needed to satisfy "
            "the schema and validation errors. Do not explain the correction and do not use synonym substitution rules.\n\n"
            + state_instructions
            + "Responsibility conservation remains authoritative during repair. Never add a Goal whose human outcome is absent from the supplied Responsibility evidence. In particular, a Fast-Planner progress acknowledgement or later response delivery is HOW around the existing Responsibility, not a sibling speech Goal. A physical_object resource is only a distinct concrete object whose acquisition and handover completes the responsibility; ordinary locomotion, body movement, gaze, blinking, waving, turning, posture, and gestures use output_mode=body_action with top-level semantic bindings and no resource_responsibility.\n\n"
            + f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            + "\n\nResolved references are only for indirect references bound to a supplied discourse referent or active Goal binding. Direct explicit entity mentions belong in Goal bindings and salient referent updates, not resolved_references. For an indirect location binding, copy the supplied referent_id into both the location binding and resolved_references, copy the indirect user surface into resolved_references.surface_form, and retain the referent canonical value. Every resolved reference and referent update must include explicit confidence.\n\nOwner-approved Chromie identity JSON:\n"
            + identity_json
            + "\n\nOwner-approved Personality Expression JSON:\n"
            + personality_json
            + "\n\n"
            + f"Latest user turn:\n{request.text}\n\n"
            "For a location named directly in that user turn, copy the complete location binding value verbatim as one contiguous span. Never translate, transliterate, shorten, or expand it. Responsibility evidence may contain a normalized or incorrectly translated spelling; the FINAL AUTHORITATIVE USER TURN owns the direct entity surface and must win. Do not ask the user for provider canonicalization or extra administrative granularity merely because multiple real-world places might share the supplied value; bind it exactly and let the downstream Capability resolve it or report provider ambiguity. Only an indirect reference resolved from a supplied referent may use the referent's canonical value.\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(candidate_goals, 7000)}\n\n"
            "Bounded live Situation projection JSON (soft/revisable relevance only):\n"
            f"{self._bounded_json(self._situation_projection(request), 3600)}\n\n"
            "Bounded active task/progress snapshots JSON:\n"
            f"{self._bounded_json(context.get('active_task_snapshots') or [], 5200)}\n\n"
            f"{goal_progress_communication_prompt('Goal Association')}\n\n"
            "Goal-scoped Interaction Context JSON:\n"
            f"{self._bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Scoped discourse referents JSON:\n"
            f"{self._bounded_json(self._discourse_referents(request), 6500)}\n\n"
            "Discourse focus stack JSON:\n"
            f"{self._bounded_json(context.get('discourse_focus') or [], 1800)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-8:], 3600)}\n\n"
            "Use recent conversation as accepted dialogue evidence for follow-up meaning, while bounded Goal and Task state remains the authority for already-validated semantic work. A newer failed or terminal-without-canonical-Goal dialogue turn remains relevant context and must not be skipped solely because an older Goal has canonical state. Never invent a Goal ID merely because dialogue implies an earlier turn is still being processed.\n\n"
            "Previous model output JSON:\n"
            f"{self._bounded_json(raw, 5000)}\n\n"
            "Exact validation errors JSON:\n"
            f"{validation_error}\n\n"
            + output_instructions
            + "Select exactly one Goal-state decision branch. Do not author clarification wording or planning gaps. Each new_goals item contains description, output_mode, optional media_operation, bindings, optional supersedes_goal_ids, and optional provider-neutral resource_responsibility only. Choose output_mode from the work that actually completes the Goal; the Host derives the internal responsibility class, lane, and provider-evidence requirement. media_playback requires one exact media_operation; non-media Goals may omit it. "
            + _EXECUTION_CONTRACT_PROMPT
            + " Preserve one nested resource_responsibility when the responsibility is genuinely to acquire and deliver a physical object or grounded information; never add it to a vocal performance or insert provider details. It is the sole writable resource authority. Use kind=information with output_mode=capability_work, an exact provider-neutral information_domain, query_scope for all requested information facts, and a narrow source object that can only delegate, remain unknown, or name one explicit information source. Classify present nearby people, objects, or events as direct_environment_perception, not weather_forecast. Use kind=physical_object with output_mode=body_action, delivery_mode=physical_handover, and source.acquisition_bindings as the sole spatial/acquisition fact surface. Never duplicate one fact across fields and never create top-level Goal bindings for a resource Goal. In physical acquisition bindings, distance uses name=distance and entity_type=distance, direction uses name=direction and entity_type=direction, and a relative place may use name=location and entity_type=relative_location. Generic measurement or string types do not replace these canonical types. Preserve human temporal scope in source-grounded semantic form, preferably entity_type=temporal_scope for a compound natural expression; do not derive Capability date/period enums or clock windows. Never repair missing human-level scope by inventing a default: preserve unresolved scope in a provisional Goal and leave the exact missing value unset. Preserve or repair explicit discourse resolution and referent updates; never use tool-result contents to infer a reference. "
            "The host owns every ID and persistence field. Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
        )

    def _layered_prompt(
        self,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        *,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = self._goal_segmentation_identity_json(context)
        identity_world = (
            "Owner-approved Chromie identity JSON:\n"
            f"{identity_json}\n\n"
        )
        identity_contracts = (
            (_GOAL_SEGMENTATION_IDENTITY_CONTRACT,)
            if identity_json != "null"
            else ()
        )
        rendered = self._build_prompt(
            request,
            candidate_goals,
            output_type=output_type,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                *identity_contracts,
                _EXECUTION_CONTRACT_PROMPT,
            ),
        )

    def _layered_repair_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        turn_id: str,
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        raw: dict[str, Any],
        validation_error: str,
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        identity_world = self._stable_identity_world_layer(context)
        rendered = self._build_repair_prompt(
            request=request,
            candidate_goals=candidate_goals,
            turn_id=turn_id,
            output_type=output_type,
            raw=raw,
            validation_error=validation_error,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
                _EXECUTION_CONTRACT_PROMPT,
            ),
        )

    @staticmethod
    def _stable_identity_world_layer(context: dict[str, Any]) -> str:
        return (
            "Owner-approved Chromie identity JSON:\n"
            f"{bounded_identity_json(context)}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{bounded_personality_json(context)}\n\n"
        )


    @staticmethod
    def _responsibility_coverage_required(
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
    ) -> bool:
        """Audit every newly proposed Goal set and no association-only branch.

        This is a structural transition, not a Host semantic risk heuristic.
        Association-only results have no candidate new-Goal set for this certificate
        to prove.
        """

        del request
        return bool(model_output.new_goals)


    @staticmethod
    def _coverage_certificate_response_schema(
        candidate_goals: list[GoalAssociationModelGoal],
        *,
        authoritative_turn: str = "",
    ) -> dict[str, Any]:
        goal_count = len(candidate_goals)
        schema = copy.deepcopy(
            GoalResponsibilityCoverageCertificate.model_json_schema()
        )
        item_schema = schema.get("$defs", {}).get(
            "GoalResponsibilityCoverageItem"
        )
        if isinstance(item_schema, dict):
            item_schema["required"] = [
                "source_excerpt",
                "role",
                "coverage",
                "independently_satisfiable",
                "candidate_goal_indices",
                "required_goal_shape",
                "required_information_domain",
                "required_output_mode",
            ]
            indices = item_schema.get("properties", {}).get(
                "candidate_goal_indices"
            )
            surface = " ".join(str(authoritative_turn or "").strip().split())
            if surface and len(surface) <= 40:
                exact_surfaces = sorted(
                    {
                        surface[start:end]
                        for start in range(len(surface))
                        for end in range(start + 1, len(surface) + 1)
                    },
                    key=lambda value: (len(value), value),
                )
                source_excerpt = item_schema.get("properties", {}).get(
                    "source_excerpt"
                )
                if isinstance(source_excerpt, dict):
                    source_excerpt["enum"] = exact_surfaces
                    source_excerpt["description"] = (
                        "Copy one exact non-empty contiguous source slice; the decoder "
                        "cannot translate, inflect, combine, or rewrite particles."
                    )
            if isinstance(indices, dict):
                indices["uniqueItems"] = True
                index_items = indices.get("items")
                if isinstance(index_items, dict):
                    index_items["type"] = "integer"
                    index_items["enum"] = list(range(max(0, goal_count)))
            item_schema.setdefault("allOf", []).extend(
                [
                    {
                        "if": {
                            "properties": {
                                "role": {"enum": ["context", "framing"]}
                            },
                            "required": ["role"],
                        },
                        "then": {
                            "properties": {
                                "coverage": {
                                    "enum": ["covered", "clarification_required"]
                                },
                                "independently_satisfiable": {"enum": [False]},
                                "candidate_goal_indices": {"maxItems": 0},
                                "required_goal_shape": {"const": "ordinary"},
                                "required_information_domain": {"const": "none"},
                                "required_output_mode": {"const": "none"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {"enum": ["constraint"]}
                            },
                            "required": ["role"],
                        },
                        "then": {
                            "properties": {
                                "independently_satisfiable": {"enum": [False]},
                                "required_goal_shape": {"const": "ordinary"},
                                "required_information_domain": {"const": "none"},
                                "required_output_mode": {"const": "none"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {"enum": ["responsibility"]},
                                "required_goal_shape": {
                                    "enum": ["information_resource"]
                                },
                            },
                            "required": ["role", "required_goal_shape"],
                        },
                        "then": {
                            "properties": {
                                "required_information_domain": {
                                    "enum": [
                                        "local_clock",
                                        "weather_forecast",
                                        "external_grounded_information",
                                        "direct_environment_perception",
                                        "private_runtime_information",
                                    ]
                                },
                                "required_output_mode": {"const": "capability_work"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "required_goal_shape": {
                                    "enum": [
                                        "ordinary",
                                        "physical_resource",
                                        "persistent_effect",
                                    ]
                                }
                            },
                            "required": ["required_goal_shape"],
                        },
                        "then": {
                            "properties": {
                                "required_information_domain": {"const": "none"}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "required_goal_shape": {
                                    "enum": ["physical_resource"]
                                }
                            },
                            "required": ["required_goal_shape"],
                        },
                        "then": {
                            "properties": {
                                "required_output_mode": {"const": "body_action"}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "required_goal_shape": {
                                    "enum": ["persistent_effect"]
                                }
                            },
                            "required": ["required_goal_shape"],
                        },
                        "then": {
                            "properties": {
                                "required_output_mode": {"const": "capability_work"}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {
                                    "enum": ["responsibility", "constraint"]
                                },
                                "coverage": {
                                    "enum": ["covered", "clarification_required"]
                                },
                            },
                            "required": ["role", "coverage"],
                        },
                        "then": {
                            "properties": {
                                "candidate_goal_indices": {"minItems": 1}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {"enum": ["responsibility"]},
                                "coverage": {"enum": ["covered"]},
                            },
                            "required": ["role", "coverage"],
                        },
                        "then": {
                            "properties": {
                                "candidate_goal_indices": {
                                    "minItems": 1,
                                    "maxItems": 1,
                                }
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "coverage": {"enum": ["representation_mismatch"]}
                            },
                            "required": ["coverage"],
                        },
                        "then": {
                            "properties": {
                                "candidate_goal_indices": {"minItems": 1}
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "role": {"enum": ["responsibility"]},
                                "coverage": {"enum": ["representation_mismatch"]},
                            },
                            "required": ["role", "coverage"],
                        },
                        "then": {
                            "properties": {
                                "candidate_goal_indices": {
                                    "minItems": 1,
                                    "maxItems": 1,
                                }
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {
                                "coverage": {
                                    "enum": ["missing"]
                                }
                            },
                            "required": ["coverage"],
                        },
                        "then": {
                            "properties": {
                                "candidate_goal_indices": {"maxItems": 0}
                            }
                        },
                    },
                ]
            )
            properties = schema.get("properties", {})
            responsibility_items = properties.get("responsibility_items")
            supporting_items = properties.get("supporting_items")
            if isinstance(responsibility_items, dict):
                responsibility_item = copy.deepcopy(item_schema)
                responsibility_item_properties = responsibility_item["properties"]
                responsibility_required = list(responsibility_item["required"])

                def candidate_shape(
                    candidate: GoalAssociationModelGoal,
                ) -> tuple[str, str, str]:
                    resource = candidate.resource_responsibility
                    if resource is not None and resource.kind == "information":
                        return (
                            "information_resource",
                            resource.information_domain,
                            candidate.output_mode,
                        )
                    if resource is not None and resource.kind == "physical_object":
                        return ("physical_resource", "none", candidate.output_mode)
                    if candidate.output_mode == "capability_work":
                        return ("persistent_effect", "none", candidate.output_mode)
                    return ("ordinary", "none", candidate.output_mode)

                def responsibility_branch(
                    *,
                    coverage: str,
                    candidate_index: int | None,
                    constrain_to_candidate: bool,
                ) -> dict[str, Any]:
                    branch_properties = copy.deepcopy(
                        responsibility_item_properties
                    )
                    branch_properties["role"] = {"const": "responsibility"}
                    branch_properties["coverage"] = {"const": coverage}
                    branch_properties["candidate_goal_indices"] = {
                        "const": (
                            []
                            if candidate_index is None
                            else [candidate_index]
                        )
                    }
                    if constrain_to_candidate and candidate_index is not None:
                        shape, information_domain, output_mode = candidate_shape(
                            candidate_goals[candidate_index]
                        )
                        branch_properties["required_goal_shape"] = {
                            "const": shape
                        }
                        branch_properties["required_information_domain"] = {
                            "const": information_domain
                        }
                        branch_properties["required_output_mode"] = {
                            "const": output_mode
                        }
                    return {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": branch_properties,
                        "required": responsibility_required,
                    }

                responsibility_branches: list[dict[str, Any]] = []
                for candidate_index in range(goal_count):
                    responsibility_branches.extend(
                        [
                            responsibility_branch(
                                coverage="covered",
                                candidate_index=candidate_index,
                                constrain_to_candidate=True,
                            ),
                            responsibility_branch(
                                coverage="clarification_required",
                                candidate_index=candidate_index,
                                constrain_to_candidate=True,
                            ),
                            responsibility_branch(
                                coverage="representation_mismatch",
                                candidate_index=candidate_index,
                                constrain_to_candidate=False,
                            ),
                        ]
                    )
                responsibility_branches.append(
                    responsibility_branch(
                        coverage="missing",
                        candidate_index=None,
                        constrain_to_candidate=False,
                    )
                )
                responsibility_items["items"] = {
                    "oneOf": responsibility_branches
                }
            if isinstance(supporting_items, dict):
                supporting_item = copy.deepcopy(item_schema)
                supporting_item["properties"]["role"] = {
                    "type": "string",
                    "enum": ["constraint", "context", "framing"],
                }
                supporting_items["items"] = supporting_item
        schema["required"] = [
            "responsibility_items",
            "supporting_items",
            "reason_summary",
        ]
        schema["additionalProperties"] = False
        return schema

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
                            cls._source_grounded_binding_coverage_conflicts(
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

    @staticmethod
    def _coverage_verdict(
        certificate: GoalResponsibilityCoverageCertificate,
        *,
        goal_count: int,
    ) -> tuple[Literal["accept", "reject"], list[str]]:
        problems: list[str] = []
        responsibility_owner_counts: dict[int, int] = {}
        positively_owned: set[int] = set()
        for item in certificate.items:
            if item.role in {"responsibility", "constraint"} and item.coverage not in {
                "covered",
                "clarification_required",
            }:
                problems.append(
                    f"{item.coverage}:{item.role}:{item.source_excerpt}"
                )
                # Preserve the auditor's typed semantic proof as feedback for the
                # one already-authorized fresh interpretation.  The Host does not
                # infer these facts from user wording; it only forwards fields the
                # GA-owned coverage model explicitly declared.
                if item.required_goal_shape != "ordinary":
                    problems.append(
                        "required_goal_shape:"
                        + item.required_goal_shape
                        + f":{item.role}:{item.source_excerpt}"
                    )
                if item.required_information_domain != "none":
                    problems.append(
                        "required_information_domain:"
                        + item.required_information_domain
                        + f":{item.role}:{item.source_excerpt}"
                    )
                if item.required_output_mode != "none":
                    problems.append(
                        "required_output_mode:"
                        + item.required_output_mode
                        + f":{item.role}:{item.source_excerpt}"
                    )
            if item.role != "responsibility" or item.coverage not in {
                "covered",
                "clarification_required",
            }:
                continue
            for goal_index in item.candidate_goal_indices:
                positively_owned.add(goal_index)
                if item.independently_satisfiable:
                    responsibility_owner_counts[goal_index] = (
                        responsibility_owner_counts.get(goal_index, 0) + 1
                    )
        for goal_index, count in sorted(responsibility_owner_counts.items()):
            if count > 1:
                problems.append(
                    f"overmerged_independent_responsibilities:goal[{goal_index}]"
                )
        unjustified = sorted(set(range(max(0, goal_count))) - positively_owned)
        if unjustified:
            problems.append(
                "unjustified_goal_indices:"
                + ",".join(str(index) for index in unjustified)
            )
        return ("reject", problems) if problems else ("accept", [])

    def _build_fresh_interpretation_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        candidate_goals: list[dict[str, Any]],
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        problems: list[str],
        preserve_unresolved_meaning: bool = False,
    ) -> str:
        terminal_instruction = (
            "The independent proof established that material meaning is unresolved. "
            "Preserve a provisional Goal for the source-grounded Responsibility without "
            "inventing the unresolved referent or scope. Goal Interpretation has already "
            "exposed the ambiguity to Fast Planner, which alone decides whether and how "
            "to ask; Goal Association must not author a clarification Activity or wording. "
            if preserve_unresolved_meaning
            else ""
        )
        return (
            self._build_prompt(
                request,
                candidate_goals,
                output_type=output_type,
            )
            + "\n\nAn independent source-grounded coverage proof rejected the "
            "first candidate set. Discard that candidate DTO as authority and perform "
            "one final fresh interpretation from the FINAL AUTHORITATIVE USER TURN. "
            "Do not discard independently supported current-turn Responsibility evidence: "
            "the Fast responsibility proposals rendered above remain provider-neutral "
            "semantic evidence and must be re-checked against the authoritative turn. "
            "The FINAL AUTHORITATIVE USER TURN remains the source for explicit material "
            "qualifiers: if a proposal or rejected candidate generalized away severity, "
            "intensity, magnitude, threshold, subtype, negation, comparison, quantity, or "
            "scope, restore that source-grounded WHAT in the final Goal representation. "
            "Planner Activity metadata is never a Responsibility source and must not be "
            "preserved as a Goal. "
            "Removing an unjustified sibling Goal never permits dropping a still-supported "
            "human Responsibility. The following compact defects are proof feedback, not "
            "Goal labels and not permission to copy a previous DTO:\n"
            + self._bounded_json(problems, 3000)
            + "\n"
            + "Typed proof feedback is structural, not optional prose. When it says "
            "required_goal_shape:ordinary, the corrected candidate must have no "
            "resource_responsibility. Preserve requested body motion, locomotion, "
            "gaze, gesture, posture, or vocal performance through its exact output_mode "
            "and top-level semantic bindings; none of those effects is an object to "
            "acquire and hand over. When the proof reports representation_mismatch for "
            "an embodied or vocal modality, re-read the source effect and use body_action "
            "for locomotion/gaze/blink/gesture/posture or the exact singing/recitation/"
            "humming/styled_speech/nonverbal_vocalization mode for an authored vocal "
            "performance. Keep each independently observable coordinated effect in its "
            "own Goal. When feedback lists required_output_mode, preserve that exact "
            "output_mode in the corrected candidate; descriptive prose cannot satisfy "
            "this typed requirement. When it says "
            "required_goal_shape:information_resource, the corrected candidate must "
            "carry one resource_responsibility object with kind=information; "
            "output_mode=capability_work or a descriptive sentence alone does not "
            "satisfy that shape. Its top-level bindings must be empty and all query "
            "facts must live in resource_responsibility.query_scope. When feedback "
            "lists required_information_domain, preserve that exact provider-neutral "
            "domain in resource_responsibility.information_domain; never relabel a "
            "nearby-person or local-observation need as weather, clock, or web research. "
            "Every query_scope item must preserve source-grounded human semantic "
            "scope. Temporal wording belongs here as the user's semantic constraint, "
            "not as Planner/Capability date, period, or clock-range arguments. Every "
            "query_scope item must "
            "be entailed by the FINAL AUTHORITATIVE USER TURN, supplied Responsibility "
            "evidence, or an explicitly resolved discourse referent. Never invent a "
            "provider prerequisite, placeholder, default, current location, source, "
            "device, or other query fact merely because it might help execution. A "
            "request for Chromie's current local clock time carries the supplied "
            "time=now fact; it does not imply a location query.\n"
            "For a physical resource, source-grounded distance, direction, location, "
            "or route feedback requires source.status=known plus one "
            "source.acquisition_bindings item for every supplied fact. unknown is not "
            "a placeholder for supplied spatial grounding, and prose cannot replace "
            "these typed bindings. Omit optional quantity unless a normalized positive "
            "numeric value is source-grounded.\n"
            + terminal_instruction
            + "Return one complete final DTO. This interpretation receives no "
            "contract repair; invalid or incomplete output fails closed."
        )

    @staticmethod
    def _responsibility_coverage_system_prompt() -> str:
        return (
            "You are Chromie's independent Goal responsibility-coverage auditor. "
            "Read the authoritative turn from scratch; candidate prose is not source "
            "evidence. Copy every source_excerpt only from an exact contiguous span of "
            "the FINAL AUTHORITATIVE USER TURN in its original language; never use a "
            "translation or paraphrase from Responsibility outcome or binding text. "
            "A positive observable outcome is a responsibility. Duration, "
            "distance, direction, order, manner, prohibition, temporal scope, and other "
            "conditions on that same outcome are constraints, never independently "
            "satisfiable responsibilities. That role distinction is only the audit "
            "shape: a constraint belongs on the same candidate Goal as the "
            "responsibility it modifies, normally through a typed binding, and does "
            "not need its own Goal. A constraint is covered when the candidate's "
            "typed binding preserves its meaning; do not call it a representation "
            "mismatch merely because the modifier also appears in the candidate "
            "description or the binding uses an equivalent normalized value. "
            "A reason or background event that only explains why the answer is useful "
            "and does not change which answer would be correct is context, not a "
            "constraint; context is covered without Goal ownership. Only background "
            "that changes valid completion is a constraint. Preserve temporal source "
            "wording as one human semantic constraint rather than decomposing it into "
            "provider-facing date/day-part fields. Coordinated effects are separate only when a "
            "person can judge each effect completed without the others. One evidence "
            "lookup and the requested judgment of its result remain one responsibility. "
            "Coordination grammar never demotes a positive effect to a constraint. If a "
            "coordinated clause mixes a relation or manner with another observable effect, "
            "give every effect its own role=responsibility item and put only the relation, "
            "order, or manner material in role=constraint. Never leave the action or effect "
            "word itself only in supporting_items. "
            "Use the exact required_output_mode: body_action for embodied effects; the "
            "exact singing/recitation/humming/styled_speech/nonverbal_vocalization mode "
            "for authored performance; media_playback for media control; capability_work "
            "for fresh evidence or persistent effects; and speech for ordinary dialogue. "
            "Wrong completion mode or resource shape is "
            "coverage=representation_mismatch. A physical resource means acquisition and "
            "handover of a distinct concrete object; body motion is not a physical "
            "resource. A state mutation or future delivery is a persistent effect, not "
            "information acquisition. For temporal constraints, coverage means the "
            "candidate preserves the source-grounded human scope without silently "
            "narrowing, translating, or decomposing it into Capability arguments. Use "
            "coverage=missing only when no candidate attempts the fragment and then use "
            "no candidate index. Use clarification_required only when supplied evidence "
            "cannot uniquely ground a material pronoun, demonstrative, ellipsis, "
            "correction, or other indirect reference. Do not plan, select Capabilities, "
            "execute, add Goals, or trust provider availability. Before returning, "
            "cross-check the JSON against reason_summary: when the reason says an effect "
            "is distinct, observable, standalone, independently satisfiable, or must have "
            "its own Goal/responsibility, that effect must appear in responsibility_items "
            "with role=responsibility and must not appear only in supporting_items. Return "
            "JSON only."
        )


    def _build_responsibility_coverage_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        raw: dict[str, Any],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        raw_json = self._bounded_json(raw, 9000)
        if self._uses_compact_coverage_contract(request=request, raw=raw):
            return self._build_compact_responsibility_coverage_prompt(
                request=request,
                raw_json=raw_json,
            )
        responsibility_cross_check = [
            {
                "local_ref": item.local_ref,
                "outcome": item.outcome,
                "output_mode": item.output_mode,
            }
            for item in request.responsibilities
        ]
        return (
            "Audit whether this candidate Goal segmentation completely accounts for "
            "the authoritative user's current semantic responsibilities. This is an "
            "independent audit: candidate Goal wording is not evidence that the "
            "segmentation is complete by itself. Inspect the complete candidate DTO: "
            "description, output_mode, typed bindings, resource responsibility, and "
            "source/recipient fields are the evidence for what each candidate "
            "actually represents. Do not call a constraint missing when those fields "
            "materially preserve it on the Goal that it modifies.\n\n"
            "For each semantically material fragment of the current turn, emit one "
            "entry and copy source_excerpt as a verbatim contiguous span from "
            "the FINAL AUTHORITATIVE USER TURN. Use role=responsibility for a positive "
            "outcome Chromie owes, role=constraint for a modifier/prohibition/timing "
            "condition on such an outcome, role=context for reference/background that "
            "does not itself need completion, and role=framing for politeness or social "
            "preamble attached to substantive work. A stated preference, reason, "
            "candidate option, or background fact that changes what counts as a valid decision "
            "must be role=constraint and must map to the Goal whose result it constrains; "
            "it cannot be downgraded to context merely because it is not an independent "
            "outcome. Only incidental background that does not change valid completion is "
            "role=context. In particular, a reason or future event that merely explains "
            "why the requested answer will be useful is context when it does not alter "
            "the correctness or required shape of that answer. These facts are not "
            "independent responsibilities unless the user "
            "separately asks for an observable outcome for each. Stated preferences therefore "
            "remain material constraints when the user asks for a choice between them. A "
            "manner, mood, persona, or social-"
            "presentation modifier attached to a requested effect is role=constraint "
            "on that effect; it is not a second responsibility merely because speech "
            "could also convey the style. When a concrete effect is requested together "
            "with a broad desired social impression but no words, information, vocal "
            "performance, or second effect modality is specified, that impression is "
            "embodiment-wide framing on the concrete effect. Do not infer speech from "
            "an adjective, state directive, conjunction, or imperative grammar. Emit "
            "each semantic fragment once: never duplicate the same source_excerpt "
            "under both responsibility and constraint (or any other conflicting "
            "roles); decide its one actual role. Temporal wording is audited as a "
            "source-grounded constraint on the affected Goal. Preserve the human scope "
            "itself; do not require or infer provider date/day-part dimensions in this "
            "Goal-coverage stage. A duration remains a duration rather than becoming a "
            "calendar or local-day parameter.\n\n"
            "Set independently_satisfiable=true only when the user could reasonably "
            "judge that positive outcome completed even if sibling outcomes did not "
            "happen. A factual lookup and an interpretation requested from that same "
            "evidence form one responsibility when one result satisfies both. Multiple "
            "aspects requested from one information result likewise remain one "
            "responsibility when the same evidence satisfies them; answerable sub-aspects "
            "are not automatically independent outcomes. Represent their contiguous request as one "
            "responsibility and set independently_satisfiable=false. Every genuinely "
            "independently satisfiable responsibility must own its own "
            "Goal candidate. Do not collapse separately observable requested effects "
            "merely because they can overlap in time, share one sentence, or use a "
            "common provider. For acquire-and-deliver meaning, apply the inverse "
            "counterfactual too: navigation, distance, direction, locating, pickup, "
            "carrying, return, and handoff are not independent positive outcomes when "
            "the person would consider them satisfied by successful resource delivery "
            "and would not still require that stage for its own sake. In that case map "
            "the material fragment as a constraint on the one resource responsibility, "
            "not as ownership evidence for another Goal. Conversely, do "
            "not promote greeting/politeness framing, implementation steps, result "
            "delivery, or a negative speech boundary into a separate Goal.\n\n"
            "For coverage=covered, map a responsibility to exactly one candidate Goal "
            "index; a constraint may map to one or more affected Goal indices. Use "
            "coverage=missing only when a responsibility or constraint has no Goal "
            "candidate attempting to own it, and then candidate_goal_indices must be empty. "
            "If a candidate attempts to own the fragment but drops or generalizes a material "
            "qualifier, binding, result aspect, severity/intensity, threshold, subtype, "
            "comparison, or scope, use coverage=representation_mismatch and include that "
            "candidate index instead. Use clarification_required only when GI's supplied "
            "unresolved-meaning evidence says the human-level responsibility cannot be "
            "fully determined without asking the user; map it to the one provisional Goal "
            "that preserves that Responsibility. Context and framing "
            "acknowledge non-owed meaning rather than requiring ownership: they must "
            "always use coverage=covered, independently_satisfiable=false, and an "
            "empty candidate_goal_indices list. Never mark context or framing as "
            "missing. For a represented constraint, the expected shape is "
            "role=constraint, independently_satisfiable=false, coverage=covered, and "
            "the affected Goal index or indices. Never mark a constraint missing "
            "merely because it is not a responsibility, has no separate Goal, or is "
            "an instrumental provider stage; mark it missing only when no candidate "
            "DTO field preserves it on the outcome that it modifies. Coverage also "
            "requires the candidate's output_mode, resource shape, and observable "
            "completion meaning to match the requested responsibility. Use "
            "coverage=representation_mismatch when a state mutation or deferred effect "
            "(recording/updating something, scheduling a future notification, or sending "
            "something later) is represented as an information resource, when provider-"
            "backed evidence work is represented as ordinary speech, or when immediate "
            "reasoning/advice with no fresh evidence need is represented as external "
            "information acquisition. Also use representation_mismatch when an ordinary "
            "authored conversational response—such as greeting, empathy, reassurance, "
            "restatement, or acknowledgement of the person's feeling—is represented as "
            "capability_work or body_action. Preserve speaker and experiencer ownership; "
            "the person's first-person state never authorizes a robot effect. If the user "
            "asks what Chromie just said, the candidate must make Chromie repeat or "
            "summarize the supplied assistant utterance; a candidate that instead asks "
            "the user to repeat reverses speaker and addressee and is a representation "
            "mismatch. Every responsibility item must set required_goal_shape: "
            "information_resource for acquiring grounded external/private/runtime information, "
            "physical_resource for acquiring and handing over an object, persistent_effect "
            "for a deferred or state-changing Capability outcome, and ordinary otherwise. "
            "Only role=responsibility classifies the Goal shape. Every constraint, "
            "context, and framing item must set required_goal_shape=ordinary even when "
            "it modifies a non-ordinary Goal; map it to that Goal with candidate indices "
            "instead of repeating the Goal-shape classification. "
            "Every information_resource responsibility must also set exactly one "
            "required_information_domain: local_clock for Chromie's trusted current "
            "date/time, weather_forecast for weather, external_grounded_information "
            "for public facts/research, direct_environment_perception for current "
            "nearby people/objects/events, or private_runtime_information for other "
            "private live state. All non-information items must use none. Judge the "
            "needed evidence domain from the authoritative turn, never from currently "
            "available Capabilities or Agent Skills. A weather provider cannot turn a "
            "person-presence question into weather. "
            "A covered item is invalid when the typed candidate lacks that declared shape. "
            "Speech cannot cover requested body motion, media "
            "control, external evidence work, or a vocal performance. Every Goal "
            "candidate must be "
            "justified by at least one covered role=responsibility item; a constraint "
            "alone never justifies another Goal. Do not author a top-level verdict or "
            "unjustified-candidate inventory; trusted code derives both from the item "
            "judgments. A resource Goal's nested typed resource fields are authoritative; "
            "its human-readable description cannot supply or override a missing resource "
            "fact, and a material contradiction between summary and typed truth is not "
            "covered. For an information resource, requested location, time, and result "
            "aspects are covered only by resource_responsibility.query_scope; its narrow "
            "source object cannot own those query facts. Reject invented query "
            "dimensions too: every query_scope item must be entailed by the final user "
            "turn, supplied Responsibility bindings, or a resolved discourse referent. "
            "A guessed current location, timezone, provider prerequisite, placeholder, "
            "device, or source is a representation_mismatch even when it is called "
            "unspecified or copied from a larger non-location clause. Audit every "
            "supplied temporal scope as source-grounded human meaning. For an information "
            "Goal, resource_responsibility.query_scope must retain that scope without "
            "silently narrowing, translating, or converting it into provider arguments. "
            "A compound natural expression may remain one temporal_scope binding. If the "
            "candidate drops or changes that human scope, use coverage=representation_mismatch. "
            "For a physical resource, an "
            "acquisition location, distance, direction, or route constraint is covered "
            "only by resource_responsibility.source.acquisition_bindings. Descriptions "
            "are summary only. The schema deliberately exposes one writable owner per "
            "resource fact, so coverage must never infer a missing typed fact from prose. "
            "Classify the meaning in context; "
            "do not decide its role from a field name alone.\n\n"
            "Reference grounding is part of responsibility coverage. Before assigning "
            "coverage, explicitly identify each material indirect referring expression "
            "in the authoritative turn and audit its grounding independently. A material "
            "pronoun, demonstrative, ellipsis, correction, or other indirect "
            "reference is covered only when the candidate copies an explicit current-"
            "turn value or a supplied discourse referent with its referent_id. A "
            "candidate description that silently invents a generic object, device, "
            "person, task, or setting does not resolve the reference. Mark the "
            "containing responsibility or constraint clarification_required when the "
            "supplied evidence does not select exactly one meaning, including when "
            "multiple scene candidates remain plausible. Candidate prose alone cannot "
            "ground an indirect target; require the explicit current-turn value or the "
            "typed referent-backed binding before marking it covered.\n\n"
            "Do not add, remove, rename, plan, execute, or complete Goals. Do not use "
            "provider availability to decide whether a responsibility exists. An "
            "unavailable requested effect remains a responsibility. Cross-check every "
            "source-grounded authoritative GI Responsibility before returning: each "
            "positive effect entailed by the final turn needs a role=responsibility owner, "
            "even when it shares a coordinated clause or no provider can perform it.\n\n"
            "Authoritative Responsibility cross-check list (audit every entry against "
            "the source; do not silently omit an entry from the certificate):\n"
            f"{self._bounded_json(responsibility_cross_check, 2200)}\n\n"
            "Put every positive-outcome role=responsibility entry in the required "
            "responsibility_items array. Set independently_satisfiable=true only when "
            "that outcome can stand as a sibling Goal; one resource lookup whose "
            "requested judgment depends on the same result may remain false. Put "
            "role=constraint, context, and framing entries in supporting_items. Once independently observable component "
            "Responsibilities have been enumerated, never add the whole compound "
            "sentence as another Responsibility; coordination is not another outcome. "
            "For coordination grammar in any language, split the smallest exact "
            "contiguous source spans so each positive effect remains in "
            "responsibility_items; supporting_items may contain only the relation, order, "
            "or manner that modifies those effects. "
            "Every candidate Goal index must have a "
            "covered responsibility owner. Never return only constraints, even when "
            "the constraints are represented correctly. Keep a positive outcome and "
            "its temporal, location, manner, or prohibition constraints in separate audit "
            "entries when the source grammar permits, but never decompose one human "
            "temporal expression into Capability-facing fields. Also reject your own draft when reason_summary calls an "
            "effect distinct, observable, standalone, independently satisfiable, or in "
            "need of its own Goal/responsibility but the JSON places that effect only in "
            "supporting_items. The structured arrays, role, and coverage must express the "
            "same conclusion as reason_summary.\n\n"
            "Candidate Goal DTO JSON:\n"
            f"{self._bounded_json(raw, 9000)}\n\n"
            "Authoritative Responsibility evidence JSON (query facts may be "
            "normalized but never invented beyond this evidence and the final turn):\n"
            f"{self._bounded_json([item.model_dump(mode='json', exclude_none=True) for item in request.responsibilities], 3200)}\n\n"
            "GI unresolved-meaning evidence (the only authority for "
            "clarification_required coverage):\n"
            f"{self._bounded_json(request.interpretation_unresolved, 1600)}\n\n"
            "Recent conversation JSON (reference context only; current-turn Goal "
            "coverage must still be anchored by source_excerpt from the final turn):\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-6:], 3000)}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
        )

    def _uses_compact_coverage_contract(
        self,
        *,
        request: CognitiveWorkRequest,
        raw: dict[str, Any],
    ) -> bool:
        """Select the bounded one-Responsibility transport shape mechanically."""

        context = request.context if isinstance(request.context, dict) else {}
        history = (context.get("history") or request.history or [])[-6:]
        return bool(
            len(request.responsibilities) == 1
            and not request.interpretation_unresolved
            and not history
            and not self._discourse_referents(request)
            and len(self._bounded_json(raw, 9000)) <= 2500
        )

    def _build_compact_responsibility_coverage_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        raw_json: str,
    ) -> str:
        """Audit one bounded, reference-free Responsibility without prompt repetition."""

        responsibility_json = self._bounded_json(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in request.responsibilities
            ],
            3200,
        )
        return (
            "Independently audit the candidate DTO against the final user turn and GI "
            "Responsibility evidence. Emit each material source fragment exactly once. "
            "Every source_excerpt must be copied from an exact contiguous span of the "
            "FINAL AUTHORITATIVE USER TURN in its original language; never copy a "
            "translated or paraphrased Responsibility outcome or binding. "
            "Use role=responsibility only for the positive outcome Chromie owes. A "
            "duration, distance, direction, speed, location, order, simultaneity, manner, "
            "prohibition, temporal scope, threshold, comparison, severity, preference, or "
            "answer-shaping detail is role=constraint on that outcome and must set "
            "independently_satisfiable=false. Duration is never a second outcome. Stated "
            "preferences that changes what counts as a valid decision must be "
            "role=constraint. A reason or future event that merely explains why the "
            "requested answer is useful, without changing which answer is correct, is "
            "role=context, coverage=covered, and owns no Goal. Context and framing are "
            "not owed outcomes. Multiple aspects "
            "requested from one information result likewise remain one responsibility. "
            "Never duplicate the same span under conflicting roles. This role split "
            "describes the certificate, not separate Goal candidates: a constraint "
            "belongs on the same candidate as the responsibility it modifies. Inspect "
            "the candidate's typed bindings as authoritative candidate evidence. Mark "
            "a constraint covered when one of those bindings preserves its meaning, "
            "including an equivalent normalized value from the supplied Responsibility "
            "evidence. Do not report representation_mismatch merely because the "
            "modifier also appears in the candidate description or has no separate "
            "Goal; those are correct for a non-independent constraint.\n\n"
            "For coverage=covered, a responsibility maps to exactly one candidate index; "
            "a represented constraint maps to the affected candidate. If nothing attempts "
            "a material fragment use coverage=missing and candidate_goal_indices must be "
            "empty. If a candidate attempts it but drops or generalizes a material "
            "qualifier, binding, scope, threshold, or completion meaning, use "
            "coverage=representation_mismatch and include its index. "
            "clarification_required is allowed only from supplied GI unresolved evidence "
            "(none is supplied here). Every candidate must have one covered positive "
            "responsibility owner. Never return only constraints.\n\n"
            "Set required_output_mode to the exact requested modality and require an exact "
            "candidate output_mode match. Set required_goal_shape to information_resource "
            "for fresh information, physical_resource for acquiring and handing over a "
            "distinct concrete object, persistent_effect for deferred/state-changing "
            "work, and ordinary otherwise. Non-responsibility items always use ordinary. "
            "A state mutation or deferred effect represented as information, ordinary "
            "dialogue represented as capability work, or body motion represented as a "
            "physical object is a representation_mismatch. For information, set exact "
            "required_information_domain; non-information uses none. requested location, "
            "time, and result aspects are covered only by "
            "resource_responsibility.query_scope. Physical acquisition location, distance, "
            "direction, and route are covered only by source.acquisition_bindings. Prose "
            "cannot replace a typed fact. A temporal constraint is covered when the Goal "
            "preserves its source-grounded human scope; do not require date/period fields "
            "that belong to a later Capability realization.\n\n"
            "Reference grounding is part of responsibility coverage. Candidate prose that "
            "silently invents a generic object does not ground a reference; use "
            "clarification_required when multiple scene candidates remain plausible. No "
            "indirect-reference evidence is supplied in this bounded request.\n\n"
            "Put positive outcomes in responsibility_items and constraints/context/framing "
            "in supporting_items. Include required_goal_shape, "
            "required_information_domain, required_output_mode, exact verbatim contiguous "
            "source_excerpt, coverage, independently_satisfiable, and candidate_goal_indices. "
            "Before returning, audit field consistency: every positive outcome that can "
            "stand alone uses independently_satisfiable=true; each modifier uses the "
            "smallest distinct contiguous source span available; and every "
            "non-responsibility uses required_output_mode=none. "
            "Return the certificate JSON only.\n\n"
            "Candidate Goal DTO JSON:\n"
            f"{raw_json}\n\n"
            "Authoritative Responsibility evidence JSON:\n"
            f"{responsibility_json}\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}"
        )


    @staticmethod
    def _semantic_review_system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
        *,
        fresh_resegmentation: bool = False,
    ) -> str:
        contract_name = (
            "Goal Segmentation"
            if output_type is GoalSegmentationModelOutput
            else "Goal Association"
        )
        return (
            f"You are Chromie's independent semantic reviewer for the "
            f"{contract_name} boundary. "
            + (
                "Perform a fresh segmentation from the authoritative user turn; "
                "no earlier Goal labels are evidence and none are available to copy. "
                if fresh_resegmentation
                else "Review the supplied DTO without assuming it is correct. "
            )
            + "Decide with model reasoning whether responsibilities are genuinely "
            "independent and classify each by its completion channel. An authored "
            "vocal performance belongs to vocal_output even when coordinated "
            "with embodied work. Return only the complete final DTO as JSON. The "
            "Host owns validation, IDs, lifecycle, and persistence and does not make "
            "this semantic choice."
        )

    @staticmethod
    def _repair_system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        contract_name = (
            "Goal Segmentation"
            if output_type is GoalSegmentationModelOutput
            else "Goal Association"
        )
        return (
            f"You repair one minimal {contract_name} semantic DTO using semantic reasoning and the supplied exact JSON Schema. "
            "Return only the corrected JSON object. Do not add commentary, markdown, lexical mappings, or hidden reasoning."
        )

    @staticmethod
    def _system_prompt(
        output_type: (
            type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
        ),
    ) -> str:
        if output_type is GoalSegmentationModelOutput:
            return (
                "You are Chromie's Goal Segmentation model. No active or retained recent Goal IDs exist, so association with existing work is impossible. "
                "Use semantic reasoning to resolve current-turn references from scoped discourse context and preserve independently satisfiable user responsibilities as separate new Goals, but never turn plan steps into goals. "
                "Conversational framing attached to a substantive responsibility is not independently satisfiable work: do not create a separate Goal for its greeting or politeness preamble. A standalone social interaction remains one conversational Goal. "
                "When one evidence acquisition satisfies both a factual lookup and the requested interpretation of its result, preserve them as one Goal. "
                "Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
                "You are advisory only and never execute or commit. Return JSON only."
            )
        return (
            "You are Chromie's Goal Association and Segmentation model. Return only the minimal semantic DTO; the host owns all transport and persistence fields. "
            "Apply continuity before creation. Resolve references from current user meaning, scoped discourse referents/focus, bounded candidate Goals and their bindings, and dialogue context. Candidate Goals may be active, recoverable, or recently terminal; referencing a terminal Goal does not reopen it. Tool-result memory is not reference-resolution authority. Status follow-ups about an unfinished lookup should associate with the bound task; if its safe read is recoverable, preserve the exact skill arguments for retry. Do not treat another task's evidence as completion. "
            "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
            "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
            "Conversational framing attached to substantive work is not a separate Goal; a standalone social interaction remains one conversational Goal. A new reaction, feeling, evaluation, acknowledgement, or practical decision after a prior result is a current conversational responsibility, not continuation of the completed lookup. One lookup and an interpretation requested as part of that same lookup are one Goal. "
            "You are advisory only and never execute or commit. Return JSON only."
        )

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
            for item in self._discourse_referents(request)
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
