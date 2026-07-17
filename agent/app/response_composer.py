from __future__ import annotations

import hashlib
import json
import logging
import copy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SkipValidation, ValidationError

from .capabilities.validator import normalize_args_for_schema, validate_args_for_schema
from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .schema import AgentRunRequest

try:
    from chromie_contracts.plan import CanonicalPlan
    from chromie_contracts.response_composition import (
        CoordinatedResponsePlan,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
    )
    from chromie_contracts.semantic_task import (
        ResponsePlan,
        pending_action_stage_direction_claims,
    )
    from chromie_contracts.social_attention import (
        SocialAttentionBehavior,
        SocialAttentionPlan,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan
    from shared.chromie_contracts.response_composition import (
        CoordinatedResponsePlan,
        ResponseCompositionResolution,
        canonical_plan_fingerprint,
    )
    from shared.chromie_contracts.semantic_task import (
        ResponsePlan,
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
    # Keep the real model-facing schema while preserving the existing fail-soft
    # deterministic validation of optional social attention below.
    social_attention_plan: SkipValidation[SocialAttentionPlan | None] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class ResponseComposerResolver:
    """Advisory composition of truthful speech and optional social attention."""

    def __init__(self, ollama: OllamaClient, *, num_ctx: int = 4096, num_predict: int = 640) -> None:
        self.ollama = ollama
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: AgentRunRequest) -> ResponseCompositionResolution:
        plan = self._canonical_plan(request.context)
        if plan is None or plan.disposition == "escalate":
            return ResponseCompositionResolution(
                status="invalid_input",
                reason_summary="A terminal CanonicalPlan is required before response composition.",
                metadata={"authority": "advisory", "resolver": "response_composer"},
            )
        composition_id = self._composition_id(request, plan)
        response_schema = self._response_schema(plan)
        previous_raw: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False
        for attempt in range(2):
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
                )
                if not isinstance(raw, dict):
                    raise ValueError("response composer output is not a JSON object")
                model_output = ResponseComposerModelOutput.model_validate(raw)
                premature_claims = self._pending_action_claim_errors(
                    model_output.response_plan,
                    plan=plan,
                )
                if premature_claims:
                    raise ValueError("; ".join(premature_claims))
                social_plan, social_reasons = self._validated_social_plan(
                    model_output.social_attention_plan,
                    plan=plan,
                    context=request.context,
                )
                composition = CoordinatedResponsePlan(
                    composition_id=composition_id,
                    canonical_plan_id=plan.plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
                    canonical_plan=plan,
                    response_plan=model_output.response_plan,
                    social_attention_plan=social_plan,
                    confidence=model_output.confidence,
                    rationale=model_output.rationale,
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "task_plan_immutable": True,
                        "social_attention_validation_reasons": social_reasons,
                        "contract_schema": "ResponseComposerModelOutput",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": contract_repair_attempted,
                    },
                )
                return ResponseCompositionResolution(
                    status="resolved",
                    composition=composition,
                    reason_summary="Task, speech, and optional attention plans were coordinated.",
                    metadata={
                        "authority": "advisory",
                        "resolver": "response_composer",
                        "contract_schema": "ResponseComposerModelOutput",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": contract_repair_attempted,
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
                if attempt == 0 and isinstance(
                    exc, (ValidationError, json.JSONDecodeError, ValueError)
                ):
                    contract_repair_attempted = True
                    previous_raw = raw
                    initial_validation_errors = self._validation_error_json(exc)
                    continue
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
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output": self._bounded(previous_raw, 5000)
                        if contract_repair_attempted and previous_raw is not None
                        else "",
                        "repair_raw_output": self._bounded(raw, 5000)
                        if contract_repair_attempted and raw is not None
                        else "",
                        **failure,
                    },
                )
        raise AssertionError("unreachable")

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
    def _response_schema(plan: CanonicalPlan) -> dict[str, Any]:
        schema = copy.deepcopy(ResponseComposerModelOutput.model_json_schema())
        schema["title"] = "ResponseComposerModelOutput"
        goal_ids = list(dict.fromkeys(plan.goal_ids))

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    covers_goal_ids = properties.get("covers_goal_ids")
                    if isinstance(covers_goal_ids, dict) and goal_ids:
                        covers_goal_ids["items"] = {
                            "type": "string",
                            "enum": goal_ids,
                        }
                        covers_goal_ids["minItems"] = 1
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
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
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
        plan: CanonicalPlan,
        context: dict[str, Any],
    ) -> tuple[SocialAttentionPlan | None, list[str]]:
        if value is None:
            return None, []
        try:
            proposed = SocialAttentionPlan.model_validate(value)
        except ValidationError as exc:
            return None, [f"invalid_social_attention_plan:{type(exc).__name__}"]

        metadata = dict(proposed.metadata)
        metadata.update({"authority": "advisory", "auxiliary_social_attention": True})
        if proposed.decision == "none":
            return proposed.model_copy(update={"metadata": metadata}), []

        reasons: list[str] = []
        target_reason = self._validate_target(proposed, context)
        if target_reason:
            reasons.append(target_reason)

        candidates = self._candidate_map(context)
        primary_ids = {step.skill_id for step in plan.steps}
        validated_behaviors: list[SocialAttentionBehavior] = []
        seen: set[str] = set()
        for behavior in proposed.behaviors:
            candidate = candidates.get(behavior.skill_id)
            if candidate is None:
                reasons.append(f"unknown_social_skill:{behavior.skill_id}")
                continue
            if behavior.skill_id in primary_ids or behavior.skill_id in seen:
                reasons.append(f"duplicate_or_primary_skill:{behavior.skill_id}")
                continue
            if candidate.get("available") is False or candidate.get("interaction_executable") is not True:
                reasons.append(f"unavailable_social_skill:{behavior.skill_id}")
                continue
            if bool(candidate.get("requires_confirmation")):
                reasons.append(f"confirmation_required:{behavior.skill_id}")
                continue
            schema = candidate.get("input_schema")
            if not isinstance(schema, dict):
                schema = {}
            target_args_reason = self._validate_target_args(
                behavior.args, schema, context
            )
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

        if target_reason or not validated_behaviors:
            none_plan = SocialAttentionPlan(
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
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            properties = {}
        target_fields = {
            key
            for key in properties
            if str(key).startswith("target_")
            or str(key) in {"head_yaw_rad", "head_pitch_rad", "yaw_rad", "pitch_rad"}
        }
        if not target_fields:
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "targeted behavior requires target evidence"
        target = evidence.get("target")
        if not isinstance(target, dict):
            target = {}
        suggested = target.get("suggested_args")
        if not isinstance(suggested, dict):
            suggested = {}
        for key, expected in suggested.items():
            if key not in args:
                continue
            actual = args.get(key)
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                if abs(float(expected) - float(actual)) > 1e-6:
                    return f"{key} does not match target evidence"
            elif actual != expected:
                return f"{key} does not match target evidence"
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
        plan: CanonicalPlan,
        social_candidate: dict[str, Any],
        candidates: dict[str, dict[str, Any]],
        timing: str,
    ) -> bool:
        if not plan.steps:
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
        return (
            f"User turn:\n{request.text}\n\n"
            f"Immutable CanonicalPlan JSON:\n{self._bounded(plan.model_dump(mode='json'), 14000)}\n\n"
            f"Active goals JSON:\n{self._bounded(context.get('active_goal_snapshots') or [], 4500)}\n\n"
            f"Social-attention candidates JSON:\n{self._bounded(context.get('social_attention_candidates') or [], 8000)}\n\n"
            f"Attention target evidence JSON:\n{self._bounded(context.get('social_attention_target_evidence') or {'available': False}, 2500)}\n\n"
            f"Previous Response Composer output when revising:\n{self._bounded(previous_raw, 5000) if previous_raw is not None else 'null'}\n\n"
            f"Exact contract validation errors when revising:\n{validation_errors or '[]'}\n\n"
            "Compose one ResponsePlan and, only when socially useful and evidence-supported, an optional SocialAttentionPlan. "
            "The CanonicalPlan is immutable: do not alter, replace, add, remove, reorder, authorize, or execute its steps. "
            "Every plan goal_id must be covered exactly through response stage covers_goal_ids; do not invent goal IDs. "
            "For execute plans this is pre-execution composition: use only none/heard/evaluating/waiting_for_user commitments, set must_not_claim_completion=true, and omit final. "
            "For mixed plans, coordinate executable and conversational goals in one natural response: use prospective wording for pending physical steps, do not narrate them with stage directions such as *Blinks twice*, do not claim completion, omit final while work is pending, and include a specific waiting_for_user clarification stage for every clarify outcome. "
            "For clarify, name the actual unresolved need naturally and use waiting_for_user. For alternatives, explain the change and request approval. "
            "Social attention is auxiliary interaction behavior, never a user goal or task step; choose decision=none when stillness is more natural, safer, unsupported, or unnecessary. "
            "response_plan must be a JSON object with only immediate, pre_action, progress, and final fields; it is never a bare list. "
            "The decoder enforces the exact ResponseComposerModelOutput JSON Schema. Return JSON with response_plan, optional social_attention_plan, confidence, and rationale only."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Response Composer. Coordinate truthful speech and optional social presence around an immutable CanonicalPlan. "
            "You do not plan tasks, mutate goals, execute, authorize, or claim unobserved completion. Return JSON only."
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You revise one Response Composer output using the immutable CanonicalPlan, exact validation errors, and the supplied ResponseComposerModelOutput JSON Schema. "
            "Preserve truthful wording and goal coverage, but correct the JSON structure and coordination invariants. Return only the corrected JSON object."
        )
