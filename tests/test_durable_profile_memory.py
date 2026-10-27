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


class PersonalFactConsentTests(unittest.TestCase):
    """Owner decision 2026-10-26: Chromie asks before keeping a fact the person told her long-term."""

    FACT = {"type": "personal_fact", "key": "workplace", "text": "The person works in Shanghai."}

    def manager(self, directory: str, *, enabled: bool = True) -> ConversationStateManager:
        return ConversationStateManager(
            durable_memory_enabled=enabled, durable_memory_path=Path(directory) / "profile.json",
        )

    def test_told_fact_is_working_memory_and_pending_consent_until_asked_and_answered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            manager.record_interaction_response("sid-1", _updates(self.FACT))
            memory = manager.session_memory()
            working = [entry for entry in memory["active_memory"]["entries"] if entry.get("key") == "workplace"]
            self.assertEqual([entry["memory_tier"] for entry in working], ["working"])
            self.assertIn("umi", working[0]["cognitive_roles"])
            self.assertEqual(memory["durable_profile_memory"]["pending_consent"],
                             {"key": "workplace", "text": "The person works in Shanghai.", "asked": False})
            # A yes before Chromie's question was heard keeps nothing.
            manager.record_interaction_response(
                "sid-2", _updates({"type": "memory_consent_reply", "key": "workplace", "answer": "yes"}))
            self.assertEqual(manager.snapshot()["durable_profile_memory"]["entries"], [])

    def test_yes_to_the_asked_question_keeps_the_fact_under_its_key_for_later_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            manager.record_interaction_response("sid-1", _updates(self.FACT))
            manager.record_interaction_response("sid-1", _updates({"type": "memory_consent_asked", "key": "workplace"}))
            manager.record_interaction_response(
                "sid-2", _updates({"type": "memory_consent_reply", "key": "workplace", "answer": "yes"}))
            [kept] = manager.snapshot()["durable_profile_memory"]["entries"]
            self.assertEqual((kept["key"], kept["text"], kept["consent_basis"], kept["scope"]),
                             ("workplace", "The person works in Shanghai.", "explicit_current_turn", "profile"))
            self.assertIsNone(manager.session_memory()["durable_profile_memory"]["pending_consent"])

            manager.start_new_conversation(reason="test")
            reloaded = self.manager(directory)
            entries = [entry for entry in reloaded.session_memory()["active_memory"]["entries"]
                       if entry.get("key") == "workplace"]
            self.assertEqual([entry["memory_tier"] for entry in entries], ["long_term"])
            self.assertIn("umi", entries[0]["cognitive_roles"])

    def test_a_changed_fact_replaces_the_kept_one_and_no_keeps_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            for text, answer in (("The person works in Shanghai.", "yes"),
                                 ("The person works in Hangzhou.", "yes"),
                                 ("The person works in Suzhou.", "no")):
                manager.record_interaction_response("sid", _updates(
                    {**self.FACT, "text": text}, {"type": "memory_consent_asked", "key": "workplace"},
                    {"type": "memory_consent_reply", "key": "workplace", "answer": answer}))
            [kept] = manager.snapshot()["durable_profile_memory"]["entries"]
            self.assertEqual(kept["text"], "The person works in Hangzhou.")

    def test_without_profile_memory_nothing_is_offered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory, enabled=False)
            manager.record_interaction_response("sid", _updates(self.FACT))
            self.assertIsNone(manager.session_memory()["durable_profile_memory"]["pending_consent"])
            self.assertFalse((Path(directory) / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
