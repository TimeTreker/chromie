from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

import pytest

from agent.app.clients.model_client_factory import build_model_client
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.clients.openai_client import OpenAICompatibleClient
from agent.app.clients.openai_protocol import build_openai_chat_payload
from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import (
    OllamaUserMeaningInterpreter,
)
from agent.app.inference_compute import CognitionComputeClass
from agent.app.settings import AgentServiceSettings, OpenAICompatibleProviderSettings

SCHEMA: dict[str, Any] = {
    "title": "Decision",
    "type": "object",
    "properties": {
        "kind": {"oneOf": [{"const": "speak"}, {"const": "act"}]},
        "text": {"type": "string", "maxLength": 12},
    },
    "required": ["kind", "text"],
    "additionalProperties": False,
    "x-guidance": {"whitespace_flexible": False},
}


class RecordedChatServer:
    """Serve ``answer(request_body) -> (content, finish_reason)`` over /chat/completions."""

    def __init__(self, answer: Callable[[dict[str, Any]], tuple[str, str]]):
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                content, finish_reason = answer(body)
                if body.get("stream"):
                    chunks = [
                        {"choices": [{"delta": {"content": content}, "finish_reason": None}]},
                        {"choices": [{"delta": {}, "finish_reason": finish_reason}],
                         "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
                    ]
                    payload = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                    payload_bytes = payload.encode()
                    content_type = "text/event-stream"
                else:
                    payload_bytes = json.dumps({
                        "model": body["model"],
                        "choices": [{"message": {"role": "assistant", "content": content},
                                     "finish_reason": finish_reason}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                    }).encode()
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload_bytes)))
                self.end_headers()
                self.wfile.write(payload_bytes)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RecordedChatServer":
        self.thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()


def _service_settings(url: str, **changes: Any) -> AgentServiceSettings:
    openai = OpenAICompatibleProviderSettings().model_copy(update={"base_url": url, "model": "remote-model", **changes})
    return AgentServiceSettings().model_copy(update={"llm_provider": "openai", "openai": openai})


@pytest.fixture(autouse=True)
def _credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")


def test_payload_drops_engine_fields_and_encodes_the_schema_both_ways() -> None:
    messages = [{"role": "system", "content": "be Chromie"}, {"role": "user", "content": "hi"}]
    options = {"num_ctx": 131072, "num_predict": 2048, "temperature": 0, "top_p": 0.9}

    native = build_openai_chat_payload(
        model="qwen3-remote", messages=messages, compute_class=CognitionComputeClass.INTERACTIVE,
        options=options, response_format=SCHEMA, stream=True, structured_output="json_schema",
    )
    assert "priority" not in native and "chat_template_kwargs" not in native
    assert native["max_tokens"] == 2048 and native["temperature"] == 0.0
    assert native["response_format"]["json_schema"] == {"name": "chromie_response", "schema": {
        **{k: v for k, v in SCHEMA.items() if k != "x-guidance"}}}
    assert native["stream_options"] == {"include_usage": True}

    prompted = build_openai_chat_payload(
        model="remote", messages=messages, compute_class=CognitionComputeClass.INTERACTIVE,
        options=options, response_format=SCHEMA, stream=False, structured_output="prompt",
    )
    assert prompted["response_format"] == {"type": "json_object"}
    assert prompted["messages"][0]["role"] == "system"
    assert '"maxLength":12' in prompted["messages"][0]["content"]
    assert messages[0]["content"] == "be Chromie"  # caller's messages are untouched


def test_factory_selects_the_remote_client_by_configuration_only() -> None:
    client = build_model_client(model="gemma4:12b", timeout_ms=5400, purpose="fast_planner",
                                service_settings=_service_settings("http://127.0.0.1:9"))
    pinned = build_model_client(model="gpt-5", timeout_ms=5400, purpose="reflection",
                                service_settings=_service_settings("http://127.0.0.1:9"))

    assert isinstance(client, OpenAICompatibleClient)
    assert client.model == "remote-model" and client.timeout_ms == 120000
    assert pinned.model == "gpt-5"
    with pytest.raises(ValueError, match="AGENT_OPENAI_MODEL"):
        build_model_client(model="gemma4:12b", timeout_ms=5400, purpose="fast_planner",
                           service_settings=_service_settings("http://127.0.0.1:9", model=""))


def test_client_sends_bearer_auth_and_returns_validated_json() -> None:
    with RecordedChatServer(lambda _body: ('{"kind":"speak","text":"hello"}', "stop")) as server:
        client = OpenAICompatibleClient("gemma4:12b", timeout_ms=1000, purpose="fast_planner",
                                        service_settings=_service_settings(server.url))
        result = asyncio.run(client.generate("hi", system="be Chromie", response_format=SCHEMA))

        async def collect() -> str:
            return "".join([delta async for delta in client.generate_stream("hi")])

        streamed = asyncio.run(collect())

    assert result == {"kind": "speak", "text": "hello"}
    assert streamed == '{"kind":"speak","text":"hello"}'
    assert all(r["headers"]["Authorization"] == "Bearer offline-test-key" for r in server.requests)
    assert all(r["path"] == "/v1/chat/completions" for r in server.requests)
    assert "priority" not in server.requests[0]["body"]


@pytest.mark.parametrize(
    ("content", "finish_reason", "failure_class"),
    [
        ('{"kind":"speak","text":"he', "length", "output_truncated"),
        ('{"kind":"speak","text":"far longer than twelve"}', "stop", "structured_output_validation"),
    ],
)
def test_client_types_untrusted_completions(content: str, finish_reason: str, failure_class: str) -> None:
    with RecordedChatServer(lambda _body: (content, finish_reason)) as server:
        client = OpenAICompatibleClient("gemma4:12b", timeout_ms=1000, purpose="fast_planner",
                                        service_settings=_service_settings(server.url))
        with pytest.raises(OllamaGenerationError) as caught:
            asyncio.run(client.generate("hi", response_format=SCHEMA))
    assert caught.value.failure_class == failure_class


def test_user_meaning_interpreter_uses_the_remote_service() -> None:
    with RecordedChatServer(lambda _body: ('{"kind":"speak","text":"hello"}', "stop")) as server:
        interpreter = OllamaUserMeaningInterpreter(
            ollama_url="http://127.0.0.1:9", model="qwen3.5:4b", inference_provider="openai",
            openai_settings=_service_settings(server.url).openai, timeout_ms=5400,
        )
        data = asyncio.run(interpreter._chat(
            {"model": interpreter.model, "format": SCHEMA, "options": {"num_ctx": 4096, "num_predict": 512},
             "messages": [{"role": "system", "content": "interpret"}, {"role": "user", "content": "hi"}]},
            stage="primary",
        ))
        assert asyncio.run(interpreter.warm_model()) == {}

    assert interpreter.model == "remote-model" and interpreter.timeout_s == 120.0
    assert json.loads(data["message"]["content"])["kind"] == "speak"
    assert server.requests[0]["headers"]["Authorization"] == "Bearer offline-test-key"
