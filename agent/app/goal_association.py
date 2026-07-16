from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .clients.ollama_client import OllamaClient, llm_failure_metadata
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
        response_schema = self._response_schema(active_goals)
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        initial_raw: dict[str, Any] | None = None
        repair_raw: dict[str, Any] | None = None
        initial_validation_error = ""
        repair_attempted = False

        try:
            raw = await self.ollama.generate(
                self._build_prompt(request, active_goals, response_schema=response_schema),
                system=self._system_prompt(),
                options=generation_options,
                response_format=response_schema,
            )
            if not isinstance(raw, dict):
                raise ValueError("goal-association response is not a JSON object")
            initial_raw = raw
            try:
                resolution = self._validate_contract_output(
                    raw, request=request, turn_id=turn_id
                )
            except ValidationError as exc:
                repair_attempted = True
                initial_validation_error = self._validation_error_json(exc)
                logger.warning(
                    "goal_association_contract_repair_start sid=%s validation_errors=%s "
                    "raw_output=%s",
                    request.sid,
                    initial_validation_error,
                    self._bounded_json(raw, 4000),
                )
                repaired = await self.ollama.generate(
                    self._build_repair_prompt(
                        request=request,
                        active_goals=active_goals,
                        turn_id=turn_id,
                        response_schema=response_schema,
                        raw=raw,
                        validation_error=initial_validation_error,
                    ),
                    system=self._repair_system_prompt(),
                    options=generation_options,
                    response_format=response_schema,
                )
                if not isinstance(repaired, dict):
                    raise ValueError("goal-association repair response is not a JSON object")
                repair_raw = repaired
                resolution = self._validate_contract_output(
                    repaired, request=request, turn_id=turn_id
                )
                repair_metadata = dict(resolution.metadata)
                repair_metadata["contract_repair"] = {
                    "attempted": True,
                    "succeeded": True,
                    "strategy": "schema_constrained_model_revision",
                    "attempt_count": 1,
                }
                resolution = resolution.model_copy(update={"metadata": repair_metadata})
                logger.info(
                    "goal_association_contract_repair_done sid=%s status=success",
                    request.sid,
                )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            status = (
                "model_contract_failed"
                if failure["failure_domain"] == "model_contract" or repair_attempted
                else "model_unavailable"
            )
            logger.exception(
                "goal_association_inference_failed sid=%s error_type=%s error=%s "
                "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s "
                "repair_attempted=%s initial_validation_errors=%s initial_raw=%s repair_raw=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                failure["retryable"],
                repair_attempted,
                initial_validation_error,
                self._bounded_json(initial_raw, 4000) if initial_raw is not None else "",
                self._bounded_json(repair_raw, 4000) if repair_raw is not None else "",
            )
            metadata: dict[str, Any] = {
                "resolver": "goal_association_agent",
                "status": status,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                **failure,
                "active_goal_count": len(active_goals),
                "sid": request.sid,
                "contract_schema": "GoalAssociationResolution",
                "contract_repair_attempted": repair_attempted,
                "contract_repair_succeeded": False,
            }
            if initial_validation_error:
                metadata["initial_validation_errors"] = initial_validation_error
            if initial_raw is not None:
                metadata["initial_raw_output"] = self._bounded_json(initial_raw, 4000)
            if repair_raw is not None:
                metadata["repair_raw_output"] = self._bounded_json(repair_raw, 4000)
            return GoalAssociationResolution(
                turn_id=turn_id,
                clarification=self._safe_clarification(request),
                confidence=0.0,
                reason_summary=(
                    "Goal association output did not satisfy the schema after one model repair attempt; no goal operation was accepted."
                    if repair_attempted
                    else "Goal association model was unavailable; no goal operation was accepted."
                ),
                metadata=metadata,
            )
        return self._validate(resolution, active_goals=active_goals, request=request)

    def _validate_contract_output(
        self,
        raw: dict[str, Any],
        *,
        request: AgentRunRequest,
        turn_id: str,
    ) -> GoalAssociationResolution:
        return GoalAssociationResolution.model_validate(
            self._normalize(raw, request=request, turn_id=turn_id)
        )

    @staticmethod
    def _validation_error_json(exc: ValidationError) -> str:
        return json.dumps(
            exc.errors(include_url=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:6000]


    @staticmethod
    def _response_schema(active_goals: list[dict[str, Any]]) -> dict[str, Any]:
        schema = copy.deepcopy(GoalAssociationResolution.model_json_schema())
        active_ids = [
            " ".join(str(item.get("goal_id") or "").strip().split())
            for item in active_goals
            if " ".join(str(item.get("goal_id") or "").strip().split())
        ]
        properties = schema.get("properties", {})
        associations = properties.get("associations")
        if isinstance(associations, dict) and not active_ids:
            associations["maxItems"] = 0

        def constrain(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
                    target_ids = node_properties.get("target_goal_ids")
                    if isinstance(target_ids, dict) and active_ids:
                        target_ids["items"] = {"type": "string", "enum": active_ids}
                        target_ids["uniqueItems"] = True
                for value in node.values():
                    constrain(value)
            elif isinstance(node, list):
                for value in node:
                    constrain(value)

        constrain(schema)
        schema["oneOf"] = [
            {
                "properties": {
                    "clarification": {"type": "string", "minLength": 1},
                    "associations": {"type": "array", "maxItems": 0},
                    "new_goals": {"type": "array", "maxItems": 0},
                },
                "required": ["clarification", "associations", "new_goals"],
            },
            {
                "properties": {"clarification": {"type": "string", "maxLength": 0}},
                "anyOf": [
                    {"properties": {"associations": {"type": "array", "minItems": 1}}},
                    {"properties": {"new_goals": {"type": "array", "minItems": 1}}},
                ],
                "required": ["clarification", "associations", "new_goals"],
            },
        ]
        return schema

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

    def _build_prompt(
        self,
        request: AgentRunRequest,
        active_goals: list[dict[str, Any]],
        *,
        response_schema: dict[str, Any],
    ) -> str:
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
            "Resolve continuity before creation. For every association, relationship must be copied exactly from this "
            "canonical enum: [\"continue\",\"modify\",\"clarify\",\"confirm\",\"reject\",\"cancel\",\"pause\",\"resume\",\"replace\",\"merge\",\"split\",\"reference\",\"new\"]. "
            "Never conjugate, pluralize, translate, or invent an enum value. Associations may target only IDs present in Bounded active goals JSON. "
            "When there are no active goals, associations must be empty; a clear user request must create new_goals rather than ask whether it is new. "
            "Create one new goal for each independently satisfiable user responsibility that can succeed, fail, be clarified, or be answered separately. "
            "A physical action and a conversational answer are independent goals. Two ordered physical actions are independent goals when each has its own completion criterion; ordering is preserved for the planner, not collapsed into one goal. "
            "Do not split implementation steps into goals. In particular, do not split implementation mechanics, safety checks, status lookups, or capability calls into goals. Do not emit relationship=new as a substitute for a SemanticGoal in new_goals. "
            "If the user's meaning itself is materially ambiguous, propose no change and ask one concise natural clarification naming human topics, never internal IDs.\n\n"
            "Return compact JSON with turn_id, associations, new_goals, clarification, confidence, reason_summary, metadata. "
            "Each association uses relationship, target_goal_ids copied exactly from active goals, confidence, and reason_summary. "
            "For modify, clarify, or replace relationships, include goal_update as a semantic delta such as description, constraints, object, beneficiary, or success_criteria; include resolved_gap_ids when the turn answers an existing gap, and set requires_replan when the retained goal or constraints changed. "
            "Each new goal uses open semantic description, source_text, beneficiary, constraints, and success_criteria when known. "
            "Do not output skills, plans, task IDs not supplied, authorization, execution claims, markdown, or hidden reasoning. "
            "The Ollama decoder enforces the exact dynamic GoalAssociationResolution JSON Schema out-of-band. Return JSON only.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL ACTIVE GOAL IDS JSON:\n{self._bounded_json([item.get('goal_id') for item in active_goals], 1800)}"
        )

    def _build_repair_prompt(
        self,
        *,
        request: AgentRunRequest,
        active_goals: list[dict[str, Any]],
        turn_id: str,
        response_schema: dict[str, Any],
        raw: dict[str, Any],
        validation_error: str,
    ) -> str:
        return (
            "The previous Goal Association JSON failed the exact contract. Re-evaluate the semantic associations and "
            "return one corrected JSON object. Preserve valid semantic judgments, but revise every field needed to satisfy "
            "the schema and validation errors. Do not explain the correction and do not use synonym substitution rules.\n\n"
            f"Latest user turn:\n{request.text}\n\n"
            f"Required turn_id:\n{turn_id}\n\n"
            "Bounded active goals JSON:\n"
            f"{self._bounded_json(active_goals, 7000)}\n\n"
            "Previous model output JSON:\n"
            f"{self._bounded_json(raw, 5000)}\n\n"
            "Exact validation errors JSON:\n"
            f"{validation_error}\n\n"
            "The Exact GoalAssociationResolution JSON Schema is enforced by the Ollama decoder out-of-band. "
            "Re-segment every independently satisfiable responsibility from the authoritative user turn; do not preserve an invalid merge merely because it appeared in the previous output.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}"
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You repair one Goal Association structured output using semantic reasoning and the supplied exact JSON Schema. "
            "Return only the corrected JSON object. Do not add commentary, markdown, lexical mappings, or hidden reasoning."
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
            normalized.setdefault("goal_update", {})
            normalized.setdefault("resolved_gap_ids", [])
            normalized.setdefault("requires_replan", normalized.get("relationship") in {"modify", "clarify", "replace"})
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
