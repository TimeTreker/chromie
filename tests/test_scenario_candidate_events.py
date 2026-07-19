from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.chromie_runtime.scenario_candidates import persist_scenario_candidate_event


class ScenarioCandidateEventTests(unittest.TestCase):
    def test_persists_pending_review_candidate_with_evidence(self) -> None:
        candidate = {
            "schema_version": 1,
            "id": "candidate_walk_not_social_fallback_001",
            "suite": "dialogue",
            "level": "integration",
            "review": {
                "status": "pending_human_review",
                "source_episode_id": "episode-1",
                "source_evaluation_id": "eval-1",
                "source_conversation_id": "conv-1",
                "requires_human_review": True,
            },
            "promotion": {
                "regression_allowed": False,
                "training_allowed": False,
                "auto_promotion_allowed": False,
                "required_review_status": "approved",
            },
            "turns": [],
        }
        episode = {"episode_id": "episode-1", "conversation_id": "conv-1"}
        evaluation = {
            "evaluation_id": "eval-1",
            "severity": "major",
            "overall_score": 30,
            "failure_tags": ["wrong_action_class"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = persist_scenario_candidate_event(
                candidate=candidate,
                episode=episode,
                evaluation=evaluation,
                event_root=root / "events",
                trigger_root=root / "inbox",
            )

            self.assertEqual(result["capture_status"], "complete")
            self.assertEqual(result["trigger_status"], "accepted")
            ready = Path(result["payload_root"])
            manifest = json.loads((ready / "event.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["event_type"], "chromie.scenario_candidate")
            self.assertEqual(manifest["correlations"]["episode_id"], "episode-1")
            self.assertFalse(manifest["derivation"]["scenario_auto_promotion_allowed"])
            payload = json.loads(
                (ready / "scenario_candidate.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["review"]["status"], "pending_human_review")

    def test_rejects_candidate_that_allows_unreviewed_promotion(self) -> None:
        candidate = {
            "id": "candidate_bad",
            "review": {
                "status": "pending_human_review",
                "requires_human_review": True,
            },
            "promotion": {
                "regression_allowed": True,
                "training_allowed": False,
                "auto_promotion_allowed": False,
            },
        }
        with self.assertRaises(ValueError):
            persist_scenario_candidate_event(
                candidate=candidate,
                episode={},
                evaluation={},
            )


if __name__ == "__main__":
    unittest.main()
