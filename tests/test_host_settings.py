from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.host_settings import (
    HostConfigurationError,
    HostSettingsSnapshot,
)


class HostSettingsSnapshotTests(unittest.TestCase):
    def test_groups_are_typed_immutable_and_paths_are_rooted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = HostSettingsSnapshot.from_env(
                project_root=root,
                environ={
                    "ORCH_ENABLE_AGENT": "true",
                    "ORCH_COGNITIVE_APPLY_LANES": "chat,tool",
                    "ORCH_TTS_CONCURRENCY": "2",
                    "ORCH_FAST_FIRST_AUDIO_CACHE_DIR": "cache/audio",
                    "RECORDINGS_DIR": "captures",
                    "ORCH_DATA_LOOP_INTERACTION_SESSION_CAPTURE_POLICY_PATH": "policies/session.json",
                    "CHROMIE_RUNTIME_EVENT_ROOT": "events",
                    "CHROMIE_DATA_LOOP_TRIGGER_ROOT": "data-loop-inbox",
                },
            )

        self.assertTrue(settings.cognition.enable_agent)
        self.assertEqual(settings.cognition.apply_lanes, frozenset({"chat", "tool"}))
        self.assertEqual(settings.playback.concurrency, 2)
        self.assertEqual(settings.playback.fast_audio_cache_dir, root / "cache/audio")
        self.assertEqual(settings.evidence.recordings_dir, root / "captures")
        self.assertEqual(
            settings.evidence.interaction_session_capture_policy_path,
            root / "policies/session.json",
        )
        self.assertEqual(settings.evidence.runtime_event_root, root / "events")
        self.assertEqual(
            settings.evidence.data_loop_trigger_root,
            root / "data-loop-inbox",
        )
        with self.assertRaises(Exception):
            settings.playback.concurrency = 3  # type: ignore[misc]


    def test_model_generation_settings_are_typed_once(self) -> None:
        settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={
                "OLLAMA_KEEP_ALIVE": "8h",
                "OLLAMA_NUM_CTX": "4096",
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "2.5",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "1024",
                "AGENT_FAST_PLANNER_MODEL": "fast-model",
                "AGENT_FAST_PLANNER_NUM_CTX": "12288",
                "AGENT_FAST_PLANNER_NUM_PREDICT": "512",
                "AGENT_FAST_PLANNER_TIMEOUT_MS": "7000",
            },
        )

        model = settings.model_generation
        self.assertEqual(model.keep_alive, "8h")
        self.assertEqual(model.prompt_chars_per_token_estimate, 2.5)
        self.assertEqual(model.context_safety_margin_tokens, 1024)
        self.assertEqual(model.ready_greeting_fallback_model, "fast-model")
        self.assertEqual(model.ready_greeting_num_ctx, 12288)


    def test_extended_host_collaborator_settings_are_typed_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = HostSettingsSnapshot.from_env(
                project_root=root,
                environ={
                    "ORCH_INPUT_DEVICE": "7",
                    "ORCH_OUTPUT_DEVICE": "USB speaker",
                    "ORCH_INPUT_RATE": "48000",
                    "ORCH_CONVERSATION_ID": "family",
                    "ORCH_CONVERSATION_MAX_TURNS": "16",
                    "ORCH_MIND_CONTEXT_MAX_CHARS": "2200",
                    "ORCH_ENABLE_EXPERIENCE_JOURNAL": "false",
                    "ORCH_EPISODE_MAX_TURNS": "20",
                    "ORCH_CAPABILITY_MAX_CONCURRENCY": "5",
                    "CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING": "session",
                    "CHROMIE_RUNTIME_TRACE_ACCELERATOR_PROVIDER": "off",
                    "AGENT_TASK_GRAPH_EXECUTION_TOKEN": "secret",
                    "ORCH_EVENT_LOG_PATH": "evidence/events.jsonl",
                },
            )

        self.assertEqual(settings.audio_device.input_device, 7)
        self.assertEqual(settings.audio_device.output_device, "USB speaker")
        self.assertEqual(settings.audio_device.input_rate, 48000)
        self.assertEqual(settings.conversation.base_conversation_id, "family")
        self.assertEqual(settings.conversation.max_turns, 16)
        self.assertEqual(settings.mind.context_max_chars, 2200)
        self.assertFalse(settings.experience.enabled)
        self.assertEqual(settings.episode.max_turns, 20)
        self.assertEqual(settings.capability_runtime.capability_max_concurrency, 5)
        self.assertEqual(settings.telemetry.system_resource_mode, "session")
        self.assertEqual(settings.telemetry.accelerator_provider, "off")
        self.assertEqual(settings.cognition.task_graph_execution_token, "secret")
        self.assertEqual(settings.session.event_log_path, root / "evidence/events.jsonl")

    def test_legacy_skill_concurrency_key_is_not_a_compatibility_alias(self) -> None:
        settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={"ORCH_SKILL_MAX_CONCURRENCY": "2"},
        )
        self.assertEqual(settings.capability_runtime.capability_max_concurrency, 8)

    def test_optional_device_rates_preserve_system_defaults(self) -> None:
        settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={},
        )
        self.assertIsNone(settings.audio_device.input_rate)
        self.assertIsNone(settings.audio_device.output_rate)


    def test_invalid_boolean_names_owning_environment_variable(self) -> None:
        with self.assertRaisesRegex(
            HostConfigurationError,
            "ORCH_ENABLE_AGENT must be a boolean",
        ):
            HostSettingsSnapshot.from_env(
                project_root=Path("/tmp"),
                environ={"ORCH_ENABLE_AGENT": "maybe"},
            )

    def test_invalid_choice_fails_closed_instead_of_silent_default(self) -> None:
        with self.assertRaisesRegex(
            HostConfigurationError,
            "ORCH_AUDIO_OUTPUT_MODE must be one of",
        ):
            HostSettingsSnapshot.from_env(
                project_root=Path("/tmp"),
                environ={"ORCH_AUDIO_OUTPUT_MODE": "speaker-ish"},
            )

    def test_empty_apply_lane_set_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            HostConfigurationError,
            "ORCH_COGNITIVE_APPLY_LANES must contain at least one lane",
        ):
            HostSettingsSnapshot.from_env(
                project_root=Path("/tmp"),
                environ={"ORCH_COGNITIVE_APPLY_LANES": " , "},
            )
