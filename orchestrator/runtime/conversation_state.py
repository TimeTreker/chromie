from __future__ import annotations

import os
import re
import time
from collections import deque
from typing import Any, Deque


_DONE_TASK_STATUSES = {"done", "failed", "cancelled", "canceled", "expired"}


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
    "start over",
    "reset conversation",
    "forget that",
    "forget it",
    "never mind",
    "nevermind",
    "change topic",
    "let's talk about something else",
    "重新开始",
    "重来",
    "换个话题",
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
        self.reset_phrases = tuple(p.lower() for p in reset_phrases)
        self.followup_phrases = tuple(p.lower() for p in followup_phrases)
        self.new_topic_starters = tuple(p.lower() for p in new_topic_starters)

        self._conversation_seq = 1
        self.conversation_id = self.base_conversation_id
        self.started_ms = _now_ms()
        self.last_activity_ms = self.started_ms
        self._turns: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_turns * 2))
        self._pending_tasks: Deque[dict[str, Any]] = deque(maxlen=max(1, self.max_pending_tasks))
        self.last_split_reason: str | None = None

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
            reset_phrases=_split_phrases(os.getenv("ORCH_CONVERSATION_RESET_PHRASES"), DEFAULT_RESET_PHRASES),
            followup_phrases=_split_phrases(os.getenv("ORCH_CONVERSATION_FOLLOWUP_PHRASES"), DEFAULT_FOLLOWUP_PHRASES),
            new_topic_starters=_split_phrases(os.getenv("ORCH_CONVERSATION_NEW_TOPIC_STARTERS"), DEFAULT_NEW_TOPIC_STARTERS),
        )

    def _compact_text(self, text: str | None, *, limit: int | None = None) -> str:
        text = " ".join((text or "").strip().split())
        max_len = limit or self.turn_max_text_chars
        if len(text) > max_len:
            return text[:max_len].rstrip() + "…"
        return text

    @staticmethod
    def _normalized(text: str | None) -> str:
        text = " ".join((text or "").strip().lower().split())
        return text

    def _has_any_context(self) -> bool:
        return bool(self._turns or self._pending_tasks)

    def _active_pending_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for task in self._pending_tasks:
            status = str(task.get("status") or "pending").lower()
            if status not in _DONE_TASK_STATUSES:
                tasks.append(task)
        return tasks

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
        return list(self._pending_tasks)[-self.max_pending_tasks :]

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
            "limits": {
                "max_turns": self.max_turns,
                "max_context_chars": self.max_context_chars,
                "soft_idle_timeout_sec": self.soft_idle_timeout_sec,
                "hard_idle_timeout_sec": self.hard_idle_timeout_sec,
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
        self._pending_tasks.append(
            {
                "sid": sid,
                "type": task_type,
                "status": status or "pending",
                "summary": self._compact_text(summary or task_type),
                "ts_ms": _now_ms(),
                "conversation_id": self.conversation_id,
                "metadata": metadata or {},
            }
        )
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
            for action in actions[:3]:
                if isinstance(action, dict):
                    action_summaries.append(
                        str(
                            action.get("skill_id")
                            or action.get("type")
                            or action.get("target")
                            or "action"
                        )
                    )
                else:
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
                metadata={"action_count": len(actions)},
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
