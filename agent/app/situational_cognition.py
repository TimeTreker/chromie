from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .clients.ollama_client import OllamaClient
from .cognitive_identity import (
    STABLE_MIND_SEMANTIC_CONTRACT,
    bounded_stable_mind_json,
)
from .prompt_projection import bounded_json

try:
    from chromie_contracts.situation import (
        SituationalCognitionDisposition,
        SituationalCognitionRequest,
        SituationalCognitionResolution,
        SituationalCommunicativeAct,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.situation import (
        SituationalCognitionDisposition,
        SituationalCognitionRequest,
        SituationalCognitionResolution,
        SituationalCommunicativeAct,
    )


class SituationalCognitionModelOutput(BaseModel):
    """Model-facing Goal-free cognition result; Runtime binds all provenance."""

    model_config = ConfigDict(extra="forbid")

    disposition: SituationalCognitionDisposition
    activity: SituationalCommunicativeAct | None = None
    reason_summary: str = Field(default="", max_length=600)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_shape(self) -> "SituationalCognitionModelOutput":
        if self.disposition == "silence" and self.activity is not None:
            raise ValueError("silence output must not carry an activity")
        if self.disposition == "communicate" and self.activity is None:
            raise ValueError("communicate output requires an activity")
        return self


class SituationalCognitionResolver:
    """Stateless same-Core invocation for Goal-free current-Situation cognition.

    This resolver owns no durable state, Goal, Work, authorization, or independent
    conversation authority. It may author at most one exact low-commitment speech
    Activity from the trusted Situation supplied by Runtime. Runtime binds provenance
    and may suppress invalid or stale output but never rewrites the wording.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        num_ctx: int = 8192,
        num_predict: int = 512,
    ) -> None:
        self.ollama = ollama
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(
        self,
        request: SituationalCognitionRequest,
    ) -> SituationalCognitionResolution:
        opportunity = request.opportunity
        if opportunity.recommended_cognition == "local":
            return self._resolution(
                request,
                disposition="silence",
                activity=None,
                reason_summary="The Situation change is local-only and does not warrant outward speech.",
            )
        if opportunity.recommended_cognition == "slow":
            # PSM-1 deliberately does not invent a second Deep Planner or a background
            # deliberative owner. Goal-free deliberative cognition is a later bounded
            # extension; until then consequential/uncertain readiness fails quiet.
            return self._resolution(
                request,
                disposition="silence",
                activity=None,
                reason_summary="Goal-free deliberative cognition is not yet qualified; remain silent.",
            )

        raw = await self.ollama.generate(
            self._prompt(request),
            system=self._system_prompt(),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            response_format=SituationalCognitionModelOutput.model_json_schema(),
        )
        output = SituationalCognitionModelOutput.model_validate(raw)
        return self._resolution(
            request,
            disposition=output.disposition,
            activity=output.activity,
            reason_summary=output.reason_summary,
        )

    @staticmethod
    def _resolution(
        request: SituationalCognitionRequest,
        *,
        disposition: SituationalCognitionDisposition,
        activity: SituationalCommunicativeAct | None,
        reason_summary: str,
    ) -> SituationalCognitionResolution:
        opportunity = request.opportunity
        return SituationalCognitionResolution(
            opportunity_id=opportunity.opportunity_id,
            situation_digest=request.situation.digest,
            source_refs=list(opportunity.source_refs),
            subject_refs=list(opportunity.subject_refs),
            disposition=disposition,
            activity=activity,
            reason_summary=reason_summary,
        )

    def _prompt(self, request: SituationalCognitionRequest) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "This is one Goal-free current-Situation cognition opportunity. Nobody has "
            "issued a task and no fake Goal or user request exists. Decide whether Chromie "
            "should remain silent or make exactly one small, socially appropriate outward "
            "utterance from the trusted Situation now. Silence is a successful and common "
            "choice. Speak only when there is a useful semantic/social delta that a real "
            "twelve-year-old girl in this relationship/context would naturally express. "
            "Never turn Capability availability into demand, never create Work, never claim "
            "an effect happened, never offer generic assistant service, and never infer a "
            "person identity, relationship, private fact, motive, emotion, or permission "
            "beyond the supplied context. Activated Memory has already passed Runtime's "
            "disclosure gate; use only the entries actually supplied, never infer hidden "
            "Memory, and never treat a relationship label as privacy, factual-trust, or "
            "authorization evidence. Keep initiative low-consequence, reversible, "
            "brief, and non-intrusive. If the Situation is uncertain, consequential, private, "
            "already acknowledged, or another person appears occupied, prefer silence. "
            "The activity text, when present, is the exact wording to say.\n\n"
            f"{STABLE_MIND_SEMANTIC_CONTRACT}\n\n"
            "Owner-approved Stable Mind JSON:\n"
            f"{bounded_stable_mind_json(context)}\n\n"
            "Current Goal-free Situation JSON:\n"
            f"{bounded_json(request.situation.prompt_projection(), 7000)}\n\n"
            "Cognitive Opportunity JSON:\n"
            f"{bounded_json(request.opportunity.prompt_projection(), 3000)}\n\n"
            "Deterministic Situational Salience JSON:\n"
            f"{bounded_json(context.get('situational_salience') or {}, 1200)}\n\n"
            "Relevant Memory Summary:\n"
            f"{bounded_json(context.get('memory_summary') or '', 1800)}\n\n"
            "Activated extracted Memory JSON:\n"
            f"{bounded_json(context.get('extracted_memory') or [], 5000)}\n\n"
            "Delivered/pending Interaction Context JSON:\n"
            f"{bounded_json(context.get('interaction_context') or {}, 5000)}\n\n"
            f"Language: {request.language}\n\n"
            "Return only the exact SituationalCognitionModelOutput JSON."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a bounded situational cognition invocation inside Chromie's one Cognitive "
            "Core. You are not a Planner, assistant, social manager, or autonomous task creator. "
            "You may choose silence or author one exact low-commitment social utterance from "
            "trusted current Situation. Preserve Chromie's Stable Mind and remain concise."
        )
