from __future__ import annotations

from agent.app import goal_association
from agent.app import goal_association_contract


def test_goal_association_model_contract_has_one_definition_owner() -> None:
    assert (
        goal_association.GoalAssociationModelGoal
        is goal_association_contract.GoalAssociationModelGoal
    )
    assert (
        goal_association.GoalAssociationModelOutput
        is goal_association_contract.GoalAssociationModelOutput
    )
    assert (
        goal_association.GoalSegmentationModelOutput
        is goal_association_contract.GoalSegmentationModelOutput
    )
    assert (
        goal_association.GoalResponsibilityCoverageCertificate
        is goal_association_contract.GoalResponsibilityCoverageCertificate
    )
    assert goal_association_contract.GoalAssociationModelGoal.__module__ == (
        "agent.app.goal_association_contract"
    )


def test_goal_association_contract_module_stays_model_only() -> None:
    namespace = vars(goal_association_contract)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "GoalAssociationResolution",
        "ActiveGoalSnapshot",
        "stable_goal_operation_id",
        "CapabilityRuntime",
        "ConversationState",
    ):
        assert forbidden not in namespace


def test_goal_association_identity_contract_preserves_current_truth_boundary() -> None:
    text = goal_association_contract._GOAL_SEGMENTATION_IDENTITY_CONTRACT
    assert "social identity" in text
    assert "biological-human claim" in text
    assert "human-child kind" not in text


def test_goal_association_prompt_module_stays_projection_only() -> None:
    from agent.app import goal_association_prompt

    namespace = vars(goal_association_prompt)
    for forbidden in (
        "OllamaClient",
        "runtime_tracer",
        "GoalAssociationResolution",
        "ActiveGoalSnapshot",
        "stable_goal_operation_id",
        "CapabilityRuntime",
        "ConversationState",
    ):
        assert forbidden not in namespace
    assert goal_association_prompt.build_prompt.__module__ == (
        "agent.app.goal_association_prompt"
    )
    assert goal_association_prompt.layered_prompt.__module__ == (
        "agent.app.goal_association_prompt"
    )


def test_goal_association_resolver_does_not_reown_contract_or_prompt_mechanics() -> None:
    for removed_surface in (
        "_response_schema",
        "_coverage_certificate_response_schema",
        "_coverage_verdict",
        "_drop_inactive_resource_bindings",
        "_source_grounded_binding_coverage_conflicts",
        "_build_prompt",
        "_build_repair_prompt",
        "_layered_prompt",
        "_responsibility_coverage_system_prompt",
        "_build_responsibility_coverage_prompt",
        "_system_prompt",
    ):
        assert not hasattr(goal_association.GoalAssociationResolver, removed_surface)
