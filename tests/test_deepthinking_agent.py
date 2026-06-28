from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices, DeepThinkingAgent
from agent.app.schema import AgentResult, AgentRunRequest


class _CapturingOllama:
    def __init__(self, response: Any | list[Any] = "Here is the architecture I recommend.") -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class DeepThinkingAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_thinking_prompt_uses_session_memory_and_larger_budget(self) -> None:
        ollama = _CapturingOllama()
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-test",
                "text": "Let's design the session memory architecture carefully.",
                "context": {
                    "mind": {
                        "prompt_summary": (
                            "Core principles, owner-approved and not experience-mutable: "
                            "protect humans; no raw low-level body commands."
                        )
                    },
                    "session_memory": {
                        "conversation_id": "local_default",
                        "current_task": {"summary": "design session memory"},
                        "forgetting_policy": {"hard_idle_timeout_sec": 900},
                    }
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "session_memory_design",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Here is the architecture I recommend.")
        self.assertIn("deepthinking_agent", result.handled_by)
        self.assertEqual(len(ollama.calls), 1)
        call = ollama.calls[0]
        self.assertIn("deepthinking agent", call["system"])
        self.assertIn("split complex requests", call["system"])
        self.assertIn("human owner approval", call["system"])
        self.assertIn("Normally do not repeat, quote, or paraphrase", call["system"])
        self.assertIn("Session working memory", call["prompt"])
        self.assertIn("Mind principles, long-term goals, and experience boundaries", call["prompt"])
        self.assertIn("owner-approved", call["prompt"])
        self.assertIn("design session memory", call["prompt"])
        self.assertEqual(call["options"]["num_ctx"], 8192)
        self.assertEqual(call["options"]["num_predict"], 384)

    async def test_conversation_agent_is_not_required_for_deep_thought(self) -> None:
        ollama = _CapturingOllama("First, split the work into memory, routing, and validation.")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=70,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-test",
                "text": "Please split this implementation task.",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "implementation_planning",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("deepthinking_agent", result.handled_by)
        self.assertNotIn("conversation_agent", result.handled_by)
        self.assertGreater(len(result.speak_immediate), 0)

    async def test_completed_pending_tasks_are_not_fed_as_active_context(self) -> None:
        ollama = _CapturingOllama("Let's reason about the claim directly.")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-completed-task-context-test",
                "text": "Think carefully about whether the sun is cold.",
                "context": {
                    "active_pending_tasks": [],
                    "pending_tasks": [
                        {
                            "type": "robot_action",
                            "status": "done",
                            "summary": "soridormi.walk_forward",
                        }
                    ],
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "reasoning",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        await agent.run(request, AgentResult())

        self.assertEqual(len(ollama.calls), 1)
        prompt = ollama.calls[0]["prompt"]
        self.assertIn("Pending tasks:\nNone", prompt)
        self.assertNotIn("soridormi.walk_forward", prompt)

    async def test_stock_model_disclaimer_is_retried_as_chromie(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have personal opinions on whether the sun is hot.",
                {
                    "decision": "revise",
                    "reason": "Objective fact should be answered directly.",
                    "spoken_response": "Yes. The Sun is extremely hot.",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-sun-hot-retry-test",
                "text": "Do you think the sun is hot?",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Yes. The Sun is extremely hot.")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Chromie's first-person robot persona", ollama.calls[0]["system"])
        self.assertIn("Candidate spoken response", ollama.calls[1]["prompt"])
        self.assertIn("Judge meaning, not keyword rules", ollama.calls[1]["system"])

    async def test_empty_joke_acknowledgement_is_retried_in_deep_thought(self) -> None:
        ollama = _CapturingOllama(
            [
                "I can tell you a joke. Why not?",
                {
                    "decision": "revise",
                    "reason": "The candidate repeats an empty promise instead of telling the joke.",
                    "spoken_response": "Why did Chromie take a nap? To reboot her sparkle.",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-joke-empty-ack-test",
                "text": "If you can, just tell me. Why not?",
                "context": {
                    "history": [
                        {"role": "user", "text": "Hey, can you tell me a joke?"},
                        {"role": "assistant", "text": "I can tell you a joke."},
                    ],
                    "current_task_context": {
                        "task_id": "task-joke",
                        "task_type": "conversation",
                        "goal": "Tell the user a joke.",
                        "last_meaningful_user_turn": "Hey, can you tell me a joke?",
                        "last_assistant_response": "I can tell you a joke.",
                    },
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Why did Chromie take a nap? To reboot her sparkle.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Tell the user a joke.", ollama.calls[1]["prompt"])

    async def test_truncated_one_character_response_is_replaced_before_tts(self) -> None:
        ollama = _CapturingOllama(
            [
                "I",
                {
                    "decision": "accept",
                    "reason": "bad reviewer accepted a fragment",
                    "spoken_response": "",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-truncated-output-test",
                "text": "Can you walk forward for 15 minutes?",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.0,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I got stuck forming that answer. Please say it again.",
        )
        self.assertEqual(len(ollama.calls), 2)


if __name__ == "__main__":
    unittest.main()
