from __future__ import annotations

from app.capabilities.local import build_chromie_registry
from app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    ConfirmationPolicy,
    ExecutionPolicy,
    FailurePolicy,
    MonitoringPolicy,
    ToolCapability,
)
from app.task_graph.executor import DagDryRunExecutor
from app.task_graph.models import TaskGraph
from app.task_graph.service import TaskGraphService
from app.task_graph.validator import GraphValidator


def _soridormi_bundle() -> CapabilityBundle:
    return CapabilityBundle(
        source="soridormi-test",
        agents=[
            AgentManifest(
                agent_id="soridormi.robot",
                tools=[
                    ToolCapability(
                        name="soridormi.robot.get_status",
                        agent_id="soridormi.robot",
                        input_schema={"type": "object", "properties": {}},
                        output_schema={"type": "object", "properties": {"standing": {"type": "boolean"}}},
                        effects=["read_only"],
                        safety_class="safe_read",
                    )
                ],
            ),
            AgentManifest(
                agent_id="soridormi.motion",
                tools=[
                    ToolCapability(
                        name="soridormi.motion.create_plan",
                        agent_id="soridormi.motion",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "commands": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "vx": {"type": "number", "minimum": -0.2, "maximum": 0.2},
                                            "vy": {"type": "number", "minimum": -0.1, "maximum": 0.1},
                                            "yaw": {"type": "number", "minimum": -0.4, "maximum": 0.4},
                                            "duration_s": {"type": "number", "minimum": 0.05, "maximum": 5.0},
                                        },
                                        "required": ["vx", "vy", "yaw", "duration_s"],
                                    },
                                }
                            },
                            "required": ["commands"],
                        },
                        output_schema={"type": "object", "properties": {"plan_id": {"type": "string"}, "summary": {"type": "string"}}},
                        effects=["planning_only", "creates_plan"],
                        safety_class="planning_only",
                    ),
                    ToolCapability(
                        name="soridormi.motion.execute_plan",
                        agent_id="soridormi.motion",
                        input_schema={"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"]},
                        output_schema={"type": "object", "properties": {"completed": {"type": "boolean"}}},
                        effects=["physical_motion"],
                        safety_class="physical_motion",
                        confirmation=ConfirmationPolicy(required=True),
                        monitoring=MonitoringPolicy(requires_safety_monitor=True, recommended_monitor_tools=["soridormi.safety.monitor_motion"]),
                        execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="robot_motion", timeout_s=10.0, idempotent=False, side_effect_free=False),
                        default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                    ),
                    ToolCapability(
                        name="soridormi.motion.stop",
                        agent_id="soridormi.motion",
                        effects=["safety_control"],
                        safety_class="safety_critical",
                    ),
                ],
            ),
            AgentManifest(
                agent_id="soridormi.safety",
                tools=[
                    ToolCapability(
                        name="soridormi.safety.monitor_motion",
                        agent_id="soridormi.safety",
                        input_schema={"type": "object", "properties": {}},
                        effects=["read_only", "safety_control"],
                        safety_class="safety_critical",
                    )
                ],
            ),
        ],
    )


def _registry():
    return build_chromie_registry([_soridormi_bundle()])


def _motion_graph() -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": "walk_forward_dry_run",
            "summary_zh": "慢速向前走一点，然后停止。",
            "nodes": [
                {"id": "status", "tool": "soridormi.robot.get_status", "type": "query"},
                {
                    "id": "make_plan",
                    "tool": "soridormi.motion.create_plan",
                    "type": "plan",
                    "depends_on": ["status"],
                    "args": {"commands": [{"vx": 0.08, "vy": 0.0, "yaw": 0.0, "duration_s": 2.0}]},
                },
                {
                    "id": "confirm",
                    "tool": "chromie.ask_confirmation",
                    "type": "confirmation",
                    "depends_on": ["make_plan"],
                    "args": {"question": "要执行这个短距离移动吗？", "plan_summary": {"$ref": "make_plan.output.summary"}},
                },
                {
                    "id": "monitor",
                    "tool": "soridormi.safety.monitor_motion",
                    "type": "monitor",
                    "during": ["execute_motion"],
                },
                {
                    "id": "execute_motion",
                    "tool": "soridormi.motion.execute_plan",
                    "type": "action",
                    "depends_on": ["confirm"],
                    "args": {"plan_id": {"$ref": "make_plan.output.plan_id"}},
                    "on_failure": {"strategy": "goto", "target": "stop_after_failure"},
                },
                {"id": "stop_after_failure", "tool": "soridormi.motion.stop", "type": "safety"},
                {
                    "id": "report_done",
                    "tool": "chromie.report",
                    "type": "report",
                    "depends_on": ["execute_motion"],
                    "args": {"message": {"$ref": "execute_motion.output.summary"}},
                },
            ],
        }
    )


def test_validator_accepts_confirmed_and_monitored_physical_motion_graph() -> None:
    report = GraphValidator(_registry()).validate(_motion_graph())
    assert report.valid, report.errors


def test_validator_rejects_physical_motion_without_confirmation() -> None:
    graph = _motion_graph()
    for node in graph.nodes:
        if node.id == "execute_motion":
            node.depends_on = ["make_plan"]
    report = GraphValidator(_registry()).validate(graph)
    assert not report.valid
    assert any("confirmation" in error for error in report.errors)


def test_validator_rejects_unknown_tool() -> None:
    graph = TaskGraph.model_validate({"graph_id": "bad", "nodes": [{"id": "x", "tool": "missing.tool"}]})
    report = GraphValidator(_registry()).validate(graph)
    assert not report.valid
    assert any("unknown tool" in error for error in report.errors)


def test_dry_run_executor_resolves_refs_and_records_success_trace() -> None:
    trace = DagDryRunExecutor(_registry()).run(_motion_graph())
    assert trace.status == "success"
    outputs = trace.result_map()
    assert outputs["execute_motion"].output["completed"] is True
    assert "dryrun-make_plan" in outputs["execute_motion"].output["summary"]


def test_dry_run_executor_triggers_fallback_and_blocks_downstream_on_declined_confirmation() -> None:
    graph = _motion_graph()
    for node in graph.nodes:
        if node.id == "confirm":
            node.on_failure = FailurePolicy(strategy="goto", target="stop_after_failure")
    trace = DagDryRunExecutor(_registry(), auto_confirm=False).run(graph)
    results = trace.result_map()
    assert results["confirm"].status == "failed_fatal"
    assert results["stop_after_failure"].status == "success"
    assert results["execute_motion"].status == "blocked"
    assert any(event.type == "fallback_triggered" for event in trace.events)


def test_task_graph_service_validates_runs_and_retains_trace() -> None:
    service = TaskGraphService(build_chromie_registry())
    graph = TaskGraph.model_validate(
        {
            "graph_id": "service_report",
            "nodes": [
                {
                    "id": "report",
                    "tool": "chromie.report",
                    "type": "report",
                    "args": {"message": "TaskGraph service is reachable."},
                }
            ],
        }
    )

    validation = service.validate(graph)
    assert validation.valid

    trace = service.dry_run(graph)
    assert trace.status == "success"
    assert service.get_trace(graph.graph_id).result_map()["report"].output["reported"] is True


def test_task_graph_service_rejects_invalid_graph_without_storing_trace() -> None:
    service = TaskGraphService(build_chromie_registry())
    graph = TaskGraph.model_validate(
        {"graph_id": "invalid_service_graph", "nodes": [{"id": "bad", "tool": "missing.tool"}]}
    )

    try:
        service.dry_run(graph)
    except ValueError as exc:
        assert "unknown tool" in str(exc)
    else:
        raise AssertionError("invalid TaskGraph unexpectedly ran")

    assert service.get_trace(graph.graph_id) is None

from app.task_graph.executor import DagToolExecutor
from app.tool_invocation import FunctionToolInvoker, ToolCallOutcome


def test_tool_executor_invokes_registered_handlers_and_resolves_refs() -> None:
    invoker = FunctionToolInvoker()
    observed: dict[str, object] = {}
    invoker.register("soridormi.robot.get_status", lambda args: {"standing": True})
    invoker.register("soridormi.motion.create_plan", lambda args: {"plan_id": "real-plan-1", "summary": "plan ready"})
    invoker.register("chromie.ask_confirmation", lambda args: {"confirmed": True, "plan_summary": args["plan_summary"]})
    invoker.register("soridormi.safety.monitor_motion", lambda args: {"ok": True, "event": None})
    invoker.register("soridormi.motion.stop", lambda args: {"stopped": True})

    def execute(args):
        observed["execute_plan_id"] = args["plan_id"]
        return {"completed": True, "summary": f"executed {args['plan_id']}"}

    invoker.register("soridormi.motion.execute_plan", execute)
    invoker.register("chromie.report", lambda args: {"reported": True, "message": args["message"]})

    trace = DagToolExecutor(_registry(), invoker).run(_motion_graph())

    assert trace.status == "success"
    assert observed["execute_plan_id"] == "real-plan-1"
    assert trace.result_map()["report_done"].output["message"] == "executed real-plan-1"


def test_tool_executor_retries_retryable_failures() -> None:
    attempts = {"count": 0}
    invoker = FunctionToolInvoker()

    def flaky_listen(args):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return ToolCallOutcome.failed("microphone warmup", retryable=True)
        return {"text": "hello", "language": "en"}

    invoker.register("chromie.listen", flaky_listen)
    graph = TaskGraph.model_validate(
        {
            "graph_id": "retry_listen",
            "nodes": [
                {
                    "id": "listen",
                    "tool": "chromie.listen",
                    "type": "query",
                    "retry": {"max_attempts": 2, "backoff_s": 0.0},
                }
            ],
        }
    )

    trace = DagToolExecutor(build_chromie_registry(), invoker).run(graph)
    result = trace.result_map()["listen"]
    assert trace.status == "success"
    assert result.attempts == 2
    assert result.output["text"] == "hello"
