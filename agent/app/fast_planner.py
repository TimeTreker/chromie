from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .schema import AgentRunRequest

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.fast_planner")


class FastPlannerResolver:
    """Low-latency semantic planner over the common catalog only."""

    def __init__(self, ollama: OllamaClient, catalog: CapabilityCatalog, *, min_confidence: float = 0.8,
                 num_ctx: int = 4096, num_predict: int = 512, max_capabilities: int = 24) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.max_capabilities = max(1, min(64, int(max_capabilities)))

    async def resolve(self, request: AgentRunRequest) -> CanonicalPlan:
        plan_id = self._plan_id(request)
        capabilities = await self.catalog.prompt_entries(scope="common", refresh=False)
        capability_payload = [
            {
                "capability_id": item.capability_id,
                "description": item.description,
                "input_schema": item.input_schema,
                "route": item.route,
                "available": item.available,
                "interaction_executable": item.interaction_executable,
                "requires_confirmation": item.requires_confirmation,
                "effects": item.effects,
                "safety_class": item.safety_class,
            }
            for item in capabilities[: self.max_capabilities]
        ]
        try:
            raw = await self.ollama.generate(
                self._prompt(request, capability_payload),
                system=self._system_prompt(),
                options={"temperature": 0, "top_p": 0.9, "num_ctx": self.num_ctx, "num_predict": self.num_predict},
                response_format="json",
            )
            if not isinstance(raw, dict):
                raise ValueError("fast planner response is not a JSON object")
            normalized = self._normalize(raw, request=request, plan_id=plan_id)
            plan = CanonicalPlan.model_validate(normalized)
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.warning(
                "fast_planner_inference_failed sid=%s error_type=%s error=%s "
                "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
            )
            return self._escalation(plan_id, request, "fast_planner_unavailable", error=exc)
        return self._validate(plan, capability_payload=capability_payload, request=request)

    @staticmethod
    def _plan_id(request: AgentRunRequest) -> str:
        digest = hashlib.sha256(f"{request.sid or 'turn'}|fast|{request.text}".encode()).hexdigest()[:20]
        return f"plan_{digest}"

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(self, request: AgentRunRequest, capabilities: list[dict[str, Any]]) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        goals = context.get("active_goal_snapshots") or []
        association = context.get("goal_association_resolution") or {}
        route = request.route_decision
        advisory = {"route": route.route, "intent": route.intent, "confidence": route.confidence}
        return (
            f"User turn:\n{request.text}\n\n"
            f"Goal association advisory JSON:\n{self._bounded(association, 2200)}\n\n"
            f"Active goals JSON:\n{self._bounded(goals, 3500)}\n\n"
            f"Router advisory JSON:\n{self._bounded(advisory, 900)}\n\n"
            f"Common capability catalog JSON:\n{self._bounded(capabilities, 8500)}\n\n"
            "Decide whether the common catalog and bounded context completely cover every semantic responsibility in the user turn. "
            "Coverage means the whole goal, including all requested actions, constraints, relationships, and required parameters. "
            "Finding one matching skill is not complete coverage. If any responsibility, parameter source, condition, sequence, concurrency relation, "
            "or required capability remains unresolved, return coverage partial or uncertain and disposition escalate with zero steps. If independent goals need different dispositions, such as executing one while clarifying another, escalate with zero steps so the Deep Planner can produce a mixed per-goal outcome. "
            "For simple chat, complete coverage may use disposition respond and response_text. For a complete direct common-skill goal, use disposition execute. "
            "Use only exact supplied capability IDs. Return compact JSON matching CanonicalPlan: planner_tier=fast, disposition, coverage, confidence, "
            "goal_ids, goal_summary, response_text, steps, escalation_reason, unresolved, parameter_resolutions, goal_satisfaction, metadata. Every executable plan must include goal_ids, and every executable step must include source_goal_ids identifying exactly the goals it serves. Do not execute, authorize, or claim completion."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Fast Planner. Plan semantically, not with phrase rules. Your responsibility is fast complete coverage, not skill matching. "
            "You may produce a complete simple response or complete direct common-skill plan. Otherwise escalate once to the Deep Planner. "
            "Never emit partial executable steps. For complete plans, assess goal satisfaction and explain how every requested responsibility is covered. Resolve only low-consequence parameters with explicit schema or safe semantic defaults; otherwise escalate. Return JSON only."
        )

    def _normalize(self, raw: dict[str, Any], *, request: AgentRunRequest, plan_id: str) -> dict[str, Any]:
        out = dict(raw)
        out["plan_id"] = plan_id
        out["planner_tier"] = "fast"
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
            step.setdefault("step_id", f"{plan_id}:step:{index}")
            step.setdefault("args", {})
            step.setdefault("timing", "sequential")
            step.setdefault("source_goal_ids", out.get("goal_ids") or [])
            normalized_steps.append(step)
        out["steps"] = normalized_steps
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "escalate")
        out.setdefault("confidence", 0.0)
        out.setdefault("goal_ids", [])
        out.setdefault("goal_summary", request.text)
        out.setdefault("response_text", "")
        out.setdefault("escalation_reason", "")
        out.setdefault("unresolved", [])
        out.setdefault("parameter_resolutions", [])
        out.setdefault("goal_outcomes", [])
        out.setdefault("goal_satisfaction", None)
        out.setdefault("metadata", {})
        return out

    def _validate(self, plan: CanonicalPlan, *, capability_payload: list[dict[str, Any]], request: AgentRunRequest) -> CanonicalPlan:
        allowed = {item["capability_id"]: item for item in capability_payload}
        if plan.coverage != "complete" or plan.confidence < self.min_confidence:
            return self._escalation(plan.plan_id, request, "coverage_not_complete", unresolved=plan.unresolved,
                                    metadata={"proposed_coverage": plan.coverage, "proposed_confidence": plan.confidence})
        if plan.goal_satisfaction is None or plan.goal_satisfaction.score < 0.95:
            return self._escalation(plan.plan_id, request, "goal_satisfaction_not_exact", unresolved=plan.unresolved, metadata={"proposed_goal_satisfaction": (plan.goal_satisfaction.model_dump(mode="json") if plan.goal_satisfaction else None)})
        for step in plan.steps:
            capability = allowed.get(step.skill_id)
            if capability is None or not capability.get("available") or not capability.get("interaction_executable"):
                return self._escalation(plan.plan_id, request, "step_not_in_executable_common_catalog",
                                        unresolved=[step.skill_id])
        metadata = dict(plan.metadata)
        metadata.update({"resolver": "fast_planner", "status": "complete", "authority": "advisory",
                         "common_capability_count": len(capability_payload), "min_confidence": self.min_confidence})
        return plan.model_copy(update={"metadata": metadata})

    def _escalation(self, plan_id: str, request: AgentRunRequest, reason: str, *, unresolved: list[str] | None = None,
                    metadata: dict[str, Any] | None = None, error: Exception | None = None) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update({"resolver": "fast_planner", "status": "escalate", "authority": "advisory"})
        if error is not None:
            detail.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                    **llm_failure_metadata(error),
                }
            )
        return CanonicalPlan(plan_id=plan_id, planner_tier="fast", disposition="escalate", coverage="uncertain",
                             confidence=0.0, goal_summary=request.text, steps=[], escalation_reason=reason,
                             unresolved=list(unresolved or []), metadata=detail)
