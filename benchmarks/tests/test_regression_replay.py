from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.regression.replay import (
    ReplayScenario,
    load_replay_scenario,
    minimize_turns,
    replay_manifest,
)
from scripts.closed_loop_e2e import build_parser


class RegressionReplayTests(unittest.TestCase):
    def test_loads_exact_scenario_from_retained_review_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = {
                "scenarios": [
                    {
                        "scenario_id": "memory",
                        "scenario": {
                            "inputs": {
                                "turns": ["Remember blue.", "What color?"],
                                "language": "en-US",
                            },
                            "expectations": {"primary_outcomes": ["Recall blue"]},
                            "oracle_policy": {
                                "mode": "hybrid",
                                "deterministic_sources": ["turn_completion"],
                                "semantic_dimensions": ["memory_recall"],
                            },
                            "review_rubric": {"dimensions": ["memory_recall"]},
                        },
                    }
                ]
            }
            (root / "semantic-review-bundle.json").write_text(
                json.dumps(bundle), encoding="utf-8"
            )
            scenario = load_replay_scenario(root, "memory")
            self.assertEqual(scenario.turns, ("Remember blue.", "What color?"))
            manifest = replay_manifest(scenario)
            self.assertEqual(manifest["workflow_cases"][0]["speaker_id"], "chromie_en")

    def test_delta_debugging_removes_irrelevant_turns_without_semantic_rules(self) -> None:
        turns = ("setup", "remember blue", "noise", "what color")

        def reproduces(candidate: tuple[str, ...]) -> bool:
            return "remember blue" in candidate and "what color" in candidate

        minimized = minimize_turns(turns, reproduces)
        self.assertEqual(minimized, ("remember blue", "what color"))

    def test_closed_loop_parser_accepts_repeatable_case_filter(self) -> None:
        args = build_parser().parse_args(["--case", "one", "--case", "two"])
        self.assertEqual(args.case, ["one", "two"])

    def test_replay_scenario_rejects_empty_reduction(self) -> None:
        scenario = ReplayScenario(
            scenario_id="x",
            language="en-US",
            turns=("one",),
            primary_outcomes=(),
            oracle_policy={"mode": "deterministic", "deterministic_sources": ["x"], "semantic_dimensions": []},
            review_rubric={},
        )
        with self.assertRaises(Exception):
            scenario.with_turns([])


if __name__ == "__main__":
    unittest.main()
