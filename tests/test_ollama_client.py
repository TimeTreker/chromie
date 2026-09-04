from __future__ import annotations

import json
import unittest
from unittest import mock

import httpx

from agent.app.clients.ollama_client import (
    LayeredPrompt,
    OllamaClient,
    OllamaGenerationError,
)


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_json_accepts_one_complete_object_with_extra_closing_delimiter(self) -> None:
        client = OllamaClient(
            base_url="http://chromie-llm:11434",
            model="test-model",
        )

        self.assertEqual(
            client._parse_json('{"activity":{"text":"ready"}}}'),
            {"activity": {"text": "ready"}},
        )

    def test_parse_json_rejects_multiple_competing_objects(self) -> None:
        client = OllamaClient(
            base_url="http://chromie-llm:11434",
            model="test-model",
        )

        with self.assertRaises(json.JSONDecodeError):
            client._parse_json('{"decision":"one"} {"decision":"two"}')

    async def test_generate_stream_yields_ndjson_deltas_from_one_request(self) -> None:
        class StreamResponse:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb

            async def aiter_lines(self):
                yield json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"presentation_commit":',
                        },
                        "done": False,
                    }
                )
                yield json.dumps(
                    {
                        "message": {"role": "assistant", "content": "{}}"},
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 4,
                        "eval_count": 2,
                    }
                )

        http_client = mock.Mock()
        http_client.stream.return_value = StreamResponse()
        client_context = mock.AsyncMock()
        client_context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=client_context,
        ):
            deltas = [
                delta
                async for delta in OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    purpose="fast_planner",
                ).generate_stream(
                    "prompt",
                    response_format={"type": "object"},
                    prompt_family="fast_planner.streaming_advance",
                    turn_id="turn-stream",
                )
            ]

        self.assertEqual("".join(deltas), '{"presentation_commit":{}}')
        payload = http_client.stream.call_args.kwargs["json"]
        self.assertTrue(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["format"], {"type": "object"})
        self.assertEqual(
            payload["messages"],
            [{"role": "user", "content": "prompt"}],
        )
        self.assertEqual(
            http_client.stream.call_args.args[:2],
            ("POST", "http://chromie-llm:11434/api/chat"),
        )

    async def test_generate_uses_chat_transport_and_reads_assistant_content(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = json.dumps(
            {
                "message": {"role": "assistant", "content": '{"status":"ok"}'},
                "done_reason": "stop",
            }
        )
        response.json.return_value = json.loads(response.text)
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="test-model",
            ).generate(
                "prompt",
                system="system",
                response_format={"type": "object"},
            )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            http_client.post.call_args.args[0],
            "http://chromie-llm:11434/api/chat",
        )
        self.assertEqual(
            http_client.post.call_args.kwargs["json"]["messages"],
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "prompt"},
            ],
        )

    async def test_generate_stream_raises_typed_midstream_provider_error(self) -> None:
        class StreamResponse:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                del exc_type, exc, tb

            async def aiter_lines(self):
                yield json.dumps({"response": "{", "done": False})
                yield json.dumps({"error": "runner stopped"})

        http_client = mock.Mock()
        http_client.stream.return_value = StreamResponse()
        client_context = mock.AsyncMock()
        client_context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=client_context,
        ), self.assertLogs("chromie.agent.ollama", level="INFO") as logs:
            with self.assertRaises(OllamaGenerationError) as raised:
                async for _ in OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                ).generate_stream("prompt"):
                    pass

        self.assertEqual(raised.exception.failure_class, "stream_provider_error")
        self.assertTrue(any("llm_call_evidence " in line for line in logs.output))
        self.assertFalse(
            any("llm_call_evidence_failed" in line for line in logs.output)
        )

    async def test_generate_renders_stable_layers_before_volatile_suffix(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"ready","done_reason":"stop"}'
        response.json.return_value = {
            "response": "ready",
            "done_reason": "stop",
        }
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        prompt = LayeredPrompt(
            identity_world=("identity\n",),
            operating_contract=("role\n",),
            capability_contract=("catalog\n",),
            volatile_suffix="turn",
        )

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="test-model",
            ).generate(prompt, system="constitution")

        self.assertEqual(result, "ready")
        payload = http_client.post.call_args.kwargs["json"]
        self.assertEqual(
            payload["messages"][0],
            {"role": "system", "content": "constitution"},
        )
        self.assertEqual(
            payload["messages"][1]["content"],
            "identity\n\nrole\n\ncatalog\n\nturn",
        )

    async def test_generate_ignores_host_proxy_environment(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"ready"}'
        response.json.return_value = {"response": "ready"}
        response.raise_for_status.return_value = None

        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ) as client_class:
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="test-model",
            ).generate("hello")

        self.assertEqual(result, "ready")
        self.assertFalse(client_class.call_args.kwargs["trust_env"])



    async def test_generate_passes_json_schema_to_ollama_format(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"{\"relationship\":\"continue\"}"}'
        response.json.return_value = {
            "response": '{"relationship":"continue"}',
            "done_reason": "stop",
        }
        response.raise_for_status.return_value = None

        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        schema = {
            "type": "object",
            "properties": {
                "relationship": {"type": "string", "enum": ["continue", "new"]}
            },
            "required": ["relationship"],
            "additionalProperties": False,
        }

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="test-model",
                purpose="goal_association",
            ).generate("hello", response_format=schema)

        self.assertEqual(result, {"relationship": "continue"})
        request_payload = http_client.post.call_args.kwargs["json"]
        self.assertEqual(request_payload["format"], schema)

    async def test_generate_logs_correlated_complete_prompt_and_raw_output(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"{\\"decision\\":\\"continue\\"}"}'
        response.json.return_value = {
            "response": '{"decision":"continue"}',
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 4,
        }
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        schema = {
            "type": "object",
            "properties": {"decision": {"type": "string"}},
            "required": ["decision"],
        }

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ), self.assertLogs("chromie.agent.ollama", level="INFO") as logs:
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="gemma4:12b",
                purpose="goal_association",
            ).generate(
                "complete user prompt",
                system="complete system prompt",
                response_format=schema,
                prompt_family="goal_association.primary",
                turn_id="daily-benchmark-case",
                attempt=1,
            )

        self.assertEqual(result, {"decision": "continue"})
        evidence_line = next(
            line for line in logs.output if "llm_call_evidence " in line
        )
        record = json.loads(evidence_line.split("llm_call_evidence ", 1)[1])
        self.assertEqual(record["purpose"], "goal_association")
        self.assertEqual(record["stage"], "goal_association.primary")
        self.assertEqual(
            record["request"]["messages"],
            [
                {"role": "system", "content": "complete system prompt"},
                {"role": "user", "content": "complete user prompt"},
            ],
        )
        self.assertEqual(record["request"]["format"], schema)
        self.assertEqual(
            record["response"]["raw_model_output"],
            '{"decision":"continue"}',
        )
        self.assertEqual(
            record["response"]["parsed_output"], {"decision": "continue"}
        )
        self.assertEqual(record["correlations"]["turn_id"], "daily-benchmark-case")

    async def test_generate_rejects_truncated_text_output_and_retains_incident_evidence(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"partial","done_reason":"length","eval_count":8}'
        response.json.return_value = {"response": "partial", "done_reason": "length", "eval_count": 8}
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        with mock.patch("agent.app.clients.ollama_client.httpx.AsyncClient", return_value=context), mock.patch.dict("os.environ", {"CHROMIE_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
                with self.assertRaises(OllamaGenerationError) as raised:
                    await OllamaClient(base_url="http://chromie-llm:11434", model="test-model", purpose="fast_planner").generate("hello", options={"num_predict": 8})
        metadata = raised.exception.metadata()
        self.assertEqual(metadata["failure_class"], "output_truncated")
        self.assertFalse(metadata["retryable"])
        self.assertFalse(metadata["automatic_retry_allowed"])
        self.assertFalse(metadata["context_reduction_allowed"])
        self.assertFalse(metadata["result_trusted"])
        self.assertNotIn("_incident_evidence", metadata)
        self.assertEqual(raised.exception.incident_evidence()["request"]["prompt"], "hello")
        self.assertTrue(any("ollama_text_output_rejected" in line for line in error_logs.output))

    async def test_generate_rejects_truncated_structured_output_with_explicit_attribution(
        self,
    ) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"{\\"partial\\":true","done_reason":"length","eval_count":8}'
        response.json.return_value = {
            "response": '{"partial":true',
            "done_reason": "length",
            "eval_count": 8,
        }
        response.raise_for_status.return_value = None

        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ), self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    purpose="goal_association",
                ).generate(
                    "hello",
                    options={"num_ctx": 2048, "num_predict": 8},
                    response_format="json",
                )

        metadata = raised.exception.metadata()
        self.assertEqual(metadata["failure_class"], "output_truncated")
        self.assertEqual(metadata["failure_domain"], "llm_budget")
        self.assertEqual(metadata["architecture_attribution"], "not_evaluated")
        self.assertFalse(metadata["retryable"])
        self.assertFalse(metadata["automatic_retry_allowed"])
        self.assertFalse(metadata["context_reduction_allowed"])
        self.assertTrue(
            any("ollama_structured_output_rejected" in line for line in error_logs.output)
        )
        self.assertTrue(
            any("architecture_attribution=not_evaluated" in line for line in error_logs.output)
        )


    async def test_generate_inherits_declared_context_defaults_into_request(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"ready","done_reason":"stop"}'
        response.json.return_value = {
            "response": "ready",
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 1,
        }
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch.dict(
            "os.environ",
            {
                "OLLAMA_NUM_CTX": "32768",
                "OLLAMA_NUM_PREDICT": "4096",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "2048",
            },
            clear=False,
        ), mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="test-model",
            ).generate("hello", options={"temperature": 0})

        self.assertEqual(result, "ready")
        options = http_client.post.call_args.kwargs["json"]["options"]
        self.assertEqual(options["num_ctx"], 32768)
        self.assertEqual(options["num_predict"], 4096)

    async def test_generate_rejects_request_that_cannot_fit_before_http(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "4.0",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "256",
            },
            clear=False,
        ), mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient"
        ) as client_class, self.assertLogs(
            "chromie.agent.ollama", level="ERROR"
        ) as error_logs:
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    purpose="deep_planner",
                ).generate(
                    "x" * 4000,
                    system="y" * 1000,
                    options={"num_ctx": 1024, "num_predict": 512},
                    response_format="json",
                )

        self.assertEqual(raised.exception.failure_class, "prompt_budget_exceeded")
        metadata = raised.exception.metadata()
        self.assertEqual(metadata["failure_domain"], "llm_budget")
        self.assertFalse(metadata["retryable"])
        self.assertFalse(metadata["new_execution_allowed"])
        client_class.assert_not_called()
        self.assertTrue(
            any("ollama_request_rejected" in line for line in error_logs.output)
        )


    async def test_prefix_probe_finishes_a_preflight_rejection(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "4.0",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "256",
            },
            clear=False,
        ), mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient"
        ) as client_class, self.assertLogs(
            "chromie.agent.ollama", level="INFO"
        ) as logs:
            with self.assertRaises(OllamaGenerationError):
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    purpose="fast_planner",
                ).generate(
                    "x" * 4000,
                    system="y" * 1000,
                    options={"num_ctx": 1024, "num_predict": 512},
                    prompt_family="fast_planner.primary",
                    turn_id="turn-probe",
                    attempt=1,
                )

        client_class.assert_not_called()
        rendered = "\n".join(logs.output)
        self.assertIn("llm_prefix_probe_start", rendered)
        self.assertIn("prompt_family=fast_planner.primary", rendered)
        self.assertIn("turn_id=turn-probe", rendered)
        self.assertIn("llm_prefix_probe_finish", rendered)
        self.assertIn("status=failed", rendered)
        self.assertIn("failure_class=prompt_budget_exceeded", rendered)
        self.assertIn("prompt_eval_duration_ms=null", rendered)

    async def test_generate_classifies_timeout_as_infrastructure_not_architecture(
        self,
    ) -> None:
        http_client = mock.AsyncMock()
        http_client.post.side_effect = httpx.ReadTimeout("slow model")
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ), self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    timeout_ms=1234,
                    purpose="deep_planner",
                ).generate("hello", options={"num_ctx": 4096, "num_predict": 512})

        metadata = raised.exception.metadata()
        self.assertEqual(metadata["failure_class"], "timeout")
        self.assertEqual(metadata["failure_domain"], "inference_transport")
        self.assertEqual(metadata["architecture_attribution"], "not_evaluated")
        self.assertEqual(metadata["timeout_ms"], 1234)
        self.assertTrue(
            any("ollama_infrastructure_failure" in line for line in error_logs.output)
        )

    async def test_generate_classifies_http_context_limit_as_budget_failure(self) -> None:
        response = mock.Mock()
        response.status_code = 500
        response.text = "input length exceeds the model context window"

        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ), self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                    purpose="fast_planner",
                ).generate(
                    "hello",
                    options={"num_ctx": 2048, "num_predict": 512},
                    response_format="json",
                )

        metadata = raised.exception.metadata()
        self.assertEqual(metadata["failure_class"], "context_limit_exceeded")
        self.assertEqual(metadata["failure_domain"], "llm_budget")
        self.assertEqual(metadata["architecture_attribution"], "not_evaluated")
        self.assertEqual(metadata["status_code"], 500)
        self.assertTrue(
            any("failure_class=context_limit_exceeded" in line for line in error_logs.output)
        )

    async def test_generate_recovers_identical_structured_json_around_bare_closing_think_marker(self) -> None:
        duplicated = (
            '{"activity":{"role":"progress","text":"我去看看。"}}'
            '</think>'
            '{"activity":{"role":"progress","text":"我去看看。"}}'
        )
        response = mock.Mock()
        response.status_code = 200
        response.text = json.dumps({"response": duplicated, "done_reason": "stop"})
        response.json.return_value = {"response": duplicated, "done_reason": "stop"}
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client
        schema = {
            "type": "object",
            "properties": {"activity": {"type": "object"}},
            "required": ["activity"],
        }

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ), self.assertLogs("chromie.agent.ollama", level="WARNING") as logs:
            result = await OllamaClient(
                base_url="http://chromie-llm:11434",
                model="qwen-test",
                purpose="fast_planner",
            ).generate("hello", response_format=schema)

        self.assertEqual(result["activity"]["text"], "我去看看。")
        self.assertTrue(
            any("ollama_non_thinking_boundary_recovered" in line for line in logs.output)
        )
        self.assertIs(http_client.post.call_args.kwargs["json"]["think"], False)

    async def test_generate_rejects_material_thinking_content_even_when_think_false(self) -> None:
        leaked = '<think>private reasoning</think>{"decision":"continue"}'
        response = mock.Mock()
        response.status_code = 200
        response.text = json.dumps({"response": leaked, "done_reason": "stop"})
        response.json.return_value = {"response": leaked, "done_reason": "stop"}
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="qwen-test",
                    purpose="fast_planner",
                ).generate(
                    "hello",
                    response_format={"type": "object"},
                )

        self.assertEqual(raised.exception.failure_class, "thinking_output_violation")
        self.assertEqual(raised.exception.failure_domain, "provider_contract")
        self.assertFalse(raised.exception.metadata()["result_trusted"])

    async def test_generate_rejects_provider_thinking_field(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = json.dumps(
            {"response": '{"decision":"continue"}', "thinking": "hidden", "done_reason": "stop"}
        )
        response.json.return_value = {
            "response": '{"decision":"continue"}',
            "thinking": "hidden",
            "done_reason": "stop",
        }
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="qwen-test",
                ).generate("hello", response_format={"type": "object"})

        self.assertEqual(raised.exception.failure_class, "thinking_output_violation")
        self.assertEqual(raised.exception.metadata()["violation"], "provider_field:thinking")

    async def test_generate_rejects_thinking_marker_in_plain_text(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = json.dumps({"response": "</think>hello", "done_reason": "stop"})
        response.json.return_value = {"response": "</think>hello", "done_reason": "stop"}
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock()
        http_client.post.return_value = response
        context = mock.AsyncMock()
        context.__aenter__.return_value = http_client

        with mock.patch(
            "agent.app.clients.ollama_client.httpx.AsyncClient",
            return_value=context,
        ):
            with self.assertRaises(OllamaGenerationError) as raised:
                await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="qwen-test",
                ).generate("hello")

        self.assertEqual(raised.exception.failure_class, "thinking_output_violation")


if __name__ == "__main__":
    unittest.main()
