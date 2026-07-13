from __future__ import annotations

import asyncio
import unittest

from pydantic import ValidationError

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    GoalSatisfactionAssessment,
    PlanParameterResolution,
)


class FakeOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class Catalog:
    async def prompt_entries(self, **kwargs):
        return [
            CatalogCapability(
                capability_id="soridormi.blink_eyes",
                agent_id="capability_agent",
                description="Blink eyes",
                route="robot_action",
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
                route="robot_action",
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


def request(text: str) -> AgentRunRequest:
    return AgentRunRequest(
        sid="sid-pr5",
        text=text,
        language="zh-CN",
        route_decision=RouteDecision(
            route="robot_action",
            intent="semantic_capability_planning",
            confidence=0.0,
            source="llm",
        ),
        context={},
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
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=0.9,
                steps=[{"step_id": "s1", "skill_id": "soridormi.walk_forward", "args": {"duration_s": 3}}],
                parameter_resolutions=[{
                    "step_id": "s1",
                    "parameter": "duration_s",
                    "strategy": "ask_user",
                    "blocking": True,
                }],
                goal_satisfaction={"score": 1.0, "status": "exact"},
            )


class DeepPlannerGoalSatisfactionTests(unittest.TestCase):
    def test_low_consequence_default_and_exact_satisfaction_are_retained(self):
        raw = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.92,
            "goal_summary": "blink naturally",
            "steps": [{"step_id": "blink", "skill_id": "soridormi.blink_eyes", "args": {"count": 4}}],
            "parameter_resolutions": [{
                "step_id": "blink",
                "parameter": "count",
                "strategy": "safe_default",
                "value": 4,
                "confidence": 0.88,
                "rationale": "A small bounded count is reversible and low consequence.",
            }],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": [],
                "unmet_goal_ids": [],
                "unmet_requirements": [],
                "rationale": "The requested blink is fully covered.",
            },
        }
        plan = asyncio.run(DeepPlannerResolver(FakeOllama([raw]), Catalog()).resolve(request("眨眨眼睛。")))
        self.assertEqual(plan.parameter_resolutions[0].strategy, "safe_default")
        self.assertEqual(plan.goal_satisfaction.status, "exact")

    def test_material_missing_parameter_returns_specific_gap(self):
        raw = {
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.9,
            "goal_summary": "walk forward",
            "response_text": "你希望我往前走多久？",
            "steps": [],
            "unresolved": ["walking duration"],
            "parameter_resolutions": [{
                "step_id": "proposed-walk",
                "parameter": "duration_s",
                "strategy": "ask_user",
                "blocking": True,
                "confidence": 0.95,
                "rationale": "Duration materially changes motion exposure.",
            }],
            "goal_satisfaction": {
                "score": 0.4,
                "status": "partial",
                "unmet_requirements": ["walking duration"],
            },
        }
        plan = asyncio.run(DeepPlannerResolver(FakeOllama([raw]), Catalog()).resolve(request("往前走。")))
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.parameter_resolutions[0].strategy, "ask_user")

    def test_complete_plan_below_satisfaction_threshold_is_replanned(self):
        low = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.9,
            "steps": [{"step_id": "blink", "skill_id": "soridormi.blink_eyes", "args": {"count": 1}}],
            "goal_satisfaction": {"score": 0.8, "status": "substantial", "unmet_requirements": ["requested repeated blinking"]},
        }
        exact = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.92,
            "steps": [{"step_id": "blink", "skill_id": "soridormi.blink_eyes", "args": {"count": 4}}],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = FakeOllama([low, exact])
        plan = asyncio.run(
            DeepPlannerResolver(
                ollama,
                Catalog(),
                min_goal_satisfaction=0.95,
                max_replans=1,
            ).resolve(request("多眨几下眼睛。"))
        )
        self.assertEqual(plan.steps[0].args["count"], 4)
        self.assertIn("goal_satisfaction_below_threshold", ollama.prompts[1])

    def test_prompt_assigns_importance_reasoning_to_model(self):
        raw = {
            "disposition": "clarify",
            "coverage": "partial",
            "confidence": 0.8,
            "steps": [],
            "unresolved": ["duration"],
            "parameter_resolutions": [{"step_id": "x", "parameter": "duration_s", "strategy": "ask_user", "blocking": True}],
            "goal_satisfaction": {"score": 0.3, "status": "partial", "unmet_requirements": ["duration"]},
        }
        ollama = FakeOllama([raw])
        asyncio.run(DeepPlannerResolver(ollama, Catalog()).resolve(request("往前走。")))
        self.assertIn("low-consequence", ollama.prompts[0])
        self.assertIn("goal_satisfaction", ollama.prompts[0])


if __name__ == "__main__":
    unittest.main()
