from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.interaction_session_evidence import (
    InteractionSessionEvidenceCollector,
    LocalInteractionSessionCapturePolicyProvider,
)
from orchestrator.runtime.session import SessionTracker


class InteractionSessionDataLoopTests(unittest.TestCase):
    def _write_policy(
        self,
        path: Path,
        *,
        version: str,
        enabled: bool,
        audio: bool = True,
        trace: bool = True,
        episode: bool = True,
    ) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "policy_id": "chromie.interaction_session_capture",
                    "policy_version": version,
                    "enabled": enabled,
                    "evidence": {
                        "user_input_audio": audio,
                        "runtime_trace": trace,
                        "episode": episode,
                    },
                    "governance": {
                        "retention_profile_id": "chromie.interaction-quality.v1",
                        "usage_purpose": "interaction_quality_evaluation",
                    },
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _collector(
        self,
        root: Path,
        *,
        policy_path: Path | None,
        event_persister=None,
    ) -> InteractionSessionEvidenceCollector:
        return InteractionSessionEvidenceCollector(
            policy_provider=LocalInteractionSessionCapturePolicyProvider(
                policy_path
            ),
            event_root=root / "events",
            trigger_root=root / "inbox",
            runtime_identity={
                "identity_sha256": "a" * 64,
                "chromie": {"revision": "revision-under-test", "dirty": False},
                "runtime_profile": {
                    "profile_id": "test-profile",
                    "fingerprint": "profile-fingerprint",
                },
            },
            event_persister=event_persister,
        )

    @staticmethod
    def _ready_event(root: Path) -> Path:
        ready = list((root / "events" / "ready").iterdir())
        if len(ready) != 1:
            raise AssertionError(f"expected one ready event, found {ready}")
        return ready[0]

    def test_disabled_policy_leaves_normal_session_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collector = self._collector(root, policy_path=None)
            with patch.dict(
                "os.environ",
                {"CHROMIE_RUNTIME_TRACE_MODE": "off"},
                clear=False,
            ):
                tracker = SessionTracker(
                    enabled=False,
                    interaction_session_capture=collector,
                )
                sid = tracker.create()
            tracker.capture_input_audio(
                sid,
                b"\x01\x00" * 80,
                sample_rate_hz=16000,
                channels=1,
            )
            tracker.state[sid]["llm_done"] = True
            tracker.maybe_done(sid)

            snapshot = tracker.state[sid]["interaction_session_capture_policy"]
            self.assertFalse(snapshot["enabled"])
            self.assertNotIn("interaction_session_capture_event", tracker.state[sid])
            self.assertFalse((root / "events" / "ready").exists())

    def test_enabled_policy_seals_audio_trace_episode_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(policy_path, version="12.0.0", enabled=True)
            collector = self._collector(root, policy_path=policy_path)
            with patch.dict(
                "os.environ",
                {"CHROMIE_RUNTIME_TRACE_MODE": "off"},
                clear=False,
            ):
                tracker = SessionTracker(
                    enabled=False,
                    interaction_session_capture=collector,
                )
                sid = tracker.create()
            tracker.update_trace_correlations(
                sid,
                conversation_id="conversation-1",
                episode_id="episode-1",
            )
            tracker.capture_input_audio(
                sid,
                b"\x02\x00" * 160,
                sample_rate_hz=16000,
                channels=1,
            )
            tracker.attach_episode_evidence(
                sid,
                {
                    "schema_version": 1,
                    "episode_id": "episode-1",
                    "conversation_id": "conversation-1",
                    "turns": [],
                },
            )
            tracker.state[sid]["llm_done"] = True
            tracker.maybe_done(sid)

            event_root = self._ready_event(root)
            event = json.loads((event_root / "event.json").read_text())
            evidence = json.loads(
                (event_root / "interaction-session-evidence.json").read_text()
            )
            self.assertEqual(
                event["event_type"], "chromie.interaction_session_evidence"
            )
            self.assertEqual(event["event_subtype"], "session_complete")
            self.assertEqual(evidence["event_id"], event["event_id"])
            self.assertEqual(evidence["session"]["sid"], sid)
            self.assertEqual(evidence["session"]["termination_state"], "complete")
            self.assertEqual(evidence["policy_snapshot"]["policy_version"], "12.0.0")
            self.assertEqual(evidence["evidence_status"], "complete")
            self.assertEqual(evidence["missing_evidence"], [])
            self.assertEqual(
                evidence["provenance"]["runtime_identity"]["chromie"]["revision"],
                "revision-under-test",
            )
            self.assertEqual(evidence["correlations"]["episode_id"], "episode-1")
            self.assertTrue(evidence["correlations"]["trace_id"])
            artifacts = {item["kind"]: item for item in evidence["artifacts"]}
            self.assertEqual(
                set(artifacts),
                {"user_input_audio", "runtime_trace", "trace_summary", "episode"},
            )
            for artifact in artifacts.values():
                self.assertEqual(len(artifact["sha256"]), 64)
                self.assertTrue((event_root / artifact["path"]).is_file())
            self.assertEqual(
                (event_root / "input-audio.pcm16").read_bytes(),
                b"\x02\x00" * 160,
            )
            self.assertTrue((root / "inbox" / f'{event["event_id"]}.json').is_file())

    def test_abandoned_session_seals_explicit_partial_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(policy_path, version="12.0.0", enabled=True)
            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(
                    root, policy_path=policy_path
                ),
            )
            sid = tracker.create()
            tracker.capture_input_audio(
                sid,
                b"\x03\x00" * 80,
                sample_rate_hz=16000,
                channels=1,
            )
            tracker.state[sid]["last_activity_ms"] = 1000.0

            self.assertEqual(
                tracker.finalize_idle_sessions(
                    idle_timeout_ms=500.0,
                    now_ms_value=1600.0,
                ),
                [sid],
            )

            event_root = self._ready_event(root)
            evidence = json.loads(
                (event_root / "interaction-session-evidence.json").read_text()
            )
            self.assertEqual(evidence["session"]["termination_state"], "abandoned")
            self.assertEqual(evidence["evidence_status"], "partial")
            self.assertIn("episode", evidence["missing_evidence"])
            self.assertNotIn("runtime_trace", evidence["missing_evidence"])

    def test_policy_refresh_applies_only_to_subsequent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(policy_path, version="12.0.0", enabled=True)
            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(
                    root, policy_path=policy_path
                ),
            )
            first = tracker.create()
            self._write_policy(policy_path, version="13.0.0", enabled=False)
            second = tracker.create()

            self.assertEqual(
                tracker.state[first]["interaction_session_capture_policy"][
                    "policy_version"
                ],
                "12.0.0",
            )
            self.assertTrue(
                tracker.state[first]["interaction_session_capture_policy"]["enabled"]
            )
            self.assertEqual(
                tracker.state[second]["interaction_session_capture_policy"][
                    "policy_version"
                ],
                "13.0.0",
            )
            self.assertFalse(
                tracker.state[second]["interaction_session_capture_policy"]["enabled"]
            )
            event_root = self._ready_event(root)
            evidence = json.loads(
                (event_root / "interaction-session-evidence.json").read_text()
            )
            self.assertEqual(evidence["session"]["sid"], first)
            self.assertEqual(evidence["policy_snapshot"]["policy_version"], "12.0.0")

    def test_data_loop_audio_and_debug_audio_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(
                policy_path,
                version="12.0.0",
                enabled=True,
                trace=False,
                episode=False,
            )
            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(
                    root, policy_path=policy_path
                ),
            )
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.sessions = tracker
            assistant.save_audio_enabled = False
            assistant.recordings_dir = str(root / "debug-recordings")
            sid = tracker.create()
            audio = b"\x04\x00" * 80

            assistant.save_audio(audio, "input", session_id=sid)
            tracker.capture_input_audio(
                sid,
                audio,
                sample_rate_hz=16000,
                channels=1,
            )
            tracker.state[sid]["llm_done"] = True
            tracker.maybe_done(sid)

            self.assertFalse((root / "debug-recordings").exists())
            self.assertTrue(
                (self._ready_event(root) / "input-audio.pcm16").is_file()
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(root, policy_path=None),
            )
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.sessions = tracker
            assistant.save_audio_enabled = True
            assistant.recordings_dir = str(root / "debug-recordings")
            Path(assistant.recordings_dir).mkdir(parents=True)
            sid = tracker.create()
            audio = b"\x05\x00" * 80

            assistant.save_audio(audio, "input", session_id=sid)
            tracker.capture_input_audio(
                sid,
                audio,
                sample_rate_hz=16000,
                channels=1,
            )
            tracker.state[sid]["llm_done"] = True
            tracker.maybe_done(sid)

            self.assertEqual(len(list(Path(assistant.recordings_dir).glob("*.raw"))), 1)
            self.assertFalse((root / "events" / "ready").exists())

    def test_recovery_and_retry_have_one_effective_committed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(policy_path, version="12.0.0", enabled=True)
            first_collector = self._collector(root, policy_path=policy_path)
            first_collector.begin_session("sid-crash")
            first_collector.capture_input_audio(
                "sid-crash",
                b"\x06\x00" * 80,
                sample_rate_hz=16000,
                channels=1,
            )

            recovered = self._collector(root, policy_path=policy_path)

            self.assertEqual(len(recovered.recovered_sessions), 1)
            event_root = self._ready_event(root)
            evidence = json.loads(
                (event_root / "interaction-session-evidence.json").read_text()
            )
            self.assertEqual(evidence["session"]["sid"], "sid-crash")
            self.assertEqual(evidence["session"]["termination_state"], "abandoned")
            first_result = recovered.recovered_sessions[0]["event"]
            retry = recovered.seal_session(
                "sid-crash",
                termination_state="abandoned",
            )
            self.assertEqual(retry["event_id"], first_result["event_id"])
            self.assertEqual(len(list((root / "events" / "ready").iterdir())), 1)

    def test_evidence_persistence_failure_never_breaks_session_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(
                policy_path,
                version="12.0.0",
                enabled=True,
                audio=False,
                episode=False,
            )

            def fail_persistence(**_kwargs):
                raise RuntimeError("downstream unavailable")

            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(
                    root,
                    policy_path=policy_path,
                    event_persister=fail_persistence,
                ),
            )
            sid = tracker.create()
            tracker.state[sid]["llm_done"] = True

            tracker.maybe_done(sid)

            self.assertTrue(tracker.state[sid]["done_logged"])
            result = tracker.state[sid]["interaction_session_capture_event"]
            self.assertEqual(result["capture_status"], "failed")
            self.assertIn("downstream unavailable", result["error"])

    def test_downstream_notification_failure_keeps_evidence_inspectable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            self._write_policy(
                policy_path,
                version="12.0.0",
                enabled=True,
                audio=False,
                episode=False,
            )
            (root / "inbox").write_text("not a directory\n", encoding="utf-8")
            tracker = SessionTracker(
                enabled=False,
                interaction_session_capture=self._collector(
                    root,
                    policy_path=policy_path,
                ),
            )
            sid = tracker.create()
            tracker.state[sid]["llm_done"] = True

            tracker.maybe_done(sid)

            self.assertTrue(tracker.state[sid]["done_logged"])
            result = tracker.state[sid]["interaction_session_capture_event"]
            self.assertEqual(result["capture_status"], "complete")
            self.assertEqual(result["trigger_status"], "failed")
            self.assertIn("FileExistsError", result["trigger_error"])
            event_root = self._ready_event(root)
            self.assertTrue((event_root / "event.json").is_file())
            self.assertTrue(
                (event_root / "interaction-session-evidence.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
