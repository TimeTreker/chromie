from __future__ import annotations

import unittest

from agent.app.agents import AgentServices, MemoryAgent
from agent.app.schema import AgentResult, AgentRunRequest


class MemoryAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_agent_emits_refined_session_memory_entry(self) -> None:
        agent = MemoryAgent(AgentServices(use_llm=False))
        request = AgentRunRequest.model_validate(
            {
                "sid": "memory-test",
                "text": "Please remember that I prefer jasmine tea without sugar.",
                "route_decision": {
                    "route": "memory",
                    "agents": ["memory_agent", "speaker_agent"],
                    "intent": "remember_user_preference",
                    "confidence": 0.92,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        extracted = result.memory_updates[0]
        self.assertEqual(extracted.type, "extracted_memory")
        self.assertEqual(extracted.key, "preference")
        self.assertEqual(extracted.value["scope"], "session")
        self.assertEqual(extracted.value["kind"], "preference")
        self.assertEqual(
            extracted.value["text"],
            "User asked Chromie to remember: I prefer jasmine tea without sugar.",
        )
        self.assertEqual(result.memory_updates[1].type, "user_statement")
        self.assertEqual(result.speak_immediate[0].text, "I will remember that.")


if __name__ == "__main__":
    unittest.main()

