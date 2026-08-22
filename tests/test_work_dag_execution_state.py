from __future__ import annotations

import unittest

from orchestrator.runtime.capability_adapters import (
    WorkDAGCapabilityProvider,
    work_dag_capability_definition,
)
from shared.chromie_contracts.interaction import CapabilityRequest
from orchestrator.runtime.capability_runtime import CapabilityExecutionContext, CapabilityTrace


class WorkDAGExecutionStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_dag_projects_execution_facts_without_residual_planning(self) -> None:
        async def handler(dag: dict) -> dict:
            self.assertEqual(dag["dag_id"], "fetch_phone")
            return {
                "dag_id": "fetch_phone",
                "dag_revision": 1,
                "status": "failed",
                "node_results": [
                    {
                        "node_id": "navigate",
                        "capability_id": "soridormi.navigate",
                        "status": "success",
                        "attempts": 1,
                        "blocked_by": [],
                        "output": {},
                    },
                    {
                        "node_id": "search",
                        "capability_id": "soridormi.search_object",
                        "status": "failed_fatal",
                        "attempts": 1,
                        "blocked_by": [],
                        "output": {
                            "reason_code": "object_not_found",
                            "blocked_subsystems": ["vision"],
                            "recommended_next_actions": ["ask_user"],
                        },
                    },
                ],
            }

        provider = WorkDAGCapabilityProvider(handler)
        definition = work_dag_capability_definition()
        request = CapabilityRequest(
            request_id="dag-1",
            capability_id=definition.capability_id,
            args={
                "dag": {
                    "dag_id": "fetch_phone",
                    "revision": 1,
                    "authored_by": "planner",
                    "goal_ids": ["goal-fetch-phone"],
                    "nodes": [
                        {"id": "navigate", "capability_id": "soridormi.navigate", "source_goal_ids": ["goal-fetch-phone"]},
                        {
                            "id": "search",
                            "capability_id": "soridormi.search_object",
                            "source_goal_ids": ["goal-fetch-phone"],
                            "depends_on": ["navigate"],
                        },
                        {
                            "id": "grasp",
                            "capability_id": "soridormi.grasp_object",
                            "source_goal_ids": ["goal-fetch-phone"],
                            "depends_on": ["search"],
                        },
                    ],
                }
            },
        )
        result = await provider.execute(
            request,
            definition,
            CapabilityExecutionContext(
                interaction_id="interaction-dag-1",
                trace=CapabilityTrace(
                    interaction_id="interaction-dag-1",
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    provider_id=definition.provider_id,
                ),
            ),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason_code, "work_dag_failed")
        self.assertEqual(result.message, "")
        self.assertEqual(result.output["dag_id"], "fetch_phone")
        self.assertEqual(result.output["dag_revision"], 1)
        self.assertEqual(result.output["goal_ids"], ["goal-fetch-phone"])
        self.assertEqual(
            result.output["node_results"][0]["source_goal_ids"],
            ["goal-fetch-phone"],
        )
        self.assertEqual(result.output["pending_node_ids"], ["grasp"])
        failed = result.output["node_results"][1]
        self.assertEqual(failed["reason_code"], "object_not_found")
        self.assertEqual(failed["blocked_subsystems"], ["vision"])
        # Provider suggestions remain explicitly provider-reported facts. The
        # DAGEngine does not promote them into a recovery plan.
        self.assertEqual(failed["provider_reported_next_actions"], ["ask_user"])
        self.assertNotIn("residual_replan", result.output)
        self.assertNotIn("recommended_next_actions", result.output)
        self.assertNotIn("outcome_summary", result.output)


if __name__ == "__main__":
    unittest.main()
