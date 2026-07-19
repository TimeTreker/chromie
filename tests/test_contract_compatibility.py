from __future__ import annotations

import unittest

from agent.app.planner_contract import validate_planner_model_output
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
from shared.chromie_contracts.task_proposal import (
    TaskProposal,
    TaskProposalLedger,
    TaskProposalSummary,
)


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
        shared_proposal = TaskProposal.model_validate(
            service_request.route_decision.metadata["task_proposals"][0]
        )
        self.assertEqual(shared_proposal.task_type, "head.turn")
        self.assertEqual(shared_proposal.source, "quick_intent")
        self.assertEqual(shared_proposal.state, "advisory")

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


    def test_single_goal_step_ownership_must_be_model_authored(self) -> None:
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "steps": [
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }

        with self.assertRaisesRegex(ValueError, "source_goal_ids"):
            validate_planner_model_output(
                raw,
                planner_tier="fast",
                expected_goal_ids_for_turn=["goal-blink"],
            )

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

    def test_task_proposal_ledger_is_shared_and_rejects_low_level_metadata(self) -> None:
        ledger = TaskProposalLedger(
            strategy="contract-test",
            summary=TaskProposalSummary(
                proposal_count=1,
                states={"committed": 1},
                sources={"interaction_response": 1},
            ),
            proposals=[
                TaskProposal(
                    id="proposal-1",
                    source="interaction_response",
                    proposal_kind="skill",
                    task_type="task.execute_skill",
                    state="committed",
                    skill_id="soridormi.nod_yes",
                    request_id="nod-1",
                    effectful=True,
                )
            ],
        )

        parsed = TaskProposalLedger.model_validate(ledger.model_dump(mode="json"))
        self.assertEqual(parsed.proposals[0].state, "committed")

        missing = TaskProposal(
            id="proposal-missing-ability",
            source="deepthinking",
            proposal_kind="ability",
            task_type="ability.requested",
            state="missing_ability",
            ability_id="manipulation.pick_up_object",
            reason="No trusted grasping skill is available.",
        )
        self.assertEqual(missing.state, "missing_ability")
        self.assertEqual(missing.ability_id, "manipulation.pick_up_object")

        with self.assertRaisesRegex(ValueError, "forbidden low-level field"):
            TaskProposal(
                id="bad-proposal",
                source="test",
                proposal_kind="skill",
                task_type="task.execute_skill",
                state="committed",
                metadata={"joint_target": [0.1, 0.2]},
            )
