from __future__ import annotations

import unittest

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.execution_outcome import ExecutionOutcomeBundle
from shared.chromie_contracts.goal import GoalAssociationResolution
from agent.app.goal_association import GoalAssociationResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.interaction import InteractionResponse


class VoiceLogGoalReplayRegressionTests(unittest.TestCase):
    def test_completed_motion_goals_cannot_replay_on_following_social_turn(self) -> None:
        state = ConversationStateManager(
            base_conversation_id="voice-log-goal-replay",
            task_store_enabled=False,
        )
        state.apply_goal_association_resolution(
            {
                "turn_id": "turn-motion",
                "new_goals": [
                    {
                        "goal_id": "goal-walk",
                        "description": "Walk forward for fifteen seconds.",
                        "source_text": "往前走十五秒。",
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "Blink twice.",
                        "source_text": "眨两下眼睛。",
                    },
                ],
                "confidence": 0.95,
            },
            sid="sid-motion",
            user_text="往前走十五秒，同时眨两下眼睛。",
            route="robot_action",
            intent="compound_action",
            atomic=True,
        )
        state.record_agent_result(
            "sid-motion",
            InteractionResponse(
                interaction_id="interaction-motion",
                skills=[
                    {
                        "request_id": "request-walk",
                        "skill_id": "soridormi.walk_forward",
                        "metadata": {
                            "source_goal_ids": ["goal-walk"],
                            "canonical_plan_id": "plan-motion",
                            "canonical_plan_fingerprint": "m" * 64,
                        },
                    },
                    {
                        "request_id": "request-blink",
                        "skill_id": "soridormi.blink_eyes",
                        "metadata": {
                            "source_goal_ids": ["goal-blink"],
                            "canonical_plan_id": "plan-motion",
                            "canonical_plan_fingerprint": "m" * 64,
                        },
                    },
                ],
                metadata={
                    "planning_result": "composed_plan",
                    "turn_id": "turn-motion",
                    "canonical_plan_id": "plan-motion",
                    "canonical_plan_fingerprint": "m" * 64,
                    "canonical_plan": {
                        "plan_id": "plan-motion",
                        "planner_tier": "fast",
                        "disposition": "execute",
                        "coverage": "complete",
                        "confidence": 0.95,
                        "goal_ids": ["goal-walk", "goal-blink"],
                        "steps": [],
                        "goal_outcomes": [
                            {
                                "goal_id": "goal-walk",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["walk"],
                            },
                            {
                                "goal_id": "goal-blink",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["blink"],
                            },
                        ],
                    },
                },
            ),
        )
        self.assertTrue(
            state.update_pending_task_status_for_request_id(
                request_id="request-walk",
                status="completed",
            )
        )
        self.assertTrue(
            state.update_pending_task_status_for_request_id(
                request_id="request-blink",
                status="completed",
            )
        )
        # Request completion is Work truth only.  Close the responsibilities
        # only after exact execution evidence has crossed the explicit
        # Responsibility reconciliation boundary.
        self.assertEqual(
            {item["responsibility_status"] for item in state.active_goal_snapshots()},
            {"open"},
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-motion",
            turn_id="turn-motion",
            interaction_id="interaction-motion",
            canonical_plan_id="plan-motion",
            canonical_plan_fingerprint="m" * 64,
            canonical_goal_ids=["goal-walk", "goal-blink"],
            aggregate_status="completed",
            evidence=[
                {
                    "evidence_id": "evidence-walk",
                    "request_id": "request-walk",
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                    "status": "completed",
                },
                {
                    "evidence_id": "evidence-blink",
                    "request_id": "request-blink",
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "source_goal_ids": ["goal-blink"],
                    "status": "completed",
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "status": "completed",
                    "step_ids": ["walk"],
                    "evidence_ids": ["evidence-walk"],
                    "completed_step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-blink",
                    "status": "completed",
                    "step_ids": ["blink"],
                    "evidence_ids": ["evidence-blink"],
                    "completed_step_ids": ["blink"],
                },
            ],
        )
        state.record_execution_outcome_bundle(bundle, sid="sid-motion")
        state.reconcile_execution_outcome_responsibilities(bundle, sid="sid-motion")

        self.assertEqual(state.active_goal_snapshots(), [])
        terminal_by_goal = {
            str((item.get("semantic_goal") or {}).get("goal_id")): (
                item.get("semantic_goal") or {}
            ).get("responsibility_status")
            for item in state.snapshot()["task_contexts"]
        }
        self.assertEqual(
            terminal_by_goal,
            {"goal-walk": "satisfied", "goal-blink": "satisfied"},
        )

        association = GoalAssociationResolution.model_validate(
            {
                "turn_id": "turn-social",
                "associations": [
                    {
                        "association_id": "reuse-walk",
                        "relationship": "continue",
                        "target_goal_ids": ["goal-walk"],
                        "confidence": 0.9,
                    },
                    {
                        "association_id": "reuse-blink",
                        "relationship": "continue",
                        "target_goal_ids": ["goal-blink"],
                        "confidence": 0.9,
                    },
                ],
                "confidence": 0.9,
                "metadata": {"status": "resolved"},
            }
        )
        social_context = {
            **state.snapshot(),
            "active_goal_snapshots": state.active_goal_snapshots(),
        }
        self.assertEqual(social_context["active_goal_snapshots"], [])

        # Goal Association is the semantic owner that may reconnect a new turn to
        # retained Goals. Once the completed motion Goals leave the active candidate
        # set, a model-shaped attempt to continue them must be rejected there; a
        # downstream route label is not an effect-safety fallback.
        request = AgentRunRequest(
            sid="sid-social",
            text="想啥呢？",
            route_decision=RouteDecision(
                route="chat",
                intent="social_exchange",
                language="zh-CN",
            ),
            language="zh-CN",
            context=social_context,
            history=state.get_history(),
        )
        validated = GoalAssociationResolver(object())._validate(
            association,
            candidate_goals=[],
            request=request,
        )

        self.assertEqual(validated.resolution_status, "needs_clarification")
        self.assertEqual(validated.associations, [])
        self.assertEqual(validated.new_goals, [])
        self.assertEqual(
            [item["reason"] for item in validated.metadata["rejected_associations"]],
            ["unknown_target_goal", "unknown_target_goal"],
        )



if __name__ == "__main__":
    unittest.main()
