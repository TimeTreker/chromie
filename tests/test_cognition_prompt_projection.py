from __future__ import annotations

import unittest

from shared.chromie_contracts.goal import GoalAssociationResolution
from agent.app.planner_contract import goal_association_prompt_projection
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_runtime.llm_diagnostics import cognition_text_reference


class CognitionPromptProjectionTests(unittest.TestCase):
    def test_goal_association_projection_excludes_all_diagnostic_metadata(self) -> None:
        resolution = GoalAssociationResolution(
            turn_id="turn-1",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-1",
                    description="Check the weather.",
                    source_text="Check the weather.",
                    success_criteria=["Weather is reported."],
                    metadata={
                        "responsibility_kind": "capability_dependent",
                        "initial_raw_output": "nested raw output",
                        "diagnostic": {"transcript": "hidden"},
                    },
                )
            ],
            confidence=0.9,
            reason_summary="A new grounded-information goal was identified.",
            metadata={
                "status": "resolved",
                "initial_raw_output": "top-level raw output",
                "repair_raw_output": "repair output",
            },
        )

        projection = resolution.prompt_projection()

        self.assertNotIn("metadata", projection)
        self.assertEqual(
            projection["new_goals"][0]["metadata"],
            {"responsibility_kind": "capability_dependent"},
        )
        rendered = repr(projection)
        self.assertNotIn("top-level raw output", rendered)
        self.assertNotIn("nested raw output", rendered)
        self.assertNotIn("repair output", rendered)


    def test_goal_association_projection_strips_nested_referent_metadata(self) -> None:
        resolution = GoalAssociationResolution(
            turn_id="turn-1",
            referent_updates=[
                {
                    "operation": "introduce",
                    "referent": {
                        "referent_id": "ref-place",
                        "entity_type": "location",
                        "canonical_value": "Neixiang",
                        "source_turn_id": "turn-1",
                        "metadata": {"raw_output": "hidden referent transcript"},
                    },
                    "confidence": 1.0,
                }
            ],
            confidence=1.0,
        )

        projection = resolution.prompt_projection()

        referent = projection["referent_updates"][0]["referent"]
        self.assertNotIn("metadata", referent)
        self.assertNotIn("hidden referent transcript", repr(projection))

    def test_partial_dictionary_projection_uses_the_same_nested_allowlist(self) -> None:
        projection = goal_association_prompt_projection(
            {
                "goal_association_resolution": {
                    "turn_id": "turn-1",
                    "referent_updates": [
                        {
                            "operation": "introduce",
                            "referent": {
                                "referent_id": "ref-place",
                                "entity_type": "location",
                                "canonical_value": "Neixiang",
                                "source_turn_id": "turn-1",
                                "metadata": {"scratchpad": "hidden"},
                            },
                            "confidence": 1.0,
                            "unknown_diagnostic": "hidden",
                        }
                    ],
                    "metadata": {"raw_output": "hidden"},
                }
            }
        )

        update = projection["referent_updates"][0]
        self.assertNotIn("unknown_diagnostic", update)
        self.assertNotIn("metadata", update["referent"])
        self.assertNotIn("hidden", repr(projection))

    def test_plan_projection_rejects_unbounded_semantic_payload(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-large",
            planner_tier="fast",
            disposition="respond",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-1"],
            goal_summary="Respond.",
            response_text="x" * 70_000,
            goal_satisfaction={
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-1"],
            },
        )

        with self.assertRaisesRegex(ValueError, "exceeds 65536 UTF-8 bytes"):
            plan.prompt_projection()

    def test_plan_projection_is_allowlisted_even_after_unvalidated_model_copy(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-1",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-1"],
            goal_summary="Blink once.",
            steps=[
                {
                    "step_id": "step-blink",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-1"],
                    "metadata": {"raw_output": "step transcript"},
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-1",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-blink"],
                    "satisfaction": {
                        "score": 1.0,
                        "status": "exact",
                        "satisfied_goal_ids": ["goal-1"],
                    },
                    "metadata": {"scratch": "outcome transcript"},
                }
            ],
            goal_satisfaction={
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-1"],
            },
            metadata={
                "plan_relation": "exact",
                "user_confirmation_required": False,
                "initial_raw_output": "plan transcript",
            },
        )
        # Pydantic documents that model_copy(update=...) does not validate the
        # replacement. The projection must remain safe even under that behavior.
        plan = plan.model_copy(
            update={
                "metadata": {
                    **plan.metadata,
                    "repair_raw_output": "x" * 20_000,
                }
            }
        )

        projection = plan.prompt_projection()

        self.assertEqual(
            projection["metadata"],
            {
                "plan_relation": "exact",
                "user_confirmation_required": False,
            },
        )
        self.assertNotIn("metadata", projection["steps"][0])
        self.assertNotIn("metadata", projection["goal_outcomes"][0])
        rendered = repr(projection)
        self.assertNotIn("plan transcript", rendered)
        self.assertNotIn("step transcript", rendered)
        self.assertNotIn("outcome transcript", rendered)
        self.assertNotIn("x" * 100, rendered)

    def test_cognition_reference_is_deterministic_and_contains_no_text(self) -> None:
        first = cognition_text_reference({"b": 2, "a": 1})
        second = cognition_text_reference({"a": 1, "b": 2})

        self.assertEqual(first, second)
        self.assertEqual(first["chars"], len('{"a":1,"b":2}'))
        self.assertTrue(first["digest"].startswith("sha256:"))
        self.assertNotIn('{"a":1', first["digest"])


if __name__ == "__main__":
    unittest.main()
