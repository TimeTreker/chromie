from __future__ import annotations

import json
import os
import unittest
from unittest import mock
from typing import Any

from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.plan import PresentationCommit
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
        self.content = _FakeContent([text.encode("utf-8")])

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, tb

    async def text(self) -> str:
        return self._text

    async def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __aiter__(self):
        async def iterate():
            for chunk in self.chunks:
                yield chunk

        return iterate()


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return self.response


@unittest.skipIf(AgentClient is None, "aiohttp is unavailable")
class AgentClientTests(unittest.IsolatedAsyncioTestCase):

    async def test_fast_stream_yields_typed_commit_from_single_endpoint(self) -> None:
        commit = PresentationCommit(
            commit_id="commit-fast",
            turn_id="turn-fast",
            activity={
                "activity_id": "ack",
                "role": "progress",
                "text": "我先看看。",
                "progress_kind": "check_information",
                "source_responsibility_refs": ["weather"],
            },
        )
        session = _FakeSession(_FakeResponse(text=commit.model_dump_json() + "\n"))

        frames = [
            frame
            async for frame in AgentClient(
                "http://agent.local"
            ).stream_fast_advance(
                session,  # type: ignore[arg-type]
                request=CognitiveWorkRequest(
                    sid="turn-fast",
                    text="查一下天气",
                    language="zh-CN",
                    responsibilities=[
                        CognitiveResponsibilityProposal(
                            local_ref="weather",
                            outcome="check the weather",
                            confidence=0.95,
                        )
                    ],
                    interpretation_confidence=0.95,
                ),
                timeout_ms=1900,
            )
        ]

        self.assertEqual(frames[0].activity.text, "我先看看。")
        self.assertEqual(
            session.posts[0]["url"],
            "http://agent.local/fast-advance",
        )
        self.assertAlmostEqual(session.posts[0]["timeout"].total, 1.9)

    async def test_goal_association_call_injects_runtime_trace_carrier(self) -> None:
        resolution = GoalAssociationResolution(
            resolution_status="resolved",
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
                    request=CognitiveWorkRequest(
                        sid="sid-agent-client",
                        text="hello",
                        responsibilities=[
                            CognitiveResponsibilityProposal(
                                local_ref="reply",
                                outcome="hello",
                                confidence=0.9,
                            )
                        ],
                        interpretation_confidence=0.9,
                        context={"history": []},
                    ),
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

    async def test_execute_planning_work_dag_posts_dag_payload(self) -> None:
        trace = {
            "dag_id": "nav",
            "status": "success",
        }
        session = _FakeSession(_FakeResponse(payload=trace))

        result = await AgentClient("http://agent.local/").execute_planning_work_dag(
            session,  # type: ignore[arg-type]
            {"dag_id": "nav", "nodes": []},
            timeout_ms=2500,
        )

        self.assertEqual(result, trace)
        self.assertEqual(
            session.posts[0]["url"],
            "http://agent.local/work-dags/execute-planning",
        )
        self.assertEqual(
            session.posts[0]["json"],
            {"dag": {"dag_id": "nav", "nodes": []}},
        )
        self.assertAlmostEqual(session.posts[0]["timeout"].total, 2.5)

    async def test_execute_planning_work_dag_raises_on_http_error(self) -> None:
        session = _FakeSession(
            _FakeResponse(status=503, text='{"detail":"planning disabled"}')
        )

        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            await AgentClient("http://agent.local").execute_planning_work_dag(
                session,  # type: ignore[arg-type]
                {"dag_id": "nav", "nodes": []},
            )

    async def test_cancel_planning_work_dag_uses_authenticated_endpoint(
        self,
    ) -> None:
        receipt = {
            "dag_id": "nav-room",
            "cancellation_requested": True,
        }
        session = _FakeSession(_FakeResponse(payload=receipt))

        result = await AgentClient(
            "http://agent.local/",
            dag_engine_execution_token="execution-secret",
        ).cancel_planning_work_dag(
            session,  # type: ignore[arg-type]
            "nav-room",
            timeout_ms=2500,
        )

        self.assertEqual(result, receipt)
        self.assertEqual(
            session.posts[0]["url"],
            "http://agent.local/work-dags/nav-room/cancel",
        )
        self.assertEqual(
            session.posts[0]["headers"],
            {"Authorization": "Bearer execution-secret"},
        )
        self.assertAlmostEqual(session.posts[0]["timeout"].total, 2.5)

    async def test_cancel_planning_work_dag_requires_token(self) -> None:
        session = _FakeSession(_FakeResponse())

        with self.assertRaisesRegex(
            RuntimeError,
            "AGENT_DAG_ENGINE_EXECUTION_TOKEN",
        ):
            await AgentClient(
                "http://agent.local",
                dag_engine_execution_token="",
            ).cancel_planning_work_dag(
                session,  # type: ignore[arg-type]
                "nav",
            )

        self.assertEqual(session.posts, [])


if __name__ == "__main__":
    unittest.main()
