from __future__ import annotations

import pytest

from orchestrator.runtime.situation import build_social_feedback_situation_observation
from shared.chromie_contracts.situation import SituationalCommunicativeAct, SituationSourceRef
from shared.chromie_contracts.social_world import (
    TrustedSocialFeedbackObservation,
    TrustedSocialFeedbackSignal,
)


def feedback() -> TrustedSocialFeedbackObservation:
    source = SituationSourceRef(
        kind="perception", reference_id="reaction-frame-9", owner="trusted_social_signal_adapter"
    )
    return TrustedSocialFeedbackObservation(
        observation_id="reaction-9",
        source_id="trusted_social_signal_adapter",
        source_revision=9,
        source_refs=[source],
        reacts_to_activity_ids=["situational-greeting-1"],
        signals=[
            TrustedSocialFeedbackSignal(
                subject_ref="person:anna",
                relation="social.observed_signal",
                value="turned_away",
                epistemic_status="established",
                source_refs=[source.reference_id],
            )
        ],
        audience_refs=["person:anna", "self:chromie"],
    )


def test_social_feedback_projects_signal_and_exact_activity_target() -> None:
    situation = build_social_feedback_situation_observation(feedback())
    values = {(item.relation, item.value) for item in situation.projection.interpretations}
    assert ("social.observed_signal", "turned_away") in values
    assert ("social.feedback_target", "situational-greeting-1") in values
    assert situation.goal_ids == []


def test_repair_act_requires_exact_prior_activity_reference() -> None:
    repair = SituationalCommunicativeAct(
        activity_id="repair-1",
        text="啊，我刚才说得不太合适。",
        speech_act="repair",
        repair_of_activity_ids=["situational-greeting-1"],
    )
    assert repair.repair_of_activity_ids == ["situational-greeting-1"]

    with pytest.raises(ValueError, match="requires repair_of_activity_ids"):
        SituationalCommunicativeAct(
            activity_id="repair-2", text="抱歉。", speech_act="repair"
        )
