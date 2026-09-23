from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from benchmarks.contracts import ContractError
from benchmarks.regression.archive import restore_frozen_corpus

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


class FrozenCorpusStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.corpus = self.repo / "frozen"
        (self.corpus / "artifacts").mkdir(parents=True)
        self.case = b'{"id":"frozen-example","expected":"unchanged"}\n'
        self.part = b'{"schema":"frozen"}\n'
        self.part_name = hashlib.sha256(self.part).hexdigest() + ".json"
        (self.corpus / "workflow-example.json").write_bytes(self.case)
        (self.corpus / "artifacts" / self.part_name).write_bytes(self.part)
        self.manifest = {"count": 1, "case_sha256": {"workflow-example.json": hashlib.sha256(self.case).hexdigest()},
                         "artifact_sha256": {self.part_name: hashlib.sha256(self.part).hexdigest()}}
        raw = json.dumps(self.manifest).encode()
        (self.corpus / "manifest.json").write_bytes(raw)
        self.commit()
        revision = self.git("rev-parse", "HEAD").strip()
        self.manifest["storage"] = {"git_revision": revision, "git_path": "frozen",
                                    "manifest_sha256": hashlib.sha256(raw).hexdigest()}
        (self.corpus / "workflow-example.json").unlink()
        (self.corpus / "artifacts" / self.part_name).unlink()
        (self.corpus / "manifest.json").write_text(json.dumps(self.manifest))

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True,
                                       stderr=subprocess.PIPE)

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                 "commit", "-qm", "Frozen test fixture")

    def test_restores_exact_bytes_without_changing_revision_and_reuses_verified_cache(self):
        before = self.git("rev-parse", "HEAD")
        result = restore_frozen_corpus(self.corpus, repo_root=self.repo)
        self.assertEqual(result["restored"], 2)
        self.assertEqual((self.corpus / "workflow-example.json").read_bytes(), self.case)
        self.assertEqual((self.corpus / "artifacts" / self.part_name).read_bytes(), self.part)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(restore_frozen_corpus(self.corpus, repo_root=self.repo)["restored"], 0)

    def test_changed_existing_input_is_not_silently_repaired(self):
        path = self.corpus / "workflow-example.json"
        path.write_text("tampered")
        with self.assertRaisesRegex(ContractError, "refusing to overwrite"):
            restore_frozen_corpus(self.corpus, repo_root=self.repo)
        self.assertEqual(path.read_text(), "tampered")

    def test_archive_mismatch_publishes_no_partial_inputs(self):
        self.manifest["artifact_sha256"][self.part_name] = "0" * 64
        (self.corpus / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ContractError, "archive hash mismatch"):
            restore_frozen_corpus(self.corpus, repo_root=self.repo)
        self.assertFalse((self.corpus / "workflow-example.json").exists())

    def test_partial_cache_restores_only_missing_inputs(self):
        (self.corpus / "workflow-example.json").write_bytes(self.case)
        self.assertEqual(restore_frozen_corpus(self.corpus, repo_root=self.repo)["restored"], 1)

    def test_undeclared_case_is_not_silently_omitted(self):
        (self.corpus / "workflow-extra.json").write_text("{}")
        with self.assertRaisesRegex(ContractError, "unexpected frozen corpus"):
            restore_frozen_corpus(self.corpus, repo_root=self.repo)

    def test_existing_cache_cannot_hide_missing_freeze_source(self):
        restore_frozen_corpus(self.corpus, repo_root=self.repo)
        self.manifest.pop("storage")
        (self.corpus / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ContractError, "source identity"):
            restore_frozen_corpus(self.corpus, repo_root=self.repo)

    def test_manifest_cannot_escape_corpus_directory(self):
        self.manifest["case_sha256"] = {"../outside.json": "0" * 64}
        (self.corpus / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ContractError, "invalid frozen corpus entry"):
            restore_frozen_corpus(self.corpus, repo_root=self.repo)

    def test_shallow_clone_fetch_is_explicit_and_preserves_checkout(self):
        self.commit()
        clone = Path(self.temp.name) / "shallow"
        subprocess.run(["git", "clone", "--depth=1", self.repo.as_uri(), str(clone)],
                       check=True, capture_output=True)
        head = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"])
        with self.assertRaisesRegex(ContractError, "--fetch once"):
            restore_frozen_corpus(clone / "frozen", repo_root=clone)
        result = restore_frozen_corpus(clone / "frozen", repo_root=clone, fetch=True)
        self.assertEqual(result["restored"], 2)
        self.assertEqual(subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"]), head)


if __name__ == "__main__":
    unittest.main()
