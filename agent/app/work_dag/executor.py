from __future__ import annotations

import time
from typing import Any

from ..capabilities.models import CapabilityRegistry, FailurePolicy
from ..tool_invocation import ToolCallOutcome, ToolInvoker

from .models import ExecutionEvent, ExecutionTrace, NodeResult, WorkDAG, WorkNode
from .refs import resolve_refs
from .validator import WorkDAGValidator

_TERMINAL_FAILURES = {"failed_retryable", "failed_fatal", "timeout", "cancelled", "safety_interrupted"}
_NON_SUCCESS = _TERMINAL_FAILURES | {"blocked"}


class DAGDryRunEngine:
    """Run a WorkDAG without calling real MCP tools or moving hardware.

    The dry-run executor validates the dag, resolves `$ref` arguments, records
    a deterministic trace, and simulates common Chromie/Soridormi capability outputs.
    It is intended for Planner/DAG development before real MCP transports exist.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        auto_confirm: bool = True,
        tool_invoker: ToolInvoker | None = None,
    ) -> None:
        self.registry = registry
        self.auto_confirm = auto_confirm
        self.tool_invoker = tool_invoker

    def run(self, dag: WorkDAG, *, validate: bool = True) -> ExecutionTrace:
        if validate:
            report = WorkDAGValidator(self.registry).validate(dag)
            report.raise_for_errors()

        trace = ExecutionTrace(dag_id=dag.dag_id, dag_revision=dag.revision, status="running", summary=dag.summary)
        nodes = dag.node_map()
        pending: set[str] = set(nodes)
        results: dict[str, NodeResult] = {}
        activated_fallbacks: set[str] = set()
        aborted = False

        while pending and not aborted:
            self._mark_blocked_nodes(pending, nodes, results, trace)
            ready = self._ready_nodes(pending, nodes, results, activated_fallbacks)
            if not ready:
                # Any remaining nodes are unreachable because dependencies failed or no fallback activated them.
                for node_id in sorted(pending):
                    node = nodes[node_id]
                    blocked_by = [dep for dep in node.depends_on if dep not in results or results[dep].status != "success"]
                    result = NodeResult(node_id=node.id, capability_id=node.capability_id, status="blocked", blocked_by=blocked_by)
                    self._record_result(trace, results, result)
                pending.clear()
                break

            # Keep execution deterministic. Capability parallelism is represented in the trace,
            # but dry-run executes one ready node at a time.
            for node in sorted(ready, key=lambda n: n.id):
                if node.id not in pending:
                    continue
                pending.remove(node.id)
                result = self._execute_node(node, results)
                self._record_result(trace, results, result)
                if result.status == "success" or result.status == "skipped":
                    continue
                policy = node.on_failure or self._capability_default_failure_policy(node.capability_id)
                fallback_target = self._apply_failure_policy(node, result, policy, trace)
                if fallback_target:
                    activated_fallbacks.add(fallback_target)
                if policy.strategy in {"abort_task", "emergency_stop", "stop_and_report"} and not fallback_target:
                    aborted = True
                    break

        if aborted:
            for node_id in sorted(pending):
                node = nodes[node_id]
                self._record_result(trace, results, NodeResult(node_id=node.id, capability_id=node.capability_id, status="cancelled"))
            trace.status = "aborted"
            trace.events.append(ExecutionEvent(type="dag_aborted", message="Dry-run work DAG aborted by failure policy."))
        elif any(result.status in _NON_SUCCESS for result in results.values()):
            trace.status = "failed"
        else:
            trace.status = "success"
        return trace

    def _ready_nodes(
        self,
        pending: set[str],
        nodes: dict[str, WorkNode],
        results: dict[str, NodeResult],
        activated_fallbacks: set[str],
    ) -> list[WorkNode]:
        ready: list[WorkNode] = []
        for node_id in pending:
            node = nodes[node_id]
            if node_id in activated_fallbacks:
                ready.append(node)
                continue
            if node.role == "monitor":
                # Dry-run monitor sidecars do not block the main dag.
                ready.append(node)
                continue
            if all(dep in results and results[dep].status == "success" for dep in node.depends_on):
                ready.append(node)
        return ready

    def _mark_blocked_nodes(
        self,
        pending: set[str],
        nodes: dict[str, WorkNode],
        results: dict[str, NodeResult],
        trace: ExecutionTrace,
    ) -> None:
        changed = True
        while changed:
            changed = False
            for node_id in sorted(list(pending)):
                node = nodes[node_id]
                blocked_by = [dep for dep in node.depends_on if dep in results and results[dep].status in _NON_SUCCESS]
                if blocked_by:
                    pending.remove(node_id)
                    result = NodeResult(node_id=node.id, capability_id=node.capability_id, status="blocked", blocked_by=blocked_by)
                    self._record_result(trace, results, result)
                    changed = True

    def _execute_node(self, node: WorkNode, results: dict[str, NodeResult]) -> NodeResult:
        started = time.monotonic()
        try:
            args = resolve_refs(node.args, results)
        except KeyError as exc:
            return NodeResult(
                node_id=node.id,
                capability_id=node.capability_id,
                status="failed_fatal",
                error=str(exc),
                started_at=started,
                finished_at=time.monotonic(),
            )

        max_attempts = node.retry.max_attempts if node.retry else 1
        last_outcome: ToolCallOutcome | None = None
        for attempt in range(1, max_attempts + 1):
            outcome = self._invoke_or_simulate(node, args)
            last_outcome = outcome
            if outcome.status == "success":
                return NodeResult(
                    node_id=node.id,
                    capability_id=node.capability_id,
                    status="success",
                    output=outcome.output,
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )
            if outcome.status != "failed_retryable" or attempt >= max_attempts:
                return NodeResult(
                    node_id=node.id,
                    capability_id=node.capability_id,
                    status=outcome.status,
                    output=outcome.output,
                    error=outcome.error,
                    attempts=attempt,
                    started_at=started,
                    finished_at=time.monotonic(),
                )

        # The retry loop always executes at least once. Keep this invariant
        # explicit because Python -O removes assert statements.
        if last_outcome is None:
            raise RuntimeError(
                "work DAG retry loop completed without an invocation outcome"
            )
        return NodeResult(
            node_id=node.id,
            capability_id=node.capability_id,
            status=last_outcome.status,
            output=last_outcome.output,
            error=last_outcome.error,
            attempts=max_attempts,
            started_at=started,
            finished_at=time.monotonic(),
        )

    def _invoke_or_simulate(self, node: WorkNode, args: dict[str, Any]) -> ToolCallOutcome:
        if node.capability_id == "chromie.ask_confirmation" and not self.auto_confirm:
            return ToolCallOutcome.failed(
                "confirmation_declined",
                output={"confirmed": False, "user_text": "dry-run declined"},
            )
        if self.tool_invoker is not None:
            return self.tool_invoker.invoke(node.capability_id, args)
        return ToolCallOutcome.success(self._simulate_tool_output(node, args))

    def _simulate_tool_output(self, node: WorkNode, args: dict[str, Any]) -> dict[str, Any]:
        capability = node.capability_id
        if capability == "chromie.ask_confirmation":
            return {"confirmed": True, "user_text": "dry-run confirmed"}
        if capability == "chromie.speak":
            return {"spoken": True, "text": args.get("text", "")}
        if capability == "chromie.report":
            return {"reported": True, "message": args.get("message", "")}
        if capability == "chromie.listen":
            return {"text": "", "language": "unknown"}
        if capability == "chromie.task.get_trace":
            return {"events": []}
        if capability == "soridormi.robot.get_status":
            return {"mode": "sim", "backend": "dry_run", "standing": True, "fallen": False, "emergency_stop": False}
        if capability == "soridormi.robot.get_mode":
            return {"mode": "sim"}
        if capability == "soridormi.robot.get_battery":
            return {"percent": None, "critical": False}
        if capability == "soridormi.motion.create_plan":
            commands = args.get("commands", [])
            duration = sum(float(command.get("duration_s", 0.0)) for command in commands if isinstance(command, dict))
            return {
                "plan_id": f"dryrun-{node.id}",
                "summary": f"Dry-run Soridormi motion plan with {len(commands)} command(s).",
                "estimated_duration_s": duration,
                "requires_confirmation": True,
            }
        if capability == "soridormi.skill.create_plan":
            return {
                "plan_id": f"dryrun-{node.id}",
                "capability_id": args.get("capability_id", ""),
                "summary": f"Dry-run Soridormi named-skill plan for {args.get('capability_id', '<missing>')}.",
                "requires_confirmation": True,
            }
        if capability == "soridormi.motion.execute_plan":
            return {"completed": True, "summary": f"Dry-run executed plan {args.get('plan_id', '<missing>')}"}
        if capability == "soridormi.skill.execute_plan":
            return {
                "completed": True,
                "no_motion": True,
                "summary": f"Dry-run executed named-skill plan {args.get('plan_id', '<missing>')}",
            }
        if capability == "soridormi.motion.stop":
            return {"stopped": True}
        if capability == "soridormi.motion.cancel":
            return {"cancelled": True}
        if capability == "soridormi.safety.monitor_motion":
            return {"ok": True, "event": None, "during": args.get("during_node_id") or node.during}
        if capability == "soridormi.safety.emergency_stop":
            return {"stopped": True, "emergency": True}
        try:
            definition = self.registry.get_tool(capability)
        except KeyError:
            return {"dry_run": True, "capability_id": capability}
        return {"dry_run": True, "capability_id": capability, "effects": definition.effects}

    def _capability_default_failure_policy(self, capability_id: str) -> FailurePolicy:
        try:
            return self.registry.get_tool(capability_id).default_failure_policy
        except KeyError:
            return FailurePolicy(strategy="abort_task")

    def _apply_failure_policy(
        self,
        node: WorkNode,
        result: NodeResult,
        policy: FailurePolicy,
        trace: ExecutionTrace,
    ) -> str | None:
        trace.events.append(
            ExecutionEvent(
                type="failure_policy",
                node_id=node.id,
                capability_id=node.capability_id,
                message=f"Applying {policy.strategy} after {result.status}.",
                data={"target": policy.target},
            )
        )
        if policy.strategy == "goto" and policy.target:
            trace.events.append(
                ExecutionEvent(type="fallback_triggered", node_id=node.id, capability_id=node.capability_id, data={"target": policy.target})
            )
            return policy.target
        if policy.strategy == "continue_with_default":
            result.status = "success"
            result.output = policy.default_output or {}
            result.error = None
            return None
        if policy.strategy == "skip":
            result.status = "skipped"
            result.error = None
            return None
        return None

    def _record_result(self, trace: ExecutionTrace, results: dict[str, NodeResult], result: NodeResult) -> None:
        results[result.node_id] = result
        trace.node_results.append(result)
        trace.events.append(
            ExecutionEvent(type="node_result", node_id=result.node_id, capability_id=result.capability_id, message=result.status, data={"error": result.error})
        )


class DAGToolEngine(DAGDryRunEngine):
    """Execute a WorkDAG through a provided ToolInvoker.

    This is still transport-neutral: the invoker may be a local Python registry,
    a test double, or a future MCP client. Safety validation remains the same as
    DAGDryRunEngine.
    """

    def __init__(self, registry: CapabilityRegistry, tool_invoker: ToolInvoker, *, auto_confirm: bool = True) -> None:
        super().__init__(registry, auto_confirm=auto_confirm, tool_invoker=tool_invoker)
