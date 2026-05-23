from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

RouteName = Literal["chat", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"]
Priority = Literal["low", "normal", "high", "urgent"]


class RouteRequest(BaseModel):
    sid: str | None = None
    text: str
    language: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class RouteDecision(BaseModel):
    route: RouteName = "chat"
    agents: list[str] = Field(default_factory=list)
    intent: str = "general"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    language: str = "auto"
    priority: Priority = "normal"
    interrupt_current: bool = False
    needs_agent: bool = True
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
