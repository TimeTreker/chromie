from __future__ import annotations

import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.post_interrupt import lock_post_interrupt_physical_resume
from orchestrator.runtime.soridormi_skill_provider import (
    SoridormiMcpSkillProvider,
    SoridormiNamedSkillAdapter,
)
from shared.chromie_contracts.interaction import InteractionResponse


class _ArchitectureInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []
        self.planned_skill_id = ""

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
                            "skill_id": "wave_hand",
                            "description": "Wave a hand to greet the user.",
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
                            "effects": ["physical_motion"],
                            "safety_class": "physical_motion",
                            "requires_confirmation": False,
                            "interruptible": True,
                        },
                        {
                            "skill_id": "inspect_object",
                            "description": "Inspect an object using live perception.",
                            "available": True,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "semantic_target": {"type": "string"}
                                },
                                "additionalProperties": False,
                            },
                            "effects": ["physical_motion"],
                            "safety_class": "physical_motion",
                            "requires_confirmation": False,
                            "interruptible": True,
                        },
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            self.planned_skill_id = str(args["skill_id"])
            return ToolCallOutcome.success(
                {"plan_id": f"plan-{self.planned_skill_id}"}
            )
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": self.planned_skill_id}
            )
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class SoridormiArchitectureIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_catalog_skill_runs_through_named_skill_adapter(self) -> None:
        invoker = _ArchitectureInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
            auto_confirm_sim=True,
        )

        result = await coordinator.execute(
            InteractionResponse(
                interaction_id="interaction-dynamic-wave",
                skills=[
                    {
                        "request_id": "wave-1",
                        "skill_id": "soridormi.wave_hand",
                        "args": {"count": 2},
                        "metadata": {
                            "source_component": "agent.capability",
                            "route_stage": "quick_intent",
                            "route_confidence": 0.97,
                        },
                    }
                ],
            ),
            session_id="sid-wave",
        )

        self.assertEqual(result.status, "completed")
        call_names = [call[0] for call in invoker.calls]
        self.assertEqual(
            call_names,
            [
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
            ],
        )
        create_plan_args = invoker.calls[1][1]
        self.assertEqual(create_plan_args["skill_id"], "wave_hand")
        self.assertEqual(create_plan_args["parameters"], {"count": 2})
        chromie_intent = create_plan_args["chromie_intent"]
        self.assertEqual(chromie_intent["execution_mode"], "proposed")
        self.assertEqual(
            chromie_intent["execution_semantics"],
            "proposal_from_chromie",
        )
        self.assertTrue(chromie_intent["requires_runtime_validation"])
        self.assertEqual(chromie_intent["source_component"], "agent.capability")
        self.assertEqual(chromie_intent["route_stage"], "quick_intent")
        self.assertEqual(chromie_intent["route_confidence"], 0.97)

    async def test_live_perception_contract_reaches_planning_without_coordinates(
        self,
    ) -> None:
        invoker = _ArchitectureInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
            auto_confirm_sim=True,
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "inspect-1",
                        "skill_id": "soridormi.inspect_object",
                        "args": {"semantic_target": "phone"},
                        "metadata": {
                            "requires_live_perception": True,
                            "perception_dependency": "locate_target",
                            "perception_reason": "Find the phone before acting.",
                            # Deliberately not part of the contract; Chromie must
                            # not provide fabricated physical state to Soridormi.
                            "target_coordinates": {"x": 1.2, "y": 0.5},
                        },
                    }
                ],
            ),
            session_id="sid-inspect",
        )

        self.assertEqual(result.status, "completed")
        chromie_intent = invoker.calls[1][1]["chromie_intent"]
        self.assertTrue(chromie_intent["requires_live_perception"])
        self.assertEqual(chromie_intent["perception_dependency"], "locate_object")
        self.assertEqual(chromie_intent["physical_state_source"], "soridormi_runtime")
        self.assertTrue(
            chromie_intent["chromie_must_not_provide_physical_coordinates"]
        )
        self.assertTrue(chromie_intent["soridormi_owns_pose_estimation"])
        self.assertNotIn("target_coordinates", chromie_intent)
        self.assertNotIn("x", chromie_intent)
        self.assertNotIn("y", chromie_intent)

    async def test_post_interrupt_body_correction_cannot_auto_resume_in_sim(
        self,
    ) -> None:
        invoker = _ArchitectureInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
            auto_confirm_sim=True,
        )
        response, locked_request_ids = lock_post_interrupt_physical_resume(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "wave-after-stop",
                        "skill_id": "soridormi.wave_hand",
                        "args": {"count": 1},
                    }
                ],
                metadata={"post_interrupt_correction": True},
            )
        )

        self.assertEqual(locked_request_ids, ("wave-after-stop",))
        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await coordinator.execute(response, session_id="sid-locked")
        self.assertNotIn("soridormi.skill.create_plan", [c[0] for c in invoker.calls])

        confirmed = await coordinator.execute(
            response,
            session_id="sid-confirmed",
            confirmed_request_ids=set(locked_request_ids),
        )

        self.assertEqual(confirmed.status, "completed")
        self.assertIn("soridormi.skill.create_plan", [c[0] for c in invoker.calls])

    def test_old_provider_name_is_backward_compatible_alias(self) -> None:
        self.assertIs(SoridormiMcpSkillProvider, SoridormiNamedSkillAdapter)
        self.assertEqual(SoridormiNamedSkillAdapter.provider_id, "soridormi.mcp")


if __name__ == "__main__":
    unittest.main()
