from __future__ import annotations

import unittest

from orchestrator.runtime.executor import AgentResultExecutor
from orchestrator.schemas.action import ActionCommand, ActionResult
from orchestrator.schemas.agent import AgentResult


class _RecordingActionClient:
    def __init__(self) -> None:
        self.calls: list[ActionCommand] = []

    async def execute(self, session: object, action: ActionCommand) -> ActionResult:
        self.calls.append(action)
        return ActionResult(
            id=action.id,
            target=action.target,
            type=action.type,
            status="completed",
        )


class ActionExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_required_action_is_not_sent(self) -> None:
        client = _RecordingActionClient()
        executor = AgentResultExecutor(client)  # type: ignore[arg-type]
        result = AgentResult(
            actions=[
                ActionCommand(
                    target="motion_controller",
                    type="motion.intent_unresolved",
                    requires_confirmation=True,
                )
            ],
            requires_confirmation=True,
        )

        execution = await executor.execute_actions(object(), result)

        self.assertEqual(client.calls, [])
        self.assertEqual(execution[0].status, "skipped")
        self.assertEqual(execution[0].message, "confirmation_required")

    async def test_confirmed_action_is_sent(self) -> None:
        client = _RecordingActionClient()
        executor = AgentResultExecutor(client)  # type: ignore[arg-type]
        result = AgentResult(
            actions=[
                ActionCommand(
                    target="robot_pose_controller",
                    type="head.turn",
                    params={"yaw_degrees": 10},
                )
            ]
        )

        execution = await executor.execute_actions(object(), result)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(execution[0].status, "completed")
