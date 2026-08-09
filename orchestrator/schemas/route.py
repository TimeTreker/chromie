from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

try:
    from chromie_contracts.interaction import OptionalCapabilityIdentityModel
    from chromie_contracts.route import MemoryUpdateProposal
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import OptionalCapabilityIdentityModel
    from shared.chromie_contracts.route import MemoryUpdateProposal

RouteName = Literal["chat", "deep_thought", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"]
Priority = Literal["low", "normal", "high", "urgent"]
DecisionSource = Literal["rules", "llm", "catalog", "fallback"]


class RouteRequest(BaseModel):
    sid: str | None = None
    text: str
    language: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class FastSpeech(BaseModel):
    """A short Core-generated user-facing prelude for fast-first TTS.

    This is a process acknowledgement, not an answer, tool result, memory commit,
    or physical execution claim.
    """

    text: str = ""
    purpose: str | None = None
    language: str | None = None
    commitment: str | None = None
    claim_state: Literal["none", "planned", "started", "completed"] = "none"
    claimed_capability_ids: list[str] = Field(default_factory=list)
    claimed_goal_ids: list[str] = Field(default_factory=list)
    must_not_claim_completion: bool = True

    @model_validator(mode="before")
    @classmethod
    def accept_bare_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        return value

    @model_validator(mode="after")
    def enforce_completion_claim_boundary(self) -> "FastSpeech":
        if self.must_not_claim_completion is not True:
            raise ValueError("fast_speech must forbid completion claims")
        if self.claim_state == "completed":
            raise ValueError("fast_speech cannot claim completed work")
        self.claimed_capability_ids = list(dict.fromkeys(
            str(item or "").strip() for item in self.claimed_capability_ids
            if str(item or "").strip()
        ))
        self.claimed_goal_ids = list(dict.fromkeys(
            str(item or "").strip() for item in self.claimed_goal_ids
            if str(item or "").strip()
        ))
        return self


class RouteItem(OptionalCapabilityIdentityModel):
    route: RouteName
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: Priority = "normal"
    lane: str = "agent"
    context_profile: str = "session_compact"
    requires_mind: bool = False
    direct_to_tts: bool = False
    text: str | None = None
    fast_speech: FastSpeech | None = None
    memory_update: MemoryUpdateProposal | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteDecision(BaseModel):
    route: RouteName = "chat"
    routes: list[RouteItem] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "auto"
    priority: Priority = "normal"
    interrupt_current: bool = False
    needs_agent: bool = True
    should_speak: bool = True
    speak_first: str | None = None
    fast_speech: FastSpeech | None = None
    memory_update: MemoryUpdateProposal | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    candidate_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    source: DecisionSource = "fallback"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_speak_first_from_fast_speech(self) -> "RouteDecision":
        if not self.speak_first and self.fast_speech and self.fast_speech.text.strip():
            self.speak_first = self.fast_speech.text.strip()
        return self
