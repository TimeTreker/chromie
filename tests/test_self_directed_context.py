from __future__ import annotations

import pytest

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.situation import SituationalSelfMemoryCandidate


def test_short_lived_self_concern_is_context_not_goal_or_action() -> None:
    state = ConversationStateManager()
    candidate = SituationalSelfMemoryCandidate(
        kind="interest",
        text="Chromie wants to continue the drawing she was working on.",
        subject_refs=["self:chromie"],
        source_refs=["situation:drawing-table"],
        confidence=0.82,
        retention_seconds=1800,
    )
    stored = state.record_cognitive_self_context([candidate], sid="session-self")
    assert stored[0]["kind"] == "interest"
    assert stored[0]["disclosure_scope"] == "self_context"
    assert stored[0]["persistence_policy"] == "ephemeral"
    assert "Goal" in stored[0]["safety_note"]

    visible = state.activated_memory_context(
        activation_texts=["drawing"],
        activation_subject_refs=["self:chromie"],
        audience_refs=[],
        limit=8,
    )
    assert any(item["kind"] == "interest" for item in visible["entries"])


def test_self_context_candidate_must_remain_about_chromie() -> None:
    with pytest.raises(ValueError, match="self:chromie"):
        SituationalSelfMemoryCandidate(
            kind="self_concern",
            text="Something to remember.",
            subject_refs=["person:anna"],
            source_refs=["source-1"],
        )
