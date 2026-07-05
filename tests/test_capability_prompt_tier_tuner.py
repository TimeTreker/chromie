from __future__ import annotations

import unittest

from scripts.tune_capability_prompt_tiers import build_prompt_tier_overlay


class CapabilityPromptTierTunerTests(unittest.TestCase):
    def test_promotes_frequently_successful_unlocked_skill(self) -> None:
        overlay, audit = build_prompt_tier_overlay(
            experience_records=[
                {
                    "selected_skills": ["soridormi.blink_eyes"],
                    "execution_status": "success",
                    "skill_results": [
                        {"skill_id": "soridormi.blink_eyes", "status": "success"}
                    ],
                },
                {
                    "selected_skills": ["soridormi.blink_eyes"],
                    "execution_status": "success",
                    "skill_results": [
                        {"skill_id": "soridormi.blink_eyes", "status": "success"}
                    ],
                },
                {
                    "selected_skills": ["soridormi.blink_eyes"],
                    "execution_status": "success",
                    "skill_results": [
                        {"skill_id": "soridormi.blink_eyes", "status": "success"}
                    ],
                },
            ],
            catalog={
                "soridormi.blink_eyes": {
                    "capability_id": "soridormi.blink_eyes",
                    "prompt_tier": "rare",
                    "prompt_tier_locked": False,
                }
            },
            promote_count=3,
            demote_count=0,
            min_success_rate=0.8,
            minimum_demotion_records=20,
        )

        self.assertEqual(
            overlay["prompt_tiers"]["soridormi.blink_eyes"]["prompt_tier"],
            "common",
        )
        self.assertEqual(overlay["prompt_tiers"]["soridormi.blink_eyes"]["source"], "experience")
        self.assertEqual(audit[0]["event"], "capability_prompt_tier_candidate")

    def test_skips_locked_safety_sensitive_skill(self) -> None:
        overlay, audit = build_prompt_tier_overlay(
            experience_records=[
                {
                    "selected_skills": ["soridormi.motion.calibrate_floor"],
                    "execution_status": "success",
                    "skill_results": [
                        {
                            "skill_id": "soridormi.motion.calibrate_floor",
                            "status": "success",
                        }
                    ],
                },
                {
                    "selected_skills": ["soridormi.motion.calibrate_floor"],
                    "execution_status": "success",
                    "skill_results": [
                        {
                            "skill_id": "soridormi.motion.calibrate_floor",
                            "status": "success",
                        }
                    ],
                },
            ],
            catalog={
                "soridormi.motion.calibrate_floor": {
                    "capability_id": "soridormi.motion.calibrate_floor",
                    "prompt_tier": "rare",
                    "prompt_tier_locked": True,
                }
            },
            promote_count=2,
            demote_count=0,
            min_success_rate=0.5,
            minimum_demotion_records=20,
        )

        self.assertEqual(overlay["prompt_tiers"], {})
        self.assertEqual(audit[0]["event"], "capability_prompt_tier_locked_skip")


if __name__ == "__main__":
    unittest.main()
