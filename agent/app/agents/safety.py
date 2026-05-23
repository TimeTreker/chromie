from __future__ import annotations

from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent


class SafetyAgent(BaseAgent):
    name = "safety_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        if not result.actions:
            self.trace(result, "no actions to validate")
            return result

        safe_actions = []
        blocked = []

        for action in result.actions:
            action = action.model_copy(deep=True)
            if action.target == "robot_pose_controller":
                self._clamp_pose_action(action)
            elif action.target == "motion_controller":
                ok, reason = self._validate_motion_action(request, action)
                if not ok:
                    blocked.append((action, reason))
                    continue
            safe_actions.append(action)

        result.actions = safe_actions

        if blocked:
            result.status = "blocked" if not safe_actions else result.status
            zh = self.is_zh(request)
            result.add_speak_immediate(
                "这个动作可能不安全，我先不执行。" if zh else "That motion may not be safe, so I will not do it.",
                style="warning",
                priority="high",
            )
            result.reason = "; ".join(reason for _, reason in blocked)
            self.trace(result, f"blocked {len(blocked)} action(s)")
        else:
            self.trace(result, f"validated {len(safe_actions)} action(s)")

        return result

    def _clamp_pose_action(self, action) -> None:
        if action.type == "head.turn":
            params = action.params
            params["yaw_degrees"] = max(-60, min(60, float(params.get("yaw_degrees", 0))))
            params["pitch_degrees"] = max(-30, min(30, float(params.get("pitch_degrees", 0))))
            params["duration_ms"] = max(100, min(3000, int(params.get("duration_ms", 700))))
        if action.type in {"head.nod", "head.shake", "gesture.wave"}:
            action.params["times"] = max(1, min(3, int(action.params.get("times", 1))))

    def _validate_motion_action(self, request: AgentRunRequest, action) -> tuple[bool, str]:
        if action.type == "motion.stop":
            return True, "ok"

        robot_state = request.context.get("robot_state") or {}
        if robot_state.get("emergency_stop"):
            return False, "robot_emergency_stop_active"

        if action.type == "motion.move_relative":
            x_m = abs(float(action.params.get("x_m", 0.0)))
            y_m = abs(float(action.params.get("y_m", 0.0)))
            max_speed = float(action.params.get("max_speed_mps", 0.2))
            if x_m > 1.0 or y_m > 1.0:
                return False, "relative_motion_too_large"
            if max_speed > 0.35:
                action.params["max_speed_mps"] = 0.35
            return True, "ok"

        if action.type == "navigate.to_user":
            distance = request.context.get("user_state", {}).get("distance_m")
            stop_distance = float(action.params.get("stop_distance_m", 0.8))
            if distance is not None and float(distance) < 0.5:
                return False, "user_already_too_close"
            if stop_distance < 0.6:
                action.params["stop_distance_m"] = 0.6
            action.params["max_speed_mps"] = min(float(action.params.get("max_speed_mps", 0.25)), 0.35)
            action.params["avoid_obstacles"] = bool(action.params.get("avoid_obstacles", True))
            return True, "ok"

        if action.requires_confirmation:
            return True, "needs_confirmation"

        return True, "ok"
