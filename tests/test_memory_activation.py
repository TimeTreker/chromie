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
