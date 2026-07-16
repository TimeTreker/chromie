from __future__ import annotations

import unittest

from scripts.test_matrix import COMBOS, GROUPS, expand


class TestMatrixCoverageTests(unittest.TestCase):
    def test_general_ability_group_runs_complete_level_a_manifest(self) -> None:
        commands = GROUPS["general-ability"].commands
        level_a = next(command for command in commands if "level-a" in command)
        self.assertNotIn("--ability-class", level_a)

    def test_local_combinations_include_cognitive_runtime(self) -> None:
        self.assertIn("cognitive-runtime", COMBOS["local-modules"])
        self.assertIn("cognitive-runtime", COMBOS["voice-mujoco-sim"])
        self.assertIn("cognitive-runtime", expand(["local-modules"]))

    def test_release_group_covers_automatic_profile_generation(self) -> None:
        rendered = " ".join(
            part
            for command in GROUPS["release"].commands
            for part in command
        )
        self.assertIn("tests.test_auto_profile_env_pipeline", rendered)


if __name__ == "__main__":
    unittest.main()
