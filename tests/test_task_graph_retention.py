from __future__ import annotations

import unittest

from agent.app.capabilities.local import build_chromie_registry
from agent.app.task_graph.grants import ConfirmationGrantStore
from agent.app.task_graph.models import TaskGraph
from agent.app.task_graph.service import TaskGraphService


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _report_graph(graph_id: str) -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": graph_id,
            "nodes": [
                {
                    "id": "report",
                    "tool": "chromie.report",
                    "type": "report",
                    "args": {"message": graph_id},
                }
            ],
        }
    )


def _confirmation_graph(graph_id: str = "confirmation") -> TaskGraph:
    return TaskGraph.model_validate(
        {
            "graph_id": graph_id,
            "nodes": [
                {
                    "id": "confirm",
                    "tool": "chromie.ask_confirmation",
                    "type": "confirmation",
                    "args": {"question": "Continue?"},
                }
            ],
        }
    )


class TaskGraphRetentionTests(unittest.TestCase):
    def test_graph_id_is_safe_for_cancel_route(self) -> None:
        graph = _report_graph("goal:fetch_phone-01")
        self.assertEqual(graph.graph_id, "goal:fetch_phone-01")
        with self.assertRaisesRegex(ValueError, "URL-path-safe"):
            _report_graph("goal/fetch phone")

    def test_traces_use_ttl_and_lru_capacity(self) -> None:
        clock = _Clock()
        service = TaskGraphService(
            build_chromie_registry(),
            trace_max_entries=2,
            trace_ttl_s=10,
            clock=clock,
        )
        service.dry_run(_report_graph("one"))
        service.dry_run(_report_graph("two"))
        self.assertIsNotNone(service.get_trace("one"))

        # Accessing "one" makes "two" the least-recently-used entry.
        service.dry_run(_report_graph("three"))
        self.assertIsNotNone(service.get_trace("one"))
        self.assertIsNone(service.get_trace("two"))
        self.assertIsNotNone(service.get_trace("three"))

        clock.now += 11
        self.assertIsNone(service.get_trace("one"))
        self.assertIsNone(service.get_trace("three"))

    def test_confirmation_grants_purge_expired_and_bound_capacity(self) -> None:
        clock = _Clock()
        store = ConfirmationGrantStore(max_entries=2, clock=clock)
        graph = _confirmation_graph()
        first, _ = store.issue(graph, {"confirm"}, ttl_s=5)
        store.issue(graph, {"confirm"}, ttl_s=5)
        store.issue(graph, {"confirm"}, ttl_s=5)
        self.assertEqual(len(store), 2)
        with self.assertRaisesRegex(ValueError, "invalid or already used"):
            store.consume(first, graph)

        clock.now += 6
        self.assertEqual(len(store), 0)


if __name__ == "__main__":
    unittest.main()
