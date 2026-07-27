from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    from chromie_contracts.user_turn import (
        AttentionReviewRequest,
        AttentionReviewResult,
        AttentionSpeechAct,
    )
except ImportError:  # pragma: no cover - repository source-layout fallback
    from shared.chromie_contracts.user_turn import (
        AttentionReviewRequest,
        AttentionReviewResult,
        AttentionSpeechAct,
    )

from ..clients.ollama_client import OllamaClient


logger = logging.getLogger("chromie.agent.cognitive_gateway.attention_review")

DIRECTED_SPEECH_ACTS: set[str] = {
    "question",
    "request",
    "imperative",
    "greeting",
}
SUPPRESSIBLE_INACTIVE_SPEECH_ACTS: set[str] = {
    "ambient_report",
    "dictation",
    "narration",
    "reply",
}


class _AttentionModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addressed: bool
    speech_act: AttentionSpeechAct
    confidence: float = Field(ge=0.0, le=1.0)


class AttentionReviewer:
    """Focused Gateway addressedness classifier with fail-open admission."""

    def __init__(
        self,
        client: OllamaClient | None,
        *,
        min_suppression_confidence: float = 0.72,
        num_ctx: int = 2048,
        num_predict: int = 96,
    ) -> None:
        self.client = client
        self.min_suppression_confidence = max(
            0.0,
            min(1.0, float(min_suppression_confidence)),
        )
        self.num_ctx = max(512, int(num_ctx))
        self.num_predict = max(32, int(num_predict))

    async def review(self, request: AttentionReviewRequest) -> AttentionReviewResult:
        engagement = request.engagement
        if engagement.get("gate_enabled") is not True:
            return self._admit(
                request=request,
                confidence=1.0,
                source="cognitive_gateway.attention_policy",
                reason="attention gate is disabled",
            )
        if engagement.get("active") is not False:
            return self._admit(
                request=request,
                confidence=1.0,
                source="cognitive_gateway.attention_policy",
                reason="active interaction context admits the turn",
            )
        if self.client is None:
            return self._admit(
                request=request,
                confidence=0.0,
                source="cognitive_gateway.attention_review_fail_open",
                reason="attention model is unavailable",
            )

        try:
            raw = await self.client.generate(
                self._prompt(request),
                system=self._system_prompt(),
                options={
                    "temperature": 0,
                    "top_p": 0.9,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
                response_format=self._response_schema(),
            )
            if not isinstance(raw, dict):
                raise ValueError("attention model did not return a JSON object")
            result = _AttentionModelOutput.model_validate(raw)
        except Exception as exc:
            logger.warning(
                "attention_review_failed turn_id=%s error_type=%s error=%s",
                request.turn_id,
                type(exc).__name__,
                exc,
            )
            return self._admit(
                request=request,
                confidence=0.0,
                source="cognitive_gateway.attention_review_fail_open",
                reason=f"attention review failed open: {type(exc).__name__}",
            )

        direct_question_form = request.text.rstrip().endswith(("?", "？"))
        fail_open_reason = ""
        if result.addressed or result.confidence < self.min_suppression_confidence:
            fail_open_reason = "addressed_or_low_confidence"
        elif result.speech_act in DIRECTED_SPEECH_ACTS:
            fail_open_reason = "direct_speech_act"
        elif result.speech_act == "unclear":
            fail_open_reason = "unclear_speech_act"
        elif direct_question_form:
            fail_open_reason = "direct_question_form"
        elif result.speech_act not in SUPPRESSIBLE_INACTIVE_SPEECH_ACTS:
            fail_open_reason = "unsupported_speech_act"

        if fail_open_reason:
            return AttentionReviewResult(
                turn_id=request.turn_id,
                session_id=request.session_id,
                context_digest=request.context_digest,
                disposition="admit",
                speech_act=result.speech_act,
                confidence=result.confidence,
                source="cognitive_gateway.attention_review_model",
                reason=f"attention review admitted: {fail_open_reason}",
            )
        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="suppress",
            speech_act=result.speech_act,
            confidence=result.confidence,
            source="cognitive_gateway.attention_review_model",
            reason="inactive turn reviewed as unaddressed ambient speech",
        )

    @staticmethod
    def _admit(
        *,
        request: AttentionReviewRequest,
        confidence: float,
        source: str,
        reason: str,
    ) -> AttentionReviewResult:
        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="admit",
            speech_act="unclear",
            confidence=confidence,
            source=source,
            reason=reason,
        )

    @staticmethod
    def _response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "addressed": {"type": "boolean"},
                "speech_act": {
                    "type": "string",
                    "enum": [
                        "question",
                        "request",
                        "imperative",
                        "greeting",
                        "reply",
                        "ambient_report",
                        "dictation",
                        "narration",
                        "unclear",
                    ],
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["addressed", "speech_act", "confidence"],
            "additionalProperties": False,
        }

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's focused Cognitive Gateway Attention Review. "
            "Classify only whether the latest transcript is directed to Chromie "
            "and its speech act. Do not infer route, intent, goal, capability, "
            "tool, action, plan, or response. Questions, requests, imperatives, "
            "greetings, and Chromie's name are addressed even when the name or "
            "pronoun 'you' is omitted. Third-person reports, dictation, meeting "
            "talk, or narration without a second-person addressee may be ambient. "
            "Delivery to this classifier is not evidence of addressedness. If "
            "genuinely unclear, use addressed=true and speech_act=unclear. Return "
            "only the schema-valid JSON object."
        )

    @staticmethod
    def _prompt(request: AttentionReviewRequest) -> str:
        return (
            f"Host engagement evidence: {request.engagement}\n"
            f"Language hint: {request.language}\n"
            f"Latest transcript: {request.text}"
        )


__all__ = ["AttentionReviewer"]
