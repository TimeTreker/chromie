from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .action import ActionCommand
from .route import RouteDecision

SpeechTiming = Literal["immediate", "after_actions"]
SpeechStyle = Literal["brief", "normal", "warm", "confirm", "error"]


class SpeechItem(BaseModel):
    text: str
    style: SpeechStyle = "brief"
    timing: SpeechTiming = "immediate"
    priority: str = "normal"
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    type: str
    key: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AgentRequest(BaseModel):
    sid: str | None = None
    text: str
    route_decision: RouteDecision
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    speak_immediate: list[SpeechItem] = Field(default_factory=list)
    actions: list[ActionCommand] = Field(default_factory=list)
    speak_after: list[SpeechItem] = Field(default_factory=list)
    memory_updates: list[MemoryUpdate] = Field(default_factory=list)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
