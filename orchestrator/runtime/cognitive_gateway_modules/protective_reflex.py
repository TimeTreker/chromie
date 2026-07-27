from __future__ import annotations

from dataclasses import dataclass, replace

from shared.chromie_contracts.reflex import (
    DEFAULT_REFLEX_FILTER,
    ReflexFilter,
    ReflexOutcome,
)

from .input_normalization import NormalizedTurnCapture


@dataclass(frozen=True)
class GatewayTurnCapture(NormalizedTurnCapture):
    """Normalized turn plus deterministic protective-reflex evidence."""

    reflex_candidate: ReflexOutcome


class ProtectiveReflex:
    """Apply deterministic stop/cancel/emergency/noise controls before cognition."""

    def __init__(self, reflex_filter: ReflexFilter | None = None) -> None:
        self._filter = reflex_filter or DEFAULT_REFLEX_FILTER

    def evaluate(self, capture: NormalizedTurnCapture) -> GatewayTurnCapture:
        outcome = self._filter.evaluate(capture.original_text)
        return GatewayTurnCapture(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            conversation_id=capture.conversation_id,
            channel=capture.channel,
            received_at=capture.received_at,
            original_text=capture.original_text,
            normalized_text=capture.normalized_text,
            language=outcome.language or capture.language,
            quality=capture.quality,
            reflex_candidate=outcome,
        )

    @staticmethod
    def with_outcome(
        capture: GatewayTurnCapture,
        outcome: ReflexOutcome,
    ) -> GatewayTurnCapture:
        return replace(
            capture,
            language=outcome.language or capture.language,
            reflex_candidate=outcome,
        )


__all__ = ["GatewayTurnCapture", "ProtectiveReflex"]
