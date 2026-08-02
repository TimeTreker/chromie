from __future__ import annotations

import asyncio
import unittest

from orchestrator.runtime.outcome_delivery import OutcomeDeliveryCoordinator


class OutcomeDeliveryCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def test_only_completed_distinct_session_is_ordinary_overlap(self) -> None:
        self.assertTrue(
            OutcomeDeliveryCoordinator.is_ordinary_overlap(
                origin_session_id="old",
                current_session_id="new",
                generation_changed=True,
                execution_status="completed",
                aggregate_status="completed",
            )
        )
        self.assertFalse(
            OutcomeDeliveryCoordinator.is_ordinary_overlap(
                origin_session_id="old",
                current_session_id="old",
                generation_changed=True,
                execution_status="completed",
                aggregate_status="completed",
            )
        )
        self.assertFalse(
            OutcomeDeliveryCoordinator.is_ordinary_overlap(
                origin_session_id="old",
                current_session_id="new",
                generation_changed=True,
                execution_status="cancelled",
                aggregate_status="cancelled",
            )
        )

    async def test_waits_for_foreground_turn_and_output_to_be_idle(self) -> None:
        state = {"current": "new", "done": False, "idle": False, "valid": True}
        coordinator = OutcomeDeliveryCoordinator(
            current_session_id=lambda: state["current"],
            session_done=lambda sid: bool(state["done"]),
            output_idle=lambda: bool(state["idle"]),
            goals_deliverable=lambda goal_ids: bool(state["valid"]),
            poll_interval_s=0.001,
        )

        async def release() -> None:
            await asyncio.sleep(0.005)
            state["done"] = True
            state["idle"] = True

        asyncio.create_task(release())
        result = await coordinator.wait_for_window(
            origin_session_id="old",
            source_goal_ids=("goal-one",),
            timeout_s=0.1,
        )
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.waited_for_session_ids, ("new",))

    async def test_goal_invalidation_suppresses_before_delivery(self) -> None:
        coordinator = OutcomeDeliveryCoordinator(
            current_session_id=lambda: "new",
            session_done=lambda sid: False,
            output_idle=lambda: False,
            goals_deliverable=lambda goal_ids: False,
            poll_interval_s=0.001,
        )
        result = await coordinator.wait_for_window(
            origin_session_id="old",
            source_goal_ids=("goal-one",),
            timeout_s=0.1,
        )
        self.assertEqual(result.status, "goal_invalidated")


if __name__ == "__main__":
    unittest.main()
