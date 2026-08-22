from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..capabilities.models import FailurePolicy

WorkNodeRole = Literal["activity", "monitor", "confirmation", "report", "safety"]
WorkDAGAuthor = Literal["planner", "operator", "system", "user"]
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
DAGStatus = Literal["pending", "running", "success", "failed", "aborted", "cancelled"]


def _normalize_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list of identifiers")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return list(dict.fromkeys(normalized))


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1)
    backoff_s: float = Field(default=0.0, ge=0.0)


class WorkNode(BaseModel):
    """One Planner-authored capability node in a WorkDAG.

    The node is representation, not cognition. ``capability_id`` names an
    already-declared Capability and the dependency fields describe committed
    topology. DAGEngine may validate and schedule this node but may not invent
    another capability, rewrite arguments, or choose replacement Work.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    role: WorkNodeRole = "activity"
    args: dict[str, Any] = Field(default_factory=dict)
    source_goal_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    during: list[str] = Field(default_factory=list)
    timeout_s: float | None = Field(default=None, gt=0)
    retry: RetryPolicy | None = None
    on_failure: FailurePolicy | None = None
    on_timeout: FailurePolicy | None = None
    on_event: dict[str, FailurePolicy] = Field(default_factory=dict)
    condition: str | None = None

    @field_validator("id", "capability_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @field_validator("source_goal_ids", "depends_on", "during", mode="before")
    @classmethod
    def normalize_identifier_lists(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @model_validator(mode="after")
    def reject_self_edges(self) -> "WorkNode":
        if self.id in self.depends_on:
            raise ValueError(f"node {self.id!r} may not depend on itself")
        if self.id in self.during:
            raise ValueError(f"node {self.id!r} may not monitor itself")
        return self


class WorkDAGPolicies(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_on_failure: FailurePolicy = Field(default_factory=FailurePolicy)
    default_on_timeout: FailurePolicy = Field(
        default_factory=lambda: FailurePolicy(strategy="stop_and_report")
    )


class WorkDAG(BaseModel):
    """Revisioned Planner-authored directed acyclic topology of planned Work.

    ``dag_id`` is stable while Planner revises one coherent body of Work.
    ``revision`` is monotonic.  DAGEngine may advance execution state for a
    committed revision, but only Planner may author the next semantic revision.
    Direct operator-authored instances are diagnostic/control-plane fixtures and
    never become Chromie's canonical cognitive author.
    """

    model_config = ConfigDict(extra="forbid")

    dag_id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    version: str = "1.0"
    summary: str = ""
    authored_by: WorkDAGAuthor = "operator"
    goal_ids: list[str] = Field(default_factory=list)
    revision_reason: str = ""
    max_duration_s: float | None = Field(default=None, gt=0)
    nodes: list[WorkNode] = Field(default_factory=list, max_length=64)
    policies: WorkDAGPolicies = Field(default_factory=WorkDAGPolicies)

    @field_validator("dag_id")
    @classmethod
    def validate_dag_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", normalized):
            raise ValueError(
                "dag_id must be URL-path-safe: 1-128 letters, digits, periods, "
                "underscores, colons, or hyphens"
            )
        return normalized

    @field_validator("goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        return _normalize_ids(value)

    @field_validator("summary", "revision_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_revision_and_nodes(self) -> "WorkDAG":
        if self.revision == 1:
            if self.parent_revision is not None:
                raise ValueError("WorkDAG revision 1 must not set parent_revision")
        else:
            if self.authored_by != "planner":
                raise ValueError(
                    "Only Planner may author a semantic WorkDAG revision after revision 1"
                )
            if self.parent_revision != self.revision - 1:
                raise ValueError(
                    "WorkDAG revisions after 1 must set parent_revision=revision-1"
                )
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate node id: {node.id}")
            seen.add(node.id)
            if self.authored_by == "planner" and not node.source_goal_ids:
                raise ValueError(
                    f"Planner-authored WorkDAG node {node.id!r} requires source_goal_ids"
                )
            unknown_goals = set(node.source_goal_ids) - set(self.goal_ids)
            if unknown_goals:
                raise ValueError(
                    f"node {node.id!r} references goal ids absent from WorkDAG: "
                    + ", ".join(sorted(unknown_goals))
                )
        if self.authored_by == "planner" and self.nodes and not self.goal_ids:
            raise ValueError("Planner-authored WorkDAG with nodes requires goal_ids")
        return self

    def node_map(self) -> dict[str, WorkNode]:
        return {node.id: node for node in self.nodes}


class NodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    capability_id: str | None = None
    status: NodeStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 1
    started_at: float | None = None
    finished_at: float | None = None
    blocked_by: list[str] = Field(default_factory=list)
    inherited_from_revision: int | None = Field(default=None, ge=1)


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    node_id: str | None = None
    capability_id: str | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    """Mechanical DAGEngine trace; never a user-facing result composer."""

    model_config = ConfigDict(extra="forbid")

    dag_id: str
    dag_revision: int = Field(default=1, ge=1)
    status: DAGStatus = "pending"
    summary: str = ""
    node_results: list[NodeResult] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)

    def result_map(self) -> dict[str, NodeResult]:
        return {result.node_id: result for result in self.node_results}
