from __future__ import annotations

import unittest

from typing import get_args

from orchestrator.runtime.abilities import (
    AbilityStatus,
    DEFAULT_UNAVAILABLE_EN,
    DEFAULT_UNAVAILABLE_ZH,
    build_default_ability_registry,
)


class AbilityRegistryTests(unittest.TestCase):
    def test_registry_contains_normal_human_like_categories(self) -> None:
        registry = build_default_ability_registry()
        categories = {ability.category for ability in registry.list()}

        self.assertGreaterEqual(len(registry.list()), 40)
        self.assertTrue(
            {
                "cognition",
                "speech",
                "memory",
                "social",
                "body",
                "task",
                "safety",
                "state",
                "manipulation",
                "navigation",
                "environment",
            }.issubset(categories)
        )

    def test_thinking_ack_is_available_and_language_matched(self) -> None:
        registry = build_default_ability_registry()

        self.assertTrue(registry.can_execute("speech.thinking_ack"))
        self.assertEqual(
            registry.localized_speech(
                "speech.thinking_ack",
                language="en-US",
            ),
            "Okay, let me think about that.",
        )
        self.assertEqual(
            registry.localized_speech(
                "speech.thinking_ack",
                user_text="请认真想一下。",
            ),
            "好的，我想一下。",
        )

    def test_static_registry_has_no_backend_specific_statuses(self) -> None:
        registry = build_default_ability_registry()
        statuses = {ability.status for ability in registry.list()}

        legacy_sim_status = "sim" + "_only"
        legacy_hardware_status = "hardware" + "_only"
        self.assertNotIn(legacy_sim_status, get_args(AbilityStatus))
        self.assertNotIn(legacy_hardware_status, get_args(AbilityStatus))
        self.assertNotIn(legacy_sim_status, statuses)
        self.assertNotIn(legacy_hardware_status, statuses)

    def test_static_registry_does_not_define_host_thinking_gestures(self) -> None:
        registry = build_default_ability_registry()
        fixed_thinking_ability = "social.thinking" + "_pose"

        with self.assertRaisesRegex(ValueError, "unknown ability"):
            registry.get(fixed_thinking_ability)

    def test_known_missing_human_like_ability_is_not_executable(self) -> None:
        registry = build_default_ability_registry()
        ability = registry.get("social.blink_eyes")

        self.assertEqual(ability.status, "known_missing")
        self.assertFalse(ability.can_execute)
        self.assertIsNone(ability.soridormi_skill_id)
        self.assertIn("don't have an executable eye-blink skill", ability.unavailable_en)

    def test_unavailable_message_is_language_matched(self) -> None:
        registry = build_default_ability_registry()

        self.assertEqual(
            registry.unavailable_message("social.look_at_user", language="en-US"),
            DEFAULT_UNAVAILABLE_EN,
        )
        self.assertEqual(
            registry.unavailable_message("social.look_at_user", user_text="看着我"),
            DEFAULT_UNAVAILABLE_ZH,
        )


if __name__ == "__main__":
    unittest.main()
