from __future__ import annotations

import importlib.util

from agent.app import (
    deep_planner,
    fast_planner,
    planner_audit,
    planner_context,
    planner_fallback,
    planner_fast_validation,
    planner_deep_validation,
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
    for module in (
        planner_schema,
        planner_validation,
        planner_fast_validation,
        planner_deep_validation,
        planner_grounding,
    ):
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
    assert planner_fast_validation.qualify_fast_canonical_plan.__module__ == (
        "agent.app.planner_fast_validation"
    )
    assert planner_deep_validation.deep_plan_validation_errors.__module__ == (
        "agent.app.planner_deep_validation"
    )
    assert not hasattr(planner_validation, "qualify_fast_canonical_plan")
    assert not hasattr(planner_validation, "deep_plan_validation_errors")
    assert planner_grounding._material_values_equal.__module__ == (
        "agent.app.planner_grounding"
    )


def test_fast_repair_schema_preserves_initial_escalation_semantics() -> None:
    goal_id = "goal_weather"
    base = planner_schema.fast_multi_goal_response_schema(
        expected_goal_ids=[goal_id],
        allowed_capability_ids=["chromie.weather.lookup"],
        capability_input_schemas={
            "chromie.weather.lookup": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
                "additionalProperties": False,
            }
        },
        requires_execution=True,
    )
    repaired = planner_schema.fast_repair_response_schema(
        base,
        {
            "disposition": "escalate",
            "goal_outcomes": {
                goal_id: {
                    "disposition": "escalate",
                }
            },
        },
        expected_goal_ids_for_turn=[goal_id],
    )

    properties = repaired["properties"]
    assert properties["disposition"]["enum"] == ["escalate"]
    assert properties["coverage"]["enum"] == ["partial"]
    assert properties["steps"]["maxItems"] == 0
    assert properties["response_text"]["maxLength"] == 0
    goal_schema = properties["goal_outcomes"]["properties"][goal_id]
    frozen = goal_schema["properties"]
    assert frozen["disposition"]["enum"] == [
        "escalate"
    ]
    assert frozen["response_text"]["maxLength"] == 0
    assert frozen["step_ids"]["maxItems"] == 0
    assert {
        "disposition",
        "response_text",
        "step_ids",
    }.issubset(goal_schema["required"])


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
    assert planner_audit.qualify_evidence_response_truth.__module__ == (
        "agent.app.planner_audit"
    )


def test_planner_fallback_is_mechanical_materialization_only() -> None:
    namespace = vars(planner_fallback)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "validate_planner_model_output",
        "validated_fail_safe_progress",
    ):
        assert forbidden not in namespace
    assert planner_fallback.materialize_fast_escalation.__module__ == (
        "agent.app.planner_fallback"
    )
    assert planner_fallback.materialize_deep_unavailable.__module__ == (
        "agent.app.planner_fallback"
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
    assert fast_planner.planner_goal_context is planner_context.planner_goal_context
    assert deep_planner.planner_goal_context is planner_context.planner_goal_context
    assert fast_planner.normalize_common_planner_output is (
        planner_validation.normalize_common_planner_output
    )
    assert deep_planner.normalize_common_planner_output is (
        planner_validation.normalize_common_planner_output
    )
    assert fast_planner.qualify_planner_capability_payload is (
        planner_validation.qualify_planner_capability_payload
    )
    assert deep_planner.qualify_planner_capability_payload is (
        planner_validation.qualify_planner_capability_payload
    )
    assert fast_planner.qualify_fast_canonical_plan is (
        planner_fast_validation.qualify_fast_canonical_plan
    )
    assert deep_planner.deep_plan_validation_errors is (
        planner_deep_validation.deep_plan_validation_errors
    )
    assert fast_planner.materialize_planner_output is (
        planner_model_contract.materialize_planner_output
    )
    assert deep_planner.materialize_planner_output is (
        planner_model_contract.materialize_planner_output
    )
    assert planner_fallback.materialize_fast_escalation.__module__ == (
        "agent.app.planner_fallback"
    )
    assert planner_fallback.materialize_deep_clarify.__module__ == (
        "agent.app.planner_fallback"
    )
    assert planner_prompt.canonical_goal_grounding is planner_context.canonical_goal_grounding


def test_resolvers_contain_only_planner_lifecycle_methods() -> None:
    fast_methods = {
        name
        for name, value in vars(fast_planner.FastPlannerResolver).items()
        if callable(value)
    }
    deep_methods = {
        name
        for name, value in vars(deep_planner.DeepPlannerResolver).items()
        if callable(value)
    }
    assert fast_methods == {
        "__init__",
        "resolve_first_response",
        "_qualify_first_response_truth",
        "_qualify_evidence_response_truth",
        "resolve_advance",
        "resolve",
        "_resolve",
    }
    assert deep_methods == {"__init__", "resolve", "_resolve"}


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
                "_gateway_speech_act",
                "_restore_required_capability_args_from_responsibilities",
                "_validate_advance_output",
                "_advance_fail_safe",
                "_validated_fail_safe_progress",
                "_validation_error_json",
                "_capability_argument_errors",
                "_plan_id",
                "_bounded",
                "_validate_work_reuse_selection",
                "_normalize_multi_goal",
                "_normalize",
                "_validate",
                "_escalation",
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
                "_validation_error_items",
                "_detached_numeric_provenance_obligations",
                "_validation_error_json",
                "_capability_payload",
                "_plan_id",
                "_initial_safety_feedback",
                "_merge_feedback",
                "_normalize_mixed_goal_outcome_accounting",
                "_validate_mechanical_numeric_revision_preserved",
                "_safety_revision_contract_errors",
                "_validate_parallel_timing_preservation",
                "_bounded",
                "_normalize",
                "_validation_errors",
                "_unavailable",
                "_clarify",
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
