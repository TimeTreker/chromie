from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.episode import EpisodeRecorder, EpisodeRecord
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.interaction import InteractionResponse, CapabilityResult
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
                        "core_interpretation_latency_ms": 120.0,
                        "agent_latency_ms": 300.0,
                        "interaction_session_evidence": {
                            "source_sid": "sid-1",
                            "evidence_event_id": "evt-session-1",
                            "policy_id": "chromie.interaction_session_capture",
                            "policy_version": "12.0.0",
                        },
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
                        "core_interpretation_latency_ms": 456.0,
                        "agent_latency_ms": 987.0,
                    }
                },
                speech=[{"text": "Please confirm a safe bounded walking plan."}],
                capabilities=[
                    {
                        "request_id": "walk-1",
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 15},
                        "requires_confirmation": True,
                    }
                ],
            )
            execution = CapabilityRuntimeResult(
                interaction_id=second.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="walk-1",
                        capability_id="soridormi.walk_velocity",
                        status="completed",
                        provider_id="soridormi.mcp",
                        output={
                            "mode": "sim",
                            "no_motion": False,
                            "recommendation_only": False,
                        },
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
            self.assertEqual(
                second_episode.metadata["interaction_session_evidence"][
                    "evidence_event_id"
                ],
                "evt-session-1",
            )
            self.assertEqual(
                second_episode.turns[0].metadata[
                    "interaction_session_evidence"
                ]["source_sid"],
                "sid-1",
            )
            self.assertEqual(second_episode.turns[0].user_text, "Hello.")
            self.assertEqual(second_episode.turns[1].agent.speech, ["Please confirm a safe bounded walking plan."])
            self.assertEqual(
                second_episode.turns[1].agent.selected_capabilities[0].capability_id,
                "soridormi.walk_velocity",
            )
            self.assertEqual(
                second_episode.turns[1].execution.capability_results[0].status,
                "completed",
            )
            recorded_result = second_episode.turns[1].execution.capability_results[0]
            self.assertEqual(recorded_result.provider_id, "soridormi.mcp")
            self.assertEqual(recorded_result.execution_mode, "sim")
            self.assertFalse(recorded_result.no_motion)
            self.assertFalse(recorded_result.recommendation_only)

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


    def test_semantic_failure_keeps_fallback_transport_success_but_marks_turn_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recorder = EpisodeRecorder(
                enabled=True,
                log_path=Path(tmp) / "episodes.jsonl",
            )
            response = InteractionResponse(
                metadata={
                    "semantic_status": "failed",
                    "experience_context": {
                        "conversation_id": "conv-fallback",
                        "user_text": "你好。",
                    },
                },
                speech=[{"text": "咦？我刚刚没弄明白。你再跟我说一遍嘛。"}],
            )
            execution = CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="fallback-speech",
                        capability_id="chromie.speak",
                        status="completed",
                    )
                ],
            )

            episode = recorder.record_interaction(
                response=response,
                execution=execution,
                session_id="sid-fallback",
                mind_profile=default_mind_profile(),
                errors=["goal_association:structured_output_validation"],
            )

            self.assertIsNotNone(episode)
            assert episode is not None
            turn = episode.turns[-1]
            self.assertEqual(turn.execution.status, "error")
            self.assertEqual(turn.execution.capability_results[0].status, "completed")

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
