from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from shared.chromie_contracts.user_turn import (
    InputQualityEvidence,
    normalize_turn_text,
)


@dataclass(frozen=True)
class NormalizedTurnCapture:
    """Transport-normalized turn evidence before reflex or semantic review."""

    turn_id: str
    session_id: str
    conversation_id: str
    channel: str
    received_at: datetime
    original_text: str
    normalized_text: str
    language: str
    quality: InputQualityEvidence


class InputNormalization:
    """Preserve original input and apply transport-safe normalization only."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(
        self,
        text: str,
        *,
        session_id: str,
        conversation_id: str | None,
        channel: str = "voice",
        language: str | None = None,
        quality: InputQualityEvidence | None = None,
    ) -> NormalizedTurnCapture:
        resolved_session_id = normalize_turn_text(session_id)
        if not resolved_session_id:
            raise ValueError("Gateway capture requires a non-empty session_id")
        resolved_conversation_id = (
            normalize_turn_text(conversation_id or "") or resolved_session_id
        )
        return NormalizedTurnCapture(
            turn_id=resolved_session_id,
            session_id=resolved_session_id,
            conversation_id=resolved_conversation_id,
            channel=channel,
            received_at=self._aware_now(),
            original_text=text or "",
            normalized_text=normalize_turn_text(text or ""),
            language=self._resolve_language(text or "", language),
            quality=quality
            or InputQualityEvidence(
                source="asr_final" if channel == "voice" else channel,
                usable=True,
                reason="accepted by the existing transport boundary",
            ),
        )

    @staticmethod
    def _resolve_language(text: str, language: str | None) -> str:
        explicit = normalize_turn_text(language or "")
        if explicit and explicit.casefold() != "auto":
            return explicit

        cjk_count = sum(
            1
            for char in text
            if (
                "\u3400" <= char <= "\u4dbf"
                or "\u4e00" <= char <= "\u9fff"
                or "\uf900" <= char <= "\ufaff"
            )
        )
        if cjk_count:
            return "zh-CN"
        if any(("A" <= char <= "Z") or ("a" <= char <= "z") for char in text):
            return "en-US"
        return "auto"

    @staticmethod
    def with_conversation_id(
        capture: NormalizedTurnCapture,
        conversation_id: str | None,
    ) -> NormalizedTurnCapture:
        normalized = normalize_turn_text(conversation_id or "")
        if not normalized or normalized == capture.conversation_id:
            return capture
        return replace(capture, conversation_id=normalized)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value


__all__ = ["InputNormalization", "NormalizedTurnCapture"]
