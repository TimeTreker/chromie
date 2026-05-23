from __future__ import annotations

import re

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class RobotPoseControllerAgent(BaseAgent):
    name = "robot_pose_controller_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if request.route_decision.route != "robot_action" and self.name not in request.route_decision.agents:
            return result

        action = self._plan_pose_action(request)
        if action is None:
            self.trace(result, "no pose action matched")
            return result

        result.add_action(
            "robot_pose_controller",
            action["type"],
            params=action.get("params", {}),
            blocking=action.get("blocking", False),
            timeout_ms=action.get("timeout_ms", 1500),
            reason=action.get("reason"),
        )
        self.trace(result, f"planned {action['type']}")
        return result

    def _plan_pose_action(self, request: AgentRunRequest) -> dict | None:
        text = request.text.lower()
        intent = request.route_decision.intent.lower()

        if any(key in intent for key in ["look_at_user", "face_user"]):
            return {"type": "head.look_at_user", "params": {"duration_ms": 3000}, "timeout_ms": 1200}

        if any(word in text for word in ["看着我", "看我", "look at me", "face me"]):
            return {"type": "head.look_at_user", "params": {"duration_ms": 3000}, "timeout_ms": 1200}

        if any(word in text for word in ["点头", "nod"]):
            return {"type": "head.nod", "params": {"times": 1}, "timeout_ms": 1000}

        if any(word in text for word in ["摇头", "shake your head"]):
            return {"type": "head.shake", "params": {"times": 1}, "timeout_ms": 1000}

        if any(word in text for word in ["左转", "往左", "turn left", "look left"]):
            return {
                "type": "head.turn",
                "params": {"yaw_degrees": -self._extract_degrees(text, default=20), "pitch_degrees": 0, "duration_ms": 700},
                "timeout_ms": 1200,
            }

        if any(word in text for word in ["右转", "往右", "turn right", "look right"]):
            return {
                "type": "head.turn",
                "params": {"yaw_degrees": self._extract_degrees(text, default=20), "pitch_degrees": 0, "duration_ms": 700},
                "timeout_ms": 1200,
            }

        if any(word in text for word in ["抬头", "look up"]):
            return {
                "type": "head.turn",
                "params": {"yaw_degrees": 0, "pitch_degrees": 12, "duration_ms": 600},
                "timeout_ms": 1000,
            }

        if any(word in text for word in ["低头", "look down"]):
            return {
                "type": "head.turn",
                "params": {"yaw_degrees": 0, "pitch_degrees": -12, "duration_ms": 600},
                "timeout_ms": 1000,
            }

        if any(word in text for word in ["回正", "正前方", "center", "straight ahead"]):
            return {"type": "head.center", "params": {"duration_ms": 600}, "timeout_ms": 1000}

        if any(word in text for word in ["挥手", "wave"]):
            return {"type": "gesture.wave", "params": {"hand": "auto", "times": 1}, "timeout_ms": 1800}

        return None

    def _extract_degrees(self, text: str, *, default: int) -> int:
        match = re.search(r"(\d{1,3})\s*(?:度|degrees?|deg)?", text)
        if not match:
            return default
        value = int(match.group(1))
        return max(5, min(value, 45))
