from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from .capabilities.validator import normalize_args_for_schema, validate_args_for_schema
from .clients.ollama_client import llm_failure_metadata
from .schema import AgentRunRequest

try:
    from chromie_contracts.interaction import SkillRequest
    from chromie_contracts.social_attention import SocialAttentionPlan, SocialAttentionRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import SkillRequest
    from shared.chromie_contracts.social_attention import SocialAttentionPlan, SocialAttentionRequest

logger = logging.getLogger("chromie.agent.social_attention")


class SocialAttentionPlanner:
    """Model-driven auxiliary body-decoration planning.

    Social Attention is background social cognition. The model decides whether
    a small body decoration would make the anchored interaction more socially
    natural without changing its Goal, response text, or completion, and selects exact
    catalog skills for the scene. Response wording remains owned by the normal
    cognitive/Response Composer path; this planner is body-only. Deterministic code validates
    schemas, evidence, safety, and resource conflicts without choosing actions.
    """

    def __init__(self, services: Any) -> None:
        self.services = services

    async def plan(
        self, request: AgentRunRequest | SocialAttentionRequest
    ) -> SocialAttentionPlan | None:
        client = self.services.social_attention_ollama
        candidates = request.context.get("social_attention_candidates")
        if client is None or not isinstance(candidates, list) or not candidates:
            return None

        session_id = (
            request.session_id
            if isinstance(request, SocialAttentionRequest)
            else request.sid
        )
        prompt = self._prompt(request, candidates)
        response_schema = self._response_schema(candidates)
        system_prompt = (
            "You are Chromie's background Social Attention planner. Choose only small, "
            "scene-appropriate body decorations for the supplied interaction anchor from "
            "the supplied catalog. Decorations must remain optional, non-disruptive, and "
            "subordinate to the primary behavior. Do not use phrase-to-skill rules, do not "
            "author or alter speech, and return JSON only."
        )
        generation_options = {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_ctx": int(self.services.social_attention_num_ctx),
            "num_predict": int(self.services.social_attention_num_predict),
        }
        started = time.perf_counter()
        logger.info(
            "social_attention_plan_start sid=%s mode=%s timeout_ms=%s num_ctx=%s "
            "num_predict=%s prompt_chars=%s candidates=%s",
            session_id,
            self.services.effective_social_attention_mode(),
            getattr(client, "timeout_ms", None),
            int(self.services.social_attention_num_ctx),
            int(self.services.social_attention_num_predict),
            len(prompt),
            len(candidates),
        )
        try:
            raw = await client.generate(
                prompt,
                system=system_prompt,
                options=generation_options,
                response_format=response_schema,
                prompt_family="social_attention.primary",
                turn_id=session_id,
                attempt=1,
            )
        except Exception as exc:
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                **llm_failure_metadata(exc),
                "stage": "social_attention",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "elapsed_ms": round(planner_ms, 1),
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_failed sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=%s elapsed_ms=%.1f "
                "error_type=%s error=%s",
                session_id,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                failure.get("architecture_attribution"),
                str(bool(failure.get("retryable"))).lower(),
                planner_ms,
                type(exc).__name__,
                exc,
            )
            return None
        if not isinstance(raw, dict):
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                "stage": "social_attention",
                "failure_class": "structured_output_invalid",
                "failure_domain": "model_contract",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
                "error_type": type(raw).__name__,
                "error": "social attention model did not return a JSON object",
                "elapsed_ms": round(planner_ms, 1),
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_invalid sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=true elapsed_ms=%.1f error=%s",
                session_id,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                planner_ms,
                failure["error"],
            )
            return None
        repair_attempted = False
        repair_succeeded = False
        validation_error: Exception | None = None
        try:
            plan = SocialAttentionPlan.model_validate(raw)
        except ValidationError as initial_exc:
            repair_attempted = True
            logger.warning(
                "social_attention_contract_repair_start sid=%s validation_errors=%s",
                session_id,
                self._validation_error_json(initial_exc),
            )
            try:
                repaired = await client.generate(
                    self._repair_prompt(
                        prompt=prompt,
                        raw=raw,
                        validation_error=initial_exc,
                    ),
                    system=system_prompt,
                    options=generation_options,
                    response_format=response_schema,
                    prompt_family="social_attention.contract_repair",
                    turn_id=session_id,
                    attempt=2,
                )
                if not isinstance(repaired, dict):
                    raise ValueError(
                        "social attention contract repair did not return a JSON object"
                    )
                plan = SocialAttentionPlan.model_validate(repaired)
                repair_succeeded = True
                logger.info(
                    "social_attention_contract_repair_done sid=%s status=success",
                    session_id,
                )
            except Exception as repair_exc:
                validation_error = repair_exc
        if validation_error is not None:
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                **llm_failure_metadata(validation_error),
                "stage": "social_attention",
                "error_type": type(validation_error).__name__,
                "error": str(validation_error)[:500],
                "elapsed_ms": round(planner_ms, 1),
                "contract_repair_attempted": repair_attempted,
                "contract_repair_succeeded": False,
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_invalid sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=%s elapsed_ms=%.1f error=%s",
                session_id,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                failure.get("architecture_attribution"),
                str(bool(failure.get("retryable"))).lower(),
                planner_ms,
                validation_error,
            )
            return None
        planner_ms = (time.perf_counter() - started) * 1000.0
        request.context.pop("social_attention_failure", None)
        plan.metadata = {
            **plan.metadata,
            "planner_ms": round(planner_ms, 1),
            "architecture_attribution": "not_evaluated",
            "contract_repair": {
                "attempted": repair_attempted,
                "succeeded": repair_succeeded,
                "attempt_count": 2 if repair_attempted else 1,
            },
        }
        logger.info(
            "social_attention_plan_done sid=%s decision=%s behaviors=%s confidence=%.2f "
            "architecture_attribution=not_evaluated ms=%.1f",
            session_id,
            plan.decision,
            len(plan.behaviors),
            plan.confidence,
            planner_ms,
        )
        return plan

    @staticmethod
    def _response_schema(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Constrain body identity to the exact reviewed live candidate set."""

        schema = copy.deepcopy(SocialAttentionPlan.model_json_schema())
        candidate_ids = list(
            dict.fromkeys(
                str(item.get("capability_id") or "").strip()
                for item in candidates
                if isinstance(item, dict)
                and str(item.get("capability_id") or "").strip()
            )
        )
        behavior_schema = schema.get("$defs", {}).get("SocialAttentionBehavior")
        if isinstance(behavior_schema, dict):
            properties = behavior_schema.get("properties")
            if isinstance(properties, dict):
                capability_id = properties.get("capability_id")
                if isinstance(capability_id, dict):
                    capability_id["type"] = "string"
                    capability_id["enum"] = candidate_ids
            required = behavior_schema.setdefault("required", [])
            if "capability_id" not in required:
                required.append("capability_id")
        required = schema.setdefault("required", [])
        for field_name in (
            "decision",
            "target",
            "behaviors",
            "confidence",
            "reason",
        ):
            if field_name not in required:
                required.append(field_name)
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"decision": {"const": "none"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {"behaviors": {"maxItems": 0}},
                    },
                },
                {
                    "if": {
                        "properties": {"decision": {"const": "express"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {"behaviors": {"minItems": 1}},
                    },
                },
            ]
        )
        return schema

    @staticmethod
    def _validation_error_json(exc: Exception) -> str:
        payload: Any = (
            exc.errors(include_url=False)
            if isinstance(exc, ValidationError)
            else [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
        )
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:5000]

    @classmethod
    def _repair_prompt(
        cls,
        *,
        prompt: str,
        raw: dict[str, Any],
        validation_error: Exception,
    ) -> str:
        return (
            prompt
            + "\n\nThe previous Social Attention JSON contradicted its own "
            "decision/behavior contract. Reconsider the scene and return one complete "
            "fresh plan. Keep a genuinely intended supported behavior with "
            "decision=express, or return decision=none with behaviors=[]. Do not merely "
            "flip a redundant field without rechecking social fit.\n\n"
            "Previous invalid JSON:\n"
            + json.dumps(raw, ensure_ascii=False, sort_keys=True)[:5000]
            + "\n\nMechanical validation feedback JSON:\n"
            + cls._validation_error_json(validation_error)
        )


    def _prompt(
        self,
        request: AgentRunRequest | SocialAttentionRequest,
        candidates: list[dict[str, Any]],
    ) -> str:
        if isinstance(request, SocialAttentionRequest):
            language = request.language
            event = request.event
            intent = request.intent
            route = ""
            priority = "normal"
            actions: list[str] = []
        else:
            language = request.language or request.route_decision.language
            event = str(request.context.get("social_attention_event") or "speaking")
            intent = request.route_decision.intent
            route = request.route_decision.route
            priority = request.route_decision.priority
            actions = list(request.route_decision.actions or [])
        payload = {
            "event": event,
            "user_utterance": request.text,
            "language": language,
            "route": route,
            "intent": intent,
            "priority": priority,
            "goal_interpretation_actions": actions,
            "interaction_state": request.context.get("social_attention_interaction_state") or {},
            "social_interaction_style": request.context.get("social_interaction_style") or {},
            "recent_auxiliary_behavior_evidence": request.context.get(
                "recent_auxiliary_behavior_evidence"
            )
            or [],
            "recent_history": list(request.history[-4:]),
            "attention_target_evidence": request.context.get("social_attention_target_evidence")
            or {"available": False},
            "eligible_social_capabilities": candidates,
            "max_behaviors": int(self.services.social_attention_max_behaviors),
        }
        return (
            "Plan optional Social Attention for the supplied interaction event.\n"
            "The event is a state transition such as understanding becoming ready, work starting, waiting, evidence arriving, or speaking; it is not a user Goal.\n"
            "Social Attention is subordinate decoration, never the user Goal. Blinking, gaze, nodding, and other supplied Capabilities are only possible expressions.\n"
            "Every explicit user action remains mandatory, exact, and completion-owning primary Activity when represented in interaction_state. "
            "Never replace it, duplicate its capability, change its count or args, or treat decoration as its completion. "
            "Ordinary cooperative engagement is itself a meaningful social anchor; playful or explicitly emotional wording is not required. "
            "At understanding_ready or work_started, a fresh direct request can support one subtle acknowledgement or presence cue when the owner-approved style, event, candidate semantics, and concurrency metadata make that cue useful and non-disruptive. "
            "A clear or direct task is not evidence that the user requires exact-only action or stillness. Treat exact-only action or stillness as a constraint only when it is actually supplied by the utterance or typed interaction state. "
            "An independent-output candidate declared parallel-safe with the primary work does not compete merely because the primary task is explicit. "
            "When the utterance and supplied primary context support playful, warm, courteous, or otherwise social engagement, you may add at most a different compatible cue; this is optional, not an automatic consequence of any body-action request. "
            "Do not default to decision=none merely because speech can acknowledge or complete the interaction. "
            "Choose decision=none when stillness is more natural for this particular scene, when the user actually requires exact-only action or stillness, or when a gesture would be repetitive, distracting, "
            "unsafe, unsupported, or likely to conflict with the primary task. Do not add a gesture merely because "
            "one is available.\n"
            "Use owner-approved Social Interaction Style and recent auxiliary evidence to keep variation contextual and restrained. "
            "A pleasant surprise is bounded contextual variation, never an unrelated random gesture.\n"
            "Use only supplied semantic target evidence. Never invent a perceived person, target location, "
            "body calibration, joint target, or controller parameter.\n"
            "Do not create or change the user's primary task or response text. Do not add speech, tool calls, memory writes, or raw "
            "joint/motor controls. Select only exact capability_id values from eligible_social_capabilities and provide "
            "schema-valid semantic args. Every auxiliary behavior must use timing=parallel and remain optional.\n"
            "Return one JSON object with keys decision, target, behaviors, confidence, reason, and optional metadata. "
            "decision is none or express. target contains target_ref, source, relative_direction, confidence, metadata. "
            "Each behavior contains capability_id, args, timing, and reason.\n\n"
            f"Interaction context:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )

    def validate_and_materialize(
        self,
        request: AgentRunRequest,
        result: Any,
        plan: SocialAttentionPlan,
    ) -> tuple[list[SkillRequest], list[str]]:
        """Validate an advisory plan and return safe auxiliary SkillRequests."""

        reasons: list[str] = []
        if plan.decision != "express":
            return [], reasons
        if result.status not in {"ok", "clarify"}:
            return [], [f"interaction_status:{result.status}"]
        if not any(item.text.strip() for item in result.speak_immediate + result.speak_after):
            return [], ["no_spoken_response"]

        candidates = request.context.get("social_attention_candidates")
        if not isinstance(candidates, list):
            return [], ["no_social_attention_candidates"]
        target_evidence = request.context.get("social_attention_target_evidence")
        if not isinstance(target_evidence, dict):
            target_evidence = {"available": False}
        target_reason = self._validate_target_claim(plan, target_evidence)
        if target_reason is not None:
            return [], [target_reason]
        candidate_by_id = {
            str(item.get("capability_id") or ""): item
            for item in candidates
            if isinstance(item, dict) and item.get("capability_id")
        }
        existing_skills = list(getattr(result, "_skills", []))
        existing_candidates = self._all_candidate_map(request)
        materialized: list[SkillRequest] = []
        seen: set[str] = {item.skill_id for item in existing_skills}

        for behavior in plan.behaviors[: int(self.services.social_attention_max_behaviors)]:
            candidate = candidate_by_id.get(behavior.skill_id)
            if candidate is None:
                reasons.append(f"unknown_skill:{behavior.skill_id}")
                continue
            if behavior.skill_id in seen:
                reasons.append(f"duplicate_skill:{behavior.skill_id}")
                continue
            if candidate.get("available") is False or candidate.get("interaction_executable") is not True:
                reasons.append(f"unavailable_skill:{behavior.skill_id}")
                continue
            if behavior.timing != "parallel":
                reasons.append(f"auxiliary_must_be_parallel:{behavior.skill_id}")
                continue
            mode = self.services.effective_social_attention_mode()
            if mode == "on" and bool(candidate.get("requires_confirmation")):
                reasons.append(f"confirmation_required:{behavior.skill_id}")
                continue

            schema = dict(candidate.get("input_schema") or {})
            target_error = self._validate_target_args(
                behavior.args,
                schema,
                target_evidence,
            )
            if target_error is not None:
                reasons.append(f"target_error:{behavior.skill_id}:{target_error}")
                continue
            args, normalized = normalize_args_for_schema(
                behavior.args,
                schema,
            )
            errors = validate_args_for_schema(args, schema)
            if errors:
                reasons.append(f"invalid_args:{behavior.skill_id}:{'; '.join(errors)}")
                continue
            if self._conflicts_with_primary_task(
                request,
                candidate,
                existing_skills,
                existing_candidates,
                behavior.timing,
            ):
                reasons.append(f"resource_conflict:{behavior.skill_id}")
                continue

            metadata = {
                "source": "social_attention_plan",
                "auxiliary_social_attention": True,
                "attention_target": plan.target.model_dump(mode="json", exclude_none=True),
                "behavior_domain": plan.behavior_domain,
                "interaction_role": plan.interaction_role,
                "social_attention_purpose": plan.purpose,
                "plan_confidence": plan.confidence,
                "plan_reason": plan.reason,
                "social_function": behavior.social_function,
                "behavior_reason": behavior.reason,
                "catalog_version": request.context.get("capability_catalog_version"),
                "catalog_score": candidate.get("score"),
            }
            if normalized:
                metadata["schema_normalized_args"] = True
            materialized.append(
                SkillRequest(
                    skill_id=behavior.skill_id,
                    args=args,
                    timing=behavior.timing,
                    requires_confirmation=bool(candidate.get("requires_confirmation")),
                    metadata=metadata,
                )
            )
            seen.add(behavior.skill_id)
        return materialized, reasons

    def _validate_target_claim(
        self,
        plan: SocialAttentionPlan,
        target_evidence: dict[str, Any],
    ) -> str | None:
        source = str(plan.target.source or "none")
        evidence_source = str(target_evidence.get("source") or "none")
        available = bool(target_evidence.get("available"))
        if source == "none":
            return None
        if not available:
            return "attention_target_not_available"
        if source == "live_perception" and evidence_source != "live_perception":
            return "unverified_live_perception_target"
        evidence_target = target_evidence.get("target")
        if not isinstance(evidence_target, dict):
            evidence_target = {}
        expected_ref = str(evidence_target.get("target_ref") or "").strip()
        claimed_ref = str(plan.target.target_ref or "").strip()
        if expected_ref and claimed_ref and claimed_ref != expected_ref:
            return "attention_target_ref_mismatch"
        expected_direction = str(evidence_target.get("relative_direction") or "").strip()
        claimed_direction = str(plan.target.relative_direction or "").strip()
        if expected_direction and claimed_direction and claimed_direction != expected_direction:
            return "attention_target_direction_mismatch"
        return None

    def _validate_target_args(
        self,
        args: dict[str, Any],
        schema: dict[str, Any],
        target_evidence: dict[str, Any],
    ) -> str | None:
        semantic_keys = {"direction", "relative_direction", "target_ref"}
        if not semantic_keys.intersection(args):
            return None
        if not bool(target_evidence.get("available")):
            return "targeted_behavior_without_semantic_target_evidence"
        target = target_evidence.get("target")
        if not isinstance(target, dict):
            return "targeted_behavior_without_semantic_target_evidence"
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

    def _all_candidate_map(self, request: AgentRunRequest) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for source in (
            request.context.get("capability_candidates"),
            request.route_decision.candidate_capabilities,
            request.context.get("social_attention_candidates"),
        ):
            if not isinstance(source, list):
                continue
            for item in source:
                if not isinstance(item, dict):
                    continue
                capability_id = str(item.get("capability_id") or "")
                if capability_id:
                    out[capability_id] = item
        return out

    def _conflicts_with_primary_task(
        self,
        request: AgentRunRequest,
        social_candidate: dict[str, Any],
        existing_skills: list[SkillRequest],
        candidate_by_id: dict[str, dict[str, Any]],
        timing: str,
    ) -> bool:
        if not existing_skills:
            return False
        if timing != "parallel":
            return True

        social_declared = bool(social_candidate.get("parallel_metadata_declared"))
        social_parallel = social_candidate.get("can_run_parallel")
        social_group = str(social_candidate.get("exclusive_group") or "")
        social_claims = {
            str(value)
            for value in (social_candidate.get("resource_claims") or [])
            if str(value).strip()
        }
        if social_parallel is False:
            return True

        for skill in existing_skills:
            if skill.skill_id == "chromie.speak":
                continue
            other = candidate_by_id.get(skill.skill_id)
            if other is None:
                if request.route_decision.route == "robot_action":
                    return True
                continue
            other_group = str(other.get("exclusive_group") or "")
            other_claims = {
                str(value)
                for value in (other.get("resource_claims") or [])
                if str(value).strip()
            }
            if social_group and other_group and social_group == other_group:
                return True
            if social_claims and other_claims and social_claims.intersection(other_claims):
                return True
            if other.get("can_run_parallel") is False:
                return True
            other_declared = bool(other.get("parallel_metadata_declared"))
            if request.route_decision.route == "robot_action" and not (
                social_declared and other_declared
            ):
                return True
        return False
