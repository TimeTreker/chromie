from __future__ import annotations

import asyncio
import json
import os
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import patch

from orchestrator.orchestrator import VoiceAssistant


class _FakeContent:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self._payloads = payloads

    def __aiter__(self):
        async def iterate():
            for payload in self._payloads:
                yield (json.dumps(payload) + "\n").encode("utf-8")

        return iterate()


class _FakeResponse:
    status = 200

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.content = _FakeContent(payloads)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return ""


class _FakeHttpSession:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.requests: list[dict[str, object]] = []

    def post(self, _url: str, *, json: dict[str, object]):
        self.requests.append(json)
        return _FakeResponse(self.payloads)


class DirectLlmTruncationGuardTests(unittest.TestCase):
    @staticmethod
    def _assistant(payloads: list[dict[str, object]]):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.ollama_model = "qwen3:4b"
        assistant.llm_url = "http://chromie-llm:11434/api/generate"
        assistant.sessions = SimpleNamespace(
            current_sid="sid",
            state={
                "sid": {
                    "response_chars": 0,
                    "scheduled_tts": 0,
                }
            }
        )
        logs: list[str] = []
        spoken: list[str] = []
        http = _FakeHttpSession(payloads)

        def build_prompt(
            self: VoiceAssistant,
            _user_text: str,
            _session_id: str | None,
            **_kwargs,
        ) -> str:
            return "Answer the user."

        async def reset_playback(self: VoiceAssistant) -> None:
            return None

        async def get_http_session(self: VoiceAssistant):
            return http

        async def schedule_tts(
            self: VoiceAssistant,
            text: str,
            _session_id: str | None,
        ) -> None:
            spoken.append(text)
            self.sessions.state["sid"]["scheduled_tts"] += 1

        def session_log(
            self: VoiceAssistant,
            _session_id: str | None,
            message: str,
            *args,
        ) -> None:
            logs.append(message % args if args else message)

        def maybe_done(self: VoiceAssistant, _session_id: str | None) -> None:
            return None

        assistant._build_direct_llm_prompt = MethodType(build_prompt, assistant)
        assistant.reset_playback_ordering = MethodType(reset_playback, assistant)
        assistant.get_http_session = MethodType(get_http_session, assistant)
        assistant.schedule_tts_sentence = MethodType(schedule_tts, assistant)
        assistant.session_log = MethodType(session_log, assistant)
        assistant.maybe_session_done = MethodType(maybe_done, assistant)
        assistant.tts_flush_chars = 120
        return assistant, http, spoken, logs

    def test_truncated_stream_is_rejected_before_any_tts(self) -> None:
        assistant, http, spoken, logs = self._assistant(
            [
                {"response": "This is only a partial answer. ", "done": False},
                {
                    "response": "It was cut off",
                    "done": True,
                    "done_reason": "length",
                    "prompt_eval_count": 20,
                    "eval_count": 4,
                },
            ]
        )
        with patch.dict(
            os.environ,
            {
                "OLLAMA_NUM_CTX": "32768",
                "OLLAMA_NUM_PREDICT": "4",
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "2.0",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "0",
                "ORCH_DIRECT_LLM_REQUIRE_COMPLETE_OUTPUT": "1",
            },
            clear=False,
        ):
            asyncio.run(assistant.process_llm_tts("hello", "sid"))

        self.assertEqual(len(http.requests), 1)
        self.assertEqual(spoken, [])
        self.assertTrue(
            any("llm_completion_rejected" in line and "output_truncated" in line for line in logs)
        )
        self.assertTrue(assistant.sessions.state["sid"]["llm_done"])

    def test_verified_complete_stream_is_spoken_only_after_done(self) -> None:
        assistant, _http, spoken, logs = self._assistant(
            [
                {"response": "Complete answer.", "done": False},
                {
                    "response": "",
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 20,
                    "eval_count": 3,
                },
            ]
        )
        with patch.dict(
            os.environ,
            {
                "OLLAMA_NUM_CTX": "32768",
                "OLLAMA_NUM_PREDICT": "64",
                "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE": "2.0",
                "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS": "0",
                "ORCH_DIRECT_LLM_REQUIRE_COMPLETE_OUTPUT": "1",
            },
            clear=False,
        ):
            asyncio.run(assistant.process_llm_tts("hello", "sid"))

        self.assertEqual(spoken, ["Complete answer."])
        self.assertTrue(any("llm_verified_flush_to_tts" in line for line in logs))
        self.assertFalse(any("llm_flush_to_tts" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
