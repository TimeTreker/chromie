from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import AgentManifest, CapabilityBundle, ToolCapability
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest
from agent.app.task_graph.planner import TaskGraphPlanner
from orchestrator.schemas.agent import AgentResult as OrchestratorAgentResult
from shared.chromie_contracts.agent import AgentResult as SharedAgentResult


class FakeOllama:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.response


def _registry():
    external = CapabilityBundle(
        source="weather-test",
        agents=[
            AgentManifest(
                agent_id="weather",
                tools=[
                    ToolCapability(
                        name="weather.current",
                        agent_id="weather",
                        description="Read current weather.",
                        input_schema={
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                            "required": ["location"],
                        },
                        effects=["read_only"],
                        safety_class="safe_read",
                    )
                ],
            )
        ],
    )
    return build_chromie_registry([external])


def _request() -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "plan-weather",
            "text": "What is the weather in Shanghai?",
            "route_decision": {
                "route": "tool",
                "agents": ["tool_agent", "speaker_agent"],
                "intent": "weather_query",
                "confidence": 0.9,
                "language": "en-US",
                "source": "llm",
            },
            "context": {"location": "Shanghai", "private_token": "must-not-enter-prompt"},
        }
    )


class TaskGraphPlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_route_returns_validated_task_graph_without_executable_action(self) -> None:
        ollama = FakeOllama(
            {
                "graph_id": "model-controlled-id",
                "summary": "Read and report the weather.",
                "nodes": [
                    {
                        "id": "weather",
                        "tool": "weather.current",
                        "type": "query",
                        "args": {"location": "Shanghai"},
                    },
                    {
                        "id": "report",
                        "tool": "chromie.report",
                        "type": "report",
                        "depends_on": ["weather"],
                        "args": {"message": {"$ref": "weather.output.summary"}},
                    },
                ],
            }
        )
        planner = TaskGraphPlanner(_registry(), ollama)  # type: ignore[arg-type]
        runtime = AgentRuntime(AgentServices(ollama=None, use_llm=True, task_graph_planner=planner))

        result = await runtime.run(_request())

        self.assertEqual(result.actions, [])
        self.assertEqual(len(result.task_graphs), 1)
        self.assertTrue(result.task_graphs[0]["graph_id"].startswith("graph_"))
        self.assertEqual(result.task_graphs[0]["created_by"], "llm")
        self.assertNotIn("private_token", ollama.calls[0]["prompt"])

        orchestrator_result = OrchestratorAgentResult.model_validate(result.model_dump(mode="json"))
        shared_result = SharedAgentResult.model_validate(result.model_dump(mode="json"))
        self.assertEqual(orchestrator_result.task_graphs[0]["nodes"][0]["tool"], "weather.current")
        self.assertEqual(shared_result.task_graphs[0]["user_request"], _request().text)

    async def test_invalid_llm_graph_falls_back_to_existing_tool_action(self) -> None:
        ollama = FakeOllama(
            {
                "graph_id": "bad",
                "nodes": [{"id": "invented", "tool": "unknown.dangerous_tool", "args": {}}],
            }
        )
        planner = TaskGraphPlanner(_registry(), ollama)  # type: ignore[arg-type]
        runtime = AgentRuntime(AgentServices(ollama=None, use_llm=True, task_graph_planner=planner))

        result = await runtime.run(_request())

        self.assertEqual(result.task_graphs, [])
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0].type, "tool.weather_query")
        self.assertTrue(any("TaskGraph planning failed" in item for item in result.trace))

    async def test_disabled_planner_keeps_existing_tool_path(self) -> None:
        runtime = AgentRuntime(AgentServices(ollama=None, use_llm=False, task_graph_planner=None))

        result = await runtime.run(_request())

        self.assertEqual(result.task_graphs, [])
        self.assertEqual(result.actions[0].target, "tool_executor")


if __name__ == "__main__":
    unittest.main()
