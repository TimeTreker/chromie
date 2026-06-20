from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.local import build_chromie_registry
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
)
from agent.app.runtime import AgentRuntime, InteractionRuntime
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


class RaisingPlanner:
    async def plan(self, **kwargs: Any):  # pragma: no cover - assertion helper
        raise AssertionError(f"TaskGraph planner should not be used: {kwargs}")


class CapabilityOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, **kwargs})
        return {
            "decision": "execute",
            "speech": "Walking forward.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_velocity",
                    "args": {"vx_mps": 0.2, "duration_s": 1.0},
                }
            ],
        }


class LiveSkillInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None):
        del arguments, context
        if tool_name != "soridormi.skill.list":
            raise AssertionError(tool_name)

        class Outcome:
            status = "success"
            error = None
            output = {
                "mode": "sim",
                "skills": [
                    {
                        "skill_id": "walk_velocity",
                        "description": "Walk forward or backward for an explicitly bounded duration.",
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "vx_mps": {"type": "number"},
                                "duration_s": {"type": "number"},
                            },
                            "required": ["vx_mps", "duration_s"],
                        },
                        "available": True,
                        "effects": ["physical_motion"],
                        "safety_class": "physical_motion",
                        "requires_confirmation": True,
                    }
                ],
            }

        return Outcome()


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


def _soridormi_task_registry() -> CapabilityRegistry:
    return build_chromie_registry(
        [
            CapabilityBundle(
                source="soridormi-task-planning-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List concrete bounded Soridormi named skills.",
                                safety_class="safe_read",
                                effects=["read_only"],
                            )
                        ],
                    ),
                    AgentManifest(
                        agent_id="soridormi.task",
                        tags=["soridormi", "task", "embodied-goal"],
                        tools=[
                            ToolCapability(
                                name="soridormi.task.get_capabilities",
                                agent_id="soridormi.task",
                                description=(
                                    "Inspect Soridormi embodied task readiness, blocked "
                                    "subsystems, navigation, approach, inspection, and delivery support."
                                ),
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                            ToolCapability(
                                name="soridormi.task.preview",
                                agent_id="soridormi.task",
                                description=(
                                    "Preview a structured embodied task goal such as navigation, "
                                    "approach, inspection, recovery, or deliver object without motion."
                                ),
                                safety_class="planning_only",
                                effects=["planning_only", "embodied_task_request", "no_motion_contract"],
                            ),
                            ToolCapability(
                                name="soridormi.task.submit",
                                agent_id="soridormi.task",
                                description=(
                                    "Submit a structured embodied goal for navigation, approach, "
                                    "inspection, recovery, or object delivery such as bringing water."
                                ),
                                safety_class="planning_only",
                                effects=["planning_only", "embodied_task_request", "no_motion_contract"],
                            ),
                            ToolCapability(
                                name="soridormi.task.events",
                                agent_id="soridormi.task",
                                description="Monitor terminal events for a submitted Soridormi task.",
                                safety_class="safe_read",
                                effects=["read_only"],
                            ),
                        ],
                    ),
                ],
            )
        ]
    )


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

    async def test_rich_embodied_goal_routes_to_soridormi_task_graph(self) -> None:
        registry = _soridormi_task_registry()
        ollama = FakeOllama(
            {
                "graph_id": "model-controlled-id",
                "summary": "Ask Soridormi to evaluate water delivery.",
                "nodes": [
                    {
                        "id": "capabilities",
                        "tool": "soridormi.task.get_capabilities",
                        "type": "query",
                    },
                    {
                        "id": "preview",
                        "tool": "soridormi.task.preview",
                        "type": "plan",
                        "depends_on": ["capabilities"],
                        "args": {
                            "task_type": "deliver_object",
                            "summary": "Bring water from the kitchen.",
                            "parameters": {"object": "water", "source": "kitchen"},
                        },
                    },
                    {
                        "id": "submit",
                        "tool": "soridormi.task.submit",
                        "type": "plan",
                        "depends_on": ["preview"],
                        "args": {
                            "task_type": "deliver_object",
                            "summary": "Bring water from the kitchen.",
                            "parameters": {"object": "water", "source": "kitchen"},
                        },
                    },
                ],
            }
        )
        runtime = InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=True,
                expressive_body_cues="off",
                capability_catalog=CapabilityCatalog(
                    registry,
                    live_invoker=None,
                    min_score=0.10,
                ),
                task_graph_planner=TaskGraphPlanner(registry, ollama),  # type: ignore[arg-type]
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "bring-water",
                "text": "Bring me water from the kitchen.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.3,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(request.route_decision.route, "tool")
        self.assertEqual(request.route_decision.intent, "soridormi_task_planning")
        self.assertEqual(response.skills[0].skill_id, "chromie.task_graph.execute")
        graph = response.skills[0].args["graph"]
        self.assertEqual(
            [node["tool"] for node in graph["nodes"]],
            [
                "soridormi.task.get_capabilities",
                "soridormi.task.preview",
                "soridormi.task.submit",
                "chromie.report",
            ],
        )
        submit = graph["nodes"][2]
        report = graph["nodes"][3]
        self.assertEqual(submit["on_failure"]["strategy"], "goto")
        self.assertEqual(submit["on_failure"]["target"], "submit_report")
        self.assertEqual(report["id"], "submit_report")
        self.assertEqual(report["type"], "report")
        self.assertEqual(report["args"]["message"], {"$ref": "submit.error"})
        self.assertIn("soridormi.task.submit", ollama.calls[0]["prompt"])
        self.assertIn("richer embodied goals", ollama.calls[0]["system"])
        self.assertIn("trace-only", ollama.calls[0]["system"])
        self.assertIn("chromie.report", ollama.calls[0]["system"])
        self.assertIn("chromie.speak", ollama.calls[0]["system"])
        self.assertIn("on_failure", ollama.calls[0]["prompt"])

    async def test_explicit_bounded_motion_stays_named_skill_not_task_graph(self) -> None:
        registry = _soridormi_task_registry()
        capability_ollama = CapabilityOllama()
        runtime = InteractionRuntime(
            AgentServices(
                ollama=capability_ollama,  # type: ignore[arg-type]
                use_llm=True,
                expressive_body_cues="off",
                capability_catalog=CapabilityCatalog(
                    registry,
                    live_invoker=LiveSkillInvoker(),
                    min_score=0.10,
                ),
                task_graph_planner=RaisingPlanner(),  # type: ignore[arg-type]
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "walk-forward",
                "text": "Walk forward at 0.2 speed for one second.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.3,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(request.route_decision.route, "robot_action")
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_velocity")
        self.assertEqual(response.skills[0].args, {"vx_mps": 0.2, "duration_s": 1.0})
        self.assertTrue(response.skills[0].requires_confirmation)
        self.assertEqual(response.speech[0].text, "Walking forward.")
        self.assertEqual(len(capability_ollama.calls), 1)


if __name__ == "__main__":
    unittest.main()
