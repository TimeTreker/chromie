from __future__ import annotations

import unittest

from agent.app.agents import AgentServices
from agent.app.runtime import AgentRuntime
from agent.app.schema import AgentRunRequest
from hardware.schema import ActionCommand as HardwareActionCommand
from hardware.service import HardwareService
from router.app.fallback import fallback_decision
from router.app.schema import RouteDecision, RouteRequest, finalize_decision


def _pose_route(request: RouteRequest) -> RouteDecision:
    return finalize_decision(
        RouteDecision(
            route="robot_action",
            agents=["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
            intent="turn_left",
            confidence=0.95,
            language="en-US",
            source="catalog",
        ),
        request,
        source="catalog",
    )


def _motion_route(request: RouteRequest) -> RouteDecision:
    return finalize_decision(
        RouteDecision(
            route="robot_action",
            agents=["motion_planner_agent", "safety_agent", "speaker_agent"],
            intent="move_closer_to_user",
            confidence=0.95,
            language="en-US",
            source="catalog",
        ),
        request,
        source="catalog",
    )


class ControlPlaneIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = AgentRuntime(AgentServices(ollama=None, use_llm=False, max_speak_chars=160))
        self.hardware = HardwareService()

    async def test_text_to_router_to_agent_to_mock_hardware(self) -> None:
        route_request = RouteRequest(sid="e2e-turn", text="turn left")
        decision = _pose_route(route_request)

        agent_request = AgentRunRequest(
            sid=route_request.sid,
            text=route_request.text,
            route_decision=decision.model_dump(mode="json"),
            context={
                "robot_state": {"emergency_stop": False},
                "allow_legacy_rule_agents": True,
            },
        )
        agent_result = await self.runtime.run(agent_request)

        self.assertEqual(agent_result.status, "ok")
        self.assertEqual(len(agent_result.actions), 1)
        self.assertEqual(agent_result.actions[0].type, "head.turn")
        self.assertEqual(agent_result.actions[0].params["yaw_degrees"], -20)

        command = HardwareActionCommand.model_validate(agent_result.actions[0].model_dump(mode="json"))
        hardware_result = await self.hardware.execute(command)

        self.assertEqual(hardware_result.status.value, "completed")
        self.assertEqual(self.hardware.driver.state().pose["head_yaw_degrees"], -20.0)
        self.assertIs(self.hardware.get_action(command.id), hardware_result)

    async def test_agent_blocks_motion_when_emergency_stop_is_active(self) -> None:
        decision = _motion_route(RouteRequest(sid="blocked", text="come here"))

        result = await self.runtime.run(
            AgentRunRequest(
                sid="blocked",
                text="come here",
                route_decision=decision.model_dump(mode="json"),
                context={
                    "robot_state": {"emergency_stop": True},
                    "allow_legacy_rule_agents": True,
                },
            )
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.actions, [])
        self.assertIn("robot_emergency_stop_active", result.reason or "")

    async def test_confirmation_required_motion_is_not_safe_to_auto_execute(self) -> None:
        decision = fallback_decision(RouteRequest(sid="confirm", text="move somewhere"))
        decision.route = "robot_action"
        decision.intent = "move_unknown"
        decision.agents = ["motion_planner_agent", "safety_agent", "speaker_agent"]

        result = await self.runtime.run(
            AgentRunRequest(
                sid="confirm",
                text="move somewhere",
                route_decision=decision.model_dump(mode="json"),
                context={
                    "robot_state": {"emergency_stop": False},
                    "allow_legacy_rule_agents": True,
                },
            )
        )

        self.assertTrue(result.requires_confirmation)
        self.assertEqual(len(result.actions), 1)
        self.assertTrue(result.actions[0].requires_confirmation)
        self.assertIn("confirm", result.speak_immediate[0].text.lower())

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
