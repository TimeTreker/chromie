from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

RouteName = Literal["chat", "deep_thought", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"]
Priority = Literal["low", "normal", "high", "urgent"]
DecisionSource = Literal["rules", "llm", "catalog", "fallback"]


class RouteRequest(BaseModel):
    sid: str | None = None
    text: str
    language: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class FastSpeech(BaseModel):
    """A short Router-generated user-facing prelude for fast-first TTS.

    This is a process acknowledgement, not an answer, tool result, memory commit,
    or physical execution claim.
    """

    text: str = ""
    purpose: str | None = None
    language: str | None = None
    commitment: str | None = None
    must_not_claim_completion: bool = True


class RouteItem(BaseModel):
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
    skill_id: str | None = None
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
    actions: list[dict[str, Any]] = Field(default_factory=list)
    candidate_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    source: DecisionSource = "fallback"
    metadata: dict[str, Any] = Field(default_factory=dict)
