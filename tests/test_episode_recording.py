from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.episode import EpisodeRecorder, EpisodeRecord
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from shared.chromie_contracts.interaction import InteractionResponse, SkillResult
from shared.chromie_contracts.mind import default_mind_profile


class EpisodeRecorderTests(unittest.TestCase):
    def test_records_conversation_thread_snapshots_with_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = EpisodeRecorder(
                enabled=True,
                log_path=root / "episodes.jsonl",
                max_turns=12,
            )
            profile = default_mind_profile()

            first = InteractionResponse(
                metadata={
                    "experience_context": {
                        "conversation_id": "conv-1",
                        "user_text": "Hello.",
                        "route": "chat",
                        "intent": "general_conversation",
                        "route_source": "llm",
                        "route_confidence": 0.95,
                        "router_latency_ms": 120.0,
                        "agent_latency_ms": 300.0,
                    }
                },
                speech=[{"text": "Hello!"}],
            )
            first_episode = recorder.record_interaction(
                response=first,
                execution=None,
                session_id="sid-1",
                mind_profile=profile,
            )

            second = InteractionResponse(
                metadata={
                    "experience_context": {
                        "conversation_id": "conv-1",
                        "user_text": "Walk forward for 15 seconds, quickly.",
                        "route": "robot_action",
                        "intent": "capability:soridormi.walk_forward",
                        "route_source": "llm",
                        "route_confidence": 0.95,
                        "router_latency_ms": 456.0,
                        "agent_latency_ms": 987.0,
                    }
                },
                speech=[{"text": "Please confirm a safe bounded walking plan."}],
                skills=[
                    {
                        "request_id": "walk-1",
                        "skill_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 15},
                        "requires_confirmation": True,
                    }
                ],
            )
            execution = SkillRuntimeResult(
                interaction_id=second.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id="walk-1",
                        skill_id="soridormi.walk_velocity",
                        status="completed",
                    )
                ],
            )
            second_episode = recorder.record_interaction(
                response=second,
                execution=execution,
                session_id="sid-2",
                mind_profile=profile,
            )

            self.assertIsNotNone(first_episode)
            self.assertIsNotNone(second_episode)
            self.assertEqual(first_episode.episode_id, second_episode.episode_id)
            self.assertEqual(len(second_episode.turns), 2)
            self.assertEqual(second_episode.turns[0].user_text, "Hello.")
            self.assertEqual(second_episode.turns[1].agent.speech, ["Please confirm a safe bounded walking plan."])
            self.assertEqual(
                second_episode.turns[1].agent.selected_skills[0].skill_id,
                "soridormi.walk_velocity",
            )
            self.assertEqual(
                second_episode.turns[1].execution.skill_results[0].status,
                "completed",
            )

            lines = recorder.log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            last = EpisodeRecord.model_validate(json.loads(lines[-1]))
            self.assertEqual(last.conversation_id, "conv-1")
            self.assertEqual(len(last.turns), 2)

    def test_episode_recorder_bounds_thread_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recorder = EpisodeRecorder(
                enabled=True,
                log_path=Path(tmp) / "episodes.jsonl",
                max_turns=1,
            )
            profile = default_mind_profile()
            for index in range(2):
                response = InteractionResponse(
                    metadata={
                        "experience_context": {
                            "conversation_id": "conv-1",
                            "user_text": f"Turn {index}",
                        }
                    },
                    speech=[{"text": "ok"}],
                )
                episode = recorder.record_interaction(
                    response=response,
                    execution=None,
                    session_id=f"sid-{index}",
                    mind_profile=profile,
                )

            self.assertIsNotNone(episode)
            self.assertEqual(len(episode.turns), 1)
            self.assertEqual(episode.turns[0].user_text, "Turn 1")
            self.assertEqual(episode.turns[0].turn_index, 1)


    def test_episode_snapshot_can_emit_runtime_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = EpisodeRecorder(
                enabled=True,
                log_path=root / "episodes.jsonl",
                emit_runtime_events=True,
                event_root=root / "events",
                trigger_root=root / "inbox",
            )
            response = InteractionResponse(
                metadata={
                    "experience_context": {
                        "conversation_id": "conv-event",
                        "user_text": "Hello.",
                    }
                },
                speech=[{"text": "Hello!"}],
            )
            episode = recorder.record_interaction(
                response=response,
                execution=None,
                session_id="sid-event",
                mind_profile=default_mind_profile(),
            )

            self.assertIsNotNone(episode)
            ready = list((root / "events" / "ready").iterdir())
            self.assertEqual(len(ready), 1)
            manifest = json.loads((ready[0] / "event.json").read_text())
            self.assertEqual(manifest["event_type"], "chromie.experience_episode")
            self.assertEqual(manifest["event_subtype"], "episode_snapshot")
            self.assertEqual(
                manifest["correlations"]["episode_id"], episode.episode_id
            )
            self.assertEqual(
                manifest["correlations"]["conversation_id"], "conv-event"
            )
            self.assertTrue((ready[0] / "episode.json").is_file())
            self.assertTrue((root / "inbox" / f'{manifest["event_id"]}.json').is_file())


if __name__ == "__main__":
    unittest.main()
