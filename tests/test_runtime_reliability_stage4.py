from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeReliabilityStage4Tests(unittest.TestCase):
    def test_warmup_uses_a_one_token_non_thinking_generation(self) -> None:
        source = Path("scripts/warm_ollama.sh").read_text(encoding="utf-8")

        self.assertIn('NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"', source)
        self.assertIn('"think": False', source)
        self.assertIn('OLLAMA_REQUIRE_ALL_WARM_MODELS_RESIDENT', source)
        self.assertIn('${OLLAMA_URL}/api/ps', source)
        self.assertIn('Concurrent residency verified for all selected models.', source)
        self.assertIn('context_for_model()', source)
        self.assertIn('model_num_ctx="$(context_for_model "$model")"', source)
        self.assertIn('"AGENT_GOAL_ASSOCIATION_MODEL", "AGENT_GOAL_ASSOCIATION_NUM_CTX"', source)
        self.assertIn('"AGENT_DEEP_PLANNER_MODEL", "AGENT_DEEP_PLANNER_NUM_CTX"', source)
        self.assertIn('"$model" "$KEEP_ALIVE" "$model_num_ctx" "$NUM_PREDICT"', source)

    def test_qualification_background_llm_load_disables_thinking(self) -> None:
        source = Path("scripts/qualification/run_comprehensive_test.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(r'\"think\":false', source)


if __name__ == "__main__":
    unittest.main()
