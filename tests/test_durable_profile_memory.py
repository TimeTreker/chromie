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


if __name__ == "__main__":
    unittest.main()
