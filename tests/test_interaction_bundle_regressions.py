from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.goal_association import (
    GoalAssociationModelOutput,
    GoalAssociationResolver,
)
from agent.app.planner_contract import coordinated_action_goal_ids
from agent.app.response_composer import (
    ResponseComposerModelOutput,
    ResponseComposerResolver,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.social_attention import SocialAttentionPlan
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution


class ResponseComposerCoordinationRepairTests(unittest.TestCase):
    @staticmethod
    def _mixed_plan() -> CanonicalPlan:
        return CanonicalPlan.model_validate(
            {
                "plan_id": "plan-concurrent-performance",
                "planner_tier": "fast",
                "disposition": "mixed",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_ids": ["goal-move", "goal-song"],
                "goal_summary": "move while performing a song",
                "steps": [
                    {
                        "step_id": "step-move",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15.0},
                        "timing": "parallel",
                        "source_goal_ids": ["goal-move"],
                    }
                ],
                "goal_outcomes": [
                    {
                        "goal_id": "goal-move",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-move"],
                    },
                    {
                        "goal_id": "goal-song",
                        "disposition": "respond",
                        "coverage": "complete",
                        "response_text": "小星星，亮晶晶。",
                        "step_ids": [],
                    },
                ],
            }
        )

    def test_missing_references_are_copied_from_immutable_plan(self) -> None:
        plan = self._mixed_plan()
        raw = {
            "response_plan": {
                "immediate": {
                    "text": "小星星，亮晶晶。",
                    "speech_act": "perform",
                    "commitment_state": "none",
                    "must_not_claim_completion": True,
                    "covers_goal_ids": ["goal-song"],
                }
            },
            "social_attention_plan": {"decision": "none"},
            "lane_coordination": [
                {
                    "coordination_id": "coord-performance",
                    "lanes": ["speaking", "activity"],
                }
            ],
            "confidence": 1.0,
            "rationale": "The user requested overlap.",
        }

        normalized = ResponseComposerResolver._canonicalize_lane_coordination_payload(
            raw,
            plan=plan,
        )
        output = ResponseComposerModelOutput.model_validate(normalized)

        self.assertEqual(
            output.lane_coordination[0].activity_step_ids,
            ["step-move"],
        )
        assert output.response_plan.immediate is not None
        self.assertEqual(
            output.response_plan.immediate.coordination_id,
            "coord-performance",
        )
        self.assertEqual(
            output.response_plan.immediate.delivery_role,
            "performance",
        )

    def test_invalid_optional_social_group_is_pruned_not_turn_fatal(self) -> None:
        plan = self._mixed_plan()
        response_plan = ResponsePlan(
            immediate=ResponseStage(
                text="我准备好啦。",
                speech_act="affirmative",
                commitment_state="none",
                must_not_claim_completion=True,
                covers_goal_ids=["goal-move", "goal-song"],
            )
        )
        group = ResponseComposerModelOutput.model_validate(
            {
                "response_plan": response_plan.model_dump(mode="json"),
                "social_attention_plan": {"decision": "none"},
                "lane_coordination": [
                    {
                        "coordination_id": "coord-social-only",
                        "lanes": ["speaking", "social_attention"],
                    }
                ],
            }
        ).lane_coordination

        reconciled, kept, reasons = ResponseComposerResolver._reconcile_lane_coordination(
            response_plan=response_plan,
            lane_coordination=group,
            social_attention_plan=SocialAttentionPlan(decision="none"),
            plan=plan,
        )

        self.assertEqual(kept, [])
        self.assertTrue(reasons)
        assert reconciled.immediate is not None
        self.assertIsNone(reconciled.immediate.coordination_id)

    def test_malformed_social_express_is_not_silently_downgraded(self) -> None:
        with self.assertRaises(ValidationError):
            ResponseComposerModelOutput.model_validate(
                {
                    "response_plan": {
                        "final": {
                            "text": "好呀。",
                            "speech_act": "acknowledge",
                            "commitment_state": "completed",
                            "must_not_claim_completion": False,
                            "covers_goal_ids": ["goal-chat"],
                        }
                    },
                    "social_attention_plan": {
                        "decision": "express",
                        "reason": "The scene feels friendly.",
                    },
                }
            )

    def test_social_speech_adaptation_is_a_real_expression_member(self) -> None:
        output = ResponseComposerModelOutput.model_validate(
            {
                "response_plan": {
                    "final": {
                        "text": "好呀。",
                        "speech_act": "acknowledge",
                        "commitment_state": "completed",
                        "must_not_claim_completion": False,
                        "covers_goal_ids": ["goal-chat"],
                    }
                },
                "social_attention_plan": {
                    "decision": "express",
                    "purpose": "engagement",
                    "speech_expression": {
                        "mode": "adapt",
                        "style": "warm",
                        "pacing": "normal",
                        "reason": "Stay gently engaged without a target-dependent gesture.",
                    },
                },
            }
        )

        assert output.social_attention_plan is not None
        self.assertEqual(output.social_attention_plan.decision, "express")
        self.assertEqual(output.social_attention_plan.speech_expression.mode, "adapt")

    def test_failed_composition_reports_zero_provider_requests(self) -> None:
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="robot_action",
            fallback_reason="response composition invalid",
            metadata={"failure_stage": "response_composer"},
        )

        summary = VoiceAssistant._cognitive_resolution_summary(resolution)

        self.assertFalse(summary["interaction_response_constructed"])
        self.assertEqual(summary["provider_request_count"], 0)
        self.assertFalse(summary["provider_dispatch_possible"])



class GoalAndCoverageRegressionTests(unittest.TestCase):
    def test_single_new_goal_with_retained_context_requires_semantic_review(self) -> None:
        output = GoalAssociationModelOutput.model_validate(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "Perform several independently observable outcomes together.",
                        "responsibility_kind": "capability_dependent",
                    }
                ],
                "confidence": 1.0,
            }
        )

        triggers = GoalAssociationResolver._semantic_review_triggers(
            output,
            request=object(),  # the trigger uses no request fields
            candidate_goals=[{"goal_id": "prior-goal"}],
        )

        self.assertIn("single_new_goal_with_retained_context", triggers)

    def test_typed_resource_goal_always_requires_coverage_audit(self) -> None:
        goal_ids = coordinated_action_goal_ids(
            [
                {
                    "goal_id": "goal-resource",
                    "metadata": {"responsibility_kind": "capability_dependent"},
                    "resource_responsibility": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource": {
                            "kind": "information",
                            "description": "requested performance content",
                        },
                    },
                    "object": {"bindings": {}},
                }
            ]
        )

        self.assertEqual(goal_ids, {"goal-resource"})


if __name__ == "__main__":
    unittest.main()
