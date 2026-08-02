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
