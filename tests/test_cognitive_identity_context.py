from __future__ import annotations

from agent.app import planner_prompt as planner_prompt

from agent.app import goal_association_prompt as ga_prompt

import json
import unittest

from agent.app.clients.ollama_client import LayeredPrompt
from agent.app.cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    STABLE_MIND_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    bounded_stable_mind_json,
    owner_approved_identity_context,
    owner_approved_personality_context,
    owner_approved_stable_mind_context,
)
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.fast_planner import FastPlannerResolver
from agent.app.goal_association import GoalAssociationResolver
from agent.app.goal_association_contract import GoalSegmentationModelOutput
from tests.cognitive_work_test_support import cognitive_work_request
from shared.chromie_contracts.mind import (
    CustomerMindPersonalization,
    apply_customer_mind_personalization,
    default_mind_profile,
)


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
                        "description": "Answer the user's question about Chromie's identity.",
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
        self.request = cognitive_work_request(
            sid="sid-identity",
            text="你叫什么名字？",
            language="zh-CN",
            context=self.context,
            history=[],
        )

    def test_owner_approved_identity_projection_uses_active_profile(self) -> None:
        projected = owner_approved_identity_context(self.context)
        self.assertTrue(projected["owner_approved"])
        self.assertEqual(projected["identity"]["name"], "Chromie")
        self.assertEqual(projected["identity"]["age_description"], "6 years old")
        self.assertIn("identity_answer_guidance", projected["identity"])
        self.assertEqual(projected["identity"]["family_role"], "the family's secretary")
        self.assertNotIn("internal_components", projected["self_model"])
        self.assertIn('"name":"Chromie"', bounded_identity_json(self.context))

    def test_owner_approved_personality_projection_uses_active_profile(self) -> None:
        projected = owner_approved_personality_context(self.context)
        self.assertTrue(projected["owner_approved"])
        self.assertIn("smart", projected["core_traits"])
        self.assertIn("quick-witted", projected["core_traits"])
        self.assertIn("lively", projected["core_traits"])
        self.assertIn("six-year-old girl", projected["self_concept"])
        self.assertIn("robotic", projected["self_concept"])
        self.assertIn("biological human", projected["self_concept"])
        encoded = bounded_personality_json(self.context)
        self.assertIn('"answer_style"', encoded)
        self.assertIn('"internal_language_boundary"', encoded)

    def test_stable_mind_projection_keeps_worldview_values_independent(self) -> None:
        projected = owner_approved_stable_mind_context(self.context)
        self.assertTrue(projected["owner_approved"])
        self.assertIn("knowledge_boundary", projected["worldview"])
        self.assertIn("authority_boundary", projected["household_values"])
        self.assertIn("core_principles", projected)
        encoded = bounded_stable_mind_json(self.context)
        self.assertIn('"worldview"', encoded)
        self.assertIn('"household_values"', encoded)

    def test_customer_name_reaches_planner_without_factory_name_restoration(self) -> None:
        active = apply_customer_mind_personalization(
            default_mind_profile(),
            CustomerMindPersonalization(display_name="Nova"),
        )
        request = self.request.model_copy(
            update={
                "context": {
                    **self.context,
                    "mind": active.prompt_context(max_chars=5000),
                }
            }
        )

        prompt = planner_prompt.fast_plan_prompt(request, [], response_schema={})

        self.assertIn('"name":"Nova"', prompt)
        self.assertNotIn("social identity is Chromie", prompt)
        self.assertIn("Use the supplied active identity values", prompt)

    def test_unapproved_or_missing_identity_is_not_prompt_evidence(self) -> None:
        self.assertEqual(owner_approved_identity_context({}), {})
        unapproved = {"mind": {**self.mind, "owner_approved": False}}
        self.assertEqual(owner_approved_identity_context(unapproved), {})
        self.assertEqual(bounded_identity_json(unapproved), "null")

    def test_bounded_identity_and_personality_are_valid_json(self) -> None:
        identity_text = bounded_identity_json(self.context, max_chars=200)
        personality_text = bounded_personality_json(self.context, max_chars=200)

        self.assertLessEqual(len(identity_text), 200)
        self.assertLessEqual(len(personality_text), 200)
        identity = json.loads(identity_text)
        personality = json.loads(personality_text)
        self.assertEqual(identity["identity"]["name"], "Chromie")
        self.assertEqual(identity["identity"]["age_description"], "6 years old")
        self.assertIn("smart", personality["core_traits"])
        self.assertIn("quick-witted", personality["core_traits"])
        self.assertFalse(identity_text.endswith("..."))
        self.assertFalse(personality_text.endswith("..."))

    def test_goal_association_prompt_contains_authoritative_identity_section(self) -> None:
        resolver = GoalAssociationResolver(_Dummy())
        prompt = ga_prompt.build_prompt(
            self.request,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn("Owner-approved Chromie identity JSON", prompt)
        self.assertIn('"name":"Chromie"', prompt)
        self.assertIn('"age_description":"6 years old"', prompt)
        self.assertIn("acting/perceiving/body ownership", prompt)
        self.assertIn("social identity", prompt)
        self.assertIn("biological-human claim", prompt)
        self.assertNotIn("human-child kind", prompt)
        self.assertIn("personality expression never create an extra Goal", prompt)
        self.assertNotIn("Owner-approved Personality Expression JSON", prompt)
        layered = ga_prompt.layered_prompt(
            self.request,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertLessEqual(
            len(layered.render())
            + len(ga_prompt.system_prompt(GoalSegmentationModelOutput)),
            11_264,
        )

    def test_fast_and_deep_planner_prompts_share_same_identity(self) -> None:
        fast = FastPlannerResolver(_Dummy(), _Dummy())
        fast_prompt = planner_prompt.fast_plan_prompt(
            self.request,
            [],
            response_schema={},
        )
        deep = DeepPlannerResolver(_Dummy(), _Dummy())
        deep_prompt = planner_prompt.deep_plan_prompt(
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
            self.assertIn("six-year-old girl", prompt)
            self.assertIn("robotic", prompt)
            self.assertIn("biological", prompt)
            self.assertIn("Owner-approved Personality Expression JSON", prompt)
            self.assertIn(PERSONALITY_SEMANTIC_CONTRACT, prompt)
            self.assertIn("Owner-approved Stable Mind worldview/values JSON", prompt)
            self.assertIn(STABLE_MIND_SEMANTIC_CONTRACT, prompt)

    def test_cognitive_role_layers_stay_stable_when_only_turn_text_changes(
        self,
    ) -> None:
        changed = self.request.model_copy(update={"text": "第二个问题"})
        goal = GoalAssociationResolver(_Dummy())
        fast = FastPlannerResolver(_Dummy(), _Dummy())
        deep = DeepPlannerResolver(_Dummy(), _Dummy())
        pairs = (
            (
                ga_prompt.layered_prompt(
                    self.request,
                    [],
                    output_type=GoalSegmentationModelOutput,
                ),
                ga_prompt.layered_prompt(
                    changed,
                    [],
                    output_type=GoalSegmentationModelOutput,
                ),
                ga_prompt.system_prompt(GoalSegmentationModelOutput),
            ),
            (
                planner_prompt.fast_layered_prompt(self.request, [], response_schema={}),
                planner_prompt.fast_layered_prompt(changed, [], response_schema={}),
                planner_prompt.fast_system_prompt(),
            ),
            (
                planner_prompt.deep_layered_prompt(
                    self.request,
                    [],
                    feedback=[],
                    response_schema={},
                    expected_goal_ids=["goal-identity"],
                ),
                planner_prompt.deep_layered_prompt(
                    changed,
                    [],
                    feedback=[],
                    response_schema={},
                    expected_goal_ids=["goal-identity"],
                ),
                planner_prompt.deep_system_prompt(),
            ),
        )

        for first, second, system in pairs:
            self.assertIsInstance(first, LayeredPrompt)
            self.assertEqual(
                first.stable_layer_items(system=system),
                second.stable_layer_items(system=system),
            )
            self.assertNotEqual(first.volatile_suffix, second.volatile_suffix)
            self.assertLess(
                second.render().index("Owner-approved Chromie identity JSON"),
                second.render().index("第二个问题"),
            )

    def test_fast_capability_layer_contains_every_contiguous_rendered_section(self) -> None:
        context = dict(self.context)
        context["agent_skill_disclosure"] = {
            "agent_role": "fast_planner",
            "projections": [
                {
                    "agent_skill_id": "chromie.test-method",
                    "version": "1.0.0",
                    "projection": "fast_planner",
                    "content": "Use the supplied evidence without inventing a result.",
                    "relevant_goal_ids": ["goal-identity"],
                }
            ],
        }
        context["planner_auxiliary_social_context"] = {
            "eligible_capabilities": [],
            "target_evidence": {"available": False},
            "social_interaction_style": {},
            "recent_auxiliary_behavior_evidence": [],
            "max_activities": 0,
        }
        request = self.request.model_copy(update={"context": context})

        prompt = planner_prompt.fast_layered_prompt(
            request,
            [],
            response_schema={},
        )

        capability_layer = "".join(prompt.capability_contract)
        self.assertIn("Owner-approved passive Agent Skill", capability_layer)
        self.assertIn("No trusted semantic target evidence", capability_layer)
        self.assertIn("No auxiliary candidates; use []", capability_layer)
        self.assertIn("Executable common capability catalog JSON", capability_layer)


if __name__ == "__main__":
    unittest.main()
