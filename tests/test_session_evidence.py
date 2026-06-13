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
