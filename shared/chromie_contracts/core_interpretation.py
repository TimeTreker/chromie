from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields
from .route import RouteDecision, RouteName
from .user_turn import UserTurnEnvelope, normalize_turn_text


_PLANNER_OWNED_BINDING_FIELDS = frozenset({
    "capability_id",
    "skill_id",
    "tool_name",
    "provider_id",
    "execution_method",
    "executable_args",
    "args",
    "actions",
    "primary_activity",
    "activity_id",
    "work_item_id",
    "plan_step_id",
    "execution_lane",
    "realization",
    "vocal_mode",
    "coordination_id",
    "execution_item_ids",
})


def _reject_planner_owned_bindings(value: Any, *, path: str = "bindings") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key or "").strip().casefold()
            if normalized in _PLANNER_OWNED_BINDING_FIELDS:
                raise ValueError(
                    f"Planner-owned field {key!r} is forbidden in responsibility {path}"
                )
            _reject_planner_owned_bindings(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_planner_owned_bindings(item, path=f"{path}[{index}]")
    return value


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


class CognitiveResponsibilityProposal(BaseModel):
    """Core-owned provider-neutral interpretation of one human responsibility.

    This is the authoritative WHAT handoff from Goal Interpretation to downstream
    cognition. Fast Planner is the first HOW owner when meaning is sufficient, while
    Goal Association remains the only stage that can create or mutate canonical Goals.
    The proposal deliberately carries no response wording, Work/Primary-Activity
    contract, Capability identity, plan step, execution lane, realization, or
    execution method.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    local_ref: str = Field(min_length=1, max_length=80)
    outcome: str = Field(min_length=1, max_length=500)
    bindings: dict[str, Any] = Field(default_factory=dict)
    completion_requires_work: bool = False
    completion_requires_fresh_evidence: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("local_ref", "outcome", mode="before")
    @classmethod
    def normalize_responsibility_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("bindings")
    @classmethod
    def reject_low_level_bindings(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_forbidden_low_level_fields(value)
        _reject_planner_owned_bindings(value)
        return value

    @model_validator(mode="after")
    def validate_evidence_requirement(self) -> "CognitiveResponsibilityProposal":
        if self.completion_requires_fresh_evidence and not self.completion_requires_work:
            raise ValueError(
                "fresh evidence requirement implies completion_requires_work"
            )
        return self


class CognitiveProgressCandidate(BaseModel):
    """Legacy compatibility shape for GI-authored pre-Goal speech.

    Maintained Goal Interpretation now emits Responsibility evidence only. Fast Planner
    owns the first HOW decision and any immediately-ready conversational Activity. This
    type remains temporarily for older direct compatibility callers and retained traces.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    candidate_id: str = Field(min_length=1, max_length=160)
    kind: Literal["native_response"] = "native_response"
    response_text: str = Field(min_length=1, max_length=600)
    speech_act: str = Field(default="inform", min_length=1, max_length=120)
    intent: str = Field(default="unknown", min_length=1, max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "candidate_id",
        "response_text",
        "speech_act",
        "intent",
        mode="before",
    )
    @classmethod
    def normalize_candidate_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @staticmethod
    def stable_id(
        *,
        turn_id: str,
        response_text: str = "",
        speech_act: str = "inform",
    ) -> str:
        payload = json.dumps(
            {
                "turn_id": normalize_turn_text(turn_id),
                "kind": "native_response",
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
    responsibilities: list[CognitiveResponsibilityProposal] = Field(default_factory=list)
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
        responsibility_proposals: list[dict[str, Any]] | None = None,
        progress_proposals: list[dict[str, Any]] | None = None,
    ) -> "CoreInterpretationResult":
        responsibilities: list[CognitiveResponsibilityProposal] = []
        seen_refs: set[str] = set()
        for raw in responsibility_proposals or []:
            if not isinstance(raw, dict):
                continue
            try:
                proposal = CognitiveResponsibilityProposal.model_validate(raw)
            except (ValueError, TypeError):
                continue
            if proposal.local_ref in seen_refs:
                continue
            seen_refs.add(proposal.local_ref)
            responsibilities.append(proposal)

        progress_candidates: list[CognitiveProgressCandidate] = []
        seen_progress_ids: set[str] = set()
        conversational_scope = decision.route == "chat" or any(
            item.route == "chat" for item in decision.routes
        )
        for raw in progress_proposals or []:
            if not isinstance(raw, dict):
                continue
            kind = normalize_turn_text(str(raw.get("kind") or ""))
            if kind != "native_response":
                continue
            response_text = normalize_turn_text(str(raw.get("response_text") or ""))
            speech_act = normalize_turn_text(raw.get("speech_act") or "inform") or "inform"
            if not conversational_scope or not response_text:
                continue
            intent = normalize_turn_text(raw.get("intent") or decision.intent or "unknown") or "unknown"
            try:
                confidence = float(raw.get("confidence", decision.confidence))
            except (TypeError, ValueError):
                continue
            candidate_id = CognitiveProgressCandidate.stable_id(
                turn_id=envelope.turn_id,
                response_text=response_text,
                speech_act=speech_act,
            )
            candidate = CognitiveProgressCandidate(
                candidate_id=candidate_id,
                response_text=response_text,
                speech_act=speech_act,
                intent=intent,
                confidence=confidence,
            )
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
            responsibilities=responsibilities,
            progress_candidates=progress_candidates,
            compatibility_projection=decision,
            projection_digest=cls.digest_projection(decision),
        )


    def route_decision_projection(self) -> RouteDecision:
        """Return a defensive copy for compatibility-only downstream adapters."""

        return self.compatibility_projection.model_copy(deep=True)
