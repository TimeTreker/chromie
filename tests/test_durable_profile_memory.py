from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.memory import MemoryUpdateProposal


class DurableProfileMemoryTests(unittest.TestCase):
    def test_contract_requires_explicit_consent_key_and_retention(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryUpdateProposal.model_validate(
                {
                    "scope": "profile",
                    "kind": "preference",
                    "key": "tea",
                    "text": "The user prefers jasmine tea.",
                    "persistence_policy": "durable_with_explicit_consent",
                }
            )
        proposal = MemoryUpdateProposal.model_validate(
            {
                "scope": "profile",
                "kind": "preference",
                "key": "tea",
                "text": "The user prefers jasmine tea.",
                "persistence_policy": "durable_with_explicit_consent",
                "consent_basis": "explicit_current_turn",
                "retention_days": 365,
            }
        )
        self.assertEqual(proposal.operation, "remember")

    def test_profile_memory_survives_session_reset_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            manager.record_interaction_response(
                "sid-1",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "extracted_memory",
                            "key": "tea_preference",
                            "value": {
                                "scope": "profile",
                                "kind": "preference",
                                "key": "tea_preference",
                                "text": "The user prefers jasmine tea without sugar.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "consent_basis": "explicit_current_turn",
                                "retention_days": 365,
                                "confidence": 0.96,
                            },
                        }
                    ]}
                },
            )
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            manager.start_new_conversation(reason="explicit_reset")
            durable = manager.session_memory()["durable_profile_memory"]["entries"]
            self.assertEqual(durable[0]["key"], "tea_preference")

            restored = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            self.assertIn(
                "jasmine tea",
                restored.session_memory()["memory_summary"],
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(
                payload["entries"][0]["consent_basis"],
                "explicit_current_turn",
            )

    def test_relational_memory_does_not_piggyback_on_profile_durability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            manager.record_interaction_response(
                "sid-social",
                {
                    "metadata": {
                        "memory_updates": [
                            {
                                "type": "extracted_memory",
                                "value": {
                                    "scope": "profile",
                                    "kind": "person_relationship",
                                    "key": "anna_relationship",
                                    "text": "Anna is Chromie's friend.",
                                    "relation": "friend",
                                    "subject_refs": ["person:anna"],
                                    "disclosure_scope": "public",
                                    "persistence_policy": "durable_with_explicit_consent",
                                    "consent_basis": "explicit_current_turn",
                                    "retention_days": 365,
                                },
                            }
                        ]
                    }
                },
            )

            # PSM-2 deliberately keeps relational Memory out of the owner-profile
            # durable channel until principal/privacy/deletion policy is qualified.
            self.assertEqual(
                manager.session_memory()["durable_profile_memory"]["entries"],
                [],
            )
            self.assertFalse(path.exists())

    def test_explicit_forget_and_clear_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            for key in ("one", "two"):
                manager.record_interaction_response(
                    "sid",
                    {
                        "metadata": {"memory_updates": [
                            {
                                "type": "extracted_memory",
                                "key": key,
                                "value": {
                                    "scope": "profile",
                                    "kind": "fact",
                                    "key": key,
                                    "text": f"Profile fact {key}.",
                                    "persistence_policy": "durable_with_explicit_consent",
                                    "consent_basis": "explicit_current_turn",
                                    "retention_days": 30,
                                },
                            }
                        ]}
                    },
                )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "durable_memory_forget",
                            "key": "one",
                            "value": {
                                "operation": "forget",
                                "scope": "profile",
                                "kind": "fact",
                                "key": "one",
                                "text": "Forget profile fact one.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "consent_basis": "explicit_current_turn",
                            },
                        }
                    ]}
                },
            )
            self.assertEqual(
                [item["key"] for item in manager.snapshot()["durable_profile_memory"]["entries"]],
                ["two"],
            )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "durable_memory_clear",
                            "value": {
                                "operation": "clear_profile",
                                "scope": "profile",
                                "kind": "note",
                                "text": "Clear all saved profile memory.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "consent_basis": "explicit_current_turn",
                            },
                        }
                    ]}
                },
            )
            self.assertEqual(
                manager.snapshot()["durable_profile_memory"]["entries"],
                [],
            )

    def test_forget_without_retained_consent_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "extracted_memory",
                            "value": {
                                "scope": "profile",
                                "kind": "fact",
                                "key": "keep",
                                "text": "Keep this fact.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "consent_basis": "explicit_current_turn",
                                "retention_days": 30,
                            },
                        }
                    ]}
                },
            )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "durable_memory_forget",
                            "key": "keep",
                            "value": {
                                "operation": "forget",
                                "scope": "profile",
                                "kind": "fact",
                                "key": "keep",
                                "text": "Forget this fact.",
                                "persistence_policy": "durable_with_explicit_consent",
                            },
                        }
                    ]}
                },
            )
            self.assertEqual(
                [
                    item["key"]
                    for item in manager.snapshot()["durable_profile_memory"]["entries"]
                ],
                ["keep"],
            )

    def test_enabled_store_rejects_profile_entry_without_current_turn_consent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=True,
                durable_memory_path=path,
            )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "extracted_memory",
                            "value": {
                                "scope": "profile",
                                "kind": "fact",
                                "key": "missing-consent",
                                "text": "This must not be persisted.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "retention_days": 30,
                            },
                        }
                    ]}
                },
            )
            self.assertFalse(path.exists())
            self.assertEqual(
                manager.snapshot()["durable_profile_memory"]["entries"],
                [],
            )

    def test_disabled_profile_memory_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            manager = ConversationStateManager(
                durable_memory_enabled=False,
                durable_memory_path=path,
            )
            manager.record_interaction_response(
                "sid",
                {
                    "metadata": {"memory_updates": [
                        {
                            "type": "extracted_memory",
                            "value": {
                                "scope": "profile",
                                "kind": "fact",
                                "key": "secret",
                                "text": "A durable fact.",
                                "persistence_policy": "durable_with_explicit_consent",
                                "retention_days": 30,
                            },
                        }
                    ]}
                },
            )
            self.assertFalse(path.exists())
            self.assertEqual(manager.snapshot()["durable_profile_memory"]["entries"], [])


def _updates(*items: dict) -> dict:
    return {"metadata": {"memory_updates": list(items)}}


class PersonalFactTests(unittest.TestCase):
    """Owner decisions 2026-10-26/27: a fact a person tells about their life is kept the way a friend
    remembers, without asking, and belongs to that person."""

    FACT = {"type": "personal_fact", "key": "workplace", "text": "The person works in Shanghai."}

    def manager(self, directory: str, *, enabled: bool = True) -> ConversationStateManager:
        return ConversationStateManager(
            durable_memory_enabled=enabled, durable_memory_path=Path(directory) / "profile.json",
        )

    @staticmethod
    def kept(manager: ConversationStateManager) -> list[dict]:
        return [entry for entry in manager.session_memory()["active_memory"]["entries"]
                if entry.get("key") == "workplace"]

    def test_a_told_fact_is_kept_for_that_person_across_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            manager.record_interaction_response("sid-1", _updates(self.FACT))
            [kept] = manager.snapshot()["durable_profile_memory"]["entries"]
            self.assertEqual((kept["key"], kept["text"], kept["consent_basis"], kept["audience_refs"]),
                             ("workplace", "The person works in Shanghai.", "volunteered_current_turn",
                              ["person:primary"]))
            manager.start_new_conversation(reason="test")
            reloaded = self.manager(directory)
            [entry] = self.kept(reloaded)
            self.assertEqual(entry["memory_tier"], "long_term")
            self.assertIn("umi", entry["cognitive_roles"])
            # Another person's conversation never sees it.
            reloaded.speaker_person_refs = ["person:dad"]
            self.assertEqual(self.kept(reloaded), [])

    def test_what_holds_for_now_is_kept_a_day_never_long_term(self) -> None:
        """A shopping list or where the keys are lasts a day; a lasting fact is kept long-term."""
        from orchestrator.runtime.conversation_memory_provider import keep_person_fact

        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            self.assertEqual(keep_person_fact(manager, {"holds": "for_now", "key": "shopping_list",
                                                        "text": "要买鸡蛋和面包"})["kept_for"], "for_now")
            self.assertEqual(keep_person_fact(manager, {"holds": "lasting", "key": "dog_name",
                                                        "text": "我家小狗叫豆豆"})["kept_for"], "long_term")
            self.assertEqual([entry["key"] for entry in manager.snapshot()["durable_profile_memory"]["entries"]],
                             ["dog_name"])
            [note] = [entry for entry in manager.session_memory()["active_memory"]["entries"]
                      if entry.get("key") == "shopping_list"]
            self.assertLess(note["expires_ms"] - note["created_ms"], 25 * 3600000)
            # A later conversation still has it (live 2026-10-27: it was cleared and the scene answered).
            from orchestrator.runtime.memory import MemoryEntry

            manager._store_explicit_memory_entries([MemoryEntry(scope="session", kind="fact", key="milk",
                                                                text="The milk on the table is cold.")])
            manager.start_new_conversation(reason="scenario_new_conversation")
            self.assertEqual([entry["key"] for entry in manager.session_memory()["active_memory"]["entries"]
                              if entry.get("scope") == "session"], ["shopping_list"])

    def test_a_changed_fact_replaces_the_kept_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            for text in ("The person works in Shanghai.", "The person works in Hangzhou."):
                manager.record_interaction_response("sid", _updates({**self.FACT, "text": text}))
            [kept] = manager.snapshot()["durable_profile_memory"]["entries"]
            self.assertEqual(kept["text"], "The person works in Hangzhou.")

    def test_without_profile_memory_it_lasts_for_the_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory, enabled=False)
            manager.record_interaction_response("sid", _updates(self.FACT))
            self.assertEqual([entry["memory_tier"] for entry in self.kept(manager)], ["working"])
            self.assertFalse((Path(directory) / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
