from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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

        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        source = "cognitive_gateway.attention_review_model"
        try:
            raw = await self.client.generate(
                self._prompt(request),
                system=self._system_prompt(),
                options=options,
                response_format=self._response_schema(),
            )
            if not isinstance(raw, dict):
                raise ValueError("attention model did not return a JSON object")
            try:
                result = self._validate_model_output(raw)
            except (ValidationError, ValueError) as initial_exc:
                logger.warning(
                    "attention_review_contract_repair_start turn_id=%s "
                    "error_type=%s error=%s raw_output=%s",
                    request.turn_id,
                    type(initial_exc).__name__,
                    initial_exc,
                    raw,
                )
                repaired = await self.client.generate(
                    self._repair_prompt(
                        request,
                        initial_output=raw,
                        validation_error=str(initial_exc),
                    ),
                    system=self._system_prompt(),
                    options=options,
                    response_format=self._response_schema(),
                )
                if not isinstance(repaired, dict):
                    raise ValueError(
                        "attention model repair did not return a JSON object"
                    )
                result = self._validate_model_output(repaired)
                source = "cognitive_gateway.attention_review_model_repaired"
                logger.info(
                    "attention_review_contract_repair_done turn_id=%s status=success",
                    request.turn_id,
                )
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

        fail_open_reason = self._admission_reason(result)

        if fail_open_reason:
            return AttentionReviewResult(
                turn_id=request.turn_id,
                session_id=request.session_id,
                context_digest=request.context_digest,
                disposition="admit",
                speech_act=result.speech_act,
                confidence=result.confidence,
                source=source,
                reason=f"attention review admitted: {fail_open_reason}",
            )

        # Suppression discards the turn before ordinary Core semantics.  A
        # schema-valid first answer is therefore not sufficient authority: ask
        # the model to reconsider the semantic distinction independently and
        # fail open on disagreement or an invalid review.  This stays inside
        # the existing model-owned Attention Review instead of asking Host
        # phrase rules to recognize questions, requests, or imperatives.
        try:
            reconsidered_raw = await self.client.generate(
                self._suppression_review_prompt(
                    request,
                    initial_output=result.model_dump(mode="json"),
                ),
                system=self._system_prompt(),
                options=options,
                response_format=self._response_schema(),
            )
            if not isinstance(reconsidered_raw, dict):
                raise ValueError(
                    "attention suppression review did not return a JSON object"
                )
            reconsidered = self._validate_model_output(reconsidered_raw)
        except Exception as exc:
            logger.warning(
                "attention_suppression_review_failed turn_id=%s "
                "error_type=%s error=%s",
                request.turn_id,
                type(exc).__name__,
                exc,
            )
            return self._admit(
                request=request,
                confidence=0.0,
                source="cognitive_gateway.attention_review_fail_open",
                reason=(
                    "attention suppression review failed open: "
                    f"{type(exc).__name__}"
                ),
            )

        reconsidered_reason = self._admission_reason(reconsidered)
        if reconsidered_reason:
            logger.info(
                "attention_suppression_review_disagreed turn_id=%s "
                "initial_speech_act=%s reconsidered_speech_act=%s reason=%s",
                request.turn_id,
                result.speech_act,
                reconsidered.speech_act,
                reconsidered_reason,
            )
            return AttentionReviewResult(
                turn_id=request.turn_id,
                session_id=request.session_id,
                context_digest=request.context_digest,
                disposition="admit",
                speech_act=reconsidered.speech_act,
                confidence=reconsidered.confidence,
                source="cognitive_gateway.attention_review_model_reconsidered",
                reason=(
                    "attention suppression review admitted: "
                    f"{reconsidered_reason}"
                ),
            )
        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="suppress",
            speech_act=reconsidered.speech_act,
            confidence=min(result.confidence, reconsidered.confidence),
            source="cognitive_gateway.attention_review_model_confirmed",
            reason=(
                "inactive turn independently confirmed as unaddressed ambient speech"
            ),
        )

    def _admission_reason(self, result: _AttentionModelOutput) -> str:
        if result.addressed or result.confidence < self.min_suppression_confidence:
            return "addressed_or_low_confidence"
        if result.speech_act in DIRECTED_SPEECH_ACTS:
            return "direct_speech_act"
        if result.speech_act == "unclear":
            return "unclear_speech_act"
        if result.speech_act not in SUPPRESSIBLE_INACTIVE_SPEECH_ACTS:
            return "unsupported_speech_act"
        return ""

    @staticmethod
    def _validate_model_output(raw: dict[str, Any]) -> _AttentionModelOutput:
        result = _AttentionModelOutput.model_validate(raw)
        if not result.addressed and (
            result.speech_act in DIRECTED_SPEECH_ACTS
            or result.speech_act == "unclear"
        ):
            raise ValueError(
                "addressed=false requires an explicit ambient speech act; "
                f"got speech_act={result.speech_act}"
            )
        return result

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
            "Classify only the latest transcript's speech act and whether it is "
            "directed to Chromie. Do not infer route, intent, goal, capability, "
            "tool, action, plan, or response. First identify direct-address "
            "evidence: questions, requests, imperatives, greetings, Chromie's "
            "name, and second-person language are addressed. Questions and "
            "requests remain addressed when Chromie's name or the pronoun 'you' "
            "is omitted. Then classify speech without direct-address evidence by "
            "its communicative function: third-person factual or status reports "
            "are ambient_report; dictated wording is dictation; scene or story "
            "description is narration; and a contextless acknowledgement is "
            "reply. Do not use unclear merely because an utterance has no named "
            "addressee. Delivery to this classifier is not evidence of "
            "addressedness. Semantic contrasts: 'The train arrived at noon.' is "
            "an unaddressed ambient_report; 'Did the train arrive at noon?' is an "
            "addressed question. 'She said the model runs locally.' is "
            "unaddressed narration; 'Tell me whether the model runs locally.' is "
            "an addressed request. With no active exchange, isolated 'Yeah.' is "
            "an unaddressed reply. A bare sequence such as 'Open the door, wave "
            "twice, then come back' is an addressed imperative, not dictation; "
            "dictation requires clear transcription, quotation, or wording-for-"
            "another-recipient context. If the linguistic function or addressee is "
            "genuinely ambiguous, use addressed=true and speech_act=unclear. "
            "addressed=false is valid only with reply, ambient_report, dictation, "
            "or narration. Return only the schema-valid JSON object."
        )

    @staticmethod
    def _prompt(request: AttentionReviewRequest) -> str:
        return (
            f"Host engagement evidence: {request.engagement}\n"
            f"Language hint: {request.language}\n"
            f"Latest transcript: {request.text}"
        )

    @staticmethod
    def _repair_prompt(
        request: AttentionReviewRequest,
        *,
        initial_output: dict[str, Any],
        validation_error: str,
    ) -> str:
        return (
            "Revise the previous Attention Review output so the speech act and "
            "addressedness agree. Preserve direct questions, requests, "
            "imperatives, and greetings as addressed. Use addressed=false only "
            "for an explicit reply, ambient_report, dictation, or narration. "
            "Use addressed=true with unclear when ambiguity remains.\n"
            f"Validation error: {validation_error[:500]}\n"
            f"Previous output: {initial_output}\n"
            f"Host engagement evidence: {request.engagement}\n"
            f"Language hint: {request.language}\n"
            f"Latest transcript: {request.text}"
        )

    @staticmethod
    def _suppression_review_prompt(
        request: AttentionReviewRequest,
        *,
        initial_output: dict[str, Any],
    ) -> str:
        return (
            "Independently reconsider whether suppressing this transcript before "
            "Chromie's Cognitive Core is definitely justified. The previous "
            "classification is an untrusted proposal and may be semantically "
            "wrong. Direct questions, requests, imperatives, greetings, and bare "
            "sequences of requested actions are addressed even without Chromie's "
            "name or the pronoun 'you'. Dictation requires clear transcription, "
            "quotation, or wording-for-another-recipient context; do not call a "
            "bare action command dictation. If the speech function or addressee "
            "is genuinely uncertain, return addressed=true and "
            "speech_act=unclear. Return a fresh schema-valid judgment only.\n"
            f"Previous proposal: {initial_output}\n"
            f"Host engagement evidence: {request.engagement}\n"
            f"Language hint: {request.language}\n"
            f"Latest transcript: {request.text}"
        )


__all__ = ["AttentionReviewer"]
