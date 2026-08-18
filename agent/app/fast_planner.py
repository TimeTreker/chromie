from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .capabilities.validator import validate_args_for_schema
from .clients.ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
    llm_failure_metadata,
)
from .agent_skills import agent_skill_prompt_section
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
)
from .planner_contract import (
    EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
    PlannerDTOContractError,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
    canonical_resource_argument_response_schema,
    canonical_goal_grounding,
    canonical_plan_response_schema,
    goal_association_prompt_projection,
    coordinated_action_goal_ids,
    evidence_bound_dialogue,
    expected_goal_ids,
    fast_multi_goal_response_schema,
    is_planner_step_capability,
    materialize_goal_outcomes,
    materialize_planner_metadata,
    normalize_detached_parameter_resolutions,
    normalize_schema_default_parameter_provenance,
    parallel_plan_contract_errors,
    planner_goal_execution_requirements,
    planner_response_goal_ids,
    planner_contract_diagnostics,
    retained_evidence_response_review_required,
    review_coordinated_action_plan_coverage,
    review_retained_evidence_response,
    situation_prompt_projection,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_user_supplied_parameter_provenance,
    validate_resource_responsibility_capability_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
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
        FastPlannerProgressAct,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerProgressAct,
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
        communication_reviewer: OllamaClient | None = None,
        min_confidence: float = 0.8,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        max_capabilities: int = 24,
        max_contract_repairs: int = 1,
    ) -> None:
        self.ollama = ollama
        self.communication_reviewer = communication_reviewer or ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.max_capabilities = max(1, min(64, int(max_capabilities)))
        self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))

    async def resolve_advance(self, request: CognitiveWorkRequest) -> FastPlannerAdvance:
        """Produce Fast Planner's first Activity Plan from GI Responsibilities."""

        context = request.context if isinstance(request.context, dict) else {}
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(item.model_dump(mode="json"))
            for item in request.responsibilities
        ]

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
        response_schema = self._advance_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            capabilities=capability_payload,
        )
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": min(self.num_predict, 1024),
        }
        previous_errors = ""
        last_raw: Any = None
        for attempt in range(self.max_contract_repairs + 1):
            try:
                last_raw = await self.ollama.generate(
                    self._advance_layered_prompt(
                        request,
                        responsibilities=responsibilities,
                        capabilities=capability_payload,
                        validation_errors=previous_errors,
                    ),
                    system=self._advance_system_prompt(),
                    options=options,
                    response_format=response_schema,
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
                output = FastPlannerAdvanceModelOutput.model_validate(last_raw)
                self._validate_advance_output(
                    output,
                    request=request,
                    responsibilities=responsibilities,
                    capabilities=capability_payload,
                )
                return FastPlannerAdvance(
                    turn_id=str(request.sid or "turn-fast-advance"),
                    disposition=output.disposition,
                    coverage=output.coverage,
                    covered_responsibility_refs=output.covered_responsibility_refs,
                    activities=output.activities,
                    continuations=output.continuations,
                    confidence=output.confidence,
                    unresolved=output.unresolved,
                    reason_summary=output.reason_summary,
                    metadata={
                        "semantic_authority": "fast_planner_model",
                        "phase": "responsibility_activity_planning",
                        "execution_authority": "trusted_capability_runtime",
                        "contract_revision_attempted": bool(attempt),
                    },
                )
            except Exception as exc:
                if attempt < self.max_contract_repairs and isinstance(
                    exc,
                    (PlannerDTOContractError, ValidationError, json.JSONDecodeError),
                ):
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
                )
        raise AssertionError("unreachable")

    @staticmethod
    def _advance_response_schema(
        responsibility_refs: list[str],
        *,
        responsibilities: list[CognitiveResponsibilityProposal] | None = None,
        capabilities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Constrain Fast Activities to the authoritative WHAT and live catalog.

        A Responsibility that only lacks fresh external Evidence cannot be decoded
        as a completed answer. The Planner may clarify only a source-proven semantic
        ambiguity or a real required Capability input after considering permitted
        sources/defaults; host validation below enforces that provenance.
        """

        responsibility_items = list(responsibilities or [])
        all_need_fresh_evidence = bool(responsibility_items) and all(
            item.completion_requires_fresh_evidence
            for item in responsibility_items
        )
        schema = copy.deepcopy(FastPlannerAdvanceModelOutput.model_json_schema())
        top_properties = schema.get("properties", {})
        disposition = top_properties.get("disposition")
        if isinstance(disposition, dict) and all_need_fresh_evidence:
            disposition["enum"] = [
                "execute",
                "mixed",
                "clarify",
                "escalate",
                "refused",
                "unavailable",
            ]
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"disposition": {"const": "escalate"}},
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "continuations": {
                                "items": {"const": "deep_planner"},
                                "minItems": 1,
                                "maxItems": 1,
                            }
                        }
                    },
                    "else": {
                        "properties": {"continuations": {"maxItems": 0}}
                    },
                },
                {
                    "if": {
                        "properties": {
                            "disposition": {"enum": ["execute", "mixed"]}
                        },
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "activities": {
                                "contains": {
                                    "type": "object",
                                    "properties": {"role": {"const": "capability"}},
                                    "required": ["role"],
                                },
                                "minContains": 1,
                            }
                        }
                    },
                },
            ]
        )
        refs = list(dict.fromkeys(responsibility_refs))
        covered = schema.get("properties", {}).get(
            "covered_responsibility_refs"
        )
        if isinstance(covered, dict):
            covered["items"] = {"type": "string", "enum": refs}
            covered["minItems"] = len(refs)
            covered["maxItems"] = len(refs)
            covered["uniqueItems"] = True
        definitions = schema.get("$defs", {})
        if all_need_fresh_evidence:
            activities = top_properties.get("activities")
            activity_items = (
                activities.get("items") if isinstance(activities, dict) else None
            )
            allowed_activity_contracts = [
                "FastPlannerProgressAct",
                "FastPlannerClarificationAct",
                "FastPlannerCapabilityActivity",
            ]
            if isinstance(activity_items, dict):
                activity_items["oneOf"] = [
                    {"$ref": f"#/$defs/{contract_name}"}
                    for contract_name in allowed_activity_contracts
                ]
                discriminator = activity_items.get("discriminator")
                if isinstance(discriminator, dict):
                    mapping = discriminator.get("mapping")
                    if isinstance(mapping, dict):
                        discriminator["mapping"] = {
                            role: ref
                            for role, ref in mapping.items()
                            if ref.rsplit("/", 1)[-1] in allowed_activity_contracts
                        }
        for contract_name in (
            "FastPlannerCompleteResponseAct",
            "FastPlannerClarificationAct",
            "FastPlannerProgressAct",
            "FastPlannerCapabilityActivity",
        ):
            contract = definitions.get(contract_name)
            if not isinstance(contract, dict):
                continue
            source_refs = contract.get("properties", {}).get(
                "source_responsibility_refs"
            )
            if isinstance(source_refs, dict):
                source_refs["items"] = {"type": "string", "enum": refs}
                source_refs["uniqueItems"] = True
        capability_contract = definitions.get("FastPlannerCapabilityActivity")
        progress_contract = definitions.get("FastPlannerProgressAct")
        if isinstance(progress_contract, dict):
            progress_contract.setdefault("allOf", []).extend(
                [
                    {
                        "if": {
                            "properties": {"progress_kind": {"const": progress_kind}},
                            "required": ["progress_kind"],
                        },
                        "then": {
                            "properties": {"speech_act": {"const": speech_act}}
                        },
                    }
                    for progress_kind, speech_act in (
                        ("acknowledge_work", "acknowledge"),
                        ("check_information", "acknowledge_and_check"),
                        ("perform_action", "acknowledge"),
                        ("think", "thinking"),
                    )
                ]
            )
        allowed_capabilities = [
            item
            for item in (capabilities or [])
            if isinstance(item, dict) and item.get("capability_id")
        ]
        if isinstance(capability_contract, dict) and allowed_capabilities:
            capability_id = capability_contract.get("properties", {}).get(
                "capability_id"
            )
            if isinstance(capability_id, dict):
                capability_id["enum"] = [
                    str(item["capability_id"])
                    for item in allowed_capabilities
                ]
            capability_contract["allOf"] = [
                {
                    "if": {
                        "properties": {
                            "capability_id": {
                                "const": str(item["capability_id"])
                            }
                        },
                        "required": ["capability_id"],
                    },
                    "then": {
                        "properties": {
                            "args": copy.deepcopy(item.get("input_schema") or {})
                        }
                    },
                }
                for item in allowed_capabilities
            ]
        return schema

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

    @staticmethod
    def _advance_fail_safe(
        request: CognitiveWorkRequest,
        *,
        responsibility_refs: list[str],
        error: Exception,
        raw_output: Any,
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
        progress_activities = FastPlannerResolver._validated_fail_safe_progress(
            raw_output,
            responsibility_refs=responsibility_refs,
        )
        return FastPlannerAdvance(
            turn_id=str(request.sid or "turn-fast-advance"),
            disposition="unavailable",
            coverage="uncertain",
            covered_responsibility_refs=responsibility_refs,
            activities=progress_activities,
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
                    item.activity_id for item in progress_activities
                ],
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
            try:
                active_response_schema = (
                    self._repair_response_schema(
                        response_schema,
                        initial_raw_output,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    if contract_repair_attempted
                    else response_schema
                )
                raw = await self.ollama.generate(
                    self._layered_prompt(
                        request,
                        capability_payload,
                        response_schema=response_schema,
                        previous_raw=previous_raw,
                        validation_errors=initial_validation_errors,
                    ),
                    system=(
                        self._repair_system_prompt()
                        if contract_repair_attempted
                        else self._system_prompt()
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
                    validate_goal_binding_argument_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
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
            if retained_evidence_response_review_required(request.context, validated):
                try:
                    communication_review = await review_retained_evidence_response(
                        self.communication_reviewer,
                        request_text=request.text,
                        language=str(request.language or "und"),
                        association=goal_association_prompt_projection(request.context),
                        authoritative_goals=canonical_goal_grounding(request.context),
                        delivered_evidence=evidence_bound_dialogue(
                            request.context,
                            fallback_history=request.history,
                        ),
                        plan=validated,
                        num_ctx=self.num_ctx,
                        turn_id=str(request.sid or ""),
                    )
                except Exception as exc:
                    logger.warning(
                        "fast_planner_communication_review_unavailable "
                        "sid=%s error_type=%s error=%s",
                        request.sid,
                        type(exc).__name__,
                        exc,
                    )
                    return self._escalation(
                        plan_id,
                        request,
                        "followup_communication_review_unavailable",
                        unresolved=["latest_communicative_act_unreviewed"],
                        error=exc,
                        path_classification="coverage_review_failure",
                        metadata={"execution_allowed": False},
                    )
                reviewed_by_goal = {
                    item.goal_id: item.response_text
                    for item in communication_review.goal_responses
                }
                reviewed_outcomes = [
                    item.model_copy(
                        update={"response_text": reviewed_by_goal[item.goal_id]}
                    )
                    if item.disposition == "respond"
                    else item
                    for item in validated.goal_outcomes
                ]
                metadata = dict(validated.metadata)
                metadata["communication_review"] = {
                    "status": (
                        "revised"
                        if communication_review.decision == "revise"
                        else "accepted"
                    ),
                    "confidence": communication_review.confidence,
                    "reason": communication_review.reason,
                    "semantic_authority": "planner_model",
                    "execution_authority": "none",
                }
                validated = validated.model_copy(
                    update={
                        "response_text": communication_review.response_text,
                        "goal_outcomes": reviewed_outcomes,
                        "metadata": metadata,
                    }
                )
                logger.info(
                    "fast_planner_communication_review_done sid=%s decision=%s",
                    request.sid,
                    communication_review.decision,
                )
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
            return validated
        raise AssertionError("unreachable")

    @staticmethod
    def _repair_response_schema(
        schema: dict[str, Any],
        initial_raw_output: Any,
        *,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        """Narrow a redundant aggregate to the model's own goal judgments.

        The initial model output remains the semantic authority for every
        per-goal disposition.  When that complete outcome map is valid but its
        redundant top-level aggregate is inconsistent, the bounded repair
        grammar permits only the mechanically consistent aggregate.  The host
        never examines user wording or chooses a goal outcome, step, or skill.
        """

        if not isinstance(initial_raw_output, dict):
            return schema
        outcomes = initial_raw_output.get("goal_outcomes")
        expected = list(expected_goal_ids_for_turn)
        if not isinstance(outcomes, dict) or set(outcomes) != set(expected):
            return schema
        dispositions: list[str] = []
        for goal_id in expected:
            outcome = outcomes.get(goal_id)
            if not isinstance(outcome, dict):
                return schema
            disposition = outcome.get("disposition")
            if disposition not in {"execute", "respond", "clarify", "escalate"}:
                return schema
            dispositions.append(disposition)
        disposition_set = set(dispositions)
        if disposition_set == {"execute"}:
            aggregate = "execute"
        elif disposition_set == {"respond"}:
            aggregate = "respond"
        elif disposition_set == {"execute", "respond"}:
            aggregate = "mixed"
        elif disposition_set == {"clarify"}:
            aggregate = "clarify"
        elif disposition_set == {"escalate"}:
            aggregate = "escalate"
        else:
            return schema
        narrowed = copy.deepcopy(schema)
        disposition_schema = narrowed.get("properties", {}).get("disposition")
        if not isinstance(disposition_schema, dict):
            return schema
        disposition_schema["enum"] = [aggregate]
        disposition_schema["description"] = (
            "Bounded contract repair: this is the sole aggregate consistent "
            "with the initial model-authored per-goal dispositions."
        )
        return narrowed

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
        return json.dumps(
            unique,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:10000]

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
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(
        self,
        request: CognitiveWorkRequest,
        capabilities: list[dict[str, Any]],
        *,
        response_schema: dict[str, Any],
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="fast_planner",
        )
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        association = goal_association_prompt_projection(context)
        grounding = canonical_goal_grounding(context)
        response_only, requires_execution = planner_goal_execution_requirements(grounding)
        argument_grounding_contract = (
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT
            + "For chromie.memory.retrieve_verified_tool_result, resolved Goal "
            "bindings such as location and date belong inside the single "
            "material_args object. They are not missing direct step arguments, "
            "so do not emit separate location or date parameter_resolutions. "
            "If a resolution for that nested object is useful, its parameter "
            "must be material_args and its value must equal the complete "
            "step.args.material_args object. "
        )
        goal_execution_contract = (
            "The canonical Goals are provider-free direct speech responsibilities. "
            "This plan is response-only: do not select executable capabilities or plan steps. "
            if response_only
            else (
                "At least one canonical Goal requires provider/effect evidence. The Plan "
                "must execute exact supplied Capability work for every such Goal or return "
                "a truthful escalation/clarification/unavailable/refused outcome. Do not "
                "close provider-required work with model memory or response text. "
                if requires_execution
                else ""
            )
        )
        semantic_scope_contract = "For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility while treating the current capability catalog as the dynamic decomposition boundary. Fast Planner may terminally execute the Goal only when one exact registered Capability is a complete one-step cover. A provider's resource_contract.plan_requires/plan_provides declares public composition state; provider-internal stages remain private unless exposed as capabilities. If the catalog has only partial resource capabilities that could form a multi-step chain, escalate to Deep Planner rather than inventing hidden provider stages or claiming a partial primitive is complete. The Goal is provider-neutral: choose from the catalog by declared semantic scope and resource contract, never from capability-name conventions or a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected complete capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. When the selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Those complete structured arguments are already grounded by the Goal contract; do not emit parameter_resolutions for their nested fields or invent a top-level quantity/distance argument that the Capability does not accept. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material tool argument, especially location, date, target, and entity identity, must equal the corresponding canonical binding; never reinterpret an original pronoun or replace a binding with an older memory entry. For chromie.weather.lookup, keep args.location exactly equal to the canonical location binding. When the user or discourse context clearly supplies a hierarchical place, you may also provide location_context with locality, admin1, country, and aliases for that same place; never use it to select a different place. Preserve every canonical-goal qualifier, including temporal scope, comparison period, answer shape, ordering, and concurrency. A calendar-date argument does not cover a finer day-part binding: exact coverage requires a capability argument and declared output evidence for that same day part. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; in particular, a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech authored by Response Composer. A user-requested spoken response or performance may still be simultaneous with an Activity-lane step. Preserve that relation without inventing a chromie.speak plan step: keep the spoken Goal as a respond outcome, set each participating Activity step to timing=parallel only when its provider declares safe parallel execution, and leave cross-lane speaking/activity coordination to Response Composer. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, escalate or propose an explicit safe adjustment rather than silently serializing the request. Never silently narrow a goal to fit a capability or its enum defaults. If the goal falls outside a capability's supported scope, escalate for clarification, another capability, or an honest unavailable result with zero steps. "
        current_turn_communication_contract = (
            "The FINAL AUTHORITATIVE USER TURN owns the current communicative act. "
            "Retained Goals, delivered evidence-bound dialogue, and verified memory "
            "may support the response, but they must not replace what the person just "
            "meant. For a reaction, feeling, acknowledgement, evaluation, or practical "
            "decision, answer that latest act directly and naturally. Do not replay the "
            "previous task answer unless the latest turn actually asks for repetition, "
            "verification, explanation, comparison, or another answer from it. For a "
            "decision-shaped follow-up, make the first sentence directly state the "
            "requested decision, recommendation, or yes/no answer; never begin by "
            "restating prior evidence. Include at most one short supporting clause "
            "after that answer, and omit previously delivered sentences, measurements, "
            "or conditions that do not change the decision. "
        )
        concise_output_contract = (
            "Keep goal summaries, step reasons, satisfaction rationales, and "
            "outcome rationales concise: one short sentence each. Do not "
            "repeat the user goal, catalog description, arguments, or the same "
            "justification across multiple fields. "
        )
        if len(expected_goal_ids(context)) > 1:
            return (
                f"Goal association advisory JSON:\n{self._bounded(association, 3000)}\n\n"
                f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
                f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
                f"{skill_section}"
                f"Executable common capability catalog JSON:\n{self._bounded(capabilities, 9000)}\n\n"
                f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
                f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
                f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{self._bounded(situation_prompt_projection(context), 3600)}\n\n"
                f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{self._bounded(situation_prompt_projection(context), 3600)}\n\n"
                f"{goal_progress_communication_prompt('Fast Planner')}\n\n"
                f"Goal-scoped Interaction Context JSON:\n{self._bounded(context.get('interaction_context') or {}, 7000)}\n\n"
                "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
                f"Previous Fast Planner output when doing a mechanical DTO regeneration:\n{self._bounded(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
                "When validation errors are present, regenerate one fresh complete model-authored plan object from the authoritative goals and catalog. Author the semantic plan directly. Do not classify text with lexical rules and do not expect the host to choose a capability, arguments, ordering, ownership, response, disposition, coverage, or satisfaction for you. "
                "Every top-level field and every nested field in FastPlannerMultiGoalPlanOutput is required. Use exact catalog capability IDs and schema-valid args. The verified tool-memory index contains no answer facts. When an exact fresh index entry matches every authoritative Goal binding, execute chromie.memory.retrieve_verified_tool_result with that evidence_id, original tool_id, and the same material arguments; never use a respond outcome directly from the index. If no exact fresh entry exists, execute the supplied fresh read capability. For a scheduled, running, or recoverable safe-read goal, reuse the bound capability and exact arguments and execute or retry it; never answer from another task's result. For an executable Goal, response_text is optional prospective conversational intent, not execution evidence. Use Interaction Context to leave it empty when an equivalent acknowledgement or commitment is already delivered or pending and nothing new needs saying. When there is a genuinely new acknowledgement, limitation, correction, confirmation need, or other conversational delta, author it naturally without predicting an external result or claiming execution/completion. A response_text never satisfies the executable Goal; post-execution factual claims require matching evidence. "
                f"{argument_grounding_contract}"
                f"{semantic_scope_contract}"
                f"{current_turn_communication_contract}"
                f"{IDENTITY_SEMANTIC_CONTRACT}"
                f"{PERSONALITY_SEMANTIC_CONTRACT}"
                f"{goal_execution_contract}"
                f"{concise_output_contract}"
                "Author stable non-empty step_id values, exact source_goal_ids, and matching outcome step_ids yourself. "
                "This is prospective planning: no action has executed yet. A planned step or response counts as satisfying its goal if it would succeed. For each keyed goal outcome, judge only that one goal; never put sibling goals or pending execution in unmet_goal_ids or unmet_requirements. Complete terminal outcomes use exact satisfaction with both unmet lists empty. "
                "Fast terminal scope permits at most one executable step per goal. A count argument performs repetition inside one skill call; never duplicate a step to implement repeated blinks, nods, or similar motions. Respond goals have no executable step. "
                "For a terminal plan, every per-goal outcome is execute or respond, coverage is complete, and the top-level disposition exactly aggregates the outcome dispositions. A respond outcome contains the actual answer now and references no steps. An execute outcome references every and only the model-authored steps owned by that goal. "
                "For semantic escalation, author disposition=escalate, coverage=partial or uncertain, steps=[], a non-empty top-level escalation_reason, and one escalate outcome for every canonical goal. Each escalate outcome must explain its own unresolved need, reference no steps, carry no response_text, and include a non-exact prospective satisfaction judgment. Do not mix escalation outcomes with executable or response outcomes. "
                "goal_satisfaction and every per-goal satisfaction are model judgments about prospective plan adequacy. A score from 0.95 through 1.0 requires status=exact. Escalation cannot claim exact satisfaction. "
                "Generic response transport is not a task-plan step, so chromie.speak is never a plan step. Do not replace a conversational answer with a gesture or attention action. "
                "Use plan_relation=exact unless the plan materially changes the request; safe_adjustment or alternative requires user_confirmation_required=true and explanatory response_text. "
                "The host adds only plan_id, planner_tier, schema_version, and the authoritative top-level goal_ids after validating your output. It does not compile semantic decisions or generate step ownership. Return JSON only.\n\n"
                f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
                f"FINAL CANONICAL GOALS JSON:\n{self._bounded(grounding, 4500)}\n\n"
                f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 2500)}\n\n"
                "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
                f"{validation_errors or '[]'}\n"
                "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently."
            )
        return (
            f"Goal association advisory JSON:\n{self._bounded(association, 3000)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Executable common capability catalog JSON:\n{self._bounded(capabilities, 9000)}\n\n"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{self._bounded(situation_prompt_projection(context), 3600)}\n\n"
            f"{goal_progress_communication_prompt('Fast Planner')}\n\n"
                f"Goal-scoped Interaction Context JSON:\n{self._bounded(context.get('interaction_context') or {}, 7000)}\n\n"
            "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
            f"Previous Fast Planner output when doing a mechanical DTO regeneration:\n{self._bounded(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
            "When validation errors are present and the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and every listed defect. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
            "Decide whether the executable common catalog completely covers every independent responsibility in the current user turn. A verified tool-memory index entry is only metadata that an exact prior result may be retrievable; it is never answer evidence. After Goal Association has fixed all material bindings, select chromie.memory.retrieve_verified_tool_result only when one index entry exactly matches the required tool_id and material arguments and is fresh enough for the user request. Otherwise select the fresh read capability. A status follow-up for a scheduled, running, or recoverable safe read must resume or retry the bound skill with its exact arguments when no matching completed memory entry exists. Never invent weather, temperature, status, price, schedule, or another external result from model memory or from index metadata. "
            "There are exactly two legal output shapes for one or many goals. A terminal plan uses coverage=complete, a goal_outcomes entry keyed exactly once by every canonical Goal ID, and non-null prospective satisfaction. A semantic escalation uses disposition=escalate, coverage=partial or uncertain, steps=[], one escalate outcome for every canonical Goal ID, non-exact prospective satisfaction, and a specific non-empty escalation_reason. "
            "Finding one matching capability is not complete coverage. If any responsibility, parameter, ordering, concurrency relation, safety judgment, or capability is unresolved, use the complete model-authored semantic-escalation shape; never return an empty outcome map or null satisfaction. "
            "Fast Planner may emit disposition=mixed only for a completely covered simple combination of common unlocked execute goals and direct conversational respond goals. A mixed plan requires at least one execute outcome, at least one respond outcome, complete per-goal satisfaction, and exact step ownership. "
            "For complete direct execution, use exact supplied capability IDs and schema-valid args. "
            f"{argument_grounding_contract}"
            f"{semantic_scope_contract}"
            f"{current_turn_communication_contract}"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            f"{goal_execution_contract}"
            f"{concise_output_contract}"
            "Generic speech transport is not a plan step. A canonical Goal with responsibility_kind=vocal_output, output_mode=speech, and provider_required=false is a direct conversational responsibility: use disposition=respond with the actual response_text now. Executable outcomes may also carry response_text when it is a still-needed prospective conversational delta; use Interaction Context to omit equivalent delivered or pending speech, and never treat that text as execution evidence. A vocal_output Goal with provider_required=true is a mode-specific vocal performance and cannot be completed by response_text, chromie.speak, ordinary TTS, media playback, or a body gesture. Execute that Goal only when the supplied catalog contains exact capability_id chromie.vocal.perform and its mode enum contains the authoritative Goal output_mode; copy that exact mode and authored content into one owned step. Otherwise escalate for an exact unavailable, refused, or clarification outcome; never invent a vocal capability ID or silently choose another mode. A canonical executable_action/activity/media_playback Goal uses exactly one `chromie.media.<media_operation>` capability copied from the qualified catalog. Playback of existing music, recordings, streams, or sound effects is never a Vocal Goal and never evidence for singing. Preserve persistent playback_id controls and do not replace play, pause, resume, seek, stop, volume, or status with another operation. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
            "Every executable step must use capability_id plus source_goal_ids copied from the canonical goals. Do not use catalog-only parameters, action, input_schema, route, or step_type fields. "
            "goal_satisfaction measures prospective plan adequacy: planned steps count as satisfying their goals if successful, so pending execution alone is never an unmet requirement. A score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. If steps are present, top-level disposition cannot be respond. "
            "For every terminal or escalation result, goal_outcomes must be keyed exactly once by every supplied canonical Goal ID. Each execute outcome needs its real step_ids; each respond outcome needs non-empty response_text and step_ids=[]; each escalation outcome needs its unresolved reason and non-exact satisfaction. "
            "Valid examples: execute uses owned steps and execute outcomes; mixed uses owned steps plus respond outcomes; escalation uses steps=[], one escalate outcome per Goal, and non-null non-exact goal_satisfaction. "
            "Use plan_relation=exact for an exact plan. A safe_adjustment or alternative must set user_confirmation_required=true so the host holds execution for approval. "
            "The Ollama decoder enforces the exact flat FastPlannerModelOutput schema out-of-band. "
            "The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. "
            "Return JSON only. The final grounding below is authoritative and overrides previous output or advisory text.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANONICAL GOALS JSON:\n{self._bounded(grounding, 4500)}\n\n"
            f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 2500)}\n\n"
            "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
            f"{validation_errors or '[]'}\n"
            "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently."
        )

    def _advance_layered_prompt(
        self,
        request: CognitiveWorkRequest,
        *,
        responsibilities: list[CognitiveResponsibilityProposal],
        capabilities: list[dict[str, Any]],
        validation_errors: str = "",
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        advance_contract = (
            "Responsibility evidence is authoritative contextual WHAT. Fast Planner owns "
            "the first complete HOW decision over that evidence: speaking and Capability "
            "Activities plus their sequential/parallel timing. Goal Association runs at "
            "the same time from the same GI result and alone commits Canonical Goal state. "
            "A speaking Activity is a Communicative Act: select its function and semantic "
            "provenance, never its sentence wording. Response Composer owns language "
            "formulation and Trusted Capability Runtime alone authorizes execution."
        )
        responsibilities_json = self._bounded(
            [item.model_dump(mode="json", exclude_none=True) for item in responsibilities],
            2200,
        )
        active_goals = self._bounded(context.get("active_goal_snapshots") or [], 600)
        interaction_context = self._bounded(
            context.get("interaction_context") or {},
            1200,
        )
        capability_json = json.dumps(
            self._advance_capability_prompt_projection(capabilities),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        user_text = " ".join(str(request.text or "").split())[:700]
        rendered = (
            advance_contract
            + "\n\nCurrent user turn:\n"
            + user_text
            + "\nLanguage hint: "
            + str(request.language or "auto")[:32]
            + "\n\nAuthoritative Responsibility evidence from Goal Interpretation:\n"
            + responsibilities_json
            + "\n\nGI unresolved-meaning evidence (exact strings or empty):\n"
            + self._bounded(request.interpretation_unresolved, 1200)
            + "\n\nActive Goal continuity summary only:\n"
            + active_goals
            + "\n\nAlready-spoken/pending interaction summary only:\n"
            + interaction_context
            + "\n\nExecutable common Capability catalog JSON:\n"
            + capability_json
            + "\n\nThe catalog projection above is complete for this Fast decision; every "
            "allowed Capability has a visible capability_id, arguments, effects, and "
            "semantic scope. Compare the Responsibility outcome against all projected "
            "descriptions, when_to_use guidance, effects, semantic_type, and semantic_scope "
            "before claiming that no Capability matches. The absence of fresh result "
            "Evidence is the reason to execute a matching read Capability, never a reason "
            "to clarify. Match required arguments from GI bindings by meaning, not only by "
            "identical field name; a clearly supplied named entity, relative date, or local "
            "day part is resolved input. Optional arguments with schema defaults are not "
            "missing inputs. When one matching Capability has every required input, use "
            "disposition=execute, coverage=complete, continuations=[], unresolved=[], and "
            "emit its schema-valid Capability Activity. For an external information read, "
            "use progress_kind=check_information with speech_act=acknowledge_and_check when "
            "a short concurrent progress act helps.\n\nCover every Responsibility ref exactly. Activities are one ordered list. "
            "Speaking is an Activity and uses the same timing field as Capability work. "
            "Use parallel only when activities can genuinely overlap without a declared "
            "resource or safety conflict; list dependent work sequentially. A progress "
            "Activity is bounded and has progress_kind rather than response_text. No "
            "Communicative Act may contain response_text or other sentence wording. A "
            "complete_response Activity may satisfy only ordinary conversation that needs "
            "no fresh Evidence. You own execution-input completeness and planning "
            "InformationGaps. Before asking, consider authoritative context, applicable "
            "trusted observation/query, owner preference, Capability schema default, and "
            "a safe consequence-bounded default. Ask only when the user can resolve a "
            "material blocker and no safer authorized source/default is enough. A "
            "clarification must create its typed InformationGap: source_kind="
            "unresolved_meaning cites one exact interpretation_unresolved string; "
            "source_kind=execution_input cites the exact selected Capability ID in "
            "source_reference and names only its genuinely absent required input keys in "
            "required_for. Record every examined source in resolution_sources_considered. "
            "Use disposition=clarify when only clarification remains; use mixed only when "
            "independent safe Capability work also proceeds. Never ask the user for an "
            "external result Chromie was asked to obtain. Do not route a missing user "
            "parameter to Deep Planner. GI bindings are resolved input evidence, including "
            "relative dates and local day parts normalized into canonical values. Never "
            "treat an already supplied binding as ambiguous merely because its value is "
            "relative to the current turn; when GI unresolved-meaning evidence is empty, "
            "do not invent a semantic clarification. When all required "
            "bindings are present and one exact available Capability covers the work, emit "
            "its exact capability_id and schema-valid args now. Select a Capability only "
            "when its description, effects, and projected semantic_scope directly match the "
            "Responsibility's observable outcome. A read-only information request must use "
            "an information-read Capability when one is supplied; physical-object acquisition, "
            "handover, body gestures, or attention motions cannot acquire external information. "
            "Do not add decorative Capability Activities that the Responsibility did not ask "
            "for. Preserve every GI binding, "
            "including all independent temporal dimensions. Add a progress speaking "
            "Activity in parallel only when it helps the interaction and does not claim a "
            "result. Use disposition=escalate and continuation=deep_planner only when HOW "
            "itself exceeds the Fast planning budget; emit no Capability Activities in "
            "that case. Goal Association is always concurrent and is never a continuation. "
            "Never claim execution or external results before Evidence.\n\n"
            "Validation errors from the prior Fast Plan, if any:\n"
            + (validation_errors or "[]")
            + "\nReturn one fresh complete schema-constrained JSON object only."
        )
        return LayeredPrompt.promote(
            rendered,
            operating_contract=(advance_contract,),
        )

    @staticmethod
    def _advance_capability_prompt_projection(
        capabilities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep every bounded catalog choice visible without slicing JSON mid-item."""

        projected: list[dict[str, Any]] = []
        for capability in capabilities:
            input_schema = capability.get("input_schema") or {}
            properties = input_schema.get("properties") or {}
            required = {
                str(item) for item in (input_schema.get("required") or [])
            }
            arguments: list[dict[str, Any]] = []
            for name, raw_schema in properties.items():
                if not isinstance(raw_schema, dict):
                    continue
                argument: dict[str, Any] = {
                    "name": str(name),
                    "required": str(name) in required,
                }
                for key in (
                    "type",
                    "enum",
                    "const",
                    "default",
                    "minimum",
                    "maximum",
                    "minLength",
                    "maxLength",
                ):
                    if key in raw_schema:
                        value = raw_schema[key]
                        argument[key] = value[:12] if isinstance(value, list) else value
                arguments.append(argument)

            hints = capability.get("hints") or {}
            semantic_scope = hints.get("semantic_scope") or {}
            bounded_scope = {
                key: value[:12] if isinstance(value, list) else value
                for key in (
                    "responsibility_type",
                    "resource_kinds",
                    "delivery_modes",
                    "domain",
                    "acquisition",
                    "supported_temporal_scopes",
                    "unsupported_temporal_scopes",
                )
                if (value := semantic_scope.get(key)) not in (None, "", [])
            }
            resource_contract = hints.get("resource_contract") or {}
            bounded_resource_contract = {
                key: value[:12] if isinstance(value, list) else value
                for key in (
                    "provider_role",
                    "plan_requires",
                    "plan_provides",
                    "completion_requires",
                )
                if (value := resource_contract.get(key)) not in (None, "", [])
            }
            projected.append(
                {
                    "capability_id": str(capability.get("capability_id") or ""),
                    "description": str(capability.get("description") or "")[:360],
                    "arguments": arguments,
                    "requires_confirmation": bool(
                        capability.get("requires_confirmation")
                    ),
                    "can_run_parallel": bool(capability.get("can_run_parallel")),
                    "parallel_metadata_declared": bool(
                        capability.get("parallel_metadata_declared")
                    ),
                    "resource_claims": list(
                        capability.get("resource_claims") or []
                    )[:12],
                    "effects": list(capability.get("effects") or [])[:12],
                    "safety_class": str(capability.get("safety_class") or ""),
                    "side_effect_free": bool(capability.get("side_effect_free")),
                    "when_to_use": str(hints.get("when_to_use") or "")[:360],
                    "semantic_type": str(hints.get("semantic_type") or ""),
                    "semantic_scope": bounded_scope,
                    "resource_contract": bounded_resource_contract,
                }
            )
        return projected

    @staticmethod
    def _advance_system_prompt() -> str:
        return (
            "You are Chromie's low-latency Fast Planner. Accept Goal Interpretation's "
            "Responsibility evidence as authoritative contextual WHAT. Produce the first "
            "Activity Plan, including speaking and exact available Capability Activities. "
            "Speaking Activities are Communicative Acts: select their function, timing, "
            "and Responsibility/InformationGap provenance, but never author sentence "
            "wording; speech_act is a closed communicative-function enum, not a text "
            "escape hatch. Ask through a clarification act when a required user-resolvable "
            "binding is genuinely absent after checking GI bindings and Capability defaults; "
            "never reinterpret a present normalized binding as missing or ambiguous. Select "
            "only a Capability whose declared description, effects, and semantic scope match "
            "the requested outcome; information reads are not physical-object delivery or "
            "decorative body motion. Delegate only genuinely complex HOW to Deep Planner. Goal "
            "Association separately owns Canonical Goal commits, and Trusted Capability "
            "Runtime owns execution authority. Response Composer owns language formulation. "
            "Return only schema-constrained JSON."
        )

    def _layered_prompt(
        self,
        request: CognitiveWorkRequest,
        capabilities: list[dict[str, Any]],
        *,
        response_schema: dict[str, Any],
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        identity_world = (
            "Owner-approved Chromie identity JSON:\n"
            f"{bounded_identity_json(context)}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{bounded_personality_json(context)}\n\n"
        )
        capability_contract = (
            agent_skill_prompt_section(context, agent_role="fast_planner")
            + "Executable common capability catalog JSON:\n"
            + self._bounded(capabilities, 9000)
            + "\n\n"
        )
        rendered = self._prompt(
            request,
            capabilities,
            response_schema=response_schema,
            previous_raw=previous_raw,
            validation_errors=validation_errors,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
                EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
            ),
            capability_contract=(capability_contract,),
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Fast Planner. Plan only the final authoritative user turn and canonical goals at the end of the prompt. "
            "Author the semantic plan from the goals and executable catalog; never use phrase-to-action rules and never delegate semantic planning to the host. "
            "A verified-memory index is provenance only, never answer evidence. For a retained completed external-result Goal, a direct response may use only supplied delivered evidence-bound dialogue: preserve every measurement and condition exactly and omit unsupported embellishment. If that dialogue is absent, retrieve matching verified evidence, perform a fresh read, or escalate. "
            "Produce a complete simple response, common-skill plan, or simple execute-plus-respond mixed plan only when every responsibility is covered; otherwise author a complete per-goal semantic escalation. "
            "Do not execute, authorize, or claim completion. Return JSON only."
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You regenerate one fresh Fast Planner output using the supplied authoritative goals, executable capability catalog, complete validation errors, and schema-constrained decoder. "
            "Validation errors describe defects in the prior plan object; they are not evidence that execution occurred, that the user request became uncertain, or that a catalog capability needs confirmation. Preserve the authoritative user meaning and catalog facts while correcting every defect. "
            "Rebuild every required model-authored plan field instead of editing or splicing invalid JSON. Do not rely on host-generated steps, ownership, outcomes, disposition, or satisfaction. Return JSON only."
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
