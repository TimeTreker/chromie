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
                },
            )

        self.assertTrue(settings.cognition.enable_agent)
        self.assertEqual(settings.cognition.apply_lanes, frozenset({"chat", "tool"}))
        self.assertEqual(settings.playback.concurrency, 2)
        self.assertEqual(settings.playback.fast_audio_cache_dir, root / "cache/audio")
        self.assertEqual(settings.evidence.recordings_dir, root / "captures")
        with self.assertRaises(Exception):
            settings.playback.concurrency = 3  # type: ignore[misc]


    def test_model_generation_settings_are_typed_once(self) -> None:
        settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={
                "OLLAMA_KEEP_ALIVE": "8h",
                "OLLAMA_NUM_CTX": "4096",
                "OLLAMA_NUM_PREDICT": "128",
                "OLLAMA_TEMPERATURE": "0.25",
                "OLLAMA_TOP_P": "0.8",
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "2.5",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "1024",
                "ORCH_DIRECT_LLM_REQUIRE_COMPLETE_OUTPUT": "false",
                "AGENT_RESPONSE_COMPOSER_NUM_CTX": "12288",
                "AGENT_RESPONSE_COMPOSER_NUM_PREDICT": "512",
                "AGENT_RESPONSE_COMPOSER_TIMEOUT_MS": "7000",
                "AGENT_FAST_PLANNER_MODEL": "fast-model",
                "AGENT_FAST_PLANNER_NUM_CTX": "6144",
            },
        )

        model = settings.model_generation
        self.assertEqual(model.keep_alive, "8h")
        self.assertEqual(model.direct_num_ctx, 4096)
        self.assertEqual(model.direct_num_predict, 128)
        self.assertEqual(model.direct_temperature, 0.25)
        self.assertEqual(model.direct_top_p, 0.8)
        self.assertEqual(model.prompt_chars_per_token_estimate, 2.5)
        self.assertEqual(model.context_safety_margin_tokens, 1024)
        self.assertFalse(model.direct_require_complete_output)
        self.assertEqual(model.failure_response_num_ctx, 12288)
        self.assertEqual(model.failure_response_num_predict, 512)
        self.assertEqual(model.failure_response_timeout_ms, 7000)
        self.assertEqual(model.ready_greeting_fallback_model, "fast-model")
        self.assertEqual(model.ready_greeting_num_ctx, 6144)


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
                    "ORCH_SKILL_MAX_CONCURRENCY": "5",
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
        self.assertEqual(settings.interaction.skill_max_concurrency, 5)
        self.assertEqual(settings.telemetry.system_resource_mode, "session")
        self.assertEqual(settings.telemetry.accelerator_provider, "off")
        self.assertEqual(settings.cognition.task_graph_execution_token, "secret")
        self.assertEqual(settings.session.event_log_path, root / "evidence/events.jsonl")

    def test_optional_device_rates_preserve_system_defaults(self) -> None:
        settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={},
        )
        self.assertIsNone(settings.audio_device.input_rate)
        self.assertIsNone(settings.audio_device.output_rate)

    def test_invalid_model_generation_value_names_owning_environment_variable(self) -> None:
        with self.assertRaisesRegex(
            HostConfigurationError,
            "OLLAMA_TOP_P must be <= 1.0",
        ):
            HostSettingsSnapshot.from_env(
                project_root=Path("/tmp"),
                environ={"OLLAMA_TOP_P": "1.5"},
            )

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
