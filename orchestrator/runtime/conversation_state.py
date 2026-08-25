from __future__ import annotations

import copy
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Deque

from pydantic import ValidationError

from orchestrator.runtime.memory import (
    MemoryEntry,
    MemoryExtractor,
    MemoryPromptBuilder,
    MemoryStore,
    ProtectedDurableMemoryStore,
    rank_memory_prompt_entries,
)

if TYPE_CHECKING:
    from orchestrator.runtime.host_settings import ConversationSettings

try:
    from chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        ResolvedDiscourseReference,
    )
    from chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from chromie_contracts.execution_outcome import (
        ExecutionOutcomeBundle,
        execution_outcome_fingerprint,
        goal_completion_qualification_summary,
    )
    from chromie_contracts.situation import CognitiveOpportunity, GoalTimeCondition
    from chromie_contracts.reflex import CancellationDispatchReceipt
    from chromie_contracts.reflection import ReflectionResolution
    from chromie_contracts.plan import CanonicalPlan, PlannerInformationGap
    from chromie_contracts.semantic_task import (
        InformationGap,
        SemanticGoal,
        SemanticTaskOperation,
        TaskContextSnapshot,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.discourse import (
        DiscourseReferent,
        DiscourseReferentUpdate,
        ResolvedDiscourseReference,
    )
    from shared.chromie_contracts.goal import (
        ActiveGoalSnapshot,
        GoalAssociationResolution,
        stable_goal_operation_id,
    )
    from shared.chromie_contracts.execution_outcome import (
        ExecutionOutcomeBundle,
        execution_outcome_fingerprint,
        goal_completion_qualification_summary,
    )
    from shared.chromie_contracts.situation import CognitiveOpportunity, GoalTimeCondition
    from shared.chromie_contracts.reflex import CancellationDispatchReceipt
    from shared.chromie_contracts.reflection import ReflectionResolution
    from shared.chromie_contracts.plan import CanonicalPlan, PlannerInformationGap
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
_DEFAULT_DURABLE_MEMORY_PATH = ".chromie/memory/profile.json"
_DEFAULT_REFLECTION_MEMORY_MAX_TTL_SEC = 900


logger = logging.getLogger("chromie.orchestrator.conversation_state")


def _now_ms() -> float:
    return time.time() * 1000.0


class ConversationStateManager:
    """Host-side conversation state and consent-bound profile memory.

    Session state stores bounded recent turns, active Goal snapshots, typed
    discourse referents, and evidence for LLM-owned reference resolution. The
    optional profile store persists only model-authored mutations carrying
    explicit current-turn consent. The Host does not decide what should be
    remembered or classify follow-ups from user phrases.

    The orchestrator still creates one SID per VAD utterance. This manager adds
    a separate conversation_id that spans SIDs until the deterministic
    hard-idle timeout starts a new conversation.
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
        max_tool_evidence: int = 8,
        max_memory_entries: int = 24,
        max_discourse_referents: int = 24,
        max_discourse_focus: int = 8,
        completed_task_retention_sec: int = 180,
        task_store_enabled: bool = False,
        task_store_path: str | os.PathLike[str] | None = None,
        durable_memory_enabled: bool = False,
        durable_memory_path: str | os.PathLike[str] | None = None,
        durable_memory_max_entries: int = 64,
        reflection_memory_max_ttl_sec: int | None = None,
    ) -> None:
        self.base_conversation_id = base_conversation_id or "local_default"
        self.enabled = enabled
        self.max_turns = max(0, int(max_turns))
        self.soft_idle_timeout_sec = max(1, int(soft_idle_timeout_sec))
        self.hard_idle_timeout_sec = max(1, int(hard_idle_timeout_sec))
        default_reflection_ttl = min(
            self.hard_idle_timeout_sec,
            _DEFAULT_REFLECTION_MEMORY_MAX_TTL_SEC,
        )
        self.reflection_memory_max_ttl_sec = max(
            1,
            int(
                default_reflection_ttl
                if reflection_memory_max_ttl_sec is None
                else reflection_memory_max_ttl_sec
            ),
        )
        self.turn_max_text_chars = max(20, int(turn_max_text_chars))
        self.max_context_chars = max(200, int(max_context_chars))
        self.max_pending_tasks = max(0, int(max_pending_tasks))
        self.max_tool_evidence = max(1, int(max_tool_evidence))
        self.max_memory_entries = max(1, int(max_memory_entries))
        self.max_discourse_referents = max(1, int(max_discourse_referents))
        self.max_discourse_focus = max(1, int(max_discourse_focus))
        self.completed_task_retention_sec = max(0, int(completed_task_retention_sec))
        self.task_store_enabled = bool(task_store_enabled)
        self.task_store_path = self._resolve_task_store_path(task_store_path)
        self.last_task_store_error: str | None = None
        self.durable_memory_enabled = bool(durable_memory_enabled)
        self.durable_memory_path = self._resolve_durable_memory_path(
            durable_memory_path
        )
        self.durable_memory_max_entries = max(1, int(durable_memory_max_entries))
        self._conversation_seq = 1
        self.conversation_id = self.base_conversation_id
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_turns * 2))
        self._pending_tasks: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_pending_tasks))
        self._task_contexts: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_pending_tasks))
        self._recent_tool_evidence: Deque[dict[str, Any]] = deque(
            maxlen=self.max_tool_evidence
        )
        self._discourse_referents: Deque[dict[str, Any]] = deque(
            maxlen=self.max_discourse_referents
        )
        self._discourse_focus: Deque[str] = deque(
            maxlen=self.max_discourse_focus
        )
        self._memory_store = MemoryStore(max_entries=self.max_memory_entries)
        self._durable_memory = ProtectedDurableMemoryStore(
            enabled=self.durable_memory_enabled,
            path=self.durable_memory_path,
            max_entries=self.durable_memory_max_entries,
        )
        self._memory_extractor = MemoryExtractor()
        self._memory_prompt_builder = MemoryPromptBuilder()
        self.last_split_reason: str | None = None
        if self.task_store_enabled:
            self._restore_task_contexts()

    @classmethod
    def from_settings(
        cls, settings: "ConversationSettings"
    ) -> "ConversationStateManager":
        return cls(
            base_conversation_id=settings.base_conversation_id,
            enabled=settings.enabled,
            max_turns=settings.max_turns,
            soft_idle_timeout_sec=settings.soft_idle_timeout_sec,
            hard_idle_timeout_sec=settings.hard_idle_timeout_sec,
            turn_max_text_chars=settings.turn_max_text_chars,
            max_context_chars=settings.max_context_chars,
            max_pending_tasks=settings.max_pending_tasks,
            max_tool_evidence=settings.max_tool_evidence,
            max_memory_entries=settings.max_memory_entries,
            max_discourse_referents=settings.max_discourse_referents,
            max_discourse_focus=settings.max_discourse_focus,
            completed_task_retention_sec=settings.completed_task_retention_sec,
            task_store_enabled=settings.task_store_enabled,
            task_store_path=settings.task_store_path,
            durable_memory_enabled=settings.durable_memory_enabled,
            durable_memory_path=settings.durable_memory_path,
            durable_memory_max_entries=settings.durable_memory_max_entries,
        )

    @staticmethod
    def _resolve_task_store_path(path: str | os.PathLike[str] | None) -> Path:
        resolved = Path(path or _DEFAULT_TASK_STORE_PATH).expanduser()
        if not resolved.is_absolute():
            resolved = _PROJECT_ROOT / resolved
        return resolved

    @staticmethod
    def _resolve_durable_memory_path(
        path: str | os.PathLike[str] | None,
    ) -> Path:
        resolved = Path(path or _DEFAULT_DURABLE_MEMORY_PATH).expanduser()
        if not resolved.is_absolute():
            resolved = _PROJECT_ROOT / resolved
        return resolved

    def _store_explicit_memory_entries(self, entries: list[MemoryEntry]) -> None:
        session_entries = [
            entry
            for entry in entries
            if not (
                entry.scope == "profile"
                and entry.persistence_policy == "durable_with_explicit_consent"
            )
        ]
        durable_entries = [
            entry
            for entry in entries
            if entry.scope == "profile"
            and entry.persistence_policy == "durable_with_explicit_consent"
        ]
        self._memory_store.add_many(session_entries)
        if durable_entries:
            self._durable_memory.add_many(durable_entries)

    def forget_durable_memory(self, *, key: str) -> int:
        return self._durable_memory.remove(key=key)

    def clear_durable_memory(self) -> int:
        return self._durable_memory.clear()

    @staticmethod
    def _authorized_durable_mutation(value: Any, *, operation: str) -> bool:
        return (
            isinstance(value, dict)
            and value.get("operation") == operation
            and value.get("scope") == "profile"
            and value.get("persistence_policy")
            == "durable_with_explicit_consent"
            and value.get("consent_basis") == "explicit_current_turn"
        )

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


    @staticmethod
    def _goal_responsibility_status(context: dict[str, Any]) -> str:
        raw = context.get("semantic_goal")
        if isinstance(raw, dict):
            return str(raw.get("responsibility_status") or "open").strip().lower() or "open"
        return "open"

    @staticmethod
    def _set_goal_responsibility_status(
        context: dict[str, Any],
        status: str,
        *,
        source: str,
        evidence_refs: list[str] | None = None,
    ) -> None:
        goal = ConversationStateManager._semantic_goal_from_context(context)
        revised = goal.model_copy(
            update={
                "responsibility_status": status,
                "version": goal.version + 1,
            }
        )
        context["semantic_goal"] = revised.model_dump(mode="json", exclude_none=True)
        context["goal_version"] = revised.version
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        history = metadata.get("responsibility_reconciliation_history")
        if not isinstance(history, list):
            history = []
        history.append({
            "status": status,
            "source": source,
            "evidence_refs": list(evidence_refs or []),
            "ts_ms": _now_ms(),
        })
        context["metadata"] = {
            **metadata,
            "responsibility_status": status,
            "responsibility_reconciliation_history": history[-16:],
        }

    @staticmethod
    def _durable_goal_context(context: dict[str, Any]) -> dict[str, Any]:
        """Return only durable Responsibility/provenance state for restart.

        Situation, derived cognitive opportunities, current provider/runtime
        snapshots, and optional Reflection outputs are reconstructable live state.
        They must never become durable truth merely because they were attached to
        an in-process Goal context.
        """

        durable = copy.deepcopy(context)
        for key in (
            "situation",
            "cognitive_opportunities",
            "reflection_resolutions",
            "reflection_state_results",
            "provider_status",
            "robot_state",
            "runtime_state",
            "current_environment",
            "current_body_state",
        ):
            durable.pop(key, None)
        metadata = durable.get("metadata")
        if isinstance(metadata, dict):
            for key in (
                "situation",
                "cognitive_opportunities",
                "reflection_resolutions",
                "reflection_state_results",
                "provider_status",
                "robot_state",
                "runtime_state",
                "current_environment",
                "current_body_state",
            ):
                metadata.pop(key, None)
        return durable

    def _durable_task_contexts(self) -> list[dict[str, Any]]:
        if self.max_pending_tasks <= 0:
            return []
        durable: list[dict[str, Any]] = []
        for context in self._task_contexts:
            if self._goal_responsibility_status(context) != "open":
                continue
            policy = str(context.get("persistence_policy") or "persist_if_unfinished").lower()
            if policy in {"ephemeral", "memory_only", "do_not_persist", "none"}:
                continue
            durable.append(self._json_safe(self._durable_goal_context(context)))
        return durable[-self.max_pending_tasks :]

    def persist_task_contexts(self) -> bool:
        if not self.enabled or not self.task_store_enabled:
            return False
        payload = {
            "version": 2,
            "conversation_id": self.conversation_id,
            "saved_ms": _now_ms(),
            "task_contexts": self._durable_task_contexts(),
            "discourse_referents": self.discourse_referents(),
            "discourse_focus": self.discourse_focus(),
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
            raw_contexts = []
        raw_referents = (
            payload.get("discourse_referents", [])
            if isinstance(payload, dict)
            else []
        )
        restored_referents: list[dict[str, Any]] = []
        if isinstance(raw_referents, list):
            for item in raw_referents[-self.max_discourse_referents :]:
                if not isinstance(item, dict):
                    continue
                try:
                    restored_referents.append(
                        DiscourseReferent.model_validate(item).model_dump(
                            mode="json",
                            exclude_none=True,
                        )
                    )
                except ValidationError as exc:
                    logger.debug(
                        "Ignoring malformed persisted discourse referent index=%s error=%s",
                        len(restored_referents),
                        exc,
                    )
                    continue
        if restored_referents:
            self._discourse_referents = deque(
                restored_referents,
                maxlen=self.max_discourse_referents,
            )
            known = {
                str(item.get("referent_id") or "")
                for item in restored_referents
            }
            raw_focus = (
                payload.get("discourse_focus", [])
                if isinstance(payload, dict)
                else []
            )
            focus = [
                str(item)
                for item in raw_focus
                if str(item) in known
            ] if isinstance(raw_focus, list) else []
            self._discourse_focus = deque(
                focus[-self.max_discourse_focus :],
                maxlen=self.max_discourse_focus,
            )
        now = _now_ms()
        restored: list[dict[str, Any]] = []
        for item in raw_contexts[-self.max_pending_tasks :]:
            if not isinstance(item, dict):
                continue
            original_status = str(item.get("status") or "open")
            if self._goal_responsibility_status(item) != "open":
                continue
            context = copy.deepcopy(item)
            context["conversation_id"] = self.conversation_id
            context["status"] = "recoverable"
            context["commitment_state"] = "evaluating"
            context["plan_status"] = "revalidation_required"
            context["task_relation"] = "continue_task"
            context["updated_ms"] = now
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            previous_confirmation = (
                copy.deepcopy(context.get("confirmation"))
                if isinstance(context.get("confirmation"), dict)
                else None
            )
            previous_remaining = self._string_list(
                metadata.get("remaining_request_ids")
            )
            previous_request_statuses = metadata.get("request_statuses")
            if not isinstance(previous_request_statuses, dict):
                previous_request_statuses = {}
            previous_confirmation_request_ids = self._string_list(
                metadata.get("confirmation_request_ids")
                or (previous_confirmation or {}).get("request_ids")
            )
            context["confirmation"] = None
            metadata = {
                **metadata,
                "restored_from_task_store": True,
                "restored_original_status": original_status,
                "restored_ms": now,
                "runtime_revalidation_required": True,
                "recovery_previous_remaining_request_ids": previous_remaining,
                "recovery_previous_request_statuses": dict(previous_request_statuses),
                "recovery_previous_confirmation_request_ids": (
                    previous_confirmation_request_ids
                ),
                "remaining_request_ids": [],
                "request_statuses": {},
                "confirmation_pending": False,
            }
            if previous_confirmation is not None:
                metadata["recovery_previous_confirmation"] = previous_confirmation
            for stale_key in (
                "confirmation_id",
                "confirmation_request_ids",
            ):
                metadata.pop(stale_key, None)
            context["metadata"] = metadata
            if not isinstance(context.get("related_sids"), list):
                context["related_sids"] = []
            restored.append(context)
        if restored:
            self._task_contexts = deque(restored, maxlen=max(1, self.max_pending_tasks))
        if restored or restored_referents:
            self.last_split_reason = "restored_semantic_context"
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
            or self._discourse_referents
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
            if self._goal_responsibility_status(context) == "open":
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
            except ValidationError as exc:
                logger.warning(
                    "Falling back from malformed persisted semantic_goal task_id=%s error=%s",
                    context.get("task_id"),
                    exc,
                )
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
                except ValidationError as exc:
                    logger.debug(
                        "Ignoring malformed task information gap task_id=%s error=%s",
                        context.get("task_id"),
                        exc,
                    )
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
        planned_capabilities: list[dict[str, Any]] = []
        raw_planned_capabilities = metadata.get("planned_capabilities")
        if isinstance(raw_planned_capabilities, list):
            for item in raw_planned_capabilities[:8]:
                if not isinstance(item, dict):
                    continue
                planned_capabilities.append(
                    {
                        "capability_id": str(item.get("capability_id") or "").strip(),
                        "request_id": str(item.get("request_id") or "").strip(),
                        "args": self._json_safe(
                            item.get("args") if isinstance(item.get("args"), dict) else {}
                        ),
                        "timing": str(item.get("timing") or "sequential").strip(),
                        "source_goal_ids": self._string_list(
                            item.get("source_goal_ids")
                        ),
                        "safety_class": str(
                            item.get("safety_class") or ""
                        ).strip(),
                        "retryable_safe_read": (
                            item.get("retryable_safe_read") is True
                        ),
                    }
                )
        request_statuses = metadata.get("request_statuses")
        if not isinstance(request_statuses, dict):
            request_statuses = {}
        remaining_request_ids = metadata.get("remaining_request_ids")
        if not isinstance(remaining_request_ids, list):
            remaining_request_ids = []
        execution_binding = {
            "planning_result": str(metadata.get("planning_result") or "").strip(),
            "planned_capabilities": planned_capabilities,
            "request_statuses": {
                str(key): str(value)
                for key, value in list(request_statuses.items())[:12]
            },
            "remaining_request_ids": [
                str(item) for item in remaining_request_ids[:12] if str(item).strip()
            ],
            "retryable_safe_read": any(
                item.get("retryable_safe_read") is True for item in planned_capabilities
            ),
            "execution_outcome_status": str(
                metadata.get("execution_outcome_status") or ""
            ).strip(),
            "interaction_id": str(metadata.get("interaction_id") or "").strip(),
            "canonical_plan_id": str(
                metadata.get("canonical_plan_id") or ""
            ).strip(),
            "canonical_plan_fingerprint": str(
                metadata.get("canonical_plan_fingerprint") or ""
            ).strip(),
        }
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
                        "restored_from_task_store",
                        "restored_original_status",
                    )
                    if metadata.get(key) is not None
                },
                "execution_binding": execution_binding,
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

        active = self._active_task_contexts()
        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        return [
            ActiveGoalSnapshot.from_task_snapshot(
                self._task_snapshot(item)
            ).model_dump(mode="json", exclude_none=True)
            for item in active[-limit:]
        ]

    def recent_goal_snapshots(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return retained terminal Goals for bounded semantic association only."""

        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0 or self.completed_task_retention_sec <= 0:
            return []
        now = _now_ms()
        retained: list[dict[str, Any]] = []
        for context in self._task_contexts:
            if self._goal_responsibility_status(context) == "open":
                continue
            updated_ms = context.get("updated_ms") or now
            try:
                age_sec = max(0.0, (now - float(updated_ms)) / 1000.0)
            except (TypeError, ValueError):
                age_sec = 0.0
            if age_sec >= self.completed_task_retention_sec:
                continue
            retained.append(
                ActiveGoalSnapshot.from_task_snapshot(
                    self._task_snapshot(context)
                ).model_dump(mode="json", exclude_none=True)
            )
        return retained[-limit:]

    def goal_association_candidate_snapshots(
        self,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Prefer active Goals, then fill the bounded association set with recent terminal Goals."""

        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        active = self.active_goal_snapshots(limit=limit)
        remaining = max(0, limit - len(active))
        recent = self.recent_goal_snapshots(limit=remaining)
        return [*active, *recent]

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
            except ValidationError as exc:
                logger.warning(
                    "Ignoring malformed semantic task operation from turn metadata error=%s",
                    exc,
                )
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
        source: str | None,
    ) -> dict[str, Any]:
        if operation.goal is None:
            raise ValueError(
                "create semantic operation requires a goal before state mutation"
            )
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
        )
        commitment = operation.commitment_state or (
            "waiting_for_user" if status == "waiting_for_user" else "evaluating"
        )
        context = {
            "task_id": task_id,
            "conversation_id": self.conversation_id,
            "status": status,
            "task_relation": "new_task",
            "task_type": str((operation.metadata or {}).get("task_type") or "conversation"),
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
                "source": source,
                "semantic_operation_id": operation.operation_id,
                "semantic_operation_confidence": operation.confidence,
                "semantic_relationship": operation.relationship,
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
        responsibility_status = (
            "open"
            if goal.responsibility_status == "satisfied"
            and operation.operation in {"modify", "clarification_answer", "correct"}
            else goal.responsibility_status
        )
        return SemanticGoal(
            goal_id=goal.goal_id,
            version=version,
            responsibility_status=responsibility_status,
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
        source: str | None,
    ) -> dict[str, Any]:
        now = _now_ms()
        previous_work_status = str(context.get("status") or "open")
        previous_commitment_state = str(context.get("commitment_state") or "none")
        previous_plan_status = str(context.get("plan_status") or "not_planned")
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

        responsibility_status = self._goal_responsibility_status(context)
        if (
            responsibility_status in {"cancelled", "refused", "superseded"}
            and operation.operation not in {"query_status"}
        ):
            result["reason"] = (
                f"responsibility_status_{responsibility_status}_is_not_modifiable"
            )
            return result
        if (
            responsibility_status == "satisfied"
            and operation.operation
            not in {"query_status", "modify", "clarification_answer", "correct"}
        ):
            result["reason"] = "satisfied_responsibility_requires_correction_to_reopen"
            return result

        if operation.operation in {"cancel", "reject"}:
            context["status"] = "cancelled" if operation.operation == "cancel" else "refused"
            context["commitment_state"] = "cancelled" if operation.operation == "cancel" else "failed"
            self._set_goal_responsibility_status(
                context,
                "cancelled" if operation.operation == "cancel" else "refused",
                source=f"semantic_operation:{operation.operation}",
            )
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
            if revised.responsibility_status == "open":
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                context["metadata"] = {**metadata, "responsibility_status": "open"}
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
            preserve_work_state = (
                old_plan_version > 0
                or previous_work_status
                in {
                    "awaiting_confirmation",
                    "committed",
                    "scheduled",
                    "running",
                    "paused",
                    "recoverable",
                }
            )
            if preserve_work_state:
                context["status"] = previous_work_status
                context["commitment_state"] = previous_commitment_state
                context["plan_status"] = previous_plan_status
            else:
                context["status"] = operation.status_update or (
                    "waiting_for_user"
                    if blocking_user_gap
                    else "needs_context"
                    if blocking_context_gap
                    else "planning"
                )
                context["commitment_state"] = operation.commitment_state or (
                    "waiting_for_user"
                    if context["status"] == "waiting_for_user"
                    else "evaluating"
                )

        context["task_relation"] = {
            "modify": "modify_task",
            "clarification_answer": "clarify_task",
            "correct": "modify_task",
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
            "source": source,
            "semantic_operation_id": operation.operation_id,
            "semantic_operation_confidence": operation.confidence,
            "semantic_relationship": operation.relationship,
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
        pending_task_snapshot = copy.deepcopy(list(self._pending_tasks))
        discourse_referent_snapshot = copy.deepcopy(list(self._discourse_referents))
        discourse_focus_snapshot = list(self._discourse_focus)
        activity_snapshot = self.last_activity_ms
        store_error_snapshot = self.last_task_store_error

        def restore_snapshot(*, store_error: str | None = store_error_snapshot) -> None:
            self._task_contexts = deque(
                task_context_snapshot, maxlen=max(1, self.max_pending_tasks)
            )
            self._pending_tasks = deque(
                pending_task_snapshot, maxlen=max(1, self.max_pending_tasks)
            )
            self._discourse_referents = deque(
                discourse_referent_snapshot,
                maxlen=self.max_discourse_referents,
            )
            self._discourse_focus = deque(
                discourse_focus_snapshot,
                maxlen=self.max_discourse_focus,
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

    def goal_cancellation_bindings(
        self,
        goal_ids: list[str] | tuple[str, ...] | set[str],
    ) -> list[dict[str, Any]]:
        """Return trusted host-only runtime bindings for named Goal cancellation.

        This projection is intentionally not part of ``active_goal_snapshots``:
        model-facing continuity context does not need interaction/request
        identities.  The Core selects semantic Goal IDs; the trusted host then
        resolves those IDs to exact committed runtime and confirmation state.
        """

        bindings: list[dict[str, Any]] = []
        for raw_goal_id in goal_ids:
            goal_id = " ".join(str(raw_goal_id or "").strip().split())
            if not goal_id:
                continue
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                bindings.append(
                    {
                        "goal_id": goal_id,
                        "found": False,
                        "reason": "unknown_target_goal",
                    }
                )
                continue
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            confirmation = context.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            remaining = self._string_list(metadata.get("remaining_request_ids"))
            confirmation_request_ids = self._string_list(
                confirmation.get("request_ids")
                or metadata.get("confirmation_request_ids")
            )
            planned_request_ids = [
                str(item.get("request_id") or "").strip()
                for item in (metadata.get("planned_capabilities") or [])
                if isinstance(item, dict) and str(item.get("request_id") or "").strip()
            ]
            bound_request_ids = sorted(
                {
                    *planned_request_ids,
                    *remaining,
                    *confirmation_request_ids,
                    *self._string_list(metadata.get("request_ids")),
                }
            )
            status = str(context.get("status") or "open").strip().lower()
            interaction_id = str(metadata.get("interaction_id") or "").strip()
            plan_id = str(metadata.get("canonical_plan_id") or "").strip()
            plan_fingerprint = str(
                metadata.get("canonical_plan_fingerprint") or ""
            ).strip()
            confirmation_id = str(
                confirmation.get("confirmation_id")
                or metadata.get("confirmation_id")
                or ""
            ).strip()
            confirmation_pending = bool(
                confirmation_id
                and str(confirmation.get("status") or "pending").strip().lower()
                == "pending"
            )
            runtime_revalidation_required = bool(
                metadata.get("runtime_revalidation_required") is True
            )
            runtime_status = status in {
                "committed",
                "scheduled",
                "running",
                "paused",
                "recoverable",
            }
            bindings.append(
                {
                    "goal_id": goal_id,
                    "task_id": str(context.get("task_id") or ""),
                    "found": True,
                    "status": status,
                    "responsibility_status": self._goal_responsibility_status(context),
                    "plan_version": max(0, int(context.get("plan_version") or 0)),
                    "request_ids": bound_request_ids,
                    "remaining_request_ids": remaining,
                    "interaction_id": interaction_id,
                    "canonical_plan_id": plan_id,
                    "canonical_plan_fingerprint": plan_fingerprint,
                    "confirmation_id": confirmation_id,
                    "confirmation_pending": confirmation_pending,
                    "confirmation_request_ids": confirmation_request_ids,
                    "requires_revalidation": runtime_revalidation_required,
                    "revalidation_reason": (
                        "restored_runtime_binding_requires_fresh_provider_state"
                        if runtime_revalidation_required
                        else ""
                    ),
                    "requires_runtime_dispatch": bool(
                        not runtime_revalidation_required
                        and (
                            runtime_status
                            or (remaining and not confirmation_pending)
                        )
                    ),
                }
            )
        return bindings

    @staticmethod
    def _receipt_failure_reasons(
        receipt: CancellationDispatchReceipt,
    ) -> list[str]:
        reasons: list[str] = []
        if receipt.requested_scope != "specific_goal":
            reasons.append("receipt_scope_not_specific_goal")
        if receipt.stale_binding_request_bindings:
            reasons.append("stale_runtime_binding")
        if receipt.shared_owner_conflict_request_bindings:
            reasons.append("shared_owner_conflict")
        if receipt.non_interruptible_request_bindings:
            reasons.append("non_interruptible_request")
        if receipt.provider_cancel_failure_evidence:
            reasons.append("provider_cancel_failure")
        if receipt.dispatch_failures:
            reasons.append("cancellation_dispatch_failure")
        return reasons

    def apply_goal_cancellation_resolution(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        receipts: list[CancellationDispatchReceipt | dict[str, Any]],
        confirmation_transition: dict[str, Any] | None,
        sid: str | None,
        user_text: str,
        source: str = "goal_cancellation_reconciliation",
        target_goal_ids_override: set[str] | list[str] | tuple[str, ...] | None = None,
        target_responsibility_status: str = "cancelled",
    ) -> list[dict[str, Any]]:
        """Atomically reconcile trusted cancellation evidence into Goal state.

        Runtime/provider cancellation cannot be rolled back, but Goal state must
        never be mutated from a model proposal alone.  This transaction first
        validates exact interaction/plan/request bindings for every execution-
        bound Goal, then applies semantic cancellation, collateral widening, and
        confirmation-token replacement in one in-memory/durable commit.
        """

        resolved = (
            resolution
            if isinstance(resolution, GoalAssociationResolution)
            else GoalAssociationResolution.model_validate(resolution)
        )
        target_goal_ids = (
            {str(goal_id).strip() for goal_id in target_goal_ids_override if str(goal_id).strip()}
            if target_goal_ids_override is not None
            else {
                goal_id
                for association in resolved.associations
                if association.relationship == "cancel"
                for goal_id in association.target_goal_ids
            }
        )
        if target_responsibility_status not in {"cancelled", "superseded"}:
            raise ValueError("unsupported target responsibility transition")
        if not target_goal_ids:
            return self.apply_goal_association_resolution(
                resolved,
                sid=sid,
                user_text=user_text,
                source=source,
                atomic=True,
            )

        validated_receipts = [
            item
            if isinstance(item, CancellationDispatchReceipt)
            else CancellationDispatchReceipt.model_validate(item)
            for item in receipts
        ]
        transition = dict(confirmation_transition or {})
        cancelled_confirmation_ids = {
            str(item).strip()
            for item in transition.get("cancelled_request_ids", [])
            if str(item).strip()
        }
        bindings = {
            item["goal_id"]: item
            for item in self.goal_cancellation_bindings(target_goal_ids)
        }
        validation_errors: list[str] = []
        receipt_by_goal: dict[str, CancellationDispatchReceipt] = {}
        for goal_id in sorted(target_goal_ids):
            binding = bindings.get(goal_id) or {"found": False}
            if not binding.get("found"):
                validation_errors.append(f"{goal_id}:unknown_target_goal")
                continue
            if not binding.get("requires_runtime_dispatch"):
                continue
            matching = [
                receipt
                for receipt in validated_receipts
                if goal_id in receipt.target_goal_ids
                and receipt.expected_plan_id
                == binding.get("canonical_plan_id")
                and receipt.expected_plan_fingerprint
                == binding.get("canonical_plan_fingerprint")
                and binding.get("interaction_id") in receipt.interaction_ids
            ]
            if len(matching) != 1:
                validation_errors.append(
                    f"{goal_id}:exact_cancellation_receipt_missing"
                )
                continue
            receipt = matching[0]
            failures = self._receipt_failure_reasons(receipt)
            if failures:
                validation_errors.extend(
                    f"{goal_id}:{reason}" for reason in failures
                )
                continue
            required_request_ids = set(
                binding.get("remaining_request_ids") or ()
            ) - cancelled_confirmation_ids
            selected_request_ids = {
                item.request_id
                for item in receipt.selected_request_bindings
                if item.interaction_id == binding.get("interaction_id")
            }
            missing = sorted(required_request_ids - selected_request_ids)
            if missing:
                validation_errors.append(
                    f"{goal_id}:unselected_runtime_requests:{','.join(missing)}"
                )
                continue
            receipt_by_goal[goal_id] = receipt

        if validation_errors:
            raise ValueError(
                "goal_cancellation_reconciliation_rejected:"
                + ";".join(validation_errors)
            )

        coaffected_goal_ids = {
            goal_id
            for receipt in validated_receipts
            for goal_id in receipt.affected_goal_ids
            if goal_id not in target_goal_ids
        }
        replacement = transition.get("replacement")
        if replacement is not None and not isinstance(replacement, dict):
            raise ValueError("confirmation replacement must be a dictionary")

        def mutate() -> list[dict[str, Any]]:
            results = self._apply_goal_association_resolution_in_memory(
                resolved,
                sid=sid,
                user_text=user_text,
                source=source,
            )
            rejected = [
                item
                for item in results
                if item.get("applied") is False
                and item.get("reason") != "operation_already_applied"
            ]
            if rejected:
                return results

            timestamp_ms = _now_ms()
            receipt_payloads = [
                item.model_dump(mode="json", exclude_none=True)
                for item in validated_receipts
            ]
            for goal_id in sorted(target_goal_ids | coaffected_goal_ids):
                context = self._task_context_by_goal_id(goal_id)
                if context is None:
                    results.append(
                        {
                            "goal_id": goal_id,
                            "applied": True,
                            "state_change": "unmatched_coaffected_goal_recorded",
                        }
                    )
                    continue
                previous_status = str(
                    context.get("status") or "open"
                ).lower()
                if goal_id in target_goal_ids:
                    context["status"] = "cancelled"
                    context["commitment_state"] = "cancelled"
                    context["plan_status"] = (
                        "work_stopped_for_replacement"
                        if target_responsibility_status == "superseded"
                        else "cancelled"
                    )
                    if target_responsibility_status == "superseded":
                        replacement_goal_ids = [
                            str(goal.goal_id or "")
                            for goal in resolved.new_goals
                            if goal_id in goal.supersedes_goal_ids and goal.goal_id
                        ]
                        self._set_goal_responsibility_status(
                            context,
                            "superseded",
                            source=source,
                        )
                        metadata = context.get("metadata")
                        if not isinstance(metadata, dict):
                            metadata = {}
                        context["metadata"] = {
                            **metadata,
                            "superseded_by_goal_ids": replacement_goal_ids,
                        }
                elif goal_id in coaffected_goal_ids:
                    if self._goal_responsibility_status(context) == "open":
                        context["status"] = "recoverable"
                        context["commitment_state"] = "evaluating"
                        context["plan_status"] = "interrupted_by_widened_scope"
                confirmation = context.get("confirmation")
                if not isinstance(confirmation, dict):
                    confirmation = {}
                if goal_id in target_goal_ids:
                    context["confirmation"] = {
                        **confirmation,
                        "status": "cancelled",
                        "resolved_ms": timestamp_ms,
                    }
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                context["metadata"] = {
                    **metadata,
                    "remaining_request_ids": (
                        []
                        if goal_id in target_goal_ids
                        else metadata.get("remaining_request_ids", [])
                    ),
                    "cancellation_source_turn_id": resolved.turn_id,
                    "cancellation_receipts": receipt_payloads,
                    "cancellation_targeted": goal_id in target_goal_ids,
                    "cancellation_scope_widened": goal_id in coaffected_goal_ids,
                }
                context["updated_ms"] = timestamp_ms
                if goal_id in coaffected_goal_ids:
                    results.append(
                        {
                            "goal_id": goal_id,
                            "operation": "runtime_scope_widened_cancel",
                            "applied": True,
                            "status": str(context.get("status") or previous_status),
                            "state_change": (
                                "work_interrupted_responsibility_open"
                                if self._goal_responsibility_status(context) == "open"
                                else "responsibility_terminal_work_recorded"
                            ),
                        }
                    )

            selected_request_bindings = {
                (item.interaction_id, item.request_id)
                for receipt in validated_receipts
                for item in receipt.selected_request_bindings
            }
            for task in self._pending_tasks:
                if task.get("type") != "goal_execution":
                    continue
                task_metadata = task.get("metadata")
                if not isinstance(task_metadata, dict):
                    continue
                task_goal_id = str(task_metadata.get("goal_id") or "").strip()
                if task_goal_id in target_goal_ids:
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **task_metadata,
                        "remaining_request_ids": [],
                        "work_stop_source_turn_id": resolved.turn_id,
                    }
                elif task_goal_id in coaffected_goal_ids:
                    remaining = self._string_list(
                        task_metadata.get("remaining_request_ids")
                        or task_metadata.get("request_ids")
                    )
                    task_interaction_id = str(
                        task_metadata.get("interaction_id") or ""
                    ).strip()
                    remaining = [
                        request_id
                        for request_id in remaining
                        if (task_interaction_id, request_id)
                        not in selected_request_bindings
                    ]
                    task["status"] = "recoverable"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **task_metadata,
                        "remaining_request_ids": remaining,
                        "work_stop_scope_widened": True,
                    }

            old_confirmation_id = str(
                transition.get("old_confirmation_id") or ""
            ).strip()
            released_confirmation_goal_ids = {
                str(item).strip()
                for item in transition.get("released_confirmation_goal_ids") or []
                if str(item).strip()
            }
            if old_confirmation_id:
                new_confirmation_id = str(
                    (replacement or {}).get("confirmation_id") or ""
                ).strip()
                new_fingerprint = str(
                    (replacement or {}).get("fingerprint") or ""
                ).strip()
                new_expires_at = (replacement or {}).get("expires_at")
                preserved_by_goal = (
                    (replacement or {}).get("request_ids_by_goal") or {}
                )
                confirmed_by_goal = (
                    (replacement or {}).get(
                        "confirmation_request_ids_by_goal"
                    )
                    or {}
                )
                replacement_interaction_id = str(
                    (replacement or {}).get("interaction_id") or ""
                ).strip()
                replacement_plan_id = str(
                    (replacement or {}).get("canonical_plan_id") or ""
                ).strip()
                replacement_plan_fingerprint = str(
                    (replacement or {}).get(
                        "canonical_plan_fingerprint"
                    )
                    or ""
                ).strip()
                for task in self._pending_tasks:
                    metadata = task.get("metadata")
                    if not isinstance(metadata, dict):
                        continue
                    if metadata.get("confirmation_id") != old_confirmation_id:
                        continue
                    goal_id = str(metadata.get("goal_id") or "").strip()
                    if goal_id in target_goal_ids:
                        task["status"] = "cancelled"
                        task["updated_ms"] = timestamp_ms
                        continue
                    request_ids = confirmed_by_goal.get(goal_id)
                    if new_confirmation_id and isinstance(request_ids, list):
                        task["metadata"] = {
                            **metadata,
                            "confirmation_id": new_confirmation_id,
                            "fingerprint": new_fingerprint,
                            "expires_at": new_expires_at,
                            "request_ids": list(request_ids),
                            "confirmation_request_ids": list(request_ids),
                            "replaces_confirmation_id": old_confirmation_id,
                        }
                        task["status"] = "awaiting_confirmation"
                        task["updated_ms"] = timestamp_ms
                    else:
                        task["status"] = "cancelled"
                        task["updated_ms"] = timestamp_ms
                        if goal_id in released_confirmation_goal_ids:
                            context = self._task_context_by_goal_id(goal_id)
                            if context is not None and self._goal_responsibility_status(context) == "open":
                                context["status"] = "planning"
                                context["commitment_state"] = "evaluating"
                                context["plan_status"] = "confirmation_revoked_requires_replan"
                                confirmation = context.get("confirmation")
                                if not isinstance(confirmation, dict):
                                    confirmation = {}
                                context["confirmation"] = {
                                    **confirmation,
                                    "status": "revoked",
                                    "resolved_ms": timestamp_ms,
                                }
                                context_metadata = context.get("metadata")
                                if not isinstance(context_metadata, dict):
                                    context_metadata = {}
                                context["metadata"] = {
                                    **context_metadata,
                                    "confirmation_id": "",
                                    "confirmation_request_ids": [],
                                    "remaining_request_ids": [],
                                    "confirmation_revoked_by_goal_cancellation": True,
                                }
                                context["updated_ms"] = timestamp_ms

                for task in self._pending_tasks:
                    if task.get("type") != "goal_execution":
                        continue
                    metadata = task.get("metadata")
                    if not isinstance(metadata, dict):
                        continue
                    goal_id = str(metadata.get("goal_id") or "").strip()
                    if not goal_id:
                        continue
                    if goal_id in target_goal_ids:
                        task["status"] = "cancelled"
                        task["updated_ms"] = timestamp_ms
                        task["metadata"] = {
                            **metadata,
                            "remaining_request_ids": [],
                            "cancellation_source_turn_id": resolved.turn_id,
                        }
                        continue
                    request_ids = preserved_by_goal.get(goal_id)
                    if goal_id in released_confirmation_goal_ids and not new_confirmation_id:
                        task["status"] = "cancelled"
                        task["updated_ms"] = timestamp_ms
                        task["metadata"] = {
                            **metadata,
                            "remaining_request_ids": [],
                            "confirmation_revoked_by_goal_cancellation": True,
                        }
                    elif new_confirmation_id and isinstance(request_ids, list):
                        task["status"] = "awaiting_confirmation"
                        task["updated_ms"] = timestamp_ms
                        task["metadata"] = {
                            **metadata,
                            "request_ids": list(request_ids),
                            "remaining_request_ids": list(request_ids),
                            "interaction_id": replacement_interaction_id,
                            "canonical_plan_id": replacement_plan_id,
                            "canonical_plan_fingerprint": (
                                replacement_plan_fingerprint
                            ),
                            "confirmation_pending": True,
                            "confirmation_id": new_confirmation_id,
                            "replaces_confirmation_id": old_confirmation_id,
                        }

                if new_confirmation_id:
                    for goal_id, request_ids in preserved_by_goal.items():
                        context = self._task_context_by_goal_id(str(goal_id))
                        if context is None or str(goal_id) in target_goal_ids:
                            continue
                        context["status"] = "awaiting_confirmation"
                        context["commitment_state"] = "waiting_for_user"
                        context["plan_status"] = "awaiting_confirmation"
                        context["confirmation"] = {
                            "status": "pending",
                            "confirmation_id": new_confirmation_id,
                            "fingerprint": new_fingerprint,
                            "expires_at": new_expires_at,
                            "request_ids": list(
                                confirmed_by_goal.get(goal_id, [])
                            ),
                            "replaces_confirmation_id": old_confirmation_id,
                        }
                        metadata = context.get("metadata")
                        if not isinstance(metadata, dict):
                            metadata = {}
                        context["metadata"] = {
                            **metadata,
                            "confirmation_id": new_confirmation_id,
                            "confirmation_request_ids": list(
                                confirmed_by_goal.get(goal_id, [])
                            ),
                            "request_ids": list(request_ids),
                            "remaining_request_ids": list(request_ids),
                            "interaction_id": replacement_interaction_id,
                            "canonical_plan_id": replacement_plan_id,
                            "canonical_plan_fingerprint": (
                                replacement_plan_fingerprint
                            ),
                        }
                        context["updated_ms"] = timestamp_ms

            results.append(
                {
                    "operation": "cancellation_receipt_reconciliation",
                    "applied": True,
                    "target_goal_ids": sorted(target_goal_ids),
                    "coaffected_goal_ids": sorted(coaffected_goal_ids),
                    "receipt_count": len(validated_receipts),
                    "confirmation_rebuilt": bool(replacement),
                }
            )
            return results

        return self._commit_semantic_state_transaction(
            mutate,
            rollback_reason="atomic_cancellation_transaction_rolled_back",
            persistence_failure_reason="atomic_cancellation_persistence_failed",
        )

    def apply_goal_replacement_resolution(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        receipts: list[CancellationDispatchReceipt | dict[str, Any]],
        confirmation_transition: dict[str, Any] | None,
        sid: str | None,
        user_text: str,
        source: str = "goal_replacement_reconciliation",
    ) -> list[dict[str, Any]]:
        resolved = (
            resolution
            if isinstance(resolution, GoalAssociationResolution)
            else GoalAssociationResolution.model_validate(resolution)
        )
        target_goal_ids = {
            goal_id
            for goal in resolved.new_goals
            for goal_id in goal.supersedes_goal_ids
        }
        if not target_goal_ids:
            return self.apply_goal_association_resolution(
                resolved,
                sid=sid,
                user_text=user_text,
                source=source,
                atomic=True,
            )
        return self.apply_goal_cancellation_resolution(
            resolved,
            receipts=receipts,
            confirmation_transition=confirmation_transition,
            sid=sid,
            user_text=user_text,
            source=source,
            target_goal_ids_override=target_goal_ids,
            target_responsibility_status="superseded",
        )

    def apply_reflex_cancellation_receipt(
        self,
        receipt: CancellationDispatchReceipt | dict[str, Any],
        *,
        revoked_confirmation: dict[str, Any] | None,
        sid: str | None,
        user_text: str,
        source: str = "reflex_cancellation_reconciliation",
    ) -> list[dict[str, Any]]:
        """Atomically reconcile a fixed-reflex dispatch into canonical Goal state.

        A broad stop is selected by deterministic operational policy, not by the
        semantic Core.  The receipt therefore owns request/interaction scope,
        while the host's committed Goal records own request-to-Goal binding.
        This transaction updates only Goals for which those two evidence sets
        intersect.  Request-level provider failures, non-interruptible work,
        host-only preflight cancellation, and stale/unselected work remain
        explicitly recoverable/uncertain rather than being rewritten as a
        successful cancellation.
        """

        if not self.enabled:
            return []
        validated = (
            receipt
            if isinstance(receipt, CancellationDispatchReceipt)
            else CancellationDispatchReceipt.model_validate(receipt)
        )
        if validated.requested_scope in {"none", "specific_goal"}:
            raise ValueError(
                "fixed reflex reconciliation requires a broad cancellation scope"
            )
        confirmation_evidence = dict(revoked_confirmation or {})
        confirmation_id = str(
            confirmation_evidence.get("confirmation_id") or ""
        ).strip()

        def binding_keys(values: Any) -> set[tuple[str, str]]:
            return {
                (str(item.interaction_id), str(item.request_id))
                for item in values
            }

        selected_keys = binding_keys(validated.selected_request_bindings)
        non_interruptible_keys = binding_keys(
            validated.non_interruptible_request_bindings
        )
        provider_failure_keys = {
            (str(item.interaction_id), str(item.request_id))
            for item in validated.provider_cancel_failure_evidence
        }
        failed_keys = non_interruptible_keys | provider_failure_keys
        affected_goal_ids = set(validated.affected_goal_ids)
        receipt_interactions = {
            *validated.interaction_ids,
            *validated.host_interaction_ids,
        }
        host_cancel_interactions = set(
            validated.host_task_cancel_requested_interaction_ids
        )
        runtime_dispatch_uncertain = any(
            str(item).startswith("capability_runtime:")
            for item in validated.dispatch_failures
        )
        output_dispatch_uncertain = any(
            str(item).startswith(
                ("output_invalidation:", "output_reinvalidation:")
            )
            for item in validated.dispatch_failures
        )
        emergency = dict(validated.emergency_stop_evidence or {})
        emergency_output = emergency.get("output")
        if not isinstance(emergency_output, dict):
            emergency_output = {}
        safe_idle_verified = bool(
            emergency.get("postcondition_confirmed") is True
            or (
                emergency.get("status") == "success"
                and all(
                    emergency_output.get(key) is True
                    for key in ("stopped", "emergency", "safe_idle")
                )
            )
        )
        receipt_payload = validated.model_dump(mode="json", exclude_none=True)

        def goal_id_for(context: dict[str, Any]) -> str:
            goal = self._semantic_goal_from_context(context)
            return str(goal.goal_id or "").strip()

        def context_request_skills(
            metadata: dict[str, Any],
        ) -> dict[str, str]:
            result: dict[str, str] = {}
            planned = metadata.get("planned_capabilities")
            if not isinstance(planned, list):
                return result
            for item in planned:
                if not isinstance(item, dict):
                    continue
                request_id = str(item.get("request_id") or "").strip()
                capability_id = str(item.get("capability_id") or "").strip()
                if request_id:
                    result[request_id] = capability_id
            return result

        candidate_contexts: list[dict[str, Any]] = []
        for context in self._task_contexts:
            goal_id = goal_id_for(context)
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            interaction_id = str(metadata.get("interaction_id") or "").strip()
            confirmation = context.get("confirmation")
            if not isinstance(confirmation, dict):
                confirmation = {}
            bound_confirmation_id = str(
                confirmation.get("confirmation_id")
                or metadata.get("confirmation_id")
                or ""
            ).strip()
            if (
                goal_id in affected_goal_ids
                or (interaction_id and interaction_id in receipt_interactions)
                or (
                    confirmation_id
                    and bound_confirmation_id == confirmation_id
                )
            ):
                candidate_contexts.append(context)

        def mutate() -> list[dict[str, Any]]:
            timestamp_ms = _now_ms()
            results: list[dict[str, Any]] = []
            summaries: dict[str, dict[str, Any]] = {}

            for context in candidate_contexts:
                goal_id = goal_id_for(context)
                if not goal_id:
                    continue
                previous_status = str(context.get("status") or "open").lower()
                if previous_status in _DONE_TASK_STATUSES:
                    results.append(
                        {
                            "goal_id": goal_id,
                            "applied": True,
                            "state_change": "terminal_state_unchanged",
                            "status": previous_status,
                        }
                    )
                    continue

                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                interaction_id = str(metadata.get("interaction_id") or "").strip()
                remaining = set(
                    self._string_list(
                        metadata.get("remaining_request_ids")
                        or metadata.get("request_ids")
                    )
                )
                request_statuses = metadata.get("request_statuses")
                if not isinstance(request_statuses, dict):
                    request_statuses = {}
                request_statuses = {
                    str(key): str(value)
                    for key, value in request_statuses.items()
                }
                skills_by_request = context_request_skills(metadata)

                confirmation = context.get("confirmation")
                if not isinstance(confirmation, dict):
                    confirmation = {}
                bound_confirmation_id = str(
                    confirmation.get("confirmation_id")
                    or metadata.get("confirmation_id")
                    or ""
                ).strip()
                confirmation_cancelled = bool(
                    confirmation_id
                    and bound_confirmation_id == confirmation_id
                )

                selected_for_goal = {
                    request_id
                    for bound_interaction, request_id in selected_keys
                    if (
                        not interaction_id
                        or bound_interaction == interaction_id
                    )
                    and (not remaining or request_id in remaining)
                }
                failed_for_goal = {
                    request_id
                    for bound_interaction, request_id in failed_keys
                    if (
                        not interaction_id
                        or bound_interaction == interaction_id
                    )
                    and (not remaining or request_id in remaining)
                }

                known_cancelled = selected_for_goal - failed_for_goal
                uncertain = set(failed_for_goal)
                uncertainty_reasons: list[str] = []

                if runtime_dispatch_uncertain and (
                    interaction_id in receipt_interactions
                    or goal_id in affected_goal_ids
                ):
                    uncertain.update(remaining or selected_for_goal)
                    uncertainty_reasons.append("runtime_dispatch_failure")
                if (
                    interaction_id in host_cancel_interactions
                    and not selected_for_goal
                ):
                    uncertain.update(remaining)
                    uncertainty_reasons.append(
                        "host_workflow_cancel_requested_unknown_start"
                    )
                if validated.requested_scope in {
                    "current_interaction",
                    "global_emergency",
                }:
                    unselected = remaining - selected_for_goal
                    if unselected and not confirmation_cancelled:
                        uncertain.update(unselected)
                        uncertainty_reasons.append(
                            "broad_scope_request_not_in_runtime_receipt"
                        )
                if output_dispatch_uncertain:
                    speech_requests = {
                        request_id
                        for request_id, capability_id in skills_by_request.items()
                        if capability_id == "chromie.speak"
                    }
                    affected_speech = speech_requests.intersection(
                        remaining or speech_requests
                    )
                    if affected_speech and validated.effective_scope in {
                        "output_only",
                        "current_interaction",
                        "global_emergency",
                    }:
                        uncertain.update(affected_speech)
                        known_cancelled.difference_update(affected_speech)
                        uncertainty_reasons.append(
                            "output_invalidation_failure"
                        )

                # A request cannot be both proven cancelled and uncertain.
                # Broad dispatch failures may retroactively make an otherwise
                # selected request unknown, so uncertainty always dominates.
                known_cancelled.difference_update(uncertain)

                if confirmation_cancelled:
                    confirmation_request_ids = set(
                        self._string_list(
                            confirmation.get("request_ids")
                            or metadata.get("confirmation_request_ids")
                        )
                    )
                    known_cancelled.update(confirmation_request_ids)
                    remaining_after = set()
                    new_status = "cancelled"
                    plan_status = "cancelled_by_operational_interrupt"
                    state_change = "confirmation_cancelled"
                else:
                    remaining_after = remaining - known_cancelled
                    if uncertain:
                        remaining_after.update(uncertain)
                        new_status = "recoverable"
                        plan_status = "cancellation_uncertain"
                        state_change = "cancellation_uncertain"
                    elif known_cancelled and remaining and not remaining_after:
                        new_status = "cancelled"
                        plan_status = "cancelled"
                        state_change = "cancelled"
                    elif known_cancelled:
                        new_status = "recoverable"
                        plan_status = "partially_cancelled"
                        state_change = "partially_cancelled"
                    elif validated.effective_scope == "output_only":
                        # Pre-action/progress speech may cover an embodied Goal
                        # without belonging to that Goal's committed execution
                        # request set. Stopping that shared output must not
                        # rewrite the embodied Goal as cancelled or uncertain.
                        context["metadata"] = {
                            **metadata,
                            "reflex_cancellation_source_turn_id": (
                                validated.source_turn_id
                            ),
                            "reflex_cancellation_scope": (
                                validated.requested_scope
                            ),
                            "reflex_cancellation_effective_scope": (
                                validated.effective_scope
                            ),
                            "reflex_cancellation_receipt": receipt_payload,
                            "output_cancellation_recorded": True,
                        }
                        context["updated_ms"] = timestamp_ms
                        results.append(
                            {
                                "goal_id": goal_id,
                                "applied": True,
                                "state_change": (
                                    "output_cancelled_goal_execution_unchanged"
                                ),
                                "status": previous_status,
                            }
                        )
                        continue
                    elif (
                        interaction_id in host_cancel_interactions
                        or goal_id in affected_goal_ids
                    ):
                        new_status = "recoverable"
                        plan_status = "cancellation_uncertain"
                        state_change = "cancellation_uncertain"
                        uncertainty_reasons.append(
                            "cancellation_receipt_has_no_bound_request"
                        )
                    else:
                        results.append(
                            {
                                "goal_id": goal_id,
                                "applied": True,
                                "state_change": "no_goal_owned_work_selected",
                                "status": previous_status,
                            }
                        )
                        continue

                for request_id in known_cancelled:
                    request_statuses[request_id] = "cancelled"
                for request_id in uncertain:
                    request_statuses[request_id] = "cancellation_uncertain"

                context["status"] = new_status
                context["commitment_state"] = (
                    self._commitment_state_for_status(new_status)
                )
                context["plan_status"] = plan_status
                if confirmation_cancelled:
                    context["confirmation"] = {
                        **confirmation,
                        "status": "operational_interrupt",
                        "resolved_ms": timestamp_ms,
                    }
                context["metadata"] = {
                    **metadata,
                    "remaining_request_ids": sorted(remaining_after),
                    "request_statuses": request_statuses,
                    "reflex_cancellation_source_turn_id": (
                        validated.source_turn_id
                    ),
                    "reflex_cancellation_scope": validated.requested_scope,
                    "reflex_cancellation_effective_scope": (
                        validated.effective_scope
                    ),
                    "reflex_cancelled_request_ids": sorted(known_cancelled),
                    "reflex_uncertain_request_ids": sorted(uncertain),
                    "reflex_cancellation_uncertainty_reasons": list(
                        dict.fromkeys(uncertainty_reasons)
                    ),
                    "reflex_cancellation_receipt": receipt_payload,
                    "emergency_stop_status": str(
                        emergency.get("status") or ""
                    ),
                    "safe_idle_verified": safe_idle_verified,
                }
                context["updated_ms"] = timestamp_ms
                summaries[goal_id] = {
                    "status": new_status,
                    "state_change": state_change,
                    "known_cancelled": sorted(known_cancelled),
                    "uncertain": sorted(uncertain),
                    "remaining": sorted(remaining_after),
                }
                results.append(
                    {
                        "goal_id": goal_id,
                        "applied": True,
                        "status": new_status,
                        "state_change": state_change,
                        "cancelled_request_ids": sorted(known_cancelled),
                        "uncertain_request_ids": sorted(uncertain),
                        "remaining_request_ids": sorted(remaining_after),
                    }
                )

            for task in self._pending_tasks:
                task_metadata = task.get("metadata")
                if not isinstance(task_metadata, dict):
                    continue
                task_goal_id = str(task_metadata.get("goal_id") or "").strip()
                summary = summaries.get(task_goal_id)
                if summary is not None:
                    task["status"] = summary["status"]
                    task["updated_ms"] = timestamp_ms
                    statuses = task_metadata.get("request_statuses")
                    if not isinstance(statuses, dict):
                        statuses = {}
                    statuses = {str(key): str(value) for key, value in statuses.items()}
                    for request_id in summary["known_cancelled"]:
                        statuses[request_id] = "cancelled"
                    for request_id in summary["uncertain"]:
                        statuses[request_id] = "cancellation_uncertain"
                    task["metadata"] = {
                        **task_metadata,
                        "remaining_request_ids": list(summary["remaining"]),
                        "request_statuses": statuses,
                        "reflex_cancellation_source_turn_id": (
                            validated.source_turn_id
                        ),
                        "reflex_cancellation_scope": validated.requested_scope,
                        "reflex_cancellation_receipt": receipt_payload,
                    }
                    continue
                if (
                    confirmation_id
                    and task_metadata.get("confirmation_id") == confirmation_id
                ):
                    task["status"] = "cancelled"
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **task_metadata,
                        "reflex_cancellation_source_turn_id": (
                            validated.source_turn_id
                        ),
                        "reflex_cancellation_scope": validated.requested_scope,
                    }

            results.append(
                {
                    "operation": "fixed_reflex_receipt_reconciliation",
                    "applied": True,
                    "requested_scope": validated.requested_scope,
                    "effective_scope": validated.effective_scope,
                    "affected_goal_ids": sorted(summaries),
                    "safe_idle_verified": safe_idle_verified,
                    "confirmation_cancelled": bool(confirmation_id),
                }
            )
            return results

        return self._commit_semantic_state_transaction(
            mutate,
            rollback_reason="atomic_reflex_cancellation_transaction_rolled_back",
            persistence_failure_reason=(
                "atomic_reflex_cancellation_persistence_failed"
            ),
        )

    def apply_goal_association_resolution(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        sid: str | None,
        user_text: str,
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

    def apply_planner_information_gaps(
        self,
        gaps_by_goal_id: dict[str, list[PlannerInformationGap | dict[str, Any]]],
        *,
        turn_id: str,
        sid: str | None,
        user_text: str,
        source: str = "fast_planner_information_gap",
    ) -> list[dict[str, Any]]:
        """Attach Planner-owned blocking needs without revising Goal meaning.

        Goal Association has already committed semantic identity. This atomic
        host adapter only joins Planner Responsibility provenance to those exact
        Goal IDs and exposes the pending question to the next turn's Context.
        """

        if not self.enabled or not gaps_by_goal_id:
            return []
        normalized: dict[str, list[PlannerInformationGap]] = {}
        for raw_goal_id, raw_gaps in gaps_by_goal_id.items():
            goal_id = " ".join(str(raw_goal_id or "").strip().split())
            if not goal_id:
                raise ValueError("Planner InformationGap requires a canonical Goal ID")
            gaps = [
                item
                if isinstance(item, PlannerInformationGap)
                else PlannerInformationGap.model_validate(item)
                for item in raw_gaps
            ]
            gap_ids = [item.gap_id for item in gaps]
            if not gaps or len(gap_ids) != len(set(gap_ids)):
                raise ValueError(
                    f"Planner InformationGaps for {goal_id!r} must be non-empty and unique"
                )
            normalized[goal_id] = gaps

        def mutate() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            now = _now_ms()
            for ordinal, (goal_id, gaps) in enumerate(normalized.items()):
                operation_id = stable_goal_operation_id(
                    turn_id=turn_id,
                    ordinal=ordinal,
                    relationship="planner_information_gap",
                    target_goal_ids=[goal_id, *[item.gap_id for item in gaps]],
                )
                context = self._task_context_by_goal_id(goal_id)
                if context is None:
                    results.append(
                        {
                            "operation_id": operation_id,
                            "operation": "planner_information_gap",
                            "goal_id": goal_id,
                            "applied": False,
                            "reason": "unknown_target_goal",
                        }
                    )
                    continue
                if self._context_has_operation_id(context, operation_id):
                    results.append(
                        {
                            "operation_id": operation_id,
                            "operation": "planner_information_gap",
                            "goal_id": goal_id,
                            "task_id": context.get("task_id"),
                            "applied": False,
                            "replayed": True,
                            "reason": "operation_already_applied",
                        }
                    )
                    continue

                raw_existing = context.get("open_information_gaps")
                by_id = {
                    str(item.get("gap_id") or ""): dict(item)
                    for item in raw_existing
                    if isinstance(item, dict) and str(item.get("gap_id") or "")
                } if isinstance(raw_existing, list) else {}
                for gap in gaps:
                    by_id[gap.gap_id] = gap.model_dump(mode="json", exclude_none=True)
                context["open_information_gaps"] = list(by_id.values())
                context["pending_questions"] = [
                    str(item.get("description") or "")
                    for item in context["open_information_gaps"]
                    if item.get("blocking") is not False
                    and str(item.get("description") or "")
                ][:4]
                context["status"] = "waiting_for_user"
                context["commitment_state"] = "waiting_for_user"
                context["task_relation"] = "clarify_task"
                context["updated_ms"] = now
                context["last_meaningful_user_turn"] = self._compact_text(
                    user_text,
                    limit=220,
                )
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
                        "operation_id": operation_id,
                        "operation": "planner_information_gap",
                        "goal_version": int(context.get("goal_version") or 1),
                        "ts_ms": now,
                        "reason_summary": "Fast Planner selected user clarification.",
                    }
                )
                context["operation_history"] = history[-24:]
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                context["metadata"] = {
                    **metadata,
                    "source": source,
                    "planner_information_gap_owner": "fast_planner",
                    "planner_information_gap_turn_id": turn_id,
                }
                results.append(
                    {
                        "operation_id": operation_id,
                        "operation": "planner_information_gap",
                        "goal_id": goal_id,
                        "task_id": context.get("task_id"),
                        "gap_ids": [item.gap_id for item in gaps],
                        "applied": True,
                        "goal_version": int(context.get("goal_version") or 1),
                        "status": context.get("status"),
                    }
                )
            return results

        return self._commit_semantic_state_transaction(
            mutate,
            rollback_reason="atomic_planner_gap_transaction_rolled_back",
            persistence_failure_reason="atomic_planner_gap_persistence_failed",
        )

    def _apply_goal_association_resolution_in_memory(
        self,
        resolution: GoalAssociationResolution | dict[str, Any],
        *,
        sid: str | None,
        user_text: str,
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
        candidates = {
            item["goal_id"]: item
            for item in self.goal_association_candidate_snapshots(
                limit=self.max_pending_tasks
            )
            if isinstance(item, dict) and item.get("goal_id")
        }
        operations: list[SemanticTaskOperation] = []
        results: list[dict[str, Any]] = []
        results.extend(self._apply_discourse_resolution_in_memory(resolved))

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
        }
        for association in resolved.associations:
            target_task_ids = [
                str(candidates[goal_id].get("source_task_id") or goal_id)
                for goal_id in association.target_goal_ids
                if goal_id in candidates
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
        source: str | None = None,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        validated: list[SemanticTaskOperation] = []
        for index, item in enumerate(operations):
            if isinstance(item, SemanticTaskOperation):
                validated.append(item)
                continue
            try:
                validated.append(SemanticTaskOperation.model_validate(item))
            except (ValidationError, TypeError) as exc:
                raise ValueError(
                    f"invalid semantic operation at index {index}: {exc}"
                ) from exc
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
                source=source,
                persist=False,
            )
        )

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

    def start_new_conversation(self, *, reason: str, sid: str | None = None) -> dict[str, Any]:
        self._conversation_seq += 1
        self.conversation_id = f"{self.base_conversation_id}-{self._conversation_seq:04d}"
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns.clear()
        self._pending_tasks.clear()
        self._task_contexts.clear()
        self._recent_tool_evidence.clear()
        self._discourse_referents.clear()
        self._discourse_focus.clear()
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
        """Apply only the deterministic hard-idle conversation boundary.

        Follow-up, correction, reset, and new-topic semantics are preserved for
        Goal Association instead of being classified by Host phrases.
        """
        if not self.enabled:
            return {"started_new": False, "reason": "disabled", "conversation_id": self.conversation_id, "sid": sid}

        now = _now_ms()
        self._prune_completed_tasks(now)
        idle_sec = (now - self.last_activity_ms) / 1000.0
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

    def recent_tool_evidence(self) -> list[dict[str, Any]]:
        """Return bounded, schema-validated tool facts for LLM context."""
        if not self.enabled:
            return []
        return [copy.deepcopy(item) for item in self._recent_tool_evidence]

    def discourse_referents(self) -> list[dict[str, Any]]:
        """Return all bounded scoped referents retained for this conversation."""

        if not self.enabled:
            return []
        return [copy.deepcopy(item) for item in self._discourse_referents]

    def discourse_focus(self) -> list[str]:
        """Return the model-authored focus stack, with foreground last."""

        if not self.enabled:
            return []
        known = {
            str(item.get("referent_id") or "")
            for item in self._discourse_referents
        }
        return [item for item in self._discourse_focus if item in known]

    def discourse_snapshot(self) -> dict[str, Any]:
        return {
            "referents": self.discourse_referents(),
            "focus": self.discourse_focus(),
            "authority": "goal_association_llm",
            "host_role": "typed_storage_and_provenance_only",
        }

    def _referent_index(self) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("referent_id") or ""): item
            for item in self._discourse_referents
            if str(item.get("referent_id") or "")
        }

    def _focus_referent(self, referent_id: str) -> None:
        normalized = " ".join(str(referent_id or "").strip().split())
        if not normalized:
            return
        focus = [item for item in self._discourse_focus if item != normalized]
        focus.append(normalized)
        self._discourse_focus = deque(
            focus[-self.max_discourse_focus :],
            maxlen=self.max_discourse_focus,
        )

    def _remove_focus(self, referent_id: str) -> None:
        self._discourse_focus = deque(
            [item for item in self._discourse_focus if item != referent_id],
            maxlen=self.max_discourse_focus,
        )

    def _apply_discourse_resolution_in_memory(
        self,
        resolution: GoalAssociationResolution,
    ) -> list[dict[str, Any]]:
        """Apply only model-authored scoped referent and focus mutations."""

        results: list[dict[str, Any]] = []
        index = self._referent_index()

        def replace_referent(referent: DiscourseReferent) -> None:
            payload = referent.model_dump(mode="json", exclude_none=True)
            retained = [
                item
                for item in self._discourse_referents
                if str(item.get("referent_id") or "") != referent.referent_id
            ]
            retained.append(payload)
            self._discourse_referents = deque(
                retained[-self.max_discourse_referents :],
                maxlen=self.max_discourse_referents,
            )
            index[referent.referent_id] = payload

        for update in resolution.referent_updates:
            if update.operation in {"introduce", "correct"}:
                if update.referent is None:
                    results.append(
                        {
                            "operation": update.operation,
                            "applied": False,
                            "reason": "missing_referent",
                        }
                    )
                    continue
                if update.operation == "correct":
                    for target_id in update.target_referent_ids:
                        current = index.get(target_id)
                        if current is None:
                            results.append(
                                {
                                    "operation": update.operation,
                                    "referent_id": target_id,
                                    "applied": False,
                                    "reason": "unknown_target_referent",
                                }
                            )
                            continue
                        background = DiscourseReferent.model_validate(current).model_copy(
                            update={"status": "background"}
                        )
                        replace_referent(background)
                        self._remove_focus(target_id)
                replace_referent(update.referent)
                self._focus_referent(update.referent.referent_id)
                results.append(
                    {
                        "operation": update.operation,
                        "referent_id": update.referent.referent_id,
                        "applied": True,
                        "state_change": "referent_upserted_and_focused",
                    }
                )
                continue

            status = {
                "focus": "foreground",
                "background": "background",
                "retire": "retired",
            }[update.operation]
            for target_id in update.target_referent_ids:
                current = index.get(target_id)
                if current is None:
                    results.append(
                        {
                            "operation": update.operation,
                            "referent_id": target_id,
                            "applied": False,
                            "reason": "unknown_target_referent",
                        }
                    )
                    continue
                revised = DiscourseReferent.model_validate(current).model_copy(
                    update={"status": status}
                )
                replace_referent(revised)
                if status == "foreground":
                    self._focus_referent(target_id)
                else:
                    self._remove_focus(target_id)
                results.append(
                    {
                        "operation": update.operation,
                        "referent_id": target_id,
                        "applied": True,
                        "state_change": f"referent_{status}",
                    }
                )

        # A successfully resolved reference is itself a model-authored focus event.
        for reference in resolution.resolved_references:
            referent_id = str(reference.referent_id or "").strip()
            if not referent_id:
                continue
            current = index.get(referent_id)
            if current is None:
                results.append(
                    {
                        "operation": "resolve_reference",
                        "referent_id": referent_id,
                        "applied": False,
                        "reason": "unknown_resolved_referent",
                    }
                )
                continue
            focused = DiscourseReferent.model_validate(current).model_copy(
                update={"status": "foreground"}
            )
            replace_referent(focused)
            self._focus_referent(referent_id)
            results.append(
                {
                    "operation": "resolve_reference",
                    "referent_id": referent_id,
                    "surface_form": reference.surface_form,
                    "resolved_value": reference.resolved_value,
                    "applied": True,
                    "state_change": "referent_focused_from_resolution",
                }
            )
        return results

    def verified_tool_memory_index(self) -> list[dict[str, Any]]:
        """Expose provenance and exact bindings, never result contents, to planners."""

        if not self.enabled:
            return []
        now = _now_ms()
        index: list[dict[str, Any]] = []
        for item in self._recent_tool_evidence:
            evidence_id = str(item.get("evidence_id") or "").strip()
            tool_id = str(item.get("tool_id") or "").strip()
            request_args = item.get("request_args")
            if not evidence_id or not tool_id or not isinstance(request_args, dict):
                continue
            if not request_args:
                # A provenance-only record with no original arguments cannot
                # support exact material-binding retrieval. Keep it out of the
                # planner-visible index rather than inviting loose reuse.
                continue
            index.append(
                {
                    "evidence_id": evidence_id,
                    "tool_id": tool_id,
                    "status": str(item.get("status") or ""),
                    "request_args": copy.deepcopy(request_args),
                    "recorded_ms": item.get("recorded_ms"),
                    "age_ms": max(
                        0.0,
                        now - float(item.get("recorded_ms") or now),
                    ),
                    "goal_ids": list(item.get("goal_ids") or []),
                    "canonical_plan_id": str(item.get("canonical_plan_id") or ""),
                    "source": "verified_tool_memory_index",
                }
            )
        return index

    @staticmethod
    def _material_arg_equal(left: Any, right: Any) -> bool:
        if isinstance(left, str) and isinstance(right, str):
            return " ".join(left.strip().casefold().split()) == " ".join(
                right.strip().casefold().split()
            )
        return left == right

    def retrieve_verified_tool_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return one exact verified result after Goal bindings are already resolved."""

        evidence_id = " ".join(str(args.get("evidence_id") or "").strip().split())
        tool_id = " ".join(str(args.get("tool_id") or "").strip().split())
        material_args = args.get("material_args")
        if not isinstance(material_args, dict) or not material_args:
            return {
                "found": False,
                "reason": "material_args_required",
                "evidence_id": evidence_id,
                "tool_id": tool_id,
            }
        max_age_s = float(args.get("max_age_s") or 900.0)
        now = _now_ms()
        for item in reversed(self._recent_tool_evidence):
            if evidence_id and str(item.get("evidence_id") or "") != evidence_id:
                continue
            if tool_id and str(item.get("tool_id") or "") != tool_id:
                continue
            request_args = item.get("request_args")
            if not isinstance(request_args, dict):
                continue
            if not all(
                key in request_args
                and self._material_arg_equal(request_args[key], expected)
                for key, expected in material_args.items()
            ):
                continue
            recorded_ms = float(item.get("recorded_ms") or 0.0)
            age_ms = max(0.0, now - recorded_ms)
            if age_ms > max_age_s * 1000.0:
                return {
                    "found": False,
                    "reason": "matching_memory_stale",
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "tool_id": str(item.get("tool_id") or ""),
                    "request_args": copy.deepcopy(request_args),
                    "age_ms": age_ms,
                    "max_age_s": max_age_s,
                }
            return {
                "found": True,
                "reason": "exact_verified_match",
                "evidence_id": str(item.get("evidence_id") or ""),
                "tool_id": str(item.get("tool_id") or ""),
                "request_args": copy.deepcopy(request_args),
                "recorded_ms": recorded_ms,
                "age_ms": age_ms,
                "data": copy.deepcopy(item.get("data") or {}),
                "source": "conversation_verified_tool_memory",
            }
        return {
            "found": False,
            "reason": "no_exact_verified_match",
            "evidence_id": evidence_id,
            "tool_id": tool_id,
            "material_args": copy.deepcopy(material_args),
        }

    def _record_tool_evidence(self, metadata: dict[str, Any]) -> None:
        bundle = metadata.get("execution_outcome_bundle")
        if not isinstance(bundle, dict):
            return
        user_request = self._compact_text(
            str(metadata.get("user_request") or ""),
            limit=500,
        )
        canonical_plan_id = str(
            metadata.get("canonical_plan_id")
            or bundle.get("canonical_plan_id")
            or ""
        ).strip()
        goal_ids = self._string_list(metadata.get("source_goal_ids"))
        if not goal_ids:
            outcomes = bundle.get("goal_outcomes")
            if isinstance(outcomes, list):
                goal_ids = [
                    str(item.get("goal_id"))
                    for item in outcomes
                    if isinstance(item, dict) and str(item.get("goal_id") or "").strip()
                ]
        evidence_items = bundle.get("evidence")
        if not isinstance(evidence_items, list):
            return
        known_ids = {
            str(item.get("evidence_id") or "")
            for item in self._recent_tool_evidence
        }
        for raw in evidence_items:
            if not isinstance(raw, dict):
                continue
            observation = raw.get("observation")
            if not isinstance(observation, dict):
                continue
            if observation.get("status") != "available":
                continue
            if observation.get("schema_validated") is not True:
                continue
            data = observation.get("data")
            if not isinstance(data, dict) or not data:
                continue
            evidence_id = str(raw.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in known_ids:
                continue
            evidence_metadata = raw.get("metadata")
            if not isinstance(evidence_metadata, dict):
                evidence_metadata = {}
            request_args = evidence_metadata.get("request_args")
            if not isinstance(request_args, dict):
                request_args = {}
            entry = {
                "evidence_id": evidence_id,
                "tool_id": str(raw.get("capability_id") or "").strip(),
                "status": str(raw.get("status") or "").strip(),
                "data": self._json_safe(data),
                "request_args": self._json_safe(request_args),
                "safety_class": str(
                    evidence_metadata.get("safety_class") or ""
                ).strip(),
                "recorded_ms": _now_ms(),
                "user_request": user_request,
                "goal_ids": goal_ids,
                "canonical_plan_id": canonical_plan_id,
                "source": "trusted_execution_outcome",
            }
            self._recent_tool_evidence.append(entry)
            known_ids.add(evidence_id)

    def _memory_activation_texts(self) -> list[str]:
        """Project current context into bounded deterministic Memory cues."""

        values: list[str] = []
        latest_user = self._latest_turn("user")
        if latest_user:
            values.append(str(latest_user.get("text") or ""))
        for context in self._active_task_contexts()[-4:]:
            values.extend(
                [
                    str(context.get("goal") or ""),
                    str(context.get("last_meaningful_user_turn") or ""),
                ]
            )
            semantic_goal = context.get("semantic_goal")
            if isinstance(semantic_goal, dict):
                values.extend(
                    [
                        str(semantic_goal.get("description") or ""),
                        str(semantic_goal.get("object") or ""),
                    ]
                )
        referents = {
            str(item.get("referent_id") or ""): item
            for item in self._discourse_referents
            if isinstance(item, dict)
        }
        for referent_id in self.discourse_focus()[-4:]:
            referent = referents.get(referent_id) or {}
            values.extend(
                [
                    str(referent.get("canonical_value") or ""),
                    str(referent.get("entity_type") or ""),
                ]
            )
        return [
            self._compact_text(value, limit=260)
            for value in values
            if str(value or "").strip()
        ][:16]

    def session_memory(self) -> dict[str, Any]:
        active_tasks = self._active_pending_tasks()
        active_task_contexts = self._active_task_contexts()
        current_task_context = self._current_task_context()
        latest_user = self._latest_turn("user")
        latest_assistant = self._latest_turn("assistant")
        activation_texts = self._memory_activation_texts()
        extracted_memory = self._memory_prompt_builder.build(
            self._memory_store,
            limit=12,
            activation_texts=activation_texts,
        )
        durable_entries = self._durable_memory.prompt_entries(
            limit=12,
            activation_texts=activation_texts,
        )
        combined_entries = rank_memory_prompt_entries(
            [*durable_entries, *extracted_memory["entries"]],
            activation_texts=activation_texts,
            limit=12,
        )
        durable_entries = rank_memory_prompt_entries(
            durable_entries,
            activation_texts=activation_texts,
            limit=8,
        )
        combined_summary_lines = [
            f"- {entry['text']}" for entry in combined_entries if entry.get("text")
        ]
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
            "recent_tool_evidence": self.recent_tool_evidence(),
            "verified_tool_memory_index": self.verified_tool_memory_index(),
            "discourse_referents": self.discourse_referents(),
            "discourse_focus": self.discourse_focus(),
            "extracted_memory": combined_entries,
            "memory_summary": (
                "\n".join(combined_summary_lines) if combined_summary_lines else "None"
            ),
            "memory_selection": {
                "policy": "context_relevance_then_recency",
                "activation_source_count": len(activation_texts),
            },
            "durable_profile_memory": {
                "enabled": self.durable_memory_enabled,
                "entries": durable_entries,
                "protected_storage": "owner_local_mode_0600",
                "last_error": self._durable_memory.last_error,
            },
            "forgetting_policy": {
                "conversation_boundary_clears_history_and_tasks": True,
                "conversation_boundary_clears_durable_profile_memory": False,
                "durable_profile_requires_explicit_forget_or_clear": True,
                "hard_idle_timeout_sec": self.hard_idle_timeout_sec,
                "completed_task_retention_sec": self.completed_task_retention_sec,
                "reflection_memory_max_ttl_sec": self.reflection_memory_max_ttl_sec,
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
            "recent_goal_snapshots": self.recent_goal_snapshots(),
            "current_task_context": self._current_task_context(),
            "discourse_referents": self.discourse_referents(),
            "discourse_focus": self.discourse_focus(),
            "discourse": self.discourse_snapshot(),
            "recent_tool_evidence": self.recent_tool_evidence(),
            "verified_tool_memory_index": self.verified_tool_memory_index(),
            "extracted_memory": self._memory_store.snapshot(),
            "durable_profile_memory": {
                "enabled": self.durable_memory_enabled,
                "path": str(self.durable_memory_path),
                "entries": self._durable_memory.snapshot(),
                "last_error": self._durable_memory.last_error,
            },
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
                "durable_memory_max_entries": self.durable_memory_max_entries,
                "max_tool_evidence": self.max_tool_evidence,
                "max_discourse_referents": self.max_discourse_referents,
                "max_discourse_focus": self.max_discourse_focus,
                "completed_task_retention_sec": self.completed_task_retention_sec,
                "reflection_memory_max_ttl_sec": self.reflection_memory_max_ttl_sec,
            },
        }

    def clear(self, *, reason: str = "manual_clear") -> None:
        self.start_new_conversation(reason=reason)

    def _matching_user_turn(
        self,
        *,
        sid: str | None,
        text: str,
    ) -> dict[str, Any] | None:
        normalized_sid = str(sid or "").strip()
        for turn in reversed(self._turns):
            if turn.get("role") != "user":
                continue
            if normalized_sid and str(turn.get("sid") or "").strip() != normalized_sid:
                continue
            if str(turn.get("text") or "") != text:
                continue
            return turn
        return None

    def user_turn_snapshot(self, sid: str | None) -> dict[str, Any]:
        """Return one bounded accepted user-turn record by SID.

        This is transport evidence only.  It is used by observability/failure
        paths that may not have received a normal response ``experience_context``;
        it never creates or changes Goal semantics.
        """

        normalized_sid = str(sid or "").strip()
        if not normalized_sid:
            return {}
        for turn in reversed(self._turns):
            if (
                turn.get("role") == "user"
                and str(turn.get("sid") or "").strip() == normalized_sid
            ):
                return copy.deepcopy(dict(turn))
        return {}

    def record_accepted_user_turn(
        self,
        sid: str | None,
        text: str | None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Publish admitted dialogue immediately without inventing semantic state.

        This is conversational evidence only. It deliberately does not create or
        mutate a Goal/Task, extract semantic memory, or claim that Goal Association
        has completed. A later ``record_user_turn`` enriches this same SID after
        the model-owned semantic path resolves.
        """

        if not self.enabled:
            return
        compact = self._compact_text(text)
        if not compact:
            return
        existing = self._matching_user_turn(sid=sid, text=compact)
        accepted_metadata = {
            "accepted_dialogue_evidence": True,
            **dict(metadata or {}),
        }
        if existing is not None:
            current_metadata = existing.get("metadata")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            existing["metadata"] = {**current_metadata, **accepted_metadata}
            self.last_activity_ms = _now_ms()
            return
        self._turns.append(
            {
                "role": "user",
                "sid": sid,
                "text": compact,
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": accepted_metadata,
            }
        )
        self.last_activity_ms = _now_ms()

    def record_user_turn(
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
        turn_metadata = dict(metadata or {})
        semantic_operations = self._semantic_operations_from_metadata(turn_metadata)
        if semantic_operations:
            operation_results = self.apply_semantic_task_operations(
                semantic_operations,
                sid=sid,
                user_text=compact,
                source=str(turn_metadata.get("source") or "goal_interpreter"),
            )
            turn_metadata["semantic_task_operation_results"] = operation_results
        existing = self._matching_user_turn(sid=sid, text=compact)
        if existing is None:
            self._turns.append(
                {
                    "role": "user",
                    "sid": sid,
                    "text": compact,
                    "ts_ms": _now_ms(),
                    "conversation_id": self.conversation_id,
                    "metadata": turn_metadata,
                }
            )
        else:
            existing_metadata = existing.get("metadata")
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}
            existing["metadata"] = {**existing_metadata, **turn_metadata}
        self._memory_store.add_many(
            self._memory_extractor.extract_user_turn(
                sid=sid,
                text=compact,
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
        if metadata.get("transient_responsibility") is True:
            return {}
        plan = metadata.get("canonical_plan")
        if not isinstance(plan, dict):
            if (
                metadata.get("planning_result") == "direct_response"
                and metadata.get("planless_direct_response") is True
            ):
                goal_ids = metadata.get("goal_ids")
                if isinstance(goal_ids, str):
                    goal_ids = [goal_ids]
                if isinstance(goal_ids, list):
                    return {
                        goal_id: {"goal_id": goal_id, "disposition": "respond"}
                        for value in goal_ids
                        if (goal_id := " ".join(str(value or "").strip().split()))
                    }
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
        are left for their goal-scoped CapabilityRequest evidence.
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
                if disposition == "refused":
                    self._set_goal_responsibility_status(
                        context,
                        "refused",
                        source="canonical_plan_refusal",
                    )
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
        planned_capabilities: list[dict[str, Any]],
        confirmation_pending: bool,
        interaction_id: str = "",
        turn_id: str = "",
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        planner_reentry_responsibilities: list[dict[str, Any]] | None = None,
        planner_reentry_language: str = "",
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
            "planned_capabilities": [dict(item) for item in planned_capabilities],
            "interaction_id": str(interaction_id or "").strip(),
            "turn_id": str(turn_id or "").strip(),
            "canonical_plan_id": str(canonical_plan_id or "").strip(),
            "canonical_plan_fingerprint": str(
                canonical_plan_fingerprint or ""
            ).strip(),
            **(
                {
                    "planner_reentry_responsibilities": [
                        self._json_safe(item)
                        for item in planner_reentry_responsibilities
                        if isinstance(item, dict)
                    ],
                    "planner_reentry_language": self._compact_text(
                        planner_reentry_language or "auto", limit=64
                    ),
                }
                if planner_reentry_responsibilities
                else {}
            ),
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
        for raw_request in data.get("capabilities", []) or data.get("actions", []) or []:
            if isinstance(raw_request, dict):
                request = raw_request
            else:
                request = {
                    "request_id": getattr(raw_request, "request_id", None),
                    "capability_id": getattr(raw_request, "capability_id", None),
                    "capability_id": getattr(raw_request, "capability_id", None),
                    "metadata": getattr(raw_request, "metadata", None),
                }
            request_id = str(request.get("request_id") or "").strip()
            if not request_id or request_id not in confirmed:
                continue
            metadata = request.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            capability_id = str(
                request.get("capability_id")
                or request.get("type")
                or request.get("target")
                or "action"
            ).strip()
            for goal_id in self._string_list(metadata.get("source_goal_ids")):
                by_goal.setdefault(goal_id, []).append(
                    {"request_id": request_id, "capability_id": capability_id}
                )
                scoped_request_ids.add(request_id)

        timestamp_ms = _now_ms()
        goal_ids: list[str] = []
        for goal_id, requests in by_goal.items():
            request_ids = list(
                dict.fromkeys(item["request_id"] for item in requests)
            )
            summary = ", ".join(
                dict.fromkeys(item["capability_id"] for item in requests)
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
                # Runtime has scheduled it. record_interaction_response performs that
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
                planned_capabilities = context["metadata"].get("planned_capabilities")
                speaking_only = bool(planned_capabilities) and all(
                    isinstance(item, dict)
                    and str(item.get("capability_id") or "") == "chromie.speak"
                    for item in planned_capabilities
                ) if isinstance(planned_capabilities, list) else False
                if task_status == "done" and speaking_only:
                    self._set_goal_responsibility_status(
                        context,
                        "satisfied",
                        source="speaking_delivery_reconciliation",
                        evidence_refs=[request_id],
                    )

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
        """Atomically attach exact execution evidence to bound Work records.

        ExecutionOutcome is immutable historical truth about what execution did.
        This method updates Work/runtime projections and evidence only; it never
        decides whether the semantic Responsibility is satisfied.
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
        evidence_by_id = {
            item.evidence_id: item for item in validated.evidence
        }
        results: list[dict[str, Any]] = []
        try:
            for outcome in validated.goal_outcomes:
                context, matching_tasks = bound_records[outcome.goal_id]
                referenced_evidence = [
                    evidence_by_id[evidence_id]
                    for evidence_id in outcome.evidence_ids
                    if evidence_id in evidence_by_id
                ]
                retryable_safe_read = bool(referenced_evidence) and all(
                    item.metadata.get("retryable_safe_read") is True
                    for item in referenced_evidence
                )
                qualification = self._completion_qualification_summary(
                    validated, outcome
                )
                completion_unqualified = bool(
                    outcome.status == "completed"
                    and qualification["required"]
                    and not qualification["established"]
                )
                lifecycle_status = (
                    "recoverable"
                    if completion_unqualified
                    or (
                        retryable_safe_read
                        and outcome.status
                        in {"failed", "timed_out", "cancelled", "not_run"}
                    )
                    else status_projection[outcome.status]
                )
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
                    "completion_qualification_required": qualification["required"],
                    "completion_qualification_established": qualification["established"],
                    "completion_qualifications": qualification["qualifications"],
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
                    "retryable_safe_read": retryable_safe_read,
                    "completion_qualification_required": qualification["required"],
                    "completion_qualification_established": qualification["established"],
                }

                matched_pending = 0
                for task in matching_tasks:
                    task_metadata = task.get("metadata")
                    if not isinstance(task_metadata, dict):
                        raise RuntimeError(
                            "pending task metadata must be an object during outcome reconciliation"
                        )
                    task["status"] = lifecycle_status
                    task["updated_ms"] = timestamp_ms
                    task["metadata"] = {
                        **task_metadata,
                        "execution_outcome_id": validated.outcome_id,
                        "execution_outcome_fingerprint": fingerprint,
                        "execution_outcome_status": outcome.status,
                        "execution_evidence_ids": list(outcome.evidence_ids),
                        "retryable_safe_read": retryable_safe_read,
                        "completion_qualification_required": qualification["required"],
                        "completion_qualification_established": qualification["established"],
                    }
                    matched_pending += 1

                results.append(
                    {
                        "goal_id": outcome.goal_id,
                        "status": outcome.status,
                        "work_status": lifecycle_status,
                        "outcome_id": validated.outcome_id,
                        "applied": True,
                        "completion_qualification_required": qualification["required"],
                        "completion_qualification_established": qualification["established"],
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

    @staticmethod
    def _completion_qualification_summary(
        bundle: ExecutionOutcomeBundle,
        outcome: Any,
    ) -> dict[str, Any]:
        return goal_completion_qualification_summary(bundle, outcome)

    def reconcile_fast_communicative_goal_completion(
        self,
        sid: str | None,
        goal_ids: list[str],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Close no-work speech Goals from delivered Fast Planner speech evidence.

        Fast Planner may deliver a ``complete_response`` before Goal Association
        has canonical Goal IDs.  The Interaction Runtime binds that already-trusted
        ``chromie.speak`` completion back to Goal IDs after GA commits.  This method
        performs only lifecycle reconciliation: it never decides wording, semantic
        ownership, or whether an Activity was complete.
        """

        if not self.enabled:
            return []
        evidence = dict(metadata or {})
        if str(evidence.get("delivery_role") or "") != "complete_response":
            return []
        normalized_sid = " ".join(str(sid or "").strip().split())
        activity_id = " ".join(
            str(evidence.get("fast_activity_id") or "").strip().split()
        )
        evidence_ref = (
            f"fast_communicative:{activity_id}"
            if activity_id
            else "fast_communicative:delivered"
        )
        results: list[dict[str, Any]] = []
        changed = False
        now = _now_ms()
        for raw_goal_id in goal_ids:
            goal_id = " ".join(str(raw_goal_id or "").strip().split())
            if not goal_id:
                continue
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                results.append(
                    {
                        "goal_id": goal_id,
                        "changed": False,
                        "reason": "unknown_goal",
                    }
                )
                continue
            if normalized_sid:
                related_sids = {
                    " ".join(str(item or "").strip().split())
                    for item in context.get("related_sids") or []
                    if str(item or "").strip()
                }
                if related_sids and normalized_sid not in related_sids:
                    results.append(
                        {
                            "goal_id": goal_id,
                            "changed": False,
                            "reason": "delivery_turn_does_not_match_goal",
                        }
                    )
                    continue
            goal = self._semantic_goal_from_context(context)
            goal_metadata = goal.metadata if isinstance(goal.metadata, dict) else {}
            if str(goal_metadata.get("output_mode") or "") != "speech":
                results.append(
                    {
                        "goal_id": goal_id,
                        "changed": False,
                        "reason": "goal_requires_nontrivial_completion_evidence",
                    }
                )
                continue
            previous = self._goal_responsibility_status(context)
            if previous != "open":
                results.append(
                    {
                        "goal_id": goal_id,
                        "previous_status": previous,
                        "responsibility_status": previous,
                        "changed": False,
                        "reason": "responsibility_already_terminal",
                    }
                )
                continue

            self._set_goal_responsibility_status(
                context,
                "satisfied",
                source="fast_planner_communicative_completion",
                evidence_refs=[evidence_ref],
            )
            context["status"] = "done"
            context["commitment_state"] = "completed"
            context["plan_status"] = "done"
            context["updated_ms"] = now
            evidence_summary = context.get("evidence_summary")
            if not isinstance(evidence_summary, dict):
                evidence_summary = {}
            evidence_summary["fast_communicative_completion"] = {
                **evidence,
                "evidence_ref": evidence_ref,
                "goal_id": goal_id,
            }
            context["evidence_summary"] = evidence_summary
            changed = True
            results.append(
                {
                    "goal_id": goal_id,
                    "previous_status": previous,
                    "responsibility_status": "satisfied",
                    "work_status": "done",
                    "changed": True,
                    "evidence_ref": evidence_ref,
                }
            )

        if changed:
            self._persist_task_contexts_if_enabled()
            self.last_activity_ms = now
        return results


    def reconcile_execution_outcome_responsibilities(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        """Reconcile current Responsibility truth from trusted execution evidence.

        A completed execution is evidence, not Goal truth by itself. This explicit
        boundary performs the current satisfaction judgment after the immutable
        outcome has already been recorded. Non-completed Work leaves the Goal open
        so later evidence, replanning, or provider changes may still advance it.
        """

        if not self.enabled:
            return []
        validated = ExecutionOutcomeBundle.model_validate(bundle)
        results: list[dict[str, Any]] = []
        changed = False
        for outcome in validated.goal_outcomes:
            context = self._task_context_by_goal_id(outcome.goal_id)
            if context is None:
                raise ValueError(
                    "responsibility reconciliation references unknown Goal: "
                    f"{outcome.goal_id}"
                )
            evidence_summary = context.get("evidence_summary")
            if not isinstance(evidence_summary, dict):
                raise ValueError(
                    "responsibility reconciliation requires recorded execution evidence"
                )
            recorded = evidence_summary.get("execution_outcome")
            if not isinstance(recorded, dict) or recorded.get("outcome_id") != validated.outcome_id:
                raise ValueError(
                    "responsibility reconciliation requires the exact recorded outcome"
                )

            previous = self._goal_responsibility_status(context)
            if previous in {"cancelled", "refused", "superseded"}:
                results.append({
                    "goal_id": outcome.goal_id,
                    "previous_status": previous,
                    "responsibility_status": previous,
                    "changed": False,
                    "reason": "semantic_terminal_state_preserved",
                })
                continue

            qualification = self._completion_qualification_summary(
                validated, outcome
            )
            completion_established = bool(
                outcome.status == "completed"
                and (
                    not qualification["required"]
                    or qualification["established"]
                )
            )
            current = "satisfied" if completion_established else "open"
            if current != previous:
                self._set_goal_responsibility_status(
                    context,
                    current,
                    source="execution_outcome_reconciliation",
                    evidence_refs=[validated.outcome_id, *outcome.evidence_ids],
                )
                context["updated_ms"] = _now_ms()
                changed = True
            results.append({
                "goal_id": outcome.goal_id,
                "previous_status": previous,
                "responsibility_status": current,
                "changed": current != previous,
                "execution_status": outcome.status,
                "completion_qualification_required": qualification["required"],
                "completion_qualification_established": qualification["established"],
                "completion_qualifications": qualification["qualifications"],
            })

        if changed:
            self._persist_task_contexts_if_enabled()
            self.last_activity_ms = _now_ms()
        return results

    def apply_reflection_resolution(
        self,
        resolution: ReflectionResolution | dict[str, Any],
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        """Apply bounded future adaptation without rewriting Goal history.

        Responsibility-control actions are valid only while the Responsibility
        remains open. Evidence-bound ``experience``/``calibration`` proposals may
        also learn from terminal history because learning forward does not reopen
        or mutate that history. Online proposals remain non-durable advisory
        Memory; shared/systemic adaptation stays outside this path.
        """

        if not self.enabled:
            return []
        reflected = (
            resolution
            if isinstance(resolution, ReflectionResolution)
            else ReflectionResolution.model_validate(resolution)
        )
        results: list[dict[str, Any]] = []
        memory_entries: list[MemoryEntry] = []
        now = _now_ms()
        responsibility_actions = {"replan", "clarify", "correct_user"}

        for goal_id in reflected.goal_ids:
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                raise ValueError(f"reflection references unknown Goal: {goal_id}")

            evidence_summary = context.get("evidence_summary")
            recorded = (
                evidence_summary.get("execution_outcome")
                if isinstance(evidence_summary, dict)
                else None
            )
            if not isinstance(recorded, dict):
                raise ValueError("reflection requires recorded execution evidence")
            recorded_outcome_id = str(recorded.get("outcome_id") or "").strip()
            allowed_refs = {recorded_outcome_id}
            allowed_refs.update(
                str(item).strip()
                for item in recorded.get("evidence_ids") or []
                if str(item).strip()
            )
            if reflected.actions and (
                not recorded_outcome_id
                or recorded_outcome_id not in reflected.evidence_refs
            ):
                raise ValueError(
                    "reflection actions require the recorded execution outcome reference"
                )
            unknown_refs = set(reflected.evidence_refs) - allowed_refs
            if unknown_refs:
                raise ValueError(
                    "reflection references evidence outside the recorded outcome: "
                    + ",".join(sorted(unknown_refs))
                )

            responsibility_status = self._goal_responsibility_status(context)
            responsibility_open = responsibility_status == "open"
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            history = metadata.get("reflection_history")
            if not isinstance(history, list):
                history = []
            current_reasons = set(reflected.reason_codes)
            repeated_pattern = any(
                current_reasons.intersection(
                    str(item).strip()
                    for item in previous.get("reason_codes") or []
                    if str(item).strip()
                )
                for previous in history
                if isinstance(previous, dict)
            )

            advisory_actions: list[str] = []
            rejected_actions: list[str] = []
            for action in reflected.actions:
                if action in responsibility_actions:
                    if not responsibility_open:
                        rejected_actions.append(action)
                        continue
                    advisory_actions.append(action)

            planner_advisory: dict[str, Any] | None = None
            if advisory_actions:
                planner_advisory = {
                    "opportunity_id": reflected.opportunity_id,
                    "goal_id": goal_id,
                    "actions": advisory_actions,
                    "correction_text": (
                        reflected.correction_text
                        if "correct_user" in advisory_actions
                        else ""
                    ),
                    "reason_codes": list(reflected.reason_codes),
                    "reason_summary": reflected.reason_summary,
                    "evidence_refs": list(reflected.evidence_refs),
                    "authority": "planner_advisory_only",
                }

            applied_actions: list[str] = []
            promoted = 0
            if "propose_memory" in reflected.actions:
                for candidate in reflected.memory_candidates:
                    memory_entries.append(
                        MemoryEntry(
                            scope=candidate.scope,
                            kind=candidate.kind,
                            text=candidate.text,
                            confidence=candidate.confidence,
                            source_sids=[sid] if sid else [],
                            source_turn_ids=[str(recorded.get("turn_id") or "")]
                            if str(recorded.get("turn_id") or "").strip()
                            else [],
                            expires_ms=(
                                now + self.reflection_memory_max_ttl_sec * 1000.0
                            ),
                            persistence_policy="ephemeral",
                        )
                    )
                    promoted += 1
                if promoted:
                    applied_actions.append("propose_memory")

            history.append({
                "opportunity_id": reflected.opportunity_id,
                "actions": list(reflected.actions),
                "planner_advisory_actions": advisory_actions,
                "applied_actions": applied_actions,
                "rejected_actions": rejected_actions,
                "reason_codes": list(reflected.reason_codes),
                "evidence_refs": list(reflected.evidence_refs),
                "memory_candidates": len(reflected.memory_candidates),
                "memory_promoted": promoted,
                "responsibility_status": responsibility_status,
                "terminal_history_learning": bool(
                    not responsibility_open and promoted
                ),
                "ts_ms": now,
            })
            context["metadata"] = {
                **metadata,
                "reflection_history": history[-12:],
            }
            if advisory_actions or applied_actions or responsibility_open:
                context["updated_ms"] = now

            result: dict[str, Any] = {
                "goal_id": goal_id,
                "applied": bool(advisory_actions or applied_actions),
                "actions": list(reflected.actions),
                "planner_advisory_actions": advisory_actions,
                "applied_actions": applied_actions,
                "rejected_actions": rejected_actions,
                "memory_promoted": promoted,
                "repeated_pattern": repeated_pattern,
                "responsibility_status": responsibility_status,
                "future_adaptation": bool(advisory_actions or applied_actions),
                "terminal_history_learning": bool(
                    not responsibility_open and promoted
                ),
            }
            if planner_advisory is not None:
                result["planner_advisory"] = planner_advisory
            if rejected_actions and not applied_actions:
                result["reason"] = "reflection_terminal_responsibility_action_rejected"
            results.append(result)

        if memory_entries:
            self._memory_store.add_many(memory_entries)
        if results:
            self._persist_task_contexts_if_enabled()
            self.last_activity_ms = now
        return results

    def derive_execution_cognitive_opportunities(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        situation_digest: str = "",
    ) -> list[CognitiveOpportunity]:
        """Derive ephemeral cognition opportunities from trusted outcome evidence.

        The result is intentionally not persisted. An opportunity is merely a
        bounded signal that current authoritative state changed enough that
        another cognitive act may be useful. The referenced Goal and Evidence
        remain authoritative in their existing owners.
        """

        if not self.enabled:
            return []
        validated = ExecutionOutcomeBundle.model_validate(bundle)
        opportunities: list[CognitiveOpportunity] = []
        for outcome in validated.goal_outcomes:
            qualification = self._completion_qualification_summary(
                validated, outcome
            )
            if outcome.status == "completed" and (
                not qualification["required"]
                or qualification["established"]
            ):
                continue
            context = self._task_context_by_goal_id(outcome.goal_id)
            if context is None:
                continue
            if self._goal_responsibility_status(context) != "open":
                continue
            evidence_summary = context.get("evidence_summary")
            if not isinstance(evidence_summary, dict):
                continue
            recorded = evidence_summary.get("execution_outcome")
            if (
                not isinstance(recorded, dict)
                or recorded.get("outcome_id") != validated.outcome_id
            ):
                continue
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            retryable_safe_read = metadata.get("retryable_safe_read") is True
            mode = "fast" if retryable_safe_read else "slow"
            qualification_reason_codes = [
                str(reason)
                for row in qualification["qualifications"]
                for reason in row.get("reason_codes", [])
                if str(reason).strip()
            ]
            reason_codes = (
                list(outcome.reason_codes)
                or qualification_reason_codes
                or [
                    (
                        "completion_evidence_insufficient"
                        if outcome.status == "completed"
                        else f"execution_{outcome.status}"
                    )
                ]
            )
            opportunities.append(
                CognitiveOpportunity.create(
                    trigger="execution_outcome",
                    goal_ids=[outcome.goal_id],
                    evidence_refs=[validated.outcome_id, *outcome.evidence_ids],
                    reason_codes=reason_codes,
                    recommended_cognition=mode,
                    situation_digest=situation_digest,
                )
            )
        return opportunities

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
        if metadata.get("retained_work_reconciliation_only") is True:
            current_metadata = context.get("metadata")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            context["metadata"] = {
                **current_metadata,
                "last_retained_work_reconciliation_plan_id": str(
                    metadata.get("canonical_plan_id") or ""
                ),
                "last_retained_work_reconciliation_ms": _now_ms(),
            }
            self._persist_task_contexts_if_enabled()
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
                except ValidationError as exc:
                    logger.debug(
                        "Ignoring malformed planning information gap task_id=%s error=%s",
                        context.get("task_id"),
                        exc,
                    )
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
            "direct_capability",
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
            planned_capabilities = metadata.get("planned_capabilities")
            if isinstance(planned_capabilities, list):
                context["plan_summary"] = {
                    "result": planning_result,
                    "capabilities": [item for item in planned_capabilities if isinstance(item, dict)][:12],
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

    def _planner_reentry_responsibilities(
        self,
        *,
        result_metadata: dict[str, Any] | None,
        goal_id: str,
    ) -> list[dict[str, Any]]:
        """Retain exact GI provenance for later state-driven Planner re-entry.

        This is not a second Responsibility authority. The canonical Goal remains
        the owed outcome; these immutable source records let a later trusted Runtime,
        Situation, or time transition reactivate the same Planner without fabricating
        a new UserTurn or reconstructing WHAT from Goal prose. Restart revalidation is
        one consumer of the same bounded provenance.
        """

        if not isinstance(result_metadata, dict):
            return []
        interpretation = result_metadata.get("goal_interpretation")
        if not isinstance(interpretation, dict):
            return []
        raw_responsibilities = interpretation.get("responsibilities")
        if not isinstance(raw_responsibilities, list):
            return []
        context = self._task_context_by_goal_id(goal_id)
        if context is None:
            return []
        semantic_goal = context.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            return []
        source_refs = {
            str(item).strip()
            for item in semantic_goal.get("source_responsibility_refs") or []
            if str(item).strip()
        }
        if not source_refs:
            return []
        retained: list[dict[str, Any]] = []
        for item in raw_responsibilities:
            if not isinstance(item, dict):
                continue
            if str(item.get("local_ref") or "").strip() not in source_refs:
                continue
            retained.append(self._json_safe(item))
        return retained

    def _record_planner_time_conditions(
        self,
        result_metadata: dict[str, Any],
    ) -> int:
        """Bind Planner-authored time semantics to current Goal provenance.

        The canonical Plan carries only Planner-owned Goal/time semantics.  This
        owner adds current Plan identity and original GI Responsibility refs at
        persistence time; it never derives time from Goal prose.
        """

        raw_plan = result_metadata.get("canonical_plan")
        if not isinstance(raw_plan, dict):
            return 0
        try:
            plan = CanonicalPlan.model_validate(raw_plan)
        except ValidationError:
            return 0
        if not plan.time_conditions:
            return 0

        canonical_fingerprint = str(
            result_metadata.get("canonical_plan_fingerprint") or ""
        ).strip()
        language = self._compact_text(
            str(result_metadata.get("language") or "auto"), limit=64
        )
        for goal_id in plan.goal_ids:
            context = self._task_context_by_goal_id(goal_id)
            if context is None or self._goal_responsibility_status(context) != "open":
                continue
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            responsibilities = self._planner_reentry_responsibilities(
                result_metadata=result_metadata,
                goal_id=goal_id,
            )
            context["metadata"] = {
                **metadata,
                "canonical_plan_id": plan.plan_id,
                **(
                    {"canonical_plan_fingerprint": canonical_fingerprint}
                    if canonical_fingerprint
                    else {}
                ),
                **(
                    {
                        "planner_reentry_responsibilities": responsibilities,
                        "planner_reentry_language": language,
                    }
                    if responsibilities
                    else {}
                ),
            }
            context["updated_ms"] = _now_ms()

        accepted = 0
        for planned in plan.time_conditions:
            context = self._task_context_by_goal_id(planned.goal_id)
            if context is None or self._goal_responsibility_status(context) != "open":
                continue
            goal = self._semantic_goal_from_context(context)
            condition = GoalTimeCondition(
                condition_id=planned.condition_id,
                goal_id=planned.goal_id,
                due_at_ms=planned.due_at_ms,
                source_plan_id=plan.plan_id,
                source_responsibility_refs=list(goal.source_responsibility_refs),
                reason_code=planned.reason_code,
            )
            if self.register_goal_time_condition(condition):
                accepted += 1
        if accepted:
            self._persist_task_contexts_if_enabled()
        return accepted


    def register_goal_time_condition(
        self,
        condition: GoalTimeCondition | dict[str, Any],
    ) -> bool:
        """Persist one structured Planner-authored wake condition on an open Goal.

        Host never parses a Goal sentence into time semantics. The caller must supply
        a typed condition already bound to the current canonical Plan and original
        Responsibility refs. Revisions supersede stale conditions mechanically.
        """

        validated = (
            condition
            if isinstance(condition, GoalTimeCondition)
            else GoalTimeCondition.model_validate(condition)
        )
        context = self._task_context_by_goal_id(validated.goal_id)
        if context is None or self._goal_responsibility_status(context) != "open":
            return False
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        if str(metadata.get("canonical_plan_id") or "").strip() != validated.source_plan_id:
            return False
        goal = self._semantic_goal_from_context(context)
        source_refs = {str(item).strip() for item in goal.source_responsibility_refs}
        if not set(validated.source_responsibility_refs).issubset(source_refs):
            return False
        existing = metadata.get("time_conditions")
        if not isinstance(existing, list):
            existing = []
        payload = validated.model_dump(mode="json")
        retained = [
            item
            for item in existing
            if isinstance(item, dict)
            and str(item.get("condition_id") or "") != validated.condition_id
        ]
        retained.append(payload)
        context["metadata"] = {**metadata, "time_conditions": retained[-16:]}
        context["updated_ms"] = _now_ms()
        self._persist_task_contexts_if_enabled()
        return True

    def due_time_condition_opportunities(
        self,
        *,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically consume due structured conditions and emit Planner readiness.

        Conditions are discarded when their Goal/Plan binding is no longer current.
        A returned item carries source provenance plus an ephemeral
        ``CognitiveOpportunity``; it does not choose an Activity or response.
        """

        now = int(_now_ms() if now_ms is None else now_ms)
        due: list[dict[str, Any]] = []
        changed = False
        for context in self._active_task_contexts():
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                continue
            raw_conditions = metadata.get("time_conditions")
            if not isinstance(raw_conditions, list) or not raw_conditions:
                continue
            goal = self._semantic_goal_from_context(context)
            current_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
            keep: list[dict[str, Any]] = []
            for raw in raw_conditions:
                try:
                    condition = GoalTimeCondition.model_validate(raw)
                except (TypeError, ValueError):
                    changed = True
                    continue
                if (
                    condition.goal_id != goal.goal_id
                    or condition.source_plan_id != current_plan_id
                    or self._goal_responsibility_status(context) != "open"
                ):
                    changed = True
                    continue
                if condition.due_at_ms > now:
                    keep.append(condition.model_dump(mode="json"))
                    continue
                changed = True
                opportunity = CognitiveOpportunity.create(
                    trigger="time_condition",
                    goal_ids=[condition.goal_id],
                    reason_codes=[condition.reason_code],
                    recommended_cognition="fast",
                )
                due.append(
                    {
                        "condition": condition.model_dump(mode="json"),
                        "opportunity": opportunity.prompt_projection(),
                        "source_text": str(
                            goal.source_text
                            or context.get("last_meaningful_user_turn")
                            or ""
                        ).strip(),
                        "language": str(
                            metadata.get("planner_reentry_language") or "auto"
                        ).strip()
                        or "auto",
                        "responsibilities": [
                            self._json_safe(item)
                            for item in (
                                metadata.get("planner_reentry_responsibilities") or []
                            )
                            if isinstance(item, dict)
                        ],
                    }
                )
            if len(keep) != len(raw_conditions):
                context["metadata"] = {**metadata, "time_conditions": keep}
                context["updated_ms"] = _now_ms()
        if changed:
            self._persist_task_contexts_if_enabled()
        return due

    def next_time_condition_due_ms(self) -> int | None:
        """Return the nearest durable due time without interpreting Goal text."""

        nearest: int | None = None
        for context in self._active_task_contexts():
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                continue
            current_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
            for raw in metadata.get("time_conditions") or []:
                try:
                    condition = GoalTimeCondition.model_validate(raw)
                except (TypeError, ValueError):
                    continue
                if condition.source_plan_id != current_plan_id:
                    continue
                nearest = (
                    condition.due_at_ms
                    if nearest is None
                    else min(nearest, condition.due_at_ms)
                )
        return nearest

    def runtime_revalidation_candidates(self) -> list[dict[str, Any]]:
        """Return bounded open Goals whose pre-restart Runtime binding is stale."""

        candidates: list[dict[str, Any]] = []
        for context in self._active_task_contexts():
            metadata = context.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("runtime_revalidation_required") is not True:
                continue
            semantic_goal = context.get("semantic_goal")
            if not isinstance(semantic_goal, dict):
                continue
            goal_id = str(semantic_goal.get("goal_id") or context.get("task_id") or "").strip()
            if not goal_id:
                continue
            planned_capabilities = metadata.get("planned_capabilities")
            if not isinstance(planned_capabilities, list):
                planned_capabilities = []
            capability_ids = list(
                dict.fromkeys(
                    str(item.get("capability_id") or "").strip()
                    for item in planned_capabilities
                    if isinstance(item, dict)
                    and str(item.get("capability_id") or "").strip()
                )
            )
            responsibilities = metadata.get("planner_reentry_responsibilities")
            if not isinstance(responsibilities, list):
                responsibilities = []
            candidates.append(
                {
                    "goal_id": goal_id,
                    "task_id": str(context.get("task_id") or ""),
                    "source_text": str(semantic_goal.get("source_text") or context.get("last_meaningful_user_turn") or "").strip(),
                    "language": str(metadata.get("planner_reentry_language") or "auto").strip() or "auto",
                    "capability_ids": capability_ids,
                    "responsibilities": [
                        self._json_safe(item)
                        for item in responsibilities
                        if isinstance(item, dict)
                    ],
                    "restored_ms": metadata.get("restored_ms"),
                }
            )
        return candidates

    def complete_runtime_revalidation(
        self,
        goal_ids: list[str],
        *,
        source_ref: str,
    ) -> list[str]:
        """Invalidate stale pre-restart Work only after fresh provider truth.

        Provider/catalog state is authoritative for its Runtime domain but is not
        execution/world Evidence. Retain the source reference without promoting it
        into the Evidence namespace.
        """

        completed: list[str] = []
        now = _now_ms()
        for goal_id in dict.fromkeys(str(item).strip() for item in goal_ids if str(item).strip()):
            context = self._task_context_by_goal_id(goal_id)
            if context is None:
                continue
            metadata = context.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("runtime_revalidation_required") is not True:
                continue
            previous_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
            previous_fingerprint = str(metadata.get("canonical_plan_fingerprint") or "").strip()
            previous_capabilities = metadata.get("planned_capabilities")
            updated = dict(metadata)
            updated.pop("runtime_revalidation_required", None)
            for key in (
                "canonical_plan_id",
                "canonical_plan_fingerprint",
                "request_ids",
                "remaining_request_ids",
                "request_statuses",
                "planned_capabilities",
                "confirmation_id",
                "confirmation_request_ids",
                "confirmation_pending",
            ):
                updated.pop(key, None)
            if previous_plan_id:
                updated["recovery_previous_canonical_plan_id"] = previous_plan_id
            if previous_fingerprint:
                updated["recovery_previous_canonical_plan_fingerprint"] = previous_fingerprint
            if isinstance(previous_capabilities, list) and previous_capabilities:
                updated["recovery_previous_planned_capabilities"] = self._json_safe(previous_capabilities)
            updated["runtime_revalidation_source_ref"] = str(source_ref or "").strip()
            updated["runtime_revalidated_ms"] = now
            context["metadata"] = updated
            if str(context.get("plan_status") or "") == "revalidation_required":
                context["plan_status"] = "revalidated"
            if str(context.get("status") or "") == "recoverable":
                context["status"] = "planning"
                context["commitment_state"] = "evaluating"
            context["updated_ms"] = now
            completed.append(goal_id)
        if completed:
            self._persist_task_contexts_if_enabled()
            self.last_activity_ms = now
        return completed

    def record_interaction_response(
        self,
        sid: str | None,
        result: Any,
        *,
        confirmed_request_ids: set[str] | None = None,
        bind_planned_execution: bool = True,
    ) -> None:
        """Record assistant speech and, when dispatched, planned execution bindings.

        Preview and other planning-only callers retain the assistant turn and
        canonical Goal/plan metadata, but must not turn an undispatched request
        into authoritative Runtime Work.  Runtime-backed callers keep the
        default and reconcile the resulting bindings from execution receipts.
        """
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
        planner_reentry_language = "auto"
        if isinstance(result_metadata, dict):
            planner_reentry_language = str(result_metadata.get("language") or "auto")
            self._record_tool_evidence(result_metadata)
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
            self._record_planner_time_conditions(result_metadata)
            goal_outcomes = self._canonical_goal_outcomes(result_metadata)
            self._record_nonexecuting_goal_outcomes(goal_outcomes)

        speech_parts: list[str] = []
        for key in ("speak_immediate", "speak_after", "speech"):
            for item in data.get(key, []) or []:
                item_metadata = (
                    item.get("metadata")
                    if isinstance(item, dict)
                    else getattr(item, "metadata", None)
                )
                if (
                    isinstance(item_metadata, dict)
                    and item_metadata.get("reuse_current_turn_speech") is True
                ):
                    # The Fast Communicative Activity was recorded when its
                    # playback completed. This response only reuses that exact
                    # event as an execution barrier; it is not a second turn.
                    continue
                text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                text = self._compact_text(text)
                if text:
                    speech_parts.append(text)
        if speech_parts:
            assistant_turn_metadata: dict[str, Any] = {"source": "agent_result"}
            if isinstance(result_metadata, dict):
                result_source = str(result_metadata.get("source") or "").strip()
                if (
                    result_source == "evidence_bound_tool_result_interpretation"
                    and result_metadata.get("full_tool_result_retained") is True
                ):
                    assistant_turn_metadata = {
                        "source": result_source,
                        "evidence_bound": True,
                        "phase": "post_execution",
                        "source_goal_ids": self._string_list(
                            result_metadata.get("source_goal_ids")
                        ),
                        "canonical_plan_id": canonical_plan_id,
                    }
            self.record_assistant_turn(
                sid,
                " ".join(speech_parts),
                metadata=assistant_turn_metadata,
            )

        # A conversational Goal is not complete merely because Response
        # Composer produced text. Bind it to the concrete chromie.speak request
        # IDs generated from InteractionSpeech so only Capability Runtime evidence
        # can make that Goal terminal. Clarification speech is intentionally not
        # bound: its Goal must remain active while waiting for the user.
        if bind_planned_execution:
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
                    planned_capabilities=[
                        {
                            "capability_id": "chromie.speak",
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
                    planner_reentry_responsibilities=(
                        self._planner_reentry_responsibilities(
                            result_metadata=result_metadata,
                            goal_id=goal_id,
                        )
                    ),
                    planner_reentry_language=planner_reentry_language,
                )

        actions = data.get("actions", []) or data.get("capabilities", []) or []
        primary_actions: list[dict[str, Any]] = []
        for action in actions:
            if isinstance(action, dict):
                item = dict(action)
            else:
                item = {
                    "request_id": getattr(action, "request_id", None),
                    "capability_id": getattr(action, "capability_id", None) or getattr(action, "capability_id", None),
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

        if primary_actions and bind_planned_execution:
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
                    str(item.get("capability_id") or item.get("type") or item.get("target") or "action")
                    for item in goal_actions[:3]
                ]
                planned_capabilities = [
                    {
                        "capability_id": item.get("capability_id"),
                        "request_id": item.get("request_id"),
                        "args": self._json_safe(
                            item.get("args") if isinstance(item.get("args"), dict) else {}
                        ),
                        "timing": str(item.get("timing") or "sequential"),
                        "source_goal_ids": self._string_list(
                            (item.get("metadata") or {}).get("source_goal_ids")
                        ),
                        "safety_class": str(
                            (item.get("metadata") or {}).get("safety_class") or ""
                        ),
                        "retryable_safe_read": (
                            (item.get("metadata") or {}).get("retryable_safe_read")
                            is True
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
                    planned_capabilities=planned_capabilities,
                    confirmation_pending=confirmation_pending,
                    interaction_id=interaction_id,
                    turn_id=turn_id,
                    canonical_plan_id=canonical_plan_id,
                    canonical_plan_fingerprint=canonical_plan_fingerprint,
                    planner_reentry_responsibilities=(
                        self._planner_reentry_responsibilities(
                            result_metadata=result_metadata,
                            goal_id=goal_id,
                        )
                    ),
                    planner_reentry_language=planner_reentry_language,
                )

            if unscoped:
                request_ids = [
                    str(item.get("request_id"))
                    for item in unscoped
                    if item.get("request_id")
                ]
                action_summaries = [
                    str(item.get("capability_id") or item.get("type") or item.get("target") or "action")
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

        # Native InteractionResponse keeps Memory mutations in metadata so the
        # shared wire contract remains narrow. Historical top-level
        # ``memory_updates`` is intentionally not a compatibility input.
        metadata = data.get("metadata")
        memory_updates = (
            metadata.get("memory_updates", []) or []
            if isinstance(metadata, dict)
            else []
        )
        for update in memory_updates:
            if not isinstance(update, dict):
                continue
            update_type = str(update.get("type") or "")
            if update_type in {"extracted_memory", "memory_entry", "memory"}:
                self._store_explicit_memory_entries(
                    self._memory_extractor.extract_explicit_entries(
                        update.get("value"),
                        sid=sid,
                    )
                )
                continue
            if update_type == "durable_memory_forget":
                value = update.get("value")
                key = str(update.get("key") or "").strip()
                if (
                    key
                    and self._authorized_durable_mutation(
                        value, operation="forget"
                    )
                    and str(value.get("key") or "").strip() == key
                ):
                    self.forget_durable_memory(key=key)
                continue
            if update_type == "durable_memory_clear":
                if self._authorized_durable_mutation(
                    update.get("value"), operation="clear_profile"
                ):
                    self.clear_durable_memory()
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
