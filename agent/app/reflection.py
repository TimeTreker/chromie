from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .prompt_projection import bounded_json
from .clients.ollama_client import OllamaClient
from .cognitive_identity import (
    STABLE_MIND_SEMANTIC_CONTRACT,
    bounded_stable_mind_json,
)
try:
    from chromie_contracts.reflection import (
        ReflectionRequest,
        ReflectionAction,
        ReflectionMemoryCandidate,
        ReflectionResolution,
    )
    from chromie_contracts.situation import CognitiveOpportunity
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.reflection import (
        ReflectionRequest,
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

    async def resolve(self, request: ReflectionRequest) -> ReflectionResolution:
        context = request.context if isinstance(request.context, dict) else {}
        opportunity = request.opportunity
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
        return bounded_json(value, limit)

    def _prompt(
        self,
        request: ReflectionRequest,
        opportunity: CognitiveOpportunity,
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        return (
            "Reflect only because trusted runtime raised a slow cognitive opportunity from "
            "recorded evidence. The target Responsibility may still be open or may already be "
            "terminal. For an open Responsibility, you may propose future replanning, "
            "clarification, a forward user correction, or bounded local memory. For terminal "
            "history, never replan, clarify, correct, reopen, or rewrite that Responsibility; "
            "you may only propose evidence-grounded experience/calibration memory that can help "
            "future cognition. One episode may justify local advisory context about that episode; "
            "it does not establish a systemic/global heuristic. Do not cache semantic decisions "
            "such as phrase-to-Capability or pattern-to-always/never-Deep shortcuts. Do not "
            "reinterpret historical execution facts, authorize effects, or change identity, "
            "personality, values, safety policy, shared Fast/Deep policy, provider capability, "
            "permissions, prompts, or models. Memory proposals are task/session only; trusted "
            "runtime, not this model, bounds their lifetime and persistence.\n\n"
            f"{STABLE_MIND_SEMANTIC_CONTRACT}\n\n"
            "Owner-approved Stable Mind worldview/values JSON:\n"
            f"{bounded_stable_mind_json(context)}\n\n"
            f"Authoritative user text:\n{request.text}\n\n"
            f"Cognitive opportunity JSON:\n{self._bounded(opportunity.prompt_projection(), 3000)}\n\n"
            f"Recorded execution outcome JSON:\n{self._bounded(context.get('execution_outcome_bundle') or {}, 9000)}\n\n"
            f"Active Goal projections JSON:\n{self._bounded(context.get('active_goal_snapshots') or [], 6000)}\n\n"
            f"Recent terminal Goal projections JSON:\n{self._bounded(context.get('recent_goal_snapshots') or [], 6000)}\n\n"
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
