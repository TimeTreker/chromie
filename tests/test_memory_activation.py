from __future__ import annotations

from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.memory import MemoryEntry, MemoryStore


def test_memory_store_activates_old_relevant_entry_before_recent_noise() -> None:
    store = MemoryStore(max_entries=16)
    store.add(
        MemoryEntry(
            scope="session",
            kind="ownership",
            key="blue_cup_owner",
            text="蓝色杯子是用户的。",
            confidence=0.95,
        )
    )
    for index in range(10):
        store.add(
            MemoryEntry(
                scope="session",
                kind="note",
                key=f"noise_{index}",
                text=f"Unrelated recent note number {index} about music.",
            )
        )

    activated = store.prompt_entries(
        limit=3,
        activation_texts=["我的蓝色杯子在哪里？"],
    )

    assert activated[0]["key"] == "blue_cup_owner"
    assert any(item["key"] == "noise_9" for item in activated)


def test_session_memory_uses_current_user_context_instead_of_recency_alone() -> None:
    manager = ConversationStateManager(base_conversation_id="memory-activation")
    manager.record_interaction_response(
        "sid-old",
        {
            "metadata": {"memory_updates": [
                {
                    "type": "extracted_memory",
                    "value": {
                        "scope": "session",
                        "kind": "ownership",
                        "key": "blue_cup_owner",
                        "text": "The blue cup belongs to the user.",
                    },
                }
            ]}
        },
    )
    for index in range(12):
        manager.record_interaction_response(
            f"sid-noise-{index}",
            {
                "metadata": {"memory_updates": [
                    {
                        "type": "extracted_memory",
                        "value": {
                            "scope": "session",
                            "kind": "note",
                            "key": f"noise_{index}",
                            "text": f"Recent unrelated music note {index}.",
                        },
                    }
                ]}
            },
        )

    manager.record_user_turn("sid-current", "Where is my blue cup?")
    memory = manager.session_memory()

    assert memory["memory_selection"] == {
        "policy": "context_relevance_then_recency",
        "activation_source_count": 1,
    }
    assert memory["extracted_memory"][0]["key"] == "blue_cup_owner"
    assert "blue cup belongs" in memory["memory_summary"]


def test_memory_without_current_activation_keeps_recent_fallback() -> None:
    store = MemoryStore(max_entries=8)
    for index in range(5):
        store.add(
            MemoryEntry(
                scope="session",
                kind="note",
                key=f"note_{index}",
                text=f"Note {index}",
            )
        )

    selected = store.prompt_entries(limit=2)

    assert [item["key"] for item in selected] == ["note_3", "note_4"]


def test_structured_subject_ref_activates_old_public_relationship_memory() -> None:
    store = MemoryStore(max_entries=16)
    store.add(
        MemoryEntry(
            scope="session",
            kind="person_relationship",
            key="dad_relationship",
            text="Dad is a close family relationship for Chromie.",
            relation="family",
            subject_refs=["person:dad"],
            source_person_refs=["person:dad"],
            disclosure_scope="public",
            confidence=0.95,
        )
    )
    for index in range(8):
        store.add(
            MemoryEntry(
                scope="session",
                kind="note",
                key=f"noise_{index}",
                text=f"Unrelated recent note {index} about drawing.",
            )
        )

    activated = store.prompt_entries(
        limit=3,
        activation_subject_refs=["person:dad"],
    )

    assert activated[0]["key"] == "dad_relationship"
    assert activated[0]["subject_refs"] == ["person:dad"]
    assert activated[0]["relation"] == "family"


def test_privacy_aware_relational_memory_fails_closed_without_resolved_audience() -> None:
    store = MemoryStore(max_entries=8)
    store.add(
        MemoryEntry(
            scope="session",
            kind="shared_experience",
            key="anna_private_topic",
            text="Anna privately shared a sensitive school concern with Chromie.",
            relation="shared_private_context",
            subject_refs=["person:anna"],
            source_person_refs=["person:anna"],
            audience_refs=["person:anna", "self:chromie"],
            disclosure_scope="shared_with_audience",
            confidence=0.9,
        )
    )

    hidden = store.prompt_entries(
        activation_subject_refs=["person:anna"],
        audience_refs=[],
    )
    visible_to_original_audience = store.prompt_entries(
        activation_subject_refs=["person:anna"],
        audience_refs=["person:anna"],
    )
    hidden_from_other_person = store.prompt_entries(
        activation_subject_refs=["person:anna"],
        audience_refs=["person:dad"],
    )

    assert hidden == []
    assert [item["key"] for item in visible_to_original_audience] == [
        "anna_private_topic"
    ]
    assert hidden_from_other_person == []


def test_relational_memory_without_disclosure_scope_defaults_to_unknown() -> None:
    entry = MemoryEntry(
        scope="session",
        kind="person_relationship",
        text="David is Dad's friend.",
        relation="friend_of",
        subject_refs=["person:david", "person:dad"],
    )
    store = MemoryStore(max_entries=4)
    store.add(entry)

    assert entry.disclosure_scope == "unknown"
    assert store.prompt_entries(activation_subject_refs=["person:david"]) == []


def test_build_context_uses_disclosure_safe_memory_projection_not_raw_snapshot() -> None:
    from types import SimpleNamespace

    from orchestrator.orchestrator import VoiceAssistant

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.is_playing_audio = False
    assistant.playback_generation = 0
    assistant.action_dry_run = False
    assistant.mind = SimpleNamespace(context=lambda: {})
    assistant._interaction_engagement_context = lambda *_args, **_kwargs: {}
    assistant.conversation_state = SimpleNamespace(
        snapshot=lambda: {
            "conversation_id": "conversation-private",
            "session_memory": {
                "memory_summary": "None",
                "extracted_memory": [],
            },
            "extracted_memory": [
                {
                    "kind": "shared_experience",
                    "text": "Private raw retained memory must not enter model context.",
                    "subject_refs": ["person:anna"],
                    "disclosure_scope": "private",
                }
            ],
        },
        active_goal_snapshots=lambda: [],
    )

    context = assistant.build_context(None)

    assert context["extracted_memory"] == []
    assert context["conversation"]["extracted_memory"][0]["disclosure_scope"] == "private"
