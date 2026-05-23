from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from .action import ActionCommand, ActionResult
from .route import RouteDecision

SpeechPriority = Literal["low", "normal", "high", "urgent"]
SpeechTiming = Literal["immediate", "after_actions"]


class SpeechItem(BaseModel):
    text: str
    style: str = "brief"
    priority: SpeechPriority = "normal"
    timing: SpeechTiming = "immediate"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    sid: str | None = None
    text: str
    route_decision: RouteDecision
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    speak_immediate: list[SpeechItem] = Field(default_factory=list)
    actions: list[ActionCommand] = Field(default_factory=list)
    speak_after: list[SpeechItem] = Field(default_factory=list)
    memory_updates: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    action_results: list[ActionResult] = Field(default_factory=list)
