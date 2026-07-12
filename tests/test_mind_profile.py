from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.experience import ExperienceManager
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult
from shared.chromie_contracts.mind import (
    CorePrinciple,
    MindProfile,
    MindUpdateProposal,
    default_mind_profile,
)


class MindProfileTests(unittest.TestCase):
    def test_default_core_principles_require_owner_approval(self) -> None:
        profile = default_mind_profile()

        self.assertTrue(profile.owner_approved)
        self.assertEqual(profile.identity.name, "Chromie")
        self.assertEqual(profile.identity.kind, "embodied robot")
        self.assertEqual(profile.identity.gender, "female")
        self.assertEqual(profile.identity.age_description, "6 years old")
        self.assertEqual(profile.version, "0.1.2")
        self.assertIn("keep people company", profile.identity.short_self_description)
        self.assertIn("internal components", profile.identity.model_identity_boundary)
        self.assertIn("she", profile.identity.pronouns)
        self.assertIn(
            "generalization_first_ai",
            {principle.principle_id for principle in profile.core_principles},
        )
        self.assertGreaterEqual(len(profile.core_principles), 3)
        self.assertTrue(
            all(not principle.mutable_by_experience for principle in profile.core_principles)
        )
        self.assertTrue(
            all(
                principle.change_policy == "owner_approval_required"
                for principle in profile.core_principles
            )
        )
        self.assertIn("owner-approved", profile.prompt_summary())
        self.assertIn("Self model", profile.prompt_summary())
        self.assertIn("Chromie", profile.prompt_summary())
        self.assertIn("language_reasoner", profile.prompt_summary())
        context = profile.prompt_context()
        self.assertEqual(context["identity"]["name"], "Chromie")
        self.assertEqual(context["self_model"]["speaker_entity"]["entity_id"], "chromie")
        self.assertEqual(context["self_model"]["acting_entity_id"], "chromie")
        self.assertEqual(
            context["self_model"]["social_presentation"]["self_reference"],
            "Chromie",
        )
        self.assertNotIn("kind", context["self_model"]["speaker_entity"])
        self.assertNotIn("age_description", context["self_model"]["speaker_entity"])
        self.assertFalse(context["self_model"]["internal_components"][0]["speaker_entity"])
        self.assertEqual(
            context["self_model"]["internal_components"][0]["kind"],
            "language model",
        )
        self.assertNotIn("model_identity_boundary", context["identity"])
        self.assertIn(
            "generalization_first_ai",
            {item["id"] for item in profile.prompt_context()["core_principles"]},
        )

    def test_rejects_experience_mutable_core_principle(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be mutable by experience"):
            MindProfile(
                core_principles=[
                    CorePrinciple(
                        principle_id="bad",
                        statement="Bad mutable principle.",
                        mutable_by_experience=True,
                    )
                ]
            )

    def test_mind_manager_loads_owner_profile_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mind.json"
            payload = default_mind_profile().model_dump(mode="json")
            payload["profile_id"] = "owner_profile"
            path.write_text(json.dumps(payload), encoding="utf-8")

            manager = MindManager._load_profile(path)

        self.assertEqual(manager.profile_id, "owner_profile")

    def test_update_proposals_never_auto_apply(self) -> None:
        with self.assertRaisesRegex(ValueError, "must never auto-apply"):
            MindUpdateProposal(
                target="core_principle",
                proposed_change="Rewrite the core principle.",
                auto_apply=True,
            )


class ExperienceManagerTests(unittest.TestCase):
    def test_records_successful_interaction_without_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ExperienceManager(
                enabled=True,
                log_path=root / "experience.jsonl",
                proposal_path=root / "proposals.jsonl",
            )
            profile = default_mind_profile()
            response = InteractionResponse(
                metadata={
                    "experience_context": {
                        "user_text": "Please blink your eyes.",
                        "route": "robot_action",
                        "intent": "capability:soridormi.blink_eyes",
                        "route_source": "catalog",
                        "route_confidence": 0.86,
                        "conversation_id": "local_default",
                    }
                },
                skills=[
                    {
                        "request_id": "blink-1",
                        "skill_id": "soridormi.blink_eyes",
                    }
                ],
                speech=[{"text": "Blinking my eyes now."}],
            )
            execution = SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id="blink-1",
                        skill_id="soridormi.blink_eyes",
                        status="completed",
                    )
                ],
            )

            record = manager.record_interaction(
                response=response,
                execution=execution,
                session_id="sid-1",
                mind_profile=profile,
            )

            self.assertIsNotNone(record)
            self.assertEqual(record.route, "robot_action")
            self.assertEqual(record.selected_skills, ["soridormi.blink_eyes"])
            self.assertTrue(manager.log_path.exists())
            self.assertFalse(manager.proposal_path.exists())

    def test_failed_interaction_creates_human_review_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ExperienceManager(
                enabled=True,
                log_path=root / "experience.jsonl",
                proposal_path=root / "proposals.jsonl",
            )
            profile = default_mind_profile()
            response = InteractionResponse(
                metadata={
                    "experience_context": {
                        "user_text": "Please do the impossible task.",
                        "route": "robot_action",
                        "intent": "unknown",
                    }
                }
            )

            record = manager.record_interaction(
                response=response,
                execution=None,
                session_id="sid-2",
                mind_profile=profile,
                errors=["unknown skill"],
            )

            self.assertIsNotNone(record)
            proposal_lines = manager.proposal_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(proposal_lines), 1)
            proposal = json.loads(proposal_lines[0])
            self.assertTrue(proposal["requires_owner_approval"])
            self.assertFalse(proposal["auto_apply"])
            self.assertEqual(proposal["target"], "experience_tuned_strategy")

    def test_proposal_mismatch_creates_review_proposal_from_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ExperienceManager(
                enabled=True,
                log_path=root / "experience.jsonl",
                proposal_path=root / "proposals.jsonl",
            )
            profile = default_mind_profile()
            response = InteractionResponse(
                metadata={
                    "experience_context": {
                        "user_text": "Look out!",
                        "route": "deep_thought",
                        "intent": "warning",
                    },
                    "truth_reconciled": True,
                    "truth_reconciliation_reason": "quick_intent_misread_warning",
                    "task_proposal_ledger": {
                        "summary": {
                            "proposal_count": 2,
                            "not_committed_effectful_count": 1,
                            "states": {"committed": 1, "not_committed": 1},
                        },
                        "proposals": [
                            {
                                "id": "quick:0",
                                "state": "not_committed",
                                "args": {"do_not_store": "raw proposal payload"},
                            }
                        ],
                    },
                    "preflight_validation": {
                        "summary": {
                            "checked_skill_count": 1,
                            "blocked_count": 1,
                            "statuses": {"blocked": 1},
                        },
                        "items": [
                            {
                                "request_id": "bad-1",
                                "message": "do not store raw preflight item",
                            }
                        ],
                    },
                },
                speech=[{"text": "Thanks for warning me. I will hold still."}],
            )
            execution = SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
            )

            record = manager.record_interaction(
                response=response,
                execution=execution,
                session_id="sid-look-out",
                mind_profile=profile,
            )

            self.assertIsNotNone(record)
            log_payload = json.loads(manager.log_path.read_text(encoding="utf-8"))
            self.assertIn("task_proposal_summary", log_payload["metadata"])
            self.assertIn("preflight_summary", log_payload["metadata"])
            self.assertNotIn("proposals", json.dumps(log_payload["metadata"]))
            self.assertNotIn("items", json.dumps(log_payload["metadata"]))
            proposal = json.loads(manager.proposal_path.read_text(encoding="utf-8"))
            self.assertTrue(proposal["requires_owner_approval"])
            self.assertFalse(proposal["auto_apply"])
            self.assertIn("proposal/preflight mismatch", proposal["proposed_change"])


if __name__ == "__main__":
    unittest.main()
