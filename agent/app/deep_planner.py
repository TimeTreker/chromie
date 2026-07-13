from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .capabilities.catalog import CapabilityCatalog
from .capabilities.validator import validate_args_for_schema
from .clients.ollama_client import OllamaClient
from .schema import AgentRunRequest

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.deep_planner")


class DeepPlannerResolver:
    """Full-catalog semantic planner with one bounded same-tier revision."""

    def __init__(self, ollama: OllamaClient, catalog: CapabilityCatalog, *, min_confidence: float = 0.65,
                 num_ctx: int = 8192, num_predict: int = 1024, max_capabilities: int = 96,
                 max_replans: int = 1, min_goal_satisfaction: float = 0.75) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(256, int(num_predict))
        self.max_capabilities = max(1, min(256, int(max_capabilities)))
        self.max_replans = max(0, min(2, int(max_replans)))
        self.min_goal_satisfaction = max(0.0, min(1.0, float(min_goal_satisfaction)))

    async def resolve(self, request: AgentRunRequest) -> CanonicalPlan:
        plan_id = self._plan_id(request)
        capabilities = await self.catalog.prompt_entries(scope="all", refresh=False)
        payload = [self._capability_payload(item) for item in capabilities[: self.max_capabilities]]
        feedback: list[dict[str, Any]] = []
        for attempt in range(self.max_replans + 1):
            try:
                raw = await self.ollama.generate(
                    self._prompt(request, payload, feedback=feedback),
                    system=self._system_prompt(),
                    options={"temperature": 0, "top_p": 0.9, "num_ctx": self.num_ctx,
                             "num_predict": self.num_predict},
                    response_format="json",
                )
                if not isinstance(raw, dict):
                    raise ValueError("deep planner response is not a JSON object")
                plan = CanonicalPlan.model_validate(self._normalize(raw, request=request, plan_id=plan_id))
            except Exception as exc:
                logger.warning("deep planner degraded sid=%s attempt=%s error_type=%s error=%s",
                               request.sid, attempt + 1, type(exc).__name__, exc)
                if attempt < self.max_replans:
                    feedback = [{"type": "invalid_plan_shape", "message": str(exc)[:400]}]
                    continue
                return self._clarify(plan_id, request, "deep_planner_unavailable", error=exc,
                                     attempts=attempt + 1)
            errors = self._validation_errors(plan, payload)
            if not errors:
                metadata = dict(plan.metadata)
                metadata.update({"resolver": "deep_planner", "status": "complete" if plan.coverage == "complete" else plan.disposition,
                                 "authority": "advisory", "attempt_count": attempt + 1,
                                 "full_capability_count": len(payload), "max_replans": self.max_replans, "min_goal_satisfaction": self.min_goal_satisfaction})
                return plan.model_copy(update={"metadata": metadata})
            if attempt < self.max_replans:
                feedback = errors
                continue
            return self._clarify(plan_id, request, "validation_rejected_after_replan",
                                 unresolved=[item.get("step_id") or item.get("skill_id") or item["type"] for item in errors],
                                 metadata={"validation_feedback": errors}, attempts=attempt + 1)
        raise AssertionError("unreachable")

    @staticmethod
    def _capability_payload(item: Any) -> dict[str, Any]:
        return {
            "capability_id": item.capability_id, "description": item.description,
            "input_schema": item.input_schema, "route": item.route, "available": item.available,
            "interaction_executable": item.interaction_executable,
            "requires_confirmation": item.requires_confirmation, "effects": item.effects,
            "safety_class": item.safety_class, "can_run_parallel": item.can_run_parallel,
            "parallel_metadata_declared": item.parallel_metadata_declared,
            "exclusive_group": item.exclusive_group, "resource_claims": item.resource_claims,
            "execution_constraints": item.execution_constraints,
        }

    @staticmethod
    def _plan_id(request: AgentRunRequest) -> str:
        digest = hashlib.sha256(f"{request.sid or 'turn'}|deep|{request.text}".encode()).hexdigest()[:20]
        return f"plan_{digest}"

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(self, request: AgentRunRequest, capabilities: list[dict[str, Any]], *, feedback: list[dict[str, Any]]) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution") or {}
        goals = context.get("active_goal_snapshots") or []
        association = context.get("goal_association_resolution") or {}
        runtime_feedback = context.get("runtime_validator_feedback") or []
        combined_feedback = [*feedback, *(runtime_feedback if isinstance(runtime_feedback, list) else [])]
        feedback_section = self._bounded(combined_feedback, 5000) if combined_feedback else "[]"
        return (
            f"User turn:\n{request.text}\n\n"
            f"Fast-plan advisory JSON:\n{self._bounded(fast_plan, 2500)}\n\n"
            f"Goal association advisory JSON:\n{self._bounded(association, 2500)}\n\n"
            f"Active goals JSON:\n{self._bounded(goals, 4500)}\n\n"
            f"Full capability catalog JSON:\n{self._bounded(capabilities, 24000)}\n\n"
            f"Deterministic validation feedback from the previous deep-plan or trusted host-runtime attempt:\n{feedback_section}\n\n"
            "Produce the final planner-tier=deep CanonicalPlan for the complete user goal. Deep planning is terminal: never return to the Fast Planner. "
            "Use the full catalog, preserve all independent responsibilities, constraints, conditions, ordering, and concurrency. Resolve low-consequence "
            "parameters semantically when justified; otherwise return a specific natural clarification. Exact, safe-adjusted, or alternative executable plans "
            "must use coverage=complete and disposition=execute. A material alternative must be described in response_text and metadata and must require "
            "confirmation downstream. For every missing parameter, return parameter_resolutions with a semantic strategy, concrete value when resolved, confidence, and rationale. Use safe_default only for low-consequence reversible values inside schema bounds. Use ask_user for material or risky values. Also return goal_satisfaction with score, status, satisfied goals, and unmet requirements. If essential information remains missing, use coverage=partial or uncertain with disposition=clarify and zero steps. "
            "If unavailable or refused, use zero steps. Use exact supplied capability IDs and schema-valid args. Return JSON only."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Deep Planner. Plan the complete goal with the full capability surface. "
            "You may revise once from structured validator feedback, but you never call or return to the Fast Planner. "
            "Skills are plan leaves, not planner ownership boundaries. Do not execute, authorize, or claim completion. Return JSON only."
        )

    def _normalize(self, raw: dict[str, Any], *, request: AgentRunRequest, plan_id: str) -> dict[str, Any]:
        out = dict(raw)
        out["plan_id"] = plan_id
        out["planner_tier"] = "deep"
        steps = out.get("steps")
        if isinstance(steps, dict):
            steps = [steps]
        if not isinstance(steps, list):
            steps = []
        normalized = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            step = dict(item)
            step.setdefault("step_id", f"{plan_id}:step:{index}")
            step.setdefault("args", {})
            step.setdefault("timing", "sequential")
            step.setdefault("source_goal_ids", out.get("goal_ids") or [])
            normalized.append(step)
        out["steps"] = normalized
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "clarify")
        out.setdefault("confidence", 0.0)
        out.setdefault("goal_ids", [])
        out.setdefault("goal_summary", request.text)
        out.setdefault("response_text", "")
        out.setdefault("escalation_reason", "")
        out.setdefault("unresolved", [])
        out.setdefault("parameter_resolutions", [])
        out.setdefault("goal_satisfaction", None)
        out.setdefault("metadata", {})
        return out

    def _validation_errors(self, plan: CanonicalPlan, capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {item["capability_id"]: item for item in capabilities}
        errors: list[dict[str, Any]] = []
        if plan.coverage == "complete" and plan.confidence < self.min_confidence:
            errors.append({"type": "confidence_below_threshold", "confidence": plan.confidence,
                           "required": self.min_confidence})
        if plan.coverage == "complete":
            if plan.goal_satisfaction is None:
                errors.append({"type": "missing_goal_satisfaction"})
            elif plan.goal_satisfaction.score < self.min_goal_satisfaction:
                errors.append({"type": "goal_satisfaction_below_threshold", "score": plan.goal_satisfaction.score, "required": self.min_goal_satisfaction})
        step_ids = {step.step_id for step in plan.steps}
        for resolution in plan.parameter_resolutions:
            if resolution.step_id not in step_ids and not resolution.blocking:
                errors.append({"type": "parameter_resolution_unknown_step", "step_id": resolution.step_id, "parameter": resolution.parameter})
            if resolution.blocking and plan.disposition == "execute":
                errors.append({"type": "blocking_parameter_resolution", "step_id": resolution.step_id, "parameter": resolution.parameter})
        for step in plan.steps:
            capability = allowed.get(step.skill_id)
            if capability is None:
                errors.append({"type": "unknown_capability", "step_id": step.step_id, "skill_id": step.skill_id})
                continue
            if not capability.get("available") or not capability.get("interaction_executable"):
                errors.append({"type": "capability_not_executable", "step_id": step.step_id,
                               "skill_id": step.skill_id})
                continue
            schema_errors = validate_args_for_schema(step.args, capability.get("input_schema") or {})
            if schema_errors:
                errors.append({"type": "invalid_args", "step_id": step.step_id, "skill_id": step.skill_id,
                               "errors": schema_errors[:8]})
        return errors

    def _clarify(self, plan_id: str, request: AgentRunRequest, reason: str, *, unresolved: list[str] | None = None,
                 metadata: dict[str, Any] | None = None, error: Exception | None = None,
                 attempts: int = 1) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update({"resolver": "deep_planner", "status": "clarify", "authority": "advisory",
                       "attempt_count": attempts, "max_replans": self.max_replans, "reason": reason})
        if error is not None:
            detail.update({"error_type": type(error).__name__, "error": str(error)[:300]})
        return CanonicalPlan(plan_id=plan_id, planner_tier="deep", disposition="clarify",
                             coverage="uncertain", confidence=0.0, goal_summary=request.text,
                             response_text="", steps=[], unresolved=list(unresolved or []), metadata=detail)
