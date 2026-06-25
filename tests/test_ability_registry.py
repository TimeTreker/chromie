from __future__ import annotations

import unittest

from orchestrator.runtime.abilities import (
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

    def test_thinking_pose_is_sim_only_when_safe_sim_cues_are_enabled(self) -> None:
        registry = build_default_ability_registry(
            enable_interaction_response=True,
            enable_soridormi_skills=True,
            auto_confirm_sim_skills=True,
            action_dry_run=True,
        )
        ability = registry.get("social.thinking_pose")

        self.assertEqual(ability.status, "sim_only")
        self.assertTrue(ability.can_execute)
        self.assertEqual(ability.soridormi_skill_id, "soridormi.express_attention")
        self.assertEqual(
            dict(ability.default_args),
            {
                "style": "neutral",
                "duration_s": 2.4,
                "hold_fraction": 0.35,
            },
        )

    def test_thinking_pose_is_stub_outside_safe_sim_mode(self) -> None:
        registry = build_default_ability_registry(
            enable_interaction_response=True,
            enable_soridormi_skills=True,
            auto_confirm_sim_skills=True,
            action_dry_run=False,
        )
        ability = registry.get("social.thinking_pose")

        self.assertEqual(ability.status, "stub")
        self.assertFalse(ability.can_execute)
        self.assertIsNone(ability.soridormi_skill_id)

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
