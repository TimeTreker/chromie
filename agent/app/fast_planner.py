from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, AsyncIterator

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
    fast_streaming_advance_response_schema,
)
from .planner_context import (
    auxiliary_social_capability_payloads,
    auxiliary_social_prompt_context,
    fast_capability_payload,
    planner_effectful_goal_ids,
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
    capability_argument_errors,
    qualify_fast_canonical_plan,
    validate_fast_advance_output,
    validate_work_reuse_selection,
)
from .planner_fallback import materialize_fast_escalation
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
        FastPlannerPresentationCommitModelOutput,
        FastPlannerStreamingModelOutput,
        FastPlannerStreamFailure,
        FastPlannerStreamFrame,
        FastPlannerStreamTerminal,
        PresentationCommit,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerPresentationCommitModelOutput,
        FastPlannerStreamingModelOutput,
        FastPlannerStreamFailure,
        FastPlannerStreamFrame,
        FastPlannerStreamTerminal,
        PresentationCommit,
    )

from .planner_prompt import (
    fast_advance_layered_prompt,
    fast_streaming_advance_system_prompt,
    fast_layered_prompt,
    fast_system_prompt,
)


logger = logging.getLogger("chromie.agent.fast_planner")

PRESENTATION_COMMIT_OPEN = "<presentation_commit>"
PRESENTATION_COMMIT_CLOSE = "</presentation_commit>"
TERMINAL_PLAN_OPEN = "<terminal_plan>"
TERMINAL_PLAN_CLOSE = "</terminal_plan>"

def presentation_commit_id(request: CognitiveWorkRequest) -> str:
    responsibility_refs = "|".join(
        str(item.local_ref) for item in request.responsibilities
    )
    digest = hashlib.sha256(
        f"{request.sid}|{responsibility_refs}|presentation".encode("utf-8")
    ).hexdigest()[:20]
    return f"present_{digest}"


def _tagged_json_frame(
    buffer: str,
    *,
    open_tag: str,
    close_tag: str,
    frame_name: str,
    start: int = 0,
    final: bool = False,
) -> tuple[dict[str, Any], int] | None:
    """Parse one closed tagged JSON object without interpreting its semantics."""

    index = start
    while index < len(buffer) and buffer[index].isspace():
        index += 1
    available = buffer[index:]
    if not available:
        if final:
            raise PlannerDTOContractError(
                f"Fast Planner stream is missing <{frame_name}>"
            )
        return None
    if not available.startswith(open_tag):
        if not final and open_tag.startswith(available):
            return None
        raise PlannerDTOContractError(
            f"Fast Planner stream must emit {open_tag} at this boundary"
        )

    payload_start = index + len(open_tag)
    search_start = payload_start
    saw_close = False
    while True:
        payload_end = buffer.find(close_tag, search_start)
        if payload_end < 0:
            break
        saw_close = True
        candidate = buffer[payload_start:payload_end].strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            # A literal closing tag may occur inside a JSON string. Keep looking
            # for the real frame boundary instead of committing a partial value.
            search_start = payload_end + 1
            continue
        if not isinstance(value, dict):
            if final:
                raise PlannerDTOContractError(
                    f"Fast Planner {frame_name} payload must be a JSON object"
                )
            search_start = payload_end + 1
            continue
        return value, payload_end + len(close_tag)

    if final:
        detail = "contains invalid JSON" if saw_close else "is not closed"
        raise PlannerDTOContractError(
            f"Fast Planner {frame_name} frame {detail}"
        )
    return None


def first_presentation_frame(buffer: str) -> dict[str, Any] | None:
    """Return the first closed presentation payload, or None while incomplete."""

    parsed = _tagged_json_frame(
        buffer,
        open_tag=PRESENTATION_COMMIT_OPEN,
        close_tag=PRESENTATION_COMMIT_CLOSE,
        frame_name="presentation_commit",
    )
    return parsed[0] if parsed is not None else None


def parse_fast_stream_document(
    buffer: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the exact two-frame wire document after provider completion."""

    presentation = _tagged_json_frame(
        buffer,
        open_tag=PRESENTATION_COMMIT_OPEN,
        close_tag=PRESENTATION_COMMIT_CLOSE,
        frame_name="presentation_commit",
        final=True,
    )
    if presentation is None:  # defensive; final=True raises on incompleteness
        raise PlannerDTOContractError(
            "Fast Planner stream is missing <presentation_commit>"
        )
    terminal = _tagged_json_frame(
        buffer,
        open_tag=TERMINAL_PLAN_OPEN,
        close_tag=TERMINAL_PLAN_CLOSE,
        frame_name="terminal_plan",
        start=presentation[1],
        final=True,
    )
    if terminal is None:  # defensive; final=True raises on incompleteness
        raise PlannerDTOContractError(
            "Fast Planner stream is missing <terminal_plan>"
        )
    if buffer[terminal[1] :].strip():
        raise PlannerDTOContractError(
            "Fast Planner stream added content after </terminal_plan>"
        )
    return presentation[0], terminal[0]


def project_presentation_schema_constants(
    raw: dict[str, Any],
    *,
    responsibility_refs: list[str],
) -> dict[str, Any]:
    """Restore only constants intentionally elided by the compact wire Schema."""

    payload = dict(raw)
    raw_activity = payload.get("activity")
    if not isinstance(raw_activity, dict):
        return payload
    activity = dict(raw_activity)
    if len(responsibility_refs) == 1:
        activity.setdefault("source_responsibility_refs", responsibility_refs)
    activity.setdefault(
        "role",
        (
            "progress"
            if activity.get("progress_kind") not in (None, "")
            else "complete_response"
        ),
    )
    payload["activity"] = activity
    return payload

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
        self,
        request: CognitiveWorkRequest,
    ) -> AsyncIterator[FastPlannerStreamFrame]:
        """Stream one Fast Planner result through an immutable typed commit."""

        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(
                item.model_dump(mode="json")
            )
            for item in request.responsibilities
        ]
        responsibility_refs = [item.local_ref for item in responsibilities]
        turn_id = str(request.sid or "turn-fast-stream")
        commit_id = presentation_commit_id(request)
        commit: PresentationCommit | None = None
        raw_text = ""
        capabilities = await self.catalog.prompt_entries(
            scope="common", refresh=False
        )
        auxiliary_catalog = await self.catalog.prompt_entries(
            scope="all", refresh=False
        )
        auxiliary_social_capabilities = auxiliary_social_capability_payloads(
            auxiliary_catalog
        )
        request.context["planner_auxiliary_social_context"] = (
            auxiliary_social_prompt_context(
                request.context,
                auxiliary_social_capabilities,
            )
        )
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
        response_schema = fast_streaming_advance_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            capabilities=capability_payload,
            auxiliary_social_capabilities=auxiliary_social_capabilities,
            interpretation_unresolved=list(request.interpretation_unresolved),
            language=str(request.language or ""),
        )
        if request.interpretation_unresolved:
            presentation_schema = response_schema["properties"][
                "presentation_commit"
            ]
            presentation_schema["properties"]["activity"] = {"type": "null"}
            presentation_schema["properties"]["auxiliary_activities"] = {
                "type": "array",
                "maxItems": 0,
            }
        prompt = fast_advance_layered_prompt(
            request,
            responsibilities=responsibilities,
            capabilities=capability_payload,
            response_schema=response_schema,
        )
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": min(self.num_predict, 2048),
        }
        try:
            async for delta in self.ollama.generate_stream(
                prompt,
                system=fast_streaming_advance_system_prompt(),
                options=options,
                response_format="text",
                prompt_family="fast_planner.streaming_advance",
                turn_id=request.sid,
                attempt=1,
            ):
                raw_text += delta
                if commit is not None:
                    continue
                raw_presentation = first_presentation_frame(raw_text)
                if raw_presentation is None:
                    continue
                projected_presentation = project_presentation_schema_constants(
                    raw_presentation,
                    responsibility_refs=responsibility_refs,
                )
                presentation = (
                    FastPlannerPresentationCommitModelOutput.model_validate(
                        projected_presentation
                    )
                )
                activity = presentation.activity
                if activity is not None:
                    refs = set(activity.source_responsibility_refs)
                    if not refs or not refs.issubset(set(responsibility_refs)):
                        raise PlannerDTOContractError(
                            "PresentationCommit must cite supplied Responsibility refs"
                        )
                    if activity.role == "complete_response":
                        modes_by_ref = {
                            item.local_ref: item.output_mode
                            for item in responsibilities
                        }
                        if any(modes_by_ref.get(ref) != "speech" for ref in refs):
                            raise PlannerDTOContractError(
                                "PresentationCommit completion is valid only for direct "
                                "speech Responsibilities cited by that Activity"
                            )
                commit = PresentationCommit(
                    commit_id=commit_id,
                    turn_id=turn_id,
                    activity=activity,
                    auxiliary_activities=presentation.auxiliary_activities,
                    metadata={
                        "semantic_authority": "fast_planner_model",
                        "phase": "streaming_presentation_commit",
                        "execution_authority": (
                            "host_communicative_runtime"
                            if activity is not None
                            else "none"
                        ),
                        "semantic_result_call_count": 1,
                    },
                )
                yield commit

            if commit is None:
                raise PlannerDTOContractError(
                    "Fast Planner stream ended before a typed PresentationCommit"
                )
            raw_presentation, raw_terminal = parse_fast_stream_document(raw_text)
            projected_presentation = project_presentation_schema_constants(
                raw_presentation,
                responsibility_refs=responsibility_refs,
            )
            output = FastPlannerStreamingModelOutput.model_validate(
                {
                    "presentation_commit": projected_presentation,
                    "terminal_result": raw_terminal,
                }
            )
            if output.presentation_commit != FastPlannerPresentationCommitModelOutput(
                activity=commit.activity,
                auxiliary_activities=commit.auxiliary_activities,
            ):
                raise PlannerDTOContractError(
                    "Fast Planner terminal result changed PresentationCommit"
                )
            if any(
                item.role == "progress"
                for item in output.terminal_result.activities
            ):
                raise PlannerDTOContractError(
                    "Fast Planner terminal result cannot author a second progress Act"
                )
            committed_completion_refs = (
                set(commit.activity.source_responsibility_refs)
                if commit.activity is not None
                and commit.activity.role == "complete_response"
                else set()
            )
            duplicate_completion_refs = {
                source_ref
                for item in output.terminal_result.activities
                if item.role == "complete_response"
                for source_ref in item.source_responsibility_refs
                if source_ref in committed_completion_refs
            }
            if duplicate_completion_refs:
                raise PlannerDTOContractError(
                    "Fast Planner terminal result duplicated presentation speech "
                    "ownership for Responsibilities: "
                    + ",".join(sorted(duplicate_completion_refs))
                )
            combined_output = output.terminal_result.model_copy(
                update={
                    "activities": [
                        *([commit.activity] if commit.activity is not None else []),
                        *output.terminal_result.activities,
                    ],
                    "auxiliary_activities": [
                        *commit.auxiliary_activities,
                        *output.terminal_result.auxiliary_activities,
                    ],
                }
            )
            validate_fast_advance_output(
                combined_output,
                request=request,
                responsibilities=responsibilities,
                capabilities=capability_payload,
            )
            advance = FastPlannerAdvance(
                turn_id=turn_id,
                disposition=combined_output.disposition,
                coverage=combined_output.coverage,
                covered_responsibility_refs=(
                    combined_output.covered_responsibility_refs
                ),
                activities=combined_output.activities,
                auxiliary_activities=combined_output.auxiliary_activities,
                continuations=combined_output.continuations,
                confidence=combined_output.confidence,
                unresolved=combined_output.unresolved,
                reason_summary=combined_output.reason_summary,
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "streaming_responsibility_activity_plan",
                    "presentation_commit_id": commit.commit_id,
                    "execution_authority": "trusted_capability_runtime",
                    "semantic_result_call_count": 1,
                },
            )
            yield FastPlannerStreamTerminal(
                turn_id=turn_id,
                presentation_commit_id=commit.commit_id,
                advance=advance,
            )
        except Exception as exc:
            failure = (
                llm_failure_metadata(exc)
                if isinstance(exc, OllamaGenerationError)
                else {
                    "failure_class": "fast_stream_contract_invalid",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "not_evaluated",
                    "retryable": False,
                }
            )
            logger.warning(
                "fast_planner_stream_fail_closed sid=%s stage=%s error_type=%s "
                "error=%s failure_class=%s",
                request.sid,
                "after_commit" if commit is not None else "before_commit",
                type(exc).__name__,
                exc,
                failure["failure_class"],
            )
            yield FastPlannerStreamFailure(
                turn_id=turn_id,
                failure_stage=(
                    "after_commit" if commit is not None else "before_commit"
                ),
                presentation_commit_id=(commit.commit_id if commit else None),
                failure_class=str(failure["failure_class"]),
                failure_domain=str(failure["failure_domain"]),
                architecture_attribution=str(
                    failure.get("architecture_attribution") or "not_evaluated"
                ),
                retryable=bool(failure.get("retryable")),
                error_type=type(exc).__name__,
                reason=str(exc)[:500],
            )

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
        auxiliary_catalog = await self.catalog.prompt_entries(scope="all", refresh=False)
        auxiliary_social_capabilities = auxiliary_social_capability_payloads(
            auxiliary_catalog
        )
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
                auxiliary_social_capabilities=auxiliary_social_capabilities,
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
                effectful_goal_ids=list(
                    planner_effectful_goal_ids(authoritative_goals)
                ),
                confirmation_required_capability_ids=[
                    item["capability_id"]
                    for item in capability_payload
                    if item.get("requires_confirmation")
                ],
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
                auxiliary_social_capabilities=auxiliary_social_capabilities,
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
                confirmation_required_capability_ids=[
                    item["capability_id"]
                    for item in capability_payload
                    if item.get("requires_confirmation")
                ],
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
        raw: Any = None
        parameter_provenance_repairs: list[dict[str, Any]] = []
        try:
                raw = await self.ollama.generate(
                    fast_layered_prompt(
                        request,
                        capability_payload,
                        response_schema=response_schema,
                    ),
                    system=fast_system_prompt(),
                    options=options,
                    response_format=response_schema,
                    prompt_family="fast_planner.primary",
                    turn_id=request.sid,
                    attempt=1,
                )
                if not isinstance(raw, dict):
                    raise ValueError("fast planner response is not a JSON object")
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
                    1,
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
                        if mechanical_contract_error
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
        if parameter_provenance_repairs:
            metadata = dict(validated.metadata)
            metadata["parameter_provenance_normalization"] = {
                "strategy": "project_mechanically_derivable_provenance",
                "repairs": parameter_provenance_repairs,
                "semantic_plan_unchanged": True,
            }
            validated = validated.model_copy(update={"metadata": metadata})
        return validated
