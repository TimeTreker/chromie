from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from .capabilities.loader import build_configured_registry
from .capabilities.models import CapabilityRegistry
from .capabilities.probe import CapabilityProbeResult, probe_mcp_capabilities
from .task_graph.models import ExecutionTrace, TaskGraph
from .task_graph.service import TaskGraphService
from .tool_invocation import AsyncToolInvoker, McpStreamableHttpInvoker

CapabilityProbe = Callable[
    [CapabilityRegistry],
    Awaitable[list[CapabilityProbeResult]],
]


def build_soridormi_planning_graph(
    commands: list[dict[str, Any]],
) -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": "soridormi-planning-acceptance",
            "created_by": "system",
            "summary": "Read Soridormi status and create a zero-motion plan.",
            "nodes": [
                {
                    "id": "status",
                    "tool": "soridormi.robot.get_status",
                    "type": "query",
                },
                {
                    "id": "plan",
                    "tool": "soridormi.motion.create_plan",
                    "type": "plan",
                    "depends_on": ["status"],
                    "args": {"commands": commands},
                },
            ],
        }
    )


async def run_soridormi_planning_acceptance(
    registry: CapabilityRegistry,
    *,
    commands: list[dict[str, Any]],
    invoker: AsyncToolInvoker,
    probe: CapabilityProbe | None = None,
) -> ExecutionTrace:
    probe_results = await (
        probe(registry)
        if probe is not None
        else probe_mcp_capabilities(registry)
    )
    failed_endpoints = [result.url for result in probe_results if not result.ok]
    if failed_endpoints:
        raise ValueError(
            "Soridormi MCP capability probe failed for: "
            + ", ".join(failed_endpoints)
        )

    graph = build_soridormi_planning_graph(commands)
    trace = await TaskGraphService(
        registry,
        planning_invoker=invoker,
    ).execute_planning(graph)
    if trace.status != "success":
        raise RuntimeError("Soridormi planning acceptance graph failed")

    results = trace.result_map()
    plan_output = results["plan"].output
    missing = {"plan_id", "summary"} - plan_output.keys()
    if missing:
        raise RuntimeError(
            f"Soridormi planning output is missing required fields: {sorted(missing)}"
        )
    return trace


async def _run(manifest: str, commands: list[dict[str, Any]]) -> int:
    configured = build_configured_registry([manifest])
    trace = await run_soridormi_planning_acceptance(
        configured.registry,
        commands=commands,
        invoker=McpStreamableHttpInvoker(configured.registry),
    )
    print(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Soridormi and run safe status/planning acceptance over MCP."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--commands-json",
        default='[{"vx":0.0,"vy":0.0,"yaw":0.0,"duration_s":0.05}]',
        help="Bounded planning commands. The default requests no physical movement.",
    )
    args = parser.parse_args()
    commands = json.loads(args.commands_json)
    if not isinstance(commands, list):
        raise SystemExit("--commands-json must decode to a JSON array")
    raise SystemExit(asyncio.run(_run(args.manifest, commands)))


if __name__ == "__main__":
    main()
