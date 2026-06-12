from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from shared.chromie_contracts.interaction import InteractionResponse


class _SoridormiInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
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
                                        "type": "integer",
                                        "minimum": 1,
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
            return ToolCallOutcome.success({"plan_id": "plan-1"})
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class InteractionRuntimeCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_only_does_not_require_soridormi(self) -> None:
        scheduled: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: scheduled.append(args) or {"scheduled": True}
        )

        result = await coordinator.execute(
            InteractionResponse(speech=[{"text": "Hello."}]),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(scheduled[0]["text"], "Hello.")
        self.assertEqual(scheduled[0]["metadata"]["session_id"], "sid-1")

    async def test_sim_body_skill_discovers_catalog_and_executes(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [call[0] for call in invoker.calls],
            [
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
            ],
        )
        self.assertTrue(invoker.calls[-1][2].confirmed)

    async def test_body_skill_fails_closed_when_provider_is_disabled(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True}
        )

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            await coordinator.execute(
                InteractionResponse(
                    skills=[{"skill_id": "soridormi.nod_yes"}]
                ),
                session_id="sid-1",
            )


if __name__ == "__main__":
    unittest.main()
