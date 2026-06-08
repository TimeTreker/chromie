from __future__ import annotations

import asyncio
import time

from pydantic import BaseModel, Field

from ..capabilities.models import CapabilityRegistry
from ..tool_invocation import AsyncToolInvoker, ToolInvocationContext
from .models import ExecutionEvent, ExecutionTrace, NodeResult, TaskGraph, TaskNode
from .refs import resolve_refs
from .validator import GraphValidator

_READ_ONLY_CLASSES = {"safe_read", "planning_only"}


class TaskGraphExecutionProofs(BaseModel):
    confirmed_node_ids: set[str] = Field(default_factory=set)


class ReadOnlyTaskGraphExecutor:
    """Execute a validated graph only when every node is free of side effects."""

    def __init__(self, registry: CapabilityRegistry, invoker: AsyncToolInvoker) -> None:
        self.registry = registry
        self.invoker = invoker

    async def run(self, graph: TaskGraph) -> ExecutionTrace:
        report = GraphValidator(self.registry).validate(graph)
        report.raise_for_errors()
        self._preflight(graph)

        trace = ExecutionTrace(
            graph_id=graph.graph_id,
            status="running",
            summary=graph.summary or graph.summary_zh or "",
        )
        nodes = graph.node_map()
        pending = set(nodes)
        results: dict[str, NodeResult] = {}

        while pending:
            ready = [
                nodes[node_id]
                for node_id in pending
                if all(dep in results and results[dep].status == "success" for dep in nodes[node_id].depends_on)
            ]
            if not ready:
                for node_id in sorted(pending):
                    node = nodes[node_id]
                    blocked_by = [
                        dep
                        for dep in node.depends_on
                        if dep not in results or results[dep].status != "success"
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
                break

            for node in sorted(ready, key=lambda item: item.id):
                pending.remove(node.id)
                result = await self._execute_node(node, results)
                self._record(trace, results, result)

        trace.status = (
            "success"
            if results and all(result.status == "success" for result in results.values())
            else "failed"
        )
        return trace

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

        max_attempts = node.retry.max_attempts if node.retry else 1
        for attempt in range(1, max_attempts + 1):
            outcome = await self.invoker.invoke(node.tool, args)
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
    ) -> None:
        self.registry = registry
        self.invoker = invoker
        self.allow_physical_motion = allow_physical_motion

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

                for node in sorted(ready, key=self._execution_priority):
                    current_node = node
                    if self._is_physical(node):
                        physical_started = True
                    pending.remove(node.id)
                    result = await self._execute_node(node, nodes, results, proofs, active_monitors)
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
            return trace

        trace.status = (
            "success"
            if results and all(result.status == "success" for result in results.values())
            else "failed"
        )
        return trace

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
        outcome = await self.invoker.invoke(node.tool, args, context=context)
        return NodeResult(
            node_id=node.id,
            tool=node.tool,
            status=outcome.status,
            output=outcome.output,
            error=outcome.error,
            started_at=started,
            finished_at=time.monotonic(),
        )

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
        outcome = await self.invoker.invoke(
            fallback.tool,
            fallback.args,
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        self._record(
            trace,
            results,
            NodeResult(
                node_id=fallback.id,
                tool=fallback.tool,
                status=outcome.status,
                output=outcome.output,
                error=outcome.error,
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
