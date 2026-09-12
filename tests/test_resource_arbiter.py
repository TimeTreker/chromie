from __future__ import annotations

import asyncio
import unittest

from shared.chromie_runtime import ResourceArbiter


class ResourceArbiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounds_parallel_work(self) -> None:
        arbiter = ResourceArbiter(2)
        active = 0
        peak = 0

        async def run() -> None:
            nonlocal active, peak
            async with arbiter.claim():
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.02)
                active -= 1

        await asyncio.gather(*(run() for _ in range(5)))

        self.assertEqual(peak, 2)
        self.assertEqual(arbiter.active_count, 0)

    async def test_non_parallel_claim_excludes_parallel_work(self) -> None:
        arbiter = ResourceArbiter(3)
        active: set[str] = set()
        overlaps: list[set[str]] = []

        async def run(name: str, can_run_parallel: bool) -> None:
            async with arbiter.claim(can_run_parallel=can_run_parallel):
                active.add(name)
                overlaps.append(set(active))
                await asyncio.sleep(0.02)
                active.remove(name)

        await asyncio.gather(
            run("parallel-a", True),
            run("serial", False),
            run("parallel-b", True),
        )

        self.assertFalse(
            any("serial" in snapshot and len(snapshot) > 1 for snapshot in overlaps)
        )

    async def test_exclusive_group_serializes_matching_claims(self) -> None:
        arbiter = ResourceArbiter(3)
        active_group = 0
        peak_group = 0

        async def run() -> None:
            nonlocal active_group, peak_group
            async with arbiter.claim(exclusive_group="robot_motion"):
                active_group += 1
                peak_group = max(peak_group, active_group)
                await asyncio.sleep(0.02)
                active_group -= 1

        await asyncio.gather(run(), run(), run())

        self.assertEqual(peak_group, 1)

    async def test_queued_non_parallel_work_is_not_starved(self) -> None:
        arbiter = ResourceArbiter(2)
        release_first = asyncio.Event()
        order: list[str] = []

        async def first_parallel() -> None:
            async with arbiter.claim():
                order.append("first")
                await release_first.wait()

        async def serial() -> None:
            async with arbiter.claim(can_run_parallel=False):
                order.append("serial")
                await asyncio.sleep(0)

        async def late_parallel() -> None:
            async with arbiter.claim():
                order.append("late")

        first = asyncio.create_task(first_parallel())
        while order != ["first"]:
            await asyncio.sleep(0)
        serial_task = asyncio.create_task(serial())
        await asyncio.sleep(0)
        late = asyncio.create_task(late_parallel())
        release_first.set()
        await asyncio.gather(first, serial_task, late)

        self.assertEqual(order, ["first", "serial", "late"])

    async def test_resource_set_waiter_holds_neither_capacity_nor_partial_resources(self) -> None:
        arbiter = ResourceArbiter(2)
        release = asyncio.Event()
        entered = asyncio.Event()

        async def blocked() -> None:
            async with arbiter.claim(resource_claims=["free", "busy", "free"]):
                entered.set()
                await release.wait()

        async with arbiter.claim(resource_claims=["busy"]):
            waiter = asyncio.create_task(blocked())
            try:
                async with asyncio.timeout(1):
                    while arbiter.snapshot().waiting_count != 1:
                        await asyncio.sleep(0)
                    async with arbiter.claim(resource_claims=["free"]):
                        self.assertFalse(entered.is_set())
                        self.assertEqual(arbiter.active_count, 2)
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
                self.assertEqual(arbiter.snapshot().waiting_count, 0)
                self.assertEqual(arbiter.active_count, 1)
            finally:
                release.set()
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
        async with arbiter.claim(resource_claims=["busy", "free"]):
            self.assertEqual(arbiter.active_count, 1)
        self.assertEqual(arbiter.active_count, 0)

    async def test_overlapping_sets_in_reverse_order_are_deadlock_free(self) -> None:
        arbiter = ResourceArbiter(3)
        active = 0
        peak = 0

        async def run(resources: list[str]) -> None:
            nonlocal active, peak
            async with arbiter.claim(resource_claims=resources):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0)
                active -= 1

        async with asyncio.timeout(1):
            await asyncio.gather(
                run(["a", "b"]), run(["b", "a"]), run(["b", "c"])
            )
        self.assertEqual(peak, 1)
        self.assertEqual(arbiter.snapshot().waiting_count, 0)

    async def test_cancelling_serial_waiter_unblocks_disjoint_parallel_work(self) -> None:
        arbiter = ResourceArbiter(3)

        async def serial() -> None:
            async with arbiter.claim(can_run_parallel=False):
                self.fail("serial work must not start beside an active claim")

        async with arbiter.claim(resource_claims=["a"]):
            waiter = asyncio.create_task(serial())
            try:
                async with asyncio.timeout(1):
                    while arbiter.snapshot().serial_waiters != 1:
                        await asyncio.sleep(0)
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
                async with asyncio.timeout(1):
                    async with arbiter.claim(resource_claims=["b"]):
                        self.assertEqual(arbiter.active_count, 2)
            finally:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
        self.assertEqual(arbiter.snapshot().serial_waiters, 0)

    async def test_active_cancellation_and_exception_release_every_resource(self) -> None:
        arbiter = ResourceArbiter(1)
        started = asyncio.Event()

        async def run() -> None:
            async with arbiter.claim(resource_claims=["a", "b"]):
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        try:
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaisesRegex(ValueError, "provider failure"):
                async with asyncio.timeout(1):
                    async with arbiter.claim(resource_claims=["b", "a"]):
                        raise ValueError("provider failure")
            async with asyncio.timeout(1):
                async with arbiter.claim(resource_claims=["a", "b"]):
                    self.assertEqual(arbiter.active_count, 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(arbiter.active_count, 0)


if __name__ == "__main__":
    unittest.main()
