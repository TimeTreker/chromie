from __future__ import annotations

import asyncio
import hashlib
import json
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
    GuardedDAGEngine,
    PlanningDAGEngine,
    ReadOnlyDAGEngine,
    DAGExecutionProofs,
)
from .executor import DAGDryRunEngine
from .grants import ConfirmationGrantStore
from .models import ExecutionEvent, ExecutionTrace, NodeResult, WorkDAG
from .validator import WorkDAGValidator


class WorkDAGValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkDAGDryRunRequest(BaseModel):
    dag: WorkDAG
    auto_confirm: bool = True


class WorkDAGExecuteRequest(BaseModel):
    dag: WorkDAG


class WorkDAGGuardedExecuteRequest(BaseModel):
    dag: WorkDAG
    confirmation_grant: str


class WorkDAGConfirmationGrantRequest(BaseModel):
    dag: WorkDAG
    confirmed_node_ids: set[str] = Field(default_factory=set)
    ttl_s: int = Field(default=60, ge=1, le=300)


class WorkDAGConfirmationGrantResponse(BaseModel):
    confirmation_grant: str
    dag_id: str
    dag_revision: int = Field(ge=1)
    confirmed_node_ids: set[str]
    expires_at: float


class WorkDAGCancelResponse(BaseModel):
    dag_id: str
    cancellation_requested: bool


class DAGEngineStatus(BaseModel):
    parallel_enabled: bool
    max_concurrency: int
    active_count: int
    waiting_count: int
    serial_active: bool
    serial_waiters: int
    active_dag_ids: list[str] = Field(default_factory=list)


class DAGEngineService:
    """Deterministic scheduler/executor for Planner-authored WorkDAG revisions."""

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
        self._traces: OrderedDict[
            str,
            tuple[float, str, str, WorkDAG, ExecutionTrace],
        ] = OrderedDict()
        self._grants = ConfirmationGrantStore(
            max_entries=grant_max_entries,
            clock=clock,
        )
        self._active_executions: dict[str, asyncio.Task[ExecutionTrace]] = {}
        self._pending_cancellations: OrderedDict[str, float] = OrderedDict()

    def validate(self, dag: WorkDAG) -> WorkDAGValidationResponse:
        report = WorkDAGValidator(self.registry).validate(dag)
        return WorkDAGValidationResponse(
            valid=report.valid,
            errors=list(report.errors),
            warnings=list(report.warnings),
        )

    def dry_run(self, dag: WorkDAG, *, auto_confirm: bool = True) -> ExecutionTrace:
        validation = self.validate(dag)
        if not validation.valid:
            raise ValueError("WorkDAG validation failed: " + "; ".join(validation.errors))

        trace = DAGDryRunEngine(self.registry, auto_confirm=auto_confirm).run(dag, validate=False)
        self._store_trace(dag, trace, execution_kind="dry_run")
        return trace

    async def execute_guarded(
        self,
        dag: WorkDAG,
        confirmation_grant: str,
    ) -> ExecutionTrace:
        if self.guarded_invoker is None:
            raise RuntimeError("guarded WorkDAG execution is disabled")
        if dag.dag_id in self._active_executions:
            raise RuntimeError(f"WorkDAG {dag.dag_id!r} is already running")

        grant = self._grants.consume(confirmation_grant, dag)
        retained, prior_results = self._prepare_execution(
            dag,
            execution_kind="guarded",
        )
        if retained is not None:
            return retained
        cancelled = self._take_pre_execution_cancellation(dag)
        if cancelled is not None:
            return cancelled
        proofs = DAGExecutionProofs(
            confirmed_node_ids=set(grant.confirmed_node_ids)
        )
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("guarded WorkDAG execution requires an asyncio task")
        self._active_executions[dag.dag_id] = task
        try:
            trace = await GuardedDAGEngine(
                self.registry,
                self.guarded_invoker,
                allow_physical_motion=self.allow_physical_motion,
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(dag, proofs, prior_results=prior_results)
            self._store_trace(
                dag,
                trace,
                execution_kind="guarded",
            )
            return trace
        finally:
            self._active_executions.pop(dag.dag_id, None)

    def issue_confirmation_grant(
        self,
        request: WorkDAGConfirmationGrantRequest,
    ) -> WorkDAGConfirmationGrantResponse:
        if self.guarded_invoker is None:
            raise RuntimeError("guarded WorkDAG execution is disabled")
        report = WorkDAGValidator(self.registry).validate(request.dag)
        report.raise_for_errors()
        confirmation_nodes = {
            node.id
            for node in request.dag.nodes
            if node.role == "confirmation" or node.capability_id == "chromie.ask_confirmation"
        }
        invalid = sorted(request.confirmed_node_ids - confirmation_nodes)
        if invalid:
            raise ValueError(
                f"confirmation grants must reference confirmation nodes: {invalid}"
            )
        token, grant = self._grants.issue(
            request.dag,
            request.confirmed_node_ids,
            ttl_s=request.ttl_s,
        )
        return WorkDAGConfirmationGrantResponse(
            confirmation_grant=token,
            dag_id=request.dag.dag_id,
            dag_revision=request.dag.revision,
            confirmed_node_ids=set(grant.confirmed_node_ids),
            expires_at=grant.expires_at,
        )

    def cancel_execution(self, dag_id: str) -> WorkDAGCancelResponse:
        task = self._active_executions.get(dag_id)
        if task is not None and not task.done():
            task.cancel()
            return WorkDAGCancelResponse(
                dag_id=dag_id,
                cancellation_requested=True,
            )

        self._purge_expired_traces()
        self._purge_expired_cancellations()
        retained = self._traces.get(dag_id)
        if retained is not None and retained[2] != "dry_run":
            return WorkDAGCancelResponse(
                dag_id=dag_id,
                cancellation_requested=False,
            )
        self._pending_cancellations.pop(dag_id, None)
        while len(self._pending_cancellations) >= self.trace_max_entries:
            self._pending_cancellations.popitem(last=False)
        self._pending_cancellations[dag_id] = (
            self._now() + self.trace_ttl_s
        )
        return WorkDAGCancelResponse(
            dag_id=dag_id,
            cancellation_requested=True,
        )

    async def execute_read_only(self, dag: WorkDAG) -> ExecutionTrace:
        if self.read_only_invoker is None:
            raise RuntimeError("read-only WorkDAG execution is disabled")
        retained, prior_results = self._prepare_execution(
            dag,
            execution_kind="read_only",
        )
        if retained is not None:
            return retained
        return await self._execute_tracked(
            dag,
            ReadOnlyDAGEngine(
                self.registry,
                self.read_only_invoker,
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(dag, prior_results=prior_results),
            execution_kind="read_only",
            already_prepared=True,
        )

    async def execute_planning(self, dag: WorkDAG) -> ExecutionTrace:
        if self.planning_invoker is None:
            raise RuntimeError("planning WorkDAG execution is disabled")
        retained, prior_results = self._prepare_execution(
            dag,
            execution_kind="planning",
        )
        if retained is not None:
            return retained
        planning_invoker = SoridormiTaskMonitoringInvoker(self.planning_invoker)
        return await self._execute_tracked(
            dag,
            PlanningDAGEngine(
                self.registry,
                planning_invoker,
                parallel_enabled=self.enable_parallel_execution,
                resource_arbiter=self._resource_arbiter,
                max_concurrency=self.max_concurrency,
            ).run(dag, prior_results=prior_results),
            execution_kind="planning",
            already_prepared=True,
        )

    async def _execute_tracked(
        self,
        dag: WorkDAG,
        execution: Awaitable[ExecutionTrace],
        *,
        execution_kind: str,
        already_prepared: bool = False,
    ) -> ExecutionTrace:
        if dag.dag_id in self._active_executions:
            if hasattr(execution, "close"):
                execution.close()
            raise RuntimeError(f"WorkDAG {dag.dag_id!r} is already running")
        if not already_prepared:
            try:
                retained, _ = self._prepare_execution(
                    dag,
                    execution_kind=execution_kind,
                )
            except BaseException:
                if hasattr(execution, "close"):
                    execution.close()
                raise
            if retained is not None:
                if hasattr(execution, "close"):
                    execution.close()
                return retained
        cancelled = self._take_pre_execution_cancellation(dag)
        if cancelled is not None:
            if hasattr(execution, "close"):
                execution.close()
            return cancelled
        task = asyncio.current_task()
        if task is None:
            if hasattr(execution, "close"):
                execution.close()
            raise RuntimeError("WorkDAG execution requires an asyncio task")
        self._active_executions[dag.dag_id] = task
        try:
            trace = await execution
            self._store_trace(
                dag,
                trace,
                execution_kind=execution_kind,
            )
            return trace
        finally:
            self._active_executions.pop(dag.dag_id, None)

    def engine_status(self) -> DAGEngineStatus:
        if self._resource_arbiter is None:
            return DAGEngineStatus(
                parallel_enabled=False,
                max_concurrency=self.max_concurrency,
                active_count=0,
                waiting_count=0,
                serial_active=False,
                serial_waiters=0,
                active_dag_ids=sorted(self._active_executions),
            )
        snapshot = self._resource_arbiter.snapshot()
        return DAGEngineStatus(
            parallel_enabled=True,
            max_concurrency=snapshot.max_concurrency,
            active_count=snapshot.active_count,
            waiting_count=snapshot.waiting_count,
            serial_active=snapshot.serial_active,
            serial_waiters=snapshot.serial_waiters,
            active_dag_ids=sorted(self._active_executions),
        )

    def get_trace(self, dag_id: str) -> ExecutionTrace | None:
        self._purge_expired_traces()
        retained = self._traces.get(dag_id)
        if retained is None:
            return None
        self._traces.move_to_end(dag_id)
        return retained[4].model_copy(deep=True)

    def _store_trace(
        self,
        dag: WorkDAG,
        trace: ExecutionTrace,
        *,
        execution_kind: str,
    ) -> None:
        self._purge_expired_traces()
        retained = self._traces.get(dag.dag_id)
        if (
            execution_kind == "dry_run"
            and retained is not None
            and retained[2] != "dry_run"
        ):
            # Diagnostics must never erase an authoritative execution or
            # cancellation receipt for this idempotency identity.
            self._traces.move_to_end(dag.dag_id)
            return
        self._traces.pop(dag.dag_id, None)
        while len(self._traces) >= self.trace_max_entries:
            self._traces.popitem(last=False)
        self._traces[dag.dag_id] = (
            self._now() + self.trace_ttl_s,
            self._dag_fingerprint(dag),
            execution_kind,
            dag.model_copy(deep=True),
            trace.model_copy(deep=True),
        )

    def _purge_expired_traces(self) -> None:
        now = self._now()
        expired = [
            dag_id
            for dag_id, (expires_at, _, _, _, _) in self._traces.items()
            if expires_at < now
        ]
        for dag_id in expired:
            self._traces.pop(dag_id, None)

    def _purge_expired_cancellations(self) -> None:
        now = self._now()
        expired = [
            dag_id
            for dag_id, expires_at in self._pending_cancellations.items()
            if expires_at < now
        ]
        for dag_id in expired:
            self._pending_cancellations.pop(dag_id, None)

    def _take_pre_execution_cancellation(
        self,
        dag: WorkDAG,
    ) -> ExecutionTrace | None:
        """Consume an early cancel that beat the execute request to Agent."""

        self._purge_expired_cancellations()
        if self._pending_cancellations.pop(dag.dag_id, None) is None:
            return None
        message = "Cancellation was accepted before WorkDAG execution started"
        trace = ExecutionTrace(
            dag_id=dag.dag_id,
            dag_revision=dag.revision,
            status="cancelled",
            summary=dag.summary,
            events=[
                ExecutionEvent(
                    type="cancelled_before_start",
                    message=message,
                )
            ],
        )
        self._store_trace(
            dag,
            trace,
            execution_kind="cancelled_before_start",
        )
        return trace.model_copy(deep=True)

    def _prepare_execution(
        self,
        dag: WorkDAG,
        *,
        execution_kind: str,
    ) -> tuple[ExecutionTrace | None, dict[str, NodeResult]]:
        """Return idempotent trace or inherited completed-node facts for a revision.

        Planner is the only semantic revision author. DAGEngine merely verifies
        monotonic revision identity and protects completed history from being
        rewritten or re-executed.
        """

        self._purge_expired_traces()
        retained = self._traces.get(dag.dag_id)
        if retained is None or retained[2] == "dry_run":
            if dag.revision != 1:
                raise ValueError(
                    f"WorkDAG dag_id={dag.dag_id!r} has no authoritative prior "
                    f"revision; first execution must use revision=1"
                )
            return None, {}

        _, fingerprint, retained_kind, prior_dag, trace = retained
        if dag.revision == prior_dag.revision:
            if fingerprint != self._dag_fingerprint(dag):
                raise ValueError(
                    f"WorkDAG dag_id={dag.dag_id!r} revision={dag.revision} "
                    "is retained for different DAG content"
                )
            if trace.status != "cancelled" and retained_kind != execution_kind:
                raise ValueError(
                    f"WorkDAG dag_id={dag.dag_id!r} revision={dag.revision} "
                    f"is retained for different execution lane={retained_kind!r}"
                )
            self._traces.move_to_end(dag.dag_id)
            return trace.model_copy(deep=True), {}

        if dag.revision != prior_dag.revision + 1:
            raise ValueError(
                f"WorkDAG dag_id={dag.dag_id!r} revision must advance exactly "
                f"from {prior_dag.revision} to {prior_dag.revision + 1}"
            )
        if dag.parent_revision != prior_dag.revision:
            raise ValueError(
                f"WorkDAG dag_id={dag.dag_id!r} revision={dag.revision} must "
                f"declare parent_revision={prior_dag.revision}"
            )
        if retained_kind != execution_kind and trace.status != "cancelled":
            raise ValueError(
                f"WorkDAG dag_id={dag.dag_id!r} revision cannot change execution "
                f"lane from {retained_kind!r} to {execution_kind!r}"
            )

        prior_nodes = prior_dag.node_map()
        new_nodes = dag.node_map()
        inherited: dict[str, NodeResult] = {}
        for result in trace.node_results:
            if result.status not in {"success", "skipped"}:
                continue
            prior_node = prior_nodes.get(result.node_id)
            new_node = new_nodes.get(result.node_id)
            if prior_node is None or new_node is None:
                raise ValueError(
                    f"WorkDAG revision may not remove completed node {result.node_id!r}"
                )
            if prior_node.model_dump(mode="json") != new_node.model_dump(mode="json"):
                raise ValueError(
                    f"WorkDAG revision may not rewrite completed node {result.node_id!r}"
                )
            inherited[result.node_id] = result.model_copy(
                deep=True,
                update={"inherited_from_revision": prior_dag.revision},
            )
        return None, inherited

    @staticmethod
    def _dag_fingerprint(dag: WorkDAG) -> str:
        canonical = json.dumps(
            dag.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _now(self) -> float:
        return self._clock() if self._clock is not None else time.time()
