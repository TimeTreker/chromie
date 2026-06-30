from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.session import SessionTracker


class SessionEvidenceTests(unittest.TestCase):
    def test_session_tracker_writes_correlated_jsonl_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            sid = tracker.create()
            tracker.log(sid, "router_done: route=%s confidence=%.2f", "chat", 0.91)

            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(records[0]["event"], "session_start")
            self.assertEqual(records[0]["sid"], sid)
            self.assertEqual(records[1]["event"], "router_done")
            self.assertIn("route=chat", records[1]["message"])
            self.assertGreaterEqual(records[1]["elapsed_ms"], 0.0)

    def test_session_done_reports_compact_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            sid = tracker.create()
            tracker.log(sid, "asr_final: asr_ms=%.1f text_chars=%s text=%r", 12.0, 12, "Please walk.")
            tracker.log(
                sid,
                "router_done: router_ms=%.1f route=%s agents=%s intent=%s confidence=%.2f interrupt=%s needs_agent=%s",
                50.0,
                "robot_action",
                "capability_agent,speaker_agent",
                "robot_action",
                0.72,
                False,
                True,
            )
            tracker.log(sid, "agent_start: route=%s agents=%s intent=%s", "robot_action", "capability_agent,speaker_agent", "robot_action")
            tracker.log(
                sid,
                "interaction_done: agent_ms=%.1f speech=%s skills=%s requires_confirmation=%s",
                1000.0,
                1,
                0,
                False,
            )
            tracker.log(
                sid,
                "skill_runtime_done: status=%s results=%s traces=%s runtime_ms=%.1f",
                "completed",
                1,
                1,
                2.0,
            )
            tracker.log(sid, "tts_schedule: order=%s chars=%s scheduled_tts=%s generation=%s text=%r", 0, 9, 1, 1, "Try again.")
            tracker.log(sid, "playback_end: order=%s playback_ms=%.1f played_tts=%s", 0, 900.0, 1)
            tracker.state[sid]["llm_done"] = True
            tracker.state[sid]["scheduled_tts"] = 1
            tracker.state[sid]["queued_tts"] = 1
            tracker.state[sid]["played_tts"] = 1
            tracker.state[sid]["response_chars"] = 9

            tracker.maybe_done(sid)

            records = [json.loads(line) for line in path.read_text().splitlines()]
            workflow = [record for record in records if record["event"] == "session_workflow"]
            self.assertEqual(len(workflow), 1)
            message = workflow[0]["message"]
            self.assertIn("asr_final:", message)
            self.assertIn("router_done:", message)
            self.assertIn("agent_start:", message)
            self.assertIn("interaction_done:", message)
            self.assertIn("skill_runtime_done:", message)
            self.assertIn("tts_schedule:", message)
            self.assertIn("playback_end:", message)
            self.assertIn("session_done:", message)
            graph_records = [record for record in records if record["event"] == "session_workflow_graph"]
            self.assertEqual(len(graph_records), 1)
            graph = graph_records[0]["graph"]
            self.assertEqual(graph["schema_version"], 1)
            self.assertEqual(graph["sid"], sid)
            self.assertGreaterEqual(graph["total_ms"], 0.0)
            self.assertGreaterEqual(len(graph["nodes"]), 8)
            self.assertEqual(len(graph["edges"]), len(graph["nodes"]) - 1)
            self.assertEqual(graph["nodes"][0]["event"], "session_start")
            self.assertIn("delta_from_previous_ms", graph["nodes"][1])
            self.assertTrue(
                any(node["event"] == "router_done" for node in graph["nodes"])
            )
            node_records = [record for record in records if record["event"] == "session_workflow_node"]
            self.assertEqual(node_records, [])
            summary = [record for record in records if record["event"] == "session_workflow_summary"]
            self.assertEqual(len(summary), 1)
            self.assertIn("slowest=", summary[0]["message"])

    def test_evidence_write_failure_does_not_break_session_logging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir) / "not-a-file"
            directory.mkdir()
            tracker = SessionTracker(event_log_path=directory)
            with self.assertLogs("orchestrator.runtime.session", level="WARNING"):
                sid = tracker.create()
                tracker.log(sid, "safe_event")
            self.assertIn(sid, tracker.state)


if __name__ == "__main__":
    unittest.main()
