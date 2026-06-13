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


if __name__ == "__main__":
    unittest.main()
