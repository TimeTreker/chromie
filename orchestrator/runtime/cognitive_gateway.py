from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable

from shared.chromie_contracts.reflex import (
    DEFAULT_REFLEX_FILTER,
    ReflexOutcome,
)
from shared.chromie_contracts.user_turn import (
    AttentionFinding,
    ContextReference,
    InputQualityEvidence,
    NormalizedTurnInput,
    OriginalTurnInput,
    UserTurnEnvelope,
    normalize_turn_text,
)


USER_TURN_ENVELOPE_CONTEXT_KEY = "user_turn_envelope"


@dataclass(frozen=True)
class GatewayTurnCapture:
    """Pre-admission evidence retained while compatibility review runs."""

    turn_id: str
    session_id: str
    conversation_id: str
    channel: str
    received_at: datetime
    original_text: str
    normalized_text: str
    language: str
    quality: InputQualityEvidence
    reflex_candidate: ReflexOutcome


@dataclass(frozen=True)
class CoreTurnProjection:
    """Legacy call arguments projected from one admitted envelope."""

    text: str
    sid: str
    language: str
    context: dict[str, Any]
    history: list[dict[str, Any]]


class GatewayCoreCompatibilityAdapter:
    """Build the canonical turn envelope while preserving current interfaces.

    Router and Agent wire shapes remain unchanged during this migration slice.
    The envelope is recorded alongside them and is the source of Core turn
    identity, normalized text, language, and context correlation.
    """

    _CONTEXT_SOURCES = {
        "conversation": "orchestrator.conversation_state",
        "history": "orchestrator.conversation_state",
        "active_goal_snapshots": "orchestrator.conversation_state",
        "interaction_engagement": "orchestrator.attention_policy",
        "mind": "orchestrator.mind",
        "robot_state": "orchestrator.runtime_state",
    }

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(
        self,
        text: str,
        *,
        session_id: str,
        conversation_id: str | None,
        channel: str = "voice",
        quality: InputQualityEvidence | None = None,
    ) -> GatewayTurnCapture:
        received_at = self._aware_now()
        reflex = DEFAULT_REFLEX_FILTER.evaluate(text)
        resolved_session_id = normalize_turn_text(session_id)
        if not resolved_session_id:
            raise ValueError("Gateway capture requires a non-empty session_id")
        resolved_conversation_id = (
            normalize_turn_text(conversation_id or "") or resolved_session_id
        )
        return GatewayTurnCapture(
            turn_id=resolved_session_id,
            session_id=resolved_session_id,
            conversation_id=resolved_conversation_id,
            channel=channel,
            received_at=received_at,
            original_text=text or "",
            normalized_text=normalize_turn_text(text or ""),
            language=reflex.language or "auto",
            quality=quality
            or InputQualityEvidence(
                source="asr_final" if channel == "voice" else channel,
                usable=True,
                reason="accepted by the existing transport boundary",
            ),
            reflex_candidate=reflex,
        )

    @staticmethod
    def with_conversation_id(
        capture: GatewayTurnCapture,
        conversation_id: str | None,
    ) -> GatewayTurnCapture:
        normalized = normalize_turn_text(conversation_id or "")
        if not normalized or normalized == capture.conversation_id:
            return capture
        return replace(capture, conversation_id=normalized)

    @staticmethod
    def with_reflex_outcome(
        capture: GatewayTurnCapture,
        outcome: ReflexOutcome,
    ) -> GatewayTurnCapture:
        return replace(
            capture,
            language=outcome.language or capture.language,
            reflex_candidate=outcome,
        )

    def for_reflex(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "interrupt":
            raise ValueError("for_reflex requires an interrupt ReflexOutcome")
        return self._envelope(
            capture,
            reflex=capture.reflex_candidate,
            attention=AttentionFinding(
                disposition="admit",
                source="cognitive_gateway.protective_reflex",
                confidence=1.0,
                reason="protective control is retained for cognitive reconciliation",
            ),
            context=context,
            admission="reflex_and_admit",
        )

    def for_confirmation(
        self,
        capture: GatewayTurnCapture,
    ) -> UserTurnEnvelope:
        return self._envelope(
            capture,
            reflex=self._continued_reflex(capture),
            attention=AttentionFinding(
                disposition="admit",
                source="orchestrator.confirmation_dialogue",
                confidence=1.0,
                reason="input is evaluated against a pending confirmation",
            ),
            context=None,
            admission="admit",
        )

    def for_direct(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
        source: str,
        reason: str,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "continue":
            raise ValueError(
                "direct admission cannot override a deterministic reflex"
            )
        return self._envelope(
            capture,
            reflex=self._continued_reflex(capture),
            attention=AttentionFinding(
                disposition="admit",
                source=source,
                confidence=1.0,
                reason=reason,
            ),
            context=context,
            admission="admit",
        )

    def for_suppression(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any] | None = None,
        source: str = "cognitive_gateway.reflex_filter",
        reason: str | None = None,
    ) -> UserTurnEnvelope:
        if capture.reflex_candidate.action != "ignore":
            raise ValueError(
                "for_suppression requires an ignore ReflexOutcome"
            )
        return self._envelope(
            capture,
            reflex=capture.reflex_candidate,
            attention=AttentionFinding(
                disposition="suppress",
                source=source,
                confidence=capture.reflex_candidate.confidence,
                reason=reason or capture.reflex_candidate.reason,
            ),
            context=context,
            admission="suppress",
        )

    def for_route(
        self,
        capture: GatewayTurnCapture,
        *,
        context: dict[str, Any],
        decision: Any,
    ) -> UserTurnEnvelope:
        metadata = (
            decision.metadata if isinstance(getattr(decision, "metadata", None), dict) else {}
        )
        reflex = self._router_reflex(metadata) or capture.reflex_candidate
        route = str(getattr(decision, "route", "") or "")
        if route == "ignore" or reflex.action == "ignore":
            confidence = self._bounded_confidence(
                metadata.get("addressedness_confidence"),
                fallback=(
                    reflex.confidence
                    if reflex.action == "ignore"
                    else getattr(decision, "confidence", 0.0)
                ),
            )
            return self._envelope(
                capture,
                reflex=(
                    reflex
                    if reflex.action == "ignore"
                    else self._continued_reflex(capture)
                ),
                attention=AttentionFinding(
                    disposition="suppress",
                    source=(
                        "cognitive_gateway.reflex_filter"
                        if reflex.action == "ignore"
                        else "compatibility_router.attention_review"
                    ),
                    confidence=confidence,
                    reason=str(
                        (
                            reflex.reason
                            if reflex.action == "ignore"
                            else getattr(decision, "reason", "")
                        )
                        or "input was suppressed"
                    ),
                ),
                context=context,
                admission="suppress",
            )

        if reflex.action != "interrupt":
            reflex = self._continued_reflex(capture)
        admission = (
            "reflex_and_admit" if reflex.action == "interrupt" else "admit"
        )
        attention_confidence = self._bounded_confidence(
            metadata.get("addressedness_confidence"),
            fallback=1.0,
        )
        return self._envelope(
            capture,
            reflex=reflex,
            attention=AttentionFinding(
                disposition="admit",
                source="compatibility_router.attention_review",
                confidence=attention_confidence,
                reason=str(
                    getattr(decision, "reason", "")
                    or "input admitted by compatibility review"
                ),
            ),
            context=context,
            admission=admission,
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
    def metadata(
        envelope: UserTurnEnvelope,
    ) -> dict[str, Any]:
        return {
            USER_TURN_ENVELOPE_CONTEXT_KEY: envelope.model_dump(mode="json"),
            "user_turn_envelope_schema_version": envelope.schema_version,
            "turn_id": envelope.turn_id,
        }

    def _envelope(
        self,
        capture: GatewayTurnCapture,
        *,
        reflex: ReflexOutcome,
        attention: AttentionFinding,
        context: dict[str, Any] | None,
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
            context_refs=self._context_refs(context),
            admission=admission,
        )

    def _context_refs(
        self,
        context: dict[str, Any] | None,
    ) -> tuple[ContextReference, ...]:
        if not isinstance(context, dict):
            return ()
        captured_at = self._aware_now()
        references: list[ContextReference] = []
        for context_type, source in self._CONTEXT_SOURCES.items():
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

    @staticmethod
    def _router_reflex(metadata: dict[str, Any]) -> ReflexOutcome | None:
        raw = metadata.get("reflex_outcome")
        if not isinstance(raw, dict):
            return None
        try:
            return ReflexOutcome.model_validate(raw)
        except Exception:
            return None

    @staticmethod
    def _continued_reflex(capture: GatewayTurnCapture) -> ReflexOutcome:
        return ReflexOutcome(language=capture.language or "auto")

    @staticmethod
    def _bounded_confidence(value: Any, *, fallback: Any) -> float:
        try:
            resolved = float(value if value is not None else fallback)
        except (TypeError, ValueError):
            resolved = 0.0
        return max(0.0, min(1.0, resolved))

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value


__all__ = [
    "CoreTurnProjection",
    "GatewayCoreCompatibilityAdapter",
    "GatewayTurnCapture",
    "USER_TURN_ENVELOPE_CONTEXT_KEY",
]
