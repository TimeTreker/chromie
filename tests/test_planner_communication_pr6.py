from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.main import app
from orchestrator.clients.agent_client import AgentClient
from orchestrator.runtime.cognitive_runtime import GoalDrivenRuntimeCoordinator
from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.plan import (
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerCompleteResponseAct,
    FastPlannerProgressAct,
)


class PlannerOwnedCommunicativeActivityTests(unittest.TestCase):
    def test_fast_activity_owns_exact_text_and_truth_stage(self) -> None:
        activity = FastPlannerProgressAct(
            activity_id="weather-progress",
            role="progress",
            text="我看看。",
            progress_kind="check_information",
            speech_act="acknowledge_and_check",
            source_responsibility_refs=["weather"],
        )

        self.assertEqual(activity.text, "我看看。")
        self.assertEqual(activity.truth_stage, "pre_evidence")
        self.assertEqual(activity.evidence_refs, [])

    def test_pre_evidence_activity_cannot_claim_evidence_provenance(self) -> None:
        with self.assertRaises(ValidationError):
            FastPlannerProgressAct(
                activity_id="weather-progress",
                role="progress",
                text="我看看。",
                progress_kind="check_information",
                source_responsibility_refs=["weather"],
                evidence_refs=["weather-evidence"],
            )

    def test_post_evidence_response_requires_exact_evidence_refs(self) -> None:
        with self.assertRaises(ValidationError):
            FastPlannerCompleteResponseAct(
                activity_id="weather-answer",
                role="complete_response",
                text="上午不会下雨。",
                speech_act="answer",
                truth_stage="post_evidence",
                source_responsibility_refs=["weather"],
            )

    def test_fast_plan_binds_planner_text_into_canonical_activity(self) -> None:
        advance = FastPlannerAdvance(
            turn_id="turn-greeting",
            disposition="respond",
            coverage="complete",
            covered_responsibility_refs=["greeting"],
            activities=[
                FastPlannerCompleteResponseAct(
                    activity_id="greeting-response",
                    role="complete_response",
                    text="你好呀！",
                    speech_act="greeting",
                    source_responsibility_refs=["greeting"],
                )
            ],
            confidence=0.98,
            metadata={"presentation_commit_id": "commit-greeting"},
        )
        association = GoalAssociationResolution(
            turn_id="turn-greeting",
            resolution_status="resolved",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-greeting",
                    description="Respond to the greeting.",
                    source_text="你好",
                    source_responsibility_refs=["greeting"],
                )
            ],
            confidence=0.98,
        )

        plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(
            advance=advance,
            association=association,
            user_text="你好",
        )

        self.assertEqual(plan.response_text, "你好呀！")
        self.assertEqual(plan.communicative_acts[0].text, "你好呀！")
        self.assertEqual(plan.communicative_acts[0].source_goal_ids, ["goal-greeting"])
        self.assertEqual(
            plan.metadata["presentation_commit_id"], "commit-greeting"
        )

    def test_fast_activity_order_projects_after_work_speech_to_final_phase(self) -> None:
        advance = FastPlannerAdvance(
            turn_id="turn-nod-greeting",
            disposition="execute",
            coverage="complete",
            covered_responsibility_refs=["nod", "greeting"],
            activities=[
                FastPlannerCapabilityActivity(
                    activity_id="nod-twice",
                    role="capability",
                    capability_id="soridormi.nod_yes",
                    args={"count": 2},
                    timing="sequential",
                    source_responsibility_refs=["nod"],
                ),
                FastPlannerCompleteResponseAct(
                    activity_id="greeting-response",
                    role="complete_response",
                    text="你好",
                    speech_act="greeting",
                    timing="sequential",
                    source_responsibility_refs=["greeting"],
                ),
            ],
            confidence=1.0,
            metadata={"presentation_commit_id": "commit-nod-greeting"},
        )
        association = GoalAssociationResolution(
            turn_id="turn-nod-greeting",
            resolution_status="resolved",
            new_goals=[
                SemanticGoal(
                    goal_id="goal-nod",
                    description="Nod twice.",
                    source_text="点两下头",
                    source_responsibility_refs=["nod"],
                ),
                SemanticGoal(
                    goal_id="goal-greeting",
                    description="Say hello.",
                    source_text="说声你好",
                    source_responsibility_refs=["greeting"],
                ),
            ],
            confidence=1.0,
        )

        plan = GoalDrivenRuntimeCoordinator._canonical_plan_from_fast_advance(
            advance=advance,
            association=association,
            user_text="点两下头，再跟我说声你好。",
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(plan.communicative_acts[0].delivery_phase, "final")
        self.assertEqual(plan.communicative_acts[0].source_goal_ids, ["goal-greeting"])

    def test_duplicate_semantic_endpoints_are_removed(self) -> None:
        paths = {route.path for route in app.routes}
        self.assertNotIn("/compose-response-plan", paths)
        self.assertNotIn("/communicative-acts/realize", paths)
        self.assertNotIn("/tool-result/interpret", paths)
        self.assertNotIn("/fast-" + "first-response", paths)
        self.assertFalse(hasattr(AgentClient, "compose_response_plan"))
        self.assertFalse(hasattr(AgentClient, "realize_communicative_acts"))
        self.assertFalse(hasattr(AgentClient, "interpret_tool_result"))
        self.assertFalse(
            hasattr(AgentClient, "resolve_fast_" + "first_response")
        )


if __name__ == "__main__":
    unittest.main()
