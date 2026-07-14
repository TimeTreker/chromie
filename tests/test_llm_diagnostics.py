from __future__ import annotations

import logging
import unittest

from shared.chromie_runtime.llm_diagnostics import (
    ollama_completion_diagnostics,
    ollama_prompt_preflight_diagnostics,
)


class LlmDiagnosticsTests(unittest.TestCase):
    def test_done_reason_length_reports_output_truncated_error(self) -> None:
        diagnostics = ollama_completion_diagnostics(
            options={"num_predict": 64, "num_ctx": 2048},
            data={"done_reason": "length", "eval_count": 64, "prompt_eval_count": 200},
            prompt_chars=800,
        )

        rendered = [item.render() for item in diagnostics]
        self.assertTrue(any(item.event == "llm_output_truncated" for item in diagnostics))
        self.assertEqual(
            next(item.level for item in diagnostics if item.event == "llm_output_truncated"),
            logging.ERROR,
        )
        self.assertTrue(any("suggestion=increase_num_predict_or_shorten_response" in item for item in rendered))
        truncation = next(
            item for item in diagnostics if item.event == "llm_output_truncated"
        )
        self.assertEqual(truncation.fields["failure_domain"], "llm_budget")
        self.assertEqual(truncation.fields["architecture_attribution"], "not_evaluated")
        self.assertTrue(truncation.fields["retryable"])

    def test_prompt_eval_count_at_context_window_reports_prompt_truncated(self) -> None:
        diagnostics = ollama_completion_diagnostics(
            options={"num_ctx": 2048, "num_predict": 128},
            data={"done_reason": "stop", "prompt_eval_count": 2048, "eval_count": 12},
            prompt_chars=9200,
        )

        self.assertTrue(any(item.event == "llm_prompt_truncated" for item in diagnostics))
        prompt_diag = next(item for item in diagnostics if item.event == "llm_prompt_truncated")
        self.assertEqual(prompt_diag.level, logging.ERROR)
        self.assertIn("suggestion=increase_num_ctx_or_compact_prompt", prompt_diag.render())
        self.assertEqual(prompt_diag.fields["architecture_attribution"], "not_evaluated")

    def test_budget_pressure_warnings_are_distinct_from_truncation(self) -> None:
        diagnostics = ollama_completion_diagnostics(
            options={"num_ctx": 2048, "num_predict": 100},
            data={"done_reason": "stop", "prompt_eval_count": 1900, "eval_count": 91},
        )
        events = {item.event: item.level for item in diagnostics}

        self.assertEqual(events["llm_prompt_context_pressure"], logging.WARNING)
        self.assertEqual(events["llm_output_budget_pressure"], logging.WARNING)
        self.assertNotIn("llm_output_truncated", events)


    def test_stop_at_exact_num_predict_is_not_assumed_truncated(self) -> None:
        diagnostics = ollama_completion_diagnostics(
            options={"num_predict": 16},
            data={"done_reason": "stop", "eval_count": 16},
        )
        self.assertFalse(any(item.event == "llm_output_truncated" for item in diagnostics))

    def test_prompt_preflight_uses_estimated_token_pressure(self) -> None:
        diagnostics = ollama_prompt_preflight_diagnostics(
            prompt_chars=7600,
            options={"num_ctx": 2048},
        )

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].event, "llm_prompt_context_pressure")
        self.assertIn("reason=estimated_prompt_near_num_ctx", diagnostics[0].render())


if __name__ == "__main__":
    unittest.main()
