from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque


def now_ms() -> float:
    return time.time() * 1000.0


def compact_text(text: str | None, *, limit: int = 220) -> str:
    value = " ".join(str(text or "").strip().split())
    if len(value) > limit:
        return value[:limit].rstrip() + "..."
    return value


def _memory_id(scope: str, kind: str, text: str, key: str | None = None) -> str:
    identity = key or text.casefold()
    digest = hashlib.sha1(f"{scope}:{kind}:{identity}".encode("utf-8")).hexdigest()[:12]
    return f"mem_{digest}"


@dataclass
class MemoryEntry:
    scope: str
    kind: str
    text: str
    key: str | None = None
    confidence: float = 0.8
    source_turn_ids: list[str] = field(default_factory=list)
    source_sids: list[str] = field(default_factory=list)
    created_ms: float = field(default_factory=now_ms)
    updated_ms: float = field(default_factory=now_ms)
    expires_ms: float | None = None
    persistence_policy: str = "ephemeral"
    safety_note: str = "Memory guides interpretation only; it does not authorize side effects."
    id: str | None = None

    def __post_init__(self) -> None:
        self.scope = compact_text(self.scope or "session", limit=40)
        self.kind = compact_text(self.kind or "note", limit=60)
        self.key = compact_text(self.key, limit=120) if self.key else None
        self.text = compact_text(self.text, limit=260)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if not self.id:
            self.id = _memory_id(self.scope, self.kind, self.text, self.key)

    def merge_source(self, *, sid: str | None = None, turn_id: str | None = None) -> None:
        if sid and sid not in self.source_sids:
            self.source_sids.append(sid)
            self.source_sids = self.source_sids[-8:]
        if turn_id and turn_id not in self.source_turn_ids:
            self.source_turn_ids.append(turn_id)
            self.source_turn_ids = self.source_turn_ids[-8:]
        self.updated_ms = now_ms()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope,
            "kind": self.kind,
            "key": self.key,
            "text": self.text,
            "confidence": self.confidence,
            "source_turn_ids": list(self.source_turn_ids),
            "source_sids": list(self.source_sids),
            "created_ms": self.created_ms,
            "updated_ms": self.updated_ms,
            "expires_ms": self.expires_ms,
            "persistence_policy": self.persistence_policy,
            "safety_note": self.safety_note,
        }

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "kind": self.kind,
            "key": self.key,
            "text": self.text,
            "confidence": self.confidence,
        }


class MemoryStore:
    def __init__(self, *, max_entries: int = 24) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: Deque[MemoryEntry] = deque(maxlen=self.max_entries)

    def clear(self) -> None:
        self._entries.clear()

    def add(self, entry: MemoryEntry) -> None:
        if not entry.text:
            return
        if entry.key:
            for index, existing in enumerate(self._entries):
                if (
                    existing.scope == entry.scope
                    and existing.kind == entry.kind
                    and existing.key == entry.key
                ):
                    entry.created_ms = existing.created_ms
                    entry.source_sids = [*existing.source_sids, *entry.source_sids][-8:]
                    entry.source_turn_ids = [*existing.source_turn_ids, *entry.source_turn_ids][-8:]
                    self._entries[index] = entry
                    return
        for existing in self._entries:
            if existing.id == entry.id:
                existing.confidence = max(existing.confidence, entry.confidence)
                existing.merge_source(
                    sid=entry.source_sids[-1] if entry.source_sids else None,
                    turn_id=entry.source_turn_ids[-1] if entry.source_turn_ids else None,
                )
                return
        self._entries.append(entry)

    def add_many(self, entries: list[MemoryEntry]) -> None:
        for entry in entries:
            self.add(entry)

    def snapshot(self) -> list[dict[str, Any]]:
        self.prune_expired()
        return [entry.to_dict() for entry in self._entries]

    def prompt_entries(self, *, limit: int = 8) -> list[dict[str, Any]]:
        self.prune_expired()
        return [entry.to_prompt_dict() for entry in list(self._entries)[-limit:]]

    def summary_lines(self, *, limit: int = 8) -> list[str]:
        return [f"- {entry['text']}" for entry in self.prompt_entries(limit=limit)]

    def summary(self, *, limit: int = 8) -> str:
        lines = self.summary_lines(limit=limit)
        return "\n".join(lines) if lines else "None"

    def prune_expired(self, now: float | None = None) -> None:
        current_ms = now if now is not None else now_ms()
        retained = [
            entry
            for entry in self._entries
            if entry.expires_ms is None or entry.expires_ms > current_ms
        ]
        if len(retained) != len(self._entries):
            self._entries = deque(retained, maxlen=self.max_entries)


class MemoryPromptBuilder:
    def build(self, store: MemoryStore, *, limit: int = 8) -> dict[str, Any]:
        return {
            "summary": store.summary(limit=limit),
            "entries": store.prompt_entries(limit=limit),
        }


class MemoryExtractor:
    def extract_user_turn(
        self,
        *,
        sid: str | None,
        text: str,
        route: str | None,
        metadata: dict[str, Any] | None,
        task_context: dict[str, Any] | None,
    ) -> list[MemoryEntry]:
        metadata = metadata or {}
        entries: list[MemoryEntry] = []
        for item in self._entries_from_metadata(metadata, sid=sid):
            entries.append(item)

        patch = self._task_patch(metadata)
        task_scope = "task" if task_context or patch else "session"
        goal = compact_text(str(patch.get("goal") or ""), limit=220)
        if goal:
            entries.append(
                MemoryEntry(
                    scope=task_scope,
                    kind="goal",
                    text=f"Current task: {goal}",
                    confidence=0.9,
                    source_sids=[sid] if sid else [],
                    persistence_policy=str(patch.get("persistence_policy") or "persist_if_unfinished"),
                )
            )
        elif route in {"robot_action", "tool", "memory", "deep_thought"}:
            compact = compact_text(text, limit=180)
            if compact:
                entries.append(
                    MemoryEntry(
                        scope=task_scope,
                        kind="goal",
                        text=f"Current task: {compact}",
                        confidence=0.7,
                        source_sids=[sid] if sid else [],
                        persistence_policy="ephemeral",
                    )
                )

        for claim in self._string_list(patch.get("important_claims") or patch.get("claims")):
            entries.append(
                MemoryEntry(
                    scope=task_scope,
                    kind="claim",
                    text=compact_text(claim, limit=220),
                    confidence=0.85,
                    source_sids=[sid] if sid else [],
                    persistence_policy=str(patch.get("persistence_policy") or "ephemeral"),
                )
            )
        for entity in self._string_list(patch.get("entities"))[:5]:
            entries.append(
                MemoryEntry(
                    scope=task_scope,
                    kind="entity",
                    text=f"Salient entity: {compact_text(entity, limit=120)}",
                    confidence=0.75,
                    source_sids=[sid] if sid else [],
                    persistence_policy="ephemeral",
                )
            )
        constraints = patch.get("constraints")
        if isinstance(constraints, dict):
            for key, value in list(constraints.items())[:6]:
                entries.append(
                    MemoryEntry(
                        scope=task_scope,
                        kind="constraint",
                        text=f"Constraint: {compact_text(str(key), limit=80)}={compact_text(str(value), limit=120)}",
                        confidence=0.85,
                        source_sids=[sid] if sid else [],
                        persistence_policy="ephemeral",
                    )
                )
        for question in self._string_list(patch.get("pending_questions") or patch.get("questions"))[:4]:
            entries.append(
                MemoryEntry(
                    scope=task_scope,
                    kind="pending_question",
                    text=f"Pending question: {compact_text(question, limit=180)}",
                    confidence=0.8,
                    source_sids=[sid] if sid else [],
                    persistence_policy="ephemeral",
                )
            )
        return entries

    def extract_task_outcome(
        self,
        *,
        sid: str | None,
        summary: str,
        status: str,
        trusted: bool,
    ) -> list[MemoryEntry]:
        if not trusted:
            return []
        compact_summary = compact_text(summary or "task", limit=180)
        compact_status = compact_text(status or "unknown", limit=40)
        if compact_status == "done":
            text = f"Runtime confirmed task completed: {compact_summary}"
            confidence = 0.95
        else:
            text = f"Runtime confirmed task status: {compact_summary} is {compact_status}"
            confidence = 0.9
        return [
            MemoryEntry(
                scope="task",
                kind="outcome",
                text=text,
                confidence=confidence,
                source_sids=[sid] if sid else [],
                persistence_policy="ephemeral",
            )
        ]

    def extract_explicit_entries(self, value: Any, *, sid: str | None) -> list[MemoryEntry]:
        raw_entries = value if isinstance(value, list) else [value]
        return self._entries_from_metadata({"extracted_memory": raw_entries}, sid=sid)

    def _entries_from_metadata(self, metadata: dict[str, Any], *, sid: str | None) -> list[MemoryEntry]:
        raw_entries = metadata.get("extracted_memory") or metadata.get("memory_entries") or []
        if not isinstance(raw_entries, list):
            return []
        entries: list[MemoryEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            text = compact_text(str(item.get("text") or ""), limit=260)
            if not text:
                continue
            entries.append(
                MemoryEntry(
                    scope=str(item.get("scope") or "session"),
                    kind=str(item.get("kind") or "note"),
                    key=str(item.get("key") or "") or None,
                    text=text,
                    confidence=float(item.get("confidence") or 0.75),
                    source_sids=[sid] if sid else [],
                    persistence_policy=str(item.get("persistence_policy") or "ephemeral"),
                )
            )
        return entries

    @staticmethod
    def _task_patch(metadata: dict[str, Any]) -> dict[str, Any]:
        patch = metadata.get("task_context_patch") or metadata.get("task_context") or {}
        return patch if isinstance(patch, dict) else {}

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [compact_text(str(item), limit=220) for item in value if compact_text(str(item), limit=220)]
