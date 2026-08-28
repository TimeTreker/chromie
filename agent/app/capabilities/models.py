from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from chromie_contracts.interaction import find_raw_controller_array_schema
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import find_raw_controller_array_schema

SafetyClass = Literal[
    "safe_read",
    "planning_only",
    "low_risk_action",
    "physical_motion",
    "safety_critical",
    "restricted",
]
FailureStrategy = Literal[
    "retry",
    "ask_user",
    "skip",
    "continue_with_default",
    "goto",
    "abort_task",
    "stop_and_report",
    "emergency_stop",
]


class TransportSpec(BaseModel):
    """How an agent can be reached.

    Chromie owns the global registry, but agents may live in the Chromie
    container, in the Soridormi container, or behind a future remote MCP server.
    """

    kind: str = "local_python"
    module: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class AgentStatus(BaseModel):
    available: bool = True
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ToolAvailability(BaseModel):
    available: bool = True
    modes: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    reason: str | None = None


class ExecutionPolicy(BaseModel):
    can_run_parallel: bool = True
    exclusive_group: str | None = None
    timeout_s: float | None = Field(default=None, gt=0)
    idempotent: bool = True
    side_effect_free: bool = True


class ConfirmationPolicy(BaseModel):
    required: bool = False
    reason: str | None = None
    required_in_modes: list[str] = Field(default_factory=list)
    skippable_in_modes: list[str] = Field(default_factory=list)


class MonitoringPolicy(BaseModel):
    requires_safety_monitor: bool = False
    recommended_monitor_tools: list[str] = Field(default_factory=list)
    hard_interrupt_events: list[str] = Field(default_factory=list)


class FailurePolicy(BaseModel):
    strategy: FailureStrategy = "abort_task"
    target: str | None = None
    message: str | None = None
    default_output: dict[str, Any] | None = None
    max_attempts: int | None = Field(default=None, ge=1)
    backoff_s: float | None = Field(default=None, ge=0)
    then: "FailurePolicy | None" = None


class ToolCapability(BaseModel):
    name: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    display_name: str | None = None
    description: str = ""
    version: str = "0.1.0"
    llm_visible: bool = True

    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    effects: list[str] = Field(default_factory=list)
    safety_class: SafetyClass = "safe_read"
    availability: ToolAvailability = Field(default_factory=ToolAvailability)
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    confirmation: ConfirmationPolicy = Field(default_factory=ConfirmationPolicy)
    monitoring: MonitoringPolicy = Field(default_factory=MonitoringPolicy)
    failure_modes: list[str] = Field(default_factory=list)
    default_failure_policy: FailurePolicy = Field(default_factory=FailurePolicy)
    llm_hints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "agent_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @model_validator(mode="after")
    def enforce_model_visibility_policy(self) -> "ToolCapability":
        if self.safety_class == "restricted":
            self.llm_visible = False
        raw_controller_path = find_raw_controller_array_schema(self.input_schema)
        if raw_controller_path is not None:
            self.llm_visible = False
            self.llm_hints = {
                **self.llm_hints,
                "chromie_visibility_policy": "hidden_raw_controller_array",
                "chromie_visibility_policy_path": raw_controller_path,
            }
        return self


class AgentManifest(BaseModel):
    agent_id: str = Field(min_length=1)
    display_name: str | None = None
    description: str = ""
    version: str = "0.1.0"
    llm_visible: bool = True
    transport: TransportSpec = Field(default_factory=TransportSpec)
    status: AgentStatus = Field(default_factory=AgentStatus)
    tags: list[str] = Field(default_factory=list)
    tools: list[ToolCapability] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tool_ownership(self) -> "AgentManifest":
        seen: set[str] = set()
        for tool in self.tools:
            if tool.agent_id != self.agent_id:
                raise ValueError(f"tool {tool.name!r} has mismatched agent_id {tool.agent_id!r}")
            if tool.name in seen:
                raise ValueError(f"duplicate tool in manifest: {tool.name}")
            seen.add(tool.name)
        return self


class CapabilityBundle(BaseModel):
    schema_version: str = "0.1"
    source: str = "chromie"
    agents: list[AgentManifest] = Field(default_factory=list)
    dag_contract: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load_file(cls, path: str | Path) -> "CapabilityBundle":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "agents" in data:
            return cls.model_validate(data)
        # Also accept a single AgentManifest for simple MCP servers.
        return cls(source=str(Path(path).stem), agents=[AgentManifest.model_validate(data)])


class CapabilityRegistry:
    """Global registry owned by Chromie.

    It may aggregate local Chromie tools and remote MCP manifests such as the
    Soridormi robot-body capability export.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentManifest] = {}
        self._tools: dict[str, ToolCapability] = {}

    @classmethod
    def from_bundles(cls, bundles: list[CapabilityBundle]) -> "CapabilityRegistry":
        registry = cls()
        for bundle in bundles:
            registry.register_bundle(bundle)
        return registry

    def register_bundle(self, bundle: CapabilityBundle) -> None:
        for manifest in bundle.agents:
            self.register_agent(manifest)

    def register_agent(self, manifest: AgentManifest) -> None:
        if manifest.agent_id in self._agents:
            raise ValueError(f"duplicate agent_id: {manifest.agent_id}")
        for tool in manifest.tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool capability: {tool.name}")
        self._agents[manifest.agent_id] = manifest
        for tool in manifest.tools:
            self._tools[tool.name] = tool

    def list_agents(self) -> list[AgentManifest]:
        return [self._agents[key] for key in sorted(self._agents)]

    def get_agent(self, agent_id: str) -> AgentManifest:
        return self._agents[agent_id]

    def list_tools(self) -> list[ToolCapability]:
        return [self._tools[key] for key in sorted(self._tools)]

    def get_tool(self, name: str) -> ToolCapability:
        return self._tools[name]

    def available_tools(self, *, llm_visible: bool | None = None) -> list[ToolCapability]:
        tools = [tool for tool in self.list_tools() if tool.availability.available]
        if llm_visible is not None:
            tools = [tool for tool in tools if tool.llm_visible is llm_visible]
        return tools

    def tools_with_effect(self, effect: str) -> list[ToolCapability]:
        return [tool for tool in self.list_tools() if effect in tool.effects]

    def tools_requiring_confirmation(self) -> list[ToolCapability]:
        return [tool for tool in self.list_tools() if tool.confirmation.required]

    def tools_for_llm(self) -> list[ToolCapability]:
        visible_agents = {agent.agent_id for agent in self.list_agents() if agent.llm_visible and agent.status.available}
        return [
            tool
            for tool in self.available_tools(llm_visible=True)
            if tool.agent_id in visible_agents and tool.safety_class != "restricted"
        ]

    def model_dump(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "agents": [agent.model_dump(mode="json") for agent in self.list_agents()],
            "tools": [tool.model_dump(mode="json") for tool in self.list_tools()],
        }

    def llm_context(self, *, language: str = "en") -> str:
        zh = language.lower().startswith("zh")
        visible = self.tools_for_llm()
        unavailable_agents = [agent for agent in self.list_agents() if not agent.status.available]
        unavailable_tools = [tool for tool in self.list_tools() if tool.llm_visible and not tool.availability.available]

        if zh:
            lines = ["你正在通过安全的 MCP 能力调用 Chromie 平台和机器人子系统。", "", "当前可用能力："]
            if not visible:
                lines.append("- 暂无可供 LLM 调用的工具。")
            for tool in visible:
                effects = ", ".join(tool.effects) if tool.effects else "无副作用声明"
                confirm = "需要确认" if tool.confirmation.required else "不需要确认"
                lines.append(f"- {tool.name}: {tool.description}（effects: {effects}; {confirm}）")
            if unavailable_agents or unavailable_tools:
                lines.extend(["", "当前不可用能力："])
                for agent in unavailable_agents:
                    reason = agent.status.reason or "原因未说明"
                    lines.append(f"- {agent.agent_id}: {reason}")
                for tool in unavailable_tools:
                    reason = tool.availability.reason or "原因未说明"
                    lines.append(f"- {tool.name}: {reason}")
            lines.extend(
                [
                    "",
                    "规则：",
                    "- 不要生成或调用原始电机/关节/力矩控制。",
                    "- 会移动机器人的工具必须先规划、再确认、再执行。",
                    "- stop / emergency_stop 类安全工具可以打断其他任务。",
                ]
            )
            return "\n".join(lines)

        lines = ["You are using safe MCP capabilities exposed to Chromie.", "", "Available capabilities:"]
        if not visible:
            lines.append("- No LLM-visible tools are currently available.")
        for tool in visible:
            effects = ", ".join(tool.effects) if tool.effects else "unspecified"
            confirm = "requires confirmation" if tool.confirmation.required else "no confirmation required"
            lines.append(f"- {tool.name}: {tool.description} (effects: {effects}; {confirm})")
        if unavailable_agents or unavailable_tools:
            lines.extend(["", "Unavailable capabilities:"])
            for agent in unavailable_agents:
                reason = agent.status.reason or "unspecified reason"
                lines.append(f"- {agent.agent_id}: {reason}")
            for tool in unavailable_tools:
                reason = tool.availability.reason or "unspecified reason"
                lines.append(f"- {tool.name}: {reason}")
        lines.extend(
            [
                "",
                "Rules:",
                "- Never call raw motor, joint, or torque controls.",
                "- Physical motion must be planned, confirmed, and monitored before execution.",
                "- stop and emergency_stop safety tools may preempt other tasks.",
            ]
        )
        return "\n".join(lines)
