from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RouteName = Literal[
    "chat",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
]

Priority = Literal["low", "normal", "high", "urgent"]
DecisionSource = Literal["rules", "llm", "fallback"]


DEFAULT_AGENTS: dict[str, list[str]] = {
    "chat": ["conversation_agent", "speaker_agent"],
    "robot_action": ["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
    "tool": ["tool_agent", "speaker_agent"],
    "memory": ["memory_agent", "speaker_agent"],
    "clarify": ["speaker_agent"],
    "interrupt": [],
    "ignore": [],
}


class RouteRequest(BaseModel):
    """Request from host orchestrator after ASR final text."""

    sid: str | None = None
    text: str = Field(min_length=0, description="ASR final text")
    language: str | None = Field(default=None, description="Optional BCP-47 language hint")
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return (value or "").strip()


class RouteDecision(BaseModel):
    """Structured decision consumed by host orchestrator."""

    route: RouteName
    agents: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "auto"
    priority: Priority = "normal"
    interrupt_current: bool = False
    needs_agent: bool = True
    should_speak: bool = True
    speak_first: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    source: DecisionSource = "fallback"

    @field_validator("agents")
    @classmethod
    def normalize_agents(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for agent in value or []:
            agent = str(agent).strip()
            if not agent or agent in seen:
                continue
            seen.add(agent)
            normalized.append(agent)
        return normalized


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "chromie-router"
    mode: str
    model: str | None = None
    ollama_url: str | None = None
    rules_first: bool = True


def default_agents_for_route(route: str) -> list[str]:
    return list(DEFAULT_AGENTS.get(route, ["conversation_agent", "speaker_agent"]))


def finalize_decision(
    decision: RouteDecision,
    request: RouteRequest | None = None,
    *,
    source: DecisionSource | None = None,
) -> RouteDecision:
    """Fill safe defaults and normalize route flags."""

    if source is not None:
        decision.source = source

    if request is not None and decision.language in ("", "auto", "unknown"):
        decision.language = request.language or detect_language(request.text)

    if not decision.agents:
        decision.agents = default_agents_for_route(decision.route)

    if decision.route == "interrupt":
        decision.priority = "urgent"
        decision.interrupt_current = True
        decision.needs_agent = False
        decision.should_speak = False
        decision.agents = []

    elif decision.route == "ignore":
        decision.needs_agent = False
        decision.should_speak = False
        decision.agents = []

    elif decision.route == "clarify":
        decision.needs_agent = True
        decision.should_speak = True
        if not decision.speak_first:
            decision.speak_first = "你是指什么？" if decision.language.startswith("zh") else "What do you mean?"

    else:
        decision.needs_agent = True

    return decision


def detect_language(text: str) -> str:
    text = text or ""
    if any("一" <= ch <= "鿿" for ch in text):
        return "zh-CN"
    if any("Ѐ" <= ch <= "ӿ" for ch in text):
        return "ru-RU"
    return "en-US"
