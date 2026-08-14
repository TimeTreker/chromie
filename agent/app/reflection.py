from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .clients.ollama_client import OllamaClient
from .schema import AgentRunRequest

try:
    from chromie_contracts.reflection import (
        ReflectionAction,
        ReflectionMemoryCandidate,
        ReflectionResolution,
    )
    from chromie_contracts.situation import CognitiveOpportunity
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.reflection import (
        ReflectionAction,
        ReflectionMemoryCandidate,
        ReflectionResolution,
    )
    from shared.chromie_contracts.situation import CognitiveOpportunity


class ReflectionModelOutput(BaseModel):
    """Model-facing Reflection proposal; runtime owns all grounding references."""

    model_config = ConfigDict(extra="forbid")

    actions: list[ReflectionAction] = Field(default_factory=list, max_length=4)
    correction_text: str = Field(default="", max_length=600)
    memory_candidates: list[ReflectionMemoryCandidate] = Field(
        default_factory=list,
        max_length=4,
    )
    reason_summary: str = Field(default="", max_length=600)

    @field_validator("correction_text", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_actions(self) -> "ReflectionModelOutput":
        if self.correction_text and "correct_user" not in self.actions:
            raise ValueError("correction_text requires correct_user")
        if "correct_user" in self.actions and not self.correction_text:
            raise ValueError("correct_user requires correction_text")
        if self.memory_candidates and "propose_memory" not in self.actions:
            raise ValueError("memory candidates require propose_memory")
        if "propose_memory" in self.actions and not self.memory_candidates:
            raise ValueError("propose_memory requires memory candidates")
        return self


class ReflectionResolver:
    """Run selective slow cognition only for a trusted slow opportunity."""

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        num_ctx: int = 8192,
        num_predict: int = 640,
    ) -> None:
        self.ollama = ollama
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def resolve(self, request: AgentRunRequest) -> ReflectionResolution:
        context = request.context if isinstance(request.context, dict) else {}
        opportunity = CognitiveOpportunity.model_validate(
            context.get("cognitive_opportunity")
        )
        if opportunity.recommended_cognition != "slow":
            return ReflectionResolution(
                opportunity_id=opportunity.opportunity_id,
                goal_ids=opportunity.goal_ids,
                evidence_refs=opportunity.evidence_refs,
                reason_codes=opportunity.reason_codes,
                reason_summary="Slow Reflection was not required for this opportunity.",
            )
        if not opportunity.evidence_refs:
            return ReflectionResolution(
                opportunity_id=opportunity.opportunity_id,
                goal_ids=opportunity.goal_ids,
                evidence_refs=[],
                reason_codes=opportunity.reason_codes,
                reason_summary="Reflection requires trusted evidence before future adaptation.",
            )
        if opportunity.trigger == "execution_outcome":
            outcome_bundle = context.get("execution_outcome_bundle")
            outcome_id = (
                str(outcome_bundle.get("outcome_id") or "").strip()
                if isinstance(outcome_bundle, dict)
                else ""
            )
            if not outcome_id or outcome_id not in opportunity.evidence_refs:
                return ReflectionResolution(
                    opportunity_id=opportunity.opportunity_id,
                    goal_ids=opportunity.goal_ids,
                    evidence_refs=opportunity.evidence_refs,
                    reason_codes=opportunity.reason_codes,
                    reason_summary=(
                        "Reflection execution evidence did not match the trusted opportunity."
                    ),
                )

        raw = await self.ollama.generate(
            self._prompt(request, opportunity),
            system=self._system_prompt(),
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            response_format=ReflectionModelOutput.model_json_schema(),
        )
        proposal = ReflectionModelOutput.model_validate(raw)
        return ReflectionResolution(
            opportunity_id=opportunity.opportunity_id,
            goal_ids=opportunity.goal_ids,
            evidence_refs=opportunity.evidence_refs,
            reason_codes=opportunity.reason_codes,
            actions=proposal.actions,
            correction_text=proposal.correction_text,
            memory_candidates=proposal.memory_candidates,
            reason_summary=proposal.reason_summary,
        )

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(
        self,
        request: AgentRunRequest,
        opportunity: CognitiveOpportunity,
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "Reflect only because trusted runtime raised a slow cognitive opportunity from "
            "recorded evidence. Decide whether the still-open responsibility needs future "
            "replanning, clarification, a forward user correction, or a reusable memory "
            "proposal. Do not rewrite or "
            "reinterpret historical execution facts. Do not authorize effects. Do not change "
            "identity, personality, values, safety policy, provider capability, or permissions. "
            "A one-off failure is normally not worth memory; propose memory only for a pattern "
            "that would be useful in later cognition. Memory proposals are task/session only.\n\n"
            f"Authoritative user text:\n{request.text}\n\n"
            f"Cognitive opportunity JSON:\n{self._bounded(opportunity.prompt_projection(), 3000)}\n\n"
            f"Recorded execution outcome JSON:\n{self._bounded(context.get('execution_outcome_bundle') or {}, 9000)}\n\n"
            f"Active Goal projections JSON:\n{self._bounded(context.get('active_goal_snapshots') or [], 6000)}\n\n"
            f"Current Situation projection JSON:\n{self._bounded(context.get('situation') or {}, 4000)}\n\n"
            "Return only the exact ReflectionModelOutput JSON. Goal IDs and evidence references "
            "are not model fields; trusted runtime binds them after validation."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's selective Reflection ability. Reflection proposes future adaptation "
            "from trusted evidence. It never rewrites history, grants authority, or silently "
            "changes Stable Mind. Keep actions minimal and evidence-grounded."
        )
