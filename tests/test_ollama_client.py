from __future__ import annotations

import unittest
from unittest import mock

from agent.app.clients.ollama_client import OllamaClient


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


if __name__ == "__main__":
    unittest.main()
