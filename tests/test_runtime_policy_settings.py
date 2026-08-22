from __future__ import annotations

import unittest
from pathlib import Path

from shared.chromie_runtime.settings import RuntimePolicySettings


class RuntimePolicySettingsTests(unittest.TestCase):
    def test_typed_runtime_policy_parsing(self) -> None:
        settings = RuntimePolicySettings.from_env(
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "debug",
                "CHROMIE_RUNTIME_TRACE_MODULES": "a,b",
                "CHROMIE_RUNTIME_TRACE_MAX_ITEMS": "24",
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE": "0.25",
                "CHROMIE_RUNTIME_TRACE_RESOURCE_SAMPLING": "session",
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_PROVIDER": "nvidia_smi",
                "CHROMIE_RUNTIME_EVENT_ROOT": "~/events",
            }
        )
        self.assertEqual(settings.trace_mode, "debug")
        self.assertEqual(settings.trace_modules, frozenset({"a", "b"}))
        self.assertEqual(settings.trace_max_items, 24)
        self.assertEqual(settings.trace_event_sample_rate, 0.25)
        self.assertEqual(settings.resource_sampling_mode, "session")
        self.assertEqual(settings.accelerator_provider, "nvidia_smi")
        self.assertEqual(
            settings.configured_path(None, "runtime_event_root"),
            Path("~/events").expanduser().resolve(),
        )

    def test_retired_event_root_alias_is_ignored(self) -> None:
        settings = RuntimePolicySettings.from_env(
            {"CHROMIE_EVENT_ROOT": "~/legacy-events"}
        )
        self.assertIsNone(settings.configured_path(None, "runtime_event_root"))
        self.assertFalse(hasattr(settings, "legacy_event_root"))

    def test_invalid_values_fall_back_to_bounded_policy(self) -> None:
        settings = RuntimePolicySettings.from_env(
            {
                "CHROMIE_RUNTIME_TRACE_MODE": "unknown",
                "CHROMIE_RUNTIME_TRACE_MAX_ITEMS": "bad",
                "CHROMIE_RUNTIME_TRACE_EVENT_SAMPLE_RATE": "9",
                "CHROMIE_RUNTIME_TRACE_ACCELERATOR_TIMEOUT_MS": "1",
            }
        )
        self.assertEqual(settings.trace_mode, "off")
        self.assertEqual(settings.trace_max_items, 1000)
        self.assertEqual(settings.trace_event_sample_rate, 1.0)
        self.assertEqual(settings.accelerator_timeout_ms, 50)


if __name__ == "__main__":
    unittest.main()
