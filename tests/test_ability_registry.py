from __future__ import annotations

import unittest

from typing import get_args

from orchestrator.runtime.abilities import (
    AbilityStatus,
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

    def test_thinking_ack_is_model_authored_not_template_authored(self) -> None:
        registry = build_default_ability_registry()

        ability = registry.get("speech.thinking_ack")
        self.assertTrue(ability.can_execute)
        self.assertEqual(ability.implementation, "model_authored_speech")
        self.assertFalse(hasattr(ability, "speech_templates"))

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
        self.assertFalse(hasattr(ability, "soridormi_skill_id"))
        self.assertFalse(hasattr(ability, "unavailable_en"))
        self.assertFalse(hasattr(ability, "unavailable_zh"))


if __name__ == "__main__":
    unittest.main()
