from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .route import RouteDecision, RouteName
from .user_turn import UserTurnEnvelope, normalize_turn_text


class CoreInterpretationUnavailable(BaseModel):
    """Typed non-semantic outcome when the Core cannot interpret a turn.

    This result deliberately carries no lane, intent, plan, or compatibility
    projection.  Callers must not reinterpret it as ordinary chat.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    status: Literal["interpretation_unavailable"] = "interpretation_unavailable"
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["goal_driven_cognitive_core"] = "goal_driven_cognitive_core"
    failure_class: str = Field(min_length=1, max_length=120)
    retryable: bool = True
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("turn_id", "session_id", "failure_class", "reason", mode="before")
    @classmethod
    def normalize_unavailable_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))


class CognitiveProgressCandidate(BaseModel):
    """Core-authored bounded progress that may become locally ready before Goal closure.

    ``capability`` means the Core already understands one exact capability-shaped
    piece of work; trusted runtime still decides whether it may execute now.
    ``native_response`` means the Core already has a complete conversational
    answer from Chromie's current Mind/context and no external acquisition or
    committed effect is required.  Neither form is a canonical Goal or execution
    authorization before Goal Association binds it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    candidate_id: str = Field(min_length=1, max_length=160)
    kind: Literal["capability", "native_response"] = "capability"
    capability_id: str = Field(default="", max_length=200)
    args: dict[str, Any] = Field(default_factory=dict)
    response_text: str = Field(default="", max_length=600)
    speech_act: str = Field(default="inform", min_length=1, max_length=120)
    intent: str = Field(default="unknown", min_length=1, max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "candidate_id",
        "capability_id",
        "response_text",
        "speech_act",
        "intent",
        mode="before",
    )
    @classmethod
    def normalize_candidate_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @model_validator(mode="after")
    def validate_candidate_shape(self) -> "CognitiveProgressCandidate":
        if self.kind == "capability":
            if not self.capability_id:
                raise ValueError("capability progress requires capability_id")
            if self.response_text:
                raise ValueError("capability progress must not carry response_text")
            return self
        if self.capability_id or self.args:
            raise ValueError("native_response progress must not carry capability work")
        if not self.response_text:
            raise ValueError("native_response progress requires response_text")
        return self

    @staticmethod
    def stable_id(
        *,
        turn_id: str,
        kind: str = "capability",
        capability_id: str = "",
        args: dict[str, Any] | None = None,
        response_text: str = "",
        speech_act: str = "inform",
    ) -> str:
        payload = json.dumps(
            {
                "turn_id": normalize_turn_text(turn_id),
                "kind": normalize_turn_text(kind),
                "capability_id": normalize_turn_text(capability_id),
                "args": dict(args or {}),
                "response_text": normalize_turn_text(response_text),
                "speech_act": normalize_turn_text(speech_act),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"progress_{hashlib.sha256(payload).hexdigest()[:20]}"


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
    progress_candidates: list[CognitiveProgressCandidate] = Field(default_factory=list)
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
    def validate_progress_candidates(self) -> "CoreInterpretationResult":
        ids = [item.candidate_id for item in self.progress_candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Core progress candidate IDs must be unique")
        return self

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
        progress_proposals: list[dict[str, Any]] | None = None,
    ) -> "CoreInterpretationResult":
        progress_candidates: list[CognitiveProgressCandidate] = []
        seen_progress_ids: set[str] = set()

        allowed_capability_ids = {
            normalize_turn_text(item.capability_id)
            for item in decision.routes
            if normalize_turn_text(item.capability_id)
        }
        for action in decision.actions or []:
            if isinstance(action, dict):
                capability_id = normalize_turn_text(action.get("capability_id"))
                if capability_id:
                    allowed_capability_ids.add(capability_id)
        if decision.intent.startswith("capability:"):
            capability_id = normalize_turn_text(decision.intent.split(":", 1)[1])
            if capability_id:
                allowed_capability_ids.add(capability_id)
        conversational_scope = decision.route == "chat" or any(
            item.route == "chat" for item in decision.routes
        )

        # Maintained Core callers pass explicit Fast Understanding progress.
        # ``None`` retains route-derived capability candidates only for older
        # compatibility callers and fixtures; an explicit [] means the model
        # intentionally found no locally-ready progress.
        if progress_proposals is None:
            progress_proposals = [
                {
                    "kind": "capability",
                    "capability_id": item.capability_id,
                    "args": dict(item.args),
                    "intent": item.intent,
                    "confidence": item.confidence,
                }
                for item in decision.routes
                if item.capability_id
            ]

        for raw in progress_proposals:
            if not isinstance(raw, dict):
                continue
            kind = normalize_turn_text(raw.get("kind"))
            intent = normalize_turn_text(raw.get("intent") or decision.intent or "unknown") or "unknown"
            try:
                confidence = float(raw.get("confidence", decision.confidence))
            except (TypeError, ValueError):
                continue
            if kind == "capability":
                capability_id = normalize_turn_text(raw.get("capability_id"))
                args = raw.get("args")
                if capability_id not in allowed_capability_ids or not isinstance(args, dict):
                    continue
                candidate_id = CognitiveProgressCandidate.stable_id(
                    turn_id=envelope.turn_id,
                    kind="capability",
                    capability_id=capability_id,
                    args=args,
                )
                candidate = CognitiveProgressCandidate(
                    candidate_id=candidate_id,
                    kind="capability",
                    capability_id=capability_id,
                    args=dict(args),
                    intent=intent,
                    confidence=confidence,
                )
            elif kind == "native_response":
                response_text = normalize_turn_text(raw.get("response_text"))
                speech_act = normalize_turn_text(raw.get("speech_act") or "inform") or "inform"
                if not conversational_scope or not response_text:
                    continue
                candidate_id = CognitiveProgressCandidate.stable_id(
                    turn_id=envelope.turn_id,
                    kind="native_response",
                    response_text=response_text,
                    speech_act=speech_act,
                )
                candidate = CognitiveProgressCandidate(
                    candidate_id=candidate_id,
                    kind="native_response",
                    response_text=response_text,
                    speech_act=speech_act,
                    intent=intent,
                    confidence=confidence,
                )
            else:
                continue
            if candidate.candidate_id in seen_progress_ids:
                continue
            seen_progress_ids.add(candidate.candidate_id)
            progress_candidates.append(candidate)
        return cls(
            turn_id=envelope.turn_id,
            session_id=envelope.session_id,
            lane=decision.route,
            intent=normalize_turn_text(decision.intent or "unknown") or "unknown",
            confidence=decision.confidence,
            language=normalize_turn_text(decision.language or "auto") or "auto",
            progress_candidates=progress_candidates,
            compatibility_projection=decision,
            projection_digest=cls.digest_projection(decision),
        )

    def route_decision_projection(self) -> RouteDecision:
        """Return a defensive copy for compatibility-only downstream adapters."""

        return self.compatibility_projection.model_copy(deep=True)
