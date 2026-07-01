from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from router.app.config import router_mode_from_env
from router.app.fallback import fallback_decision
from router.app.rules import route_by_priority_rules
from router.app.schema import RouteRequest


class RouterCoreTests(unittest.TestCase):
    def test_rules_route_interrupt_without_agent(self) -> None:
        for text in (
            "stop",
            "Stop!",
            "cancel?",
            "Please stop.",
            "Can you stop please?",
            "Could you please stop?",
            "Stop moving right now.",
            "停止移动",
            "请停止移动",
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

    def test_priority_rules_do_not_stop_on_negated_or_contextual_stop(self) -> None:
        for text in (
            "Don't stop talking.",
            "Do not stop speaking.",
            "Can you explain what stop means?",
            "The stop sign is red.",
            "Stop by the table means visit the table.",
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

    def test_rules_only_fallback_routes_unknown_text_to_chat(self) -> None:
        request = RouteRequest(sid="s3", text="tell me something unusual")

        self.assertIsNone(route_by_priority_rules(request))
        decision = fallback_decision(request, reason="rules_only_no_match")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")
        self.assertTrue(decision.needs_agent)

    def test_fallback_preserves_semantic_non_chat_lanes(self) -> None:
        cases = (
            (
                "Remember that my favorite color is blue.",
                "memory",
                "remember_user_preference",
            ),
            (
                "Can you check whether it will rain today?",
                "tool",
                "weather_query",
            ),
            (
                "Please think carefully and split the work to add long-term memory to Chromie.",
                "deep_thought",
                "deep_thought_planning",
            ),
        )
        for text, route, intent in cases:
            with self.subTest(text=text):
                decision = fallback_decision(
                    RouteRequest(sid="fallback-semantic", text=text),
                    reason="llm_router_error:ReadTimeout",
                )

                self.assertEqual(decision.route, route)
                self.assertEqual(decision.intent, intent)
                self.assertEqual(decision.source, "fallback")
                self.assertTrue(decision.needs_agent)

    def test_router_use_llm_controls_default_mode(self) -> None:
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "0"}, clear=True):
            self.assertEqual(router_mode_from_env(), "rules_only")
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "1"}, clear=True):
            self.assertEqual(router_mode_from_env(), "hybrid")
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "0", "ROUTER_MODE": "llm_only"}, clear=True):
            self.assertEqual(router_mode_from_env(), "llm_only")
