from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.runtime.session import (
    SessionTracker,
    now_ms,
    summarize_provider_start_evidence,
)
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    CapabilityTrace,
    CapabilityTraceEvent,
)


class SessionEvidenceTests(unittest.TestCase):
    @staticmethod
    def _started_trace(
        *,
        request_id: str,
        capability_id: str,
        provider_id: str,
    ) -> CapabilityTrace:
        return CapabilityTrace(
            interaction_id="interaction-evidence",
            request_id=request_id,
            capability_id=capability_id,
            provider_id=provider_id,
            events=[CapabilityTraceEvent(type="started")],
        )

    def test_provider_start_evidence_scopes_speech_away_from_requested_work(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-evidence",
            speech=[InteractionSpeech(id="speech-fallback", text="I could not do that.")],
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            traces=[
                self._started_trace(
                    request_id="speech-fallback",
                    capability_id="chromie.speak",
                    provider_id="chromie.local_speech",
                )
            ],
        )

        evidence = summarize_provider_start_evidence(response, execution)

        self.assertEqual(evidence["requested_work_request_count"], 0)
        self.assertEqual(evidence["speech_delivery_request_count"], 1)
        self.assertFalse(evidence["requested_work_provider_start_observed"])
        self.assertTrue(evidence["speech_delivery_provider_start_observed"])
        self.assertTrue(evidence["any_provider_start_observed"])

    def test_provider_start_evidence_tracks_requested_work_and_speech_independently(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-evidence",
            speech=[InteractionSpeech(id="speech-result", text="Here is the result.")],
            capabilities=[
                CapabilityRequest(
                    request_id="weather-request",
                    capability_id="chromie.weather.lookup",
                    args={"location": "Shanghai"},
                )
            ],
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            traces=[
                self._started_trace(
                    request_id="weather-request",
                    capability_id="chromie.weather.lookup",
                    provider_id="weather-provider",
                ),
                self._started_trace(
                    request_id="speech-result",
                    capability_id="chromie.speak",
                    provider_id="chromie.local_speech",
                ),
            ],
        )

        evidence = summarize_provider_start_evidence(response, execution)

        self.assertEqual(evidence["requested_work_request_count"], 1)
        self.assertEqual(evidence["speech_delivery_request_count"], 1)
        self.assertTrue(evidence["requested_work_provider_start_observed"])
        self.assertTrue(evidence["speech_delivery_provider_start_observed"])
        self.assertTrue(evidence["any_provider_start_observed"])

    def test_finished_session_writes_structured_and_human_workflow_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tracker = SessionTracker(
                event_log_path=root / "events.jsonl",
                workflow_report_root=root / "session-workflows",
                workflow_report_include_text=True,
            )
            sid = tracker.create()
            tracker.update_trace_correlations(
                sid,
                conversation_id="conversation-7",
                turn_id="turn-2",
            )
            tracker.log(
                sid,
                "asr_final: asr_ms=%.1f text_chars=%s text=%r",
                18.0,
                11,
                "Please walk",
            )
            started = now_ms()
            tracker.record_cognitive_stage(
                sid,
                stage="asr",
                started_monotonic_ms=started,
                finished_monotonic_ms=started + 18.0,
                status="accepted",
                input_payload={"audio_duration_ms": 900.0},
                output_payload={"user_text": "Please walk"},
            )
            tracker.record_cognitive_stage(
                sid,
                stage="goal_association",
                started_monotonic_ms=started + 19.0,
                finished_monotonic_ms=started + 29.0,
                status="resolved",
                input_payload={"user_text": "Please walk"},
                output_payload={"disposition": "new_goal", "goal_id": "goal-1"},
            )
            tracker.record_cognitive_stage(
                sid,
                stage="canonical_plan_rejection",
                started_monotonic_ms=started + 30.0,
                finished_monotonic_ms=started + 31.0,
                status="rejected",
                input_payload={"canonical_plan": {"plan_id": "plan-1"}},
                output_payload={"validation_errors": ["numeric mismatch"]},
                errors=["numeric mismatch"],
                metadata={"dispatch_allowed": False},
            )
            tracker.record_cognitive_stage(
                sid,
                stage="fallback_speech",
                started_monotonic_ms=started + 32.0,
                finished_monotonic_ms=started + 33.0,
                status="selected",
                input_payload={"failure_stage": "canonical_plan_validation"},
                output_payload={"speech": "I could not safely dispatch that plan."},
            )
            tracker.state[sid]["llm_done"] = True

            tracker.maybe_done(sid)

            json_paths = list(
                (root / "session-workflows").glob(f"*-{sid}.json")
            )
            markdown_paths = list(
                (root / "session-workflows").glob(f"*-{sid}.md")
            )
            self.assertEqual(len(json_paths), 1)
            self.assertEqual(len(markdown_paths), 1)
            report = json.loads(json_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(report["sid"], sid)
            self.assertEqual(report["termination_state"], "complete")
            self.assertEqual(
                report["correlations"]["conversation_id"],
                "conversation-7",
            )
            self.assertEqual(
                [stage["stage"] for stage in report["cognitive_stages"]],
                [
                    "asr",
                    "goal_association",
                    "canonical_plan_rejection",
                    "fallback_speech",
                ],
            )
            self.assertTrue(report["outcome"]["dispatch_blocked_before_requested_provider"])
            self.assertFalse(report["outcome"]["requested_work_provider_start_observed"])
            self.assertEqual(
                report["cognitive_stages"][0]["output"]["user_text"],
                "Please walk",
            )
            markdown = markdown_paths[0].read_text(encoding="utf-8")
            self.assertIn("Goal Association [resolved]", markdown)
            self.assertIn("Canonical Plan Rejection [rejected]", markdown)
            self.assertIn("          ▼", markdown)
            self.assertIn("Please walk", markdown)
            self.assertIn("dispatch_blocked_before_requested_provider", markdown)

    def test_fallback_speech_start_does_not_claim_requested_provider_dispatch(
        self,
    ) -> None:
        tracker = SessionTracker()
        sid = tracker.create()
        started = now_ms()
        tracker.record_cognitive_stage(
            sid,
            stage="canonical_plan_rejection",
            started_monotonic_ms=started,
            finished_monotonic_ms=started + 1.0,
            status="rejected",
            metadata={"dispatch_allowed": False},
        )
        response = InteractionResponse(
            interaction_id="fallback-interaction",
            speech=[InteractionSpeech(id="fallback-speech", text="No verified result yet.")],
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            traces=[
                self._started_trace(
                    request_id="fallback-speech",
                    capability_id="chromie.speak",
                    provider_id="chromie.local_speech",
                )
            ],
        )
        tracker.record_cognitive_stage(
            sid,
            stage="fallback_speech",
            started_monotonic_ms=started + 2.0,
            finished_monotonic_ms=started + 3.0,
            status="selected",
        )
        tracker.record_cognitive_stage(
            sid,
            stage="trusted_capability_runtime",
            started_monotonic_ms=started + 4.0,
            finished_monotonic_ms=started + 5.0,
            status="completed",
            metadata=summarize_provider_start_evidence(response, execution),
        )

        report = tracker._workflow_report(sid, termination_state="complete")
        outcome = report["outcome"]

        self.assertFalse(outcome["requested_work_provider_start_observed"])
        self.assertTrue(outcome["speech_delivery_provider_start_observed"])
        self.assertTrue(outcome["any_provider_start_observed"])
        self.assertTrue(outcome["dispatch_blocked_before_requested_provider"])

    def test_conversation_workflow_rollup_combines_multiple_finished_sids(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_root = Path(temp_dir) / "session-workflows"
            tracker = SessionTracker(
                workflow_report_root=report_root,
                workflow_report_include_text=True,
            )
            for index, user_text in enumerate(("First turn", "Why did it fail?")):
                sid = tracker.create()
                tracker.update_trace_correlations(
                    sid,
                    conversation_id="conversation-shared",
                    turn_id=f"turn-{index + 1}",
                )
                started = now_ms()
                tracker.record_cognitive_stage(
                    sid,
                    stage="goal_association",
                    started_monotonic_ms=started,
                    finished_monotonic_ms=started + 1.0,
                    status="resolved",
                    input_payload={"user_text": user_text},
                    output_payload={"disposition": "continue"},
                )
                tracker.state[sid]["llm_done"] = True
                tracker.maybe_done(sid)

            rollup_path = next(
                report_root.glob("conversation-conversation-shared-*.json")
            )
            markdown_path = next(
                report_root.glob("conversation-conversation-shared-*.md")
            )
            rollup = json.loads(rollup_path.read_text(encoding="utf-8"))
            self.assertEqual(rollup["session_count"], 2)
            self.assertEqual(
                [
                    item["cognitive_stages"][0]["input"]["user_text"]
                    for item in rollup["sessions"]
                ],
                ["First turn", "Why did it fail?"],
            )
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("Turn 1", markdown)
            self.assertIn("Turn 2", markdown)
            self.assertIn("Why did it fail?", markdown)

    def test_workflow_report_redacts_text_from_stages_and_runtime_timeline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tracker = SessionTracker(
                workflow_report_root=root / "session-workflows",
                workflow_report_include_text=False,
            )
            sid = tracker.create()
            tracker.log(
                sid,
                "asr_final: asr_ms=1.0 text_chars=18 text=%r",
                "private family fact",
            )
            started = now_ms()
            tracker.record_cognitive_stage(
                sid,
                stage="planner_communicative_activity_validation",
                started_monotonic_ms=started,
                finished_monotonic_ms=started + 1.0,
                status="accepted",
                input_payload={
                    "user_text": "private family fact",
                    "args": {"recipient": "private person"},
                },
                output_payload={"speech": "private response"},
                errors=[{"error": "private model diagnostic"}],
            )
            tracker.state[sid]["llm_done"] = True

            tracker.maybe_done(sid)

            report_path = next((root / "session-workflows").glob("*.json"))
            markdown_path = next((root / "session-workflows").glob("*.md"))
            report_text = report_path.read_text(encoding="utf-8")
            markdown = markdown_path.read_text(encoding="utf-8")
            for private_text in (
                "private family fact",
                "private person",
                "private response",
                "private model diagnostic",
            ):
                self.assertNotIn(private_text, report_text)
                self.assertNotIn(private_text, markdown)
            report = json.loads(report_text)
            stage = report["cognitive_stages"][0]
            self.assertTrue(stage["input"]["user_text"]["redacted"])
            self.assertTrue(stage["input"]["args"]["recipient"]["redacted"])
            self.assertTrue(report["runtime_timeline"][1]["message"]["redacted"])

    def test_interrupted_session_writes_one_abandoned_workflow_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_root = Path(temp_dir) / "session-workflows"
            tracker = SessionTracker(workflow_report_root=report_root)
            first_sid = tracker.create()
            tracker.record_cognitive_stage(
                first_sid,
                stage="goal_association",
                started_monotonic_ms=now_ms(),
                finished_monotonic_ms=now_ms(),
                status="cancelled",
                errors=[{"reason": "newer_session"}],
            )

            tracker.create()
            tracker.finalize_active_sessions(reason="test_shutdown")

            matching = list(report_root.glob(f"*-{first_sid}.json"))
            self.assertEqual(len(matching), 1)
            report = json.loads(matching[0].read_text(encoding="utf-8"))
            self.assertEqual(report["termination_state"], "abandoned")
            self.assertEqual(
                report["cognitive_stages"][0]["status"],
                "cancelled",
            )

    def test_session_tracker_writes_correlated_jsonl_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            sid = tracker.create()
            tracker.log(sid, "goal_interpretation_done: route=%s confidence=%.2f", "chat", 0.91)

            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(records[0]["event"], "session_start")
            self.assertEqual(records[0]["sid"], sid)
            self.assertEqual(records[1]["event"], "goal_interpretation_done")
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
                "goal_interpretation_done: interpretation_ms=%.1f route=%s agents=%s intent=%s confidence=%.2f interrupt=%s needs_agent=%s",
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
                "interaction_done: agent_ms=%.1f speech=%s capabilities=%s requires_confirmation=%s",
                1000.0,
                1,
                0,
                False,
            )
            tracker.log(
                sid,
                "capability_runtime_done: status=%s results=%s traces=%s runtime_ms=%.1f",
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
            self.assertIn("goal_interpretation_done:", message)
            self.assertIn("agent_start:", message)
            self.assertIn("interaction_done:", message)
            self.assertIn("capability_runtime_done:", message)
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
                any(node["event"] == "goal_interpretation_done" for node in graph["nodes"])
            )
            node_records = [record for record in records if record["event"] == "session_workflow_node"]
            self.assertEqual(node_records, [])
            summary = [record for record in records if record["event"] == "session_workflow_summary"]
            self.assertEqual(len(summary), 1)
            self.assertIn("slowest=", summary[0]["message"])

    def test_session_completion_logs_one_operator_readable_flow_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            sid = tracker.create()
            tracker.log(
                sid,
                "vad_valid_end: audio=%.2fs rms=%.1f bytes=%s",
                2.5,
                500.0,
                80000,
            )
            started = now_ms()
            tracker.record_cognitive_stage(
                sid,
                stage="asr",
                started_monotonic_ms=started,
                finished_monotonic_ms=started + 120.0,
                status="accepted",
            )
            tracker.record_cognitive_stage(
                sid,
                stage="goal_interpretation",
                started_monotonic_ms=started + 121.0,
                finished_monotonic_ms=started + 421.0,
                status="accepted",
            )
            tracker.record_cognitive_stage(
                sid,
                stage="fast_planner",
                started_monotonic_ms=started + 422.0,
                finished_monotonic_ms=started + 1922.0,
                status="escalate",
            )
            tracker.record_cognitive_stage(
                sid,
                stage="deep_planner",
                started_monotonic_ms=started + 1923.0,
                finished_monotonic_ms=started + 2523.0,
                status="complete",
            )
            tracker.state[sid]["llm_done"] = True
            tracker.state[sid]["scheduled_tts"] = 1
            tracker.state[sid]["queued_tts"] = 1
            tracker.state[sid]["played_tts"] = 1

            tracker.maybe_done(sid)

            records = [json.loads(line) for line in path.read_text().splitlines()]
            flow = [record for record in records if record["event"] == "session_flow"]
            self.assertEqual(len(flow), 1)
            message = flow[0]["message"]
            self.assertNotIn("\n", message)
            self.assertIn("vad[accepted]", message)
            self.assertIn("asr[accepted,120.0ms]", message)
            self.assertIn("goal_interpretation[accepted,300.0ms]", message)
            self.assertIn("fast_planner[escalate,1.50s]", message)
            self.assertIn("deep_planner[complete,600.0ms]", message)
            self.assertIn("tts_playback[played=1/1,failed=0,skipped=0]", message)
            self.assertIn("state=complete", message)
            self.assertIn("slowest=fast_planner:1.50s", message)

    def test_interrupted_session_logs_flow_once_before_abandonment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            first = tracker.create()
            started = now_ms()
            tracker.record_cognitive_stage(
                first,
                stage="goal_interpretation",
                started_monotonic_ms=started,
                finished_monotonic_ms=started + 10.0,
                status="accepted",
            )

            tracker.create()

            records = [json.loads(line) for line in path.read_text().splitlines()]
            flow = [
                record
                for record in records
                if record["event"] == "session_flow" and record["sid"] == first
            ]
            self.assertEqual(len(flow), 1)
            self.assertIn("state=abandoned", flow[0]["message"])
            self.assertIn("goal_interpretation[accepted,10.0ms]", flow[0]["message"])

    def test_evidence_write_failure_does_not_break_session_logging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir) / "not-a-file"
            directory.mkdir()
            tracker = SessionTracker(event_log_path=directory)
            with self.assertLogs("orchestrator.runtime.session", level="WARNING"):
                sid = tracker.create()
                tracker.log(sid, "safe_event")
            self.assertIn(sid, tracker.state)

    def test_bad_session_nodes_are_logged_above_info_and_recorded_with_severity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            tracker = SessionTracker(event_log_path=path)
            sid = tracker.create()

            with self.assertLogs("orchestrator.runtime.session", level="WARNING") as warning_logs:
                tracker.log(
                    sid,
                    "goal_interpretation_done: route=%s agents=%s intent=%s confidence=%.2f",
                    "robot_action",
                    "capability_agent,speaker_agent",
                    "capability:chromie.speak",
                    1.0,
                )
            self.assertTrue(any("WARNING" in line for line in warning_logs.output))

            with self.assertLogs("orchestrator.runtime.session", level="ERROR") as error_logs:
                tracker.log(
                    sid,
                    "capability_result: request_id=%s capability_id=%s status=%s reason=%s message=%s",
                    "move-1",
                    "soridormi.walk_forward",
                    "failed",
                    "provider_error",
                    "provider disconnected",
                )
            self.assertTrue(any("ERROR" in line for line in error_logs.output))

            records = [json.loads(line) for line in path.read_text().splitlines()]
            interpretation_records = [record for record in records if record["event"] == "goal_interpretation_done"]
            skill_records = [record for record in records if record["event"] == "capability_result"]
            self.assertEqual(interpretation_records[-1]["severity"], "warning")
            self.assertEqual(skill_records[-1]["severity"], "error")

    def test_tts_text_does_not_determine_log_severity_or_color(self) -> None:
        tracker = SessionTracker(event_log_path=None)
        sid = tracker.create()
        with patch.dict(os.environ, {"ORCH_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("orchestrator.runtime.session", level="INFO") as info_logs:
                tracker.log(
                    sid,
                    "tts_schedule: order=%s chars=%s scheduled_tts=%s generation=%s text=%r",
                    0,
                    29,
                    1,
                    12,
                    "I cannot perform that action.",
                )
        self.assertTrue(any("I cannot perform that action." in line for line in info_logs.output))
        self.assertTrue(all("\033[33m" not in line for line in info_logs.output))


    def test_llm_truncation_events_are_colored_red_in_cli(self) -> None:
        tracker = SessionTracker(event_log_path=None)
        sid = tracker.create()
        with patch.dict(os.environ, {"ORCH_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("orchestrator.runtime.session", level="ERROR") as error_logs:
                tracker.log(
                    sid,
                    "llm_output_truncated: reason=%s done_reason=%s eval_count=%s num_predict=%s",
                    "done_reason_length",
                    "length",
                    64,
                    64,
                )
        self.assertTrue(any("\033[31m" in line for line in error_logs.output))

    def test_llm_budget_pressure_events_are_colored_yellow_in_cli(self) -> None:
        tracker = SessionTracker(event_log_path=None)
        sid = tracker.create()
        with patch.dict(os.environ, {"ORCH_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("orchestrator.runtime.session", level="WARNING") as warning_logs:
                tracker.log(
                    sid,
                    "llm_prompt_context_pressure: reason=%s prompt_eval_count=%s num_ctx=%s usage=%s",
                    "prompt_eval_count_near_num_ctx",
                    1900,
                    2048,
                    "0.93",
                )
        self.assertTrue(any("\033[33m" in line for line in warning_logs.output))

    def test_failed_nodes_can_be_colored_red_in_cli(self) -> None:
        tracker = SessionTracker(event_log_path=None)
        sid = tracker.create()
        with patch.dict(os.environ, {"ORCH_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("orchestrator.runtime.session", level="ERROR") as error_logs:
                tracker.log(
                    sid,
                    "capability_runtime_done: status=%s results=%s traces=%s runtime_ms=%.1f",
                    "failed",
                    0,
                    1,
                    10.0,
                )
        self.assertTrue(any("\033[31m" in line for line in error_logs.output))


if __name__ == "__main__":
    unittest.main()
