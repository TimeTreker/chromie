from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices, ConversationAgent
from agent.app.runtime import AgentRuntime, InteractionRuntime
from agent.app.schema import AgentResult, AgentRunRequest, sanitize_spoken_text


class _ExplodingOllama:
    async def generate(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - must not be called
        raise AssertionError("missing-capability clarify must not call conversation LLM")


class _BadOllama:
    async def generate(self, *args: Any, **kwargs: Any) -> str:
        return "好的，没问题。我会向前走15秒钟。 执行指令： soridormi.walk forward(duration s=15.0, speed='normal')"


def _request(*, speak_first: str | None = None) -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "missing-ability-test",
            "text": "往前走15秒钟。",
            "route_decision": {
                "route": "clarify",
                "agents": ["speaker_agent"],
                "intent": "missing_or_unsupported_ability",
                "confidence": 0.0,
                "language": "zh-CN",
                "source": "llm",
                "speak_first": speak_first,
            },
        }
    )


class MissingAbilityClarifyTerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_interaction_runtime_does_not_rewrite_missing_ability_after_fast_first(self) -> None:
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ExplodingOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        ).run(_request(speak_first=None))

        self.assertEqual(response.status, "clarify")
        self.assertEqual(response.speech, [])
        self.assertEqual(response.skills, [])
        self.assertIn(
            "runtime: terminal missing-ability clarify; skipped agent rewrite",
            response.metadata.get("trace", []),
        )

    async def test_legacy_runtime_returns_only_router_missing_ability_text(self) -> None:
        result = await AgentRuntime(
            AgentServices(
                ollama=_ExplodingOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        ).run(
            _request(
                speak_first="我没有找到能安全执行这个动作的对应技能，所以不会猜一个相似动作来做。"
            )
        )

        self.assertEqual(result.status, "clarify")
        self.assertEqual(len(result.speak_immediate), 1)
        self.assertIn("不会猜", result.speak_immediate[0].text)
        self.assertEqual(result.actions, [])

    async def test_conversation_guard_blocks_chinese_fake_execution_claim_if_reached(self) -> None:
        agent = ConversationAgent(
            AgentServices(
                ollama=_BadOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "conversation-guard-test",
                "text": "往前走15秒钟。",
                "route_decision": {
                    "route": "clarify",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "clarify_action",
                    "confidence": 0.4,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(len(result.speak_immediate), 1)
        self.assertIn("不会假装", result.speak_immediate[0].text)
        self.assertNotIn("执行指令", result.speak_immediate[0].text)
        self.assertNotIn("soridormi", result.speak_immediate[0].text.casefold())

    def test_sanitize_spoken_text_drops_chinese_internal_execution_tail(self) -> None:
        text = sanitize_spoken_text(
            "好的，没问题。 我会向前走15秒钟。 执行指令： soridormi.walk forward(duration s=15.0, speed='normal')"
        )

        self.assertEqual(text, "好的，没问题。 我会向前走15秒钟。")


if __name__ == "__main__":
    unittest.main()
