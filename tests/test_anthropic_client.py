from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic
import pytest

from agent.app.clients import anthropic_client
from agent.app.clients.anthropic_client import (
    AnthropicGenerationError,
    ClaudeClient,
    build_anthropic_request,
)
from agent.app.clients.anthropic_protocol import (
    CLAUDE_OPTIONAL_PARAMETER_LIMIT,
    claude_output_schema,
)
from agent.app.clients.model_client_factory import build_model_client
from agent.app.clients.ollama_client import OllamaClient
from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import (
    OllamaUserMeaningInterpreter,
)
from agent.app.settings import AgentServiceSettings, AnthropicProviderSettings
from benchmarks.integration.model_replay import ModelReplay, load_case
from tests.anthropic_replay_support import RecordedAnthropicServer
from tests.workflow_replay_support import run_case

ROOT = Path(__file__).resolve().parents[1]

SCHEMA: dict[str, Any] = {
    "title": "Decision",
    "type": "object",
    "properties": {
        "kind": {"oneOf": [{"const": "speak"}, {"const": "act"}]},
        "text": {"type": "string", "maxLength": 12},
        "count": {"type": "integer", "minimum": 0, "maximum": 3},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 2, "uniqueItems": True},
    },
    "required": ["kind", "text"],
    "additionalProperties": False,
}


def _settings(**changes: Any) -> AnthropicProviderSettings:
    return AnthropicProviderSettings().model_copy(update=changes)


def _service_settings(url: str, **changes: Any) -> AgentServiceSettings:
    return AgentServiceSettings().model_copy(
        update={"llm_provider": "anthropic", "anthropic": _settings(base_url=url, **changes)}
    )


@pytest.fixture(autouse=True)
def _offline_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    anthropic_client._PROMPT_ONLY_SCHEMAS.clear()


def test_schema_translation_keeps_alternatives_and_records_removed_constraints() -> None:
    translation = claude_output_schema(SCHEMA)

    kind = translation.schema["properties"]["kind"]
    assert kind == {"anyOf": [{"const": "speak"}, {"const": "act"}]}
    assert translation.schema["additionalProperties"] is False
    assert "maxLength" not in translation.schema["properties"]["text"]
    assert translation.summary()["removed_keywords"] == {
        "maxItems": 1, "maxLength": 1, "maximum": 1, "minimum": 1, "uniqueItems": 1,
    }
    assert (translation.optional_parameters, translation.union_parameters) == (2, 1)
    assert translation.native_eligible
    assert SCHEMA["properties"]["kind"].get("oneOf")  # the canonical schema is untouched


def test_schema_translation_flags_recursion_and_parameter_limits() -> None:
    recursive = {"$defs": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Node"}}}},
                 "$ref": "#/$defs/Node"}
    wide = {"type": "object", "properties": {
        f"p{i}": {"type": "string"} for i in range(CLAUDE_OPTIONAL_PARAMETER_LIMIT + 1)}}

    assert claude_output_schema(recursive).recursive
    assert not claude_output_schema(recursive).native_eligible
    assert not claude_output_schema(wide).native_eligible


def test_request_maps_local_options_and_selects_schema_encoding() -> None:
    messages = [{"role": "system", "content": "be Chromie"}, {"role": "user", "content": "hi"}]
    options = {"num_ctx": 131072, "num_predict": 2048, "temperature": 0, "top_p": 0.9}

    native, decision = build_anthropic_request(
        model="claude-opus-5-5", messages=messages, response_format=SCHEMA,
        options=options, settings=_settings(),
    )
    assert decision["mode"] == "native_schema"
    assert decision["ignored_options"] == ["num_ctx", "temperature", "top_p"]
    assert native["max_tokens"] == 16000
    assert native["thinking"] == {"type": "adaptive"}
    assert native["output_config"]["effort"] == "medium"
    assert native["output_config"]["format"]["type"] == "json_schema"
    assert native["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert native["fallbacks"] == "default"
    assert "temperature" not in native

    prompted, decision = build_anthropic_request(
        model="claude-opus-5-5", messages=messages, response_format=SCHEMA,
        options=options, settings=_settings(structured_output="prompt", server_side_fallback=False),
    )
    assert decision["mode"] == "prompt_schema"
    assert "format" not in prompted["output_config"]
    assert '"maxLength":12' in prompted["system"][0]["text"]
    assert "betas" not in prompted and "fallbacks" not in prompted


def test_request_rejects_assistant_prefill() -> None:
    with pytest.raises(AnthropicGenerationError) as caught:
        build_anthropic_request(
            model="claude-opus-5-5",
            messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "{"}],
            response_format="text", options=None, settings=_settings(),
        )
    assert caught.value.failure_class == "provider_contract_unsupported"


def test_factory_keeps_local_default_and_swaps_by_configuration_only() -> None:
    local = build_model_client(model="gemma4:12b", timeout_ms=5400, purpose="fast_planner",
                               service_settings=AgentServiceSettings().model_copy(update={"llm_provider": "ollama"}))
    claude = build_model_client(model="gemma4:12b", timeout_ms=5400, purpose="fast_planner",
                                service_settings=_service_settings("http://127.0.0.1:9"))
    pinned = build_model_client(model="claude-sonnet-5-5", timeout_ms=5400, purpose="reflection",
                                service_settings=_service_settings("http://127.0.0.1:9"))

    assert type(local) is OllamaClient and local.model == "gemma4:12b"
    assert isinstance(claude, ClaudeClient) and claude.model == "claude-opus-5-5"
    assert claude.timeout_ms == 120000  # local GPU budgets get a remote floor
    assert pinned.model == "claude-sonnet-5-5"


def _answers(*replies: tuple[str, str]) -> Any:
    queue = list(replies)
    return lambda _body: queue.pop(0)


def test_client_returns_parsed_json_over_the_messages_stream() -> None:
    reply = json.dumps({"kind": "speak", "text": "hello"})
    with RecordedAnthropicServer(_answers((reply, "end_turn"))) as server:
        client = ClaudeClient("gemma4:12b", timeout_ms=1000, purpose="fast_planner",
                              service_settings=_service_settings(server.url))
        result = asyncio.run(client.generate("hi", system="be Chromie", response_format=SCHEMA))

    assert result == {"kind": "speak", "text": "hello"}
    body = server.requests[0]["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"]["format"]["schema"]["properties"]["kind"]["anyOf"]
    assert "server-side-fallback-2026-07-01" in server.requests[0]["headers"]["anthropic-beta"]


def test_client_streams_text() -> None:
    with RecordedAnthropicServer(_answers(("ready", "end_turn"))) as server:
        client = ClaudeClient("gemma4:12b", timeout_ms=1000, purpose="speech",
                              service_settings=_service_settings(server.url))

        async def collect() -> str:
            return "".join([delta async for delta in client.generate_stream("hi")])

        assert asyncio.run(collect()) == "ready"


@pytest.mark.parametrize(
    ("reply", "stop_reason", "failure_class"),
    [
        ('{"kind":"speak","text":"he', "max_tokens", "output_truncated"),
        ("", "refusal", "model_refusal"),
        ('{"kind":"speak","text":"far longer than twelve"}', "end_turn", "structured_output_validation"),
    ],
)
def test_client_types_untrusted_completions(reply: str, stop_reason: str, failure_class: str) -> None:
    with RecordedAnthropicServer(_answers((reply, stop_reason))) as server:
        client = ClaudeClient("gemma4:12b", timeout_ms=1000, purpose="fast_planner",
                              service_settings=_service_settings(server.url))
        with pytest.raises(AnthropicGenerationError) as caught:
            asyncio.run(client.generate("hi", response_format=SCHEMA))

    assert caught.value.failure_class == failure_class
    assert caught.value.retryable is (failure_class == "structured_output_validation")


def test_rejected_native_grammar_is_restated_in_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class Stream:
        def __init__(self, request: dict[str, Any]):
            self.request = request

        async def __aenter__(self) -> "Stream":
            calls.append(self.request)
            if "format" in self.request["output_config"]:
                response = anthropic.BadRequestError.__new__(anthropic.BadRequestError)
                Exception.__init__(response, "Schema is too complex for compilation.")
                response.status_code = 400
                raise response
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def get_final_message(self) -> Any:
            block = type("Block", (), {"type": "text", "text": '{"kind":"act","text":"ok"}'})()
            return type("Message", (), {"content": [block], "stop_reason": "end_turn",
                                        "model": "claude-opus-5-5", "usage": None})()

    fake = type("Fake", (), {})()
    fake.beta = type("Beta", (), {})()
    fake.beta.messages = type("Messages", (), {"stream": staticmethod(lambda **request: Stream(request))})()

    text, _evidence, _request, decision = asyncio.run(anthropic_client.claude_complete(
        fake, model="claude-opus-5-5", messages=[{"role": "user", "content": "hi"}],
        response_format=SCHEMA, options=None, settings=_settings(), purpose="fast_planner",
    ))

    assert json.loads(text)["kind"] == "act"
    assert decision["mode"] == "prompt_schema" and decision["native_rejected"]
    assert ["format" in call["output_config"] for call in calls] == [True, False]


def test_user_meaning_interpreter_uses_the_same_provider_contract() -> None:
    reply = json.dumps({"kind": "speak", "text": "hello"})
    with RecordedAnthropicServer(_answers((reply, "end_turn"))) as server:
        interpreter = OllamaUserMeaningInterpreter(
            ollama_url="http://127.0.0.1:9", model="qwen3.5:4b", inference_provider="anthropic",
            anthropic_settings=_settings(base_url=server.url), timeout_ms=5400,
        )
        data = asyncio.run(interpreter._chat(
            {"model": interpreter.model, "format": SCHEMA, "options": {"num_ctx": 4096, "num_predict": 512},
             "messages": [{"role": "system", "content": "interpret"}, {"role": "user", "content": "hi"}]},
            stage="primary",
        ))
        assert asyncio.run(interpreter.warm_model()) == {}

    assert interpreter.model == "claude-opus-5-5" and interpreter.timeout_s == 120.0
    assert json.loads(data["message"]["content"])["kind"] == "speak"
    assert data["done_reason"] == "stop"
    assert len(server.requests) == 1


def _first_case(role: str) -> Path:
    for path in sorted((ROOT / "benchmarks/integration/workflow_scenarios").glob("workflow-*.json")):
        steps = load_case(path)["model_steps"]
        if all(step.get("fixture_kind", "authored_reference") == "authored_reference" for step in steps) and any(
            step.get("role", step["name"].split("-")[0]) == role for step in steps
        ):
            return path
    raise AssertionError(f"no authored replay case for {role}")


@pytest.mark.parametrize("role", ["umi", "ga", "fast"])
def test_workflow_replay_runs_each_role_through_the_claude_wire_path(role: str, tmp_path: Path) -> None:
    case = load_case(_first_case(role))
    holder: dict[str, ModelReplay] = {}

    def answer(_body: dict[str, Any]) -> tuple[str, str]:
        replay = holder["replay"]
        step = replay.steps[replay.position]
        return json.dumps(replay.materialize(step["response"]), ensure_ascii=False), "end_turn"

    with RecordedAnthropicServer(answer) as server:
        replay = ModelReplay(case, candidate={
            "role": role, "model": "claude-opus-5-5", "url": server.url, "provider": "anthropic", "timeout": 60,
        })
        holder["replay"] = replay
        result = asyncio.run(run_case(case, tmp_path, replay))

    assert result["passed"], result
    assert replay.candidate_calls == len(server.requests) > 0
    assert not replay.candidate_changed_result
    modes = {record["structured_output"]["mode"] for record in replay.records if record.get("provider") == "anthropic"}
    assert modes == ({"prompt_schema"} if role == "fast" else {"native_schema"})
