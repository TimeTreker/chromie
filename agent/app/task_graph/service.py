from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..capabilities.models import CapabilityRegistry
from ..tool_invocation import AsyncToolInvoker

from .async_executor import (
    GuardedTaskGraphExecutor,
    ReadOnlyTaskGraphExecutor,
    TaskGraphExecutionProofs,
)
from .executor import DagDryRunExecutor
from .grants import ConfirmationGrantStore
from .models import ExecutionTrace, TaskGraph
from .validator import GraphValidator


class TaskGraphValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TaskGraphDryRunRequest(BaseModel):
    graph: TaskGraph
    auto_confirm: bool = True


class TaskGraphExecuteRequest(BaseModel):
    graph: TaskGraph


class TaskGraphGuardedExecuteRequest(BaseModel):
    graph: TaskGraph
    confirmation_grant: str


class TaskGraphConfirmationGrantRequest(BaseModel):
    graph: TaskGraph
    confirmed_node_ids: set[str] = Field(default_factory=set)
    ttl_s: int = Field(default=60, ge=1, le=300)


class TaskGraphConfirmationGrantResponse(BaseModel):
    confirmation_grant: str
    graph_id: str
    confirmed_node_ids: set[str]
    expires_at: float


class TaskGraphCancelResponse(BaseModel):
    graph_id: str
    cancellation_requested: bool


class TaskGraphService:
    """Expose safe TaskGraph validation and dry-run execution to the Agent API."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        read_only_invoker: AsyncToolInvoker | None = None,
        guarded_invoker: AsyncToolInvoker | None = None,
        allow_physical_motion: bool = False,
    ) -> None:
        self.registry = registry
        self.read_only_invoker = read_only_invoker
        self.guarded_invoker = guarded_invoker
        self.allow_physical_motion = allow_physical_motion
        self._traces: dict[str, ExecutionTrace] = {}
        self._grants = ConfirmationGrantStore()
        self._active_executions: dict[str, asyncio.Task[ExecutionTrace]] = {}

    def validate(self, graph: TaskGraph) -> TaskGraphValidationResponse:
        report = GraphValidator(self.registry).validate(graph)
        return TaskGraphValidationResponse(
            valid=report.valid,
            errors=list(report.errors),
            warnings=list(report.warnings),
        )

    def dry_run(self, graph: TaskGraph, *, auto_confirm: bool = True) -> ExecutionTrace:
        validation = self.validate(graph)
        if not validation.valid:
            raise ValueError("TaskGraph validation failed: " + "; ".join(validation.errors))

        trace = DagDryRunExecutor(self.registry, auto_confirm=auto_confirm).run(graph, validate=False)
        self._traces[graph.graph_id] = trace.model_copy(deep=True)
        return trace

    async def execute_guarded(
        self,
        graph: TaskGraph,
        confirmation_grant: str,
    ) -> ExecutionTrace:
        if self.guarded_invoker is None:
            raise RuntimeError("guarded TaskGraph execution is disabled")
        if graph.graph_id in self._active_executions:
            raise RuntimeError(f"TaskGraph {graph.graph_id!r} is already running")

        grant = self._grants.consume(confirmation_grant, graph)
        proofs = TaskGraphExecutionProofs(
            confirmed_node_ids=set(grant.confirmed_node_ids)
        )
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("guarded TaskGraph execution requires an asyncio task")
        self._active_executions[graph.graph_id] = task
        try:
            trace = await GuardedTaskGraphExecutor(
                self.registry,
                self.guarded_invoker,
                allow_physical_motion=self.allow_physical_motion,
            ).run(graph, proofs)
            self._traces[graph.graph_id] = trace.model_copy(deep=True)
            return trace
        finally:
            self._active_executions.pop(graph.graph_id, None)

    def issue_confirmation_grant(
        self,
        request: TaskGraphConfirmationGrantRequest,
    ) -> TaskGraphConfirmationGrantResponse:
        report = GraphValidator(self.registry).validate(request.graph)
        report.raise_for_errors()
        confirmation_nodes = {
            node.id
            for node in request.graph.nodes
            if node.type == "confirmation" or node.tool == "chromie.ask_confirmation"
        }
        invalid = sorted(request.confirmed_node_ids - confirmation_nodes)
        if invalid:
            raise ValueError(
                f"confirmation grants must reference confirmation nodes: {invalid}"
            )
        token, grant = self._grants.issue(
            request.graph,
            request.confirmed_node_ids,
            ttl_s=request.ttl_s,
        )
        return TaskGraphConfirmationGrantResponse(
            confirmation_grant=token,
            graph_id=request.graph.graph_id,
            confirmed_node_ids=set(grant.confirmed_node_ids),
            expires_at=grant.expires_at,
        )

    def cancel_execution(self, graph_id: str) -> TaskGraphCancelResponse:
        task = self._active_executions.get(graph_id)
        if task is None or task.done():
            return TaskGraphCancelResponse(
                graph_id=graph_id,
                cancellation_requested=False,
            )
        task.cancel()
        return TaskGraphCancelResponse(
            graph_id=graph_id,
            cancellation_requested=True,
        )

    async def execute_read_only(self, graph: TaskGraph) -> ExecutionTrace:
        if self.read_only_invoker is None:
            raise RuntimeError("read-only TaskGraph execution is disabled")
        trace = await ReadOnlyTaskGraphExecutor(self.registry, self.read_only_invoker).run(graph)
        self._traces[graph.graph_id] = trace.model_copy(deep=True)
        return trace

    def get_trace(self, graph_id: str) -> ExecutionTrace | None:
        trace = self._traces.get(graph_id)
        return trace.model_copy(deep=True) if trace is not None else None
