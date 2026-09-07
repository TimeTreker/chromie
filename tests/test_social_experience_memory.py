from __future__ import annotations

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.situation import SituationalRelationshipMemoryCandidate


def test_cognitive_relationship_experience_is_private_bounded_memory() -> None:
    state = ConversationStateManager()
    candidate = SituationalRelationshipMemoryCandidate(
        text="Anna and Chromie drew together and Anna asked to keep the sketch private.",
        subject_refs=["person:anna"],
        source_refs=["social-feedback-1"],
        confidence=0.77,
        retention_seconds=3600,
    )
    stored = state.record_cognitive_relational_experience([candidate], sid="session-1")
    assert stored[0]["kind"] == "shared_experience"
    assert stored[0]["relation"] == "shared_experience"
    assert stored[0]["disclosure_scope"] == "private"
    assert stored[0]["subject_refs"] == ["person:anna"]
    assert stored[0]["source_ref_ids"] == ["social-feedback-1"]
    assert stored[0]["persistence_policy"] == "ephemeral"
