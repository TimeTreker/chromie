from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeReliabilityStage4Tests(unittest.TestCase):
    def test_warmup_uses_a_one_token_non_thinking_generation(self) -> None:
        source = Path("scripts/warm_ollama.sh").read_text(encoding="utf-8")

        self.assertIn('NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"', source)
        self.assertIn('"think": False', source)


if __name__ == "__main__":
    unittest.main()
