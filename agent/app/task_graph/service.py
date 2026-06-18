from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

try:
    from chromie_runtime import ResourceArbiter
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime import ResourceArbiter

from ..capabilities.models import CapabilityRegistry
from ..soridormi_task_client import SoridormiTaskMonitoringInvoker
from ..tool_invocation import AsyncToolInvoker

from .async_executor import (
    GuardedTaskGraphExecutor,
    PlanningTaskGraphExecutor,
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


class TaskGraphSchedulerStatus(BaseModel):
    parallel_enabled: bool
    max_concurrency: int
    active_count: int
    waiting_count: int
    serial_active: bool
    serial_waiters: int
    active_graph_ids: list[str] = Field(default_factory=list)


class TaskGraphService:
    """Expose safe TaskGraph validation and dry-run execution to the Agent API."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        read_only_invoker: AsyncToolInvoker | None = None,
        planning_invoker: AsyncToolInvoker | None = None,
        guarded_invoker: AsyncToolInvoker | None = None,
        allow_physical_motion: bool = False,
        enable_parallel_execution: bool = False,
        max_concurrency: int = 4,
        trace_max_entries: int = 128,
        trace_ttl_s: float = 900.0,
        grant_max_entries: int = 128,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if trace_max_entries < 1:
            raise ValueError("trace_max_entries must be at least 1")
        if trace_ttl_s <= 0:
            raise ValueError("trace_ttl_s must be positive")
        self.registry = registry
        self.read_only_invoker = read_only_invoker
        self.planning_invoker = planning_invoker
        self.guarded_invoker = guarded_invoker
        self.allow_physical_motion = allow_physical_motion
        self.enable_parallel_execution = enable_parallel_execution
        self.max_concurrency = max_concurrency
        self.trace_max_entries = trace_max_entries
        self.trace_ttl_s = trace_ttl_s
        self._clock = clock
        self._resource_arbiter = (
            ResourceArbiter(max_concurrency)
            if enable_parallel_execution
            else None
        )
        self._traces: OrderedDict[str, tuple[float, ExecutionTrace]] = OrderedDict()
        self._grants = ConfirmationGrantStore(
            max_entries=grant_max_entries,
            clock=clock,
        )
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
        self._store_trace(graph.graph_id, trace)
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
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(graph, proofs)
            self._store_trace(graph.graph_id, trace)
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
        return await self._execute_tracked(
            graph,
            ReadOnlyTaskGraphExecutor(
                self.registry,
                self.read_only_invoker,
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(graph),
        )

    async def execute_planning(self, graph: TaskGraph) -> ExecutionTrace:
        if self.planning_invoker is None:
            raise RuntimeError("planning TaskGraph execution is disabled")
        planning_invoker = SoridormiTaskMonitoringInvoker(self.planning_invoker)
        return await self._execute_tracked(
            graph,
            PlanningTaskGraphExecutor(
                self.registry,
                planning_invoker,
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(graph),
        )

    async def _execute_tracked(
        self,
        graph: TaskGraph,
        execution: Awaitable[ExecutionTrace],
    ) -> ExecutionTrace:
        if graph.graph_id in self._active_executions:
            if hasattr(execution, "close"):
                execution.close()
            raise RuntimeError(f"TaskGraph {graph.graph_id!r} is already running")
        task = asyncio.current_task()
        if task is None:
            if hasattr(execution, "close"):
                execution.close()
            raise RuntimeError("TaskGraph execution requires an asyncio task")
        self._active_executions[graph.graph_id] = task
        try:
            trace = await execution
            self._store_trace(graph.graph_id, trace)
            return trace
        finally:
            self._active_executions.pop(graph.graph_id, None)

    def scheduler_status(self) -> TaskGraphSchedulerStatus:
        if self._resource_arbiter is None:
            return TaskGraphSchedulerStatus(
                parallel_enabled=False,
                max_concurrency=self.max_concurrency,
                active_count=0,
                waiting_count=0,
                serial_active=False,
                serial_waiters=0,
                active_graph_ids=sorted(self._active_executions),
            )
        snapshot = self._resource_arbiter.snapshot()
        return TaskGraphSchedulerStatus(
            parallel_enabled=True,
            max_concurrency=snapshot.max_concurrency,
            active_count=snapshot.active_count,
            waiting_count=snapshot.waiting_count,
            serial_active=snapshot.serial_active,
            serial_waiters=snapshot.serial_waiters,
            active_graph_ids=sorted(self._active_executions),
        )

    def get_trace(self, graph_id: str) -> ExecutionTrace | None:
        self._purge_expired_traces()
        retained = self._traces.get(graph_id)
        if retained is None:
            return None
        self._traces.move_to_end(graph_id)
        return retained[1].model_copy(deep=True)

    def _store_trace(self, graph_id: str, trace: ExecutionTrace) -> None:
        self._purge_expired_traces()
        self._traces.pop(graph_id, None)
        while len(self._traces) >= self.trace_max_entries:
            self._traces.popitem(last=False)
        self._traces[graph_id] = (
            self._now() + self.trace_ttl_s,
            trace.model_copy(deep=True),
        )

    def _purge_expired_traces(self) -> None:
        now = self._now()
        expired = [
            graph_id
            for graph_id, (expires_at, _) in self._traces.items()
            if expires_at < now
        ]
        for graph_id in expired:
            self._traces.pop(graph_id, None)

    def _now(self) -> float:
        return self._clock() if self._clock is not None else time.time()
