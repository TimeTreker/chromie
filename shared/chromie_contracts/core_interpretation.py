from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .route import RouteDecision, RouteName
from .user_turn import UserTurnEnvelope, normalize_turn_text


class CoreInterpretationResult(BaseModel):
    """Core-owned semantic interpretation with an isolated legacy projection.

    ``compatibility_projection`` exists only while downstream planner contracts
    still consume ``RouteDecision``.  The projection is digest-bound and must
    agree with the Core-owned lane/intent identity; it is not a Gateway output.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["goal_driven_cognitive_core"] = "goal_driven_cognitive_core"
    lane: RouteName
    intent: str = Field(default="unknown", min_length=1, max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = Field(default="auto", min_length=1, max_length=64)
    projection_schema: Literal["route_decision_v1_compatibility"] = (
        "route_decision_v1_compatibility"
    )
    compatibility_projection: RouteDecision
    projection_digest: str = Field(min_length=64, max_length=64)

    @field_validator("turn_id", "session_id", "intent", "language", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @staticmethod
    def digest_projection(decision: RouteDecision) -> str:
        payload = decision.model_dump(mode="json", exclude_none=True)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @model_validator(mode="after")
    def validate_projection_identity(self) -> "CoreInterpretationResult":
        decision = self.compatibility_projection
        if decision.route != self.lane:
            raise ValueError("Core interpretation lane does not match compatibility projection")
        if normalize_turn_text(decision.intent) != self.intent:
            raise ValueError("Core interpretation intent does not match compatibility projection")
        if abs(float(decision.confidence) - float(self.confidence)) > 1e-9:
            raise ValueError(
                "Core interpretation confidence does not match compatibility projection"
            )
        if normalize_turn_text(decision.language or "auto") != self.language:
            raise ValueError(
                "Core interpretation language does not match compatibility projection"
            )
        if self.projection_digest != self.digest_projection(decision):
            raise ValueError("Core interpretation compatibility projection digest mismatch")
        return self

    @classmethod
    def from_route_decision(
        cls,
        *,
        envelope: UserTurnEnvelope,
        decision: RouteDecision,
    ) -> "CoreInterpretationResult":
        return cls(
            turn_id=envelope.turn_id,
            session_id=envelope.session_id,
            lane=decision.route,
            intent=normalize_turn_text(decision.intent or "unknown") or "unknown",
            confidence=decision.confidence,
            language=normalize_turn_text(decision.language or "auto") or "auto",
            compatibility_projection=decision,
            projection_digest=cls.digest_projection(decision),
        )

    def route_decision_projection(self) -> RouteDecision:
        """Return a defensive copy for compatibility-only downstream adapters."""

        return self.compatibility_projection.model_copy(deep=True)
