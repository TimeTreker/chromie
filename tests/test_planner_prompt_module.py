from __future__ import annotations

from agent.app import deep_planner, fast_planner, planner_prompt
from tests.cognitive_work_test_support import cognitive_work_request


def test_planner_prompt_module_stays_projection_only() -> None:
    namespace = vars(planner_prompt)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "CanonicalPlan",
        "CapabilityRuntime",
        "GoalAssociationResolution",
        "validate_planner_model_output",
        "materialize_planner_metadata",
    ):
        assert forbidden not in namespace

    assert planner_prompt.fast_plan_prompt.__module__ == "agent.app.planner_prompt"
    assert planner_prompt.deep_plan_prompt.__module__ == "agent.app.planner_prompt"
    assert planner_prompt.fast_streaming_advance_system_prompt.__module__ == (
        "agent.app.planner_prompt"
    )


def test_fast_and_deep_resolvers_do_not_reown_prompt_mechanics() -> None:
    for resolver, removed in (
        (
            fast_planner.FastPlannerResolver,
            (
                "_first_response_truth_system_prompt",
                "_first_response_truth_prompt",
                "_first_response_system_prompt",
                "_first_response_prompt",
                "_prompt",
                "_advance_layered_prompt",
                "_advance_capability_prompt_projection",
                "_advance_system_prompt",
                "_layered_prompt",
                "_system_prompt",
                "_repair_system_prompt",
            ),
        ),
        (
            deep_planner.DeepPlannerResolver,
            (
                "_prompt",
                "_layered_prompt",
                "_prioritize_capability_contracts",
                "_prompt_capability_contract",
                "_system_prompt",
                "_revision_system_prompt",
            ),
        ),
    ):
        for name in removed:
            assert not hasattr(resolver, name)


def test_fast_prompt_keeps_supportive_speech_grounded() -> None:
    request = cognitive_work_request(
        sid="supportive-speech-grounding",
        text="Please encourage me.",
        language="en-US",
        context={
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": "goal-encouragement",
                        "description": "Give one encouraging sentence.",
                        "metadata": {"output_mode": "speech"},
                    },
                    {
                        "goal_id": "goal-blink",
                        "description": "Blink twice.",
                        "metadata": {"output_mode": "body_action"},
                    },
                ],
            }
        },
    )

    prompt = planner_prompt.fast_plan_prompt(request, [], response_schema={})

    assert "must not state or imply an unprovided user history" in prompt
    assert "express support without inventing familiarity or evidence" in prompt
