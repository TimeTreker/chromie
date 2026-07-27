from __future__ import annotations

from shared.chromie_contracts.user_turn import (
    AttentionReviewRequest,
    AttentionReviewResult,
    GatewayContextSnapshot,
)

from .protective_reflex import GatewayTurnCapture


class AttentionReview:
    """Create and validate the focused pre-Core addressedness boundary."""

    def request(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot,
    ) -> AttentionReviewRequest:
        engagement = snapshot.context.get("interaction_engagement")
        return AttentionReviewRequest(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest=snapshot.digest,
            text=capture.normalized_text,
            language=capture.language or "auto",
            engagement=(engagement if isinstance(engagement, dict) else {}),
        )

    @staticmethod
    def fail_open(
        request: AttentionReviewRequest,
        *,
        reason: str,
    ) -> AttentionReviewResult:
        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="admit",
            speech_act="unclear",
            confidence=0.0,
            source="cognitive_gateway.attention_review_fail_open",
            reason=reason,
        )


__all__ = ["AttentionReview"]
