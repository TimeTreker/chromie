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
        history = snapshot.context.get("history")
        recent_dialogue: list[dict[str, str]] = []
        if isinstance(history, list):
            for item in history[-8:]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip().casefold()
                text = " ".join(str(item.get("text") or "").strip().split())
                metadata = item.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}
                # Suppressed room speech remains bounded transport evidence in
                # Conversation State, but it is not part of the dialogue Chromie
                # believes it was having with the person. Feeding it back here
                # poisons addressedness on the next turn (for example, repeated
                # greetings begin to look like self-directed narration).
                if (
                    role == "user"
                    and metadata.get("accepted_dialogue_evidence") is not True
                ):
                    continue
                if role in {"user", "assistant"} and text:
                    recent_dialogue.append({"role": role, "text": text[:1200]})
        return AttentionReviewRequest(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest=snapshot.digest,
            text=capture.normalized_text,
            language=capture.language or "auto",
            engagement=(engagement if isinstance(engagement, dict) else {}),
            recent_dialogue=recent_dialogue,
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
