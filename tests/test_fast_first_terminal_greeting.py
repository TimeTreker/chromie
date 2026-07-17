from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest


class _ExplodingOllama:
    async def generate(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - must not be called
        raise AssertionError("terminal router greeting must not call conversation LLM")


class FastFirstTerminalGreetingTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_router_greeting_skips_agent_rewrite(self) -> None:
        cases = (
            {
                "name": "already_scheduled",
                "text": "Hello, how are you.",
                "metadata": {
                    "fast_first_response_scheduled": True,
                    "fast_first_response": {
                        "scheduled": True,
                        "text": "Hello!",
                    },
                },
                "speak_first": None,
                "expected_speech": [],
                "trace": "runtime: terminal router greeting already spoken by fast-first",
            },
            {
                "name": "speak_first_not_pre_scheduled",
                "text": "Hello.",
                "metadata": {},
                "speak_first": "Hi!",
                "expected_speech": ["Hi!"],
                "trace": "runtime: terminal router greeting fast-first; skipped agent rewrite",
            },
        )

        for case in cases:
            with self.subTest(case=case["name"]):
                route_decision = {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "greeting",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": case["metadata"],
                }
                if case["speak_first"] is not None:
                    route_decision["speak_first"] = case["speak_first"]

                request = AgentRunRequest.model_validate(
                    {
                        "sid": f"greeting-terminal-{case['name']}",
                        "text": case["text"],
                        "language": "en-US",
                        "route_decision": route_decision,
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
                self.assertEqual(
                    [item.text for item in response.speech],
                    case["expected_speech"],
                )
                self.assertEqual(response.skills, [])
                self.assertIn(case["trace"], response.metadata.get("trace", []))


if __name__ == "__main__":
    unittest.main()
