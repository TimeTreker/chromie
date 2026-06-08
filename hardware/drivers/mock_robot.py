from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

try:
    from ..schema import ActionCommand, ActionResult, ActionStatus, RobotState
except ImportError:  # pragma: no cover - direct script launch
    from schema import ActionCommand, ActionResult, ActionStatus, RobotState


class MockRobotDriver:
    """Safe fake robot driver used for local integration tests."""

    name = "mock"

    def __init__(self) -> None:
        self._emergency_stopped = False
        self._is_moving = False
        self._pose: dict[str, Any] = {
            "head_yaw_degrees": 0.0,
            "head_pitch_degrees": 0.0,
            "body_yaw_degrees": 0.0,
            "led": "off",
        }
        self._last_action_id: str | None = None

    def state(self) -> RobotState:
        return RobotState(
            driver=self.name,
            ready=True,
            emergency_stopped=self._emergency_stopped,
            is_moving=self._is_moving,
            pose=dict(self._pose),
            battery=1.0,
            last_action_id=self._last_action_id,
        )

    async def emergency_stop(self) -> RobotState:
        self._emergency_stopped = True
        self._is_moving = False
        return self.state()

    async def reset_emergency_stop(self) -> RobotState:
        self._emergency_stopped = False
        return self.state()

    async def execute(self, command: ActionCommand) -> ActionResult:
        started = datetime.now(timezone.utc)

        if self._emergency_stopped and command.type != "system.reset_emergency_stop":
            return ActionResult(
                id=command.id,
                status=ActionStatus.REJECTED,
                target=command.target,
                type=command.type,
                error="hardware is emergency stopped",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )

        self._last_action_id = command.id
        self._is_moving = command.type.startswith(("head.", "body.", "navigate.", "gesture."))

        try:
            result = await self._apply(command)
            status = ActionStatus.COMPLETED
            message = "completed"
            error = None
        except Exception as exc:  # defensive: daemon should return structured failures
            result = {}
            status = ActionStatus.FAILED
            message = "failed"
            error = str(exc)
        finally:
            self._is_moving = False

        return ActionResult(
            id=command.id,
            status=status,
            target=command.target,
            type=command.type,
            message=message,
            result=result,
            error=error,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )

    async def _apply(self, command: ActionCommand) -> dict[str, Any]:
        params = command.params
        duration_ms = int(params.get("duration_ms", 100))
        await asyncio.sleep(max(0, min(duration_ms, 2000)) / 1000.0)

        if command.type == "head.turn":
            self._pose["head_yaw_degrees"] = float(params.get("yaw_degrees", 0.0))
            self._pose["head_pitch_degrees"] = float(params.get("pitch_degrees", 0.0))
        elif command.type == "head.look_at_user":
            self._pose["head_yaw_degrees"] = 0.0
            self._pose["head_pitch_degrees"] = 0.0
            self._pose["tracking"] = "user"
        elif command.type == "body.rotate":
            delta = float(params.get("yaw_degrees", 0.0))
            self._pose["body_yaw_degrees"] = float(self._pose.get("body_yaw_degrees", 0.0)) + delta
        elif command.type == "led.set":
            self._pose["led"] = str(params.get("color", "white"))
        elif command.type == "gesture.wave":
            self._pose["last_gesture"] = "wave"
        elif command.type == "navigate.to_user":
            self._pose["navigation"] = {
                "target": "user",
                "stop_distance_m": float(params.get("stop_distance_m", 0.8)),
            }
        elif command.type == "system.reset_emergency_stop":
            self._emergency_stopped = False
        else:
            # Mock accepts unknown commands so integration can continue.
            self._pose["last_unknown_action"] = command.type

        return {"state": self.state().model_dump(mode="json")}
