from __future__ import annotations

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
    from chromie_contracts.social_attention import SocialAttentionPlan
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import SkillRequest
    from shared.chromie_contracts.social_attention import SocialAttentionPlan

logger = logging.getLogger("chromie.agent.social_attention")


class SocialAttentionPlanner:
    """Model-driven auxiliary body-expression planning.

    Social attention is a high-level behavior domain. The model decides whether
    a body expression would improve the current interaction and selects exact
    catalog skills for the scene. In the goal-driven path, Response Composer
    coordinates language expression and body expression together. This native
    compatibility path plans body expression only; deterministic code validates
    schemas, evidence, safety, and resource conflicts without choosing actions.
    """

    def __init__(self, services: Any) -> None:
        self.services = services

    async def plan(self, request: AgentRunRequest) -> SocialAttentionPlan | None:
        client = self.services.social_attention_ollama
        candidates = request.context.get("social_attention_candidates")
        if client is None or not isinstance(candidates, list) or not candidates:
            return None

        prompt = self._prompt(request, candidates)
        started = time.perf_counter()
        logger.info(
            "social_attention_plan_start sid=%s mode=%s timeout_ms=%s num_ctx=%s "
            "num_predict=%s prompt_chars=%s candidates=%s",
            request.sid,
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
                system=(
                    "You are Chromie's auxiliary social-attention body planner. Treat social "
                    "attention as a high-level interaction purpose, then choose scene-appropriate "
                    "body expressions from the supplied catalog. Do not use phrase-to-skill rules, "
                    "do not author speech in this compatibility path, and return JSON only."
                ),
                options={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_ctx": int(self.services.social_attention_num_ctx),
                    "num_predict": int(self.services.social_attention_num_predict),
                },
                response_format="json",
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
                request.sid,
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
                request.sid,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                planner_ms,
                failure["error"],
            )
            return None
        try:
            plan = SocialAttentionPlan.model_validate(raw)
        except ValidationError as exc:
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
                "social_attention_plan_invalid sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=%s elapsed_ms=%.1f error=%s",
                request.sid,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                failure.get("architecture_attribution"),
                str(bool(failure.get("retryable"))).lower(),
                planner_ms,
                exc,
            )
            return None
        planner_ms = (time.perf_counter() - started) * 1000.0
        request.context.pop("social_attention_failure", None)
        plan.metadata = {
            **plan.metadata,
            "planner_ms": round(planner_ms, 1),
            "architecture_attribution": "not_evaluated",
        }
        logger.info(
            "social_attention_plan_done sid=%s decision=%s behaviors=%s confidence=%.2f "
            "architecture_attribution=not_evaluated ms=%.1f",
            request.sid,
            plan.decision,
            len(plan.behaviors),
            plan.confidence,
            planner_ms,
        )
        return plan

    def _prompt(self, request: AgentRunRequest, candidates: list[dict[str, Any]]) -> str:
        payload = {
            "user_utterance": request.text,
            "language": request.language or request.route_decision.language,
            "route": request.route_decision.route,
            "intent": request.route_decision.intent,
            "priority": request.route_decision.priority,
            "router_actions": list(request.route_decision.actions or []),
            "recent_history": list(request.history[-4:]),
            "attention_target_evidence": request.context.get("social_attention_target_evidence")
            or {"available": False},
            "eligible_social_capabilities": candidates,
            "max_behaviors": int(self.services.social_attention_max_behaviors),
        }
        return (
            "Plan optional social attention for the current spoken interaction.\n"
            "Attention is the goal; blinking, gaze, nodding, and other supplied skills are only possible expressions.\n"
            "Choose decision=none when speech alone is natural, when a gesture would be repetitive, distracting, "
            "unsafe, unsupported, or likely to conflict with the primary task. Do not add a gesture merely because "
            "one is available.\n"
            "If live target evidence exists, prefer it. Installation calibration is only a fallback when live "
            "perception is absent. Never invent a perceived person or target location.\n"
            "Do not create or change the user's primary task. Do not add speech, tool calls, memory writes, or raw "
            "joint/motor controls. Select only exact skill_id values from eligible_social_capabilities and provide "
            "schema-valid args. Prefer timing=parallel for behavior intended to accompany speech.\n"
            "Return one JSON object with keys decision, target, behaviors, confidence, reason, and optional metadata. "
            "decision is none or express. target contains target_ref, source, relative_direction, confidence, metadata. "
            "Each behavior contains skill_id, args, timing, and reason.\n\n"
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
            mode = self.services.effective_social_attention_mode()
            capability_mode = str((candidate.get("metadata") or {}).get("mode") or "")
            if mode == "sim_only" and capability_mode != "sim":
                reasons.append(f"not_sim_skill:{behavior.skill_id}")
                continue
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
        if source == "installation_calibration" and evidence_source != "installation_calibration":
            return "unverified_calibrated_target"
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
        if not bool(target_evidence.get("available")):
            return "targeted_behavior_without_target_evidence"
        target = target_evidence.get("target")
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
                    return f"{key} does not match calibrated target evidence"
            elif actual != expected:
                return f"{key} does not match target evidence"
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
