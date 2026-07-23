from __future__ import annotations

import unittest

from scripts.check_docs import (
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

    def test_semantic_paths_are_allowed(self) -> None:
        self.assertIsNone(
            NUMBERED_PHASE_PATH_RE.search(
                "tests/test_supervised_target_acceptance.py"
            )
        )


if __name__ == "__main__":
    unittest.main()
