from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque

from orchestrator.runtime.memory import MemoryExtractor, MemoryPromptBuilder, MemoryStore


_DONE_TASK_STATUSES = {"done", "failed", "cancelled", "canceled", "expired"}
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
    "start over",
    "start a new session",
    "reset conversation",
    "reset session",
    "forget that",
    "forget it",
    "forget this task",
    "clear session",
    "never mind",
    "nevermind",
    "change topic",
    "let's talk about something else",
    "重新开始",
    "新的会话",
    "新会话",
    "开始新的会话",
    "重来",
    "换个话题",
    "清空会话",
    "忘记这个任务",
    "别管刚才",
    "不用了",
    "算了",
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
        relation = self._task_relation_from_metadata(metadata)
        if relation:
            return relation
        if not self._looks_like_meaningful_task_text(text):
            return None
        if self.is_followup_reference(text) and self._current_task_context():
            return "continue_task"
        route = str(route or "").strip()
        if route in {"robot_action", "tool", "memory", "deep_thought"}:
            return "new_task"
        return "side_conversation"

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
        return self._contains_phrase(self._normalized(text), self.reset_phrases)

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

        if self._has_any_context() and idle_sec >= self.hard_idle_timeout_sec:
            return self.start_new_conversation(reason="hard_idle_timeout", sid=sid)

        if self._active_pending_tasks():
            self.last_split_reason = "kept_active_pending_task"
            return {"started_new": False, "reason": "active_pending_task", "conversation_id": self.conversation_id, "sid": sid}

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
        self._turns.append(
            {
                "role": "user",
                "sid": sid,
                "text": compact,
                "route": route,
                "intent": intent,
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": metadata or {},
            }
        )
        self._record_task_context_from_user_turn(
            sid=sid,
            text=compact,
            route=route,
            intent=intent,
            metadata=metadata,
        )
        self._memory_store.add_many(
            self._memory_extractor.extract_user_turn(
                sid=sid,
                text=compact,
                route=route,
                metadata=metadata,
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
            "expired": "expired",
            "timed_out": "expired",
            "refused": "cancelled",
            "failed": "failed",
            "error": "failed",
        }.get(normalized_status, normalized_status)
        for task in reversed(self._pending_tasks):
            metadata = task.get("metadata")
            if not isinstance(metadata, dict):
                continue
            request_ids = metadata.get("request_ids")
            if isinstance(request_ids, str):
                request_ids = [request_ids]
            if not isinstance(request_ids, list) or request_id not in request_ids:
                continue
            statuses = metadata.setdefault("request_statuses", {})
            if isinstance(statuses, dict):
                statuses[request_id] = final_status
            remaining = metadata.get("remaining_request_ids")
            if isinstance(remaining, str):
                remaining = [remaining]
            if isinstance(remaining, list):
                metadata["remaining_request_ids"] = [
                    item for item in remaining if item != request_id
                ]
                if metadata["remaining_request_ids"]:
                    task["status"] = "running"
                else:
                    values = list(statuses.values()) if isinstance(statuses, dict) else [final_status]
                    if "failed" in values:
                        task["status"] = "failed"
                    elif "cancelled" in values:
                        task["status"] = "cancelled"
                    elif "expired" in values:
                        task["status"] = "expired"
                    else:
                        task["status"] = "done"
            else:
                task["status"] = final_status
            task["updated_ms"] = _now_ms()
            for context in reversed(self._task_contexts):
                metadata = context.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                request_ids = metadata.get("request_ids")
                if isinstance(request_ids, str):
                    request_ids = [request_ids]
                if isinstance(request_ids, list) and request_id in request_ids:
                    context["status"] = task["status"]
                    context["updated_ms"] = task["updated_ms"]
                    self._persist_task_contexts_if_enabled()
                    break
            self._memory_store.add_many(
                self._memory_extractor.extract_task_outcome(
                    sid=str(task.get("sid") or ""),
                    summary=str(task.get("summary") or task.get("type") or "task"),
                    status=str(task.get("status") or final_status),
                    trusted=True,
                )
            )
            self.last_activity_ms = _now_ms()
            return True
        return False

    def record_agent_result(self, sid: str | None, result: Any) -> None:
        """Record assistant speech and lightweight task hints from AgentResult."""
        if not self.enabled:
            return

        if hasattr(result, "model_dump"):
            data = result.model_dump(mode="json")
        elif isinstance(result, dict):
            data = result
        else:
            data = {}

        speech_parts: list[str] = []
        for key in ("speak_immediate", "speak_after", "speech"):
            for item in data.get(key, []) or []:
                text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                text = self._compact_text(text)
                if text:
                    speech_parts.append(text)
        if speech_parts:
            self.record_assistant_turn(sid, " ".join(speech_parts), metadata={"source": "agent_result"})

        actions = data.get("actions", []) or data.get("skills", []) or []
        if actions:
            action_summaries: list[str] = []
            request_ids: list[str] = []
            for index, action in enumerate(actions):
                if isinstance(action, dict):
                    request_id = action.get("request_id")
                    if request_id:
                        request_ids.append(str(request_id))
                    if index >= 3:
                        continue
                    action_summaries.append(
                        str(
                            action.get("skill_id")
                            or action.get("type")
                            or action.get("target")
                            or "action"
                        )
                    )
                else:
                    request_id = getattr(action, "request_id", None)
                    if request_id:
                        request_ids.append(str(request_id))
                    if index >= 3:
                        continue
                    action_summaries.append(
                        str(
                            getattr(action, "skill_id", None)
                            or getattr(action, "type", None)
                            or getattr(action, "target", None)
                            or "action"
                        )
                    )
            self.record_pending_task(
                sid=sid,
                task_type="robot_action",
                status="scheduled",
                summary=", ".join(action_summaries),
                metadata={
                    "action_count": len(actions),
                    "request_ids": request_ids,
                    "remaining_request_ids": list(request_ids),
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
