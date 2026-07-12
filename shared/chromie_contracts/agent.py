from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .action import ActionCommand
from .route import RouteDecision

AgentStatus = Literal["ok", "clarify", "blocked", "ignored", "error"]
SpeechStyle = Literal["brief", "normal", "empathetic", "confirm", "warning"]


class SpeechItem(BaseModel):
    text: str
    style: SpeechStyle = "brief"
    priority: str = "normal"
    interruptible: bool = True
    after_action_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    type: str
    key: str | None = None
    value: Any = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
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
    memory_updates: list[MemoryUpdate] = Field(default_factory=list)
    task_graphs: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    handled_by: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
