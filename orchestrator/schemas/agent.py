from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from .action import ActionCommand, ActionResult
from .route import RouteDecision

SpeechPriority = Literal["low", "normal", "high", "urgent"]
AgentStatus = Literal["ok", "clarify", "blocked", "ignored", "error"]


class SpeechItem(BaseModel):
    text: str
    style: str = "brief"
    priority: SpeechPriority = "normal"
    interruptible: bool = True
    after_action_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    sid: str | None = None
    text: str
    route_decision: RouteDecision
    language: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class AgentResult(BaseModel):
    status: AgentStatus = "ok"
    speak_immediate: list[SpeechItem] = Field(default_factory=list)
    actions: list[ActionCommand] = Field(default_factory=list)
    speak_after: list[SpeechItem] = Field(default_factory=list)
    memory_updates: list[dict[str, Any]] = Field(default_factory=list)
    task_graphs: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    handled_by: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    action_results: list[ActionResult] = Field(default_factory=list)
