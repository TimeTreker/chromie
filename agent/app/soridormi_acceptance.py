from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from .capabilities.loader import build_configured_registry
from .capabilities.models import CapabilityRegistry
from .capabilities.probe import CapabilityProbeResult, probe_mcp_capabilities
from .task_graph.models import ExecutionTrace, TaskGraph
from .task_graph.service import (
    TaskGraphConfirmationGrantRequest,
    TaskGraphService,
)
from .tool_invocation import (
    AsyncToolInvoker,
    McpStreamableHttpInvoker,
    ToolInvocationContext,
)

CapabilityProbe = Callable[
    [CapabilityRegistry],
    Awaitable[list[CapabilityProbeResult]],
]


class SoridormiDryRunAcceptanceReport(BaseModel):
    planning: ExecutionTrace
    guarded_execution: ExecutionTrace
    failure_recovery: ExecutionTrace
    emergency_stop: dict[str, Any] | None = None
    status_after_emergency_stop: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)


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


def build_soridormi_guarded_graph(
    plan_id: str,
    *,
    graph_id: str = "soridormi-guarded-dry-run-acceptance",
) -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": graph_id,
            "created_by": "system",
            "requires_confirmation": True,
            "summary": "Execute a confirmed Soridormi dry-run plan with safety monitoring.",
            "nodes": [
                {
                    "id": "confirm",
                    "tool": "chromie.ask_confirmation",
                    "type": "confirmation",
                    "args": {"question": "Run the Soridormi dry-run acceptance plan?"},
                },
                {
                    "id": "monitor",
                    "tool": "soridormi.safety.monitor_motion",
                    "type": "monitor",
                    "during": ["execute"],
                },
                {
                    "id": "execute",
                    "tool": "soridormi.motion.execute_plan",
                    "type": "action",
                    "depends_on": ["confirm"],
                    "args": {"plan_id": plan_id},
                    "on_failure": {"strategy": "goto", "target": "stop"},
                    "on_timeout": {"strategy": "goto", "target": "stop"},
                    "on_event": {
                        "safety_event": {
                            "strategy": "goto",
                            "target": "emergency",
                        }
                    },
                },
                {
                    "id": "stop",
                    "tool": "soridormi.motion.stop",
                    "type": "safety",
                },
                {
                    "id": "emergency",
                    "tool": "soridormi.safety.emergency_stop",
                    "type": "safety",
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


async def run_soridormi_guarded_dry_run_acceptance(
    registry: CapabilityRegistry,
    *,
    plan_id: str,
    invoker: AsyncToolInvoker,
    exercise_emergency_stop: bool = False,
) -> tuple[ExecutionTrace, ExecutionTrace, dict[str, Any] | None, dict[str, Any] | None]:
    service = TaskGraphService(
        registry,
        guarded_invoker=invoker,
        allow_physical_motion=True,
    )

    graph = build_soridormi_guarded_graph(plan_id)
    grant = service.issue_confirmation_grant(
        TaskGraphConfirmationGrantRequest(
            graph=graph,
            confirmed_node_ids={"confirm"},
        )
    )
    guarded_trace = await service.execute_guarded(
        graph,
        grant.confirmation_grant,
    )
    if guarded_trace.status != "success":
        raise RuntimeError("Soridormi guarded dry-run acceptance graph failed")
    execution_output = guarded_trace.result_map()["execute"].output
    if execution_output.get("dry_run_only") is not True:
        raise RuntimeError("Soridormi acceptance expected dry_run_only=true")

    failure_graph = build_soridormi_guarded_graph(
        "soridormi-missing-acceptance-plan",
        graph_id="soridormi-stop-fallback-acceptance",
    )
    failure_grant = service.issue_confirmation_grant(
        TaskGraphConfirmationGrantRequest(
            graph=failure_graph,
            confirmed_node_ids={"confirm"},
        )
    )
    failure_trace = await service.execute_guarded(
        failure_graph,
        failure_grant.confirmation_grant,
    )
    failure_results = failure_trace.result_map()
    if (
        failure_trace.status != "failed"
        or failure_results["execute"].status == "success"
        or failure_results.get("stop") is None
        or failure_results["stop"].status != "success"
    ):
        raise RuntimeError("Soridormi stop fallback acceptance did not behave as expected")

    emergency_output: dict[str, Any] | None = None
    status_output: dict[str, Any] | None = None
    if exercise_emergency_stop:
        emergency = await invoker.invoke(
            "soridormi.safety.emergency_stop",
            {"reason": "Chromie M5 dry-run acceptance"},
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        if emergency.status != "success" or emergency.output.get("stopped") is not True:
            raise RuntimeError("Soridormi emergency-stop acceptance failed")
        emergency_output = emergency.output

        status = await invoker.invoke("soridormi.robot.get_status", {})
        if (
            status.status != "success"
            or status.output.get("emergency_stop") is not True
        ):
            raise RuntimeError("Soridormi status did not retain emergency-stop state")
        status_output = status.output

    return guarded_trace, failure_trace, emergency_output, status_output


async def _run(
    manifest: str,
    commands: list[dict[str, Any]],
    *,
    guarded_dry_run: bool,
    exercise_emergency_stop: bool,
) -> int:
    configured = build_configured_registry([manifest])
    invoker = McpStreamableHttpInvoker(configured.registry)
    planning_trace = await run_soridormi_planning_acceptance(
        configured.registry,
        commands=commands,
        invoker=invoker,
    )
    if not guarded_dry_run:
        print(
            json.dumps(
                planning_trace.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    plan_id = planning_trace.result_map()["plan"].output["plan_id"]
    guarded, failure, emergency, status = (
        await run_soridormi_guarded_dry_run_acceptance(
            configured.registry,
            plan_id=plan_id,
            invoker=invoker,
            exercise_emergency_stop=exercise_emergency_stop,
        )
    )
    notes = [
        "Guarded execution is Soridormi dry-run only; no motor commands were sent.",
        "Cancellation remains pending for a long-running runtime-backed MCP operation.",
    ]
    if exercise_emergency_stop:
        notes.append(
            "Emergency stop remains active in this Soridormi process; "
            "restart it before more motion acceptance."
        )
    report = SoridormiDryRunAcceptanceReport(
        planning=planning_trace,
        guarded_execution=guarded,
        failure_recovery=failure,
        emergency_stop=emergency,
        status_after_emergency_stop=status,
        notes=notes,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
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
    parser.add_argument(
        "--guarded-dry-run",
        action="store_true",
        help="Also verify confirmation, monitoring, dry-run execution, and stop fallback.",
    )
    parser.add_argument(
        "--exercise-emergency-stop",
        action="store_true",
        help="Set and verify Soridormi emergency stop. Restart Soridormi afterwards.",
    )
    args = parser.parse_args()
    commands = json.loads(args.commands_json)
    if not isinstance(commands, list):
        raise SystemExit("--commands-json must decode to a JSON array")
    if args.exercise_emergency_stop and not args.guarded_dry_run:
        raise SystemExit("--exercise-emergency-stop requires --guarded-dry-run")
    raise SystemExit(
        asyncio.run(
            _run(
                args.manifest,
                commands,
                guarded_dry_run=args.guarded_dry_run,
                exercise_emergency_stop=args.exercise_emergency_stop,
            )
        )
    )


if __name__ == "__main__":
    main()
