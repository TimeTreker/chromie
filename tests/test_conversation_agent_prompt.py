from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices, ConversationAgent
from agent.app.schema import AgentResult, AgentRunRequest


class _CapturingOllama:
    def __init__(self, response: str = "Here is a little song I made for you.") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.response


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
                "context": {
                    "mind": {
                        "prompt_summary": (
                            "Core principles, owner-approved and not experience-mutable: "
                            "protect humans; be honest about abilities."
                        )
                    }
                },
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
        prompt = ollama.calls[0]["prompt"]
        self.assertIn("sing original lyrics", system)
        self.assertIn("split them into spoken sections", system)
        self.assertIn("Do not quote copyrighted lyrics", system)
        self.assertIn("do not say you are not programmed to sing", system)
        self.assertIn("mind principles", system)
        self.assertIn("Mind principles and long-term goals", prompt)
        self.assertIn("owner-approved", prompt)

    async def test_long_song_response_is_split_into_tts_sized_sections(self) -> None:
        response = (
            "Verse one glows softly under a friendly moon. "
            "Verse two keeps walking through a field of tiny lights. "
            "Verse three comes home with a bright little chorus for you."
        )
        ollama = _CapturingOllama(response)
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=70,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "long-song-test",
                "text": "Please sing a long song for me.",
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

        self.assertGreater(len(result.speak_immediate), 1)
        self.assertTrue(all(len(item.text) <= 70 for item in result.speak_immediate))
        self.assertIn("Verse three", " ".join(item.text for item in result.speak_immediate))


if __name__ == "__main__":
    unittest.main()
