from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices, ConversationAgent
from agent.app.schema import AgentResult, AgentRunRequest


class _CapturingOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return "Here is a little song I made for you."


class ConversationAgentPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_song_requests_are_left_to_llm_as_original_spoken_creativity(self) -> None:
        ollama = _CapturingOllama()
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "song-test",
                "text": "Go ahead and sing a song for me.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Here is a little song I made for you.")
        self.assertEqual(len(ollama.calls), 1)
        system = ollama.calls[0]["system"]
        self.assertIn("brief original verse", system)
        self.assertIn("continue in sections", system)
        self.assertIn("Do not quote copyrighted lyrics", system)
        self.assertIn("do not say you are not programmed to sing", system)


if __name__ == "__main__":
    unittest.main()
