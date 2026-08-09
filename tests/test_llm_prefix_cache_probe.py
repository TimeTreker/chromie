from __future__ import annotations

import unittest

from shared.chromie_runtime.llm_diagnostics import PrefixCacheTracker


class PrefixCacheTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = PrefixCacheTracker()

    def test_failed_attempt_remains_the_previous_call(self) -> None:
        first = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.primary",
            model="qwen3:4b",
            system="stable system",
            prompt="volatile turn one",
            turn_id="sid-1",
            attempt=1,
        )
        first_id = first.fields["call_id"]
        self.tracker.finish(
            first_id,
            status="failed",
            error_type="ValidationError",
            failure_class="structured_output_validation",
        )

        second = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.repair",
            model="qwen3:4b",
            system="repair system",
            prompt="repair turn one",
            turn_id="sid-1",
            attempt=2,
        )

        self.assertEqual(second.fields["previous_call_id"], first_id)
        self.assertEqual(
            second.fields["previous_prompt_family"], "fast_planner.primary"
        )

    def test_prompt_families_do_not_pollute_each_other(self) -> None:
        primary = self.tracker.begin(
            purpose="response_composer",
            prompt_family="response_composer.primary",
            model="gemma4:e2b",
            system="primary",
            prompt="same",
        )
        self.tracker.finish(primary.fields["call_id"], status="completed")
        review = self.tracker.begin(
            purpose="response_composer",
            prompt_family="response_composer.safe_read_review",
            model="gemma4:e2b",
            system="review",
            prompt="different",
        )

        self.assertFalse(review.fields["family_seen_before"])
        self.assertIsNone(review.fields["common_prefix_lower_bound_chars"])

    def test_chunked_hashes_report_partial_common_prefix(self) -> None:
        stable = "s" * 1200
        first = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.primary",
            model="qwen3:4b",
            system=stable,
            prompt="turn one",
        )
        self.tracker.finish(first.fields["call_id"], status="completed")
        second = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.primary",
            model="qwen3:4b",
            system=stable,
            prompt="turn two",
        )

        self.assertGreaterEqual(second.fields["common_prefix_lower_bound_chars"], 1024)
        self.assertFalse(second.fields["exact_proxy_repeat"])

    def test_missing_durations_remain_none(self) -> None:
        start = self.tracker.begin(
            purpose="goal_association",
            prompt_family="goal_association.primary",
            model="qwen3:4b",
            system="system",
            prompt="prompt",
        )
        finish = self.tracker.finish(start.fields["call_id"], status="failed")

        self.assertIsNotNone(finish)
        assert finish is not None
        self.assertIsNone(finish.fields["prompt_eval_duration_ms"])
        self.assertIsNone(finish.fields["load_duration_ms"])

    def test_completion_metrics_are_converted_from_nanoseconds(self) -> None:
        start = self.tracker.begin(
            purpose="deep_planner",
            prompt_family="deep_planner.primary",
            model="gemma4:e2b",
            system="system",
            prompt="prompt",
        )
        call_id = start.fields["call_id"]
        self.tracker.record_response(
            call_id,
            {
                "prompt_eval_count": 123,
                "prompt_eval_duration": 2_500_000,
                "load_duration": 1_000_000,
                "eval_count": 10,
                "eval_duration": 4_000_000,
                "total_duration": 8_000_000,
            },
        )
        finish = self.tracker.finish(call_id, status="completed")

        self.assertIsNotNone(finish)
        assert finish is not None
        self.assertEqual(finish.fields["prompt_eval_duration_ms"], 2.5)
        self.assertEqual(finish.fields["load_duration_ms"], 1.0)
        self.assertEqual(finish.fields["total_duration_ms"], 8.0)

    def test_declared_stable_prefix_repeat_is_only_a_reuse_candidate(self) -> None:
        layers = (
            ("layer0_constitutional_foundation", "system"),
            ("layer1_identity_world", "identity"),
            ("layer2_operating_contract", "role"),
            ("layer3_capability_contract", "catalog"),
        )
        first = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.primary",
            model="qwen3:4b",
            system="system",
            prompt="identityrolecatalogturn one",
            declared_stable_layers=layers,
            request_contract_digest="sha256:contract",
        )
        self.tracker.finish(first.fields["call_id"], status="completed")

        second = self.tracker.begin(
            purpose="fast_planner",
            prompt_family="fast_planner.primary",
            model="qwen3:4b",
            system="system",
            prompt="identityrolecatalogturn two",
            declared_stable_layers=layers,
            request_contract_digest="sha256:contract",
        )

        self.assertTrue(second.fields["stable_prefix_repeat"])
        self.assertTrue(second.fields["request_contract_repeat"])
        self.assertTrue(second.fields["reuse_candidate"])
        self.assertNotIn("cache_hit", second.fields)

    def test_changed_request_contract_is_not_a_reuse_candidate(self) -> None:
        layers = (("layer0_constitutional_foundation", "system"),)
        first = self.tracker.begin(
            purpose="goal_association",
            prompt_family="goal_association.primary",
            model="gemma4:12b",
            system="system",
            prompt="turn one",
            declared_stable_layers=layers,
            request_contract_digest="sha256:schema-one",
        )
        self.tracker.finish(first.fields["call_id"], status="completed")
        second = self.tracker.begin(
            purpose="goal_association",
            prompt_family="goal_association.primary",
            model="gemma4:12b",
            system="system",
            prompt="turn two",
            declared_stable_layers=layers,
            request_contract_digest="sha256:schema-two",
        )

        self.assertTrue(second.fields["stable_prefix_repeat"])
        self.assertFalse(second.fields["request_contract_repeat"])
        self.assertFalse(second.fields["reuse_candidate"])


if __name__ == "__main__":
    unittest.main()
