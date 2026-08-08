from __future__ import annotations

import hashlib
import json
import logging
import copy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .capabilities.validator import normalize_args_for_schema, validate_args_for_schema
from .clients.ollama_client import OllamaClient, llm_failure_metadata
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
from .schema import AgentRunRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.llm_diagnostics import cognition_text_reference
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from chromie_contracts.execution_lanes import LaneCoordinationGroup
    from chromie_contracts.goal import GoalAssociationResolution
    from chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from chromie_contracts.plan import CanonicalPlan
    from chromie_contracts.response_composition import (
        CoordinatedResponsePlan,
        DirectResponseComposition,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
        goal_association_fingerprint,
    )
    from chromie_contracts.semantic_task import (
        ResponsePlan,
        ResponseStage,
        pending_action_stage_direction_claims,
    )
    from chromie_contracts.social_attention import (
        SocialAttentionBehavior,
        SocialAttentionPlan,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
    from shared.chromie_contracts.execution_lanes import LaneCoordinationGroup
    from shared.chromie_contracts.goal import GoalAssociationResolution
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.response_composition import (
        CoordinatedResponsePlan,
        DirectResponseComposition,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
        goal_association_fingerprint,
    )
    from shared.chromie_contracts.semantic_task import (
        ResponsePlan,
        ResponseStage,
        pending_action_stage_direction_claims,
    )
    from shared.chromie_contracts.social_attention import (
        SocialAttentionBehavior,
        SocialAttentionPlan,
    )

logger = logging.getLogger("chromie.agent.response_composer")


class ResponseComposerModelOutput(BaseModel):
    """Small model-facing DTO; composition identity remains host-owned."""

    model_config = ConfigDict(extra="forbid")

    response_plan: ResponsePlan
    # Keep the DTO fail-soft for policy-off and compatibility callers. The
    # resolver makes this field decoder-required and non-null whenever Social
    # Attention is enabled and reviewed candidates are available.
    social_attention_plan: SocialAttentionPlan | None = None
    lane_coordination: list[LaneCoordinationGroup] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class ResponseComposerResolver:
    """Advisory composition of truthful speech and scene-aware social attention.

    The model coordinates the actual ResponsePlan language with optional body
    expression under one high-level social-attention purpose. Deterministic code
    never chooses the gesture or rewrites the response; it only validates the
    model-authored plan against evidence, capability schemas, and resource gates.
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

    async def resolve(self, request: AgentRunRequest) -> ResponseCompositionResolution:
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

    async def _resolve(self, request: AgentRunRequest) -> ResponseCompositionResolution:
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
        social_attention_mode = self._social_attention_mode(request.context)
        social_attention_candidate_count = self._social_attention_candidate_count(request.context)
        social_attention_decision_required = self._social_attention_decision_required(
            request.context
        )
        target_evidence = request.context.get("social_attention_target_evidence")
        target_available = bool(
            isinstance(target_evidence, dict) and target_evidence.get("available")
        )
        delivered_turn_speech = self._delivered_turn_speech(request.context)
        pure_safe_read = (
            plan.disposition == "execute"
            and self._is_safe_read_plan(plan, request.context)
            and not self._confirmation_required(plan, request.context)
        )
        logger.info(
            "response_composer_social_attention_context sid=%s mode=%s "
            "candidates=%s decision_required=%s target_available=%s",
            request.sid,
            social_attention_mode,
            social_attention_candidate_count,
            str(social_attention_decision_required).lower(),
            str(target_available).lower(),
        )
        response_schema = self._response_schema(plan, request.context)
        previous_raw: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False
        safe_read_semantic_review_attempted = False
        safe_read_semantic_review_succeeded = False
        effectful_semantic_review_attempted = False
        effectful_semantic_review_succeeded = False
        for attempt in range(2):
            safe_read_semantic_review_succeeded = False
            effectful_semantic_review_succeeded = False
            raw: Any = None
            try:
                raw = await self.ollama.generate(
                    self._prompt(
                        request,
                        plan,
                        previous_raw=previous_raw,
                        validation_errors=initial_validation_errors,
                    ),
                    system=(
                        self._repair_system_prompt()
                        if contract_repair_attempted
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
                        "response_composer.repair"
                        if contract_repair_attempted
                        else "response_composer.primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ValueError("response composer output is not a JSON object")
                raw = self._canonicalize_optional_social_attention_payload(raw)
                raw = self._canonicalize_lane_coordination_payload(raw, plan=plan)
                model_output = ResponseComposerModelOutput.model_validate(raw)
                if self._is_safe_read_plan(plan, request.context) and not pure_safe_read:
                    safe_read_semantic_review_attempted = True
                    logger.info(
                        "response_composer_safe_read_semantic_review_start sid=%s",
                        request.sid,
                    )
                    reviewed = await self.ollama.generate(
                        self._safe_read_semantic_review_prompt(
                            request=request,
                            plan=plan,
                            candidate=model_output,
                        ),
                        system=self._safe_read_semantic_review_system_prompt(),
                        options={
                            "temperature": 0,
                            "top_p": 0.9,
                            "num_ctx": self.num_ctx,
                            "num_predict": self.num_predict,
                        },
                        response_format=response_schema,
                        prompt_family="response_composer.safe_read_review",
                        turn_id=request.sid,
                        attempt=1,
                    )
                    if not isinstance(reviewed, dict):
                        raise ValueError("safe-read semantic review output is not a JSON object")
                    raw = reviewed
                    reviewed = self._canonicalize_optional_social_attention_payload(reviewed)
                    reviewed = self._canonicalize_lane_coordination_payload(reviewed, plan=plan)
                    model_output = ResponseComposerModelOutput.model_validate(reviewed)
                    safe_read_semantic_review_succeeded = True
                    logger.info(
                        "response_composer_safe_read_semantic_review_done sid=%s status=success",
                        request.sid,
                    )
                elif self._requires_effectful_semantic_review(plan, request.context):
                    effectful_semantic_review_attempted = True
                    logger.info(
                        "response_composer_effectful_semantic_review_start sid=%s",
                        request.sid,
                    )
                    reviewed = await self.ollama.generate(
                        self._effectful_semantic_review_prompt(
                            request=request,
                            plan=plan,
                            candidate=model_output,
                        ),
                        system=self._effectful_semantic_review_system_prompt(),
                        options={
                            "temperature": 0,
                            "top_p": 0.9,
                            "num_ctx": self.num_ctx,
                            "num_predict": self.num_predict,
                        },
                        response_format=response_schema,
                        prompt_family="response_composer.effectful_review",
                        turn_id=request.sid,
                        attempt=1,
                    )
                    if not isinstance(reviewed, dict):
                        raise ValueError("effectful semantic review output is not a JSON object")
                    raw = reviewed
                    reviewed = self._canonicalize_optional_social_attention_payload(reviewed)
                    reviewed = self._canonicalize_lane_coordination_payload(reviewed, plan=plan)
                    model_output = ResponseComposerModelOutput.model_validate(reviewed)
                    effectful_semantic_review_succeeded = True
                    logger.info(
                        "response_composer_effectful_semantic_review_done sid=%s status=success",
                        request.sid,
                    )
                repaired_response_plan, mixed_coverage_reasons = (
                    self._repair_mixed_execution_coverage(
                        model_output.response_plan,
                        plan=plan,
                        context=request.context,
                    )
                )
                if mixed_coverage_reasons:
                    model_output = model_output.model_copy(
                        update={"response_plan": repaired_response_plan}
                    )
                self._validate_social_attention_decision(
                    model_output.social_attention_plan,
                    context=request.context,
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
                )
                premature_claims = self._pending_action_claim_errors(
                    model_output.response_plan,
                    plan=plan,
                )
                if premature_claims:
                    raise ValueError("; ".join(premature_claims))
                self._validate_spoken_language(
                    model_output.response_plan,
                    request=request,
                )
                social_plan, social_reasons = self._validated_social_plan(
                    model_output.social_attention_plan,
                    plan=plan,
                    context=request.context,
                )
                model_social_decision = self._social_attention_decision(
                    model_output.social_attention_plan
                )
                model_social_behavior_count = self._social_attention_behavior_count(
                    model_output.social_attention_plan
                )
                validated_social_decision = (
                    social_plan.decision if social_plan is not None else "missing"
                )
                validated_social_behavior_count = (
                    len(social_plan.behaviors) if social_plan is not None else 0
                )
                if (
                    attempt == 0
                    and model_social_decision == "express"
                    and validated_social_decision == "none"
                    and social_reasons
                ):
                    raise ValueError(
                        "social_attention decision=express lost every proposed "
                        "member during deterministic validation: "
                        + "; ".join(social_reasons)
                        + ". Revise to another eligible untargeted behavior, "
                        "speech_expression.mode=adapt, or an explicit "
                        "decision=none with a concrete scene reason."
                    )
                response_plan, lane_coordination, lane_reasons = self._reconcile_lane_coordination(
                    response_plan=model_output.response_plan,
                    lane_coordination=model_output.lane_coordination,
                    social_attention_plan=social_plan,
                    plan=plan,
                )
                logger.info(
                    "response_composer_social_attention_decision sid=%s mode=%s "
                    "candidates=%s required=%s model_decision=%s "
                    "model_behaviors=%s validated_decision=%s "
                    "validated_behaviors=%s validation_reasons=%s",
                    request.sid,
                    social_attention_mode,
                    social_attention_candidate_count,
                    str(social_attention_decision_required).lower(),
                    model_social_decision,
                    model_social_behavior_count,
                    validated_social_decision,
                    validated_social_behavior_count,
                    ",".join(social_reasons) or "none",
                )
                composition = CoordinatedResponsePlan(
                    composition_id=composition_id,
                    canonical_plan_id=plan.plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
                    canonical_plan=plan,
                    response_plan=response_plan,
                    social_attention_plan=social_plan,
                    lane_coordination=lane_coordination,
                    confidence=model_output.confidence,
                    rationale=model_output.rationale,
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "task_plan_immutable": True,
                        "social_attention_validation_reasons": social_reasons,
                        "lane_coordination_validation_reasons": lane_reasons,
                        "mixed_coverage_repair_reasons": mixed_coverage_reasons,
                        "social_attention_policy": {
                            "mode": social_attention_mode,
                            "execution_enabled": social_attention_mode == "on",
                            "embodiment_independent": True,
                        },
                        "social_attention_decision_required": (social_attention_decision_required),
                        "social_attention_candidate_count": (social_attention_candidate_count),
                        "social_attention_model_decision": model_social_decision,
                        "social_attention_model_behavior_count": (model_social_behavior_count),
                        "social_attention_validated_decision": (validated_social_decision),
                        "social_attention_validated_behavior_count": (
                            validated_social_behavior_count
                        ),
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
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": contract_repair_attempted,
                        "safe_read_semantic_review": {
                            "attempted": safe_read_semantic_review_attempted,
                            "succeeded": safe_read_semantic_review_succeeded,
                            "strategy": (
                                "fast_act_reference_or_post_execution_result"
                                if pure_safe_read
                                else "model_owned_pre_evidence_speech_review"
                            ),
                        },
                        "effectful_semantic_review": {
                            "attempted": effectful_semantic_review_attempted,
                            "succeeded": effectful_semantic_review_succeeded,
                            "strategy": "model_owned_pre_execution_claim_review",
                        },
                    },
                )
                return ResponseCompositionResolution(
                    status="resolved",
                    composition=composition,
                    reason_summary="Task, speech, and an explicit social-attention decision were coordinated.",
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "contract_schema": "ResponseComposerModelOutput",
                        "social_attention_decision_required": (social_attention_decision_required),
                        "social_attention_candidate_count": (social_attention_candidate_count),
                        "social_attention_model_decision": model_social_decision,
                        "social_attention_validated_decision": (validated_social_decision),
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": contract_repair_attempted,
                        "safe_read_semantic_review_attempted": (
                            safe_read_semantic_review_attempted
                        ),
                        "safe_read_semantic_review_succeeded": (
                            safe_read_semantic_review_succeeded
                        ),
                        "effectful_semantic_review_attempted": (
                            effectful_semantic_review_attempted
                        ),
                        "effectful_semantic_review_succeeded": (
                            effectful_semantic_review_succeeded
                        ),
                        "mixed_coverage_repair_reasons": mixed_coverage_reasons,
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
                    exc, (ValidationError, json.JSONDecodeError, ValueError)
                ):
                    contract_repair_attempted = True
                    previous_raw = raw
                    initial_validation_errors = self._validation_error_json(exc)
                    continue
                fallback = self._primary_activity_fail_soft_composition(
                    request=request,
                    plan=plan,
                    composition_id=composition_id,
                    failure=exc,
                    contract_repair_attempted=contract_repair_attempted,
                )
                if fallback is not None:
                    return fallback
                logger.warning(
                    "response_composer_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s repair_raw_output_ref=%s "
                    "initial_raw_output=%s repair_raw_output=%s",
                    request.sid,
                    cognition_text_reference(previous_raw if contract_repair_attempted else None),
                    cognition_text_reference(raw if contract_repair_attempted else None),
                    self._bounded(previous_raw, 5000)
                    if contract_repair_attempted and previous_raw is not None
                    else "",
                    self._bounded(raw, 5000)
                    if contract_repair_attempted and raw is not None
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
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "safe_read_semantic_review_attempted": (
                            safe_read_semantic_review_attempted
                        ),
                        "safe_read_semantic_review_succeeded": False,
                        "effectful_semantic_review_attempted": (
                            effectful_semantic_review_attempted
                        ),
                        "effectful_semantic_review_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output_ref": cognition_text_reference(
                            previous_raw if contract_repair_attempted else None
                        ),
                        "repair_raw_output_ref": cognition_text_reference(
                            raw if contract_repair_attempted else None
                        ),
                        **integrity_metadata,
                        **failure,
                    },
                )
        raise AssertionError("unreachable")

    @classmethod
    def _primary_activity_fail_soft_composition(
        cls,
        *,
        request: AgentRunRequest,
        plan: CanonicalPlan,
        composition_id: str,
        failure: Exception,
        contract_repair_attempted: bool,
    ) -> ResponseCompositionResolution | None:
        """Preserve a validated pure execution Plan after presentation-only failure.

        Response Composer owns wording and optional lane presentation; it does not
        own the already validated Capability Plan.  When a pure, non-confirmation
        safe-read execution Plan can proceed without dynamic pre-evidence speech;
        other execution Plans require one model-authored current-turn acknowledgement
        already queued or playback-started, which is reused as the existing
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
            delivered_event_ids = {
                cls._speech_event_id(item)
                for item in cls._delivered_turn_speech(request.context)
            }
            candidate = next(
                (
                    item
                    for item in reversed(cls._scheduled_turn_speech(request.context))
                    if cls._speech_event_id(item)
                    and cls._speech_event_id(item) not in delivered_event_ids
                ),
                None,
            )
            if candidate is None:
                response_plan = ResponsePlan()
            else:
                response_plan = ResponsePlan(
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
        else:
            reusable = cls._reusable_turn_speech(request.context)
            if not reusable:
                return None
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
            if candidate is None:
                return None
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
        cls._validate_reused_turn_speech(
            response_plan,
            context=request.context,
        )
        cls._validate_pending_response_contract(
            response_plan,
            plan=plan,
            context=request.context,
        )
        social_plan = SocialAttentionPlan(
            decision="none",
            reason=(
                "Optional expression was omitted because response composition "
                "failed while the validated primary activity was preserved."
            ),
            metadata={
                "authority": "advisory",
                "fail_soft_primary_activity": True,
                "auxiliary_social_attention": True,
                "execution_permitted": False,
            },
        )
        composition = CoordinatedResponsePlan(
            composition_id=composition_id,
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=response_plan,
            social_attention_plan=social_plan,
            lane_coordination=[],
            confidence=0.0,
            rationale=(
                "Reused a scheduled acknowledgement when present, without treating "
                "it as delivered, so an optional presentation failure could not "
                "cancel the validated primary activity."
                if safe_read
                else "Reused an existing model-authored acknowledgement so an optional "
                "presentation failure could not cancel the validated primary activity."
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
                "contract_repair_attempted": contract_repair_attempted,
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
                else "Validated primary activity was preserved by reusing existing "
                "current-turn acknowledgement speech."
            ),
            metadata={
                "authority": "advisory",
                "resolver": "response_composer",
                "fail_soft_primary_activity": True,
                "pure_safe_read_fast_act_reference_only": safe_read,
                "contract_repair_attempted": contract_repair_attempted,
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

    @classmethod
    def _repair_mixed_execution_coverage(
        cls,
        response_plan: ResponsePlan,
        *,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> tuple[ResponsePlan, list[str]]:
        """Reuse reviewed current-turn speech for uncovered mixed execute Goals.

        A mixed response can legitimately use one stage for a requested spoken
        outcome and a separate, already scheduled fast acknowledgement for the
        pending Activity.  Response Composer sometimes covers only the spoken
        Goal, which must not cancel the immutable validated Activity Plan.  This
        adapter may only reference an exact scheduled/playback-started
        robot-action speech event; it never invents speech, changes a Capability,
        or covers a non-execute Goal mechanically.
        """

        if (
            plan.disposition != "mixed"
            or not plan.steps
            or cls._confirmation_required(plan, context)
            or plan.waiting_goal_ids()
        ):
            return response_plan, []
        execute_goal_ids = set(plan.executable_goal_ids())
        if not execute_goal_ids:
            return response_plan, []
        stages = [
            stage
            for stage in (
                response_plan.immediate,
                response_plan.pre_action,
                *response_plan.progress,
                response_plan.final,
            )
            if stage is not None
        ]
        covered = {goal_id for stage in stages for goal_id in stage.covers_goal_ids}
        missing = set(plan.goal_ids) - covered
        if not missing:
            return response_plan, []
        if not missing.issubset(execute_goal_ids):
            return response_plan, []
        non_execute_goal_ids = set(plan.goal_ids) - execute_goal_ids
        if not non_execute_goal_ids.issubset(covered):
            return response_plan, []

        reusable = cls._reusable_turn_speech(context)
        candidate = next(
            (
                item
                for item in reversed(reusable)
                if str(item.get("route") or "").strip() in {"", "robot_action"}
                and str(item.get("text") or "").strip()
                and cls._speech_event_id(item)
            ),
            None,
        )
        if candidate is None:
            return response_plan, []
        candidate_text = " ".join(str(candidate["text"]).strip().split())
        ordered_missing = [goal_id for goal_id in plan.goal_ids if goal_id in missing]

        for field_name in ("immediate", "pre_action"):
            stage = getattr(response_plan, field_name)
            if (
                stage is not None
                and stage.reuse_current_turn_speech
                and stage.reused_speech_event_id == cls._speech_event_id(candidate)
            ):
                updated_ids = list(dict.fromkeys([*stage.covers_goal_ids, *ordered_missing]))
                repaired = response_plan.model_copy(
                    update={field_name: stage.model_copy(update={"covers_goal_ids": updated_ids})}
                )
                return repaired, ["mixed_execute_goal_coverage_extended_from_reused_turn_speech"]

        if response_plan.pre_action is not None:
            return response_plan, []
        stage = ResponseStage(
            text=candidate_text,
            speech_act=str(candidate.get("purpose") or "acknowledge"),
            commitment_state="heard",
            must_not_claim_completion=True,
            reuse_current_turn_speech=True,
            reused_speech_event_id=cls._speech_event_id(candidate),
            covers_goal_ids=ordered_missing,
        )
        repaired = response_plan.model_copy(update={"pre_action": stage})
        cls._validate_reused_turn_speech(repaired, context=context)
        return repaired, ["mixed_execute_goal_coverage_recovered_from_scheduled_fast_speech"]

    @classmethod
    def _validate_reused_turn_speech(
        cls,
        response_plan: ResponsePlan,
        *,
        context: dict[str, Any] | None,
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
                    "pure safe-read execution may represent pending Fast speech "
                    "only as an immediate reused-speech stage"
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
                        "speech event instead of authoring another acknowledgement"
                    )
            elif response_plan.immediate is not None:
                raise ValueError(
                    "pure safe-read execution must not author dynamic pre-evidence speech"
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
        request: AgentRunRequest,
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
    def _has_effectful_goal_context(
        context: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(context, dict):
            return False

        def contains_effectful_goal(items: Any) -> bool:
            if not isinstance(items, list):
                return False
            for item in items:
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata")
                if (
                    isinstance(metadata, dict)
                    and str(metadata.get("responsibility_kind") or "").strip()
                    == "executable_action"
                ):
                    return True
            return False

        if contains_effectful_goal(context.get("active_goal_snapshots")):
            return True
        association = goal_association_prompt_projection(context)
        return bool(
            isinstance(association, dict) and contains_effectful_goal(association.get("new_goals"))
        )

    @classmethod
    def _requires_effectful_semantic_review(
        cls,
        plan: CanonicalPlan,
        context: dict[str, Any] | None,
    ) -> bool:
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
            and plan.disposition in {"execute", "mixed", "clarify", "unavailable", "refused"}
            and (cls._has_effectful_goal_context(context) or has_non_read_execution)
        )

    @staticmethod
    def _social_attention_candidate_count(
        context: dict[str, Any] | None,
    ) -> int:
        if not isinstance(context, dict):
            return 0
        values = context.get("social_attention_candidates")
        if not isinstance(values, list):
            return 0
        return sum(1 for item in values if isinstance(item, dict))

    @classmethod
    def _social_attention_decision_required(
        cls,
        context: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(context, dict):
            return False
        return (
            cls._social_attention_mode(context) != "off"
            and cls._social_attention_candidate_count(context) > 0
        )

    @classmethod
    def _validate_social_attention_decision(
        cls,
        value: Any,
        *,
        context: dict[str, Any] | None,
    ) -> None:
        if cls._social_attention_decision_required(context) and value is None:
            raise ValueError(
                "social_attention_plan is required when Social Attention policy "
                "is enabled and reviewed candidates are available; return an "
                "explicit decision=none or decision=express plan"
            )

    @staticmethod
    def _social_attention_decision(value: Any) -> str:
        if isinstance(value, SocialAttentionPlan):
            return value.decision
        if isinstance(value, dict):
            decision = str(value.get("decision") or "").strip()
            return decision or "missing"
        return "missing"

    @staticmethod
    def _social_attention_behavior_count(value: Any) -> int:
        if isinstance(value, SocialAttentionPlan):
            return len(value.behaviors)
        if isinstance(value, dict):
            behaviors = value.get("behaviors")
            return len(behaviors) if isinstance(behaviors, list) else 0
        return 0

    @staticmethod
    def _require_social_attention_decision_in_schema(
        schema: dict[str, Any],
    ) -> None:
        """Require the model's auxiliary-expression choice at decode time.

        ``SocialAttentionPlan`` keeps defaults for compatibility and policy-off
        callers. When reviewed candidates make the responsibility mandatory,
        the decoder must also require the nested semantic decision. Otherwise
        a body proposal with an omitted decision reaches Pydantic as the
        default ``none`` and fails only after decoding, leaving repair without
        an explicit model-authored choice.
        """

        required = schema.setdefault("required", [])
        if "social_attention_plan" not in required:
            required.append("social_attention_plan")
        social_schema = schema.get("properties", {}).get("social_attention_plan")
        if isinstance(social_schema, dict):
            alternatives = social_schema.get("anyOf")
            if isinstance(alternatives, list):
                non_null = [
                    item
                    for item in alternatives
                    if not (isinstance(item, dict) and item.get("type") == "null")
                ]
                if len(non_null) == 1:
                    schema["properties"]["social_attention_plan"] = non_null[0]
        social_plan_schema = schema.get("$defs", {}).get("SocialAttentionPlan")
        if isinstance(social_plan_schema, dict):
            social_required = social_plan_schema.setdefault("required", [])
            if "decision" not in social_required:
                social_required.append("decision")

    @staticmethod
    def _response_schema(
        plan: CanonicalPlan,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema = copy.deepcopy(ResponseComposerModelOutput.model_json_schema())
        schema["title"] = "ResponseComposerModelOutput"
        if ResponseComposerResolver._social_attention_decision_required(context):
            ResponseComposerResolver._require_social_attention_decision_in_schema(schema)
        goal_ids = list(dict.fromkeys(plan.goal_ids))

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    covers_goal_ids = properties.get("covers_goal_ids")
                    if isinstance(covers_goal_ids, dict):
                        covers_goal_ids["items"] = (
                            {"type": "string", "enum": goal_ids} if goal_ids else {"type": "string"}
                        )
                        if goal_ids:
                            covers_goal_ids["minItems"] = 1
                        else:
                            # Goal Association can legitimately return a
                            # clarification before a canonical goal exists.
                            # In that state an invented goal ID is never valid.
                            covers_goal_ids["maxItems"] = 0
                        covers_goal_ids["uniqueItems"] = True
                        required = node.setdefault("required", [])
                        if "covers_goal_ids" not in required:
                            required.append("covers_goal_ids")
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
                "covers_goal_ids",
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
                    # A pure safe read never authors another pre-evidence act.
                    # When Fast speech is still pending, the stage is a typed
                    # reference that lets Runtime reuse its exact delivery or
                    # fulfill the same act if that delivery never starts.
                    pending_speech = (
                        ResponseComposerResolver._pending_scheduled_turn_speech(context)
                    )
                    response_properties["immediate"] = (
                        {"$ref": "#/$defs/ResponseStage"}
                        if pending_speech
                        else {"type": "null"}
                    )
                    response_properties["pre_action"] = {"type": "null"}
                    if pending_speech and "immediate" not in response_required:
                        response_required.append("immediate")
                    elif not pending_speech and "immediate" in response_required:
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
    def _pending_action_claim_errors(
        response_plan: ResponsePlan,
        *,
        plan: CanonicalPlan,
    ) -> list[str]:
        if not plan.steps:
            return []
        pending_skill_ids = [step.skill_id for step in plan.steps]
        stage_items = [
            ("immediate", response_plan.immediate),
            ("pre_action", response_plan.pre_action),
            *[("progress", stage) for stage in response_plan.progress],
            ("final", response_plan.final),
        ]
        errors: list[str] = []
        for phase, stage in stage_items:
            if stage is None or not stage.must_not_claim_completion:
                continue
            claims = pending_action_stage_direction_claims(
                stage.text,
                pending_skill_ids,
            )
            if claims:
                errors.append(
                    "pending physical action stage direction claims completion: "
                    f"{phase}:" + ",".join(claims)
                )
        return errors

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
        if association.clarification or association.associations or not association.new_goals:
            return None
        if any(
            str((goal.metadata or {}).get("responsibility_kind") or "") != "spoken_response"
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
        request: AgentRunRequest,
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
        request: AgentRunRequest,
        association: GoalAssociationResolution,
    ) -> ResponseCompositionResolution:
        goal_ids = self._direct_goal_ids(association)
        response_schema = self._direct_response_schema(goal_ids, request.context)
        previous_raw: Any = None
        validation_errors = ""
        repair_attempted = False
        for attempt in range(2):
            raw: Any = None
            try:
                raw = await self.ollama.generate(
                    self._direct_prompt(
                        request,
                        association,
                        previous_raw=previous_raw,
                        validation_errors=validation_errors,
                    ),
                    system=(
                        self._repair_system_prompt() if repair_attempted else self._system_prompt()
                    ),
                    options={
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                    },
                    response_format=response_schema,
                    prompt_family=(
                        "response_composer.direct_repair"
                        if repair_attempted
                        else "response_composer.direct_primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ValueError("response composer output is not a JSON object")
                raw = self._canonicalize_optional_social_attention_payload(raw)
                output = ResponseComposerModelOutput.model_validate(raw)
                self._validate_social_attention_decision(
                    output.social_attention_plan,
                    context=request.context,
                )
                self._validate_direct_response_plan(
                    output.response_plan,
                    goal_ids=goal_ids,
                )
                self._validate_spoken_language(output.response_plan, request=request)
                social_plan, social_reasons = self._validated_social_plan(
                    output.social_attention_plan,
                    plan=None,
                    context=request.context,
                )
                if output.lane_coordination:
                    raise ValueError(
                        "planless direct responses cannot declare cross-lane coordination"
                    )
                composition = DirectResponseComposition(
                    composition_id=self._direct_composition_id(request, association),
                    goal_association_fingerprint=(goal_association_fingerprint(association)),
                    goal_association=association,
                    response_plan=output.response_plan,
                    social_attention_plan=social_plan,
                    confidence=output.confidence,
                    rationale=output.rationale,
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "planless_direct_response": True,
                        "goal_association_immutable": True,
                        "social_attention_validation_reasons": social_reasons,
                        "contract_schema": "ResponseComposerModelOutput",
                        "contract_repair_attempted": repair_attempted,
                        "contract_repair_succeeded": repair_attempted,
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
                        "contract_repair_attempted": repair_attempted,
                        "contract_repair_succeeded": repair_attempted,
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
                    exc, (ValidationError, json.JSONDecodeError, ValueError)
                ):
                    repair_attempted = True
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
                        "contract_repair_attempted": repair_attempted,
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
        if ResponseComposerResolver._social_attention_decision_required(context):
            ResponseComposerResolver._require_social_attention_decision_in_schema(schema)
        stage_schema = schema.get("$defs", {}).get("ResponseStage")
        if isinstance(stage_schema, dict):
            required = stage_schema.setdefault("required", [])
            for name in (
                "text",
                "speech_act",
                "commitment_state",
                "must_not_claim_completion",
                "covers_goal_ids",
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
                covers["items"] = {"type": "string", "enum": goal_ids}
                covers["minItems"] = len(goal_ids)
                covers["maxItems"] = len(goal_ids)
                covers["uniqueItems"] = True
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
        request: AgentRunRequest,
        association: GoalAssociationResolution,
        *,
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> str:
        repair = ""
        if previous_raw is not None:
            repair = (
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
            "identity facts. Social Attention remains optional auxiliary expression "
            "under the supplied policy. When Social Attention is enabled and candidates "
            "exist, return a structurally complete decision: decision=express requires "
            "at least one supplied behavior or speech_expression.mode=adapt; a reason "
            "alone is invalid.\n\n"
            + repair
            + "Return JSON with response_plan, social_attention_plan, lane_coordination=[], confidence, "
            "and rationale only."
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
    def _composition_id(request: AgentRunRequest, plan: CanonicalPlan) -> str:
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
    def _candidate_map(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key in ("capability_candidates", "social_attention_candidates"):
            values = context.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                capability_id = str(item.get("capability_id") or "").strip()
                if capability_id:
                    out[capability_id] = item
        return out

    def _validated_social_plan(
        self,
        value: Any,
        *,
        plan: CanonicalPlan | None,
        context: dict[str, Any],
    ) -> tuple[SocialAttentionPlan | None, list[str]]:
        mode = self._social_attention_mode(context)
        if mode == "off":
            return None, (["policy_off"] if value is not None else [])
        if value is None:
            return None, (
                ["missing_social_attention_decision"]
                if self._social_attention_decision_required(context)
                else []
            )
        try:
            proposed = SocialAttentionPlan.model_validate(value)
        except ValidationError as exc:
            return None, [f"invalid_social_attention_plan:{type(exc).__name__}"]

        metadata = dict(proposed.metadata)
        metadata.update(
            {
                "authority": "advisory",
                "auxiliary_social_attention": True,
                "behavior_domain": proposed.behavior_domain,
                "interaction_role": proposed.interaction_role,
                "purpose": proposed.purpose,
                "speech_expression": proposed.speech_expression.model_dump(
                    mode="json", exclude_none=True
                ),
                "policy_mode": mode,
                "execution_permitted": mode == "on",
                "embodiment_independent": True,
            }
        )
        if proposed.decision == "none":
            return proposed.model_copy(update={"metadata": metadata}), []

        reasons: list[str] = []
        target_reason = self._validate_target(proposed, context)
        if target_reason:
            reasons.append(target_reason)

        candidates = self._candidate_map(context)
        primary_ids = {step.skill_id for step in plan.steps} if plan is not None else set()
        validated_behaviors: list[SocialAttentionBehavior] = []
        seen: set[str] = set()
        for behavior in proposed.behaviors:
            if behavior.timing != "parallel":
                reasons.append(f"auxiliary_must_be_parallel:{behavior.skill_id}")
                continue
            candidate = candidates.get(behavior.skill_id)
            if candidate is None:
                reasons.append(f"unknown_social_skill:{behavior.skill_id}")
                continue
            if behavior.skill_id in primary_ids or behavior.skill_id in seen:
                reasons.append(f"duplicate_or_primary_skill:{behavior.skill_id}")
                continue
            if (
                candidate.get("available") is False
                or candidate.get("interaction_executable") is not True
            ):
                reasons.append(f"unavailable_social_skill:{behavior.skill_id}")
                continue
            if bool(candidate.get("requires_confirmation")):
                reasons.append(f"confirmation_required:{behavior.skill_id}")
                continue
            schema = candidate.get("input_schema")
            if not isinstance(schema, dict):
                schema = {}
            target_args_reason = self._validate_target_args(behavior.args, schema, context)
            if target_args_reason:
                reasons.append(f"target_error:{behavior.skill_id}:{target_args_reason}")
                continue
            args, _ = normalize_args_for_schema(behavior.args, schema)
            errors = validate_args_for_schema(args, schema)
            if errors:
                reasons.append(f"invalid_args:{behavior.skill_id}:{'; '.join(errors)}")
                continue
            if self._conflicts_with_primary(plan, candidate, candidates, behavior.timing):
                reasons.append(f"resource_conflict:{behavior.skill_id}")
                continue
            validated_behaviors.append(behavior.model_copy(update={"args": args}))
            seen.add(behavior.skill_id)

        speech_adaptation_selected = proposed.speech_expression.mode == "adapt"
        if target_reason:
            validated_behaviors = []
        if not validated_behaviors and not speech_adaptation_selected:
            none_plan = SocialAttentionPlan(
                purpose=proposed.purpose,
                decision="none",
                confidence=proposed.confidence,
                reason="Optional attention was omitted after deterministic validation.",
                metadata={**metadata, "validation_reasons": reasons},
            )
            return none_plan, reasons
        return proposed.model_copy(
            update={
                "behaviors": validated_behaviors,
                "metadata": {**metadata, "validation_reasons": reasons},
            }
        ), reasons

    @staticmethod
    def _canonicalize_optional_social_attention_payload(
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        """Fail soft on contradictory empty or none auxiliary expression.

        Social Attention is auxiliary presentation, never execution authority. A
        model output that chooses ``express`` but supplies neither a body behavior
        nor ``speech_expression.mode=adapt`` has no executable semantic member.
        Conversely, an explicit ``none`` decision cannot authorize optional body
        behavior or adapted speech. Normalize either contradiction to stillness
        before nested Pydantic validation, preserving the immutable primary Plan
        without selecting an auxiliary behavior on the model's behalf.
        """

        normalized = copy.deepcopy(raw)
        value = normalized.get("social_attention_plan")
        if not isinstance(value, dict):
            return normalized
        decision = str(value.get("decision") or "").strip()
        behaviors = value.get("behaviors")
        has_behavior = isinstance(behaviors, list) and any(
            isinstance(item, dict) for item in behaviors
        )
        speech_expression = value.get("speech_expression")
        speech_mode = (
            str(speech_expression.get("mode") or "").strip()
            if isinstance(speech_expression, dict)
            else ""
        )
        if decision == "none" and (has_behavior or speech_mode == "adapt"):
            metadata = value.get("metadata")
            value["behaviors"] = []
            value["speech_expression"] = {"mode": "none"}
            value["metadata"] = {
                **(metadata if isinstance(metadata, dict) else {}),
                "canonicalized_conflicting_none_expression": True,
                "authority": "advisory",
                "auxiliary_social_attention": True,
            }
            return normalized
        if decision != "express":
            return normalized
        if has_behavior or speech_mode == "adapt":
            return normalized
        confidence = value.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = 0.0
        confidence = min(1.0, max(0.0, float(confidence)))
        normalized["social_attention_plan"] = {
            "decision": "none",
            "purpose": "neutral_presence",
            "confidence": confidence,
            "reason": (
                "Optional social expression was omitted because the model selected "
                "express without an executable behavior or speech adaptation."
            ),
            "metadata": {
                "canonicalized_empty_expression": True,
                "authority": "advisory",
                "auxiliary_social_attention": True,
            },
        }
        return normalized

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
        allowed_lanes = {"speaking", "activity", "social_attention"}
        parallel_speaking_step_ids = {
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
            if "speaking" in lanes:
                for value in values_list(item.get("speaking_step_ids")):
                    step_id = str(value).strip()
                    if (
                        step_id
                        and step_id in parallel_speaking_step_ids
                        and step_id not in speaking_ids
                    ):
                        speaking_ids.append(step_id)
                if (
                    not speaking_ids
                    and len(parallel_speaking_step_ids) == 1
                    and len(
                        [
                            group
                            for group in groups
                            if isinstance(group, dict)
                            and "speaking" in values_list(group.get("lanes"))
                        ]
                    )
                    == 1
                ):
                    speaking_ids = sorted(parallel_speaking_step_ids)
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
            if "speaking" in lanes and speaking_ids:
                cleaned["speaking_step_ids"] = speaking_ids
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

        respond_goal_ids = {
            outcome.goal_id for outcome in plan.goal_outcomes if outcome.disposition == "respond"
        }
        stages = cls._raw_response_stages(normalized.get("response_plan"))
        for group in valid_groups:
            lanes = {str(value).strip() for value in group.get("lanes") or []}
            coordination_id = " ".join(str(group.get("coordination_id") or "").strip().split())
            if "speaking" not in lanes or not coordination_id:
                continue
            if group.get("speaking_step_ids"):
                continue
            if any(
                str(stage.get("coordination_id") or "").strip() == coordination_id
                for stage in stages
            ):
                continue
            candidates = []
            for stage in stages:
                covered = {
                    str(value).strip()
                    for value in stage.get("covers_goal_ids") or []
                    if str(value).strip()
                }
                if not covered.intersection(respond_goal_ids):
                    continue
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
        social_attention_plan: SocialAttentionPlan | None,
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
        social_ids: set[str] = set()
        if social_attention_plan is not None:
            social_ids = {
                str(item.coordination_id or "").strip()
                for item in social_attention_plan.behaviors
                if str(item.coordination_id or "").strip()
            }
        parallel_speaking_steps = {
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
            speaking_step_ids = [
                step_id for step_id in group.speaking_step_ids if step_id in parallel_speaking_steps
            ]
            if "speaking" in group.lanes and (
                group.coordination_id in speech_ids or speaking_step_ids
            ):
                lanes.append("speaking")
            if (
                "activity" in group.lanes
                and group.activity_step_ids
                and set(group.activity_step_ids).issubset(parallel_activity_steps)
            ):
                lanes.append("activity")
            if "social_attention" in group.lanes and group.coordination_id in social_ids:
                lanes.append("social_attention")
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
                        "speaking_step_ids": (speaking_step_ids if "speaking" in lanes else []),
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

    @staticmethod
    def _social_attention_mode(context: dict[str, Any]) -> str:
        policy = context.get("social_attention_policy")
        raw = str(policy.get("mode") if isinstance(policy, dict) else "off").strip().lower()
        return raw if raw in {"off", "report_only", "on"} else "off"

    @staticmethod
    def _validate_target(plan: SocialAttentionPlan, context: dict[str, Any]) -> str | None:
        if plan.target.source == "none":
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "attention_target_not_available"
        evidence_source = str(evidence.get("source") or "none")
        if plan.target.source != evidence_source:
            return "attention_target_source_mismatch"
        target = evidence.get("target")
        if not isinstance(target, dict):
            target = {}
        expected_ref = str(target.get("target_ref") or "").strip()
        if expected_ref and plan.target.target_ref != expected_ref:
            return "attention_target_ref_mismatch"
        expected_direction = str(target.get("relative_direction") or "").strip()
        claimed_direction = str(plan.target.relative_direction or "").strip()
        if expected_direction and claimed_direction and expected_direction != claimed_direction:
            return "attention_target_direction_mismatch"
        return None

    @staticmethod
    def _validate_target_args(
        args: dict[str, Any],
        schema: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        semantic_keys = {"direction", "relative_direction", "target_ref"}
        if not semantic_keys.intersection(args):
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "targeted behavior requires semantic target evidence"
        target = evidence.get("target")
        if not isinstance(target, dict):
            return "targeted behavior requires semantic target evidence"
        expected_direction = str(target.get("relative_direction") or "").strip()
        actual_direction = str(
            args.get("relative_direction") or args.get("direction") or ""
        ).strip()
        if expected_direction and actual_direction and expected_direction != actual_direction:
            return "direction does not match semantic target evidence"
        expected_ref = str(target.get("target_ref") or "").strip()
        actual_ref = str(args.get("target_ref") or "").strip()
        if expected_ref and actual_ref and expected_ref != actual_ref:
            return "target_ref does not match semantic target evidence"
        return None

    @staticmethod
    def _resource_set(candidate: dict[str, Any]) -> set[str]:
        return {
            str(value).strip()
            for value in candidate.get("resource_claims") or []
            if str(value).strip()
        }

    def _conflicts_with_primary(
        self,
        plan: CanonicalPlan | None,
        social_candidate: dict[str, Any],
        candidates: dict[str, dict[str, Any]],
        timing: str,
    ) -> bool:
        if plan is None or not plan.steps:
            return False
        if timing != "parallel":
            return True
        if social_candidate.get("can_run_parallel") is False:
            return True
        social_group = str(social_candidate.get("exclusive_group") or "")
        social_resources = self._resource_set(social_candidate)
        social_declared = bool(social_candidate.get("parallel_metadata_declared"))
        for step in plan.steps:
            other = candidates.get(step.skill_id)
            if other is None:
                return True
            if other.get("can_run_parallel") is False:
                return True
            other_group = str(other.get("exclusive_group") or "")
            if social_group and other_group and social_group == other_group:
                return True
            if social_resources.intersection(self._resource_set(other)):
                return True
            if not (social_declared and bool(other.get("parallel_metadata_declared"))):
                return True
        return False

    def _prompt(
        self,
        request: AgentRunRequest,
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
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 6000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Speech already delivered in this current turn JSON (playback-started conversational context, never external-fact evidence):\n{self._bounded(self._delivered_turn_speech(context), 3600)}\n\n"
            f"Fast speech already scheduled in this current turn JSON (queued communicative commitment for de-duplication only; not proof that the user heard it and never external-fact or completion evidence):\n{self._bounded(self._scheduled_turn_speech(context), 2400)}\n\n"
            f"Pending execution capability semantics JSON:\n{self._bounded(context.get('execution_capabilities') or [], 3000)}\n\n"
            f"Recent conversation JSON:\n{self._bounded((context.get('history') or request.history or [])[-6:], 2600)}\n\n"
            f"Social-attention policy JSON:\n{self._bounded(context.get('social_attention_policy') or {'mode': 'off'}, 800)}\n\n"
            f"Owner-approved Social Interaction Style JSON:\n{self._bounded(context.get('social_interaction_style') or {}, 5000)}\n\n"
            f"Recent auxiliary-behavior evidence JSON:\n{self._bounded(context.get('recent_auxiliary_behavior_evidence') or [], 5000)}\n\n"
            f"Social-attention candidates JSON:\n{self._bounded(context.get('social_attention_candidates') or [], 8000)}\n\n"
            f"Attention target evidence JSON:\n{self._bounded(context.get('social_attention_target_evidence') or {'available': False}, 2500)}\n\n"
            f"Previous Response Composer output when revising:\n{self._bounded(previous_raw, 5000) if previous_raw is not None else 'null'}\n\n"
            f"Exact contract validation errors when revising:\n{validation_errors or '[]'}\n\n"
            "Compose one ResponsePlan, one explicit social-attention decision, and zero or more typed lane-coordination groups. When Social Attention policy is enabled and the candidate list is non-empty, social_attention_plan must be a SocialAttentionPlan with decision=express or decision=none; never omit it or return null. decision=express is structurally valid only when it contains at least one supplied body behavior or speech_expression.mode=adapt. A reason alone is not expression. When a requested action already owns a capability, do not duplicate that same capability as auxiliary Social Attention. If a proposed body expression conflicts with primary Activity, choose another eligible untargeted candidate, adapt the response style, or return decision=none with a concrete scene reason. When policy is off or the candidate list is empty, return social_attention_plan=null. "
            "The CanonicalPlan is immutable: do not alter, replace, add, remove, reorder, authorize, or execute its steps. The verified tool-memory index contains provenance and bound arguments only, not answer facts. It may support honest wording that Chromie recently checked an exact matching subject and is retrieving it, but never state the remembered result before the memory retrieval step returns evidence. Conversation context may ground ordinary conversational repair, but never claim external facts without executed evidence. Answer the user's requested judgment or decision directly before supporting detail, and naturally acknowledge a prior context failure when the current turn calls for repair. "
            "Ground every user-specific statement in the newest turn, active Goals, or supplied conversation context. Do not invent the user's plans, schedule, preferences, relationships, experiences, feelings, or circumstances to make a response sound helpful. When a friendly supporting reason is useful but no personal fact was supplied, phrase it generally. "
            "For a retained completed external-result Goal, treat delivered evidence-bound dialogue as the only supplied factual projection. Preserve every measurement and condition from the immutable plan and that dialogue exactly; do not substitute, infer, or embellish external details. The newest user turn remains the conversational target: when it is a reaction, feeling, acknowledgement, evaluation, or practical decision, respond to that act first and use prior facts only as useful support. Never replace the current intent with a replay of the old answer. Omit supporting detail when a direct judgment is sufficient. "
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "The explicit Language hint is authoritative for spoken output unless the user explicitly asks for translation or a different language. When it is zh-CN, speak Chinese only; do not mirror a bilingual greeting, switch to English, or follow the language of identity/internal context. "
            "Every plan goal_id must be covered exactly through response stage covers_goal_ids; do not invent goal IDs. "
            "For a terminal respond plan, emit exactly one final stage, omit immediate/pre_action/progress, set commitment_state=completed, and set must_not_claim_completion=false. This marks the conversational response itself as complete; it does not claim that an unexecuted action occurred. Greeting wording and length are ordinary model-authored conversational choices; use the full scene, recent relationship context, and owner-approved personality without a fixed greeting template or Host-imposed brevity target. "
            "For execute plans this is pre-execution composition. Effectful or confirmation-bound work must emit an immediate and/or pre_action stage covering every canonical goal, use only none/heard/evaluating/waiting_for_user commitments, set must_not_claim_completion=true, omit progress and final, and phrase the speech naturally. "
            "When the CanonicalPlan or supplied execution capability semantics require confirmation, explain any supplied adjustment or alternative without claiming it started, ask the user to approve it, set speech_act=ask_confirmation and commitment_state=waiting_for_user, and do not imply that approval has already been granted. "
            "Speech already delivered in this current turn is part of the live conversation. Judge its meaning, not its wording. Do not repeat or lightly paraphrase a communicative responsibility the user has already heard. You may supplement it when it covered only part of the current plan, and you may correct it when the later canonical interpretation makes it misleading. Fast speech marked scheduled is a queued current-turn communicative commitment: do not author another acknowledgement with the same semantic job while it is starting, but never treat scheduled status as proof that the user heard it or as external-fact, execution, or completion evidence. When an existing delivered or scheduled acknowledgement adequately covers pending work, reference its speech_event_id in reused_speech_event_id, copy its text only as a playback-integrity field, set reuse_current_turn_speech=true, set speech_act to the event purpose, and add the current canonical goal IDs. That stage is a structured reference to an existing conversational act, not a request to speak it again. Use reuse_current_turn_speech=false and omit reused_speech_event_id for any supplement, correction, confirmation question, result, or failure. De-duplication is based on structured act identity and delivery status, never string similarity, keyword matching, or a fixed fast-speech suppression rule. "
            "For a pure execute plan whose pending capabilities are all safe_read or external_read, never author another pre-evidence act. If scheduled Fast speech has not reached playback_started, represent that exact event as one immediate reused-speech stage so Runtime can reuse its delivery or fulfill the act if delivery fails; otherwise immediate, pre_action, progress, and final must all be absent. The post-execution tool-result interpreter owns the factual answer. A mixed plan with an independent respond responsibility may still require model-authored speech; that speech must cover only the respond responsibility and must not state any pending measurement, condition, recommendation, or conclusion before matching trusted evidence exists. Do not mention internal tools, APIs, execution, backend, evidence IDs, or memory implementation. "
            "For mixed plans, coordinate executable and conversational goals in one natural response: use prospective wording for pending physical steps, do not narrate them with stage directions such as *Blinks twice*, do not claim completion, omit final while work is pending, and include a specific waiting_for_user clarification stage for every clarify outcome. "
            "Chromie has one Cognitive Core and three concurrent execution lanes: social_attention proposes optional social expression, speaking delivers model-authored communication and exact provider-qualified vocal performance, and activity executes non-speech provider work. chromie.vocal.perform is a Speaking-lane provider step, never response transport and never an Activity step. The exact chromie.media.* family is persistent Activity-lane playback/control, never Speaking or vocal-performance evidence. Media may share the physical speaker with Speaking only under its declared duck_media_during_speaking mixer policy; describing that overlap must not mutate either Goal, playback identity, or cancellation scope. An optional acknowledgement about pending vocal or media work remains ordinary chromie.speak delivery and is not provider completion evidence. lane_coordination describes execution overlap only; it never creates another mind, selects a provider, authorizes an effect, or weakens provider safety. Use a lane_coordination group only when the current meaning genuinely requires or benefits from overlap across at least two lanes. Copy an already-parallel chromie.vocal.perform step into speaking_step_ids; copy only already-parallel non-speech provider steps, including chromie.media.play, into activity_step_ids. A coordinated response stage may supply the speaking member only when no provider speaking_step_ids are present; it must copy the same coordination_id and use delivery_role=activity_companion or performance. A coordinated social behavior must copy that coordination_id. Ordinary pre-action acknowledgement remains delivery_role=response with no coordination_id and keeps the playback-start barrier. Never coordinate ask_confirmation or waiting_for_user speech with effect execution. The maintained start policy is best_effort_parallel and the failure policy is independent; do not imply synchronized starts or atomic cross-provider cancellation. "
            "For clarify, emit exactly one final clarification stage that names the actual unresolved need naturally; do not add a second acknowledgement, progress line, promise, or status sentence. That stage must set speech_act=clarify or ask_clarification and commitment_state=waiting_for_user as direct fields, never inside metadata; waiting_for_user is a commitment_state, not a speech_act. When the CanonicalPlan has no goal_ids, every covers_goal_ids list must be empty. For alternatives, explain the change and request approval. "
            "Social attention is a high-level auxiliary behavior domain, never a user goal or task step and never a replacement for one. The supplied social_attention_policy is authoritative: mode=off requires social_attention_plan=null and no independently added auxiliary styling; report_only may retain an advisory plan but cannot authorize body execution; on may select any supplied reviewed candidate without reasoning about simulator or physical backend metadata. Set behavior_domain=social_attention and interaction_role=auxiliary_expression. Follow the owner-approved Social Interaction Style as an active preference rather than decorative context; use recent auxiliary-behavior evidence for cooldown and repetition restraint, but never treat accepted-request evidence as proof that a behavior completed. Do not default to decision=none merely because speech alone could complete the task. Under a courteous style, meaningful direct engagement is positive scene evidence for subtle embodiment. When policy is on, at least one untargeted eligible candidate exists, and the supplied recent evidence contains no cooldown, repetition, conflict, emergency, explicit-action priority, or other concrete restraint, normally prefer decision=express with one subtle behavior for a social opening or acknowledgement. This remains semantic scene judgment, not phrase matching or a fixed gesture rule. A generic claim that expression is unnecessary solely because speech is sufficient is not a concrete restraint. Infer a scene-specific purpose such as listening, acknowledgement, engagement, empathy, turn-taking, or deference. The actual ResponsePlan text must reflect any permitted speech_expression adaptation; do not put a second answer inside SocialAttentionPlan and do not add speech merely to announce an auxiliary behavior. Select body behaviors only from the supplied social-attention candidates, require timing=parallel, and use decision=none with a concrete scene-specific reason when neutral language and stillness are more natural, safer, unsupported, repetitive, or unnecessary. Explicit user actions, emergency handling, response speech, and primary task execution always have priority. "
            "response_plan must be a JSON object with only immediate, pre_action, progress, and final fields; it is never a bare list. "
            "The decoder enforces the exact ResponseComposerModelOutput JSON Schema. Return JSON with response_plan, social_attention_plan, lane_coordination, confidence, and rationale only."
        )

    def _safe_read_semantic_review_prompt(
        self,
        *,
        request: AgentRunRequest,
        plan: CanonicalPlan,
        candidate: ResponseComposerModelOutput,
    ) -> str:
        return (
            "Independently review the candidate Response Composer DTO and return "
            "the complete final DTO as JSON. The immutable CanonicalPlan still "
            "contains a pending safe read, and no result from that pending read "
            "exists at this composition boundary. This review trigger is "
            "mechanical; the semantic judgment and revised wording belong to you.\n\n"
            "Review the meaning of every immediate spoken sentence. It may "
            "naturally acknowledge the request, a correction, or that Chromie is "
            "checking. It must not state or imply any measurement, observed "
            "condition, recommendation, conclusion, or completed lookup. Prior "
            "dialogue and another Goal's delivered result are not factual evidence "
            "for the pending Goal, even when the current Goal changes only one "
            "binding. Do not infer that a result exists from a location correction "
            "or from the presence of a verified-memory index.\n\n"
            "Speech already delivered in this current turn is authoritative "
            "conversation context about what the user has heard, but it is not "
            "evidence for the pending external result. Fast speech marked scheduled "
            "is not proof that the user heard it, but it is a queued communicative "
            "commitment that must not be duplicated while playback starts. Decide "
            "whether delivered or scheduled speech already adequately fulfills the "
            "pending-work acknowledgement. If so, reference its speech_event_id in "
            "reused_speech_event_id, copy its text only as a playback-integrity field "
            "into response_plan.immediate, set reuse_current_turn_speech=true and "
            "speech_act to the event purpose, and cover the current Goal IDs without "
            "requesting another utterance. If it was incomplete or later context makes it misleading, author only "
            "the useful supplement or correction.\n\n"
            "Use semantic reasoning rather than keyword, number, punctuation, "
            "phrase, or lexical-overlap tests. If the candidate already contains "
            "only truthful and still-needed pre-evidence acknowledgement, preserve "
            "its natural wording. Otherwise omit, supplement, or revise it according "
            "to the delivered conversational context. "
            "Preserve the immutable Goal coverage and return a valid explicit "
            "social-attention decision under the supplied DTO schema. Do not add "
            "facts or task steps.\n\n"
            f"Authoritative user turn:\n{request.text}\n\n"
            "Authoritative effectful Goal context JSON:\n"
            f"{self._bounded(request.context.get('active_goal_snapshots') or goal_association_prompt_projection(request.context), 7000)}\n\n"
            "Speech already delivered in this current turn JSON:\n"
            f"{self._bounded(self._delivered_turn_speech(request.context), 3600)}\n\n"
            "Fast speech already scheduled in this current turn JSON (de-duplication only):\n"
            f"{self._bounded(self._scheduled_turn_speech(request.context), 2400)}\n\n"
            "Immutable CanonicalPlan JSON:\n"
            f"{self._bounded(plan.prompt_projection(), 14000)}\n\n"
            "Candidate Response Composer DTO JSON:\n"
            f"{self._bounded(candidate.model_dump(mode='json'), 7000)}\n\n"
            "Return only the complete ResponseComposerModelOutput JSON object."
        )

    def _effectful_semantic_review_prompt(
        self,
        *,
        request: AgentRunRequest,
        plan: CanonicalPlan,
        candidate: ResponseComposerModelOutput,
    ) -> str:
        return (
            "Independently review the candidate Response Composer DTO for pending "
            "effectful work and return the complete final DTO as JSON. This review "
            "happens before execution evidence exists. Keep the immutable Plan and "
            "its supplied Capability semantics unchanged.\n\n"
            "Every spoken claim must stay within what the immutable Plan actually "
            "authorizes. Do not promise success, safety, an exact physical distance, "
            "object acquisition, carrying, a return trip, or any other responsibility "
            "that lacks an owned executable step and matching Capability semantics. "
            "Identity affects expression only; a person's age, family role, personality, or self-concept never proves "
            "a physical ability. Do not say that movement has started. Do not turn "
            "internal safety checks, route checks, plans, providers, or execution "
            "states into ordinary speech.\n\n"
            "When the Plan contains unavailable, refused, or clarification outcomes, "
            "state the limitation or question naturally instead of promising the whole "
            "request. If the Plan has no executable steps, speech must not narrate, role-play, "
            "or imply that any requested physical action is happening. If the spoken text "
            "asks the user to approve an action or supported subset, its typed speech_act "
            "must be ask_confirmation and commitment_state must be waiting_for_user, and the "
            "immutable Plan must itself require confirmation; otherwise remove the approval "
            "question and state the supported and unsupported scope without implying execution. "
            "The typed speech_act and commitment_state must match the actual communicative "
            "function of the sentence. Do not tell the user to wait while Chromie learns a new "
            "physical ability during the current turn. When current-turn speech already gave an "
            "adequate generic acknowledgement, or fast speech already scheduled that same acknowledgement, do not repeat it. Instead reference that speech_event_id in reused_speech_event_id, copy its text only as a playback-integrity field into immediate or pre_action, set reuse_current_turn_speech=true and speech_act to the event purpose, and cover the current Goal IDs so Runtime can reuse its delivery barrier without scheduling duplicate audio. Use concrete everyday wording "
            "that sounds like Chromie, not customer service or a machine status message. Never "
            "guarantee that an effectful action will be completed safely. Use semantic reasoning, "
            "not phrase matching. Preserve valid goal coverage and the explicit social-attention "
            "decision.\n\n"
            f"Authoritative user turn:\n{request.text}\n\n"
            "Speech already delivered in this current turn JSON:\n"
            f"{self._bounded(self._delivered_turn_speech(request.context), 3600)}\n\n"
            "Fast speech already scheduled in this current turn JSON (de-duplication only; never execution evidence):\n"
            f"{self._bounded(self._scheduled_turn_speech(request.context), 2400)}\n\n"
            "Pending execution Capability semantics JSON:\n"
            f"{self._bounded(request.context.get('execution_capabilities') or [], 6000)}\n\n"
            "Immutable CanonicalPlan JSON:\n"
            f"{self._bounded(plan.prompt_projection(), 14000)}\n\n"
            "Candidate Response Composer DTO JSON:\n"
            f"{self._bounded(candidate.model_dump(mode='json'), 7000)}\n\n"
            "Return only the complete ResponseComposerModelOutput JSON object."
        )

    @staticmethod
    def _effectful_semantic_review_system_prompt() -> str:
        return (
            "You are Chromie's independent pre-execution claim reviewer. Use model "
            "reasoning to keep speech childlike, truthful, and strictly bounded by "
            "the immutable Plan and supplied Capability semantics. Identity affects "
            "expression only, never ability. At this boundary no pending body action "
            "has started. Judge the ordinary sentence meaning, not only typed fields: "
            "wording that places Chromie already inside an ongoing movement must be "
            "rewritten prospectively before approval. Host code does not inspect wording or "
            "make the semantic judgment. Return JSON only."
        )

    @staticmethod
    def _safe_read_semantic_review_system_prompt() -> str:
        return (
            "You are Chromie's independent pre-evidence speech semantic reviewer. "
            "A pending safe read has no current result yet. Use model reasoning to "
            "keep only truthful acknowledgement while preserving the typed "
            "Response Composer contract. Host code does not inspect words or make "
            "this semantic choice. Return JSON only."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Response Composer. Coordinate truthful language expression, optional social-attention proposals, and typed speaking/activity overlap around an immutable CanonicalPlan using one Cognitive Core. When policy is enabled and reviewed candidates exist, always choose decision=none or decision=express instead of omitting the responsibility. "
            "You do not plan tasks, mutate goals, execute, authorize, or claim unobserved completion. Return JSON only."
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You revise one Response Composer output using the immutable CanonicalPlan, exact validation errors, and the supplied ResponseComposerModelOutput JSON Schema. "
            "Preserve truthful wording, the explicit Language hint, goal coverage, and valid model-authored conversational style, but correct the JSON structure and coordination invariants. The spoken text must actually use the authoritative language rather than merely describing it. Put speech_act, commitment_state, must_not_claim_completion, covers_goal_ids, coordination_id, delivery_role, reuse_current_turn_speech, and reused_speech_event_id directly on each response stage, never in metadata. For terminal respond, use exactly one final stage with commitment_state=completed and must_not_claim_completion=false. Do not shorten or rewrite otherwise valid speech merely to satisfy a Host style preference. For execute and mixed plans with pending effectful steps, use immediate and/or pre_action, omit progress and final, and keep must_not_claim_completion=true. A pure execute Plan whose pending capabilities are all safe_read or external_read must never author another pre-evidence act. If a scheduled Fast event has not reached playback_started, reference it as one immediate stage using its speech_event_id, exact text, purpose, and reuse_current_turn_speech=true; otherwise emit no response stage. For other pending work, if delivered or scheduled current-turn speech already adequately provided the acknowledgement, reference its speech_event_id in reused_speech_event_id and set reuse_current_turn_speech=true; Runtime will reuse that exact event instead of speaking it twice. Otherwise author only a required supplement or correction with reuse_current_turn_speech=false and no reused_speech_event_id. When the CanonicalPlan or supplied execution capability semantics require confirmation, explain any supplied adjustment or alternative, ask for approval with speech_act=ask_confirmation and commitment_state=waiting_for_user, and never claim that the action started. Confirmation or waiting speech must never join a lane_coordination group. Use lane_coordination only for best-effort overlap across speaking, activity, and optional social_attention lanes, with exact parallel CanonicalPlan step IDs and matching coordination_id values on participating speech stages or social behaviors. For clarification, emit exactly one final stage with speech_act=clarify or ask_clarification and commitment_state=waiting_for_user. When Social Attention policy is enabled and reviewed candidates exist, social_attention_plan must be an explicit decision=none or decision=express object and must not be omitted or null; null is reserved for policy off or an empty candidate list. decision=express requires at least one supplied behavior or speech_expression.mode=adapt. Never repeat a primary user-requested capability as auxiliary Social Attention; use another eligible behavior, speech adaptation, or decision=none. Return only the corrected JSON object."
        )
