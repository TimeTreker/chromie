from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.post_interrupt import lock_post_interrupt_physical_resume
from shared.chromie_contracts.interaction import InteractionResponse


class _Invoker:
    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        del args, context
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": "sim",
                    "skills": [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {"type": "object"},
                            "requires_confirmation": False,
                        }
                    ],
                }
            )
        return ToolCallOutcome.success({})


class PostInterruptPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_only_correction_is_not_locked(self) -> None:
        response = InteractionResponse(speech=[{"text": "Sorry, I misheard that."}])

        locked, request_ids = lock_post_interrupt_physical_resume(response)

        self.assertIs(locked, response)
        self.assertEqual(request_ids, ())
        self.assertFalse(locked.requires_confirmation)

    async def test_body_correction_requires_fresh_confirmation(self) -> None:
        response = InteractionResponse(
            skills=[
                {
                    "request_id": "nod-1",
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "requires_confirmation": False,
                }
            ],
            metadata={"post_interrupt_correction": True},
        )

        locked, request_ids = lock_post_interrupt_physical_resume(response)

        self.assertEqual(request_ids, ("nod-1",))
        self.assertTrue(locked.requires_confirmation)
        self.assertTrue(locked.metadata["post_interrupt_physical_resume_lock"])
        self.assertTrue(locked.metadata["disable_body_auto_confirm"])
        self.assertTrue(locked.skills[0].requires_confirmation)
        self.assertTrue(locked.skills[0].metadata["post_interrupt_physical_resume_lock"])
        self.assertEqual(
            locked.skills[0].metadata["post_interrupt_resume_policy"],
            "requires_fresh_confirmation",
        )

    async def test_body_lock_disables_sim_auto_confirm(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=_Invoker(),
            auto_confirm_sim=True,
        )
        coordinator.soridormi_mode = "sim"
        response, _ = lock_post_interrupt_physical_resume(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {},
                    }
                ]
            )
        )

        required = await coordinator.confirmation_request_ids(response)
        exempted = await coordinator.confirmation_exemption_request_ids(response)

        self.assertEqual(required, {"nod-1"})
        self.assertEqual(exempted, set())


if __name__ == "__main__":
    unittest.main()
