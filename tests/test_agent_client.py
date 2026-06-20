from __future__ import annotations

import unittest
from typing import Any

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


if __name__ == "__main__":
    unittest.main()
