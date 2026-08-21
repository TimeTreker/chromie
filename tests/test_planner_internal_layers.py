from __future__ import annotations

import importlib.util

from agent.app import (
    deep_planner,
    fast_planner,
    planner_audit,
    planner_context,
    planner_grounding,
    planner_model_contract,
    planner_prompt,
    planner_schema,
    planner_validation,
)


def test_planner_model_contract_is_representation_only() -> None:
    namespace = vars(planner_model_contract)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "GoalAssociationResolution",
        "CapabilityRuntime",
        "ConversationState",
    ):
        assert forbidden not in namespace
    assert planner_model_contract.PlannerModelOutput.__module__ == (
        "agent.app.planner_model_contract"
    )


def test_planner_context_is_read_only_projection_only() -> None:
    namespace = vars(planner_context)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "CapabilityRuntime",
        "validate_planner_model_output",
        "canonical_plan_response_schema",
    ):
        assert forbidden not in namespace
    assert planner_context.canonical_goal_grounding.__module__ == (
        "agent.app.planner_context"
    )


def test_planner_schema_and_validation_have_distinct_mechanical_owners() -> None:
    for module in (planner_schema, planner_validation, planner_grounding):
        namespace = vars(module)
        for forbidden in (
            "OllamaClient",
            "runtime_tracer",
            "CapabilityRuntime",
            "ConversationState",
        ):
            assert forbidden not in namespace

    assert planner_schema.canonical_plan_response_schema.__module__ == (
        "agent.app.planner_schema"
    )
    assert planner_validation.validate_planner_model_output.__module__ == (
        "agent.app.planner_validation"
    )
    assert planner_grounding._material_values_equal.__module__ == (
        "agent.app.planner_grounding"
    )


def test_planner_audit_is_planner_owned_bounded_audit_not_runtime_authority() -> None:
    namespace = vars(planner_audit)
    for forbidden in (
        "runtime_tracer",
        "CapabilityRuntime",
        "ConversationState",
        "GoalAssociationResolution",
    ):
        assert forbidden not in namespace
    assert planner_audit.review_coordinated_action_plan_coverage.__module__ == (
        "agent.app.planner_audit"
    )


def test_fast_deep_and_prompt_depend_on_real_planner_layer_owners() -> None:
    assert fast_planner.canonical_plan_response_schema is (
        planner_schema.canonical_plan_response_schema
    )
    assert deep_planner.deep_plan_response_schema is (
        planner_schema.deep_plan_response_schema
    )
    assert fast_planner.validate_planner_model_output is (
        planner_validation.validate_planner_model_output
    )
    assert deep_planner.validate_planner_model_output is (
        planner_validation.validate_planner_model_output
    )
    assert fast_planner.materialize_goal_outcomes is (
        planner_model_contract.materialize_goal_outcomes
    )
    assert deep_planner.materialize_goal_outcomes is (
        planner_model_contract.materialize_goal_outcomes
    )
    assert planner_prompt.canonical_goal_grounding is planner_context.canonical_goal_grounding

def test_fast_and_deep_resolvers_do_not_reown_schema_mechanics() -> None:
    for resolver, removed in (
        (
            fast_planner.FastPlannerResolver,
            (
                "_truth_certificate_schema",
                "_first_response_schema",
                "_advance_revision_response_schema",
                "_advance_response_schema",
                "_repair_response_schema",
            ),
        ),
        (
            deep_planner.DeepPlannerResolver,
            (
                "_response_schema",
                "_safety_revision_response_schema",
                "_contract_revision_response_schema",
                "_requires_safety_revision",
                "_requires_sequential_safety_revision",
            ),
        ),
    ):
        for name in removed:
            assert not hasattr(resolver, name)

    assert fast_planner.fast_first_response_response_schema is (
        planner_schema.fast_first_response_response_schema
    )
    assert fast_planner.fast_advance_response_schema is (
        planner_schema.fast_advance_response_schema
    )
    assert deep_planner.deep_plan_response_schema is planner_schema.deep_plan_response_schema
    assert deep_planner.requires_safety_revision is planner_validation.requires_safety_revision

def test_planner_contract_catch_all_is_not_a_compatibility_surface() -> None:
    assert importlib.util.find_spec("agent.app.planner_contract") is None
