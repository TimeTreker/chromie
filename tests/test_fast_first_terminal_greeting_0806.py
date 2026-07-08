from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest


class _ExplodingOllama:
    async def generate(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - must not be called
        raise AssertionError("terminal router greeting must not call conversation LLM")


class FastFirstTerminalGreeting0806Tests(unittest.IsolatedAsyncioTestCase):
    async def test_router_fast_first_greeting_already_scheduled_skips_agent_rewrite(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "greeting-terminal-test",
                "text": "Hello, how are you.",
                "language": "en-US",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "greeting",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "fast_first_response_scheduled": True,
                        "fast_first_response": {
                            "scheduled": True,
                            "text": "Hello!",
                        },
                    },
                },
            }
        )

        response = await InteractionRuntime(
            AgentServices(
                ollama=_ExplodingOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        ).run(request)

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.speech, [])
        self.assertEqual(response.skills, [])
        self.assertIn(
            "runtime: terminal router greeting already spoken by fast-first",
            response.metadata.get("trace", []),
        )

    async def test_router_greeting_speak_first_is_terminal_when_not_pre_scheduled(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "greeting-terminal-legacy-test",
                "text": "Hello.",
                "language": "en-US",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "greeting",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                    "speak_first": "Hi!",
                },
            }
        )

        response = await InteractionRuntime(
            AgentServices(
                ollama=_ExplodingOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        ).run(request)

        self.assertEqual(response.status, "ok")
        self.assertEqual([item.text for item in response.speech], ["Hi!"])
        self.assertEqual(response.skills, [])
        self.assertIn(
            "runtime: terminal router greeting fast-first; skipped agent rewrite",
            response.metadata.get("trace", []),
        )


if __name__ == "__main__":
    unittest.main()
