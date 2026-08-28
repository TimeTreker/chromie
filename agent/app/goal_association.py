from __future__ import annotations

import hashlib
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
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
)
from .goal_association_schema import goal_association_response_schema
from .goal_association_validation import (
    action_collection_bindings,
    binding_semantic_contract_conflicts,
    drop_ungrounded_resource_query_locations,
    non_verbatim_explicit_location_bindings,
    normalize_grounded_binding_types,
    normalize_optional_referent_updates,
    normalize_optional_resource_quantity,
    normalize_resource_binding_branches,
    resource_source_binding_contract_conflicts,
    responsibility_output_mode_conflicts,
    restore_missing_goal_descriptions,
    source_grounded_binding_conservation_conflicts,
    validation_error_json,
)


from .goal_association_prompt import (
    discourse_referents,
    layered_prompt,
    layered_repair_prompt,
    repair_system_prompt,
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
            responsibility_information_refs={
                item.local_ref
                for item in request.responsibilities
                if item.output_mode == "information"
            },
            responsibility_bindings={
                item.local_ref: {
                    str(name): value
                    for name, value in item.bindings.items()
                    if isinstance(value, (str, int, float, bool))
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
        contract_repair_attempted = False
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
            if logical_invocations >= 2:
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
            normalized, recovered = normalize_grounded_binding_types(
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
                model_output = output_type.model_validate(initial_raw)
                accepted_raw = initial_raw
            except ValidationError as initial_exc:
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
                model_output = output_type.model_validate(repaired)
                accepted_raw = repaired

            resolution = await self._materialize_primary_output(
                model_output,
                request=request,
                turn_id=turn_id,
            )

            metadata = dict(resolution.metadata)
            expected_responsibility_refs = [
                item.local_ref for item in request.responsibilities
            ]
            mapped_responsibility_refs = [
                ref
                for association in getattr(model_output, "associations", [])
                for ref in association.source_responsibility_refs
            ] + [
                ref
                for goal in model_output.new_goals
                for ref in goal.source_responsibility_refs
            ]
            metadata.update(
                {
                    "goal_semantic_transaction": {
                        "logical_invocation_count": logical_invocations,
                        "logical_invocation_budget": 2,
                        "prompt_families": invocation_families,
                        "contract_repair_attempted": contract_repair_attempted,
                        "terminal_state": "commit",
                    },
                    "responsibility_conservation": {
                        "evidence_source": "goal_association.primary",
                        "expected_refs": expected_responsibility_refs,
                        "mapped_refs": mapped_responsibility_refs,
                        "source_grounded_bindings": "validated",
                        "status": "validated",
                    },
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
                    "logical_invocation_budget": 2,
                    "prompt_families": invocation_families,
                    "contract_repair_attempted": contract_repair_attempted,
                    "terminal_state": "fail_closed",
                },
                "initial_raw_output_ref": cognition_text_reference(initial_raw),
                "accepted_raw_output_ref": cognition_text_reference(accepted_raw),
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


    async def _materialize_primary_output(
        self,
        model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
        *,
        request: CognitiveWorkRequest,
        turn_id: str,
    ) -> GoalAssociationResolution:
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
        binding_conservation_conflicts = (
            source_grounded_binding_conservation_conflicts(
                model_output,
                request=request,
            )
        )
        if binding_conservation_conflicts:
            raise ValueError(
                "Goal Association primary result must conserve every directly "
                "source-grounded material binding on its canonical Goal surface: "
                + ", ".join(binding_conservation_conflicts)
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
                        "output_mode": item.output_mode,
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
