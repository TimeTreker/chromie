from __future__ import annotations

import asyncio
import importlib.util
import json

from benchmarks.datasets.fast_planner_daily_life import qualification as fast_qualification

from agent.app import (
    planner,
    planner_context,
    planner_fallback,
    planner_fast_validation,
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
    assert planner_context.canonical_goal_grounding.__module__ == ("agent.app.planner_context")


def test_planner_schema_and_validation_have_distinct_mechanical_owners() -> None:
    for module in (
        planner_schema,
        planner_validation,
        planner_fast_validation,
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

    assert planner_schema.canonical_plan_response_schema.__module__ == ("agent.app.planner_schema")
    assert planner_validation.validate_planner_model_output.__module__ == (
        "agent.app.planner_validation"
    )
    assert planner_fast_validation.qualify_fast_canonical_plan.__module__ == (
        "agent.app.planner_fast_validation"
    )
    assert not hasattr(planner_validation, "qualify_fast_canonical_plan")
    assert planner_grounding._material_values_equal.__module__ == ("agent.app.planner_grounding")


def test_planner_layers_expose_no_same_tier_semantic_repair_surface() -> None:
    assert not hasattr(planner_schema, "fast_repair_response_schema")
    assert not hasattr(planner_schema, "deep_contract_revision_response_schema")
    assert not hasattr(planner_schema, "deep_safety_revision_response_schema")
    assert not hasattr(planner_prompt, "fast_repair_system_prompt")
    assert not hasattr(planner_prompt, "deep_revision_system_prompt")


def test_one_planner_has_no_second_planner_modules() -> None:
    # PLANNER-AUTHORITY-001: the Deep Planner was retired on 2026-10-11.
    for retired in ("agent.app.deep_planner", "agent.app.planner_deep_validation"):
        assert importlib.util.find_spec(retired) is None
    assert not hasattr(planner_prompt, "deep_plan_prompt")
    assert not hasattr(planner_schema, "deep_plan_response_schema")


def test_common_normalization_does_not_rewrite_planner_semantics() -> None:
    raw = {
        "disposition": "execute",
        "coverage": "partial",
        "response_text": "original words",
        "steps": [{"step_id": "work", "depends_on": []}],
        "parameter_resolutions": [],
        "goal_outcomes": {
            "goal": {
                "disposition": "respond",
                "coverage": "complete",
                "response_text": "different words",
                "step_ids": [],
                "unresolved": [],
                "satisfaction": {
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal"],
                    "unmet_goal_ids": [],
                    "unmet_requirements": [],
                },
            }
        },
    }

    normalized, repairs = planner_validation.normalize_common_planner_output(
        raw,
        authoritative_goals=[{"goal_id": "goal"}],
        capability_payload=[],
    )

    assert normalized == raw
    assert all(
        not values
        for key, values in repairs.items()
        if key
        in {
            "terminal_response_goal_outcome_accounting",
            "nonexecuting_plan_mechanics",
        }
    )


def test_fast_qualification_required_capability_reaches_target_blind_transaction() -> None:
    scenario_path = (
        fast_qualification.DATASET_ROOT
        / "scenarios"
        / "train_candidate"
        / "canonical_primary"
        / "fpdl_v2_plan_relation_and_confirmation_proposal_22_supported_en.json"
    )
    case = json.loads(scenario_path.read_text(encoding="utf-8"))

    transaction = asyncio.run(fast_qualification.build_transaction(case))
    transaction_contract = transaction["user_prompt"] + json.dumps(
        transaction["response_schema"],
        sort_keys=True,
    )

    assert "chromie.reminder.create" in transaction_contract
    catalog, _ = json.JSONDecoder().raw_decode(
        transaction["user_prompt"].split("Executable common capability catalog JSON:\n")[1])
    assert {item["capability_id"] for item in catalog} == {"chromie.reminder.create", "chromie.weather.lookup"}



def test_planner_fallback_is_mechanical_materialization_only() -> None:
    namespace = vars(planner_fallback)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "validate_planner_model_output",
        "validated_fail_safe_progress",
    ):
        assert forbidden not in namespace
    assert planner_fallback.materialize_planner_failure.__module__ == ("agent.app.planner_fallback")
    assert planner_fallback.materialize_planner_unavailable.__module__ == (
        "agent.app.planner_fallback"
    )


def test_planner_and_prompt_depend_on_real_planner_layer_owners() -> None:
    assert planner.canonical_plan_response_schema is (
        planner_schema.canonical_plan_response_schema
    )
    assert planner.validate_planner_model_output is (
        planner_validation.validate_planner_model_output
    )
    assert planner.planner_goal_context is planner_context.planner_goal_context
    assert planner.normalize_common_planner_output is (
        planner_validation.normalize_common_planner_output
    )
    assert planner.qualify_planner_capability_payload is (
        planner_validation.qualify_planner_capability_payload
    )
    assert planner.qualify_fast_canonical_plan is (
        planner_fast_validation.qualify_fast_canonical_plan
    )
    assert planner.materialize_planner_output is (
        planner_model_contract.materialize_planner_output
    )
    assert planner_fallback.materialize_planner_failure.__module__ == ("agent.app.planner_fallback")
    assert planner_prompt.canonical_goal_grounding is planner_context.canonical_goal_grounding


def test_resolvers_contain_only_planner_lifecycle_methods() -> None:
    fast_methods = {
        name for name, value in vars(planner.PlannerResolver).items() if callable(value)
    }
    assert fast_methods == {
        "__init__",
        "stream_advance",
        "resolve",
        "_resolve",
    }


def test_planner_resolver_does_not_reown_schema_mechanics() -> None:
    for resolver, removed in (
        (
            planner.PlannerResolver,
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
    ):
        for name in removed:
            assert not hasattr(resolver, name)

    assert planner.fast_streaming_advance_response_schema is (
        planner_schema.fast_streaming_advance_response_schema
    )


def test_planner_contract_catch_all_is_not_a_compatibility_surface() -> None:
    assert importlib.util.find_spec("agent.app.planner_contract") is None
