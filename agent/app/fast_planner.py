from __future__ import annotations

from .goal_progress_communication import goal_progress_communication_prompt
import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import re
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
    owner_approved_identity_context,
    owner_approved_personality_context,
)
from .planner_contract import (
    EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
    PlannerDTOContractError,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
    canonical_goal_binding_argument_response_schema,
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
    normalize_missing_numeric_parameter_provenance,
    normalize_schema_default_parameter_provenance,
    parallel_plan_contract_errors,
    planner_goal_execution_requirements,
    planner_response_goal_ids,
    planner_contract_diagnostics,
    result_evidence_reentry_goal_ids,
    review_coordinated_action_plan_coverage,
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
    from chromie_contracts.interaction import (
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
        FastPlannerFirstResponseTruthCertificate,
        FastPlannerProgressAct,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.interaction import (
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerAdvance,
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponse,
        FastPlannerFirstResponseModelOutput,
        FastPlannerFirstResponseTruthCertificate,
        FastPlannerProgressAct,
    )

logger = logging.getLogger("chromie.agent.fast_planner")


_SINGLE_SEMANTIC_NUMBER = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?)\s*[^\d]*$"
)


def _semantic_numeric_values(value: Any) -> set[Decimal]:
    """Collect exact user-semantic quantities without mining prose or IDs."""

    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float, Decimal)):
        try:
            return {Decimal(str(value))}
        except InvalidOperation:
            return set()
    if isinstance(value, str):
        match = _SINGLE_SEMANTIC_NUMBER.fullmatch(value)
        if match is None:
            return set()
        try:
            return {Decimal(match.group(1))}
        except InvalidOperation:
            return set()
    if isinstance(value, dict):
        return {
            number
            for key, item in value.items()
            if str(key).strip().casefold()
            not in {"confidence", "schema_version", "version", "referent_id"}
            for number in _semantic_numeric_values(item)
        }
    if isinstance(value, (list, tuple)):
        return {
            number
            for item in value
            for number in _semantic_numeric_values(item)
        }
    return set()


def _first_response_target_goal_grounding(
    context: dict[str, Any],
    responsibilities: list[CognitiveResponsibilityProposal],
) -> list[dict[str, Any]]:
    """Project human-facing semantics for Goals referenced before Association.

    Fast first response intentionally runs before Goal Association so it can reduce
    speech latency. A continuation Responsibility can therefore carry a valid
    retained Goal ID while ``canonical_goal_grounding`` is still empty. Preserve
    the existing phase order but give the same Fast semantic owner the minimal
    provider-neutral meaning needed to speak about the resolved action naturally.
    """

    target_goal_ids = {
        str(goal_id).strip()
        for responsibility in responsibilities
        for goal_id in responsibility.target_goal_ids
        if str(goal_id).strip()
    }
    if not target_goal_ids:
        return []

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [
        *(context.get("active_goal_snapshots") or []),
        *(context.get("recent_goal_snapshots") or []),
    ]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        goal_id = " ".join(
            str(item.get("goal_id") or goal.get("goal_id") or "").split()
        )
        if not goal_id or goal_id not in target_goal_ids or goal_id in seen:
            continue
        seen.add(goal_id)
        result.append(
            {
                "goal_id": goal_id,
                "description": goal.get("description")
                or item.get("last_user_update")
                or "",
                "source_text": goal.get("source_text")
                or item.get("last_user_update")
                or "",
                "object": goal.get("object") or {},
                "constraints": goal.get("constraints") or {},
                "success_criteria": goal.get("success_criteria") or [],
            }
        )
    return result


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
        first_response_ollama: OllamaClient | None = None,
        first_response_num_ctx: int | None = None,
        truth_ollama: OllamaClient | None = None,
        truth_num_ctx: int | None = None,
        min_confidence: float = 0.8,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        max_capabilities: int = 24,
        max_contract_repairs: int = 1,
    ) -> None:
        self.ollama = ollama
        # Fast Planner remains the sole semantic owner of both phases.  The
        # Separately qualified clients may specialize the latency-critical
        # natural-language Activity and its bounded accept/reject qualification;
        # complete Capability planning stays on ``ollama``. When configured roles
        # share a model, main reuses the exact client so bounded calls do not force
        # an avoidable runner reload.
        self.first_response_ollama = first_response_ollama or ollama
        self.first_response_num_ctx = max(
            2048,
            int(
                first_response_num_ctx
                if first_response_num_ctx is not None
                else min(num_ctx, 6144)
            ),
        )
        self.truth_ollama = truth_ollama or ollama
        self.truth_num_ctx = max(
            2048,
            int(
                truth_num_ctx
                if truth_num_ctx is not None
                else (
                    num_ctx
                    if self.truth_ollama is self.ollama
                    else self.first_response_num_ctx
                    if self.truth_ollama is self.first_response_ollama
                    else min(num_ctx, 6144)
                )
            ),
        )
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.max_capabilities = max(1, min(64, int(max_capabilities)))
        self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))

    async def resolve_first_response(
        self, request: CognitiveWorkRequest
    ) -> FastPlannerFirstResponse:
        """Author the earliest useful speech while Fast HOW planning continues.

        This is deliberately a latency phase of Fast Planner. It neither selects a
        Capability nor resolves an execution-input gap, and it never creates a
        second response-authoring owner.
        """

        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(
                item.model_dump(mode="json")
            )
            for item in request.responsibilities
        ]
        responsibility_refs = [item.local_ref for item in responsibilities]
        needs_work = any(
            item.completion_requires_work
            or item.completion_requires_fresh_evidence
            for item in responsibilities
        )
        needs_fresh_evidence = any(
            item.completion_requires_fresh_evidence
            for item in responsibilities
        )
        requested_output_modes = {
            item.output_mode for item in responsibilities
        }
        effect_output_modes = {
            "body_action",
            "media_playback",
            "styled_speech",
            "recitation",
            "singing",
            "humming",
            "nonverbal_vocalization",
        }
        required_progress_kind = (
            "check_information"
            if needs_fresh_evidence
            else (
                "perform_action"
                if requested_output_modes
                and requested_output_modes.issubset(effect_output_modes)
                else None
            )
        )
        response_schema = self._first_response_schema(
            responsibility_refs,
            responsibilities=responsibilities,
            needs_work=needs_work,
            needs_fresh_evidence=needs_fresh_evidence,
            required_progress_kind=required_progress_kind,
            language=str(request.language or ""),
        )
        try:
            raw = await self.first_response_ollama.generate(
                self._first_response_prompt(
                    request,
                    responsibilities=responsibilities,
                    needs_work=needs_work,
                ),
                system=self._first_response_system_prompt(),
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    # The specialized response client does not share the full
                    # planner's runner. Size this bounded phase to its compact
                    # input instead of allocating the qualification profile's 32K
                    # planning window for a ten-word acknowledgement.
                    "num_ctx": self.first_response_num_ctx,
                    "num_predict": min(self.num_predict, 192),
                },
                response_format=response_schema,
                prompt_family="fast_planner.first_response",
                turn_id=request.sid,
                attempt=1,
            )
            if needs_work and isinstance(raw, dict):
                raw_activity = raw.get("activity")
                if isinstance(raw_activity, dict):
                    activity_payload = dict(raw_activity)
                    if len(responsibility_refs) == 1:
                        # There is no semantic association choice in the single-
                        # Responsibility case.  Keep that mechanical provenance out
                        # of the latency-critical model DTO and restore it before the
                        # authoritative Activity contract is validated.
                        activity_payload.setdefault(
                            "source_responsibility_refs", responsibility_refs
                        )
                    activity_payload.setdefault("role", "progress")
                    activity_payload.setdefault(
                        "activity_id",
                        "progress_"
                        + hashlib.sha256(
                            (
                                str(request.sid or "turn")
                                + "|"
                                + "|".join(responsibility_refs)
                            ).encode("utf-8")
                        ).hexdigest()[:12],
                    )
                    raw = {**raw, "activity": activity_payload}
            output = FastPlannerFirstResponseModelOutput.model_validate(raw)
            activity = output.activity
            refs = set(activity.source_responsibility_refs)
            if not refs or not refs.issubset(set(responsibility_refs)):
                raise PlannerDTOContractError(
                    "Fast first response must cite supplied Responsibility refs"
                )
            if needs_work and activity.role != "progress":
                raise PlannerDTOContractError(
                    "unfinished work requires a prospective progress response"
                )
            if not needs_work and activity.role != "complete_response":
                raise PlannerDTOContractError(
                    "immediate conversational work requires a complete response"
                )
            truth_certificate = await self._qualify_first_response_truth(
                request,
                activity=activity,
                responsibilities=responsibilities,
            )
            qualification_metadata = {
                "truth_qualification_owner": "fast_planner",
                "truth_qualification_call_count": 1,
                "truth_qualification": truth_certificate.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude_defaults=True,
                ),
            }
            if truth_certificate.decision != "accept":
                logger.warning(
                    "fast_planner_first_response_truth_rejected sid=%s activity_id=%s",
                    request.sid,
                    activity.activity_id,
                )
                return FastPlannerFirstResponse(
                    turn_id=str(request.sid or "turn-fast-first-response"),
                    activity=None,
                    metadata={
                        "semantic_authority": "fast_planner_truth_rejection",
                        "phase": "first_communicative_activity",
                        "execution_authority": "none",
                        **qualification_metadata,
                    },
                )
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=activity,
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "first_communicative_activity",
                    "execution_authority": "host_communicative_runtime",
                    **qualification_metadata,
                },
            )
        except Exception as exc:
            failure = (
                llm_failure_metadata(exc)
                if isinstance(exc, OllamaGenerationError)
                else {
                    "failure_class": "fast_first_response_contract_invalid",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "not_evaluated",
                    "retryable": True,
                }
            )
            logger.warning(
                "fast_planner_first_response_fail_safe sid=%s error_type=%s "
                "error=%s failure_class=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
            )
            return FastPlannerFirstResponse(
                turn_id=str(request.sid or "turn-fast-first-response"),
                activity=None,
                metadata={
                    "semantic_authority": "deterministic_fail_safe",
                    "phase": "first_communicative_activity",
                    "execution_authority": "none",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    **failure,
                },
            )

    async def _qualify_first_response_truth(
        self,
        request: CognitiveWorkRequest,
        *,
        activity: Any,
        responsibilities: list[CognitiveResponsibilityProposal],
    ) -> FastPlannerFirstResponseTruthCertificate:
        """Accept or reject immutable wording without authoring a replacement.

        This is the single owner-approved Epistemic Qualification inside Fast
        Planner.  A failure, malformed certificate, or uncertain acceptance is
        terminal for the first-response Activity and is never repaired.
        """

        schema = self._truth_certificate_schema()
        context = request.context if isinstance(request.context, dict) else {}
        raw = await self.truth_ollama.generate(
            self._first_response_truth_prompt(
                request,
                activity=activity,
                responsibilities=responsibilities,
                trusted_evidence=context.get("trusted_terminal_evidence") or [],
            ),
            system=self._first_response_truth_system_prompt(),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.truth_num_ctx,
                "num_predict": min(self.num_predict, 128),
            },
            response_format=schema,
            prompt_family="fast_planner.first_response.truth_check",
            turn_id=request.sid,
            attempt=1,
        )
        certificate = FastPlannerFirstResponseTruthCertificate.model_validate(raw)
        return certificate

    async def _qualify_evidence_response_truth(
        self,
        request: CognitiveWorkRequest,
        *,
        plan: CanonicalPlan,
    ) -> FastPlannerFirstResponseTruthCertificate:
        """Accept or reject immutable post-Evidence wording without repairing it."""

        schema = self._truth_certificate_schema()
        context = request.context if isinstance(request.context, dict) else {}
        contract = (
            "Fast Planner post-Evidence Epistemic Qualification contract: inspect every "
            "candidate response string against only the admitted trusted terminal "
            "Evidence and authoritative Goal scope. Return decision=accept only when "
            "every material claim preserves the Evidence values, scope, and epistemic "
            "strength. A forecast, estimate, or probability below 100% remains "
            "uncertain even when a provider condition label names rain or showers. "
            "Reject wording that turns it into certainty, including forms equivalent "
            "to '所以会下雨' or 'it will rain'; wording such as '可能会下雨' or 'a 76% "
            "chance of rain' preserves uncertainty. Reject unsupported duration, "
            "severity, advice, reassurance, or facts from another period. Do not "
            "rewrite the response, choose a Capability, or add an explanation. "
            "Classify whether the response has an unsupported material claim or a "
            "semantic-perspective contradiction, then return only decision=accept "
            "when neither is present. Otherwise return decision=reject."
        )
        candidate = {
            "response_text": plan.response_text,
            "goal_outcome_response_texts": [
                {
                    "goal_id": outcome.goal_id,
                    "response_text": outcome.response_text,
                }
                for outcome in plan.goal_outcomes
                if getattr(outcome, "response_text", "")
            ],
        }
        rendered = (
            contract
            + "\n\nImmutable candidate response JSON:\n"
            + json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n\nAdmitted trusted terminal Evidence JSON:\n"
            + self._bounded(context.get("trusted_terminal_evidence") or [], 6000)
            + "\n\nAuthoritative canonical Goal JSON:\n"
            + self._bounded(canonical_goal_grounding(context), 3000)
            + "\n\nCurrent user turn (scope only):\n"
            + " ".join(str(request.text or "").split())[:700]
        )
        raw = await self.truth_ollama.generate(
            LayeredPrompt.promote(rendered, operating_contract=(contract,)),
            system=(
                "You are the same Fast Planner's bounded post-Evidence Epistemic "
                "Qualification, not a response author. Accept or reject the immutable "
                "candidate. Never repair, replace, or expand it."
            ),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.truth_num_ctx,
                "num_predict": min(self.num_predict, 64),
            },
            response_format=schema,
            prompt_family="fast_planner.evidence_response.truth_check",
            turn_id=request.sid,
            attempt=1,
        )
        return FastPlannerFirstResponseTruthCertificate.model_validate(raw)

    @staticmethod
    def _first_response_truth_system_prompt() -> str:
        return (
            "Classify one immutable Fast Planner sentence; do not rewrite it. Return "
            "only the four audit fields required by the JSON schema. Set each violation "
            "flag explicitly, then accept only when all three are false. Before action or Evidence, a "
            "present acknowledgement or future intention is supported, while an "
            "already-started/completed action, result, invented method, or invented fact is "
            "not. An onset or progressive predicate saying execution starts, has "
            "started, or is underway is an already-started claim even when an immediacy "
            "marker appears before it. Resolve grammatical roles: in a human command addressed to Chromie, "
            "Chromie is the commanded actor. Chromie's first-person subject is the "
            "correct actor; the user's second-person command does not make that reply "
            "a perspective contradiction. A reply telling the human to do Chromie's "
            "action does. Never choose a Capability or change Goal meaning."
        )

    @staticmethod
    def _truth_certificate_schema() -> dict[str, Any]:
        schema = copy.deepcopy(
            FastPlannerFirstResponseTruthCertificate.model_json_schema()
        )
        schema["required"] = [
            "has_unverified_result_or_completion_claim",
            "has_ungrounded_method_or_world_claim",
            "has_semantic_perspective_contradiction",
            "decision",
        ]
        return schema

    @staticmethod
    def _first_response_truth_prompt(
        request: CognitiveWorkRequest,
        *,
        activity: Any,
        responsibilities: list[CognitiveResponsibilityProposal],
        trusted_evidence: list[Any],
    ) -> LayeredPrompt:
        contract = (
            "Judge the exact immutable activity.text, not its label. At pre_evidence, "
            "a present acknowledgement or prospective intention is valid; an intention "
            "to check next is not an execution claim, and an intention to act next is "
            "not a completion claim. Chinese '我先…', '我这就…', '我马上…', '我会…', "
            "and '我将…', and English 'Let me…', 'I will…', and 'I'll do it now' are "
            "prospective only when they modify a future intention. An onset or "
            "progressive predicate equivalent to 'I am starting', 'I start executing', "
            "or 'I am doing it' claims that work is underway and must be rejected even "
            "after one of those immediacy markers. In contrast, wording equivalent to 'I checked', 'I did it', "
            "'I finished', or a requested result says work already happened. "
            "Reject only when the sentence contains an unverified result, changed-world "
            "claim, already-started/completed claim, or when it invents a physical "
            "instrument, source, sensor, observation, action, personal fact, or world "
            "fact absent from Responsibility/context; never say Chromie will "
            "look at a phone, camera, or look outside or use direct perception unless "
            "supplied. Also reject a real speaker, experiencer, actor, addressee, "
            "polarity, referent, or semantic relationship reversal. The sentence "
            "must preserve each authoritative Responsibility's concrete outcome and "
            "relationship. In particular, relationship=continue must sound like "
            "continuing or resuming the resolved work rather than starting it as a "
            "new action, and it must not fall back to a generic thing, matter, or "
            "action after the target meaning is supplied. "
            "For a command addressed to Chromie, first-person 我/I is the correct actor; "
            "a reply that tells the human to perform that action is not. In an "
            "immediate command response, a bare Chinese first-person action such as "
            "'我往前走十秒' still keeps Chromie as actor; only mark a perspective "
            "contradiction if the sentence actually assigns the action to the human. "
            "A human's feeling must remain the human's, and repeating Chromie's last utterance "
            "must use the supplied assistant utterance. A progress question that asks "
            "the human to supply or reconfirm information without an InformationGap "
            "also reverses responsibility. For context_grounded text, reject invented "
            "facts; for post_evidence text, require cited Evidence. Set each of the "
            "three audit flags explicitly. A missing continue/resume relationship in "
            "wording for relationship=continue is a semantic-perspective contradiction. "
            "Accept when none applies; otherwise reject. Never supply replacement wording."
        )
        rendered = (
            contract
            + "\n\nImmutable Communicative Activity JSON:\n"
            + json.dumps(
                activity.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n\nAuthoritative Responsibility evidence JSON:\n"
            + json.dumps(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in responsibilities
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:3000]
            + "\n\nAdmitted trusted Evidence JSON:\n"
            + json.dumps(
                trusted_evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:2200]
            + "\n\nBounded Interaction Context JSON:\n"
            + json.dumps(
                (request.context or {}).get("interaction_context") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:900]
            + "\n\nCurrent user turn (context only, never external-result Evidence):\n"
            + " ".join(str(request.text or "").split())[:700]
        )
        return LayeredPrompt.promote(
            rendered,
            operating_contract=(contract,),
        )

    @staticmethod
    def _first_response_schema(
        responsibility_refs: list[str],
        *,
        responsibilities: list[CognitiveResponsibilityProposal] | None = None,
        needs_work: bool,
        needs_fresh_evidence: bool = False,
        required_progress_kind: str | None = None,
        language: str = "",
    ) -> dict[str, Any]:
        schema = copy.deepcopy(
            FastPlannerFirstResponseModelOutput.model_json_schema()
        )
        definitions = schema.get("$defs", {})
        allowed_contract = (
            "FastPlannerProgressAct"
            if needs_work
            else "FastPlannerCompleteResponseAct"
        )
        activity = schema.get("properties", {}).get("activity")
        if isinstance(activity, dict):
            activity.clear()
            activity["$ref"] = f"#/$defs/{allowed_contract}"
        contract = definitions.get(allowed_contract)
        if isinstance(contract, dict):
            properties = contract.get("properties")
            if isinstance(properties, dict):
                for field_name in (
                    "evidence_refs",
                    "timing",
                    "speech_act",
                    "truth_stage",
                ):
                    properties.pop(field_name, None)
                activity_id = properties.get("activity_id")
                if isinstance(activity_id, dict):
                    activity_id["maxLength"] = 48
                progress_kind = properties.get("progress_kind")
                if isinstance(progress_kind, dict) and needs_work:
                    progress_kind["description"] = (
                        "Select check_information only for fresh information Evidence; "
                        "perform_action for a requested embodied, media, vocal, or "
                        "state-changing effect; acknowledge_work only for other work."
                    )
                    enum_values = progress_kind.get("enum")
                    if isinstance(enum_values, list):
                        # Some Ollama/Qwen templates treat the literal value
                        # ``think`` as a provider control token even when
                        # think=false, closing a phantom thinking block and
                        # duplicating otherwise-valid JSON. Deeper planning keeps
                        # the full communicative contract; this optional latency
                        # phase uses the three non-control progress functions.
                        progress_kind["enum"] = [
                            value for value in enum_values if value != "think"
                        ]
                    if required_progress_kind:
                        progress_kind["enum"] = [required_progress_kind]
                text_contract = properties.get("text")
                if isinstance(text_contract, dict):
                    text_contract["maxLength"] = (
                        32 if str(language).casefold().startswith("zh") else 72
                    )
                    if needs_work:
                        semantic_contract = [
                            {
                                "relationship": item.relationship,
                                "outcome": item.outcome,
                                "target_goal_ids": list(item.target_goal_ids),
                            }
                            for item in (responsibilities or [])
                        ]
                        text_contract["pattern"] = r"^[^?？]*$"
                        text_contract["description"] = (
                            "Exact short speech before any work or Evidence exists. "
                            "It may acknowledge and prospectively say what Chromie will "
                            "check/do, but must not name an instrument, source, sensor, "
                            "screen, or implementation method because no Capability has "
                            "been selected in this phase. It also must not answer the "
                            "request or imply a lookup, "
                            "action, result, or completion already happened. Keep only "
                            "the acknowledgement/intention. A willingness or immediacy "
                            "marker must still describe a future action; never use an "
                            "onset or progressive predicate that says execution is starting "
                            "or underway before Runtime commitment. Omit an explanation of what "
                            "the check will reveal. Preserve the authoritative semantic "
                            "relationship and concrete resolved outcome in this decoder "
                            "contract: "
                            + json.dumps(
                                semantic_contract,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            )[:1200]
                            + ". For relationship=continue, explicitly word the sentence "
                            "as continuing or resuming that concrete outcome, not as a "
                            "new start and not with a generic stand-in."
                        )
                source_refs = properties.get("source_responsibility_refs")
                if isinstance(source_refs, dict):
                    source_refs["items"] = {
                        "type": "string",
                        "enum": list(dict.fromkeys(responsibility_refs)),
                    }
                    source_refs["uniqueItems"] = True
                    if needs_work and len(set(responsibility_refs)) == 1:
                        properties.pop("source_responsibility_refs", None)
                if needs_work:
                    properties.pop("role", None)
                    properties.pop("activity_id", None)
                    # Ollama follows schema property order while decoding. Make the
                    # Planner commit its semantic progress function before it authors
                    # immutable wording. The bounded phase fixes mechanical role,
                    # Activity ID, and truth_stage without choosing semantic HOW.
                    preferred_order = (
                        "progress_kind",
                        "source_responsibility_refs",
                        "text",
                    )
                    ordered = {
                        name: properties[name]
                        for name in preferred_order
                        if name in properties
                    }
                    ordered.update(
                        (name, value)
                        for name, value in properties.items()
                        if name not in ordered
                    )
                    properties.clear()
                    properties.update(ordered)
                    required = contract.get("required")
                    if isinstance(required, list):
                        # A decoder schema cannot require mechanical fields that
                        # this latency phase deliberately removed from properties.
                        # Keep required and properties closed over the same output
                        # shape; the Host restores role, Activity ID, truth stage,
                        # and a uniquely determined Responsibility ref afterward.
                        required_names = set(required).intersection(properties)
                        if len(set(responsibility_refs)) == 1:
                            required_names.discard("source_responsibility_refs")
                        contract["required"] = [
                            name
                            for name in preferred_order
                            if name in required_names
                        ] + sorted(required_names - set(preferred_order))
        unused_contract = (
            "FastPlannerCompleteResponseAct"
            if needs_work
            else "FastPlannerProgressAct"
        )
        definitions.pop(unused_contract, None)
        return schema

    @staticmethod
    def _first_response_system_prompt() -> str:
        return (
            "You are Chromie's low-latency Fast Planner authoring exactly one "
            "immediately realizable Communicative Activity. You own its communicative "
            "function and exact natural wording. Do not select a Capability, resolve "
            "parameters, ask a clarification, claim execution, or invent external "
            "Evidence in this latency phase. This is a method-blind phase: never name "
            "where or how Chromie will check or act, including an instrument, device, "
            "screen, sensor, source, or implementation, unless that exact method is "
            "already explicit in Responsibility evidence. Name only the user-level "
            "outcome Chromie will check or do. Return only schema-constrained JSON."
        )

    @staticmethod
    def _first_response_prompt(
        request: CognitiveWorkRequest,
        *,
        responsibilities: list[CognitiveResponsibilityProposal],
        needs_work: bool,
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        language = str(request.language or "auto")[:32]
        role_contract = (
            "Author one short progress Activity that honestly acknowledges the work "
            "without giving a result."
            if needs_work
            else "Author the complete natural response Activity now."
        )
        identity = owner_approved_identity_context(context).get("identity") or {}
        personality = owner_approved_personality_context(context)
        identity_projection = {
            "identity": {
                key: identity[key]
                for key in ("name",)
                if identity.get(key) not in (None, "", [], {})
            },
            "voice": {
                key: str(personality[key])[:360]
                for key in ("spoken_style", "tool_use_style")
                if personality.get(key) not in (None, "", [], {})
            },
        }
        identity_section = "Bounded owner-approved speaking style JSON:\n" + json.dumps(
            identity_projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        progress_contract = (
            "Fast Planner first-response contract: author one useful spoken Main "
            "Activity and its exact wording. At truth_stage=pre_evidence, no check, "
            "execution, or fresh Evidence has happened. Say only a present "
            "acknowledgement or prospective intention; never claim or predict a result, "
            "completion, method, instrument, source, sensor, or screen. A progress "
            "Activity is not a clarification: never ask a question, request a choice, "
            "or ask the person to reconfirm supplied meaning. Preserve who said, felt, "
            "perceived, or did each thing: the human's first person never becomes "
            "Chromie's first person. An imperative addressed to Chromie makes Chromie "
            "the actor. Reply to a command with Chromie's first-person intention; never "
            "repeat the commanded action with the human as its subject. Do not turn a command into an "
            "observation about the human's hobbies, practice, preferences, or recent "
            "activity. For a human feeling, acknowledge the human as 你/you, never as "
            "我/I. For a request to restate Chromie's last utterance, use only the "
            "supplied assistant utterance. When a Responsibility continues, resumes, "
            "modifies, or otherwise references a supplied Goal, use the resolved "
            "target Goal meaning below. The sentence must name that concrete resolved "
            "user-level action or work in natural language and preserve the supplied "
            "relationship. For relationship=continue, the wording must explicitly say "
            "continue/resume (继续/接着), rather than sounding like a new start. For "
            "example, a retained "
            "Goal meaning 'move forward' must be realized as continuing to move/walk "
            "forward, not merely as continuing a thing or an action. Generic stand-ins "
            "such as the thing, the matter, that request, that action, or the previous "
            "action are invalid after the referent is available. It may omit repeated "
            "parameter detail when brevity makes that natural. Before an embodied or "
            "state-changing action, make the intention prospective with a natural "
            "willingness/immediacy marker (for example Chinese 好/我这就/我马上 or "
            "English okay/I'll), so a bare present-tense action is not mistaken for "
            "execution already underway. That marker must modify a future intention, "
            "not wording equivalent to 'I am starting' or 'I am doing it now'; those "
            "claims require Runtime commitment. Do not invent current activity, household "
            "work, personal state, or external facts."
        )
        responsibility_field_contract = (
            "The decoder schema deliberately omits Responsibility refs because exactly "
            "one Responsibility exists. Output no responsibility, ref, role, ID, or "
            "other field: activity contains only progress_kind and text."
            if needs_work and len(responsibilities) == 1
            else (
                "When the schema exposes source_responsibility_refs, use that exact "
                "array field with only supplied refs; never invent a nested "
                "responsibility object."
            )
        )
        rendered = (
            identity_section
            + "\n\n"
            + progress_contract
            + "\n\nCurrent user turn:\n"
            + " ".join(str(request.text or "").split())[:700]
            + "\nRequired response language: "
            + language
            + "\nUse that language naturally in activity.text; zh/zh-CN requires "
            "natural Chinese.\n\n"
            + role_contract
            + " Use one brief conversational sentence. Progress states the prospective "
            "check, action, or work instead of repeating the question; omit a second "
            "clause explaining what the check will reveal. "
            + responsibility_field_contract
            + "\n\n"
            "Authoritative Responsibility evidence:\n"
            + json.dumps(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in responsibilities
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:2600]
            + "\n\nResolved target Goal semantics for referenced Responsibilities:\n"
            + json.dumps(
                _first_response_target_goal_grounding(context, responsibilities),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:1800]
            + "\n\nAlready delivered or pending interaction summary:\n"
            + json.dumps(
                context.get("interaction_context") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:700]
            + (
                "\n\nFINAL COUNTERFACTUAL CHECK: the exact sentence must remain true if "
                "no checking has started and no result exists."
                if needs_work
                else ""
            )
        )
        return LayeredPrompt.promote(
            rendered,
            identity_world=(identity_section,),
            operating_contract=(progress_contract,),
        )

    async def resolve_advance(self, request: CognitiveWorkRequest) -> FastPlannerAdvance:
        """Produce Fast Planner's first Activity Plan from GI Responsibilities."""

        context = request.context if isinstance(request.context, dict) else {}
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(item.model_dump(mode="json"))
            for item in request.responsibilities
        ]
        committed_communicative_activities: list[Any] = []
        first_response_decided = False
        raw_first_response = context.get("fast_planner_first_response")
        if isinstance(raw_first_response, dict):
            try:
                first_response = FastPlannerFirstResponse.model_validate(
                    raw_first_response
                )
            except ValidationError:
                first_response = None
            if first_response is not None:
                first_response_decided = True
                if first_response.activity is not None:
                    committed_communicative_activities.append(first_response.activity)

        # A fully qualified immediate conversational response already covers a
        # Responsibility that GI says needs no downstream work.  Returning here
        # keeps unrelated body/tool choices out of a second model decision; before
        # this boundary, greetings and human feelings could acquire decorative
        # stand/stop Activities despite requesting no physical effect.
        if (
            responsibilities
            and all(
                not item.completion_requires_work
                and not item.completion_requires_fresh_evidence
                for item in responsibilities
            )
            and len(committed_communicative_activities) == 1
            and committed_communicative_activities[0].role == "complete_response"
        ):
            return FastPlannerAdvance(
                turn_id=str(request.sid or "turn-fast-advance"),
                disposition="respond",
                coverage="complete",
                covered_responsibility_refs=[
                    item.local_ref for item in responsibilities
                ],
                activities=committed_communicative_activities,
                continuations=[],
                confidence=min(item.confidence for item in responsibilities),
                unresolved=[],
                reason_summary="Immediate conversational response is complete.",
                metadata={
                    "semantic_authority": "fast_planner_model",
                    "phase": "responsibility_activity_planning",
                    "execution_authority": "host_communicative_runtime",
                    "immediate_conversation_terminal": True,
                },
            )

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
            interpretation_unresolved=list(request.interpretation_unresolved),
            # A null first-response result is still a terminal decision for that
            # bounded speech phase.  Advance must not author a substitute progress
            # sentence and thereby bypass its one truth qualification.
            committed_communicative=first_response_decided,
            suppress_new_communicative=(
                first_response_decided
                and not committed_communicative_activities
            ),
        )
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": min(self.num_predict, 2048),
        }
        previous_errors = ""
        last_raw: Any = None
        revision_source: Any = None
        for attempt in range(self.max_contract_repairs + 1):
            try:
                active_response_schema = (
                    self._advance_revision_response_schema(
                        response_schema,
                        revision_source,
                        committed_communicative=first_response_decided,
                        capabilities=capability_payload,
                        responsibilities=responsibilities,
                    )
                    if attempt
                    else response_schema
                )
                last_raw = await self.ollama.generate(
                    self._advance_layered_prompt(
                        request,
                        responsibilities=responsibilities,
                        capabilities=capability_payload,
                        committed_communicative_activities=(
                            committed_communicative_activities
                        ),
                        first_response_decided=first_response_decided,
                        validation_errors=previous_errors,
                    ),
                    system=self._advance_system_prompt(),
                    options=options,
                    response_format=active_response_schema,
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
                if first_response_decided and any(
                    activity.role == "progress" for activity in output.activities
                ):
                    raise PlannerDTOContractError(
                        "Fast Planner advance cannot replace a completed first-response "
                        "accept/reject decision with another progress Activity"
                    )
                combined_output = output.model_copy(
                    update={
                        "activities": [
                            *committed_communicative_activities,
                            *output.activities,
                        ]
                    }
                )
                self._validate_advance_output(
                    combined_output,
                    request=request,
                    responsibilities=responsibilities,
                    capabilities=capability_payload,
                )
                return FastPlannerAdvance(
                    turn_id=str(request.sid or "turn-fast-advance"),
                    disposition=combined_output.disposition,
                    coverage=combined_output.coverage,
                    covered_responsibility_refs=(
                        combined_output.covered_responsibility_refs
                    ),
                    activities=combined_output.activities,
                    continuations=combined_output.continuations,
                    confidence=combined_output.confidence,
                    unresolved=combined_output.unresolved,
                    reason_summary=combined_output.reason_summary,
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
                    (ValidationError, json.JSONDecodeError),
                ):
                    revision_source = last_raw
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
                    committed_communicative_activities=(
                        committed_communicative_activities
                    ),
                    allow_progress_salvage=not first_response_decided,
                )
        raise AssertionError("unreachable")

    @staticmethod
    def _advance_revision_response_schema(
        schema: dict[str, Any],
        initial_raw: Any,
        *,
        committed_communicative: bool,
        capabilities: list[dict[str, Any]],
        responsibilities: list[CognitiveResponsibilityProposal],
    ) -> dict[str, Any]:
        """Constrain one DTO revision to the model's initial disposition.

        A malformed Activity list must not make the permitted same-stage repair
        reconsider user meaning. In particular, an initial ``execute`` decision
        already commits the model to Capability work; when the first Communicative
        Activity was independently committed, the repaired list can contain only
        Capability Activities. The model still owns which available Capability and
        arguments satisfy the Responsibility.
        """

        if not isinstance(initial_raw, dict):
            return schema
        disposition_value = initial_raw.get("disposition")
        allowed_contracts_by_disposition = {
            "execute": ["FastPlannerCapabilityActivity"],
            "respond": ["FastPlannerCompleteResponseAct"],
            "clarify": ["FastPlannerClarificationAct"],
        }
        allowed_contracts = allowed_contracts_by_disposition.get(disposition_value)
        if allowed_contracts is None:
            return schema
        if disposition_value == "execute" and not committed_communicative:
            allowed_contracts.append("FastPlannerProgressAct")

        narrowed = copy.deepcopy(schema)
        properties = narrowed.get("properties", {})
        disposition = properties.get("disposition")
        if isinstance(disposition, dict):
            disposition["enum"] = [disposition_value]
            disposition["description"] = (
                "Mechanical DTO revision: preserve the initial model-authored "
                "disposition exactly."
            )
        activities = properties.get("activities")
        activity_items = activities.get("items") if isinstance(activities, dict) else None
        if not isinstance(activity_items, dict):
            return narrowed
        activity_items["oneOf"] = [
            {"$ref": f"#/$defs/{contract_name}"}
            for contract_name in allowed_contracts
        ]
        discriminator = activity_items.get("discriminator")
        if isinstance(discriminator, dict):
            mapping = discriminator.get("mapping")
            if isinstance(mapping, dict):
                discriminator["mapping"] = {
                    role: ref
                    for role, ref in mapping.items()
                    if ref.rsplit("/", 1)[-1] in allowed_contracts
                }
        if isinstance(activities, dict):
            activities["minItems"] = 1
        if disposition_value == "execute":
            definitions = narrowed.get("$defs", {})
            capability_contract = definitions.get("FastPlannerCapabilityActivity")
            capability_properties = (
                capability_contract.get("properties")
                if isinstance(capability_contract, dict)
                else None
            )
            capability_required = (
                list(capability_contract.get("required", []))
                if isinstance(capability_contract, dict)
                else []
            )
            if "args" not in capability_required:
                capability_required.append("args")
            branches: list[dict[str, Any]] = []
            explicit_numbers = sorted(
                {
                    number
                    for responsibility in responsibilities
                    for number in _semantic_numeric_values(
                        responsibility.bindings
                    )
                }
            )
            if isinstance(capability_properties, dict):
                for capability in capabilities:
                    capability_id = str(capability.get("capability_id") or "")
                    input_schema = capability.get("input_schema")
                    if not capability_id or not isinstance(input_schema, dict):
                        continue
                    branch_properties = copy.deepcopy(capability_properties)
                    branch_properties["capability_id"] = {
                        "type": "string",
                        "enum": [capability_id],
                    }
                    explicit_input_schema = copy.deepcopy(input_schema)
                    explicit_required = list(
                        explicit_input_schema.get("required", [])
                    )
                    input_properties = explicit_input_schema.get("properties")
                    if isinstance(input_properties, dict):
                        numeric_parameter_names = [
                            parameter_name
                            for parameter_name, parameter_schema in input_properties.items()
                            if isinstance(parameter_schema, dict)
                            and parameter_schema.get("type") in {"integer", "number"}
                        ]
                        for parameter_name, parameter_schema in input_properties.items():
                            if (
                                isinstance(parameter_schema, dict)
                                and "default" in parameter_schema
                                and parameter_name not in explicit_required
                            ):
                                # A mechanical revision materializes schema defaults
                                # explicitly. This keeps the model-selected scope in
                                # the DTO instead of making downstream Runtime guess
                                # whether an omitted optional temporal/behavior field
                                # was intentional.
                                explicit_required.append(parameter_name)
                        if (
                            len(explicit_numbers) == 1
                            and len(numeric_parameter_names) == 1
                        ):
                            numeric_name = numeric_parameter_names[0]
                            numeric_schema = input_properties.get(numeric_name)
                            explicit_number = explicit_numbers[0]
                            if isinstance(numeric_schema, dict) and (
                                numeric_schema.get("type") == "number"
                                or explicit_number == explicit_number.to_integral_value()
                            ):
                                numeric_schema["enum"] = [
                                    int(explicit_number)
                                    if numeric_schema.get("type") == "integer"
                                    else float(explicit_number)
                                ]
                    if explicit_required:
                        explicit_input_schema["required"] = explicit_required
                    branch_properties["args"] = explicit_input_schema
                    branches.append(
                        {
                            "type": "object",
                            "properties": branch_properties,
                            "required": capability_required,
                            "additionalProperties": False,
                        }
                    )
            if isinstance(capability_contract, dict) and branches:
                capability_contract["oneOf"] = branches
        return narrowed

    @staticmethod
    def _advance_response_schema(
        responsibility_refs: list[str],
        *,
        responsibilities: list[CognitiveResponsibilityProposal] | None = None,
        capabilities: list[dict[str, Any]] | None = None,
        interpretation_unresolved: list[str] | None = None,
        committed_communicative: bool = False,
        suppress_new_communicative: bool = False,
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
        all_need_work = bool(responsibility_items) and all(
            item.completion_requires_work for item in responsibility_items
        )
        schema = copy.deepcopy(FastPlannerAdvanceModelOutput.model_json_schema())
        top_properties = schema.get("properties", {})
        activities_schema = top_properties.get("activities")
        if isinstance(activities_schema, dict):
            activities_schema["maxItems"] = max(
                1,
                len(responsibility_refs)
                if committed_communicative or suppress_new_communicative
                else len(responsibility_refs) * 2,
            )
        disposition = top_properties.get("disposition")
        if isinstance(disposition, dict) and all_need_work:
            disposition["enum"] = [
                "execute",
                "mixed",
                "clarify",
                "escalate",
                "refused",
                "unavailable",
            ]
        if isinstance(disposition, dict) and all_need_fresh_evidence:
            disposition["enum"] = [
                "execute",
                "mixed",
                "clarify",
                "escalate",
                "refused",
                "unavailable",
            ]
            if suppress_new_communicative:
                disposition["enum"] = [
                    "execute",
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
                                    "properties": {
                                        "role": {
                                            "enum": [
                                                "progress",
                                                "clarification",
                                                "complete_response",
                                            ]
                                        }
                                    },
                                    "required": ["role"],
                                },
                                "minContains": (
                                    1
                                    if all_need_fresh_evidence
                                    and not committed_communicative
                                    else 0
                                ),
                            }
                        }
                    },
                },
            ]
        )
        if all_need_fresh_evidence and committed_communicative:
            for conditional in schema["allOf"]:
                condition = conditional.get("if", {})
                disposition_values = (
                    condition.get("properties", {})
                    .get("disposition", {})
                    .get("enum", [])
                )
                if disposition_values != ["execute", "mixed"]:
                    continue
                activity_constraint = (
                    conditional.setdefault("then", {})
                    .setdefault("properties", {})
                    .setdefault("activities", {})
                )
                activity_constraint["prefixItems"] = [
                    {"$ref": "#/$defs/FastPlannerCapabilityActivity"}
                ]
                break
        reason_summary = top_properties.get("reason_summary")
        if isinstance(reason_summary, dict):
            reason_summary["maxLength"] = 100
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
        information_gap_contract = definitions.get("PlannerInformationGap")
        if isinstance(information_gap_contract, dict):
            gap_properties = information_gap_contract.get("properties")
            if isinstance(gap_properties, dict):
                # PlannerInformationGap appears only inside a clarification Act in
                # this decoder contract.  Encode the Act invariant directly so the
                # model's one mechanical revision receives the deeper input-schema
                # error instead of failing first on a duplicate Pydantic invariant.
                gap_properties["preferred_resolution"] = {
                    "const": "ask_user",
                    "type": "string",
                }
                gap_properties["blocking"] = {
                    "const": True,
                    "default": True,
                    "type": "boolean",
                }
                gap_properties["resolved"] = {
                    "const": False,
                    "default": False,
                    "type": "boolean",
                }
                required_for = gap_properties.get("required_for")
                if isinstance(required_for, dict):
                    required_for["minItems"] = 1
                if interpretation_unresolved == []:
                    gap_properties["source_kind"] = {
                        "const": "execution_input",
                        "type": "string",
                    }
                    applicable_capability_ids = [
                        str(item.get("capability_id") or "").strip()
                        for item in (capabilities or [])
                        if isinstance(item, dict)
                        and str(item.get("capability_id") or "").strip()
                    ]
                    if applicable_capability_ids:
                        gap_properties["source_reference"] = {
                            "type": "string",
                            "enum": applicable_capability_ids,
                        }
        clarification_contract = definitions.get("FastPlannerClarificationAct")
        if isinstance(clarification_contract, dict):
            gaps = clarification_contract.get("properties", {}).get(
                "information_gaps"
            )
            if isinstance(gaps, dict):
                gaps["maxItems"] = 1
        if all_need_fresh_evidence:
            activities = top_properties.get("activities")
            activity_items = (
                activities.get("items") if isinstance(activities, dict) else None
            )
            allowed_activity_contracts = [
                "FastPlannerCapabilityActivity",
                "FastPlannerClarificationAct",
            ]
            if suppress_new_communicative or committed_communicative:
                allowed_activity_contracts = ["FastPlannerCapabilityActivity"]
            elif not committed_communicative:
                allowed_activity_contracts.insert(0, "FastPlannerProgressAct")
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
        elif all_need_work or committed_communicative or suppress_new_communicative:
            # The first-response phase has already made its one immutable
            # progress decision.  Runtime validation has always rejected a
            # second progress Act here, but the general body/media/state-change
            # decoder still advertised that impossible branch and forced a
            # mechanical repair.  Keep genuine terminal work and a real
            # clarification available; remove only the already-decided progress
            # function from the model-facing contract.
            activities = top_properties.get("activities")
            activity_items = (
                activities.get("items") if isinstance(activities, dict) else None
            )
            allowed_activity_contracts = [
                "FastPlannerCapabilityActivity",
                "FastPlannerClarificationAct",
            ]
            if not all_need_work:
                allowed_activity_contracts.append(
                    "FastPlannerCompleteResponseAct"
                )
            if not committed_communicative and not suppress_new_communicative:
                allowed_activity_contracts.insert(0, "FastPlannerProgressAct")
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
                            if ref.rsplit("/", 1)[-1]
                            in allowed_activity_contracts
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
            # These values are fixed by the selected progress_kind contract and
            # Pydantic validation. Omitting their duplicate decoder properties
            # keeps the low-latency response schema small without moving wording
            # or semantic-function ownership out of Fast Planner.
            progress_contract.pop("allOf", None)
            progress_properties = progress_contract.get("properties")
            if isinstance(progress_properties, dict):
                for field_name in (
                    "evidence_refs",
                    "speech_act",
                    "timing",
                    "truth_stage",
                ):
                    progress_properties.pop(field_name, None)
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
            # The compact prompt projection already carries every allowed
            # argument contract. Decoder-time duplication of every full schema
            # inflated the first-response context. Host validation below remains
            # the sole acceptance boundary for the Planner-authored args.
            capability_contract.pop("allOf", None)
            capability_properties = capability_contract.get("properties")
            if isinstance(capability_properties, dict):
                capability_properties.pop("reason_summary", None)
        return schema

    @staticmethod
    def _first_response_phase_decided(request: CognitiveWorkRequest) -> bool:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("fast_planner_first_response")
        if not isinstance(raw, dict):
            return False
        try:
            FastPlannerFirstResponse.model_validate(raw)
        except ValidationError:
            return False
        return True

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
        numeric_args_by_ref: dict[str, set[Decimal]] = {
            ref: set() for ref in responsibility_refs
        }
        for activity in capability_activities:
            activity_numbers = _semantic_numeric_values(activity.args)
            for source_ref in activity.source_responsibility_refs:
                if source_ref in numeric_args_by_ref:
                    numeric_args_by_ref[source_ref].update(activity_numbers)
        for source_ref, source in by_ref.items():
            required_numbers = _semantic_numeric_values(source.bindings)
            missing_numbers = sorted(
                required_numbers - numeric_args_by_ref.get(source_ref, set())
            )
            if missing_numbers and any(
                source_ref in activity.source_responsibility_refs
                for activity in capability_activities
            ):
                raise PlannerDTOContractError(
                    "Fast Planner Capability args omitted explicit numeric "
                    f"Responsibility bindings for {source_ref}: "
                    + ",".join(str(value) for value in missing_numbers)
                )
        if output.disposition in {"execute", "respond", "clarify", "mixed"}:
            terminal_roles = {"capability", "complete_response", "clarification"}
            terminal_refs = {
                source_ref
                for activity in output.activities
                if activity.role in terminal_roles
                for source_ref in activity.source_responsibility_refs
            }
            missing_terminal_refs = set(responsibility_refs) - terminal_refs
            if missing_terminal_refs:
                raise PlannerDTOContractError(
                    "Fast Planner must supply one terminal Activity for every "
                    "authoritative Responsibility before claiming a terminal "
                    "disposition; missing="
                    + ",".join(sorted(missing_terminal_refs))
                )
        if all(item.completion_requires_fresh_evidence for item in responsibilities) and not (
            clarification_activities
            or complete_response_activities
            or any(item.role == "progress" for item in output.activities)
            or self._first_response_phase_decided(request)
        ):
            raise PlannerDTOContractError(
                "fresh-evidence Fast work requires a Communicative Main Activity"
            )
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
            for source_ref in activity.source_responsibility_refs:
                source = by_ref[source_ref]
                if source.output_mode not in set(VOCAL_MODES) - {"speech"}:
                    continue
                if (
                    activity.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
                    or activity.args.get("mode") != source.output_mode
                ):
                    raise PlannerDTOContractError(
                        "Fast Planner must preserve a mode-specific vocal "
                        "Responsibility through the exact qualified vocal provider; "
                        f"source_ref={source_ref} expected_capability="
                        f"{VOCAL_PERFORMANCE_CAPABILITY_ID} expected_mode="
                        f"{source.output_mode} actual_capability="
                        f"{activity.capability_id} actual_mode="
                        f"{activity.args.get('mode')!r}. Ordinary speech, media, and "
                        "body Activities are not completion evidence for that mode."
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
            input_schema = definition.get("input_schema") or {}
            properties = input_schema.get("properties") or {}
            required_inputs = set(input_schema.get("required") or [])
            authoritative_bindings = {
                str(name): value
                for ref in activity.source_responsibility_refs
                for name, value in by_ref[ref].bindings.items()
            }
            for parameter in sorted(required_inputs):
                parameter_schema = properties.get(parameter)
                if not isinstance(parameter_schema, dict):
                    continue
                if "default" in parameter_schema:
                    continue
                if parameter not in authoritative_bindings:
                    raise _AuthoritativeGroundingValidationError(
                        "Fast Planner cannot invent an unbound required Capability "
                        f"input before canonical Goal grounding: "
                        f"{activity.capability_id}.{parameter}"
                    )
                actual = activity.args.get(parameter)
                expected = authoritative_bindings[parameter]
                if actual != expected and str(actual).strip() != str(expected).strip():
                    raise _AuthoritativeGroundingValidationError(
                        "Fast Planner required Capability input contradicts GI "
                        f"binding: {activity.capability_id}.{parameter}"
                    )

    @staticmethod
    def _advance_fail_safe(
        request: CognitiveWorkRequest,
        *,
        responsibility_refs: list[str],
        error: Exception,
        raw_output: Any,
        committed_communicative_activities: list[Any] | None = None,
        allow_progress_salvage: bool = True,
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
        progress_activities = (
            FastPlannerResolver._validated_fail_safe_progress(
                raw_output,
                responsibility_refs=responsibility_refs,
            )
            if allow_progress_salvage
            else []
        )
        retained_communicative_activities = list(
            committed_communicative_activities or []
        )
        retained_ids = {
            item.activity_id for item in retained_communicative_activities
        }
        for item in progress_activities:
            if item.activity_id in retained_ids:
                continue
            retained_communicative_activities.append(item)
            retained_ids.add(item.activity_id)
        return FastPlannerAdvance(
            turn_id=str(request.sid or "turn-fast-advance"),
            disposition="unavailable",
            coverage="uncertain",
            covered_responsibility_refs=responsibility_refs,
            activities=retained_communicative_activities,
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
                    item.activity_id for item in retained_communicative_activities
                ],
                "progress_salvage_suppressed_by_first_response_decision": (
                    not allow_progress_salvage
                ),
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
                activity.text,
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
        reentry_goal_ids = result_evidence_reentry_goal_ids(context)
        if reentry_goal_ids == set(expected_goal_ids_for_turn):
            response_only = True
            requires_execution = False
            response_goal_ids = list(expected_goal_ids_for_turn)
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
            "num_predict": self.num_predict,
        }
        previous_raw: Any = None
        initial_raw_output: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False
        for attempt in range(self.max_contract_repairs + 1):
            raw: Any = None
            numeric_provenance_repairs: list[dict[str, Any]] = []
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
                        "fast_planner_numeric_provenance_normalized sid=%s repairs=%s",
                        request.sid,
                        self._bounded(numeric_provenance_repairs, 2000),
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
                    self._validate_work_reuse_selection(
                        validated_model_output,
                        context=request.context,
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
                except ValueError as exc:
                    # A missing or internally inconsistent provenance record is
                    # a mechanically malformed Planner DTO. One same-stage repair
                    # may add or correct that record without changing Goal meaning,
                    # Capability selection, or executable arguments.
                    raise PlannerDTOContractError(str(exc)) from exc
                try:
                    validate_goal_binding_argument_grounding(
                        validated_model_output,
                        authoritative_goals=authoritative_goals,
                        capabilities=capability_payload,
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
            if (
                reentry_goal_ids
                and validated.disposition == "respond"
                and validated.response_text
            ):
                try:
                    evidence_truth = await self._qualify_evidence_response_truth(
                        request,
                        plan=validated,
                    )
                except Exception as exc:
                    logger.warning(
                        "fast_planner_evidence_response_truth_unavailable "
                        "sid=%s error_type=%s error=%s",
                        request.sid,
                        type(exc).__name__,
                        exc,
                    )
                    return self._escalation(
                        plan_id,
                        request,
                        "fast_planner_evidence_response_truth_unavailable",
                        error=exc,
                        unresolved=[
                            "Post-Evidence wording could not be truth-qualified."
                        ],
                        path_classification="semantic_escalation",
                    )
                qualification = evidence_truth.model_dump(
                    mode="json", exclude_none=True, exclude_defaults=True
                )
                if evidence_truth.decision != "accept":
                    logger.warning(
                        "fast_planner_evidence_response_truth_rejected sid=%s",
                        request.sid,
                    )
                    return self._escalation(
                        plan_id,
                        request,
                        "fast_planner_evidence_response_truth_rejected",
                        unresolved=[
                            "Post-Evidence wording must preserve probability below "
                            "100% as uncertainty rather than certainty."
                        ],
                        path_classification="semantic_escalation",
                        metadata={
                            "evidence_response_truth_qualification": qualification,
                            "execution_allowed": False,
                        },
                    )
                metadata = dict(validated.metadata)
                metadata["evidence_response_truth_qualification"] = qualification
                validated = validated.model_copy(update={"metadata": metadata})
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
            if numeric_provenance_repairs:
                metadata = dict(validated.metadata)
                metadata["numeric_provenance_normalization"] = {
                    "strategy": "copy_exact_owned_step_argument",
                    "repairs": numeric_provenance_repairs,
                    "semantic_plan_unchanged": True,
                }
                validated = validated.model_copy(update={"metadata": metadata})
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

    @staticmethod
    def _validate_work_reuse_selection(
        output: Any,
        *,
        context: dict[str, Any] | None,
    ) -> None:
        """Validate explicit Planner reuse references without choosing reuse.

        Fast Planner owns the semantic decision by either citing a supplied
        provisional Activity ID or omitting it. This check is deliberately
        mechanical: cited IDs must exist and the selected step must preserve
        the Activity's immutable Capability, arguments, and timing. The Host
        later validates canonical Goal ownership and live runtime state.
        """

        raw_activities = (context or {}).get(
            "work_reconciliation_activities"
        )
        activities = (
            [item for item in raw_activities if isinstance(item, dict)]
            if isinstance(raw_activities, list)
            else []
        )
        by_id = {
            str(item.get("activity_id") or "").strip(): item
            for item in activities
            if str(item.get("activity_id") or "").strip()
        }
        cited: set[str] = set()
        for step in output.steps:
            activity_id = str(step.reuse_activity_id or "").strip()
            if not activity_id:
                continue
            if activity_id in cited:
                raise PlannerDTOContractError(
                    f"reuse_activity_id is duplicated: {activity_id}"
                )
            cited.add(activity_id)
            activity = by_id.get(activity_id)
            if activity is None:
                raise PlannerDTOContractError(
                    f"reuse_activity_id was not supplied by Runtime: {activity_id}"
                )
            if step.capability_id != str(activity.get("capability_id") or ""):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes capability_id"
                )
            if step.args != dict(activity.get("args") or {}):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes immutable args"
                )
            if step.timing != str(activity.get("timing") or "sequential"):
                raise PlannerDTOContractError(
                    f"reuse_activity_id {activity_id} changes timing"
                )

        # The supplied reconciliation projection is one bounded snapshot.
        # Reusing any member currently requires selecting every member; extra
        # newly planned steps remain legal and execute beside the reused set.
        if cited and cited != set(by_id):
            raise PlannerDTOContractError(
                "Work reuse must select the complete supplied "
                "Activity set"
            )
        if cited and any(
            by_id[activity_id].get("origin") == "retained_runtime"
            for activity_id in cited
        ) and len(output.steps) != len(cited):
            raise PlannerDTOContractError(
                "retained Runtime Work reuse cannot add steps to the "
                "reconciliation-only Plan"
            )

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
        result_evidence_contract = (
            "Host-bound terminal Evidence completes the provider-read prerequisite for "
            "the exact canonical Goals. Answer from trusted_terminal_evidence only, "
            "preserve its values, scope, and epistemic strength, and return a respond "
            "Plan with zero steps. An observation, forecast, estimate, and probability "
            "are different claims. A probability below 100% must remain uncertain in "
            "the answer and must not become an unqualified claim that the event will "
            "occur. "
            if isinstance(context.get("result_evidence_reentry"), dict)
            else ""
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
        semantic_scope_contract = "For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility while treating the current capability catalog as the dynamic decomposition boundary. Fast Planner may terminally execute the Goal only when one exact registered Capability is a complete one-step cover. A provider's resource_contract.plan_requires/plan_provides declares public composition state; provider-internal stages remain private unless exposed as capabilities. If the catalog has only partial resource capabilities that could form a multi-step chain, escalate to Deep Planner rather than inventing hidden provider stages or claiming a partial primitive is complete. The Goal is provider-neutral: choose from the catalog by declared semantic scope and resource contract, never from capability-name conventions or a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected complete capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. Capability domains are not interchangeable merely because each reads current information: a local-clock capability covers only declared clock facts, a weather capability covers only declared weather facts, and neither covers environmental person-presence or direct perception. Never choose the nearest read-only capability from another domain. When the selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Those complete structured arguments are already grounded by the Goal contract; do not emit parameter_resolutions for their nested fields or invent a top-level quantity/distance argument that the Capability does not accept. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material tool argument, especially location, date, target, and entity identity, must equal the corresponding canonical binding; never reinterpret an original pronoun or replace a binding with an older memory entry. For chromie.weather.lookup, keep args.location exactly equal to the canonical location binding. When the user or discourse context clearly supplies a hierarchical place, you may also provide location_context with locality, admin1, country, and aliases for that same place; never use it to select a different place. Preserve every canonical-goal qualifier, including temporal scope, comparison period, answer shape, ordering, and concurrency. A calendar-date argument does not cover a finer day-part binding: exact coverage requires a capability argument and declared output evidence for that same day part. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; in particular, a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech whose exact wording you own. A user-requested spoken response or performance may still be simultaneous with an Activity-lane step. Preserve that relation without inventing a chromie.speak plan step: keep the spoken Goal as a respond outcome, set each participating Activity step to timing=parallel only when its provider declares safe parallel execution, and leave cross-lane scheduling to trusted Runtime. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, escalate or propose an explicit safe adjustment rather than silently serializing the request. Never silently narrow a goal to fit a capability or its enum defaults. If the goal falls outside a capability's supported scope, escalate for clarification, another capability, or an honest unavailable result with zero steps. "
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
        provisional_fast_activities = context.get(
            "work_reconciliation_activities"
        )
        provisional_work_contract = (
            "The listed retained or provisional Runtime Activities may already be "
            "running or completed. Decide from the canonical Goals whether their Work "
            "is still required. To preserve and reuse the complete provisional plan, "
            "set each corresponding step.reuse_activity_id to the supplied stable "
            "activity_id and preserve the same Capability ID, exact arguments, Goal "
            "ownership, and timing. Omitting reuse_activity_id means that Activity is "
            "not selected for reuse. The Host will validate the explicit selection "
            "mechanically and will not execute selected Work twice. If any Work is no "
            "longer applicable or additional/different Work is required, author the "
            "correct complete canonical Plan instead; Runtime will then cancel only "
            "pending/cancellable provisional Work. Do not treat provisional execution "
            "as Goal Evidence before Host binding. Reusing retained_runtime Work is a "
            "reconciliation-only Plan and cannot add steps; when additional Work is "
            "needed, omit all reuse_activity_id values and author the complete replacement "
            "Plan so Runtime can cancel the old group before dispatch. "
            if isinstance(provisional_fast_activities, list)
            and provisional_fast_activities
            else "This is prospective planning: no retained or provisional Runtime Work is supplied for reconciliation. "
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
                f"Host-bound terminal Evidence JSON:\n{self._bounded(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
                f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
                f"Retained or provisional Runtime Activities for Work reconciliation JSON:\n{self._bounded(provisional_fast_activities or [], 3500)}\n\n"
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
                f"{result_evidence_contract}{goal_execution_contract}"
                f"{concise_output_contract}"
                f"{provisional_work_contract}"
                "Author stable non-empty step_id values, exact source_goal_ids, and matching outcome step_ids yourself. "
                "A planned step or response counts as satisfying its goal if it would succeed. For each keyed goal outcome, judge only that one goal; never put sibling goals or pending execution in unmet_goal_ids or unmet_requirements. Complete terminal outcomes use exact satisfaction with both unmet lists empty. "
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
            f"Host-bound terminal Evidence JSON:\n{self._bounded(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
            f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Retained or provisional Runtime Activities for Work reconciliation JSON:\n{self._bounded(provisional_fast_activities or [], 3500)}\n\n"
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
            f"{result_evidence_contract}{goal_execution_contract}"
            f"{concise_output_contract}"
            f"{provisional_work_contract}"
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
            "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently.\n"
            f"FINAL RESULT-EVIDENCE WORDING CONTRACT:\n{result_evidence_contract or 'not_applicable'}"
        )

    def _advance_layered_prompt(
        self,
        request: CognitiveWorkRequest,
        *,
        responsibilities: list[CognitiveResponsibilityProposal],
        capabilities: list[dict[str, Any]],
        committed_communicative_activities: list[Any] | None = None,
        first_response_decided: bool = False,
        validation_errors: str = "",
    ) -> LayeredPrompt:
        context = request.context if isinstance(request.context, dict) else {}
        advance_contract = (
            "Responsibility evidence is authoritative contextual WHAT. Fast Planner owns "
            "the first complete HOW decision over that evidence: speaking and Capability "
            "Activities plus their sequential/parallel timing. Goal Association runs at "
            "the same time from the same GI result and alone commits Canonical Goal state. "
            "A speaking Activity is a Communicative Act: select its function, exact natural "
            "wording, truth stage, and semantic provenance. The Host validates and realizes "
            "that immutable act; Trusted Capability Runtime alone authorizes execution."
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
        committed_communicative_json = self._bounded(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in (committed_communicative_activities or [])
            ],
            900,
        )
        if committed_communicative_activities:
            communication_instruction = (
                "A Fast Planner Communicative Activity has already been committed and "
                "is shown below. Do not repeat, replace, translate, or re-author it in "
                "activities. Continue the same HOW decision with only the still-needed "
                "Capability or clarification Activities."
            )
        elif first_response_decided:
            communication_instruction = (
                "The bounded first-response phase completed with no committed speech. "
                "Do not bypass that decision by authoring a replacement progress "
                "Activity. Continue with only the still-needed Capability or genuine "
                "source-grounded clarification Activities."
            )
        else:
            communication_instruction = (
                "No Fast Planner Communicative Activity decision exists yet."
            )
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
            + "\n\nAlready committed Fast Planner Communicative Activity JSON:\n"
            + committed_communicative_json
            + "\n"
            + communication_instruction
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
            "include one short progress Activity with progress_kind=check_information "
            "for fresh external information work only when no committed Fast Planner "
            "Communicative Activity is supplied above. Never fuse progress wording into "
            "a Capability Activity or use a Capability ID as a progress activity_id.\n\n"
            "Cover every Responsibility ref exactly. Activities are one ordered list. "
            "Speaking is an Activity and uses the same timing field as Capability work. "
            "Use parallel only when activities can genuinely overlap without a declared "
            "resource or safety conflict; list dependent work sequentially. A progress "
            "Activity has progress_kind, exact text, truth_stage=pre_evidence, and no "
            "evidence_refs. Its text may acknowledge or prospectively describe the "
            "check but must not state a result that has not been observed. Every "
            "Communicative Activity owns its exact natural wording; do not emit "
            "response_text inside an Activity. Use truth_stage=context_grounded for "
            "ordinary answers and clarification, and truth_stage=post_evidence with "
            "exact evidence_refs only when supplied trusted Evidence supports it. A "
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
            "for. Preserve speaker, experiencer, and actor ownership: a human report of "
            "their feeling or state does not request any robot body state, stop, posture, "
            "gesture, or other physical effect. Preserve every GI binding, "
            "including all independent temporal dimensions. When fresh Evidence is still "
            "needed and no committed Communicative Activity is supplied above, add one "
            "concise progress speaking Activity that does not claim a result. Every "
            "Communicative Activity must use the requested response language; zh or "
            "zh-CN requires natural Chinese, never English or pinyin. Use short Activity "
            "IDs, omit optional default fields, and keep "
            "reason_summary under one brief clause. Use disposition=escalate and "
            "continuation=deep_planner only when HOW "
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
                    "when_not_to_use": str(hints.get("when_not_to_use") or "")[:360],
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
            "Speaking Activities are Communicative Acts: select their function, exact "
            "natural wording, timing, truth stage, and Responsibility/InformationGap "
            "provenance; speech_act remains a closed communicative-function enum. Ask "
            "through a clarification act when a required user-resolvable "
            "binding is genuinely absent after checking GI bindings and Capability defaults; "
            "never reinterpret a present normalized binding as missing or ambiguous. Select "
            "only a Capability whose declared description, effects, and semantic scope match "
            "the requested outcome; information reads are not physical-object delivery or "
            "decorative body motion. Delegate only genuinely complex HOW to Deep Planner. Goal "
            "Association separately owns Canonical Goal commits, and Trusted Capability "
            "Runtime owns execution authority and mechanically realizes Planner wording. "
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
        if result_evidence_reentry_goal_ids(request.context) == set(
            expected_goal_ids_for_turn
        ):
            requires_execution = False
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
