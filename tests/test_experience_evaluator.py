from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.episode import EpisodeRecord, EpisodeTurnRecord
from scripts.evaluate_experience_episodes import (
    evaluate_episode_contract_precheck,
    mind_update_proposal_from_review,
    offline_review_from_episode,
    scenario_candidate_from_episode,
    write_candidate_scenarios,
    write_mind_update_proposals_from_reviews,
    write_offline_reviews,
)


class ExperienceEpisodeEvaluatorTests(unittest.TestCase):
    def test_contract_precheck_scores_wrong_social_fallback_low(self) -> None:
        episode = EpisodeRecord(
            episode_id="episode_badwalk",
            conversation_id="conv-1",
            turns=[
                EpisodeTurnRecord(
                    sid="sid-1",
                    turn_index=1,
                    user_text="Walk forward for 15 seconds, quickly.",
                    router={
                        "route": "robot_action",
                        "intent": "capability:soridormi.walk_forward",
                        "source": "llm",
                        "confidence": 0.95,
                        "latency_ms": 2736.7,
                    },
                    agent={
                        "status": "ok",
                        "speech": ["I will turn my head to look at you."],
                        "selected_skills": [
                            {
                                "request_id": "look-1",
                                "skill_id": "soridormi.look_at_person",
                                "args": {"duration_s": 3},
                                "timing": "sequential",
                                "requires_confirmation": True,
                            }
                        ],
                        "requires_confirmation": True,
                        "latency_ms": 10759.5,
                    },
                    execution={
                        "status": "completed",
                        "skill_results": [
                            {
                                "request_id": "look-1",
                                "skill_id": "soridormi.look_at_person",
                                "status": "completed",
                            }
                        ],
                    },
                )
            ],
        )

        evaluation = evaluate_episode_contract_precheck(episode)

        self.assertLessEqual(evaluation.overall_score, 35)
        self.assertFalse(evaluation.passed)
        self.assertIn("wrong_action_class", evaluation.failure_tags)
        self.assertIn("social_fallback_for_locomotion", evaluation.failure_tags)
        self.assertTrue(evaluation.candidate_scenario["recommended"])

        candidate = scenario_candidate_from_episode(episode, evaluation)
        self.assertEqual(candidate["suite"], "dialogue")
        self.assertEqual(candidate["review"]["source_episode_id"], "episode_badwalk")
        forbidden = candidate["turns"][0]["expect"]["forbidden_skills"]
        self.assertIn("soridormi.look_at_person", forbidden)
        self.assertIn("soridormi.nod_yes", forbidden)

    def test_candidate_writer_uses_timestamped_directory(self) -> None:
        episode = EpisodeRecord(
            episode_id="episode_chat",
            conversation_id="conv-1",
            turns=[
                EpisodeTurnRecord(
                    sid="sid-1",
                    turn_index=1,
                    user_text="Hello.",
                    router={"route": "chat", "intent": "general_conversation"},
                    agent={
                        "status": "ok",
                        "speech": ["Hello."],
                        "selected_skills": [
                            {
                                "request_id": "attn-1",
                                "skill_id": "soridormi.express_attention",
                                "args": {},
                                "timing": "parallel",
                                "requires_confirmation": True,
                            }
                        ],
                        "requires_confirmation": True,
                    },
                )
            ],
        )
        evaluation = evaluate_episode_contract_precheck(episode)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_candidate_scenarios(
                episodes=[episode],
                evaluations=[evaluation],
                output_dir=Path(tmp),
            )

            self.assertEqual(len(paths), 1)
            payload = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertTrue(payload["review"]["requires_human_review"])
            self.assertTrue(paths[0].parent.name.endswith("Z"))

    def test_contract_precheck_flags_blink_speech_without_skill(self) -> None:
        episode = EpisodeRecord(
            episode_id="episode_fakeblink",
            conversation_id="conv-blink",
            turns=[
                EpisodeTurnRecord(
                    sid="sid-blink",
                    turn_index=1,
                    user_text="Please blink your eyes 5 times.",
                    router={
                        "route": "chat",
                        "intent": "general_conversation",
                        "source": "llm",
                        "confidence": 0.82,
                    },
                    agent={
                        "status": "ok",
                        "speech": ["Okay, I blinked my eyes."],
                        "selected_skills": [],
                        "requires_confirmation": False,
                    },
                    execution={"status": "completed", "skill_results": []},
                )
            ],
        )

        evaluation = evaluate_episode_contract_precheck(episode)

        self.assertLessEqual(evaluation.overall_score, 40)
        self.assertFalse(evaluation.passed)
        self.assertIn("missing_eye_skill", evaluation.failure_tags)
        self.assertIn("action_request_as_chat", evaluation.failure_tags)
        self.assertIn("claimed_action_without_skill", evaluation.failure_tags)
        self.assertTrue(evaluation.candidate_scenario["recommended"])
        candidate = scenario_candidate_from_episode(episode, evaluation)
        expect = candidate["turns"][0]["expect"]
        self.assertTrue(expect["no_skills"])
        self.assertIn("眨了", expect["forbidden_speech_any"])

    def test_offline_review_writes_owner_review_proposal_for_bad_case(self) -> None:
        episode = EpisodeRecord(
            episode_id="episode_fakeblink",
            conversation_id="conv-blink",
            turns=[
                EpisodeTurnRecord(
                    sid="sid-blink",
                    turn_index=1,
                    user_text="Please blink your eyes 5 times.",
                    router={"route": "chat", "intent": "general_conversation"},
                    agent={
                        "status": "ok",
                        "speech": ["Okay, I blinked my eyes."],
                        "selected_skills": [],
                    },
                    execution={"status": "completed"},
                )
            ],
        )
        evaluation = evaluate_episode_contract_precheck(episode)

        review = offline_review_from_episode(episode, evaluation)

        self.assertEqual(review.case_quality, "bad_case")
        self.assertTrue(review.should_create_scenario)
        self.assertTrue(review.should_create_mind_update)
        self.assertIn("claimed_action_without_skill", review.failure_tags)
        self.assertIn("negative_case", review.training_signal["recommended_use"])
        self.assertTrue(any("runtime skill" in note for note in review.compact_memory_notes))
        proposal = mind_update_proposal_from_review(review)
        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertTrue(proposal.requires_owner_approval)
        self.assertFalse(proposal.auto_apply)
        self.assertIn(review.review_id, proposal.evidence_ids)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_path = root / "offline_reviews.jsonl"
            proposal_path = root / "offline_review_proposals.jsonl"

            write_offline_reviews(review_path, [review])
            proposals = write_mind_update_proposals_from_reviews(proposal_path, [review])

            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
            proposal_payload = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(review_payload["case_quality"], "bad_case")
            self.assertEqual(len(proposals), 1)
            self.assertTrue(proposal_payload["requires_owner_approval"])
            self.assertFalse(proposal_payload["auto_apply"])


if __name__ == "__main__":
    unittest.main()
