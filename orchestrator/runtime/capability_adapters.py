from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from agent.app.task_graph.models import ExecutionTrace, TaskGraph
from agent.app.task_graph.residual import attach_residual_replan_state

from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    CapabilityResult,
)

from .capability_runtime import CapabilityDefinition, CapabilityExecutionContext




TaskGraphHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
TaskGraphCancelHandler = Callable[
    [str],
    dict[str, Any] | Awaitable[dict[str, Any]],
]


TASK_GRAPH_RESULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "graph_id": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["success", "failed", "aborted", "cancelled"],
        },
        "outcome_summary": {"type": "string"},
        "residual_replan": {
            "type": ["object", "null"],
            "properties": {
                "status": {"type": "string"},
                "graph_id": {"type": "string"},
                "original_goal": {"type": "string"},
                "trace_status": {"type": "string"},
                "outcome_summary": {"type": "string"},
                "failure_code": {"type": ["string", "null"]},
                "failed_step": {
                    "type": ["object", "null"],
                    "properties": {
                        "node_id": {"type": "string"},
                        "tool": {"type": "string"},
                        "type": {"type": "string"},
                        "status": {"type": "string"},
                        "error": {"type": ["string", "null"]},
                        "attempts": {"type": "integer"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "additionalProperties": False,
                },
                "remaining_node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_next_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "replan_scope": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string"},
                        "exclude_completed_node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "failed_node_id": {"type": ["string", "null"]},
                        "remaining_node_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "additionalProperties": False,
                },
                "safety_note": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "required": ["graph_id", "status", "outcome_summary"],
    "additionalProperties": False,
}


class TaskGraphCapabilityProvider:
    """Compatibility provider around the existing guarded TaskGraph executor."""

    provider_id = "chromie.task_graph"

    def __init__(
        self,
        handler: TaskGraphHandler,
        cancel_handler: TaskGraphCancelHandler | None = None,
    ) -> None:
        self._handler = handler
        self._cancel_handler = cancel_handler
        self.cancelled_request_ids: set[str] = set()

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        raw = self._handler(request.args["graph"])
        output = await raw if inspect.isawaitable(raw) else raw
        output = _with_residual_replan(request.args.get("graph"), output)
        status = _task_graph_skill_status(output)
        message = _task_graph_skill_message(output, status)
        model_safe_output = _task_graph_result_output(output)
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status=status,
            provider_id=self.provider_id,
            output=model_safe_output,
            reason_code=_task_graph_reason_code(output, status),
            message=message,
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        if self._cancel_handler is None:
            raise RuntimeError(
                "TaskGraph cancellation endpoint is not configured"
            )
        graph = request.args.get("graph")
        graph_id = (
            str(graph.get("graph_id") or "").strip()
            if isinstance(graph, dict)
            else ""
        )
        if not graph_id:
            raise RuntimeError(
                "TaskGraph cancellation requires the committed graph_id"
            )
        raw = self._cancel_handler(graph_id)
        receipt = await raw if inspect.isawaitable(raw) else raw
        if not isinstance(receipt, dict):
            raise RuntimeError(
                "TaskGraph cancellation endpoint returned an invalid receipt"
            )
        if (
            str(receipt.get("graph_id") or "").strip() != graph_id
            or receipt.get("cancellation_requested") is not True
        ):
            raise RuntimeError(
                "TaskGraph cancellation was not confirmed "
                f"for graph_id={graph_id!r}"
            )
        self.cancelled_request_ids.add(request.request_id)


def _with_residual_replan(graph_payload: Any, output: dict[str, Any]) -> dict[str, Any]:
    if output.get("residual_replan") is not None:
        return output
    if str(output.get("status") or "").strip().lower() not in {"failed", "aborted"}:
        return output
    if not isinstance(graph_payload, dict):
        return output
    try:
        graph = TaskGraph.model_validate(graph_payload)
        trace = ExecutionTrace.model_validate(output)
    except Exception:
        return output
    attach_residual_replan_state(graph, trace)
    return trace.model_dump(mode="json")


def _task_graph_result_output(output: dict[str, Any]) -> dict[str, Any]:
    """Project TaskGraph evidence into the committed model-safe result schema."""

    projected: dict[str, Any] = {
        "graph_id": str(output.get("graph_id") or ""),
        "status": str(output.get("status") or "").strip().lower(),
        "outcome_summary": str(output.get("outcome_summary") or ""),
    }
    residual = output.get("residual_replan")
    if not isinstance(residual, dict):
        return projected

    failed_step = residual.get("failed_step")
    projected_failed_step: dict[str, Any] | None = None
    if isinstance(failed_step, dict):
        projected_failed_step = {}
        for key in ("node_id", "tool", "type", "status"):
            if key in failed_step:
                projected_failed_step[key] = str(failed_step.get(key) or "")
        if "error" in failed_step:
            error = failed_step.get("error")
            projected_failed_step["error"] = None if error is None else str(error)
        if isinstance(failed_step.get("attempts"), int):
            projected_failed_step["attempts"] = failed_step["attempts"]
        depends_on = failed_step.get("depends_on")
        if isinstance(depends_on, list):
            projected_failed_step["depends_on"] = [
                str(item) for item in depends_on if str(item).strip()
            ]

    replan_scope = residual.get("replan_scope")
    projected_scope: dict[str, Any] = {}
    if isinstance(replan_scope, dict):
        if "mode" in replan_scope:
            projected_scope["mode"] = str(replan_scope.get("mode") or "")
        for key in ("exclude_completed_node_ids", "remaining_node_ids"):
            values = replan_scope.get(key)
            if isinstance(values, list):
                projected_scope[key] = [
                    str(item) for item in values if str(item).strip()
                ]
        if "failed_node_id" in replan_scope:
            failed_node_id = replan_scope.get("failed_node_id")
            projected_scope["failed_node_id"] = (
                None if failed_node_id is None else str(failed_node_id)
            )

    projected_residual: dict[str, Any] = {}
    for key in (
        "status",
        "graph_id",
        "original_goal",
        "trace_status",
        "outcome_summary",
        "safety_note",
    ):
        if key in residual:
            projected_residual[key] = str(residual.get(key) or "")
    if "failure_code" in residual:
        failure_code = residual.get("failure_code")
        projected_residual["failure_code"] = (
            None if failure_code is None else str(failure_code)
        )
    if projected_failed_step is not None:
        projected_residual["failed_step"] = projected_failed_step
    remaining = residual.get("remaining_node_ids")
    if isinstance(remaining, list):
        projected_residual["remaining_node_ids"] = [
            str(item) for item in remaining if str(item).strip()
        ]
    recommendations = residual.get("recommended_next_actions")
    if isinstance(recommendations, list):
        projected_residual["recommended_next_actions"] = [
            item for item in recommendations if isinstance(item, str) and item.strip()
        ]
    if projected_scope:
        projected_residual["replan_scope"] = projected_scope
    projected["residual_replan"] = projected_residual
    return projected


def _task_graph_skill_status(output: dict[str, Any]) -> str:
    """Map only explicit terminal TaskGraph evidence to CapabilityResult status."""

    graph_status = str(output.get("status") or "").strip().lower()
    if graph_status == "success":
        return "completed"
    if graph_status == "cancelled":
        return "cancelled"
    if graph_status in {"failed", "aborted"}:
        return "failed"
    # Missing, pending, running, or unknown provider states are not completion
    # evidence. The compatibility adapter must fail closed rather than turning
    # an incomplete receipt into a successful user-visible result.
    return "failed"


def _task_graph_skill_message(output: dict[str, Any], status: str) -> str:
    if status == "completed":
        return ""
    summary = str(output.get("outcome_summary") or "").strip()
    if summary:
        return summary
    graph_status = str(output.get("status") or "unknown").strip() or "unknown"
    return f"TaskGraph ended with status={graph_status}"


def _task_graph_reason_code(
    output: dict[str, Any],
    status: str,
) -> str | None:
    if status == "completed":
        return None
    if status == "cancelled":
        return "task_graph_cancelled"
    graph_status = str(output.get("status") or "").strip().lower()
    if not graph_status:
        return "task_graph_missing_terminal_status"
    if graph_status in {"pending", "running"}:
        return "task_graph_non_terminal_result"
    if graph_status not in {"failed", "aborted"}:
        return "task_graph_invalid_terminal_status"
    return "task_graph_failed"


def task_graph_capability_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.task_graph.execute",
        version="1.0.0",
        provider_id=TaskGraphCapabilityProvider.provider_id,
        description="Execute a validated legacy Chromie TaskGraph.",
        input_schema={
            "type": "object",
            "properties": {
                "graph": {"type": "object"},
            },
            "required": ["graph"],
            "additionalProperties": False,
        },
        output_schema=TASK_GRAPH_RESULT_OUTPUT_SCHEMA,
        timeout_ms=120000,
        interruptible=True,
        can_run_parallel=False,
        cancellation_domains=("embodied_motion",),
        metadata={
            "effects": ["physical_motion"],
            "safety_class": "physical_motion",
            "cancellation_granularity": "request",
        },
    )
