from __future__ import annotations

import asyncio
import unittest

from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.execution_outcome import ExecutionOutcomeBundle
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import CanonicalPlan


class _ReplayClient:
    def __init__(
        self,
        association: GoalAssociationResolution,
        plan: CanonicalPlan,
    ) -> None:
        self.association = association
        self.plan = plan
        self.calls: list[str] = []

    async def resolve_goal_association(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append("association")
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append("fast")
        return self.plan

    async def resolve_deep_plan(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("the replay plan must fail before deep planning")

    async def compose_response_plan(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append("compose")
        raise AssertionError("the replay plan must fail before response composition")


class _NoExecutionRuntime:
    def __init__(self) -> None:
        self.ensure_calls: list[list[str]] = []

    async def ensure_skill_definitions(self, skill_ids):  # type: ignore[no-untyped-def]
        self.ensure_calls.append(list(skill_ids))
        raise AssertionError("chat must fail before physical capability validation")

    def skill_definition(self, skill_id):  # type: ignore[no-untyped-def]
        raise AssertionError(f"chat must not resolve physical skill {skill_id}")


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
        replay_plan = CanonicalPlan.model_validate(
            {
                "plan_id": "plan-replay",
                "planner_tier": "fast",
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 0.9,
                "goal_ids": ["goal-walk", "goal-blink"],
                "steps": [
                    {
                        "step_id": "walk",
                        "skill_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0, "speed": "normal"},
                        "source_goal_ids": ["goal-walk"],
                    },
                    {
                        "step_id": "blink",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "source_goal_ids": ["goal-blink"],
                    },
                ],
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
                "goal_satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-walk", "goal-blink"],
                },
            }
        )
        client = _ReplayClient(association, replay_plan)
        runtime = _NoExecutionRuntime()
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(runtime),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat", "robot_action"}),
            ),
        )

        social_context = {
            **state.snapshot(),
            "active_goal_snapshots": state.active_goal_snapshots(),
        }
        self.assertEqual(social_context["active_goal_snapshots"], [])
        resolution = asyncio.run(
            coordinator.resolve(
                object(),
                text="想啥呢？",
                sid="sid-social",
                route_decision=type(
                    "Decision",
                    (),
                    {
                        "route": "chat",
                        "intent": "social_exchange",
                        "language": "zh-CN",
                    },
                )(),
                context=social_context,
                history=state.get_history(),
                language="zh-CN",
            )
        )

        self.assertEqual(resolution.status, "error")
        self.assertEqual(resolution.metadata["failure_stage"], "authority_boundary")
        self.assertEqual(resolution.metadata["failure_class"], "route_effect_escalation")
        self.assertIsNone(resolution.interaction_response)
        self.assertEqual(client.calls, ["association", "fast"])
        self.assertEqual(runtime.ensure_calls, [])
        self.assertEqual(state.active_goal_snapshots(), [])


if __name__ == "__main__":
    unittest.main()
