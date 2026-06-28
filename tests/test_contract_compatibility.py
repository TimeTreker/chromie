from __future__ import annotations

import unittest

from agent.app.schema import AgentResult as ServiceAgentResult
from agent.app.schema import AgentRunRequest as ServiceAgentRequest
from hardware.schema import ActionCommand as HardwareActionCommand
from hardware.schema import ActionResult as HardwareActionResult
from orchestrator.schemas.action import ActionResult as OrchestratorActionResult
from orchestrator.schemas.agent import AgentRequest as OrchestratorAgentRequest
from orchestrator.schemas.agent import AgentResult as OrchestratorAgentResult
from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
from router.app.schema import RouteDecision, RouteRequest, finalize_decision
from shared.chromie_contracts.action import ActionCommand as SharedActionCommand
from shared.chromie_contracts.agent import AgentResult as SharedAgentResult
from shared.chromie_contracts.route import RouteDecision as SharedRouteDecision


class ContractCompatibilityTests(unittest.TestCase):
    def test_router_decision_survives_orchestrator_and_agent_round_trip(self) -> None:
        route_request = RouteRequest(sid="contract-route", text="turn left")
        router_decision = finalize_decision(
            RouteDecision(
                route="robot_action",
                agents=["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
                intent="turn_left",
                confidence=0.95,
                language="en-US",
                should_speak=True,
                actions=[
                    {
                        "target": "robot_pose_controller",
                        "type": "head.turn",
                        "params": {"yaw_degrees": -20, "duration_ms": 600},
                        "blocking": False,
                    }
                ],
                source="catalog",
            ),
            route_request,
            source="catalog",
        )

        orchestrator_decision = OrchestratorRouteDecision.model_validate(router_decision.model_dump(mode="json"))
        shared_decision = SharedRouteDecision.model_validate(router_decision.model_dump(mode="json"))
        self.assertTrue(orchestrator_decision.should_speak)
        self.assertEqual(orchestrator_decision.source, "catalog")
        self.assertEqual(orchestrator_decision.actions[0]["type"], "head.turn")
        self.assertEqual(shared_decision.source, "catalog")

        orchestrator_request = OrchestratorAgentRequest(
            sid="contract-route",
            text="turn left",
            route_decision=orchestrator_decision,
            context={"conversation_id": "test-conversation"},
            history=[{"role": "user", "text": "hello"}],
        )
        service_request = ServiceAgentRequest.model_validate(orchestrator_request.model_dump(mode="json"))
        self.assertEqual(service_request.history[0]["text"], "hello")
        self.assertEqual(service_request.route_decision.intent, "turn_left")
        self.assertEqual(
            service_request.route_decision.metadata["task_list"][0]["task_type"],
            "head.turn",
        )
        self.assertEqual(
            service_request.route_decision.metadata["task_list"][0]["source_stage"],
            "quick_intent",
        )

    def test_agent_result_survives_orchestrator_and_hardware_round_trip(self) -> None:
        service_result = ServiceAgentResult()
        action = service_result.add_action(
            "robot_pose_controller",
            "head.turn",
            params={"yaw_degrees": -20, "duration_ms": 1},
            timeout_ms=1200,
        )
        service_result.add_speak_immediate("Okay.")

        orchestrator_result = OrchestratorAgentResult.model_validate(service_result.model_dump(mode="json"))
        shared_result = SharedAgentResult.model_validate(service_result.model_dump(mode="json"))
        self.assertEqual(orchestrator_result.actions[0].id, action.id)
        self.assertEqual(orchestrator_result.speak_immediate[0].text, "Okay.")
        self.assertEqual(shared_result.actions[0].id, action.id)

        hardware_command = HardwareActionCommand.model_validate(
            orchestrator_result.actions[0].model_dump(mode="json")
        )
        shared_command = SharedActionCommand.model_validate(orchestrator_result.actions[0].model_dump(mode="json"))
        self.assertEqual(hardware_command.type, "head.turn")
        self.assertEqual(hardware_command.timeout_ms, 1200)
        self.assertEqual(shared_command.type, "head.turn")

    def test_hardware_result_is_parseable_by_orchestrator(self) -> None:
        hardware_result = HardwareActionResult(
            id="act_contract",
            status="completed",
            target="robot_pose_controller",
            type="head.turn",
            result={"ok": True},
        )

        parsed = OrchestratorActionResult.model_validate(hardware_result.model_dump(mode="json"))
        self.assertEqual(parsed.status, "completed")
        self.assertEqual(parsed.result, {"ok": True})
