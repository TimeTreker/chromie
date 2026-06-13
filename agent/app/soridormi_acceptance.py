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
    ToolCallOutcome,
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


class SoridormiRuntimeCancellationAcceptanceReport(BaseModel):
    planning: ExecutionTrace
    cancellation: ExecutionTrace
    status_after_cancellation: dict[str, Any]
    notes: list[str] = Field(default_factory=list)


class SoridormiRuntimePreflightReport(BaseModel):
    endpoint: str
    backend: str
    mode: str
    emergency_stop: bool
    status: dict[str, Any]


class _ExecutePlanObserver:
    def __init__(self, invoker: AsyncToolInvoker, started: asyncio.Event) -> None:
        self._invoker = invoker
        self._started = started

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        if tool_name == "soridormi.motion.execute_plan":
            self._started.set()
        return await self._invoker.invoke(tool_name, args, context=context)


def require_soridormi_runtime_status(
    status: dict[str, Any],
    *,
    expected_backend: str = "runtime",
    expected_mode: str = "sim",
) -> tuple[str, str]:
    backend = str(status.get("backend", ""))
    mode = str(status.get("mode", ""))
    if backend != expected_backend:
        raise RuntimeError(
            f"Soridormi backend is {backend or 'missing'!r}; "
            f"expected {expected_backend!r}"
        )
    if mode != expected_mode:
        raise RuntimeError(
            f"Soridormi mode is {mode or 'missing'!r}; expected {expected_mode!r}"
        )
    if status.get("emergency_stop") is not False:
        raise RuntimeError(
            "Soridormi runtime preflight requires emergency_stop=false"
        )
    return backend, mode


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


async def run_soridormi_runtime_preflight(
    registry: CapabilityRegistry,
    *,
    invoker: AsyncToolInvoker,
    expected_backend: str = "runtime",
    expected_mode: str = "sim",
    probe: CapabilityProbe | None = None,
) -> SoridormiRuntimePreflightReport:
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
    if len(probe_results) != 1:
        raise RuntimeError(
            "Soridormi runtime preflight requires exactly one MCP endpoint"
        )

    outcome = await invoker.invoke("soridormi.robot.get_status", {})
    if outcome.status != "success":
        raise RuntimeError(
            "Soridormi runtime status failed: "
            + (outcome.error or outcome.status)
        )
    status = outcome.output
    backend, mode = require_soridormi_runtime_status(
        status,
        expected_backend=expected_backend,
        expected_mode=expected_mode,
    )
    return SoridormiRuntimePreflightReport(
        endpoint=probe_results[0].url,
        backend=backend,
        mode=mode,
        emergency_stop=bool(status["emergency_stop"]),
        status=status,
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


async def run_soridormi_runtime_cancellation_acceptance(
    registry: CapabilityRegistry,
    *,
    plan_id: str,
    invoker: AsyncToolInvoker,
    cancel_after_s: float = 1.0,
    start_timeout_s: float = 10.0,
) -> tuple[ExecutionTrace, dict[str, Any]]:
    if cancel_after_s < 0:
        raise ValueError("cancel_after_s must be non-negative")

    execution_started = asyncio.Event()
    previous_call_started = None
    observed_invoker: AsyncToolInvoker = invoker
    if isinstance(invoker, McpStreamableHttpInvoker):
        previous_call_started = invoker.call_started

        def call_started(tool_name: str) -> None:
            if previous_call_started is not None:
                previous_call_started(tool_name)
            if tool_name == "soridormi.motion.execute_plan":
                execution_started.set()

        invoker.call_started = call_started
    else:
        observed_invoker = _ExecutePlanObserver(invoker, execution_started)

    service = TaskGraphService(
        registry,
        guarded_invoker=observed_invoker,
        allow_physical_motion=True,
    )
    graph = build_soridormi_guarded_graph(
        plan_id,
        graph_id="soridormi-runtime-cancellation-acceptance",
    )
    grant = service.issue_confirmation_grant(
        TaskGraphConfirmationGrantRequest(
            graph=graph,
            confirmed_node_ids={"confirm"},
        )
    )
    execution = asyncio.create_task(
        service.execute_guarded(graph, grant.confirmation_grant)
    )
    try:
        await asyncio.wait_for(execution_started.wait(), timeout=start_timeout_s)
        await asyncio.sleep(cancel_after_s)
        try:
            await asyncio.wait_for(asyncio.shield(execution), timeout=0.01)
        except TimeoutError:
            pass
        else:
            raise RuntimeError(
                "Soridormi operation completed before cancellation was requested"
            )
        cancellation = service.cancel_execution(graph.graph_id)
        if not cancellation.cancellation_requested:
            raise RuntimeError(
                "Soridormi operation completed before cancellation was requested"
            )
        trace = await asyncio.wait_for(execution, timeout=start_timeout_s)
    except (Exception, asyncio.CancelledError):
        if not execution.done():
            service.cancel_execution(graph.graph_id)
            await asyncio.gather(execution, return_exceptions=True)
        raise
    finally:
        if isinstance(invoker, McpStreamableHttpInvoker):
            invoker.call_started = previous_call_started

    results = trace.result_map()
    if (
        trace.status != "cancelled"
        or results.get("execute") is None
        or results["execute"].status != "cancelled"
        or results.get("emergency") is None
        or results["emergency"].status != "success"
    ):
        raise RuntimeError(
            "Soridormi runtime cancellation did not complete the emergency fallback: "
            f"trace={trace.model_dump(mode='json')}"
        )

    status = await invoker.invoke("soridormi.robot.get_status", {})
    if status.status != "success" or status.output.get("emergency_stop") is not True:
        raise RuntimeError(
            "Soridormi runtime did not retain emergency-stop state after cancellation"
        )
    return trace, status.output


async def _run(
    manifest: str,
    commands: list[dict[str, Any]],
    *,
    runtime_preflight: bool,
    expected_backend: str,
    expected_mode: str,
    guarded_dry_run: bool,
    exercise_emergency_stop: bool,
    exercise_runtime_cancellation: bool,
    cancel_after_s: float,
) -> int:
    configured = build_configured_registry([manifest])
    invoker = McpStreamableHttpInvoker(configured.registry)
    if runtime_preflight:
        report = await run_soridormi_runtime_preflight(
            configured.registry,
            invoker=invoker,
            expected_backend=expected_backend,
            expected_mode=expected_mode,
        )
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    planning_trace = await run_soridormi_planning_acceptance(
        configured.registry,
        commands=commands,
        invoker=invoker,
    )
    if exercise_runtime_cancellation:
        planning_results = planning_trace.result_map()
        require_soridormi_runtime_status(
            planning_results["status"].output,
            expected_backend=expected_backend,
            expected_mode=expected_mode,
        )
        plan_id = planning_results["plan"].output["plan_id"]
        cancellation, status = (
            await run_soridormi_runtime_cancellation_acceptance(
                configured.registry,
                plan_id=plan_id,
                invoker=invoker,
                cancel_after_s=cancel_after_s,
            )
        )
        report = SoridormiRuntimeCancellationAcceptanceReport(
            planning=planning_trace,
            cancellation=cancellation,
            status_after_cancellation=status,
            notes=[
                "Cancellation reached an in-flight runtime operation and completed the emergency fallback.",
                "Emergency stop remains active; follow the Soridormi recovery procedure before more motion.",
            ],
        )
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

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
        help=(
            "Bounded planning commands. Defaults to a 0.05-second zero-motion plan, "
            "or a 5-second zero-motion plan for runtime cancellation."
        ),
    )
    execution_group = parser.add_mutually_exclusive_group()
    execution_group.add_argument(
        "--runtime-preflight",
        action="store_true",
        help=(
            "Probe the MCP contract and require a ready runtime-backed endpoint "
            "without creating or executing a plan."
        ),
    )
    execution_group.add_argument(
        "--guarded-dry-run",
        action="store_true",
        help="Also verify confirmation, monitoring, dry-run execution, and stop fallback.",
    )
    execution_group.add_argument(
        "--exercise-runtime-cancellation",
        action="store_true",
        help=(
            "Cancel an in-flight runtime-backed plan, verify emergency fallback, "
            "and leave Soridormi emergency-stopped."
        ),
    )
    parser.add_argument(
        "--exercise-emergency-stop",
        action="store_true",
        help="Set and verify Soridormi emergency stop. Restart Soridormi afterwards.",
    )
    parser.add_argument(
        "--expected-backend",
        default="runtime",
        help="Required get_status backend for --runtime-preflight.",
    )
    parser.add_argument(
        "--expected-mode",
        default="sim",
        help="Required get_status mode for --runtime-preflight.",
    )
    parser.add_argument(
        "--cancel-after-s",
        type=float,
        default=1.0,
        help="Seconds to wait after execute_plan is dispatched before cancelling it.",
    )
    args = parser.parse_args()
    commands_json = args.commands_json
    if commands_json is None:
        duration_s = 5.0 if args.exercise_runtime_cancellation else 0.05
        commands_json = (
            f'[{{"vx":0.0,"vy":0.0,"yaw":0.0,"duration_s":{duration_s}}}]'
        )
    commands = json.loads(commands_json)
    if not isinstance(commands, list):
        raise SystemExit("--commands-json must decode to a JSON array")
    if args.exercise_emergency_stop and not args.guarded_dry_run:
        raise SystemExit("--exercise-emergency-stop requires --guarded-dry-run")
    if args.cancel_after_s < 0:
        raise SystemExit("--cancel-after-s must be non-negative")
    raise SystemExit(
        asyncio.run(
            _run(
                args.manifest,
                commands,
                runtime_preflight=args.runtime_preflight,
                expected_backend=args.expected_backend,
                expected_mode=args.expected_mode,
                guarded_dry_run=args.guarded_dry_run,
                exercise_emergency_stop=args.exercise_emergency_stop,
                exercise_runtime_cancellation=args.exercise_runtime_cancellation,
                cancel_after_s=args.cancel_after_s,
            )
        )
    )


if __name__ == "__main__":
    main()
