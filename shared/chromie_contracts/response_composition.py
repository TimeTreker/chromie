from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields
from .plan import CanonicalPlan
from .semantic_task import ResponsePlan, ResponseStage
from .social_attention import SocialAttentionPlan

ResponseCompositionStatus = Literal["resolved", "model_unavailable", "invalid_input"]
ResponseCompositionPhase = Literal["pre_execution"]


def canonical_plan_fingerprint(plan: CanonicalPlan) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CoordinatedResponsePlan(BaseModel):
    """Immutable task plan plus truthful speech and optional social presence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    composition_id: str = Field(min_length=1)
    phase: ResponseCompositionPhase = "pre_execution"
    canonical_plan_id: str = Field(min_length=1)
    canonical_plan_fingerprint: str = Field(min_length=16)
    canonical_plan: CanonicalPlan
    response_plan: ResponsePlan
    social_attention_plan: SocialAttentionPlan | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "composition_id",
        "canonical_plan_id",
        "canonical_plan_fingerprint",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @staticmethod
    def _stages(plan: ResponsePlan) -> list[ResponseStage]:
        return [
            stage
            for stage in (
                plan.immediate,
                plan.pre_action,
                *plan.progress,
                plan.final,
            )
            if stage is not None
        ]

    @model_validator(mode="after")
    def validate_coordination(self) -> "CoordinatedResponsePlan":
        plan = self.canonical_plan
        if plan.disposition == "escalate":
            raise ValueError("response composition requires a terminal canonical plan")
        if self.canonical_plan_id != plan.plan_id:
            raise ValueError("canonical_plan_id must match the embedded immutable plan")
        expected_fingerprint = canonical_plan_fingerprint(plan)
        if self.canonical_plan_fingerprint != expected_fingerprint:
            raise ValueError("canonical plan fingerprint mismatch")

        stages = self._stages(self.response_plan)
        if not stages:
            raise ValueError("terminal canonical plans require at least one spoken response stage")

        known_goals = set(plan.goal_ids)
        covered_goals: set[str] = set()
        for stage in stages:
            unknown = set(stage.covers_goal_ids) - known_goals
            if unknown:
                raise ValueError(
                    "response stage references unknown goal IDs: " + ",".join(sorted(unknown))
                )
            covered_goals.update(stage.covers_goal_ids)

        if known_goals and covered_goals != known_goals:
            missing = sorted(known_goals - covered_goals)
            raise ValueError("response composition does not cover all plan goals: " + ",".join(missing))

        if plan.disposition == "execute":
            if self.response_plan.final is not None:
                raise ValueError("pre-execution response composition must not include a final stage")
            allowed = {"none", "heard", "evaluating", "waiting_for_user"}
            for stage in stages:
                if stage.commitment_state not in allowed:
                    raise ValueError(
                        "pre-execution response stage overstates commitment: "
                        + stage.commitment_state
                    )
                if not stage.must_not_claim_completion:
                    raise ValueError("pre-execution response stages must forbid completion claims")
        elif plan.disposition == "clarify":
            clarification_stages = [
                stage
                for stage in stages
                if stage.speech_act.casefold() in {"clarify", "ask_clarification"}
                and stage.commitment_state == "waiting_for_user"
            ]
            if not clarification_stages:
                raise ValueError(
                    "clarification plans require a waiting-for-user clarification speech stage"
                )
        elif plan.disposition in {"unavailable", "refused"}:
            if any(stage.commitment_state in {"completed", "executing"} for stage in stages):
                raise ValueError("unavailable or refused plans cannot claim execution or completion")

        if self.social_attention_plan is not None:
            metadata = self.social_attention_plan.metadata
            if metadata.get("auxiliary_social_attention") is not True:
                raise ValueError("social attention plan must be explicitly auxiliary")

        return self


class ResponseCompositionResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResponseCompositionStatus
    composition: CoordinatedResponsePlan | None = None
    reason_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> Any:
        return " ".join(value.strip().split()) if isinstance(value, str) else value

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_status(self) -> "ResponseCompositionResolution":
        if self.status == "resolved" and self.composition is None:
            raise ValueError("resolved response composition requires composition")
        if self.status != "resolved" and self.composition is not None:
            raise ValueError("non-resolved response composition must not carry composition")
        return self
