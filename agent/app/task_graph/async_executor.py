from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

try:
    from chromie_runtime import ResourceArbiter
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_runtime import ResourceArbiter

from ..capabilities.models import CapabilityRegistry, FailurePolicy
from ..tool_invocation import AsyncToolInvoker, ToolInvocationContext
from .models import ExecutionEvent, ExecutionTrace, NodeResult, TaskGraph, TaskNode
from .refs import resolve_refs
from .validator import GraphValidator

_READ_ONLY_CLASSES = {"safe_read", "planning_only"}


def _finalize_trace(
    trace: ExecutionTrace,
    *,
    sort_node_events: bool,
) -> ExecutionTrace:
    node_order = {
        node_id: index
        for index, node_id in enumerate(
            sorted(result.node_id for result in trace.node_results)
        )
    }
    if sort_node_events:
        indexed = list(enumerate(trace.events))
        event_priority = {
            "failure_policy": 0,
            "fallback_triggered": 1,
            "node_result": 2,
        }
        indexed.sort(
            key=lambda item: (
                1 if item[1].node_id is None else 0,
                node_order.get(item[1].node_id or "", len(node_order)),
                event_priority.get(item[1].type, 3),
                item[0],
            )
        )
        trace.events = [event for _, event in indexed]
    for sequence, event in enumerate(trace.events):
        event.data = {
            **event.data,
            "sequence": sequence,
            "stable_order": (
                node_order.get(event.node_id)
                if event.node_id is not None
                else None
            ),
        }
    return trace


@dataclass
class TaskGraphRunState:
    nodes: dict[str, TaskNode]
    pending: set[str]
    results: dict[str, NodeResult]
    activated_fallbacks: set[str]
    fallback_targets: set[str]
    aborted: bool = False

    @classmethod
    def create(cls, graph: TaskGraph) -> "TaskGraphRunState":
        nodes = graph.node_map()
        fallback_targets: set[str] = set()
        for node in graph.nodes:
            for policy in (node.on_failure, node.on_timeout):
                if policy and policy.target:
                    fallback_targets.add(policy.target)
            for policy in node.on_event.values():
                if policy.target:
                    fallback_targets.add(policy.target)
        return cls(
            nodes=nodes,
            pending=set(nodes),
            results={},
            activated_fallbacks=set(),
            fallback_targets=fallback_targets,
        )


class TaskGraphExecutionProofs(BaseModel):
    confirmed_node_ids: set[str] = Field(default_factory=set)


class ReadOnlyTaskGraphExecutor:
    """Execute a validated graph only when every node is free of side effects."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        invoker: AsyncToolInvoker,
        *,
        parallel_enabled: bool = False,
        resource_arbiter: ResourceArbiter | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.registry = registry
        self.invoker = invoker
        self.parallel_enabled = parallel_enabled
        self.resource_arbiter = (
            resource_arbiter
            if parallel_enabled
            else None
        ) or (
            ResourceArbiter(max_concurrency)
            if parallel_enabled
            else None
        )

    async def run(self, graph: TaskGraph) -> ExecutionTrace:
        report = GraphValidator(self.registry).validate(graph)
        report.raise_for_errors()
        self._preflight(graph)

        trace = ExecutionTrace(
            graph_id=graph.graph_id,
            status="running",
            summary=graph.summary or graph.summary_zh or "",
        )
        state = TaskGraphRunState.create(graph)

        try:
            while state.pending and not state.aborted:
                self._record_blocked_descendants(state, trace)
                ready = self._ready_nodes(state)
                if not ready:
                    dormant = state.pending & state.fallback_targets
                    state.pending.difference_update(dormant)
                    if not state.pending:
                        break
                    self._record_remaining(state, trace, status="blocked")
                    break

                ordered_ready = sorted(ready, key=lambda item: item.id)
                if self.parallel_enabled:
                    for node in ordered_ready:
                        state.pending.remove(node.id)
                    completed = await self._execute_parallel_wave(
                        ordered_ready,
                        state,
                        trace,
                    )
                else:
                    completed = []
                    for node in ordered_ready:
                        state.pending.remove(node.id)
                        result = await self._execute_node(node, state.results)
                        completed.append(result)
                        if self._apply_failure_policy(node, result, state, trace):
                            break
                for result in sorted(completed, key=lambda item: item.node_id):
                    self._record(trace, state.results, result)
                if state.aborted:
                    self._record_remaining(state, trace, status="cancelled")
        except asyncio.CancelledError:
            self._record_remaining(state, trace, status="cancelled")
            trace.status = "cancelled"
            trace.events.append(
                ExecutionEvent(
                    type="graph_cancelled",
                    message="TaskGraph execution cancelled.",
                )
            )
            return _finalize_trace(trace, sort_node_events=True)

        if state.aborted:
            trace.status = "aborted"
            trace.events.append(
                ExecutionEvent(
                    type="graph_aborted",
                    message="TaskGraph aborted by failure policy.",
                )
            )
        else:
            trace.status = (
                "success"
                if state.results
                and all(
                    result.status in {"success", "skipped"}
                    for result in state.results.values()
                )
                else "failed"
            )
        return _finalize_trace(trace, sort_node_events=True)

    def _ready_nodes(self, state: TaskGraphRunState) -> list[TaskNode]:
        ready: list[TaskNode] = []
        for node_id in state.pending:
            node = state.nodes[node_id]
            if node_id in state.activated_fallbacks:
                ready.append(node)
                continue
            if node_id in state.fallback_targets:
                continue
            if all(
                dep in state.results
                and state.results[dep].status in {"success", "skipped"}
                for dep in node.depends_on
            ):
                ready.append(node)
        return ready

    async def _execute_parallel_wave(
        self,
        nodes: list[TaskNode],
        state: TaskGraphRunState,
        trace: ExecutionTrace,
    ) -> list[NodeResult]:
        tasks = {
            asyncio.create_task(self._execute_node(node, state.results)): node
            for node in nodes
        }
        completed: list[NodeResult] = []
        try:
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                abort_wave = False
                for task in sorted(done, key=lambda item: tasks[item].id):
                    node = tasks[task]
                    result = task.result()
                    completed.append(result)
                    abort_wave = (
                        self._apply_failure_policy(node, result, state, trace)
                        or abort_wave
                    )
                if abort_wave and pending:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    completed.extend(
                        NodeResult(
                            node_id=tasks[task].id,
                            tool=tasks[task].tool,
                            status="cancelled",
                            error="cancelled by sibling failure policy",
                        )
                        for task in pending
                    )
                    break
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for task, node in tasks.items():
                if task.cancelled():
                    completed.append(
                        NodeResult(
                            node_id=node.id,
                            tool=node.tool,
                            status="cancelled",
                            error="execution cancelled",
                        )
                    )
                elif task.done() and not task.exception():
                    completed.append(task.result())
            for result in sorted(completed, key=lambda item: item.node_id):
                if result.node_id not in state.results:
                    self._record(trace, state.results, result)
            raise
        return completed

    def _apply_failure_policy(
        self,
        node: TaskNode,
        result: NodeResult,
        state: TaskGraphRunState,
        trace: ExecutionTrace,
    ) -> bool:
        if result.status == "success":
            return False
        policy = self._effective_failure_policy(node, result.status)
        trace.events.append(
            ExecutionEvent(
                type="failure_policy",
                node_id=node.id,
                tool=node.tool,
                message=f"Applying {policy.strategy} after {result.status}.",
                data={"target": policy.target},
            )
        )
        if policy.strategy == "continue_with_default":
            result.status = "success"
            result.output = policy.default_output or {}
            result.error = None
            return False
        if policy.strategy == "skip":
            result.status = "skipped"
            result.error = None
            return False
        if policy.strategy == "goto" and policy.target:
            state.activated_fallbacks.add(policy.target)
            trace.events.append(
                ExecutionEvent(
                    type="fallback_triggered",
                    node_id=node.id,
                    tool=node.tool,
                    data={"target": policy.target},
                )
            )
            return False
        if policy.strategy in {
            "abort_task",
            "stop_and_report",
            "emergency_stop",
            "ask_user",
        }:
            state.aborted = True
            return True
        return False

    def _effective_failure_policy(
        self,
        node: TaskNode,
        status: str,
    ) -> FailurePolicy:
        if status == "timeout" and node.on_timeout is not None:
            return node.on_timeout
        if node.on_failure is not None:
            return node.on_failure
        policy = self.registry.get_tool(node.tool).default_failure_policy
        if policy.strategy == "retry":
            return policy.then or FailurePolicy(strategy="abort_task")
        return policy

    def _record_blocked_descendants(
        self,
        state: TaskGraphRunState,
        trace: ExecutionTrace,
    ) -> None:
        changed = True
        while changed:
            changed = False
            for node_id in sorted(state.pending - state.fallback_targets):
                node = state.nodes[node_id]
                blocked_by = [
                    dep
                    for dep in node.depends_on
                    if dep in state.results
                    and state.results[dep].status
                    not in {"success", "skipped"}
                ]
                if blocked_by:
                    state.pending.remove(node_id)
                    self._record(
                        trace,
                        state.results,
                        NodeResult(
                            node_id=node.id,
                            tool=node.tool,
                            status="blocked",
                            blocked_by=blocked_by,
                        ),
                    )
                    changed = True

    def _record_remaining(
        self,
        state: TaskGraphRunState,
        trace: ExecutionTrace,
        *,
        status: str,
    ) -> None:
        for node_id in sorted(state.pending - state.fallback_targets):
            node = state.nodes[node_id]
            blocked_by = [
                dep
                for dep in node.depends_on
                if dep not in state.results
                or state.results[dep].status not in {"success", "skipped"}
            ]
            self._record(
                trace,
                state.results,
                NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status=status,
                    blocked_by=blocked_by if status == "blocked" else [],
                ),
            )
        state.pending.clear()

    def _preflight(self, graph: TaskGraph) -> None:
        if not graph.nodes:
            raise ValueError("read-only TaskGraph execution requires at least one node")
        unsafe: list[str] = []
        for node in graph.nodes:
            capability = self.registry.get_tool(node.tool)
            if capability.safety_class not in _READ_ONLY_CLASSES:
                unsafe.append(f"{node.id}:{node.tool}[{capability.safety_class}]")
            elif not capability.execution.side_effect_free:
                unsafe.append(f"{node.id}:{node.tool}[side_effect_free=false]")
        if unsafe:
            raise ValueError(
                "read-only TaskGraph execution rejected non-read-only nodes: " + ", ".join(unsafe)
            )

    async def _execute_node(
        self,
        node: TaskNode,
        results: dict[str, NodeResult],
    ) -> NodeResult:
        started = time.monotonic()
        try:
            args = resolve_refs(node.args, results)
        except KeyError as exc:
            return NodeResult(
                node_id=node.id,
                tool=node.tool,
                status="failed_fatal",
                error=str(exc),
                started_at=started,
                finished_at=time.monotonic(),
            )

        capability = self.registry.get_tool(node.tool)
        default_policy = capability.default_failure_policy
        max_attempts = (
            node.retry.max_attempts
            if node.retry
            else (
                default_policy.max_attempts or 1
                if default_policy.strategy == "retry"
                else 1
            )
        )
        backoff_s = (
            node.retry.backoff_s
            if node.retry
            else default_policy.backoff_s or 0.0
        )
        for attempt in range(1, max_attempts + 1):
            async def invoke() -> Any:
                if self.resource_arbiter is None:
                    return await self.invoker.invoke(node.tool, args)
                async with self.resource_arbiter.claim(
                    can_run_parallel=capability.execution.can_run_parallel,
                    exclusive_group=capability.execution.exclusive_group,
                ):
                    return await self.invoker.invoke(node.tool, args)

            timeout_s = node.timeout_s or capability.execution.timeout_s
            try:
                outcome = (
                    await asyncio.wait_for(invoke(), timeout=timeout_s)
                    if timeout_s is not None
                    else await invoke()
                )
            except TimeoutError:
                return NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status="timeout",
                    error=f"node exceeded {timeout_s:.3f}s timeout",
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )
            if outcome.status == "success" or outcome.status != "failed_retryable" or attempt >= max_attempts:
                return NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status=outcome.status,
                    output=outcome.output,
                    error=outcome.error,
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )
            if backoff_s:
                await asyncio.sleep(backoff_s)
        raise AssertionError("read-only TaskGraph retry loop exhausted unexpectedly")

    def _record(
        self,
        trace: ExecutionTrace,
        results: dict[str, NodeResult],
        result: NodeResult,
    ) -> None:
        results[result.node_id] = result
        trace.node_results.append(result)
        trace.events.append(
            ExecutionEvent(
                type="node_result",
                node_id=result.node_id,
                tool=result.tool,
                message=result.status,
                data={"error": result.error},
            )
        )


class PlanningTaskGraphExecutor(ReadOnlyTaskGraphExecutor):
    """Execute safe reads and non-physical planning tools, including plan creation."""

    def _preflight(self, graph: TaskGraph) -> None:
        if not graph.nodes:
            raise ValueError("planning TaskGraph execution requires at least one node")
        unsafe: list[str] = []
        for node in graph.nodes:
            capability = self.registry.get_tool(node.tool)
            if capability.safety_class == "safe_read":
                if not capability.execution.side_effect_free:
                    unsafe.append(f"{node.id}:{node.tool}[side_effect_free=false]")
                continue
            if capability.safety_class == "planning_only":
                prohibited_effects = {
                    "physical_motion",
                    "safety_control",
                } & set(capability.effects)
                if prohibited_effects:
                    unsafe.append(
                        f"{node.id}:{node.tool}[effects={sorted(prohibited_effects)}]"
                    )
                continue
            unsafe.append(f"{node.id}:{node.tool}[{capability.safety_class}]")
        if unsafe:
            raise ValueError(
                "planning TaskGraph execution rejected unsafe nodes: "
                + ", ".join(unsafe)
            )


class GuardedTaskGraphExecutor:
    """Execute side effects only with node-bound confirmation and monitor proof."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        invoker: AsyncToolInvoker,
        *,
        allow_physical_motion: bool = False,
        parallel_enabled: bool = False,
        resource_arbiter: ResourceArbiter | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.registry = registry
        self.invoker = invoker
        self.allow_physical_motion = allow_physical_motion
        self.parallel_enabled = parallel_enabled
        self.resource_arbiter = (
            resource_arbiter
            if parallel_enabled
            else None
        ) or (
            ResourceArbiter(max_concurrency)
            if parallel_enabled
            else None
        )

    async def run(
        self,
        graph: TaskGraph,
        proofs: TaskGraphExecutionProofs,
    ) -> ExecutionTrace:
        report = GraphValidator(self.registry).validate(graph)
        report.raise_for_errors()
        self._preflight(graph, proofs)

        trace = ExecutionTrace(
            graph_id=graph.graph_id,
            status="running",
            summary=graph.summary or graph.summary_zh or "",
        )
        nodes = graph.node_map()
        pending = set(nodes)
        results: dict[str, NodeResult] = {}
        active_monitors: set[str] = set()
        fallback_targets = self._fallback_targets(graph)
        current_node: TaskNode | None = None
        physical_started = False
        inflight_physical: set[asyncio.Task[Any]] = set()

        try:
            while pending:
                ready = [
                    nodes[node_id]
                    for node_id in pending
                    if node_id not in fallback_targets
                    and all(
                        dep in results and results[dep].status == "success"
                        for dep in nodes[node_id].depends_on
                    )
                ]
                if not ready:
                    dormant_fallbacks = pending & fallback_targets
                    pending.difference_update(dormant_fallbacks)
                    if not pending:
                        break
                    self._record_blocked(pending, nodes, results, trace)
                    break

                ordered_ready = sorted(ready, key=self._execution_priority)
                parallel_ready = [
                    node
                    for node in ordered_ready
                    if self._can_parallelize_guarded(node)
                ]
                if len(parallel_ready) >= 2:
                    for node in parallel_ready:
                        pending.remove(node.id)
                    completed = await self._execute_guarded_wave(
                        parallel_ready,
                        nodes,
                        results,
                        proofs,
                        active_monitors,
                        trace,
                    )
                    failed = False
                    for result in sorted(completed, key=lambda item: item.node_id):
                        self._record(trace, results, result)
                        failed = failed or result.status != "success"
                    if failed:
                        pending.difference_update(fallback_targets)
                        self._record_blocked(pending, nodes, results, trace)
                        pending.clear()
                    continue

                for node in ordered_ready:
                    current_node = node
                    if self._is_physical(node):
                        physical_started = True
                    pending.remove(node.id)
                    result = await self._execute_node(
                        node,
                        nodes,
                        results,
                        proofs,
                        active_monitors,
                        inflight_physical=inflight_physical,
                    )
                    current_node = None
                    self._record(trace, results, result)
                    monitor_started = (
                        result.output.get("ok") is True or result.output.get("active") is True
                    )
                    if node.type == "monitor" and result.status == "success" and monitor_started:
                        active_monitors.add(node.id)
                    if result.status != "success":
                        if self._is_physical(node):
                            await self._run_failure_fallback(
                                node,
                                result.status,
                                nodes,
                                pending,
                                results,
                                trace,
                            )
                        pending.difference_update(fallback_targets)
                        self._record_blocked(pending, nodes, results, trace)
                        pending.clear()
                        break
        except asyncio.CancelledError:
            if current_node is not None and current_node.id not in results:
                self._record(
                    trace,
                    results,
                    NodeResult(
                        node_id=current_node.id,
                        tool=current_node.tool,
                        status="cancelled",
                        error="execution cancelled",
                    ),
                )
            if physical_started:
                await asyncio.shield(
                    self._run_all_emergency_fallbacks(graph, nodes, pending, results, trace)
                )
                await asyncio.shield(self._drain_inflight_physical(inflight_physical))
            for node_id in sorted(pending - fallback_targets):
                node = nodes[node_id]
                if node.id not in results:
                    self._record(
                        trace,
                        results,
                        NodeResult(node_id=node.id, tool=node.tool, status="cancelled"),
                    )
            trace.status = "cancelled"
            trace.events.append(
                ExecutionEvent(type="graph_cancelled", message="TaskGraph execution cancelled.")
            )
            return _finalize_trace(trace, sort_node_events=False)

        trace.status = (
            "success"
            if results and all(result.status == "success" for result in results.values())
            else "failed"
        )
        return _finalize_trace(trace, sort_node_events=False)

    def _preflight(self, graph: TaskGraph, proofs: TaskGraphExecutionProofs) -> None:
        if not graph.nodes:
            raise ValueError("guarded TaskGraph execution requires at least one node")
        nodes = graph.node_map()
        invalid_proofs = sorted(proofs.confirmed_node_ids - set(nodes))
        if invalid_proofs:
            raise ValueError(f"confirmation proofs reference unknown nodes: {invalid_proofs}")

        confirmation_nodes = {
            node.id
            for node in graph.nodes
            if node.type == "confirmation" or node.tool == "chromie.ask_confirmation"
        }
        non_confirmation_proofs = sorted(proofs.confirmed_node_ids - confirmation_nodes)
        if non_confirmation_proofs:
            raise ValueError(
                f"confirmation proofs must reference confirmation nodes: {non_confirmation_proofs}"
            )

        for node in graph.nodes:
            capability = self.registry.get_tool(node.tool)
            if capability.safety_class == "restricted":
                raise ValueError(f"guarded execution rejects restricted tool {node.tool!r}")
            if capability.confirmation.required:
                required = self._transitive_confirmation_nodes(
                    node.id,
                    nodes,
                    confirmation_nodes,
                )
                if not required or not required.issubset(proofs.confirmed_node_ids):
                    raise ValueError(
                        f"node {node.id!r} lacks node-bound confirmation proof"
                    )
            if capability.safety_class == "physical_motion":
                if not self.allow_physical_motion:
                    raise ValueError("physical TaskGraph execution is disabled")
                if self._failure_fallback_node(node, nodes) is None:
                    raise ValueError(
                        f"physical node {node.id!r} requires a stop fallback target"
                    )
                if (
                    node.on_timeout is not None
                    and self._failure_fallback_node(node, nodes, status="timeout") is None
                ):
                    raise ValueError(
                        f"physical node {node.id!r} requires a stop timeout target"
                    )
                if self._emergency_fallback_node(node, nodes) is None:
                    raise ValueError(
                        f"physical node {node.id!r} requires an emergency-stop fallback target"
                    )
            if node.tool == "chromie.ask_confirmation":
                continue
            agent = self.registry.get_agent(capability.agent_id)
            if agent.transport.kind not in {"mcp_streamable_http", "streamable_http"}:
                raise ValueError(
                    f"guarded execution requires MCP Streamable HTTP for {node.tool!r}"
                )

    async def _execute_node(
        self,
        node: TaskNode,
        nodes: dict[str, TaskNode],
        results: dict[str, NodeResult],
        proofs: TaskGraphExecutionProofs,
        active_monitors: set[str],
        *,
        inflight_physical: set[asyncio.Task[Any]] | None = None,
    ) -> NodeResult:
        started = time.monotonic()
        if node.tool == "chromie.ask_confirmation":
            confirmed = node.id in proofs.confirmed_node_ids
            return NodeResult(
                node_id=node.id,
                tool=node.tool,
                status="success" if confirmed else "failed_fatal",
                output={"confirmed": confirmed},
                error=None if confirmed else "confirmation proof missing",
                started_at=started,
                finished_at=time.monotonic(),
            )

        try:
            args = resolve_refs(node.args, results)
        except KeyError as exc:
            return NodeResult(
                node_id=node.id,
                tool=node.tool,
                status="failed_fatal",
                error=str(exc),
                started_at=started,
                finished_at=time.monotonic(),
            )

        capability = self.registry.get_tool(node.tool)
        confirmation_nodes = {
            item.id
            for item in nodes.values()
            if item.type == "confirmation" or item.tool == "chromie.ask_confirmation"
        }
        confirmed = bool(
            self._transitive_confirmation_nodes(node.id, nodes, confirmation_nodes)
            & proofs.confirmed_node_ids
        )
        monitor_active = any(node.id in nodes[monitor_id].during for monitor_id in active_monitors)
        context = ToolInvocationContext(
            allow_side_effects=capability.safety_class in {"low_risk_action", "physical_motion"},
            confirmed=confirmed,
            safety_monitor_active=monitor_active,
            allow_safety_controls=node.type in {"monitor", "safety"},
        )
        if node.type in {"monitor", "safety"} or self._is_physical(node):
            if self._is_physical(node) and inflight_physical is not None:
                invocation = asyncio.create_task(
                    self.invoker.invoke(node.tool, args, context=context)
                )
                inflight_physical.add(invocation)
                invocation.add_done_callback(
                    lambda task: self._finish_inflight_physical(
                        task,
                        inflight_physical,
                    )
                )
                outcome = await asyncio.shield(invocation)
            else:
                outcome = await self.invoker.invoke(
                    node.tool,
                    args,
                    context=context,
                )
            return NodeResult(
                node_id=node.id,
                tool=node.tool,
                status=outcome.status,
                output=outcome.output,
                error=outcome.error,
                started_at=started,
                finished_at=time.monotonic(),
            )
        max_attempts = node.retry.max_attempts if node.retry else 1
        backoff_s = node.retry.backoff_s if node.retry else 0.0
        timeout_s = node.timeout_s or capability.execution.timeout_s
        for attempt in range(1, max_attempts + 1):
            async def invoke() -> Any:
                if self.resource_arbiter is None:
                    return await self.invoker.invoke(
                        node.tool,
                        args,
                        context=context,
                    )
                async with self.resource_arbiter.claim(
                    can_run_parallel=capability.execution.can_run_parallel,
                    exclusive_group=capability.execution.exclusive_group,
                ):
                    return await self.invoker.invoke(
                        node.tool,
                        args,
                        context=context,
                    )

            try:
                outcome = (
                    await asyncio.wait_for(invoke(), timeout=timeout_s)
                    if timeout_s is not None
                    else await invoke()
                )
            except TimeoutError:
                return NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status="timeout",
                    error=f"node exceeded {timeout_s:.3f}s timeout",
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )
            if (
                outcome.status == "success"
                or outcome.status != "failed_retryable"
                or attempt >= max_attempts
            ):
                return NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status=outcome.status,
                    output=outcome.output,
                    error=outcome.error,
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )
            if backoff_s:
                await asyncio.sleep(backoff_s)
        raise AssertionError("guarded TaskGraph retry loop exhausted unexpectedly")

    @staticmethod
    def _finish_inflight_physical(
        task: asyncio.Task[Any],
        inflight: set[asyncio.Task[Any]],
    ) -> None:
        inflight.discard(task)
        if task.cancelled():
            return
        task.exception()

    @staticmethod
    async def _drain_inflight_physical(
        inflight: set[asyncio.Task[Any]],
    ) -> None:
        if not inflight:
            return
        tasks = tuple(inflight)
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=2.0,
            )
        except TimeoutError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _can_parallelize_guarded(self, node: TaskNode) -> bool:
        if not self.parallel_enabled:
            return False
        capability = self.registry.get_tool(node.tool)
        return (
            node.type not in {"confirmation", "monitor", "safety"}
            and not self._is_physical(node)
            and capability.safety_class
            in {"safe_read", "planning_only", "low_risk_action"}
            and capability.execution.can_run_parallel
        )

    async def _execute_guarded_wave(
        self,
        ready: list[TaskNode],
        nodes: dict[str, TaskNode],
        results: dict[str, NodeResult],
        proofs: TaskGraphExecutionProofs,
        active_monitors: set[str],
        trace: ExecutionTrace,
    ) -> list[NodeResult]:
        tasks = {
            asyncio.create_task(
                self._execute_node(
                    node,
                    nodes,
                    results,
                    proofs,
                    active_monitors,
                )
            ): node
            for node in ready
        }
        completed: list[NodeResult] = []
        try:
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                failed = False
                for task in done:
                    result = task.result()
                    completed.append(result)
                    failed = failed or result.status != "success"
                if failed and pending:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    completed.extend(
                        NodeResult(
                            node_id=tasks[task].id,
                            tool=tasks[task].tool,
                            status="cancelled",
                            error="cancelled by sibling guarded-node failure",
                        )
                        for task in pending
                    )
                    break
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            cancelled: list[NodeResult] = []
            for task, node in tasks.items():
                if task.cancelled():
                    cancelled.append(
                        NodeResult(
                            node_id=node.id,
                            tool=node.tool,
                            status="cancelled",
                            error="execution cancelled",
                        )
                    )
                elif task.done() and not task.exception():
                    cancelled.append(task.result())
            for result in sorted(cancelled, key=lambda item: item.node_id):
                if result.node_id not in results:
                    self._record(trace, results, result)
            raise
        return completed

    def _execution_priority(self, node: TaskNode) -> tuple[int, str]:
        priority = {"confirmation": 0, "monitor": 1, "safety": 2}.get(node.type, 3)
        return priority, node.id

    def _fallback_targets(self, graph: TaskGraph) -> set[str]:
        targets: set[str] = set()
        for node in graph.nodes:
            for policy in (node.on_failure, node.on_timeout):
                if policy and policy.target:
                    targets.add(policy.target)
            for policy in node.on_event.values():
                if policy.target:
                    targets.add(policy.target)
        return targets

    def _is_physical(self, node: TaskNode) -> bool:
        capability = self.registry.get_tool(node.tool)
        return capability.safety_class == "physical_motion" or "physical_motion" in capability.effects

    def _failure_fallback_node(
        self,
        node: TaskNode,
        nodes: dict[str, TaskNode],
        *,
        status: str = "failed_fatal",
    ) -> TaskNode | None:
        policy = node.on_timeout if status == "timeout" and node.on_timeout else node.on_failure
        target = policy.target if policy else None
        if not target or target not in nodes:
            return None
        fallback = nodes[target]
        capability = self.registry.get_tool(fallback.tool)
        if (
            fallback.type == "safety"
            and capability.safety_class == "safety_critical"
            and "stop" in fallback.tool
        ):
            return fallback
        return None

    def _emergency_fallback_node(
        self,
        node: TaskNode,
        nodes: dict[str, TaskNode],
    ) -> TaskNode | None:
        policies = [node.on_failure, *node.on_event.values()]
        for policy in policies:
            target = policy.target if policy else None
            if not target or target not in nodes:
                continue
            fallback = nodes[target]
            capability = self.registry.get_tool(fallback.tool)
            if (
                fallback.type == "safety"
                and capability.safety_class == "safety_critical"
                and "emergency_stop" in fallback.tool
            ):
                return fallback
        return None

    async def _run_fallback(
        self,
        fallback: TaskNode | None,
        nodes: dict[str, TaskNode],
        pending: set[str],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
        *,
        event_type: str,
    ) -> None:
        if fallback is None or fallback.id in results:
            return
        pending.discard(fallback.id)
        capability = self.registry.get_tool(fallback.tool)
        max_attempts = 3 if capability.execution.idempotent else 1
        outcome = None
        attempts = 0
        for attempts in range(1, max_attempts + 1):
            outcome = await self.invoker.invoke(
                fallback.tool,
                fallback.args,
                context=ToolInvocationContext(allow_safety_controls=True),
            )
            if outcome.status != "failed_retryable" or attempts >= max_attempts:
                break
            await asyncio.sleep(0.1)
        assert outcome is not None
        self._record(
            trace,
            results,
            NodeResult(
                node_id=fallback.id,
                tool=fallback.tool,
                status=outcome.status,
                output=outcome.output,
                error=outcome.error,
                attempts=attempts,
            ),
        )
        trace.events.append(
            ExecutionEvent(
                type=event_type,
                node_id=fallback.id,
                tool=fallback.tool,
                message=outcome.status,
            )
        )

    async def _run_failure_fallback(
        self,
        node: TaskNode,
        status: str,
        nodes: dict[str, TaskNode],
        pending: set[str],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
    ) -> None:
        fallback = self._failure_fallback_node(node, nodes, status=status)
        await self._run_fallback(
            fallback,
            nodes,
            pending,
            results,
            trace,
            event_type=(
                "emergency_fallback"
                if fallback and "emergency_stop" in fallback.tool
                else "stop_fallback"
            ),
        )

    async def _run_emergency_fallback(
        self,
        node: TaskNode,
        nodes: dict[str, TaskNode],
        pending: set[str],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
    ) -> None:
        await self._run_fallback(
            self._emergency_fallback_node(node, nodes),
            nodes,
            pending,
            results,
            trace,
            event_type="emergency_fallback",
        )

    async def _run_all_emergency_fallbacks(
        self,
        graph: TaskGraph,
        nodes: dict[str, TaskNode],
        pending: set[str],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
    ) -> None:
        for node in graph.nodes:
            if self._is_physical(node):
                await self._run_emergency_fallback(node, nodes, pending, results, trace)

    def _transitive_confirmation_nodes(
        self,
        node_id: str,
        nodes: dict[str, TaskNode],
        confirmation_nodes: set[str],
    ) -> set[str]:
        found: set[str] = set()
        seen: set[str] = set()

        def walk(current: str) -> None:
            if current in seen or current not in nodes:
                return
            seen.add(current)
            for dep in nodes[current].depends_on:
                if dep in confirmation_nodes:
                    found.add(dep)
                walk(dep)

        walk(node_id)
        return found

    def _record_blocked(
        self,
        pending: set[str],
        nodes: dict[str, TaskNode],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
    ) -> None:
        for node_id in sorted(pending):
            node = nodes[node_id]
            blocked_by = [
                dep for dep in node.depends_on if dep not in results or results[dep].status != "success"
            ]
            self._record(
                trace,
                results,
                NodeResult(
                    node_id=node.id,
                    tool=node.tool,
                    status="blocked",
                    blocked_by=blocked_by,
                ),
            )

    def _record(
        self,
        trace: ExecutionTrace,
        results: dict[str, NodeResult],
        result: NodeResult,
    ) -> None:
        results[result.node_id] = result
        trace.node_results.append(result)
        trace.events.append(
            ExecutionEvent(
                type="node_result",
                node_id=result.node_id,
                tool=result.tool,
                message=result.status,
                data={"error": result.error},
            )
        )
