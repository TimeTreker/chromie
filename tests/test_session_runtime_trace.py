from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.runtime.session import SessionTracker


class SessionRuntimeTraceTests(unittest.TestCase):
    def test_session_trace_records_lifecycle_and_user_observable_milestone(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "0",
            },
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            sid = tracker.create()
            tracker.trace_mark(
                sid,
                "first_audio_playback",
                kind="user_observable",
                attributes={"order": 0},
            )
            state = tracker.state[sid]
            state.update(
                {
                    "llm_done": True,
                    "scheduled_tts": 1,
                    "queued_tts": 1,
                    "played_tts": 1,
                    "response_chars": 12,
                }
            )
            tracker.maybe_done(sid)

            snapshot = state["runtime_trace_snapshot"]
            self.assertEqual(snapshot.trace["state"], "complete")
            names = [item["name"] for item in snapshot.trace["items"]]
            self.assertIn("session_started", names)
            self.assertIn("first_audio_playback", names)
            self.assertIn("session_finished", names)
            self.assertIsNotNone(
                snapshot.summary["first_user_observable_latency_ms"]
            )

    def test_new_session_abandons_previous_session_trace(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            first = tracker.create()
            second = tracker.create()

            self.assertNotEqual(first, second)
            snapshot = tracker.state[first]["runtime_trace_snapshot"]
            self.assertEqual(snapshot.trace["state"], "abandoned")

    def test_idle_timeout_abandons_unfinished_session_trace(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            sid = tracker.create()
            state = tracker.state[sid]
            state["last_activity_ms"] = 1000.0

            finalized = tracker.finalize_idle_sessions(
                idle_timeout_ms=500.0,
                now_ms_value=1600.0,
            )

            self.assertEqual(finalized, [sid])
            self.assertTrue(state["interrupted"])
            self.assertEqual(
                state["runtime_trace_snapshot"].trace["state"],
                "abandoned",
            )

    def test_session_trace_event_is_packaged_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ",
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "1",
                "CHROMIE_RUNTIME_EVENT_ROOT": str(Path(directory) / "events"),
            },
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            sid = tracker.create()
            state = tracker.state[sid]
            state["llm_done"] = True
            tracker.maybe_done(sid)

            event = state["runtime_trace_event"]
            self.assertEqual(event["capture_status"], "complete")
            payload_root = Path(event["payload_root"])
            self.assertTrue((payload_root / "trace.json").is_file())
            self.assertTrue((payload_root / "trace-summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
