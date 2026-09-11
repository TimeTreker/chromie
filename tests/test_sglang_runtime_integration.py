from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from agent.app.cognitive_core.goal_interpreter.model_interpreter import OllamaGoalInterpreter
from agent.app.clients.model_client_factory import build_model_client
from agent.app.clients.ollama_client import OllamaClient
from agent.app.clients.sglang_client import SGLangClient, SGLangGenerationError
from agent.app.clients.sglang_protocol import (
    build_sglang_chat_payload,
    candidate_compatible_schema,
    sglang_priority,
    sglang_stream_delta,
)
from agent.app.inference_compute import CognitionComputeClass
from agent.app.settings import Settings
from orchestrator.runtime.presentation_compute_lease import PresentationComputeLease


class SGLangProtocolTests(unittest.TestCase):
    def test_planner_and_skill_wire_preserve_shapes_and_original_validation(self) -> None:
        import copy
        from jsonschema import Draft202012Validator

        for title in (
            "DeepPlannerModelOutput", "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput",
        ):
            with self.subTest(title=title):
                schema = {
                    "title": title, "type": "object",
                    "properties": {
                        "decision": {"enum": ["select", "none"]},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["decision", "items"], "additionalProperties": False,
                    "allOf": [{
                        "if": {"properties": {"decision": {"const": "none"}}},
                        "then": {"properties": {"items": {"maxItems": 0}}},
                    }],
                }
                original = copy.deepcopy(schema)
                payload = build_sglang_chat_payload(
                    model="fixed", messages=[],
                    compute_class=CognitionComputeClass.DELIBERATIVE,
                    options={}, response_format=schema, stream=False, priority_step=100,
                )
                wire = payload["response_format"]["json_schema"]["schema"]
                self.assertEqual(wire["anyOf"][0]["required"], schema["required"])
                self.assertFalse(wire["anyOf"][0]["additionalProperties"])
                self.assertEqual(schema, original)
                for value, expected in (
                    ({"decision": "none", "items": []}, True),
                    ({"decision": "select", "items": ["a"]}, True),
                    ({"decision": "none", "items": ["a"]}, False),
                    ({"decision": "none"}, False),
                    ({"decision": "none", "selected_items": []}, False),
                ):
                    self.assertEqual(Draft202012Validator(wire).is_valid(value), expected)
                    self.assertEqual(Draft202012Validator(schema).is_valid(value), expected)

    def test_streaming_json_keeps_schema_authority_and_decoder_compatible_shapes(self) -> None:
        import copy
        from jsonschema import Draft202012Validator

        schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "pattern": "^[^?？]*$"},
                "duration": {"type": "number", "minimum": 0.05, "maximum": 0.5},
            },
            "required": ["text", "duration"], "additionalProperties": False,
            "allOf": [{"properties": {"text": {"minLength": 1}}}],
        }
        original = copy.deepcopy(schema)
        declared = {"title": "FastPlannerStreamingAdvanceOutput", **schema}
        payload = build_sglang_chat_payload(
            model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
            options={}, response_format=declared, stream=True, priority_step=100,
        )
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        wire_schema = payload["response_format"]["json_schema"]["schema"]
        self.assertEqual(wire_schema["x-guidance"], {"whitespace_flexible": False})
        self.assertEqual(wire_schema["required"], ["text", "duration"])
        self.assertFalse(wire_schema["additionalProperties"])
        self.assertIn("anyOf", wire_schema)
        self.assertNotIn("pattern", wire_schema["properties"]["text"])
        self.assertNotIn("minimum", wire_schema["properties"]["duration"])
        self.assertEqual(schema, original)
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid({"text": "checking", "duration": 0.12}))
        self.assertFalse(validator.is_valid({"text": "checking?", "duration": 0.12}))
        self.assertFalse(validator.is_valid({"text": "checking", "duration": 0.9}))

    def test_compact_formatting_is_scoped_without_mutating_contract(self) -> None:
        for title in (
            "GoalSegmentationModelOutput", "GoalAssociationModelOutput",
            "DeepPlannerModelOutput", "AgentSkillSelectionModelOutput",
            "GoalInterpretationModelOutput", "FastPlannerOutput", "OtherOutput",
        ):
            with self.subTest(title=title):
                schema = {"title": title, "type": "object", "properties": {}}
                payload = build_sglang_chat_payload(
                    model="chromie-gemma4-12b", messages=[],
                    compute_class=CognitionComputeClass.INTERACTIVE,
                    options={}, response_format=schema, stream=False,
                    priority_step=100,
                )
                wire = payload["response_format"]["json_schema"]["schema"]
                expected = dict(schema)
                if title in {
                    "GoalSegmentationModelOutput", "GoalAssociationModelOutput",
                    "DeepPlannerModelOutput", "AgentSkillSelectionModelOutput",
                }:
                    expected["x-guidance"] = {"whitespace_flexible": False}
                self.assertEqual(wire, expected)
                self.assertNotIn("x-guidance", schema)

    def test_priority_preserves_provider_neutral_compute_order(self) -> None:
        self.assertGreater(
            sglang_priority(CognitionComputeClass.REALTIME),
            sglang_priority(CognitionComputeClass.INTERACTIVE),
        )
        self.assertGreater(
            sglang_priority(CognitionComputeClass.INTERACTIVE),
            sglang_priority(CognitionComputeClass.DELIBERATIVE),
        )

    def test_payload_uses_qualified_thinking_and_priority_controls(self) -> None:
        payload = build_sglang_chat_payload(
            model="chromie-qwen35-9b-sglang",
            messages=[{"role": "user", "content": "hello"}],
            compute_class=CognitionComputeClass.INTERACTIVE,
            options={"num_ctx": 32768, "num_predict": 123},
            response_format="text",
            stream=True,
            priority_step=100,
        )
        self.assertEqual(payload["priority"], 300)
        self.assertEqual(payload["max_tokens"], 123)
        self.assertEqual(
            payload["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertNotIn("num_ctx", payload)

    def test_schema_projection_matches_qualified_unique_items_removal(self) -> None:
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
        translated, removed = candidate_compatible_schema(original)
        self.assertEqual(removed, ["$.properties.refs.uniqueItems"])
        self.assertNotIn("uniqueItems", translated["properties"]["refs"])
        self.assertTrue(original["properties"]["refs"]["uniqueItems"])

    def test_non_qwen_model_does_not_receive_qwen_template_control(self) -> None:
        payload = build_sglang_chat_payload(
            model="some-gemma-model",
            messages=[{"role": "user", "content": "hello"}],
            compute_class=CognitionComputeClass.DELIBERATIVE,
            options={"num_predict": 32},
            response_format="text",
            stream=False,
            priority_step=100,
        )
        self.assertNotIn("chat_template_kwargs", payload)
        self.assertEqual(payload["priority"], 100)

    def test_stream_rejects_reasoning_output(self) -> None:
        with self.assertRaises(ValueError):
            sglang_stream_delta(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "answer",
                                "reasoning_content": "hidden",
                            },
                            "finish_reason": None,
                        }
                    ]
                }
            )

    def test_factory_keeps_ollama_default_and_allows_explicit_sglang(self) -> None:
        with patch.dict(os.environ, {"AGENT_LLM_PROVIDER": "ollama"}, clear=False):
            configured = Settings()
            client = build_model_client(
                model="test",
                timeout_ms=1000,
                purpose="fast_planner",
                service_settings=configured,
            )
            self.assertIs(type(client), OllamaClient)

        with patch.dict(
            os.environ,
            {
                "AGENT_LLM_PROVIDER": "sglang",
                "AGENT_SGLANG_URL": "http://example.invalid/v1",
                "AGENT_SGLANG_PRIORITY_STEP": "100",
            },
            clear=False,
        ):
            configured = Settings()
            client = build_model_client(
                model="test",
                timeout_ms=1000,
                purpose="fast_planner",
                service_settings=configured,
            )
            self.assertIsInstance(client, SGLangClient)
            self.assertEqual(client.base_url, "http://example.invalid/v1")
            self.assertEqual(client.compute_class, CognitionComputeClass.INTERACTIVE)


class SGLangStreamEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonstream_failures_retain_request_and_available_response(self) -> None:
        import httpx

        for mode in ("stop", "nested_stop", "length", "invalid_json", "http_error", "invalid_response", "nonobject_response", "timeout", "cancel"):
            with self.subTest(mode=mode):
                data = {"choices": [{"message": {"content": "broken" if mode == "invalid_json" else '{"ok":true}'},
                                     "finish_reason": "length" if mode == "length" else "stop"}]}
                response = Mock(status_code=503 if mode == "http_error" else 200,
                                text="provider body")
                response.json.return_value = [1, 2] if mode == "nonobject_response" else data
                if mode == "invalid_response":
                    response.json.side_effect = ValueError("invalid provider JSON")
                transport = AsyncMock()
                transport.__aenter__.return_value = transport
                transport.post.return_value = response
                if mode == "timeout":
                    transport.post.side_effect = httpx.ReadTimeout("test timeout")
                elif mode == "cancel":
                    transport.post.side_effect = asyncio.CancelledError()
                client = SGLangClient("http://sglang.invalid/v1", "fixed", timeout_ms=1000,
                                      purpose="agent_skill_selection")
                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=transport), \
                     patch("agent.app.clients.sglang_client.log_llm_call_evidence") as evidence:
                    call = client._generate("exact prompt", response_format="json",
                                            prefix_probe_call_id="test-call",
                                            evidence_context={"turn_id": "test-turn", "attempt": 1})
                    if mode == "nested_stop":
                        try:
                            raise ValueError("caller already handling an unrelated error")
                        except ValueError:
                            self.assertEqual(await call, {"ok": True})
                    elif mode == "stop":
                        self.assertEqual(await call, {"ok": True})
                    else:
                        error_type = asyncio.CancelledError if mode == "cancel" else (ValueError if mode in {"invalid_json", "invalid_response", "nonobject_response"} else SGLangGenerationError)
                        with self.assertRaises(error_type):
                            await call
                evidence.assert_called_once()
                record = evidence.call_args.kwargs
                self.assertEqual(record["request"], transport.post.call_args.kwargs["json"])
                expected_response = (None if mode in {"timeout", "cancel"} else
                                     {"http_status": response.status_code, "body": "provider body"}
                                     if mode in {"http_error", "invalid_response", "nonobject_response"} else data)
                self.assertEqual(record["response"], expected_response)
                self.assertEqual(record["status"], "accepted" if mode in {"stop", "nested_stop"} else "cancelled" if mode == "cancel" else "failed")
                self.assertEqual(record["correlations"], {"turn_id": "test-turn", "attempt": 1})
                transport.post.assert_called_once()
                self.assertEqual(record["error"] is None, mode in {"stop", "nested_stop"})
                if mode in {"timeout", "length"}:
                    self.assertEqual(record["error"]["failure_class"], "timeout" if mode == "timeout" else "output_truncated")

    async def test_each_stream_exit_retains_one_exact_request_and_partial_output(self) -> None:
        import json
        import httpx

        for mode in ("stop", "length", "eof", "timeout", "cancel"):
            with self.subTest(mode=mode):
                class StreamResponse:
                    status_code = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        return None

                    async def aiter_lines(self):
                        yield "data: " + json.dumps({"choices": [{
                            "delta": {"content": "<terminal_plan>{"}, "finish_reason": None,
                        }]})
                        if mode == "timeout":
                            raise httpx.ReadTimeout("test timeout")
                        if mode == "cancel":
                            raise asyncio.CancelledError()
                        if mode != "eof":
                            yield "data: " + json.dumps({"choices": [{
                                "delta": {}, "finish_reason": mode,
                            }]})

                http_client = Mock()
                http_client.stream.return_value = StreamResponse()
                client_context = AsyncMock()
                client_context.__aenter__.return_value = http_client
                client = SGLangClient("http://sglang.invalid/v1", "fixed", timeout_ms=1000,
                                      purpose="fast_planner")

                async def consume():
                    return [delta async for delta in client.generate_stream(
                        "exact prompt", response_format="text", turn_id="turn-evidence", attempt=1,
                    )]

                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=client_context), \
                     patch("agent.app.clients.sglang_client.log_llm_call_evidence") as evidence:
                    if mode == "stop":
                        try:
                            raise ValueError("caller already handling an unrelated error")
                        except ValueError:
                            self.assertEqual(await consume(), ["<terminal_plan>{"])
                    else:
                        expected = asyncio.CancelledError if mode == "cancel" else SGLangGenerationError
                        with self.assertRaises(expected):
                            await consume()
                evidence.assert_called_once()
                record = evidence.call_args.kwargs
                self.assertEqual(record["request"], http_client.stream.call_args.kwargs["json"])
                self.assertEqual(record["response"]["choices"][0]["message"]["content"], "<terminal_plan>{")
                self.assertEqual(record["correlations"], {"turn_id": "turn-evidence", "attempt": 1})
                self.assertEqual(record["status"], "accepted" if mode == "stop" else
                                 "cancelled" if mode == "cancel" else "failed")
                self.assertEqual(record["error"] is None, mode == "stop")
                if mode == "length":
                    self.assertEqual(record["error"]["failure_class"], "output_truncated")


class SGLangGoalInterpreterWarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_warm_probe_reserves_terminal_completion_headroom(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://ollama.invalid",
            model="chromie-qwen35-9b-sglang",
            inference_provider="sglang",
            sglang_url="http://sglang.invalid/v1",
            timeout_ms=1000,
        )
        logged = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "ready"},
                "done": True,
                "done_reason": "stop",
            }
        )

        with patch.object(interpreter, "_chat_logged", logged):
            await interpreter.warm_model()

        logged.assert_awaited_once()
        payload = logged.await_args.args[0]
        self.assertEqual(logged.await_args.kwargs["stage"], "startup_warm")
        self.assertEqual(payload["stream"], False)
        self.assertGreater(payload["options"]["num_predict"], 1)
        self.assertEqual(payload["options"]["num_predict"], 8)


class _ObservedLease(PresentationComputeLease):
    def __init__(self) -> None:
        super().__init__(
            enabled=True,
            control_url="http://example.invalid",
            mode="in_place",
            timeout_ms=1000,
        )
        self.controls: list[tuple[str, dict[str, object]]] = []

    async def _post_control(self, action: str, payload: dict[str, object]) -> None:
        self.controls.append((action, dict(payload)))


class PresentationComputeLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrap_holds_engine_for_vocal_delivery(self) -> None:
        lease = _ObservedLease()
        observed: list[dict[str, object]] = []

        async def speech(args):
            observed.append(args)
            self.assertTrue(lease.active)
            return {"scheduled": True}

        wrapped = lease.wrap_speech_scheduler(speech)
        result = await wrapped({"text": "hi", "metadata": {}})
        self.assertEqual(result, {"scheduled": True})
        self.assertFalse(lease.active)
        self.assertEqual(
            [item[0] for item in lease.controls],
            ["pause_generation", "continue_generation"],
        )
        metadata = observed[0]["metadata"]
        self.assertIsInstance(metadata, dict)
        self.assertTrue(metadata["wait_for_voice_release"])

    async def test_revocation_invalidates_old_release_token(self) -> None:
        lease = _ObservedLease()
        old = await lease.acquire(reason="old_speech")
        self.assertTrue(await lease.revoke(reason="new_user_input"))
        new = await lease.acquire(reason="replacement_speech")
        self.assertFalse(await lease.release(old, reason="stale_old_speech"))
        self.assertTrue(lease.active)
        self.assertTrue(await lease.release(new, reason="replacement_done"))
        self.assertEqual(
            [item[0] for item in lease.controls],
            [
                "pause_generation",
                "continue_generation",
                "pause_generation",
                "continue_generation",
            ],
        )


if __name__ == "__main__":
    unittest.main()
