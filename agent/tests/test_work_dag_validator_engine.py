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
from app.work_dag.executor import DAGDryRunEngine
from app.work_dag.models import WorkDAG
from app.work_dag.service import DAGEngineService
from app.work_dag.validator import WorkDAGValidator


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
                agent_id="soridormi.skill",
                tools=[
                    ToolCapability(
                        name="soridormi.skill.create_plan",
                        agent_id="soridormi.skill",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "capability_id": {"type": "string", "enum": ["walk_forward"]},
                                "parameters": {"type": "object"},
                            },
                            "required": ["capability_id"],
                        },
                        output_schema={"type": "object", "properties": {"plan_id": {"type": "string"}, "summary": {"type": "string"}}},
                        effects=["planning_only", "creates_plan"],
                        safety_class="planning_only",
                    ),
                    ToolCapability(
                        name="soridormi.skill.execute_plan",
                        agent_id="soridormi.skill",
                        input_schema={"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"]},
                        output_schema={"type": "object", "properties": {"completed": {"type": "boolean"}}},
                        effects=["physical_motion"],
                        safety_class="physical_motion",
                        confirmation=ConfirmationPolicy(required=True),
                        monitoring=MonitoringPolicy(requires_safety_monitor=True, recommended_monitor_tools=["soridormi.safety.monitor_motion"]),
                        execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="robot_motion", timeout_s=10.0, idempotent=False, side_effect_free=False),
                        default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                    ),
                ],
            ),
            AgentManifest(
                agent_id="soridormi.motion",
                tools=[
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


def _motion_graph() -> WorkDAG:
    return WorkDAG.model_validate(
        {
            "dag_id": "walk_forward_dry_run",
            "summary": "慢速向前走一点，然后停止。",
            "nodes": [
                {"id": "status", "capability_id": "soridormi.robot.get_status", "role": "activity"},
                {
                    "id": "make_plan",
                    "capability_id": "soridormi.skill.create_plan",
                    "role": "activity",
                    "depends_on": ["status"],
                    "args": {
                        "capability_id": "walk_forward",
                        "parameters": {"duration_s": 2.0, "speed": "slow"},
                    },
                },
                {
                    "id": "confirm",
                    "capability_id": "chromie.ask_confirmation",
                    "role": "confirmation",
                    "depends_on": ["make_plan"],
                    "args": {"question": "要执行这个短距离移动吗？", "plan_summary": {"$ref": "make_plan.output.summary"}},
                },
                {
                    "id": "monitor",
                    "capability_id": "soridormi.safety.monitor_motion",
                    "role": "monitor",
                    "during": ["execute_motion"],
                },
                {
                    "id": "execute_motion",
                    "capability_id": "soridormi.skill.execute_plan",
                    "role": "activity",
                    "depends_on": ["confirm"],
                    "args": {"plan_id": {"$ref": "make_plan.output.plan_id"}},
                    "on_failure": {"strategy": "goto", "target": "stop_after_failure"},
                },
                {"id": "stop_after_failure", "capability_id": "soridormi.motion.stop", "role": "safety"},
                {
                    "id": "report_done",
                    "capability_id": "chromie.report",
                    "role": "report",
                    "depends_on": ["execute_motion"],
                    "args": {"message": {"$ref": "execute_motion.output.summary"}},
                },
            ],
        }
    )


def test_validator_accepts_confirmed_and_monitored_physical_motion_graph() -> None:
    report = WorkDAGValidator(_registry()).validate(_motion_graph())
    assert report.valid, report.errors


def test_validator_rejects_physical_motion_without_confirmation() -> None:
    graph = _motion_graph()
    for node in graph.nodes:
        if node.id == "execute_motion":
            node.depends_on = ["make_plan"]
    report = WorkDAGValidator(_registry()).validate(graph)
    assert not report.valid
    assert any("confirmation" in error for error in report.errors)


def test_validator_rejects_unknown_tool() -> None:
    graph = WorkDAG.model_validate({"dag_id": "bad", "nodes": [{"id": "x", "capability_id": "missing.tool"}]})
    report = WorkDAGValidator(_registry()).validate(graph)
    assert not report.valid
    assert any("unknown capability" in error for error in report.errors)


def test_dry_run_executor_resolves_refs_and_records_success_trace() -> None:
    trace = DAGDryRunEngine(_registry()).run(_motion_graph())
    assert trace.status == "success"
    outputs = trace.result_map()
    assert outputs["execute_motion"].output["completed"] is True
    assert "dryrun-make_plan" in outputs["execute_motion"].output["summary"]


def test_dry_run_executor_triggers_fallback_and_blocks_downstream_on_declined_confirmation() -> None:
    graph = _motion_graph()
    for node in graph.nodes:
        if node.id == "confirm":
            node.on_failure = FailurePolicy(strategy="goto", target="stop_after_failure")
    trace = DAGDryRunEngine(_registry(), auto_confirm=False).run(graph)
    results = trace.result_map()
    assert results["confirm"].status == "failed_fatal"
    assert results["stop_after_failure"].status == "success"
    assert results["execute_motion"].status == "blocked"
    assert any(event.type == "fallback_triggered" for event in trace.events)


def test_work_dag_service_validates_runs_and_retains_trace() -> None:
    service = DAGEngineService(build_chromie_registry())
    graph = WorkDAG.model_validate(
        {
            "dag_id": "service_report",
            "nodes": [
                {
                    "id": "report",
                    "capability_id": "chromie.report",
                    "role": "report",
                    "args": {"message": "WorkDAG service is reachable."},
                }
            ],
        }
    )

    validation = service.validate(graph)
    assert validation.valid

    trace = service.dry_run(graph)
    assert trace.status == "success"
    assert service.get_trace(graph.dag_id).result_map()["report"].output["reported"] is True


def test_work_dag_service_rejects_invalid_graph_without_storing_trace() -> None:
    service = DAGEngineService(build_chromie_registry())
    graph = WorkDAG.model_validate(
        {"dag_id": "invalid_service_graph", "nodes": [{"id": "bad", "capability_id": "missing.tool"}]}
    )

    try:
        service.dry_run(graph)
    except ValueError as exc:
        assert "unknown capability" in str(exc)
    else:
        raise AssertionError("invalid WorkDAG unexpectedly ran")

    assert service.get_trace(graph.dag_id) is None

from app.work_dag.executor import DAGToolEngine
from app.tool_invocation import FunctionToolInvoker, ToolCallOutcome


def test_tool_executor_invokes_registered_handlers_and_resolves_refs() -> None:
    invoker = FunctionToolInvoker()
    observed: dict[str, object] = {}
    invoker.register("soridormi.robot.get_status", lambda args: {"standing": True})
    invoker.register("soridormi.skill.create_plan", lambda args: {"plan_id": "real-plan-1", "summary": "plan ready"})
    invoker.register("chromie.ask_confirmation", lambda args: {"confirmed": True, "plan_summary": args["plan_summary"]})
    invoker.register("soridormi.safety.monitor_motion", lambda args: {"ok": True, "event": None})
    invoker.register("soridormi.motion.stop", lambda args: {"stopped": True})

    def execute(args):
        observed["execute_plan_id"] = args["plan_id"]
        return {"completed": True, "summary": f"executed {args['plan_id']}"}

    invoker.register("soridormi.skill.execute_plan", execute)
    invoker.register("chromie.report", lambda args: {"reported": True, "message": args["message"]})

    trace = DAGToolEngine(_registry(), invoker).run(_motion_graph())

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
    graph = WorkDAG.model_validate(
        {
            "dag_id": "retry_listen",
            "nodes": [
                {
                    "id": "listen",
                    "capability_id": "chromie.listen",
                    "role": "activity",
                    "retry": {"max_attempts": 2, "backoff_s": 0.0},
                }
            ],
        }
    )

    trace = DAGToolEngine(build_chromie_registry(), invoker).run(graph)
    result = trace.result_map()["listen"]
    assert trace.status == "success"
    assert result.attempts == 2
    assert result.output["text"] == "hello"
