from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from agent.app.work_dag.models import WorkDAG
from shared.chromie_contracts.interaction import CapabilityRequest, CapabilityResult

from .capability_runtime import CapabilityDefinition, CapabilityExecutionContext


WorkDAGHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
WorkDAGCancelHandler = Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]]


WORK_DAG_RESULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dag_id": {"type": "string"},
        "dag_revision": {"type": "integer", "minimum": 1},
        "goal_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "status": {
            "type": "string",
            "enum": ["success", "failed", "aborted", "cancelled"],
        },
        "node_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "capability_id": {"type": ["string", "null"]},
                    "status": {"type": "string"},
                    "error": {"type": ["string", "null"]},
                    "attempts": {"type": "integer"},
                    "inherited_from_revision": {"type": ["integer", "null"], "minimum": 1},
                    "blocked_by": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_goal_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason_code": {"type": ["string", "null"]},
                    "blocked_subsystems": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "provider_reported_next_actions": {"type": "array"},
                },
                "required": [
                    "node_id",
                    "status",
                    "attempts",
                    "blocked_by",
                    "source_goal_ids",
                ],
                "additionalProperties": False,
            },
        },
        "pending_node_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "dag_id",
        "dag_revision",
        "goal_ids",
        "status",
        "node_results",
        "pending_node_ids",
    ],
    "additionalProperties": False,
}


class WorkDAGCapabilityProvider:
    """Capability adapter for the deterministic DAGEngine.

    WorkDAG is authored before this adapter runs.  The adapter may project
    execution facts, but it must never choose replacement Work or manufacture
    a recovery recommendation.
    """

    provider_id = "chromie.dag_engine"

    def __init__(
        self,
        handler: WorkDAGHandler,
        cancel_handler: WorkDAGCancelHandler | None = None,
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
        del context
        dag_payload = request.args["dag"]
        dag = WorkDAG.model_validate(dag_payload)
        if dag.authored_by != "planner":
            raise ValueError(
                "chromie.work_dag.execute accepts only Planner-authored WorkDAG values"
            )
        raw = self._handler(dag.model_dump(mode="json"))
        output = await raw if inspect.isawaitable(raw) else raw
        status = _work_dag_result_status(output)
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status=status,
            provider_id=self.provider_id,
            output=_work_dag_result_output(dag_payload, output),
            reason_code=_work_dag_reason_code(output, status),
            message="",
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        del definition, context
        if self._cancel_handler is None:
            raise RuntimeError("DAGEngine cancellation endpoint is not configured")
        dag = request.args.get("dag")
        dag_id = str(dag.get("dag_id") or "").strip() if isinstance(dag, dict) else ""
        if not dag_id:
            raise RuntimeError("DAGEngine cancellation requires the committed dag_id")
        raw = self._cancel_handler(dag_id)
        receipt = await raw if inspect.isawaitable(raw) else raw
        if not isinstance(receipt, dict):
            raise RuntimeError("DAGEngine cancellation endpoint returned an invalid receipt")
        if (
            str(receipt.get("dag_id") or "").strip() != dag_id
            or receipt.get("cancellation_requested") is not True
        ):
            raise RuntimeError(
                "DAGEngine cancellation was not confirmed " f"for dag_id={dag_id!r}"
            )
        self.cancelled_request_ids.add(request.request_id)


def _work_dag_result_output(
    dag_payload: Any,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Project only execution facts into Planner-visible Evidence."""

    dag_id = str(output.get("dag_id") or "").strip()
    known_node_ids: list[str] = []
    goal_ids: list[str] = []
    node_goal_ids: dict[str, list[str]] = {}
    if isinstance(dag_payload, dict):
        dag_id = dag_id or str(dag_payload.get("dag_id") or "").strip()
        goal_ids = [
            str(value).strip()
            for value in (dag_payload.get("goal_ids") or [])
            if str(value).strip()
        ]
        raw_nodes = dag_payload.get("nodes")
        if isinstance(raw_nodes, list):
            for item in raw_nodes:
                if not isinstance(item, dict):
                    continue
                node_id = str(item.get("id") or "").strip()
                if not node_id:
                    continue
                known_node_ids.append(node_id)
                node_goal_ids[node_id] = [
                    str(value).strip()
                    for value in (item.get("source_goal_ids") or [])
                    if str(value).strip()
                ]

    projected_results: list[dict[str, Any]] = []
    completed_ids: set[str] = set()
    raw_results = output.get("node_results")
    if isinstance(raw_results, list):
        for item in raw_results[:64]:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            if not node_id:
                continue
            status = str(item.get("status") or "").strip()
            if status:
                completed_ids.add(node_id)
            projected: dict[str, Any] = {
                "node_id": node_id,
                "status": status,
                "attempts": int(item.get("attempts") or 1),
                "inherited_from_revision": (
                    int(item["inherited_from_revision"])
                    if isinstance(item.get("inherited_from_revision"), int)
                    else None
                ),
                "blocked_by": [
                    str(value)
                    for value in (item.get("blocked_by") or [])
                    if str(value).strip()
                ],
                "source_goal_ids": list(node_goal_ids.get(node_id, [])),
            }
            capability_id = item.get("capability_id")
            projected["capability_id"] = (
                None if capability_id is None else str(capability_id)
            )
            error = item.get("error")
            projected["error"] = None if error is None else str(error)
            node_output = item.get("output")
            if isinstance(node_output, dict):
                reason_code = node_output.get("reason_code") or node_output.get("error_code")
                projected["reason_code"] = (
                    None if reason_code is None else str(reason_code)
                )
                blocked = node_output.get("blocked_subsystems")
                projected["blocked_subsystems"] = (
                    [str(value) for value in blocked if str(value).strip()]
                    if isinstance(blocked, list)
                    else []
                )
                recommendations = node_output.get("recommended_next_actions")
                projected["provider_reported_next_actions"] = (
                    list(recommendations[:16]) if isinstance(recommendations, list) else []
                )
            else:
                projected["reason_code"] = None
                projected["blocked_subsystems"] = []
                projected["provider_reported_next_actions"] = []
            projected_results.append(projected)

    dag_revision = output.get("dag_revision")
    if not isinstance(dag_revision, int) and isinstance(dag_payload, dict):
        dag_revision = dag_payload.get("revision")
    return {
        "dag_id": dag_id,
        "dag_revision": int(dag_revision or 1),
        "goal_ids": goal_ids,
        "status": str(output.get("status") or "").strip().lower(),
        "node_results": projected_results,
        "pending_node_ids": [node_id for node_id in known_node_ids if node_id not in completed_ids],
    }


def _work_dag_result_status(output: dict[str, Any]) -> str:
    dag_status = str(output.get("status") or "").strip().lower()
    if dag_status == "success":
        return "completed"
    if dag_status == "cancelled":
        return "cancelled"
    return "failed"


def _work_dag_reason_code(output: dict[str, Any], status: str) -> str | None:
    if status == "completed":
        return None
    if status == "cancelled":
        return "work_dag_cancelled"
    dag_status = str(output.get("status") or "").strip().lower()
    if not dag_status:
        return "work_dag_missing_terminal_status"
    if dag_status in {"pending", "running"}:
        return "work_dag_non_terminal_result"
    if dag_status not in {"failed", "aborted"}:
        return "work_dag_invalid_terminal_status"
    return "work_dag_failed"


def _work_dag_input_schema() -> dict[str, Any]:
    dag_schema = WorkDAG.model_json_schema()
    properties = dag_schema.get("properties")
    if isinstance(properties, dict):
        properties["authored_by"] = {"type": "string", "const": "planner"}
        goal_ids = properties.get("goal_ids")
        if isinstance(goal_ids, dict):
            goal_ids["minItems"] = 1
    required = list(dag_schema.get("required") or [])
    for field in ("dag_id", "revision", "authored_by", "goal_ids", "nodes"):
        if field not in required:
            required.append(field)
    dag_schema["required"] = required
    defs = dag_schema.pop("$defs", {})
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"dag": dag_schema},
        "required": ["dag"],
        "additionalProperties": False,
    }
    if defs:
        schema["$defs"] = defs
    return schema


def work_dag_capability_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.work_dag.execute",
        version="2.0.0",
        provider_id=WorkDAGCapabilityProvider.provider_id,
        description=(
            "Execute a Planner-authored WorkDAG through the deterministic DAGEngine. "
            "The DAGEngine schedules committed nodes; it does not plan replacement Work."
        ),
        input_schema=_work_dag_input_schema(),
        output_schema=WORK_DAG_RESULT_OUTPUT_SCHEMA,
        timeout_ms=120000,
        interruptible=True,
        can_run_parallel=False,
        cancellation_domains=("embodied_motion",),
        metadata={
            "effects": ["physical_motion"],
            "safety_class": "physical_motion",
            "cancellation_granularity": "request",
            "semantic_owner": "planner",
            "execution_owner": "dag_engine",
        },
    )
