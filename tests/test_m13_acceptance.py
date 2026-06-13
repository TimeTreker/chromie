from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.m13_voice_acceptance import (
    AcceptanceAudioDriver,
    CASES,
    FULL_CASE_ORDER,
    analyze_case,
    build_parser,
    capability_probe_invocation,
    endpoint_for_container,
    events_for_sessions,
    extract_asr_text,
    friendly_event_line,
    guide_spoken_step,
    missing_required_terms,
    parse_case_list,
    prompt_verdict,
    redact_env_file,
    wait_for_any_event,
    wait_for_case_checks,
    write_override_file,
)
from orchestrator.audio_injection import encode_audio_packet, read_audio_packet
from scripts.acceptance_audio import AudioFixture
from scripts.verify_m13_evidence import REQUIRED_FILES, verify_bundle
import scripts.prepare_alpha_release as release_module


def event(name: str, message: str, sid: str = "sid-1") -> dict[str, object]:
    return {"event": name, "message": message, "sid": sid}


class M13AcceptanceTests(unittest.TestCase):
    def test_parse_all_cases_preserves_release_order(self) -> None:
        self.assertEqual(parse_case_list("all"), list(FULL_CASE_ORDER))

    def test_synthetic_mode_is_the_default(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.mode, "synthetic")

    def test_audio_injection_packet_round_trip(self) -> None:
        payload = (b"\x01\x00" * 320)
        packet = encode_audio_packet(
            pcm16=payload,
            sample_rate=16000,
            channels=1,
        )
        decoded = read_audio_packet(io.BytesIO(packet))
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.sample_rate, 16000)
        self.assertEqual(decoded.channels, 1)
        self.assertEqual(decoded.pcm16, payload)

    def test_synthetic_audio_driver_writes_framed_pcm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = AudioFixture(
                text="Please nod twice.",
                pcm16=b"\x02\x00" * 160,
                sample_rate=16000,
                channels=1,
                path=Path(temp_dir) / "nod.wav",
            )
            stdin = io.BytesIO()
            process = SimpleNamespace(stdin=stdin)
            driver = AcceptanceAudioDriver(
                mode="synthetic",
                fixtures={fixture.text: fixture},
                orchestrator_process=process,
            )
            driver.deliver(fixture.text)
            stdin.seek(0)
            decoded = read_audio_packet(stdin)
            self.assertEqual(decoded.pcm16, fixture.pcm16)

    def test_acceptance_overrides_select_headless_synthetic_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "override.env"
            write_override_file(
                path,
                event_path=Path(temp_dir) / "events.jsonl",
                recordings_dir=Path(temp_dir) / "recordings",
                soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                enable_soridormi=True,
                mode="synthetic",
            )
            text = path.read_text()
            self.assertIn("ORCH_AUDIO_INPUT_MODE=stdin", text)
            self.assertIn("ORCH_AUDIO_OUTPUT_MODE=discard", text)
            self.assertIn("ORCH_MIN_AUDIO_MS=250", text)

    def test_virtual_mic_overrides_use_pulse_monitor_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "override.env"
            write_override_file(
                path,
                event_path=Path(temp_dir) / "events.jsonl",
                recordings_dir=Path(temp_dir) / "recordings",
                soridormi_mcp_url=None,
                enable_soridormi=False,
                mode="virtual-mic",
                virtual_mic_source="chromie_test.monitor",
            )
            text = path.read_text()
            self.assertIn("PULSE_SOURCE=chromie_test.monitor", text)
            self.assertIn("ORCH_AUDIO_INPUT_MODE=device", text)
            self.assertIn("ORCH_AUDIO_OUTPUT_MODE=discard", text)

    def test_container_endpoint_translates_host_loopback(self) -> None:
        self.assertEqual(
            endpoint_for_container("http://127.0.0.1:8000/mcp"),
            "http://host.docker.internal:8000/mcp",
        )
        self.assertEqual(
            endpoint_for_container("http://localhost:8000/mcp?mode=sim"),
            "http://host.docker.internal:8000/mcp?mode=sim",
        )
        self.assertEqual(
            endpoint_for_container("http://soridormi:8000/mcp"),
            "http://soridormi:8000/mcp",
        )

    def test_container_probe_uses_agent_runtime_and_mounted_manifest(self) -> None:
        command, environment, endpoint = capability_probe_invocation(
            runtime="container",
            endpoint="http://127.0.0.1:8000/mcp",
        )
        self.assertIsNone(environment)
        self.assertEqual(endpoint, "http://host.docker.internal:8000/mcp")
        self.assertIn("chromie-agent", command)
        self.assertIn("SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp", command)
        self.assertEqual(command[-2:], ["--manifest", "/app/capabilities/soridormi.json"])

    def test_host_probe_remains_an_explicit_development_option(self) -> None:
        command, environment, endpoint = capability_probe_invocation(
            runtime="host",
            endpoint="http://127.0.0.1:8000/mcp",
        )
        self.assertEqual(command[0], __import__("sys").executable)
        self.assertEqual(endpoint, "http://127.0.0.1:8000/mcp")
        self.assertEqual(environment["PYTHONPATH"], "agent")
        self.assertEqual(
            environment["SORIDORMI_MCP_URL"],
            "http://127.0.0.1:8000/mcp",
        )

    def test_extract_asr_text_handles_repr_rendering(self) -> None:
        self.assertEqual(
            extract_asr_text(
                event("asr_final", "asr_final: asr_ms=12.0 text_chars=5 text='hello'")
            ),
            "hello",
        )

    def test_wait_for_any_event_only_reads_after_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            path.write_text(
                json.dumps(event("asr_final", "text='old'")) + "\n"
                + json.dumps(event("router_done", "route=chat")) + "\n"
            )
            self.assertIsNone(
                wait_for_any_event(
                    path,
                    marker=1,
                    event_names=("asr_final",),
                    timeout_s=0.01,
                    poll_s=0.001,
                )
            )

    def test_guided_step_reports_detected_transcript(self) -> None:
        case = CASES["speech-only"]
        detected = event(
            "asr_final",
            "asr_final: asr_ms=12.0 text_chars=10 text='hello moon'",
        )
        with mock.patch(
            "scripts.m13_voice_acceptance.wait_for_any_event",
            return_value=detected,
        ), mock.patch("scripts.m13_voice_acceptance.print_countdown"), mock.patch(
            "builtins.print"
        ):
            result = guide_spoken_step(
                case=case,
                step=case.spoken_steps[0],
                step_index=1,
                events_path=Path("unused.jsonl"),
                case_marker=0,
                countdown_s=3,
                asr_timeout_s=20,
                trigger_timeout_s=60,
                asr_retries=0,
                case_session_ids=set(),
            )
        self.assertTrue(result.check.passed)
        self.assertIn("hello moon", result.check.detail)
        self.assertEqual(result.sid, "sid-1")

    def test_missing_required_terms_supports_alternatives(self) -> None:
        self.assertEqual(
            missing_required_terms(
                "Please nod two times",
                (("nod",), ("twice", "two")),
            ),
            [],
        )
        self.assertEqual(
            missing_required_terms(
                "Shh shh shh",
                (("nod",), ("twice", "two")),
            ),
            ["nod", "twice/two"],
        )

    def test_friendly_trace_renders_skill_identity_and_status(self) -> None:
        proposed = friendly_event_line(
            event(
                "skill_proposed",
                "skill_proposed: request_id=req-1 skill_id=soridormi.nod_yes "
                "timing=parallel cancellable=True requires_confirmation=False",
            )
        )
        completed = friendly_event_line(
            event(
                "skill_result",
                "skill_result: request_id=req-1 skill_id=soridormi.nod_yes "
                "status=completed reason=None message=done",
            )
        )
        self.assertIn("soridormi.nod_yes", proposed or "")
        self.assertIn("status=completed", completed or "")

    def test_case_events_are_isolated_by_session(self) -> None:
        records = [
            event("skill_result", "skill_result: status=completed", "old"),
            event("interaction_done", "interaction_done: skills=0", "current"),
        ]
        self.assertEqual(
            events_for_sessions(records, {"current"}),
            [records[1]],
        )

    def test_empty_operator_verdict_defaults_to_pass(self) -> None:
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(prompt_verdict(), "pass")

    def test_speech_only_checks_require_native_zero_skill_completion(self) -> None:
        checks = analyze_case(
            "speech-only",
            [
                event("asr_final", "asr_final: text='hello'"),
                event("router_done", "router_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 skills=0"),
                event("session_done", "session_done: played_tts=1"),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_wait_for_case_checks_returns_when_evidence_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            records = [
                event("asr_final", "asr_final: text='hello'"),
                event("router_done", "router_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 skills=0"),
                event("session_done", "session_done: played_tts=1"),
            ]
            path.write_text("".join(json.dumps(item) + "\n" for item in records))
            events, checks = wait_for_case_checks(
                "speech-only",
                path,
                marker=0,
                timeout_s=0.1,
                poll_s=0.001,
            )
            self.assertEqual(len(events), 4)
            self.assertTrue(all(item.passed for item in checks))

    def test_followup_requires_two_utterances_in_same_conversation(self) -> None:
        checks = analyze_case(
            "follow-up",
            [
                event("asr_final", "asr_final: text='remember blue'", "sid-1"),
                event("router_done", "router_done: route=chat", "sid-1"),
                event("interaction_done", "interaction_done: speech=1 skills=0", "sid-1"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=0", "sid-1"),
                event("asr_final", "asr_final: text='what color'", "sid-2"),
                event("router_done", "router_done: route=chat", "sid-2"),
                event("interaction_done", "interaction_done: speech=1 skills=0", "sid-2"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=2", "sid-2"),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_redaction_removes_secret_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.env"
            target = Path(temp_dir) / "target.env"
            source.write_text("MODEL=test\nAPI_KEY=secret\nAUTHORIZATION_TOKEN=abc\n")
            redact_env_file(source, target)
            text = target.read_text()
            self.assertIn("MODEL=test", text)
            self.assertNotIn("secret", text)
            self.assertNotIn("abc", text)
            self.assertEqual(text.count("<redacted>"), 2)

    def test_complete_evidence_bundle_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            metadata = {
                "status": "passed",
                "event_count": 40,
                "acceptance_id": "test",
                "runner": {"dry_run": False, "mode": "supervised"},
                "chromie": {"revision": "abc123", "version": "0.1.0-alpha.1", "dirty": False},
                "soridormi_manifest": {"upstream_commit": "def456"},
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
            }
            cases = [
                {
                    "case_id": case_id,
                    "operator_verdict": "pass",
                    "event_count": 2,
                    "session_ids": [f"sid-{index}"],
                    "checks": [{"name": "check", "passed": True}],
                }
                for index, case_id in enumerate(FULL_CASE_ORDER)
            ]
            (root / "metadata.json").write_text(json.dumps(metadata))
            (root / "cases.json").write_text(json.dumps(cases))
            (root / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_SKILLS=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=device\n"
                "ORCH_AUDIO_OUTPUT_MODE=device\n"
            )
            report = verify_bundle(root, require_clean=True)
            self.assertTrue(report["passed"], report)


    def test_automated_evidence_verifies_only_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            metadata = {
                "status": "passed",
                "event_count": 40,
                "acceptance_id": "test-auto",
                "runner": {"dry_run": False, "mode": "synthetic"},
                "chromie": {
                    "revision": "abc123",
                    "version": "0.1.0-alpha.1",
                    "dirty": False,
                },
                "soridormi_manifest": {"upstream_commit": "def456"},
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
            }
            cases = [
                {
                    "case_id": case_id,
                    "operator_verdict": "automated",
                    "event_count": 2,
                    "session_ids": [f"sid-{index}"],
                    "checks": [{"name": "check", "passed": True}],
                }
                for index, case_id in enumerate(FULL_CASE_ORDER)
            ]
            (root / "metadata.json").write_text(json.dumps(metadata))
            (root / "cases.json").write_text(json.dumps(cases))
            generated = root / "generated-input"
            generated.mkdir()
            (generated / "manifest.json").write_text("{}\n")
            (generated / "01-test.wav").write_bytes(b"RIFFfixture")
            (root / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_SKILLS=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=stdin\n"
                "ORCH_AUDIO_OUTPUT_MODE=discard\n"
            )
            release_report = verify_bundle(root)
            self.assertFalse(release_report["passed"])
            self.assertTrue(
                any("cannot close M13" in item for item in release_report["errors"])
            )
            automated_report = verify_bundle(root, allow_automated=True)
            self.assertTrue(automated_report["passed"], automated_report)
            self.assertFalse(automated_report["release_eligible"])

    def test_release_preview_creates_non_publishable_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            evidence = temp / "evidence"
            output = temp / "output"
            repo.mkdir()
            evidence.mkdir()

            (repo / "release").mkdir()
            (repo / "VERSION").write_text("0.1.0-alpha.1\n")
            (repo / "release" / "v0.1.0-alpha.1.md").write_text("# Notes\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "chromie": {"version": "0.1.0-alpha.1"},
                        "m13_closure_blockers": ["confirmation pending"],
                    }
                )
            )
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            for name in REQUIRED_FILES:
                (evidence / name).write_text("placeholder\n")
            (evidence / "metadata.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "event_count": 20,
                        "acceptance_id": "fixture",
                        "runner": {"dry_run": False},
                        "chromie": {
                            "revision": subprocess.check_output(
                                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                            ).strip(),
                            "version": "0.1.0-alpha.1",
                            "dirty": False,
                        },
                        "soridormi_manifest": {"upstream_commit": "soridormi-fixture"},
                        "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                    }
                )
            )
            (evidence / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "case_id": case_id,
                            "operator_verdict": "pass",
                            "event_count": 2,
                            "session_ids": [f"sid-{index}"],
                            "checks": [{"name": "check", "passed": True}],
                        }
                        for index, case_id in enumerate(FULL_CASE_ORDER)
                    ]
                )
            )
            (evidence / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_SKILLS=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=device\n"
                "ORCH_AUDIO_OUTPUT_MODE=device\n"
            )

            args = SimpleNamespace(
                evidence_dir=str(evidence),
                output_root=str(output),
                skip_tests=True,
                allow_dirty=False,
                require_clean_evidence=True,
                preview=True,
                overwrite=False,
            )
            with mock.patch.object(release_module, "ROOT", repo):
                bundle = release_module.prepare_release(args)

            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertFalse(manifest["publishable"])
            self.assertTrue((bundle / "chromie-0.1.0-alpha.1.tar.gz").is_file())
            self.assertTrue((bundle / "SHA256SUMS").is_file())

    def test_dry_run_evidence_cannot_close_m13(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "status": "dry-run",
                        "event_count": 0,
                        "runner": {"dry_run": True},
                        "chromie": {"revision": "abc", "dirty": False},
                        "soridormi_manifest": {"upstream_commit": "def"},
                        "soridormi_mcp_url": "http://example/mcp",
                    }
                )
            )
            (root / "cases.json").write_text("[]")
            report = verify_bundle(root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("Dry-run" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
