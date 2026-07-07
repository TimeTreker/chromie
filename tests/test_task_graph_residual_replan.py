from __future__ import annotations

import unittest
from typing import Any

from agent.app.task_graph.models import ExecutionTrace, NodeResult, TaskGraph
from agent.app.task_graph.residual import build_residual_replan_state
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from shared.chromie_contracts.interaction import InteractionResponse


def _graph() -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": "fetch_phone",
            "user_request": "Bring me the phone from the office.",
            "nodes": [
                {"id": "navigate", "tool": "soridormi.navigate", "type": "action"},
                {
                    "id": "search",
                    "tool": "soridormi.search_object",
                    "type": "query",
                    "depends_on": ["navigate"],
                    "args": {"object": "phone"},
                },
                {
                    "id": "grasp",
                    "tool": "soridormi.grasp_object",
                    "type": "action",
                    "depends_on": ["search"],
                },
                {
                    "id": "return",
                    "tool": "soridormi.return_to_user",
                    "type": "action",
                    "depends_on": ["grasp"],
                },
            ],
        }
    )


class TaskGraphResidualReplanTests(unittest.TestCase):
    def test_failed_trace_preserves_completed_failed_and_remaining_steps(self) -> None:
        graph = _graph()
        trace = ExecutionTrace(
            graph_id=graph.graph_id,
            status="failed",
            outcome_summary="TaskGraph failed at node search.",
            node_results=[
                NodeResult(
                    node_id="navigate",
                    tool="soridormi.navigate",
                    status="success",
                    output={
                        "summary": "Arrived in the office.",
                        "irreversible_effects": ["robot_moved_to_office"],
                        "current_state": {"location": "office"},
                    },
                ),
                NodeResult(
                    node_id="search",
                    tool="soridormi.search_object",
                    status="failed_retryable",
                    output={
                        "error_code": "object_not_found",
                        "current_physical_state": {
                            "location": "office",
                            "target_visible": False,
                        },
                        "recommended_next_actions": [
                            "ask_user_for_more_specific_location"
                        ],
                    },
                    error="phone not visible",
                ),
                NodeResult(
                    node_id="grasp",
                    tool="soridormi.grasp_object",
                    status="blocked",
                    blocked_by=["search"],
                ),
            ],
        )

        state = build_residual_replan_state(graph, trace)

        assert state is not None
        self.assertEqual(state["status"], "needs_residual_replan")
        self.assertEqual(state["original_goal"], "Bring me the phone from the office.")
        self.assertEqual(
            [step["node_id"] for step in state["completed_steps"]],
            ["navigate"],
        )
        self.assertEqual(state["failed_step"]["node_id"], "search")
        self.assertEqual(state["failure_code"], "object_not_found")
        self.assertEqual(state["current_physical_state"]["source_node_id"], "search")
        self.assertEqual(
            state["current_physical_state"]["value"],
            {"location": "office", "target_visible": False},
        )
        self.assertEqual(
            state["recommended_next_actions"],
            ["ask_user_for_more_specific_location"],
        )
        self.assertEqual(
            state["replan_scope"]["exclude_completed_node_ids"],
            ["navigate"],
        )
        self.assertEqual(
            state["replan_scope"]["remaining_node_ids"],
            ["search", "grasp", "return"],
        )
        self.assertEqual(
            state["irreversible_effects"][0]["effect"],
            "robot_moved_to_office",
        )

    def test_success_trace_has_no_residual_state(self) -> None:
        graph = _graph()
        trace = ExecutionTrace(graph_id=graph.graph_id, status="success")

        self.assertIsNone(build_residual_replan_state(graph, trace))


class TaskGraphResidualCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_graph_provider_adds_residual_replan_to_failed_handler_output(
        self,
    ) -> None:
        graph = _graph().model_dump(mode="json")
        spoken: list[str] = []

        async def execute_graph(graph_payload: dict[str, Any]) -> dict[str, Any]:
            self.assertEqual(graph_payload["graph_id"], "fetch_phone")
            return {
                "graph_id": "fetch_phone",
                "status": "failed",
                "outcome_summary": "TaskGraph failed at node search.",
                "node_results": [
                    {
                        "node_id": "navigate",
                        "tool": "soridormi.navigate",
                        "status": "success",
                        "output": {"summary": "Arrived in the office."},
                    },
                    {
                        "node_id": "search",
                        "tool": "soridormi.search_object",
                        "status": "failed_retryable",
                        "output": {
                            "reason_code": "object_not_found",
                            "recommended_next_actions": ["ask_user"],
                        },
                    },
                ],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "graph-1",
                        "skill_id": "chromie.task_graph.execute",
                        "args": {"graph": graph},
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-residual",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(spoken, ["I could not complete that task safely."])
        residual = result.results[0].output["residual_replan"]
        self.assertEqual(residual["failed_step"]["node_id"], "search")
        self.assertEqual(residual["failure_code"], "object_not_found")
        self.assertEqual(
            residual["replan_scope"]["exclude_completed_node_ids"],
            ["navigate"],
        )
        self.assertEqual(
            residual["replan_scope"]["remaining_node_ids"],
            ["search", "grasp", "return"],
        )


if __name__ == "__main__":
    unittest.main()
