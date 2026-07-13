from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .clients.ollama_client import OllamaClient
from .schema import AgentRunRequest

try:
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.semantic_task import SemanticGoal
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociation,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.semantic_task import SemanticGoal

logger = logging.getLogger("chromie.agent.goal_association")


class GoalAssociationResolver:
    """Resolve continuity before creation without mutating runtime state."""

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        min_confidence: float = 0.65,
        max_active_goals: int = 8,
        num_ctx: int = 4096,
        num_predict: int = 512,
    ) -> None:
        self.ollama = ollama
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.max_active_goals = max(1, min(32, int(max_active_goals)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: AgentRunRequest) -> GoalAssociationResolution:
        active_goals = self._active_goals(request)
        turn_id = self._turn_id(request)
        try:
            raw = await self.ollama.generate(
                self._build_prompt(request, active_goals),
                system=self._system_prompt(),
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
                response_format="json",
            )
            if not isinstance(raw, dict):
                raise ValueError("goal-association response is not a JSON object")
            resolution = GoalAssociationResolution.model_validate(
                self._normalize(raw, request=request, turn_id=turn_id)
            )
        except Exception as exc:
            logger.exception(
                "goal association model degraded sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return GoalAssociationResolution(
                turn_id=turn_id,
                clarification=self._safe_clarification(request),
                confidence=0.0,
                reason_summary="Goal association model was unavailable; no goal operation was accepted.",
                metadata={
                    "resolver": "goal_association_agent",
                    "status": "model_unavailable",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    "active_goal_count": len(active_goals),
                    "sid": request.sid,
                },
            )
        return self._validate(resolution, active_goals=active_goals, request=request)

    def _active_goals(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("active_goal_snapshots")
        if not isinstance(raw, list):
            raw = []
        out: list[dict[str, Any]] = []
        for item in raw[: self.max_active_goals]:
            if not isinstance(item, dict):
                continue
            try:
                out.append(ActiveGoalSnapshot.model_validate(item).model_dump(mode="json", exclude_none=True))
            except Exception:
                continue
        return out

    @staticmethod
    def _turn_id(request: AgentRunRequest) -> str:
        seed = f"{request.sid or 'turn'}|{request.text}"
        return f"turn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _bounded_json(value: Any, max_chars: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."

    def _build_prompt(self, request: AgentRunRequest, active_goals: list[dict[str, Any]]) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        route = request.route_decision
        route_advisory = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
            "routes": [
                {"route": item.route, "intent": item.intent, "confidence": item.confidence}
                for item in route.routes[:8]
            ],
        }
        return (
            "Latest user turn:\n"
            f"{request.text}\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(active_goals, 7000)}\n\n"
            "Recent conversation JSON:\n"
            f"{self._bounded_json((context.get('history') or request.history or [])[-6:], 2600)}\n\n"
            "Router output is advisory JSON:\n"
            f"{self._bounded_json(route_advisory, 1800)}\n\n"
            "Resolve continuity before creation. First decide whether each semantic responsibility in the turn "
            "continues, modifies, clarifies, confirms, rejects, cancels, pauses, resumes, replaces, merges, splits, "
            "or references supplied active goals. Only responsibilities not belonging to existing goals become new goals. "
            "One turn may update existing goals and create multiple independent new goals. Do not split implementation steps "
            "into goals. If the reference is materially ambiguous, propose no change and ask one concise natural clarification "
            "that names the human topics, never internal IDs.\n\n"
            "Return compact JSON with turn_id, associations, new_goals, clarification, confidence, reason_summary, metadata. "
            "Each association uses relationship, target_goal_ids copied exactly from active goals, confidence, and reason_summary. "
            "Each new goal uses open semantic description, source_text, beneficiary, constraints, and success_criteria when known. "
            "Do not output skills, plans, task IDs not supplied, authorization, execution claims, markdown, or hidden reasoning."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Goal Association and Segmentation model. "
            "Apply continuity before creation. Understand references from meaning, bounded active goals, unresolved gaps, and dialogue context. "
            "Do not decide association through regexes, phrase tables, lexical overlap, or recency alone. "
            "Preserve independent user responsibilities as separate goals, but never turn plan steps into goals. "
            "You are advisory only and never execute or commit. Return JSON only."
        )

    def _normalize(self, raw: dict[str, Any], *, request: AgentRunRequest, turn_id: str) -> dict[str, Any]:
        associations = raw.get("associations")
        if isinstance(associations, dict):
            associations = [associations]
        if not isinstance(associations, list):
            associations = []
        normalized_associations = []
        for index, item in enumerate(associations):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["association_id"] = stable_goal_operation_id(
                turn_id=turn_id,
                ordinal=index,
                relationship=str(normalized.get("relationship") or "reference"),
                target_goal_ids=normalized.get("target_goal_ids") or [],
            )
            normalized_associations.append(normalized)

        goals = raw.get("new_goals")
        if goals is None:
            goals = raw.get("goals")
        if isinstance(goals, dict):
            goals = [goals]
        if not isinstance(goals, list):
            goals = []
        normalized_goals = []
        for index, item in enumerate(goals):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if not normalized.get("goal_id"):
                digest = hashlib.sha256(f"{turn_id}|goal|{index}|{normalized.get('description','')}".encode()).hexdigest()[:20]
                normalized["goal_id"] = f"goal_{digest}"
            normalized.setdefault("source_text", request.text)
            normalized_goals.append(normalized)

        return {
            "schema_version": raw.get("schema_version", 1),
            "turn_id": turn_id,
            "associations": normalized_associations,
            "new_goals": normalized_goals,
            "clarification": raw.get("clarification") or "",
            "confidence": raw.get("confidence", 0.0),
            "reason_summary": raw.get("reason_summary") or "",
            "metadata": raw.get("metadata") or {},
        }

    def _validate(
        self,
        resolution: GoalAssociationResolution,
        *,
        active_goals: list[dict[str, Any]],
        request: AgentRunRequest,
    ) -> GoalAssociationResolution:
        active_ids = {str(item.get("goal_id") or "") for item in active_goals}
        accepted: list[GoalAssociation] = []
        rejected: list[dict[str, Any]] = []
        for association in resolution.associations:
            reason = None
            if association.confidence < self.min_confidence:
                reason = "below_confidence_threshold"
            elif any(goal_id not in active_ids for goal_id in association.target_goal_ids):
                reason = "unknown_target_goal"
            if reason:
                rejected.append({"association_id": association.association_id, "reason": reason})
            else:
                accepted.append(association)

        if resolution.clarification:
            accepted = []
            new_goals: list[SemanticGoal] = []
        else:
            new_goals = resolution.new_goals

        metadata = dict(resolution.metadata)
        metadata.update(
            {
                "resolver": "goal_association_agent",
                "status": "resolved",
                "active_goal_count": len(active_goals),
                "accepted_association_count": len(accepted),
                "new_goal_count": len(new_goals),
                "rejected_associations": rejected,
                "min_confidence": self.min_confidence,
                "sid": request.sid,
                "authority": "advisory",
            }
        )
        if not accepted and not new_goals and not resolution.clarification:
            return GoalAssociationResolution(
                turn_id=resolution.turn_id,
                clarification=self._safe_clarification(request),
                confidence=0.0,
                reason_summary="No sufficiently grounded goal association or new goal was accepted.",
                metadata={**metadata, "status": "needs_clarification"},
            )
        return resolution.model_copy(update={"associations": accepted, "new_goals": new_goals, "metadata": metadata})

    @staticmethod
    def _safe_clarification(request: AgentRunRequest) -> str:
        return "你是在继续刚才的事情，还是想开始一件新的事情？" if (request.language or "").startswith("zh") else "Is this about what we were already doing, or is it a new request?"
