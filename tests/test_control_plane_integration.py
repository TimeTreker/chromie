from __future__ import annotations

import unittest

from agent.app.agents import AgentServices
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest, RouteDecision
from hardware.schema import ActionCommand as HardwareActionCommand
from hardware.service import HardwareService


class ControlPlaneIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = AgentRuntime(AgentServices(ollama=None, use_llm=False, max_speak_chars=160))
        self.hardware = HardwareService()

    async def test_removed_phrase_agents_cannot_be_reenabled_by_request_context(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["robot_pose_controller_agent", "motion_planner_agent", "speaker_agent"],
            intent="legacy_phrase_request",
            confidence=0.99,
            language="en-US",
            source="catalog",
        )
        result = await self.runtime.run(
            AgentRunRequest(
                sid="removed-legacy-agents",
                text="turn left and come here",
                route_decision=decision,
                context={"allow_legacy_rule_agents": True},
            )
        )

        self.assertNotIn("robot_pose_controller_agent", self.runtime.available_agents())
        self.assertNotIn("motion_planner_agent", self.runtime.available_agents())
        self.assertEqual(result.actions, [])

    async def test_hardware_rejects_unsafe_namespace_and_emergency_stop(self) -> None:
        confirmation_required = HardwareActionCommand(
            id="confirmation-action",
            target="motion_controller",
            type="motion.move_relative",
            params={"x_m": 0.2},
            timeout_ms=100,
            requires_confirmation=True,
        )
        confirmation_result = await self.hardware.execute(confirmation_required)
        self.assertEqual(confirmation_result.status.value, "rejected")
        self.assertEqual(confirmation_result.error, "action requires confirmation")

        unsafe = HardwareActionCommand(
            id="unsafe-action",
            target="robot_pose_controller",
            type="unsafe.raw_motor",
            params={},
            timeout_ms=100,
        )
        unsafe_result = await self.hardware.execute(unsafe)
        self.assertEqual(unsafe_result.status.value, "rejected")

        await self.hardware.driver.emergency_stop()
        normal = HardwareActionCommand(
            id="stopped-action",
            target="robot_pose_controller",
            type="head.turn",
            params={"yaw_degrees": 10, "duration_ms": 1},
            timeout_ms=100,
        )
        stopped_result = await self.hardware.execute(normal)
        self.assertEqual(stopped_result.status.value, "rejected")

        await self.hardware.driver.reset_emergency_stop()
        resumed_result = await self.hardware.execute(normal.model_copy(update={"id": "resumed-action"}))
        self.assertEqual(resumed_result.status.value, "completed")
