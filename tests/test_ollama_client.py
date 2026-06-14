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


if __name__ == "__main__":
    unittest.main()
