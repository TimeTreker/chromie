from __future__ import annotations

import unittest

from agent.app.cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    owner_approved_identity_context,
    owner_approved_personality_context,
)
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import (
    GoalAssociationResolver,
    GoalSegmentationModelOutput,
)
from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.plan import CanonicalPlan


class _Dummy:
    pass


class CognitiveIdentityContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mind = default_mind_profile().prompt_context(max_chars=5000)
        self.context = {
            "mind": self.mind,
            "active_goal_snapshots": [],
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": "goal-identity",
                        "description": "Answer the user's question about the robot's identity.",
                        "source_text": "你叫什么名字？",
                        "constraints": {},
                        "success_criteria": [],
                    }
                ],
            },
            "fast_plan_resolution": {
                "disposition": "escalate",
                "coverage": "uncertain",
                "steps": [],
            },
        }
        self.request = AgentRunRequest(
            sid="sid-identity",
            text="你叫什么名字？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat",
                intent="self_identity_question",
                confidence=0.95,
                source="llm",
            ),
            context=self.context,
            history=[],
        )

    def test_owner_approved_identity_projection_uses_active_profile(self) -> None:
        projected = owner_approved_identity_context(self.context)
        self.assertTrue(projected["owner_approved"])
        self.assertEqual(projected["identity"]["name"], "Chromie")
        self.assertEqual(projected["identity"]["age_description"], "6 years old")
        self.assertIn("identity_answer_guidance", projected["identity"])
        self.assertIn('"name":"Chromie"', bounded_identity_json(self.context))

    def test_owner_approved_personality_projection_uses_active_profile(self) -> None:
        projected = owner_approved_personality_context(self.context)
        self.assertTrue(projected["owner_approved"])
        self.assertIn("smart", projected["core_traits"])
        self.assertIn("six-year-old girl", projected["self_concept"])
        encoded = bounded_personality_json(self.context)
        self.assertIn('"answer_style"', encoded)
        self.assertIn('"internal_language_boundary"', encoded)

    def test_unapproved_or_missing_identity_is_not_prompt_evidence(self) -> None:
        self.assertEqual(owner_approved_identity_context({}), {})
        unapproved = {"mind": {**self.mind, "owner_approved": False}}
        self.assertEqual(owner_approved_identity_context(unapproved), {})
        self.assertEqual(bounded_identity_json(unapproved), "null")

    def test_goal_association_prompt_contains_authoritative_identity_section(self) -> None:
        resolver = GoalAssociationResolver(_Dummy())
        prompt = resolver._build_prompt(
            self.request,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn("Owner-approved Chromie identity JSON", prompt)
        self.assertIn('"name":"Chromie"', prompt)
        self.assertIn('"age_description":"6 years old"', prompt)
        self.assertIn(IDENTITY_SEMANTIC_CONTRACT, prompt)
        self.assertIn(PERSONALITY_SEMANTIC_CONTRACT, prompt)

    def test_fast_and_deep_planner_prompts_share_same_identity(self) -> None:
        fast = FastPlannerResolver(_Dummy(), _Dummy())
        fast_prompt = fast._prompt(
            self.request,
            [],
            response_schema={},
        )
        deep = DeepPlannerResolver(_Dummy(), _Dummy())
        deep_prompt = deep._prompt(
            self.request,
            [],
            feedback=[],
            response_schema={},
            expected_goal_ids=["goal-identity"],
        )
        for prompt in (fast_prompt, deep_prompt):
            self.assertIn("Owner-approved Chromie identity JSON", prompt)
            self.assertIn('"name":"Chromie"', prompt)
            self.assertIn('"age_description":"6 years old"', prompt)
            self.assertIn("generic robot category", prompt)
            self.assertIn("Owner-approved Personality Expression JSON", prompt)
            self.assertIn(PERSONALITY_SEMANTIC_CONTRACT, prompt)

    def test_response_composer_receives_identity_as_final_wording_evidence(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-identity",
            planner_tier="deep",
            disposition="respond",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-identity"],
            goal_summary="Answer the identity question.",
            response_text="我叫 Chromie，今年 6 岁。",
            steps=[],
        )
        request = self.request.model_copy(
            update={
                "context": {
                    **self.context,
                    "canonical_plan_resolution": plan.model_dump(mode="json"),
                }
            }
        )
        prompt = ResponseComposerResolver(_Dummy())._prompt(request, plan)
        self.assertIn("Owner-approved Chromie identity JSON", prompt)
        self.assertIn('"name":"Chromie"', prompt)
        self.assertIn('"age_description":"6 years old"', prompt)
        self.assertIn("identity.identity_answer_guidance", prompt)
        self.assertIn("Owner-approved Personality Expression JSON", prompt)
        self.assertIn(PERSONALITY_SEMANTIC_CONTRACT, prompt)


if __name__ == "__main__":
    unittest.main()
