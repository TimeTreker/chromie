from __future__ import annotations

import unittest
from unittest import mock

import httpx

from agent.app.clients.ollama_client import OllamaClient, OllamaGenerationError


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_generate_rejects_truncated_text_output_and_retains_incident_evidence(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"partial","done_reason":"length","eval_count":8}'
        response.json.return_value = {"response": "partial", "done_reason": "length", "eval_count": 8}
        response.raise_for_status.return_value = None
        http_client = mock.AsyncMock(); http_client.post.return_value = response
        context = mock.AsyncMock(); context.__aenter__.return_value = http_client
        with mock.patch("agent.app.clients.ollama_client.httpx.AsyncClient", return_value=context), mock.patch.dict("os.environ", {"CHROMIE_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
                with self.assertRaises(OllamaGenerationError) as raised:
                    await OllamaClient(base_url="http://chromie-llm:11434", model="test-model", purpose="response_composer").generate("hello", options={"num_predict": 8})
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
                    purpose="response_composer",
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


if __name__ == "__main__":
    unittest.main()
