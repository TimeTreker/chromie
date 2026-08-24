from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from orchestrator.runtime.capability_runtime import CapabilityDefinition
from orchestrator.runtime.outcome_reconciliation import ExecutionOutcomeReconciler
from shared.chromie_contracts.execution_outcome import (
    ClaimQualification,
    ClaimQualificationPolicy,
    EvidenceRequirement,
    ProviderPostconditionEvidence,
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.interaction import CapabilityRequest


def completion_policy() -> ClaimQualificationPolicy:
    return ClaimQualificationPolicy(
        claim="capability request completed",
        requirement_groups=[
            {
                "requirements": [
                    {
                        "source": "execution_observation",
                        "field_assertions": {"completed": True},
                    },
                    {
                        "source": "provider_postcondition",
                        "condition": "post_execution_robot_status",
                        "field_assertions": {
                            "safe_idle": True,
                            "active_task_present": False,
                        },
                    },
                ],
                "minimum_independent_trust_domains": 1,
            }
        ],
    )


def test_claim_policy_digest_is_stable_and_request_commit_is_typed() -> None:
    policy = completion_policy()
    digest = claim_qualification_policy_sha256(policy)

    reordered = ClaimQualificationPolicy.model_validate(
        {
            "claim": "capability request completed",
            "schema_version": 1,
            "requires_complete_coverage": False,
            "requirement_groups": [
                {
                    "minimum_independent_trust_domains": 1,
                    "requirements": [
                        {
                            "field_assertions": {"completed": True},
                            "source": "execution_observation",
                        },
                        {
                            "field_assertions": {
                                "active_task_present": False,
                                "safe_idle": True,
                            },
                            "condition": "post_execution_robot_status",
                            "source": "provider_postcondition",
                        },
                    ],
                }
            ],
        }
    )
    assert claim_qualification_policy_sha256(reordered) == digest

    request = CapabilityRequest(
        request_id="request-1",
        capability_id="soridormi.nod_yes",
        committed_completion_evidence_sha256=digest,
    )
    assert request.committed_completion_evidence_sha256 == digest

    with pytest.raises(ValidationError):
        CapabilityRequest(
            request_id="request-bad",
            capability_id="soridormi.nod_yes",
            committed_completion_evidence_sha256="not-a-digest",
        )


def test_capability_definition_carries_owner_reviewed_completion_policy() -> None:
    definition = CapabilityDefinition(
        capability_id="soridormi.nod_yes",
        provider_id="soridormi.mcp",
        completion_evidence_policy=completion_policy(),
    )

    assert definition.completion_evidence_policy is not None
    assert definition.completion_evidence_policy.claim == "capability request completed"


def test_evidence_requirement_is_not_a_general_rule_engine() -> None:
    with pytest.raises(ValidationError, match="must not name a postcondition"):
        EvidenceRequirement(
            source="execution_observation",
            condition="safe_idle",
            field_assertions={"completed": True},
        )

    with pytest.raises(ValidationError, match="require condition"):
        EvidenceRequirement(
            source="provider_postcondition",
            field_assertions={"safe_idle": True},
        )

    with pytest.raises(ValidationError, match="exact JSON scalars"):
        EvidenceRequirement(
            source="execution_observation",
            field_assertions={"resource_outcome": {"resource_acquired": True}},
        )

    nested = EvidenceRequirement(
        source="execution_observation",
        field_assertions={"resource_outcome.resource_acquired": True},
    )
    assert nested.field_assertions == {"resource_outcome.resource_acquired": True}

    presence_only = EvidenceRequirement(source="execution_observation")
    assert presence_only.field_assertions == {}


def test_claim_qualification_keeps_established_and_unknown_distinct() -> None:
    policy = completion_policy()
    digest = claim_qualification_policy_sha256(policy)
    now = datetime.now(timezone.utc)
    established = ClaimQualification(
        claim=policy.claim,
        status="established",
        policy_sha256=digest,
        evidence_ids=["evidence-1", "postcondition-1"],
        trust_domains=["soridormi.mcp"],
        coverage="not_required",
        satisfied_group_index=0,
        evaluated_at=now,
    )
    assert established.status == "established"

    with pytest.raises(ValidationError, match="requires satisfied_group_index"):
        ClaimQualification(
            claim=policy.claim,
            status="established",
            policy_sha256=digest,
            evidence_ids=["evidence-1"],
            evaluated_at=now,
        )


def _scalar_schema(name: str, value_type: str) -> dict:
    return {
        "type": "object",
        "properties": {name: {"type": value_type}},
        "required": [name],
        "additionalProperties": False,
    }


def test_epistemic_freshness_failure_is_not_downgraded_to_unknown() -> None:
    reconciler = ExecutionOutcomeReconciler()
    now = datetime.now(timezone.utc)
    observation = reconciler.build_model_observation(
        {"completed": True},
        output_schema=_scalar_schema("completed", "boolean"),
    )
    policy = ClaimQualificationPolicy(
        claim="fresh completion",
        requirement_groups=[
            {
                "requirements": [
                    {
                        "source": "execution_observation",
                        "field_assertions": {"completed": True},
                        "max_age_ms": 1000,
                    }
                ]
            }
        ],
    )

    qualification = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="evidence-stale",
        execution_status="completed",
        execution_observation=observation,
        execution_output={"completed": True},
        execution_trust_domain="robot.provider",
        execution_finished_at=now - timedelta(seconds=5),
        source_goal_ids=["goal-1"],
        provider_postconditions=[],
        evaluated_at=now,
        missing_result=False,
    )

    assert qualification.status == "stale"
    assert any("stale" in reason for reason in qualification.reason_codes)


def test_epistemic_contradiction_beats_matching_transport_completion() -> None:
    reconciler = ExecutionOutcomeReconciler()
    now = datetime.now(timezone.utc)
    observation = reconciler.build_model_observation(
        {"safe": False},
        output_schema=_scalar_schema("safe", "boolean"),
    )
    policy = ClaimQualificationPolicy(
        claim="robot is safe after execution",
        requirement_groups=[
            {
                "requirements": [
                    {
                        "source": "execution_observation",
                        "field_assertions": {"safe": True},
                    }
                ]
            }
        ],
    )

    qualification = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="evidence-contradicted",
        execution_status="completed",
        execution_observation=observation,
        execution_output={"safe": False},
        execution_trust_domain="robot.provider",
        execution_finished_at=now,
        source_goal_ids=["goal-1"],
        provider_postconditions=[],
        evaluated_at=now,
        missing_result=False,
    )

    assert qualification.status == "contradicted"


def test_epistemic_independence_counts_trust_domains_not_evidence_count() -> None:
    reconciler = ExecutionOutcomeReconciler()
    now = datetime.now(timezone.utc)
    execution = reconciler.build_model_observation(
        {"completed": True},
        output_schema=_scalar_schema("completed", "boolean"),
    )
    post_observation = reconciler.build_model_observation(
        {"safe_idle": True},
        output_schema=_scalar_schema("safe_idle", "boolean"),
    )
    policy = ClaimQualificationPolicy(
        claim="independently corroborated completion",
        requirement_groups=[
            {
                "requirements": [
                    {"source": "execution_observation"},
                    {
                        "source": "provider_postcondition",
                        "condition": "robot_status",
                        "field_assertions": {"safe_idle": True},
                    },
                ],
                "minimum_independent_trust_domains": 2,
            }
        ],
    )
    same_domain = ProviderPostconditionEvidence(
        evidence_id="post-same",
        provider_id="robot.provider",
        trust_domain="robot.provider",
        condition="robot_status",
        observation=post_observation,
        source_goal_ids=["goal-1"],
        observed_at=now,
    )
    insufficient = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="execution-same",
        execution_status="completed",
        execution_observation=execution,
        execution_output={"completed": True},
        execution_trust_domain="robot.provider",
        execution_finished_at=now,
        source_goal_ids=["goal-1"],
        provider_postconditions=[same_domain],
        evaluated_at=now,
        missing_result=False,
    )
    assert insufficient.status == "insufficient"
    assert "independent_trust_domains_insufficient" in insufficient.reason_codes

    independent = same_domain.model_copy(
        update={
            "evidence_id": "post-independent",
            "provider_id": "safety.monitor",
            "trust_domain": "safety.monitor",
        }
    )
    established = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="execution-independent",
        execution_status="completed",
        execution_observation=execution,
        execution_output={"completed": True},
        execution_trust_domain="robot.provider",
        execution_finished_at=now,
        source_goal_ids=["goal-1"],
        provider_postconditions=[independent],
        evaluated_at=now,
        missing_result=False,
    )
    assert established.status == "established"
    assert set(established.trust_domains) == {"robot.provider", "safety.monitor"}


def test_closed_world_negative_claim_requires_complete_collection_coverage() -> None:
    reconciler = ExecutionOutcomeReconciler()
    now = datetime.now(timezone.utc)
    observation = reconciler.build_model_observation(
        {"hazard_present": False},
        output_schema=_scalar_schema("hazard_present", "boolean"),
    )
    policy = ClaimQualificationPolicy(
        claim="no hazard is present in the observed workspace",
        requires_complete_coverage=True,
        requirement_groups=[
            {
                "requirements": [
                    {
                        "source": "execution_observation",
                        "field_assertions": {"hazard_present": False},
                    }
                ]
            }
        ],
    )

    partial = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="negative-partial",
        execution_status="completed",
        execution_observation=observation,
        execution_output={"hazard_present": False},
        execution_trust_domain="workspace.sensor",
        execution_finished_at=now,
        source_goal_ids=["goal-1"],
        provider_postconditions=[],
        evaluated_at=now,
        missing_result=False,
        coverage="partial",
    )
    assert partial.status == "insufficient"
    assert partial.reason_codes == ["closed_world_coverage_not_complete"]

    complete = reconciler.qualify_completion_claim(
        policy=policy,
        evidence_id="negative-complete",
        execution_status="completed",
        execution_observation=observation,
        execution_output={"hazard_present": False},
        execution_trust_domain="workspace.sensor",
        execution_finished_at=now,
        source_goal_ids=["goal-1"],
        provider_postconditions=[],
        evaluated_at=now,
        missing_result=False,
        coverage="complete",
    )
    assert complete.status == "established"
