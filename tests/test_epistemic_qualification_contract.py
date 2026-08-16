from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from orchestrator.runtime.capability_runtime import CapabilityDefinition
from shared.chromie_contracts.execution_outcome import (
    ClaimQualification,
    ClaimQualificationPolicy,
    EvidenceRequirement,
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
