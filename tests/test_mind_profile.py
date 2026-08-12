from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from orchestrator.runtime.experience import ExperienceManager
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult
from shared.chromie_contracts.mind import (
    CorePrinciple,
    MindProfile,
    SocialInteractionStyle,
    MindUpdateProposal,
    default_mind_profile,
    default_mind_profile_path,
)


class MindProfileTests(unittest.TestCase):
    def test_default_core_principles_require_owner_approval(self) -> None:
        profile = default_mind_profile()

        self.assertTrue(profile.owner_approved)
        self.assertEqual(profile.identity.name, "Chromie")
        self.assertEqual(profile.identity.kind, "human child")
        self.assertEqual(profile.identity.gender, "female")
        self.assertEqual(profile.identity.age_description, "6 years old")
        self.assertEqual(profile.version, "0.6.1")
        self.assertIn("family's little secretary", profile.identity.short_self_description)
        self.assertIn("six-year-old human child", profile.identity.model_identity_boundary)
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
        self.assertIn("family role", profile.prompt_summary())
        self.assertIn("Social interaction style", profile.prompt_summary())
        context = profile.prompt_context()
        self.assertEqual(context["identity"]["name"], "Chromie")
        self.assertEqual(context["self_model"]["speaker_entity"]["entity_id"], "chromie")
        self.assertEqual(context["self_model"]["acting_entity_id"], "chromie")
        self.assertTrue(
            context["social_interaction_style"]["owner_approved"]
        )
        self.assertTrue(context["personality_expression"]["owner_approved"])
        self.assertIn("smart", context["personality_expression"]["core_traits"])
        self.assertIn("six-year-old human girl", context["personality_expression"]["self_concept"])
        self.assertIn("question first", context["personality_expression"]["answer_style"])
        self.assertIn("logs and memory", context["personality_expression"]["internal_language_boundary"])
        self.assertIn(
            "explicit user action",
            context["social_interaction_style"]["restraint"],
        )
        self.assertIn(
            "recent auxiliary-behavior evidence",
            context["social_interaction_style"]["repetition_guidance"],
        )
        self.assertEqual(
            context["self_model"]["social_presentation"]["self_reference"],
            "Chromie",
        )
        self.assertNotIn("kind", context["self_model"]["speaker_entity"])
        self.assertNotIn("age_description", context["self_model"]["speaker_entity"])
        self.assertEqual(
            context["self_model"]["social_presentation"]["family_role"],
            "the family's secretary",
        )
        self.assertNotIn("internal_components", context["self_model"])
        self.assertIn("model_identity_boundary", context["identity"])
        self.assertNotIn("robot", context["identity"]["model_identity_boundary"].casefold())
        self.assertIn(
            "generalization_first_ai",
            {item["id"] for item in profile.prompt_context()["core_principles"]},
        )



    def test_default_identity_is_loaded_from_owner_editable_json(self) -> None:
        path = default_mind_profile_path(Path(__file__).resolve().parents[1])
        self.assertEqual(path.as_posix().split("/")[-3:], ["config", "mind", "chromie_default.json"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["identity"]["name"], "Chromie")
        self.assertEqual(payload["identity"]["age_description"], "6 years old")
        self.assertEqual(payload["identity"]["family_role"], "the family's secretary")
        self.assertTrue(
            MindProfile.model_fields["identity"].is_required(),
            "MindProfile identity must come from configuration, not a Python default",
        )

    def test_owner_can_change_identity_without_code_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mind.json"
            payload = default_mind_profile().model_dump(mode="json")
            payload["profile_id"] = "owner_custom_identity"
            payload["identity"]["name"] = "Nova"
            payload["identity"]["age_description"] = "3 years old"
            payload["identity"]["short_self_description"] = "I'm Nova. I'm three years old and I like learning with people."
            payload["identity"]["identity_answer_guidance"] = (
                "Use the configured name Nova and age 3 years old for direct identity questions."
            )
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, {"ORCH_MIND_PROFILE_PATH": str(path)}, clear=False):
                manager = MindManager.from_env(project_root=Path(tmp))

        self.assertEqual(manager.profile.identity.name, "Nova")
        self.assertEqual(manager.profile.identity.age_description, "3 years old")
        self.assertEqual(manager.profile_path, path)

    def test_social_interaction_style_presets_are_operator_selectable(self) -> None:
        courteous = SocialInteractionStyle(preset="courteous")
        neutral = SocialInteractionStyle(preset="neutral")
        reserved = SocialInteractionStyle(preset="reserved")

        self.assertEqual(courteous.preset, "courteous")
        self.assertIn("greetings", courteous.bounded_courtesy)
        self.assertIn("normal baseline", neutral.expressiveness)
        self.assertIn("Prefer stillness", reserved.expressiveness)
        self.assertNotEqual(courteous.expressiveness, reserved.expressiveness)

    def test_custom_social_interaction_style_requires_complete_guidance(self) -> None:
        with self.assertRaisesRegex(ValueError, "custom social interaction style"):
            SocialInteractionStyle(preset="custom")

    def test_mind_manager_applies_operator_style_preset_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {"ORCH_SOCIAL_INTERACTION_STYLE_PRESET": "reserved"},
            clear=False,
        ):
            manager = MindManager.from_env()

        self.assertEqual(manager.profile.social_interaction_style.preset, "reserved")
        self.assertIn(
            "Prefer stillness",
            manager.profile.social_interaction_style.expressiveness,
        )

    def test_rejects_experience_mutable_core_principle(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be mutable by experience"):
            MindProfile(
                identity=default_mind_profile().identity,
                personality_expression=default_mind_profile().personality_expression,
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

    def test_missing_ability_is_retained_for_owner_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ExperienceManager(
                enabled=True,
                log_path=root / "experience.jsonl",
                proposal_path=root / "proposals.jsonl",
            )
            profile = default_mind_profile()
            response = InteractionResponse(
                status="clarify",
                reason="missing_or_unsupported_ability",
                metadata={
                    "experience_context": {
                        "user_text": "附近有什么好吃的餐厅？",
                        "route": "clarify",
                        "intent": "missing_or_unsupported_ability",
                    },
                    "task_proposal_ledger": {
                        "summary": {
                            "proposal_count": 2,
                            "effectful_proposal_count": 0,
                            "states": {
                                "missing_ability": 1,
                                "committed": 1,
                            },
                        },
                        "proposals": [
                            {
                                "id": "semantic_route_repair:ability:0",
                                "state": "missing_ability",
                                "ability_id": "local.restaurant_recommendation",
                                "reason": "No restaurant lookup capability is available.",
                                "metadata": {
                                    "intent": "Recommend good restaurants near the user",
                                    "confidence": 1.0,
                                },
                            },
                            {
                                "id": "interaction_response:speech:0",
                                "state": "committed",
                                "args": {"must_not_store": "raw speech proposal"},
                            },
                        ],
                    },
                },
                speech=[
                    {
                        "text": (
                            "我明白你想找附近好吃的餐厅，不过我现在还没有这个能力。"
                        )
                    }
                ],
            )
            execution = SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
            )

            record = manager.record_interaction(
                response=response,
                execution=execution,
                session_id="sid-missing-restaurant",
                mind_profile=profile,
            )

            self.assertIsNotNone(record)
            assert record is not None
            requests = record.metadata["missing_ability_requests"]
            self.assertEqual(
                requests[0]["ability_id"],
                "local.restaurant_recommendation",
            )
            self.assertEqual(
                requests[0]["intent"],
                "Recommend good restaurants near the user",
            )
            self.assertNotIn("must_not_store", json.dumps(record.metadata))
            proposal = json.loads(manager.proposal_path.read_text(encoding="utf-8"))
            self.assertIn(
                "local.restaurant_recommendation",
                proposal["proposed_change"],
            )
            self.assertTrue(proposal["requires_owner_approval"])
            self.assertFalse(proposal["auto_apply"])

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


def test_mind_profile_rejects_unapproved_profile() -> None:
    payload = default_mind_profile().model_dump(mode="json")
    payload["owner_approved"] = False
    with unittest.TestCase().assertRaisesRegex(ValueError, "owner-approved"):
        MindProfile.model_validate(payload)
