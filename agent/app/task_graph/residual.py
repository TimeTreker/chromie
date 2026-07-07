from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..capabilities.models import CapabilityRegistry
from .models import ExecutionTrace, NodeResult, TaskGraph, TaskNode

_SUCCESS_STATUSES = {"success", "skipped"}
_FAILURE_STATUSES = {
    "failed_retryable",
    "failed_fatal",
    "timeout",
    "blocked",
    "cancelled",
    "safety_interrupted",
}
_CURRENT_STATE_KEYS = (
    "current_physical_state",
    "current_state",
    "physical_state",
    "world_state",
    "robot_state",
    "soridormi_state",
    "state_summary",
    "observation_summary",
)
_RECOMMENDED_NEXT_ACTIONS_KEYS = (
    "recommended_next_actions",
    "next_actions",
    "recovery_actions",
    "suggested_next_actions",
)
_IRREVERSIBLE_EFFECT_KEYS = (
    "irreversible_effects",
    "committed_effects",
    "effects_committed",
    "physical_effects",
)
_FAILURE_CODE_KEYS = (
    "error_code",
    "reason_code",
    "failure_code",
    "status_code",
)


def attach_residual_replan_state(
    graph: TaskGraph,
    trace: ExecutionTrace,
    *,
    registry: CapabilityRegistry | None = None,
) -> ExecutionTrace:
    """Attach a residual-replan state to failed/aborted TaskGraph traces.

    The residual state is advisory planning context. It preserves what already
    happened and what Soridormi reported, but it does not authorize a retry or
    physical execution. Any residual plan produced later must re-enter the same
    validation, confirmation, and Soridormi safety gates as a fresh graph.
    """

    state = build_residual_replan_state(graph, trace, registry=registry)
    if state is None:
        trace.residual_replan = None
        return trace
    trace.residual_replan = state
    return trace


def build_residual_replan_state(
    graph: TaskGraph,
    trace: ExecutionTrace,
    *,
    registry: CapabilityRegistry | None = None,
) -> dict[str, Any] | None:
    if trace.status not in {"failed", "aborted"}:
        return None

    nodes = graph.node_map()
    results = trace.result_map()
    completed = [
        _node_summary(nodes[result.node_id], result)
        for result in trace.node_results
        if result.node_id in nodes and result.status in _SUCCESS_STATUSES
    ]
    failed_result = _first_failed_result(trace.node_results)
    blocked = [
        _node_summary(nodes[result.node_id], result)
        for result in trace.node_results
        if result.node_id in nodes and result.status == "blocked"
    ]
    pending_node_ids = [node.id for node in graph.nodes if node.id not in results]
    remaining_node_ids = _remaining_node_ids(
        graph,
        results,
        failed_result.node_id if failed_result is not None else None,
    )

    failed_step = (
        _node_summary(nodes[failed_result.node_id], failed_result)
        if failed_result is not None and failed_result.node_id in nodes
        else None
    )
    failure_code = _failure_code(failed_result) if failed_result is not None else None
    current_state = _collect_current_state(
        trace.node_results,
        preferred_node_id=failed_result.node_id if failed_result is not None else None,
    )
    recommended = _collect_recommended_next_actions(trace.node_results)
    irreversible = _collect_irreversible_effects(
        trace.node_results,
        nodes,
        registry=registry,
    )

    return {
        "status": "needs_residual_replan",
        "graph_id": graph.graph_id,
        "original_goal": _original_goal(graph),
        "trace_status": trace.status,
        "outcome_summary": trace.outcome_summary,
        "completed_steps": completed,
        "failed_step": failed_step,
        "failure_code": failure_code,
        "blocked_steps": blocked,
        "pending_steps": [_node_only_summary(nodes[node_id]) for node_id in pending_node_ids],
        "remaining_node_ids": remaining_node_ids,
        "current_physical_state": current_state,
        "irreversible_effects": irreversible,
        "recommended_next_actions": recommended,
        "replan_scope": {
            "mode": "residual_only",
            "exclude_completed_node_ids": [item["node_id"] for item in completed],
            "failed_node_id": failed_result.node_id if failed_result is not None else None,
            "remaining_node_ids": remaining_node_ids,
        },
        "safety_note": (
            "Residual context is advisory. Any follow-up plan must be newly "
            "validated and must re-enter confirmation, SkillRuntime, and "
            "Soridormi safety gates."
        ),
    }


def _first_failed_result(results: list[NodeResult]) -> NodeResult | None:
    for result in results:
        if result.status in _FAILURE_STATUSES and result.status != "blocked":
            return result
    for result in results:
        if result.status == "blocked":
            return result
    return None


def _remaining_node_ids(
    graph: TaskGraph,
    results: Mapping[str, NodeResult],
    failed_node_id: str | None,
) -> list[str]:
    incomplete = {
        node.id
        for node in graph.nodes
        if node.id not in results or results[node.id].status not in _SUCCESS_STATUSES
    }
    if failed_node_id:
        incomplete.add(failed_node_id)
        descendants = _descendants(graph, failed_node_id)
        incomplete.update(descendants)
    ordered = [node.id for node in graph.nodes if node.id in incomplete]
    return ordered


def _descendants(graph: TaskGraph, node_id: str) -> set[str]:
    children: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
    for node in graph.nodes:
        for dep in node.depends_on:
            children.setdefault(dep, set()).add(node.id)
    found: set[str] = set()
    stack = list(children.get(node_id, ()))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, ()))
    return found


def _node_only_summary(node: TaskNode) -> dict[str, Any]:
    return {
        "node_id": node.id,
        "tool": node.tool,
        "type": node.type,
        "depends_on": list(node.depends_on),
    }


def _node_summary(node: TaskNode, result: NodeResult) -> dict[str, Any]:
    summary = _node_only_summary(node)
    summary.update(
        {
            "status": result.status,
            "error": result.error,
            "attempts": result.attempts,
        }
    )
    output_summary = _output_summary(result.output)
    if output_summary:
        summary["output_summary"] = output_summary
    if result.blocked_by:
        summary["blocked_by"] = list(result.blocked_by)
    return summary


def _output_summary(output: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "summary",
        "message",
        "reason",
        "reason_code",
        "error_code",
        "completed",
        "plan_id",
    ):
        if key in output:
            summary[key] = output[key]
    return summary


def _failure_code(result: NodeResult | None) -> str | None:
    if result is None:
        return None
    for key in _FAILURE_CODE_KEYS:
        value = result.output.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if result.error:
        return result.error
    return result.status


def _collect_current_state(
    results: list[NodeResult],
    *,
    preferred_node_id: str | None = None,
) -> dict[str, Any] | None:
    collected: list[dict[str, Any]] = []
    for result in results:
        for key in _CURRENT_STATE_KEYS:
            value = result.output.get(key)
            if value is None:
                continue
            collected.append(
                {
                    "node_id": result.node_id,
                    "key": key,
                    "value": value,
                }
            )
    if not collected:
        return None
    if preferred_node_id is not None:
        for item in collected:
            if item["node_id"] == preferred_node_id:
                return {
                    "source_node_id": item["node_id"],
                    "key": item["key"],
                    "value": item["value"],
                }
    if len(collected) == 1:
        item = collected[0]
        return {
            "source_node_id": item["node_id"],
            "key": item["key"],
            "value": item["value"],
        }
    return {"observations": collected}


def _collect_recommended_next_actions(results: list[NodeResult]) -> list[Any]:
    actions: list[Any] = []
    for result in results:
        for key in _RECOMMENDED_NEXT_ACTIONS_KEYS:
            value = result.output.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                actions.extend(value)
            else:
                actions.append(value)
    return actions


def _collect_irreversible_effects(
    results: list[NodeResult],
    nodes: Mapping[str, TaskNode],
    *,
    registry: CapabilityRegistry | None,
) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for result in results:
        if result.status != "success" or result.node_id not in nodes:
            continue
        for key in _IRREVERSIBLE_EFFECT_KEYS:
            value = result.output.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    effects.append(
                        {
                            "node_id": result.node_id,
                            "source": key,
                            "effect": item,
                        }
                    )
            else:
                effects.append(
                    {
                        "node_id": result.node_id,
                        "source": key,
                        "effect": value,
                    }
                )
        if registry is None:
            continue
        node = nodes[result.node_id]
        try:
            capability = registry.get_tool(node.tool)
        except KeyError:
            continue
        if capability.execution.side_effect_free:
            continue
        effects.append(
            {
                "node_id": result.node_id,
                "tool": node.tool,
                "source": "capability_policy",
                "effects": list(capability.effects),
                "safety_class": capability.safety_class,
            }
        )
    return effects


def _original_goal(graph: TaskGraph) -> str:
    return (
        graph.user_request
        or graph.summary
        or graph.summary_zh
        or graph.graph_id
    )
