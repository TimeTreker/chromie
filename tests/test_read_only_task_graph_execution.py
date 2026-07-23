from __future__ import annotations

import unittest
import asyncio
from typing import Any

from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ExecutionPolicy,
    ToolCapability,
    TransportSpec,
)
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.service import TaskGraphService
from agent.app.tool_invocation import McpStreamableHttpInvoker


def _registry():
    bundle = CapabilityBundle(
        source="remote-test",
        agents=[
            AgentManifest(
                agent_id="remote",
                transport=TransportSpec(kind="mcp_streamable_http", url="http://remote:8000/mcp"),
                tools=[
                    ToolCapability(
                        name="remote.lookup",
                        agent_id="remote",
                        safety_class="safe_read",
                        effects=["read_only"],
                    ),
                    ToolCapability(
                        name="remote.plan",
                        agent_id="remote",
                        safety_class="planning_only",
                        effects=["planning_only"],
                    ),
                    ToolCapability(
                        name="remote.write",
                        agent_id="remote",
                        safety_class="low_risk_action",
                        effects=["write"],
                        execution=ExecutionPolicy(side_effect_free=False),
                    ),
                ],
            )
        ],
    )
    return build_chromie_registry([bundle])


class ReadOnlyTaskGraphExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_executes_read_only_graph_and_resolves_refs(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            calls.append((tool, args))
            if tool == "remote.lookup":
                return {"structuredContent": {"value": "result-1"}}
            return {"structuredContent": {"plan": f"use {args['input']}"}}

        service = TaskGraphService(
            _registry(),
            read_only_invoker=McpStreamableHttpInvoker(_registry(), call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "read-only-success",
                "created_by": "user",
                "nodes": [
                    {"id": "lookup", "tool": "remote.lookup", "type": "query"},
                    {
                        "id": "plan",
                        "tool": "remote.plan",
                        "type": "plan",
                        "depends_on": ["lookup"],
                        "args": {"input": {"$ref": "lookup.output.value"}},
                    },
                ],
            }
        )

        dry_run = service.dry_run(graph)
        trace = await service.execute_read_only(graph)

        self.assertIn(dry_run.status, {"success", "aborted"})
        self.assertEqual(trace.status, "success")
        self.assertEqual(calls[1], ("remote.plan", {"input": "result-1"}))
        self.assertEqual(service.get_trace(graph.graph_id).status, "success")

    async def test_rejects_entire_graph_before_calling_any_side_effect(self) -> None:
        calls = 0

        async def call(url: str, tool: str, args: dict[str, Any], timeout_s: float) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "read-only-rejected",
                "created_by": "user",
                "nodes": [
                    {"id": "lookup", "tool": "remote.lookup", "type": "query"},
                    {
                        "id": "write",
                        "tool": "remote.write",
                        "type": "action",
                        "depends_on": ["lookup"],
                    },
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "non-read-only nodes"):
            await service.execute_read_only(graph)

        self.assertEqual(calls, 0)
        self.assertIsNone(service.get_trace(graph.graph_id))

    async def test_disabled_execution_fails_without_invocation(self) -> None:
        graph = TaskGraph.model_validate(
            {
                "graph_id": "disabled",
                "created_by": "user",
                "nodes": [{"id": "lookup", "tool": "remote.lookup", "type": "query"}],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            await TaskGraphService(_registry()).execute_read_only(graph)

    async def test_parallel_execution_is_bounded_and_result_order_is_stable(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(float(args["delay_s"]))
            active -= 1
            return {"structuredContent": {"node": args["node"]}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "parallel-order",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "c",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"node": "c", "delay_s": 0.01},
                    },
                    {
                        "id": "a",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"node": "a", "delay_s": 0.04},
                    },
                    {
                        "id": "b",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"node": "b", "delay_s": 0.02},
                    },
                ],
            }
        )

        trace = await service.execute_read_only(graph)

        self.assertEqual(peak, 2)
        self.assertEqual(
            [result.node_id for result in trace.node_results],
            ["a", "b", "c"],
        )

    async def test_parallel_flag_off_preserves_sequential_execution(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "sequential-fallback",
                "created_by": "user",
                "nodes": [
                    {"id": "a", "tool": "remote.lookup", "type": "query"},
                    {"id": "b", "tool": "remote.lookup", "type": "query"},
                ],
            }
        )

        await service.execute_read_only(graph)

        self.assertEqual(peak, 1)

    async def test_exclusive_group_serializes_across_graph_executions(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        registry.get_tool("remote.lookup").execution.exclusive_group = "remote_api"
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )

        def graph(graph_id: str) -> TaskGraph:
            return TaskGraph.model_validate(
                {
                    "graph_id": graph_id,
                    "created_by": "user",
                    "nodes": [
                        {"id": "lookup", "tool": "remote.lookup", "type": "query"}
                    ],
                }
            )

        await asyncio.gather(
            service.execute_read_only(graph("graph-a")),
            service.execute_read_only(graph("graph-b")),
        )

        self.assertEqual(peak, 1)

    async def test_non_parallel_capability_excludes_other_ready_work(self) -> None:
        active = 0
        peak = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        registry.get_tool("remote.lookup").execution.can_run_parallel = False
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "non-parallel-capability",
                "created_by": "user",
                "nodes": [
                    {"id": "a", "tool": "remote.lookup", "type": "query"},
                    {"id": "b", "tool": "remote.lookup", "type": "query"},
                ],
            }
        )

        await service.execute_read_only(graph)

        self.assertEqual(peak, 1)

    async def test_node_timeout_and_retry_policy_are_preserved(self) -> None:
        attempts = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if args.get("timeout"):
                await asyncio.sleep(0.05)
            if attempts == 1:
                raise ConnectionError("retry me")
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        retry_graph = TaskGraph.model_validate(
            {
                "graph_id": "retry-policy",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "lookup",
                        "tool": "remote.lookup",
                        "type": "query",
                        "retry": {"max_attempts": 2, "backoff_s": 0},
                    }
                ],
            }
        )

        retry_trace = await service.execute_read_only(retry_graph)

        self.assertEqual(retry_trace.node_results[0].status, "success")
        self.assertEqual(retry_trace.node_results[0].attempts, 2)

        timeout_graph = TaskGraph.model_validate(
            {
                "graph_id": "timeout-policy",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "lookup",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"timeout": True},
                        "timeout_s": 0.01,
                    }
                ],
            }
        )

        timeout_trace = await service.execute_read_only(timeout_graph)

        self.assertEqual(timeout_trace.node_results[0].status, "timeout")

    async def test_failure_policies_support_default_skip_and_goto(self) -> None:
        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            if args.get("fail"):
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": "lookup failed"}],
                }
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "failure-policies",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "defaulted",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"fail": True},
                        "on_failure": {
                            "strategy": "continue_with_default",
                            "default_output": {"ok": False},
                        },
                    },
                    {
                        "id": "skipped",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"fail": True},
                        "on_failure": {"strategy": "skip"},
                    },
                    {
                        "id": "failed",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"fail": True},
                        "on_failure": {
                            "strategy": "goto",
                            "target": "fallback",
                        },
                    },
                    {
                        "id": "fallback",
                        "tool": "remote.lookup",
                        "type": "query",
                    },
                ],
            }
        )

        trace = await service.execute_read_only(graph)
        results = trace.result_map()

        self.assertEqual(trace.status, "failed")
        self.assertEqual(results["defaulted"].status, "success")
        self.assertEqual(results["defaulted"].output, {"ok": False})
        self.assertEqual(results["skipped"].status, "skipped")
        self.assertEqual(results["failed"].status, "failed_fatal")
        self.assertEqual(results["fallback"].status, "success")
        self.assertTrue(any(event.type == "fallback_triggered" for event in trace.events))

    async def test_abort_policy_cancels_running_sibling(self) -> None:
        slow_started = asyncio.Event()
        slow_cancelled = asyncio.Event()

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            if args.get("slow"):
                slow_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    slow_cancelled.set()
            await slow_started.wait()
            return {
                "isError": True,
                "content": [{"type": "text", "text": "fatal"}],
            }

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "abort-sibling",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "fail",
                        "tool": "remote.lookup",
                        "type": "query",
                        "on_failure": {"strategy": "abort_task"},
                    },
                    {
                        "id": "slow",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"slow": True},
                    },
                ],
            }
        )

        trace = await service.execute_read_only(graph)

        self.assertEqual(trace.status, "aborted")
        self.assertTrue(slow_cancelled.is_set())
        self.assertEqual(trace.result_map()["slow"].status, "cancelled")

    async def test_read_only_cancellation_retains_trace_and_is_isolated(self) -> None:
        started = {"cancel": asyncio.Event(), "keep": asyncio.Event()}
        release_keep = asyncio.Event()

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            graph = str(args["graph"])
            started[graph].set()
            if graph == "keep":
                await release_keep.wait()
                return {"structuredContent": {"ok": True}}
            await asyncio.Event().wait()
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )

        def graph(graph_id: str, marker: str) -> TaskGraph:
            return TaskGraph.model_validate(
                {
                    "graph_id": graph_id,
                    "created_by": "user",
                    "nodes": [
                        {
                            "id": "lookup",
                            "tool": "remote.lookup",
                            "type": "query",
                            "args": {"graph": marker},
                        }
                    ],
                }
            )

        cancel_task = asyncio.create_task(
            service.execute_read_only(graph("cancel-graph", "cancel"))
        )
        keep_task = asyncio.create_task(
            service.execute_read_only(graph("keep-graph", "keep"))
        )
        await asyncio.gather(
            started["cancel"].wait(),
            started["keep"].wait(),
        )

        cancellation = service.cancel_execution("cancel-graph")
        cancelled_trace = await cancel_task
        replayed_cancelled_trace = await asyncio.wait_for(
            service.execute_read_only(
                graph("cancel-graph", "cancel")
            ),
            timeout=0.2,
        )
        release_keep.set()
        kept_trace = await keep_task

        self.assertTrue(cancellation.cancellation_requested)
        self.assertEqual(cancelled_trace.status, "cancelled")
        self.assertEqual(replayed_cancelled_trace.status, "cancelled")
        self.assertEqual(cancelled_trace.result_map()["lookup"].status, "cancelled")
        self.assertEqual(service.get_trace("cancel-graph").status, "cancelled")
        self.assertEqual(kept_trace.status, "success")

    async def test_cancel_before_execute_is_consumed_without_provider_call(
        self,
    ) -> None:
        calls = 0

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(
                registry,
                call=call,
            ),
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "early-cancel",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "lookup",
                        "tool": "remote.lookup",
                        "type": "query",
                    }
                ],
            }
        )

        dry_run = service.dry_run(graph)
        cancellation = service.cancel_execution(graph.graph_id)
        trace = await service.execute_read_only(graph)
        second_dry_run = service.dry_run(graph)
        replay = await service.execute_read_only(graph)
        different = graph.model_copy(
            update={"user_request": "different retained graph content"},
            deep=True,
        )

        self.assertTrue(cancellation.cancellation_requested)
        self.assertEqual(dry_run.status, "success")
        self.assertEqual(second_dry_run.status, "success")
        self.assertEqual(trace.status, "cancelled")
        self.assertEqual(replay.status, "cancelled")
        self.assertEqual(trace.events[0].type, "cancelled_before_start")
        self.assertEqual(calls, 0)
        self.assertEqual(service.get_trace(graph.graph_id).status, "cancelled")
        self.assertFalse(
            service.cancel_execution(graph.graph_id).cancellation_requested
        )
        with self.assertRaisesRegex(ValueError, "different graph content"):
            await service.execute_read_only(different)

    async def test_scheduler_status_reports_active_work(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            started.set()
            await release.wait()
            return {"structuredContent": {"ok": True}}

        registry = _registry()
        service = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )
        graph = TaskGraph.model_validate(
            {
                "graph_id": "diagnostics",
                "created_by": "user",
                "nodes": [
                    {"id": "lookup", "tool": "remote.lookup", "type": "query"}
                ],
            }
        )
        execution = asyncio.create_task(service.execute_read_only(graph))
        await started.wait()

        status = service.scheduler_status()

        self.assertTrue(status.parallel_enabled)
        self.assertEqual(status.active_count, 1)
        self.assertEqual(status.active_graph_ids, ["diagnostics"])
        release.set()
        await execution

    async def test_sequential_and_parallel_results_are_conformant(self) -> None:
        async def call(
            url: str,
            tool: str,
            args: dict[str, Any],
            timeout_s: float,
        ) -> dict[str, Any]:
            await asyncio.sleep(float(args.get("delay_s", 0)))
            return {"structuredContent": {"value": args["value"]}}

        registry = _registry()
        graph = TaskGraph.model_validate(
            {
                "graph_id": "conformance",
                "created_by": "user",
                "nodes": [
                    {
                        "id": "b",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"value": "b", "delay_s": 0.01},
                    },
                    {
                        "id": "a",
                        "tool": "remote.lookup",
                        "type": "query",
                        "args": {"value": "a", "delay_s": 0.02},
                    },
                ],
            }
        )
        sequential = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
        )
        parallel = TaskGraphService(
            registry,
            read_only_invoker=McpStreamableHttpInvoker(registry, call=call),
            enable_parallel_execution=True,
            max_concurrency=2,
        )

        sequential_trace = await sequential.execute_read_only(graph)
        parallel_trace = await parallel.execute_read_only(graph)

        def outcomes(trace):  # type: ignore[no-untyped-def]
            return [
                (result.node_id, result.status, result.output)
                for result in trace.node_results
            ]

        self.assertEqual(outcomes(sequential_trace), outcomes(parallel_trace))
        self.assertEqual(
            [event.data["sequence"] for event in parallel_trace.events],
            list(range(len(parallel_trace.events))),
        )
        self.assertEqual(
            [event.node_id for event in parallel_trace.events],
            ["a", "b"],
        )


if __name__ == "__main__":
    unittest.main()
