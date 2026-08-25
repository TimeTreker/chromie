from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.app.planner_model_contract import PlannerModelOutput, materialize_planner_output
from shared.chromie_contracts.plan import CanonicalPlan, GoalSatisfactionAssessment


def _satisfaction(goal_id: str) -> dict[str, object]:
    return GoalSatisfactionAssessment(
        score=1.0,
        status="exact",
        satisfied_goal_ids=[goal_id],
        unmet_goal_ids=[],
        unmet_requirements=[],
        rationale="The planned observation would provide the needed grounding.",
    ).model_dump(mode="json")


def _active_perception_output(*, expected_outcome: str) -> PlannerModelOutput:
    goal_id = "goal-find-cup"
    return PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.94,
            "goal_summary": "Acquire fresh visual grounding for the cup.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "observe-cup",
                    "capability_id": "soridormi.look_direction",
                    "args": {"direction": "left"},
                    "timing": "sequential",
                    "source_goal_ids": [goal_id],
                    "reuse_activity_id": "",
                    "step_purpose": "acquire_information",
                    "expected_outcome": expected_outcome,
                    "reason_summary": "Look where the referenced cup may be visible.",
                }
            ],
            "escalation_reason": "",
            "unresolved": [],
            "parameter_resolutions": [],
            "time_conditions": [],
            "goal_outcomes": {
                goal_id: {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["observe-cup"],
                    "satisfaction": _satisfaction(goal_id),
                    "rationale": "Fresh observation is the next required progress.",
                }
            },
            "goal_satisfaction": _satisfaction(goal_id),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
    )


def test_active_perception_step_is_ordinary_planner_work_with_falsifiable_expectation() -> None:
    output = _active_perception_output(
        expected_outcome="Fresh observation establishes whether the blue cup is visible on the left."
    )
    raw = materialize_planner_output(
        output,
        planner_tier="deep",
        plan_id="plan-find-cup",
        expected_goal_ids_for_turn=["goal-find-cup"],
        goal_summary_fallback="Find the cup.",
    )
    plan = CanonicalPlan.model_validate(raw)

    assert plan.steps[0].step_purpose == "acquire_information"
    assert "blue cup" in plan.steps[0].expected_outcome
    projection = plan.prompt_projection()
    assert projection["steps"][0]["step_purpose"] == "acquire_information"
    assert projection["steps"][0]["expected_outcome"] == plan.steps[0].expected_outcome


def test_information_acquisition_cannot_hide_the_observation_it_expects() -> None:
    with pytest.raises(ValidationError, match="expected_outcome"):
        _active_perception_output(expected_outcome="")


def test_expected_outcome_is_not_execution_evidence_or_goal_completion() -> None:
    plan = CanonicalPlan.model_validate(
        materialize_planner_output(
            _active_perception_output(
                expected_outcome="A fresh camera observation identifies the referenced cup."
            ),
            planner_tier="deep",
            plan_id="plan-find-cup",
            expected_goal_ids_for_turn=["goal-find-cup"],
            goal_summary_fallback="Find the cup.",
        )
    )

    assert plan.disposition == "execute"
    assert plan.goal_satisfaction is not None
    assert plan.steps[0].expected_outcome
    assert "evidence" not in plan.steps[0].model_dump(mode="json")


def test_terminal_evidence_reentry_exposes_prior_expectation_without_promoting_it_to_evidence() -> None:
    import asyncio
    from types import SimpleNamespace

    from orchestrator.orchestrator import VoiceAssistant
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.interaction import InteractionResponse
    from shared.chromie_contracts.plan import RespondGoalPlanOutcome

    goal_id = "goal-find-cup"
    original = CanonicalPlan.model_validate(
        materialize_planner_output(
            _active_perception_output(
                expected_outcome="A fresh observation establishes whether the blue cup is visible."
            ),
            planner_tier="deep",
            plan_id="plan-find-cup",
            expected_goal_ids_for_turn=[goal_id],
            goal_summary_fallback="Find the cup.",
        )
    )
    satisfaction = GoalSatisfactionAssessment(
        score=1.0,
        status="exact",
        satisfied_goal_ids=[goal_id],
    )
    followup = CanonicalPlan(
        plan_id="plan-after-observation",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.98,
        goal_ids=[goal_id],
        response_text="I can see it now.",
        goal_outcomes=[
            RespondGoalPlanOutcome(
                goal_id=goal_id,
                disposition="respond",
                coverage="complete",
                response_text="I can see it now.",
                satisfaction=satisfaction,
            )
        ],
        goal_satisfaction=satisfaction,
    )

    class Client:
        request = None

        async def resolve_fast_plan(self, _session, *, request, timeout_ms):
            self.request = request
            return followup

    class Adapter:
        async def build_planner_owned_response(self, **_kwargs):
            return InteractionResponse(interaction_id="after-observation", status="ok")

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Client()
    assistant.cognitive_runtime_policy = SimpleNamespace(
        fast_planner_timeout_ms=3000,
        deep_planner_timeout_ms=6000,
    )
    assistant.cognitive_runtime = SimpleNamespace(adapter=Adapter(), interaction_ledger=None)
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.build_context = lambda _sid: {"history": []}
    assistant._goal_driven_authority_context = lambda context, **_kwargs: context

    async def get_session():
        return object()

    assistant.get_http_session = get_session
    response = asyncio.run(
        assistant._planner_state_reentry_response(
            source_response=None,
            canonical_plan=original,
            user_request="Bring me the cup.",
            language="en-US",
            goal_ids=[goal_id],
            evidence_goal_ids=[goal_id],
            evidence_refs=["evidence-cup-visible"],
            session_id=None,
            phase="post_observation",
            context_updates={
                "trusted_terminal_evidence": [
                    {
                        "evidence_id": "evidence-cup-visible",
                        "status": "completed",
                    }
                ]
            },
            fast_workflow_stage="fast_planner_observation_reentry",
            deep_workflow_stage="planner_deep_pass_observation_reentry",
            response_source="fast_planner_observation_reentry",
            responsibilities_override=[
                CognitiveResponsibilityProposal(
                    local_ref="resp-find-cup",
                    outcome="Bring the user's referenced cup.",
                    output_mode="stateful_effect",
                    relationship="new",
                    confidence=1.0,
                )
            ],
        )
    )

    assert response is not None
    expectations = assistant.agent_client.request.context["planner_reentry_expectations"]
    assert expectations == [
        {
            "step_id": "observe-cup",
            "source_goal_ids": [goal_id],
            "step_purpose": "acquire_information",
            "expected_outcome": "A fresh observation establishes whether the blue cup is visible.",
        }
    ]
    assert "evidence_refs" not in expectations[0]
