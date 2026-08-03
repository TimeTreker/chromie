from __future__ import annotations

import unittest

from agent.app.agents import AgentServices, MemoryAgent
from agent.app.schema import AgentResult, AgentRunRequest


class MemoryAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_agent_applies_model_authored_session_proposal(self) -> None:
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
                    "source": "llm",
                    "memory_update": {
                        "scope": "session",
                        "kind": "preference",
                        "key": "tea_preference",
                        "text": "User prefers jasmine tea without sugar.",
                        "persistence_policy": "ephemeral",
                        "confidence": 0.96,
                    },
                },
            }
        )

        result = await agent.run(request, AgentResult())

        extracted = result.memory_updates[0]
        self.assertEqual(extracted.type, "extracted_memory")
        self.assertEqual(extracted.key, "tea_preference")
        self.assertEqual(extracted.value["scope"], "session")
        self.assertEqual(extracted.value["kind"], "preference")
        self.assertEqual(extracted.value["text"], "User prefers jasmine tea without sugar.")
        self.assertEqual(extracted.confidence, 0.96)
        self.assertEqual(result.memory_updates[1].type, "user_statement")
        self.assertEqual(result.actions[0].params["text"], "User prefers jasmine tea without sugar.")
        self.assertEqual(result.speak_immediate, [])

    async def test_memory_agent_emits_typed_durable_forget(self) -> None:
        agent = MemoryAgent(AgentServices(use_llm=False))
        request = AgentRunRequest.model_validate(
            {
                "sid": "memory-forget",
                "text": "Forget my saved tea preference everywhere.",
                "route_decision": {
                    "route": "memory",
                    "agents": ["memory_agent"],
                    "intent": "forget_durable_preference",
                    "confidence": 0.95,
                    "source": "llm",
                    "memory_update": {
                        "operation": "forget",
                        "scope": "profile",
                        "kind": "preference",
                        "key": "tea_preference",
                        "text": "Forget the saved tea preference.",
                        "persistence_policy": "durable_with_explicit_consent",
                        "consent_basis": "explicit_current_turn",
                    },
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.memory_updates[0].type, "durable_memory_forget")
        self.assertEqual(result.memory_updates[0].key, "tea_preference")
        self.assertEqual(result.actions[0].type, "memory.forget")
        self.assertEqual(result.actions[0].target, "memory_store")

    async def test_memory_agent_missing_proposal_fails_closed_to_clarification(self) -> None:
        agent = MemoryAgent(AgentServices(use_llm=False))
        request = AgentRunRequest.model_validate(
            {
                "sid": "memory-missing",
                "text": "Please remember this.",
                "route_decision": {
                    "route": "memory",
                    "agents": ["memory_agent", "speaker_agent"],
                    "intent": "remember_session_note",
                    "confidence": 0.90,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.status, "clarify")
        self.assertEqual(result.reason, "memory_update_missing")
        self.assertEqual(result.memory_updates, [])
        self.assertEqual(result.actions, [])
        self.assertEqual(result.speak_immediate, [])

    async def test_memory_agent_does_not_reclassify_raw_user_text(self) -> None:
        agent = MemoryAgent(AgentServices(use_llm=False))
        request = AgentRunRequest.model_validate(
            {
                "sid": "memory-no-keywords",
                "text": "My favorite is irrelevant raw wording.",
                "route_decision": {
                    "route": "memory",
                    "agents": ["memory_agent"],
                    "intent": "remember_note",
                    "confidence": 0.88,
                    "language": "en-US",
                    "source": "llm",
                    "memory_update": {
                        "kind": "fact",
                        "text": "The user's project codename is Aurora.",
                        "confidence": 0.91,
                    },
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.memory_updates[0].value["kind"], "fact")
        self.assertEqual(
            result.memory_updates[0].value["text"],
            "The user's project codename is Aurora.",
        )


if __name__ == "__main__":
    unittest.main()
