from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.capabilities.models import FailurePolicy

NodeType = Literal["query", "plan", "action", "monitor", "confirmation", "report", "safety"]
CreatedBy = Literal["llm", "system", "user"]
NodeStatus = Literal[
    "pending",
    "running",
    "success",
    "failed_retryable",
    "failed_fatal",
    "timeout",
    "skipped",
    "blocked",
    "cancelled",
    "safety_interrupted",
]
GraphStatus = Literal["pending", "running", "success", "failed", "aborted", "cancelled"]


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_s: float = Field(default=0.0, ge=0.0)


class TaskNode(BaseModel):
    """A single node in a tool-call DAG proposed by the LLM.

    Nodes reference MCP tools through the global CapabilityRegistry. The node
    only describes what to call and how it depends on other nodes; execution
    remains governed by the registry, validator, and safety policies.
    """

    id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    type: NodeType = "action"
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    during: list[str] = Field(default_factory=list)
    timeout_s: float | None = Field(default=None, gt=0)
    retry: RetryPolicy | None = None
    on_failure: FailurePolicy | None = None
    on_timeout: FailurePolicy | None = None
    on_event: dict[str, FailurePolicy] = Field(default_factory=dict)
    condition: str | None = None

    @field_validator("id", "tool")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value


class TaskGraphPolicies(BaseModel):
    default_on_failure: FailurePolicy = Field(default_factory=FailurePolicy)
    default_on_timeout: FailurePolicy = Field(default_factory=lambda: FailurePolicy(strategy="stop_and_report"))


class TaskGraph(BaseModel):
    graph_id: str = Field(min_length=1)
    version: str = "0.1"
    user_request: str = ""
    summary_zh: str | None = None
    summary: str | None = None
    created_by: CreatedBy = "llm"
    requires_confirmation: bool = False
    max_duration_s: float | None = Field(default=None, gt=0)
    nodes: list[TaskNode] = Field(default_factory=list)
    policies: TaskGraphPolicies = Field(default_factory=TaskGraphPolicies)

    @model_validator(mode="after")
    def validate_unique_node_ids(self) -> "TaskGraph":
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate node id: {node.id}")
            seen.add(node.id)
        return self

    def node_map(self) -> dict[str, TaskNode]:
        return {node.id: node for node in self.nodes}


class NodeResult(BaseModel):
    node_id: str
    tool: str | None = None
    status: NodeStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 1
    started_at: float | None = None
    finished_at: float | None = None
    blocked_by: list[str] = Field(default_factory=list)


class ExecutionEvent(BaseModel):
    type: str
    node_id: str | None = None
    tool: str | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    graph_id: str
    status: GraphStatus = "pending"
    summary: str = ""
    node_results: list[NodeResult] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)

    def result_map(self) -> dict[str, NodeResult]:
        return {result.node_id: result for result in self.node_results}
