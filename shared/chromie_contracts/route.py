from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import OptionalCapabilityIdentityModel

RouteName = Literal[
    "chat",
    "deep_thought",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
]

Priority = Literal["low", "normal", "high", "urgent"]
DecisionSource = Literal["rules", "llm", "catalog", "fallback"]

_FAST_SPEECH_CONTRACT_MARKERS = {
    "checking_only",
    "prelude_only",
    "needs_confirmation",
    "acknowledge",
    "acknowledge_and_check",
    "clarify",
    "thinking",
    "safety_prelude",
}


def _fast_speech_marker(value: str | None) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())


class FastSpeech(BaseModel):
    """Core-authored process acknowledgement preserved across services."""

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
    def reject_contract_marker_as_spoken_text(self) -> "FastSpeech":
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
        if _fast_speech_marker(self.text) in _FAST_SPEECH_CONTRACT_MARKERS:
            self.text = ""
        return self


MemoryKind = Literal[
    "preference",
    "fact",
    "note",
    "instruction",
    "constraint",
    "relationship",
    "other",
]


class MemoryUpdateProposal(BaseModel):
    """Model-authored, Host-validated memory mutation proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["remember", "forget", "clear_profile"] = "remember"
    scope: Literal["session", "profile"] = "session"
    kind: MemoryKind
    text: str = Field(min_length=1, max_length=1000)
    key: str | None = Field(default=None, max_length=160)
    persistence_policy: Literal[
        "ephemeral",
        "durable_with_explicit_consent",
    ] = "ephemeral"
    consent_basis: Literal["explicit_current_turn"] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_memory_authority(self) -> "MemoryUpdateProposal":
        durable = self.persistence_policy == "durable_with_explicit_consent"
        if self.scope == "session":
            if self.operation != "remember" or durable:
                raise ValueError("session memory supports only ephemeral remember")
            if self.consent_basis is not None or self.retention_days is not None:
                raise ValueError("session memory must not carry durable consent fields")
            return self
        if not durable or self.consent_basis != "explicit_current_turn":
            raise ValueError(
                "profile memory requires durable_with_explicit_consent and explicit_current_turn"
            )
        if self.operation == "forget" and not self.key:
            raise ValueError("profile forget requires a stable memory key")
        if self.operation == "remember" and not self.key:
            raise ValueError("durable profile memory requires a stable memory key")
        if self.operation == "remember" and self.retention_days is None:
            raise ValueError("durable profile memory requires bounded retention_days")
        if self.operation != "remember" and self.retention_days is not None:
            raise ValueError("forget and clear_profile must not set retention_days")
        return self

    @field_validator("text", "key", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.strip().split())
        return normalized or None


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


class RouteRequest(BaseModel):
    sid: str | None = None
    text: str
    language: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class RouteDecision(BaseModel):
    route: RouteName
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
        if _fast_speech_marker(self.speak_first) in _FAST_SPEECH_CONTRACT_MARKERS:
            self.speak_first = None
        if not self.speak_first and self.fast_speech and self.fast_speech.text.strip():
            self.speak_first = self.fast_speech.text.strip()
        return self
