from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from shared.chromie_contracts.user_turn import (
    ContextReference,
    GatewayContextSnapshot,
)

from .protective_reflex import GatewayTurnCapture


class ContextAssembly:
    """Build one bounded, source-attributed context snapshot before admission."""

    CONTEXT_SOURCES = {
        "conversation_id": "orchestrator.conversation_state",
        "session_memory": "orchestrator.conversation_state",
        "history": "orchestrator.conversation_state",
        "pending_tasks": "orchestrator.conversation_state",
        "active_pending_tasks": "orchestrator.conversation_state",
        "active_task_contexts": "orchestrator.conversation_state",
        "active_task_snapshots": "orchestrator.conversation_state",
        "active_goal_snapshots": "orchestrator.conversation_state",
        "recent_goal_snapshots": "orchestrator.conversation_state",
        "current_task_context": "orchestrator.conversation_state",
        "interaction_engagement": "orchestrator.attention_policy",
        "interaction_context": "orchestrator.interaction_ledger",
        "mind": "orchestrator.mind",
        "robot_state": "orchestrator.runtime_state",
        "recent_tool_evidence": "orchestrator.conversation_state",
        "verified_tool_memory_index": "orchestrator.conversation_state",
        "discourse_referents": "orchestrator.conversation_state",
        "discourse_focus": "orchestrator.conversation_state",
    }

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def assemble(
        self,
        capture: GatewayTurnCapture,
        context: dict[str, Any] | None,
    ) -> GatewayContextSnapshot:
        copied = self._project_context(context)
        captured_at = self._aware_now()
        references = self._references(copied, captured_at=captured_at)
        encoded = json.dumps(
            copied,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return GatewayContextSnapshot(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            conversation_id=capture.conversation_id,
            captured_at=captured_at,
            context=copied,
            references=references,
            digest=hashlib.sha256(encoded).hexdigest(),
        )

    @classmethod
    def _project_context(
        cls,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Remove duplicate aggregate state before creating the bounded snapshot.

        ``VoiceAssistant.build_context`` retains the complete Conversation State
        aggregate for downstream compatibility while also publishing the leaf
        projections used by the maintained Core. Copying both into the Gateway
        snapshot double-counts the same semantic state and lets a bounded
        conversation grow past the snapshot byte contract. The Gateway owns the
        ingress projection: top-level leaf owners win, while aggregate-only legacy
        callers are mechanically flattened without reinterpreting their meaning.
        """

        source = context if isinstance(context, dict) else {}
        conversation = source.get("conversation")
        projected = {
            key: deepcopy(value)
            for key, value in source.items()
            if key
            not in {
                "conversation",
                # These values are already owned by the retained ``mind`` object.
                "core_principles",
                "long_term_goals",
                "experience_tuning_policy",
                # These values are already owned by ``session_memory``.
                "memory_summary",
                "extracted_memory",
                # Full retained task history is not Gateway/Core ingress state;
                # active snapshots/context carry the current continuity evidence.
                "task_contexts",
            }
        }
        if not isinstance(conversation, dict):
            return projected

        for key in cls.CONTEXT_SOURCES:
            if key in projected or key not in conversation:
                continue
            projected[key] = deepcopy(conversation[key])
        return projected

    def _references(
        self,
        context: dict[str, Any],
        *,
        captured_at: datetime,
    ) -> tuple[ContextReference, ...]:
        references: list[ContextReference] = []
        for context_type, source in self.CONTEXT_SOURCES.items():
            if context_type not in context:
                continue
            value = context.get(context_type)
            digest = hashlib.sha256(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()[:20]
            references.append(
                ContextReference(
                    context_type=context_type,
                    reference_id=f"ctx_{context_type}_{digest}",
                    source=source,
                    captured_at=captured_at,
                    freshness="current",
                    age_ms=0,
                )
            )
        return tuple(references)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value


__all__ = ["ContextAssembly"]
