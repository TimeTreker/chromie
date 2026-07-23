from __future__ import annotations

import copy
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque

from orchestrator.runtime.memory import MemoryExtractor, MemoryPromptBuilder, MemoryStore

try:
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.execution_outcome import (
        ExecutionOutcomeBundle,
        execution_outcome_fingerprint,
    )
    from chromie_contracts.semantic_task import (
        InformationGap,
        SemanticGoal,
        SemanticTaskOperation,
        TaskContextSnapshot,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.execution_outcome import (
        ExecutionOutcomeBundle,
        execution_outcome_fingerprint,
    )
    from shared.chromie_contracts.semantic_task import (
        InformationGap,
        SemanticGoal,
        SemanticTaskOperation,
        TaskContextSnapshot,
    )


_DONE_TASK_STATUSES = {"done", "failed", "refused", "timed_out", "cancelled", "canceled", "expired", "superseded"}
_TASK_RELATIONS = {
    "new_task",
    "continue_task",
    "modify_task",
    "close_task",
    "side_conversation",
    "clarify_task",
}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_TASK_STORE_PATH = ".chromie/conversation/task_contexts.json"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now_ms() -> float:
    return time.time() * 1000.0


def _split_phrases(value: str | None, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return defaults
    phrases = [part.strip().lower() for part in value.split("|") if part.strip()]
    return tuple(phrases) if phrases else defaults


DEFAULT_RESET_PHRASES = (
    "new topic",
    "new session",
    "start a new session",
    "start a new conversation",
    "reset conversation",
    "reset session",
    "clear session",
    "clear conversation",
    "新的会话",
    "新会话",
    "开始新的会话",
    "开始新会话",
    "重置会话",
    "清空会话",
)

DEFAULT_FOLLOWUP_PHRASES = (
    "when",
    "when will",
    "how about",
    "what about",
    "did you",
    "did it",
    "is it",
    "that one",
    "this one",
    "continue",
    "go on",
    "then",
    "why",
    "what do you mean",
    "answer",
    "result",
    "it",
    "that",
    "them",
    "him",
    "her",
    "什么时候",
    "结果",
    "查到了吗",
    "好了没",
    "继续",
    "然后呢",
    "为什么",
    "什么意思",
    "那个",
    "这个",
    "它",
    "他",
    "她",
    "刚才",
)

DEFAULT_NEW_TOPIC_STARTERS = (
    "check ",
    "search ",
    "look up ",
    "tell me ",
    "what is ",
    "what's ",
    "who is ",
    "where is ",
    "can you ",
    "could you ",
    "please ",
    "turn ",
    "move ",
    "go ",
    "查",
    "搜索",
    "帮我",
    "告诉我",
    "什么是",
    "请",
    "转",
    "移动",
    "去",
)


class ConversationStateManager:
    """Host-side short-term conversation state for Chromie.

    This is not long-term memory. It keeps only recent turns and lightweight
    pending-task hints in RAM so follow-up utterances can resolve references
    such as "when will you give me the answer?" or "what about it?".

    The orchestrator still creates one SID per VAD utterance. This manager adds
    a separate conversation_id that can span many SIDs until a reset phrase or
    idle timeout starts a new conversation.
    """

    def __init__(
        self,
        *,
        base_conversation_id: str = "local_default",
        enabled: bool = True,
        max_turns: int = 12,
        soft_idle_timeout_sec: int = 180,
        hard_idle_timeout_sec: int = 900,
        turn_max_text_chars: int = 260,
        max_context_chars: int = 2200,
        max_pending_tasks: int = 8,
        max_memory_entries: int = 24,
        completed_task_retention_sec: int = 180,
        task_store_enabled: bool = False,
        task_store_path: str | os.PathLike[str] | None = None,
        reset_phrases: tuple[str, ...] = DEFAULT_RESET_PHRASES,
        followup_phrases: tuple[str, ...] = DEFAULT_FOLLOWUP_PHRASES,
        new_topic_starters: tuple[str, ...] = DEFAULT_NEW_TOPIC_STARTERS,
    ) -> None:
        self.base_conversation_id = base_conversation_id or "local_default"
        self.enabled = enabled
        self.max_turns = max(0, int(max_turns))
        self.soft_idle_timeout_sec = max(1, int(soft_idle_timeout_sec))
        self.hard_idle_timeout_sec = max(self.soft_idle_timeout_sec, int(hard_idle_timeout_sec))
        self.turn_max_text_chars = max(20, int(turn_max_text_chars))
        self.max_context_chars = max(200, int(max_context_chars))
        self.max_pending_tasks = max(0, int(max_pending_tasks))
        self.max_memory_entries = max(1, int(max_memory_entries))
        self.completed_task_retention_sec = max(0, int(completed_task_retention_sec))
        self.task_store_enabled = bool(task_store_enabled)
        self.task_store_path = self._resolve_task_store_path(task_store_path)
        self.last_task_store_error: str | None = None
        self.reset_phrases = tuple(p.lower() for p in reset_phrases)
        self.followup_phrases = tuple(p.lower() for p in followup_phrases)
        self.new_topic_starters = tuple(p.lower() for p in new_topic_starters)

        self._conversation_seq = 1
        self.conversation_id = self.base_conversation_id
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_turns * 2))
        self._pending_tasks: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_pending_tasks))
        self._task_contexts: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_pending_tasks))
        self._memory_store = MemoryStore(max_entries=self.max_memory_entries)
        self._memory_extractor = MemoryExtractor()
        self._memory_prompt_builder = MemoryPromptBuilder()
        self.last_split_reason: str | None = None
        if self.task_store_enabled:
            self._restore_task_contexts()

    @classmethod
    def from_env(cls) -> "ConversationStateManager":
        return cls(
            base_conversation_id=os.getenv("ORCH_CONVERSATION_ID", "local_default"),
            enabled=_env_bool("ORCH_ENABLE_CONVERSATION_STATE", True),
            max_turns=int(os.getenv("ORCH_CONVERSATION_MAX_TURNS", os.getenv("ORCH_CONTEXT_MAX_TURNS", "12"))),
            soft_idle_timeout_sec=int(
                os.getenv("ORCH_CONVERSATION_IDLE_TIMEOUT_SEC", os.getenv("ORCH_CONTEXT_IDLE_TIMEOUT_SEC", "180"))
            ),
            hard_idle_timeout_sec=int(
                os.getenv("ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC", os.getenv("ORCH_CONTEXT_MAX_AGE_SECONDS", "900"))
            ),
            turn_max_text_chars=int(
                os.getenv("ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS", os.getenv("ORCH_CONTEXT_MAX_TEXT_CHARS", "260"))
            ),
            max_context_chars=int(os.getenv("ORCH_CONVERSATION_MAX_CONTEXT_CHARS", "2200")),
            max_pending_tasks=int(
                os.getenv("ORCH_CONVERSATION_MAX_PENDING_TASKS", os.getenv("ORCH_CONTEXT_MAX_PENDING_TASKS", "8"))
            ),
            max_memory_entries=int(os.getenv("ORCH_CONVERSATION_MAX_MEMORY_ENTRIES", "24")),
            completed_task_retention_sec=int(os.getenv("ORCH_CONVERSATION_COMPLETED_TASK_RETENTION_SEC", "180")),
            task_store_enabled=_env_bool("ORCH_ENABLE_TASK_CONTEXT_STORE", False),
            task_store_path=os.getenv("ORCH_TASK_CONTEXT_STORE_PATH", _DEFAULT_TASK_STORE_PATH),
            reset_phrases=_split_phrases(os.getenv("ORCH_CONVERSATION_RESET_PHRASES"), DEFAULT_RESET_PHRASES),
            followup_phrases=_split_phrases(os.getenv("ORCH_CONVERSATION_FOLLOWUP_PHRASES"), DEFAULT_FOLLOWUP_PHRASES),
            new_topic_starters=_split_phrases(os.getenv("ORCH_CONVERSATION_NEW_TOPIC_STARTERS"), DEFAULT_NEW_TOPIC_STARTERS),
        )

    @staticmethod
    def _resolve_task_store_path(path: str | os.PathLike[str] | None) -> Path:
        resolved = Path(path or _DEFAULT_TASK_STORE_PATH).expanduser()
        if not resolved.is_absolute():
            resolved = _PROJECT_ROOT / resolved
        return resolved

    def _compact_text(self, text: str | None, *, limit: int | None = None) -> str:
        text = " ".join((text or "").strip().split())
        max_len = limit or self.turn_max_text_chars
        if len(text) > max_len:
            return text[:max_len].rstrip() + "…"
        return text

    def _new_task_id(self) -> str:
        return f"task_{int(_now_ms())}_{len(self._task_contexts) + 1}"

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _durable_task_contexts(self) -> list[dict[str, Any]]:
        if self.max_pending_tasks <= 0:
            return []
        durable: list[dict[str, Any]] = []
        for context in self._task_contexts:
            status = str(context.get("status") or "open").lower()
            if status in _DONE_TASK_STATUSES:
                continue
            policy = str(context.get("persistence_policy") or "persist_if_unfinished").lower()
            if policy in {"ephemeral", "memory_only", "do_not_persist", "none"}:
                continue
            durable.append(self._json_safe(dict(context)))
        return durable[-self.max_pending_tasks :]

    def persist_task_contexts(self) -> bool:
        if not self.enabled or not self.task_store_enabled:
            return False
        payload = {
            "version": 1,
            "conversation_id": self.conversation_id,
            "saved_ms": _now_ms(),
            "task_contexts": self._durable_task_contexts(),
        }
        try:
            self.task_store_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.task_store_path.with_name(self.task_store_path.name + ".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            temp_path.replace(self.task_store_path)
            self.last_task_store_error = None
            return True
        except OSError as exc:
            self.last_task_store_error = str(exc)
            return False

    def _persist_task_contexts_if_enabled(self) -> None:
        self.persist_task_contexts()

    def _restore_task_contexts(self) -> None:
        if self.max_pending_tasks <= 0:
            return
        if not self.task_store_path.exists():
            return
        try:
            payload = json.loads(self.task_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.last_task_store_error = str(exc)
            return
        raw_contexts = payload.get("task_contexts") if isinstance(payload, dict) else payload
        if not isinstance(raw_contexts, list):
            return
        now = _now_ms()
        restored: list[dict[str, Any]] = []
        for item in raw_contexts[-self.max_pending_tasks :]:
            if not isinstance(item, dict):
                continue
            original_status = str(item.get("status") or "open")
            if original_status.lower() in _DONE_TASK_STATUSES:
                continue
            context = dict(item)
            context["conversation_id"] = self.conversation_id
            context["status"] = "recoverable"
            context["task_relation"] = "continue_task"
            context["updated_ms"] = now
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            context["metadata"] = {
                **metadata,
                "restored_from_task_store": True,
                "restored_original_status": original_status,
                "restored_ms": now,
            }
            if not isinstance(context.get("related_sids"), list):
                context["related_sids"] = []
            restored.append(context)
        if restored:
            self._task_contexts = deque(restored, maxlen=max(1, self.max_pending_tasks))
            self.last_split_reason = "restored_task_contexts"
            self.last_task_store_error = None

    @staticmethod
    def _normalized(text: str | None) -> str:
        text = " ".join((text or "").strip().lower().split())
        return text

    def _has_any_context(self) -> bool:
        return bool(
            self._turns
            or self._pending_tasks
            or self._task_contexts
            or self._memory_store.prompt_entries(limit=1)
        )

    def _active_pending_tasks(self) -> list[dict[str, Any]]:
        self._prune_completed_tasks()
        tasks: list[dict[str, Any]] = []
        for task in self._pending_tasks:
            status = str(task.get("status") or "pending").lower()
            if status not in _DONE_TASK_STATUSES:
                tasks.append(task)
        return tasks

    def _active_task_contexts(self) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for context in self._task_contexts:
            status = str(context.get("status") or "open").lower()
            if status not in _DONE_TASK_STATUSES:
                contexts.append(context)
        return contexts

    def _current_task_context(self) -> dict[str, Any] | None:
        active = self._active_task_contexts()
        if active:
            return active[-1]
        if self._task_contexts:
            return self._task_contexts[-1]
        return None

    def _task_context_by_id(self, task_id: str | None) -> dict[str, Any] | None:
        if not task_id:
            return None
        for context in reversed(self._task_contexts):
            if str(context.get("task_id") or "") == task_id:
                return context
        return None

    def _task_context_by_goal_id(self, goal_id: str | None) -> dict[str, Any] | None:
        """Resolve a semantic goal ID without confusing it with its task ID.

        Goal Association intentionally gives newly segmented goals stable
        ``goal_*`` identifiers while the host creates separate ``task_*``
        persistence records.  Planner steps are scoped to the semantic goal ID,
        so execution evidence must cross that boundary explicitly instead of
        treating a goal ID as a task ID.  Legacy task-backed goals still work
        because their semantic goal ID is the task ID.
        """

        normalized = " ".join(str(goal_id or "").strip().split())
        if not normalized:
            return None
        task_id_match: dict[str, Any] | None = None
        for context in reversed(self._task_contexts):
            goal = self._semantic_goal_from_context(context)
            if str(goal.goal_id or "") == normalized:
                return context
            if (
                task_id_match is None
                and str(context.get("task_id") or "") == normalized
            ):
                task_id_match = context
        return task_id_match

    @staticmethod
    def _semantic_goal_from_context(context: dict[str, Any]) -> SemanticGoal:
        raw = context.get("semantic_goal")
        if isinstance(raw, dict):
            try:
                return SemanticGoal.model_validate(raw)
            except Exception:
                pass
        description = " ".join(
            str(context.get("goal") or context.get("task_type") or "task").strip().split()
        ) or "task"
        source_text = " ".join(
            str(context.get("last_meaningful_user_turn") or description).strip().split()
        ) or description
        constraints = context.get("constraints")
        if not isinstance(constraints, dict):
            constraints = {}
        return SemanticGoal(
            goal_id=str(context.get("task_id") or "") or None,
            version=max(1, int(context.get("goal_version") or 1)),
            description=description,
            source_text=source_text,
            constraints=constraints,
        )

    def _task_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        goal = self._semantic_goal_from_context(context)
        raw_gaps = context.get("open_information_gaps")
        gaps: list[InformationGap] = []
        if isinstance(raw_gaps, list):
            for item in raw_gaps:
                if not isinstance(item, dict):
                    continue
                try:
                    gap = InformationGap.model_validate(item)
                except Exception:
                    continue
                if not gap.resolved:
                    gaps.append(gap)
        raw_status = str(context.get("status") or "open").strip().lower()
        status_alias = {
            "pending": "open",
            "awaiting_user": "waiting_for_user",
            "canceled": "cancelled",
            "expired": "timed_out",
        }
        status = status_alias.get(raw_status, raw_status)
        allowed_statuses = {
            "open",
            "planning",
            "needs_context",
            "waiting_for_user",
            "awaiting_confirmation",
            "committed",
            "scheduled",
            "running",
            "paused",
            "recoverable",
            "done",
            "failed",
            "refused",
            "timed_out",
            "cancelled",
            "superseded",
        }
        if status not in allowed_statuses:
            status = "open"
        commitment = str(context.get("commitment_state") or "none").strip().lower()
        if commitment not in {
            "none",
            "heard",
            "evaluating",
            "accepted",
            "waiting_for_user",
            "executing",
            "completed",
            "failed",
            "cancelled",
        }:
            commitment = "none"
        confirmation = context.get("confirmation")
        if not isinstance(confirmation, dict):
            confirmation = None
        evidence = context.get("evidence_summary")
        if not isinstance(evidence, dict):
            evidence = {}
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return TaskContextSnapshot(
            task_id=str(context.get("task_id") or "unknown-task"),
            status=status,  # type: ignore[arg-type]
            semantic_goal=goal,
            goal_version=max(1, int(context.get("goal_version") or goal.version or 1)),
            plan_version=max(0, int(context.get("plan_version") or 0)),
            open_information_gaps=gaps,
            confirmation=confirmation,
            commitment_state=commitment,  # type: ignore[arg-type]
            last_user_update=str(context.get("last_meaningful_user_turn") or ""),
            evidence_summary=evidence,
            metadata={
                "task_type": context.get("task_type"),
                "task_relation": context.get("task_relation"),
                "updated_ms": context.get("updated_ms"),
                **{
                    key: metadata.get(key)
                    for key in (
                        "last_route",
                        "last_intent",
                        "restored_from_task_store",
                        "restored_original_status",
                    )
                    if metadata.get(key) is not None
                },
            },
        ).model_dump(mode="json", exclude_none=True)

    def active_task_snapshots(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        active = self._active_task_contexts()
        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        return [self._task_snapshot(item) for item in active[-limit:]]

    def active_goal_snapshots(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return a bounded goal-first projection without changing task runtime behavior."""

        task_snapshots = self.active_task_snapshots(limit=limit)
        return [
            ActiveGoalSnapshot.from_task_snapshot(item).model_dump(mode="json", exclude_none=True)
            for item in task_snapshots
        ]

    @staticmethod
    def _semantic_operations_from_metadata(
        metadata: dict[str, Any] | None,
    ) -> list[SemanticTaskOperation]:
        if not isinstance(metadata, dict):
            return []
        raw = (
            metadata.get("semantic_task_operations")
            or metadata.get("task_operations")
            or metadata.get("semantic_task_operation")
        )
        if raw is None:
            return []
        if isinstance(raw, dict):
            if isinstance(raw.get("operations"), list):
                raw = raw["operations"]
            else:
                raw = [raw]
        if not isinstance(raw, list):
            return []
        operations: list[SemanticTaskOperation] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                operations.append(SemanticTaskOperation.model_validate(item))
            except Exception:
                continue
        return operations

    @staticmethod
    def _context_has_operation_id(
        context: dict[str, Any],
        operation_id: str,
    ) -> bool:
        history = context.get("operation_history")
        if not isinstance(history, list):
            return False
        return any(
            isinstance(item, dict)
            and str(item.get("operation_id") or "") == operation_id
            for item in history
        )

    def _context_by_operation_id(
        self,
        operation_id: str,
    ) -> dict[str, Any] | None:
        if not operation_id:
            return None
        for context in reversed(self._task_contexts):
            if self._context_has_operation_id(context, operation_id):
                return context
        return None

    def _new_semantic_task_context(
        self,
        *,
        sid: str | None,
        operation: SemanticTaskOperation,
        user_text: str,
        route: str | None,
        intent: str | None,
        source: str | None,
    ) -> dict[str, Any]:
        assert operation.goal is not None
        now = _now_ms()
        task_id = self._new_task_id()
        goal = operation.goal.model_copy(
            update={
                "goal_id": operation.goal.goal_id or task_id,
                "version": 1,
                "source_text": operation.goal.source_text or user_text,
            }
        )
        status = operation.status_update or (
            "waiting_for_user"
            if any(gap.blocking and gap.preferred_resolution == "ask_user" for gap in operation.information_gaps)
            else "planning"
            if operation.requires_replan
            else "open"
        )
        commitment = operation.commitment_state or (
            "waiting_for_user" if status == "waiting_for_user" else "evaluating"
        )
        context = {
            "task_id": task_id,
            "conversation_id": self.conversation_id,
            "status": status,
            "task_relation": "new_task",
            "task_type": str((operation.metadata or {}).get("task_type") or self._default_task_type(route, intent)),
            "goal": self._compact_text(goal.description, limit=220),
            "semantic_goal": goal.model_dump(mode="json", exclude_none=True),
            "goal_version": 1,
            "plan_version": 0,
            "plan_status": "not_planned",
            "commitment_state": commitment,
            "important_claims": [],
            "entities": [],
            "constraints": dict(goal.constraints),
            "pending_questions": [gap.description for gap in operation.information_gaps if gap.blocking],
            "open_information_gaps": [
                gap.model_dump(mode="json", exclude_none=True)
                for gap in operation.information_gaps
                if not gap.resolved
            ],
            "operation_history": [
                {
                    "operation_id": operation.operation_id,
                    "operation": operation.operation,
                    "goal_version": 1,
                    "ts_ms": now,
                    "reason_summary": operation.reason_summary,
                }
            ],
            "last_meaningful_user_turn": self._compact_text(user_text, limit=220),
            "last_assistant_response": None,
            "related_sids": [sid] if sid else [],
            "created_ms": now,
            "updated_ms": now,
            "persistence_policy": str((operation.metadata or {}).get("persistence_policy") or "persist_if_unfinished"),
            "confirmation": None,
            "evidence_summary": {},
            "metadata": {
                "last_route": route,
                "last_intent": intent,
                "source": source,
                "semantic_operation_id": operation.operation_id,
                "semantic_operation_confidence": operation.confidence,
                "semantic_relationship": operation.relationship,
                "requires_replan": operation.requires_replan,
            },
        }
        self._task_contexts.append(context)
        return context

    @staticmethod
    def _merge_semantic_goal(
        goal: SemanticGoal,
        operation: SemanticTaskOperation,
        *,
        user_text: str,
    ) -> SemanticGoal:
        update = dict(operation.goal_update or {})
        if operation.goal is not None:
            replacement = operation.goal
            update = {
                "description": replacement.description,
                "source_text": replacement.source_text,
                "beneficiary": replacement.beneficiary,
                "object": replacement.object,
                "constraints": replacement.constraints,
                "success_criteria": replacement.success_criteria,
                "metadata": replacement.metadata,
                **update,
            }

        constraints = dict(goal.constraints)
        replacement_constraints = update.get("constraints")
        if isinstance(replacement_constraints, dict):
            constraints = dict(replacement_constraints)
        constraint_updates = update.get("constraint_updates")
        if isinstance(constraint_updates, dict):
            constraints.update(constraint_updates)
        removals = update.get("constraint_removals")
        if isinstance(removals, list):
            for key in removals:
                constraints.pop(str(key), None)

        object_value = dict(goal.object)
        replacement_object = update.get("object")
        if isinstance(replacement_object, dict):
            object_value = replacement_object
        object_updates = update.get("object_updates")
        if isinstance(object_updates, dict):
            object_value.update(object_updates)

        criteria = update.get("success_criteria", goal.success_criteria)
        metadata = dict(goal.metadata)
        update_metadata = update.get("metadata")
        if isinstance(update_metadata, dict):
            metadata.update(update_metadata)

        version = goal.version + 1
        return SemanticGoal(
            goal_id=goal.goal_id,
            version=version,
            description=str(update.get("description") or goal.description),
            source_text=str(update.get("source_text") or user_text or goal.source_text),
            beneficiary=(
                str(update.get("beneficiary"))
                if update.get("beneficiary") is not None
                else goal.beneficiary
            ),
            object=object_value,
            constraints=constraints,
            success_criteria=criteria,
            metadata=metadata,
        )

    def _apply_semantic_operation_to_context(
        self,
        context: dict[str, Any],
        operation: SemanticTaskOperation,
        *,
        sid: str | None,
        user_text: str,
        route: str | None,
        intent: str | None,
        source: str | None,
    ) -> dict[str, Any]:
        now = _now_ms()
        result: dict[str, Any] = {
            "operation_id": operation.operation_id,
            "operation": operation.operation,
            "task_id": context.get("task_id"),
            "applied": False,
        }
        if self._context_has_operation_id(context, operation.operation_id):
            result.update(
                {
                    "replayed": True,
                    "reason": "operation_already_applied",
                    "goal_version": int(context.get("goal_version") or 1),
                    "plan_version": int(context.get("plan_version") or 0),
                    "status": context.get("status"),
                }
            )
            return result

        status = str(context.get("status") or "open").lower()
        if status in _DONE_TASK_STATUSES and operation.operation not in {"query_status"}:
            result["reason"] = f"task_status_{status}_is_not_modifiable"
            return result

        if operation.operation in {"cancel", "reject"}:
            context["status"] = "cancelled" if operation.operation == "cancel" else "refused"
            context["commitment_state"] = "cancelled" if operation.operation == "cancel" else "failed"
        elif operation.operation == "pause":
            context["status"] = "paused"
        elif operation.operation == "resume":
            context["status"] = operation.status_update or "planning"
            context["commitment_state"] = operation.commitment_state or "evaluating"
        elif operation.operation == "confirm":
            context["status"] = operation.status_update or "committed"
            context["commitment_state"] = operation.commitment_state or "accepted"
        elif operation.operation == "query_status":
            pass
        else:
            goal = self._semantic_goal_from_context(context)
            revised = self._merge_semantic_goal(goal, operation, user_text=user_text)
            context["semantic_goal"] = revised.model_dump(mode="json", exclude_none=True)
            context["goal"] = self._compact_text(revised.description, limit=220)
            context["goal_version"] = revised.version
            context["constraints"] = dict(revised.constraints)

            raw_gaps = context.get("open_information_gaps")
            existing_gaps: list[dict[str, Any]] = [
                dict(item) for item in raw_gaps if isinstance(item, dict)
            ] if isinstance(raw_gaps, list) else []
            resolved = set(operation.resolved_gap_ids)
            existing_gaps = [
                item for item in existing_gaps
                if str(item.get("gap_id") or "") not in resolved
            ]
            by_id = {
                str(item.get("gap_id") or ""): item
                for item in existing_gaps
                if str(item.get("gap_id") or "")
            }
            for gap in operation.information_gaps:
                if gap.resolved:
                    by_id.pop(gap.gap_id, None)
                else:
                    by_id[gap.gap_id] = gap.model_dump(mode="json", exclude_none=True)
            context["open_information_gaps"] = list(by_id.values())
            context["pending_questions"] = [
                str(item.get("description") or "")
                for item in context["open_information_gaps"]
                if item.get("blocking") is not False and str(item.get("description") or "")
            ][:4]

            old_plan_version = max(0, int(context.get("plan_version") or 0))
            if operation.requires_replan or operation.operation in {
                "modify",
                "clarification_answer",
                "correct",
                "replace",
            }:
                if old_plan_version:
                    superseded = context.get("superseded_plan_versions")
                    if not isinstance(superseded, list):
                        superseded = []
                    if old_plan_version not in superseded:
                        superseded.append(old_plan_version)
                    context["superseded_plan_versions"] = superseded[-12:]
                context["plan_status"] = "superseded" if old_plan_version else "not_planned"
                confirmation = context.get("confirmation")
                if isinstance(confirmation, dict) and confirmation:
                    invalidated = context.get("invalidated_confirmations")
                    if not isinstance(invalidated, list):
                        invalidated = []
                    invalidated.append({**confirmation, "invalidated_ms": now, "reason": "goal_version_changed"})
                    context["invalidated_confirmations"] = invalidated[-8:]
                    context["confirmation"] = None

            blocking_user_gap = any(
                bool(item.get("blocking", True))
                and str(item.get("preferred_resolution") or "") == "ask_user"
                for item in context["open_information_gaps"]
            )
            blocking_context_gap = any(
                bool(item.get("blocking", True))
                and str(item.get("preferred_resolution") or "")
                in {"observe_environment", "query_trusted_service"}
                for item in context["open_information_gaps"]
            )
            context["status"] = operation.status_update or (
                "waiting_for_user"
                if blocking_user_gap
                else "needs_context"
                if blocking_context_gap
                else "planning"
            )
            context["commitment_state"] = operation.commitment_state or (
                "waiting_for_user" if context["status"] == "waiting_for_user" else "evaluating"
            )

        context["task_relation"] = {
            "modify": "modify_task",
            "clarification_answer": "clarify_task",
            "correct": "modify_task",
            "replace": "modify_task",
            "cancel": "close_task",
            "reject": "close_task",
        }.get(operation.operation, context.get("task_relation") or "continue_task")
        context["updated_ms"] = now
        context["last_meaningful_user_turn"] = self._compact_text(user_text, limit=220)
        if sid:
            related = context.get("related_sids")
            if not isinstance(related, list):
                related = []
            if sid not in related:
                related.append(sid)
            context["related_sids"] = related[-12:]
        history = context.get("operation_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "operation_id": operation.operation_id,
                "operation": operation.operation,
                "goal_version": int(context.get("goal_version") or 1),
                "plan_version": int(context.get("plan_version") or 0),
                "ts_ms": now,
                "reason_summary": operation.reason_summary,
            }
        )
        context["operation_history"] = history[-24:]
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        context["metadata"] = {
            **metadata,
            "last_route": route,
            "last_intent": intent,
            "source": source,
            "semantic_operation_id": operation.operation_id,
            "semantic_operation_confidence": operation.confidence,
            "semantic_relationship": operation.relationship,
            "requires_replan": operation.requires_replan,
        }
        result.update(
            {
                "applied": True,
                "goal_version": int(context.get("goal_version") or 1),
                "plan_version": int(context.get("plan_version") or 0),
                "status": context.get("status"),
            }
        )
        return result


    def _commit_semantic_state_transaction(
        self,
        mutate: Callable[[], list[dict[str, Any]]],
        *,
        rollback_reason: str = "atomic_semantic_transaction_rolled_back",
        persistence_failure_reason: str = "atomic_semantic_persistence_failed",
    ) -> list[dict[str, Any]]:
        """Commit one semantic-state mutation as an in-memory/durable transaction.

        This is the only rollback and durable-commit boundary for atomic Goal
        Association and semantic-operation batches. Callers mutate only in memory;
        this primitive snapshots state, rejects the whole batch on any
        non-idempotent failure, persists once, and restores the snapshot on
        rejection, persistence failure, or exception.
        """

        task_context_snapshot = copy.deepcopy(list(self._task_contexts))
        activity_snapshot = self.last_activity_ms
        store_error_snapshot = self.last_task_store_error

        def restore_snapshot(*, store_error: str | None = store_error_snapshot) -> None:
            self._task_contexts = deque(
                task_context_snapshot, maxlen=max(1, self.max_pending_tasks)
            )
            self.last_activity_ms = activity_snapshot
            self.last_task_store_error = store_error

        try:
            results = mutate()
            rejected = [
                item
                for item in results
                if item.get("applied") is False
                and item.get("reason") != "operation_already_applied"
            ]
            if rejected:
                restore_snapshot()
                for item in results:
                    if item.get("applied") is True:
                        item["applied"] = False
                        item["reason"] = rollback_reason
                        item["rolled_back"] = True
                return results

            changed = any(item.get("applied") is True for item in results)
            if changed:
                self.last_activity_ms = _now_ms()
            if changed and self.task_store_enabled and not self.persist_task_contexts():
                persistence_error = (
                    self.last_task_store_error or "task context persistence failed"
                )
                restore_snapshot(store_error=persistence_error)
                for item in results:
                    if item.get("applied") is True:
                        item["applied"] = False
                        item["reason"] = persistence_failure_reason
                        item["rolled_back"] = True
                        item["persistence_error"] = persistence_error
            return results
        except Exception:
            restore_snapshot()
            raise

    def apply_goal_association_resolution(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        sid: str | None,
        user_text: str,
        route: str | None = None,
        intent: str | None = None,
        source: str = "goal_association",
        atomic: bool = False,
    ) -> list[dict[str, Any]]:
        """Apply Goal Association through the shared semantic-state boundary."""

        if not self.enabled:
            return []

        def mutate() -> list[dict[str, Any]]:
            return self._apply_goal_association_resolution_in_memory(
                resolution,
                sid=sid,
                user_text=user_text,
                route=route,
                intent=intent,
                source=source,
            )

        if atomic:
            return self._commit_semantic_state_transaction(
                mutate,
                rollback_reason="atomic_goal_transaction_rolled_back",
                persistence_failure_reason="atomic_goal_persistence_failed",
            )

        results = mutate()
        if any(item.get("applied") is True for item in results):
            self._persist_task_contexts_if_enabled()
        return results

    def _apply_goal_association_resolution_in_memory(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        sid: str | None,
        user_text: str,
        route: str | None = None,
        intent: str | None = None,
        source: str = "goal_association",
    ) -> list[dict[str, Any]]:
        """Apply a validated goal-continuity result through semantic-task state.

        Semantic interpretation remains model-owned. This adapter only maps
        supported structured relationships into replay-safe state operations and
        records continuity markers for non-mutating references. Merge and split
        remain advisory until a dedicated multi-goal state transaction exists.
        """

        if not self.enabled:
            return []
        resolved = (
            resolution
            if isinstance(resolution, GoalAssociationResolution)
            else GoalAssociationResolution.model_validate(resolution)
        )
        active = {
            item["goal_id"]: item
            for item in self.active_goal_snapshots(limit=self.max_pending_tasks)
            if isinstance(item, dict) and item.get("goal_id")
        }
        operations: list[SemanticTaskOperation] = []
        results: list[dict[str, Any]] = []

        for ordinal, goal in enumerate(resolved.new_goals):
            operation_id = stable_goal_operation_id(
                turn_id=resolved.turn_id,
                ordinal=len(resolved.associations) + ordinal,
                relationship="new",
            )
            operations.append(
                SemanticTaskOperation(
                    operation_id=operation_id,
                    operation="create",
                    confidence=resolved.confidence,
                    relationship="new",
                    goal=goal,
                    requires_replan=True,
                    reason_summary=resolved.reason_summary,
                    metadata={
                        "goal_association_turn_id": resolved.turn_id,
                        "goal_association_authority": "applied_after_validation",
                    },
                )
            )

        relationship_map = {
            "modify": "modify",
            "clarify": "clarification_answer",
            "confirm": "confirm",
            "reject": "reject",
            "cancel": "cancel",
            "pause": "pause",
            "resume": "resume",
            "replace": "replace",
        }
        for association in resolved.associations:
            target_task_ids = [
                str(active[goal_id].get("source_task_id") or goal_id)
                for goal_id in association.target_goal_ids
                if goal_id in active
            ]
            if len(target_task_ids) != len(association.target_goal_ids):
                results.append(
                    {
                        "association_id": association.association_id,
                        "relationship": association.relationship,
                        "applied": False,
                        "reason": "unknown_target_goal",
                    }
                )
                continue
            if association.relationship in {"merge", "split"}:
                results.append(
                    {
                        "association_id": association.association_id,
                        "relationship": association.relationship,
                        "applied": False,
                        "reason": "multi_goal_transaction_not_implemented",
                    }
                )
                continue
            if association.relationship in {"continue", "reference"}:
                for task_id in target_task_ids:
                    context = self._task_context_by_id(task_id)
                    if context is None:
                        continue
                    metadata = context.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                    context["metadata"] = {
                        **metadata,
                        "goal_association_id": association.association_id,
                        "goal_relationship": association.relationship,
                        "goal_association_confidence": association.confidence,
                        "goal_association_reason": association.reason_summary,
                    }
                    context["last_meaningful_user_turn"] = self._compact_text(
                        user_text, limit=220
                    )
                    context["updated_ms"] = _now_ms()
                    if sid:
                        related = context.get("related_sids")
                        if not isinstance(related, list):
                            related = []
                        if sid not in related:
                            related.append(sid)
                        context["related_sids"] = related[-12:]
                    results.append(
                        {
                            "association_id": association.association_id,
                            "relationship": association.relationship,
                            "task_id": task_id,
                            "applied": True,
                            "state_change": "continuity_marker",
                        }
                    )
                continue

            operation_name = relationship_map.get(association.relationship)
            if operation_name is None:
                results.append(
                    {
                        "association_id": association.association_id,
                        "relationship": association.relationship,
                        "applied": False,
                        "reason": "unsupported_relationship",
                    }
                )
                continue
            if operation_name in {
                "modify",
                "clarification_answer",
                "replace",
            } and not (association.goal_update or association.resolved_gap_ids):
                results.append(
                    {
                        "association_id": association.association_id,
                        "relationship": association.relationship,
                        "applied": False,
                        "reason": "semantic_delta_required",
                    }
                )
                continue
            operations.append(
                SemanticTaskOperation(
                    operation_id=association.association_id,
                    operation=operation_name,
                    target_task_ids=target_task_ids,
                    confidence=association.confidence,
                    relationship=association.relationship,
                    goal_update=association.goal_update,
                    resolved_gap_ids=association.resolved_gap_ids,
                    requires_replan=association.requires_replan,
                    reason_summary=association.reason_summary,
                    metadata={
                        "goal_association_turn_id": resolved.turn_id,
                        "goal_association_authority": "applied_after_validation",
                    },
                )
            )

        if operations:
            results.extend(
                self.apply_semantic_task_operations(
                    operations,
                    sid=sid,
                    user_text=user_text,
                    route=route,
                    intent=intent,
                    source=source,
                    persist=False,
                )
            )
        return results

    def apply_semantic_task_operations(
        self,
        operations: list[SemanticTaskOperation] | list[dict[str, Any]],
        *,
        sid: str | None,
        user_text: str,
        route: str | None = None,
        intent: str | None = None,
        source: str | None = None,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        validated: list[SemanticTaskOperation] = []
        for item in operations:
            if isinstance(item, SemanticTaskOperation):
                validated.append(item)
            elif isinstance(item, dict):
                try:
                    validated.append(SemanticTaskOperation.model_validate(item))
                except Exception:
                    continue
        results: list[dict[str, Any]] = []
        for operation in validated:
            if operation.operation == "create":
                existing = self._context_by_operation_id(operation.operation_id)
                if existing is not None:
                    results.append(
                        {
                            "operation_id": operation.operation_id,
                            "operation": operation.operation,
                            "task_id": existing.get("task_id"),
                            "applied": False,
                            "replayed": True,
                            "reason": "operation_already_applied",
                            "goal_version": int(existing.get("goal_version") or 1),
                            "plan_version": int(existing.get("plan_version") or 0),
                            "status": existing.get("status"),
                        }
                    )
                    continue
                context = self._new_semantic_task_context(
                    sid=sid,
                    operation=operation,
                    user_text=user_text,
                    route=route,
                    intent=intent,
                    source=source,
                )
                results.append(
                    {
                        "operation_id": operation.operation_id,
                        "operation": operation.operation,
                        "task_id": context["task_id"],
                        "applied": True,
                        "goal_version": context["goal_version"],
                        "plan_version": context["plan_version"],
                        "status": context["status"],
                    }
                )
                continue
            for task_id in operation.target_task_ids:
                context = self._task_context_by_id(task_id)
                if context is None:
                    results.append(
                        {
                            "operation_id": operation.operation_id,
                            "operation": operation.operation,
                            "task_id": task_id,
                            "applied": False,
                            "reason": "unknown_task_id",
                        }
                    )
                    continue
                results.append(
                    self._apply_semantic_operation_to_context(
                        context,
                        operation,
                        sid=sid,
                        user_text=user_text,
                        route=route,
                        intent=intent,
                        source=source,
                    )
                )
        if results:
            if persist:
                self._persist_task_contexts_if_enabled()
            self.last_activity_ms = _now_ms()
        return results

    def apply_semantic_task_operations_atomically(
        self,
        operations: list[SemanticTaskOperation] | list[dict[str, Any]],
        *,
        sid: str | None,
        user_text: str,
        route: str | None = None,
        intent: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Apply a semantic-operation batch as one in-memory/durable transaction.

        The full batch is validated before mutation. Any state-level rejection
        rolls back all earlier operations, and durable state is written only once
        after the complete batch succeeds. Existing idempotent replays remain
        accepted.
        """
        if not self.enabled:
            return []

        validated: list[SemanticTaskOperation] = []
        for index, item in enumerate(operations):
            try:
                validated.append(
                    item
                    if isinstance(item, SemanticTaskOperation)
                    else SemanticTaskOperation.model_validate(item)
                )
            except Exception as exc:
                raise ValueError(
                    f"invalid semantic operation at batch index {index}: {exc}"
                ) from exc

        return self._commit_semantic_state_transaction(
            lambda: self.apply_semantic_task_operations(
                validated,
                sid=sid,
                user_text=user_text,
                route=route,
                intent=intent,
                source=source,
                persist=False,
            )
        )

    def _looks_like_meaningful_task_text(self, text: str | None) -> bool:
        normalized = self._normalized(text)
        if not normalized:
            return False
        if len(normalized) <= 2:
            return False
        if normalized in {"ok", "okay", "done", "then", "or", "and", "the", "um", "uh"}:
            return False
        words = normalized.split()
        if len(words) <= 2 and normalized.endswith((",", ";", ":")):
            return False
        return True

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text:
                out.append(text)
        return out

    def _merge_string_list(self, current: Any, new_items: Any, *, max_items: int = 8) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*self._string_list(current), *self._string_list(new_items)]:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(self._compact_text(item, limit=180))
        return merged[-max_items:]

    @staticmethod
    def _task_patch_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        patch = metadata.get("task_context_patch") or metadata.get("task_context")
        return patch if isinstance(patch, dict) else {}

    @staticmethod
    def _task_relation_from_metadata(metadata: dict[str, Any] | None) -> str | None:
        if not isinstance(metadata, dict):
            return None
        relation = str(metadata.get("task_relation") or "").strip()
        return relation if relation in _TASK_RELATIONS else None

    def _default_task_type(self, route: str | None, intent: str | None) -> str:
        route = str(route or "chat").strip() or "chat"
        intent = str(intent or "").strip()
        if route == "robot_action":
            return "robot_action"
        if route in {"tool", "memory", "deep_thought"}:
            return route
        if intent:
            return intent
        return "conversation"

    def _infer_task_relation(
        self,
        text: str,
        *,
        route: str | None,
        metadata: dict[str, Any] | None,
    ) -> str | None:
        """Compatibility relation inference without semantic phrase matching.

        Normal task continuation and modification must arrive as structured model
        output. This fallback only opens a task for an explicitly effectful route
        or records a side conversation; it never binds a follow-up to an existing
        task through keywords, regexes, pronouns, or recency.
        """

        relation = self._task_relation_from_metadata(metadata)
        if relation:
            return relation
        if not self._looks_like_meaningful_task_text(text):
            return None
        route = str(route or "").strip()
        if route in {"robot_action", "tool", "memory", "deep_thought"}:
            return "new_task"
        return None

    def _record_task_context_from_user_turn(
        self,
        *,
        sid: str | None,
        text: str,
        route: str | None,
        intent: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        if not self.enabled or route == "ignore":
            return
        relation = self._infer_task_relation(text, route=route, metadata=metadata)
        if relation is None:
            return

        patch = self._task_patch_from_metadata(metadata)
        target_task_id = str((metadata or {}).get("target_task_id") or patch.get("task_id") or "").strip()
        context = self._task_context_by_id(target_task_id)
        if context is None and relation in {"continue_task", "modify_task", "close_task", "clarify_task"}:
            context = self._current_task_context()
        if context is None and relation in {"continue_task", "modify_task", "close_task", "clarify_task"}:
            return

        if context is None or relation in {"new_task", "side_conversation"}:
            task_id = target_task_id or self._new_task_id()
            now = _now_ms()
            context = {
                "task_id": task_id,
                "conversation_id": self.conversation_id,
                "status": "open",
                "task_relation": relation,
                "task_type": str(patch.get("task_type") or self._default_task_type(route, intent)),
                "goal": self._compact_text(str(patch.get("goal") or text), limit=220),
                "semantic_goal": SemanticGoal(
                    goal_id=task_id,
                    version=1,
                    description=self._compact_text(str(patch.get("goal") or text), limit=220),
                    source_text=self._compact_text(text, limit=220),
                    constraints=(
                        dict(patch.get("constraints"))
                        if isinstance(patch.get("constraints"), dict)
                        else {}
                    ),
                ).model_dump(mode="json", exclude_none=True),
                "goal_version": 1,
                "plan_version": 0,
                "plan_status": "not_planned",
                "commitment_state": "evaluating",
                "open_information_gaps": [],
                "operation_history": [],
                "confirmation": None,
                "evidence_summary": {},
                "important_claims": [],
                "entities": [],
                "constraints": {},
                "pending_questions": [],
                "last_meaningful_user_turn": None,
                "last_assistant_response": None,
                "related_sids": [],
                "created_ms": now,
                "updated_ms": now,
                "persistence_policy": str(
                    patch.get("persistence_policy") or "persist_if_unfinished"
                ),
                "metadata": {},
            }
            self._task_contexts.append(context)

        now = _now_ms()
        context["task_relation"] = relation
        context["updated_ms"] = now
        context["last_meaningful_user_turn"] = self._compact_text(text, limit=220)
        context["task_type"] = str(patch.get("task_type") or context.get("task_type") or self._default_task_type(route, intent))
        if patch.get("goal"):
            context["goal"] = self._compact_text(str(patch.get("goal")), limit=220)
        legacy_goal = self._semantic_goal_from_context(context)
        context["important_claims"] = self._merge_string_list(
            context.get("important_claims"),
            patch.get("important_claims") or patch.get("claims"),
        )
        if not context["important_claims"] and route == "chat":
            context["important_claims"] = [self._compact_text(text, limit=180)]
        context["entities"] = self._merge_string_list(context.get("entities"), patch.get("entities"))
        context["pending_questions"] = self._merge_string_list(
            context.get("pending_questions"),
            patch.get("pending_questions") or patch.get("questions"),
            max_items=4,
        )
        constraints = context.get("constraints")
        if not isinstance(constraints, dict):
            constraints = {}
        patch_constraints = patch.get("constraints")
        if isinstance(patch_constraints, dict):
            constraints = {**constraints, **patch_constraints}
        context["constraints"] = constraints
        legacy_goal = legacy_goal.model_copy(
            update={
                "description": str(context.get("goal") or legacy_goal.description),
                "source_text": self._compact_text(text, limit=220),
                "constraints": dict(constraints),
            }
        )
        context["semantic_goal"] = legacy_goal.model_dump(mode="json", exclude_none=True)
        context["goal_version"] = max(1, int(context.get("goal_version") or legacy_goal.version or 1))
        related_sids = context.get("related_sids")
        if not isinstance(related_sids, list):
            related_sids = []
        if sid and sid not in related_sids:
            related_sids.append(sid)
        context["related_sids"] = related_sids[-12:]
        meta = context.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        context["metadata"] = {
            **meta,
            "last_route": route,
            "last_intent": intent,
            "source": (metadata or {}).get("source"),
            "confidence": (metadata or {}).get("confidence"),
        }
        if relation == "close_task":
            context["status"] = str(patch.get("status") or "done")
        self._persist_task_contexts_if_enabled()

    def _prune_completed_tasks(self, now_ms: float | None = None) -> None:
        if not self._pending_tasks:
            return
        now = now_ms if now_ms is not None else _now_ms()
        retained: list[dict[str, Any]] = []
        changed = False
        for task in self._pending_tasks:
            status = str(task.get("status") or "pending").lower()
            if status in _DONE_TASK_STATUSES:
                updated_ms = task.get("updated_ms") or task.get("ts_ms") or now
                try:
                    age_sec = (now - float(updated_ms)) / 1000.0
                except (TypeError, ValueError):
                    age_sec = 0.0
                if age_sec >= self.completed_task_retention_sec:
                    changed = True
                    continue
            retained.append(task)
        if changed:
            self._pending_tasks = deque(retained, maxlen=max(1, self.max_pending_tasks))

    def _contains_phrase(self, text: str, phrases: tuple[str, ...]) -> bool:
        if not text:
            return False
        padded = f" {text} "
        for phrase in phrases:
            phrase = phrase.strip().lower()
            if not phrase:
                continue
            # Chinese phrases and multi-word English phrases are safest with substring matching.
            if re.search(r"[\u4e00-\u9fff]", phrase) or " " in phrase:
                if phrase in text:
                    return True
            elif f" {phrase} " in padded or text == phrase:
                return True
        return False

    def is_explicit_reset(self, text: str | None) -> bool:
        # Conversation reset is an operational control, so require one explicit
        # whole-utterance command. Goal cancellation, replacement, and phrases
        # such as “never mind” or “算了” are semantic and must be resolved by
        # Goal Association rather than clearing every active goal here.
        normalized = self._normalized(text).strip(" \t\r\n.,!?;:，。！？；：")
        return normalized in {
            phrase.strip().lower().strip(" \t\r\n.,!?;:，。！？；：")
            for phrase in self.reset_phrases
            if phrase.strip()
        }

    def is_followup_reference(self, text: str | None) -> bool:
        normalized = self._normalized(text)
        if not normalized:
            return False
        if self._contains_phrase(normalized, self.followup_phrases):
            return True
        # Very short pronoun-like turns are usually context-dependent.
        return normalized in {"it", "that", "this", "him", "her", "them", "那个", "这个", "它", "他", "她"}

    def is_new_topic_like(self, text: str | None) -> bool:
        normalized = self._normalized(text)
        if not normalized:
            return False
        return any(normalized.startswith(prefix) for prefix in self.new_topic_starters)

    def start_new_conversation(self, *, reason: str, sid: str | None = None) -> dict[str, Any]:
        self._conversation_seq += 1
        self.conversation_id = f"{self.base_conversation_id}-{self._conversation_seq:04d}"
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns.clear()
        self._pending_tasks.clear()
        self._task_contexts.clear()
        self._memory_store.clear()
        self._persist_task_contexts_if_enabled()
        self.last_split_reason = reason
        return {
            "started_new": True,
            "reason": reason,
            "conversation_id": self.conversation_id,
            "sid": sid,
        }

    def prepare_for_user_text(self, text: str | None, sid: str | None = None) -> dict[str, Any]:
        """Decide whether this user turn starts a new conversation.

        This does not record the current user text. It only performs boundary
        detection so the context snapshot sent to router/agent contains previous
        turns from the correct conversation, not the current turn duplicated.
        """
        if not self.enabled:
            return {"started_new": False, "reason": "disabled", "conversation_id": self.conversation_id, "sid": sid}

        now = _now_ms()
        self._prune_completed_tasks(now)
        idle_sec = (now - self.last_activity_ms) / 1000.0
        normalized = self._normalized(text)

        if self.is_explicit_reset(normalized):
            return self.start_new_conversation(reason="explicit_reset", sid=sid)

        if self._active_pending_tasks():
            self.last_split_reason = "kept_active_pending_task"
            return {"started_new": False, "reason": "active_pending_task", "conversation_id": self.conversation_id, "sid": sid}

        # A goal waiting for clarification, confirmation, provider recovery, or
        # later continuation is still active even when it has no current Skill
        # Runtime request. Conversation-boundary heuristics must not discard it.
        if self._active_task_contexts():
            self.last_split_reason = "kept_active_goal"
            return {
                "started_new": False,
                "reason": "active_goal",
                "conversation_id": self.conversation_id,
                "sid": sid,
            }

        if self._has_any_context() and idle_sec >= self.hard_idle_timeout_sec:
            return self.start_new_conversation(reason="hard_idle_timeout", sid=sid)

        if self.is_followup_reference(normalized):
            self.last_split_reason = "kept_followup_reference"
            return {"started_new": False, "reason": "followup_reference", "conversation_id": self.conversation_id, "sid": sid}

        if self._has_any_context() and idle_sec >= self.soft_idle_timeout_sec and self.is_new_topic_like(normalized):
            return self.start_new_conversation(reason="soft_idle_new_topic", sid=sid)

        self.last_split_reason = "kept_default"
        return {"started_new": False, "reason": "kept_default", "conversation_id": self.conversation_id, "sid": sid}

    def get_history(self) -> list[dict[str, Any]]:
        if not self.enabled or self.max_turns <= 0:
            return []
        turns = list(self._turns)[-self.max_turns :]
        # Keep the context prompt bounded. Prefer newest turns.
        selected: list[dict[str, Any]] = []
        total_chars = 0
        for turn in reversed(turns):
            text = str(turn.get("text") or "")
            if selected and total_chars + len(text) > self.max_context_chars:
                break
            total_chars += len(text)
            selected.append(turn)
        return list(reversed(selected))

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        if not self.enabled or self.max_pending_tasks <= 0:
            return []
        self._prune_completed_tasks()
        return list(self._pending_tasks)[-self.max_pending_tasks :]

    def _latest_turn(self, role: str) -> dict[str, Any] | None:
        for turn in reversed(self._turns):
            if str(turn.get("role") or "").lower() == role:
                return turn
        return None

    def session_memory(self) -> dict[str, Any]:
        active_tasks = self._active_pending_tasks()
        active_task_contexts = self._active_task_contexts()
        current_task_context = self._current_task_context()
        latest_user = self._latest_turn("user")
        latest_assistant = self._latest_turn("assistant")
        extracted_memory = self._memory_prompt_builder.build(self._memory_store)
        summaries = [
            str(task.get("summary") or task.get("type") or "task")
            for task in active_tasks[-4:]
        ]
        current_task = None
        if summaries:
            current_task = {
                "status": "active",
                "summary": "; ".join(summaries),
                "tasks": active_tasks[-4:],
            }
        elif current_task_context:
            current_task = {
                "status": current_task_context.get("status") or "open",
                "summary": current_task_context.get("goal") or current_task_context.get("task_type") or "task",
                "task_context": current_task_context,
            }
        return {
            "kind": "short_term_session_memory",
            "conversation_id": self.conversation_id,
            "recent_user_request": latest_user.get("text") if latest_user else None,
            "recent_assistant_response": latest_assistant.get("text") if latest_assistant else None,
            "current_task": current_task,
            "current_task_context": current_task_context,
            "active_task_contexts": active_task_contexts[-4:],
            "active_task_snapshots": self.active_task_snapshots(limit=4),
            "active_pending_tasks": active_tasks[-4:],
            "extracted_memory": extracted_memory["entries"],
            "memory_summary": extracted_memory["summary"],
            "forgetting_policy": {
                "explicit_reset_clears_history_and_tasks": True,
                "hard_idle_timeout_sec": self.hard_idle_timeout_sec,
                "soft_idle_new_topic_timeout_sec": self.soft_idle_timeout_sec,
                "completed_task_retention_sec": self.completed_task_retention_sec,
                "last_split_reason": self.last_split_reason,
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "conversation_id": self.conversation_id,
            "base_conversation_id": self.base_conversation_id,
            "started_ms": self.started_ms,
            "last_activity_ms": self.last_activity_ms,
            "last_split_reason": self.last_split_reason,
            "history": self.get_history(),
            "pending_tasks": self.get_pending_tasks(),
            "active_pending_tasks": self._active_pending_tasks(),
            "task_contexts": list(self._task_contexts),
            "active_task_contexts": self._active_task_contexts(),
            "active_task_snapshots": self.active_task_snapshots(),
            "current_task_context": self._current_task_context(),
            "extracted_memory": self._memory_store.snapshot(),
            "session_memory": self.session_memory(),
            "task_store": {
                "enabled": self.task_store_enabled,
                "path": str(self.task_store_path),
                "last_error": self.last_task_store_error,
            },
            "limits": {
                "max_turns": self.max_turns,
                "max_context_chars": self.max_context_chars,
                "soft_idle_timeout_sec": self.soft_idle_timeout_sec,
                "hard_idle_timeout_sec": self.hard_idle_timeout_sec,
                "max_memory_entries": self.max_memory_entries,
                "completed_task_retention_sec": self.completed_task_retention_sec,
            },
        }

    def clear(self, *, reason: str = "manual_clear") -> None:
        self.start_new_conversation(reason=reason)

    def record_user_turn(
        self,
        sid: str | None,
        text: str | None,
        *,
        route: str | None = None,
        intent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        compact = self._compact_text(text)
        if not compact:
            return
        turn_metadata = dict(metadata or {})
        semantic_operations = self._semantic_operations_from_metadata(turn_metadata)
        semantic_resolution_authoritative = bool(
            turn_metadata.get("semantic_task_resolution_authoritative")
        )
        if semantic_operations:
            operation_results = self.apply_semantic_task_operations(
                semantic_operations,
                sid=sid,
                user_text=compact,
                route=route,
                intent=intent,
                source=str(turn_metadata.get("source") or "router"),
            )
            turn_metadata["semantic_task_operation_results"] = operation_results
        self._turns.append(
            {
                "role": "user",
                "sid": sid,
                "text": compact,
                "route": route,
                "intent": intent,
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": turn_metadata,
            }
        )
        if not semantic_operations and not semantic_resolution_authoritative:
            self._record_task_context_from_user_turn(
                sid=sid,
                text=compact,
                route=route,
                intent=intent,
                metadata=turn_metadata,
            )
        self._memory_store.add_many(
            self._memory_extractor.extract_user_turn(
                sid=sid,
                text=compact,
                route=route,
                metadata=turn_metadata,
                task_context=self._current_task_context(),
            )
        )
        self.last_activity_ms = _now_ms()

    def record_assistant_turn(
        self,
        sid: str | None,
        text: str | None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        compact = self._compact_text(text)
        if not compact:
            return
        self._turns.append(
            {
                "role": "assistant",
                "sid": sid,
                "text": compact,
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": metadata or {},
            }
        )
        current_task = self._current_task_context()
        if current_task is not None:
            current_task["last_assistant_response"] = compact
            current_task["updated_ms"] = _now_ms()
            self._persist_task_contexts_if_enabled()
        self.last_activity_ms = _now_ms()

    @staticmethod
    def _canonical_goal_outcomes(
        metadata: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        """Return goal-keyed outcomes from a trusted canonical-plan envelope."""

        if not isinstance(metadata, dict):
            return {}
        plan = metadata.get("canonical_plan")
        if not isinstance(plan, dict):
            return {}
        raw_outcomes = plan.get("goal_outcomes")
        outcomes: dict[str, dict[str, Any]] = {}
        if isinstance(raw_outcomes, dict):
            iterable = []
            for goal_id, value in raw_outcomes.items():
                if isinstance(value, dict):
                    iterable.append({"goal_id": goal_id, **value})
        elif isinstance(raw_outcomes, list):
            iterable = [item for item in raw_outcomes if isinstance(item, dict)]
        else:
            iterable = []
        for item in iterable:
            goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
            disposition = str(item.get("disposition") or "").strip().lower()
            if goal_id and disposition:
                outcomes[goal_id] = dict(item)

        # Single-disposition plans may omit per-goal outcomes. Preserve their
        # exact structured disposition without inferring anything from speech.
        if not outcomes:
            disposition = str(plan.get("disposition") or "").strip().lower()
            goal_ids = plan.get("goal_ids")
            if isinstance(goal_ids, str):
                goal_ids = [goal_ids]
            if disposition and isinstance(goal_ids, list):
                for value in goal_ids:
                    goal_id = " ".join(str(value or "").strip().split())
                    if goal_id:
                        outcomes[goal_id] = {
                            "goal_id": goal_id,
                            "disposition": disposition,
                        }
        return outcomes

    @staticmethod
    def _commitment_state_for_status(status: str) -> str:
        return {
            "awaiting_confirmation": "waiting_for_user",
            "scheduled": "accepted",
            "running": "executing",
            "done": "completed",
            "failed": "failed",
            "refused": "failed",
            "timed_out": "failed",
            "cancelled": "cancelled",
        }.get(status, "evaluating")

    def _record_nonexecuting_goal_outcomes(
        self,
        outcomes: dict[str, dict[str, Any]],
    ) -> None:
        """Apply deterministic non-execution lifecycle outcomes per goal.

        A clarification remains active and waits for the user.  Refusal and
        unavailability are terminal planning outcomes.  Respond outcomes are
        deliberately left for speech-request evidence, while execute outcomes
        are left for their goal-scoped SkillRequest evidence.
        """

        changed = False
        now = _now_ms()
        for goal_id, outcome in outcomes.items():
            disposition = str(outcome.get("disposition") or "").strip().lower()
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                continue
            item_changed = False
            if disposition == "clarify":
                context["status"] = "waiting_for_user"
                context["commitment_state"] = "waiting_for_user"
                context["plan_status"] = "blocked_on_user"
                unresolved = outcome.get("unresolved")
                if isinstance(unresolved, str):
                    unresolved = [unresolved]
                if isinstance(unresolved, list):
                    context["pending_questions"] = [
                        self._compact_text(str(item), limit=220)
                        for item in unresolved
                        if str(item).strip()
                    ][:4]
                item_changed = True
            elif disposition in {"unavailable", "refused"}:
                context["status"] = "refused"
                context["commitment_state"] = "failed"
                context["plan_status"] = disposition
                item_changed = True
            if item_changed:
                context["updated_ms"] = now
                changed = True
        if changed:
            self._persist_task_contexts_if_enabled()

    def _record_goal_pending_execution(
        self,
        *,
        sid: str | None,
        goal_id: str,
        status: str,
        summary: str,
        request_ids: list[str],
        planning_result: str,
        planned_skills: list[dict[str, Any]],
        confirmation_pending: bool,
        interaction_id: str = "",
        turn_id: str = "",
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
    ) -> None:
        """Track execution lifecycle for one semantic goal only.

        Multi-goal plans must not attach every provider request to whichever goal
        happens to be last in the deque. Auxiliary social-attention requests are
        intentionally omitted by the caller.
        """

        if not self.enabled or not goal_id or not request_ids:
            return
        timestamp_ms = _now_ms()
        metadata = {
            "goal_id": goal_id,
            "request_ids": list(request_ids),
            "remaining_request_ids": list(request_ids),
            "request_statuses": {},
            "planning_result": planning_result,
            "confirmation_pending": confirmation_pending,
            "planned_skills": [dict(item) for item in planned_skills],
            "interaction_id": str(interaction_id or "").strip(),
            "turn_id": str(turn_id or "").strip(),
            "canonical_plan_id": str(canonical_plan_id or "").strip(),
            "canonical_plan_fingerprint": str(
                canonical_plan_fingerprint or ""
            ).strip(),
        }
        self._pending_tasks.append(
            {
                "sid": sid,
                "type": "goal_execution",
                "status": status,
                "summary": self._compact_text(summary or goal_id),
                "ts_ms": timestamp_ms,
                "updated_ms": timestamp_ms,
                "conversation_id": self.conversation_id,
                "metadata": metadata,
            }
        )
        context = self._task_context_by_goal_id(goal_id)
        if context is not None:
            context["status"] = status
            context["commitment_state"] = self._commitment_state_for_status(status)
            context["updated_ms"] = timestamp_ms
            current_metadata = context.get("metadata")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            context["metadata"] = {**current_metadata, **metadata}
            self._persist_task_contexts_if_enabled()
        self.last_activity_ms = timestamp_ms

    def record_confirmation_scope(
        self,
        *,
        sid: str | None,
        confirmation_id: str,
        interaction_id: str,
        fingerprint: str,
        expires_at: float,
        response: Any,
        confirmed_request_ids: set[str],
    ) -> list[str]:
        """Bind a staged confirmation to every semantic goal it covers.

        A confirmation is a user-decision boundary, not runtime execution
        evidence.  Its request IDs are therefore retained for auditability but
        are deliberately stored in ``goal_confirmation`` records instead of
        ``goal_execution`` records.  Only the post-approval Agent result may
        schedule those requests.
        """

        if not self.enabled or self.max_pending_tasks <= 0:
            return []
        if hasattr(response, "model_dump"):
            data = response.model_dump(mode="json")
        elif isinstance(response, dict):
            data = response
        else:
            data = {}

        confirmed = {
            str(request_id).strip()
            for request_id in confirmed_request_ids
            if str(request_id).strip()
        }
        by_goal: dict[str, list[dict[str, str]]] = {}
        scoped_request_ids: set[str] = set()
        for raw_request in data.get("skills", []) or data.get("actions", []) or []:
            if isinstance(raw_request, dict):
                request = raw_request
            else:
                request = {
                    "request_id": getattr(raw_request, "request_id", None),
                    "skill_id": getattr(raw_request, "skill_id", None),
                    "metadata": getattr(raw_request, "metadata", None),
                }
            request_id = str(request.get("request_id") or "").strip()
            if not request_id or request_id not in confirmed:
                continue
            metadata = request.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            skill_id = str(
                request.get("skill_id")
                or request.get("type")
                or request.get("target")
                or "action"
            ).strip()
            for goal_id in self._string_list(metadata.get("source_goal_ids")):
                by_goal.setdefault(goal_id, []).append(
                    {"request_id": request_id, "skill_id": skill_id}
                )
                scoped_request_ids.add(request_id)

        timestamp_ms = _now_ms()
        goal_ids: list[str] = []
        for goal_id, requests in by_goal.items():
            request_ids = list(
                dict.fromkeys(item["request_id"] for item in requests)
            )
            summary = ", ".join(
                dict.fromkeys(item["skill_id"] for item in requests)
            )
            metadata = {
                "confirmation_id": confirmation_id,
                "interaction_id": interaction_id,
                "fingerprint": fingerprint,
                "expires_at": expires_at,
                "goal_id": goal_id,
                "request_ids": request_ids,
                "confirmation_request_ids": request_ids,
            }
            self._pending_tasks.append(
                {
                    "sid": sid,
                    "type": "goal_confirmation",
                    "status": "awaiting_confirmation",
                    "summary": self._compact_text(summary or goal_id),
                    "ts_ms": timestamp_ms,
                    "updated_ms": timestamp_ms,
                    "conversation_id": self.conversation_id,
                    "metadata": metadata,
                }
            )
            goal_ids.append(goal_id)
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                continue
            context["status"] = "awaiting_confirmation"
            context["commitment_state"] = "waiting_for_user"
            context["plan_status"] = "awaiting_confirmation"
            context["confirmation"] = {
                "status": "pending",
                "confirmation_id": confirmation_id,
                "fingerprint": fingerprint,
                "expires_at": expires_at,
                "request_ids": request_ids,
            }
            context["updated_ms"] = timestamp_ms
            current_metadata = context.get("metadata")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            context["metadata"] = {
                **current_metadata,
                "confirmation_id": confirmation_id,
                "confirmation_request_ids": request_ids,
            }

        # Keep request-bound evidence even for legacy/unscoped requests, but do
        # not mutate whichever task context happens to be current.
        unscoped_request_ids = sorted(confirmed - scoped_request_ids)
        if unscoped_request_ids:
            self._pending_tasks.append(
                {
                    "sid": sid,
                    "type": "confirmation",
                    "status": "awaiting_confirmation",
                    "summary": "confirmation",
                    "ts_ms": timestamp_ms,
                    "updated_ms": timestamp_ms,
                    "conversation_id": self.conversation_id,
                    "metadata": {
                        "confirmation_id": confirmation_id,
                        "interaction_id": interaction_id,
                        "fingerprint": fingerprint,
                        "expires_at": expires_at,
                        "request_ids": unscoped_request_ids,
                        "confirmation_request_ids": unscoped_request_ids,
                    },
                }
            )

        if goal_ids:
            self._persist_task_contexts_if_enabled()
        self.last_activity_ms = timestamp_ms
        return goal_ids

    def resolve_confirmation_scope(
        self,
        *,
        confirmation_id: str,
        decision: str,
    ) -> bool:
        """Resolve all pending records and goals bound to one confirmation."""

        if not self.enabled or not confirmation_id:
            return False
        normalized_decision = str(decision or "").strip().lower()
        final_status = {
            "approved": "done",
            "denied": "cancelled",
            "ambiguous": "refused",
            "expired": "timed_out",
            "operational_interrupt": "cancelled",
        }.get(normalized_decision, "cancelled")
        matched = False
        changed_context = False
        timestamp_ms = _now_ms()
        for task in self._pending_tasks:
            metadata = task.get("metadata")
            if not isinstance(metadata, dict):
                continue
            if metadata.get("confirmation_id") != confirmation_id:
                continue
            matched = True
            task["status"] = final_status
            task["updated_ms"] = timestamp_ms
            goal_id = str(metadata.get("goal_id") or "").strip()
            if not goal_id:
                continue
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                continue
            if normalized_decision == "approved":
                # Approval commits the plan but does not claim that Skill
                # Runtime has scheduled it. record_agent_result performs that
                # transition immediately before the authorized launch.
                context["status"] = "planning"
                context["commitment_state"] = "accepted"
                context["plan_status"] = "confirmed"
            else:
                context["status"] = final_status
                context["commitment_state"] = self._commitment_state_for_status(
                    final_status
                )
                context["plan_status"] = final_status
            confirmation = context.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            context["confirmation"] = {
                **confirmation,
                "status": normalized_decision or final_status,
                "resolved_ms": timestamp_ms,
            }
            context["updated_ms"] = timestamp_ms
            changed_context = True

        if changed_context:
            self._persist_task_contexts_if_enabled()
        if matched:
            self.last_activity_ms = timestamp_ms
        return matched

    def record_pending_task(
        self,
        *,
        sid: str | None,
        task_type: str,
        status: str = "pending",
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled or self.max_pending_tasks <= 0:
            return
        task_type = (task_type or "unknown").strip() or "unknown"
        timestamp_ms = _now_ms()
        self._pending_tasks.append(
            {
                "sid": sid,
                "type": task_type,
                "status": status or "pending",
                "summary": self._compact_text(summary or task_type),
                "ts_ms": timestamp_ms,
                "updated_ms": timestamp_ms,
                "conversation_id": self.conversation_id,
                "metadata": metadata or {},
            }
        )
        current_task = self._current_task_context()
        if current_task is not None:
            current_task["status"] = status or "pending"
            current_task["updated_ms"] = timestamp_ms
            meta = current_task.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
            current_task["metadata"] = {
                **meta,
                "pending_task_type": task_type,
                **(metadata or {}),
            }
            self._persist_task_contexts_if_enabled()
        self.last_activity_ms = _now_ms()

    def update_pending_task_status(
        self,
        *,
        metadata_key: str,
        metadata_value: Any,
        status: str,
    ) -> bool:
        if not self.enabled:
            return False
        for task in reversed(self._pending_tasks):
            metadata = task.get("metadata")
            if not isinstance(metadata, dict):
                continue
            if metadata.get(metadata_key) != metadata_value:
                continue
            task["status"] = status
            task["updated_ms"] = _now_ms()
            current_task = self._current_task_context()
            if current_task is not None:
                current_task["status"] = status
                current_task["updated_ms"] = task["updated_ms"]
                self._persist_task_contexts_if_enabled()
            self.last_activity_ms = _now_ms()
            return True
        return False

    def update_pending_task_status_for_request_id(
        self,
        *,
        request_id: str | None,
        status: str,
    ) -> bool:
        if not self.enabled or not request_id:
            return False
        normalized_status = str(status or "done").lower()
        final_status = {
            "completed": "done",
            "success": "done",
            "ok": "done",
            "cancelled": "cancelled",
            "canceled": "cancelled",
            "expired": "timed_out",
            "timed_out": "timed_out",
            "refused": "refused",
            "failed": "failed",
            "error": "failed",
            "partial": "failed",
            "not_run": "failed",
        }.get(normalized_status, normalized_status)
        matched = False
        for task in list(self._pending_tasks):
            if task.get("type") in {"confirmation", "goal_confirmation"}:
                # A confirmation record is decision evidence only. Runtime
                # results belong to the execution record created after
                # approval, even though both retain the same request IDs.
                continue
            metadata = task.get("metadata")
            if not isinstance(metadata, dict):
                continue
            request_ids = metadata.get("request_ids")
            if isinstance(request_ids, str):
                request_ids = [request_ids]
            if not isinstance(request_ids, list) or request_id not in request_ids:
                continue
            matched = True
            statuses = metadata.setdefault("request_statuses", {})
            if not isinstance(statuses, dict):
                statuses = {}
                metadata["request_statuses"] = statuses
            statuses[request_id] = final_status
            remaining = metadata.get("remaining_request_ids")
            if isinstance(remaining, str):
                remaining = [remaining]
            if not isinstance(remaining, list):
                remaining = list(request_ids)
            remaining = [item for item in remaining if item != request_id]
            metadata["remaining_request_ids"] = remaining
            if remaining:
                task_status = "running"
            else:
                values = list(statuses.values())
                if "failed" in values:
                    task_status = "failed"
                elif "refused" in values:
                    task_status = "refused"
                elif "cancelled" in values:
                    task_status = "cancelled"
                elif "timed_out" in values:
                    task_status = "timed_out"
                else:
                    task_status = "done"
            task["status"] = task_status
            task["updated_ms"] = _now_ms()

            goal_id = str(metadata.get("goal_id") or "").strip()
            contexts: list[dict[str, Any]] = []
            if goal_id:
                context = self._task_context_by_goal_id(goal_id)
                if context is not None:
                    contexts.append(context)
            else:
                for context in self._task_contexts:
                    context_metadata = context.get("metadata")
                    if not isinstance(context_metadata, dict):
                        continue
                    context_request_ids = context_metadata.get("request_ids")
                    if isinstance(context_request_ids, str):
                        context_request_ids = [context_request_ids]
                    if isinstance(context_request_ids, list) and request_id in context_request_ids:
                        contexts.append(context)
            for context in contexts:
                context["status"] = task_status
                context["commitment_state"] = (
                    self._commitment_state_for_status(task_status)
                )
                if task_status in _DONE_TASK_STATUSES:
                    context["plan_status"] = task_status
                context["updated_ms"] = task["updated_ms"]
                context_metadata = context.get("metadata")
                if not isinstance(context_metadata, dict):
                    context_metadata = {}
                context["metadata"] = {
                    **context_metadata,
                    "request_statuses": dict(statuses),
                    "remaining_request_ids": list(remaining),
                }

            self._memory_store.add_many(
                self._memory_extractor.extract_task_outcome(
                    sid=str(task.get("sid") or ""),
                    summary=str(task.get("summary") or task.get("type") or "task"),
                    status=str(task_status),
                    trusted=True,
                )
            )
        if matched:
            self._persist_task_contexts_if_enabled()
            self.last_activity_ms = _now_ms()
        return matched

    def record_execution_outcome_bundle(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        """Atomically attach exact execution evidence to every affected goal.

        The existing task lifecycle uses a smaller legacy status vocabulary.
        Keep that projection for compatibility, but retain the exact
        ``GoalExecutionOutcome.status`` in each task context's evidence and
        metadata so partial and not-run results are never flattened in the
        authoritative cognitive record.
        """

        if not self.enabled:
            return []
        validated = ExecutionOutcomeBundle.model_validate(bundle)
        fingerprint = execution_outcome_fingerprint(validated)
        normalized_sid = str(sid or "").strip()
        evidence_request_ids_by_goal: dict[str, set[str]] = {}
        for evidence in validated.evidence:
            for goal_id in evidence.source_goal_ids:
                evidence_request_ids_by_goal.setdefault(goal_id, set()).add(
                    evidence.request_id
                )

        expected_binding = {
            "interaction_id": validated.interaction_id,
            "turn_id": validated.turn_id,
            "canonical_plan_id": validated.canonical_plan_id,
            "canonical_plan_fingerprint": (
                validated.canonical_plan_fingerprint
            ),
        }
        bound_records: dict[
            str,
            tuple[dict[str, Any], list[dict[str, Any]]],
        ] = {}
        for outcome in validated.goal_outcomes:
            context = self._task_context_by_goal_id(outcome.goal_id)
            if context is None:
                raise ValueError(
                    "execution outcome references a goal with no committed "
                    f"task context: {outcome.goal_id}"
                )
            context_metadata = context.get("metadata")
            if not isinstance(context_metadata, dict):
                raise ValueError(
                    "execution outcome goal has no committed plan binding: "
                    f"{outcome.goal_id}"
                )
            for key, expected in expected_binding.items():
                if str(context_metadata.get(key) or "").strip() != expected:
                    raise ValueError(
                        "execution outcome is stale or does not match the "
                        f"current goal binding: {outcome.goal_id}:{key}"
                    )

            expected_request_ids = evidence_request_ids_by_goal.get(
                outcome.goal_id,
                set(),
            )
            matches: list[dict[str, Any]] = []
            for task in self._pending_tasks:
                task_metadata = task.get("metadata")
                if (
                    task.get("type") != "goal_execution"
                    or not isinstance(task_metadata, dict)
                    or str(task_metadata.get("goal_id") or "").strip()
                    != outcome.goal_id
                ):
                    continue
                if normalized_sid and str(task.get("sid") or "").strip() != normalized_sid:
                    continue
                if any(
                    str(task_metadata.get(key) or "").strip() != expected
                    for key, expected in expected_binding.items()
                ):
                    continue
                request_ids = task_metadata.get("request_ids")
                if isinstance(request_ids, str):
                    request_ids = [request_ids]
                if not isinstance(request_ids, list):
                    continue
                if {
                    str(item).strip()
                    for item in request_ids
                    if str(item).strip()
                } != expected_request_ids:
                    continue
                matches.append(task)
            if len(matches) != 1:
                raise ValueError(
                    "execution outcome requires exactly one matching committed "
                    f"goal execution record: {outcome.goal_id}"
                )
            bound_records[outcome.goal_id] = (context, matches)

        pending_backup = copy.deepcopy(self._pending_tasks)
        contexts_backup = copy.deepcopy(self._task_contexts)
        timestamp_ms = _now_ms()
        status_projection = {
            "completed": "done",
            "partial": "failed",
            "failed": "failed",
            "refused": "refused",
            "timed_out": "timed_out",
            "cancelled": "cancelled",
            "not_run": "failed",
        }
        results: list[dict[str, Any]] = []
        try:
            for outcome in validated.goal_outcomes:
                context, matching_tasks = bound_records[outcome.goal_id]
                lifecycle_status = status_projection[outcome.status]
                evidence_summary = context.get("evidence_summary")
                if not isinstance(evidence_summary, dict):
                    evidence_summary = {}
                evidence_summary["execution_outcome"] = {
                    "outcome_id": validated.outcome_id,
                    "outcome_fingerprint": fingerprint,
                    "turn_id": validated.turn_id,
                    "interaction_id": validated.interaction_id,
                    "canonical_plan_id": validated.canonical_plan_id,
                    "canonical_plan_fingerprint": (
                        validated.canonical_plan_fingerprint
                    ),
                    "goal_id": outcome.goal_id,
                    "status": outcome.status,
                    "step_ids": list(outcome.step_ids),
                    "evidence_ids": list(outcome.evidence_ids),
                    "completed_step_ids": list(outcome.completed_step_ids),
                    "unresolved_step_ids": list(outcome.unresolved_step_ids),
                    "reason_codes": list(outcome.reason_codes),
                }
                context["evidence_summary"] = evidence_summary
                context["status"] = lifecycle_status
                context["commitment_state"] = (
                    self._commitment_state_for_status(lifecycle_status)
                )
                context["plan_status"] = lifecycle_status
                context["updated_ms"] = timestamp_ms
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                context["metadata"] = {
                    **metadata,
                    "execution_outcome_id": validated.outcome_id,
                    "execution_outcome_fingerprint": fingerprint,
                    "execution_outcome_status": outcome.status,
                    "execution_evidence_ids": list(outcome.evidence_ids),
                }

                matched_pending = 0
                for task in matching_tasks:
                    task_metadata = task.get("metadata")
                    assert isinstance(task_metadata, dict)
                    task["status"] = lifecycle_status
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **task_metadata,
                        "execution_outcome_id": validated.outcome_id,
                        "execution_outcome_fingerprint": fingerprint,
                        "execution_outcome_status": outcome.status,
                        "execution_evidence_ids": list(outcome.evidence_ids),
                    }
                    matched_pending += 1

                results.append(
                    {
                        "goal_id": outcome.goal_id,
                        "status": outcome.status,
                        "lifecycle_status": lifecycle_status,
                        "outcome_id": validated.outcome_id,
                        "applied": True,
                        "pending_records_updated": matched_pending,
                    }
                )
            self._persist_task_contexts_if_enabled()
        except Exception:
            self._pending_tasks = pending_backup
            self._task_contexts = contexts_backup
            raise
        self.last_activity_ms = timestamp_ms
        return results

    def _record_planning_metadata(
        self,
        metadata: dict[str, Any],
        *,
        confirmation_authorized: bool = False,
    ) -> None:
        planning_result = str(metadata.get("planning_result") or "").strip()
        if not planning_result:
            return
        task_id = str(metadata.get("task_id") or "").strip()
        context = self._task_context_by_id(task_id) if task_id else self._current_task_context()
        if context is None:
            return
        try:
            proposed_goal_version = int(metadata.get("goal_version") or context.get("goal_version") or 1)
        except (TypeError, ValueError):
            proposed_goal_version = 1
        current_goal_version = max(1, int(context.get("goal_version") or 1))
        if proposed_goal_version != current_goal_version:
            meta = context.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
            context["metadata"] = {
                **meta,
                "stale_planning_result_rejected": {
                    "planning_result": planning_result,
                    "proposed_goal_version": proposed_goal_version,
                    "current_goal_version": current_goal_version,
                    "ts_ms": _now_ms(),
                },
            }
            return

        raw_gaps = metadata.get("information_gaps")
        gaps: list[dict[str, Any]] = []
        if isinstance(raw_gaps, list):
            for item in raw_gaps:
                if not isinstance(item, dict):
                    continue
                try:
                    gap = InformationGap.model_validate(item)
                except Exception:
                    continue
                if not gap.resolved:
                    gaps.append(gap.model_dump(mode="json", exclude_none=True))

        if planning_result == "needs_clarification":
            context["status"] = "waiting_for_user"
            context["commitment_state"] = "waiting_for_user"
            context["plan_status"] = "blocked_on_user"
            context["open_information_gaps"] = gaps
            context["pending_questions"] = [
                str(item.get("description") or "")
                for item in gaps
                if item.get("blocking") is not False
            ][:4]
        elif planning_result == "needs_context":
            context["status"] = "needs_context"
            context["commitment_state"] = "evaluating"
            context["plan_status"] = "blocked_on_context"
            context["open_information_gaps"] = gaps
        elif planning_result in {"unavailable", "refused"}:
            context["status"] = "refused"
            context["commitment_state"] = "failed"
            context["plan_status"] = planning_result
            context["open_information_gaps"] = gaps
        elif planning_result in {
            "direct_skill",
            "composed_plan",
            "safe_adjustment",
            "alternative_plan",
            "mixed_plan",
        }:
            context["plan_version"] = max(0, int(context.get("plan_version") or 0)) + 1
            context["plan_status"] = "proposed"
            requires_confirmation = bool(
                not confirmation_authorized
                and (
                    metadata.get("semantic_plan_confirmation_required")
                    or metadata.get("confirmation_prompt")
                    or planning_result == "alternative_plan"
                )
            )
            context["status"] = (
                "awaiting_confirmation" if requires_confirmation else "planning"
            )
            context["commitment_state"] = (
                "waiting_for_user" if requires_confirmation else "evaluating"
            )
            context["open_information_gaps"] = []
            confirmation_prompt = " ".join(
                str(metadata.get("confirmation_prompt") or "").strip().split()
            )
            context["pending_questions"] = (
                [confirmation_prompt] if confirmation_prompt else []
            )
            planned_skills = metadata.get("planned_skills")
            if isinstance(planned_skills, list):
                context["plan_summary"] = {
                    "result": planning_result,
                    "skills": [item for item in planned_skills if isinstance(item, dict)][:12],
                }
            if requires_confirmation:
                context["confirmation"] = {
                    "status": "pending",
                    "goal_version": current_goal_version,
                    "plan_version": context["plan_version"],
                    "prompt": confirmation_prompt,
                }
        else:
            return

        context["updated_ms"] = _now_ms()
        meta = context.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        context["metadata"] = {
            **meta,
            "last_planning_result": planning_result,
            "last_planning_goal_version": current_goal_version,
        }
        self._persist_task_contexts_if_enabled()

    def record_agent_result(
        self,
        sid: str | None,
        result: Any,
        *,
        confirmed_request_ids: set[str] | None = None,
    ) -> None:
        """Record assistant speech and lightweight task hints from AgentResult."""
        if not self.enabled:
            return

        if hasattr(result, "model_dump"):
            data = result.model_dump(mode="json")
        elif isinstance(result, dict):
            data = result
        else:
            data = {}

        result_metadata = data.get("metadata")
        interaction_id = str(data.get("interaction_id") or "").strip()
        turn_id = ""
        canonical_plan_id = ""
        canonical_plan_fingerprint = ""
        goal_outcomes: dict[str, dict[str, Any]] = {}
        if isinstance(result_metadata, dict):
            turn_id = str(result_metadata.get("turn_id") or "").strip()
            canonical_plan_id = str(
                result_metadata.get("canonical_plan_id") or ""
            ).strip()
            canonical_plan_fingerprint = str(
                result_metadata.get("canonical_plan_fingerprint") or ""
            ).strip()
            self._record_planning_metadata(
                result_metadata,
                confirmation_authorized=bool(confirmed_request_ids),
            )
            goal_outcomes = self._canonical_goal_outcomes(result_metadata)
            self._record_nonexecuting_goal_outcomes(goal_outcomes)

        speech_parts: list[str] = []
        for key in ("speak_immediate", "speak_after", "speech"):
            for item in data.get(key, []) or []:
                text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                text = self._compact_text(text)
                if text:
                    speech_parts.append(text)
        if speech_parts:
            self.record_assistant_turn(sid, " ".join(speech_parts), metadata={"source": "agent_result"})

        # A conversational Goal is not complete merely because Response
        # Composer produced text. Bind it to the concrete chromie.speak request
        # IDs generated from InteractionSpeech so only Skill Runtime evidence
        # can make that Goal terminal. Clarification speech is intentionally not
        # bound: its Goal must remain active while waiting for the user.
        speech_items = [
            item for item in (data.get("speech") or []) if isinstance(item, dict)
        ]
        for goal_id, outcome in goal_outcomes.items():
            if str(outcome.get("disposition") or "").strip().lower() != "respond":
                continue
            scoped_speech: list[dict[str, Any]] = []
            for item in speech_items:
                item_metadata = item.get("metadata")
                if not isinstance(item_metadata, dict):
                    continue
                covered_goal_ids = self._string_list(
                    item_metadata.get("covers_goal_ids")
                )
                if goal_id in covered_goal_ids:
                    scoped_speech.append(item)
            request_ids = [
                str(item.get("id"))
                for item in scoped_speech
                if str(item.get("id") or "").strip()
            ]
            if not request_ids:
                continue
            self._record_goal_pending_execution(
                sid=sid,
                goal_id=goal_id,
                status="scheduled",
                summary="chromie.speak",
                request_ids=request_ids,
                planning_result="respond",
                planned_skills=[
                    {
                        "skill_id": "chromie.speak",
                        "request_id": request_id,
                        "source_goal_ids": [goal_id],
                    }
                    for request_id in request_ids
                ],
                confirmation_pending=False,
                interaction_id=interaction_id,
                turn_id=turn_id,
                canonical_plan_id=canonical_plan_id,
                canonical_plan_fingerprint=canonical_plan_fingerprint,
            )

        actions = data.get("actions", []) or data.get("skills", []) or []
        primary_actions: list[dict[str, Any]] = []
        for action in actions:
            if isinstance(action, dict):
                item = dict(action)
            else:
                item = {
                    "request_id": getattr(action, "request_id", None),
                    "skill_id": getattr(action, "skill_id", None),
                    "type": getattr(action, "type", None),
                    "target": getattr(action, "target", None),
                    "metadata": dict(getattr(action, "metadata", {}) or {}),
                }
            action_metadata = item.get("metadata")
            if not isinstance(action_metadata, dict):
                action_metadata = {}
            if action_metadata.get("auxiliary_social_attention"):
                continue
            item["metadata"] = action_metadata
            primary_actions.append(item)

        if primary_actions:
            planning_result = (
                str(result_metadata.get("planning_result") or "").strip()
                if isinstance(result_metadata, dict)
                else ""
            )
            confirmation_pending = bool(
                not confirmed_request_ids
                and isinstance(result_metadata, dict)
                and (
                    result_metadata.get("semantic_plan_confirmation_required")
                    or result_metadata.get("confirmation_prompt")
                    or planning_result == "alternative_plan"
                )
            )
            pending_status = "awaiting_confirmation" if confirmation_pending else "scheduled"
            by_goal: dict[str, list[dict[str, Any]]] = {}
            unscoped: list[dict[str, Any]] = []
            for item in primary_actions:
                action_metadata = item.get("metadata") or {}
                goal_ids = self._string_list(action_metadata.get("source_goal_ids"))
                if not goal_ids:
                    unscoped.append(item)
                    continue
                for goal_id in goal_ids:
                    by_goal.setdefault(goal_id, []).append(item)

            for goal_id, goal_actions in by_goal.items():
                request_ids = [
                    str(item.get("request_id"))
                    for item in goal_actions
                    if item.get("request_id")
                ]
                summaries = [
                    str(item.get("skill_id") or item.get("type") or item.get("target") or "action")
                    for item in goal_actions[:3]
                ]
                planned_skills = [
                    {
                        "skill_id": item.get("skill_id"),
                        "request_id": item.get("request_id"),
                        "source_goal_ids": self._string_list(
                            (item.get("metadata") or {}).get("source_goal_ids")
                        ),
                    }
                    for item in goal_actions
                ]
                self._record_goal_pending_execution(
                    sid=sid,
                    goal_id=goal_id,
                    status=pending_status,
                    summary=", ".join(summaries),
                    request_ids=request_ids,
                    planning_result=planning_result,
                    planned_skills=planned_skills,
                    confirmation_pending=confirmation_pending,
                    interaction_id=interaction_id,
                    turn_id=turn_id,
                    canonical_plan_id=canonical_plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint,
                )

            if unscoped:
                request_ids = [
                    str(item.get("request_id"))
                    for item in unscoped
                    if item.get("request_id")
                ]
                action_summaries = [
                    str(item.get("skill_id") or item.get("type") or item.get("target") or "action")
                    for item in unscoped[:3]
                ]
                self.record_pending_task(
                    sid=sid,
                    task_type="robot_action",
                    status=pending_status,
                    summary=", ".join(action_summaries),
                    metadata={
                        "action_count": len(unscoped),
                        "request_ids": request_ids,
                        "remaining_request_ids": list(request_ids),
                        "planning_result": planning_result,
                        "confirmation_pending": confirmation_pending,
                    },
                )

        # AgentResult exposes memory_updates at the top level. Native
        # InteractionResponse keeps them in metadata so the shared wire
        # contract remains narrow. Support both representations.
        memory_updates = data.get("memory_updates", []) or []
        metadata = data.get("metadata")
        if not memory_updates and isinstance(metadata, dict):
            memory_updates = metadata.get("memory_updates", []) or []
        for update in memory_updates:
            if not isinstance(update, dict):
                continue
            update_type = str(update.get("type") or "")
            if update_type in {"extracted_memory", "memory_entry", "memory"}:
                self._memory_store.add_many(
                    self._memory_extractor.extract_explicit_entries(
                        update.get("value"),
                        sid=sid,
                    )
                )
                continue
            if update_type not in {"pending_task", "task_status", "active_task"}:
                continue
            value = update.get("value")
            if isinstance(value, dict):
                self.record_pending_task(
                    sid=sid,
                    task_type=str(value.get("type") or update.get("key") or "task"),
                    status=str(value.get("status") or "pending"),
                    summary=str(value.get("summary") or value.get("description") or value.get("type") or "task"),
                    metadata=value,
                )
