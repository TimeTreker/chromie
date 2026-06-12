from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.app.tool_invocation import ToolCallOutcome
from scripts.interaction_text_acceptance import run_acceptance


class _Invoker:
    async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
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
            return ToolCallOutcome.success({"plan_id": "plan-1"})
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True})
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        if tool_name == "soridormi.robot.get_status":
            return ToolCallOutcome.success(
                {"active_task": None, "emergency_stop": False}
            )
        return ToolCallOutcome.failed("unexpected tool")


class InteractionTextAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_nod_acceptance_emits_speech_and_named_skill(self) -> None:
        with patch(
            "scripts.interaction_text_acceptance.build_soridormi_invoker",
            return_value=_Invoker(),
        ):
            payload = await run_acceptance(
                text="nod",
                manifest=None,  # type: ignore[arg-type]
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scheduled_speech"], ["Okay."])
        self.assertEqual(
            payload["interaction_response"]["skills"][0]["skill_id"],
            "soridormi.nod_yes",
        )


if __name__ == "__main__":
    unittest.main()
