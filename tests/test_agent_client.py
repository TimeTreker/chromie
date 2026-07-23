from __future__ import annotations

import json
import os
import unittest
from unittest import mock
from typing import Any

from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_runtime.runtime_trace import TRACE_CARRIER_KEY, runtime_tracer

try:
    from orchestrator.clients.agent_client import AgentClient
except ModuleNotFoundError as exc:  # pragma: no cover - dependency-light host
    if exc.name != "aiohttp":
        raise
    AgentClient = None  # type: ignore[assignment]


class _FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        text: str = "{}",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self._text = text
        self._payload = payload or {}

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, tb

    async def text(self) -> str:
        return self._text

    async def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return self.response


@unittest.skipIf(AgentClient is None, "aiohttp is unavailable")
class AgentClientTests(unittest.IsolatedAsyncioTestCase):

    async def test_goal_association_call_injects_runtime_trace_carrier(self) -> None:
        resolution = GoalAssociationResolution(
            turn_id="turn-agent-client",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-agent-client",
                    description="Respond to the user.",
                    source_text="hello",
                )
            ],
            confidence=0.9,
            metadata={"status": "resolved"},
        )
        session = _FakeSession(
            _FakeResponse(text=resolution.model_dump_json())
        )
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            scope = runtime_tracer.start_trace(
                correlations={"session_id": "sid-agent-client"}
            )
            async with scope:
                result = await AgentClient(
                    "http://agent.local"
                ).resolve_goal_association(
                    session,  # type: ignore[arg-type]
                    sid="sid-agent-client",
                    text="hello",
                    route_decision={
                        "route": "chat",
                        "intent": "conversation",
                        "confidence": 0.9,
                        "source": "llm",
                    },
                    context={"history": []},
                )
            snapshot = scope.finish()

        self.assertEqual(result.turn_id, "turn-agent-client")
        carrier = session.posts[0]["json"]["context"][TRACE_CARRIER_KEY]
        self.assertEqual(carrier["trace_id"], snapshot.trace["trace_id"])
        self.assertTrue(carrier["parent_item_id"].startswith("item_"))
        modules = {
            item["module"]["name"] for item in snapshot.trace["items"]
        }
        self.assertIn("orchestrator.agent_client", modules)

    async def test_execute_planning_task_graph_posts_graph_payload(self) -> None:
        trace = {
            "graph_id": "nav",
            "status": "success",
            "outcome_summary": "TaskGraph completed successfully.",
        }
        session = _FakeSession(_FakeResponse(payload=trace))

        result = await AgentClient("http://agent.local/").execute_planning_task_graph(
            session,  # type: ignore[arg-type]
            {"graph_id": "nav", "nodes": []},
            timeout_ms=2500,
        )

        self.assertEqual(result, trace)
        self.assertEqual(
            session.posts[0]["url"],
            "http://agent.local/task-graphs/execute-planning",
        )
        self.assertEqual(
            session.posts[0]["json"],
            {"graph": {"graph_id": "nav", "nodes": []}},
        )
        self.assertAlmostEqual(session.posts[0]["timeout"].total, 2.5)

    async def test_execute_planning_task_graph_raises_on_http_error(self) -> None:
        session = _FakeSession(
            _FakeResponse(status=503, text='{"detail":"planning disabled"}')
        )

        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            await AgentClient("http://agent.local").execute_planning_task_graph(
                session,  # type: ignore[arg-type]
                {"graph_id": "nav", "nodes": []},
            )

    async def test_cancel_planning_task_graph_uses_authenticated_endpoint(
        self,
    ) -> None:
        receipt = {
            "graph_id": "nav-room",
            "cancellation_requested": True,
        }
        session = _FakeSession(_FakeResponse(payload=receipt))

        result = await AgentClient(
            "http://agent.local/",
            task_graph_execution_token="execution-secret",
        ).cancel_planning_task_graph(
            session,  # type: ignore[arg-type]
            "nav-room",
            timeout_ms=2500,
        )

        self.assertEqual(result, receipt)
        self.assertEqual(
            session.posts[0]["url"],
            "http://agent.local/task-graphs/nav-room/cancel",
        )
        self.assertEqual(
            session.posts[0]["headers"],
            {"Authorization": "Bearer execution-secret"},
        )
        self.assertAlmostEqual(session.posts[0]["timeout"].total, 2.5)

    async def test_cancel_planning_task_graph_requires_token(self) -> None:
        session = _FakeSession(_FakeResponse())

        with self.assertRaisesRegex(
            RuntimeError,
            "AGENT_TASK_GRAPH_EXECUTION_TOKEN",
        ):
            await AgentClient(
                "http://agent.local",
                task_graph_execution_token="",
            ).cancel_planning_task_graph(
                session,  # type: ignore[arg-type]
                "nav",
            )

        self.assertEqual(session.posts, [])


if __name__ == "__main__":
    unittest.main()
