from __future__ import annotations

import unittest

from agent.app.capabilities.local import build_chromie_registry
from agent.app.tool_invocation import ToolCallOutcome
from agent.app.work_dag.models import WorkDAG
from agent.app.work_dag.service import DAGEngineService


class _ReadInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def invoke(self, tool_name: str, args: dict, *, context=None) -> ToolCallOutcome:
        del context
        self.calls.append((tool_name, dict(args)))
        return ToolCallOutcome.success({"events": [], "task_id": args.get("task_id")})


def _dag(
    *,
    revision: int,
    parent_revision: int | None,
    include_second: bool,
    first_task_id: str = "first",
) -> WorkDAG:
    nodes = [
        {
            "id": "inspect-a",
            "capability_id": "chromie.task.get_trace",
            "args": {"task_id": first_task_id},
            "source_goal_ids": ["goal-a"],
        }
    ]
    goal_ids = ["goal-a"]
    if include_second:
        goal_ids.append("goal-b")
        nodes.append(
            {
                "id": "inspect-b",
                "capability_id": "chromie.task.get_trace",
                "args": {"task_id": "second"},
                "source_goal_ids": ["goal-b"],
                "depends_on": ["inspect-a"],
            }
        )
    return WorkDAG.model_validate(
        {
            "dag_id": "session-work",
            "revision": revision,
            "parent_revision": parent_revision,
            "authored_by": "planner",
            "goal_ids": goal_ids,
            "revision_reason": "initial" if revision == 1 else "goal-b-added",
            "nodes": nodes,
        }
    )


class WorkDAGRevisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_next_revision_inherits_completed_nodes_without_reexecution(self) -> None:
        invoker = _ReadInvoker()
        engine = DAGEngineService(
            build_chromie_registry(),
            read_only_invoker=invoker,
        )

        first = await engine.execute_read_only(
            _dag(revision=1, parent_revision=None, include_second=False)
        )
        self.assertEqual(first.status, "success")
        self.assertEqual(first.dag_revision, 1)
        self.assertEqual([name for name, _ in invoker.calls], ["chromie.task.get_trace"])

        second = await engine.execute_read_only(
            _dag(revision=2, parent_revision=1, include_second=True)
        )
        self.assertEqual(second.status, "success")
        self.assertEqual(second.dag_revision, 2)
        self.assertEqual(len(invoker.calls), 2)
        self.assertEqual(invoker.calls[-1][1]["task_id"], "second")
        inherited = second.result_map()["inspect-a"]
        self.assertEqual(inherited.inherited_from_revision, 1)
        self.assertTrue(
            any(
                event.type == "node_inherited" and event.node_id == "inspect-a"
                for event in second.events
            )
        )

    async def test_revision_cannot_rewrite_completed_node(self) -> None:
        invoker = _ReadInvoker()
        engine = DAGEngineService(
            build_chromie_registry(),
            read_only_invoker=invoker,
        )
        await engine.execute_read_only(
            _dag(revision=1, parent_revision=None, include_second=False)
        )

        with self.assertRaisesRegex(ValueError, "may not rewrite completed node"):
            await engine.execute_read_only(
                _dag(
                    revision=2,
                    parent_revision=1,
                    include_second=True,
                    first_task_id="rewritten",
                )
            )

    def test_non_planner_cannot_author_semantic_revision(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only Planner may author"):
            WorkDAG.model_validate(
                {
                    "dag_id": "dag-revision-owner",
                    "revision": 2,
                    "parent_revision": 1,
                    "authored_by": "operator",
                    "nodes": [],
                }
            )

    async def test_revision_must_advance_exactly_once(self) -> None:
        invoker = _ReadInvoker()
        engine = DAGEngineService(
            build_chromie_registry(),
            read_only_invoker=invoker,
        )
        await engine.execute_read_only(
            _dag(revision=1, parent_revision=None, include_second=False)
        )
        with self.assertRaisesRegex(ValueError, "advance exactly"):
            await engine.execute_read_only(
                WorkDAG.model_validate(
                    {
                        "dag_id": "session-work",
                        "revision": 3,
                        "parent_revision": 2,
                        "authored_by": "planner",
                        "goal_ids": ["goal-a"],
                        "nodes": [
                            {
                                "id": "inspect-a",
                                "capability_id": "chromie.task.get_trace",
                                "args": {"task_id": "first"},
                                "source_goal_ids": ["goal-a"],
                            }
                        ],
                    }
                )
            )

    def test_planner_work_dag_requires_goal_ownership(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires source_goal_ids"):
            WorkDAG.model_validate(
                {
                    "dag_id": "bad",
                    "authored_by": "planner",
                    "nodes": [
                        {
                            "id": "inspect",
                            "capability_id": "chromie.task.get_trace",
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
