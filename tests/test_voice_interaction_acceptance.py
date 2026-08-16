from __future__ import annotations

import io
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.voice_acceptance import (
    AcceptanceAudioDriver,
    CASES,
    CheckResult,
    FULL_CASE_ORDER,
    acceptance_runtime_environment,
    acceptance_readiness,
    analyze_case,
    build_parser,
    capability_probe_invocation,
    endpoint_for_container,
    ensure_acceptance_runtime,
    events_for_sessions,
    extract_asr_text,
    friendly_event_line,
    guide_spoken_step,
    is_confirmation_prompt_text,
    missing_required_terms,
    parse_case_list,
    prompt_verdict,
    redact_env_file,
    run_acceptance,
    service_runtime_overrides,
    tts_health_ready,
    warm_supervised_tts_delivery,
    wait_for_any_event,
    wait_for_case_checks,
    wait_for_confirmation_prompt_completion,
    write_service_override_file,
    write_override_file,
    write_bundle_manifest,
)
from scripts.check_python_runtime import runtime_is_supported
from orchestrator.runtime.evidence_identity import canonical_json_sha256
from orchestrator.audio_injection import encode_audio_packet, read_audio_packet
from scripts.acceptance_audio import AudioFixture, HostSpeakerPlayer, PulseVirtualMicrophone
from scripts.verify_voice_evidence import (
    CURRENT_REVISION_LIVE_VOICE_PROFILE,
    FULL_VOICE_MUJOCO_PROFILE,
    LIVE_VOICE_REQUIRED_FILES,
    REQUIRED_FILES,
    build_parser as build_verifier_parser,
    verify_bundle,
)
import scripts.prepare_release as release_module


def event(name: str, message: str, sid: str = "sid-1") -> dict[str, object]:
    return {"event": name, "message": message, "sid": sid}


def tts_completion_events(
    sid: str,
    text: str,
    *,
    order: int = 0,
    scheduled: int = 1,
) -> list[dict[str, object]]:
    return [
        event(
            "tts_schedule",
            f"tts_schedule: order={order} chars={len(text)} "
            f"scheduled_tts={scheduled} generation=1 text={text!r}",
            sid,
        ),
        event(
            "playback_start",
            f"playback_start: order={order} source_rate=44100 "
            "output_rate=44100 audio_ms=100.0 generation=1",
            sid,
        ),
        event(
            "playback_end",
            f"playback_end: order={order} playback_ms=100.0 "
            f"played_tts={scheduled}",
            sid,
        ),
        event(
            "session_done",
            f"session_done: scheduled_tts={scheduled} queued_tts={scheduled} "
            f"played_tts={scheduled} failed_tts=0 skipped_tts=0 "
            "response_chars=20 total_ms=200.0",
            sid,
        ),
    ]


def confirmation_prompt_playback_events(
    sid: str,
    *,
    order: int = 0,
) -> list[dict[str, object]]:
    prompt = "Please confirm: should I nod twice? Please answer yes or no."
    return [
        event(
            "tts_schedule",
            f"tts_schedule: order={order} chars={len(prompt)} "
            f"scheduled_tts=1 generation=1 text={prompt!r}",
            sid,
        ),
        event(
            "playback_start",
            f"playback_start: order={order} source_rate=44100 "
            "output_rate=44100 audio_ms=500.0 generation=1",
            sid,
        ),
        event(
            "playback_end",
            f"playback_end: order={order} playback_ms=500.0 played_tts=1",
            sid,
        ),
    ]


class NaturalConfirmationPromptDetectionTests(unittest.TestCase):
    def test_childlike_confirmation_wording_is_detected(self) -> None:
        self.assertTrue(
            is_confirmation_prompt_text(
                "我可以先往前走十五秒，再眨四下眼睛。这样可以吗？"
            )
        )
        self.assertTrue(
            is_confirmation_prompt_text(
                "I can walk first and blink next. Is that okay?"
            )
        )


def speech_capability_runtime_events(
    *,
    include_confirmation_prompt: bool = True,
) -> list[dict[str, object]]:
    records = [
        event("asr_final", "asr_final: text='Please nod twice.'", "sid-1"),
        event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "sid-1"),
        event(
            "interaction_done",
            "interaction_done: speech=1 capabilities=1 requires_confirmation=True",
            "sid-1",
        ),
        event(
            "capability_proposed",
            'capability_proposed: request_id=nod-1 capability_id=soridormi.nod_yes '
            'timing=parallel cancellable=True requires_confirmation=True args={"count":2}',
            "sid-1",
        ),
        event(
            "confirmation_requested",
            "confirmation_requested: confirmation_id=confirm-1 "
            "interaction_id=interaction-1 request_ids=nod-1 "
            "fingerprint=abc expires_at=1.0",
            "sid-1",
        ),
    ]
    if include_confirmation_prompt:
        records.extend(confirmation_prompt_playback_events("sid-1"))
    records.extend(
        [
            event(
                "confirmation_reply",
                "confirmation_reply: confirmation_id=confirm-1 "
                "decision=approved fingerprint=abc",
                "sid-2",
            ),
            event(
                "confirmation_authorized",
                "confirmation_authorized: confirmation_id=confirm-1 "
                "interaction_id=interaction-1 request_ids=nod-1 fingerprint=abc",
                "sid-2",
            ),
            event(
                "capability_result",
                "capability_result: request_id=nod-1 capability_id=soridormi.nod_yes "
                "status=completed",
                "sid-2",
            ),
            event(
                "soridormi_post_status",
                "soridormi_post_status: mode=sim backend=runtime safe_idle=True "
                "active_task_present=False emergency_stop=False fallen=False",
                "sid-2",
            ),
        ]
    )
    return records


def fixture_case_session_ids(index: int, case_id: str) -> list[str]:
    session_ids = [f"sid-{index}"]
    if case_id in {"barge-in", "body-cancel", "stop", "follow-up"}:
        session_ids.append(f"sid-{index}-follow")
    return session_ids


GOAL_DRIVEN_OVERRIDE_TEXT = (
    "ORCH_COGNITIVE_RUNTIME_MODE=apply\n"
    "ORCH_COGNITIVE_APPLY_LANES=chat,memory,robot_action,tool\n"
    "ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed\n"
    "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0\n"
    "ORCH_COGNITIVE_EVIDENCE_ENABLED=1\n"
)


def write_cognitive_runtime_fixture(root: Path) -> None:
    events = [
        {"sid": "sid-0", "mode": "apply", "status": "applied", "lane": "chat"},
        {"sid": "sid-1", "mode": "apply", "status": "applied", "lane": "robot_action"},
        {"sid": "sid-2", "mode": "apply", "status": "applied", "lane": "robot_action"},
        {"sid": "sid-3", "mode": "apply", "status": "applied", "lane": "chat"},
        {"sid": "sid-4", "mode": "apply", "status": "applied", "lane": "robot_action"},
        {"sid": "sid-5", "mode": "apply", "status": "applied", "lane": "chat"},
        {"sid": "sid-6", "mode": "apply", "status": "applied", "lane": "chat"},
        {"sid": "sid-6-follow", "mode": "apply", "status": "applied", "lane": "chat"},
    ]
    (root / "cognitive-runtime.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in events),
        encoding="utf-8",
    )
    status_message = (
        "soridormi_post_status: mode=sim backend=runtime safe_idle=True "
        "active_task_present=False emergency_stop=False fallen=False"
    )
    runtime_events = [
        event("asr_final", "asr_final: text='Moon fact'", "sid-0"),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-0"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False", "sid-0"),
        *tts_completion_events("sid-0", "The Moon has lower gravity than Earth."),
        event("asr_final", "asr_final: text='nod twice'", "sid-1"),
        event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "sid-1"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=1 requires_confirmation=True", "sid-1"),
        event("cognitive_capability_proposed", 'cognitive_capability_proposed: request_id=nod-2 capability_id=soridormi.nod_yes timing=parallel requires_confirmation=True args={"count":2}', "sid-1"),
        event("confirmation_requested", "confirmation_requested: confirmation_id=c1 interaction_id=i1 request_ids=nod-2 fingerprint=fp1 expires_at=1.0", "sid-1"),
        *confirmation_prompt_playback_events("sid-1"),
        event("confirmation_reply", "confirmation_reply: confirmation_id=c1 decision=approved fingerprint=fp1", "sid-1"),
        event("confirmation_authorized", "confirmation_authorized: confirmation_id=c1 interaction_id=i1 request_ids=nod-2 fingerprint=fp1", "sid-1"),
        event("capability_runtime_done", "capability_runtime_done: status=completed results=1 traces=1 provider_mode=sim runtime_ms=10.0", "sid-1"),
        event("capability_result", "capability_result: request_id=nod-2 capability_id=soridormi.nod_yes status=completed", "sid-1"),
        event("soridormi_post_status", status_message, "sid-1"),
        event("asr_final", "asr_final: text='nod twice'", "sid-2"),
        event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "sid-2"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=1 requires_confirmation=True", "sid-2"),
        event("cognitive_capability_proposed", 'cognitive_capability_proposed: request_id=nod-denied capability_id=soridormi.nod_yes timing=parallel requires_confirmation=True args={"count":2}', "sid-2"),
        event("confirmation_requested", "confirmation_requested: confirmation_id=c2 interaction_id=i2 request_ids=nod-denied fingerprint=fp2 expires_at=1.0", "sid-2"),
        event("confirmation_reply", "confirmation_reply: confirmation_id=c2 decision=denied fingerprint=fp2", "sid-2"),
        event("confirmation_rejected", "confirmation_rejected: confirmation_id=c2 reason=denied fingerprint=fp2", "sid-2"),
        *tts_completion_events("sid-2", "Okay, I will not perform that action."),
        event("asr_final", "asr_final: text='tell me a long story'", "sid-3"),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-3"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False", "sid-3"),
        event("tts_schedule", "tts_schedule: order=0 chars=20 scheduled_tts=1 generation=1 text='A long Moon story begins.'", "sid-3"),
        event("playback_start", "playback_start: order=0 source_rate=44100 output_rate=44100 audio_ms=30000.0 generation=1", "sid-3"),
        event("playback_duck_started", "playback_duck_started: generation=1 vad_start_to_duck_ms=40.0 cancel_cognitive_work=false pause_error=none", "sid-3"),
        event("session_interrupted_by_new_session", "session_interrupted_by_new_session: new_sid=sid-3-follow", "sid-3"),
        event("asr_final", "asr_final: text='stop talking'", "sid-3-follow"),
        event("barge_in_external_speech_confirmed", "barge_in_external_speech_confirmed: scope=output_only cancel_cognitive_work=false playback_generation_at_start=1 confirmed_speech_to_silence_ms=20.0", "sid-3-follow"),
        event("cognitive_gateway_cancellation_dispatched", "cognitive_gateway_cancellation_dispatched: requested_scope=output_only effective_scope=output_only interactions=none selected=0 active=0 queued=0 non_interruptible=0 provider_failures=0 dispatch_failures=0", "sid-3-follow"),
        event("cognitive_gateway_reflex_applied", "cognitive_gateway_reflex_applied: action=interrupt trigger=stop_output_command goal_interpretation_bypassed=True", "sid-3-follow"),
        event("playback_aborted_by_interrupt", "playback_aborted_by_interrupt: order=0 playback_ms=100.0 generation=1", "sid-3"),
        event("asr_final", "asr_final: text='nod eight times'", "sid-4"),
        event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "sid-4"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=1 requires_confirmation=True", "sid-4"),
        event("cognitive_capability_proposed", 'cognitive_capability_proposed: request_id=nod-8 capability_id=soridormi.nod_yes timing=parallel requires_confirmation=True args={"count":8}', "sid-4"),
        event("confirmation_requested", "confirmation_requested: confirmation_id=c4 interaction_id=i4 request_ids=nod-8 fingerprint=fp4 expires_at=1.0", "sid-4"),
        event("confirmation_reply", "confirmation_reply: confirmation_id=c4 decision=approved fingerprint=fp4", "sid-4"),
        event("confirmation_authorized", "confirmation_authorized: confirmation_id=c4 interaction_id=i4 request_ids=nod-8 fingerprint=fp4", "sid-4"),
        event("asr_final", "asr_final: text='stop talking'", "sid-4-follow"),
        event("goal_interpretation_done", "goal_interpretation_done: route=interrupt", "sid-4-follow"),
        event("capability_runtime_cancelled", "capability_runtime_cancelled: runtime_ms=10.0", "sid-4"),
        event("soridormi_post_status", status_message, "sid-4"),
        event("interrupt_previous_audio_done", "interrupt_previous_audio_done: playback_generation=3", "sid-4-follow"),
        event("asr_final", "asr_final: text='tell me a long space story'", "sid-5"),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-5"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False", "sid-5"),
        event("tts_schedule", "tts_schedule: order=0 chars=20 scheduled_tts=1 generation=3 text='A long space story begins.'", "sid-5"),
        event("playback_start", "playback_start: order=0 source_rate=44100 output_rate=44100 audio_ms=30000.0 generation=3", "sid-5"),
        event("session_interrupted_by_new_session", "session_interrupted_by_new_session: new_sid=sid-5-follow", "sid-5"),
        event("asr_final", "asr_final: text='stop talking'", "sid-5-follow"),
        event("goal_interpretation_done", "goal_interpretation_done: route=interrupt", "sid-5-follow"),
        event("interrupt_previous_audio_done", "interrupt_previous_audio_done: playback_generation=4", "sid-5-follow"),
        event("asr_final", "asr_final: text='remember blue'", "sid-6"),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-6"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False", "sid-6"),
        event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=0", "sid-6"),
        event("asr_final", "asr_final: text='what color'", "sid-6-follow"),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-6-follow"),
        event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False", "sid-6-follow"),
        event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=2", "sid-6-follow"),
        *tts_completion_events("sid-6-follow", "Your test color was blue."),
    ]
    (root / "events.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in runtime_events),
        encoding="utf-8",
    )


def write_live_voice_fixture(root: Path) -> None:
    sid = "live-speech"
    command = [
        "/usr/bin/python",
        "scripts/voice_acceptance.py",
        "--mode",
        "supervised",
        "--cases",
        "speech-only",
    ]
    for name in LIVE_VOICE_REQUIRED_FILES - {
        "bundle-manifest.json",
        "cognitive-runtime.jsonl",
        "events.jsonl",
        "metadata.json",
        "cases.json",
    }:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("fixture\n", encoding="utf-8")
    (root / "command.txt").write_text(shlex.join(command) + "\n", encoding="utf-8")
    (root / "audio-devices.log").write_text(
        "Input device name=physical-microphone\n"
        "Output device name=physical-speaker\n",
        encoding="utf-8",
    )
    metadata = {
        "schema_version": 2,
        "status": "passed",
        "event_count": 7,
        "acceptance_id": "live-voice",
        "operator": "operator",
        "runner": {
            "dry_run": False,
            "mode": "supervised",
            "verification_profile": CURRENT_REVISION_LIVE_VOICE_PROFILE,
            "command": command,
        },
        "chromie": {
            "revision": "abc123",
            "version": "development",
            "dirty": False,
        },
        "selected_cases": ["speech-only"],
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    cases = [
        {
            "case_id": "speech-only",
            "operator_verdict": "pass",
            "operator_notes": "Audible response confirmed.",
            "event_count": 7,
            "session_ids": [sid],
            "checks": [{"name": "fixture", "passed": True}],
        }
    ]
    (root / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (root / "acceptance-overrides.env").write_text(
        "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
        "ORCH_ENABLE_SORIDORMI_CAPABILITIES=0\n"
        "AGENT_INTERACTION_OUTPUT_MODE=native\n"
        "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
        "ORCH_AUDIO_INPUT_MODE=device\n"
        "ORCH_AUDIO_OUTPUT_MODE=device\n"
        "ORCH_COGNITIVE_RUNTIME_MODE=apply\n"
        "ORCH_COGNITIVE_APPLY_LANES=chat,memory,tool\n"
        "ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed\n"
        "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0\n"
        "ORCH_COGNITIVE_EVIDENCE_ENABLED=1\n"
        f"ORCH_COGNITIVE_RUN_IDENTITY_PATH={root / 'runtime-identity.json'}\n",
        encoding="utf-8",
    )
    retained_runtime_profile = {
        "fingerprint": "profile-fingerprint",
        "models": {"fast": "qwen3:4b"},
    }
    runtime_profile_path = root / "runtime-profile.json"
    runtime_profile_path.write_text(
        json.dumps(retained_runtime_profile),
        encoding="utf-8",
    )
    runtime_profile_sha256 = hashlib.sha256(runtime_profile_path.read_bytes()).hexdigest()
    identity = {
        "schema_version": 1,
        "captured_at": "2026-07-31T00:00:00+00:00",
        "evidence_claim": "runtime_identity_only",
        "chromie": {"revision": "abc123", "dirty": False},
        "runtime_profile": {
            "fingerprint": "profile-fingerprint",
            "sha256": runtime_profile_sha256,
            "models": {"fast": "qwen3:4b"},
        },
        "orchestrator_runtime": {
            "effective_models": {"AGENT_FAST_PLANNER_MODEL": "qwen3:4b"},
        },
        "capability_manifests": [{"path": "fixture", "sha256": "b" * 64}],
        "deployment": {
            "complete": True,
            "service_images": {
                service: {
                    "image_id": f"sha256:{service}",
                    "effective_runtime": (
                        {"CHROMIE_RUNTIME_ENV_FINGERPRINT": "profile-fingerprint"}
                        if service == "chromie-agent"
                        else {}
                    ),
                    "effective_models": (
                        {"AGENT_FAST_PLANNER_MODEL": "qwen3:4b"}
                        if service == "chromie-agent"
                        else {}
                    ),
                }
                for service in (
                    "chromie-agent",
                    "chromie-asr",
                    "chromie-llm",
                    "chromie-tts",
                )
            },
        },
        "qualification": {
            "source_clean": True,
            "deployment_complete": True,
            "release_qualified": False,
        },
    }
    identity["identity_sha256"] = canonical_json_sha256(identity)
    (root / "runtime-identity.json").write_text(
        json.dumps(identity),
        encoding="utf-8",
    )
    reference = {
        "identity_sha256": identity["identity_sha256"],
        "complete": True,
    }
    cognitive_events = [
        {
            "event": "cognitive_gateway_admission",
            "sid": sid,
            "channel": "voice",
            "admission": "admit",
            "quality": {"source": "asr_final"},
            "run_identity": reference,
        },
        {
            "event": "cognitive_runtime_resolution",
            "sid": sid,
            "mode": "apply",
            "status": "applied",
            "lane": "chat",
            "run_identity": reference,
            "terminal_plan": {"capability_ids": []},
            "interaction": {"capability_ids": [], "speech_count": 1},
            "fallback_reason": None,
            "metadata": {},
        },
    ]
    (root / "cognitive-runtime.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in cognitive_events),
        encoding="utf-8",
    )
    runtime_events = [
        event("asr_final", "asr_final: text='Tell me a Moon fact.'", sid),
        event("goal_interpretation_done", "goal_interpretation_done: route=chat", sid),
        event(
            "cognitive_interaction_ready",
            "cognitive_interaction_ready: speech=1 capabilities=0 requires_confirmation=False",
            sid,
        ),
        event(
            "capability_runtime_done",
            "capability_runtime_done: status=completed results=1 traces=1 runtime_ms=20.0",
            sid,
        ),
        event(
            "capability_result",
            "capability_result: request_id=speak-1 capability_id=chromie.speak status=completed",
            sid,
        ),
        *tts_completion_events(sid, "The Moon has lower gravity than Earth."),
    ]
    (root / "events.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in runtime_events),
        encoding="utf-8",
    )
    recordings = root / "recordings"
    recordings.mkdir()
    (recordings / f"input_{sid}_1.raw").write_bytes(b"microphone")
    (recordings / f"output_{sid}_2.raw").write_bytes(b"speaker")
    write_bundle_manifest(root)


def _update_json(path: Path, updater) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    updater(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _update_jsonl(path: Path, updater) -> None:
    payload = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    updated = updater(payload)
    path.write_text(
        "".join(json.dumps(item) + "\n" for item in updated),
        encoding="utf-8",
    )


class VoiceInteractionAcceptanceTests(unittest.TestCase):
    def test_acceptance_uses_one_speech_runtime_for_services_and_orchestrator(
        self,
    ) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_OPERATOR_MODE": "services", "TEST_SENTINEL": "retained"},
            clear=True,
        ):
            environment = acceptance_runtime_environment()

        self.assertEqual(environment["CHROMIE_OPERATOR_MODE"], "speech")
        self.assertEqual(environment["TEST_SENTINEL"], "retained")

    def test_host_runtime_requires_python_311_or_newer(self) -> None:
        self.assertFalse(runtime_is_supported((3, 10, 20)))
        self.assertTrue(runtime_is_supported((3, 11, 0)))
        self.assertTrue(runtime_is_supported((3, 13, 1)))

    def test_parse_all_cases_preserves_release_order(self) -> None:
        self.assertEqual(parse_case_list("all"), list(FULL_CASE_ORDER))

    def test_confirmation_replies_wait_for_prompt_playback(self) -> None:
        for case_id, step_index in (
            ("speech-capability", 1),
            ("refusal", 1),
            ("body-cancel", 1),
        ):
            with self.subTest(case_id=case_id):
                self.assertEqual(
                    CASES[case_id]
                    .spoken_steps[step_index]
                    .wait_for_confirmation_prompt_completion,
                    True,
                )

    def test_synthetic_mode_is_the_default(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.mode, "synthetic")

    def test_full_voice_mujoco_verification_profile_remains_the_default(self) -> None:
        args = build_verifier_parser().parse_args(["evidence"])
        self.assertEqual(args.profile, FULL_VOICE_MUJOCO_PROFILE)

    def test_automatic_mode_reexecs_in_managed_runtime_when_needed(self) -> None:
        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=None,
            ),
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                return_value="/usr/bin/conda",
            ),
            mock.patch(
                "scripts.voice_acceptance.os.execvpe",
            ) as execvpe,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            ensure_acceptance_runtime(["--mode", "synthetic", "--allow-dirty"])

        command = execvpe.call_args.args[1]
        environment = execvpe.call_args.args[2]
        self.assertEqual(command[:6], [
            "/usr/bin/conda",
            "run",
            "--no-capture-output",
            "-n",
            "Chromie",
            "python",
        ])
        self.assertEqual(command[-3:], ["--mode", "synthetic", "--allow-dirty"])
        self.assertEqual(environment["CHROMIE_VOICE_ACCEPTANCE_RUNTIME_REEXEC"], "1")

    def test_acoustic_mode_reexecs_in_managed_runtime_when_needed(self) -> None:
        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=None,
            ),
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                return_value="/usr/bin/conda",
            ),
            mock.patch(
                "scripts.voice_acceptance.os.execvpe",
            ) as execvpe,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            ensure_acceptance_runtime(["--mode", "acoustic", "--allow-dirty"])

        command = execvpe.call_args.args[1]
        self.assertEqual(command[-3:], ["--mode", "acoustic", "--allow-dirty"])

    def test_supervised_mode_reexecs_for_tts_warmup_when_needed(self) -> None:
        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=None,
            ),
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                return_value="/usr/bin/conda",
            ),
            mock.patch("scripts.voice_acceptance.os.execvpe") as execvpe,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            ensure_acceptance_runtime(["--mode", "supervised", "--allow-dirty"])

        command = execvpe.call_args.args[1]
        self.assertEqual(command[-3:], ["--mode", "supervised", "--allow-dirty"])

    def test_acoustic_mode_reexecs_when_playback_dependency_is_missing(self) -> None:
        def find_spec(name: str) -> object | None:
            return object() if name == "websockets" else None

        def which(name: str) -> str | None:
            return "/usr/bin/conda" if name == "conda" else None

        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                side_effect=find_spec,
            ),
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                side_effect=which,
            ),
            mock.patch(
                "scripts.voice_acceptance.os.execvpe",
            ) as execvpe,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            ensure_acceptance_runtime(["--mode", "acoustic", "--allow-dirty"])

        command = execvpe.call_args.args[1]
        self.assertEqual(command[-3:], ["--mode", "acoustic", "--allow-dirty"])

    def test_acoustic_mode_uses_host_player_without_reexec(self) -> None:
        def find_spec(name: str) -> object | None:
            return object() if name == "websockets" else None

        def which(name: str) -> str | None:
            if name == "pw-play":
                return "/usr/bin/pw-play"
            if name == "conda":
                return "/usr/bin/conda"
            return None

        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                side_effect=find_spec,
            ),
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                side_effect=which,
            ),
            mock.patch(
                "scripts.voice_acceptance.os.execvpe",
            ) as execvpe,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            ensure_acceptance_runtime(["--mode", "acoustic", "--allow-dirty"])

        execvpe.assert_not_called()

    def test_preflight_does_not_reexec_managed_runtime(self) -> None:
        with (
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=None,
            ),
            mock.patch("scripts.voice_acceptance.os.execvpe") as execvpe,
        ):
            ensure_acceptance_runtime(["--preflight-only"])

        execvpe.assert_not_called()

    def test_preflight_reports_missing_docker_and_soridormi(self) -> None:
        args = build_parser().parse_args(
            [
                "--preflight-only",
                "--cases",
                "speech-capability",
                "--soridormi-mcp-url",
                "http://127.0.0.1:8000/mcp",
                "--soridormi-repo",
                "/missing/soridormi",
                "--start-services",
            ]
        )
        with (
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                side_effect=lambda command: None,
            ),
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=object(),
            ),
            mock.patch(
                "scripts.voice_acceptance.socket.create_connection",
                side_effect=ConnectionRefusedError("refused"),
            ),
        ):
            checks = acceptance_readiness(args, ["speech-capability"])

        failures = {item.name: item.detail for item in checks if not item.passed}
        self.assertIn("Docker CLI", failures)
        self.assertIn("Soridormi MCP endpoint", failures)
        self.assertIn("Soridormi repository", failures)

    def test_speech_only_preflight_allows_services_to_start_later(self) -> None:
        args = build_parser().parse_args(
            [
                "--preflight-only",
                "--cases",
                "speech-only",
                "--start-services",
            ]
        )
        daemon = subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with (
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                side_effect=lambda command: (
                    "/usr/bin/docker"
                    if command == "docker"
                    else "/usr/bin/conda"
                    if command == "conda"
                    else None
                ),
            ),
            mock.patch(
                "scripts.voice_acceptance.subprocess.run",
                return_value=daemon,
            ),
            mock.patch(
                "scripts.voice_acceptance.importlib.util.find_spec",
                return_value=object(),
            ),
        ):
            checks = acceptance_readiness(args, ["speech-only"])

        self.assertTrue(all(item.passed for item in checks))
        self.assertEqual(
            next(item.detail for item in checks if item.name == "TTS endpoint"),
            "Chromie services will be started by --start-services",
        )

    def test_preflight_rejects_an_unsupported_orchestrator_python(self) -> None:
        args = build_parser().parse_args(
            [
                "--preflight-only",
                "--mode",
                "supervised",
                "--cases",
                "speech-only",
                "--start-services",
            ]
        )

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command[-1] == "info":
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "[orchestrator][error] Python 3.10.20 is unsupported; "
                "Python 3.11+ is required.",
            )

        with (
            mock.patch(
                "scripts.voice_acceptance.shutil.which",
                side_effect=lambda command: f"/usr/bin/{command}",
            ),
            mock.patch("scripts.voice_acceptance.subprocess.run", side_effect=run),
        ):
            checks = acceptance_readiness(args, ["speech-only"])

        runtime = next(
            item for item in checks if item.name == "Orchestrator Python runtime"
        )
        self.assertFalse(runtime.passed)
        self.assertIn("Python 3.10.20 is unsupported", runtime.detail)

    def test_preflight_only_does_not_create_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_root = Path(temp_dir) / "evidence"
            args = build_parser().parse_args(
                [
                    "--preflight-only",
                    "--cases",
                    "speech-only",
                    "--evidence-root",
                    str(evidence_root),
                ]
            )
            with (
                mock.patch(
                    "scripts.voice_acceptance.acceptance_readiness",
                    return_value=[CheckResult("test", True, "ready")],
                ),
                mock.patch("builtins.print"),
            ):
                result = run_acceptance(args)

            self.assertEqual(result, 0)
            self.assertFalse(evidence_root.exists())

    def test_supervised_override_records_audio_tuning_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "acceptance-overrides.env"
            with mock.patch.dict(
                os.environ,
                {
                    "ORCH_INPUT_DEVICE": "15",
                    "ORCH_OUTPUT_DEVICE": "14",
                    "ORCH_INPUT_GAIN": "20",
                    "ORCH_MIN_RMS": "5",
                    "ORCH_BARGE_IN_MIN_RMS": "10",
                    "ORCH_VAD_MODE": "0",
                },
                clear=False,
            ):
                write_override_file(
                    path,
                    event_path=Path(temp_dir) / "events.jsonl",
                    recordings_dir=Path(temp_dir) / "recordings",
                    soridormi_mcp_url="http://127.0.0.1:8000/mcp",
                    enable_soridormi=True,
                    mode="supervised",
                )

            text = path.read_text()
            self.assertIn("ORCH_AUDIO_INPUT_MODE=device", text)
            self.assertIn("ORCH_INPUT_DEVICE=15", text)
            self.assertIn("ORCH_OUTPUT_DEVICE=14", text)
            self.assertIn("ORCH_INPUT_GAIN=20", text)
            self.assertIn("ORCH_MIN_RMS=5", text)
            self.assertIn("ORCH_BARGE_IN_MIN_RMS=10", text)
            self.assertIn("ORCH_VAD_MODE=0", text)

    def test_acoustic_override_uses_host_audio_devices(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "acceptance-overrides.env"
            with mock.patch.dict(
                os.environ,
                {
                    "ORCH_INPUT_DEVICE": "0",
                    "ORCH_OUTPUT_DEVICE": "16",
                    "ORCH_INPUT_GAIN": "80",
                },
                clear=False,
            ):
                write_override_file(
                    path,
                    event_path=Path(temp_dir) / "events.jsonl",
                    recordings_dir=Path(temp_dir) / "recordings",
                    soridormi_mcp_url=None,
                    enable_soridormi=False,
                    mode="acoustic",
                )

            text = path.read_text()
            self.assertIn("ORCH_AUDIO_INPUT_MODE=device", text)
            self.assertIn("ORCH_AUDIO_OUTPUT_MODE=discard", text)
            self.assertIn("ORCH_DISCARD_PLAYBACK_REALTIME=1", text)
            self.assertIn("ORCH_INPUT_DEVICE=0", text)
            self.assertIn("ORCH_OUTPUT_DEVICE=16", text)
            self.assertIn("ORCH_INPUT_GAIN=80", text)

    def test_acoustic_override_can_use_device_response_playback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "acceptance-overrides.env"
            write_override_file(
                path,
                event_path=Path(temp_dir) / "events.jsonl",
                recordings_dir=Path(temp_dir) / "recordings",
                soridormi_mcp_url=None,
                enable_soridormi=False,
                mode="acoustic",
                acoustic_response_output_mode="device",
            )

            text = path.read_text()
            self.assertIn("ORCH_AUDIO_INPUT_MODE=device", text)
            self.assertIn("ORCH_AUDIO_OUTPUT_MODE=device", text)

    def test_live_voice_override_disables_body_work_and_binds_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "acceptance-overrides.env"
            identity = Path(temp_dir) / "runtime-identity.json"
            write_override_file(
                path,
                event_path=Path(temp_dir) / "events.jsonl",
                recordings_dir=Path(temp_dir) / "recordings",
                soridormi_mcp_url=None,
                enable_soridormi=False,
                mode="supervised",
                runtime_identity_path=identity,
            )

            text = path.read_text(encoding="utf-8")
            self.assertIn("ORCH_ENABLE_SORIDORMI_CAPABILITIES=0", text)
            self.assertIn("ORCH_COGNITIVE_APPLY_LANES=chat,memory,tool", text)
            self.assertIn(f"ORCH_COGNITIVE_RUN_IDENTITY_PATH={identity}", text)

    def test_host_speaker_player_uses_pw_play_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fixture.wav"
            path.write_bytes(b"RIFFfixture")
            fixture = AudioFixture(
                text="hello",
                pcm16=b"\x00\x00" * 10,
                sample_rate=44100,
                channels=1,
                path=path,
            )

            def which(name: str) -> str | None:
                return "/usr/bin/pw-play" if name == "pw-play" else None

            with (
                mock.patch("scripts.acceptance_audio.shutil.which", side_effect=which),
                mock.patch("scripts.acceptance_audio.subprocess.run") as run,
            ):
                run.return_value = SimpleNamespace(
                    returncode=0,
                    stdout="",
                    stderr="",
                )
                HostSpeakerPlayer(player="auto").play(fixture, timeout_s=3)

            command = run.call_args.args[0]
            self.assertEqual(command, ["/usr/bin/pw-play", str(path)])

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
                recordings_dir=Path(temp_dir),
                orchestrator_process=process,
            )
            driver.deliver(fixture.text)
            stdin.seek(0)
            decoded = read_audio_packet(stdin)
            self.assertEqual(decoded.pcm16, fixture.pcm16)

    def test_tts_readiness_requires_ready_live_worker(self) -> None:
        self.assertEqual(
            tts_health_ready(
                {
                    "provider_health": {
                        "ready": True,
                        "worker_process_alive": True,
                    }
                }
            ),
            (True, "provider and worker are ready"),
        )
        ready, detail = tts_health_ready(
            {
                "provider_health": {
                    "ready": True,
                    "worker_process_alive": False,
                }
            }
        )
        self.assertFalse(ready)
        self.assertIn("not alive", detail)

    def test_supervised_tts_warmup_uses_effective_runtime_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_env = root / ".env.runtime"
            runtime_env.write_text(
                "TTS_SPEAKER_ID=chromie_mixed\n",
                encoding="utf-8",
            )
            output_dir = root / "warmup"
            fixture = AudioFixture(
                text="Hello.",
                pcm16=b"\x01\x00" * 32,
                sample_rate=24000,
                channels=1,
                path=output_dir / "01-hello.wav",
            )
            with mock.patch(
                "scripts.voice_acceptance.generate_tts_fixtures",
                return_value={"Hello.": fixture},
            ) as generate:
                result = warm_supervised_tts_delivery(
                    "ws://127.0.0.1:5000",
                    runtime_env_path=runtime_env,
                    output_dir=output_dir,
                    fallback_speaker_id="default",
                    default_sample_rate=44100,
                    timeout_s=180.0,
                )

            self.assertEqual(result["speaker_id"], "chromie_mixed")
            self.assertEqual(result["pcm_bytes"], 64)
            self.assertEqual(result["playback"], "disabled")
            self.assertEqual(
                generate.call_args.kwargs["speaker_id"],
                "chromie_mixed",
            )
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["purpose"], "supervised_response_delivery_warmup")

    def test_synthetic_audio_driver_replays_retained_output_pcm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recordings = root / "recordings"
            recordings.mkdir()
            payload = b"\x03\x00" * 160
            (recordings / "output_sid-echo_1.raw").write_bytes(payload)
            stdin = io.BytesIO()
            driver = AcceptanceAudioDriver(
                mode="synthetic",
                fixtures={},
                recordings_dir=recordings,
                orchestrator_process=SimpleNamespace(stdin=stdin),
            )

            fixture = driver.replay_output(
                session_id="sid-echo",
                source_rate=24000,
            )

            stdin.seek(0)
            decoded = read_audio_packet(stdin)
            self.assertEqual(decoded.pcm16, payload)
            self.assertEqual(decoded.sample_rate, 24000)
            self.assertTrue(fixture.path.is_file())

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
            self.assertIn("ORCH_COGNITIVE_RUNTIME_MODE=apply", text)
            self.assertIn("ORCH_COGNITIVE_APPLY_LANES=chat,memory,robot_action,tool", text)
            self.assertIn("ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed", text)
            self.assertIn("ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0", text)
            self.assertIn("cognitive-runtime.jsonl", text)

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
            self.assertIn("ORCH_INPUT_DEVICE=chromie_test.monitor", text)
            self.assertIn("ORCH_AUDIO_INPUT_MODE=device", text)
            self.assertIn("ORCH_AUDIO_OUTPUT_MODE=discard", text)

    def test_virtual_mic_selects_native_pipewire_fallback(self) -> None:
        available = {"pw-cli", "pw-cat", "pw-dump"}
        with mock.patch(
            "scripts.acceptance_audio.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}" if name in available else None,
        ):
            self.assertEqual(
                PulseVirtualMicrophone.available_backend(),
                "pipewire",
            )

    def test_native_pipewire_virtual_mic_lifecycle(self) -> None:
        microphone = PulseVirtualMicrophone("chromie_test")
        fixture = AudioFixture(
            text="Yes.",
            pcm16=b"",
            sample_rate=44100,
            channels=1,
            path=Path("/tmp/yes.wav"),
        )
        completed = SimpleNamespace(returncode=0, stdout="")
        with (
            mock.patch.object(
                PulseVirtualMicrophone,
                "require_tools",
                return_value="pipewire",
            ),
            mock.patch.object(
                microphone,
                "_pipewire_node_id",
                return_value=70,
            ),
            mock.patch(
                "scripts.acceptance_audio.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            microphone.start()
            microphone.play(fixture)
            microphone.stop()

        self.assertEqual(microphone.backend, None)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:3], ["pw-cli", "create-node", "adapter"])
        self.assertEqual(
            commands[1],
            ["pw-cat", "--playback", "--target", "chromie_test", "/tmp/yes.wav"],
        )
        self.assertEqual(commands[2], ["pw-cli", "destroy", "70"])

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
        self.assertEqual(
            command[-4:],
            [
                "--manifest",
                "/app/capabilities/soridormi.json",
                "--exclude-effect",
                "test_control",
            ],
        )

    def test_body_cases_start_agent_with_soridormi_manifest(self) -> None:
        values = service_runtime_overrides(
            soridormi_mcp_url="http://127.0.0.1:8000/mcp",
            enable_soridormi=True,
        )
        self.assertEqual(
            values["AGENT_CAPABILITY_MANIFESTS"],
            "/app/capabilities/soridormi.json",
        )
        self.assertEqual(
            values["SORIDORMI_MCP_URL"],
            "http://host.docker.internal:8000/mcp",
        )

    def test_service_override_file_is_shell_sourceable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "service.env"
            write_service_override_file(
                path,
                {
                    "AGENT_CAPABILITY_MANIFESTS": "/app/capabilities/soridormi.json",
                    "SORIDORMI_MCP_URL": "http://host.docker.internal:8000/mcp",
                },
            )
            text = path.read_text()

        self.assertIn("AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json", text)
        self.assertIn("SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp", text)

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
        self.assertEqual(command[-2:], ["--exclude-effect", "test_control"])

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
                + json.dumps(event("goal_interpretation_done", "route=chat")) + "\n"
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

    def test_confirmation_prompt_wait_ignores_earlier_unbound_playback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            records = [
                event(
                    "playback_start",
                    "playback_start: order=9 generation=1",
                    "sid-1",
                ),
                event(
                    "playback_end",
                    "playback_end: order=9 played_tts=1",
                    "sid-1",
                ),
                event(
                    "confirmation_requested",
                    "confirmation_requested: confirmation_id=c1",
                    "sid-1",
                ),
                *confirmation_prompt_playback_events("sid-1"),
            ]
            path.write_text(
                "".join(json.dumps(item) + "\n" for item in records),
                encoding="utf-8",
            )

            matched = wait_for_confirmation_prompt_completion(
                path,
                marker=0,
                timeout_s=0.01,
                session_ids={"sid-1"},
                poll_s=0.001,
            )

        self.assertIsNotNone(matched)
        self.assertEqual(matched["event"], "playback_end")
        self.assertIn("order=0", str(matched["message"]))

    def test_guided_step_reports_detected_transcript(self) -> None:
        case = CASES["speech-only"]
        detected = event(
            "asr_final",
            "asr_final: asr_ms=12.0 text_chars=10 text='hello moon'",
        )
        with mock.patch(
            "scripts.voice_acceptance.wait_for_any_event",
            return_value=detected,
        ), mock.patch("scripts.voice_acceptance.print_countdown"), mock.patch(
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
                "capability_proposed",
                "capability_proposed: request_id=req-1 capability_id=soridormi.nod_yes "
                "timing=parallel cancellable=True requires_confirmation=False",
            )
        )
        completed = friendly_event_line(
            event(
                "capability_result",
                "capability_result: request_id=req-1 capability_id=soridormi.nod_yes "
                "status=completed reason=None message=done",
            )
        )
        self.assertIn("soridormi.nod_yes", proposed or "")
        self.assertIn("status=completed", completed or "")

    def test_case_events_are_isolated_by_session(self) -> None:
        records = [
            event("capability_result", "capability_result: status=completed", "old"),
            event("interaction_done", "interaction_done: capabilities=0", "current"),
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
                event("goal_interpretation_done", "goal_interpretation_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0"),
                *tts_completion_events("sid-1", "A short spoken answer."),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_speech_only_accepts_current_cognitive_core_event(self) -> None:
        checks = analyze_case(
            "speech-only",
            [
                event("asr_final", "asr_final: text='hello'"),
                event(
                    "cognitive_core_done",
                    "cognitive_core_done: lane=chat intent=greeting",
                ),
                event(
                    "cognitive_interaction_ready",
                    "cognitive_interaction_ready: speech=1 capabilities=0",
                ),
                *tts_completion_events("sid-1", "A short spoken answer."),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_speech_only_rejects_session_done_without_tts_output(self) -> None:
        checks = analyze_case(
            "speech-only",
            [
                event("asr_final", "asr_final: text='hello'"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0"),
                event(
                    "session_done",
                    "session_done: scheduled_tts=0 queued_tts=0 played_tts=0 "
                    "failed_tts=0 skipped_tts=0 response_chars=0 total_ms=10.0",
                ),
            ],
        )
        self.assertFalse(
            next(item.passed for item in checks if item.name == "speech output completed")
        )

    def test_wait_for_case_checks_returns_when_evidence_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            records = [
                event("asr_final", "asr_final: text='hello'"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0"),
                *tts_completion_events("sid-1", "A short spoken answer."),
            ]
            path.write_text("".join(json.dumps(item) + "\n" for item in records))
            events, checks = wait_for_case_checks(
                "speech-only",
                path,
                marker=0,
                timeout_s=0.1,
                poll_s=0.001,
            )
            self.assertEqual(len(events), 7)
            self.assertTrue(all(item.passed for item in checks))

    def test_body_cancel_accepts_cancelled_runtime_completion(self) -> None:
        checks = analyze_case(
            "body-cancel",
            [
                event("asr_final", "asr_final: text='nod eight times'", "body-session"),
                event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "body-session"),
                event("cognitive_interaction_ready", "cognitive_interaction_ready: speech=1 capabilities=1 requires_confirmation=True", "body-session"),
                event("cognitive_capability_proposed", 'cognitive_capability_proposed: request_id=body-1 capability_id=soridormi.nod_yes timing=parallel requires_confirmation=True args={"count":8}', "body-session"),
                event(
                    "confirmation_requested",
                    "confirmation_requested: confirmation_id=confirm-1 "
                    "interaction_id=interaction-1 request_ids=body-1 "
                    "fingerprint=abc expires_at=1.0",
                    "body-session",
                ),
                event(
                    "confirmation_reply",
                    "confirmation_reply: confirmation_id=confirm-1 "
                    "decision=approved fingerprint=abc",
                    "body-session",
                ),
                event(
                    "confirmation_authorized",
                    "confirmation_authorized: confirmation_id=confirm-1 "
                    "interaction_id=interaction-1 request_ids=body-1 "
                    "fingerprint=abc",
                    "body-session",
                ),
                event(
                    "asr_final",
                    "asr_final: text='stop talking'",
                    "stop-session",
                ),
                event(
                    "goal_interpretation_done",
                    "goal_interpretation_done: route=interrupt",
                    "stop-session",
                ),
                event(
                    "capability_runtime_cancelled",
                    "capability_runtime_cancelled: runtime_ms=10.0",
                    "body-session",
                ),
                event(
                    "soridormi_post_status",
                    "soridormi_post_status: mode=sim backend=runtime safe_idle=True "
                    "active_task_present=False emergency_stop=False fallen=False",
                    "body-session",
                ),
                event(
                    "interrupt_previous_audio_done",
                    "interrupt_previous_audio_done: playback_generation=2",
                    "stop-session",
                ),
            ],
        )

        self.assertTrue(all(item.passed for item in checks))

    def test_barge_in_rejects_stale_old_session_playback(self) -> None:
        records = [
            event(
                "playback_start",
                "playback_start: order=0 source_rate=44100 output_rate=44100 "
                "audio_ms=30000.0 generation=1",
                "old",
            ),
            event(
                "playback_duck_started",
                "playback_duck_started: generation=1 vad_start_to_duck_ms=30.0 "
                "cancel_cognitive_work=false pause_error=none",
                "old",
            ),
            event(
                "session_interrupted_by_new_session",
                "session_interrupted_by_new_session: new_sid=stop",
                "old",
            ),
            event("asr_final", "asr_final: text='stop talking'", "stop"),
            event(
                "barge_in_external_speech_confirmed",
                "barge_in_external_speech_confirmed: scope=output_only "
                "cancel_cognitive_work=false playback_generation_at_start=1 "
                "confirmed_speech_to_silence_ms=25.0",
                "stop",
            ),
            event(
                "cognitive_gateway_cancellation_dispatched",
                "cognitive_gateway_cancellation_dispatched: "
                "requested_scope=output_only effective_scope=output_only "
                "interactions=none selected=0 active=0 queued=0 "
                "non_interruptible=0 provider_failures=0 dispatch_failures=0",
                "stop",
            ),
            event(
                "cognitive_gateway_reflex_applied",
                "cognitive_gateway_reflex_applied: action=interrupt "
                "trigger=stop_output_command goal_interpretation_bypassed=True",
                "stop",
            ),
            event(
                "playback_start",
                "playback_start: order=1 source_rate=44100 output_rate=44100 "
                "audio_ms=100.0 generation=1",
                "old",
            ),
        ]
        checks = analyze_case("barge-in", records)
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "stale playback did not resume"
            )
        )

    def test_barge_in_accepts_independent_retry_receipt(self) -> None:
        records = [
            event(
                "playback_start",
                "playback_start: order=0 source_rate=44100 output_rate=44100 "
                "audio_ms=30000.0 generation=1",
                "old",
            ),
            event(
                "playback_duck_started",
                "playback_duck_started: generation=1 vad_start_to_duck_ms=30.0 "
                "cancel_cognitive_work=false pause_error=none",
                "old",
            ),
            event(
                "session_interrupted_by_new_session",
                "session_interrupted_by_new_session: new_sid=unrecognized",
                "old",
            ),
            event("asr_final", "asr_final: text='unrecognized stop'", "unrecognized"),
            event(
                "barge_in_external_speech_confirmed",
                "barge_in_external_speech_confirmed: scope=output_only "
                "cancel_cognitive_work=false playback_generation_at_start=1 "
                "confirmed_speech_to_silence_ms=25.0",
                "unrecognized",
            ),
            event("asr_final", "asr_final: text='stop talking'", "retry"),
            event(
                "cognitive_gateway_cancellation_dispatched",
                "cognitive_gateway_cancellation_dispatched: "
                "requested_scope=output_only effective_scope=output_only "
                "interactions=none selected=0 active=0 queued=0 "
                "non_interruptible=0 provider_failures=0 dispatch_failures=0",
                "retry",
            ),
            event(
                "cognitive_gateway_reflex_applied",
                "cognitive_gateway_reflex_applied: action=interrupt "
                "trigger=stop_output_command goal_interpretation_bypassed=True",
                "retry",
            ),
        ]

        checks = analyze_case("barge-in", records)

        self.assertTrue(all(item.passed for item in checks), checks)

    def test_barge_in_missing_interrupt_asr_fails_without_analyzer_error(self) -> None:
        checks = analyze_case(
            "barge-in",
            [
                event(
                    "playback_start",
                    "playback_start: order=0 source_rate=44100 "
                    "output_rate=44100 audio_ms=30000.0 generation=1",
                    "old",
                ),
                event(
                    "playback_duck_started",
                    "playback_duck_started: generation=1 "
                    "vad_start_to_duck_ms=30.0 cancel_cognitive_work=false "
                    "pause_error=none",
                    "old",
                ),
                event(
                    "session_interrupted_by_new_session",
                    "session_interrupted_by_new_session: new_sid=stop",
                    "old",
                ),
                event(
                    "barge_in_external_speech_confirmed",
                    "barge_in_external_speech_confirmed: scope=output_only "
                    "cancel_cognitive_work=false playback_generation_at_start=1 "
                    "confirmed_speech_to_silence_ms=25.0",
                    "stop",
                ),
            ],
        )
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "active playback session interrupted"
            )
        )

    def test_barge_in_echo_requires_same_generation_resume_and_no_duplicates(self) -> None:
        checks = analyze_case(
            "barge-in-echo",
            [
                event(
                    "playback_start",
                    "playback_start: order=1 source_rate=44100 output_rate=44100 "
                    "audio_ms=30000.0 generation=4",
                    "old",
                ),
                event(
                    "playback_duck_started",
                    "playback_duck_started: generation=4 "
                    "vad_start_to_duck_ms=35.0 cancel_cognitive_work=false "
                    "pause_error=none",
                    "old",
                ),
                event(
                    "asr_tts_echo_suppressed",
                    "asr_tts_echo_suppressed: generation=4 ratio=1.000 "
                    "coverage=1.000 text='the robot response'",
                    "old",
                ),
                event(
                    "playback_duck_released",
                    "playback_duck_released: generation=4 "
                    "reason=likely_tts_echo duck_duration_ms=400.0 "
                    "resume_error=none",
                    "old",
                ),
                event(
                    "playback_end",
                    "playback_end: order=1 playback_ms=1000.0 played_tts=2",
                    "old",
                ),
                event(
                    "session_done",
                    "session_done: scheduled_tts=2 queued_tts=2 played_tts=2 "
                    "failed_tts=0 skipped_tts=0 response_chars=80 total_ms=2000.0",
                    "old",
                ),
            ],
        )

        self.assertTrue(all(item.passed for item in checks))

    def test_stop_rejects_late_old_session_work(self) -> None:
        records = [
            event(
                "playback_start",
                "playback_start: order=0 source_rate=44100 output_rate=44100 "
                "audio_ms=30000.0 generation=1",
                "old",
            ),
            event(
                "session_interrupted_by_new_session",
                "session_interrupted_by_new_session: new_sid=stop",
                "old",
            ),
            event("asr_final", "asr_final: text='stop talking'", "stop"),
            event("goal_interpretation_done", "goal_interpretation_done: route=interrupt", "stop"),
            event(
                "interrupt_previous_audio_done",
                "interrupt_previous_audio_done: playback_generation=2",
                "stop",
            ),
            event(
                "capability_result",
                "capability_result: request_id=late capability_id=soridormi.nod_yes "
                "status=completed",
                "old",
            ),
        ]
        checks = analyze_case("stop", records)
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "no stale output or completed work after stop"
            )
        )

    def test_stop_accepts_current_gateway_reflex_receipt(self) -> None:
        records = [
            event(
                "playback_start",
                "playback_start: order=0 source_rate=44100 output_rate=44100 "
                "audio_ms=30000.0 generation=1",
                "old",
            ),
            event(
                "session_interrupted_by_new_session",
                "session_interrupted_by_new_session: new_sid=stop",
                "old",
            ),
            event("asr_final", "asr_final: text='stop talking'", "stop"),
            event(
                "cognitive_gateway_reflex_applied",
                "cognitive_gateway_reflex_applied: action=interrupt "
                "trigger=stop_command goal_interpretation_bypassed=True",
                "stop",
            ),
            event(
                "interrupt_previous_audio_done",
                "interrupt_previous_audio_done: playback_generation=2",
                "stop",
            ),
        ]
        checks = analyze_case("stop", records)
        self.assertTrue(all(item.passed for item in checks))

    def test_speech_skill_requires_bound_spoken_approval(self) -> None:
        checks = analyze_case(
            "speech-capability",
            speech_capability_runtime_events(),
        )

        self.assertTrue(all(item.passed for item in checks))

    def test_speech_skill_rejects_approval_before_confirmation_prompt_completion(
        self,
    ) -> None:
        checks = analyze_case(
            "speech-capability",
            speech_capability_runtime_events(include_confirmation_prompt=False),
        )

        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "confirmation prompt playback completed"
            )
        )

    def test_speech_skill_rejects_mismatched_confirmation_fingerprint(self) -> None:
        checks = analyze_case(
            "speech-capability",
            [
                event("asr_final", "asr_final: text='Please nod twice.'"),
                event("goal_interpretation_done", "goal_interpretation_done: route=robot_action"),
                event("interaction_done", "interaction_done: speech=1 capabilities=1"),
                event(
                    "capability_proposed",
                    'capability_proposed: request_id=nod-1 capability_id=soridormi.nod_yes '
                    'requires_confirmation=True args={"count":2}',
                ),
                event(
                    "confirmation_requested",
                    "confirmation_requested: confirmation_id=confirm-1 "
                    "interaction_id=interaction-1 request_ids=nod-1 "
                    "fingerprint=expected expires_at=1.0",
                ),
                event(
                    "confirmation_reply",
                    "confirmation_reply: confirmation_id=confirm-1 "
                    "decision=approved fingerprint=different",
                ),
                event(
                    "confirmation_authorized",
                    "confirmation_authorized: confirmation_id=confirm-1 "
                    "interaction_id=interaction-1 request_ids=nod-1 "
                    "fingerprint=expected",
                ),
            ],
        )
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "exact request confirmation approved"
            )
        )

    def test_refusal_requires_denial_and_no_body_completion(self) -> None:
        checks = analyze_case(
            "refusal",
            [
                event("asr_final", "asr_final: text='Please nod twice.'", "sid-1"),
                event("goal_interpretation_done", "goal_interpretation_done: route=robot_action", "sid-1"),
                event(
                    "interaction_done",
                    "interaction_done: speech=1 capabilities=1 requires_confirmation=True",
                    "sid-1",
                ),
                event(
                    "capability_proposed",
                    'capability_proposed: request_id=nod-1 capability_id=soridormi.nod_yes '
                    'timing=parallel cancellable=True requires_confirmation=True args={"count":2}',
                    "sid-1",
                ),
                event(
                    "confirmation_requested",
                    "confirmation_requested: confirmation_id=confirm-1 "
                    "interaction_id=interaction-1 request_ids=nod-1 "
                    "fingerprint=abc expires_at=1.0",
                    "sid-1",
                ),
                event(
                    "confirmation_reply",
                    "confirmation_reply: confirmation_id=confirm-1 "
                    "decision=denied fingerprint=abc",
                    "sid-2",
                ),
                event(
                    "confirmation_rejected",
                    "confirmation_rejected: confirmation_id=confirm-1 "
                    "reason=denied fingerprint=abc",
                    "sid-2",
                ),
                *tts_completion_events(
                    "sid-2", "Okay, I will not perform that action."
                ),
            ],
        )

        self.assertTrue(all(item.passed for item in checks))

    def test_refusal_rejects_denial_without_spoken_output(self) -> None:
        records = [
            event("asr_final", "asr_final: text='Please nod twice.'"),
            event("goal_interpretation_done", "goal_interpretation_done: route=robot_action"),
            event("interaction_done", "interaction_done: speech=1 capabilities=1"),
            event(
                "capability_proposed",
                'capability_proposed: request_id=nod-1 capability_id=soridormi.nod_yes '
                'requires_confirmation=True args={"count":2}',
            ),
            event(
                "confirmation_requested",
                "confirmation_requested: confirmation_id=confirm-1 "
                "interaction_id=interaction-1 request_ids=nod-1 "
                "fingerprint=abc expires_at=1.0",
            ),
            event(
                "confirmation_reply",
                "confirmation_reply: confirmation_id=confirm-1 "
                "decision=denied fingerprint=abc",
            ),
            event(
                "confirmation_rejected",
                "confirmation_rejected: confirmation_id=confirm-1 "
                "reason=denied fingerprint=abc",
            ),
        ]
        checks = analyze_case("refusal", records)
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "denial speech output completed"
            )
        )

    def test_followup_requires_two_utterances_in_same_conversation(self) -> None:
        checks = analyze_case(
            "follow-up",
            [
                event("asr_final", "asr_final: text='remember blue'", "sid-1"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-1"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0", "sid-1"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=0", "sid-1"),
                event("asr_final", "asr_final: text='what color'", "sid-2"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-2"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0", "sid-2"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=2", "sid-2"),
                *tts_completion_events("sid-2", "Your test color was blue."),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_followup_rejects_response_without_recalled_value(self) -> None:
        checks = analyze_case(
            "follow-up",
            [
                event("asr_final", "asr_final: text='remember blue'", "sid-1"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-1"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0", "sid-1"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=0", "sid-1"),
                event("asr_final", "asr_final: text='what color'", "sid-2"),
                event("goal_interpretation_done", "goal_interpretation_done: route=chat", "sid-2"),
                event("interaction_done", "interaction_done: speech=1 capabilities=0", "sid-2"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=2", "sid-2"),
                *tts_completion_events("sid-2", "I do not remember."),
            ],
        )
        self.assertFalse(
            next(
                item.passed
                for item in checks
                if item.name == "follow-up response recalled blue"
            )
        )

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

    def test_current_revision_live_voice_profile_verifies_narrow_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_live_voice_fixture(root)

            report = verify_bundle(
                root,
                profile=CURRENT_REVISION_LIVE_VOICE_PROFILE,
                expected_chromie_revision="abc123",
                expected_chromie_version="development",
            )

            self.assertTrue(report["passed"], report)
            self.assertTrue(
                report["current_revision_live_voice_claim"]["eligible"]
            )
            self.assertFalse(report["release_qualified"])
            self.assertFalse(report["human_voice_device_claim_eligible"])
            self.assertTrue(report["runtime_identity"]["source_bound"])
            self.assertTrue(report["artifact_manifest"]["valid"])
            self.assertEqual(report["cognitive_runtime"]["applied_lanes"], ["chat"])
            full_report = verify_bundle(
                root,
                expected_chromie_revision="abc123",
                expected_chromie_version="development",
                expected_soridormi_revision="def456",
            )
            self.assertFalse(full_report["passed"])
            self.assertTrue(
                any("Missing required cases" in item for item in full_report["errors"])
            )

    def test_current_revision_live_voice_rejects_nonphysical_or_unreviewed_input(self) -> None:
        mutations = {
            "synthetic input": lambda root: (
                _update_json(
                    root / "metadata.json",
                    lambda payload: payload["runner"].update({"mode": "synthetic"}),
                )
            ),
            "absent operator verdict": lambda root: _update_json(
                root / "cases.json",
                lambda payload: payload[0].pop("operator_verdict"),
            ),
            "missing microphone recording": lambda root: next(
                (root / "recordings").glob("input_*.raw")
            ).unlink(),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                write_live_voice_fixture(root)
                mutate(root)
                write_bundle_manifest(root)
                report = verify_bundle(
                    root,
                    profile=CURRENT_REVISION_LIVE_VOICE_PROFILE,
                    expected_chromie_revision="abc123",
                    expected_chromie_version="development",
                )
                self.assertFalse(report["passed"], report)
                self.assertFalse(
                    report["current_revision_live_voice_claim"]["eligible"]
                )

    def test_current_revision_live_voice_rejects_incomplete_or_unsafe_turns(self) -> None:
        def remove_playback_end(root: Path) -> None:
            _update_jsonl(
                root / "events.jsonl",
                lambda events: [
                    item for item in events if item.get("event") != "playback_end"
                ],
            )

        def add_capability(root: Path) -> None:
            _update_jsonl(
                root / "cognitive-runtime.jsonl",
                lambda events: [
                    {
                        **item,
                        "terminal_plan": {"capability_ids": ["soridormi.nod_yes"]},
                    }
                    if item.get("event") == "cognitive_runtime_resolution"
                    else item
                    for item in events
                ],
            )

        def add_body_capability_result(root: Path) -> None:
            _update_jsonl(
                root / "events.jsonl",
                lambda events: [
                    *events,
                    event(
                        "capability_result",
                        "capability_result: request_id=nod-1 "
                        "capability_id=soridormi.nod_yes status=completed",
                        "live-speech",
                    ),
                ],
            )

        def claim_unretained_capability_result(root: Path) -> None:
            _update_jsonl(
                root / "events.jsonl",
                lambda events: [
                    {
                        **item,
                        "message": str(item["message"]).replace(
                            "results=1", "results=2"
                        ),
                    }
                    if item.get("event") == "capability_runtime_done"
                    else item
                    for item in events
                ],
            )

        def add_stale_playback(root: Path) -> None:
            _update_jsonl(
                root / "events.jsonl",
                lambda events: [
                    *events,
                    event(
                        "playback_drop_stale_before_order",
                        "playback_drop_stale_before_order: order=1",
                        "live-speech",
                    ),
                ],
            )

        def add_timeout(root: Path) -> None:
            _update_jsonl(
                root / "cognitive-runtime.jsonl",
                lambda events: [
                    {
                        **item,
                        "metadata": {"failure_class": "timeout"},
                    }
                    if item.get("event") == "cognitive_runtime_resolution"
                    else item
                    for item in events
                ],
            )

        def add_truncation(root: Path) -> None:
            _update_jsonl(
                root / "events.jsonl",
                lambda events: [
                    *events,
                    event(
                        "llm_output_truncated",
                        "llm_output_truncated: purpose=response_composer",
                        "live-speech",
                    ),
                ],
            )

        def add_authority_fallback(root: Path) -> None:
            _update_jsonl(
                root / "cognitive-runtime.jsonl",
                lambda events: [
                    {**item, "fallback_reason": "model unavailable"}
                    if item.get("event") == "cognitive_runtime_resolution"
                    else item
                    for item in events
                ],
            )

        for label, mutate in {
            "partial playback": remove_playback_end,
            "executable capability": add_capability,
            "body capability runtime result": add_body_capability_result,
            "unretained capability runtime result": claim_unretained_capability_result,
            "stale playback": add_stale_playback,
            "critical model timeout": add_timeout,
            "truncated model output": add_truncation,
            "post-authority fallback": add_authority_fallback,
        }.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                write_live_voice_fixture(root)
                mutate(root)
                write_bundle_manifest(root)
                report = verify_bundle(
                    root,
                    profile=CURRENT_REVISION_LIVE_VOICE_PROFILE,
                    expected_chromie_revision="abc123",
                    expected_chromie_version="development",
                )
                self.assertFalse(report["passed"], report)

    def test_current_revision_live_voice_rejects_unbound_source_and_artifacts(self) -> None:
        def mark_dirty(root: Path) -> None:
            _update_json(
                root / "metadata.json",
                lambda payload: payload["chromie"].update({"dirty": True}),
            )

        def mismatch_source(root: Path) -> None:
            _update_json(
                root / "metadata.json",
                lambda payload: payload["chromie"].update({"revision": "old-source"}),
            )

        def remove_runtime_identity(root: Path) -> None:
            (root / "runtime-identity.json").unlink()

        def remove_running_service(root: Path) -> None:
            def mutate(payload: dict[str, object]) -> None:
                payload["deployment"]["service_images"].pop("chromie-tts")
                payload["identity_sha256"] = canonical_json_sha256(
                    {key: value for key, value in payload.items() if key != "identity_sha256"}
                )

            _update_json(root / "runtime-identity.json", mutate)

        def tamper_after_manifest(root: Path) -> None:
            with (root / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write("{}\n")

        for label, mutate, refresh_manifest in (
            ("dirty source", mark_dirty, True),
            ("mismatched source", mismatch_source, True),
            ("missing runtime identity", remove_runtime_identity, True),
            ("missing running service", remove_running_service, True),
            ("artifact digest mismatch", tamper_after_manifest, False),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                write_live_voice_fixture(root)
                mutate(root)
                if refresh_manifest:
                    write_bundle_manifest(root)
                report = verify_bundle(
                    root,
                    profile=CURRENT_REVISION_LIVE_VOICE_PROFILE,
                    expected_chromie_revision="abc123",
                    expected_chromie_version="development",
                )
                self.assertFalse(report["passed"], report)

    def test_complete_evidence_bundle_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            write_cognitive_runtime_fixture(root)
            metadata = {
                "schema_version": 2,
                "status": "passed",
                "event_count": 40,
                "acceptance_id": "test",
                "runner": {"dry_run": False, "mode": "supervised"},
                "chromie": {"revision": "abc123", "version": "development", "dirty": False},
                "soridormi_manifest": {"upstream_commit": "def456"},
                "soridormi_local_revision": "def456",
                "soridormi_local_dirty": False,
                "soridormi_source_binding": {
                    "kind": "endpoint_reported_revision",
                    "endpoint_revision": "def456",
                },
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                "selected_cases": list(FULL_CASE_ORDER),
            }
            cases = [
                {
                    "case_id": case_id,
                    "operator_verdict": "pass",
                    "event_count": 2,
                    "session_ids": fixture_case_session_ids(index, case_id),
                    "checks": [{"name": "check", "passed": True}],
                }
                for index, case_id in enumerate(FULL_CASE_ORDER)
            ]
            (root / "metadata.json").write_text(json.dumps(metadata))
            (root / "cases.json").write_text(json.dumps(cases))
            (root / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_CAPABILITIES=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=device\n"
                "ORCH_AUDIO_OUTPUT_MODE=device\n"
                + GOAL_DRIVEN_OVERRIDE_TEXT
            )
            report = verify_bundle(
                root,
                require_clean=True,
                expected_chromie_revision="abc123",
                expected_chromie_version="development",
                expected_soridormi_revision="def456",
            )
            self.assertTrue(report["passed"], report)
            self.assertEqual(report["verification_profile"], FULL_VOICE_MUJOCO_PROFILE)
            self.assertTrue(report["policy_evaluation_ready"])
            self.assertTrue(report["human_voice_device_claim_eligible"])

            for missing_dirty in (True, False):
                with self.subTest(
                    chromie_dirty=("missing" if missing_dirty else None)
                ):
                    if missing_dirty:
                        metadata["chromie"].pop("dirty", None)
                    else:
                        metadata["chromie"]["dirty"] = None
                    (root / "metadata.json").write_text(json.dumps(metadata))
                    report = verify_bundle(
                        root,
                        require_clean=True,
                        expected_chromie_revision="abc123",
                        expected_chromie_version="development",
                        expected_soridormi_revision="def456",
                    )
                    self.assertFalse(
                        report["passed"],
                        "clean evidence must explicitly record chromie.dirty=false",
                    )

    def test_automated_evidence_verifies_only_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            write_cognitive_runtime_fixture(root)
            metadata = {
                "schema_version": 2,
                "status": "passed",
                "event_count": 40,
                "acceptance_id": "test-auto",
                "runner": {"dry_run": False, "mode": "synthetic"},
                "chromie": {
                    "revision": "abc123",
                    "version": "development",
                    "dirty": False,
                },
                "soridormi_manifest": {"upstream_commit": "def456"},
                "soridormi_local_revision": "def456",
                "soridormi_local_dirty": False,
                "soridormi_source_binding": {
                    "kind": "endpoint_reported_revision",
                    "endpoint_revision": "def456",
                },
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                "selected_cases": list(FULL_CASE_ORDER),
            }
            cases = [
                {
                    "case_id": case_id,
                    "operator_verdict": "automated",
                    "event_count": 2,
                    "session_ids": fixture_case_session_ids(index, case_id),
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
                "ORCH_ENABLE_SORIDORMI_CAPABILITIES=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=stdin\n"
                "ORCH_AUDIO_OUTPUT_MODE=discard\n"
                + GOAL_DRIVEN_OVERRIDE_TEXT
            )
            release_report = verify_bundle(
                root,
                expected_chromie_revision="abc123",
                expected_chromie_version="development",
                expected_soridormi_revision="def456",
            )
            self.assertFalse(release_report["passed"])
            self.assertTrue(
                any(
                    "cannot close a human-supervised voice-device release gate" in item
                    for item in release_report["errors"]
                )
            )
            automated_report = verify_bundle(
                root,
                allow_automated=True,
                expected_chromie_revision="abc123",
                expected_chromie_version="development",
                expected_soridormi_revision="def456",
            )
            self.assertTrue(automated_report["passed"], automated_report)
            self.assertTrue(automated_report["policy_evaluation_ready"])
            self.assertFalse(
                automated_report["human_voice_device_claim_eligible"]
            )

    def test_release_preview_creates_non_publishable_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            evidence = temp / "evidence"
            output = temp / "output"
            repo.mkdir()
            evidence.mkdir()

            (repo / "release").mkdir()
            (repo / "capabilities").mkdir()
            (repo / "VERSION").write_text("development\n")
            (repo / "release" / "development.md").write_text("# Development Scope\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "release_state": "development",
                        "chromie": {
                            "version": "development",
                            "supported_branch": "main",
                            "runtime_modes": ["soridormi-mujoco-sim"],
                        },
                        "soridormi": {
                            "upstream_commit": "soridormi-fixture",
                            "supported_mode": "sim",
                        },
                        "evidence_policy": {
                            "accepted_voice_modes": ["supervised"],
                            "human_supervised_voice_device_claim": True,
                            "soridormi_mujoco_sim_executor_required": True,
                        },
                        "known_evidence_gaps": ["confirmation pending"],
                    }
                )
            )
            (repo / "capabilities" / "soridormi.json").write_text(
                json.dumps(
                    {"metadata": {"upstream_commit": "soridormi-fixture"}}
                )
            )
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            for name in REQUIRED_FILES:
                (evidence / name).write_text("placeholder\n")
            write_cognitive_runtime_fixture(evidence)
            (evidence / "metadata.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "passed",
                        "event_count": 20,
                        "acceptance_id": "fixture",
                        "runner": {"dry_run": False, "mode": "supervised"},
                        "chromie": {
                            "revision": subprocess.check_output(
                                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                            ).strip(),
                            "version": "development",
                            "dirty": False,
                        },
                        "soridormi_manifest": {"upstream_commit": "soridormi-fixture"},
                        "soridormi_local_revision": "soridormi-fixture",
                        "soridormi_local_dirty": False,
                        "soridormi_source_binding": {
                            "kind": "endpoint_reported_revision",
                            "endpoint_revision": "soridormi-fixture",
                        },
                        "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                        "selected_cases": list(FULL_CASE_ORDER),
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
                            "session_ids": fixture_case_session_ids(index, case_id),
                            "checks": [{"name": "check", "passed": True}],
                        }
                        for index, case_id in enumerate(FULL_CASE_ORDER)
                    ]
                )
            )
            (evidence / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_CAPABILITIES=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=device\n"
                "ORCH_AUDIO_OUTPUT_MODE=device\n"
                + GOAL_DRIVEN_OVERRIDE_TEXT
            )

            args = SimpleNamespace(
                evidence_dir=str(evidence),
                output_root=str(output),
                skip_tests=True,
                allow_dirty=False,
                require_clean_evidence=True,
                allow_automated_evidence=False,
                preview=True,
                overwrite=False,
            )
            with mock.patch.object(release_module, "ROOT", repo):
                bundle = release_module.prepare_release(args)

            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertFalse(manifest["publishable"])
            self.assertTrue((bundle / "chromie-development.tar.gz").is_file())
            self.assertTrue((bundle / "build-provenance.json").is_file())
            self.assertEqual(
                manifest["artifacts"]["build_provenance"],
                "build-provenance.json",
            )
            self.assertEqual(manifest["publication_steps"], [])
            self.assertNotIn(str(evidence), json.dumps(manifest))
            self.assertNotIn(
                str(evidence),
                (bundle / "voice-acceptance-summary.md").read_text(),
            )
            self.assertTrue((bundle / "SHA256SUMS").is_file())

    def test_release_compatibility_policy_is_fail_closed(self) -> None:
        valid = {
            "schema_version": 1,
            "release_state": "development",
            "chromie": {
                "version": "development",
                "supported_branch": "main",
                "runtime_modes": ["soridormi-mujoco-sim"],
            },
            "soridormi": {
                "upstream_commit": "fixture",
                "supported_mode": "sim",
            },
            "evidence_policy": {
                "accepted_voice_modes": ["synthetic"],
                "human_supervised_voice_device_claim": False,
                "soridormi_mujoco_sim_executor_required": True,
            },
            "known_evidence_gaps": ["fixture blocker"],
        }
        release_module.validate_compatibility(valid)

        malformed = [
            {**valid, "schema_version": 2},
            {**valid, "release_state": "published"},
            {**valid, "known_evidence_gaps": "not-a-list"},
            {
                **valid,
                "chromie": {**valid["chromie"], "supported_branch": ""},
            },
            {
                **valid,
                "chromie": {**valid["chromie"], "runtime_modes": []},
            },
            {
                **valid,
                "chromie": {
                    **valid["chromie"],
                    "runtime_modes": [
                        "soridormi-mujoco-sim",
                        "soridormi-mujoco-sim",
                    ],
                },
            },
            {
                **valid,
                "soridormi": {**valid["soridormi"], "supported_mode": "hardware"},
            },
            {
                **valid,
                "evidence_policy": {
                    **valid["evidence_policy"],
                    "soridormi_mujoco_sim_executor_required": False,
                },
            },
        ]
        for payload in malformed:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    release_module.validate_compatibility(payload)

    def test_release_test_log_sanitizes_repository_and_home_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "operator-home"
            repo = home / "src" / "chromie"
            log = Path(temp_dir) / "tests.log"
            log.write_text(
                f"Traceback: {repo}/orchestrator/orchestrator.py:12\n"
                f"cache={home}/.cache/chromie\n"
                "system=/usr/lib/python3.11/unittest.py\n",
                encoding="utf-8",
            )

            release_module.sanitize_release_log(
                log,
                repository_root=repo,
                home_directory=home,
            )

            content = log.read_text(encoding="utf-8")
            self.assertNotIn(str(repo), content)
            self.assertNotIn(str(home), content)
            self.assertIn("<repo>/orchestrator/orchestrator.py:12", content)
            self.assertIn("cache=<home>/.cache/chromie", content)
            self.assertIn("system=/usr/lib/python3.11/unittest.py", content)

    def test_voice_evidence_rejects_provenance_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            write_cognitive_runtime_fixture(root)
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "passed",
                        "event_count": 40,
                        "acceptance_id": "stale",
                        "runner": {"dry_run": False, "mode": "supervised"},
                        "chromie": {
                            "revision": "old-revision",
                            "version": "0.0.0",
                            "dirty": False,
                        },
                        "soridormi_manifest": {"upstream_commit": "old-soridormi"},
                        "soridormi_local_revision": "other-soridormi",
                        "soridormi_local_dirty": False,
                        "soridormi_source_binding": {
                            "kind": "endpoint_reported_revision",
                            "endpoint_revision": "old-soridormi",
                        },
                        "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                        "selected_cases": list(FULL_CASE_ORDER),
                    }
                )
            )
            (root / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "case_id": case_id,
                            "operator_verdict": "pass",
                            "event_count": 2,
                            "session_ids": fixture_case_session_ids(index, case_id),
                            "checks": [{"name": "check", "passed": True}],
                        }
                        for index, case_id in enumerate(FULL_CASE_ORDER)
                    ]
                )
            )
            (root / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_CAPABILITIES=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
                "ORCH_AUDIO_INPUT_MODE=device\n"
                "ORCH_AUDIO_OUTPUT_MODE=device\n"
                + GOAL_DRIVEN_OVERRIDE_TEXT
            )
            report = verify_bundle(
                root,
                expected_chromie_revision="current-revision",
                expected_chromie_version="development",
                expected_soridormi_revision="current-soridormi",
            )
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["provenance_errors"]), 4)
            self.assertTrue(
                all("does not match" in item for item in report["provenance_errors"])
            )

    def test_voice_evidence_malformed_shapes_fail_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "passed",
                        "runner": [],
                        "event_count": "many",
                        "selected_cases": list(FULL_CASE_ORDER),
                        "chromie": [],
                        "soridormi_manifest": "not-an-object",
                    }
                )
            )
            (root / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "case_id": case_id,
                            "operator_verdict": "pass",
                            "event_count": "many",
                            "session_ids": [f"sid-{index}"],
                            "checks": [{"name": "fixture", "passed": True}],
                        }
                        for index, case_id in enumerate(FULL_CASE_ORDER)
                    ]
                )
            )

            report = verify_bundle(
                root,
                expected_chromie_revision="chromie",
                expected_chromie_version="development",
                expected_soridormi_revision="soridormi",
            )

            self.assertFalse(report["passed"])
            self.assertIn("metadata.json runner must be an object", report["errors"])
            self.assertIn("metadata.json chromie must be an object", report["errors"])
            self.assertIn(
                "metadata.json soridormi_manifest must be an object",
                report["errors"],
            )
            self.assertIn(
                "metadata.json reports no structured session events",
                report["errors"],
            )
            self.assertIn(
                "Case speech-only has no correlated events",
                report["errors"],
            )

            (root / "metadata.json").write_text(json.dumps([]))
            array_report = verify_bundle(
                root,
                expected_chromie_revision="chromie",
                expected_chromie_version="development",
                expected_soridormi_revision="soridormi",
            )
            self.assertFalse(array_report["passed"])
            self.assertIn(
                "metadata.json must contain an object",
                array_report["errors"],
            )

    def test_release_preview_rejects_evidence_provenance_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            evidence = Path(temp_dir) / "evidence"
            repo.mkdir()
            evidence.mkdir()
            (repo / "release").mkdir()
            (repo / "capabilities").mkdir()
            (repo / "VERSION").write_text("1.2.3\n")
            (repo / "release" / "1.2.3.md").write_text("# Development Scope\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "release_state": "release",
                        "chromie": {
                            "version": "1.2.3",
                            "supported_branch": "main",
                            "runtime_modes": ["soridormi-mujoco-sim"],
                        },
                        "soridormi": {
                            "upstream_commit": "soridormi-fixture",
                            "supported_mode": "sim",
                        },
                        "evidence_policy": {
                            "accepted_voice_modes": ["supervised"],
                            "human_supervised_voice_device_claim": True,
                            "soridormi_mujoco_sim_executor_required": True,
                        },
                        "known_evidence_gaps": [],
                    }
                )
            )
            (repo / "capabilities" / "soridormi.json").write_text(
                json.dumps(
                    {"metadata": {"upstream_commit": "soridormi-fixture"}}
                )
            )
            subprocess.run(
                ["git", "init"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo, check=True
            )
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "fixture"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            args = SimpleNamespace(
                evidence_dir=str(evidence),
                output_root=str(Path(temp_dir) / "output"),
                skip_tests=True,
                allow_dirty=False,
                require_clean_evidence=False,
                allow_automated_evidence=False,
                preview=True,
                overwrite=False,
            )
            report = {
                "passed": False,
                "errors": ["stale source"],
                "provenance_errors": ["stale source"],
            }
            with (
                mock.patch.object(release_module, "ROOT", repo),
                mock.patch.object(release_module, "verify_bundle", return_value=report),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "provenance does not match"
                ):
                    release_module.prepare_release(args)

    def test_release_rejects_compatibility_manifest_revision_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "release").mkdir()
            (repo / "capabilities").mkdir()
            (repo / "VERSION").write_text("1.2.3\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "release_state": "candidate",
                        "chromie": {
                            "version": "1.2.3",
                            "supported_branch": "main",
                            "runtime_modes": ["soridormi-mujoco-sim"],
                        },
                        "soridormi": {
                            "upstream_commit": "compatibility-revision",
                            "supported_mode": "sim",
                        },
                        "evidence_policy": {
                            "accepted_voice_modes": ["supervised"],
                            "human_supervised_voice_device_claim": True,
                            "soridormi_mujoco_sim_executor_required": True,
                        },
                        "known_evidence_gaps": ["fixture blocker"],
                    }
                )
            )
            (repo / "capabilities" / "soridormi.json").write_text(
                json.dumps(
                    {"metadata": {"upstream_commit": "manifest-revision"}}
                )
            )
            with mock.patch.object(release_module, "ROOT", repo):
                with self.assertRaisesRegex(
                    ValueError, "does not match the capability manifest"
                ):
                    release_module.prepare_release(SimpleNamespace())

    def test_release_rejects_a_branch_outside_compatibility_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "release").mkdir()
            (repo / "capabilities").mkdir()
            (repo / "VERSION").write_text("1.2.3\n")
            (repo / "release" / "1.2.3.md").write_text("# Development Scope\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "release_state": "release",
                        "chromie": {
                            "version": "1.2.3",
                            "supported_branch": "main",
                            "runtime_modes": ["soridormi-mujoco-sim"],
                        },
                        "soridormi": {
                            "upstream_commit": "soridormi-fixture",
                            "supported_mode": "sim",
                        },
                        "evidence_policy": {
                            "accepted_voice_modes": ["supervised"],
                            "human_supervised_voice_device_claim": True,
                            "soridormi_mujoco_sim_executor_required": True,
                        },
                        "known_evidence_gaps": [],
                    }
                )
            )
            (repo / "capabilities" / "soridormi.json").write_text(
                json.dumps(
                    {"metadata": {"upstream_commit": "soridormi-fixture"}}
                )
            )
            subprocess.run(
                ["git", "init"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "fixture"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "checkout", "-b", "feature"],
                cwd=repo,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with mock.patch.object(release_module, "ROOT", repo):
                with self.assertRaisesRegex(RuntimeError, "requires branch 'main'"):
                    release_module.prepare_release(
                        SimpleNamespace(preview=False)
                    )

    def test_dry_run_evidence_cannot_close_text_to_mujoco_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            write_cognitive_runtime_fixture(root)
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "status": "dry-run",
                        "event_count": 0,
                        "runner": {"dry_run": True, "mode": "supervised"},
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
