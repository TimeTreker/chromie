from __future__ import annotations

import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from agent.app.soridormi_task_client import (
    SoridormiTaskClient,
    SoridormiTaskClientError,
    SoridormiTaskMonitorTimeout,
    soridormi_client_task_ref,
    with_client_task_ref,
)
from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext


class RecordingInvoker:
    def __init__(
        self,
        handler: Callable[
            [str, dict[str, Any], ToolInvocationContext | None],
            ToolCallOutcome,
        ],
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []
        self._handler = handler

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        copied_args = dict(args)
        self.calls.append((tool_name, copied_args, context))
        return self._handler(tool_name, copied_args, context)


async def _no_sleep(_: float) -> None:
    return None


class SoridormiTaskClientTests(unittest.IsolatedAsyncioTestCase):
    def test_client_task_ref_is_stable_and_bounded(self) -> None:
        short = soridormi_client_task_ref("graph-1", "walk")
        long_a = soridormi_client_task_ref("graph-" + ("x" * 180), "walk")
        long_b = soridormi_client_task_ref("graph-" + ("x" * 179) + "y", "walk")

        self.assertEqual(short, "chromie:graph-1:walk")
        self.assertLessEqual(len(long_a), 128)
        self.assertEqual(long_a, soridormi_client_task_ref("graph-" + ("x" * 180), "walk"))
        self.assertNotEqual(long_a, long_b)

    def test_payload_copy_preserves_explicit_client_task_ref(self) -> None:
        payload = {"task_type": "move_velocity", "client_task_ref": "external-ref"}

        copied = with_client_task_ref(payload, graph_id="graph", node_id="node")

        self.assertEqual(copied["client_task_ref"], "external-ref")
        self.assertIsNot(copied, payload)

    async def test_submit_adds_graph_node_client_task_ref(self) -> None:
        def handler(
            tool_name: str,
            args: dict[str, Any],
            context: ToolInvocationContext | None,
        ) -> ToolCallOutcome:
            self.assertEqual(tool_name, "soridormi.task.submit")
            self.assertIsNone(context)
            return ToolCallOutcome.success(
                {
                    "task_id": "soridormi-task-1",
                    "client_task_ref": args["client_task_ref"],
                    "idempotent_replay": False,
                }
            )

        invoker = RecordingInvoker(handler)
        client = SoridormiTaskClient(invoker, sleep=_no_sleep)

        output = await client.submit(
            {"task_type": "move_velocity", "parameters": {"vx_mps": 0.2}},
            graph_id="bring-water",
            node_id="approach-kitchen",
        )

        self.assertEqual(output["task_id"], "soridormi-task-1")
        self.assertEqual(
            invoker.calls[0][1]["client_task_ref"],
            "chromie:bring-water:approach-kitchen",
        )

    async def test_monitor_advances_cursor_until_terminal(self) -> None:
        responses = iter(
            [
                ToolCallOutcome.success(
                    {
                        "task_id": "soridormi-task-1",
                        "terminal": False,
                        "next_after_sequence": 3,
                        "poll_recommendation": {
                            "action": "continue_polling_or_cancel",
                            "recommended_poll_interval_s": 0.0,
                        },
                    }
                ),
                ToolCallOutcome.success(
                    {
                        "task_id": "soridormi-task-1",
                        "terminal": True,
                        "next_after_sequence": 5,
                        "poll_recommendation": {"action": "stop_polling"},
                    }
                ),
            ]
        )

        def handler(
            tool_name: str,
            args: dict[str, Any],
            context: ToolInvocationContext | None,
        ) -> ToolCallOutcome:
            self.assertEqual(tool_name, "soridormi.task.events")
            self.assertIsNone(context)
            return next(responses)

        invoker = RecordingInvoker(handler)
        client = SoridormiTaskClient(invoker, default_poll_interval_s=0.0, sleep=_no_sleep)

        output = await client.monitor_until_terminal(task_id="soridormi-task-1")

        self.assertTrue(output["terminal"])
        self.assertEqual(
            [call[1]["after_sequence"] for call in invoker.calls],
            [0, 3],
        )

    async def test_monitor_timeout_preserves_last_events(self) -> None:
        def handler(
            tool_name: str,
            args: dict[str, Any],
            context: ToolInvocationContext | None,
        ) -> ToolCallOutcome:
            self.assertEqual(tool_name, "soridormi.task.events")
            return ToolCallOutcome.success(
                {
                    "task_id": "soridormi-task-1",
                    "terminal": False,
                    "next_after_sequence": args["after_sequence"] + 1,
                    "poll_recommendation": {
                        "action": "continue_polling_or_cancel",
                        "recommended_poll_interval_s": 0.0,
                    },
                }
            )

        client = SoridormiTaskClient(
            RecordingInvoker(handler),
            default_poll_interval_s=0.0,
            sleep=_no_sleep,
        )

        with self.assertRaises(SoridormiTaskMonitorTimeout) as caught:
            await client.monitor_until_terminal(task_id="soridormi-task-1", max_polls=2)

        self.assertEqual(caught.exception.last_events["next_after_sequence"], 2)

    async def test_cancel_uses_safety_control_authorization(self) -> None:
        def handler(
            tool_name: str,
            args: dict[str, Any],
            context: ToolInvocationContext | None,
        ) -> ToolCallOutcome:
            self.assertEqual(tool_name, "soridormi.task.cancel")
            self.assertEqual(args["reason"], "stop now")
            self.assertIsNotNone(context)
            assert context is not None
            self.assertTrue(context.allow_safety_controls)
            return ToolCallOutcome.success(
                {
                    "task_id": "soridormi-task-1",
                    "cancelled": True,
                    "terminal": True,
                }
            )

        client = SoridormiTaskClient(RecordingInvoker(handler), sleep=_no_sleep)

        output = await client.cancel(task_id="soridormi-task-1", reason="stop now")

        self.assertTrue(output["cancelled"])

    async def test_tool_failure_raises_client_error(self) -> None:
        def handler(
            tool_name: str,
            args: dict[str, Any],
            context: ToolInvocationContext | None,
        ) -> ToolCallOutcome:
            return ToolCallOutcome.failed("provider disconnected", retryable=True)

        client = SoridormiTaskClient(RecordingInvoker(handler), sleep=_no_sleep)

        with self.assertRaises(SoridormiTaskClientError) as caught:
            await client.status(task_id="soridormi-task-1")

        self.assertEqual(caught.exception.tool_name, "soridormi.task.status")
        self.assertIn("provider disconnected", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
