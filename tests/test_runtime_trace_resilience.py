from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.runtime.session import SessionTracker
from shared.chromie_runtime.resource_sampling import SystemResourceSampler
from shared.chromie_runtime.runtime_trace import (
    RuntimeTrace,
    TraceCheckpointStore,
    TracePolicy,
    TraceSnapshot,
)


class RuntimeTraceResilienceTests(unittest.TestCase):
    def test_latency_threshold_overrides_zero_sampling(self) -> None:
        policy = TracePolicy(
            mode="basic",
            emit_events=True,
            event_sample_rate=0.0,
            event_min_total_ms=1000.0,
            event_min_first_observable_ms=500.0,
        )
        snapshot = TraceSnapshot(
            trace={"trace_id": "trace_threshold", "state": "complete"},
            summary={
                "total_duration_ms": 200.0,
                "first_user_observable_latency_ms": 750.0,
            },
        )

        decision = policy.retention_decision(snapshot)

        self.assertTrue(decision.emit)
        self.assertEqual(decision.reason, "first_user_observable_latency_threshold")
        self.assertEqual(decision.severity, "warning")

    def test_abandoned_trace_is_retained_when_configured(self) -> None:
        policy = TracePolicy(
            mode="basic",
            emit_events=True,
            event_sample_rate=0.0,
            event_always_emit_abandoned=True,
        )
        snapshot = TraceSnapshot(
            trace={"trace_id": "trace_abandoned", "state": "abandoned"},
            summary={"total_duration_ms": 10.0},
        )

        decision = policy.retention_decision(snapshot)

        self.assertTrue(decision.emit)
        self.assertEqual(decision.reason, "abandoned_trace")

    def test_trace_correlations_can_be_enriched_while_active(self) -> None:
        trace = RuntimeTrace(
            policy=TracePolicy(mode="basic"),
            correlations={"session_id": "sid-1"},
        )

        trace.update_correlations(
            {
                "conversation_id": "conversation-1",
                "interaction_id": "interaction-1",
                "empty": "",
            }
        )
        snapshot = trace.finish()

        self.assertEqual(snapshot.trace["correlations"]["session_id"], "sid-1")
        self.assertEqual(
            snapshot.trace["correlations"]["conversation_id"],
            "conversation-1",
        )
        self.assertEqual(
            snapshot.trace["correlations"]["interaction_id"],
            "interaction-1",
        )
        self.assertNotIn("empty", snapshot.trace["correlations"])

    def test_checkpoint_store_round_trips_and_archives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TraceCheckpointStore(Path(directory) / "checkpoints")
            trace = RuntimeTrace(policy=TracePolicy(mode="basic"))
            snapshot = trace.snapshot(state="active")

            path = Path(store.write(snapshot))
            pending = store.pending()

            self.assertTrue(path.is_file())
            self.assertEqual(len(pending), 1)
            self.assertEqual(
                pending[0][1]["trace"]["trace_id"],
                snapshot.trace["trace_id"],
            )
            archived = Path(store.archive(pending[0][0]))
            self.assertTrue(archived.is_file())
            self.assertFalse(path.exists())

    def test_resource_sampler_emits_bounded_process_facts(self) -> None:
        sampler = SystemResourceSampler("periodic")

        first = sampler.sample(reason="session_start")
        second = sampler.sample(
            reason="periodic",
            event_loop_lag_ms=12.5,
            attributes={"playback_queue_depth": 3},
        )

        self.assertEqual(first["sample_reason"], "session_start")
        self.assertIn("process_cpu_time_ms", first)
        self.assertEqual(second["event_loop_lag_ms"], 12.5)
        self.assertEqual(second["playback_queue_depth"], 3)
        self.assertIn("process_cpu_percent_one_core", second)

    def test_session_checkpoint_is_recovered_as_abandoned_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ",
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "1",
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE": "0",
                "CHROMIE_RUNTIME_TRACE_EVENT_ALWAYS_EMIT_ABANDONED": "1",
                "CHROMIE_RUNTIME_TRACE_CHECKPOINT_DIR": str(
                    Path(directory) / "checkpoints"
                ),
                "CHROMIE_RUNTIME_EVENT_ROOT": str(Path(directory) / "events"),
            },
            clear=False,
        ):
            first = SessionTracker(enabled=False)
            sid = first.create()
            first.update_trace_correlations(
                sid,
                conversation_id="conversation-1",
                interaction_id="interaction-1",
            )
            first.checkpoint_active_traces()

            second = SessionTracker(enabled=False)

            self.assertEqual(len(second.recovered_runtime_traces), 1)
            recovered = second.recovered_runtime_traces[0]
            self.assertEqual(recovered["event"]["capture_status"], "complete")
            payload_root = Path(recovered["event"]["payload_root"])
            trace = json.loads(
                (payload_root / "trace.json").read_text(encoding="utf-8")
            )
            self.assertEqual(trace["state"], "abandoned")
            self.assertEqual(
                trace["attributes"]["recovery_reason"],
                "process_restart",
            )
            self.assertEqual(
                trace["correlations"]["conversation_id"],
                "conversation-1",
            )
            self.assertTrue(Path(recovered["archive_path"]).is_file())

    def test_session_resource_samples_and_retention_decision_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ",
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "basic",
                "CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING": "session",
                "CHROMIE_RUNTIME_TRACE_EMIT_EVENTS": "1",
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE": "0",
                "CHROMIE_RUNTIME_TRACE_EVENT_MIN_TOTAL_MS": "999999",
                "CHROMIE_RUNTIME_EVENT_ROOT": str(Path(directory) / "events"),
            },
            clear=False,
        ):
            tracker = SessionTracker(enabled=False)
            sid = tracker.create()
            state = tracker.state[sid]
            state["llm_done"] = True
            tracker.maybe_done(sid)

            snapshot = state["runtime_trace_snapshot"]
            resource_items = [
                item
                for item in snapshot.trace["items"]
                if item["kind"] == "resource_sample"
            ]
            self.assertGreaterEqual(len(resource_items), 2)
            self.assertEqual(
                state["runtime_trace_retention"]["reason"],
                "not_sampled",
            )
            self.assertEqual(state["runtime_trace_event"], {})


if __name__ == "__main__":
    unittest.main()
