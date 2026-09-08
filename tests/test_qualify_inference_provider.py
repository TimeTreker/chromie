from __future__ import annotations

import argparse
import asyncio
import time
import unittest
from unittest.mock import patch

from scripts.qualify_inference_provider import (
    DEFAULT_GOAL_INTERPRETER_MANIFEST,
    QualificationFailure,
    StreamObservation,
    TtsObservation,
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
    _qualify_foreground_under_deep_load,
    _resolve_contention_model_topology,
    _sglang_native_control_url,
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

    def test_chat_payload_uses_ollama_openai_reasoning_control_for_all_models(self) -> None:
        for model in ("qwen3.5:4b", "gemma4:12b"):
            with self.subTest(model=model):
                payload = _chat_payload(
                    model,
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

    def test_contention_model_topology_defaults_and_overrides_per_transaction(self) -> None:
        gemma_artifact = {
            "source_model_id": "ollama/gemma4:12b",
            "weight_format": "gguf",
            "quantization": "Q4_K_M",
        }
        qwen_artifact = {
            "source_model_id": "ollama/qwen3.5:9b",
            "weight_format": "gguf",
            "quantization": "Q4_K_M",
        }
        args = argparse.Namespace(
            model="gemma4:12b",
            model_revision="gemma-digest",
            model_artifact_json=gemma_artifact,
            fast_gi_model=None,
            fast_gi_model_revision=None,
            fast_gi_model_artifact_json=None,
            fast_planner_model="qwen3.5:9b",
            fast_planner_model_revision="qwen-digest",
            fast_planner_model_artifact_json=qwen_artifact,
            deliberative_model=None,
            deliberative_model_revision=None,
            deliberative_model_artifact_json=None,
        )

        topology = _resolve_contention_model_topology(args)

        self.assertEqual(topology["fast_gi"]["model"], "gemma4:12b")
        self.assertEqual(topology["fast_planner"]["model"], "qwen3.5:9b")
        self.assertEqual(topology["deliberative"]["model"], "gemma4:12b")
        self.assertEqual(topology["fast_planner"]["revision"], "qwen-digest")
        self.assertEqual(topology["fast_planner"]["artifact"], qwen_artifact)

    def test_contention_model_topology_rejects_partial_override_identity(self) -> None:
        args = argparse.Namespace(
            model="gemma4:12b",
            model_revision="gemma-digest",
            model_artifact_json={
                "source_model_id": "ollama/gemma4:12b",
                "weight_format": "gguf",
                "quantization": "Q4_K_M",
            },
            fast_gi_model=None,
            fast_gi_model_revision=None,
            fast_gi_model_artifact_json=None,
            fast_planner_model="qwen3.5:9b",
            fast_planner_model_revision=None,
            fast_planner_model_artifact_json=None,
            deliberative_model=None,
            deliberative_model_revision=None,
            deliberative_model_artifact_json=None,
        )

        with self.assertRaisesRegex(ValueError, "fast_planner model override requires"):
            _resolve_contention_model_topology(args)

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


class InferenceProviderContentionRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_contention_routes_each_stage_to_its_declared_model(self) -> None:
        seen: dict[str, str] = {}
        release_deep = asyncio.Event()

        def observation(
            *,
            label: str,
            text: str,
            started_s: float,
            finished_s: float,
        ) -> StreamObservation:
            return StreamObservation(
                label=label,
                started_s=started_s,
                first_delta_s=started_s + 0.01,
                last_delta_s=finished_s - 0.01,
                finished_s=finished_s,
                delta_count=1,
                text=text,
                finish_reason="stop",
                terminal_seen=True,
            )

        async def fake_observe_stream(
            client, endpoint, payload, *, label, first_delta_event=None, delta_times=None
        ):
            del client, endpoint
            seen[label] = payload["model"]
            if label == "deliberative_load":
                if first_delta_event is not None:
                    first_delta_event.set()
                await release_deep.wait()
                return observation(
                    label=label, text="1 2 3", started_s=1.0, finished_s=3.0
                )
            if label == "foreground_fast_gi":
                return observation(
                    label=label,
                    text="chromie-fast-gi-ready",
                    started_s=1.2,
                    finished_s=1.4,
                )
            if label == "foreground_fast_planner":
                release_deep.set()
                return observation(
                    label=label,
                    text="chromie-presentation-commit-ready",
                    started_s=1.5,
                    finished_s=1.7,
                )
            raise AssertionError(label)

        with patch(
            "scripts.qualify_inference_provider._observe_stream",
            side_effect=fake_observe_stream,
        ):
            result = await _qualify_foreground_under_deep_load(
                object(),
                "http://provider.invalid/v1/chat/completions",
                provider="ollama",
                fast_gi_model="gemma4:12b",
                fast_planner_model="qwen3.5:9b",
                deliberative_model="gemma4:12b",
                priority_step=100,
                deliberative_context_repeat=1,
                deliberative_max_tokens=256,
                tts_url=None,
                tts_speaker="chromie_mixed",
                require_foreground_before_deep=True,
            )

        self.assertEqual(
            seen,
            {
                "deliberative_load": "gemma4:12b",
                "foreground_fast_gi": "gemma4:12b",
                "foreground_fast_planner": "qwen3.5:9b",
            },
        )
        self.assertEqual(
            result["model_routes"],
            {
                "fast_gi": "gemma4:12b",
                "fast_planner": "qwen3.5:9b",
                "deliberative": "gemma4:12b",
            },
        )
        self.assertTrue(result["foreground_completed_before_deep"])

    def test_sglang_native_control_url_strips_openai_v1_suffix(self) -> None:
        self.assertEqual(
            _sglang_native_control_url(
                "http://127.0.0.1:30000/v1", "pause_generation"
            ),
            "http://127.0.0.1:30000/pause_generation",
        )
        self.assertEqual(
            _sglang_native_control_url(
                "http://provider.invalid/prefix/v1/", "continue_generation"
            ),
            "http://provider.invalid/prefix/continue_generation",
        )

    async def test_presentation_lease_pauses_tts_window_and_resumes_deep(self) -> None:
        release_deep = asyncio.Event()
        controls: list[tuple[str, dict]] = []

        def stream_observation(label: str, text: str, started: float, finished: float):
            return StreamObservation(
                label=label,
                started_s=started,
                first_delta_s=started + 0.001,
                last_delta_s=finished - 0.001,
                finished_s=finished,
                delta_count=1,
                text=text,
                finish_reason="stop",
                terminal_seen=True,
            )

        async def fake_observe_stream(
            client, endpoint, payload, *, label, first_delta_event=None, delta_times=None
        ):
            del client, endpoint, payload
            now = time.perf_counter()
            if label == "deliberative_load":
                if delta_times is not None:
                    delta_times.append(now)
                if first_delta_event is not None:
                    first_delta_event.set()
                await release_deep.wait()
                resumed = time.perf_counter()
                if delta_times is not None:
                    delta_times.append(resumed)
                return stream_observation(label, "1 2 3", now, resumed + 0.01)
            if label == "foreground_fast_gi":
                return stream_observation(
                    label, "chromie-fast-gi-ready", now, now + 0.01
                )
            if label == "foreground_fast_planner":
                return stream_observation(
                    label, "chromie-presentation-commit-ready", now, now + 0.01
                )
            raise AssertionError(label)

        async def fake_observe_tts(url, *, speaker, label):
            del url, speaker
            started = time.perf_counter()
            return TtsObservation(
                started_s=started,
                first_audio_s=started + 0.01,
                finished_s=started + 0.02,
                audio_bytes=16,
                audio_sha256=f"sha-{label}",
            )

        async def fake_control(client, *, url, label, payload):
            del client
            started = time.perf_counter()
            finished = time.perf_counter()
            controls.append((url, dict(payload)))
            if label == "presentation_lease_continue":
                asyncio.get_running_loop().call_soon(release_deep.set)
            return {
                "started_s": started,
                "finished_s": finished,
                "elapsed_ms": (finished - started) * 1000.0,
                "request": dict(payload),
                "response": {"status": "ok"},
            }

        with (
            patch(
                "scripts.qualify_inference_provider._observe_stream",
                side_effect=fake_observe_stream,
            ),
            patch(
                "scripts.qualify_inference_provider._observe_tts",
                side_effect=fake_observe_tts,
            ),
            patch(
                "scripts.qualify_inference_provider._post_generation_control",
                side_effect=fake_control,
            ),
        ):
            result = await _qualify_foreground_under_deep_load(
                object(),
                "http://127.0.0.1:30000/v1/chat/completions",
                provider="sglang",
                fast_gi_model="chromie-qwen35-9b-sglang",
                fast_planner_model="chromie-qwen35-9b-sglang",
                deliberative_model="chromie-qwen35-9b-sglang",
                priority_step=100,
                deliberative_context_repeat=1,
                deliberative_max_tokens=256,
                tts_url="ws://127.0.0.1:5000",
                tts_speaker="chromie_mixed",
                require_foreground_before_deep=True,
                presentation_lease_mode="in_place",
                provider_base_url="http://127.0.0.1:30000/v1",
            )

        lease = result["presentation_lease"]
        self.assertEqual(result["status"], "pass")
        self.assertEqual(lease["scope"], "sglang_engine")
        self.assertEqual(lease["deep_deltas_during_tts"], 0)
        self.assertTrue(lease["deep_resumed_after_continue"])
        self.assertEqual(result["tts"]["measurement_mode"], "presentation_lease")
        self.assertIn("presentation_lease", result["tts"])
        self.assertEqual(
            controls,
            [
                (
                    "http://127.0.0.1:30000/pause_generation",
                    {"mode": "in_place"},
                ),
                (
                    "http://127.0.0.1:30000/continue_generation",
                    {"torch_empty_cache": False},
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
