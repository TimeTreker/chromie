from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .clients.ollama_client import OllamaClient
from .schema import AgentRunRequest

try:
    from chromie_contracts.semantic_task import (
        SemanticTaskOperation,
        SemanticTaskOperationSet,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.semantic_task import (
        SemanticTaskOperation,
        SemanticTaskOperationSet,
    )


logger = logging.getLogger("chromie.agent.task_continuity")


class TaskContinuityResolver:
    """Resolve how one utterance changes the bounded active-task set.

    The model proposes semantic operations. This class validates shape, target
    task IDs, confidence, and deterministic operation IDs, but it never mutates
    task state or authorizes side effects.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        min_confidence: float = 0.65,
        max_active_tasks: int = 8,
        num_ctx: int = 8192,
        num_predict: int = 640,
    ) -> None:
        self.ollama = ollama
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.max_active_tasks = max(1, min(32, int(max_active_tasks)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: AgentRunRequest) -> SemanticTaskOperationSet:
        active_tasks = self._active_tasks(request)
        if not active_tasks:
            return SemanticTaskOperationSet(
                confidence=1.0,
                reason_summary="No active tasks require continuity resolution.",
                metadata={
                    "resolver": "task_continuity_agent",
                    "status": "skipped_no_active_tasks",
                },
            )

        try:
            raw = await self.ollama.generate(
                self._build_prompt(request, active_tasks),
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
                raise ValueError("task-continuity model response is not a JSON object")
            normalized = self._normalize_raw_output(raw, request)
            proposed = SemanticTaskOperationSet.model_validate(normalized)
        except Exception as exc:
            logger.exception(
                "task continuity model degraded sid=%s error_type=%s error=%s",
                request.sid,
                type(exc).__name__,
                exc,
            )
            return SemanticTaskOperationSet(
                confidence=0.0,
                reason_summary="Task continuity model was unavailable; no semantic task operation was accepted.",
                metadata={
                    "resolver": "task_continuity_agent",
                    "status": "model_unavailable",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    "active_task_count": len(active_tasks),
                    "sid": request.sid,
                },
            )

        return self._validate_against_active_tasks(
            proposed,
            request=request,
            active_tasks=active_tasks,
        )

    def _active_tasks(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context if isinstance(request.context, dict) else {}
        raw = context.get("active_task_snapshots")
        if not isinstance(raw, list):
            session_memory = context.get("session_memory")
            raw = (
                session_memory.get("active_task_snapshots")
                if isinstance(session_memory, dict)
                else []
            )
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)][
            : self.max_active_tasks
        ]

    @staticmethod
    def _bounded_json(value: Any, *, max_chars: int) -> str:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if len(text) > max_chars:
            return text[:max_chars].rstrip() + "..."
        return text

    def _build_prompt(
        self,
        request: AgentRunRequest,
        active_tasks: list[dict[str, Any]],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        mind = context.get("mind") if isinstance(context.get("mind"), dict) else {}
        route = request.route_decision
        route_summary = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
            "routes": [
                {
                    "route": item.route,
                    "intent": item.intent,
                    "confidence": item.confidence,
                    "lane": item.lane,
                }
                for item in route.routes[:8]
            ],
            "router_semantic_task_operations": (
                route.metadata.get("semantic_task_operations")
                if isinstance(route.metadata, dict)
                else None
            ),
        }
        session_summary = {
            "conversation_id": context.get("conversation_id"),
            "recent_turn_fallback": context.get("recent_turn_fallback") or [],
            "current_task_context": context.get("current_task_context"),
        }
        identity = mind.get("identity") if isinstance(mind, dict) else None
        return (
            "Global Context Group:\n"
            f"Robot identity JSON: {self._bounded_json(identity or {'name': 'Chromie'}, max_chars=500)}\n"
            "The model proposes semantic task operations only. Runtime code owns task IDs, versions, authorization, commitment, and execution.\n\n"
            "Session Context Group:\n"
            f"Language hint: {request.language or route.language or 'auto'}\n"
            f"Bounded session JSON: {self._bounded_json(session_summary, max_chars=1600)}\n"
            f"Active task snapshots JSON: {self._bounded_json(active_tasks, max_chars=6200)}\n\n"
            "Current Job:\n"
            "Determine how the latest user utterance relates to the supplied active tasks. "
            "Return create, modify, clarification_answer, confirm, reject, cancel, pause, resume, query_status, correct, or replace operations only when semantically justified.\n\n"
            "Task Context Group:\n"
            f"Latest user input: {request.text}\n"
            f"Router output is advisory JSON: {self._bounded_json(route_summary, max_chars=2600)}\n\n"
            "Cost Function:\n"
            "Preserve task continuity before creating unnecessary tasks. Preserve the user's intended outcome before preserving an old plan. "
            "Meaning and bounded context before lexical overlap. Clarify before attaching a change to the wrong task. "
            "Update goals before rewriting execution steps. Honest uncertainty before guessing.\n\n"
            "Output Contract:\n"
            "Return one compact JSON object with keys operations, response_plan, confidence, reason_summary, and optional metadata. "
            "operations may be empty. Every create operation requires an open semantic goal with description and source_text. "
            "Every non-create operation requires target_task_ids copied exactly from the supplied task snapshots. "
            "Use goal_update for semantic changes and requires_replan when the implementation method may change. "
            "If task reference is ambiguous, return no modifying operation and use response_plan.immediate to ask one concise clarification. "
            "Immediate speech may acknowledge, evaluate, or clarify but must not claim unverified execution or completion. "
            "Do not output skills, motor controls, authorization, chain-of-thought, hidden analysis, markdown, or text outside JSON."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's semantic Task Continuity Agent. "
            "Understand task relationships from meaning, conversation context, open semantic goals, unresolved information gaps, and task lifecycle. "
            "Do not decide normal association through keywords, phrase tables, regexes, entity overlap, or recency alone. "
            "Retrieval and Router output are advisory context only. "
            "Never execute, authorize, or claim a task update was applied. Return JSON only."
        )

    def _normalize_raw_output(
        self,
        raw: dict[str, Any],
        request: AgentRunRequest,
    ) -> dict[str, Any]:
        operations = raw.get("operations")
        if operations is None:
            operations = raw.get("semantic_task_operations")
        if isinstance(operations, dict):
            operations = [operations]
        if not isinstance(operations, list):
            operations = []

        normalized_ops: list[dict[str, Any]] = []
        for index, item in enumerate(operations):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["operation_id"] = self._operation_id(
                request,
                index=index,
                operation=normalized,
            )
            normalized_ops.append(normalized)

        return {
            "schema_version": raw.get("schema_version", 1),
            "operations": normalized_ops,
            "response_plan": raw.get("response_plan"),
            "confidence": raw.get("confidence", 0.0),
            "reason_summary": raw.get("reason_summary") or raw.get("reason") or "",
            "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
        }

    @staticmethod
    def _operation_id(
        request: AgentRunRequest,
        *,
        index: int,
        operation: dict[str, Any],
    ) -> str:
        payload = dict(operation)
        payload.pop("operation_id", None)
        stable = json.dumps(
            {
                "sid": request.sid or "",
                "text": request.text,
                "index": index,
                "operation": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
        sid = "".join(ch for ch in str(request.sid or "turn") if ch.isalnum())[:24]
        return f"task-continuity:{sid or 'turn'}:{index}:{digest}"

    def _validate_against_active_tasks(
        self,
        proposed: SemanticTaskOperationSet,
        *,
        request: AgentRunRequest,
        active_tasks: list[dict[str, Any]],
    ) -> SemanticTaskOperationSet:
        active_ids = {
            str(item.get("task_id") or "").strip()
            for item in active_tasks
            if str(item.get("task_id") or "").strip()
        }
        accepted: list[SemanticTaskOperation] = []
        rejected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for operation in proposed.operations:
            reason = ""
            if operation.operation_id in seen_ids:
                reason = "duplicate_operation_id"
            elif operation.confidence < self.min_confidence:
                reason = "below_confidence_threshold"
            elif operation.operation != "create" and any(
                task_id not in active_ids for task_id in operation.target_task_ids
            ):
                reason = "unknown_target_task"
            elif operation.operation == "create" and operation.target_task_ids:
                reason = "create_must_not_target_existing_task"

            if reason:
                rejected.append(
                    {
                        "operation_id": operation.operation_id,
                        "operation": operation.operation,
                        "reason": reason,
                        "target_task_ids": operation.target_task_ids,
                        "confidence": operation.confidence,
                    }
                )
                continue
            seen_ids.add(operation.operation_id)
            accepted.append(operation)

        metadata = dict(proposed.metadata)
        metadata.update(
            {
                "resolver": "task_continuity_agent",
                "status": "resolved",
                "active_task_count": len(active_tasks),
                "accepted_operation_count": len(accepted),
                "rejected_operations": rejected,
                "min_confidence": self.min_confidence,
                "sid": request.sid,
            }
        )
        return proposed.model_copy(
            update={
                "operations": accepted,
                "metadata": metadata,
            }
        )
