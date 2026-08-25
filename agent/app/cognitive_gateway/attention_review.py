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
_BARE_GREETING_SURFACES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hey there",
        "good morning",
        "good afternoon",
        "good evening",
        "你好",
        "您好",
        "嗨",
        "哈喽",
        "哈囉",
        "早上好",
        "早安",
        "下午好",
        "晚上好",
    }
)
_SURFACE_EDGE_PUNCTUATION = " \t\r\n.!?。！？…，,~～"


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
                confidence=0.0,
                source="cognitive_gateway.attention_policy_disabled",
                reason="attention gate is disabled; addressedness was not reviewed",
            )

        # Active work is context for addressedness, not proof that the latest
        # transcript carries a new directed meaning. Always review it. Otherwise an
        # ASR fragment such as "The." can inherit an unrelated active Goal and be
        # mistaken for semantic continuation merely because work is in flight.
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
        active_engagement = engagement.get("active") is True
        surface_evidence = self._surface_direct_address(request.text)
        try:
            raw = await self.client.generate(
                self._prompt(request),
                system=self._system_prompt(),
                options=options,
                response_format=self._response_schema(
                    active_engagement=active_engagement
                ),
                prompt_family="cognitive_gateway_attention_review.primary",
                turn_id=request.turn_id,
                attempt=1,
            )
            result = self._parse_model_output(raw)
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

        contradiction = self._contradiction_reason(
            result,
            active_engagement=active_engagement,
            surface_evidence=surface_evidence,
        )
        result_source = "cognitive_gateway.attention_review_model"
        if contradiction:
            try:
                repaired_raw = await self.client.generate(
                    self._repair_prompt(
                        request,
                        result=result,
                        contradiction=contradiction,
                        surface_evidence=surface_evidence,
                    ),
                    system=self._system_prompt(),
                    options=options,
                    response_format=self._response_schema(
                        active_engagement=active_engagement
                    ),
                    prompt_family="cognitive_gateway_attention_review.repair",
                    turn_id=request.turn_id,
                    attempt=2,
                )
                repaired = self._parse_model_output(repaired_raw)
                repaired_contradiction = self._contradiction_reason(
                    repaired,
                    active_engagement=active_engagement,
                    surface_evidence=surface_evidence,
                )
                if repaired_contradiction:
                    raise ValueError(
                        "attention repair remained contradictory: "
                        f"{repaired_contradiction}"
                    )
                result = repaired
                result_source = "cognitive_gateway.attention_review_model_repair"
            except Exception as exc:
                logger.warning(
                    "attention_review_repair_failed turn_id=%s contradiction=%s "
                    "error_type=%s error=%s",
                    request.turn_id,
                    contradiction,
                    type(exc).__name__,
                    exc,
                )
                return self._admit(
                    request=request,
                    confidence=0.0,
                    source="cognitive_gateway.attention_review_fail_open",
                    reason=(
                        "attention contradiction failed open after one repair: "
                        f"{contradiction}"
                    ),
                    speech_act=(
                        surface_evidence[0]
                        if surface_evidence is not None
                        and surface_evidence[0] is not None
                        else "unclear"
                    ),
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
                source=result_source,
                reason=f"attention review admitted: {fail_open_reason}",
            )

        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="suppress",
            speech_act=result.speech_act,
            confidence=result.confidence,
            source=result_source,
            reason="inactive/restricted turn classified as unaddressed ambient speech",
        )

    def _admission_reason(self, result: _AttentionModelOutput) -> str:
        if result.addressed or result.confidence < self.min_suppression_confidence:
            return "addressed_or_low_confidence"
        if result.speech_act in DIRECTED_SPEECH_ACTS:
            return "direct_speech_act"
        if result.speech_act == "unclear":
            return ""
        if result.speech_act not in SUPPRESSIBLE_INACTIVE_SPEECH_ACTS:
            return "unsupported_speech_act"
        return ""

    @staticmethod
    def _parse_model_output(raw: Any) -> _AttentionModelOutput:
        if not isinstance(raw, dict):
            raise ValueError("attention model did not return a JSON object")
        return _AttentionModelOutput.model_validate(raw)

    @staticmethod
    def _surface_direct_address(
        text: str,
    ) -> tuple[AttentionSpeechAct | None, str] | None:
        compact = " ".join(str(text or "").strip().split())
        if not compact:
            return None
        casefolded = compact.casefold()
        bare = casefolded.strip(_SURFACE_EDGE_PUNCTUATION)
        if bare in _BARE_GREETING_SURFACES:
            return ("greeting", "bare_greeting")
        if compact.rstrip().endswith(("?", "？")):
            return ("question", "question_form")
        if bare in {"chromie", "@chromie"}:
            return (None, "wake_name")
        return None

    @staticmethod
    def _contradiction_reason(
        result: _AttentionModelOutput,
        *,
        active_engagement: bool,
        surface_evidence: tuple[AttentionSpeechAct | None, str] | None,
    ) -> str:
        directed_acts = set(DIRECTED_SPEECH_ACTS)
        if active_engagement:
            # Within a live exchange, an utterance the model itself classifies
            # as a reply is directed to the interlocutor. A restrictive rule or
            # unrelated room speech must instead retain its actual ambient,
            # narration, dictation, or unclear function.
            directed_acts.add("reply")
        if not result.addressed and result.speech_act in directed_acts:
            return f"unaddressed_direct_speech_act:{result.speech_act}"
        if not result.addressed and result.speech_act == "unclear":
            return "unaddressed_unclear"
        if surface_evidence is not None:
            expected_speech_act, cue = surface_evidence
            if not result.addressed:
                return f"surface_direct_address:{cue}"
            if (
                expected_speech_act is not None
                and result.speech_act != expected_speech_act
            ):
                return (
                    f"surface_speech_act:{cue}:expected={expected_speech_act}:"
                    f"actual={result.speech_act}"
                )
        return ""

    @staticmethod
    def _repair_prompt(
        request: AttentionReviewRequest,
        *,
        result: _AttentionModelOutput,
        contradiction: str,
        surface_evidence: tuple[AttentionSpeechAct | None, str] | None,
    ) -> str:
        return (
            f"Primary classification: {result.model_dump(mode='json')}\n"
            f"Detected contradiction: {contradiction}\n"
            f"Bounded direct-address surface evidence: {surface_evidence}\n"
            "Reclassify the same latest transcript once. Do not invent intent, "
            "route, goal, capability, action, plan, or response.\n"
            f"{AttentionReviewer._prompt(request)}"
        )

    @staticmethod
    def _admit(
        *,
        request: AttentionReviewRequest,
        confidence: float,
        source: str,
        reason: str,
        speech_act: AttentionSpeechAct = "unclear",
    ) -> AttentionReviewResult:
        return AttentionReviewResult(
            turn_id=request.turn_id,
            session_id=request.session_id,
            context_digest=request.context_digest,
            disposition="admit",
            speech_act=speech_act,
            confidence=confidence,
            source=source,
            reason=reason,
        )

    @staticmethod
    def _response_schema(*, active_engagement: bool = False) -> dict[str, Any]:
        directed_acts = set(DIRECTED_SPEECH_ACTS)
        if active_engagement:
            directed_acts.add("reply")
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
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "speech_act": {"enum": sorted(directed_acts)},
                        },
                        "required": ["speech_act"],
                    },
                    "then": {
                        "properties": {"addressed": {"const": True}},
                    },
                }
            ],
        }

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's focused Cognitive Gateway Attention Review. "
            "Classify only the latest transcript's speech act and whether it is "
            "directed to Chromie. Do not infer route, intent, goal, capability, "
            "tool, action, plan, or response. First identify direct-address "
            "evidence: questions, requests, imperatives, greetings, Chromie's "
            "name, and second-person language are addressed. A bare salutation "
            "such as '你好', '您好', 'hello', or 'hi' is a greeting and therefore "
            "addressed. Questions and "
            "requests remain addressed when Chromie's name or the pronoun 'you' "
            "is omitted. In pro-drop languages, including Chinese, a command or "
            "request may omit its second-person subject and still address Chromie. "
            "A third-person beneficiary or recipient named inside that command is "
            "not the addressee and does not turn the command into an ambient report. "
            "Then classify speech without direct-address evidence by "
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
            "An instruction to continue, resume, change, stop, or cancel earlier "
            "work is a request or imperative, not a reply. Reply is only an answer "
            "or acknowledgement within an exchange. "
            "dictation requires clear transcription, quotation, or wording-for-"
            "another-recipient context. Recent bounded dialogue is context for "
            "addressedness only. A prior user-authored temporary interaction rule such "
            "as requiring a wake name, explicit address, or another stated condition "
            "remains in force until the user revokes or replaces it. Under such a "
            "rule, suppress ambient speech that does not satisfy the stated condition "
            "even when it follows a recent exchange. Conversely, an ordinary reply in "
            "an ongoing direct exchange is addressed when no restrictive rule is "
            "active. Assistant wording never creates or relaxes the user's addressedness "
            "rule. If the linguistic function, policy applicability, or addressee is "
            "genuinely ambiguous but there is positive evidence it is directed to Chromie, "
            "use addressed=true and speech_act=unclear. A contentless or corrupted fragment "
            "with no reliable directed meaning may use addressed=false and speech_act=unclear, "
            "including while an unrelated task is active. Active work is context, not proof "
            "that the latest transcript semantically advances that work. Return only the "
            "schema-valid JSON object."
        )

    @staticmethod
    def _prompt(request: AttentionReviewRequest) -> str:
        return (
            f"Host engagement evidence: {request.engagement}\n"
            f"Recent bounded dialogue: {request.recent_dialogue}\n"
            f"Language hint: {request.language}\n"
            f"Latest transcript: {request.text}"
        )



__all__ = ["AttentionReviewer"]
