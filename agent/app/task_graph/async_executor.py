from __future__ import annotations

import time

from ..capabilities.models import CapabilityRegistry
from ..tool_invocation import AsyncToolInvoker
from .models import ExecutionEvent, ExecutionTrace, NodeResult, TaskGraph, TaskNode
from .refs import resolve_refs
from .validator import GraphValidator

_READ_ONLY_CLASSES = {"safe_read", "planning_only"}


class ReadOnlyTaskGraphExecutor:
    """Execute a validated graph only when every node is free of side effects."""

    def __init__(self, registry: CapabilityRegistry, invoker: AsyncToolInvoker) -> None:
        self.registry = registry
        self.invoker = invoker

    async def run(self, graph: TaskGraph) -> ExecutionTrace:
        report = GraphValidator(self.registry).validate(graph)
        report.raise_for_errors()
        self._preflight_read_only(graph)

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

    def _preflight_read_only(self, graph: TaskGraph) -> None:
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
