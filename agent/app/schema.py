from __future__ import annotations

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


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
AgentStatus = Literal["ok", "clarify", "blocked", "ignored", "error"]
SpeakStyle = Literal["brief", "normal", "empathetic", "confirm", "warning"]
ActionTarget = Literal[
    "robot_pose_controller",
    "motion_controller",
    "tool_executor",
    "memory_store",
    "vision_system",
    "system",
]

_INTERNAL_SPEECH_ID_RE = re.compile(
    r"\b(?:soridormi|chromie)\.[A-Za-z0-9_][A-Za-z0-9_.-]*\b",
    re.IGNORECASE,
)
_INTERNAL_PLAN_LABEL_RE = re.compile(
    r"\b(?:task split|key risk|next step)\s*:",
    re.IGNORECASE,
)
_INTERNAL_EXECUTION_RE = re.compile(
    r"(?:\b(?:execute|call|run)\s+(?:soridormi|chromie)\.)"
    r"|(?:执行(?:指令|命令)[:：]?\s*(?:soridormi|chromie)\.)",
    re.IGNORECASE,
)
_LEADING_PUNCT_RE = re.compile(r"^[\s,;:.!?，。！？、]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;:.!?，。！？、])")
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)|\[\s*\]|\{\s*\}")


class FastSpeech(BaseModel):
    """Router-authored process acknowledgement preserved across services."""

    text: str = ""
    purpose: str | None = None
    language: str | None = None
    commitment: str | None = None
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
        marker = "_".join(self.text.strip().casefold().replace("-", "_").split())
        if marker in {
            "checking_only",
            "prelude_only",
            "needs_confirmation",
            "acknowledge",
            "acknowledge_and_check",
            "clarify",
            "thinking",
            "safety_prelude",
        }:
            self.text = ""
        return self


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


def sanitize_spoken_text(value: str | None) -> str:
    text = " ".join((value or "").strip().split())
    if not text:
        return ""
    execution = _INTERNAL_EXECUTION_RE.search(text)
    if execution:
        text = text[: execution.start()].strip()
        if not text:
            return ""
    label = _INTERNAL_PLAN_LABEL_RE.search(text)
    if label:
        text = text[: label.start()].strip()
        if not text:
            return ""
    text = _INTERNAL_SPEECH_ID_RE.sub("", text)
    text = _EMPTY_BRACKETS_RE.sub("", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = re.sub(r"([,;:，、])\s*([.?!。！？])", r"\2", text)
    text = _LEADING_PUNCT_RE.sub("", text)
    text = " ".join(text.strip().split())
    if text and all(ch in ",;:.!?，。！？、" for ch in text):
        return ""
    return text


def _normalize_speech_items(items: list["SpeakItem"], max_chars: int) -> list["SpeakItem"]:
    seen: set[str] = set()
    out: list[SpeakItem] = []
    max_chars = max(1, int(max_chars or 1))
    for item in items:
        text = sanitize_spoken_text(item.text)
        if not text or text in seen:
            continue
        if len(text) > max_chars:
            text = text[:max_chars].rstrip("，,。.!！?？ ")
            text += "。" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "."
        seen.add(text)
        out.append(item.model_copy(update={"text": text}))
    return out


class RouteDecision(BaseModel):
    """Router output consumed by the agent service.

    This mirrors router/app/schema.py so the agent module can run independently.
    Later this can move into shared/chromie_contracts.
    """

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
    actions: list[dict[str, Any]] = Field(default_factory=list)
    candidate_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    source: DecisionSource = "fallback"
    metadata: dict[str, Any] = Field(default_factory=dict)

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

    @model_validator(mode="after")
    def populate_speak_first_from_fast_speech(self) -> "RouteDecision":
        contract_markers = {
            "checking_only",
            "prelude_only",
            "needs_confirmation",
            "acknowledge",
            "acknowledge_and_check",
            "clarify",
            "thinking",
            "safety_prelude",
        }
        marker = "_".join(
            str(self.speak_first or "").strip().casefold().replace("-", "_").split()
        )
        if marker in contract_markers:
            self.speak_first = None
        if not self.speak_first and self.fast_speech and self.fast_speech.text.strip():
            self.speak_first = self.fast_speech.text.strip()
        return self


class AgentRunRequest(BaseModel):
    """Request from host orchestrator after routing."""

    sid: str | None = None
    text: str = Field(default="", description="ASR final text")
    route_decision: RouteDecision
    language: str | None = Field(default=None, description="Optional BCP-47 language hint")
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return (value or "").strip()

    @model_validator(mode="after")
    def fill_language(self) -> "AgentRunRequest":
        if not self.language:
            if self.route_decision.language and self.route_decision.language != "auto":
                self.language = self.route_decision.language
            else:
                self.language = detect_language(self.text)
        return self


class SpeakItem(BaseModel):
    text: str = Field(min_length=1)
    style: SpeakStyle = "brief"
    priority: Priority = "normal"
    interruptible: bool = True
    after_action_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join((value or "").strip().split())


class ActionCommand(BaseModel):
    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:8]}")
    target: ActionTarget
    type: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
    timeout_ms: int | None = Field(default=None, ge=1)
    requires_confirmation: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    type: str = Field(min_length=1)
    key: str | None = None
    value: Any = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    status: AgentStatus = "ok"
    speak_immediate: list[SpeakItem] = Field(default_factory=list)
    actions: list[ActionCommand] = Field(default_factory=list)
    speak_after: list[SpeakItem] = Field(default_factory=list)
    memory_updates: list[MemoryUpdate] = Field(default_factory=list)
    task_graphs: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    handled_by: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_speak_immediate(
        self,
        text: str | None,
        *,
        style: SpeakStyle = "brief",
        priority: Priority = "normal",
    ) -> None:
        text = (text or "").strip()
        if text:
            self.speak_immediate.append(SpeakItem(text=text, style=style, priority=priority))

    def add_speak_after(
        self,
        text: str | None,
        *,
        style: SpeakStyle = "brief",
        priority: Priority = "normal",
        after_action_id: str | None = None,
    ) -> None:
        text = (text or "").strip()
        if text:
            self.speak_after.append(
                SpeakItem(text=text, style=style, priority=priority, after_action_id=after_action_id)
            )

    def add_action(
        self,
        target: ActionTarget,
        action_type: str,
        *,
        params: dict[str, Any] | None = None,
        blocking: bool = False,
        timeout_ms: int | None = None,
        requires_confirmation: bool = False,
        reason: str | None = None,
    ) -> ActionCommand:
        action = ActionCommand(
            target=target,
            type=action_type,
            params=params or {},
            blocking=blocking,
            timeout_ms=timeout_ms,
            requires_confirmation=requires_confirmation,
            reason=reason,
        )
        self.actions.append(action)
        if requires_confirmation:
            self.requires_confirmation = True
        return action

    def add_task_graph(self, graph: dict[str, Any]) -> None:
        self.task_graphs.append(graph)

    def normalize_speech(self, max_chars: int) -> None:
        self.speak_immediate = _normalize_speech_items(self.speak_immediate, max_chars)
        self.speak_after = _normalize_speech_items(self.speak_after, max_chars)


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "chromie-agent"
    model: str | None = None
    ollama_url: str | None = None
    use_llm: bool = True
    available_agents: list[str] = Field(default_factory=list)
    capability_sources: list[str] = Field(default_factory=list)
    capability_manifest_files: list[str] = Field(default_factory=list)
    task_graph_planning_enabled: bool = False
    read_only_task_graph_execution_enabled: bool = False
    planning_task_graph_execution_enabled: bool = False
    parallel_task_graph_execution_enabled: bool = False
    task_graph_max_concurrency: int = 1
    task_graph_active_count: int = 0
    task_graph_waiting_count: int = 0
    active_task_graph_ids: list[str] = Field(default_factory=list)
    guarded_task_graph_execution_enabled: bool = False
    physical_task_graph_execution_enabled: bool = False
    interaction_output_mode: str = "native"
    native_interaction_fallback_enabled: bool = False
    legacy_capability_fallback_enabled: bool = False
    capability_catalog_enabled: bool = False
    capability_catalog_version: int = 0
    task_continuity_enabled: bool = False
    goal_association_enabled: bool = False
    goal_association_model: str | None = None
    fast_planner_enabled: bool = False
    fast_planner_model: str | None = None
    deep_planner_enabled: bool = False
    deep_planner_model: str | None = None
    response_composer_enabled: bool = False
    response_composer_model: str | None = None
    tool_result_interpreter_enabled: bool = False
    tool_result_interpreter_model: str | None = None
    task_continuity_model: str | None = None
    social_attention_mode: str = "off"
    social_attention_model: str | None = None


def detect_language(text: str) -> str:
    text = text or ""
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return "zh-CN"
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return "ru-RU"
    return "en-US"
