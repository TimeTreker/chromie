from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.skill_runtime import (
    RuntimeAuthorization,
    SkillRegistry,
    SkillRuntime,
)
from orchestrator.runtime.soridormi_skill_provider import SoridormiMcpSkillProvider
from shared.chromie_contracts.interaction import InteractionResponse


class _RecordingInvoker:
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
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success(
                {
                    "plan_id": "plan-1",
                    "skill_id": args["skill_id"],
                    "requires_confirmation": True,
                }
            )
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {
                    "completed": True,
                    "skill_id": "nod_yes",
                    "summary": "completed nod_yes",
                }
            )
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class SoridormiSkillProviderTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, invoker: _RecordingInvoker) -> SkillRuntime:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "nod_yes",
                    "description": "Nod the robot head.",
                    "available": True,
                    "parameters_schema": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "minimum": 1, "maximum": 3},
                            "amplitude": {
                                "type": "string",
                                "enum": ["small", "medium"],
                            },
                        },
                        "additionalProperties": False,
                    },
                    "interruptible": True,
                    "execution": "scripted_keyframe",
                    "fallback": "neutral_head",
                }
            ]
        )
        runtime = SkillRuntime(registry)
        runtime.register_provider(SoridormiMcpSkillProvider(invoker))
        return runtime

    async def test_named_skill_uses_opaque_plan_execute_contract(self) -> None:
        invoker = _RecordingInvoker()
        execution = await self._runtime(invoker).execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2, "amplitude": "small"},
                    }
                ]
            ),
            authorization=RuntimeAuthorization(
                confirmed_request_ids={"nod-1"},
                safety_monitor_active=True,
            ),
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(
            invoker.calls[0][0:2],
            (
                "soridormi.skill.create_plan",
                {
                    "skill_id": "nod_yes",
                    "parameters": {"count": 2, "amplitude": "small"},
                },
            ),
        )
        self.assertEqual(
            invoker.calls[1][0:2],
            (
                "soridormi.safety.monitor_motion",
                {"during_node_id": "nod-1"},
            ),
        )
        self.assertEqual(
            invoker.calls[2][0:2],
            ("soridormi.skill.execute_plan", {"plan_id": "plan-1"}),
        )
        self.assertTrue(invoker.calls[2][2].confirmed)
        self.assertTrue(invoker.calls[2][2].safety_monitor_active)

    async def test_catalog_preserves_unavailable_skill_reason(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "wave_hand",
                    "available": False,
                    "unavailable_reason": "not executable",
                    "parameters_schema": {"type": "object"},
                }
            ]
        )
        runtime = SkillRuntime(registry)
        runtime.register_provider(SoridormiMcpSkillProvider(_RecordingInvoker()))

        with self.assertRaisesRegex(ValueError, "not executable"):
            await runtime.execute(
                InteractionResponse(
                    skills=[{"skill_id": "soridormi.wave_hand"}]
                ),
                authorization=RuntimeAuthorization(
                    safety_monitor_active=True,
                ),
            )


if __name__ == "__main__":
    unittest.main()
