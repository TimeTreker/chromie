from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_docs
from scripts.check_docs import (
    ABANDONED_RELEASE_VERSION_RE,
    MILESTONE_TOKEN_RE,
    NUMBERED_PHASE_PATH_RE,
    NUMBERED_STEP_TOKEN_RE,
)


class SemanticProjectNamingTests(unittest.TestCase):
    def test_numbered_milestone_token_is_rejected(self) -> None:
        token = "M" + "13"
        self.assertIsNotNone(MILESTONE_TOKEN_RE.search(f"historical {token} evidence"))

    def test_numbered_implementation_stage_is_rejected(self) -> None:
        token = "Step" + " 7"
        self.assertIsNotNone(
            NUMBERED_STEP_TOKEN_RE.search(f"continue with {token} work")
        )

    def test_compact_numbered_implementation_stage_is_rejected(self) -> None:
        token = "STEP" + "10"
        self.assertIsNotNone(
            NUMBERED_STEP_TOKEN_RE.search(f"legacy {token} document")
        )

    def test_embedded_technical_identifiers_are_not_project_phases(self) -> None:
        text = "PCM16 audio on ARM64 with protocol v1"
        self.assertIsNone(MILESTONE_TOKEN_RE.search(text))
        self.assertIsNone(NUMBERED_STEP_TOKEN_RE.search(text))

    def test_numbered_phase_path_is_rejected(self) -> None:
        path = "tests/test_" + "m" + "5_target_acceptance.py"
        self.assertIsNotNone(NUMBERED_PHASE_PATH_RE.search(path))

    def test_numbered_step_path_is_rejected(self) -> None:
        path = "docs/" + "step" + "10_accelerator_evidence.md"
        self.assertIsNotNone(NUMBERED_PHASE_PATH_RE.search(path))

    def test_pull_request_stage_review_and_phase_paths_are_rejected(self) -> None:
        for token in ("pr" + "7", "stage" + "4", "r" + "4", "PSM-" + "2", "phase_" + "3", "m" + "13"):
            with self.subTest(token=token):
                path = f"tests/test_cognitive_runtime_{token}_guard.py"
                self.assertIsNotNone(NUMBERED_PHASE_PATH_RE.search(path))

    def test_model_and_hardware_identifiers_are_not_numbered_paths(self) -> None:
        for path in (
            "tts_candidates/qwen3/Dockerfile",
            "env/profiles/sglang_rtx4090_laptop.env",
            "benchmarks/manifests/goal_interpreter_primary_v2.json",
            "docker-compose.sglang-rtx4090-laptop.yml",
            "tests/test_prompt_generalization_guards.py",
            "tests/test_ollama_warmup_script.py",
        ):
            with self.subTest(path=path):
                self.assertIsNone(NUMBERED_PHASE_PATH_RE.search(path))

    def test_abandoned_fixed_release_version_is_rejected(self) -> None:
        version = "0." + "0.1"
        self.assertIsNotNone(ABANDONED_RELEASE_VERSION_RE.search(version))

    def test_loopback_address_is_not_a_release_version(self) -> None:
        self.assertIsNone(
            ABANDONED_RELEASE_VERSION_RE.search("http://127.0.0.1:8091")
        )

    def test_semantic_paths_are_allowed(self) -> None:
        self.assertIsNone(
            NUMBERED_PHASE_PATH_RE.search(
                "tests/test_supervised_target_acceptance.py"
            )
        )


class MarkdownAnchorLinkTests(unittest.TestCase):
    def test_heading_slug_matches_github_rules(self) -> None:
        self.assertEqual(check_docs.heading_slug("Current `gate` (B/D) status"), "current-gate-bd-status")
        self.assertEqual(check_docs.heading_slug("当前 状态"), "当前-状态")

    def test_missing_and_present_anchors_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "TARGET.md").write_text("# Target\n\n## Open work\n\n## Open work\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[ok](TARGET.md#open-work) [dup](TARGET.md#open-work-1) [self](#readme)\n"
                "# Readme\n[bad](TARGET.md#closed-work) [badself](#nothing)\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            with (
                mock.patch.object(check_docs, "ROOT", root),
                mock.patch.object(check_docs, "_ANCHOR_CACHE", {}),
            ):
                check_docs.check_local_links(errors)
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("TARGET.md#closed-work", errors[0])
        self.assertIn("#nothing", errors[1])


if __name__ == "__main__":
    unittest.main()
