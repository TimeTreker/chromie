from __future__ import annotations

import re

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class MotionPlannerAgent(BaseAgent):
    name = "motion_planner_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.context.get("allow_legacy_rule_agents") is not True:
            self.trace(result, "legacy rule agent disabled")
            return result
        if request.route_decision.route != "robot_action" and self.name not in request.route_decision.agents:
            return result

        action = self._plan_motion(request)
        if action is None:
            self.trace(result, "no motion action matched")
            return result

        result.add_action(
            "motion_controller",
            action["type"],
            params=action.get("params", {}),
            blocking=action.get("blocking", False),
            timeout_ms=action.get("timeout_ms", 3000),
            requires_confirmation=action.get("requires_confirmation", False),
            reason=action.get("reason"),
        )
        self.trace(result, f"planned {action['type']}")
        return result

    def _plan_motion(self, request: AgentRunRequest) -> dict | None:
        text = request.text.lower()
        intent = request.route_decision.intent.lower()

        if any(word in text for word in ["停下", "停止移动", "stop moving", "stop motion"]):
            return {"type": "motion.stop", "params": {}, "timeout_ms": 500, "blocking": True}

        # Avoid interpreting pose phrases like "转过来" as navigation.
        if any(word in text for word in ["转过来", "转过身", "回过头", "turn around"]):
            return None

        if any(word in text for word in ["过来", "靠近", "come here", "come closer"]):
            return {
                "type": "navigate.to_user",
                "params": {"stop_distance_m": 0.8, "max_speed_mps": 0.25, "avoid_obstacles": True},
                "timeout_ms": 10000,
                "requires_confirmation": False,
                "reason": "move_toward_user",
            }

        if any(word in text for word in ["后退", "退后", "back up", "move back"]):
            return {
                "type": "motion.move_relative",
                "params": {"x_m": -self._extract_distance(text, default=0.3), "y_m": 0.0, "max_speed_mps": 0.2},
                "timeout_ms": 3000,
            }

        if any(word in text for word in ["前进", "往前", "move forward", "go forward"]):
            return {
                "type": "motion.move_relative",
                "params": {"x_m": self._extract_distance(text, default=0.3), "y_m": 0.0, "max_speed_mps": 0.2},
                "timeout_ms": 3000,
            }

        if "navigate" in intent or "move" in intent:
            return {
                "type": "motion.intent_unresolved",
                "params": {"intent": request.route_decision.intent, "text": request.text},
                "requires_confirmation": True,
                "reason": "motion_intent_needs_clarification",
            }

        return None

    def _extract_distance(self, text: str, *, default: float) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:米|m|meter|meters)", text)
        if not match:
            return default
        value = float(match.group(1))
        return max(0.05, min(value, 1.0))
