from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import hashlib
import json
import logging
import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .clients.ollama_client import LayeredPrompt, OllamaClient, llm_failure_metadata
from .agent_skills import agent_skill_prompt_section
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
)
from .planner_contract import (
    evidence_bound_dialogue,
    goal_association_prompt_projection,
)
try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.llm_diagnostics import cognition_text_reference
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from chromie_contracts.execution_lanes import LaneCoordinationGroup
    from chromie_contracts.goal import GoalAssociationResolution
    from chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerProgressAct,
    )
    from chromie_contracts.response_composition import (
        CommunicativeActRealization,
        CommunicativeActRealizationRequest,
        CommunicativeActWording,
        CoordinatedResponsePlan,
        DirectResponseComposition,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
        goal_association_fingerprint,
        realize_bounded_fast_progress_act,
    )
    from chromie_contracts.semantic_task import (
        ResponsePlan,
        ResponseStage,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from shared.chromie_contracts.execution_lanes import LaneCoordinationGroup
    from shared.chromie_contracts.goal import GoalAssociationResolution
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerProgressAct,
    )
    from shared.chromie_contracts.response_composition import (
        CommunicativeActRealization,
        CommunicativeActRealizationRequest,
        CommunicativeActWording,
        CoordinatedResponsePlan,
        DirectResponseComposition,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
        goal_association_fingerprint,
        realize_bounded_fast_progress_act,
    )
    from shared.chromie_contracts.semantic_task import (
        ResponsePlan,
        ResponseStage,
    )

logger = logging.getLogger("chromie.agent.response_composer")


class ResponseComposerModelOutput(BaseModel):
    """Small model-facing DTO; composition identity remains host-owned."""

    model_config = ConfigDict(extra="forbid")

    response_plan: ResponsePlan
    lane_coordination: list[LaneCoordinationGroup] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class CommunicativeActWordingModelOutput(BaseModel):
    """Wording-only model output for immutable Planner-selected acts."""

    model_config = ConfigDict(extra="forbid")

    wordings: list[CommunicativeActWording] = Field(min_length=1, max_length=16)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=800)




class ResponseComposerDTOContractError(ValueError):
    """Mechanical Response Composer representation failure eligible for one retransmission."""


class ResponseComposerSemanticValidationError(ValueError):
    """Consequential response meaning/truth failure; terminal for this composition."""


ResponseTruthViolation = Literal[
    "unsupported_reality_claim",
    "premature_effect_claim",
    "unsupported_completion_claim",
    "capability_overclaim",
    "unsupported_future_commitment",
    "confirmation_mismatch",
    "goal_scope_mismatch",
    "other_consequential_claim",
]


class ResponseTruthAudit(BaseModel):
    """Immutable proof certificate for consequential response wording.

    The audit never rewrites ResponsePlan or any upstream semantic object. The Host
    derives acceptance mechanically: an empty violations list accepts; any violation
    rejects the composition. Invalid audit output is terminal and is never repaired.
    """

    model_config = ConfigDict(extra="forbid")

    violations: list[ResponseTruthViolation] = Field(default_factory=list, max_length=8)
    reason_summary: str = Field(default="", max_length=800)


class ResponseComposerResolver:
    """Advisory composition of truthful user-facing response expression.

    Planner owns Communicative Act selection. This model owns exact wording and
    optional Vocal/Activity lane presentation around immutable Planner/Goal state.
    Social Attention is independent background cognition owned by
    SocialAttentionPlanner and is not part of this DTO.
    """

    TRACE_MODULE = TraceModule(
        name="agent.response_composer",
        component_type="response_composer",
        implementation="ResponseComposerResolver",
        schema_version=1,
    )

    def __init__(
        self, ollama: OllamaClient, *, num_ctx: int = 8192, num_predict: int = 1024
    ) -> None:
        self.ollama = ollama
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def realize_communicative_acts(
        self,
        request: CommunicativeActRealizationRequest,
    ) -> CommunicativeActRealization:
        """Formulate exact words without re-deciding the Planner's activities."""

        bounded_wordings: list[CommunicativeActWording] = []
        open_acts = []
        for act in request.acts:
            if isinstance(act, FastPlannerProgressAct):
                bounded_wordings.append(
                    CommunicativeActWording(
                        activity_id=act.activity_id,
                        text=realize_bounded_fast_progress_act(
                            act,
                            language=request.language,
                        ),
                    )
                )
            else:
                open_acts.append(act)

        model_wordings: list[CommunicativeActWording] = []
        if open_acts:
            schema = CommunicativeActWordingModelOutput.model_json_schema()
            ids = [act.activity_id for act in open_acts]
            wording_items = schema.get("properties", {}).get("wordings")
            item_ref = wording_items.get("items") if isinstance(wording_items, dict) else None
            if isinstance(item_ref, dict) and "$ref" in item_ref:
                definition = schema.get("$defs", {}).get(
                    str(item_ref["$ref"]).rsplit("/", 1)[-1]
                )
                activity_id = (
                    definition.get("properties", {}).get("activity_id")
                    if isinstance(definition, dict)
                    else None
                )
                if isinstance(activity_id, dict):
                    activity_id["enum"] = ids
            if isinstance(wording_items, dict):
                wording_items["minItems"] = len(ids)
                wording_items["maxItems"] = len(ids)
            previous_errors = ""
            for attempt in range(2):
                try:
                    raw = await self.ollama.generate(
                        self._communicative_act_wording_prompt(
                            request,
                            acts=open_acts,
                            validation_errors=previous_errors,
                        ),
                        system=self._communicative_act_wording_system_prompt(),
                        options={
                            "temperature": 0.2,
                            "top_p": 0.9,
                            "num_ctx": self.num_ctx,
                            "num_predict": min(self.num_predict, 768),
                        },
                        response_format=schema,
                        prompt_family=(
                            "response_composer.communicative_act_wording.revision"
                            if attempt
                            else "response_composer.communicative_act_wording"
                        ),
                        turn_id=request.turn_id,
                        attempt=attempt + 1,
                    )
                    output = CommunicativeActWordingModelOutput.model_validate(raw)
                    output_ids = [item.activity_id for item in output.wordings]
                    if set(output_ids) != set(ids) or len(output_ids) != len(ids):
                        raise ResponseComposerDTOContractError(
                            "wording output must cover every Communicative Act exactly once"
                        )
                    if any(
                        not self._wording_matches_language(
                            item.text,
                            request.language,
                        )
                        for item in output.wordings
                    ):
                        raise ResponseComposerDTOContractError(
                            "Communicative Act wording must use the interaction language"
                        )
                    model_wordings = list(output.wordings)
                    break
                except (ValidationError, ResponseComposerDTOContractError) as exc:
                    if attempt:
                        logger.warning(
                            "communicative_act_wording_unavailable turn_id=%s error_type=%s error=%s",
                            request.turn_id,
                            type(exc).__name__,
                            exc,
                        )
                        return CommunicativeActRealization(
                            status="model_unavailable",
                            turn_id=request.turn_id,
                            reason_summary=(
                                "Communicative Act wording failed its closed contract."
                            ),
                        )
                    previous_errors = json.dumps(
                        (
                            exc.errors(include_url=False)
                            if isinstance(exc, ValidationError)
                            else [{"type": type(exc).__name__, "message": str(exc)}]
                        ),
                        ensure_ascii=False,
                        default=str,
                    )[:3000]

        ordered_by_id = {
            item.activity_id: item for item in [*bounded_wordings, *model_wordings]
        }
        if set(ordered_by_id) != {item.activity_id for item in request.acts}:
            return CommunicativeActRealization(
                status="model_unavailable",
                turn_id=request.turn_id,
                reason_summary="Communicative Act realization was incomplete.",
            )
        return CommunicativeActRealization(
            status="resolved",
            turn_id=request.turn_id,
            wordings=[ordered_by_id[item.activity_id] for item in request.acts],
        )

    def _communicative_act_wording_prompt(
        self,
        request: CommunicativeActRealizationRequest,
        *,
        acts: list[Any],
        validation_errors: str,
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        responsibility_by_ref = {
            item.local_ref: item for item in request.responsibilities
        }
        projections = []
        for act in acts:
            projections.append(
                {
                    "activity_id": act.activity_id,
                    "role": act.role,
                    "speech_act": act.speech_act,
                    "timing": act.timing,
                    "source_responsibilities": [
                        responsibility_by_ref[ref].model_dump(
                            mode="json", exclude_none=True
                        )
                        for ref in act.source_responsibility_refs
                    ],
                    "information_gaps": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in getattr(act, "information_gaps", [])
                    ],
                }
            )
        identity_world = (
            "Owner-approved Chromie identity JSON:\n"
            f"{bounded_identity_json(context)}\n\n"
            "Owner-approved Personality Expression JSON:\n"
            f"{bounded_personality_json(context)}\n\n"
        )
        operating_contract = (
            "Planner has already selected every Communicative Act. Formulate only "
            "the exact surface sentence for each activity_id. Do not add, remove, "
            "merge, split, reorder, suppress, or reinterpret an act. Do not choose "
            "Capabilities, promise execution, claim external Evidence, change a Goal, "
            "or answer a clarification gap on the user's behalf. A complete_response "
            "may use only its supplied Responsibility and ordinary non-fresh reasoning. "
            "A clarification must ask naturally for exactly the missing values in its "
            "Planner-owned InformationGap records; source provenance is explanatory and "
            "must not leak into the question. Preserve the requested language and "
            "Chromie's approved voice."
        )
        rendered = (
            identity_world
            + operating_contract
            + IDENTITY_SEMANTIC_CONTRACT
            + PERSONALITY_SEMANTIC_CONTRACT
            + "\n\nLanguage hint:\n"
            + request.language
            + "\n\nImmutable Communicative Acts JSON:\n"
            + self._bounded(projections, 5200)
            + "\n\nBounded Interaction Context for continuity only:\n"
            + self._bounded(context.get("interaction_context") or {}, 1800)
            + "\n\nMechanical validation errors from the previous wording DTO:\n"
            + (validation_errors or "[]")
            + "\nReturn exactly one wording for every supplied activity_id as JSON only."
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                operating_contract,
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
            ),
        )

    @staticmethod
    def _communicative_act_wording_system_prompt() -> str:
        return (
            "You are Chromie's language-formulation function inside Response Composer. "
            "Planner owns whether to communicate and the function of each Communicative "
            "Act. You own only exact wording for those immutable acts. Return the closed "
            "schema JSON and no extra text."
        )

    @staticmethod
    def _wording_matches_language(text: str, language: str | None) -> bool:
        normalized_language = str(language or "").strip().casefold()
        if not normalized_language or normalized_language == "auto":
            return True
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text or "")
        if normalized_language.startswith("zh"):
            return has_cjk
        if normalized_language.startswith("en"):
            return not has_cjk
        return True

    async def resolve(self, request: CognitiveWorkRequest) -> ResponseCompositionResolution:
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
                    },
                ) as span:
                    result = await self._resolve(request)
                    span.set_attribute("result_status", result.status)
                    span.set_attribute("composition_available", result.composition is not None)
                    if result.status != "resolved":
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: CognitiveWorkRequest) -> ResponseCompositionResolution:
        plan = self._canonical_plan(request.context)
        if plan is None:
            direct_association = self._direct_goal_association(request.context)
            if direct_association is not None:
                return await self._resolve_direct(request, direct_association)
        if plan is None or plan.disposition == "escalate":
            return ResponseCompositionResolution(
                status="invalid_input",
                reason_summary="A terminal CanonicalPlan is required before response composition.",
                metadata={"authority": "advisory", "resolver": "response_composer"},
            )
        composition_id = self._composition_id(request, plan)
        delivered_turn_speech = self._delivered_turn_speech(request.context)
        pure_safe_read = (
            plan.disposition == "execute"
            and self._is_safe_read_plan(plan, request.context)
            and not self._confirmation_required(plan, request.context)
        )
        response_schema = self._response_schema(plan, request.context)
        previous_raw: Any = None
        initial_validation_errors = ""
        dto_regeneration_attempted = False
        response_truth_audit: ResponseTruthAudit | None = None
        response_truth_audit_attempted = False
        for attempt in range(2):
            raw: Any = None
            try:
                raw = await self.ollama.generate(
                    self._layered_prompt(
                        request,
                        plan,
                        previous_raw=previous_raw,
                        validation_errors=initial_validation_errors,
                    ),
                    system=(
                        self._dto_regeneration_system_prompt()
                        if dto_regeneration_attempted
                        else self._system_prompt()
                    ),
                    options={
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                    response_format=response_schema,
                    prompt_family=(
                        "response_composer.dto_regeneration"
                        if dto_regeneration_attempted
                        else "response_composer.primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ResponseComposerDTOContractError("response composer output is not a JSON object")
                raw = self._canonicalize_lane_coordination_payload(raw, plan=plan)
                raw = self._strip_model_authored_goal_coverage(raw)
                model_output = ResponseComposerModelOutput.model_validate(raw)
                if pure_safe_read:
                    # Pure safe-read presentation has no new pre-evidence semantic
                    # responsibility. Preserve only an already-scheduled Fast act;
                    # otherwise suppress model-authored speech mechanically.
                    model_output.response_plan = self._pure_safe_read_response_plan(
                        plan=plan,
                        context=request.context,
                    )
                projected_response_plan, coverage_projection_reasons = (
                    self._project_goal_coverage(
                        model_output.response_plan,
                        plan=plan,
                        context=request.context,
                    )
                )
                model_output = model_output.model_copy(
                    update={"response_plan": projected_response_plan}
                )
                self._validate_safe_read_acknowledgement(
                    model_output.response_plan,
                    plan=plan,
                    context=request.context,
                    language=request.language,
                )
                self._validate_pending_response_contract(
                    model_output.response_plan,
                    plan=plan,
                    context=request.context,
                )
                self._validate_reused_turn_speech(
                    model_output.response_plan,
                    context=request.context,
                    plan=plan,
                )
                self._validate_spoken_language(
                    model_output.response_plan,
                    request=request,
                )
                if self._requires_response_truth_audit(
                    plan, request.context, pure_safe_read=pure_safe_read
                ):
                    response_truth_audit_attempted = True
                    response_truth_audit = await self._run_response_truth_audit(
                        request=request,
                        plan=plan,
                        candidate=model_output,
                    )
                    if response_truth_audit.violations:
                        raise ResponseComposerSemanticValidationError(
                            "response truth audit rejected consequential wording: "
                            + ",".join(response_truth_audit.violations)
                        )
                response_plan, lane_coordination, lane_reasons = self._reconcile_lane_coordination(
                    response_plan=model_output.response_plan,
                    lane_coordination=model_output.lane_coordination,
                    plan=plan,
                )
                composition = CoordinatedResponsePlan(
                    composition_id=composition_id,
                    canonical_plan_id=plan.plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
                    canonical_plan=plan,
                    response_plan=response_plan,
                    lane_coordination=lane_coordination,
                    confidence=model_output.confidence,
                    rationale=model_output.rationale,
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "task_plan_immutable": True,
                        "lane_coordination_validation_reasons": lane_reasons,
                        "goal_coverage_projection_reasons": coverage_projection_reasons,
                        "contract_schema": "ResponseComposerModelOutput",
                        "safe_read_speech_required": (
                            self._is_safe_read_plan(plan, request.context)
                            and not pure_safe_read
                            and not delivered_turn_speech
                        ),
                        "safe_read_speech_optional": (
                            self._is_safe_read_plan(plan, request.context)
                            and (pure_safe_read or bool(delivered_turn_speech))
                        ),
                        "pure_safe_read_fast_act_reference_only": pure_safe_read,
                        "delivered_turn_speech_count": len(delivered_turn_speech),
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        "dto_regeneration_succeeded": dto_regeneration_attempted,
                        "response_truth_audit": {
                            "attempted": response_truth_audit_attempted,
                            "accepted": bool(
                                response_truth_audit is not None
                                and not response_truth_audit.violations
                            ),
                            "violations": (
                                list(response_truth_audit.violations)
                                if response_truth_audit is not None
                                else []
                            ),
                            "reason_summary": (
                                response_truth_audit.reason_summary
                                if response_truth_audit is not None
                                else ""
                            ),
                            "authority": "immutable_proof",
                        },
                    },
                )
                return ResponseCompositionResolution(
                    status="resolved",
                    composition=composition,
                    reason_summary="Task and speech were coordinated by the single Response Composer owner.",
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "contract_schema": "ResponseComposerModelOutput",
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        "dto_regeneration_succeeded": dto_regeneration_attempted,
                        "response_truth_audit_attempted": response_truth_audit_attempted,
                        "response_truth_audit_accepted": bool(
                            response_truth_audit is not None
                            and not response_truth_audit.violations
                        ),
                        "goal_coverage_projection_reasons": coverage_projection_reasons,
                    },
                )
            except Exception as exc:
                failure = llm_failure_metadata(exc)
                logger.warning(
                    "response_composer_inference_failed sid=%s attempt=%s error_type=%s error=%s "
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
                integrity_metadata = cognitive_integrity_metadata(
                    stage="response_composer", exc=exc, request=request
                )
                if attempt == 0 and isinstance(
                    exc, (ValidationError, json.JSONDecodeError, ResponseComposerDTOContractError)
                ):
                    dto_regeneration_attempted = True
                    previous_raw = raw
                    initial_validation_errors = self._validation_error_json(exc)
                    continue
                fallback = self._primary_activity_fail_soft_composition(
                    request=request,
                    plan=plan,
                    composition_id=composition_id,
                    failure=exc,
                    dto_regeneration_attempted=dto_regeneration_attempted,
                )
                if fallback is not None:
                    return fallback
                logger.warning(
                    "response_composer_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s regeneration_raw_output_ref=%s "
                    "initial_raw_output=%s regeneration_raw_output=%s",
                    request.sid,
                    cognition_text_reference(previous_raw if dto_regeneration_attempted else None),
                    cognition_text_reference(raw if dto_regeneration_attempted else None),
                    self._bounded(previous_raw, 5000)
                    if dto_regeneration_attempted and previous_raw is not None
                    else "",
                    self._bounded(raw, 5000)
                    if dto_regeneration_attempted and raw is not None
                    else "",
                )
                return ResponseCompositionResolution(
                    status="model_unavailable",
                    reason_summary="Response composition model output was unavailable or invalid.",
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                        "contract_schema": "ResponseComposerModelOutput",
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        "dto_regeneration_succeeded": False,
                        "response_truth_audit_attempted": response_truth_audit_attempted,
                        "response_truth_audit_accepted": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output_ref": cognition_text_reference(
                            previous_raw if dto_regeneration_attempted else None
                        ),
                        "regeneration_raw_output_ref": cognition_text_reference(
                            raw if dto_regeneration_attempted else None
                        ),
                        **integrity_metadata,
                        **failure,
                    },
                )
        raise AssertionError("unreachable")

    @classmethod
    def _pure_safe_read_response_plan(
        cls,
        *,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> ResponsePlan:
        """Materialize only an exact pending Fast act for pure safe-read work."""

        delivered_event_ids = {
            cls._speech_event_id(item)
            for item in cls._delivered_turn_speech(context)
        }
        candidate = next(
            (
                item
                for item in reversed(cls._scheduled_turn_speech(context))
                if cls._speech_event_id(item)
                and cls._speech_event_id(item) not in delivered_event_ids
            ),
            None,
        )
        if candidate is None:
            return ResponsePlan()
        return ResponsePlan(
            immediate=ResponseStage(
                text=str(candidate["text"]),
                speech_act=str(candidate.get("purpose") or "acknowledge"),
                commitment_state="evaluating",
                must_not_claim_completion=True,
                reuse_current_turn_speech=True,
                reused_speech_event_id=cls._speech_event_id(candidate),
                covers_goal_ids=list(plan.goal_ids),
            )
        )

    @classmethod
    def _primary_activity_fail_soft_composition(
        cls,
        *,
        request: CognitiveWorkRequest,
        plan: CanonicalPlan,
        composition_id: str,
        failure: Exception,
        dto_regeneration_attempted: bool,
    ) -> ResponseCompositionResolution | None:
        """Preserve a validated pure execution Plan after presentation-only failure.

        Response Composer owns wording and optional lane presentation; it does not
        own the already validated Capability Plan.  When a pure, non-confirmation
        safe-read execution Plan can proceed without dynamic pre-evidence speech;
        other execution Plans require one model-authored current-turn acknowledgement.
        Prefer one already queued or playback-started; when a direct Core caller has
        not scheduled it yet, preserve the Core's validated FastSpeech DTO as the new
        delivery/effect barrier instead of discarding the Activity Plan because an
        optional composition DTO remained malformed.

        The adapter never invents speech, chooses a Capability, weakens confirmation,
        or bypasses playback.  Mixed/clarification/confirmation-bound Plans remain
        fail-closed because their outstanding communicative responsibilities cannot
        be reconstructed mechanically.
        """

        if (
            plan.disposition != "execute"
            or not plan.steps
            or cls._confirmation_required(plan, request.context)
            or plan.waiting_goal_ids()
            or any(outcome.disposition != "execute" for outcome in plan.goal_outcomes)
        ):
            return None
        safe_read = cls._is_safe_read_plan(plan, request.context)
        if safe_read:
            response_plan = cls._pure_safe_read_response_plan(
                plan=plan,
                context=request.context,
            )
        else:
            reusable = cls._reusable_turn_speech(request.context)
            candidate = next(
                (
                    item
                    for item in reversed(reusable)
                    if str(item.get("route") or "").strip()
                    in {"", "robot_action"}
                    and str(item.get("text") or "").strip()
                    and cls._speech_event_id(item)
                ),
                None,
            )
            if candidate is not None:
                response_plan = ResponsePlan(
                    pre_action=ResponseStage(
                        text=str(candidate["text"]),
                        speech_act=str(candidate.get("purpose") or "acknowledge"),
                        commitment_state="heard",
                        must_not_claim_completion=True,
                        reuse_current_turn_speech=True,
                        reused_speech_event_id=cls._speech_event_id(candidate),
                        covers_goal_ids=list(plan.goal_ids),
                    )
                )
            else:
                return None
        cls._validate_reused_turn_speech(
            response_plan,
            context=request.context,
            plan=plan,
        )
        cls._validate_pending_response_contract(
            response_plan,
            plan=plan,
            context=request.context,
        )
        composition = CoordinatedResponsePlan(
            composition_id=composition_id,
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=response_plan,
            lane_coordination=[],
            confidence=0.0,
            rationale=(
                "Reused a scheduled acknowledgement when present, without treating "
                "it as delivered, so an optional presentation failure could not "
                "cancel the validated primary activity."
                if safe_read
                else "Preserved the existing Core-authored acknowledgement so an "
                "optional presentation failure could not cancel the validated "
                "primary activity."
            ),
            metadata={
                "authority": "advisory",
                "resolver": "response_composer",
                "task_plan_immutable": True,
                "fail_soft_primary_activity": True,
                "reused_current_turn_speech": any(
                    stage is not None and stage.reuse_current_turn_speech
                    for stage in (
                        response_plan.immediate,
                        response_plan.pre_action,
                    )
                ),
                "safe_read_speech_optional": safe_read,
                "pure_safe_read_fast_act_reference_only": safe_read,
                "original_failure_type": type(failure).__name__,
                "original_failure": str(failure)[:300],
                "dto_regeneration_attempted": dto_regeneration_attempted,
            },
        )
        logger.warning(
            "response_composer_primary_activity_fail_soft sid=%s plan_id=%s failure_type=%s",
            request.sid,
            plan.plan_id,
            type(failure).__name__,
        )
        return ResponseCompositionResolution(
            status="resolved",
            composition=composition,
            reason_summary=(
                "Validated safe-read activity was preserved with dynamic "
                "pre-evidence speech suppressed."
                if safe_read
                else "Validated primary activity was preserved with the existing "
                "Core-authored current-turn acknowledgement speech."
            ),
            metadata={
                "authority": "advisory",
                "resolver": "response_composer",
                "fail_soft_primary_activity": True,
                "pure_safe_read_fast_act_reference_only": safe_read,
                "dto_regeneration_attempted": dto_regeneration_attempted,
                "original_failure_type": type(failure).__name__,
            },
        )

    @staticmethod
    def _validation_error_json(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return json.dumps(
                exc.errors(include_url=False),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )[:8000]
        return json.dumps(
            [{"type": type(exc).__name__, "message": str(exc)[:1000]}],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _is_safe_read_plan(
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> bool:
        if (
            plan.disposition not in {"execute", "mixed"}
            or not plan.steps
            or not isinstance(context, dict)
        ):
            return False
        raw = context.get("execution_capabilities")
        if not isinstance(raw, list):
            return False
        safety_by_capability = {
            str(item.get("capability_id") or "").strip(): str(
                item.get("safety_class") or ""
            ).strip()
            for item in raw
            if isinstance(item, dict)
        }
        return all(
            safety_by_capability.get(step.capability_id) == "safe_read" for step in plan.steps
        )

    @staticmethod
    def _delivered_turn_speech(
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not isinstance(context, dict):
            return []
        raw = context.get("delivered_turn_speech")
        if not isinstance(raw, list):
            return []
        delivered: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip()
            text = " ".join(str(item.get("text") or "").strip().split())
            if status not in {"playback_started", "playback_completed"} or not text:
                continue
            delivered.append({**item, "text": text, "status": status})
        return delivered

    @staticmethod
    def _scheduled_turn_speech(
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Return queued current-turn speech for semantic de-duplication only."""

        if not isinstance(context, dict):
            return []
        raw = context.get("scheduled_turn_speech")
        if not isinstance(raw, list):
            return []
        scheduled: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = " ".join(str(item.get("text") or "").strip().split())
            if str(item.get("status") or "").strip() != "scheduled" or not text:
                continue
            scheduled.append(
                {
                    **item,
                    "text": text,
                    "status": "scheduled",
                    "external_fact_evidence": False,
                    "completion_evidence": False,
                }
            )
        return scheduled

    @classmethod
    def _reusable_turn_speech(
        cls,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return [
            *cls._delivered_turn_speech(context),
            *cls._scheduled_turn_speech(context),
        ]

    @classmethod
    def _existing_event_for_pending_speech_act(
        cls,
        stage: ResponseStage,
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Return an exact current-turn act identity already scheduled/heard.

        This is deliberately not text similarity.  The model-authored
        ``speech_act`` and the Interaction Ledger event purpose are the typed
        conversational responsibility identity.  A genuinely new supplement,
        correction, warning, or confirmation must carry its own act identity;
        an acknowledgement with the same identity must reference the existing
        event instead of requesting duplicate audio.
        """

        speech_act = " ".join(stage.speech_act.strip().casefold().split())
        if not speech_act:
            return None
        stage_goal_ids = set(stage.covers_goal_ids)
        for event in reversed(cls._reusable_turn_speech(context)):
            event_id = cls._speech_event_id(event)
            purpose = " ".join(
                str(event.get("purpose") or event.get("speech_act") or "")
                .strip()
                .casefold()
                .split()
            )
            if not event_id or purpose != speech_act:
                continue
            event_goal_ids = {
                normalized
                for item in event.get("source_goal_ids") or []
                if (normalized := " ".join(str(item or "").strip().split()))
            }
            if event_goal_ids and stage_goal_ids and not event_goal_ids.intersection(
                stage_goal_ids
            ):
                continue
            return event
        return None

    @classmethod
    def _pending_scheduled_turn_speech(
        cls,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        delivered_event_ids = {
            cls._speech_event_id(item)
            for item in cls._delivered_turn_speech(context)
            if cls._speech_event_id(item)
        }
        return [
            item
            for item in cls._scheduled_turn_speech(context)
            if cls._speech_event_id(item)
            and cls._speech_event_id(item) not in delivered_event_ids
        ]

    @staticmethod
    def _speech_event_id(item: dict[str, Any]) -> str:
        return " ".join(
            str(item.get("event_id") or item.get("speech_event_id") or "")
            .strip()
            .split()
        )

    @staticmethod
    def _strip_model_authored_goal_coverage(raw: dict[str, Any]) -> dict[str, Any]:
        """Remove duplicate writable Goal coverage from model-authored response DTOs.

        Goal ownership already exists in the immutable CanonicalPlan/Goal Association.
        Response Composer owns wording only.  Stage ``covers_goal_ids`` is therefore a
        Host-derived projection and any model-authored copy is discarded before typed
        validation.
        """

        normalized = copy.deepcopy(raw)
        response_plan = normalized.get("response_plan")
        if not isinstance(response_plan, dict):
            return normalized
        for key in ("immediate", "pre_action", "final"):
            stage = response_plan.get(key)
            if isinstance(stage, dict):
                stage.pop("covers_goal_ids", None)
        progress = response_plan.get("progress")
        if isinstance(progress, list):
            for stage in progress:
                if isinstance(stage, dict):
                    stage.pop("covers_goal_ids", None)
        return normalized

    @staticmethod
    def _project_direct_goal_coverage(
        response_plan: ResponsePlan, *, goal_ids: list[str]
    ) -> ResponsePlan:
        if response_plan.final is None:
            return response_plan
        return response_plan.model_copy(
            update={
                "final": response_plan.final.model_copy(
                    update={"covers_goal_ids": list(dict.fromkeys(goal_ids))}
                )
            }
        )

    @classmethod
    def _project_goal_coverage(
        cls,
        response_plan: ResponsePlan,
        *,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> tuple[ResponsePlan, list[str]]:
        """Project immutable Goal ownership onto response stages mechanically.

        ``covers_goal_ids`` is delivery bookkeeping, not a second semantic decision.
        The projection uses only CanonicalPlan goal outcomes, response phase/commitment,
        and exact reused current-turn speech provenance.  It never infers new Goals,
        rewrites wording, changes execution, or promotes evidence.
        """

        payload = response_plan.model_dump(mode="python", exclude_none=True)
        raw_stages: list[tuple[str, dict[str, Any]]] = []
        for key in ("immediate", "pre_action"):
            stage = payload.get(key)
            if isinstance(stage, dict):
                stage["covers_goal_ids"] = []
                raw_stages.append((key, stage))
        progress = payload.get("progress")
        if isinstance(progress, list):
            for stage in progress:
                if isinstance(stage, dict):
                    stage["covers_goal_ids"] = []
                    raw_stages.append(("progress", stage))
        final = payload.get("final")
        if isinstance(final, dict):
            final["covers_goal_ids"] = []
            raw_stages.append(("final", final))

        ordered_goal_ids = list(dict.fromkeys(plan.goal_ids))
        if not ordered_goal_ids or not raw_stages:
            return ResponsePlan.model_validate(payload), []

        goal_set = set(ordered_goal_ids)
        outcome_disposition = {
            outcome.goal_id: outcome.disposition for outcome in plan.goal_outcomes
        }
        execute_ids = [
            goal_id for goal_id in ordered_goal_ids
            if outcome_disposition.get(goal_id) == "execute"
        ]
        clarify_ids = [
            goal_id for goal_id in ordered_goal_ids
            if outcome_disposition.get(goal_id) == "clarify"
        ]
        respond_ids = [
            goal_id for goal_id in ordered_goal_ids
            if outcome_disposition.get(goal_id) == "respond"
        ]
        other_ids = [
            goal_id for goal_id in ordered_goal_ids
            if goal_id not in set(execute_ids + clarify_ids + respond_ids)
        ]
        if not plan.goal_outcomes:
            if plan.disposition == "execute":
                execute_ids = ordered_goal_ids
            elif plan.disposition == "clarify":
                clarify_ids = ordered_goal_ids
            else:
                respond_ids = ordered_goal_ids

        reasons: list[str] = []
        reusable_by_event_id = {
            cls._speech_event_id(item): item
            for item in cls._reusable_turn_speech(context)
            if cls._speech_event_id(item)
        }

        # Exact reused speech keeps the Goal provenance of the event it references.
        for _, stage in raw_stages:
            if not stage.get("reuse_current_turn_speech"):
                continue
            event_id = " ".join(str(stage.get("reused_speech_event_id") or "").strip().split())
            event = reusable_by_event_id.get(event_id)
            if not isinstance(event, dict):
                continue
            event_goal_ids = [
                normalized
                for item in event.get("source_goal_ids") or []
                if (normalized := " ".join(str(item or "").strip().split())) in goal_set
            ]
            if event_goal_ids:
                stage["covers_goal_ids"] = list(dict.fromkeys(event_goal_ids))
                reasons.append("reused_speech_goal_provenance_projected")

        def assigned() -> set[str]:
            return {
                goal_id
                for _, stage in raw_stages
                for goal_id in stage.get("covers_goal_ids") or []
            }

        def can_extend(stage: dict[str, Any]) -> bool:
            if not stage.get("reuse_current_turn_speech"):
                return True
            event_id = " ".join(str(stage.get("reused_speech_event_id") or "").strip().split())
            event = reusable_by_event_id.get(event_id)
            return not isinstance(event, dict) or not list(event.get("source_goal_ids") or [])

        def add(stage: dict[str, Any] | None, goal_ids: list[str], reason: str) -> None:
            if stage is None or not goal_ids or not can_extend(stage):
                return
            existing = list(stage.get("covers_goal_ids") or [])
            additions = [goal_id for goal_id in goal_ids if goal_id not in existing]
            if additions:
                stage["covers_goal_ids"] = [*existing, *additions]
                reasons.append(reason)

        def first_stage(*, clarification: bool | None = None, prefer_pre_action: bool = False) -> dict[str, Any] | None:
            candidates = list(raw_stages)
            if prefer_pre_action:
                candidates.sort(key=lambda item: 0 if item[0] == "pre_action" else 1)
            for _, stage in candidates:
                is_clarification = (
                    str(stage.get("speech_act") or "").strip().casefold()
                    in {"clarify", "ask_clarification"}
                    or str(stage.get("commitment_state") or "").strip() == "waiting_for_user"
                )
                if clarification is not None and is_clarification != clarification:
                    continue
                if can_extend(stage):
                    return stage
            return None

        if plan.disposition in {"respond", "unavailable", "refused"}:
            add(
                next((stage for phase, stage in raw_stages if phase == "final"), raw_stages[0][1]),
                ordered_goal_ids,
                "terminal_goal_coverage_projected",
            )
        elif plan.disposition == "clarify":
            add(
                first_stage(clarification=True) or raw_stages[0][1],
                clarify_ids or ordered_goal_ids,
                "clarification_goal_coverage_projected",
            )
        else:
            if clarify_ids:
                add(
                    first_stage(clarification=True),
                    clarify_ids,
                    "clarification_goal_coverage_projected",
                )
            if respond_ids:
                add(
                    first_stage(clarification=False) or first_stage(),
                    respond_ids,
                    "response_goal_coverage_projected",
                )
            if execute_ids:
                # Execution coverage belongs to one prospective speech barrier. Prefer
                # a stage that is not already carrying a conversational/clarification
                # responsibility. When an exact pending Fast acknowledgement exists,
                # keep the responsibilities separate and project that event below.
                pending_fast_ack = any(
                    str(item.get("route") or "").strip() in {"", "robot_action"}
                    and str(item.get("text") or "").strip()
                    and cls._speech_event_id(item)
                    and not list(item.get("source_goal_ids") or [])
                    for item in cls._reusable_turn_speech(context)
                )
                execute_stage = next(
                    (
                        stage
                        for phase, stage in sorted(
                            raw_stages, key=lambda item: 0 if item[0] == "pre_action" else 1
                        )
                        if can_extend(stage) and not list(stage.get("covers_goal_ids") or [])
                    ),
                    None,
                )
                if execute_stage is None and not pending_fast_ack:
                    execute_stage = first_stage(clarification=False, prefer_pre_action=True)
                    if execute_stage is None:
                        execute_stage = first_stage(prefer_pre_action=True)
                add(execute_stage, execute_ids, "execute_goal_coverage_projected")
            if other_ids:
                add(first_stage() or raw_stages[0][1], other_ids, "other_goal_coverage_projected")

        missing = [goal_id for goal_id in ordered_goal_ids if goal_id not in assigned()]
        if missing and plan.disposition == "mixed" and set(missing).issubset(set(execute_ids)):
            # Reuse an exact already-scheduled Fast acknowledgement when the current
            # authored response is only the non-execute part of a mixed Plan.
            candidate = next(
                (
                    item
                    for item in reversed(cls._reusable_turn_speech(context))
                    if str(item.get("route") or "").strip() in {"", "robot_action"}
                    and str(item.get("text") or "").strip()
                    and cls._speech_event_id(item)
                    and not list(item.get("source_goal_ids") or [])
                ),
                None,
            )
            if candidate is not None and payload.get("pre_action") is None:
                payload["pre_action"] = ResponseStage(
                    text=" ".join(str(candidate["text"]).strip().split()),
                    speech_act=str(candidate.get("purpose") or "acknowledge"),
                    commitment_state="heard",
                    must_not_claim_completion=True,
                    reuse_current_turn_speech=True,
                    reused_speech_event_id=cls._speech_event_id(candidate),
                    covers_goal_ids=missing,
                ).model_dump(mode="python", exclude_none=True)
                reasons.append("execute_goal_coverage_projected_from_existing_fast_speech")
                missing = []

        # Preserve one canonical Goal ordering in every derived projection.
        ordering = {goal_id: index for index, goal_id in enumerate(ordered_goal_ids)}
        for _, stage in raw_stages:
            stage["covers_goal_ids"] = sorted(
                list(dict.fromkeys(stage.get("covers_goal_ids") or [])),
                key=lambda goal_id: ordering.get(goal_id, len(ordering)),
            )
        projected = ResponsePlan.model_validate(payload)
        return projected, list(dict.fromkeys(reasons))

    @classmethod
    def _validate_reused_turn_speech(
        cls,
        response_plan: ResponsePlan,
        *,
        context: dict[str, Any] | None,
        plan: CanonicalPlan | None = None,
    ) -> None:
        reusable_by_event_id = {
            event_id: item
            for item in cls._reusable_turn_speech(context)
            if isinstance(item, dict)
            and (event_id := cls._speech_event_id(item))
        }
        for phase, stage in (
            ("immediate", response_plan.immediate),
            ("pre_action", response_plan.pre_action),
            *[("progress", item) for item in response_plan.progress],
            ("final", response_plan.final),
        ):
            if stage is None:
                continue
            if not stage.reuse_current_turn_speech:
                continue
            if phase not in {"immediate", "pre_action"}:
                raise ValueError("only immediate or pre_action may reuse current-turn speech")
            event = reusable_by_event_id.get(str(stage.reused_speech_event_id or ""))
            if event is None:
                raise ValueError(
                    "reused current-turn speech must reference one exact scheduled "
                    "or playback-started speech event"
                )
            if " ".join(stage.text.strip().split()) != " ".join(
                str(event.get("text") or "").strip().split()
            ):
                raise ValueError(
                    "reused current-turn speech text must match the referenced "
                    "speech event"
                )
            purpose = " ".join(str(event.get("purpose") or "").strip().split())
            if purpose and stage.speech_act != purpose:
                raise ValueError(
                    "reused current-turn speech act must match the referenced "
                    "speech event purpose"
                )
            event_goal_ids = {
                normalized
                for item in event.get("source_goal_ids") or []
                if (normalized := " ".join(str(item or "").strip().split()))
            }
            reassigned_goal_ids = set(stage.covers_goal_ids) - event_goal_ids
            if event_goal_ids and reassigned_goal_ids:
                raise ValueError(
                    "Goal-bound current-turn speech cannot be reassigned to "
                    "unrelated canonical Goals: "
                    + ", ".join(sorted(reassigned_goal_ids))
                )
            if plan is None:
                continue
            event_plan_id = " ".join(
                str(event.get("canonical_plan_id") or "").strip().split()
            )
            if event_plan_id and event_plan_id != plan.plan_id:
                raise ValueError(
                    "reused current-turn speech references a different canonical plan"
                )
            event_plan_fingerprint = " ".join(
                str(event.get("canonical_plan_fingerprint") or "").strip().split()
            )
            if (
                event_plan_fingerprint
                and event_plan_fingerprint != canonical_plan_fingerprint(plan)
            ):
                raise ValueError(
                    "reused current-turn speech canonical-plan fingerprint mismatch"
                )

    @staticmethod
    def _confirmation_required(
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> bool:
        if plan.metadata.get("user_confirmation_required") is True:
            return True
        if not isinstance(context, dict):
            return False
        capabilities = context.get("execution_capabilities")
        return isinstance(capabilities, list) and any(
            isinstance(item, dict) and item.get("requires_confirmation") is True
            for item in capabilities
        )

    @classmethod
    def _validate_pending_response_contract(
        cls,
        response_plan: ResponsePlan,
        *,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> None:
        if plan.disposition not in {"execute", "mixed"} or not plan.steps:
            return
        if response_plan.final is not None:
            raise ValueError(
                f"{plan.disposition} pre-execution response must not include a final stage"
            )
        if response_plan.progress:
            raise ValueError(
                f"{plan.disposition} pre-execution response must not include progress stages"
            )
        pending_stages = [
            stage
            for stage in (response_plan.immediate, response_plan.pre_action)
            if stage is not None
        ]
        if not pending_stages:
            if (
                plan.disposition == "execute"
                and cls._is_safe_read_plan(plan, context)
                and not cls._confirmation_required(plan, context)
            ):
                return
            raise ValueError(
                f"{plan.disposition} pre-execution response requires immediate or pre_action speech"
            )
        for stage in pending_stages:
            if not stage.reuse_current_turn_speech:
                existing = cls._existing_event_for_pending_speech_act(
                    stage,
                    context,
                )
                if existing is not None:
                    raise ValueError(
                        "pending response repeats a current-turn speech act that "
                        "must be referenced with reuse_current_turn_speech=true: "
                        + cls._speech_event_id(existing)
                    )
            if stage.speech_act.strip().casefold() == "none":
                raise ValueError(
                    f"{plan.disposition} pre-execution response cannot use "
                    "speech_act=none as a playback/effect barrier"
                )
            if not any(character.isalnum() for character in stage.text):
                raise ValueError(
                    f"{plan.disposition} pre-execution response requires "
                    "speakable text; punctuation-only placeholders are not a "
                    "playback/effect barrier"
                )
            if stage.commitment_state not in {
                "none",
                "heard",
                "evaluating",
                "waiting_for_user",
            }:
                raise ValueError(
                    f"{plan.disposition} pre-execution response overstates commitment: "
                    + stage.commitment_state
                )
            if not stage.must_not_claim_completion:
                raise ValueError(
                    f"{plan.disposition} pre-execution response must forbid completion claims"
                )
        confirmation_required = cls._confirmation_required(plan, context)
        if confirmation_required and not any(
            stage.commitment_state == "waiting_for_user"
            and stage.speech_act.casefold() == "ask_confirmation"
            for stage in pending_stages
        ):
            raise ValueError(
                "confirmation-bound pre-execution response requires an "
                "ask_confirmation stage with commitment_state=waiting_for_user"
            )
        if (
            not confirmation_required
            and plan.disposition == "execute"
            and any(
                stage.commitment_state == "waiting_for_user"
                or stage.speech_act.casefold() == "ask_confirmation"
                for stage in pending_stages
            )
        ):
            raise ValueError(
                "execute response requests confirmation without a supplied confirmation requirement"
            )

    @classmethod
    def _validate_safe_read_acknowledgement(
        cls,
        response_plan: ResponsePlan,
        *,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
        language: str | None,
    ) -> None:
        if not cls._is_safe_read_plan(plan, context):
            return
        if (
            plan.disposition == "execute"
            and not cls._confirmation_required(plan, context)
        ):
            pending_speech = cls._pending_scheduled_turn_speech(context)
            if response_plan.pre_action is not None or response_plan.final is not None:
                raise ValueError(
                    "pure safe-read execution may use only an immediate "
                    "pre-evidence response stage"
                )
            if response_plan.progress:
                raise ValueError("pure safe-read execution must not emit progress speech")
            if pending_speech:
                if response_plan.immediate is None:
                    raise ValueError(
                        "pending safe-read Fast speech requires an immediate "
                        "reused-speech stage"
                    )
                if not response_plan.immediate.reuse_current_turn_speech:
                    raise ValueError(
                        "safe-read composition must reference the pending Fast "
                        "speech event instead of duplicating its communicative act"
                    )
                return
            if response_plan.immediate is not None:
                raise ValueError(
                    "pure safe-read composition must not author dynamic "
                    "pre-evidence speech"
                )
            return
        reusable = cls._reusable_turn_speech(context)
        if reusable:
            if response_plan.immediate is None:
                if cls._delivered_turn_speech(context):
                    return
                raise ValueError(
                    "scheduled safe-read acknowledgement must be represented by "
                    "an immediate reused-speech stage"
                )
            if not response_plan.immediate.reuse_current_turn_speech:
                raise ValueError(
                    "safe-read composition must reuse the already scheduled or "
                    "delivered current-turn acknowledgement instead of authoring "
                    "another pre-evidence utterance"
                )
        if response_plan.immediate is None:
            if cls._delivered_turn_speech(context) and not cls._confirmation_required(
                plan, context
            ):
                return
            raise ValueError(
                "safe-read execution requires one model-authored immediate acknowledgement"
            )
        if response_plan.pre_action is not None:
            raise ValueError("safe-read acknowledgement must use immediate, not pre_action")
        # Wording and length are conversational choices owned by the model.
        # The Host validates only the coordination contract: one immediate
        # pre-result stage, exact reuse of an existing current-turn utterance when
        # present, no pre_action/final stage, and no completion claim.

    @staticmethod
    def _validate_spoken_language(
        response_plan: ResponsePlan,
        *,
        request: CognitiveWorkRequest,
    ) -> None:
        language = str(request.language or "").strip().lower()
        if language in {"", "auto"}:
            return
        texts = [
            stage.text
            for stage in (
                response_plan.immediate,
                response_plan.pre_action,
                *response_plan.progress,
                response_plan.final,
            )
            if stage is not None and stage.text.strip()
        ]
        spoken = " ".join(texts)
        if not spoken:
            return
        cjk_count = sum(
            1
            for char in spoken
            if (
                "\u3400" <= char <= "\u4dbf"
                or "\u4e00" <= char <= "\u9fff"
                or "\uf900" <= char <= "\ufaff"
            )
        )
        latin_count = sum(1 for char in spoken if ("A" <= char <= "Z") or ("a" <= char <= "z"))
        if language.startswith("zh"):
            # Permit names and compact technical units inside Chinese, but
            # reject an English answer merely wrapped in Chinese context.
            if cjk_count == 0 and latin_count:
                raise ValueError("spoken response must use the authoritative Chinese language")
            if latin_count > max(12, cjk_count * 2):
                raise ValueError("spoken response contains too much English for zh-CN")
        elif language.startswith("en") and cjk_count > max(2, latin_count // 4):
            raise ValueError("spoken response must use the authoritative English language")

    @staticmethod
    def _has_provider_required_goal_context(
        context: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(context, dict):
            return False

        def contains_provider_required_goal(items: Any) -> bool:
            if not isinstance(items, list):
                return False
            for item in items:
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata")
                if (
                    isinstance(metadata, dict)
                    and (
                        str(metadata.get("responsibility_kind") or "").strip()
                        in {"executable_action", "capability_dependent"}
                        or metadata.get("provider_required") is True
                    )
                ):
                    return True
            return False

        if contains_provider_required_goal(context.get("active_goal_snapshots")):
            return True
        association = goal_association_prompt_projection(context)
        return bool(
            isinstance(association, dict) and contains_provider_required_goal(association.get("new_goals"))
        )

    @classmethod
    def _requires_response_truth_audit(
        cls,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
        *,
        pure_safe_read: bool,
    ) -> bool:
        """Spend a bounded proof call only where unsupported wording matters.

        This is not another response author. The audit may only certify or reject
        the already-authored ResponsePlan. Benign/pure-safe-read presentation stays
        on the single writer call.
        """

        if pure_safe_read:
            return False
        if cls._is_safe_read_plan(plan, context):
            return plan.disposition != "execute" or cls._confirmation_required(
                plan, context
            )
        execution_capabilities = (
            context.get("execution_capabilities") if isinstance(context, dict) else None
        )
        has_non_read_execution = bool(
            isinstance(execution_capabilities, list)
            and execution_capabilities
            and not cls._is_safe_read_plan(plan, context)
        )
        return bool(
            plan.goal_ids
            and plan.disposition in {
                "execute",
                "mixed",
                "clarify",
                "unavailable",
                "refused",
            }
            and (cls._has_provider_required_goal_context(context) or has_non_read_execution)
        )

    @staticmethod
    def _response_schema(
        plan: CanonicalPlan,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = copy.deepcopy(ResponseComposerModelOutput.model_json_schema())
        schema["title"] = "ResponseComposerModelOutput"
        goal_ids = list(dict.fromkeys(plan.goal_ids))

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    covers_goal_ids = properties.get("covers_goal_ids")
                    if isinstance(covers_goal_ids, dict):
                        # Goal coverage is Host-derived from the immutable Plan.
                        # The model may omit the field or return the schema default only.
                        covers_goal_ids["maxItems"] = 0
                        required = node.setdefault("required", [])
                        if "covers_goal_ids" in required:
                            required.remove("covers_goal_ids")
                for value in node.values():
                    constrain(value)
            elif isinstance(node, list):
                for value in node:
                    constrain(value)

        constrain(schema)
        stage_schema = schema.get("$defs", {}).get("ResponseStage")
        if isinstance(stage_schema, dict):
            stage_required = stage_schema.setdefault("required", [])
            for field_name in (
                "text",
                "speech_act",
                "commitment_state",
                "must_not_claim_completion",
            ):
                if field_name not in stage_required:
                    stage_required.append(field_name)
            stage_properties = stage_schema.get("properties", {})
            speech_act = stage_properties.get("speech_act")
            commitment = stage_properties.get("commitment_state")
            must_not_claim = stage_properties.get("must_not_claim_completion")
            reusable_event_ids = [
                event_id
                for item in ResponseComposerResolver._reusable_turn_speech(context)
                if (event_id := ResponseComposerResolver._speech_event_id(item))
            ]
            if reusable_event_ids:
                stage_properties["reused_speech_event_id"] = {
                    "anyOf": [
                        {
                            "type": "string",
                            "enum": list(dict.fromkeys(reusable_event_ids)),
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                }
            if plan.disposition == "clarify":
                if isinstance(speech_act, dict):
                    speech_act["enum"] = ["clarify", "ask_clarification"]
                if isinstance(commitment, dict):
                    commitment["enum"] = ["waiting_for_user"]
                if isinstance(must_not_claim, dict):
                    must_not_claim["const"] = True
            elif plan.disposition in {"execute", "mixed"}:
                confirmation_required = ResponseComposerResolver._confirmation_required(
                    plan, context
                )
                if isinstance(commitment, dict):
                    if confirmation_required:
                        commitment["enum"] = ["waiting_for_user"]
                    elif plan.disposition == "execute":
                        commitment["enum"] = ["none", "heard", "evaluating"]
                    else:
                        commitment["enum"] = [
                            "none",
                            "heard",
                            "evaluating",
                            "waiting_for_user",
                        ]
                if isinstance(must_not_claim, dict):
                    must_not_claim["const"] = True
                if (
                    confirmation_required
                    and not plan.waiting_goal_ids()
                    and isinstance(speech_act, dict)
                ):
                    speech_act["enum"] = ["ask_confirmation"]
                elif isinstance(speech_act, dict):
                    reusable_purposes = [
                        " ".join(str(item.get("purpose") or "").strip().split())
                        for item in ResponseComposerResolver._reusable_turn_speech(
                            context
                        )
                        if " ".join(
                            str(item.get("purpose") or "").strip().split()
                        )
                    ]
                    speech_act["enum"] = list(
                        dict.fromkeys(
                            [
                                "acknowledge",
                                "acknowledge_and_check",
                                "inform",
                                "answer",
                                "response",
                                "statement",
                                "support",
                                "confirm",
                                "supplement",
                                "affirmative",
                                "perform",
                                "greeting",
                                "greet",
                                "clarify",
                                "ask_clarification",
                                *reusable_purposes,
                            ]
                        )
                    )
            elif plan.disposition == "respond":
                if isinstance(commitment, dict):
                    commitment["enum"] = ["completed"]
                if isinstance(must_not_claim, dict):
                    must_not_claim["const"] = False
            elif plan.disposition in {"unavailable", "refused"}:
                if isinstance(commitment, dict):
                    commitment["enum"] = ["none", "heard", "evaluating"]
                if isinstance(must_not_claim, dict):
                    must_not_claim["const"] = True

        response_plan_schema = schema.get("$defs", {}).get("ResponsePlan")
        if isinstance(response_plan_schema, dict):
            response_properties = response_plan_schema.get("properties", {})
            response_required = response_plan_schema.setdefault("required", [])
            if plan.disposition == "respond":
                response_properties["immediate"] = {"type": "null"}
                response_properties["pre_action"] = {"type": "null"}
                progress = response_properties.get("progress")
                if isinstance(progress, dict):
                    progress["maxItems"] = 0
                response_properties["final"] = {"$ref": "#/$defs/ResponseStage"}
                if "final" not in response_required:
                    response_required.append("final")
            elif plan.disposition == "clarify":
                response_properties["immediate"] = {"type": "null"}
                response_properties["pre_action"] = {"type": "null"}
                progress = response_properties.get("progress")
                if isinstance(progress, dict):
                    progress["maxItems"] = 0
                response_properties["final"] = {"$ref": "#/$defs/ResponseStage"}
                if "final" not in response_required:
                    response_required.append("final")
            elif plan.disposition in {"unavailable", "refused"}:
                response_properties["immediate"] = {"type": "null"}
                response_properties["pre_action"] = {"type": "null"}
                progress = response_properties.get("progress")
                if isinstance(progress, dict):
                    progress["maxItems"] = 0
                response_properties["final"] = {"$ref": "#/$defs/ResponseStage"}
                if "final" not in response_required:
                    response_required.append("final")
            elif plan.disposition in {"execute", "mixed"}:
                response_properties["final"] = {"type": "null"}
                progress = response_properties.get("progress")
                if isinstance(progress, dict):
                    progress["maxItems"] = 0
                if plan.disposition == "execute" and ResponseComposerResolver._is_safe_read_plan(
                    plan, context
                ):
                    # A pure safe read must not author new pre-evidence speech.
                    # If Fast speech is already pending, Composer may only reference
                    # that exact act; otherwise the stage is mechanically null.
                    pending_speech = (
                        ResponseComposerResolver._pending_scheduled_turn_speech(context)
                    )
                    response_properties["pre_action"] = {"type": "null"}
                    if pending_speech:
                        response_properties["immediate"] = {
                            "$ref": "#/$defs/ResponseStage"
                        }
                        if "immediate" not in response_required:
                            response_required.append("immediate")
                    else:
                        response_properties["immediate"] = {"type": "null"}
                        if "immediate" in response_required:
                            response_required.remove("immediate")
                    response_plan_schema.pop("anyOf", None)
                else:
                    # Effectful work retains the delivery/effect barrier: it
                    # cannot start until immediate and/or pre_action speech
                    # covering every goal begins playback.
                    response_plan_schema["anyOf"] = [
                        {
                            "required": ["immediate"],
                            "properties": {"immediate": {"$ref": "#/$defs/ResponseStage"}},
                        },
                        {
                            "required": ["pre_action"],
                            "properties": {"pre_action": {"$ref": "#/$defs/ResponseStage"}},
                        },
                    ]
        return schema

    @staticmethod
    def _direct_goal_association(
        context: dict[str, Any],
    ) -> GoalAssociationResolution | None:
        value = context.get("direct_goal_association_resolution")
        if isinstance(value, GoalAssociationResolution):
            association = value
        elif isinstance(value, dict):
            try:
                association = GoalAssociationResolution.model_validate(value)
            except ValidationError:
                return None
        else:
            return None
        if association.associations or not association.new_goals:
            return None
        if any(
            str((goal.metadata or {}).get("responsibility_kind") or "") != "vocal_output"
            for goal in association.new_goals
        ):
            return None
        if any(not str(goal.goal_id or "").strip() for goal in association.new_goals):
            return None
        return association

    @staticmethod
    def _direct_goal_ids(association: GoalAssociationResolution) -> list[str]:
        return list(
            dict.fromkeys(
                str(goal.goal_id or "").strip()
                for goal in association.new_goals
                if str(goal.goal_id or "").strip()
            )
        )

    @staticmethod
    def _direct_composition_id(
        request: CognitiveWorkRequest,
        association: GoalAssociationResolution,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{request.sid or 'turn'}|"
                f"{goal_association_fingerprint(association)}|direct-response"
            ).encode()
        ).hexdigest()[:20]
        return f"composition_{digest}"

    async def _resolve_direct(
        self,
        request: CognitiveWorkRequest,
        association: GoalAssociationResolution,
    ) -> ResponseCompositionResolution:
        goal_ids = self._direct_goal_ids(association)
        response_schema = self._direct_response_schema(goal_ids, request.context)
        previous_raw: Any = None
        validation_errors = ""
        dto_regeneration_attempted = False
        for attempt in range(2):
            raw: Any = None
            try:
                raw = await self.ollama.generate(
                    self._layered_direct_prompt(
                        request,
                        association,
                        previous_raw=previous_raw,
                        validation_errors=validation_errors,
                    ),
                    system=(
                        self._dto_regeneration_system_prompt() if dto_regeneration_attempted else self._system_prompt()
                    ),
                    options={
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                    response_format=response_schema,
                    prompt_family=(
                        "response_composer.direct_dto_regeneration"
                        if dto_regeneration_attempted
                        else "response_composer.direct_primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ResponseComposerDTOContractError("response composer output is not a JSON object")
                raw = self._strip_model_authored_goal_coverage(raw)
                output = ResponseComposerModelOutput.model_validate(raw)
                output = output.model_copy(
                    update={
                        "response_plan": self._project_direct_goal_coverage(
                            output.response_plan, goal_ids=goal_ids
                        )
                    }
                )
                self._validate_direct_response_plan(
                    output.response_plan,
                    goal_ids=goal_ids,
                )
                self._validate_spoken_language(output.response_plan, request=request)
                if output.lane_coordination:
                    raise ValueError(
                        "planless direct responses cannot declare cross-lane coordination"
                    )
                composition = DirectResponseComposition(
                    composition_id=self._direct_composition_id(request, association),
                    goal_association_fingerprint=(goal_association_fingerprint(association)),
                    goal_association=association,
                    response_plan=output.response_plan,
                    confidence=output.confidence,
                    rationale=output.rationale,
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "planless_direct_response": True,
                        "goal_association_immutable": True,
                        "contract_schema": "ResponseComposerModelOutput",
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        "dto_regeneration_succeeded": dto_regeneration_attempted,
                    },
                )
                return ResponseCompositionResolution(
                    status="resolved",
                    composition=composition,
                    reason_summary=(
                        "Model-authored spoken Goals were composed without a "
                        "planning transport stage."
                    ),
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "planless_direct_response": True,
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        "dto_regeneration_succeeded": dto_regeneration_attempted,
                    },
                )
            except Exception as exc:
                failure = llm_failure_metadata(exc)
                logger.warning(
                    "response_composer_direct_inference_failed sid=%s attempt=%s "
                    "error_type=%s error=%s failure_class=%s failure_domain=%s",
                    request.sid,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                    failure["failure_class"],
                    failure["failure_domain"],
                )
                if attempt == 0 and isinstance(
                    exc, (ValidationError, json.JSONDecodeError, ResponseComposerDTOContractError)
                ):
                    dto_regeneration_attempted = True
                    previous_raw = raw
                    validation_errors = self._validation_error_json(exc)
                    continue
                return ResponseCompositionResolution(
                    status=(
                        "invalid_input"
                        if failure["failure_domain"] == "model_contract"
                        else "model_unavailable"
                    ),
                    reason_summary=("Direct response composition did not complete successfully."),
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "planless_direct_response": True,
                        "dto_regeneration_attempted": dto_regeneration_attempted,
                        **failure,
                    },
                )
        raise AssertionError("unreachable direct response composition loop")

    @staticmethod
    def _validate_direct_response_plan(
        response_plan: ResponsePlan,
        *,
        goal_ids: list[str],
    ) -> None:
        if (
            response_plan.immediate is not None
            or response_plan.pre_action is not None
            or response_plan.progress
            or response_plan.final is None
        ):
            raise ValueError("direct spoken Goals require exactly one final response stage")
        final = response_plan.final
        if set(final.covers_goal_ids) != set(goal_ids):
            raise ValueError("direct response must cover every spoken Goal")
        if final.commitment_state != "completed":
            raise ValueError("direct response must complete the spoken Goals")
        if final.must_not_claim_completion:
            raise ValueError("direct response must permit completion of the authored speech")

    @staticmethod
    def _direct_response_schema(
        goal_ids: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = copy.deepcopy(ResponseComposerModelOutput.model_json_schema())
        schema["title"] = "DirectResponseComposerModelOutput"
        stage_schema = schema.get("$defs", {}).get("ResponseStage")
        if isinstance(stage_schema, dict):
            required = stage_schema.setdefault("required", [])
            for name in (
                "text",
                "speech_act",
                "commitment_state",
                "must_not_claim_completion",
            ):
                if name not in required:
                    required.append(name)
            properties = stage_schema.get("properties", {})
            properties["commitment_state"] = {
                "type": "string",
                "enum": ["completed"],
            }
            properties["must_not_claim_completion"] = {
                "type": "boolean",
                "const": False,
            }
            covers = properties.get("covers_goal_ids")
            if isinstance(covers, dict):
                covers["maxItems"] = 0
        response_schema = schema.get("$defs", {}).get("ResponsePlan")
        if isinstance(response_schema, dict):
            properties = response_schema.get("properties", {})
            properties["immediate"] = {"type": "null"}
            properties["pre_action"] = {"type": "null"}
            progress = properties.get("progress")
            if isinstance(progress, dict):
                progress["maxItems"] = 0
            properties["final"] = {"$ref": "#/$defs/ResponseStage"}
            required = response_schema.setdefault("required", [])
            if "final" not in required:
                required.append("final")
        return schema

    def _direct_prompt(
        self,
        request: CognitiveWorkRequest,
        association: GoalAssociationResolution,
        *,
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> str:
        regeneration_context = ""
        if previous_raw is not None:
            regeneration_context = (
                "Previous invalid response JSON:\n"
                f"{self._bounded(previous_raw, 3000)}\n\n"
                "Validation errors:\n"
                f"{validation_errors}\n\n"
            )
        return (
            "Compose Chromie's complete direct conversational response for the "
            "model-authored spoken Goals below. No capability planning or effect "
            "execution is required at this boundary. The newest user turn owns "
            "the communicative intent; prior dialogue is context, not a script to "
            "replay. Ground every user-specific statement in the newest turn, "
            "validated Goals, or supplied conversation context. Do not invent the "
            "user's plans, schedule, preferences, relationships, experiences, "
            "feelings, or circumstances to make a response sound helpful. When a "
            "friendly supporting reason is useful but no personal fact was supplied, "
            "phrase it generally.\n\n"
            f"User turn: {request.text}\n"
            f"Language hint: {request.language or 'auto'}\n\n"
            "Validated Goal Association JSON:\n"
            f"{self._bounded(association.prompt_projection(), 7000)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded((request.history or [])[-8:], 3600)}\n\n"
            "Current-turn delivered speech JSON:\n"
            f"{self._bounded(self._delivered_turn_speech(request.context), 2400)}\n\n"
            "Current-turn scheduled fast speech JSON (de-duplication only; not delivery or result evidence):\n"
            f"{self._bounded(self._scheduled_turn_speech(request.context), 1600)}\n\n"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Return exactly one final response stage covering every supplied Goal "
            "ID. Set commitment_state=completed and "
            "must_not_claim_completion=false because the authored speech itself "
            "completes these Goals. Do not emit immediate, pre_action, or progress. "
            "Do not repeat speech already delivered or already scheduled in this turn unless the newest "
            "meaning requires a correction. Scheduled speech is only a queued communicative commitment, "
            "never result, execution, completion, or proof that the user heard it. Use the authoritative language and "
            "natural six-year-old family-secretary perspective without reciting "
            "identity facts. Social Attention remains optional body decoration under "
            "the supplied policy and must not author or rewrite response text. When "
            "Social Attention is enabled and candidates exist, return a structurally "
            "complete decision: decision=express requires at least one supplied body "
            "behavior; a reason alone is invalid.\n\n"
            + regeneration_context
            + "Return JSON with response_plan, lane_coordination=[], confidence, "
            "and rationale only."
        )

    def _layered_direct_prompt(
        self,
        request: CognitiveWorkRequest,
        association: GoalAssociationResolution,
        *,
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
        rendered = self._direct_prompt(
            request,
            association,
            previous_raw=previous_raw,
            validation_errors=validation_errors,
        )
        promoted = LayeredPrompt.promote(
            rendered,
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
            ),
        )
        return LayeredPrompt(
            identity_world=(identity_world,),
            operating_contract=promoted.operating_contract,
            volatile_suffix=promoted.volatile_suffix,
        )

    @staticmethod
    def _canonical_plan(context: dict[str, Any]) -> CanonicalPlan | None:
        for key in (
            "canonical_plan_resolution",
            "deep_plan_resolution",
            "fast_plan_resolution",
        ):
            value = context.get(key)
            if isinstance(value, CanonicalPlan):
                return value
            if isinstance(value, dict):
                try:
                    return CanonicalPlan.model_validate(value)
                except ValidationError:
                    continue
        return None

    @staticmethod
    def _composition_id(request: CognitiveWorkRequest, plan: CanonicalPlan) -> str:
        digest = hashlib.sha256(
            f"{request.sid or 'turn'}|{plan.plan_id}|response-composition".encode()
        ).hexdigest()[:20]
        return f"composition_{digest}"

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    @staticmethod
    def _raw_response_stages(response_plan: Any) -> list[dict[str, Any]]:
        if not isinstance(response_plan, dict):
            return []
        stages: list[dict[str, Any]] = []
        for key in ("immediate", "pre_action", "final"):
            stage = response_plan.get(key)
            if isinstance(stage, dict):
                stages.append(stage)
        progress = response_plan.get("progress")
        if isinstance(progress, list):
            stages.extend(item for item in progress if isinstance(item, dict))
        return stages

    @classmethod
    def _canonicalize_lane_coordination_payload(
        cls,
        raw: dict[str, Any],
        *,
        plan: CanonicalPlan,
    ) -> dict[str, Any]:
        """Normalize only unambiguous DTO references from the immutable Plan.

        The model still owns whether overlap is desired.  This adapter may copy
        exact already-parallel Plan step IDs and attach an existing coordination
        ID to the one response stage that already covers a model-authored respond
        Goal.  It never chooses a Capability, changes timing, invents speech, or
        authorizes execution.
        """

        normalized = copy.deepcopy(raw)
        groups = normalized.get("lane_coordination")
        if not isinstance(groups, list) or not groups:
            return normalized
        allowed_lanes = {"vocal", "activity"}
        parallel_vocal_step_ids = {
            step.step_id
            for step in plan.steps
            if step.timing == "parallel" and step.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
        }
        parallel_activity_step_ids = {
            step.step_id
            for step in plan.steps
            if step.timing == "parallel" and step.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
        }

        def values_list(value: Any) -> list[Any]:
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return [value]
            return []

        raw_activity_group_count = sum(
            1
            for item in groups
            if isinstance(item, dict)
            and "activity" in {str(value).strip() for value in values_list(item.get("lanes"))}
        )
        valid_groups: list[dict[str, Any]] = []
        for item in groups:
            if not isinstance(item, dict):
                continue
            coordination_id = " ".join(str(item.get("coordination_id") or "").strip().split())
            if not coordination_id:
                continue
            lanes: list[str] = []
            for value in values_list(item.get("lanes")):
                lane = str(value).strip()
                if lane in allowed_lanes and lane not in lanes:
                    lanes.append(lane)
            activity_ids: list[str] = []
            speaking_ids: list[str] = []
            if "vocal" in lanes:
                for value in values_list(item.get("vocal_step_ids")):
                    step_id = str(value).strip()
                    if (
                        step_id
                        and step_id in parallel_vocal_step_ids
                        and step_id not in speaking_ids
                    ):
                        speaking_ids.append(step_id)
                if (
                    not speaking_ids
                    and len(parallel_vocal_step_ids) == 1
                    and len(
                        [
                            group
                            for group in groups
                            if isinstance(group, dict)
                            and "vocal" in values_list(group.get("lanes"))
                        ]
                    )
                    == 1
                ):
                    speaking_ids = sorted(parallel_vocal_step_ids)
            if "activity" in lanes:
                for value in values_list(item.get("activity_step_ids")):
                    step_id = str(value).strip()
                    if (
                        step_id
                        and step_id in parallel_activity_step_ids
                        and step_id not in activity_ids
                    ):
                        activity_ids.append(step_id)
                if (
                    not activity_ids
                    and raw_activity_group_count == 1
                    and parallel_activity_step_ids
                ):
                    activity_ids = [
                        step.step_id
                        for step in plan.steps
                        if step.step_id in parallel_activity_step_ids
                    ]
                if not activity_ids:
                    lanes = [lane for lane in lanes if lane != "activity"]
            if len(lanes) < 2:
                continue
            cleaned = {
                "coordination_id": coordination_id,
                "relation": "parallel",
                "lanes": lanes,
                "start_policy": "best_effort_parallel",
                "failure_policy": "independent",
                "reason_summary": " ".join(str(item.get("reason_summary") or "").strip().split()),
            }
            if "activity" in lanes:
                cleaned["activity_step_ids"] = activity_ids
            if "vocal" in lanes and speaking_ids:
                cleaned["vocal_step_ids"] = speaking_ids
            valid_groups.append(cleaned)
        activity_groups = [
            item
            for item in valid_groups
            if "activity" in {str(value).strip() for value in item.get("lanes") or []}
        ]
        if len(activity_groups) == 1 and parallel_activity_step_ids:
            group = activity_groups[0]
            if not group.get("activity_step_ids"):
                group["activity_step_ids"] = [
                    step.step_id
                    for step in plan.steps
                    if step.step_id in parallel_activity_step_ids
                ]

        stages = cls._raw_response_stages(normalized.get("response_plan"))
        for group in valid_groups:
            lanes = {str(value).strip() for value in group.get("lanes") or []}
            coordination_id = " ".join(str(group.get("coordination_id") or "").strip().split())
            if "vocal" not in lanes or not coordination_id:
                continue
            if group.get("vocal_step_ids"):
                continue
            coordinated_stages = [
                stage
                for stage in stages
                if str(stage.get("coordination_id") or "").strip() == coordination_id
            ]
            if coordinated_stages:
                # Lane coordination is optional execution decoration. A model may
                # copy a coordination ID onto otherwise valid response speech yet
                # omit the paired delivery role, whose schema default is the
                # explicitly uncoordinated `response` role. Do not let that
                # malformed optional reference invalidate the whole turn. Remove
                # only the inconsistent reference here; the ordinary reconciliation
                # pass will then prune the now-memberless optional group. The Host
                # does not guess whether the speech was intended as a performance
                # or an activity companion.
                for stage in coordinated_stages:
                    if str(stage.get("delivery_role") or "response").strip() == "response":
                        stage.pop("coordination_id", None)
                        stage.pop("delivery_role", None)
                continue
            candidates = []
            for stage in stages:
                if (
                    str(stage.get("speech_act") or "").strip().casefold() == "ask_confirmation"
                    or str(stage.get("commitment_state") or "").strip() == "waiting_for_user"
                ):
                    continue
                candidates.append(stage)
            if len(candidates) == 1:
                candidates[0]["coordination_id"] = coordination_id
                candidates[0]["delivery_role"] = "performance"
        normalized["lane_coordination"] = valid_groups
        return normalized

    @classmethod
    def _reconcile_lane_coordination(
        cls,
        *,
        response_plan: ResponsePlan,
        lane_coordination: list[LaneCoordinationGroup],
        plan: CanonicalPlan,
    ) -> tuple[ResponsePlan, list[LaneCoordinationGroup], list[str]]:
        """Prune invalid optional lane references without discarding the turn."""

        response_payload = response_plan.model_dump(mode="python", exclude_none=True)
        stages = cls._raw_response_stages(response_payload)
        speech_ids = {
            str(stage.get("coordination_id") or "").strip()
            for stage in stages
            if str(stage.get("coordination_id") or "").strip()
        }
        parallel_vocal_steps = {
            step.step_id
            for step in plan.steps
            if step.timing == "parallel" and step.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
        }
        parallel_activity_steps = {
            step.step_id
            for step in plan.steps
            if step.timing == "parallel" and step.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
        }
        kept: list[LaneCoordinationGroup] = []
        reasons: list[str] = []
        dropped_ids: set[str] = set()
        for group in lane_coordination:
            lanes: list[str] = []
            vocal_step_ids = [
                step_id for step_id in group.vocal_step_ids if step_id in parallel_vocal_steps
            ]
            if "vocal" in group.lanes and (
                group.coordination_id in speech_ids or vocal_step_ids
            ):
                lanes.append("vocal")
            if (
                "activity" in group.lanes
                and group.activity_step_ids
                and set(group.activity_step_ids).issubset(parallel_activity_steps)
            ):
                lanes.append("activity")
            if len(lanes) < 2:
                dropped_ids.add(group.coordination_id)
                reasons.append(
                    "lane_coordination_pruned_after_member_validation:" + group.coordination_id
                )
                continue
            activity_step_ids = list(group.activity_step_ids) if "activity" in lanes else []
            kept.append(
                group.model_copy(
                    update={
                        "lanes": lanes,
                        "vocal_step_ids": (vocal_step_ids if "vocal" in lanes else []),
                        "activity_step_ids": activity_step_ids,
                    }
                )
            )
        if dropped_ids:
            for stage in stages:
                if str(stage.get("coordination_id") or "").strip() in dropped_ids:
                    stage.pop("coordination_id", None)
                    stage.pop("delivery_role", None)
        return ResponsePlan.model_validate(response_payload), kept, reasons

    def _prompt(
        self,
        request: CognitiveWorkRequest,
        plan: CanonicalPlan,
        *,
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="response_composer",
        )
        return (
            f"User turn:\n{request.text}\n\n"
            f"Language hint: {request.language or 'auto'}\n\n"
            f"Immutable CanonicalPlan JSON:\n{self._bounded(plan.prompt_projection(), 14000)}\n\n"
            f"Active goals JSON:\n{self._bounded(context.get('active_goal_snapshots') or [], 4500)}\n\n"
            f"{goal_progress_communication_prompt('Response Composer')}\n\n"
            f"Goal-scoped Interaction Context JSON:\n{self._bounded(context.get('interaction_context') or {}, 8000)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 6000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Speech already delivered in this current turn JSON (playback-started conversational context, never external-fact evidence):\n{self._bounded(self._delivered_turn_speech(context), 3600)}\n\n"
            f"Fast speech already scheduled in this current turn JSON (queued communicative commitment for de-duplication only; not proof that the user heard it and never external-fact or completion evidence):\n{self._bounded(self._scheduled_turn_speech(context), 2400)}\n\n"
            f"Pending execution capability semantics JSON:\n{self._bounded(context.get('execution_capabilities') or [], 3000)}\n\n"
            f"Recent conversation JSON:\n{self._bounded((context.get('history') or request.history or [])[-6:], 2600)}\n\n"
            f"Previous Response Composer output for mechanical DTO regeneration:\n{self._bounded(previous_raw, 5000) if previous_raw is not None else 'null'}\n\n"
            f"Exact mechanical DTO validation errors:\n{validation_errors or '[]'}\n\n"
            "Compose one ResponsePlan and zero or more typed lane-coordination groups. Social Attention is owned by its independent background cognition and is not part of Response Composer output. Never author, select, validate, or suppress a Social Attention behavior here. "
            "The CanonicalPlan is immutable: do not alter, replace, add, remove, reorder, authorize, or execute its steps or Communicative Acts. A typed communicative_acts entry is Planner-owned semantic intent, timing, and provenance without wording: formulate its still-needed surface expression, but never re-decide whether the act exists or what function it serves. CanonicalPlan.response_text remains wording from an older canonical Planner contract and is not execution evidence: preserve its meaning when still needed while preferring typed Communicative Acts on the Fast-advance path. Suppress or reuse an act only when Interaction Context shows it is already delivered or pending, and supplement or correct it only when new context requires that delta. The verified tool-memory index contains provenance and bound arguments only, not answer facts. It may support honest wording that Chromie recently checked an exact matching subject and is retrieving it, but never state the remembered result before the memory retrieval step returns evidence. Conversation context may ground ordinary conversational repair, but never claim external facts without executed evidence. Answer the user's requested judgment or decision directly before supporting detail, and naturally acknowledge a prior context failure when the current turn calls for repair. "
            "Ground every user-specific statement in the newest turn, active Goals, or supplied conversation context. Do not invent the user's plans, schedule, preferences, relationships, experiences, feelings, or circumstances to make a response sound helpful. When a friendly supporting reason is useful but no personal fact was supplied, phrase it generally. "
            "Use Interaction Context to account for what Chromie already said, committed, attempted, completed, or failed on the relevant Goals. Do not treat an earlier stage's silence as authoritative conversational policy: if no equivalent notification was actually delivered or is pending, a later stage may still speak when Planner owns a real new progress delta. Realize only the Communicative Act still needed. Never promote speech, plan, committed-request, or social-action events into Activity completion; only execution_closure terminal events with evidence references can support such a claim. "
            "For a retained completed external-result Goal, treat delivered evidence-bound dialogue as the only supplied factual projection. Preserve every measurement and condition from the immutable plan and that dialogue exactly; do not substitute, infer, or embellish external details. The newest user turn remains the conversational target: when it is a reaction, feeling, acknowledgement, evaluation, or practical decision, respond to that act first and use prior facts only as useful support. Never replace the current intent with a replay of the old answer. Omit supporting detail when a direct judgment is sufficient. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "The explicit Language hint is authoritative for spoken output unless the user explicitly asks for translation or a different language. When it is zh-CN, speak Chinese only; do not mirror a bilingual greeting, switch to English, or follow the language of identity/internal context. "
            "Do not author covers_goal_ids. Goal coverage is immutable Host-derived delivery bookkeeping projected from the CanonicalPlan after wording is accepted. "
            "For a terminal respond plan, emit exactly one final stage, omit immediate/pre_action/progress, set commitment_state=completed, and set must_not_claim_completion=false. This marks the conversational response itself as complete; it does not claim that an unexecuted action occurred. Greeting wording and length are ordinary model-authored conversational choices; use the full scene, recent relationship context, and owner-approved personality without a fixed greeting template or Host-imposed brevity target. "
            "For execute plans this is pre-execution composition. Effectful or confirmation-bound work must emit an immediate and/or pre_action stage covering every canonical goal, use only none/heard/evaluating/waiting_for_user commitments, set must_not_claim_completion=true, omit progress and final, and phrase the speech naturally. speech_act=none and punctuation-only placeholder text are not audible communication and cannot satisfy the playback/effect barrier. Reuse an exact scheduled acknowledgement when it already owns this act; otherwise author one real prospective acknowledgement. "
            "When the CanonicalPlan or supplied execution capability semantics require confirmation, explain any supplied adjustment or alternative without claiming it started, ask the user to approve it, set speech_act=ask_confirmation and commitment_state=waiting_for_user, and do not imply that approval has already been granted. "
            "Speech already delivered in this current turn is part of the live conversation. Judge its meaning, not its wording. Do not repeat or lightly paraphrase a communicative responsibility the user has already heard. You may supplement it when it covered only part of the current plan, and you may correct it when the later canonical interpretation makes it misleading. Fast speech marked scheduled is a queued current-turn communicative commitment: do not author another acknowledgement with the same semantic job while it is starting, but never treat scheduled status as proof that the user heard it or as external-fact, execution, or completion evidence. When an existing delivered or scheduled acknowledgement adequately covers pending work, reference its speech_event_id in reused_speech_event_id, copy its text only as a playback-integrity field, set reuse_current_turn_speech=true, set speech_act to the event purpose, and add the current canonical goal IDs. That stage is a structured reference to an existing Communicative Act, not a request to speak it again. Use reuse_current_turn_speech=false and omit reused_speech_event_id for any supplement, correction, confirmation question, result, or failure. De-duplication is based on structured act identity and delivery status, never string similarity, keyword matching, or a fixed fast-speech suppression rule. "
            "For a pure execute plan whose pending capabilities are all safe_read or external_read, never author new pre-evidence speech. If scheduled Fast speech has not reached playback_started, represent that exact event as one immediate reused-speech stage so Runtime can reuse or fulfill it; otherwise omit immediate and pre_action speech. Never state any pending measurement, condition, recommendation, conclusion, or completed lookup before matching trusted evidence exists. The post-execution tool-result interpreter owns the evidence-bound factual result. A mixed plan with an independent respond responsibility may still require model-authored speech; that speech must cover only the still-needed conversational responsibility and must not substitute for pending effect evidence. Do not mention internal tools, APIs, execution, backend, evidence IDs, or memory implementation. "
            "For mixed plans, coordinate executable and conversational goals in one natural response: use prospective wording for pending physical steps, do not narrate them with stage directions such as *Blinks twice*, do not claim completion, omit final while work is pending, and include a specific waiting_for_user clarification stage for every clarify outcome. "
            "Chromie has one Cognitive Core and two execution lanes: Vocal delivers model-authored communication and exact provider-qualified vocal performance, while Activity executes non-vocal provider work. Social Attention is background social cognition, not a third execution lane. It may add small optional body decorations such as gaze, blink, nod, smile, wave, or slight posture/orientation changes around an anchored interaction; accepted body decorations execute through Activity with auxiliary_social_attention=true and never own Goal completion. chromie.vocal.perform is a Vocal-lane provider step, never response transport and never an Activity step. The exact chromie.media.* family is persistent Activity-lane playback/control, never Vocal or vocal-performance evidence. Media may share the physical speaker with Vocal only under its declared duck_media_during_vocal mixer policy; describing that overlap must not mutate either Goal, playback identity, or cancellation scope. An optional acknowledgement about pending vocal or media work remains ordinary chromie.speak delivery and is not provider completion evidence. lane_coordination describes Vocal/Activity execution overlap only; it never coordinates Social Attention as a lane, creates another mind, selects a provider, authorizes an effect, or weakens provider safety. Copy an already-parallel chromie.vocal.perform step into vocal_step_ids; copy only already-parallel non-speech provider steps, including chromie.media.play, into activity_step_ids. A coordinated response stage may supply the Vocal member only when no provider vocal_step_ids are present; it must copy the same coordination_id and use delivery_role=activity_companion or performance. Social Attention behaviors never carry coordination_id; they remain opportunistic, parallel, fail-soft Activity decorations. Ordinary pre-action acknowledgement remains delivery_role=response with no coordination_id and keeps the playback-start barrier. Never coordinate ask_confirmation or waiting_for_user speech with effect execution. The maintained start policy is best_effort_parallel and the failure policy is independent; do not imply synchronized starts or atomic cross-provider cancellation. "
            "For clarify, emit exactly one final clarification stage that names the actual unresolved need naturally; do not add a second acknowledgement, progress line, promise, or status sentence. That stage must set speech_act=clarify or ask_clarification and commitment_state=waiting_for_user as direct fields, never inside metadata; waiting_for_user is a commitment_state, not a speech_act. For alternatives, explain the change and request approval. "
            "For unavailable or refused work, state the actual capability/evidence boundary plainly and name the specific requested outcome Chromie cannot do now; do not hide behind a generic 'new ability', 'skill', 'feature', or 'I have not learned that yet'. Do not promise to perform the unavailable work later. When useful, offer at most one honest next step that is immediately conversational or explicitly supported by a supplied Capability; a user-side check or suggestion is allowed. A gentle future possibility such as 'when I can do that someday' is fine only when it makes no promise that Chromie will learn or gain the Capability; 'I will learn/remember/remind/update/send it later' is not. "
            "Social Attention is independent background cognition. Response Composer may acknowledge that it exists conceptually, but it must not author a SocialAttentionPlan, choose decorative capabilities, or treat missing decoration as a response failure. Optional presentation must never reopen primary cognition. "
            "response_plan must be a JSON object with only immediate, pre_action, progress, and final fields; it is never a bare list. "
            "The decoder enforces the exact ResponseComposerModelOutput JSON Schema. Return JSON with response_plan, lane_coordination, confidence, and rationale only."
        )

    def _layered_prompt(
        self,
        request: CognitiveWorkRequest,
        plan: CanonicalPlan,
        *,
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
        skill_contract = agent_skill_prompt_section(
            context,
            agent_role="response_composer",
        )
        rendered = self._prompt(
            request,
            plan,
            previous_raw=previous_raw,
            validation_errors=validation_errors,
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_world,),
            operating_contract=(
                IDENTITY_SEMANTIC_CONTRACT,
                PERSONALITY_SEMANTIC_CONTRACT,
            ),
            capability_contract=(skill_contract,),
        )


    async def _run_response_truth_audit(
        self,
        *,
        request: CognitiveWorkRequest,
        plan: CanonicalPlan,
        candidate: ResponseComposerModelOutput,
    ) -> ResponseTruthAudit:
        """Return one immutable accept/reject proof; never rewrite the response."""

        try:
            raw = await self.ollama.generate(
                self._response_truth_audit_prompt(
                    request=request,
                    plan=plan,
                    candidate=candidate,
                ),
                system=self._response_truth_audit_system_prompt(),
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    "num_ctx": self.num_ctx,
                    "num_predict": min(self.num_predict, 256),
                },
                response_format=ResponseTruthAudit.model_json_schema(),
                prompt_family="response_composer.truth_audit",
                turn_id=request.sid,
                attempt=1,
            )
            if not isinstance(raw, dict):
                raise ResponseComposerSemanticValidationError(
                    "response truth audit did not return a JSON object"
                )
            return ResponseTruthAudit.model_validate(raw)
        except ResponseComposerSemanticValidationError:
            raise
        except Exception as exc:
            raise ResponseComposerSemanticValidationError(
                "response truth audit was unavailable or invalid: "
                f"{type(exc).__name__}: {str(exc)[:300]}"
            ) from exc

    def _response_truth_audit_prompt(
        self,
        *,
        request: CognitiveWorkRequest,
        plan: CanonicalPlan,
        candidate: ResponseComposerModelOutput,
    ) -> str:
        return (
            "Audit one already-authored ResponsePlan against immutable plan/evidence "
            "truth. You are a proof stage, not a response author. Never rewrite text, "
            "Goals, Plans, Social Attention, or typed response stages. Return only an "
            "immutable certificate with `violations` and `reason_summary`. The Host "
            "derives acceptance mechanically: violations=[] accepts; any violation "
            "rejects.\n\n"
            "Report unsupported_reality_claim when the wording states fresh/external "
            "facts not present in trusted evidence. Report premature_effect_claim when "
            "pending physical/effectful work is worded as already happening or started. "
            "Report unsupported_completion_claim when pending work is worded as done. "
            "Report capability_overclaim when wording promises effects outside supplied "
            "Capability semantics. Report unsupported_future_commitment when wording "
            "claims Chromie will later remember, remind, notify, modify/store a list or "
            "record, send a message, or perform another persistent future effect without "
            "a committed Capability/Goal state that can actually deliver it. A friendly "
            "suggestion the user can do now is not a future commitment. Report "
            "confirmation_mismatch when approval wording "
            "does not match the immutable Plan. Report goal_scope_mismatch when the "
            "spoken act materially drops or substitutes an owed user-facing outcome. "
            "Use other_consequential_claim only for another material truth/safety defect. "
            "Harmless style variation is not a violation. Speech already delivered in this "
            "turn is conversational history, not a restriction on what the immutable Plan "
            "may truthfully say next; it does not restrict later plan-authorized content. "
            "A final answer, clarification, suggestion, or limitation after progress speech "
            "is not unsupported_reality_claim merely because that content was not already "
            "spoken in the progress act. Use prior speech only to detect contradiction, "
            "misleading correction, or redundant fulfillment of the same communicative "
            "responsibility.\n\n"
            f"Authoritative user turn:\n{request.text}\n\n"
            "Delivered evidence-bound dialogue JSON:\n"
            f"{self._bounded(evidence_bound_dialogue(request.context, fallback_history=request.history), 3600)}\n\n"
            "Speech already delivered in this turn JSON:\n"
            f"{self._bounded(self._delivered_turn_speech(request.context), 2800)}\n\n"
            "Pending execution Capability semantics JSON:\n"
            f"{self._bounded(request.context.get('execution_capabilities') or [], 6000)}\n\n"
            "Immutable CanonicalPlan JSON:\n"
            f"{self._bounded(plan.prompt_projection(), 14000)}\n\n"
            "Candidate ResponsePlan JSON:\n"
            f"{self._bounded(candidate.response_plan.model_dump(mode='json'), 7000)}\n\n"
            "Return only ResponseTruthAudit JSON. Do not provide replacement wording."
        )

    @staticmethod
    def _response_truth_audit_system_prompt() -> str:
        return (
            "You are Chromie's bounded response-truth auditor. Judge consequential "
            "ordinary sentence meaning against supplied immutable evidence and "
            "Capability semantics. You have no authority to rewrite the response or "
            "reinterpret upstream cognition. Return JSON only."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Response Composer. Coordinate truthful language expression and typed Vocal/Activity overlap around an immutable CanonicalPlan using one Cognitive Core. Social Attention is owned by independent background cognition and is not part of your output. "
            "You do not plan tasks, mutate goals, execute, authorize, or claim unobserved completion. Return JSON only."
        )

    @staticmethod
    def _dto_regeneration_system_prompt() -> str:
        return (
            "Retransmit the same Response Composer meaning under the supplied "
            "ResponseComposerModelOutput schema. Fix only mechanical JSON/DTO contract "
            "errors reported by validation. Do not reconsider the user, Goals, Plan, "
            "evidence, capability meaning, or conversational intent; do not rewrite "
            "already-valid spoken wording. Return JSON only."
        )
