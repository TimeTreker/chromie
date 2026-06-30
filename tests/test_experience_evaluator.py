from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.episode import EpisodeRecord, EpisodeTurnRecord
from scripts.evaluate_experience_episodes import (
    evaluate_episode_contract_precheck,
    scenario_candidate_from_episode,
    write_candidate_scenarios,
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


if __name__ == "__main__":
    unittest.main()
