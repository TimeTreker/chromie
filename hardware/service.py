from __future__ import annotations

try:
    from .drivers.mock_robot import MockRobotDriver
    from .schema import ActionCommand, ActionResult, ActionStatus
except ImportError:  # pragma: no cover - direct script launch
    from drivers.mock_robot import MockRobotDriver
    from schema import ActionCommand, ActionResult, ActionStatus


class HardwareService:
    """Transport-free hardware execution policy used by the HTTP daemon and tests."""

    def __init__(self, driver: MockRobotDriver | None = None) -> None:
        self.driver = driver or MockRobotDriver()
        self.action_results: dict[str, ActionResult] = {}

    async def execute(self, command: ActionCommand) -> ActionResult:
        if command.requires_confirmation:
            result = ActionResult(
                id=command.id,
                status=ActionStatus.REJECTED,
                target=command.target,
                type=command.type,
                error="action requires confirmation",
            )
        elif command.type.startswith("unsafe."):
            result = ActionResult(
                id=command.id,
                status=ActionStatus.REJECTED,
                target=command.target,
                type=command.type,
                error="unsafe action namespace is rejected",
            )
        else:
            result = await self.driver.execute(command)
        self.action_results[command.id] = result
        return result

    def get_action(self, action_id: str) -> ActionResult | None:
        return self.action_results.get(action_id)
