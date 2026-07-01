from __future__ import annotations

import unittest

from agent.app.agents import AgentServices, SpeakerAgent
from agent.app.schema import AgentResult, AgentRunRequest


def _chat_request() -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "speaker-test",
            "text": "Why is the first answer important?",
            "route_decision": {
                "route": "chat",
                "agents": ["speaker_agent"],
                "intent": "general_conversation",
                "confidence": 0.9,
                "language": "en-US",
                "source": "llm",
            },
        }
    )


class SpeakerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_internal_skill_id_before_tts(self) -> None:
        result = AgentResult()
        result.add_speak_immediate(
            "soridormi.nod_yes. Short first voice responses feel faster."
        )

        updated = await SpeakerAgent(AgentServices(max_speak_chars=220)).run(
            _chat_request(),
            result,
        )

        self.assertEqual(
            updated.speak_immediate[0].text,
            "Short first voice responses feel faster.",
        )
        self.assertNotIn("soridormi", updated.speak_immediate[0].text)

    async def test_internal_only_speech_falls_back_after_filtering(self) -> None:
        result = AgentResult()
        result.add_speak_immediate("soridormi.express_attention.")

        updated = await SpeakerAgent(AgentServices(max_speak_chars=220)).run(
            _chat_request(),
            result,
        )

        self.assertEqual(updated.speak_immediate[0].text, "I understand.")

    async def test_filters_internal_plan_labels_before_tts(self) -> None:
        result = AgentResult()
        result.add_speak_immediate(
            'I\'ll get moving. Execute soridormi.walk_forward with speed="quick".'
        )
        result.add_speak_immediate("Task Split: 1.")
        result.add_speak_immediate(
            'Execute soridormi.walk_forward with speed="quick".'
        )
        result.add_speak_immediate("Key Risk: duration is near a safety limit.")
        result.add_speak_immediate("Next Step: initiating the walk command now.")

        updated = await SpeakerAgent(AgentServices(max_speak_chars=220)).run(
            _chat_request(),
            result,
        )

        self.assertEqual(len(updated.speak_immediate), 1)
        self.assertEqual(updated.speak_immediate[0].text, "I'll get moving.")


if __name__ == "__main__":
    unittest.main()
