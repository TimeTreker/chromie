from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.test_matrix import COMBOS, GROUPS, expand


class TestMatrixCoverageTests(unittest.TestCase):
    def test_general_ability_group_runs_complete_level_a_library(self) -> None:
        commands = GROUPS["general-ability"].commands
        level_a = next(command for command in commands if "level-a" in command)
        self.assertNotIn("--ability-class", level_a)

    def test_general_ability_group_checks_the_everyday_live_library(self) -> None:
        commands = GROUPS["general-ability"].commands
        self.assertIn(
            ("--mode", "check", "--no-write", "--scenario-root", "scenarios/everyday"),
            [tuple(command[2:]) for command in commands],
        )

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

    def test_every_listed_test_module_and_script_exists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        missing = []
        for name, group in GROUPS.items():
            for command in group.commands:
                for part in command:
                    if part.startswith("tests.test_"):
                        target = root / (part.replace(".", "/") + ".py")
                    elif part.startswith(("scripts/", "./scripts/")):
                        target = root / part.removeprefix("./")
                    else:
                        continue
                    if not target.is_file():
                        missing.append(f"{name}: {part}")
                for path in re.findall(r"agent/tests/[A-Za-z0-9_]+\.py", " ".join(command)):
                    if not (root / path).is_file():
                        missing.append(f"{name}: {path}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
