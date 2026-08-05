from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent.app.cognitive_core.goal_interpreter.config import goal_interpretation_mode_from_env
from agent.app.cognitive_core.goal_interpreter.fallback import (
    InterpretationUnavailableError,
    fallback_decision,
)
from agent.app.cognitive_core.goal_interpreter.rules import route_by_priority_rules
from agent.app.cognitive_core.goal_interpreter.schema import RouteRequest


class GoalInterpreterCoreTests(unittest.TestCase):
    def test_rules_route_interrupt_without_agent(self) -> None:
        for text in (
            "stop",
            "Stop!",
            "cancel?",
            "Please stop.",
            "Can you stop please?",
            "Could you please stop?",
            "Stop moving right now.",
            "Stop talking for a moment.",
            "Please stop talking for a second.",
            "Stop speaking, please.",
            "Don't speak anymore.",
            "Could you stop talking for a while?",
            "Emergency stop!",
            "E stop!",
            "停止移动",
            "请停止移动",
            "急停！",
            "紧急停止一下",
            "请急停一下",
        ):
            with self.subTest(text=text):
                decision = route_by_priority_rules(RouteRequest(sid="s1", text=text))

                self.assertIsNotNone(decision)
                assert decision is not None
                self.assertEqual(decision.route, "interrupt")
                self.assertTrue(decision.interrupt_current)
                self.assertFalse(decision.needs_agent)
                self.assertFalse(decision.should_speak)

    def test_priority_rules_route_motion_stop_before_model(self) -> None:
        decision = route_by_priority_rules(
            RouteRequest(sid="s-stop", text="Stop moving right now.")
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.route, "interrupt")
        self.assertEqual(decision.source, "rules")
        self.assertTrue(decision.interrupt_current)
        self.assertFalse(decision.needs_agent)
        self.assertFalse(decision.should_speak)
        self.assertEqual(
            decision.metadata["reflex_outcome"]["trigger"],
            "stop_command",
        )

    def test_priority_rules_do_not_stop_on_negated_or_contextual_stop(self) -> None:
        for text in (
            "Don't stop talking.",
            "Do not stop speaking.",
            "Can you explain what stop means?",
            "The stop sign is red.",
            "Stop by the table means visit the table.",
            "What does emergency stop mean?",
            "The emergency stop button is red.",
            "Don't emergency stop the robot.",
            "What does E stop mean?",
            "Please explain the phrase 'stop talking for a moment'.",
            "请解释什么是急停。",
            "不要急停。",
        ):
            with self.subTest(text=text):
                self.assertIsNone(route_by_priority_rules(RouteRequest(sid="s-safe", text=text)))

    def test_priority_rules_ignore_repeated_ack_hallucination(self) -> None:
        text = "All right. All right. All right. All right. All right. All right."

        decision = route_by_priority_rules(RouteRequest(sid="s-ack", text=text))

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.route, "ignore")
        self.assertEqual(decision.intent, "repeated_filler_or_asr_hallucination")
        self.assertFalse(decision.needs_agent)
        self.assertFalse(decision.should_speak)

    def test_priority_rules_do_not_ignore_ack_with_meaningful_request(self) -> None:
        for text in (
            "All right, walk forward quickly.",
            "All right. All right. Can you walk forward quickly?",
            "All right. All right. All right. All right. Walk forward quickly.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(route_by_priority_rules(RouteRequest(sid="s-command", text=text)))

    def test_rules_only_no_match_reports_interpretation_unavailable(self) -> None:
        request = RouteRequest(sid="s3", text="tell me something unusual")

        self.assertIsNone(route_by_priority_rules(request))
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "rules_only_no_match",
        ):
            fallback_decision(request, reason="rules_only_no_match")

    def test_fallback_never_assigns_a_semantic_lane_to_non_empty_input(self) -> None:
        cases = (
            "Remember that my favorite color is blue.",
            "Can you check whether it will rain today?",
            "Please think carefully and split the work to add long-term memory to Chromie.",
        )
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    InterpretationUnavailableError,
                    "goal_interpreter_error:ReadTimeout",
                ):
                    fallback_decision(
                        RouteRequest(sid="fallback-semantic", text=text),
                        reason="goal_interpreter_error:ReadTimeout",
                    )

    def test_fallback_still_ignores_empty_input(self) -> None:
        decision = fallback_decision(
            RouteRequest(sid="empty", text="  "),
            reason="rules_only_no_match",
        )

        self.assertEqual(decision.route, "ignore")
        self.assertEqual(decision.intent, "empty_input")
        self.assertFalse(decision.needs_agent)


    def test_route_decision_preserves_fast_speech_contract(self) -> None:
        from agent.app.cognitive_core.goal_interpreter.schema import RouteDecision

        decision = RouteDecision.model_validate({
            "route": "tool",
            "intent": "weather_query",
            "confidence": 0.91,
            "fast_speech": {
                "text": "好的，我查一下北京今天的天气。",
                "purpose": "acknowledge_and_check",
                "commitment": "checking_only",
                "must_not_claim_completion": True,
            },
            "routes": [
                {
                    "route": "tool",
                    "intent": "weather_query",
                    "confidence": 0.91,
                    "lane": "tool",
                    "fast_speech": {
                        "text": "好的，我查一下北京今天的天气。",
                        "purpose": "acknowledge_and_check",
                    },
                }
            ],
        })

        self.assertEqual(decision.fast_speech.text, "好的，我查一下北京今天的天气。")
        self.assertEqual(decision.fast_speech.commitment, "checking_only")
        self.assertEqual(decision.routes[0].fast_speech.purpose, "acknowledge_and_check")

    def test_goal_interpreter_use_llm_controls_default_mode(self) -> None:
        with patch.dict(os.environ, {"AGENT_GOAL_INTERPRETER_USE_LLM": "0"}, clear=True):
            self.assertEqual(goal_interpretation_mode_from_env(), "rules_only")
        with patch.dict(os.environ, {"AGENT_GOAL_INTERPRETER_USE_LLM": "1"}, clear=True):
            self.assertEqual(goal_interpretation_mode_from_env(), "hybrid")
        with patch.dict(os.environ, {"AGENT_GOAL_INTERPRETER_USE_LLM": "0", "AGENT_GOAL_INTERPRETER_MODE": "llm_only"}, clear=True):
            self.assertEqual(goal_interpretation_mode_from_env(), "llm_only")
