from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest
from agent.app.task_graph.models import TaskGraph, TaskNode
from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from router.app.schema import RouteDecision, RouteRequest, finalize_decision
from shared.chromie_contracts.interaction import InteractionSpeech


def _nod_route(request: RouteRequest) -> RouteDecision:
    return finalize_decision(
        RouteDecision(
            route="robot_action",
            agents=["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
            intent="nod",
            confidence=0.95,
            language="en-US",
            source="catalog",
        ),
        request,
        source="catalog",
    )


class _NamedSkillInvoker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append(tool_name)
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": "sim",
                    "skills": [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "count": {
                                        "type": "number",
                                        "minimum": 2,
                                        "maximum": 3,
                                    }
                                },
                                "additionalProperties": False,
                            },
                            "interruptible": True,
                        }
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            self.assertEqual(args["skill_id"], "nod_yes")
            self.assertEqual(args["parameters"], {"count": 2})
            return ToolCallOutcome.success({"plan_id": "plan-nod"})
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True})
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

    def assertEqual(self, left: Any, right: Any) -> None:
        if left != right:
            raise AssertionError(f"{left!r} != {right!r}")


class _RichTaskPlanner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def plan(self, **kwargs: Any) -> TaskGraph:
        self.calls.append(dict(kwargs))
        return TaskGraph(
            graph_id="rich-body-task",
            user_request=str(kwargs.get("user_request") or ""),
            created_by="llm",
            nodes=[
                TaskNode(
                    id="submit",
                    tool="soridormi.task.submit",
                    type="action",
                    args={"task_type": "navigate_to_location"},
                )
            ],
        )


class InteractionControlPlaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_nod_reaches_named_skill_runtime(self) -> None:
        route_request = RouteRequest(sid="interaction-nod", text="nod")
        decision = _nod_route(route_request)

        response = await InteractionRuntime(
            AgentServices(ollama=None, use_llm=False)
        ).run(
            AgentRunRequest(
                sid=route_request.sid,
                text=route_request.text,
                route_decision=decision.model_dump(mode="json"),
            )
        )
        spoken: list[str] = []
        invoker = _NamedSkillInvoker()
        execution = await InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        ).execute(response, session_id=route_request.sid)

        self.assertEqual(execution.status, "completed")
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(spoken, ["Okay."])
        self.assertEqual(
            invoker.calls,
            [
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
            ],
        )

    async def test_rich_task_graph_reaches_host_planning_handler(self) -> None:
        planner = _RichTaskPlanner()
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=True,
                task_graph_planner=planner,  # type: ignore[arg-type]
            )
        ).run(
            AgentRunRequest(
                sid="rich-task",
                text="Walk to the kitchen and tell me when you arrive.",
                route_decision={
                    "route": "tool",
                    "intent": "soridormi_task_planning",
                    "agents": ["tool_agent", "speaker_agent"],
                    "confidence": 0.92,
                    "source": "catalog",
                },
            )
        )
        response = response.model_copy(
            deep=True,
            update={
                "speech": [
                    *response.speech,
                    InteractionSpeech(text="Arrived.", timing="after_skills"),
                ]
            },
        )
        graphs: list[dict[str, Any]] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            graphs.append(graph)
            return {
                "graph_id": graph["graph_id"],
                "status": "failed",
                "outcome_summary": (
                    "TaskGraph failed at node submit: "
                    "reason code: missing_navigation_pipeline"
                ),
                "node_results": [],
                "events": [],
            }

        spoken: list[str] = []
        execution = await InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        ).execute(response, session_id="rich-task")

        self.assertEqual(response.skills[0].skill_id, "chromie.task_graph.execute")
        self.assertEqual(graphs[0]["graph_id"], "rich-body-task")
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.results[1].skill_id, "chromie.task_graph.execute")
        self.assertNotIn("Arrived.", spoken)
        self.assertEqual(
            spoken,
            ["I prepared a task plan.", "I could not complete that task safely."],
        )


if __name__ == "__main__":
    unittest.main()
