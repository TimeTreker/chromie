from __future__ import annotations

from typing import Any, Literal

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
        SituationalRelationshipMemoryCandidate,
        SituationalSelfMemoryCandidate,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.situation import (
        SituationalCognitionDisposition,
        SituationalCognitionRequest,
        SituationalCognitionResolution,
        SituationalCommunicativeAct,
        SituationalRelationshipMemoryCandidate,
        SituationalSelfMemoryCandidate,
    )


class SituationalCognitionModelOutput(BaseModel):
    """Model-facing Goal-free cognition result; Runtime binds all provenance."""

    model_config = ConfigDict(extra="forbid")

    disposition: Literal["silence", "communicate", "deliberate"]
    activity: SituationalCommunicativeAct | None = None
    memory_candidates: list[SituationalRelationshipMemoryCandidate] = Field(default_factory=list, max_length=4)
    self_memory_candidates: list[SituationalSelfMemoryCandidate] = Field(default_factory=list, max_length=4)
    reason_summary: str = Field(default="", max_length=600)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_shape(self) -> "SituationalCognitionModelOutput":
        if self.disposition in {"silence", "deliberate"} and self.activity is not None:
            raise ValueError(f"{self.disposition} output must not carry an activity")
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
        deliberative_ollama: OllamaClient | None = None,
        num_ctx: int = 8192,
        num_predict: int = 512,
    ) -> None:
        self.ollama = ollama
        self.deliberative_ollama = deliberative_ollama
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
                reason_summary="Local mechanical handling requires no outward cognition.",
            )
        if opportunity.recommended_cognition == "slow":
            return await self._resolve_deliberative(request, fast_reason="trusted readiness requested deliberation")

        output = await self._generate_model_output(request, self.ollama, deliberative=False)
        if output.disposition == "deliberate":
            return await self._resolve_deliberative(request, fast_reason=output.reason_summary)
        return self._resolution(
            request,
            disposition=output.disposition,
            activity=output.activity,
            memory_candidates=output.memory_candidates,
            self_memory_candidates=output.self_memory_candidates,
            reason_summary=output.reason_summary,
        )

    async def _resolve_deliberative(
        self,
        request: SituationalCognitionRequest,
        *,
        fast_reason: str,
    ) -> SituationalCognitionResolution:
        if self.deliberative_ollama is None:
            return self._resolution(
                request,
                disposition="silence",
                activity=None,
                reason_summary="Deliberative situational cognition is unavailable; fail quiet.",
            )
        output = await self._generate_model_output(
            request,
            self.deliberative_ollama,
            deliberative=True,
            fast_reason=fast_reason,
        )
        if output.disposition == "deliberate":
            raise ValueError("deliberative situational cognition cannot recurse")
        return self._resolution(
            request,
            disposition=output.disposition,
            activity=output.activity,
            memory_candidates=output.memory_candidates,
            self_memory_candidates=output.self_memory_candidates,
            reason_summary=output.reason_summary,
        )

    async def _generate_model_output(
        self,
        request: SituationalCognitionRequest,
        ollama: OllamaClient,
        *,
        deliberative: bool,
        fast_reason: str = "",
    ) -> SituationalCognitionModelOutput:
        raw = await ollama.generate(
            self._prompt(request, deliberative=deliberative, fast_reason=fast_reason),
            system=self._system_prompt(deliberative=deliberative),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            response_format=SituationalCognitionModelOutput.model_json_schema(),
        )
        return SituationalCognitionModelOutput.model_validate(raw)

    @staticmethod
    def _resolution(
        request: SituationalCognitionRequest,
        *,
        disposition: SituationalCognitionDisposition,
        activity: SituationalCommunicativeAct | None,
        memory_candidates: list[SituationalRelationshipMemoryCandidate] | None = None,
        self_memory_candidates: list[SituationalSelfMemoryCandidate] | None = None,
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
            memory_candidates=list(memory_candidates or []),
            self_memory_candidates=list(self_memory_candidates or []),
            reason_summary=reason_summary,
        )

    def _prompt(self, request: SituationalCognitionRequest, *, deliberative: bool = False, fast_reason: str = "") -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            ("This is the one bounded DELIBERATIVE continuation of a Goal-free current-Situation cognition opportunity. " if deliberative else "This is one Goal-free current-Situation cognition opportunity. ")
            + "Nobody has "
            "issued a task and no fake Goal or user request exists. Decide whether Chromie "
            "should remain silent or make exactly one small, socially appropriate outward "
            "utterance from the trusted Situation now. You own the semantic judgment of "
            "whether this Situation matters enough for an outward response; Runtime has not "
            "pre-classified the event with social keyword, person-type, relationship, or "
            "priority rules. Silence is a successful and common choice. Reason holistically "
            "from current Situation, disclosure-safe Memory, actual Interaction history, and "
            "Stable Mind. Speak only when there is a useful semantic/social delta that a real "
            "twelve-year-old girl in this relationship/context would naturally express. "
            "Never turn Capability availability into demand, never create Work, never claim "
            "an effect happened, never offer generic assistant service, and never infer a "
            "person identity, relationship, private fact, motive, emotion, or permission "
            "beyond the supplied context. Activated Memory has already passed Runtime's "
            "disclosure gate; use only the entries actually supplied, never infer hidden "
            "Memory, and never treat a relationship label as privacy, factual-trust, or "
            "authorization evidence. Keep initiative low-consequence, reversible, "
            "brief, and non-intrusive. Treat the supplied current audience as exact only when "
            "Situation provides it; never infer missing listeners or widen disclosure. Consider "
            "uncertainty, consequence, privacy, interruption, prior delivery, relationship, and "
            "the person's apparent engagement together rather than by fixed rules. The activity "
            "text, when present, is the exact wording to say.\n\n"
            f"{STABLE_MIND_SEMANTIC_CONTRACT}\n\n"
            "Owner-approved Stable Mind JSON:\n"
            f"{bounded_stable_mind_json(context)}\n\n"
            "Current Goal-free Situation JSON:\n"
            f"{bounded_json(request.situation.prompt_projection(), 7000)}\n\n"
            "Cognitive Opportunity JSON:\n"
            f"{bounded_json(request.opportunity.prompt_projection(), 3000)}\n\n"
            "Relevant Memory Summary:\n"
            f"{bounded_json(context.get('memory_summary') or '', 1800)}\n\n"
            "Activated extracted Memory JSON:\n"
            f"{bounded_json(context.get('extracted_memory') or [], 5000)}\n\n"
            "Delivered/pending Interaction Context JSON:\n"
            f"{bounded_json(context.get('interaction_context') or {}, 5000)}\n\n"
            f"Language: {request.language}\n\n"
            + (f"Fast cognition escalation reason: {fast_reason}\n\n" if deliberative and fast_reason else "")
            + ("This is already the deliberative pass: disposition must be silence or communicate; never deliberate again. " if deliberative else "If broader reasoning is genuinely needed before a safe/natural decision, disposition=deliberate with no activity. ")
            + "If this interaction created a reusable shared experience, you may also propose a small private memory candidate grounded only in supplied Situation/source refs; record the episode, not a permanent relationship label. You may also retain one short-lived self_concern or interest when it is genuinely Chromie's own unfinished curiosity/interest; it is context only, never a Goal, action, timer, or permission. Return only the exact SituationalCognitionModelOutput JSON."
        )

    @staticmethod
    def _system_prompt(*, deliberative: bool = False) -> str:
        return (
            ("You are the bounded deliberative pass of " if deliberative else "You are a bounded ")
            + "situational cognition inside Chromie's one Cognitive Core. "
            "You are not a Planner, assistant, social manager, or autonomous task creator. "
            "You may choose silence or author one exact low-commitment social utterance from "
            "trusted current Situation. Preserve Chromie's Stable Mind and remain concise."
        )
