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

from shared.chromie_contracts.discourse import (
    DiscourseReferent,
)
from shared.chromie_contracts.goal import (
    ActiveGoalSnapshot,
    GoalAssociationResolution,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
)
from shared.chromie_contracts.situation import CognitiveOpportunity, GoalTimeCondition
from shared.chromie_contracts.reflex import CancellationDispatchReceipt
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.plan import PlannerInformationGap
from shared.chromie_contracts.semantic_task import (
    InformationGap,
    SemanticGoal,
    SemanticTaskOperation,
    TaskContextSnapshot,
)


_DONE_TASK_STATUSES = {"done", "failed", "refused", "timed_out", "cancelled", "canceled", "expired", "superseded"}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_TASK_STORE_PATH = ".chromie/conversation/task_contexts.json"
_DEFAULT_DURABLE_MEMORY_PATH = ".chromie/memory/profile.json"
_DEFAULT_REFLECTION_MEMORY_MAX_TTL_SEC = 900


logger = logging.getLogger("chromie.orchestrator.conversation_state")


def _now_ms() -> float:
    return time.time() * 1000.0


# The Goal state function modules import _DONE_TASK_STATUSES and _now_ms from
# this module, so they are imported after those definitions.
from orchestrator.runtime import goal_association_state  # noqa: E402
from orchestrator.runtime import goal_cancellation_state  # noqa: E402
from orchestrator.runtime import goal_outcome_state  # noqa: E402
from orchestrator.runtime import goal_planning_state  # noqa: E402


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

    def record_trusted_relational_memory(
        self,
        value: Any,
        *,
        sid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retain bounded relational Memory from an already-trusted source boundary.

        This method does not recognize people or decide privacy. A source-specific adapter
        must first establish its own provenance/principal/audience policy. The Memory owner
        then validates and stores the supplied relationship/shared-experience projection.
        """

        entries = self._memory_extractor.extract_trusted_relational_entries(
            value,
            sid=sid,
        )
        self._store_explicit_memory_entries(entries)
        return [entry.to_dict() for entry in entries]

    def record_cognitive_relational_experience(
        self,
        candidates: list[Any],
        *,
        sid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retain private bounded experience proposed by cognition, never disclosure authority."""

        entries: list[MemoryEntry] = []
        for candidate in candidates[:4]:
            payload = candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else dict(candidate)
            entries.append(
                MemoryEntry(
                    scope="session",
                    kind="shared_experience",
                    text=str(payload.get("text") or ""),
                    confidence=float(payload.get("confidence") or 0.7),
                    relation="shared_experience",
                    subject_refs=[str(v) for v in payload.get("subject_refs") or []],
                    source_ref_ids=[str(v) for v in payload.get("source_refs") or []],
                    disclosure_scope="private",
                    source_sids=[sid] if sid else [],
                    expires_ms=_now_ms() + 1000.0 * float(payload.get("retention_seconds") or 21600),
                    persistence_policy="ephemeral",
                )
            )
        self._memory_store.add_many(entries)
        return [entry.to_dict() for entry in entries]

    def record_cognitive_self_context(
        self,
        candidates: list[Any],
        *,
        sid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retain short-lived Chromie-owned concern/interest context without action authority."""

        entries: list[MemoryEntry] = []
        for candidate in candidates[:4]:
            payload = candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else dict(candidate)
            entries.append(
                MemoryEntry(
                    scope="session",
                    kind=str(payload.get("kind") or "self_concern"),
                    text=str(payload.get("text") or ""),
                    confidence=float(payload.get("confidence") or 0.7),
                    relation="self_context",
                    subject_refs=[str(v) for v in payload.get("subject_refs") or ["self:chromie"]],
                    source_ref_ids=[str(v) for v in payload.get("source_refs") or []],
                    disclosure_scope="self_context",
                    source_sids=[sid] if sid else [],
                    expires_ms=_now_ms() + 1000.0 * float(payload.get("retention_seconds") or 14400),
                    persistence_policy="ephemeral",
                    safety_note="Self-context guides cognition only; it creates no Goal, timer, action, or authorization.",
                )
            )
        self._memory_store.add_many(entries)
        return [entry.to_dict() for entry in entries]

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

    def _recoverable_persistent_goal_context(
        self,
        item: dict[str, Any],
        *,
        now: float,
        source: str,
    ) -> dict[str, Any] | None:
        """Rebase one unfinished durable Goal onto a fresh runtime context.

        Conversation/session boundaries and process restart both preserve semantic
        Goal identity while invalidating transient execution/confirmation bindings.
        The Goal therefore returns as recoverable and must be revalidated before new
        Work is committed. This is persistence mechanics, not a continuity decision;
        GA still decides whether a new Responsibility belongs to this Goal.
        """

        if self._goal_responsibility_status(item) != "open":
            return None
        original_status = str(item.get("status") or "open")
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
        recovery_metadata = {
            "restored_original_status": original_status,
            "restored_ms": now,
            "runtime_revalidation_required": True,
            "persistence_resume_source": source,
            "recovery_previous_remaining_request_ids": previous_remaining,
            "recovery_previous_request_statuses": dict(previous_request_statuses),
            "recovery_previous_confirmation_request_ids": (
                previous_confirmation_request_ids
            ),
            "remaining_request_ids": [],
            "request_statuses": {},
            "confirmation_pending": False,
        }
        if source == "task_store":
            recovery_metadata["restored_from_task_store"] = True
        elif source == "conversation_boundary":
            recovery_metadata["carried_across_conversation"] = True
        metadata = {**metadata, **recovery_metadata}
        if previous_confirmation is not None:
            metadata["recovery_previous_confirmation"] = previous_confirmation
        for stale_key in ("confirmation_id", "confirmation_request_ids"):
            metadata.pop(stale_key, None)
        context["metadata"] = metadata
        if not isinstance(context.get("related_sids"), list):
            context["related_sids"] = []
        return context

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
            context = self._recoverable_persistent_goal_context(
                item, now=now, source="task_store"
            )
            if context is not None:
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
                "persistence_policy": str(
                    context.get("persistence_policy") or "persist_if_unfinished"
                ),
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

    @staticmethod
    def _goal_memory_projection_metadata(
        snapshot: dict[str, Any],
        *,
        tier: str,
        backing: str,
        abstracted: bool,
    ) -> dict[str, Any]:
        metadata = snapshot.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.update(
            {
                "goal_memory_tier": tier,
                "memory_backing": backing,
                "abstracted_memory_projection": abstracted,
            }
        )
        return metadata

    def working_goal_memory(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return RAM-resident Goal continuity memory for current cognition.

        Working Goal memory contains active/recoverable Goals plus a bounded recent
        terminal tail. It is detailed enough for immediate continuity but remains a
        read-only projection; GA alone decides whether current meaning belongs to one
        of these canonical Goals.
        """

        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        active = self.active_goal_snapshots(limit=limit)
        remaining = max(0, limit - len(active))
        recent = self.recent_goal_snapshots(limit=remaining)
        out: list[dict[str, Any]] = []
        for snapshot in [*active, *recent]:
            item = copy.deepcopy(snapshot)
            metadata = self._goal_memory_projection_metadata(
                item, tier="working", backing="ram", abstracted=False,
            )
            policy = str(metadata.get("persistence_policy") or "persist_if_unfinished")
            metadata["durable_backing"] = bool(
                self.task_store_enabled
                and str(item.get("responsibility_status") or "open") == "open"
                and policy.casefold()
                not in {"ephemeral", "memory_only", "do_not_persist", "none"}
            )
            if metadata.get("restored_from_task_store") is True:
                metadata["long_term_origin"] = True
            item["metadata"] = metadata
            out.append(item)
        return out

    def long_term_goal_memory(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return abstract disk-backed Goal summaries for long-horizon continuity.

        The durable task store keeps canonical semantic state needed for correct restart
        recovery. Cognition does not receive that full retained record as "memory".
        Instead this projection removes transient Work, raw source wording, gaps and
        per-turn provenance while preserving stable Goal identity plus the abstract
        human outcome needed by GA. Persistence does not itself create continuity.
        """

        if not self.task_store_enabled:
            return []
        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        summaries: list[dict[str, Any]] = []
        for context in self._durable_task_contexts()[-limit:]:
            snapshot = ActiveGoalSnapshot.from_task_snapshot(
                self._task_snapshot(context)
            ).model_dump(mode="json", exclude_none=True)
            goal = snapshot.get("goal")
            if not isinstance(goal, dict):
                continue
            description = self._compact_text(str(goal.get("description") or ""), limit=360)
            if not description:
                continue
            goal_metadata = goal.get("metadata")
            goal_metadata = dict(goal_metadata) if isinstance(goal_metadata, dict) else {}
            abstract_goal = {
                "schema_version": int(goal.get("schema_version") or 1),
                "goal_id": goal.get("goal_id") or snapshot.get("goal_id"),
                "version": int(goal.get("version") or snapshot.get("goal_version") or 1),
                "responsibility_status": goal.get("responsibility_status") or "open",
                "description": description,
                # Long-term memory retains meaning, not the verbatim historical turn.
                "source_text": description,
                "beneficiary": goal.get("beneficiary"),
                "object": copy.deepcopy(goal.get("object") or {}),
                "constraints": copy.deepcopy(goal.get("constraints") or {}),
                "success_criteria": [
                    self._compact_text(str(item), limit=260)
                    for item in list(goal.get("success_criteria") or [])[:4]
                    if str(item or "").strip()
                ],
                "source_responsibility_refs": [],
                "related_goal_ids": list(goal.get("related_goal_ids") or [])[:8],
                "supersedes_goal_ids": list(goal.get("supersedes_goal_ids") or [])[:8],
                "metadata": {
                    key: copy.deepcopy(goal_metadata[key])
                    for key in ("output_mode", "body_effect_families", "body_effect_family")
                    if goal_metadata.get(key) not in (None, "", [], {})
                },
            }
            item = {
                "schema_version": int(snapshot.get("schema_version") or 1),
                "goal_id": snapshot.get("goal_id"),
                "goal_version": int(snapshot.get("goal_version") or 1),
                "responsibility_status": snapshot.get("responsibility_status") or "open",
                "work_status": "stored",
                "goal": abstract_goal,
                "open_information_gaps": [],
                "last_user_update": "",
                "updated_ms": snapshot.get("updated_ms"),
                "metadata": self._goal_memory_projection_metadata(
                    snapshot, tier="long_term", backing="disk", abstracted=True,
                ),
            }
            item["metadata"].pop("execution_binding", None)
            item["metadata"]["persistence_policy"] = str(
                context.get("persistence_policy") or "persist_if_unfinished"
            )
            try:
                summaries.append(
                    ActiveGoalSnapshot.model_validate(item).model_dump(
                        mode="json", exclude_none=True
                    )
                )
            except ValidationError as exc:
                logger.debug(
                    "Ignoring malformed long-term Goal memory goal_id=%s error=%s",
                    item.get("goal_id"),
                    exc,
                )
        return summaries

    def goal_association_candidate_snapshots(
        self,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return bounded Goal memory candidates that GA alone may associate.

        Working RAM Goal memory is preferred because it contains current continuity.
        Abstract long-term Goal memory may add durable cross-session candidates. The
        same canonical Goal is never duplicated across tiers; when it is already in
        working memory, that current projection wins. Storage tier is evidence about
        retention only and never decides semantic continuity or reopens terminal Goals.
        """

        if limit is None:
            limit = self.max_pending_tasks
        limit = max(0, int(limit))
        if limit == 0:
            return []
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for snapshot in [
            *self.working_goal_memory(limit=limit),
            *self.long_term_goal_memory(limit=limit),
        ]:
            goal_id = str(snapshot.get("goal_id") or "").strip()
            if not goal_id or goal_id in seen:
                continue
            seen.add(goal_id)
            candidates.append(snapshot)
            if len(candidates) >= limit:
                break
        return candidates

    def _commit_semantic_state_transaction(
        self,
        mutate: Callable[[], list[dict[str, Any]]],
        *,
        rollback_reason: str = "atomic_semantic_transaction_rolled_back",
        persistence_failure_reason: str = "atomic_semantic_persistence_failed",
    ) -> list[dict[str, Any]]:
        return goal_association_state.commit_semantic_state_transaction(
            self,
            mutate,
            rollback_reason=rollback_reason,
            persistence_failure_reason=persistence_failure_reason,
        )

    def goal_cancellation_bindings(
        self,
        goal_ids: list[str] | tuple[str, ...] | set[str],
    ) -> list[dict[str, Any]]:
        return goal_cancellation_state.goal_cancellation_bindings(self, goal_ids)

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
        return goal_cancellation_state.apply_goal_cancellation_resolution(
            self,
            resolution,
            receipts=receipts,
            confirmation_transition=confirmation_transition,
            sid=sid,
            user_text=user_text,
            source=source,
            target_goal_ids_override=target_goal_ids_override,
            target_responsibility_status=target_responsibility_status,
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
        return goal_cancellation_state.apply_goal_replacement_resolution(
            self,
            resolution,
            receipts=receipts,
            confirmation_transition=confirmation_transition,
            sid=sid,
            user_text=user_text,
            source=source,
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
        return goal_cancellation_state.apply_reflex_cancellation_receipt(
            self,
            receipt,
            revoked_confirmation=revoked_confirmation,
            sid=sid,
            user_text=user_text,
            source=source,
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
        return goal_association_state.apply_goal_association_resolution(
            self,
            resolution,
            sid=sid,
            user_text=user_text,
            source=source,
            atomic=atomic,
        )

    def apply_planner_information_gaps(
        self,
        gaps_by_goal_id: dict[str, list[PlannerInformationGap | dict[str, Any]]],
        *,
        turn_id: str,
        sid: str | None,
        user_text: str,
        source: str = "fast_planner_information_gap",
    ) -> list[dict[str, Any]]:
        return goal_association_state.apply_planner_information_gaps(
            self,
            gaps_by_goal_id,
            turn_id=turn_id,
            sid=sid,
            user_text=user_text,
            source=source,
        )

    def apply_semantic_task_operations(
        self,
        operations: list[SemanticTaskOperation] | list[dict[str, Any]],
        *,
        sid: str | None,
        user_text: str,
        source: str | None = None,
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        return goal_association_state.apply_semantic_task_operations(
            self,
            operations,
            sid=sid,
            user_text=user_text,
            source=source,
            persist=persist,
        )

    def apply_semantic_task_operations_atomically(
        self,
        operations: list[SemanticTaskOperation] | list[dict[str, Any]],
        *,
        sid: str | None,
        user_text: str,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        return goal_association_state.apply_semantic_task_operations_atomically(
            self,
            operations,
            sid=sid,
            user_text=user_text,
            source=source,
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
        # A conversation boundary clears local discourse/session state, not unfinished
        # persistent responsibility. Preserve durable canonical Goals and invalidate
        # only their transient execution bindings; GA may associate future sessions
        # with these recoverable candidates.
        persistent_goals = self._durable_task_contexts()
        self._conversation_seq += 1
        self.conversation_id = f"{self.base_conversation_id}-{self._conversation_seq:04d}"
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns.clear()
        self._pending_tasks.clear()
        self._task_contexts.clear()
        for item in persistent_goals:
            context = self._recoverable_persistent_goal_context(
                item, now=self.started_ms, source="conversation_boundary"
            )
            if context is not None:
                self._task_contexts.append(context)
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
            status = str(item.get("status") or "").strip().casefold()
            request_args = item.get("request_args")
            if (
                not evidence_id or not tool_id or status != "completed"
                or not isinstance(request_args, dict)
            ):
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
                    "status": status,
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
            if str(item.get("status") or "").strip().casefold() != "completed":
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
            if str(raw.get("status") or "").strip().casefold() != "completed":
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
            evidence_goal_ids = self._string_list(raw.get("source_goal_ids")) or goal_ids
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
                "goal_ids": evidence_goal_ids,
                "canonical_plan_id": canonical_plan_id,
                "source": "trusted_execution_outcome",
            }
            self._recent_tool_evidence.append(entry)
            known_ids.add(evidence_id)

    def _record_execution_outcome_tool_evidence(
        self,
        bundle: ExecutionOutcomeBundle,
    ) -> None:
        """Promote committed trusted observations into reusable Memory immediately.

        ExecutionOutcome is the authoritative point at which provider output has
        already been schema-validated, correlated to exact Work, and committed to
        Goal state.  Reuse must not depend on a later speech/response object carrying
        that bundle again.  ``_record_tool_evidence`` keeps the existing bounded,
        provenance-preserving storage and duplicate suppression policy.
        """

        self._record_tool_evidence({
            "canonical_plan_id": bundle.canonical_plan_id,
            "source_goal_ids": list(bundle.canonical_goal_ids),
            "execution_outcome_bundle": bundle.model_dump(mode="json"),
        })

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

    def activated_memory_context(
        self,
        *,
        activation_texts: list[str] | None = None,
        activation_subject_refs: list[str] | None = None,
        audience_refs: list[str] | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Project bounded Memory for an exact current cognitive context.

        The normal session projection activates by current user/task/discourse cues.
        Goal-free Situation cognition can additionally bind exact ``subject_refs`` so
        relational Memory about the observed person outranks unrelated recency. Privacy
        filtering remains inside the Memory owner; callers may pass only a fully resolved
        current audience and an empty audience never widens disclosure.
        """

        base_activation_texts = self._memory_activation_texts()
        extra_activation_texts = [
            self._compact_text(value, limit=260)
            for value in list(activation_texts or [])[:16]
            if str(value or "").strip()
        ]
        combined_activation_texts = [
            *base_activation_texts,
            *extra_activation_texts,
        ][:32]
        extracted = self._memory_prompt_builder.build(
            self._memory_store,
            limit=limit,
            activation_texts=combined_activation_texts,
            activation_subject_refs=activation_subject_refs,
            audience_refs=audience_refs,
        )
        durable_entries = self._durable_memory.prompt_entries(
            limit=limit,
            activation_texts=combined_activation_texts,
            activation_subject_refs=activation_subject_refs,
            audience_refs=audience_refs,
        )
        working_entries = [
            {**copy.deepcopy(entry), "memory_tier": "working", "memory_backing": "ram"}
            for entry in extracted["entries"]
        ]
        long_term_entries = [
            {**copy.deepcopy(entry), "memory_tier": "long_term", "memory_backing": "disk"}
            for entry in durable_entries
        ]
        combined_entries = rank_memory_prompt_entries(
            [*long_term_entries, *working_entries],
            activation_texts=combined_activation_texts,
            activation_subject_refs=activation_subject_refs,
            audience_refs=audience_refs,
            limit=limit,
        )
        summary_lines = [
            f"- {entry['text']}"
            for entry in combined_entries
            if entry.get("text")
        ]
        return {
            "entries": combined_entries,
            "summary": "\n".join(summary_lines) if summary_lines else "None",
            "selection": {
                "policy": "context_subject_relevance_then_recency",
                "activation_source_count": len(combined_activation_texts),
                "activation_subject_ref_count": len(
                    [
                        item
                        for item in list(activation_subject_refs or [])
                        if str(item or "").strip()
                    ]
                ),
                "audience_resolved": bool(
                    [item for item in list(audience_refs or []) if str(item or "").strip()]
                ),
            },
        }

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
        working_entries = [
            {**copy.deepcopy(entry), "memory_tier": "working", "memory_backing": "ram"}
            for entry in extracted_memory["entries"]
        ]
        long_term_entries = [
            {**copy.deepcopy(entry), "memory_tier": "long_term", "memory_backing": "disk"}
            for entry in durable_entries
        ]
        combined_entries = rank_memory_prompt_entries(
            [*long_term_entries, *working_entries],
            activation_texts=activation_texts,
            limit=12,
        )
        durable_entries = rank_memory_prompt_entries(
            long_term_entries,
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
            "kind": "tiered_conversation_memory",
            "conversation_id": self.conversation_id,
            "memory_tiers": {
                "working": {
                    "storage": "ram",
                    "entry_count": len(working_entries),
                    "goal_count": len(self.working_goal_memory(limit=4)),
                },
                "long_term": {
                    "storage": "disk",
                    "entry_count": len(long_term_entries),
                    "goal_count": len(self.long_term_goal_memory(limit=4)),
                },
            },
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
            # Active Memory is the bounded, relevance-activated cognitive projection
            # over both retention tiers. It is deliberately not a third store.
            "active_memory": {
                "kind": "relevance_projection",
                "entries": copy.deepcopy(combined_entries),
                "selection_policy": "context_relevance_then_recency",
                "role_projection_policy": "entry_cognitive_roles",
                "activation_source_count": len(activation_texts),
            },
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
                "conversation_boundary_clears_history_and_ephemeral_tasks": True,
                "conversation_boundary_preserves_unfinished_persistent_goals": True,
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
            "working_goal_memory": self.working_goal_memory(),
            "long_term_goal_memory": self.long_term_goal_memory(),
            "goal_association_candidates": self.goal_association_candidate_snapshots(),
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
        semantic_operations = goal_association_state.semantic_operations_from_metadata(turn_metadata)
        if semantic_operations:
            operation_results = self.apply_semantic_task_operations(
                semantic_operations,
                sid=sid,
                user_text=compact,
                source=str(turn_metadata.get("source") or "user_meaning_interpreter"),
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
        turn_metadata = dict(metadata or {})
        activity_ids = self._string_list(turn_metadata.get("communicative_activity_ids"))
        turn_id = str(turn_metadata.get("turn_id") or "").strip()
        existing = None
        if (sid and turn_id and activity_ids
                and turn_metadata.get("wording_owner") == "social_cognition"
                and turn_metadata.get("playback_completed") is True):
            for candidate in reversed(self._turns):
                prior = candidate.get("metadata") or {}
                if (candidate.get("role") == "assistant" and candidate.get("sid") == sid
                        and prior.get("turn_id") == turn_id
                        and prior.get("wording_owner") == "social_cognition"
                        and prior.get("playback_completed") is True
                        and self._string_list(prior.get("communicative_activity_ids")) == activity_ids):
                    existing = candidate
                    break
        if existing is not None:
            # Runtime has validated full immutable wording before history
            # compaction. A later Need receipt enriches that delivered act;
            # it must not become a second utterance in Memory or the console.
            if existing.get("text") != compact:
                raise ValueError("Delivered communicative Activity wording cannot change")
            existing["metadata"] = {**existing["metadata"], **turn_metadata}
        else:
            self._turns.append({
                "role": "assistant",
                "sid": sid,
                "text": compact,
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": turn_metadata,
            })
        current_task = self._current_task_context()
        if current_task is not None:
            current_task["last_assistant_response"] = compact
            current_task["updated_ms"] = _now_ms()
            self._persist_task_contexts_if_enabled()
        self.last_activity_ms = _now_ms()

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
        return goal_outcome_state.record_confirmation_scope(
            self,
            sid=sid,
            confirmation_id=confirmation_id,
            interaction_id=interaction_id,
            fingerprint=fingerprint,
            expires_at=expires_at,
            response=response,
            confirmed_request_ids=confirmed_request_ids,
        )

    def resolve_confirmation_scope(
        self,
        *,
        confirmation_id: str,
        decision: str,
    ) -> bool:
        return goal_outcome_state.resolve_confirmation_scope(
            self,
            confirmation_id=confirmation_id,
            decision=decision,
        )

    def record_pending_task(
        self,
        *,
        sid: str | None,
        task_type: str,
        status: str = "pending",
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return goal_outcome_state.record_pending_task(
            self,
            sid=sid,
            task_type=task_type,
            status=status,
            summary=summary,
            metadata=metadata,
        )

    def update_pending_task_status(
        self,
        *,
        metadata_key: str,
        metadata_value: Any,
        status: str,
    ) -> bool:
        return goal_outcome_state.update_pending_task_status(
            self,
            metadata_key=metadata_key,
            metadata_value=metadata_value,
            status=status,
        )

    def update_pending_task_status_for_request_id(
        self,
        *,
        request_id: str | None,
        status: str,
    ) -> bool:
        return goal_outcome_state.update_pending_task_status_for_request_id(
            self,
            request_id=request_id,
            status=status,
        )

    def record_execution_outcome_bundle(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        return goal_outcome_state.record_execution_outcome_bundle(self, bundle, sid=sid)

    def reconcile_communicative_goal_completion(
        self,
        sid: str | None,
        goal_ids: list[str],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return goal_outcome_state.reconcile_communicative_goal_completion(
            self,
            sid,
            goal_ids,
            metadata=metadata,
        )

    def reconcile_execution_outcome_responsibilities(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        return goal_outcome_state.reconcile_execution_outcome_responsibilities(
            self,
            bundle,
            sid=sid,
        )

    def apply_reflection_resolution(
        self,
        resolution: ReflectionResolution | dict[str, Any],
        *,
        sid: str | None,
    ) -> list[dict[str, Any]]:
        return goal_outcome_state.apply_reflection_resolution(self, resolution, sid=sid)

    def derive_execution_cognitive_opportunities(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        situation_digest: str = "",
    ) -> list[CognitiveOpportunity]:
        return goal_outcome_state.derive_execution_cognitive_opportunities(
            self,
            bundle,
            situation_digest=situation_digest,
        )

    def register_goal_time_condition(
        self,
        condition: GoalTimeCondition | dict[str, Any],
    ) -> bool:
        return goal_planning_state.register_goal_time_condition(self, condition)

    def due_time_condition_opportunities(
        self,
        *,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        return goal_planning_state.due_time_condition_opportunities(self, now_ms=now_ms)

    def next_time_condition_due_ms(self) -> int | None:
        return goal_planning_state.next_time_condition_due_ms(self)

    def runtime_revalidation_candidates(self) -> list[dict[str, Any]]:
        return goal_planning_state.runtime_revalidation_candidates(self)

    def goal_reentry_provenance(
        self,
        goal_ids: list[str] | tuple[str, ...] | set[str],
    ) -> list[dict[str, Any]]:
        return goal_planning_state.goal_reentry_provenance(self, goal_ids)

    def complete_runtime_revalidation(
        self,
        goal_ids: list[str],
        *,
        source_ref: str,
    ) -> list[str]:
        return goal_planning_state.complete_runtime_revalidation(
            self,
            goal_ids,
            source_ref=source_ref,
        )

    def record_interaction_response(
        self,
        sid: str | None,
        result: Any,
        *,
        confirmed_request_ids: set[str] | None = None,
        bind_planned_execution: bool = True,
    ) -> None:
        return goal_planning_state.record_interaction_response(
            self,
            sid,
            result,
            confirmed_request_ids=confirmed_request_ids,
            bind_planned_execution=bind_planned_execution,
        )
