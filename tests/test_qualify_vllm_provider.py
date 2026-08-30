from __future__ import annotations

import unittest

from scripts.qualify_vllm_provider import (
    DEFAULT_GOAL_INTERPRETER_MANIFEST,
    QualificationFailure,
    StreamObservation,
    _assert_complete_stream,
    _binding_value_matches,
    _chat_payload,
    _evaluate_goal_interpreter_case,
    _evaluate_goal_interpreter_case_dimensions,
    _extract_stream_delta,
    _load_goal_interpreter_manifest,
    _vllm_compatible_schema,
    _wire_coordination_satisfies,
)


class VllmProviderQualificationTests(unittest.TestCase):
    def test_chat_payload_explicitly_disables_qwen_thinking(self) -> None:
        payload = _chat_payload(
            "Qwen/Qwen3.5-4B",
            "prompt",
            stream=True,
            max_tokens=32,
        )

        self.assertEqual(
            payload["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertEqual(payload["temperature"], 0)
        self.assertTrue(payload["stream"])

    def test_chat_payload_does_not_send_qwen_template_kwargs_to_other_models(self) -> None:
        payload = _chat_payload(
            "RedHatAI/gemma-3-12b-it-quantized.w4a16",
            "prompt",
            stream=False,
            max_tokens=32,
        )

        self.assertNotIn("chat_template_kwargs", payload)

    def test_stream_delta_detects_reasoning_channel(self) -> None:
        content, finish_reason, reasoning = _extract_stream_delta(
            {
                "choices": [
                    {
                        "delta": {
                            "content": "visible",
                            "reasoning_content": "hidden",
                        },
                        "finish_reason": None,
                    }
                ]
            }
        )

        self.assertEqual(content, "visible")
        self.assertIsNone(finish_reason)
        self.assertTrue(reasoning)

    def test_complete_stream_requires_terminal_marker(self) -> None:
        observation = StreamObservation(
            label="test",
            started_s=1.0,
            first_delta_s=1.1,
            finished_s=1.2,
            delta_count=1,
            text="visible",
            finish_reason="stop",
            terminal_seen=False,
        )

        with self.assertRaisesRegex(QualificationFailure, "terminal SSE"):
            _assert_complete_stream(observation)

    def test_complete_stream_rejects_reasoning_even_with_visible_text(self) -> None:
        observation = StreamObservation(
            label="test",
            started_s=1.0,
            first_delta_s=1.1,
            finished_s=1.2,
            delta_count=1,
            text="visible",
            finish_reason="stop",
            terminal_seen=True,
            reasoning_seen=True,
        )

        with self.assertRaisesRegex(QualificationFailure, "reasoning channel"):
            _assert_complete_stream(observation)

    def test_vllm_schema_translation_removes_only_unique_items(self) -> None:
        original = {
            "type": "object",
            "properties": {
                "refs": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                }
            },
            "additionalProperties": False,
        }

        translated, removed = _vllm_compatible_schema(original)

        self.assertEqual(removed, ["$.properties.refs.uniqueItems"])
        self.assertNotIn("uniqueItems", translated["properties"]["refs"])
        self.assertTrue(original["properties"]["refs"]["uniqueItems"])
        self.assertFalse(translated["additionalProperties"])

    def test_wire_coordination_is_checked_before_legacy_lowering(self) -> None:
        payload = {"coordination": [{"kind": "parallel", "refs": ["r1", "r2"]}]}

        self.assertTrue(_wire_coordination_satisfies(payload, "parallel", 2))
        self.assertFalse(_wire_coordination_satisfies(payload, "sequence", 2))

    def test_wire_coordination_rejects_duplicate_refs(self) -> None:
        payload = {"coordination": [{"kind": "sequence", "refs": ["r1", "r1"]}]}

        self.assertFalse(_wire_coordination_satisfies(payload, "sequence", 2))

    def test_primary_goal_interpreter_manifest_freezes_broader_contract(self) -> None:
        manifest = _load_goal_interpreter_manifest(DEFAULT_GOAL_INTERPRETER_MANIFEST)
        case_ids = {str(case["id"]) for case in manifest["cases"]}
        groups = {str(case["group"]) for case in manifest["cases"]}

        self.assertEqual(manifest["qualification_id"], "chromie.goal_interpreter.primary.v1")
        self.assertEqual(len(manifest["cases"]), 16)
        self.assertGreaterEqual(len(groups), 6)
        self.assertTrue(
            {
                "weather_exact_location",
                "compound_numeric_sequence",
                "filler_blink_twice",
                "parallel_gaze_blink",
                "ambiguous_bare_referent",
                "cross_clause_acquire_delivery",
            }.issubset(case_ids)
        )
        self.assertEqual(len(manifest["manifest_sha256"]), 64)

    def test_binding_match_normalizes_text_and_integral_float(self) -> None:
        self.assertTrue(_binding_value_matches("  Tonight  ", ["tonight"]))
        self.assertTrue(_binding_value_matches(3.0, [3]))
        self.assertFalse(_binding_value_matches("three", [3]))

    def test_case_evaluator_binds_modifiers_to_their_own_responsibility(self) -> None:
        manifest = _load_goal_interpreter_manifest(DEFAULT_GOAL_INTERPRETER_MANIFEST)
        case = next(item for item in manifest["cases"] if item["id"] == "parallel_gaze_blink")
        decision = {
            "responsibilities": [
                {
                    "local_ref": "gaze",
                    "outcome": "look at the user",
                    "output_mode": "body_action",
                    "bindings": {},
                },
                {
                    "local_ref": "blink",
                    "outcome": "blink eyes",
                    "output_mode": "body_action",
                    "bindings": {},
                },
            ],
            "unresolved": [],
        }
        wire = {
            "responsibilities": [
                {
                    "local_ref": "gaze",
                    "output_mode": "body_action",
                    "binding_items": {"entity": "我", "duration": 3},
                },
                {
                    "local_ref": "blink",
                    "output_mode": "body_action",
                    "binding_items": {"count": 2},
                },
            ],
            "coordination": [{"kind": "parallel", "refs": ["gaze", "blink"]}],
        }

        self.assertEqual(_evaluate_goal_interpreter_case(case, decision, wire), [])
        dimensions = _evaluate_goal_interpreter_case_dimensions(case, decision, wire)
        self.assertTrue(all(errors == [] for errors in dimensions.values()))

        wire["responsibilities"][0]["binding_items"] = {"entity": "我", "count": 2}
        wire["responsibilities"][1]["binding_items"] = {"duration": 3}
        errors = _evaluate_goal_interpreter_case(case, decision, wire)
        dimensions = _evaluate_goal_interpreter_case_dimensions(case, decision, wire)

        self.assertTrue(any("missing required binding duration" in error for error in errors))
        self.assertTrue(any("contains forbidden binding count" in error for error in errors))
        self.assertTrue(dimensions["bindings"])
        self.assertEqual(dimensions["outcome"], [])


if __name__ == "__main__":
    unittest.main()
