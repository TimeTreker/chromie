from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.interaction import AgentResultInteractionAdapter
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest
from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from router.app.rules import route_by_rules
from router.app.schema import RouteRequest


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


class InteractionControlPlaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_nod_reaches_named_skill_runtime(self) -> None:
        route_request = RouteRequest(sid="interaction-nod", text="nod")
        decision = route_by_rules(route_request)
        self.assertIsNotNone(decision)
        assert decision is not None

        legacy_result = await AgentRuntime(
            AgentServices(ollama=None, use_llm=False)
        ).run(
            AgentRunRequest(
                sid=route_request.sid,
                text=route_request.text,
                route_decision=decision.model_dump(mode="json"),
            )
        )
        response = AgentResultInteractionAdapter().convert(legacy_result)
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


if __name__ == "__main__":
    unittest.main()
