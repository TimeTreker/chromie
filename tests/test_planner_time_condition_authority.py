from __future__ import annotations

from agent.app.planner_model_contract import (
    PlannerModelOutput,
    materialize_planner_output,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    GoalSatisfactionAssessment,
    PlannedGoalTimeCondition,
)
from shared.chromie_contracts.semantic_task import SemanticGoal


def _satisfaction(goal_id: str) -> GoalSatisfactionAssessment:
    return GoalSatisfactionAssessment(
        score=1.0,
        status="exact",
        satisfied_goal_ids=[goal_id],
        unmet_goal_ids=[],
        unmet_requirements=[],
        rationale="The executable plan covers the current work.",
    )


def test_planner_model_time_condition_is_materialized_with_host_plan_identity() -> None:
    output = PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.9,
            "goal_summary": "Keep the running work live until a future check.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "step-read",
                    "capability_id": "example.safe_read",
                    "args": {},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-1"],
                    "reuse_activity_id": "",
                    "reason_summary": "Start the current observable work.",
                }
            ],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "time_conditions": [
                {
                    "goal_id": "goal-1",
                    "due_at_ms": 2_000,
                    "reason_code": "recheck_running_work",
                }
            ],
            "goal_outcomes": {},
            "goal_satisfaction": _satisfaction("goal-1").model_dump(mode="json"),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
    )
    raw = materialize_planner_output(
        output,
        planner_tier="fast",
        plan_id="plan-1",
        expected_goal_ids_for_turn=["goal-1"],
        goal_summary_fallback="fallback",
    )
    plan = CanonicalPlan.model_validate(raw)
    assert len(plan.time_conditions) == 1
    assert plan.time_conditions[0].condition_id == "plan-1:time:0"
    assert plan.time_conditions[0].goal_id == "goal-1"
    assert plan.time_conditions[0].due_at_ms == 2_000


def test_conversation_state_binds_planner_time_condition_to_original_responsibility() -> None:
    manager = ConversationStateManager(task_store_enabled=False)
    goal = SemanticGoal(
        goal_id="goal-1",
        description="Keep monitoring the running work.",
        source_text="Keep an eye on it and check again later.",
        source_responsibility_refs=["r1"],
    )
    manager._task_contexts.append(
        {
            "task_id": "task-1",
            "status": "planning",
            "commitment_state": "evaluating",
            "goal_version": 1,
            "semantic_goal": goal.model_dump(mode="json", exclude_none=True),
            "metadata": {},
        }
    )
    plan = CanonicalPlan(
        plan_id="plan-1",
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=0.9,
        goal_ids=["goal-1"],
        steps=[
            CanonicalPlanStep(
                step_id="step-read",
                capability_id="example.safe_read",
                args={},
                source_goal_ids=["goal-1"],
            )
        ],
        time_conditions=[
            PlannedGoalTimeCondition(
                condition_id="plan-1:time:0",
                goal_id="goal-1",
                due_at_ms=2_000,
                reason_code="recheck_running_work",
            )
        ],
        goal_satisfaction=_satisfaction("goal-1"),
    )
    metadata = {
        "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
        "canonical_plan_id": plan.plan_id,
        "canonical_plan_fingerprint": "fingerprint-1",
        "language": "en",
        "goal_interpretation": {
            "responsibilities": [
                {
                    "schema_version": 1,
                    "local_ref": "r1",
                    "outcome": "Keep monitoring the running work.",
                    "bindings": {},
                    "output_mode": "information",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                }
            ]
        },
    }

    assert manager._record_planner_time_conditions(metadata) == 1
    due = manager.due_time_condition_opportunities(now_ms=2_000)
    assert len(due) == 1
    assert due[0]["condition"]["source_plan_id"] == "plan-1"
    assert due[0]["condition"]["source_responsibility_refs"] == ["r1"]
    assert due[0]["responsibilities"][0]["local_ref"] == "r1"
    assert due[0]["opportunity"]["trigger"] == "time_condition"
