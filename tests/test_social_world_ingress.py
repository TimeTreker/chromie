from __future__ import annotations

import pytest

from orchestrator.runtime.situation import build_social_perception_situation_observation
from shared.chromie_contracts.situation import SituationSourceRef
from shared.chromie_contracts.social_world import (
    TrustedPersonPresence,
    TrustedSocialPerceptionObservation,
)


def perception(*, audience=None, status="resolved", confidence=0.94):
    source = SituationSourceRef(
        kind="perception", reference_id="camera-frame-7", owner="trusted_presence_adapter"
    )
    return TrustedSocialPerceptionObservation(
        observation_id="social-frame-7",
        source_id="trusted_presence_adapter",
        source_revision=7,
        source_refs=[source],
        people=[
            TrustedPersonPresence(
                subject_ref="person:dad" if status == "resolved" else "candidate:track-4",
                presence="entered",
                identity_status=status,
                identity_confidence=confidence,
                epistemic_status="established" if status == "resolved" else "provisional",
                source_refs=[source.reference_id],
            )
        ],
        audience_refs=audience or [],
    )


def test_trusted_social_perception_projects_source_truth_without_behavior() -> None:
    observed = perception(audience=["person:dad", "self:chromie"])
    situation = build_social_perception_situation_observation(observed)

    assert situation.goal_ids == []
    assert situation.projection.audience_refs == ["person:dad", "self:chromie"]
    values = {(item.relation, item.value) for item in situation.projection.interpretations}
    assert ("social.presence", "entered") in values
    assert ("social.identity_resolution", "resolved:0.940") in values
    assert all("greet" not in item.relation for item in situation.projection.interpretations)


def test_uncertain_identity_stays_candidate_in_situation() -> None:
    situation = build_social_perception_situation_observation(
        perception(status="candidate", confidence=0.41)
    )
    subject_refs = {item.subject_ref for item in situation.projection.interpretations}
    assert subject_refs == {"candidate:track-4"}
    assert any(item.value == "candidate:0.410" for item in situation.projection.interpretations)


def test_audience_must_come_from_present_source_truth() -> None:
    with pytest.raises(ValueError, match="audience refs"):
        perception(audience=["person:someone-not-observed", "self:chromie"])
