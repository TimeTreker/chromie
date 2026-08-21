from __future__ import annotations

from agent.app import deep_planner, fast_planner, planner_prompt


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
    assert planner_prompt.fast_first_response_prompt.__module__ == (
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
