from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from shared.chromie_contracts.reflex import ReflexOutcome
from shared.chromie_contracts.user_turn import (
    AttentionReviewRequest,
    AttentionReviewResult,
    CoreTurnRequest,
    GatewayContextSnapshot,
    InputQualityEvidence,
    UserTurnEnvelope,
    normalize_turn_text,
)

from .cognitive_gateway_modules import (
    AttentionReview,
    ContextAssembly,
    GatewayTurnCapture,
    InputNormalization,
    ProtectiveReflex,
    TurnAdmission,
)


USER_TURN_ENVELOPE_CONTEXT_KEY = "user_turn_envelope"
GATEWAY_CONTEXT_SNAPSHOT_CONTEXT_KEY = "gateway_context_snapshot"


@dataclass(frozen=True)
class CoreTurnProjection:
    """Compatibility call arguments projected from an admitted Core request."""

    text: str
    sid: str
    language: str
    context: dict[str, Any]
    history: list[dict[str, Any]]


class CognitiveGateway:
    """Facade over the five physical Gateway modules.

    The facade preserves current host call sites while the modules own distinct
    contracts and can be tested independently.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.input_normalization = InputNormalization(clock=clock)
        self.protective_reflex = ProtectiveReflex()
        self.attention_review = AttentionReview()
        self.context_assembly = ContextAssembly(clock=clock)
        self.turn_admission = TurnAdmission()

    def capture(
        self,
        text: str,
        *,
        session_id: str,
        conversation_id: str | None,
        channel: str = "voice",
        language: str | None = None,
        quality: InputQualityEvidence | None = None,
    ) -> GatewayTurnCapture:
        normalized = self.input_normalization.capture(
            text,
            session_id=session_id,
            conversation_id=conversation_id,
            channel=channel,
            language=language,
            quality=quality,
        )
        return self.protective_reflex.evaluate(normalized)

    def with_conversation_id(
        self,
        capture: GatewayTurnCapture,
        conversation_id: str | None,
    ) -> GatewayTurnCapture:
        normalized = self.input_normalization.with_conversation_id(
            capture,
            conversation_id,
        )
        if not isinstance(normalized, GatewayTurnCapture):
            raise TypeError("Gateway conversation update lost reflex evidence")
        return normalized

    def with_reflex_outcome(
        self,
        capture: GatewayTurnCapture,
        outcome: ReflexOutcome,
    ) -> GatewayTurnCapture:
        return self.protective_reflex.with_outcome(capture, outcome)

    def assemble_context(
        self,
        capture: GatewayTurnCapture,
        context: dict[str, Any] | None,
    ) -> GatewayContextSnapshot:
        return self.context_assembly.assemble(capture, context)

    def attention_request(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot,
    ) -> AttentionReviewRequest:
        return self.attention_review.request(capture, snapshot)

    def attention_fail_open(
        self,
        request: AttentionReviewRequest,
        *,
        reason: str,
    ) -> AttentionReviewResult:
        return self.attention_review.fail_open(request, reason=reason)

    def admit_attention(
        self,
        capture: GatewayTurnCapture,
        snapshot: GatewayContextSnapshot,
        review: AttentionReviewResult,
    ) -> UserTurnEnvelope:
        return self.turn_admission.from_attention(capture, snapshot, review)

    def for_reflex(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
    ) -> UserTurnEnvelope:
        snapshot = self.assemble_context(capture, context) if context else None
        return self.turn_admission.for_reflex(capture, snapshot)

    def for_confirmation(self, capture: GatewayTurnCapture) -> UserTurnEnvelope:
        return self.turn_admission.for_confirmation(capture)

    def for_direct(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
        source: str,
        reason: str,
    ) -> UserTurnEnvelope:
        snapshot = self.assemble_context(capture, context) if context else None
        return self.turn_admission.for_direct(
            capture,
            snapshot,
            source=source,
            reason=reason,
        )

    def for_suppression(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
        source: str = "cognitive_gateway.reflex_filter",
        reason: str | None = None,
    ) -> UserTurnEnvelope:
        snapshot = self.assemble_context(capture, context) if context else None
        return self.turn_admission.for_suppression(
            capture,
            snapshot,
            source=source,
            reason=reason,
        )

    def for_core_review(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any],
        decision: Any,
    ) -> UserTurnEnvelope:
        """Deprecated compatibility projection for historical tests/replays.

        Production admission no longer depends on a semantic RouteDecision.
        """

        snapshot = self.assemble_context(capture, context)
        metadata = (
            decision.metadata
            if isinstance(getattr(decision, "metadata", None), dict)
            else {}
        )
        route = str(getattr(decision, "route", "") or "")
        if route == "ignore":
            review = AttentionReviewResult(
                turn_id=capture.turn_id,
                session_id=capture.session_id,
                context_digest=snapshot.digest,
                disposition="suppress",
                speech_act=str(
                    metadata.get("addressedness_speech_act") or "unclear"
                ),
                confidence=self._bounded_confidence(
                    metadata.get("addressedness_confidence"),
                    fallback=getattr(decision, "confidence", 0.0),
                ),
                source="cognitive_gateway.compatibility_route_projection",
                reason=str(
                    getattr(decision, "reason", "")
                    or "compatibility ignore projection"
                ),
            )
        else:
            review = AttentionReviewResult(
                turn_id=capture.turn_id,
                session_id=capture.session_id,
                context_digest=snapshot.digest,
                disposition="admit",
                speech_act=str(
                    metadata.get("addressedness_speech_act") or "unclear"
                ),
                confidence=self._bounded_confidence(
                    metadata.get("addressedness_confidence"),
                    fallback=1.0,
                ),
                source="cognitive_gateway.compatibility_route_projection",
                reason=str(
                    getattr(decision, "reason", "")
                    or "compatibility admitted projection"
                ),
            )
        return self.admit_attention(capture, snapshot, review)

    def core_request(
        self,
        envelope: UserTurnEnvelope,
        snapshot: GatewayContextSnapshot,
    ) -> CoreTurnRequest:
        return CoreTurnRequest(
            turn_envelope=envelope,
            context_snapshot=snapshot,
        )

    def project_for_core(
        self,
        envelope: UserTurnEnvelope,
        *,
        legacy_text: str,
        legacy_session_id: str,
        context: dict[str, Any],
    ) -> CoreTurnProjection:
        if envelope.admission not in {"admit", "reflex_and_admit"}:
            raise ValueError(
                f"Core projection requires admitted input, got {envelope.admission}"
            )
        if normalize_turn_text(legacy_session_id) != envelope.session_id:
            raise ValueError("legacy session_id does not match UserTurnEnvelope")
        if normalize_turn_text(legacy_text) != envelope.normalized_input.text:
            raise ValueError("legacy text does not match UserTurnEnvelope")

        projected_context = dict(context)
        projected_context[USER_TURN_ENVELOPE_CONTEXT_KEY] = envelope.model_dump(
            mode="json"
        )
        projected_context["gateway_admission_complete"] = True
        projected_context["turn_id"] = envelope.turn_id
        projected_context["user_turn_schema_version"] = envelope.schema_version
        history = projected_context.get("history")
        if not isinstance(history, list):
            history = []
        return CoreTurnProjection(
            text=envelope.normalized_input.text,
            sid=envelope.session_id,
            language=envelope.normalized_input.language,
            context=projected_context,
            history=list(history),
        )

    @staticmethod
    def _bounded_confidence(value: Any, *, fallback: Any) -> float:
        try:
            resolved = float(value if value is not None else fallback)
        except (TypeError, ValueError):
            resolved = 0.0
        return max(0.0, min(1.0, resolved))

    @staticmethod
    def metadata(envelope: UserTurnEnvelope) -> dict[str, Any]:
        return {
            USER_TURN_ENVELOPE_CONTEXT_KEY: envelope.model_dump(mode="json"),
            "user_turn_envelope_schema_version": envelope.schema_version,
            "turn_id": envelope.turn_id,
        }


__all__ = [
    "CoreTurnProjection",
    "CognitiveGateway",
    "GATEWAY_CONTEXT_SNAPSHOT_CONTEXT_KEY",
    "GatewayTurnCapture",
    "USER_TURN_ENVELOPE_CONTEXT_KEY",
]
