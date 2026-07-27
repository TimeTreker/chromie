from __future__ import annotations

from shared.chromie_contracts.reflex import ReflexOutcome
from shared.chromie_contracts.user_turn import (
    AttentionFinding,
    AttentionReviewResult,
    GatewayContextSnapshot,
    NormalizedTurnInput,
    OriginalTurnInput,
    UserTurnEnvelope,
)

from .protective_reflex import GatewayTurnCapture


class TurnAdmission:
    """Produce the immutable envelope after reflex, attention, and context review."""

    def from_attention(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot,
        review: AttentionReviewResult,
    ) -> UserTurnEnvelope:
        if review.turn_id != capture.turn_id:
            raise ValueError("attention review turn does not match captured turn")
        if review.session_id != capture.session_id:
            raise ValueError("attention review session does not match captured turn")
        if review.context_digest != snapshot.digest:
            raise ValueError("attention review context digest does not match snapshot")
        reflex = self._continued_reflex(capture)
        admission = "admit" if review.disposition == "admit" else "suppress"
        return self._envelope(
            capture,
            snapshot=snapshot,
            reflex=reflex,
            attention=review.as_finding(),
            admission=admission,
        )

    def for_reflex(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot | None = None,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "interrupt":
            raise ValueError("for_reflex requires an interrupt ReflexOutcome")
        return self._envelope(
            capture,
            snapshot=snapshot,
            reflex=capture.reflex_candidate,
            attention=AttentionFinding(
                disposition="admit",
                source="cognitive_gateway.protective_reflex",
                confidence=1.0,
                reason="protective control is retained for cognitive reconciliation",
            ),
            admission="reflex_and_admit",
        )

    def for_confirmation(self, capture: GatewayTurnCapture) -> UserTurnEnvelope:
        return self._envelope(
            capture,
            snapshot=None,
            reflex=self._continued_reflex(capture),
            attention=AttentionFinding(
                disposition="admit",
                source="orchestrator.confirmation_dialogue",
                confidence=1.0,
                reason="input is evaluated against a pending confirmation",
            ),
            admission="admit",
        )

    def for_direct(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot | None,
        *,
        source: str,
        reason: str,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "continue":
            raise ValueError("direct admission cannot override a deterministic reflex")
        return self._envelope(
            capture,
            snapshot=snapshot,
            reflex=self._continued_reflex(capture),
            attention=AttentionFinding(
                disposition="admit",
                source=source,
                confidence=1.0,
                reason=reason,
            ),
            admission="admit",
        )

    def for_suppression(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot | None,
        *,
        source: str = "cognitive_gateway.reflex_filter",
        reason: str | None = None,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "ignore":
            raise ValueError("for_suppression requires an ignore ReflexOutcome")
        return self._envelope(
            capture,
            snapshot=snapshot,
            reflex=capture.reflex_candidate,
            attention=AttentionFinding(
                disposition="suppress",
                source=source,
                confidence=capture.reflex_candidate.confidence,
                reason=reason or capture.reflex_candidate.reason,
            ),
            admission="suppress",
        )

    @staticmethod
    def _envelope(
        capture: GatewayTurnCapture,
        *,
        snapshot: GatewayContextSnapshot | None,
        reflex: ReflexOutcome,
        attention: AttentionFinding,
        admission: str,
    ) -> UserTurnEnvelope:
        return UserTurnEnvelope(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            conversation_id=capture.conversation_id,
            channel=capture.channel,
            received_at=capture.received_at,
            original_input=OriginalTurnInput(text=capture.original_text),
            normalized_input=NormalizedTurnInput(
                text=capture.normalized_text,
                language=reflex.language or capture.language or "auto",
            ),
            quality=capture.quality,
            reflex=reflex,
            attention=attention,
            context_refs=(snapshot.references if snapshot is not None else ()),
            admission=admission,
        )

    @staticmethod
    def _continued_reflex(capture: GatewayTurnCapture) -> ReflexOutcome:
        return ReflexOutcome(language=capture.language or "auto")


__all__ = ["TurnAdmission"]
