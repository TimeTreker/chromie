from __future__ import annotations

from pydantic import BaseModel, Field

from ..capabilities.models import CapabilityRegistry
from ..tool_invocation import AsyncToolInvoker

from .async_executor import ReadOnlyTaskGraphExecutor
from .executor import DagDryRunExecutor
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


class TaskGraphService:
    """Expose safe TaskGraph validation and dry-run execution to the Agent API."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        read_only_invoker: AsyncToolInvoker | None = None,
    ) -> None:
        self.registry = registry
        self.read_only_invoker = read_only_invoker
        self._traces: dict[str, ExecutionTrace] = {}

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

    async def execute_read_only(self, graph: TaskGraph) -> ExecutionTrace:
        if self.read_only_invoker is None:
            raise RuntimeError("read-only TaskGraph execution is disabled")
        trace = await ReadOnlyTaskGraphExecutor(self.registry, self.read_only_invoker).run(graph)
        self._traces[graph.graph_id] = trace.model_copy(deep=True)
        return trace

    def get_trace(self, graph_id: str) -> ExecutionTrace | None:
        trace = self._traces.get(graph_id)
        return trace.model_copy(deep=True) if trace is not None else None
