from __future__ import annotations

import unittest

from scripts.qualify_inference_provider import (
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
    _candidate_compatible_schema,
    _model_artifact_arg,
    _provider_priority,
    _provider_priority_semantics,
    _priority_mapping,
    _wire_coordination_satisfies,
)
from agent.app.inference_compute import CognitionComputeClass


class InferenceProviderQualificationTests(unittest.TestCase):
    def test_chat_payload_uses_candidate_qwen_thinking_control(self) -> None:
        for provider in ("sglang", "vllm"):
            with self.subTest(provider=provider):
                payload = _chat_payload(
                    "Qwen/Qwen3.5-4B",
                    "prompt",
                    provider=provider,
                    stream=True,
                    max_tokens=32,
                )

                self.assertEqual(
                    payload["chat_template_kwargs"],
                    {"enable_thinking": False},
                )
                self.assertNotIn("reasoning_effort", payload)
                self.assertEqual(payload["temperature"], 0)
                self.assertTrue(payload["stream"])

    def test_chat_payload_uses_ollama_openai_reasoning_control(self) -> None:
        payload = _chat_payload(
            "qwen3.5:4b",
            "prompt",
            provider="ollama",
            stream=True,
            max_tokens=32,
        )

        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertNotIn("chat_template_kwargs", payload)

    def test_chat_payload_carries_provider_priority_only_when_requested(self) -> None:
        without_priority = _chat_payload(
            "model", "prompt", provider="sglang", stream=True, max_tokens=32
        )
        with_priority = _chat_payload(
            "model",
            "prompt",
            provider="sglang",
            stream=True,
            max_tokens=32,
            priority=300,
        )

        self.assertNotIn("priority", without_priority)
        self.assertEqual(with_priority["priority"], 300)

    def test_provider_priority_translation_preserves_relative_compute_order(self) -> None:
        self.assertGreater(
            _provider_priority(
                "sglang", CognitionComputeClass.INTERACTIVE, step=100
            ),
            _provider_priority(
                "sglang", CognitionComputeClass.DELIBERATIVE, step=100
            ),
        )
        self.assertLess(
            _provider_priority(
                "vllm", CognitionComputeClass.INTERACTIVE, step=100
            ),
            _provider_priority(
                "vllm", CognitionComputeClass.DELIBERATIVE, step=100
            ),
        )

    def test_qualification_priority_mapping_is_provider_specific_not_semantic(self) -> None:
        self.assertEqual(
            _priority_mapping("sglang", step=100),
            {
                "realtime": 400,
                "interactive": 300,
                "continuity": 200,
                "deliberative": 100,
                "background": 0,
            },
        )
        self.assertEqual(
            _priority_mapping("vllm", step=100),
            {
                "realtime": 0,
                "interactive": 100,
                "continuity": 200,
                "deliberative": 300,
                "background": 400,
            },
        )

    def test_model_artifact_requires_comparison_identity_fields(self) -> None:
        artifact = _model_artifact_arg(
            '{"source_model_id":"Qwen/Qwen3.5-4B","weight_format":"gguf",'
            '"quantization":"Q4_K_M","dtype":"q4"}'
        )
        self.assertEqual(artifact["source_model_id"], "Qwen/Qwen3.5-4B")
        self.assertEqual(artifact["quantization"], "Q4_K_M")

        with self.assertRaisesRegex(Exception, "source_model_id"):
            _model_artifact_arg('{"weight_format":"safetensors","quantization":"none"}')

    def test_ollama_control_never_fabricates_request_priority(self) -> None:
        self.assertIsNone(
            _provider_priority(
                "ollama", CognitionComputeClass.INTERACTIVE, step=100
            )
        )
        self.assertEqual(
            _priority_mapping("ollama", step=100),
            {
                "realtime": None,
                "interactive": None,
                "continuity": None,
                "deliberative": None,
                "background": None,
            },
        )
        self.assertEqual(
            _provider_priority_semantics("ollama"),
            "unsupported_control_no_priority_sent",
        )

    def test_chat_payload_does_not_send_qwen_template_kwargs_to_other_models(self) -> None:
        payload = _chat_payload(
            "RedHatAI/gemma-3-12b-it-quantized.w4a16",
            "prompt",
            provider="sglang",
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

    def test_candidate_schema_translation_removes_only_unique_items(self) -> None:
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

        translated, removed = _candidate_compatible_schema(original)

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
