from __future__ import annotations

import asyncio
import unittest
from functools import partial

from pydantic import ValidationError

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver
from agent.app.planner_fast_validation import qualify_fast_canonical_plan
from benchmarks.datasets.fast_planner_daily_life.qualification import declared_ability_needs
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from tests.cognitive_work_test_support import cognitive_work_request
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    GoalSatisfactionAssessment,
    PlanParameterResolution,
)
from tests.model_fakes import ScriptedOllama

FakeOllama = partial(ScriptedOllama, shape=declared_ability_needs)


class Catalog:
    async def prompt_entries(self, **kwargs):
        return [
            CatalogCapability(
                capability_id="soridormi.blink_eyes",
                agent_id="capability_agent",
                description="Blink eyes",
                effects=["physical_motion"],
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                input_schema={
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 10}},
                    "required": ["count"],
                },
            ),
            CatalogCapability(
                capability_id="soridormi.walk_forward",
                agent_id="capability_agent",
                description="Walk forward",
                effects=["physical_motion"],
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                input_schema={
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "minimum": 0.1}},
                    "required": ["duration_s"],
                },
            ),
        ]


def request(text: str, *, goal_ids: list[str]) -> CognitiveWorkRequest:
    return cognitive_work_request(
        sid="sid-pr5",
        text=text,
        language="zh-CN",
        context={
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {"goal_id": goal_id, "description": f"Goal {goal_id}"} for goal_id in goal_ids
                ],
            }
        },
        history=[],
    )


class GoalSatisfactionContractTests(unittest.TestCase):
    def test_safe_default_requires_concrete_value(self):
        with self.assertRaises(ValidationError):
            PlanParameterResolution(
                step_id="s1",
                parameter="count",
                strategy="safe_default",
                value=None,
            )

    def test_ask_user_is_blocking_and_has_no_value(self):
        item = PlanParameterResolution(
            step_id="s1",
            parameter="duration_s",
            strategy="ask_user",
            blocking=True,
            rationale="Duration materially changes the motion.",
        )
        self.assertTrue(item.blocking)

    def test_exact_satisfaction_cannot_have_unmet_requirements(self):
        with self.assertRaises(ValidationError):
            GoalSatisfactionAssessment(
                score=1.0,
                status="exact",
                unmet_requirements=["blink count"],
            )

    def test_execute_plan_cannot_retain_blocking_gap(self):
        with self.assertRaises(ValidationError):
            CanonicalPlan(
                plan_id="p",
                planner_tier="fast",
                disposition="execute",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-walk"],
                steps=[
                    {
                        "step_id": "s1",
                        "capability_id": "soridormi.walk_forward",
                        "args": {"duration_s": 3},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-walk"],
                    }
                ],
                parameter_resolutions=[
                    {
                        "step_id": "s1",
                        "parameter": "duration_s",
                        "strategy": "ask_user",
                        "blocking": True,
                        "source_goal_ids": ["goal-walk"],
                    }
                ],
                goal_satisfaction={"score": 1.0, "status": "exact"},
            )


class PlannerGoalSatisfactionTests(unittest.TestCase):
    def test_low_consequence_default_and_exact_satisfaction_are_retained(self):
        raw = {
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": [
                        "blink"
                    ],
                    "unresolved": [],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": [],
                        "unmet_goal_ids": [],
                        "unmet_requirements": [],
                        "rationale": "The requested blink is fully covered."
                    }
                }
            },
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.92,
            "goal_ids": ["goal-blink"],
            "goal_summary": "blink naturally",
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 4},
                    "depends_on": [],
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "parameter_resolutions": [
                {
                    "step_id": "blink",
                    "parameter": "count",
                    "strategy": "safe_default",
                    "value": 4,
                    "confidence": 0.88,
                    "rationale": "A small bounded count is reversible and low consequence.",
                }
            ],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": [],
                "unmet_goal_ids": [],
                "unmet_requirements": [],
                "rationale": "The requested blink is fully covered.",
            },
        }
        plan = asyncio.run(
            FastPlannerResolver(FakeOllama([raw]), Catalog()).resolve(
                request("眨眨眼睛。", goal_ids=["goal-blink"])
            )
        )
        self.assertEqual(plan.parameter_resolutions[0].strategy, "safe_default")
        self.assertEqual(plan.goal_satisfaction.status, "exact")

    def test_material_missing_parameter_returns_specific_gap(self):
        raw = {
            "goal_outcomes": {
                "goal-walk": {
                    "disposition": "clarify",
                    "coverage": "partial",
                    "step_ids": [],
                    "unresolved": [
                        "walking duration"
                    ],
                    "satisfaction": {
                        "score": 0.4,
                        "status": "partial",
                        "unmet_goal_ids": ["goal-walk"],
                        "unmet_requirements": [
                            "walking duration"
                        ]
                    }
                }
            },
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.9,
            "goal_ids": ["goal-walk"],
            "goal_summary": "walk forward",
            "steps": [],
            "unresolved": ["walking duration"],
            "parameter_resolutions": [
                {
                    "step_id": "proposed-walk",
                    "parameter": "duration_s",
                    "strategy": "ask_user",
                    "blocking": True,
                    "source_goal_ids": ["goal-walk"],
                    "confidence": 0.95,
                    "rationale": "Duration materially changes motion exposure.",
                }
            ],
            "goal_satisfaction": {
                "score": 0.4,
                "status": "partial",
                "unmet_goal_ids": ["goal-walk"],
                "unmet_requirements": ["walking duration"],
            },
        }
        plan = asyncio.run(
            FastPlannerResolver(FakeOllama([raw]), Catalog()).resolve(
                request("往前走。", goal_ids=["goal-walk"])
            )
        )
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.parameter_resolutions[0].strategy, "ask_user")

    def test_complete_plan_below_satisfaction_threshold_fails_closed_without_replan(self):
        low = {
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": [
                        "blink"
                    ],
                    "unresolved": [],
                    "satisfaction": {
                        "score": 0.6,
                        "status": "partial",
                        "unmet_requirements": [
                            "requested repeated blinking"
                        ]
                    }
                }
            },
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.9,
            "goal_ids": ["goal-blink"],
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "depends_on": [],
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_satisfaction": {
                "score": 0.6,
                "status": "partial",
                "unmet_requirements": ["requested repeated blinking"],
            },
        }
        exact = {
            "goal_outcomes": {
                "goal-blink": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": [
                        "blink"
                    ],
                    "unresolved": [],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact"
                    }
                }
            },
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.92,
            "goal_ids": ["goal-blink"],
            "steps": [
                {
                    "step_id": "blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 4},
                    "depends_on": [],
                    "source_goal_ids": ["goal-blink"],
                }
            ],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = FakeOllama([low, exact])
        plan = asyncio.run(
            FastPlannerResolver(
                ollama,
                Catalog(),
            ).resolve(request("多眨几下眼睛。", goal_ids=["goal-blink"]))
        )
        # Below the commitment bar the Planner itself judged the Goal unmet: an honest
        # limitation, never a second planning pass.
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(plan.disposition, "unavailable")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["reason"], "goal_satisfaction_below_commitment")
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        # Live 2026-10-12 (run 4): a re-entry limitation with no result need let Social
        # Cognition stay silent. Each limited Goal carries the result SC must say now.
        from shared.chromie_contracts.social_cognition import SocialCognitionRequest, must_say_now_need_ids
        [need] = plan.communication_needs
        self.assertEqual((need.owner, need.kind, need.source_goal_ids), ("planner", "result", ["goal-blink"]))
        self.assertEqual(need.facts["disposition"], "unavailable")
        social = SocialCognitionRequest(
            request_id="sc:limitation", trigger="work_state", source_refs=[plan.plan_id],
            goal_ids=plan.goal_ids, responsibilities=request("多眨几下眼睛。", goal_ids=["goal-blink"]).responsibilities,
            communication_needs=plan.communication_needs,
        )
        self.assertEqual(must_say_now_need_ids(social), {need.need_id})

    def test_complete_accounting_can_truthfully_report_an_unsatisfied_goal(self):
        plan = CanonicalPlan.model_validate(
            {
                "plan_id": "plan-failed-result",
                "communication_needs": [{"need_id": "failed-weather", "owner": "planner",
                    "kind": "answer", "reference_id": "plan-failed-result",
                    "source_goal_ids": ["goal-weather"],
                    "facts": {"execution_status": "failed"}}],
                "planner_tier": "fast",
                "disposition": "respond",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_ids": ["goal-weather"],
                "steps": [],
                "goal_outcomes": [
                    {
                        "goal_id": "goal-weather",
                        "disposition": "respond",
                        "coverage": "complete",
                        "step_ids": [],
                        "satisfaction": {
                            "score": 0.0,
                            "status": "unsatisfied",
                            "satisfied_goal_ids": [],
                            "unmet_goal_ids": ["goal-weather"],
                            "unmet_requirements": ["A weather result is unavailable."],
                            "rationale": "Trusted execution evidence records failure.",
                        },
                    }
                ],
                "goal_satisfaction": {
                    "score": 0.0,
                    "status": "unsatisfied",
                    "satisfied_goal_ids": [],
                    "unmet_goal_ids": ["goal-weather"],
                    "unmet_requirements": ["A weather result is unavailable."],
                    "rationale": "The Planner accounted for the Goal without claiming success.",
                },
            }
        )

        self.assertEqual(plan.coverage, "complete")
        self.assertEqual(plan.goal_satisfaction.status, "unsatisfied")
        self.assertTrue(
            qualify_fast_canonical_plan(
                plan,
                capability_payload=[],
                expected_goal_ids_for_turn=["goal-weather"],
                authoritative_goals=[],
                evidence_reentry_goal_ids={"goal-weather"},
                nonfulfilling_response_goal_ids={"goal-weather"},
            ).accepted
        )

    def test_prompt_assigns_importance_reasoning_to_model(self):
        raw = {
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.8,
            "goal_ids": ["goal-walk"],
            "steps": [],
            "unresolved": ["duration"],
            "parameter_resolutions": [
                {
                    "step_id": "x",
                    "parameter": "duration_s",
                    "strategy": "ask_user",
                    "blocking": True,
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            "goal_satisfaction": {
                "score": 0.3,
                "status": "partial",
                "unmet_requirements": ["duration"],
            },
        }
        ollama = FakeOllama([raw])
        asyncio.run(
            FastPlannerResolver(ollama, Catalog()).resolve(
                request("往前走。", goal_ids=["goal-walk"])
            )
        )
        self.assertIn("Satisfaction measures prospective Goal fulfillment", ollama.prompts[0][0])
        self.assertIn("minimum_goal_satisfaction", ollama.prompts[0][0])


if __name__ == "__main__":
    unittest.main()
