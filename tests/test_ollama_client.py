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

    async def test_generate_logs_colored_output_truncation_diagnostic(self) -> None:
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"response":"partial","done_reason":"length","eval_count":8}'
        response.json.return_value = {
            "response": "partial",
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
        ), mock.patch.dict("os.environ", {"CHROMIE_CLI_COLOR": "1"}, clear=False):
            with self.assertLogs("chromie.agent.ollama", level="ERROR") as error_logs:
                result = await OllamaClient(
                    base_url="http://chromie-llm:11434",
                    model="test-model",
                ).generate("hello", options={"num_predict": 8})

        self.assertEqual(result, "partial")
        self.assertTrue(any("llm_output_truncated" in line for line in error_logs.output))
        self.assertTrue(any("\033[31m" in line for line in error_logs.output))

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
        self.assertTrue(metadata["retryable"])
        self.assertTrue(
            any("ollama_structured_output_rejected" in line for line in error_logs.output)
        )
        self.assertTrue(
            any("architecture_attribution=not_evaluated" in line for line in error_logs.output)
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
