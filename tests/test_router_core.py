from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from router.app.config import router_mode_from_env
from router.app.fallback import fallback_decision
from router.app.rules import (
    route_by_deep_thought_rules,
    route_by_priority_rules,
    route_by_rules,
)
from router.app.schema import RouteRequest


class RouterCoreTests(unittest.TestCase):
    def test_rules_route_interrupt_without_agent(self) -> None:
        for text in ("stop", "Stop!", "cancel?", "Stop moving right now.", "停止移动"):
            with self.subTest(text=text):
                decision = route_by_rules(RouteRequest(sid="s1", text=text))

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

    def test_rules_route_robot_action(self) -> None:
        decision = route_by_rules(RouteRequest(sid="s2", text="turn left"))

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.route, "robot_action")
        self.assertEqual(decision.intent, "turn_left")
        self.assertEqual(decision.actions[0]["type"], "head.turn")

    def test_explicit_deep_thought_rule_routes_planning_requests(self) -> None:
        for text in (
            "Please think deeply and make an implementation plan.",
            "请深入思考并给我一个实现计划。",
        ):
            with self.subTest(text=text):
                decision = route_by_deep_thought_rules(RouteRequest(sid="deep", text=text))

                self.assertIsNotNone(decision)
                assert decision is not None
                self.assertEqual(decision.route, "deep_thought")
                self.assertEqual(decision.agents, ["deepthinking_agent", "speaker_agent"])
                self.assertEqual(decision.intent, "deep_thought_planning")
                self.assertTrue(decision.should_speak)

    def test_rules_only_fallback_routes_unknown_text_to_chat(self) -> None:
        request = RouteRequest(sid="s3", text="tell me something unusual")

        self.assertIsNone(route_by_rules(request))
        decision = fallback_decision(request, reason="rules_only_no_match")
        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")
        self.assertTrue(decision.needs_agent)

    def test_router_use_llm_controls_default_mode(self) -> None:
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "0"}, clear=True):
            self.assertEqual(router_mode_from_env(), "rules_only")
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "1"}, clear=True):
            self.assertEqual(router_mode_from_env(), "hybrid")
        with patch.dict(os.environ, {"ROUTER_USE_LLM": "0", "ROUTER_MODE": "llm_only"}, clear=True):
            self.assertEqual(router_mode_from_env(), "llm_only")
