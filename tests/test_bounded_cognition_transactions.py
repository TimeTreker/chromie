from __future__ import annotations

import unittest
from unittest import mock

from agent.app.cognitive_core.goal_interpreter import engine
from agent.app.cognitive_core.goal_interpreter.fallback import (
    InterpretationUnavailableError,
)
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    RouteDecision,
    RouteRequest,
)


class GoalInterpreterTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_primary_dto_gets_exactly_one_mechanical_repair(self) -> None:
        class Interpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                del payload
                self.stages.append(stage)
                if stage == "quick_intent":
                    return {
                        "message": {
                            "content": (
                                '{"route":"chat","intent":"general_conversation",'
                                '"confidence":"invalid","fast_speech":null,'
                                '"progress":[]}'
                            )
                        }
                    }
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"general_conversation",'
                            '"confidence":0.91,"fast_speech":null,"progress":[]}'
                        )
                    }
                }

        interpreter = Interpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="Tell me something interesting.",
                context={"gateway_admission_complete": True},
            )
        )

        self.assertEqual(
            interpreter.stages,
            ["quick_intent", "quick_intent_contract_repair"],
        )
        transaction = decision.metadata["goal_interpreter_transaction"]
        self.assertEqual(transaction["logical_invocation_count"], 2)
        self.assertEqual(transaction["logical_invocation_budget"], 2)
        self.assertTrue(transaction["contract_repair_attempted"])
        self.assertFalse(transaction["semantic_repair_attempted"])

    async def test_invalid_repaired_dto_fails_closed_after_two_calls(self) -> None:
        class Interpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                del payload
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"general_conversation",'
                            '"confidence":"still-invalid"}'
                        )
                    }
                }

        interpreter = Interpreter()
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "after_one_dto_repair",
        ):
            await interpreter.route(
                RouteRequest(
                    text="Tell me something interesting.",
                    context={"gateway_admission_complete": True},
                )
            )

        self.assertEqual(
            interpreter.stages,
            ["quick_intent", "quick_intent_contract_repair"],
        )

    async def test_semantic_contract_failure_is_not_repaired_online(self) -> None:
        class Interpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="quality-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                del payload
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"tool",'
                            '"confidence":0.95,"fast_speech":null,"progress":[]}'
                        )
                    }
                }

        interpreter = Interpreter()
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "route_name_intent_mismatch",
        ):
            await interpreter.route(
                RouteRequest(
                    text="What is the weather?",
                    context={"gateway_admission_complete": True},
                )
            )

        self.assertEqual(interpreter.stages, ["quick_intent"])

    async def test_placeholder_capability_fails_closed_without_reviewer(self) -> None:
        class Interpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="quality-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                del payload
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"robot_action","intent":"capability",'
                            '"confidence":0.91,"fast_speech":null,"progress":[]}'
                        )
                    }
                }

        interpreter = Interpreter()
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "placeholder_capability_intent",
        ):
            await interpreter.route(
                RouteRequest(
                    text="Please move.",
                    context={"gateway_admission_complete": True},
                )
            )

        self.assertEqual(interpreter.stages, ["quick_intent"])

    async def test_valid_generic_chat_is_terminal_even_with_affordances(self) -> None:
        class Interpreter(OllamaGoalInterpreter):
            def __init__(self) -> None:
                super().__init__(
                    ollama_url="http://example.invalid",
                    model="quick-model",
                    review_model="quality-model",
                    timeout_ms=800,
                    confidence_threshold=0.55,
                )
                self.stages: list[str] = []

            async def _chat(self, payload: dict, *, stage: str = "unknown") -> dict:
                del payload
                self.stages.append(stage)
                return {
                    "message": {
                        "content": (
                            '{"route":"chat","intent":"user_question",'
                            '"confidence":0.94,"fast_speech":null,"progress":[]}'
                        )
                    }
                }

        interpreter = Interpreter()
        decision = await interpreter.route(
            RouteRequest(
                text="Hello, how are you?",
                context={
                    "gateway_admission_complete": True,
                    "common_ability_catalog": [
                        {
                            "capability_id": "chromie.weather.lookup",
                            "route": "tool",
                            "available": True,
                            "interaction_executable": True,
                        }
                    ],
                },
            )
        )

        self.assertEqual(decision.route, "chat")
        self.assertEqual(interpreter.stages, ["quick_intent"])
        self.assertEqual(
            decision.metadata["goal_interpreter_transaction"][
                "logical_invocation_count"
            ],
            1,
        )


class DeepThinkingHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_confidence_chat_uses_existing_deep_thinking_handoff(self) -> None:
        class Catalog:
            async def snapshot(self) -> dict:
                return {"catalog_version": 1, "capabilities": []}

        class Interpreter:
            async def route(self, request: RouteRequest) -> RouteDecision:
                del request
                return RouteDecision(
                    route="chat",
                    intent="uncertain_explanation",
                    confidence=0.31,
                    source="llm",
                    reason="fast interpretation is uncertain",
                )

        request = RouteRequest(
            text="Please reason carefully about the trade-offs in this design.",
            language="en-US",
            context={"gateway_admission_complete": True},
        )
        with mock.patch.object(engine.settings, "mode", "hybrid"), mock.patch.object(
            engine.settings, "confidence_threshold", 0.55
        ), mock.patch.object(engine, "capability_catalog", Catalog()), mock.patch.object(
            engine, "goal_interpreter", Interpreter()
        ):
            decision = await engine.interpret_turn(request)

        self.assertEqual(decision.route, "deep_thought")
        self.assertEqual(decision.intent, "deep_thought_low_confidence")
        review = decision.metadata["fast_goal_interpreter_review_request"]
        self.assertEqual(review["quick_route"], "chat")
        self.assertEqual(review["execution_state"], "not_committed")
        self.assertIn("deepthinking_agent", decision.agents)


if __name__ == "__main__":
    unittest.main()
